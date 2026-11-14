"""v1.3.14: users.show_commands (beta command buttons are a per-account setting)

Revision ID: d6e8f0a2b4c6
Revises: c5d7e9f1a3b4
Create Date: 2026-11-14
"""
from typing import Sequence, Union

from alembic import op

revision: str = "d6e8f0a2b4c6"
down_revision: Union[str, None] = "c5d7e9f1a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS show_commands BOOLEAN NOT NULL DEFAULT FALSE;")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS show_commands;")
