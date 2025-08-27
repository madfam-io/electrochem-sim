"""
Pytest configuration and fixtures
"""

import pytest
import asyncio
from typing import Generator, Dict
from fastapi.testclient import TestClient
from services.api.main import app
from services.api.auth import create_access_token

@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Create a test client"""
    with TestClient(app) as test_client:
        yield test_client

@pytest.fixture
def auth_headers() -> Dict[str, str]:
    """Create authentication headers for testing"""
    token = create_access_token(data={"sub": "demo_user"})
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def sample_scenario() -> dict:
    """Sample scenario for testing"""
    return {
        "name": "Test Electrodeposition",
        "version": "0.1",
        "description": "Test scenario for unit tests",
        "physics": {
            "transport": "nernst_planck",
            "electroneutral": True,
            "potential_model": "poisson",
            "heat_coupling": False,
            "phase_field": False
        },
        "geometry": {
            "type": "1D",
            "length": 0.001,
            "mesh": {"elements": 100}
        },
        "materials": {
            "electrolyte": {
                "species": [
                    {"name": "Ni2+", "D": 6.7e-10, "z": 2, "c0": 100.0}
                ]
            }
        },
        "boundaries": {
            "electrode": {
                "type": "robin",
                "location": "left"
            },
            "bulk": {
                "type": "dirichlet",
                "location": "right"
            }
        },
        "kinetics": {
            "model": "butler_volmer",
            "exchange_current_density": 2.0,
            "alpha_a": 0.5,
            "alpha_c": 0.5
        },
        "drive": {
            "mode": "potentiostatic",
            "waveform": {
                "type": "step",
                "V": -0.8,
                "t_end": 10.0
            }
        },
        "numerics": {
            "time_integrator": "BDF",
            "dt_initial": 0.001,
            "dt_max": 0.1,
            "tolerance": 1e-6
        },
        "outputs": {
            "save": ["current_density", "concentration", "potential"],
            "cadence": 0.1,
            "format": "json"
        }
    }

@pytest.fixture
def sample_run_request() -> dict:
    """Sample run request for testing"""
    return {
        "type": "simulation",
        "scenario_yaml": "test scenario yaml content",
        "engine": "auto",
        "tags": ["test", "unit-test"],
        "metadata": {"test": True}
    }