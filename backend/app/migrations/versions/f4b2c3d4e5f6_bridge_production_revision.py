"""Bridge migration: absorb unknown production revision f4b2c3d4e5f6.

The production server was on a different commit (release branch) when its DB
was restored to dev. That branch had alembic head = 'f4b2c3d4e5f6', a revision
that does not exist in the development chain. Without this bridge, running
`alembic upgrade head` against the restored production DB fails with
"Can't locate revision identified by 'f4b2c3d4e5f6'".

This no-op migration registers 'f4b2c3d4e5f6' as a known revision pointing to
the current development head ('ea873b9fe6a2'). The schema state at
'f4b2c3d4e5f6' is therefore treated as equivalent to 'ea873b9fe6a2', which
matches what the restored production DB actually contains (all data + the
AI/vector tables created during this deployment pass).

Revision ID: f4b2c3d4e5f6
Revises: ea873b9fe6a2
Create Date: 2026-06-08 09:30:00.000000
"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "f4b2c3d4e5f6"
down_revision: Union[str, None] = "ea873b9fe6a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
