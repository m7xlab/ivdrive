"""Add MyŠkoda Login credential columns on users.

Revision ID: a9f3c2d1e8b7
Revises: c3d5e7f9a1b2
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9f3c2d1e8b7"
down_revision: Union[str, None] = "c3d5e7f9a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("skoda_login_email", sa.String(length=320), nullable=True))
    op.add_column("users", sa.Column("skoda_login_password_encrypted", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("skoda_login_access_encrypted", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("skoda_login_refresh_encrypted", sa.Text(), nullable=True))
    # Source rename: legacy → login
    op.execute("UPDATE user_vehicles SET telemetry_source = 'login' WHERE telemetry_source = 'legacy'")


def downgrade() -> None:
    op.execute("UPDATE user_vehicles SET telemetry_source = 'legacy' WHERE telemetry_source = 'login'")
    op.drop_column("users", "skoda_login_refresh_encrypted")
    op.drop_column("users", "skoda_login_access_encrypted")
    op.drop_column("users", "skoda_login_password_encrypted")
    op.drop_column("users", "skoda_login_email")
