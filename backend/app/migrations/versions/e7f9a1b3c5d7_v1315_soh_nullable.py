"""v1.3.15: battery_health_analytics.soh_pct may be NULL (a method with no result is not 0 %)

Revision ID: e7f9a1b3c5d7
Revises: d6e8f0a2b4c6
Create Date: 2026-11-14
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e7f9a1b3c5d7"
down_revision: Union[str, None] = "d6e8f0a2b4c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE battery_health_analytics ALTER COLUMN soh_pct DROP NOT NULL;")


def downgrade() -> None:
    op.execute("UPDATE battery_health_analytics SET soh_pct = 0 WHERE soh_pct IS NULL;")
    op.execute("ALTER TABLE battery_health_analytics ALTER COLUMN soh_pct SET NOT NULL;")
