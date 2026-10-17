"""add abrp_connections table

Revision ID: a9c4e2b7d1f8
Revises: c5849a2e1b70
Create Date: 2026-10-17 12:00:00.000000

Per-vehicle ABRP (A Better Route Planner) telemetry integration settings.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a9c4e2b7d1f8"
down_revision: Union[str, None] = "c5849a2e1b70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "abrp_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("token_encrypted", sa.Text(), nullable=True),
        sa.Column("car_model_typecode", sa.String(length=100), nullable=True),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_text", sa.String(length=255), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column("backoff_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_charge_pct", sa.Float(), nullable=True),
        sa.Column("next_charge_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_vehicle_id"], ["user_vehicles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_abrp_connections_user_vehicle_id",
        "abrp_connections",
        ["user_vehicle_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_abrp_connections_user_vehicle_id", table_name="abrp_connections")
    op.drop_table("abrp_connections")
