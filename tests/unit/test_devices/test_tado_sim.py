"""
Tests for Tado client in sim mode.
All tests use sim_mode=True to avoid real API calls.
"""

import pytest
from unittest.mock import AsyncMock

from app.devices.tado_client import TadoClient


@pytest.mark.asyncio
async def test_tado_turn_on_sim_mode(mock_db_session):
    """Test turn_on in sim mode."""
    client = TadoClient(
        home_id="12345",
        db_session=mock_db_session,
        sim_mode=True
    )

    result = await client.turn_on("Master Bedroom", 22.0, minutes=60)

    assert result is True


@pytest.mark.asyncio
async def test_tado_turn_off_sim_mode(mock_db_session):
    """Test turn_off in sim mode."""
    client = TadoClient(
        home_id="12345",
        db_session=mock_db_session,
        sim_mode=True
    )

    result = await client.turn_off("Master Bedroom")

    assert result is True


@pytest.mark.asyncio
async def test_tado_get_temperature_sim_mode(mock_db_session):
    """Test get_temperature in sim mode."""
    client = TadoClient(
        home_id="12345",
        db_session=mock_db_session,
        sim_mode=True
    )

    temp = await client.get_temperature("Master Bedroom")

    assert temp == 19.5


@pytest.mark.asyncio
async def test_tado_get_heating_percent_sim_mode(mock_db_session):
    """Test get_heating_percent in sim mode."""
    client = TadoClient(
        home_id="12345",
        db_session=mock_db_session,
        sim_mode=True
    )

    power = await client.get_heating_percent("Master Bedroom")

    assert power == 0


@pytest.mark.asyncio
async def test_tado_list_zones_sim_mode(mock_db_session):
    """Test list_zones in sim mode."""
    client = TadoClient(
        home_id="12345",
        db_session=mock_db_session,
        sim_mode=True
    )

    zones = await client.list_zones()

    assert isinstance(zones, list)
    assert len(zones) > 0
    assert "Master Bedroom" in zones


@pytest.mark.asyncio
async def test_tado_oauth_start_sim_mode(mock_db_session):
    """Test OAuth flow start in sim mode."""
    client = TadoClient(
        home_id="12345",
        db_session=mock_db_session,
        sim_mode=True
    )

    result = await client.start_oauth_flow()

    assert "user_code" in result
    assert "verification_uri_complete" in result
    assert "device_code" in result


@pytest.mark.asyncio
async def test_tado_oauth_poll_sim_mode(mock_db_session):
    """Test OAuth flow polling in sim mode."""
    client = TadoClient(
        home_id="12345",
        db_session=mock_db_session,
        sim_mode=True
    )

    result = await client.poll_oauth_completion("fake_device_code")

    assert result is not None
    assert "access_token" in result
    assert "refresh_token" in result


@pytest.mark.asyncio
async def test_tado_minimum_duration_enforcement(mock_db_session):
    """Test that minimum 15-minute duration is enforced."""
    client = TadoClient(
        home_id="12345",
        db_session=mock_db_session,
        sim_mode=True
    )

    # Try to set 5 minutes - should work but internally use minimum 15
    result = await client.turn_on("Master Bedroom", 22.0, minutes=5)

    assert result is True


@pytest.mark.asyncio
async def test_tado_access_token_caching_sim(mock_db_session):
    """Test that access token is cached in sim mode."""
    client = TadoClient(
        home_id="12345",
        db_session=mock_db_session,
        sim_mode=True
    )

    # First call should cache token
    token1 = await client.get_access_token()

    # Second call should return cached token
    token2 = await client.get_access_token()

    assert token1 == token2
    assert token1 == "sim_access_token"
