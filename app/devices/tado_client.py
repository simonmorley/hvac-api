"""
Tado API client with OAuth2 device code flow and refresh token rotation.

CRITICAL: Tado uses refresh token rotation - every refresh invalidates the old token.
Uses database locking to prevent concurrent refresh attempts.
"""

import asyncio
import httpx
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.devices.base import DeviceClient
from app.utils.secrets import SecretsManager
from app.utils.logging import get_logger

logger = get_logger(__name__)


class TadoClient(DeviceClient):
    """
    Tado API client for smart radiator thermostat control.

    Features:
    - OAuth2 device code flow for initial auth
    - Refresh token rotation with database locking
    - Zone control (overlay with timer termination)
    - Temperature and heating power reading
    - Retry logic (401→refresh+retry, 429→fail, others→exponential backoff)
    - Caching (zones: 1hr, states: 2min, access token: 10min)
    """

    BASE_URL = "https://my.tado.com/api/v2"
    AUTH_URL = "https://login.tado.com/oauth2"
    CLIENT_ID = "1bb50063-6b0c-4d11-bd99-387f4a91cc46"  # Public Tado client ID

    # Cache TTLs
    ACCESS_TOKEN_TTL = timedelta(minutes=10)
    ZONE_LIST_TTL = timedelta(hours=1)
    ZONE_STATE_TTL = timedelta(minutes=2)

    # Retry configuration
    BASE_BACKOFF_SECONDS = 0.1  # 100ms
    BACKOFF_MULTIPLIER = 5
    MAX_RETRIES = 2

    # Tado API constraints
    MIN_OVERLAY_DURATION_SECONDS = 900  # 15 minutes minimum

    def __init__(
        self,
        home_id: str,
        db_session: AsyncSession,
        sim_mode: bool = False
    ):
        """
        Initialize Tado client.

        Args:
            home_id: Tado home ID
            db_session: Database session for secrets and locking
            sim_mode: If True, don't make real API calls
        """
        super().__init__(sim_mode)
        self.home_id = home_id
        self.db = db_session
        self.secrets = SecretsManager(db_session)

        # In-memory caches
        self._access_token_cache: Optional[str] = None
        self._access_token_expires_at: Optional[datetime] = None
        self._zone_list_cache: Optional[List[Dict[str, Any]]] = None
        self._zone_list_expires_at: Optional[datetime] = None
        self._zone_state_cache: Dict[int, tuple[Dict[str, Any], datetime]] = {}

    async def get_access_token(self) -> str:
        """
        Get valid access token (from cache or refresh).

        Uses database locking to prevent concurrent token refresh
        (refresh tokens rotate and old token becomes invalid).

        Returns:
            Valid access token

        Raises:
            Exception: If no refresh token or refresh fails
        """
        # Check cache
        now = datetime.now()
        cache_valid = (
            self._access_token_cache
            and self._access_token_expires_at
            and now < self._access_token_expires_at
        )
        if cache_valid:
            return self._access_token_cache

        # Need to refresh - acquire database lock
        async with self.db.begin():
            # Use SELECT FOR UPDATE to lock the refresh token row
            await self.db.execute(
                text("SELECT pg_advisory_lock(hashtext('tado_token_refresh'))")
            )

            try:
                # Get refresh token from database
                refresh_token = await self.secrets.get("tado_refresh_token")
                if not refresh_token:
                    raise Exception("No Tado refresh token found. Run OAuth flow first.")

                if self.sim_mode:
                    logger.info("[SIM] Refreshing Tado access token")
                    self._access_token_cache = "sim_access_token"
                    self._access_token_expires_at = now + self.ACCESS_TOKEN_TTL
                    return self._access_token_cache

                # Refresh the token
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        f"{self.AUTH_URL}/token",
                        data={
                            "client_id": self.CLIENT_ID,
                            "grant_type": "refresh_token",
                            "refresh_token": refresh_token
                        }
                    )
                    response.raise_for_status()
                    data = response.json()

                # Extract tokens
                new_access_token = data["access_token"]
                new_refresh_token = data["refresh_token"]

                # CRITICAL: Store new refresh token immediately (old one is now invalid)
                await self.secrets.set("tado_refresh_token", new_refresh_token)

                # Cache access token
                self._access_token_cache = new_access_token
                self._access_token_expires_at = now + self.ACCESS_TOKEN_TTL

                logger.info("Tado access token refreshed successfully")
                return new_access_token

            finally:
                # Release database lock
                await self.db.execute(
                    text("SELECT pg_advisory_unlock(hashtext('tado_token_refresh'))")
                )

    async def _make_request(
        self,
        method: str,
        path: str,
        retry_count: int = 0,
        **kwargs
    ) -> httpx.Response:
        """
        Make authenticated request to Tado API with retry logic.

        Retry logic:
        - 401: Refresh token and retry once
        - 429: Fail immediately (rate limited)
        - Others: Retry 2x with exponential backoff (100ms, 500ms)

        Args:
            method: HTTP method (GET, PUT, DELETE, etc.)
            path: API path (e.g., "/homes/123/zones")
            retry_count: Current retry attempt (internal)
            **kwargs: Additional httpx request kwargs

        Returns:
            httpx.Response object

        Raises:
            httpx.HTTPStatusError: On final failure
        """
        token = await self.get_access_token()
        url = f"{self.BASE_URL}{path}"

        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.request(method, url, headers=headers, **kwargs)

            # Handle errors with retry logic
            if response.status_code == 401 and retry_count == 0:
                # Token expired - clear cache and retry once
                logger.warning("Tado API returned 401, refreshing token and retrying")
                self._access_token_cache = None
                self._access_token_expires_at = None
                return await self._make_request(method, path, retry_count=1, **kwargs)

            elif response.status_code == 429:
                # Rate limited - fail immediately
                logger.error("Tado API rate limited (429)")
                response.raise_for_status()

            elif response.status_code >= 500 and retry_count < self.MAX_RETRIES:
                # Server error - retry with exponential backoff
                backoff = self.BASE_BACKOFF_SECONDS * (self.BACKOFF_MULTIPLIER ** retry_count)
                logger.warning(
                    f"Tado API returned {response.status_code}, "
                    f"retrying in {backoff}s (attempt {retry_count + 1}/{self.MAX_RETRIES})"
                )
                await asyncio.sleep(backoff)
                return await self._make_request(method, path, retry_count + 1, **kwargs)

            response.raise_for_status()
            return response

    async def list_zones(self) -> List[str]:
        """
        List all available zone names.
        Cached for 1 hour.

        Returns:
            List of zone names
        """
        if self.sim_mode:
            logger.info("[SIM] Listing Tado zones")
            return ["Master Bedroom", "Living Room", "Kitchen"]

        # Check cache
        now = datetime.now()
        cache_valid = (
            self._zone_list_cache
            and self._zone_list_expires_at
            and now < self._zone_list_expires_at
        )
        if cache_valid:
            return [z["name"] for z in self._zone_list_cache]

        # Fetch from API
        response = await self._make_request("GET", f"/homes/{self.home_id}/zones")
        zones = response.json()

        # Cache result
        self._zone_list_cache = zones
        self._zone_list_expires_at = now + self.ZONE_LIST_TTL

        return [z["name"] for z in zones]

    async def _get_zone_id(self, zone_name: str) -> int:
        """
        Get zone ID from zone name.

        Args:
            zone_name: Zone name

        Returns:
            Zone ID

        Raises:
            ValueError: If zone not found
        """
        if self.sim_mode:
            # Fake zone IDs in sim mode
            return hash(zone_name) % 1000

        # Get zone list (uses cache)
        response = await self._make_request("GET", f"/homes/{self.home_id}/zones")
        zones = response.json()

        for zone in zones:
            if zone["name"] == zone_name:
                return zone["id"]

        raise ValueError(f"Tado zone not found: {zone_name}")

    async def _get_zone_state(self, zone_id: int) -> Dict[str, Any]:
        """
        Get zone state (cached for 2 minutes).

        Args:
            zone_id: Zone ID

        Returns:
            Zone state dict
        """
        if self.sim_mode:
            return {
                "sensorDataPoints": {
                    "insideTemperature": {"celsius": 19.5}
                },
                "activityDataPoints": {
                    "heatingPower": {"percentage": 0}
                },
                "overlay": None
            }

        # Check cache
        now = datetime.now()
        if zone_id in self._zone_state_cache:
            state, expires_at = self._zone_state_cache[zone_id]
            if now >= expires_at:
                # Cache expired - continue to API fetch
                pass
            else:
                return state

        # Fetch from API
        response = await self._make_request(
            "GET",
            f"/homes/{self.home_id}/zones/{zone_id}/state"
        )
        state = response.json()

        # Cache result
        self._zone_state_cache[zone_id] = (state, now + self.ZONE_STATE_TTL)

        return state

    async def turn_on(
        self,
        zone_name: str,
        setpoint: float,
        minutes: int = 60,
        **kwargs
    ) -> bool:
        """
        Turn on Tado zone with temperature overlay.

        Args:
            zone_name: Zone name
            setpoint: Target temperature in Celsius
            minutes: Duration in minutes (minimum 15)
            **kwargs: Ignored (for interface compatibility)

        Returns:
            True on success, False on failure
        """
        try:
            if self.sim_mode:
                logger.info(
                    "[SIM] Tado turn_on",
                    extra={
                        "zone": zone_name,
                        "setpoint": setpoint,
                        "minutes": minutes
                    }
                )
                return True

            zone_id = await self._get_zone_id(zone_name)

            # Enforce minimum duration
            duration_seconds = max(minutes * 60, self.MIN_OVERLAY_DURATION_SECONDS)

            payload = {
                "setting": {
                    "type": "HEATING",
                    "power": "ON",
                    "temperature": {"celsius": setpoint}
                },
                "termination": {
                    "type": "TIMER",
                    "durationInSeconds": duration_seconds
                }
            }

            await self._make_request(
                "PUT",
                f"/homes/{self.home_id}/zones/{zone_id}/overlay",
                json=payload
            )

            logger.info(
                f"Tado zone turned ON: {zone_name} → {setpoint}°C for {minutes} min"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to turn on Tado zone {zone_name}: {e}")
            return False

    async def turn_off(self, zone_name: str) -> bool:
        """
        Turn off Tado zone (remove overlay).

        Args:
            zone_name: Zone name

        Returns:
            True on success, False on failure
        """
        try:
            if self.sim_mode:
                logger.info("[SIM] Tado turn_off", extra={"zone": zone_name})
                return True

            zone_id = await self._get_zone_id(zone_name)

            await self._make_request(
                "DELETE",
                f"/homes/{self.home_id}/zones/{zone_id}/overlay"
            )

            logger.info(f"Tado zone turned OFF: {zone_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to turn off Tado zone {zone_name}: {e}")
            return False

    async def get_temperature(self, zone_name: str) -> Optional[float]:
        """
        Get current room temperature from zone.

        Args:
            zone_name: Zone name

        Returns:
            Temperature in Celsius, or None on failure
        """
        try:
            if self.sim_mode:
                return 19.5

            zone_id = await self._get_zone_id(zone_name)
            state = await self._get_zone_state(zone_id)

            temp = state.get("sensorDataPoints", {}).get("insideTemperature", {}).get("celsius")
            return temp

        except Exception as e:
            logger.error(f"Failed to get temperature for Tado zone {zone_name}: {e}")
            return None

    async def get_heating_percent(self, zone_name: str) -> Optional[int]:
        """
        Get heating power percentage (0-100).

        Args:
            zone_name: Zone name

        Returns:
            Heating power percentage, or None on failure
        """
        try:
            if self.sim_mode:
                return 0

            zone_id = await self._get_zone_id(zone_name)
            state = await self._get_zone_state(zone_id)

            power = state.get("activityDataPoints", {}).get("heatingPower", {}).get("percentage")
            return power

        except Exception as e:
            logger.error(f"Failed to get heating power for Tado zone {zone_name}: {e}")
            return None

    # OAuth Device Code Flow Methods

    async def start_oauth_flow(self) -> Dict[str, str]:
        """
        Initiate OAuth device code flow.

        Returns:
            Dict with 'user_code' and 'verification_uri_complete' for user

        Raises:
            Exception: On API error
        """
        if self.sim_mode:
            logger.info("[SIM] Starting Tado OAuth flow")
            return {
                "user_code": "SIM-CODE",
                "verification_uri_complete": "https://auth.tado.com/sim",
                "device_code": "sim_device_code"
            }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.AUTH_URL}/device_authorize",
                data={"client_id": self.CLIENT_ID}
            )
            response.raise_for_status()
            return response.json()

    async def poll_oauth_completion(self, device_code: str) -> Optional[Dict[str, str]]:
        """
        Poll for OAuth completion.

        Args:
            device_code: Device code from start_oauth_flow()

        Returns:
            Dict with 'access_token' and 'refresh_token' if complete,
            None if still pending

        Raises:
            Exception: On error (expired, denied, etc.)
        """
        if self.sim_mode:
            logger.info("[SIM] Polling Tado OAuth completion")
            return {
                "access_token": "sim_access_token",
                "refresh_token": "sim_refresh_token"
            }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.AUTH_URL}/token",
                data={
                    "client_id": self.CLIENT_ID,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": device_code
                }
            )

            if response.status_code == 400:
                error = response.json().get("error")
                if error == "authorization_pending":
                    return None  # Still waiting
                elif error in ("expired_token", "access_denied"):
                    raise Exception(f"OAuth flow {error}")

            response.raise_for_status()
            return response.json()
