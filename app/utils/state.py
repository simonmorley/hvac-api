"""
State manager for database-backed system state storage.
Provides async interface to the system_state table.
"""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert

from app.models.database import SystemState


class StateManager:
    """
    Manages system state in the database system_state table.

    Examples of state keys:
    - policy_enabled
    - last_policy_run
    - tado_device_code
    """

    def __init__(self, db_session: AsyncSession):
        """
        Initialize state manager with database session.

        Args:
            db_session: SQLAlchemy async session
        """
        self.db = db_session

    async def get(self, key: str) -> Optional[str]:
        """
        Get state value from database.

        Args:
            key: State key (e.g., 'tado_device_code')

        Returns:
            State value as string, or None if not found
        """
        result = await self.db.execute(
            select(SystemState.value).where(SystemState.key == key)
        )
        row = result.scalar_one_or_none()
        return row

    async def set(self, key: str, value: str) -> None:
        """
        Store or update state in database (upsert).

        Args:
            key: State key
            value: State value
        """
        stmt = insert(SystemState).values(key=key, value=value)
        stmt = stmt.on_conflict_do_update(
            index_elements=[SystemState.key],
            set_={"value": value}
        )
        await self.db.execute(stmt)
        await self.db.commit()

    async def delete(self, key: str) -> None:
        """
        Remove state from database.

        Args:
            key: State key to delete
        """
        await self.db.execute(
            delete(SystemState).where(SystemState.key == key)
        )
        await self.db.commit()
