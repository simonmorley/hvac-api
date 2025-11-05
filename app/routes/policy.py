"""
Policy management endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.utils.auth import validate_api_key
from app.utils.state import StateManager

router = APIRouter()


class PolicyEnabledRequest(BaseModel):
    enabled: bool


@router.get("/policy-enabled")
async def get_policy_enabled(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(validate_api_key)
):
    """
    Check if automated policy engine is enabled.

    Returns:
        dict: {"enabled": bool}
    """
    state_mgr = StateManager(db)
    enabled = await state_mgr.get_policy_enabled()
    return {"enabled": enabled}


@router.post("/policy-enabled")
async def set_policy_enabled(
    request: PolicyEnabledRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(validate_api_key)
):
    """
    Enable or disable automated policy engine.

    Args:
        request: {"enabled": bool}

    Returns:
        dict: {"ok": true, "enabled": bool}
    """
    state_mgr = StateManager(db)
    await state_mgr.set_policy_enabled(request.enabled)

    return {
        "ok": True,
        "enabled": request.enabled
    }


@router.post("/apply-policy")
async def apply_policy(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(validate_api_key)
):
    """
    Manually trigger the policy engine.

    Normally runs every 15 minutes via background task.

    Returns:
        HTTP 501: Policy engine not yet fully implemented
    """
    state_mgr = StateManager(db)
    enabled = await state_mgr.get_policy_enabled()

    if not enabled:
        return {
            "ok": False,
            "reason": "policy disabled"
        }

    # Policy engine implementation is pending (requires SchedulerService, NotificationService, etc.)
    raise HTTPException(
        status_code=501,
        detail="Policy engine not yet implemented. Use /control endpoint for manual device control."
    )
