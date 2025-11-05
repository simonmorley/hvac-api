"""
Inventory and device discovery endpoints.
"""

from typing import List, Dict, Any, Tuple
from fastapi import APIRouter, Depends

from app.utils.auth import validate_api_key
from app.dependencies import get_device_clients, get_config_manager
from app.config import ConfigManager
from app.devices.tado_client import TadoClient
from app.devices.melcloud_client import MELCloudClient

router = APIRouter()


@router.get("/inventory")
async def get_inventory(
    clients: Tuple[TadoClient, MELCloudClient] = Depends(get_device_clients),
    config_mgr: ConfigManager = Depends(get_config_manager),
    _: None = Depends(validate_api_key)
):
    """
    List all available rooms with device mappings and available zones/units.

    Returns:
        dict: {
            "rooms": [...],
            "tado_zones": [...],
            "mel_units": [...]
        }
    """
    tado, mel = clients
    config = await config_mgr.load_config()

    # Fetch available devices
    tado_zones = await tado.list_zones()
    mel_units = await mel.list_devices()

    # Build room inventory from config
    rooms: List[Dict[str, Any]] = []

    for room_key, room_config in config.rooms.items():
        # Determine mel field format (string or list)
        mel_value = None
        if room_config.mel:
            mel_value = room_config.mel
        elif room_config.mel_multi and len(room_config.mel_multi) > 0:
            mel_value = room_config.mel_multi

        room_data = {
            "key": room_key,
            "tado": room_config.tado,
            "mel": mel_value,
            "mel_multi": room_config.mel_multi or [],
            "hasRad": bool(room_config.tado),
            "hasAC": bool(room_config.mel or room_config.mel_multi)
        }
        rooms.append(room_data)

    return {
        "rooms": rooms,
        "tado_zones": tado_zones,
        "mel_units": mel_units
    }


@router.get("/rooms")
async def get_rooms(
    clients: Tuple[TadoClient, MELCloudClient] = Depends(get_device_clients),
    _: None = Depends(validate_api_key)
):
    """
    List available Tado zones and MELCloud units.

    Returns:
        dict: {
            "tado_zones": [...],
            "mel_units": [...]
        }
    """
    tado, mel = clients

    tado_zones = await tado.list_zones()
    mel_units = await mel.list_devices()

    return {
        "tado_zones": tado_zones,
        "mel_units": mel_units
    }
