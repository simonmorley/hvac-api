"""
Tests for MELCloud client in sim mode.
All tests use sim_mode=True to avoid real API calls.
"""

import pytest
from app.devices.melcloud_client import MELCloudClient


@pytest.mark.asyncio
async def test_melcloud_turn_on_sim_mode(mock_db_session):
    """Test turn_on in sim mode."""
    client = MELCloudClient(
        email="test@example.com",
        password="test",
        db_session=mock_db_session,
        sim_mode=True
    )

    result = await client.turn_on("Living", 23.0, mode="heat", fan=3)

    assert result is True


@pytest.mark.asyncio
async def test_melcloud_turn_on_with_vanes_disabled(mock_db_session):
    """Test turn_on with vanes disabled (for ducted units)."""
    client = MELCloudClient(
        email="test@example.com",
        password="test",
        db_session=mock_db_session,
        sim_mode=True
    )

    result = await client.turn_on("Living", 23.0, vanes=False)

    assert result is True


@pytest.mark.asyncio
async def test_melcloud_turn_off_sim_mode(mock_db_session):
    """Test turn_off in sim mode."""
    client = MELCloudClient(
        email="test@example.com",
        password="test",
        db_session=mock_db_session,
        sim_mode=True
    )

    result = await client.turn_off("Living")

    assert result is True


@pytest.mark.asyncio
async def test_melcloud_get_temperature_sim_mode(mock_db_session):
    """Test get_temperature in sim mode."""
    client = MELCloudClient(
        email="test@example.com",
        password="test",
        db_session=mock_db_session,
        sim_mode=True
    )

    temp = await client.get_temperature("Living")

    assert temp == 20.0


@pytest.mark.asyncio
async def test_melcloud_get_device_state_sim_mode(mock_db_session):
    """Test get_device_state in sim mode."""
    client = MELCloudClient(
        email="test@example.com",
        password="test",
        db_session=mock_db_session,
        sim_mode=True
    )

    state = await client.get_device_state("Living")

    assert state is not None
    assert "Power" in state
    assert "RoomTemperature" in state
    assert "SetTemperature" in state


@pytest.mark.asyncio
async def test_melcloud_list_devices_sim_mode(mock_db_session):
    """Test list_devices in sim mode."""
    client = MELCloudClient(
        email="test@example.com",
        password="test",
        db_session=mock_db_session,
        sim_mode=True
    )

    devices = await client.list_devices()

    assert isinstance(devices, list)
    assert len(devices) > 0
    assert "Living" in devices


@pytest.mark.asyncio
async def test_melcloud_session_token_caching_sim(mock_db_session):
    """Test that session token is cached in sim mode."""
    client = MELCloudClient(
        email="test@example.com",
        password="test",
        db_session=mock_db_session,
        sim_mode=True
    )

    # First call should cache token
    token1 = await client.get_session_token()

    # Second call should return cached token
    token2 = await client.get_session_token()

    assert token1 == token2
    assert token1 == "sim_context_key"
