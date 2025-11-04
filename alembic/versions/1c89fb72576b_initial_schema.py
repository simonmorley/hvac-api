"""Initial schema

Revision ID: 1c89fb72576b
Revises:
Create Date: 2025-11-03 22:04:57.668606

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = '1c89fb72576b'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create secrets table
    op.create_table(
        'secrets',
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('key')
    )

    # Create system_state table
    op.create_table(
        'system_state',
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('key')
    )

    # Create device_commands table
    op.create_table(
        'device_commands',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('device_name', sa.String(), nullable=False),
        sa.Column('device_type', sa.String(), nullable=False),
        sa.Column('commanded_action', sa.String(), nullable=False),
        sa.Column('commanded_setpoint', sa.Float(), nullable=True),
        sa.Column('commanded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('success', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('device_name', 'device_type', name='uq_device_command')
    )

    # Create device_overrides table
    op.create_table(
        'device_overrides',
        sa.Column('device_name', sa.String(), nullable=False),
        sa.Column('device_type', sa.String(), nullable=False),
        sa.Column('override_detected_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('device_name', 'device_type')
    )

    # Create device_cooldowns table
    op.create_table(
        'device_cooldowns',
        sa.Column('device_name', sa.String(), nullable=False),
        sa.Column('last_turned_on_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_turned_off_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('device_name')
    )

    # Create config_store table
    op.create_table(
        'config_store',
        sa.Column('id', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('config_json', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('id = 1', name='single_row_check')
    )

    # Create logs table
    op.create_table(
        'logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('level', sa.String(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('extra_data', JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create index on logs.created_at
    op.create_index('idx_logs_created_at', 'logs', ['created_at'], unique=False, postgresql_using='btree')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_logs_created_at', table_name='logs')
    op.drop_table('logs')
    op.drop_table('config_store')
    op.drop_table('device_cooldowns')
    op.drop_table('device_overrides')
    op.drop_table('device_commands')
    op.drop_table('system_state')
    op.drop_table('secrets')
