"""
SQLAlchemy ORM models for database tables.
Uses SQLAlchemy 2.0+ async style.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, Column, Float, Integer,
    String, Text, DateTime, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


class Secret(Base):
    """
    Stores API tokens and credentials.
    Examples: tado_refresh_token, melcloud_session, slack_webhook
    """
    __tablename__ = "secrets"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )


class SystemState(Base):
    """
    Tracks policy engine state.
    Examples: policy_enabled (true/false), last_run_time (ISO timestamp)
    """
    __tablename__ = "system_state"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )


class DeviceCommand(Base):
    """
    Records every command sent to devices.
    Used for override detection (compare last command vs actual state).
    Only stores latest command per device (UNIQUE constraint).
    """
    __tablename__ = "device_commands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_name: Mapped[str] = mapped_column(String, nullable=False)
    device_type: Mapped[str] = mapped_column(String, nullable=False)  # 'ac' or 'tado'
    commanded_action: Mapped[str] = mapped_column(String, nullable=False)  # 'on' or 'off'
    commanded_setpoint: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    commanded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    success: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    __table_args__ = (
        UniqueConstraint('device_name', 'device_type', name='uq_device_command'),
    )


class DeviceOverride(Base):
    """
    Tracks active manual overrides.
    When user manually changes a device, pause automation until expires_at.
    """
    __tablename__ = "device_overrides"

    device_name: Mapped[str] = mapped_column(String, primary_key=True)
    device_type: Mapped[str] = mapped_column(String, primary_key=True)  # 'ac' or 'tado'
    override_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class DeviceCooldown(Base):
    """
    Tracks AC/Tado cooldown timers for compressor protection.
    AC: 5 min OFF->ON, 5 min ON->OFF, 15 min minimum ON time
    Tado: 3 min between any state change
    """
    __tablename__ = "device_cooldowns"

    device_name: Mapped[str] = mapped_column(String, primary_key=True)
    last_turned_on_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    last_turned_off_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )


class ConfigStore(Base):
    """
    Stores the active configuration JSON.
    Singleton table (only one row allowed via CHECK constraint).
    """
    __tablename__ = "config_store"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        default=1,
        server_default="1"
    )
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint('id = 1', name='single_row_check'),
    )


class Log(Base):
    """
    Simple logging table for GET /logs endpoint.
    Supports structured logging with JSONB extra_data.
    """
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(String, nullable=False)  # 'info', 'warning', 'error'
    message: Mapped[str] = mapped_column(Text, nullable=False)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True
    )

    __table_args__ = (
        Index('idx_logs_created_at', 'created_at', postgresql_using='btree'),
    )
