"""
Configuration management for HVAC system.
Loads config from database with file fallback.
"""

import json
import os
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.config import HVACConfig
from app.models.database import ConfigStore


class ConfigManager:
    """Manages loading and saving HVAC configuration."""

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def load_config(self) -> HVACConfig:
        """
        Load configuration from database or file fallback.

        Priority:
        1. Database (config_store table)
        2. config.json file in project root
        3. Raise error if neither exists

        Returns:
            Validated HVACConfig instance

        Raises:
            FileNotFoundError: If no config found in DB or file
            ValueError: If config validation fails
        """
        # Try loading from database first
        result = await self.db.execute(
            select(ConfigStore).where(ConfigStore.id == 1)
        )
        config_row = result.scalar_one_or_none()

        if config_row:
            # Parse JSON from database
            config_data = json.loads(config_row.config_json)
            return HVACConfig(**config_data)

        # Fall back to config.json file
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "config.json"
        )

        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config_data = json.load(f)
            return HVACConfig(**config_data)

        raise FileNotFoundError(
            "No configuration found in database or config.json file"
        )

    async def save_config(self, config: HVACConfig) -> bool:
        """
        Save configuration to database.

        Args:
            config: Validated HVACConfig instance

        Returns:
            True if successful

        Raises:
            Exception: If database operation fails
        """
        # Serialize to JSON
        config_json = config.model_dump_json(indent=2)

        # Check if config exists
        result = await self.db.execute(
            select(ConfigStore).where(ConfigStore.id == 1)
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing config
            existing.config_json = config_json
        else:
            # Insert new config
            new_config = ConfigStore(
                id=1,
                config_json=config_json
            )
            self.db.add(new_config)

        await self.db.commit()
        return True

    async def get_config_json(self) -> Optional[str]:
        """
        Get raw configuration JSON from database.

        Returns:
            JSON string or None if not found
        """
        result = await self.db.execute(
            select(ConfigStore.config_json).where(ConfigStore.id == 1)
        )
        return result.scalar_one_or_none()


async def load_config_from_file(filepath: str) -> HVACConfig:
    """
    Load and validate configuration from a JSON file.

    Args:
        filepath: Path to config.json file

    Returns:
        Validated HVACConfig instance

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If validation fails
    """
    with open(filepath, 'r') as f:
        config_data = json.load(f)

    return HVACConfig(**config_data)
