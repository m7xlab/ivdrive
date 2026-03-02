"""add_wltp_range_km_to_user_vehicles

Revision ID: 92328e409763
Revises: b2c3d4e5f6a7
Create Date: 2026-03-02 22:15:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '92328e409763'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Adding wltp_range_km column to user_vehicles table
    op.add_column('user_vehicles', sa.Column('wltp_range_km', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('user_vehicles', 'wltp_range_km')
