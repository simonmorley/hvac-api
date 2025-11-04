"""
Tests for secrets manager.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.engine import Result, ScalarResult

from app.utils.secrets import SecretsManager


@pytest.mark.asyncio
async def test_get_existing_secret(mock_db_session):
    """Test getting an existing secret from database."""
    # Mock database response
    mock_result = MagicMock(spec=Result)
    mock_result.scalar_one_or_none.return_value = "test_value"
    mock_db_session.execute.return_value = mock_result

    manager = SecretsManager(mock_db_session)
    value = await manager.get("test_key")

    assert value == "test_value"
    mock_db_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_nonexistent_secret(mock_db_session):
    """Test getting a secret that doesn't exist."""
    # Mock database response
    mock_result = MagicMock(spec=Result)
    mock_result.scalar_one_or_none.return_value = None
    mock_db_session.execute.return_value = mock_result

    manager = SecretsManager(mock_db_session)
    value = await manager.get("nonexistent_key")

    assert value is None
    mock_db_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_set_secret(mock_db_session):
    """Test setting a secret value (upsert)."""
    manager = SecretsManager(mock_db_session)
    await manager.set("test_key", "test_value")

    # Should execute and commit
    mock_db_session.execute.assert_called_once()
    mock_db_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_delete_secret(mock_db_session):
    """Test deleting a secret."""
    manager = SecretsManager(mock_db_session)
    await manager.delete("test_key")

    # Should execute and commit
    mock_db_session.execute.assert_called_once()
    mock_db_session.commit.assert_called_once()
