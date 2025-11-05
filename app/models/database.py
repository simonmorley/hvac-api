"""
SQLAlchemy ORM models for database tables.
Uses SQLAlchemy 2.0+ async style.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, CheckConstraint, Column, Float, Integer, ForeignKey,
    String, Text, DateTime, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
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


class ApiCache(Base):
    """
    Generic API response cache to prevent rate limiting.

    Critical for Tado API which has strict rate limits (blocked for days on violation).
    Caches zone lists (1 hour TTL), zone states (2 minute TTL), etc.

    Key format examples:
    - tado:zones:{home_id}
    - tado:zone_state:{home_id}:{zone_id}
    - melcloud:devices
    """
    __tablename__ = "api_cache"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    __table_args__ = (
        Index('idx_api_cache_expires_at', 'expires_at', postgresql_using='btree'),
    )


class Group(Base):
    """
    Room grouping (e.g., Upstairs, Downstairs, Bedrooms).
    Supports many-to-many relationship with rooms.
    """
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )


class Room(Base):
    """
    Room configuration with device mappings and schedule.
    """
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    tado_zone: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    mel_device: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    mel_devices: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # List of AC unit names
    ac_settings: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    schedule: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )


class RoomGroup(Base):
    """
    Junction table for many-to-many relationship between rooms and groups.
    """
    __tablename__ = "room_groups"

    room_id: Mapped[int] = mapped_column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), primary_key=True)
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )


class SystemSettings(Base):
    """
    Global system configuration (singleton table).
    Stores AC defaults, PV config, weather config, thresholds, targets.
    """
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1, server_default="1")
    ac_defaults: Mapped[dict] = mapped_column(JSONB, nullable=False)
    pv_config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    weather_config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    thresholds: Mapped[dict] = mapped_column(JSONB, nullable=False)
    targets: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint('id = 1', name='system_settings_singleton'),
    )


class Exclusion(Base):
    """
    Devices to exclude from automation.
    """
    __tablename__ = "exclusions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_type: Mapped[str] = mapped_column(String(20), nullable=False)  # 'tado' or 'mel'
    device_name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint('device_type', 'device_name', name='uq_exclusion_device'),
    )


class BlackoutWindow(Base):
    """
    Time windows where automation should be paused.
    """
    __tablename__ = "blackout_windows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_time: Mapped[str] = mapped_column(String(5), nullable=False)  # HH:MM format
    end_time: Mapped[str] = mapped_column(String(5), nullable=False)  # HH:MM format
    applies_to: Mapped[dict] = mapped_column(JSONB, nullable=False)  # ["tado", "mel"]
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
