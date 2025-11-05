"""
Domain models for room status and device state.

These are pure data structures with no business logic dependencies.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class DeviceState:
    """State of a single HVAC device (AC or radiator)."""
    current_temp: Optional[float] = None
    target_temp: Optional[float] = None
    power: bool = False
    heating: bool = False
    heating_percent: int = 0
    mode: Optional[int] = None


@dataclass
class RoomStatus:
    """Complete status for a single room."""
    name: str
    temp: Optional[float] = None
    setpoint: Optional[float] = None
    scheduled_target: Optional[float] = None
    heating_percent: int = 0
    ac_power: bool = False
    source: str = "none"  # Policy preference: "ac", "tado", or "none"
    active_source: str = "none"  # What's actually running
    has_rad: bool = False
    has_ac: bool = False
    disabled: bool = False
    floor: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to API response format."""
        return {
            "name": self.name,
            "temp": self.temp,
            "setpoint": self.setpoint,
            "scheduledTarget": self.scheduled_target,
            "heatingPercent": self.heating_percent,
            "acPower": self.ac_power,
            "source": self.source,
            "activeSource": self.active_source,
            "hasRad": self.has_rad,
            "hasAC": self.has_ac,
            "disabled": self.disabled,
            "floor": self.floor
        }


def determine_policy_source(
    outdoor_temp: Optional[float],
    ac_min_outdoor_c: float,
    has_ac: bool,
    has_rad: bool
) -> str:
    """
    Determine which heating source should be used based on outdoor temperature.

    Args:
        outdoor_temp: Current outdoor temperature in Celsius
        ac_min_outdoor_c: Minimum outdoor temperature to use AC
        has_ac: Whether room has AC units
        has_rad: Whether room has radiators (Tado)

    Returns:
        "ac" if AC should be used, "tado" if radiators, "none" if neither
    """
    # Guard clause: no outdoor temp data
    if outdoor_temp is None:
        return "tado" if has_rad else "none"

    # Guard clause: no devices
    if not has_ac and not has_rad:
        return "none"

    # Use AC if warm enough and available
    if outdoor_temp >= ac_min_outdoor_c and has_ac:
        return "ac"

    # Otherwise use radiators if available
    if has_rad:
        return "tado"

    return "none"


def select_temperature(
    policy_source: str,
    tado_state: Optional[DeviceState],
    ac_state: Optional[DeviceState]
) -> tuple[Optional[float], Optional[float]]:
    """
    Select which temperature to display based on policy source.

    Priority: policy source > fallback to whatever is available

    Args:
        policy_source: Preferred source ("ac" or "tado")
        tado_state: Current Tado device state
        ac_state: Current AC device state

    Returns:
        Tuple of (current_temp, setpoint)
    """
    # Guard clause: no data
    if not tado_state and not ac_state:
        return None, None

    # Try policy source first
    if policy_source == "ac" and ac_state:
        return ac_state.current_temp, ac_state.target_temp

    if policy_source == "tado" and tado_state:
        return tado_state.current_temp, tado_state.target_temp

    # Fallback: use whatever is available
    if tado_state and tado_state.current_temp is not None:
        return tado_state.current_temp, tado_state.target_temp

    if ac_state and ac_state.current_temp is not None:
        return ac_state.current_temp, ac_state.target_temp

    return None, None
