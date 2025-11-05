"""
Logs API endpoints.
"""

from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.utils.auth import validate_api_key
from app.models.database import Log

router = APIRouter()


@router.get("/logs")
async def get_logs(
    n: int = Query(200, description="Number of log lines to retrieve"),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(validate_api_key)
):
    """
    Retrieve last N log lines.

    Args:
        n: Number of log lines to retrieve (default: 200)

    Returns:
        dict: {"lines": ["timestamp | level | message", ...]}
    """
    # Query last N logs ordered by created_at descending
    from sqlalchemy import select

    stmt = select(Log).order_by(Log.created_at.desc()).limit(n)
    result = await db.execute(stmt)
    logs = result.scalars().all()

    # Format logs as strings (created_at | level | message)
    lines = [
        f"{log.created_at.isoformat()} | {log.level} | {log.message}"
        for log in reversed(logs)  # Reverse to show oldest first
    ]

    return {"lines": lines}
