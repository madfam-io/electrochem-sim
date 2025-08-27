"""
Test Pydantic models and validation
"""

import pytest
from pydantic import ValidationError
from services.api.models import (
    CreateRunRequest,
    UpdateRunRequest,
    PhysicsConfig,
    GeometryConfig,
    KineticsConfig,
    Species,
    MaterialsConfig,
    DriveConfig,
    NumericsConfig,
    OutputsConfig,
    ScenarioCreate,
    RunStatus,
    RunType,
    SimulationEngine,
    TransportModel
)

def test_create_run_request_validation():
    """Test CreateRunRequest validation"""
    # Valid request with scenario_yaml
    request = CreateRunRequest(
        type=RunType.SIMULATION,
        scenario_yaml="valid yaml content",
        engine=SimulationEngine.AUTO,
        tags=["test", "valid-tag"],
        metadata={"key": "value"}
    )
    assert request.type == RunType.SIMULATION
    assert request.scenario_yaml == "valid yaml content"
    
    # Valid request with scenario_id
    request = CreateRunRequest(
        scenario_id="scn_abc123",
        type=RunType.EXPERIMENT
    )
    assert request.scenario_id == "scn_abc123"
    
    # Invalid: neither scenario_id nor scenario_yaml
    with pytest.raises(ValidationError) as exc_info:
        CreateRunRequest(type=RunType.SIMULATION)
    assert "scenario_id or scenario_yaml must be provided" in str(exc_info.value)
    
    # Invalid scenario_id format
    with pytest.raises(ValidationError) as exc_info:
        CreateRunRequest(scenario_id="invalid_format")
    assert "string does not match regex" in str(exc_info.value)
    
    # Invalid tag format
    with pytest.raises(ValidationError) as exc_info:
        CreateRunRequest(
            scenario_yaml="content",
            tags=["valid", "invalid tag with spaces"]
        )
    assert "Invalid tag format" in str(exc_info.value)
    
    # Tag too long
    with pytest.raises(ValidationError) as exc_info:
        CreateRunRequest(
            scenario_yaml="content",
            tags=["a" * 51]
        )
    assert "Tag too long" in str(exc_info.value)

def test_update_run_request_validation():
    """Test UpdateRunRequest validation"""
    # Valid pause request
    request = UpdateRunRequest(action="pause")
    assert request.action == "pause"
    assert request.reason is None
    
    # Valid abort with reason
    request = UpdateRunRequest(action="abort", reason="User requested")
    assert request.action == "abort"
    assert request.reason == "User requested"
    
    # Invalid: abort without reason
    with pytest.raises(ValidationError) as exc_info:
        UpdateRunRequest(action="abort")
    assert "Reason is required for abort action" in str(exc_info.value)
    
    # Invalid action
    with pytest.raises(ValidationError) as exc_info:
        UpdateRunRequest(action="invalid")
    assert "string does not match regex" in str(exc_info.value)

def test_physics_config_validation():
    """Test PhysicsConfig validation"""
    # Valid config
    config = PhysicsConfig(
        transport=TransportModel.NERNST_PLANCK,
        electroneutral=True,
        potential_model="poisson"
    )
    assert config.transport == TransportModel.NERNST_PLANCK
    
    # Invalid: Stefan-Maxwell without potential model
    with pytest.raises(ValidationError) as exc_info:
        PhysicsConfig(
            transport=TransportModel.STEFAN_MAXWELL,
            potential_model="none"
        )
    assert "Stefan-Maxwell requires potential model" in str(exc_info.value)
    
    # Invalid potential model
    with pytest.raises(ValidationError) as exc_info:
        PhysicsConfig(potential_model="invalid")
    assert "string does not match regex" in str(exc_info.value)

def test_geometry_config_validation():
    """Test GeometryConfig validation"""
    # Valid 1D geometry
    config = GeometryConfig(type="1D", length=0.001)
    assert config.type == "1D"
    assert config.length == 0.001
    
    # Valid 3D geometry
    config = GeometryConfig(
        type="3D",
        length=0.01,
        width=0.005,
        height=0.002,
        mesh={"elements": 500}
    )
    assert config.type == "3D"
    
    # Invalid: negative length
    with pytest.raises(ValidationError) as exc_info:
        GeometryConfig(type="1D", length=-0.001)
    assert "ensure this value is greater than 0" in str(exc_info.value)
    
    # Invalid: length too large
    with pytest.raises(ValidationError) as exc_info:
        GeometryConfig(type="1D", length=1.5)
    assert "ensure this value is less than or equal to 1" in str(exc_info.value)
    
    # Invalid mesh elements
    with pytest.raises(ValidationError) as exc_info:
        GeometryConfig(type="1D", length=0.001, mesh={"elements": 5})
    assert "Mesh elements must be between 10 and 10000" in str(exc_info.value)

def test_kinetics_config_validation():
    """Test KineticsConfig validation"""
    # Valid config
    config = KineticsConfig(
        model="butler_volmer",
        exchange_current_density=10.0,
        alpha_a=0.3,
        alpha_c=0.7
    )
    assert config.model == "butler_volmer"
    
    # Invalid: transfer coefficients don't sum to 1
    with pytest.raises(ValidationError) as exc_info:
        KineticsConfig(
            exchange_current_density=10.0,
            alpha_a=0.3,
            alpha_c=0.3
        )
    assert "Sum of transfer coefficients should be approximately 1" in str(exc_info.value)
    
    # Invalid model
    with pytest.raises(ValidationError) as exc_info:
        KineticsConfig(
            model="invalid",
            exchange_current_density=10.0
        )
    assert "string does not match regex" in str(exc_info.value)

def test_species_validation():
    """Test Species validation"""
    # Valid species
    species = Species(
        name="Ni2+",
        D=6.7e-10,
        z=2,
        c0=100.0
    )
    assert species.name == "Ni2+"
    assert species.z == 2
    
    # Invalid: charge too large
    with pytest.raises(ValidationError) as exc_info:
        Species(name="X", D=1e-9, z=6, c0=1.0)
    assert "ensure this value is less than or equal to 5" in str(exc_info.value)
    
    # Invalid: negative diffusivity
    with pytest.raises(ValidationError) as exc_info:
        Species(name="X", D=-1e-9, z=1, c0=1.0)
    assert "ensure this value is greater than 0" in str(exc_info.value)

def test_materials_config_validation():
    """Test MaterialsConfig validation"""
    # Valid config
    config = MaterialsConfig(
        electrolyte={
            "species": [
                {"name": "Na+", "D": 1e-9, "z": 1, "c0": 50.0},
                {"name": "Cl-", "D": 2e-9, "z": -1, "c0": 50.0}
            ]
        }
    )
    assert len(config.electrolyte["species"]) == 2
    
    # Invalid: no species
    with pytest.raises(ValidationError) as exc_info:
        MaterialsConfig(electrolyte={"species": []})
    assert "At least one species must be defined" in str(exc_info.value)
    
    # Invalid: electroneutrality violation
    with pytest.raises(ValidationError) as exc_info:
        MaterialsConfig(
            electrolyte={
                "species": [
                    {"name": "Na+", "D": 1e-9, "z": 1, "c0": 100.0},
                    {"name": "Cl-", "D": 2e-9, "z": -1, "c0": 50.0}
                ]
            }
        )
    assert "Initial electroneutrality not satisfied" in str(exc_info.value)

def test_drive_config_validation():
    """Test DriveConfig validation"""
    # Valid potentiostatic
    config = DriveConfig(
        mode="potentiostatic",
        waveform={
            "type": "step",
            "V": -2.0,
            "t_end": 100.0
        }
    )
    assert config.mode == "potentiostatic"
    
    # Invalid: voltage too high
    with pytest.raises(ValidationError) as exc_info:
        DriveConfig(
            mode="potentiostatic",
            waveform={"type": "step", "V": 15.0, "t_end": 100.0}
        )
    assert "Voltage must be between -10V and 10V" in str(exc_info.value)
    
    # Invalid: duration too long
    with pytest.raises(ValidationError) as exc_info:
        DriveConfig(
            mode="galvanostatic",
            waveform={"type": "step", "I": 1.0, "t_end": 100000.0}
        )
    assert "Duration must be between 0 and 86400 seconds" in str(exc_info.value)
    
    # Invalid waveform type
    with pytest.raises(ValidationError) as exc_info:
        DriveConfig(
            mode="potentiostatic",
            waveform={"type": "invalid", "V": 1.0, "t_end": 100.0}
        )
    assert "Invalid waveform type" in str(exc_info.value)

def test_scenario_create_validation():
    """Test ScenarioCreate validation"""
    # Valid scenario
    scenario = ScenarioCreate(
        name="Test Scenario",
        version="0.1.0",
        physics=PhysicsConfig(),
        geometry=GeometryConfig(type="1D", length=0.001),
        materials=MaterialsConfig(
            electrolyte={
                "species": [
                    {"name": "H+", "D": 9e-9, "z": 1, "c0": 1.0},
                    {"name": "OH-", "D": 5e-9, "z": -1, "c0": 1.0}
                ]
            }
        ),
        boundaries={},
        drive=DriveConfig(
            mode="potentiostatic",
            waveform={"type": "step", "V": -0.8, "t_end": 100.0}
        ),
        numerics=NumericsConfig(),
        outputs=OutputsConfig(save=["current_density"])
    )
    assert scenario.name == "Test Scenario"
    assert scenario.version == "0.1.0"
    
    # Test name sanitization (XSS prevention)
    scenario = ScenarioCreate(
        name="<script>alert('xss')</script>Test",
        version="0.1",
        physics=PhysicsConfig(),
        geometry=GeometryConfig(type="1D", length=0.001),
        materials=MaterialsConfig(
            electrolyte={"species": [{"name": "H+", "D": 9e-9, "z": 1, "c0": 1.0}]}
        ),
        boundaries={},
        drive=DriveConfig(
            mode="potentiostatic",
            waveform={"type": "step", "V": -0.8, "t_end": 100.0}
        ),
        numerics=NumericsConfig(),
        outputs=OutputsConfig(save=["current_density"])
    )
    assert "<script>" not in scenario.name
    assert "Test" in scenario.name