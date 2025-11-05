"""
Status API endpoints - returns per-room live data.

This is a thin HTTP adapter - all business logic is in StatusService.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from fastapi import APIRouter, Depends

from app.utils.auth import validate_api_key
from app.utils.logging import get_logger
from app.dependencies import get_device_clients, get_config_manager
from app.config import ConfigManager
from app.devices.tado_client import TadoClient
from app.devices.melcloud_client import MELCloudClient
from app.services.status_service import StatusService

logger = get_logger(__name__)

router = APIRouter()

# IMPORTANT: In-memory cache - not shared across workers
# For multi-worker deployments, use Redis or database caching instead
# This is acceptable for single-worker development/testing
_status_cache: Optional[Dict[str, Any]] = None
_cache_expires_at: Optional[datetime] = None
_CACHE_TTL = timedelta(seconds=30)


@router.get("/status")
async def get_status(
    clients: Tuple[TadoClient, MELCloudClient] = Depends(get_device_clients),
    config_mgr: ConfigManager = Depends(get_config_manager),
    _: None = Depends(validate_api_key)
):
    """
    Get live status for all rooms (temperatures, power states, etc).

    Returns per-room data with current temperatures and device states.

    Cached for 30 seconds to prevent API rate limiting.
    """
    global _status_cache, _cache_expires_at

    # Check cache - early return if valid
    now = datetime.now()
    if _status_cache and _cache_expires_at and now < _cache_expires_at:
        logger.info("Returning cached status")
        return _status_cache

    # Delegate all business logic to service
    tado, mel = clients
    service = StatusService(tado, mel, config_mgr)
    result = await service.get_all_room_status()

    # Update cache
    _status_cache = result
    _cache_expires_at = datetime.now() + _CACHE_TTL

    return result
