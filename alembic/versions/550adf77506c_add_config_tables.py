"""add config tables for database-backed configuration

Revision ID: 550adf77506c
Revises: 53d985768d5c
Create Date: 2025-11-04 19:45:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import json

# revision identifiers, used by Alembic.
revision = '550adf77506c'
down_revision = '53d985768d5c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create system_settings table (single row for global config)
    op.create_table(
        'system_settings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('ac_defaults', postgresql.JSONB(), nullable=False),
        sa.Column('pv_config', postgresql.JSONB(), nullable=False),
        sa.Column('weather_config', postgresql.JSONB(), nullable=False),
        sa.Column('thresholds', postgresql.JSONB(), nullable=False),
        sa.Column('targets', postgresql.JSONB(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False)
    )

    # Create groups table (for organizing rooms - upstairs, downstairs, bedrooms, etc.)
    op.create_table(
        'groups',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False)
    )

    # Create rooms table (NO hardcoded floor field)
    op.create_table(
        'rooms',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('tado_zone', sa.String(100), nullable=True),
        sa.Column('mel_device', sa.String(100), nullable=True),
        sa.Column('mel_devices', postgresql.JSONB(), nullable=True),  # Array of multiple AC units
        sa.Column('ac_settings', postgresql.JSONB(), nullable=True),  # Room-specific AC overrides
        sa.Column('schedule', postgresql.JSONB(), nullable=True),  # Room schedule config
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False)
    )

    # Create room_groups junction table (many-to-many)
    op.create_table(
        'room_groups',
        sa.Column('room_id', sa.Integer(), sa.ForeignKey('rooms.id', ondelete='CASCADE'), nullable=False),
        sa.Column('group_id', sa.Integer(), sa.ForeignKey('groups.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False),
        sa.PrimaryKeyConstraint('room_id', 'group_id')
    )

    # Create exclusions table
    op.create_table(
        'exclusions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('device_type', sa.String(20), nullable=False),  # 'tado' or 'mel'
        sa.Column('device_name', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('device_type', 'device_name', name='uq_exclusion_device')
    )

    # Create blackout_windows table
    op.create_table(
        'blackout_windows',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.Column('applies_to', postgresql.JSONB(), nullable=False),  # ["tado", "mel"]
        sa.Column('enabled', sa.Boolean(), default=True, nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False)
    )

    # Seed system_settings with data from old-config.json
    op.execute(
        sa.text("""
            INSERT INTO system_settings (id, ac_defaults, pv_config, weather_config, thresholds, targets)
            VALUES (
                1,
                :ac_defaults,
                :pv_config,
                :weather_config,
                :thresholds,
                :targets
            )
        """),
        {
            "ac_defaults": json.dumps({"mode": "heat", "fan": "auto", "vaneH": "auto", "vaneV": "auto", "vanes": True}),
            "pv_config": json.dumps({"boost_threshold_w": 600.0, "boost_delta_c": 0.5}),
            "weather_config": json.dumps({"lat": 51.4184637, "lon": 0.0135339, "provider": "open-meteo"}),
            "thresholds": json.dumps({"ac_min_outdoor_c": 2.0}),
            "targets": json.dumps({"spare": 17.0, "hall": 17.0, "loo": 17.0, "bathroom": 17.0})
        }
    )

    # Seed groups first (Upstairs, Downstairs)
    op.execute(sa.text("INSERT INTO groups (id, name, description) VALUES (1, 'Upstairs', 'Upper floor rooms')"))
    op.execute(sa.text("INSERT INTO groups (id, name, description) VALUES (2, 'Downstairs', 'Ground floor rooms')"))

    # Seed rooms with data from old-config.json + add Bathroom
    rooms_data = [
        # Master bedroom
        {
            "name": "Master",
            "tado_zone": "Main Bed",
            "mel_device": "Master bedroom",
            "mel_devices": None,
            "ac_settings": json.dumps({"fan": 3, "vanes": False}),
            "schedule": json.dumps({"type": "three-period", "day": 17, "eve": 19, "night": 16, "day_start": "07:00", "eve_start": "18:00", "eve_end": "22:00"})
        },
        # Kids bedroom
        {
            "name": "Kids",
            "tado_zone": "Doug",
            "mel_device": "Douglas's bedroom",
            "mel_devices": None,
            "ac_settings": json.dumps({"vanes": False}),
            "schedule": json.dumps({"type": "three-period", "day": 18, "eve": 18, "night": 16, "day_start": "07:00", "eve_start": "18:00", "eve_end": "19:00"})
        },
        # Living Room (renamed from "Downstairs")
        {
            "name": "Living Room",
            "tado_zone": None,
            "mel_device": None,
            "mel_devices": json.dumps(["Living"]),
            "ac_settings": json.dumps({"fan": 4}),
            "schedule": json.dumps({
                "type": "four-period",
                "night": 16,
                "morning": 21,
                "day": 18,
                "evening": 19,
                "morning_start": "07:00",
                "morning_end": "08:00",
                "evening_start": "17:30",
                "evening_end": "22:00",
                "night_ac": {"fan": "auto"},
                "morning_ac": {"fan": 4},
                "day_ac": {"fan": "auto"},
                "evening_ac": {"fan": 4}
            })
        },
        # Office
        {
            "name": "Office",
            "tado_zone": "Office",
            "mel_device": None,
            "mel_devices": None,
            "ac_settings": None,
            "schedule": json.dumps({"type": "workday", "work": 20, "idle": 17, "start": "08:00", "end": "20:00"})
        },
        # Spare Room
        {
            "name": "Spare",
            "tado_zone": "Spare Room",
            "mel_device": None,
            "mel_devices": None,
            "ac_settings": None,
            "schedule": None
        },
        # Hall
        {
            "name": "Hall",
            "tado_zone": "Hall",
            "mel_device": None,
            "mel_devices": None,
            "ac_settings": None,
            "schedule": None
        },
        # Loo
        {
            "name": "Loo",
            "tado_zone": "Loo",
            "mel_device": None,
            "mel_devices": None,
            "ac_settings": None,
            "schedule": None
        },
        # Bathroom (NEW - from Tado API)
        {
            "name": "Bathroom",
            "tado_zone": "Bathroom",
            "mel_device": None,
            "mel_devices": None,
            "ac_settings": None,
            "schedule": None
        }
    ]

    for room in rooms_data:
        op.execute(
            sa.text("""
                INSERT INTO rooms (name, tado_zone, mel_device, mel_devices, ac_settings, schedule)
                VALUES (:name, :tado_zone, :mel_device, :mel_devices, :ac_settings, :schedule)
            """),
            room
        )

    # Seed room_groups mappings (many-to-many)
    # Upstairs: Master, Kids, Office, Spare, Hall, Bathroom
    # Downstairs: Living Room, Loo
    room_group_mappings = [
        # Upstairs rooms (group_id=1)
        ("Master", 1),
        ("Kids", 1),
        ("Office", 1),
        ("Spare", 1),
        ("Hall", 1),
        ("Bathroom", 1),
        # Downstairs rooms (group_id=2)
        ("Living Room", 2),
        ("Loo", 2)
    ]

    for room_name, group_id in room_group_mappings:
        op.execute(
            sa.text("""
                INSERT INTO room_groups (room_id, group_id)
                SELECT r.id, :group_id
                FROM rooms r
                WHERE r.name = :room_name
            """),
            {"room_name": room_name, "group_id": group_id}
        )

    # Seed exclusions
    op.execute(
        sa.text("INSERT INTO exclusions (device_type, device_name) VALUES ('tado', 'Hot Water')")
    )

    # Seed blackout windows
    op.execute(
        sa.text("""
            INSERT INTO blackout_windows (name, start_time, end_time, applies_to, enabled, reason)
            VALUES (
                'Tado Morning Blackout',
                '08:00',
                '09:00',
                :applies_to,
                TRUE,
                NULL
            )
        """),
        {"applies_to": json.dumps(["tado"])}
    )


def downgrade() -> None:
    op.drop_table('blackout_windows')
    op.drop_table('room_groups')  # Drop junction table first (has foreign keys)
    op.drop_table('exclusions')
    op.drop_table('rooms')
    op.drop_table('groups')
    op.drop_table('system_settings')
