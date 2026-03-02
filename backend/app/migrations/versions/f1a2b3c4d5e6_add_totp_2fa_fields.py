"""add_totp_2fa_fields

Revision ID: f1a2b3c4d5e6
Revises: de8349efe7f2
Create Date: 2026-03-02 17:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "de8349efe7f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_secret_enc", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "is_totp_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_totp_enabled")
    op.drop_column("users", "totp_secret_enc")
