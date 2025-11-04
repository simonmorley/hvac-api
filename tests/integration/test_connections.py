"""
Integration tests for test-connections endpoint.
Uses test client with sim mode enabled.
"""

import pytest
from httpx import AsyncClient
from unittest.mock import patch
import os

from app.main import app


@pytest.mark.asyncio
async def test_test_connections_endpoint_sim_mode():
    """
    Test the /test-connections endpoint in sim mode.
    All external API tests should pass in sim mode.
    """
    # Set SIM_MODE and API_KEY for this test
    with patch.dict(os.environ, {"SIM_MODE": "true", "API_KEY": "test-key"}):
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/test-connections",
                headers={"x-api-key": "test-key"}
            )

    assert response.status_code == 200
    data = response.json()

    # All tests should pass in sim mode
    assert data["sim_mode"] is True
    assert data["tado_ok"] is True
    assert data["melcloud_ok"] is True
    assert data["weather_ok"] is True

    # Check details
    assert data["details"]["tado"] == "Connected"
    assert data["details"]["melcloud"] == "Connected"
    assert data["details"]["weather"] == "Connected"


@pytest.mark.asyncio
async def test_test_connections_response_format():
    """
    Test that response format matches expected structure.
    """
    with patch.dict(os.environ, {"SIM_MODE": "true", "API_KEY": "test-key"}):
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/test-connections",
                headers={"x-api-key": "test-key"}
            )

    assert response.status_code == 200
    data = response.json()

    # Check required keys
    assert "tado_ok" in data
    assert "melcloud_ok" in data
    assert "weather_ok" in data
    assert "sim_mode" in data
    assert "details" in data

    # Check types
    assert isinstance(data["tado_ok"], bool)
    assert isinstance(data["melcloud_ok"], bool)
    assert isinstance(data["weather_ok"], bool)
    assert isinstance(data["sim_mode"], bool)
    assert isinstance(data["details"], dict)


@pytest.mark.asyncio
async def test_test_connections_requires_auth():
    """
    Test that /test-connections requires API key authentication.
    """
    with patch.dict(os.environ, {"SIM_MODE": "true", "API_KEY": "test-key"}):
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Request without API key should fail
            response = await client.get("/test-connections")

    assert response.status_code == 401
    assert "Missing x-api-key header" in response.json()["detail"]


@pytest.mark.asyncio
async def test_test_connections_invalid_api_key():
    """
    Test that /test-connections rejects invalid API key.
    """
    with patch.dict(os.environ, {"SIM_MODE": "true", "API_KEY": "correct-key"}):
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Request with wrong API key should fail
            response = await client.get(
                "/test-connections",
                headers={"x-api-key": "wrong-key"}
            )

    assert response.status_code == 401
    assert "Invalid API key" in response.json()["detail"]
