"""
Tests for Weather client.
"""

import pytest
from app.devices.weather_client import WeatherClient


@pytest.mark.asyncio
async def test_weather_get_temperature_sim_mode():
    """Test get_outdoor_temperature in sim mode."""
    client = WeatherClient(
        latitude=51.4184637,
        longitude=0.0135339,
        sim_mode=True
    )

    temp = await client.get_outdoor_temperature()

    assert temp == 12.0


@pytest.mark.asyncio
async def test_weather_caching_sim_mode():
    """Test that temperature is cached in sim mode."""
    client = WeatherClient(
        latitude=51.4184637,
        longitude=0.0135339,
        sim_mode=True
    )

    # First call should cache
    temp1 = await client.get_outdoor_temperature()

    # Second call should return cached value
    temp2 = await client.get_outdoor_temperature()

    assert temp1 == temp2
    assert temp1 == 12.0


@pytest.mark.asyncio
async def test_weather_sim_mode_enabled():
    """Test that sim mode is properly set."""
    client = WeatherClient(
        latitude=51.4184637,
        longitude=0.0135339,
        sim_mode=True
    )

    assert client.sim_mode is True


@pytest.mark.asyncio
async def test_weather_sim_mode_disabled():
    """Test that sim mode defaults to False."""
    client = WeatherClient(
        latitude=51.4184637,
        longitude=0.0135339
    )

    assert client.sim_mode is False
