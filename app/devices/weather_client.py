"""
Weather API client using Open-Meteo.

Simple free weather API with no authentication required.
Used for outdoor temperature reading to determine AC vs radiator selection.
"""

from datetime import datetime, timedelta
from typing import Optional
import httpx

from app.utils.logging import get_logger

logger = get_logger(__name__)


class WeatherClient:
    """
    Weather client for Open-Meteo API.

    Features:
    - Free, no authentication required
    - Outdoor temperature reading
    - 10-minute caching
    - Sim mode support
    """

    BASE_URL = "https://api.open-meteo.com/v1/forecast"
    CACHE_TTL = timedelta(minutes=10)

    def __init__(
        self,
        latitude: float,
        longitude: float,
        sim_mode: bool = False
    ):
        """
        Initialize weather client.

        Args:
            latitude: Location latitude
            longitude: Location longitude
            sim_mode: If True, return fake data without API calls
        """
        self.latitude = latitude
        self.longitude = longitude
        self.sim_mode = sim_mode

        # In-memory cache
        self._cache: Optional[float] = None
        self._cache_expires_at: Optional[datetime] = None

    async def get_outdoor_temperature(self) -> Optional[float]:
        """
        Get current outdoor temperature in Celsius.
        Cached for 10 minutes.

        Returns:
            Temperature in Celsius, or None on failure
        """
        try:
            if self.sim_mode:
                logger.info("[SIM] Getting outdoor temperature")
                return 12.0  # Fake outdoor temp for sim mode

            # Check cache
            now = datetime.now()
            cache_valid = (
                self._cache
                and self._cache_expires_at
                and now < self._cache_expires_at
            )
            if cache_valid:
                return self._cache

            # Fetch from API
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    self.BASE_URL,
                    params={
                        "latitude": self.latitude,
                        "longitude": self.longitude,
                        "current": "temperature_2m"
                    }
                )
                response.raise_for_status()
                data = response.json()

            # Extract temperature
            temperature = data.get("current", {}).get("temperature_2m")

            if temperature is None:
                logger.error("Failed to extract temperature from Open-Meteo response")
                return None

            # Cache result
            self._cache = temperature
            self._cache_expires_at = now + self.CACHE_TTL

            logger.info(f"Outdoor temperature: {temperature}°C")
            return temperature

        except Exception as e:
            logger.error(f"Failed to get outdoor temperature: {e}")
            return None
