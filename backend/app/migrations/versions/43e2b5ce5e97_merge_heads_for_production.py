"""merge heads for production

Revision ID: 43e2b5ce5e97
Revises: a59b21a4819b, b2c8d9e7f6a5
Create Date: 2026-03-16 20:32:22.143817
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '43e2b5ce5e97'
down_revision: Union[str, None] = ('a59b21a4819b', 'b2c8d9e7f6a5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
