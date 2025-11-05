"""
Control service - handles device control logic.

All business logic for control endpoint lives here, using guard clauses
instead of nested conditionals.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from app.config import ConfigManager
from app.models.config import RoomConfig
from app.devices.tado_client import TadoClient
from app.devices.melcloud_client import MELCloudClient
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ControlRequest:
    """Control request parameters."""
    action: str  # "heat" or "off"
    setpoint: Optional[float] = None
    delta: Optional[float] = None
    minutes: int = 60
    device: str = "auto"
    mode: Optional[str] = None
    fan: Optional[str] = None
    vane_h: Optional[str] = None
    vane_v: Optional[str] = None
    vanes: Optional[bool] = None


@dataclass
class ControlResult:
    """Result of a control action."""
    room: str
    device: Optional[str] = None
    action: Optional[str] = None
    setpoint: Optional[float] = None
    success: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to API response format."""
        result = {"room": self.room}

        if self.error:
            result["error"] = self.error
        else:
            result["device"] = self.device
            result["action"] = self.action
            result["success"] = self.success
            if self.setpoint is not None:
                result["setpoint"] = self.setpoint

        return result


class ControlService:
    """
    Service for controlling HVAC devices.

    Handles:
    - Device type selection (AC vs Tado)
    - Setpoint calculation
    - Device control execution
    - Error handling
    """

    def __init__(
        self,
        tado: TadoClient,
        mel: MELCloudClient,
        config: ConfigManager
    ):
        """
        Initialize control service.

        Args:
            tado: Tado API client
            mel: MELCloud API client
            config: Configuration manager
        """
        self.tado = tado
        self.mel = mel
        self.config = config

    async def control_rooms(
        self,
        room_keys: List[str],
        request: ControlRequest
    ) -> List[ControlResult]:
        """
        Execute control action on multiple rooms.

        Args:
            room_keys: List of room identifiers
            request: Control request parameters

        Returns:
            List of ControlResult for each room
        """
        cfg = await self.config.load_config()

        results = []
        for room_key in room_keys:
            result = await self._control_single_room(room_key, cfg.rooms.get(room_key), request)
            results.append(result)

        return results

    async def _control_single_room(
        self,
        room_key: str,
        room_config: Optional[RoomConfig],
        request: ControlRequest
    ) -> ControlResult:
        """
        Execute control action on a single room.

        Uses guard clauses to avoid nesting.
        """
        # Guard clause: room not found in config
        if not room_config:
            return ControlResult(room=room_key, error="Room not found in configuration")

        # Determine device type
        device_type = self._determine_device_type(request.device, room_config)

        # Guard clause: no devices configured
        if not device_type:
            return ControlResult(room=room_key, error="No devices configured for this room")

        # Execute action (device clients handle errors internally)
        if request.action == "heat":
            return await self._execute_heat_action(room_key, room_config, device_type, request)

        # action == "off"
        return await self._execute_off_action(room_key, room_config, device_type)

    def _determine_device_type(self, requested_device: str, room_config: RoomConfig) -> Optional[str]:
        """
        Determine which device type to use.

        Args:
            requested_device: "auto", "ac", "tado", or "rad"
            room_config: Room configuration

        Returns:
            "ac" or "tado", or None if no devices available
        """
        # Explicit device type requested
        if requested_device in ["ac", "tado", "rad"]:
            return requested_device

        # Auto selection: prefer AC if available
        if room_config.mel or room_config.mel_multi:
            return "ac"

        if room_config.tado:
            return "tado"

        return None

    async def _execute_heat_action(
        self,
        room_key: str,
        room_config: RoomConfig,
        device_type: str,
        request: ControlRequest
    ) -> ControlResult:
        """Execute heating action on a device."""
        setpoint = self._calculate_setpoint(request)

        if device_type == "ac":
            return await self._heat_with_ac(room_key, room_config, setpoint)

        # device_type in ["tado", "rad"]
        return await self._heat_with_tado(room_key, room_config, setpoint, request.minutes)

    async def _execute_off_action(
        self,
        room_key: str,
        room_config: RoomConfig,
        device_type: str
    ) -> ControlResult:
        """Execute off action on a device."""
        if device_type == "ac":
            return await self._turn_off_ac(room_key, room_config)

        # device_type in ["tado", "rad"]
        return await self._turn_off_tado(room_key, room_config)

    def _calculate_setpoint(self, request: ControlRequest) -> float:
        """
        Calculate target setpoint from request.

        Priority: explicit setpoint > default + delta
        """
        if request.setpoint is not None:
            return request.setpoint

        default_setpoint = 21.0
        if request.delta:
            return default_setpoint + request.delta

        return default_setpoint

    async def _heat_with_ac(
        self,
        room_key: str,
        room_config: RoomConfig,
        setpoint: float
    ) -> ControlResult:
        """Turn on AC heating."""
        # Get AC unit name
        mel_name = self._get_ac_unit_name(room_config)

        # Guard clause: no AC unit configured
        if not mel_name:
            return ControlResult(room=room_key, error="No AC unit configured")

        # Execute control
        success = await self.mel.turn_on(mel_name, setpoint)

        return ControlResult(
            room=room_key,
            device="ac",
            action="heat",
            setpoint=setpoint,
            success=success
        )

    async def _heat_with_tado(
        self,
        room_key: str,
        room_config: RoomConfig,
        setpoint: float,
        minutes: int
    ) -> ControlResult:
        """Turn on Tado heating."""
        # Guard clause: no Tado zone configured
        if not room_config.tado:
            return ControlResult(room=room_key, error="No Tado zone configured")

        # Execute control
        duration_seconds = minutes * 60
        success = await self.tado.turn_on(room_config.tado, setpoint, duration_seconds=duration_seconds)

        return ControlResult(
            room=room_key,
            device="tado",
            action="heat",
            setpoint=setpoint,
            success=success
        )

    async def _turn_off_ac(
        self,
        room_key: str,
        room_config: RoomConfig
    ) -> ControlResult:
        """Turn off AC."""
        mel_name = self._get_ac_unit_name(room_config)

        # Guard clause: no AC unit configured
        if not mel_name:
            return ControlResult(room=room_key, error="No AC unit configured")

        # Execute control
        success = await self.mel.turn_off(mel_name)

        return ControlResult(
            room=room_key,
            device="ac",
            action="off",
            success=success
        )

    async def _turn_off_tado(
        self,
        room_key: str,
        room_config: RoomConfig
    ) -> ControlResult:
        """Turn off Tado."""
        # Guard clause: no Tado zone configured
        if not room_config.tado:
            return ControlResult(room=room_key, error="No Tado zone configured")

        # Execute control
        success = await self.tado.turn_off(room_config.tado)

        return ControlResult(
            room=room_key,
            device="tado",
            action="off",
            success=success
        )

    def _get_ac_unit_name(self, room_config: RoomConfig) -> Optional[str]:
        """
        Get AC unit name for a room.

        Checks mel first, then first unit in mel_multi.
        """
        if room_config.mel:
            return room_config.mel

        if room_config.mel_multi:
            return room_config.mel_multi[0]

        return None
