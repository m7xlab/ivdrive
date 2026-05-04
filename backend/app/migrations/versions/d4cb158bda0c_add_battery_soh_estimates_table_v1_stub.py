"""add_battery_soh_estimates_table_v1_stub

Revision ID: d4cb158bda0c
Revises: 4c5c9e5b4a60
Create Date: 2026-04-30 15:00:00.000000

Stub migration to bridge battery_soh chain.
Production recorded this revision but no migration file existed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd4cb158bda0c'
down_revision: Union[str, None] = '4c5c9e5b4a60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
