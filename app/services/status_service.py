"""
Status service - handles fetching and building room status data.

All business logic for status endpoint lives here, keeping the router thin.
"""

from typing import Dict, List, Optional
from datetime import datetime

from app.config import ConfigManager
from app.models.config import RoomConfig
from app.devices.tado_client import TadoClient
from app.devices.melcloud_client import MELCloudClient
from app.devices.weather_client import WeatherClient
from app.models.room_status import RoomStatus, DeviceState, determine_policy_source, select_temperature
from app.utils.logging import get_logger

logger = get_logger(__name__)


class StatusService:
    """
    Service for fetching and building room status data.

    Handles:
    - Sequential device state fetching (no async gather to avoid 429s)
    - Source selection based on outdoor temperature
    - Temperature priority logic
    - Room status building
    """

    def __init__(
        self,
        tado: TadoClient,
        mel: MELCloudClient,
        config: ConfigManager
    ):
        """
        Initialize status service.

        Args:
            tado: Tado API client
            mel: MELCloud API client
            config: Configuration manager
        """
        self.tado = tado
        self.mel = mel
        self.config = config

    async def get_all_room_status(self) -> Dict[str, List[Dict]]:
        """
        Get complete status for all rooms.

        Returns:
            Dict with "rooms" key containing list of room status dicts
        """
        start_time = datetime.now()

        # Load config
        cfg = await self.config.load_config()

        # Get outdoor temperature
        outdoor_temp = await self._fetch_outdoor_temperature(cfg)
        ac_min_outdoor_c = cfg.thresholds.ac_min_outdoor_c

        logger.info(f"Outdoor temp: {outdoor_temp}°C, AC threshold: {ac_min_outdoor_c}°C")

        # Fetch all device states (sequential to avoid API rate limits)
        tado_states = await self._fetch_all_tado_states()
        mel_states = await self._fetch_all_mel_states()

        logger.info(f"Fetched all device states in {(datetime.now() - start_time).total_seconds():.2f}s")

        # Build room status list
        rooms = []
        for room_key, room_config in cfg.rooms.items():
            room_status = self._build_room_status(
                room_key,
                room_config,
                outdoor_temp,
                ac_min_outdoor_c,
                tado_states,
                mel_states
            )
            rooms.append(room_status.to_dict())

        logger.info(f"Total status processing time: {(datetime.now() - start_time).total_seconds():.2f}s")

        return {"rooms": rooms}

    async def _fetch_outdoor_temperature(self, cfg) -> Optional[float]:
        """Fetch outdoor temperature from weather API."""
        weather = WeatherClient(
            latitude=cfg.weather.lat,
            longitude=cfg.weather.lon,
            sim_mode=self.tado.sim_mode
        )
        return await weather.get_outdoor_temperature()

    async def _fetch_all_tado_states(self) -> Dict[str, DeviceState]:
        """
        Fetch state for all Tado zones sequentially.

        Returns:
            Dict mapping zone_name to DeviceState
        """
        zone_names = await self.tado.list_zones()
        states = {}

        for zone_name in zone_names:
            state = await self._fetch_single_tado_state(zone_name)
            if state:
                states[zone_name] = state

        return states

    async def _fetch_single_tado_state(self, zone_name: str) -> Optional[DeviceState]:
        """
        Fetch state for a single Tado zone with error handling.

        Uses get_zone_state() to fetch all data in one call (more efficient than
        calling get_temperature() and get_heating_percent() separately).

        Args:
            zone_name: Name of the zone

        Returns:
            DeviceState or None on error
        """
        state = await self.tado.get_zone_state(zone_name)

        # Guard clause: no state returned
        if not state:
            return None

        temp = state.get("temperature")
        heating_percent = state.get("heating_percent", 0)

        return DeviceState(
            current_temp=temp,
            target_temp=None,  # Tado doesn't provide this in simple state
            power=heating_percent > 0,
            heating=heating_percent > 0,
            heating_percent=heating_percent
        )

    async def _fetch_all_mel_states(self) -> Dict[str, DeviceState]:
        """
        Fetch state for all MELCloud devices sequentially.

        Returns:
            Dict mapping device_name to DeviceState
        """
        device_names = await self.mel.list_devices()
        states = {}

        for device_name in device_names:
            state = await self._fetch_single_mel_state(device_name)
            if state:
                states[device_name] = state

        return states

    async def _fetch_single_mel_state(self, device_name: str) -> Optional[DeviceState]:
        """
        Fetch state for a single MELCloud device with error handling.

        Args:
            device_name: Name of the device

        Returns:
            DeviceState or None on error
        """
        state = await self.mel.get_device_state(device_name)

        # Guard clause: no state returned
        if not state:
            return None

        return DeviceState(
            current_temp=state.get("RoomTemperature"),
            target_temp=state.get("SetTemperature"),
            power=state.get("Power", False),
            heating=state.get("Power", False),  # Simplified: power = heating for AC
            mode=state.get("OperationMode")
        )

    def _build_room_status(
        self,
        room_key: str,
        room_config: RoomConfig,
        outdoor_temp: Optional[float],
        ac_min_outdoor_c: float,
        tado_states: Dict[str, DeviceState],
        mel_states: Dict[str, DeviceState]
    ) -> RoomStatus:
        """
        Build complete status for a single room.

        Args:
            room_key: Room identifier
            room_config: Room configuration
            outdoor_temp: Current outdoor temperature
            ac_min_outdoor_c: Minimum outdoor temp to use AC
            tado_states: All Tado device states
            mel_states: All MELCloud device states

        Returns:
            RoomStatus with all fields populated
        """
        has_ac = bool(room_config.mel or room_config.mel_multi)
        has_rad = bool(room_config.tado)

        # Determine policy source
        policy_source = determine_policy_source(outdoor_temp, ac_min_outdoor_c, has_ac, has_rad)

        # Create base room status
        room_status = RoomStatus(
            name=room_key,
            has_ac=has_ac,
            has_rad=has_rad,
            source=policy_source
        )

        # Get device states for this room
        tado_state = self._get_tado_state_for_room(room_config, tado_states)
        ac_state = self._get_ac_state_for_room(room_config, mel_states)

        # Apply device state to room status
        self._apply_tado_state(room_status, tado_state)
        self._apply_ac_state(room_status, ac_state)

        # Select temperature to display
        temp, setpoint = select_temperature(policy_source, tado_state, ac_state)
        room_status.temp = temp
        room_status.setpoint = setpoint
        room_status.scheduled_target = setpoint

        return room_status

    def _get_tado_state_for_room(
        self,
        room_config: RoomConfig,
        tado_states: Dict[str, DeviceState]
    ) -> Optional[DeviceState]:
        """Get Tado state for a room, or None if not configured/available."""
        if not room_config.tado:
            return None
        return tado_states.get(room_config.tado)

    def _get_ac_state_for_room(
        self,
        room_config: RoomConfig,
        mel_states: Dict[str, DeviceState]
    ) -> Optional[DeviceState]:
        """
        Get AC state for a room (checks both mel and mel_multi).

        If multiple units, returns first one found.
        """
        # Check primary mel unit
        if room_config.mel and room_config.mel in mel_states:
            return mel_states[room_config.mel]

        # Check mel_multi units
        if room_config.mel_multi:
            for unit_name in room_config.mel_multi:
                if unit_name in mel_states:
                    return mel_states[unit_name]

        return None

    def _apply_tado_state(self, room_status: RoomStatus, tado_state: Optional[DeviceState]) -> None:
        """Apply Tado device state to room status."""
        if not tado_state:
            return

        room_status.heating_percent = tado_state.heating_percent

        # Set active source if Tado is heating
        if tado_state.heating:
            room_status.active_source = "tado"

    def _apply_ac_state(self, room_status: RoomStatus, ac_state: Optional[DeviceState]) -> None:
        """Apply AC device state to room status."""
        if not ac_state:
            return

        room_status.ac_power = ac_state.power

        # If AC is ON, it's the active source (overrides Tado)
        if ac_state.power:
            room_status.active_source = "ac"
