"""
Tado API client with OAuth2 device code flow and refresh token rotation.

CRITICAL: Tado uses refresh token rotation - every refresh invalidates the old token.
Uses database locking to prevent concurrent refresh attempts.
"""

import asyncio
import httpx
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, delete

from app.devices.base import DeviceClient
from app.models.database import ApiCache
from app.utils.secrets import SecretsManager
from app.utils.logging import get_logger
from app.utils.text_utils import sanitize_device_name as sanitize_zone_name

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

        # In-memory L1 cache (fast path, short TTL)
        # Falls back to PostgreSQL L2 cache (persistent, survives restarts)
        self._access_token_cache: Optional[str] = None
        self._access_token_expires_at: Optional[datetime] = None

    async def _get_cache(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get value from PostgreSQL cache if not expired.

        Args:
            key: Cache key

        Returns:
            Cached value dict or None if expired/missing
        """
        result = await self.db.execute(
            select(ApiCache).where(ApiCache.key == key)
        )
        cache_entry = result.scalar_one_or_none()

        if not cache_entry:
            return None

        # Check if expired
        now = datetime.now(timezone.utc)
        if now >= cache_entry.expires_at:
            # Expired - delete and return None
            await self.db.execute(
                delete(ApiCache).where(ApiCache.key == key)
            )
            await self.db.commit()
            return None

        return cache_entry.value

    async def _set_cache(
        self,
        key: str,
        value: Dict[str, Any],
        ttl: timedelta
    ) -> None:
        """
        Store value in PostgreSQL cache with TTL.

        Args:
            key: Cache key
            value: Value to cache (must be JSON-serializable)
            ttl: Time to live
        """
        now = datetime.now(timezone.utc)
        expires_at = now + ttl

        # Upsert cache entry
        result = await self.db.execute(
            select(ApiCache).where(ApiCache.key == key)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.value = value
            existing.expires_at = expires_at
        else:
            cache_entry = ApiCache(
                key=key,
                value=value,
                expires_at=expires_at
            )
            self.db.add(cache_entry)

        await self.db.commit()

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
        now = datetime.now(timezone.utc)
        cache_valid = (
            self._access_token_cache
            and self._access_token_expires_at
            and now < self._access_token_expires_at
        )
        if cache_valid:
            return self._access_token_cache

        # Need to refresh - acquire database lock
        # Use advisory lock to prevent concurrent token refresh
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
        Cached for 1 hour in PostgreSQL to prevent rate limiting.

        Rate limit protection:
        - Zone list rarely changes
        - Cache for 1 hour in database
        - Survives restarts and shared across instances

        Returns:
            List of zone names
        """
        if self.sim_mode:
            logger.info("[SIM] Listing Tado zones")
            return []

        # Check PostgreSQL cache
        cache_key = f"tado:zones:{self.home_id}"
        cached = await self._get_cache(cache_key)
        if cached and "zones" in cached:
            logger.debug("Tado zones cache HIT (PostgreSQL)")
            return [sanitize_zone_name(z["name"]) for z in cached["zones"]]

        # Cache MISS - fetch from API
        logger.info("Tado zones cache MISS - fetching from API")
        response = await self._make_request("GET", f"/homes/{self.home_id}/zones")
        zones = response.json()

        # Store in PostgreSQL cache
        await self._set_cache(
            cache_key,
            {"zones": zones},
            self.ZONE_LIST_TTL
        )

        return [sanitize_zone_name(z["name"]) for z in zones]

    async def _get_zone_id(self, zone_name: str) -> int:
        """
        Get zone ID from zone name (uses cached zone list).

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

        # Get zone list from PostgreSQL cache
        cache_key = f"tado:zones:{self.home_id}"
        cached = await self._get_cache(cache_key)

        if not cached or "zones" not in cached:
            # Cache miss - fetch from API
            response = await self._make_request("GET", f"/homes/{self.home_id}/zones")
            zones = response.json()

            # Store in cache
            await self._set_cache(
                cache_key,
                {"zones": zones},
                self.ZONE_LIST_TTL
            )
        else:
            zones = cached["zones"]

        for zone in zones:
            if zone["name"] == zone_name:
                return zone["id"]

        raise ValueError(f"Tado zone not found: {zone_name}")

    async def _get_zone_state(self, zone_id: int) -> Dict[str, Any]:
        """
        Get zone state (cached for 2 minutes in PostgreSQL).

        Rate limit protection:
        - Zone states change frequently (temperature, power)
        - Cache for 2 minutes - tolerate slight staleness
        - Database cache survives restarts

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

        # Check PostgreSQL cache
        cache_key = f"tado:zone_state:{self.home_id}:{zone_id}"
        cached = await self._get_cache(cache_key)
        if cached and "state" in cached:
            logger.debug(f"Tado zone {zone_id} state cache HIT (PostgreSQL)")
            return cached["state"]

        # Cache MISS - fetch from API
        logger.debug(f"Tado zone {zone_id} state cache MISS - fetching from API")
        response = await self._make_request(
            "GET",
            f"/homes/{self.home_id}/zones/{zone_id}/state"
        )
        state = response.json()

        # Store in PostgreSQL cache
        await self._set_cache(
            cache_key,
            {"state": state},
            self.ZONE_STATE_TTL
        )

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

    async def get_zone_state(self, zone_name: str) -> Optional[Dict[str, Any]]:
        """
        Get full zone state (temperature, heating, overlay, etc).

        Cached for 2 minutes in PostgreSQL to prevent rate limiting.
        This is more efficient than calling get_temperature() and get_heating_percent()
        separately since it only does one zone lookup and one state fetch.

        Args:
            zone_name: Zone name

        Returns:
            Zone state dict with parsed temperature and heating data, or None on failure

        Example return value:
            {
                "temperature": 20.5,
                "heating_percent": 35,
                "overlay": {...},
                "raw_state": {...}
            }
        """
        if self.sim_mode:
            return {
                "temperature": 19.5,
                "heating_percent": 0,
                "overlay": None,
                "raw_state": {}
            }

        zone_id = await self._get_zone_id(zone_name)
        state = await self._get_zone_state(zone_id)

        # Parse out commonly needed values
        temp = state.get("sensorDataPoints", {}).get("insideTemperature", {}).get("celsius")
        power = state.get("activityDataPoints", {}).get("heatingPower", {}).get("percentage")

        return {
            "temperature": temp,
            "heating_percent": power if power is not None else 0,
            "overlay": state.get("overlay"),
            "raw_state": state
        }

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
                data={
                    "client_id": self.CLIENT_ID,
                    "scope": "home.user offline_access"
                }
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
            result = response.json()
            logger.info(f"Tado OAuth poll response: {result}")
            return result
