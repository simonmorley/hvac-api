"""
Health check endpoints.
"""

from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.utils.auth import validate_api_key

router = APIRouter()


@router.get("/health")
async def health_check(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(validate_api_key)
):
    """
    Extended health check with service status.

    Returns:
        dict: {
            "ok": true,
            "timestamp": "2024-01-01T12:00:00.000Z",
            "services": {
                "kv": {"CONFIG": true, "STATE": true, "LOGS": true},
                "stateTracker": "simple"
            }
        }
    """
    # Test database connectivity
    try:
        await db.execute("SELECT 1")
        db_ok = True
    except:
        db_ok = False

    return {
        "ok": db_ok,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "services": {
            "kv": {
                "CONFIG": db_ok,
                "STATE": db_ok,
                "LOGS": db_ok
            },
            "stateTracker": "simple"
        }
    }
