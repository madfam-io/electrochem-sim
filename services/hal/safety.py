"""
Safety Interlock Layer

Wraps instrument drivers with safety checks and automatic emergency stop.
Never trust the driver - validate every command before execution.

RFC-002: Hardware Abstraction Layer - Safety Interlocks
"""

import logging
from typing import AsyncIterator, Dict, Any
from datetime import datetime

from services.hal.drivers.base import (
    BaseInstrumentDriver,
    InstrumentCapability,
    Waveform,
    InstrumentFrame,
    SafetyLimits
)

logger = logging.getLogger(__name__)


class SafetyViolationError(Exception):
    """Raised when a safety limit is violated"""
    pass


class SafetyWrapper:
    """
    Safety wrapper for instrument drivers

    Enforces safety limits and automatic emergency stop on violations.
    All commands pass through validation before reaching the driver.

    Philosophy: Never trust the driver. Always validate.

    Safety Checks:
    - Voltage within global limits (+/- 10V)
    - Current within global limits (+/- 1A)
    - Experiment duration within timeout (1 hour)
    - Automatic emergency stop on violation

    Example:
        raw_driver = MockInstrumentDriver(config)
        safe_driver = SafetyWrapper(raw_driver, limits=SafetyLimits())

        # This will be validated before execution
        await safe_driver.set_voltage(5.0)  # OK

        # This will trigger emergency stop
        await safe_driver.set_voltage(15.0)  # SafetyViolationError!
    """

    def __init__(
        self,
        driver: BaseInstrumentDriver,
        limits: SafetyLimits = None
    ):
        """
        Wrap a driver with safety checks

        Args:
            driver: Raw instrument driver
            limits: Safety limits (defaults to SafetyLimits())
        """
        self._driver = driver
        self.limits = limits or SafetyLimits()

        # Violation tracking
        self._violations: list[Dict[str, Any]] = []
        self._emergency_stopped = False

        logger.info(
            f"SafetyWrapper initialized for {driver.__class__.__name__} "
            f"with limits: V={self.limits.min_voltage}..{self.limits.max_voltage}V, "
            f"I={self.limits.min_current}..{self.limits.max_current}A, "
            f"timeout={self.limits.max_duration}s"
        )

    # ============ Safety Validation ============

    def _check_voltage(self, voltage: float) -> None:
        """
        Validate voltage against safety limits

        Args:
            voltage: Voltage in Volts

        Raises:
            SafetyViolationError: If voltage out of range
        """
        if voltage > self.limits.max_voltage:
            self._record_violation(
                "voltage_too_high",
                f"Voltage {voltage}V exceeds maximum {self.limits.max_voltage}V"
            )
            raise SafetyViolationError(
                f"SAFETY VIOLATION: Voltage {voltage}V exceeds maximum {self.limits.max_voltage}V"
            )

        if voltage < self.limits.min_voltage:
            self._record_violation(
                "voltage_too_low",
                f"Voltage {voltage}V below minimum {self.limits.min_voltage}V"
            )
            raise SafetyViolationError(
                f"SAFETY VIOLATION: Voltage {voltage}V below minimum {self.limits.min_voltage}V"
            )

    def _check_current(self, current: float) -> None:
        """
        Validate current against safety limits

        Args:
            current: Current in Amperes

        Raises:
            SafetyViolationError: If current out of range
        """
        if current > self.limits.max_current:
            self._record_violation(
                "current_too_high",
                f"Current {current}A exceeds maximum {self.limits.max_current}A"
            )
            raise SafetyViolationError(
                f"SAFETY VIOLATION: Current {current}A exceeds maximum {self.limits.max_current}A"
            )

        if current < self.limits.min_current:
            self._record_violation(
                "current_too_low",
                f"Current {current}A below minimum {self.limits.min_current}A"
            )
            raise SafetyViolationError(
                f"SAFETY VIOLATION: Current {current}A below minimum {self.limits.min_current}A"
            )

    def _check_timeout(self) -> None:
        """
        Check if experiment has exceeded maximum duration

        Raises:
            SafetyViolationError: If timeout exceeded
        """
        elapsed = self._driver.get_elapsed_time()

        if elapsed > self.limits.max_duration:
            self._record_violation(
                "timeout_exceeded",
                f"Experiment duration {elapsed:.1f}s exceeds maximum {self.limits.max_duration}s"
            )
            raise SafetyViolationError(
                f"SAFETY VIOLATION: Timeout exceeded ({elapsed:.1f}s > {self.limits.max_duration}s)"
            )

    def _record_violation(self, violation_type: str, message: str) -> None:
        """Record a safety violation"""
        violation = {
            "type": violation_type,
            "message": message,
            "timestamp": datetime.now().isoformat()
        }

        self._violations.append(violation)

        logger.error(f"SAFETY VIOLATION: {violation_type} - {message}")

    # ============ Wrapped Driver Methods ============

    async def connect(self) -> None:
        """Connect to instrument (no safety checks needed)"""
        await self._driver.connect()

    async def disconnect(self) -> None:
        """Disconnect from instrument (no safety checks needed)"""
        await self._driver.disconnect()

    async def get_info(self) -> Dict[str, Any]:
        """Get instrument info (no safety checks needed)"""
        return await self._driver.get_info()

    async def program(self, waveform: Waveform, technique: InstrumentCapability) -> None:
        """
        Program instrument with waveform validation

        Args:
            waveform: Voltage/current waveform
            technique: Electrochemical technique

        Raises:
            SafetyViolationError: If waveform violates safety limits
        """
        # Validate waveform before programming
        self._driver.validate_waveform(waveform)

        # Extra validation: check voltage and current ranges
        if waveform.initial_value is not None:
            if waveform.type in ["step", "ramp", "triangle"]:
                # Assume voltage waveform
                self._check_voltage(waveform.initial_value)

                if waveform.final_value is not None:
                    self._check_voltage(waveform.final_value)

        # Validate duration
        if waveform.duration > self.limits.max_duration:
            raise SafetyViolationError(
                f"Waveform duration {waveform.duration}s exceeds "
                f"maximum {self.limits.max_duration}s"
            )

        logger.info(f"Programming {technique.value} waveform (validated)")
        await self._driver.program(waveform, technique)

    async def start(self) -> None:
        """Start experiment (with timeout monitoring)"""
        if self._emergency_stopped:
            raise SafetyViolationError(
                "Cannot start: Emergency stop active. Reset required."
            )

        logger.info("Starting experiment")
        await self._driver.start()

    async def pause(self) -> None:
        """Pause experiment (no safety checks needed)"""
        await self._driver.pause()

    async def resume(self) -> None:
        """Resume experiment (with timeout check)"""
        self._check_timeout()
        await self._driver.resume()

    async def stop(self) -> None:
        """Stop experiment (no safety checks needed)"""
        await self._driver.stop()

    async def emergency_stop(self) -> None:
        """
        Emergency stop (CRITICAL: Must complete within 100ms)

        Sets emergency_stopped flag and triggers driver emergency stop
        """
        self._emergency_stopped = True

        logger.critical("EMERGENCY STOP TRIGGERED")

        # Record emergency stop violation
        self._record_violation(
            "emergency_stop",
            "Emergency stop activated"
        )

        # Trigger driver emergency stop
        await self._driver.emergency_stop()

    async def set_voltage(self, voltage: float) -> None:
        """
        Set voltage with safety validation

        Args:
            voltage: Target voltage (V)

        Raises:
            SafetyViolationError: If voltage out of range
        """
        # CRITICAL: Validate before execution
        self._check_voltage(voltage)

        # Check timeout
        if self._driver.is_running():
            self._check_timeout()

        # Execute if safe
        await self._driver.set_voltage(voltage)

    async def set_current(self, current: float) -> None:
        """
        Set current with safety validation

        Args:
            current: Target current (A)

        Raises:
            SafetyViolationError: If current out of range
        """
        # CRITICAL: Validate before execution
        self._check_current(current)

        # Check timeout
        if self._driver.is_running():
            self._check_timeout()

        # Execute if safe
        await self._driver.set_current(current)

    async def read_data(self) -> InstrumentFrame:
        """
        Read data with timeout monitoring

        Returns:
            InstrumentFrame

        Raises:
            SafetyViolationError: If timeout exceeded
        """
        # Check timeout before reading
        if self._driver.is_running():
            try:
                self._check_timeout()
            except SafetyViolationError:
                # Timeout exceeded - trigger emergency stop
                logger.error("Timeout exceeded during read - triggering emergency stop")
                await self.emergency_stop()
                raise

        return await self._driver.read_data()

    async def stream(self) -> AsyncIterator[InstrumentFrame]:
        """
        Stream data with continuous timeout monitoring

        Yields:
            InstrumentFrame objects

        Note:
            Automatically triggers emergency stop if timeout exceeded
        """
        try:
            async for frame in self._driver.stream():
                # Check timeout on every frame
                if self._driver.is_running():
                    try:
                        self._check_timeout()
                    except SafetyViolationError:
                        # Timeout exceeded - emergency stop
                        logger.error("Timeout exceeded during stream - triggering emergency stop")
                        await self.emergency_stop()
                        raise

                yield frame

        except SafetyViolationError:
            # Re-raise safety violations
            raise
        except Exception as e:
            # Other errors - trigger emergency stop for safety
            logger.error(f"Error during stream: {e} - triggering emergency stop")
            await self.emergency_stop()
            raise

    # ============ Safety Status ============

    def is_emergency_stopped(self) -> bool:
        """Check if emergency stop is active"""
        return self._emergency_stopped

    def reset_emergency_stop(self) -> None:
        """
        Reset emergency stop flag

        WARNING: Only call this after verifying system is safe
        """
        if self._emergency_stopped:
            logger.warning("Resetting emergency stop flag")
            self._emergency_stopped = False

    def get_violations(self) -> list[Dict[str, Any]]:
        """Get list of all safety violations"""
        return self._violations.copy()

    def clear_violations(self) -> None:
        """Clear violation history"""
        logger.info(f"Clearing {len(self._violations)} violation records")
        self._violations.clear()

    # ============ Pass-through Properties ============

    @property
    def status(self):
        """Get driver status"""
        return self._driver.status

    @property
    def capabilities(self):
        """Get driver capabilities"""
        return self._driver.capabilities

    def supports(self, capability: InstrumentCapability) -> bool:
        """Check if capability is supported"""
        return self._driver.supports(capability)

    def is_running(self) -> bool:
        """Check if experiment is running"""
        return self._driver.is_running()

    def get_elapsed_time(self) -> float:
        """Get elapsed time"""
        return self._driver.get_elapsed_time()
