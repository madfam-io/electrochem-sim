"""
Base Instrument Driver Interface

Abstract base class for all potentiostat drivers with strict typing.
Ensures consistent interface across Gamry, BioLogic, and mock drivers.

RFC-002: Hardware Abstraction Layer - Driver Interface
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Any, List, Optional
from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class InstrumentCapability(Enum):
    """Supported electrochemical techniques"""
    CV = "cyclic_voltammetry"
    CA = "chronoamperometry"
    CP = "chronopotentiometry"
    EIS = "electrochemical_impedance_spectroscopy"
    LSV = "linear_sweep_voltammetry"
    DPV = "differential_pulse_voltammetry"


class ConnectionConfig(BaseModel):
    """Connection parameters (vendor-specific)"""
    host: Optional[str] = None  # For network instruments
    port: Optional[int] = None
    serial_port: Optional[str] = None  # For USB/serial
    device_id: Optional[str] = None
    timeout: float = 5.0

    # Mock-specific
    seed: Optional[int] = None  # For reproducible testing
    noise_level: float = 0.05  # Noise amplitude (fraction of signal)


class Waveform(BaseModel):
    """Experiment waveform definition"""
    type: str = Field(..., description="step, ramp, triangle, sine")
    duration: float = Field(..., gt=0, description="Duration in seconds")
    initial_value: float = Field(..., description="Initial voltage (V) or current (A)")
    final_value: Optional[float] = None
    scan_rate: Optional[float] = None  # V/s for CV
    frequency: Optional[float] = None  # Hz for EIS
    amplitude: Optional[float] = None


class SafetyLimits(BaseModel):
    """Safety interlocks - enforced by SafetyWrapper"""
    max_voltage: float = Field(10.0, description="Maximum voltage (V)")
    min_voltage: float = Field(-10.0, description="Minimum voltage (V)")
    max_current: float = Field(1.0, description="Maximum current (A)")
    min_current: float = Field(-1.0, description="Minimum current (A)")
    max_duration: float = Field(3600.0, description="Maximum duration (s)")
    emergency_stop_on_disconnect: bool = True


class InstrumentFrame(BaseModel):
    """Single data point from instrument"""
    timestamp: float = Field(..., description="Unix epoch milliseconds")
    time: float = Field(..., description="Experiment time (s)")
    voltage: float = Field(..., description="Voltage (V)")
    current: float = Field(..., description="Current (A)")
    charge: Optional[float] = Field(None, description="Integrated charge (C)")
    impedance: Optional[complex] = Field(None, description="Impedance (Ω) for EIS")
    frequency: Optional[float] = Field(None, description="Frequency (Hz) for EIS")

    class Config:
        arbitrary_types_allowed = True  # Allow complex numbers


class InstrumentStatus(Enum):
    """Instrument connection and operation status"""
    DISCONNECTED = "disconnected"
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


class BaseInstrumentDriver(ABC):
    """
    Abstract interface for all potentiostat drivers

    All drivers must implement this interface to ensure:
    - Consistent API across vendors
    - Type safety for critical operations
    - Safety interlock compatibility

    Example:
        class GamryDriver(BaseInstrumentDriver):
            async def connect(self):
                # Gamry-specific connection logic
                pass

            async def set_voltage(self, voltage: float):
                # Gamry command: set voltage
                pass
    """

    def __init__(self, config: ConnectionConfig):
        self.config = config
        self.status = InstrumentStatus.DISCONNECTED
        self.capabilities: List[InstrumentCapability] = []
        self.safety_limits = SafetyLimits()

        # Experiment state
        self._running = False
        self._start_time: Optional[datetime] = None
        self._waveform: Optional[Waveform] = None
        self._technique: Optional[InstrumentCapability] = None

    # ============ Connection Management ============

    @abstractmethod
    async def connect(self) -> None:
        """
        Establish connection to instrument

        Raises:
            ConnectionError: If connection fails
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection gracefully"""
        pass

    @abstractmethod
    async def get_info(self) -> Dict[str, Any]:
        """
        Get instrument metadata

        Returns:
            Dict with keys: vendor, model, serial, firmware
        """
        pass

    # ============ Experiment Control ============

    @abstractmethod
    async def program(self, waveform: Waveform, technique: InstrumentCapability) -> None:
        """
        Program the instrument with experiment parameters

        Args:
            waveform: Voltage/current waveform definition
            technique: Electrochemical technique to use

        Raises:
            ValueError: If waveform invalid or technique not supported
        """
        pass

    @abstractmethod
    async def start(self) -> None:
        """
        Start the experiment

        Must set self._running = True and self._start_time
        """
        pass

    @abstractmethod
    async def pause(self) -> None:
        """Pause the experiment (if supported)"""
        pass

    @abstractmethod
    async def resume(self) -> None:
        """Resume a paused experiment"""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """
        Stop the experiment gracefully

        Must set self._running = False
        """
        pass

    @abstractmethod
    async def emergency_stop(self) -> None:
        """
        Immediate stop (safety critical)

        MUST complete within 100ms
        MUST set output to 0V/0A
        """
        pass

    # ============ Critical Control Methods ============

    @abstractmethod
    async def set_voltage(self, voltage: float) -> None:
        """
        Set output voltage

        Args:
            voltage: Target voltage in Volts

        Raises:
            ValueError: If voltage out of safety limits

        CRITICAL: Must be validated by SafetyWrapper before execution
        """
        pass

    @abstractmethod
    async def set_current(self, current: float) -> None:
        """
        Set output current

        Args:
            current: Target current in Amperes

        Raises:
            ValueError: If current out of safety limits

        CRITICAL: Must be validated by SafetyWrapper before execution
        """
        pass

    @abstractmethod
    async def read_data(self) -> InstrumentFrame:
        """
        Read single data point from instrument

        Returns:
            InstrumentFrame with current measurement

        CRITICAL: Must return valid data within timeout period
        """
        pass

    # ============ Data Streaming ============

    @abstractmethod
    async def stream(self) -> AsyncIterator[InstrumentFrame]:
        """
        Stream data points in real-time

        Yields:
            InstrumentFrame objects at instrument sampling rate

        Example:
            async for frame in driver.stream():
                await redis_publisher.publish(frame)
        """
        pass

    # ============ Capabilities ============

    def supports(self, capability: InstrumentCapability) -> bool:
        """Check if technique is supported"""
        return capability in self.capabilities

    def is_running(self) -> bool:
        """Check if experiment is currently running"""
        return self._running

    def get_elapsed_time(self) -> float:
        """Get elapsed time since experiment start (seconds)"""
        if not self._start_time:
            return 0.0
        return (datetime.now() - self._start_time).total_seconds()

    # ============ Safety Validation ============

    def validate_waveform(self, waveform: Waveform) -> None:
        """
        Validate waveform against safety limits

        Raises:
            ValueError: If waveform violates safety limits
        """
        if waveform.initial_value > self.safety_limits.max_voltage:
            raise ValueError(
                f"Initial voltage {waveform.initial_value}V exceeds "
                f"maximum {self.safety_limits.max_voltage}V"
            )

        if waveform.initial_value < self.safety_limits.min_voltage:
            raise ValueError(
                f"Initial voltage {waveform.initial_value}V below "
                f"minimum {self.safety_limits.min_voltage}V"
            )

        if waveform.final_value is not None:
            if waveform.final_value > self.safety_limits.max_voltage:
                raise ValueError(
                    f"Final voltage {waveform.final_value}V exceeds "
                    f"maximum {self.safety_limits.max_voltage}V"
                )

            if waveform.final_value < self.safety_limits.min_voltage:
                raise ValueError(
                    f"Final voltage {waveform.final_value}V below "
                    f"minimum {self.safety_limits.min_voltage}V"
                )

        if waveform.duration > self.safety_limits.max_duration:
            raise ValueError(
                f"Duration {waveform.duration}s exceeds "
                f"maximum {self.safety_limits.max_duration}s"
            )
