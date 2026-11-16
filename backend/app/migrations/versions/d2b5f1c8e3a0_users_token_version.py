"""v1.4.0: users.token_version — sessions can be revoked

Access and refresh tokens carry the user's token_version; a token whose version is behind the
row is refused. Password change, password reset and "log out everywhere" bump it. Existing
tokens carry no version and are refused once this is deployed: every user logs in once.

Revision ID: d2b5f1c8e3a0
Revises: c1a4e0b7d2f9
Create Date: 2026-11-15
"""
from typing import Sequence, Union

from alembic import op

revision: str = "d2b5f1c8e3a0"
down_revision: Union[str, None] = "c1a4e0b7d2f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 1;")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS token_version;")
