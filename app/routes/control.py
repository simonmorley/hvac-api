"""
Manual control endpoints.

This is a thin HTTP adapter - all business logic is in ControlService.
"""

from typing import List, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.utils.auth import validate_api_key
from app.dependencies import get_device_clients, get_config_manager
from app.config import ConfigManager
from app.devices.tado_client import TadoClient
from app.devices.melcloud_client import MELCloudClient
from app.services.control_service import ControlService, ControlRequest as ServiceControlRequest
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


class ControlRequest(BaseModel):
    """Request model for /control endpoint."""
    rooms: Optional[str] = None
    room: Optional[str] = None
    action: str
    setpoint: Optional[float] = None
    delta: Optional[float] = None
    minutes: int = 60
    device: str = "auto"
    mode: Optional[str] = None
    fan: Optional[str] = None
    vaneH: Optional[str] = None
    vaneV: Optional[str] = None
    vanes: Optional[bool] = None


@router.post("/control")
async def control_rooms(
    request: ControlRequest,
    clients: Tuple[TadoClient, MELCloudClient] = Depends(get_device_clients),
    config_mgr: ConfigManager = Depends(get_config_manager),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(validate_api_key)
):
    """
    Execute manual control action on rooms.

    Supports per-room or whole-house control with optional temperature override.

    Returns:
        dict: {
            "ok": true,
            "summary": "Controlled N rooms",
            "results": [...]
        }
    """
    tado, mel = clients
    config = await config_mgr.load_config()

    # Parse room list from request
    room_list = _parse_room_list(request, config)

    # Validate action
    if request.action not in ["heat", "off"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="action must be 'heat' or 'off'"
        )

    # Validate and clamp minutes
    minutes = min(max(request.minutes, 5), 360)

    # Delegate to service
    service = ControlService(tado, mel, config_mgr)
    service_request = ServiceControlRequest(
        action=request.action,
        setpoint=request.setpoint,
        delta=request.delta,
        minutes=minutes,
        device=request.device,
        mode=request.mode,
        fan=request.fan,
        vane_h=request.vaneH,
        vane_v=request.vaneV,
        vanes=request.vanes
    )

    results = await service.control_rooms(room_list, service_request)

    # Convert results to dicts
    result_dicts = [r.to_dict() for r in results]

    return {
        "ok": True,
        "summary": f"Controlled {len(results)} rooms",
        "results": result_dicts
    }


def _parse_room_list(request: ControlRequest, config) -> List[str]:
    """
    Parse room list from request and validate against config.

    Args:
        request: Control request
        config: System configuration

    Returns:
        List of valid room keys

    Raises:
        HTTPException if no valid rooms found
    """
    # Determine requested rooms
    room_list: List[str] = []

    if request.rooms:
        if request.rooms == "all":
            room_list = list(config.rooms.keys())
        else:
            room_list = [r.strip() for r in request.rooms.split(",")]
    elif request.room:
        room_list = [request.room]
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="missing room/rooms parameter"
        )

    # Validate rooms exist in config
    valid_rooms = [r for r in room_list if r in config.rooms]

    if not valid_rooms:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No rooms found matching: {','.join(room_list)}"
        )

    return valid_rooms
