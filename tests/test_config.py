"""
Tests for configuration loading and validation.
"""

import json
import pytest

from app.models.config import HVACConfig, RoomConfig, ACSettings


def test_load_sample_config():
    """Test loading and validating the sample config.json."""
    with open("tests/fixtures/sample_config.json") as f:
        data = json.load(f)

    config = HVACConfig(**data)

    # Validate basic structure
    assert len(config.rooms) > 0, "Config should have rooms defined"
    assert config.weather.provider == "open-meteo", "Weather provider should be open-meteo"
    assert config.thresholds.ac_min_outdoor_c >= 0, "AC min outdoor temp should be reasonable"


def test_ac_settings_defaults():
    """Test ACSettings model with defaults."""
    ac = ACSettings()

    assert ac.mode == "heat"
    assert ac.fan == "auto"
    assert ac.vaneH == "auto"
    assert ac.vaneV == "auto"
    assert ac.vanes is True


def test_room_config_optional_fields():
    """Test RoomConfig with minimal fields."""
    room = RoomConfig(tado="Living Room")

    assert room.tado == "Living Room"
    assert room.mel is None
    assert room.mel_multi is None
    assert room.ac is None
    assert room.floor is None


def test_room_config_with_ac_settings():
    """Test RoomConfig with AC overrides."""
    room = RoomConfig(
        mel="Master bedroom",
        ac=ACSettings(mode="cool", fan=3, vanes=False)
    )

    assert room.mel == "Master bedroom"
    assert room.ac.mode == "cool"
    assert room.ac.fan == 3
    assert room.ac.vanes is False


def test_three_period_schedule():
    """Test three-period schedule parsing."""
    with open("tests/fixtures/sample_config.json") as f:
        data = json.load(f)

    config = HVACConfig(**data)

    # Find a room with three-period schedule (Master bedroom)
    master = config.rooms.get("Master")
    assert master is not None
    assert master.schedule is not None
    assert master.schedule.type == "three-period"
    assert master.schedule.day == 17
    assert master.schedule.eve == 19
    assert master.schedule.night == 16


def test_exclude_lists():
    """Test exclusion lists."""
    with open("tests/fixtures/sample_config.json") as f:
        data = json.load(f)

    config = HVACConfig(**data)

    assert "Hot Water" in config.exclude.tado
    assert isinstance(config.exclude.mel, list)


def test_pv_config():
    """Test PV configuration."""
    with open("tests/fixtures/sample_config.json") as f:
        data = json.load(f)

    config = HVACConfig(**data)

    assert config.pv.boost_threshold_w > 0
    assert config.pv.boost_delta_c > 0


def test_config_validation_allows_extra_fields():
    """Test that config validation allows unknown fields for forward compatibility."""
    data = {
        "exclude": {"tado": [], "mel": []},
        "ac_defaults": {"mode": "heat"},
        "rooms": {},
        "targets": {},
        "pv": {"boost_threshold_w": 600, "boost_delta_c": 0.5},
        "blackout_windows": [],
        "weather": {"lat": 51.0, "lon": 0.0},
        "thresholds": {"ac_min_outdoor_c": 2.0},
        "future_field": "allowed"  # Extra fields are allowed
    }

    # Should not raise - extra fields allowed for forward compatibility
    config = HVACConfig(**data)
    assert config.exclude.tado == []
