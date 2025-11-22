"""
Prometheus metrics configuration for Galvana Platform
Provides observability for API performance, database, and simulation runs
"""

from prometheus_client import Counter, Histogram, Gauge, Info
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from prometheus_fastapi_instrumentator.metrics import Info as MetricInfo
from fastapi import FastAPI
from typing import Callable
import logging

logger = logging.getLogger(__name__)

# Custom metrics for Galvana domain

# Run metrics
galvana_runs_total = Counter(
    "galvana_runs_total",
    "Total number of runs created",
    ["type", "engine", "status"]
)

galvana_runs_active = Gauge(
    "galvana_runs_active",
    "Number of currently active runs",
    ["status"]
)

galvana_simulation_duration_seconds = Histogram(
    "galvana_simulation_duration_seconds",
    "Time taken to complete simulations",
    ["engine", "status"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600]  # 1s to 1hr
)

galvana_simulation_timesteps = Histogram(
    "galvana_simulation_timesteps",
    "Number of timesteps in completed simulations",
    ["engine"],
    buckets=[10, 50, 100, 500, 1000, 5000, 10000, 50000, 100000]
)

# Database metrics
galvana_db_connections_active = Gauge(
    "galvana_db_connections_active",
    "Number of active database connections"
)

galvana_db_query_duration_seconds = Histogram(
    "galvana_db_query_duration_seconds",
    "Database query execution time",
    ["query_type"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
)

# Authentication metrics
galvana_auth_attempts_total = Counter(
    "galvana_auth_attempts_total",
    "Total authentication attempts",
    ["status"]  # success, failed
)

galvana_active_users = Gauge(
    "galvana_active_users",
    "Number of active users in the last 24 hours"
)

# WebSocket metrics (for future Sprint 2)
galvana_websocket_connections = Gauge(
    "galvana_websocket_connections",
    "Number of active WebSocket connections",
    ["run_id"]
)

galvana_websocket_messages_total = Counter(
    "galvana_websocket_messages_total",
    "Total WebSocket messages sent",
    ["type"]  # status, frame, log, event
)

# API request size
galvana_request_size_bytes = Histogram(
    "galvana_request_size_bytes",
    "HTTP request body size in bytes",
    buckets=[100, 1000, 10000, 100000, 1000000, 10000000, 50000000]  # Up to 50MB
)

galvana_response_size_bytes = Histogram(
    "galvana_response_size_bytes",
    "HTTP response body size in bytes",
    buckets=[100, 1000, 10000, 100000, 1000000, 10000000]
)

# System info
galvana_info = Info(
    "galvana_app",
    "Galvana application information"
)


def setup_metrics(app: FastAPI) -> Instrumentator:
    """
    Setup Prometheus metrics for FastAPI application

    Args:
        app: FastAPI application instance

    Returns:
        Configured Instrumentator instance
    """

    # Create instrumentator with custom configuration
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/metrics", "/health"],  # Don't track metrics/health endpoints
        env_var_name="ENABLE_METRICS",
        inprogress_name="galvana_requests_inprogress",
        inprogress_labels=True,
    )

    # Add default metrics
    instrumentator.add(
        metrics.request_size(
            should_include_handler=True,
            should_include_method=True,
            should_include_status=True,
            metric_name="galvana_request_size_bytes",
            metric_doc="Size of HTTP requests",
        )
    )

    instrumentator.add(
        metrics.response_size(
            should_include_handler=True,
            should_include_method=True,
            should_include_status=True,
            metric_name="galvana_response_size_bytes",
            metric_doc="Size of HTTP responses",
        )
    )

    instrumentator.add(
        metrics.latency(
            should_include_handler=True,
            should_include_method=True,
            should_include_status=True,
            metric_name="galvana_request_duration_seconds",
            metric_doc="HTTP request latency",
            buckets=[0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0]
        )
    )

    instrumentator.add(
        metrics.requests(
            should_include_handler=True,
            should_include_method=True,
            should_include_status=True,
            metric_name="galvana_http_requests_total",
            metric_doc="Total HTTP requests",
        )
    )

    # Set application info
    galvana_info.info({
        "version": "0.1.0",
        "platform": "phygital_electrochemistry",
        "project": "Galvana",
        "organization": "Aureo Labs (MADFAM)"
    })

    # Instrument the app
    instrumentator.instrument(app)

    logger.info("Prometheus metrics configured successfully")

    return instrumentator


# Helper functions for updating custom metrics

def record_run_created(run_type: str, engine: str):
    """Record a new run creation"""
    galvana_runs_total.labels(type=run_type, engine=engine, status="created").inc()
    galvana_runs_active.labels(status="queued").inc()


def record_run_status_change(old_status: str, new_status: str):
    """Record a run status change"""
    if old_status:
        galvana_runs_active.labels(status=old_status).dec()
    galvana_runs_active.labels(status=new_status).inc()


def record_simulation_completed(engine: str, duration_seconds: float, timesteps: int, status: str):
    """Record simulation completion metrics"""
    galvana_simulation_duration_seconds.labels(engine=engine, status=status).observe(duration_seconds)
    galvana_simulation_timesteps.labels(engine=engine).observe(timesteps)
    galvana_runs_total.labels(type="simulation", engine=engine, status=status).inc()


def record_auth_attempt(success: bool):
    """Record authentication attempt"""
    status_label = "success" if success else "failed"
    galvana_auth_attempts_total.labels(status=status_label).inc()


def update_db_connections(count: int):
    """Update active database connection count"""
    galvana_db_connections_active.set(count)


def record_db_query(query_type: str, duration_seconds: float):
    """Record database query execution time"""
    galvana_db_query_duration_seconds.labels(query_type=query_type).observe(duration_seconds)
