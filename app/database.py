"""
Database connection and session management.
Uses SQLAlchemy 2.0+ async style.
"""

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker
)

from app.models.database import Base


# Get database URL from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://hvac:hvac@localhost:5432/hvac"
)

# Create async engine
# echo=True for development (shows SQL queries)
engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("LOG_LEVEL", "INFO") == "DEBUG",
    pool_pre_ping=True,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI endpoints.
    Yields a database session and ensures proper cleanup.

    Usage in FastAPI:
        @app.get("/endpoint")
        async def endpoint(db: AsyncSession = Depends(get_db)):
            # Use db here
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize database tables.
    Only for development/testing - use Alembic migrations in production.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """
    Close database connections.
    Call during application shutdown.
    """
    await engine.dispose()
