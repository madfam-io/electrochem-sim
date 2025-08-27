from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import asyncio
import uuid
import logging

# Import local modules
from services.api.config import settings
from services.api.models import (
    RunStatus, RunType, SimulationEngine,
    CreateRunRequest, UpdateRunRequest,
    RunResponse, ScenarioCreate
)
from services.api.auth import (
    authenticate_user, create_access_token,
    get_current_active_user, require_user,
    Token, User, ACCESS_TOKEN_EXPIRE_MINUTES
)
from services.api.middleware import setup_middleware, create_rate_limit
from services.api.exceptions import (
    register_exception_handlers,
    ResourceNotFoundException,
    SimulationException,
    ValidationException
)
from services.api.logging_config import setup_logging, get_logger

# Configure logging
setup_logging()
logger = get_logger(__name__)


class RunHandle(BaseModel):
    """Simplified response for run creation"""
    run_id: str
    status: RunStatus
    queue_position: Optional[int] = None
    estimated_start: Optional[datetime] = None
    stream_url: str


class Run(BaseModel):
    id: str
    type: RunType
    status: RunStatus
    scenario_id: Optional[str]
    engine: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    progress: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    tags: List[str] = Field(default_factory=list)


class Scenario(BaseModel):
    id: str
    name: str
    version: str = "0.1"
    description: Optional[str] = None
    physics: Dict[str, Any]
    geometry: Dict[str, Any]
    materials: Dict[str, Any]
    boundaries: Dict[str, Any]
    drive: Dict[str, Any]
    numerics: Dict[str, Any]
    outputs: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class HealthCheck(BaseModel):
    status: str = "healthy"
    timestamp: datetime
    services: Dict[str, str]


# In-memory storage for MVP
runs_store: Dict[str, Run] = {}
scenarios_store: Dict[str, Scenario] = {}
run_queue: List[str] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Galvana API...")
    # Initialize background tasks
    asyncio.create_task(process_run_queue())
    yield
    logger.info("Shutting down Galvana API...")


app = FastAPI(
    title="Galvana API",
    description="Phygital Electrochemistry Platform API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.environment != "production" else None,
    redoc_url="/api/redoc" if settings.environment != "production" else None,
)

# Setup all middleware (CORS, security, rate limiting, etc.)
setup_middleware(app)

# Register exception handlers
register_exception_handlers(app)


@app.post("/api/v1/auth/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Authenticate and receive access token"""
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/api/v1/auth/me", response_model=User)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """Get current user information"""
    return current_user


@app.get("/health", response_model=HealthCheck)
async def health_check():
    return HealthCheck(
        timestamp=datetime.utcnow(),
        services={
            "api": "healthy",
            "database": "healthy",
            "redis": "healthy",
        }
    )


@app.post("/api/v1/runs", response_model=RunHandle, status_code=202)
async def create_run(
    request: CreateRunRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user)
):
    """Create and queue a new simulation run"""
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    
    run = Run(
        id=run_id,
        type=request.type,
        status=RunStatus.QUEUED,
        scenario_id=request.scenario_id,
        engine=request.engine.value,
        created_at=datetime.utcnow(),
        tags=request.tags
    )
    
    runs_store[run_id] = run
    run_queue.append(run_id)
    
    return RunHandle(
        run_id=run_id,
        status=RunStatus.QUEUED,
        queue_position=len(run_queue),
        stream_url=f"/api/v1/runs/{run_id}/stream"
    )


@app.get("/api/v1/runs", response_model=List[Run])
async def list_runs(
    status: Optional[RunStatus] = None,
    limit: int = 20,
    current_user: User = Depends(get_current_active_user)
):
    """List runs with optional filtering"""
    runs = list(runs_store.values())
    
    if status:
        runs = [r for r in runs if r.status == status]
    
    return sorted(runs, key=lambda r: r.created_at, reverse=True)[:limit]


@app.get("/api/v1/runs/{run_id}", response_model=Run)
async def get_run(
    run_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """Get run details"""
    if run_id not in runs_store:
        raise ResourceNotFoundException("Run", run_id)
    
    return runs_store[run_id]


@app.patch("/api/v1/runs/{run_id}")
async def update_run(run_id: str, action: str, reason: Optional[str] = None):
    """Update run status (pause/resume/abort)"""
    if run_id not in runs_store:
        raise HTTPException(404, "Run not found")
    
    run = runs_store[run_id]
    
    if action == "pause" and run.status == RunStatus.RUNNING:
        run.status = RunStatus.PAUSED
    elif action == "resume" and run.status == RunStatus.PAUSED:
        run.status = RunStatus.RUNNING
    elif action == "abort":
        run.status = RunStatus.ABORTED
        run.completed_at = datetime.utcnow()
        if reason:
            run.error = {"message": reason}
    else:
        raise HTTPException(400, f"Invalid action {action} for status {run.status}")
    
    return run


@app.post("/api/v1/scenarios", response_model=Scenario, status_code=201)
async def create_scenario(scenario_data: Dict[str, Any]):
    """Create or update a scenario"""
    scenario_id = f"scn_{uuid.uuid4().hex[:12]}"
    
    scenario = Scenario(
        id=scenario_id,
        name=scenario_data.get("name", "Unnamed Scenario"),
        version=scenario_data.get("version", "0.1"),
        description=scenario_data.get("description"),
        physics=scenario_data.get("physics", {
            "transport": "nernst_planck",
            "electroneutral": True,
            "potential_model": "poisson"
        }),
        geometry=scenario_data.get("geometry", {
            "type": "1D",
            "length": 1e-3
        }),
        materials=scenario_data.get("materials", {}),
        boundaries=scenario_data.get("boundaries", {}),
        drive=scenario_data.get("drive", {
            "mode": "potentiostatic",
            "waveform": {"type": "step", "V": -0.8, "t_end": 120.0}
        }),
        numerics=scenario_data.get("numerics", {
            "time_integrator": "BDF",
            "dt_initial": 1e-3
        }),
        outputs=scenario_data.get("outputs", {
            "save": ["current_density", "potential"],
            "cadence": 0.1
        }),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    scenarios_store[scenario_id] = scenario
    
    return scenario


@app.get("/api/v1/scenarios", response_model=List[Scenario])
async def list_scenarios(limit: int = 20):
    """List available scenarios"""
    scenarios = list(scenarios_store.values())
    return sorted(scenarios, key=lambda s: s.created_at, reverse=True)[:limit]


@app.get("/api/v1/scenarios/{scenario_id}", response_model=Scenario)
async def get_scenario(scenario_id: str):
    """Get scenario details"""
    if scenario_id not in scenarios_store:
        raise HTTPException(404, "Scenario not found")
    
    return scenarios_store[scenario_id]


async def process_run_queue():
    """Background task to process queued runs"""
    while True:
        if run_queue:
            run_id = run_queue.pop(0)
            if run_id in runs_store:
                run = runs_store[run_id]
                run.status = RunStatus.STARTING
                run.started_at = datetime.utcnow()
                
                # Simulate processing
                await asyncio.sleep(2)
                run.status = RunStatus.RUNNING
                
                # Simulate completion
                await asyncio.sleep(5)
                run.status = RunStatus.COMPLETED
                run.completed_at = datetime.utcnow()
                run.progress = {"percentage": 100, "timesteps": 1000}
                
                logger.info(f"Completed run {run_id}")
        
        await asyncio.sleep(1)


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": f"HTTP_{exc.status_code}",
                "message": exc.detail
            }
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080, reload=True)