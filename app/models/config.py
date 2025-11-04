"""
Pydantic models for HVAC configuration.
Matches the structure defined in config.json.
"""

from typing import Annotated, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


class ACSettings(BaseModel):
    """AC unit settings (MELCloud)."""
    mode: Optional[Literal["heat", "cool", "auto", "dry", "fan"]] = "heat"
    fan: Optional[Union[Literal["auto"], int]] = "auto"
    vaneH: Optional[Union[Literal["auto", "swing"], int]] = "auto"
    vaneV: Optional[Union[Literal["auto", "swing"], int]] = "auto"
    vanes: Optional[bool] = True


class ThreePeriodSchedule(BaseModel):
    """Three-period schedule: day, eve, night."""
    type: Literal["three-period"]
    day: float
    eve: float
    night: float
    day_start: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    eve_start: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    eve_end: str = Field(..., pattern=r"^\d{2}:\d{2}$")


class FourPeriodSchedule(BaseModel):
    """Four-period schedule: morning, day, evening, night."""
    type: Literal["four-period"]
    night: float
    morning: float
    day: float
    evening: float
    morning_start: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    morning_end: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    evening_start: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    evening_end: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    # Optional per-period AC settings
    night_ac: Optional[ACSettings] = None
    morning_ac: Optional[ACSettings] = None
    day_ac: Optional[ACSettings] = None
    evening_ac: Optional[ACSettings] = None


class WorkdaySchedule(BaseModel):
    """Workday schedule: work hours vs idle."""
    type: Literal["workday"]
    work: float
    idle: float
    start: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    end: str = Field(..., pattern=r"^\d{2}:\d{2}$")


class SimpleSchedule(BaseModel):
    """Simple static setpoint schedule."""
    type: Literal["simple"]
    setpoint: float


# Union type for all schedule types using discriminated union
RoomSchedule = Annotated[
    Union[ThreePeriodSchedule, FourPeriodSchedule, WorkdaySchedule, SimpleSchedule],
    Field(discriminator='type')
]


class RoomConfig(BaseModel):
    """Configuration for a single room."""
    tado: Optional[str] = None  # Tado zone name
    mel: Optional[str] = None  # Primary MELCloud unit name
    mel_multi: Optional[List[str]] = None  # Multiple AC units per room
    ac: Optional[ACSettings] = None  # Room-specific AC overrides
    floor: Optional[Literal["upstairs", "downstairs"]] = None
    schedule: Optional[RoomSchedule] = None  # Room-specific schedule override


class ExcludeConfig(BaseModel):
    """Devices to exclude from automation."""
    tado: List[str] = Field(default_factory=list)
    mel: List[str] = Field(default_factory=list)


class PVConfig(BaseModel):
    """Solar PV boost configuration."""
    boost_threshold_w: float
    boost_delta_c: float


class BlackoutWindow(BaseModel):
    """Time window where heating should be disabled."""
    name: Optional[str] = None
    start: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    end: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    applies_to: Optional[List[str]] = None  # e.g., ["tado"], ["mel"], or both
    enabled: Optional[bool] = True
    reason: Optional[str] = None


class WeatherConfig(BaseModel):
    """Weather API configuration."""
    lat: float
    lon: float
    provider: Literal["open-meteo"] = "open-meteo"


class ThresholdConfig(BaseModel):
    """Control thresholds."""
    ac_min_outdoor_c: float = Field(
        default=2.0,
        description="Minimum outdoor temperature for AC usage"
    )


class HVACConfig(BaseModel):
    """Top-level HVAC system configuration."""
    exclude: ExcludeConfig
    ac_defaults: ACSettings
    names: Optional[Dict[str, Union[str, List[str]]]] = None  # Device name mappings (legacy)
    rooms: Dict[str, RoomConfig]
    targets: Dict[str, float]  # Spare room targets, etc.
    pv: PVConfig
    blackout_windows: List[BlackoutWindow] = Field(default_factory=list)
    weather: WeatherConfig
    thresholds: ThresholdConfig

    class Config:
        """Pydantic config."""
        # Allow extra fields for forward compatibility
        extra = "allow"
