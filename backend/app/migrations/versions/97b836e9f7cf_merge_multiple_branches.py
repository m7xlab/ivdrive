"""Merge multiple branches

Revision ID: 97b836e9f7cf
Revises: 32abc4d5e6f8, 35abc4d5e6f1
Create Date: 2026-04-19 08:32:40.604083
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '97b836e9f7cf'
down_revision: Union[str, None] = ('32abc4d5e6f8', '35abc4d5e6f1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
