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
import redis.asyncio as aioredis

from services.api.database import get_db, Run as RunModel
from services.api.models import RunStatus, User
from services.api.auth_service import get_current_user_from_token
from services.api.utils.backpressure import BackpressureController, backpressure_monitor
from services.api.exceptions import ResourceNotFoundException
from services.api.config import settings
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

redis_messages_received_total = Counter(
    "galvana_redis_messages_received_total",
    "Total messages received from Redis telemetry channels",
    ["run_id"]
)

redis_subscribe_errors_total = Counter(
    "galvana_redis_subscribe_errors_total",
    "Total Redis subscription errors",
    ["run_id"]
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

        # Redis subscriber tasks: {run_id: task}
        self.redis_tasks: Dict[str, asyncio.Task] = {}

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

        # Start Redis subscriber task
        redis_task = asyncio.create_task(
            self.subscribe_to_redis(run_id, controller)
        )
        self.redis_tasks[run_id] = redis_task

        return controller

    async def disconnect(self, run_id: str, user_id: str, reason: str = "client_disconnect"):
        """
        Disconnect WebSocket and cleanup resources

        Args:
            run_id: Run identifier
            user_id: User identifier
            reason: Reason for disconnection
        """
        # Cancel Redis subscriber task
        if run_id in self.redis_tasks:
            self.redis_tasks[run_id].cancel()
            try:
                await self.redis_tasks[run_id]
            except asyncio.CancelledError:
                pass
            del self.redis_tasks[run_id]

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

    async def subscribe_to_redis(
        self,
        run_id: str,
        controller: BackpressureController
    ):
        """
        Subscribe to Redis telemetry channel and forward messages to WebSocket

        This method runs as a background task for each WebSocket connection.
        When HAL publishes telemetry to Redis channel run:{run_id}:telemetry,
        this subscriber forwards it to the WebSocket client via the backpressure controller.

        Args:
            run_id: Run identifier
            controller: Backpressure controller for this connection

        Solarpunk Efficiency:
        - Per-connection subscription (no wasted CPU for unwatched runs)
        - Automatic cleanup on disconnect
        - Respects backpressure controller for frame dropping
        """
        redis_client: Optional[aioredis.Redis] = None
        pubsub: Optional[aioredis.client.PubSub] = None

        try:
            # Create Redis client
            redis_client = await aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True
            )

            # Create pub/sub connection
            pubsub = redis_client.pubsub()

            # Subscribe to telemetry channel
            channel = f"run:{run_id}:telemetry"
            await pubsub.subscribe(channel)

            logger.info(f"Subscribed to Redis channel: {channel}")

            # Listen for messages
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        # Parse JSON frame from HAL
                        frame_data = json.loads(message["data"])

                        # Check if it's a keyframe
                        is_keyframe = frame_data.get("is_keyframe", False)

                        # Enqueue with backpressure control
                        enqueued = await controller.enqueue(frame_data, is_keyframe=is_keyframe)

                        if enqueued:
                            redis_messages_received_total.labels(run_id=run_id).inc()
                        else:
                            logger.debug(
                                f"Redis frame dropped due to backpressure: run={run_id}, "
                                f"timestep={frame_data.get('timestep', 'unknown')}"
                            )

                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON from Redis channel {channel}: {e}")
                        redis_subscribe_errors_total.labels(run_id=run_id).inc()
                    except Exception as e:
                        logger.error(f"Error processing Redis message for run {run_id}: {e}")
                        redis_subscribe_errors_total.labels(run_id=run_id).inc()

        except asyncio.CancelledError:
            logger.info(f"Redis subscriber cancelled for run {run_id}")
            raise

        except Exception as e:
            logger.error(f"Redis subscription error for run {run_id}: {e}")
            redis_subscribe_errors_total.labels(run_id=run_id).inc()

            # Send error to client
            await controller.enqueue({
                "type": "event",
                "event": "redis_error",
                "message": "Lost connection to telemetry stream",
                "error": str(e)
            }, is_keyframe=True)

        finally:
            # Cleanup
            if pubsub:
                try:
                    await pubsub.unsubscribe(f"run:{run_id}:telemetry")
                    await pubsub.close()
                except Exception as e:
                    logger.error(f"Error closing Redis pubsub for run {run_id}: {e}")

            if redis_client:
                try:
                    await redis_client.close()
                except Exception as e:
                    logger.error(f"Error closing Redis client for run {run_id}: {e}")

            logger.info(f"Redis subscriber cleaned up for run {run_id}")


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
            "message": "WebSocket connection established (subscribed to Redis telemetry)",
            "telemetry_channel": f"run:{run_id}:telemetry",
            "backpressure": {
                "max_queue_size": controller.max_queue_size,
                "slow_threshold": controller.slow_threshold,
                "frame_dropping_enabled": True
            }
        })

        # Stream frames to client with backpressure control
        # Frames are populated by the Redis subscriber task (started in connect())
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
