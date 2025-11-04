"""
FastAPI application for HVAC Control System.
Phase 1: Basic skeleton with health check endpoint only.
"""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from app.database import close_db, init_db
from app.utils.logging import setup_logging, get_logger
from app.routes import test_connections


# Load environment variables
load_dotenv()

# Setup logging
setup_logging()
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    FastAPI 0.104+ uses lifespan instead of @app.on_event.
    """
    # Startup
    log.info("application_starting", version="2.0.0")

    # Initialize database (optional - use Alembic in production)
    if os.getenv("INIT_DB", "false").lower() == "true":
        log.info("initializing_database")
        await init_db()

    log.info("application_ready")

    yield

    # Shutdown
    log.info("application_shutting_down")
    await close_db()
    log.info("application_stopped")


# Create FastAPI application
app = FastAPI(
    title="HVAC Control System",
    version="2.0.0",
    description="Smart HVAC control for Tado radiators and MELCloud AC units",
    lifespan=lifespan
)

# Include routers
app.include_router(test_connections.router, tags=["Testing"])


@app.get("/healthz")
async def healthz():
    """
    Health check endpoint.
    No authentication required.

    Returns:
        dict: {"ok": true}
    """
    return {"ok": True}


@app.get("/")
async def root():
    """
    Root endpoint - basic info.

    Returns:
        dict: Application information
    """
    return {
        "ok": True,
        "name": "HVAC Control System",
        "version": "2.0.0",
        "status": "operational"
    }
