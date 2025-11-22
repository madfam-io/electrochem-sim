"""
Driver Registry - Plugin Architecture

Manages registration and instantiation of instrument drivers.
Designed for future plugin directory scanning while currently using dict-based registration.

RFC-002: Hardware Abstraction Layer - Plugin System
"""

import importlib
import logging
from typing import Dict, List, Type, Optional
from pathlib import Path

from services.hal.drivers.base import BaseInstrumentDriver, ConnectionConfig

logger = logging.getLogger(__name__)


class DriverRegistry:
    """
    Registry for instrument drivers with plugin architecture

    Current: Dictionary-based registration
    Future: Auto-discovery from plugins/ directory

    Example:
        registry = DriverRegistry()
        registry.register("mock", MockInstrumentDriver)
        registry.register("gamry", GamryDriver)

        driver = registry.create("mock", ConnectionConfig())
    """

    def __init__(self, plugin_dir: Optional[str] = None):
        """
        Initialize driver registry

        Args:
            plugin_dir: Optional directory to scan for plugins (future feature)
        """
        self._drivers: Dict[str, Type[BaseInstrumentDriver]] = {}
        self._plugin_dir = plugin_dir

        logger.info("DriverRegistry initialized")

    def register(self, name: str, driver_class: Type[BaseInstrumentDriver]) -> None:
        """
        Register a driver implementation

        Args:
            name: Driver identifier (e.g., "mock", "gamry", "biologic")
            driver_class: Driver class (must inherit from BaseInstrumentDriver)

        Raises:
            TypeError: If driver_class doesn't inherit from BaseInstrumentDriver
            ValueError: If driver name already registered

        Example:
            registry.register("mock", MockInstrumentDriver)
        """
        # Validate driver class
        if not issubclass(driver_class, BaseInstrumentDriver):
            raise TypeError(
                f"Driver class {driver_class.__name__} must inherit from BaseInstrumentDriver"
            )

        # Check for duplicates
        if name in self._drivers:
            logger.warning(f"Driver '{name}' already registered, overwriting")

        # Register
        self._drivers[name] = driver_class
        logger.info(f"Registered driver: {name} -> {driver_class.__name__}")

    def unregister(self, name: str) -> None:
        """
        Unregister a driver

        Args:
            name: Driver identifier

        Raises:
            KeyError: If driver not found
        """
        if name not in self._drivers:
            raise KeyError(f"Driver '{name}' not registered")

        del self._drivers[name]
        logger.info(f"Unregistered driver: {name}")

    def create(self, name: str, config: ConnectionConfig) -> BaseInstrumentDriver:
        """
        Instantiate a driver by name

        Args:
            name: Driver identifier
            config: Connection configuration

        Returns:
            Instantiated driver

        Raises:
            KeyError: If driver not registered

        Example:
            config = ConnectionConfig(seed=42, noise_level=0.05)
            driver = registry.create("mock", config)
            await driver.connect()
        """
        if name not in self._drivers:
            raise KeyError(
                f"Unknown driver: '{name}'. "
                f"Available drivers: {self.list_drivers()}"
            )

        driver_class = self._drivers[name]
        driver = driver_class(config)

        logger.info(f"Created driver instance: {name} ({driver_class.__name__})")
        return driver

    def list_drivers(self) -> List[str]:
        """
        List all registered driver names

        Returns:
            List of driver identifiers

        Example:
            >>> registry.list_drivers()
            ['mock', 'gamry', 'biologic']
        """
        return sorted(self._drivers.keys())

    def get_driver_info(self, name: str) -> Dict[str, any]:
        """
        Get information about a registered driver

        Args:
            name: Driver identifier

        Returns:
            Dict with driver metadata

        Raises:
            KeyError: If driver not found
        """
        if name not in self._drivers:
            raise KeyError(f"Driver '{name}' not registered")

        driver_class = self._drivers[name]

        return {
            "name": name,
            "class": driver_class.__name__,
            "module": driver_class.__module__,
            "docstring": driver_class.__doc__,
        }

    def scan_plugins(self, plugin_dir: Optional[str] = None) -> int:
        """
        Scan plugin directory for driver implementations (future feature)

        Args:
            plugin_dir: Directory to scan (defaults to self._plugin_dir)

        Returns:
            Number of plugins discovered

        Note:
            Currently returns 0 (not implemented).
            Future: Scan for Python files implementing BaseInstrumentDriver.

        Design:
            1. List all .py files in plugin_dir
            2. Import each module
            3. Find classes inheriting from BaseInstrumentDriver
            4. Auto-register with class name as identifier

        Example (future):
            # plugins/gamry_driver.py
            class GamryDriver(BaseInstrumentDriver):
                pass

            # Auto-discovered and registered as "GamryDriver"
        """
        plugin_dir = plugin_dir or self._plugin_dir

        if not plugin_dir:
            logger.debug("No plugin directory configured")
            return 0

        plugin_path = Path(plugin_dir)

        if not plugin_path.exists():
            logger.warning(f"Plugin directory does not exist: {plugin_dir}")
            return 0

        # Future implementation:
        # 1. Discover .py files
        # 2. Import and inspect classes
        # 3. Auto-register drivers
        # 4. Handle errors gracefully

        logger.info(f"Plugin scanning not yet implemented (target: {plugin_dir})")
        return 0


# Global registry instance
registry = DriverRegistry()


def get_registry() -> DriverRegistry:
    """Get the global driver registry"""
    return registry
