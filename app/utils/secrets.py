"""
Secrets manager for database-backed credential storage.
Provides async interface to the secrets table.
"""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert

from app.models.database import Secret


class SecretsManager:
    """
    Manages secrets in the database secrets table.

    Examples of secrets:
    - tado_refresh_token
    - melcloud_context_key
    - slack_webhook
    """

    def __init__(self, db_session: AsyncSession):
        """
        Initialize secrets manager with database session.

        Args:
            db_session: SQLAlchemy async session
        """
        self.db = db_session

    async def get(self, key: str) -> Optional[str]:
        """
        Get secret value from database.

        Args:
            key: Secret key (e.g., 'tado_refresh_token')

        Returns:
            Secret value as string, or None if not found
        """
        result = await self.db.execute(
            select(Secret.value).where(Secret.key == key)
        )
        row = result.scalar_one_or_none()
        return row

    async def set(self, key: str, value: str) -> None:
        """
        Store or update secret in database (upsert).

        Args:
            key: Secret key
            value: Secret value
        """
        stmt = insert(Secret).values(key=key, value=value)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Secret.key],
            set_={"value": value}
        )
        await self.db.execute(stmt)
        await self.db.commit()

    async def delete(self, key: str) -> None:
        """
        Remove secret from database.

        Args:
            key: Secret key to delete
        """
        await self.db.execute(
            delete(Secret).where(Secret.key == key)
        )
        await self.db.commit()
