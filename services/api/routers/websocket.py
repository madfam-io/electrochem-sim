"""
WebSocket Router for Real-time Simulation Streaming

Implements RFC-001: Real-time Simulation Streaming with Backpressure Control

Features:
- JWT authentication via query parameter
- Connection limit enforcement (3 per user)
- Backpressure-aware frame streaming
- Automatic reconnection support
- Connection quality metrics
"""

import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query
from fastapi.websockets import WebSocketState
from typing import Dict, Optional, Set
from datetime import datetime
from sqlalchemy.orm import Session
import logging

from services.api.database import get_db, Run as RunModel
from services.api.models import RunStatus, User
from services.api.auth_service import get_current_user_from_token
from services.api.utils.backpressure import BackpressureController, backpressure_monitor
from services.api.exceptions import ResourceNotFoundException
from prometheus_client import Counter, Gauge

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/ws", tags=["websocket"])

# Prometheus metrics
websocket_connections_total = Counter(
    "galvana_websocket_connections_total",
    "Total WebSocket connection attempts",
    ["status"]  # success, auth_failed, limit_exceeded, error
)

websocket_connections_active = Gauge(
    "galvana_websocket_connections_active",
    "Current number of active WebSocket connections",
    ["user_id"]
)

websocket_messages_total = Counter(
    "galvana_websocket_messages_total",
    "Total WebSocket messages sent",
    ["run_id", "type"]  # status, frame, log, event
)

websocket_disconnections_total = Counter(
    "galvana_websocket_disconnections_total",
    "Total WebSocket disconnections",
    ["reason"]  # client_disconnect, error, server_close
)


class ConnectionManager:
    """
    Manages WebSocket connections with per-user limits

    Enforces Solarpunk efficiency through connection limits:
    - Max 3 concurrent connections per user (prevent resource exhaustion)
    - Track connections by user_id for quota enforcement
    - Graceful cleanup on disconnect
    """

    def __init__(self, max_connections_per_user: int = 3):
        self.max_connections_per_user = max_connections_per_user

        # Active connections: {run_id: websocket}
        self.active_connections: Dict[str, WebSocket] = {}

        # User connection tracking: {user_id: set(run_ids)}
        self.user_connections: Dict[str, Set[str]] = {}

        # Backpressure controllers: {run_id: controller}
        self.controllers: Dict[str, BackpressureController] = {}

        logger.info(
            f"ConnectionManager initialized: "
            f"max_connections_per_user={max_connections_per_user}"
        )

    def get_user_connection_count(self, user_id: str) -> int:
        """Get number of active connections for a user"""
        return len(self.user_connections.get(user_id, set()))

    def can_connect(self, user_id: str) -> bool:
        """Check if user can create a new connection (within limits)"""
        count = self.get_user_connection_count(user_id)
        return count < self.max_connections_per_user

    async def connect(
        self,
        websocket: WebSocket,
        run_id: str,
        user_id: str
    ) -> BackpressureController:
        """
        Accept WebSocket connection and create backpressure controller

        Args:
            websocket: WebSocket connection
            run_id: Run identifier
            user_id: User identifier

        Returns:
            BackpressureController instance for this connection

        Raises:
            HTTPException: If connection limit exceeded
        """
        # Check connection limit
        if not self.can_connect(user_id):
            websocket_connections_total.labels(status="limit_exceeded").inc()
            logger.warning(
                f"User {user_id} exceeded connection limit "
                f"({self.max_connections_per_user} max)"
            )
            raise HTTPException(
                status_code=429,
                detail=f"Connection limit exceeded (max {self.max_connections_per_user} per user)"
            )

        # Accept connection
        await websocket.accept()

        # Create backpressure controller
        controller = BackpressureController(run_id=run_id, max_queue_size=100)

        # Register connection
        self.active_connections[run_id] = websocket
        self.controllers[run_id] = controller

        # Track user connections
        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()
        self.user_connections[user_id].add(run_id)

        # Register with global monitor
        backpressure_monitor.register(run_id, controller)

        # Update metrics
        websocket_connections_total.labels(status="success").inc()
        websocket_connections_active.labels(user_id=user_id).set(
            self.get_user_connection_count(user_id)
        )

        logger.info(
            f"WebSocket connected: run={run_id}, user={user_id}, "
            f"user_connections={self.get_user_connection_count(user_id)}/{self.max_connections_per_user}"
        )

        return controller

    async def disconnect(self, run_id: str, user_id: str, reason: str = "client_disconnect"):
        """
        Disconnect WebSocket and cleanup resources

        Args:
            run_id: Run identifier
            user_id: User identifier
            reason: Reason for disconnection
        """
        # Close controller
        if run_id in self.controllers:
            await self.controllers[run_id].close()
            del self.controllers[run_id]

        # Unregister from monitor
        backpressure_monitor.unregister(run_id)

        # Remove connection
        if run_id in self.active_connections:
            del self.active_connections[run_id]

        # Update user tracking
        if user_id in self.user_connections:
            self.user_connections[user_id].discard(run_id)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]

        # Update metrics
        websocket_disconnections_total.labels(reason=reason).inc()
        websocket_connections_active.labels(user_id=user_id).set(
            self.get_user_connection_count(user_id)
        )

        logger.info(
            f"WebSocket disconnected: run={run_id}, user={user_id}, reason={reason}"
        )

    async def send_message(
        self,
        run_id: str,
        message: Dict,
        message_type: str = "frame"
    ):
        """
        Send message to WebSocket client

        Args:
            run_id: Run identifier
            message: Message data
            message_type: Type of message (status, frame, log, event)
        """
        if run_id not in self.active_connections:
            return

        websocket = self.active_connections[run_id]

        # Check if connection is still open
        if websocket.client_state != WebSocketState.CONNECTED:
            logger.warning(f"WebSocket for run {run_id} is not connected")
            return

        try:
            await websocket.send_json(message)
            websocket_messages_total.labels(run_id=run_id, type=message_type).inc()
        except Exception as e:
            logger.error(f"Failed to send message to run {run_id}: {e}")


# Global connection manager
connection_manager = ConnectionManager(max_connections_per_user=3)


async def get_current_user_ws(
    token: str = Query(..., description="JWT access token"),
    db: Session = Depends(get_db)
) -> User:
    """
    Authenticate WebSocket connection via query parameter

    Args:
        token: JWT token from query parameter
        db: Database session

    Returns:
        Authenticated user

    Raises:
        HTTPException: If authentication fails

    Note:
        Standard WebSocket headers don't support custom Authorization header
        in browsers, so we use query parameters for JWT authentication.
    """
    try:
        user = await get_current_user_from_token(token, db)
        return user
    except Exception as e:
        logger.warning(f"WebSocket authentication failed: {e}")
        websocket_connections_total.labels(status="auth_failed").inc()
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )


@router.websocket("/runs/{run_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    run_id: str,
    current_user: User = Depends(get_current_user_ws),
    db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for real-time simulation streaming

    Connection URL:
        ws://localhost:8080/ws/runs/{run_id}?token={jwt_token}

    Message Types:
        - status: Run status updates (running, paused, completed, failed)
        - frame: Simulation data frame
        - log: Log messages from simulation
        - event: System events (connected, disconnected, error)

    Backpressure Handling:
        - Queue < 30%: Send all frames (FAST)
        - Queue 30-70%: Send all frames + warn (MEDIUM)
        - Queue > 70%: Drop non-keyframes, send keyframes only (SLOW)

    Connection Limits:
        - Max 3 concurrent connections per user
        - HTTP 429 if limit exceeded

    Args:
        websocket: WebSocket connection
        run_id: Run identifier
        current_user: Authenticated user (from JWT token)
        db: Database session
    """
    controller: Optional[BackpressureController] = None

    try:
        # Verify run exists and user has access
        run = db.query(RunModel).filter(
            RunModel.id == run_id,
            (RunModel.user_id == current_user.id) | (current_user.is_superuser == True)
        ).first()

        if not run:
            websocket_connections_total.labels(status="error").inc()
            await websocket.close(code=1008, reason="Run not found or access denied")
            return

        # Connect and create backpressure controller
        controller = await connection_manager.connect(
            websocket=websocket,
            run_id=run_id,
            user_id=current_user.id
        )

        # Send connection confirmation
        await websocket.send_json({
            "type": "event",
            "event": "connected",
            "run_id": run_id,
            "timestamp": datetime.utcnow().isoformat(),
            "message": "WebSocket connection established",
            "backpressure": {
                "max_queue_size": controller.max_queue_size,
                "slow_threshold": controller.slow_threshold,
                "frame_dropping_enabled": True
            }
        })

        # Start simulation worker (async task)
        simulation_task = asyncio.create_task(
            simulate_and_stream(run_id, controller, db)
        )

        # Stream frames to client with backpressure control
        try:
            async for frame in controller.stream():
                # Add connection metadata
                frame["run_id"] = run_id
                frame["timestamp"] = datetime.utcnow().isoformat()

                # Determine message type
                msg_type = frame.get("type", "frame")

                # Send frame
                await connection_manager.send_message(
                    run_id=run_id,
                    message=frame,
                    message_type=msg_type
                )

        except asyncio.CancelledError:
            logger.info(f"WebSocket stream cancelled for run {run_id}")
            simulation_task.cancel()

    except WebSocketDisconnect:
        logger.info(f"Client disconnected from run {run_id}")
        if controller:
            await connection_manager.disconnect(
                run_id=run_id,
                user_id=current_user.id,
                reason="client_disconnect"
            )

    except Exception as e:
        logger.error(f"WebSocket error for run {run_id}: {e}")
        websocket_connections_total.labels(status="error").inc()

        if controller:
            await connection_manager.disconnect(
                run_id=run_id,
                user_id=current_user.id,
                reason="error"
            )

        # Try to send error message before closing
        try:
            await websocket.send_json({
                "type": "event",
                "event": "error",
                "message": "WebSocket error occurred",
                "timestamp": datetime.utcnow().isoformat()
            })
        except:
            pass

        await websocket.close(code=1011, reason="Internal server error")


async def simulate_and_stream(
    run_id: str,
    controller: BackpressureController,
    db: Session
):
    """
    Run simulation and stream frames to backpressure controller

    This is a placeholder that will be replaced with actual simulation logic
    in the solver refactor task.

    Args:
        run_id: Run identifier
        controller: Backpressure controller for this connection
        db: Database session
    """
    # TODO: Import actual simulation solver in next task
    # For now, simulate with dummy data

    try:
        timestep = 0
        max_timesteps = 1000
        dt = 0.1  # 100ms per frame = 10 Hz

        while timestep < max_timesteps:
            # Simulate frame generation
            await asyncio.sleep(dt)

            # Every 10th frame is a keyframe
            is_keyframe = (timestep % 10 == 0)

            frame = {
                "type": "frame",
                "timestep": timestep,
                "time": timestep * dt,
                "data": {
                    "current_density": -2.5 + (timestep * 0.001),
                    "voltage": -0.8,
                    "concentration_surface": 100.0 - (timestep * 0.01)
                },
                "is_keyframe": is_keyframe
            }

            # Enqueue with backpressure
            enqueued = await controller.enqueue(frame, is_keyframe=is_keyframe)

            if not enqueued and not is_keyframe:
                logger.debug(f"Frame {timestep} dropped due to backpressure")

            timestep += 1

        # Send completion message
        await controller.enqueue({
            "type": "status",
            "status": "completed",
            "message": "Simulation completed successfully",
            "final_timestep": timestep
        }, is_keyframe=True)

    except asyncio.CancelledError:
        logger.info(f"Simulation task cancelled for run {run_id}")
    except Exception as e:
        logger.error(f"Simulation error for run {run_id}: {e}")
        await controller.enqueue({
            "type": "status",
            "status": "failed",
            "error": str(e)
        }, is_keyframe=True)
