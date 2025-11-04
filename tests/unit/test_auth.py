"""
Tests for API key authentication.
"""

import pytest
from unittest.mock import patch
from fastapi import HTTPException

from app.utils.auth import verify_api_key


def test_verify_api_key_missing_header():
    """Test that missing API key header raises 401."""
    with patch.dict("os.environ", {"API_KEY": "test-key"}):
        with pytest.raises(HTTPException) as exc_info:
            verify_api_key(x_api_key=None)

        assert exc_info.value.status_code == 401
        assert "Missing x-api-key header" in exc_info.value.detail


def test_verify_api_key_invalid():
    """Test that invalid API key raises 401."""
    with patch.dict("os.environ", {"API_KEY": "correct-key"}):
        with pytest.raises(HTTPException) as exc_info:
            verify_api_key(x_api_key="wrong-key")

        assert exc_info.value.status_code == 401
        assert "Invalid API key" in exc_info.value.detail


def test_verify_api_key_valid():
    """Test that valid API key is accepted."""
    with patch.dict("os.environ", {"API_KEY": "test-key-12345"}):
        result = verify_api_key(x_api_key="test-key-12345")
        assert result == "test-key-12345"


def test_verify_api_key_not_configured():
    """Test that missing API_KEY env var raises 500."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(HTTPException) as exc_info:
            verify_api_key(x_api_key="any-key")

        assert exc_info.value.status_code == 500
        assert "API_KEY not configured" in exc_info.value.detail
