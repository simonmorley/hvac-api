"""
Pytest fixtures for testing.
Provides mock database sessions and other test utilities.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_db_session():
    """
    Provides a mock async database session for testing.
    Use this when you need a database session but don't want real DB operations.
    """
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.close = AsyncMock()
    return session
