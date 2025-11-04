"""
Tado OAuth authentication endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.devices.tado_client import TadoClient
from app.utils.auth import verify_api_key
from app.utils.secrets import SecretsManager
from app.utils.state import StateManager
from app.utils.logging import get_logger
import os

logger = get_logger(__name__)

router = APIRouter()


@router.post("/tado/start")
async def start_tado_oauth(
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key)
):
    """
    Start Tado OAuth device code flow.

    Returns user_code and verification URL for user to authorize.
    Stores device_code in database for /tado/poll to retrieve.

    Returns:
        {
            "user_code": "ABCD-EFGH",
            "verification_uri_complete": "https://auth.tado.com/...",
            "message": "Visit the URL and enter the code to authorize"
        }
    """
    try:
        tado = TadoClient(
            home_id=os.getenv("TADO_HOME_ID", ""),
            db_session=db,
            sim_mode=False
        )

        result = await tado.start_oauth_flow()

        # Store device_code in database for /tado/poll to retrieve
        state = StateManager(db)
        await state.set("tado_device_code", result["device_code"])

        logger.info("Tado OAuth flow started", extra={"user_code": result["user_code"]})

        # Don't return device_code - it's stored server-side
        return {
            "user_code": result["user_code"],
            "verification_uri_complete": result["verification_uri_complete"],
            "message": f"Visit {result['verification_uri_complete']} and enter code: {result['user_code']}"
        }

    except Exception as e:
        logger.error(f"Failed to start Tado OAuth flow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tado/poll")
async def poll_tado_oauth(
    db: AsyncSession = Depends(get_db),
    api_key: str = Depends(verify_api_key)
) -> dict:
    """
    Poll Tado OAuth completion.

    Keep calling this endpoint until authorization is complete.
    Retrieves device_code from database (stored by /tado/start).

    Returns:
        - 200: Authorization complete, tokens stored
        - 202: Still waiting for user to authorize
        - 400: Authorization failed/expired or no device_code saved
    """
    try:
        # Retrieve device_code from database
        state = StateManager(db)
        device_code = await state.get("tado_device_code")

        if not device_code:
            logger.warning("No device_code found in database - user must call /tado/start first")
            return {
                "ok": False,
                "error": "no device_code saved (run /tado/start again)"
            }

        tado = TadoClient(
            home_id=os.getenv("TADO_HOME_ID", ""),
            db_session=db,
            sim_mode=False
        )

        result = await tado.poll_oauth_completion(device_code)

        if result is None:
            # Still pending - user hasn't authorized yet
            return {
                "pending": True,
                "message": "Waiting for user approval"
            }

        # Validate response contains refresh_token
        if "refresh_token" not in result:
            logger.error(f"No refresh_token in Tado response: {result}")
            raise HTTPException(
                status_code=500,
                detail="No refresh_token returned from Tado - response may be incomplete"
            )

        # Success - store refresh token
        secrets = SecretsManager(db)
        await secrets.set("tado_refresh_token", result["refresh_token"])

        # Clean up device_code from state
        await state.delete("tado_device_code")

        logger.info("Tado OAuth completed successfully, refresh token stored")

        return {
            "ok": True,
            "message": "Tado authentication successful! Token saved and verified. Will persist across restarts.",
            "verified": True
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Tado OAuth polling failed: {error_msg}")

        if "expired" in error_msg.lower() or "denied" in error_msg.lower():
            raise HTTPException(status_code=400, detail=error_msg)

        raise HTTPException(status_code=500, detail=error_msg)
