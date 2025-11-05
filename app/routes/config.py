"""
Configuration management endpoints.
"""

from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.utils.auth import validate_api_key
from app.config import ConfigManager

router = APIRouter()


@router.get("/config")
async def get_config(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(validate_api_key)
):
    """
    Retrieve current HVAC configuration.

    Returns:
        dict: Full configuration object with all settings
    """
    config_mgr = ConfigManager(db)

    try:
        config = await config_mgr.load_config()
        # Return as dict for JSON serialization
        return config.model_dump()
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Configuration not found"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load configuration: {str(e)}"
        )


@router.put("/config")
async def update_config(
    config_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    _: None = Depends(validate_api_key)
):
    """
    Update HVAC configuration.

    Accepts partial or complete config object. Server merges with existing config.

    Args:
        config_data: Configuration object (partial or complete)

    Returns:
        dict: {"ok": true}
    """
    from app.models.config import HVACConfig

    config_mgr = ConfigManager(db)

    try:
        # Load existing config
        try:
            existing_config = await config_mgr.load_config()
            existing_dict = existing_config.model_dump()
        except FileNotFoundError:
            # No existing config, use provided data as-is
            existing_dict = {}

        # Deep merge new config into existing
        merged_dict = deep_merge(existing_dict, config_data)

        # Validate merged config
        new_config = HVACConfig(**merged_dict)

        # Save to database
        await config_mgr.save_config(new_config)

        return {"ok": True}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid configuration: {str(e)}"
        )


def deep_merge(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge two dictionaries.

    Args:
        base: Base dictionary
        updates: Updates to apply

    Returns:
        Merged dictionary
    """
    result = base.copy()

    for key, value in updates.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value

    return result
