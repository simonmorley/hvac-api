"""
MELCloud API client for Mitsubishi AC control.

Handles session-based authentication and nested device hierarchy traversal.
Uses EffectiveFlags bitmap to specify which device settings are being changed.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Union
import httpx

from app.devices.base import DeviceClient
from app.utils.secrets import SecretsManager
from app.utils.logging import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


class MELCloudClient(DeviceClient):
    """
    MELCloud API client for Mitsubishi AC units.

    Features:
    - Session-based authentication (ContextKey header)
    - Nested device hierarchy traversal
    - EffectiveFlags bitmap for command specification
    - Mode/fan/vane mapping
    - Device state reading with caching (1 minute)
    - Re-authentication on 401 errors
    """

    BASE_URL = "https://app.melcloud.com/Mitsubishi.Wifi.Client"

    # EffectiveFlags bitmap constants
    FLAG_POWER = 0x01
    FLAG_MODE = 0x02
    FLAG_SETPOINT = 0x04
    FLAG_FAN_SPEED = 0x08
    FLAG_VANE_VERTICAL = 0x10
    FLAG_VANE_HORIZONTAL = 0x100

    # Cache TTLs
    DEVICE_LIST_TTL = timedelta(hours=1)
    DEVICE_STATE_TTL = timedelta(minutes=1)

    def __init__(
        self,
        email: str,
        password: str,
        db_session: AsyncSession,
        sim_mode: bool = False
    ):
        """
        Initialize MELCloud client.

        Args:
            email: MELCloud account email
            password: MELCloud account password
            db_session: Database session for secrets storage
            sim_mode: If True, don't make real API calls
        """
        super().__init__(sim_mode)
        self.email = email
        self.password = password
        self.db = db_session
        self.secrets = SecretsManager(db_session)

        # In-memory caches
        self._session_token: Optional[str] = None
        self._device_list_cache: Optional[List[Dict[str, Any]]] = None
        self._device_list_expires_at: Optional[datetime] = None
        self._device_state_cache: Dict[int, tuple[Dict[str, Any], datetime]] = {}

    async def get_session_token(self) -> str:
        """
        Get session token (from cache or login).

        Re-authenticates on 401 errors automatically.

        Returns:
            Valid ContextKey session token

        Raises:
            Exception: On authentication failure
        """
        if self._session_token:
            return self._session_token

        if self.sim_mode:
            logger.info("[SIM] Logging into MELCloud")
            self._session_token = "sim_context_key"
            return self._session_token

        # Login to get ContextKey
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/Login/ClientLogin",
                json={
                    "Email": self.email,
                    "Password": self.password,
                    "AppVersion": "1.32.1.0"
                }
            )
            response.raise_for_status()
            data = response.json()

        context_key = data["LoginData"]["ContextKey"]
        self._session_token = context_key

        # Optionally store in database for cross-instance sharing
        await self.secrets.set("melcloud_context_key", context_key)

        logger.info("MELCloud authentication successful")
        return context_key

    async def _make_request(
        self,
        method: str,
        path: str,
        retry_on_401: bool = True,
        **kwargs
    ) -> httpx.Response:
        """
        Make authenticated request to MELCloud API.

        Automatically re-authenticates on 401 errors.

        Args:
            method: HTTP method
            path: API path
            retry_on_401: If True, retry once on 401
            **kwargs: Additional httpx request kwargs

        Returns:
            httpx.Response object

        Raises:
            httpx.HTTPStatusError: On failure
        """
        token = await self.get_session_token()
        url = f"{self.BASE_URL}{path}"

        headers = kwargs.pop("headers", {})
        headers["X-MitsContextKey"] = token

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.request(method, url, headers=headers, **kwargs)

            # Re-authenticate on 401
            if response.status_code == 401 and retry_on_401:
                logger.warning("MELCloud session expired (401), re-authenticating")
                self._session_token = None
                return await self._make_request(method, path, retry_on_401=False, **kwargs)

            response.raise_for_status()
            return response

    def _collect_devices(self, structure: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Recursively traverse nested device hierarchy and collect all devices.

        MELCloud structure: Site → Building → Structure → Devices/Areas/Floors/Children

        Args:
            structure: Structure dict from API

        Returns:
            List of flattened device dicts with {id, building_id, name, type}
        """
        devices = []

        def traverse(node: Dict[str, Any], building_id: int):
            # Add direct devices
            for device in node.get("Devices", []):
                # Only support Air-to-Air (type 0)
                if device.get("DeviceType") == 0:
                    devices.append({
                        "id": device["DeviceID"],
                        "building_id": building_id,
                        "name": device["DeviceName"],
                        "type": device["DeviceType"]
                    })

            # Recurse into nested structures
            for area in node.get("Areas", []):
                traverse(area, building_id)
            for floor in node.get("Floors", []):
                traverse(floor, building_id)

        # Top-level structure
        for building in structure.get("Structure", {}).get("Devices", []):
            if building.get("DeviceType") == 0:
                devices.append({
                    "id": building["DeviceID"],
                    "building_id": structure["ID"],
                    "name": building["DeviceName"],
                    "type": building["DeviceType"]
                })

        for building in structure.get("Structure", {}).get("Areas", []):
            traverse(building, structure["ID"])

        for building in structure.get("Structure", {}).get("Floors", []):
            traverse(building, structure["ID"])

        return devices

    async def list_devices(self) -> List[str]:
        """
        List all available AC device names.
        Cached for 1 hour.

        Returns:
            List of device names
        """
        if self.sim_mode:
            logger.info("[SIM] Listing MELCloud devices")
            return ["Living", "Master bedroom", "Downstairs"]

        # Check cache
        now = datetime.now()
        cache_valid = (
            self._device_list_cache
            and self._device_list_expires_at
            and now < self._device_list_expires_at
        )
        if cache_valid:
            return [d["name"] for d in self._device_list_cache]

        # Fetch from API
        response = await self._make_request("GET", "/User/ListDevices")
        data = response.json()

        # Flatten nested structure
        all_devices = []
        for structure in data:
            all_devices.extend(self._collect_devices(structure))

        # Cache result
        self._device_list_cache = all_devices
        self._device_list_expires_at = now + self.DEVICE_LIST_TTL

        return [d["name"] for d in all_devices]

    async def _get_device_ids(self, device_name: str) -> tuple[int, int]:
        """
        Get device ID and building ID from device name.

        Args:
            device_name: Device name

        Returns:
            Tuple of (device_id, building_id)

        Raises:
            ValueError: If device not found
        """
        if self.sim_mode:
            # Fake IDs in sim mode
            return (hash(device_name) % 10000, 12345)

        # Get device list (uses cache)
        response = await self._make_request("GET", "/User/ListDevices")
        data = response.json()

        # Flatten and search
        for structure in data:
            devices = self._collect_devices(structure)
            for device in devices:
                if device["name"] == device_name:
                    return (device["id"], device["building_id"])

        raise ValueError(f"MELCloud device not found: {device_name}")

    def _calculate_flags(
        self,
        power: bool = False,
        mode: bool = False,
        setpoint: bool = False,
        fan: bool = False,
        vanes: bool = False
    ) -> int:
        """
        Calculate EffectiveFlags bitmap.

        EffectiveFlags tells MELCloud which fields are being changed.
        Must include flags for ALL fields in the payload being modified.

        Args:
            power: Include Power flag
            mode: Include Mode flag
            setpoint: Include SetTemperature flag
            fan: Include FanSpeed flag
            vanes: Include Vane (horizontal + vertical) flags

        Returns:
            EffectiveFlags integer
        """
        flags = 0
        if power:
            flags |= self.FLAG_POWER
        if mode:
            flags |= self.FLAG_MODE
        if setpoint:
            flags |= self.FLAG_SETPOINT
        if fan:
            flags |= self.FLAG_FAN_SPEED
        if vanes:
            flags |= self.FLAG_VANE_VERTICAL | self.FLAG_VANE_HORIZONTAL
        return flags

    def _mode_to_int(self, mode: str) -> int:
        """
        Convert mode string to MELCloud integer.

        Args:
            mode: Mode string (heat, cool, dry, fan, auto)

        Returns:
            Mode integer (1=heat, 2=cool, 3=dry, 7=fan, 8=auto)
        """
        mapping = {
            "heat": 1,
            "cool": 2,
            "dry": 3,
            "fan": 7,
            "auto": 8
        }
        return mapping.get(mode.lower(), 1)  # Default to heat

    def _fan_to_int(self, fan: Union[str, int]) -> int:
        """
        Convert fan setting to MELCloud integer.

        Args:
            fan: Fan setting ("auto" or 1-5)

        Returns:
            Fan speed integer (0=auto, 1-5=speed)
        """
        if isinstance(fan, int):
            return fan
        if fan.lower() == "auto":
            return 0
        return 0  # Default to auto

    async def turn_on(
        self,
        device_name: str,
        setpoint: float,
        mode: str = "heat",
        fan: Union[str, int] = "auto",
        vanes: bool = True,
        **kwargs
    ) -> bool:
        """
        Turn on AC unit with settings.

        Args:
            device_name: Device name
            setpoint: Target temperature in Celsius
            mode: Operation mode (heat, cool, dry, fan, auto)
            fan: Fan speed ("auto" or 1-5)
            vanes: Enable vane control (set False for ducted units)
            **kwargs: Additional kwargs (vaneH, vaneV if needed)

        Returns:
            True on success, False on failure
        """
        try:
            if self.sim_mode:
                logger.info(
                    "[SIM] MELCloud turn_on",
                    extra={
                        "device": device_name,
                        "setpoint": setpoint,
                        "mode": mode,
                        "fan": fan,
                        "vanes": vanes
                    }
                )
                return True

            device_id, building_id = await self._get_device_ids(device_name)

            # Build payload
            payload = {
                "DeviceID": device_id,
                "EffectiveFlags": self._calculate_flags(
                    power=True,
                    mode=True,
                    setpoint=True,
                    fan=True,
                    vanes=vanes
                ),
                "Power": True,
                "SetTemperature": setpoint,
                "OperationMode": self._mode_to_int(mode),
                "SetFanSpeed": self._fan_to_int(fan),
                "VaneHorizontal": kwargs.get("vaneH", 12 if vanes else 0),  # 12=swing, 0=auto
                "VaneVertical": kwargs.get("vaneV", 7 if vanes else 0),  # 7=swing, 0=auto
                "HasPendingCommand": True
            }

            await self._make_request("POST", "/Device/SetAta", json=payload)

            logger.info(
                f"MELCloud device turned ON: {device_name} → {setpoint}°C ({mode})"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to turn on MELCloud device {device_name}: {e}")
            return False

    async def turn_off(self, device_name: str) -> bool:
        """
        Turn off AC unit.

        Args:
            device_name: Device name

        Returns:
            True on success, False on failure
        """
        try:
            if self.sim_mode:
                logger.info("[SIM] MELCloud turn_off", extra={"device": device_name})
                return True

            device_id, building_id = await self._get_device_ids(device_name)

            # Build payload (only Power flag)
            payload = {
                "DeviceID": device_id,
                "EffectiveFlags": self.FLAG_POWER,
                "Power": False,
                "HasPendingCommand": True
            }

            await self._make_request("POST", "/Device/SetAta", json=payload)

            logger.info(f"MELCloud device turned OFF: {device_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to turn off MELCloud device {device_name}: {e}")
            return False

    async def get_temperature(self, device_name: str) -> Optional[float]:
        """
        Get current room temperature from device.

        Args:
            device_name: Device name

        Returns:
            Temperature in Celsius, or None on failure
        """
        try:
            if self.sim_mode:
                return 20.0

            state = await self.get_device_state(device_name)
            if state:
                return state.get("RoomTemperature")
            return None

        except Exception as e:
            logger.error(f"Failed to get temperature for MELCloud device {device_name}: {e}")
            return None

    async def get_device_state(self, device_name: str) -> Optional[Dict[str, Any]]:
        """
        Get full device state (power, setpoint, mode, temp, etc.).
        Cached for 1 minute.

        Args:
            device_name: Device name

        Returns:
            Device state dict, or None on failure
        """
        try:
            if self.sim_mode:
                return {
                    "Power": False,
                    "RoomTemperature": 20.0,
                    "SetTemperature": 21.0,
                    "OperationMode": 1,
                    "SetFanSpeed": 0
                }

            device_id, building_id = await self._get_device_ids(device_name)

            # Check cache
            now = datetime.now()
            if device_id in self._device_state_cache:
                state, expires_at = self._device_state_cache[device_id]
                if now >= expires_at:
                    # Cache expired - continue to API fetch
                    pass
                else:
                    return state

            # Fetch from API
            response = await self._make_request(
                "GET",
                f"/Device/Get?id={device_id}&buildingID={building_id}"
            )
            state = response.json()

            # Cache result
            self._device_state_cache[device_id] = (state, now + self.DEVICE_STATE_TTL)

            return state

        except Exception as e:
            logger.error(f"Failed to get state for MELCloud device {device_name}: {e}")
            return None
