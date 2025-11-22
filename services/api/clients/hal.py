"""
HAL Service Client

Async HTTP client for communicating with the HAL (Hardware Abstraction Layer) microservice.
Implements the command link: Main API -> HAL Service.

Features:
- Async HTTP client with httpx
- Automatic retries with exponential backoff
- Connection pooling
- Request/response validation with Pydantic
- Prometheus metrics for observability
"""

import asyncio
import logging
from typing import Dict, Optional, Any
from datetime import datetime

import httpx
from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram

from services.api.config import settings

logger = logging.getLogger(__name__)

# Prometheus metrics
hal_requests_total = Counter(
    "galvana_hal_requests_total",
    "Total requests to HAL service",
    ["endpoint", "status"]  # /connect, /start_run, /emergency_stop | success, error
)

hal_request_duration_seconds = Histogram(
    "galvana_hal_request_duration_seconds",
    "HAL request duration in seconds",
    ["endpoint"]
)


# ============ Request/Response Models ============

class ConnectRequest(BaseModel):
    """Request to connect to an instrument"""
    driver_name: str = Field(..., description="Driver identifier (mock, gamry, biologic)")
    config: Dict[str, Any] = Field(default_factory=dict, description="Driver-specific configuration")
    connection_id: str = Field(..., description="Unique connection identifier")


class ConnectResponse(BaseModel):
    """Response after successful connection"""
    connection_id: str
    driver_name: str
    instrument_info: Dict[str, Any]
    capabilities: list
    message: str


class StartRunRequest(BaseModel):
    """Request to start an experimental run"""
    connection_id: str = Field(..., description="Active connection ID")
    run_id: str = Field(..., description="Run identifier for telemetry channel")
    technique: str = Field(..., description="Electrochemical technique")
    waveform: Dict[str, Any] = Field(..., description="Waveform parameters")


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


# ============ HAL Client ============

class HALClient:
    """
    Async HTTP client for HAL microservice

    Handles connection management, run execution, and emergency stop commands.
    Uses connection pooling and automatic retries for resilience.

    Example:
        async with HALClient() as client:
            response = await client.start_run(
                connection_id="conn_123",
                run_id="run_456",
                technique="cyclic_voltammetry",
                waveform={...}
            )
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3
    ):
        """
        Initialize HAL client

        Args:
            base_url: HAL service URL (defaults to HAL_SERVICE_URL env var)
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
        """
        self.base_url = base_url or self._get_hal_url()
        self.timeout = timeout
        self.max_retries = max_retries

        # Create async HTTP client with connection pooling
        self.client: Optional[httpx.AsyncClient] = None

        logger.info(f"HALClient initialized: base_url={self.base_url}, timeout={timeout}s")

    def _get_hal_url(self) -> str:
        """Get HAL service URL from environment or default"""
        import os
        return os.getenv("HAL_SERVICE_URL", "http://localhost:8081")

    async def __aenter__(self):
        """Context manager entry - create HTTP client"""
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            limits=httpx.Limits(
                max_connections=50,
                max_keepalive_connections=20
            )
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close HTTP client"""
        if self.client:
            await self.client.aclose()

    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> httpx.Response:
        """
        Make HTTP request with retries and metrics

        Args:
            method: HTTP method (GET, POST, DELETE)
            endpoint: API endpoint (e.g., "/connect", "/start_run")
            **kwargs: Additional arguments for httpx.request()

        Returns:
            Response object

        Raises:
            httpx.HTTPError: If request fails after retries
        """
        if not self.client:
            raise RuntimeError("HALClient not initialized - use async context manager")

        # Start timer for metrics
        with hal_request_duration_seconds.labels(endpoint=endpoint).time():
            for attempt in range(self.max_retries):
                try:
                    response = await self.client.request(method, endpoint, **kwargs)
                    response.raise_for_status()

                    # Record success metric
                    hal_requests_total.labels(endpoint=endpoint, status="success").inc()

                    return response

                except httpx.HTTPStatusError as e:
                    # Don't retry client errors (4xx)
                    if 400 <= e.response.status_code < 500:
                        hal_requests_total.labels(endpoint=endpoint, status="error").inc()
                        logger.error(
                            f"HAL request failed: {method} {endpoint} -> "
                            f"{e.response.status_code} {e.response.text}"
                        )
                        raise

                    # Retry server errors (5xx)
                    if attempt < self.max_retries - 1:
                        wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                        logger.warning(
                            f"HAL request failed (attempt {attempt + 1}/{self.max_retries}): "
                            f"{method} {endpoint} -> {e.response.status_code}. "
                            f"Retrying in {wait_time}s..."
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        hal_requests_total.labels(endpoint=endpoint, status="error").inc()
                        raise

                except httpx.RequestError as e:
                    # Retry network errors
                    if attempt < self.max_retries - 1:
                        wait_time = 2 ** attempt
                        logger.warning(
                            f"HAL request error (attempt {attempt + 1}/{self.max_retries}): "
                            f"{method} {endpoint} -> {e}. "
                            f"Retrying in {wait_time}s..."
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        hal_requests_total.labels(endpoint=endpoint, status="error").inc()
                        raise

    # ============ HAL API Methods ============

    async def health_check(self) -> HealthResponse:
        """
        Check HAL service health

        Returns:
            HealthResponse with service status
        """
        response = await self._request("GET", "/health")
        return HealthResponse(**response.json())

    async def connect(
        self,
        driver_name: str,
        connection_id: str,
        config: Optional[Dict[str, Any]] = None
    ) -> ConnectResponse:
        """
        Connect to an instrument

        Args:
            driver_name: Driver identifier (mock, gamry, biologic)
            connection_id: Unique connection identifier
            config: Driver-specific configuration (seed, noise_level, etc.)

        Returns:
            ConnectResponse with instrument info and capabilities

        Example:
            response = await client.connect(
                driver_name="mock",
                connection_id="conn_123",
                config={"seed": 42, "noise_level": 0.05}
            )
        """
        request = ConnectRequest(
            driver_name=driver_name,
            connection_id=connection_id,
            config=config or {}
        )

        response = await self._request(
            "POST",
            "/connect",
            json=request.dict()
        )

        return ConnectResponse(**response.json())

    async def start_run(
        self,
        connection_id: str,
        run_id: str,
        technique: str,
        waveform: Dict[str, Any]
    ) -> StartRunResponse:
        """
        Start an experimental run

        Args:
            connection_id: Active connection ID
            run_id: Run identifier for telemetry channel
            technique: Electrochemical technique (cyclic_voltammetry, chronoamperometry, etc.)
            waveform: Waveform parameters (type, initial_value, final_value, duration)

        Returns:
            StartRunResponse with telemetry channel info

        Example:
            response = await client.start_run(
                connection_id="conn_123",
                run_id="run_456",
                technique="cyclic_voltammetry",
                waveform={
                    "type": "triangle",
                    "initial_value": -0.5,
                    "final_value": 0.5,
                    "duration": 10.0
                }
            )
        """
        request = StartRunRequest(
            connection_id=connection_id,
            run_id=run_id,
            technique=technique,
            waveform=waveform
        )

        response = await self._request(
            "POST",
            "/start_run",
            json=request.dict()
        )

        return StartRunResponse(**response.json())

    async def emergency_stop(
        self,
        connection_id: Optional[str] = None
    ) -> EmergencyStopResponse:
        """
        Trigger emergency stop

        Args:
            connection_id: Specific connection to stop (None = stop all)

        Returns:
            EmergencyStopResponse with list of stopped connections

        Example:
            # Stop specific connection
            response = await client.emergency_stop(connection_id="conn_123")

            # Stop all connections
            response = await client.emergency_stop()
        """
        request = EmergencyStopRequest(connection_id=connection_id)

        response = await self._request(
            "POST",
            "/emergency_stop",
            json=request.dict()
        )

        return EmergencyStopResponse(**response.json())

    async def list_connections(self) -> Dict[str, Any]:
        """
        List all active connections

        Returns:
            Dict with active connections and their status
        """
        response = await self._request("GET", "/connections")
        return response.json()

    async def disconnect(self, connection_id: str) -> Dict[str, Any]:
        """
        Disconnect from an instrument

        Args:
            connection_id: Connection to disconnect

        Returns:
            Dict with confirmation message
        """
        response = await self._request("DELETE", f"/connections/{connection_id}")
        return response.json()


# ============ Global Client Instance ============

# Singleton pattern for reusing connection pool
_hal_client: Optional[HALClient] = None


def get_hal_client() -> HALClient:
    """
    Get global HAL client instance

    Returns:
        HALClient instance (singleton)

    Note:
        Use within async context manager:

        async with get_hal_client() as client:
            await client.start_run(...)
    """
    global _hal_client

    if _hal_client is None:
        _hal_client = HALClient()

    return _hal_client
