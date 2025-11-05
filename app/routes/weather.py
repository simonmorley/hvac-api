"""
Weather API endpoints.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends

from app.utils.auth import validate_api_key
from app.dependencies import get_config_manager
from app.config import ConfigManager
from app.devices.weather_client import WeatherClient

router = APIRouter()

# Simple in-memory cache with 10-minute TTL
_weather_cache: Optional[Dict[str, Any]] = None
_weather_cache_expires_at: Optional[datetime] = None
_WEATHER_CACHE_TTL = timedelta(minutes=10)


@router.get("/weather")
async def get_weather(
    config_mgr: ConfigManager = Depends(get_config_manager),
    _: None = Depends(validate_api_key)
):
    """
    Get current outdoor temperature from weather API.

    Cached for 10 minutes to reduce API calls.

    Returns:
        dict: {"outdoorC": float}
    """
    global _weather_cache, _weather_cache_expires_at

    # Check cache first
    now = datetime.now()
    if _weather_cache and _weather_cache_expires_at and now < _weather_cache_expires_at:
        return _weather_cache

    # Load configuration to get lat/lon
    config = await config_mgr.load_config()

    # Get outdoor temperature
    weather = WeatherClient(
        latitude=config.weather.lat,
        longitude=config.weather.lon
    )
    outdoor_c = await weather.get_outdoor_temperature()

    result = {"outdoorC": outdoor_c}

    # Update cache
    _weather_cache = result
    _weather_cache_expires_at = datetime.now() + _WEATHER_CACHE_TTL

    return result
