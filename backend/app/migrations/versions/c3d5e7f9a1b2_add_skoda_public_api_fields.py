"""add official Skoda public API dual-stack fields

Revision ID: c3d5e7f9a1b2
Revises: b7e1a4c9d2f3
Create Date: 2026-10-19 18:30:00.000000

users.skoda_public_api_key_encrypted + expiry; user_vehicles.telemetry_source.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c3d5e7f9a1b2"
down_revision: Union[str, None] = "b7e1a4c9d2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("skoda_public_api_key_encrypted", sa.Text(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("skoda_public_key_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_vehicles",
        sa.Column(
            "telemetry_source",
            sa.String(length=16),
            server_default="auto",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("user_vehicles", "telemetry_source")
    op.drop_column("users", "skoda_public_key_expires_at")
    op.drop_column("users", "skoda_public_api_key_encrypted")
