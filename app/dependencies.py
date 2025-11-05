"""
FastAPI dependency injection for common services.
Centralizes client initialization to avoid repetition.
"""

import os
from typing import Tuple
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.devices.tado_client import TadoClient
from app.devices.melcloud_client import MELCloudClient
from app.config import ConfigManager


async def get_device_clients(
    db: AsyncSession = Depends(get_db)
) -> Tuple[TadoClient, MELCloudClient]:
    """
    Dependency that provides initialized device clients.

    Args:
        db: Database session (injected)

    Returns:
        Tuple of (TadoClient, MELCloudClient)

    Raises:
        ValueError: If required environment variables are missing
    """
    # Get configuration from environment
    tado_home_id = os.getenv("TADO_HOME_ID")
    melcloud_email = os.getenv("MELCLOUD_EMAIL")
    melcloud_password = os.getenv("MELCLOUD_PASSWORD")
    sim_mode = os.getenv("SIM_MODE", "false").lower() == "true"

    # Validate required credentials
    if not tado_home_id:
        raise ValueError("TADO_HOME_ID environment variable not set")
    if not melcloud_email:
        raise ValueError("MELCLOUD_EMAIL environment variable not set")
    if not melcloud_password:
        raise ValueError("MELCLOUD_PASSWORD environment variable not set")

    # Initialize clients
    tado = TadoClient(
        home_id=tado_home_id,
        db_session=db,
        sim_mode=sim_mode
    )

    mel = MELCloudClient(
        email=melcloud_email,
        password=melcloud_password,
        db_session=db,
        sim_mode=sim_mode
    )

    return tado, mel


async def get_config_manager(
    db: AsyncSession = Depends(get_db)
) -> ConfigManager:
    """
    Dependency that provides a ConfigManager instance.

    Args:
        db: Database session (injected)

    Returns:
        ConfigManager instance
    """
    return ConfigManager(db)
