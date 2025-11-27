"""
Pydantic models with proper validation for API endpoints
"""

from pydantic import BaseModel, Field, validator, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import re

class RunStatus(str, Enum):
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"

class RunType(str, Enum):
    SIMULATION = "simulation"
    EXPERIMENT = "experiment"

class SimulationEngine(str, Enum):
    AUTO = "auto"
    FENICSX = "fenicsx"
    MOOSE = "moose"

class TransportModel(str, Enum):
    NERNST_PLANCK = "nernst_planck"
    STEFAN_MAXWELL = "stefan_maxwell"

class CreateRunRequest(BaseModel):
    """Validated request for creating a run"""
    type: RunType = RunType.SIMULATION
    scenario_id: Optional[str] = Field(None, pattern="^scn_[a-zA-Z0-9]+$")
    scenario_yaml: Optional[str] = Field(None, max_length=50000)
    engine: SimulationEngine = SimulationEngine.AUTO
    tags: List[str] = Field(default_factory=list, max_items=20)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    @validator('tags')
    def validate_tags(cls, v):
        for tag in v:
            if not re.match(r'^[a-zA-Z0-9_-]+$', tag):
                raise ValueError(f"Invalid tag format: {tag}")
            if len(tag) > 50:
                raise ValueError(f"Tag too long: {tag}")
        return v
    
    @validator('scenario_id', 'scenario_yaml')
    def validate_scenario(cls, v, values):
        if not v and not values.get('scenario_yaml'):
            raise ValueError("Either scenario_id or scenario_yaml must be provided")
        return v

class UpdateRunRequest(BaseModel):
    """Validated request for updating a run"""
    action: str = Field(..., pattern="^(pause|resume|abort)$")
    reason: Optional[str] = Field(None, max_length=500)
    
    @validator('reason')
    def reason_required_for_abort(cls, v, values):
        if values.get('action') == 'abort' and not v:
            raise ValueError("Reason is required for abort action")
        return v

class PhysicsConfig(BaseModel):
    """Physics configuration with validation"""
    transport: TransportModel = TransportModel.NERNST_PLANCK
    electroneutral: bool = True
    potential_model: str = Field("poisson", pattern="^(poisson|none|simplified)$")
    heat_coupling: bool = False
    phase_field: bool = False
    
    @validator('potential_model')
    def validate_potential_model(cls, v, values):
        if values.get('transport') == TransportModel.STEFAN_MAXWELL and v == 'none':
            raise ValueError("Stefan-Maxwell requires potential model")
        return v

class GeometryConfig(BaseModel):
    """Geometry configuration with validation"""
    type: str = Field(..., pattern="^(1D|2D|3D)$")
    length: float = Field(..., gt=0, le=1.0, description="Length in meters")
    width: Optional[float] = Field(None, gt=0, le=1.0)
    height: Optional[float] = Field(None, gt=0, le=1.0)
    mesh: Dict[str, Any] = Field(default_factory=dict)
    
    @validator('mesh')
    def validate_mesh(cls, v):
        elements = v.get('elements', 100)
        if not isinstance(elements, int) or elements < 10 or elements > 10000:
            raise ValueError("Mesh elements must be between 10 and 10000")
        return v

class KineticsConfig(BaseModel):
    """Kinetics configuration with validation"""
    model: str = Field("butler_volmer", pattern="^(butler_volmer|marcus_hush|linear)$")
    exchange_current_density: float = Field(..., gt=0, le=1000)
    alpha_a: float = Field(0.5, ge=0, le=1)
    alpha_c: float = Field(0.5, ge=0, le=1)
    film_resistance: float = Field(0, ge=0, le=1000)
    
    @validator('alpha_c')
    def validate_alphas(cls, v, values):
        alpha_a = values.get('alpha_a', 0.5)
        if abs(alpha_a + v - 1.0) > 0.01:
            raise ValueError("Sum of transfer coefficients should be approximately 1")
        return v

class Species(BaseModel):
    """Chemical species with validation"""
    name: str = Field(..., min_length=1, max_length=50)
    D: float = Field(..., gt=0, le=1e-6, description="Diffusivity in m²/s")
    z: int = Field(..., ge=-5, le=5, description="Charge")
    c0: float = Field(1.0, gt=0, le=10000, description="Initial concentration in mol/m³")

class MaterialsConfig(BaseModel):
    """Materials configuration with validation"""
    electrolyte: Dict[str, Any]
    electrode: Optional[Dict[str, Any]] = None
    
    @validator('electrolyte')
    def validate_electrolyte(cls, v):
        species = v.get('species', [])
        if not species:
            raise ValueError("At least one species must be defined")
        
        # Validate each species
        validated_species = []
        for s in species:
            if isinstance(s, dict):
                validated_species.append(Species(**s).dict())
            else:
                validated_species.append(s)
        v['species'] = validated_species
        
        # Check electroneutrality
        total_charge = sum(s.get('z', 0) * s.get('c0', 1) for s in validated_species)
        if abs(total_charge) > 0.1:
            raise ValueError("Initial electroneutrality not satisfied")
        
        return v

class DriveConfig(BaseModel):
    """Drive configuration with validation"""
    mode: str = Field(..., pattern="^(potentiostatic|galvanostatic|potentiodynamic)$")
    waveform: Dict[str, Any]
    
    @validator('waveform')
    def validate_waveform(cls, v, values):
        wave_type = v.get('type')
        if wave_type not in ['step', 'ramp', 'sine', 'cv', 'pulse']:
            raise ValueError(f"Invalid waveform type: {wave_type}")
        
        # Validate voltage/current limits
        if values.get('mode') == 'potentiostatic':
            voltage = v.get('V', 0)
            if abs(voltage) > 10:
                raise ValueError("Voltage must be between -10V and 10V")
        
        # Validate time
        t_end = v.get('t_end', 0)
        if t_end <= 0 or t_end > 86400:  # Max 24 hours
            raise ValueError("Duration must be between 0 and 86400 seconds")
        
        return v

class NumericsConfig(BaseModel):
    """Numerics configuration with validation"""
    time_integrator: str = Field("BDF", pattern="^(BDF|SDIRK|implicit_euler|explicit_euler)$")
    dt_initial: float = Field(1e-3, gt=1e-10, le=1)
    dt_max: float = Field(0.1, gt=1e-10, le=10)
    tolerance: float = Field(1e-6, gt=1e-12, le=1e-2)
    newton_tol: Optional[float] = Field(1e-8, gt=1e-12, le=1e-4)
    linear_solver: Optional[str] = Field("gmres", pattern="^(gmres|bicgstab|direct)$")
    
    @validator('dt_max')
    def validate_dt(cls, v, values):
        dt_initial = values.get('dt_initial', 1e-3)
        if v < dt_initial:
            raise ValueError("dt_max must be greater than dt_initial")
        return v

class OutputsConfig(BaseModel):
    """Outputs configuration with validation"""
    save: List[str] = Field(..., min_items=1, max_items=20)
    cadence: float = Field(0.1, gt=0, le=10)
    format: str = Field("json", pattern="^(json|hdf5|netcdf|csv|zarr)$")
    
    @validator('save')
    def validate_outputs(cls, v):
        valid_outputs = {
            'current_density', 'concentration', 'potential', 'temperature',
            'pressure', 'velocity', 'electric_field', 'flux'
        }
        for output in v:
            # Parse output like "concentration(Ni2+)"
            base_output = output.split('(')[0]
            if base_output not in valid_outputs:
                raise ValueError(f"Invalid output type: {base_output}")
        return v

class ScenarioCreate(BaseModel):
    """Create scenario with full validation"""
    name: str = Field(..., min_length=1, max_length=200)
    version: str = Field("0.1", pattern=r"^\d+\.\d+(\.\d+)?$")
    description: Optional[str] = Field(None, max_length=1000)
    physics: PhysicsConfig
    geometry: GeometryConfig
    materials: MaterialsConfig
    boundaries: Dict[str, Any]  # Complex validation would be added
    drive: DriveConfig
    numerics: NumericsConfig
    outputs: OutputsConfig
    tags: List[str] = Field(default_factory=list, max_items=20)
    
    @validator('name')
    def sanitize_name(cls, v):
        # Remove any potential XSS/injection characters
        v = re.sub(r'[<>\"\'&]', '', v)
        return v.strip()

class RunResponse(BaseModel):
    """Run response with proper typing"""
    id: str
    type: RunType
    status: RunStatus
    scenario_id: Optional[str]
    engine: str
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    progress: Optional[Dict[str, Any]]
    error: Optional[Dict[str, str]]
    tags: List[str]
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

# User management models
class User(BaseModel):
    """User model"""
    id: str
    username: str
    email: EmailStr
    full_name: Optional[str]
    role: str = "user"
    is_active: bool = True
    is_superuser: bool = False

class UserCreate(BaseModel):
    """User creation model"""
    username: str = Field(..., min_length=3, max_length=50, pattern="^[a-zA-Z0-9_-]+$")
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    full_name: Optional[str] = Field(None, max_length=255)
    role: Optional[str] = Field("user", pattern="^(user|researcher|admin|superuser)$")
    is_superuser: Optional[bool] = False
    
    @validator('password')
    def validate_password_strength(cls, v):
        """Ensure password meets security requirements"""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v

class UserUpdate(BaseModel):
    """User update model"""
    full_name: Optional[str] = Field(None, max_length=255)
    email: Optional[EmailStr]
    role: Optional[str] = Field(None, pattern="^(user|researcher|admin|superuser)$")
    is_active: Optional[bool]

class PasswordChange(BaseModel):
    """Password change model"""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)
    
    @validator('new_password')
    def validate_password_strength(cls, v, values):
        """Ensure new password meets requirements and differs from current"""
        if 'current_password' in values and v == values['current_password']:
            raise ValueError("New password must be different from current password")
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v

class Token(BaseModel):
    """Token response model"""
    access_token: str
    refresh_token: Optional[str]
    token_type: str = "bearer"
    expires_in: int