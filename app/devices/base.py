"""
Base device interface for all HVAC device clients.
All device drivers inherit from DeviceClient and implement sim mode.
"""

from abc import ABC, abstractmethod
from typing import Optional


class DeviceClient(ABC):
    """
    Abstract base class for all device clients (Tado, MELCloud, Weather).

    All clients MUST support sim_mode to prevent accidentally controlling
    real devices during development/testing.
    """

    def __init__(self, sim_mode: bool = False):
        """
        Initialize device client.

        Args:
            sim_mode: If True, log actions but don't make real API calls.
                     Returns fake but realistic data for testing.
        """
        self.sim_mode = sim_mode

    @abstractmethod
    async def turn_on(
        self,
        device_name: str,
        setpoint: float,
        **kwargs
    ) -> bool:
        """
        Turn on device with target setpoint.

        Args:
            device_name: Name of device/zone to control
            setpoint: Target temperature in Celsius
            **kwargs: Device-specific options (AC mode, fan speed, etc.)

        Returns:
            True on success, False on failure
        """
        pass

    @abstractmethod
    async def turn_off(self, device_name: str) -> bool:
        """
        Turn off device.

        Args:
            device_name: Name of device/zone to control

        Returns:
            True on success, False on failure
        """
        pass

    @abstractmethod
    async def get_temperature(self, device_name: str) -> Optional[float]:
        """
        Get current room temperature from device.

        Args:
            device_name: Name of device/zone to read

        Returns:
            Temperature in Celsius, or None on failure
        """
        pass
