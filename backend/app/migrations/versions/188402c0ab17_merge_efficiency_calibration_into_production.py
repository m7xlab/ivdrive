"""merge efficiency calibration into production

Revision ID: 188402c0ab17
Revises: 469e9a141062, a3b7c2d1e9f5
Create Date: 2026-04-25 16:46:30.448981
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '188402c0ab17'
down_revision: Union[str, None] = ('469e9a141062', 'a3b7c2d1e9f5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
