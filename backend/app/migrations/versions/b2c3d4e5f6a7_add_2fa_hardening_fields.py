"""add_2fa_hardening_fields

Phase 4 — 2FA Hardening:
  * last_totp_at (Integer, nullable) — tracks the last consumed TOTP 30-s
    window counter to prevent replay attacks.
  * recovery_codes (JSON, nullable) — stores SHA-256-hashed single-use
    recovery codes for TOTP-device-loss scenarios.

Revision ID: b2c3d4e5f6a7
Revises: f1a2b3c4d5e6
Create Date: 2026-03-02 19:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("last_totp_at", sa.Integer(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("recovery_codes", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "recovery_codes")
    op.drop_column("users", "last_totp_at")
