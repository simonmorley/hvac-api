"""
Tests for base device interface.
"""

import pytest
from app.devices.base import DeviceClient


class ConcreteDevice(DeviceClient):
    """Concrete implementation for testing abstract base class."""

    async def turn_on(self, device_name: str, setpoint: float, **kwargs) -> bool:
        if self.sim_mode:
            return True
        return False

    async def turn_off(self, device_name: str) -> bool:
        if self.sim_mode:
            return True
        return False

    async def get_temperature(self, device_name: str) -> float:
        if self.sim_mode:
            return 20.0
        return 0.0


@pytest.mark.asyncio
async def test_device_sim_mode_enabled():
    """Test that sim mode can be enabled."""
    device = ConcreteDevice(sim_mode=True)
    assert device.sim_mode is True


@pytest.mark.asyncio
async def test_device_sim_mode_disabled():
    """Test that sim mode defaults to False."""
    device = ConcreteDevice()
    assert device.sim_mode is False


@pytest.mark.asyncio
async def test_device_turn_on_sim_mode():
    """Test turn_on works in sim mode."""
    device = ConcreteDevice(sim_mode=True)
    result = await device.turn_on("TestDevice", 22.0)
    assert result is True


@pytest.mark.asyncio
async def test_device_turn_off_sim_mode():
    """Test turn_off works in sim mode."""
    device = ConcreteDevice(sim_mode=True)
    result = await device.turn_off("TestDevice")
    assert result is True


@pytest.mark.asyncio
async def test_device_get_temperature_sim_mode():
    """Test get_temperature works in sim mode."""
    device = ConcreteDevice(sim_mode=True)
    temp = await device.get_temperature("TestDevice")
    assert temp == 20.0
