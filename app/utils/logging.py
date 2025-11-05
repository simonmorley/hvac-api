"""
Structured logging setup using structlog.
Outputs JSON-formatted logs for easy parsing.
"""

import logging
import os
import sys

import structlog


def setup_logging():
    """
    Configure structlog for JSON-formatted logging.

    Log levels:
    - DEBUG: Detailed diagnostic information
    - INFO: General informational messages
    - WARNING: Warning messages (e.g., timeouts, retries)
    - ERROR: Error messages (e.g., API failures)

    Usage:
        from app.utils.logging import get_logger
        log = get_logger()
        log.info("config_loaded", rooms=5, outdoor_provider="open-meteo")
        log.warning("device_timeout", device="Master bedroom", timeout_ms=5000)
        log.error("api_call_failed", api="tado", error="401 Unauthorized")
    """
    log_level = os.getenv("LOG_LEVEL", "WARNING").upper()  # Default to WARNING to reduce noise

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level, logging.INFO),
    )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level, logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = None) -> structlog.BoundLogger:
    """
    Get a structlog logger instance.

    Args:
        name: Optional logger name (e.g., module name)

    Returns:
        Configured structlog logger

    Example:
        log = get_logger(__name__)
        log.info("event_occurred", user_id=123, action="login")
    """
    if name:
        return structlog.get_logger(name)
    return structlog.get_logger()
