"""
API key authentication middleware.
"""

import os
from typing import Optional
from fastapi import Header, HTTPException, status


def verify_api_key(x_api_key: Optional[str] = Header(None)) -> str:
    """
    Verify API key from x-api-key header.

    Args:
        x_api_key: API key from header

    Returns:
        Validated API key

    Raises:
        HTTPException: If API key is missing or invalid (401)
    """
    expected_key = os.getenv("API_KEY")

    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API_KEY not configured on server"
        )

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing x-api-key header"
        )

    if x_api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )

    return x_api_key


# Alias for consistency with route usage
validate_api_key = verify_api_key
