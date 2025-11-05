"""
Test connections endpoint for verifying external API connectivity.
"""

from typing import Dict, Any, Tuple

from fastapi import APIRouter, Depends

from app.dependencies import get_device_clients, get_config_manager
from app.config import ConfigManager
from app.devices.tado_client import TadoClient
from app.devices.melcloud_client import MELCloudClient
from app.devices.weather_client import WeatherClient
from app.utils.logging import get_logger
from app.utils.auth import verify_api_key

logger = get_logger(__name__)

router = APIRouter()


async def test_tado(client: TadoClient) -> bool:
    """
    Test Tado connectivity.

    Args:
        client: TadoClient instance

    Returns:
        True if successful, False otherwise
    """
    try:
        zones = await client.list_zones()
        logger.info(f"Tado test successful: {len(zones)} zones found")
        return True
    except Exception as e:
        logger.error(f"Tado test failed: {e}")
        return False


async def test_melcloud(client: MELCloudClient) -> bool:
    """
    Test MELCloud connectivity.

    Args:
        client: MELCloudClient instance

    Returns:
        True if successful, False otherwise
    """
    try:
        devices = await client.list_devices()
        logger.info(f"MELCloud test successful: {len(devices)} devices found")
        return True
    except Exception as e:
        logger.error(f"MELCloud test failed: {e}")
        return False


async def test_weather(client: WeatherClient) -> bool:
    """
    Test weather API connectivity.

    Args:
        client: WeatherClient instance

    Returns:
        True if successful, False otherwise
    """
    try:
        temp = await client.get_outdoor_temperature()
        if temp is not None:
            logger.info(f"Weather test successful: {temp}°C")
            return True
        else:
            logger.error("Weather test failed: No temperature returned")
            return False
    except Exception as e:
        logger.error(f"Weather test failed: {e}")
        return False


@router.get("/test-connections")
async def test_connections_endpoint(
    clients: Tuple[TadoClient, MELCloudClient] = Depends(get_device_clients),
    config_mgr: ConfigManager = Depends(get_config_manager),
    api_key: str = Depends(verify_api_key)
) -> Dict[str, Any]:
    """
    Test connectivity to all external APIs.

    This endpoint verifies that:
    - Tado API authentication and zone listing works
    - MELCloud API authentication and device listing works
    - Weather API can fetch outdoor temperature

    Returns:
        dict: Test results with sim_mode flag
        {
            "tado_ok": bool,
            "melcloud_ok": bool,
            "weather_ok": bool,
            "sim_mode": bool,
            "details": {
                "tado": str,
                "melcloud": str,
                "weather": str
            }
        }
    """
    # Unpack device clients
    tado_client, melcloud_client = clients

    # Get sim mode from clients
    sim_mode = tado_client.sim_mode

    logger.info("Testing external API connections", extra={"sim_mode": sim_mode})

    # Load config for weather client
    config = await config_mgr.load_config()

    weather_client = WeatherClient(
        latitude=config.weather.lat,
        longitude=config.weather.lon,
        sim_mode=sim_mode
    )

    # Test each API
    tado_ok = await test_tado(tado_client)
    melcloud_ok = await test_melcloud(melcloud_client)
    weather_ok = await test_weather(weather_client)

    # Build details
    details = {
        "tado": "Connected" if tado_ok else "Failed",
        "melcloud": "Connected" if melcloud_ok else "Failed",
        "weather": "Connected" if weather_ok else "Failed"
    }

    return {
        "tado_ok": tado_ok,
        "melcloud_ok": melcloud_ok,
        "weather_ok": weather_ok,
        "sim_mode": sim_mode,
        "details": details
    }
