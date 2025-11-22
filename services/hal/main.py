"""
HAL Microservice - Hardware Abstraction Layer

Standalone FastAPI service for managing electrochemical instruments.
Communicates with main API via Redis pub/sub (not WebSockets).

Architecture:
- HAL receives commands via REST API
- HAL publishes telemetry to Redis channel: run:{run_id}:telemetry
- Main API subscribes to Redis and forwards to WebSocket clients

RFC-002: Hardware Abstraction Layer - Main Service
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
import redis.asyncio as aioredis
import json

from services.hal.registry import get_registry
from services.hal.drivers.base import (
    BaseInstrumentDriver,
    ConnectionConfig,
    Waveform,
    InstrumentCapability,
    InstrumentFrame
)
from services.hal.drivers.mock import MockInstrumentDriver
from services.hal.safety import SafetyWrapper, SafetyViolationError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global state
active_drivers: Dict[str, SafetyWrapper] = {}
redis_client: Optional[aioredis.Redis] = None
active_streams: Dict[str, asyncio.Task] = {}


# ============ Request/Response Models ============

class ConnectRequest(BaseModel):
    """Request to connect to an instrument"""
    driver_name: str = Field(..., description="Driver identifier (mock, gamry, biologic)")
    config: Dict = Field(default_factory=dict, description="Driver-specific configuration")
    connection_id: str = Field(..., description="Unique connection identifier")


class ConnectResponse(BaseModel):
    """Response after successful connection"""
    connection_id: str
    driver_name: str
    instrument_info: Dict
    capabilities: list
    message: str


class StartRunRequest(BaseModel):
    """Request to start an experimental run"""
    connection_id: str = Field(..., description="Active connection ID")
    run_id: str = Field(..., description="Run identifier for telemetry channel")
    technique: str = Field(..., description="Electrochemical technique")
    waveform: Dict = Field(..., description="Waveform parameters")


class StartRunResponse(BaseModel):
    """Response after starting run"""
    run_id: str
    connection_id: str
    status: str
    telemetry_channel: str
    message: str


class EmergencyStopRequest(BaseModel):
    """Request for emergency stop"""
    connection_id: Optional[str] = None  # If None, stop all


class EmergencyStopResponse(BaseModel):
    """Response after emergency stop"""
    connections_stopped: list
    message: str


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    active_connections: int
    active_streams: int
    redis_connected: bool


# ============ Lifespan Management ============

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup resources"""
    global redis_client

    logger.info("Starting HAL microservice...")

    # Connect to Redis
    try:
        redis_client = await aioredis.from_url(
            "redis://localhost:6379",
            encoding="utf-8",
            decode_responses=True
        )
        await redis_client.ping()
        logger.info("Connected to Redis")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        redis_client = None

    # Register mock driver
    registry = get_registry()
    registry.register("mock", MockInstrumentDriver)
    logger.info("Registered mock driver")

    yield

    # Cleanup
    logger.info("Shutting down HAL microservice...")

    # Stop all active streams
    for task in active_streams.values():
        task.cancel()

    # Disconnect all drivers
    for driver in active_drivers.values():
        try:
            await driver.disconnect()
        except:
            pass

    # Close Redis connection
    if redis_client:
        await redis_client.close()

    logger.info("HAL microservice stopped")


# ============ FastAPI App ============

app = FastAPI(
    title="Galvana HAL",
    description="Hardware Abstraction Layer for Electrochemical Instruments",
    version="0.1.0",
    lifespan=lifespan
)


# ============ Endpoints ============

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    redis_ok = False
    if redis_client:
        try:
            await redis_client.ping()
            redis_ok = True
        except:
            pass

    return HealthResponse(
        status="healthy" if redis_ok else "degraded",
        active_connections=len(active_drivers),
        active_streams=len(active_streams),
        redis_connected=redis_ok
    )


@app.post("/connect", response_model=ConnectResponse, status_code=status.HTTP_201_CREATED)
async def connect_instrument(request: ConnectRequest):
    """
    Connect to an instrument

    Example:
        POST /connect
        {
            "driver_name": "mock",
            "config": {"seed": 42, "noise_level": 0.05},
            "connection_id": "conn_123"
        }
    """
    # Check if connection already exists
    if request.connection_id in active_drivers:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Connection {request.connection_id} already exists"
        )

    # Get registry
    registry = get_registry()

    # Parse connection config
    try:
        config = ConnectionConfig(**request.config)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid config: {e}"
        )

    # Create driver
    try:
        raw_driver = registry.create(request.driver_name, config)
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

    # Wrap with safety
    safe_driver = SafetyWrapper(raw_driver)

    # Connect
    try:
        await safe_driver.connect()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Connection failed: {e}"
        )

    # Get instrument info
    info = await safe_driver.get_info()

    # Store connection
    active_drivers[request.connection_id] = safe_driver

    logger.info(f"Connected to {request.driver_name}: {request.connection_id}")

    return ConnectResponse(
        connection_id=request.connection_id,
        driver_name=request.driver_name,
        instrument_info=info,
        capabilities=[c.value for c in safe_driver.capabilities],
        message="Connected successfully"
    )


@app.post("/start_run", response_model=StartRunResponse)
async def start_run(request: StartRunRequest):
    """
    Start an experimental run

    Example:
        POST /start_run
        {
            "connection_id": "conn_123",
            "run_id": "run_456",
            "technique": "cyclic_voltammetry",
            "waveform": {
                "type": "triangle",
                "initial_value": -0.5,
                "final_value": 0.5,
                "duration": 10.0
            }
        }
    """
    # Get driver
    if request.connection_id not in active_drivers:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connection {request.connection_id} not found"
        )

    driver = active_drivers[request.connection_id]

    # Check if Redis is available
    if not redis_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis not available for telemetry"
        )

    # Parse technique
    try:
        technique = InstrumentCapability(request.technique)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown technique: {request.technique}"
        )

    # Parse waveform
    try:
        waveform = Waveform(**request.waveform)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid waveform: {e}"
        )

    # Program instrument
    try:
        await driver.program(waveform, technique)
    except SafetyViolationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Safety violation: {e}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Programming failed: {e}"
        )

    # Start experiment
    try:
        await driver.start()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Start failed: {e}"
        )

    # Start telemetry stream
    telemetry_channel = f"run:{request.run_id}:telemetry"
    stream_task = asyncio.create_task(
        stream_telemetry(driver, telemetry_channel, request.run_id)
    )
    active_streams[request.run_id] = stream_task

    logger.info(f"Started run {request.run_id} on {request.connection_id}")

    return StartRunResponse(
        run_id=request.run_id,
        connection_id=request.connection_id,
        status="running",
        telemetry_channel=telemetry_channel,
        message="Run started successfully"
    )


@app.post("/emergency_stop", response_model=EmergencyStopResponse)
async def emergency_stop(request: EmergencyStopRequest):
    """
    Trigger emergency stop

    If connection_id is None, stops all active connections.

    Example:
        POST /emergency_stop
        {"connection_id": "conn_123"}

        OR

        POST /emergency_stop
        {}  # Stops all
    """
    stopped = []

    if request.connection_id:
        # Stop specific connection
        if request.connection_id not in active_drivers:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Connection {request.connection_id} not found"
            )

        driver = active_drivers[request.connection_id]
        await driver.emergency_stop()
        stopped.append(request.connection_id)

        logger.critical(f"EMERGENCY STOP: {request.connection_id}")

    else:
        # Stop all connections
        for conn_id, driver in active_drivers.items():
            await driver.emergency_stop()
            stopped.append(conn_id)

        logger.critical(f"EMERGENCY STOP ALL: {len(stopped)} connections")

    return EmergencyStopResponse(
        connections_stopped=stopped,
        message=f"Emergency stop executed on {len(stopped)} connection(s)"
    )


@app.get("/connections")
async def list_connections():
    """List all active connections"""
    connections = []

    for conn_id, driver in active_drivers.items():
        info = await driver.get_info()
        connections.append({
            "connection_id": conn_id,
            "status": driver.status.value,
            "instrument": info,
            "is_running": driver.is_running(),
            "emergency_stopped": driver.is_emergency_stopped()
        })

    return {
        "active_connections": len(connections),
        "connections": connections
    }


@app.delete("/connections/{connection_id}")
async def disconnect_instrument(connection_id: str):
    """Disconnect from an instrument"""
    if connection_id not in active_drivers:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connection {connection_id} not found"
        )

    driver = active_drivers[connection_id]

    # Disconnect
    await driver.disconnect()

    # Remove from active drivers
    del active_drivers[connection_id]

    logger.info(f"Disconnected: {connection_id}")

    return {"message": f"Disconnected {connection_id}"}


# ============ Telemetry Bridge ============

async def stream_telemetry(
    driver: SafetyWrapper,
    channel: str,
    run_id: str
):
    """
    Stream instrument data to Redis channel

    Args:
        driver: Instrument driver (wrapped with safety)
        channel: Redis channel name (e.g., "run:run_123:telemetry")
        run_id: Run identifier
    """
    logger.info(f"Starting telemetry stream on channel: {channel}")

    try:
        frame_count = 0

        async for frame in driver.stream():
            # Convert frame to dict
            frame_dict = frame.dict()
            frame_dict["run_id"] = run_id

            # Publish to Redis
            if redis_client:
                await redis_client.publish(
                    channel,
                    json.dumps(frame_dict)
                )

            frame_count += 1

            if frame_count % 100 == 0:
                logger.debug(f"Streamed {frame_count} frames to {channel}")

        logger.info(f"Telemetry stream completed: {frame_count} frames")

    except SafetyViolationError as e:
        logger.error(f"Safety violation during stream: {e}")

        # Publish error to channel
        if redis_client:
            await redis_client.publish(
                channel,
                json.dumps({
                    "type": "error",
                    "run_id": run_id,
                    "error": "safety_violation",
                    "message": str(e)
                })
            )

    except asyncio.CancelledError:
        logger.info(f"Telemetry stream cancelled for {run_id}")

    except Exception as e:
        logger.error(f"Error during telemetry stream: {e}")

        # Publish error to channel
        if redis_client:
            await redis_client.publish(
                channel,
                json.dumps({
                    "type": "error",
                    "run_id": run_id,
                    "error": "stream_error",
                    "message": str(e)
                })
            )

    finally:
        # Remove from active streams
        if run_id in active_streams:
            del active_streams[run_id]


# ============ Main Entry Point ============

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8081,  # Different port from main API (8080)
        log_level="info"
    )
