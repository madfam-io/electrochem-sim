"""
Mock Instrument Driver

Simulates a potentiostat with realistic electrochemical behavior.
Generates "duck-shaped" cyclic voltammetry curves with noise for testing.

RFC-002: Hardware Abstraction Layer - Mock Driver
"""

import asyncio
import numpy as np
from typing import AsyncIterator, Dict, Any
from datetime import datetime
import logging

from .base import (
    BaseInstrumentDriver,
    InstrumentCapability,
    ConnectionConfig,
    Waveform,
    InstrumentFrame,
    InstrumentStatus
)

logger = logging.getLogger(__name__)


class MockInstrumentDriver(BaseInstrumentDriver):
    """
    Mock driver for testing without real hardware

    Simulates realistic electrochemical behavior:
    - Cyclic Voltammetry (CV): "Duck-shaped" hysteresis loop
    - Chronoamperometry (CA): Cottrell decay
    - Chronopotentiometry (CP): Potential drift

    Deterministic with seed for reproducible integration tests
    """

    def __init__(self, config: ConnectionConfig):
        super().__init__(config)

        # Set capabilities
        self.capabilities = [
            InstrumentCapability.CV,
            InstrumentCapability.CA,
            InstrumentCapability.CP,
            InstrumentCapability.LSV
        ]

        # Random number generator (for reproducible tests)
        self.rng = np.random.default_rng(config.seed)

        # Noise parameters
        self.noise_level = config.noise_level or 0.05

        # Simulation state
        self._current_voltage = 0.0
        self._current_current = 0.0
        self._sampling_rate = 100  # Hz

        # Electrochemical parameters (realistic for Fe(CN)6^3-/4- system)
        self.E0 = 0.2  # V (formal potential)
        self.n = 1  # electrons transferred
        self.A = 0.01  # cm² electrode area
        self.D = 7.6e-6  # cm²/s diffusion coefficient
        self.C_bulk = 1e-3  # M bulk concentration
        self.k0 = 0.01  # cm/s standard rate constant
        self.alpha = 0.5  # transfer coefficient

        # Constants
        self.F = 96485  # C/mol
        self.R = 8.314  # J/(mol·K)
        self.T = 298  # K

    async def connect(self) -> None:
        """Simulate connection delay"""
        await asyncio.sleep(0.1)  # 100ms connection time
        self.status = InstrumentStatus.IDLE
        logger.info(f"MockDriver connected (seed={self.config.seed})")

    async def disconnect(self) -> None:
        """Simulate disconnect"""
        await asyncio.sleep(0.05)
        self.status = InstrumentStatus.DISCONNECTED
        logger.info("MockDriver disconnected")

    async def get_info(self) -> Dict[str, Any]:
        """Return mock instrument metadata"""
        return {
            "vendor": "Mock Instruments Inc.",
            "model": "MockStat 3000",
            "serial": f"MOCK-{self.config.seed or 0:05d}",
            "firmware": "1.0.0-mock",
            "capabilities": [c.value for c in self.capabilities],
            "sampling_rate_hz": self._sampling_rate
        }

    async def program(self, waveform: Waveform, technique: InstrumentCapability) -> None:
        """Store waveform for simulation"""
        self.validate_waveform(waveform)

        if not self.supports(technique):
            raise ValueError(
                f"Technique {technique.value} not supported. "
                f"Available: {[c.value for c in self.capabilities]}"
            )

        self._waveform = waveform
        self._technique = technique

        logger.info(
            f"Programmed {technique.value}: "
            f"{waveform.type} waveform, duration={waveform.duration}s"
        )

    async def start(self) -> None:
        """Start experiment"""
        if not self._waveform:
            raise RuntimeError("No waveform programmed")

        self._running = True
        self._start_time = datetime.now()
        self.status = InstrumentStatus.RUNNING

        logger.info(f"Started {self._technique.value} experiment")

    async def pause(self) -> None:
        """Pause experiment"""
        self._running = False
        self.status = InstrumentStatus.PAUSED
        logger.info("Paused experiment")

    async def resume(self) -> None:
        """Resume experiment"""
        self._running = True
        self.status = InstrumentStatus.RUNNING
        logger.info("Resumed experiment")

    async def stop(self) -> None:
        """Stop experiment"""
        self._running = False
        self.status = InstrumentStatus.IDLE
        self._current_voltage = 0.0
        self._current_current = 0.0
        logger.info("Stopped experiment")

    async def emergency_stop(self) -> None:
        """Emergency stop (immediate)"""
        self._running = False
        self.status = InstrumentStatus.IDLE
        self._current_voltage = 0.0
        self._current_current = 0.0
        logger.critical("EMERGENCY STOP - MockDriver")

    async def set_voltage(self, voltage: float) -> None:
        """Set output voltage"""
        self._current_voltage = voltage

    async def set_current(self, current: float) -> None:
        """Set output current"""
        self._current_current = current

    async def read_data(self) -> InstrumentFrame:
        """Read single data point"""
        t = self.get_elapsed_time()
        V = self._get_voltage_at_time(t)
        I = self._simulate_current(V, t)

        return InstrumentFrame(
            timestamp=datetime.now().timestamp() * 1000,
            time=t,
            voltage=V,
            current=I
        )

    async def stream(self) -> AsyncIterator[InstrumentFrame]:
        """
        Stream data at sampling rate

        Generates realistic electrochemical response based on technique
        """
        if not self._running or not self._waveform:
            raise RuntimeError("Experiment not running")

        dt = 1.0 / self._sampling_rate
        duration = self._waveform.duration

        t = 0.0
        while t < duration and self._running:
            # Calculate voltage from waveform
            V = self._get_voltage_at_time(t)

            # Simulate current response
            I = self._simulate_current(V, t)

            # Create frame
            frame = InstrumentFrame(
                timestamp=datetime.now().timestamp() * 1000,
                time=t,
                voltage=V,
                current=I
            )

            yield frame

            # Wait for next sample
            await asyncio.sleep(dt)
            t += dt

        logger.info(f"Stream completed: {t:.2f}s elapsed")

    def _get_voltage_at_time(self, t: float) -> float:
        """
        Calculate voltage from waveform at given time

        Args:
            t: Time in seconds

        Returns:
            Voltage in Volts
        """
        if not self._waveform:
            return 0.0

        waveform = self._waveform

        if waveform.type == "step":
            return waveform.initial_value

        elif waveform.type == "ramp":
            # Linear ramp
            slope = (waveform.final_value - waveform.initial_value) / waveform.duration
            V = waveform.initial_value + slope * t
            return V

        elif waveform.type == "triangle":
            # CV triangle wave (creates "duck shape")
            V_min = waveform.initial_value
            V_max = waveform.final_value or -waveform.initial_value
            period = waveform.duration

            # Forward scan: 0 to period/2
            # Reverse scan: period/2 to period
            if t < period / 2:
                # Forward scan
                V = V_min + (V_max - V_min) * (t / (period / 2))
            else:
                # Reverse scan
                V = V_max - (V_max - V_min) * ((t - period / 2) / (period / 2))

            return V

        elif waveform.type == "sine":
            # Sinusoidal (for EIS)
            freq = waveform.frequency or 1.0
            amp = waveform.amplitude or 0.01
            V = waveform.initial_value + amp * np.sin(2 * np.pi * freq * t)
            return V

        else:
            return waveform.initial_value

    def _simulate_current(self, voltage: float, time: float) -> float:
        """
        Simulate current response using Butler-Volmer + mass transport

        Creates realistic "duck-shaped" CV curve with hysteresis

        Args:
            voltage: Applied voltage (V)
            time: Experiment time (s)

        Returns:
            Current in Amperes
        """
        if self._technique == InstrumentCapability.CV:
            return self._simulate_cv_current(voltage, time)
        elif self._technique == InstrumentCapability.CA:
            return self._simulate_ca_current(voltage, time)
        elif self._technique == InstrumentCapability.CP:
            return self._simulate_cp_current(time)
        else:
            return self._simulate_cv_current(voltage, time)

    def _simulate_cv_current(self, V: float, t: float) -> float:
        """
        Simulate CV current (Randles-Sevcik-like behavior)

        Creates "duck-shaped" hysteresis loop characteristic of reversible CV

        Args:
            V: Voltage (V)
            t: Time (s)

        Returns:
            Current (A)
        """
        # Overpotential relative to formal potential
        eta = V - self.E0

        # Butler-Volmer kinetics
        k_red = self.k0 * np.exp(-self.alpha * self.n * self.F * eta / (self.R * self.T))
        k_ox = self.k0 * np.exp((1 - self.alpha) * self.n * self.F * eta / (self.R * self.T))

        # Nernst equation for surface concentrations (simplified)
        theta = np.exp(self.n * self.F * (V - self.E0) / (self.R * self.T))
        C_red_surf = self.C_bulk / (1 + theta)
        C_ox_surf = self.C_bulk - C_red_surf

        # Faradaic current (Butler-Volmer)
        i_f = self.n * self.F * self.A * (
            k_ox * C_red_surf - k_red * C_ox_surf
        )

        # Add capacitive current (creates "duck beak" at vertex)
        # Scan rate from waveform
        if self._waveform and hasattr(self._waveform, 'scan_rate'):
            scan_rate = self._waveform.scan_rate or 0.1  # V/s
        else:
            # Estimate from waveform
            if self._waveform and self._waveform.final_value:
                dV = abs(self._waveform.final_value - self._waveform.initial_value)
                scan_rate = dV / (self._waveform.duration / 2)
            else:
                scan_rate = 0.1

        C_dl = 20e-6  # F/cm² double layer capacitance
        i_c = self.A * C_dl * scan_rate

        # Total current
        i_total = i_f + i_c

        # Add noise
        noise = self.rng.normal(0, abs(i_total) * self.noise_level)

        return float(i_total + noise)

    def _simulate_ca_current(self, V: float, t: float) -> float:
        """
        Simulate Chronoamperometry current (Cottrell equation)

        Args:
            V: Voltage (V)
            t: Time (s)

        Returns:
            Current (A)
        """
        # Cottrell equation: i = nFAC√(D/(πt))
        if t < 1e-3:
            t = 1e-3  # Avoid division by zero

        i_cottrell = (
            self.n * self.F * self.A * self.C_bulk *
            np.sqrt(self.D / (np.pi * t))
        )

        # Add noise
        noise = self.rng.normal(0, abs(i_cottrell) * self.noise_level)

        return float(i_cottrell + noise)

    def _simulate_cp_current(self, t: float) -> float:
        """
        Simulate Chronopotentiometry (constant current)

        Args:
            t: Time (s)

        Returns:
            Current (A) - constant value
        """
        # Return constant current from set_current
        i_const = self._current_current or 1e-6  # Default 1 µA

        # Add noise
        noise = self.rng.normal(0, abs(i_const) * self.noise_level)

        return float(i_const + noise)
