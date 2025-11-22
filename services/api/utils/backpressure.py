"""
Backpressure Controller for WebSocket Streaming

Implements intelligent frame dropping to prevent memory overflow when clients
are slow to consume simulation data. Follows Solarpunk efficiency principles
by preserving keyframes and dropping intermediate data.

RFC-001: Real-time Simulation Streaming with Backpressure Control
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

# Prometheus metrics for backpressure monitoring
frames_dropped_total = Counter(
    "galvana_frames_dropped_total",
    "Total frames dropped due to backpressure (Solarpunk efficiency)",
    ["run_id", "reason"]
)

queue_size_gauge = Gauge(
    "galvana_frame_queue_size",
    "Current size of frame queue",
    ["run_id"]
)

queue_utilization_gauge = Gauge(
    "galvana_frame_queue_utilization",
    "Queue utilization percentage (0-1)",
    ["run_id"]
)

frame_latency_histogram = Histogram(
    "galvana_frame_latency_seconds",
    "Time between frame generation and transmission",
    ["run_id"],
    buckets=[0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0]
)


@dataclass
class FrameQueueMetrics:
    """Metrics for frame queue performance"""
    queue_size: int
    max_size: int
    utilization: float
    frames_dropped: int
    frames_transmitted: int
    average_latency_ms: float


class BackpressureController:
    """
    Manages frame queue with intelligent backpressure handling

    Solarpunk Efficiency Strategy:
    - Queue < 30%: Send all frames (FAST client)
    - Queue 30-70%: Send all frames + warn (MEDIUM client)
    - Queue > 70%: Drop non-keyframes, send keyframes only (SLOW client)
    - Queue 100%: Drop frames with timeout (STALLED client)

    Example:
        controller = BackpressureController(run_id="run_123", max_queue_size=100)

        # Producer (simulation worker)
        await controller.enqueue(frame, is_keyframe=(timestep % 10 == 0))

        # Consumer (WebSocket client)
        async for frame in controller.stream():
            await websocket.send_json(frame)
    """

    def __init__(
        self,
        run_id: str,
        max_queue_size: int = 100,
        slow_threshold: float = 0.7,
        medium_threshold: float = 0.3,
        enqueue_timeout: float = 1.0
    ):
        """
        Initialize backpressure controller

        Args:
            run_id: Unique identifier for this run
            max_queue_size: Maximum number of frames to buffer
            slow_threshold: Utilization threshold for slow client (0.7 = 70%)
            medium_threshold: Utilization threshold for medium warning (0.3 = 30%)
            enqueue_timeout: Timeout in seconds for enqueue operations
        """
        self.run_id = run_id
        self.max_queue_size = max_queue_size
        self.slow_threshold = slow_threshold
        self.medium_threshold = medium_threshold
        self.enqueue_timeout = enqueue_timeout

        # Async queue for frames
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)

        # Metrics tracking
        self.frames_dropped = 0
        self.frames_transmitted = 0
        self.keyframes_preserved = 0
        self.total_latency_ms = 0.0

        # Client health tracking
        self.last_warning_time: Optional[datetime] = None
        self.warning_cooldown_seconds = 5.0

        logger.info(
            f"BackpressureController initialized for run {run_id}: "
            f"max_queue={max_queue_size}, slow_threshold={slow_threshold*100}%"
        )

    def get_utilization(self) -> float:
        """Get current queue utilization (0.0 to 1.0)"""
        return self.queue.qsize() / self.max_queue_size

    def is_slow_client(self) -> bool:
        """Check if client is slow (queue > 70% full)"""
        return self.get_utilization() > self.slow_threshold

    def is_medium_client(self) -> bool:
        """Check if client is medium speed (queue 30-70% full)"""
        utilization = self.get_utilization()
        return self.medium_threshold < utilization <= self.slow_threshold

    def should_warn(self) -> bool:
        """Check if we should emit a warning (respects cooldown)"""
        if self.last_warning_time is None:
            return True

        elapsed = (datetime.now() - self.last_warning_time).total_seconds()
        return elapsed > self.warning_cooldown_seconds

    async def enqueue(
        self,
        frame: Dict[str, Any],
        is_keyframe: bool = False,
        timeout: Optional[float] = None
    ) -> bool:
        """
        Enqueue a frame with backpressure handling

        Args:
            frame: Frame data dictionary
            is_keyframe: Whether this is a critical keyframe (must be preserved)
            timeout: Override default enqueue timeout

        Returns:
            True if frame was enqueued, False if dropped

        Solarpunk Logic:
            - If queue < 70% full: Always enqueue
            - If queue > 70% full AND not keyframe: DROP (save bandwidth)
            - If queue > 70% full AND is keyframe: Force enqueue (critical data)
            - If queue full: Drop with timeout
        """
        timeout = timeout or self.enqueue_timeout
        utilization = self.get_utilization()

        # Update Prometheus metrics
        queue_size_gauge.labels(run_id=self.run_id).set(self.queue.qsize())
        queue_utilization_gauge.labels(run_id=self.run_id).set(utilization)

        # Solarpunk Decision: Should we drop this frame?
        if self.is_slow_client() and not is_keyframe:
            # Client is slow and this is NOT a keyframe -> DROP
            self.frames_dropped += 1
            frames_dropped_total.labels(
                run_id=self.run_id,
                reason="slow_client_non_keyframe"
            ).inc()

            if self.should_warn():
                logger.warning(
                    f"Run {self.run_id}: Dropping non-keyframe "
                    f"(queue {utilization*100:.1f}% full, saving bandwidth)"
                )
                self.last_warning_time = datetime.now()

            return False

        # Add metadata to frame
        frame["_enqueued_at"] = datetime.now().timestamp()
        frame["is_keyframe"] = is_keyframe

        # Try to enqueue with timeout
        try:
            await asyncio.wait_for(
                self.queue.put(frame),
                timeout=timeout
            )

            if is_keyframe:
                self.keyframes_preserved += 1
                logger.debug(f"Run {self.run_id}: Keyframe preserved (critical data)")

            # Warn if queue is getting full (medium threshold)
            if self.is_medium_client() and self.should_warn():
                logger.info(
                    f"Run {self.run_id}: Queue {utilization*100:.1f}% full "
                    f"(approaching backpressure threshold)"
                )
                self.last_warning_time = datetime.now()

            return True

        except asyncio.TimeoutError:
            # Queue is completely full - drop frame
            self.frames_dropped += 1
            frames_dropped_total.labels(
                run_id=self.run_id,
                reason="queue_full_timeout"
            ).inc()

            logger.error(
                f"Run {self.run_id}: Frame dropped due to timeout "
                f"(queue full, client stalled)"
            )
            return False

    async def dequeue(self) -> Dict[str, Any]:
        """
        Dequeue a frame and calculate latency

        Returns:
            Frame data with latency metadata
        """
        frame = await self.queue.get()

        # Calculate latency
        enqueued_at = frame.pop("_enqueued_at", None)
        if enqueued_at:
            latency_seconds = datetime.now().timestamp() - enqueued_at
            latency_ms = latency_seconds * 1000

            # Update metrics
            frame_latency_histogram.labels(run_id=self.run_id).observe(latency_seconds)
            self.total_latency_ms += latency_ms
            self.frames_transmitted += 1

            # Add latency to frame metadata
            frame["_latency_ms"] = round(latency_ms, 2)

        # Update queue metrics
        queue_size_gauge.labels(run_id=self.run_id).set(self.queue.qsize())
        queue_utilization_gauge.labels(run_id=self.run_id).set(self.get_utilization())

        return frame

    async def stream(self) -> Any:
        """
        Stream frames as async generator

        Yields:
            Frame data dictionaries

        Example:
            async for frame in controller.stream():
                await websocket.send_json(frame)
        """
        while True:
            try:
                frame = await self.dequeue()
                yield frame
            except asyncio.CancelledError:
                logger.info(f"Run {self.run_id}: Stream cancelled by client")
                break
            except Exception as e:
                logger.error(f"Run {self.run_id}: Stream error: {e}")
                break

    def get_metrics(self) -> FrameQueueMetrics:
        """
        Get current performance metrics

        Returns:
            FrameQueueMetrics with current statistics
        """
        avg_latency = (
            self.total_latency_ms / self.frames_transmitted
            if self.frames_transmitted > 0
            else 0.0
        )

        return FrameQueueMetrics(
            queue_size=self.queue.qsize(),
            max_size=self.max_queue_size,
            utilization=self.get_utilization(),
            frames_dropped=self.frames_dropped,
            frames_transmitted=self.frames_transmitted,
            average_latency_ms=round(avg_latency, 2)
        )

    async def close(self):
        """
        Close the controller and log final metrics
        """
        metrics = self.get_metrics()

        logger.info(
            f"Run {self.run_id}: BackpressureController closing\n"
            f"  Frames transmitted: {metrics.frames_transmitted}\n"
            f"  Frames dropped: {metrics.frames_dropped}\n"
            f"  Keyframes preserved: {self.keyframes_preserved}\n"
            f"  Average latency: {metrics.average_latency_ms}ms\n"
            f"  Bandwidth saved: {metrics.frames_dropped} frames (Solarpunk efficiency)"
        )

        # Clear queue
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break


class BackpressureMonitor:
    """
    Monitor multiple BackpressureControllers across all active runs

    Useful for system-wide metrics and alerts
    """

    def __init__(self):
        self.controllers: Dict[str, BackpressureController] = {}

    def register(self, run_id: str, controller: BackpressureController):
        """Register a controller for monitoring"""
        self.controllers[run_id] = controller
        logger.debug(f"Registered BackpressureController for run {run_id}")

    def unregister(self, run_id: str):
        """Unregister a controller"""
        if run_id in self.controllers:
            del self.controllers[run_id]
            logger.debug(f"Unregistered BackpressureController for run {run_id}")

    def get_global_metrics(self) -> Dict[str, Any]:
        """
        Get aggregated metrics across all active runs

        Returns:
            Dictionary with global statistics
        """
        total_dropped = sum(c.frames_dropped for c in self.controllers.values())
        total_transmitted = sum(c.frames_transmitted for c in self.controllers.values())
        total_keyframes = sum(c.keyframes_preserved for c in self.controllers.values())

        avg_utilization = (
            sum(c.get_utilization() for c in self.controllers.values()) / len(self.controllers)
            if self.controllers
            else 0.0
        )

        return {
            "active_runs": len(self.controllers),
            "total_frames_transmitted": total_transmitted,
            "total_frames_dropped": total_dropped,
            "total_keyframes_preserved": total_keyframes,
            "average_queue_utilization": round(avg_utilization, 3),
            "bandwidth_efficiency": round(
                (total_dropped / (total_transmitted + total_dropped) * 100)
                if (total_transmitted + total_dropped) > 0
                else 0.0,
                2
            )
        }


# Global monitor instance
backpressure_monitor = BackpressureMonitor()
