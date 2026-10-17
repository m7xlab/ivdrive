"""add users.abrp_api_key_encrypted

Revision ID: b7e1a4c9d2f3
Revises: a9c4e2b7d1f8
Create Date: 2026-10-17 14:00:00.000000

Per-user ABRP Telemetry API key (free, generated in the ABRP account).
Per-vehicle tokens live in abrp_connections.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b7e1a4c9d2f3"
down_revision: Union[str, None] = "a9c4e2b7d1f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("abrp_api_key_encrypted", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "abrp_api_key_encrypted")
