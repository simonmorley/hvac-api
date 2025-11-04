"""
Tests for MELCloud EffectiveFlags bitmap calculation.
Critical for proper AC control - wrong flags = API failure.
"""

import pytest
from app.devices.melcloud_client import MELCloudClient


def test_effective_flags_power_only(mock_db_session):
    """Test EffectiveFlags with only power flag."""
    client = MELCloudClient(
        email="test@example.com",
        password="test",
        db_session=mock_db_session,
        sim_mode=True
    )

    flags = client._calculate_flags(power=True)

    assert flags == 0x01


def test_effective_flags_power_and_setpoint(mock_db_session):
    """Test EffectiveFlags with power and setpoint."""
    client = MELCloudClient(
        email="test@example.com",
        password="test",
        db_session=mock_db_session,
        sim_mode=True
    )

    flags = client._calculate_flags(power=True, setpoint=True)

    assert flags == 0x05  # 0x01 | 0x04


def test_effective_flags_all(mock_db_session):
    """Test EffectiveFlags with all flags enabled."""
    client = MELCloudClient(
        email="test@example.com",
        password="test",
        db_session=mock_db_session,
        sim_mode=True
    )

    flags = client._calculate_flags(
        power=True,
        mode=True,
        setpoint=True,
        fan=True,
        vanes=True
    )

    # Power(0x01) + Mode(0x02) + Setpoint(0x04) + Fan(0x08) + VaneV(0x10) + VaneH(0x100)
    assert flags == 0x11F


def test_effective_flags_no_vanes(mock_db_session):
    """Test EffectiveFlags without vane control (ducted units)."""
    client = MELCloudClient(
        email="test@example.com",
        password="test",
        db_session=mock_db_session,
        sim_mode=True
    )

    flags = client._calculate_flags(
        power=True,
        mode=True,
        setpoint=True,
        fan=True,
        vanes=False
    )

    # Power(0x01) + Mode(0x02) + Setpoint(0x04) + Fan(0x08)
    assert flags == 0x0F


def test_mode_to_int_heat(mock_db_session):
    """Test mode string to integer conversion - heat."""
    client = MELCloudClient(
        email="test@example.com",
        password="test",
        db_session=mock_db_session,
        sim_mode=True
    )

    assert client._mode_to_int("heat") == 1


def test_mode_to_int_cool(mock_db_session):
    """Test mode string to integer conversion - cool."""
    client = MELCloudClient(
        email="test@example.com",
        password="test",
        db_session=mock_db_session,
        sim_mode=True
    )

    assert client._mode_to_int("cool") == 2


def test_mode_to_int_dry(mock_db_session):
    """Test mode string to integer conversion - dry."""
    client = MELCloudClient(
        email="test@example.com",
        password="test",
        db_session=mock_db_session,
        sim_mode=True
    )

    assert client._mode_to_int("dry") == 3


def test_mode_to_int_fan(mock_db_session):
    """Test mode string to integer conversion - fan."""
    client = MELCloudClient(
        email="test@example.com",
        password="test",
        db_session=mock_db_session,
        sim_mode=True
    )

    assert client._mode_to_int("fan") == 7


def test_mode_to_int_auto(mock_db_session):
    """Test mode string to integer conversion - auto."""
    client = MELCloudClient(
        email="test@example.com",
        password="test",
        db_session=mock_db_session,
        sim_mode=True
    )

    assert client._mode_to_int("auto") == 8


def test_fan_to_int_auto(mock_db_session):
    """Test fan setting conversion - auto."""
    client = MELCloudClient(
        email="test@example.com",
        password="test",
        db_session=mock_db_session,
        sim_mode=True
    )

    assert client._fan_to_int("auto") == 0


def test_fan_to_int_numeric(mock_db_session):
    """Test fan setting conversion - numeric speed."""
    client = MELCloudClient(
        email="test@example.com",
        password="test",
        db_session=mock_db_session,
        sim_mode=True
    )

    assert client._fan_to_int(3) == 3
