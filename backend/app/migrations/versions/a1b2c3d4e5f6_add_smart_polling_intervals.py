"""add smart polling intervals

Revision ID: a1b2c3d4e5f6
Revises: ceb70f201aef
Create Date: 2026-03-01 19:55:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'ceb70f201aef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('user_vehicles', sa.Column('active_interval_seconds', sa.Integer(), nullable=False, server_default='300'))
    op.add_column('user_vehicles', sa.Column('parked_interval_seconds', sa.Integer(), nullable=False, server_default='1800'))
    # Migrate: active inherits old value, parked = min(old*6, 1800)
    op.execute("""
        UPDATE user_vehicles
        SET active_interval_seconds = collection_interval_seconds,
            parked_interval_seconds = LEAST(collection_interval_seconds * 6, 1800)
    """)
    op.drop_column('user_vehicles', 'collection_interval_seconds')


def downgrade() -> None:
    op.add_column('user_vehicles', sa.Column('collection_interval_seconds', sa.Integer(), nullable=False, server_default='300'))
    op.execute("UPDATE user_vehicles SET collection_interval_seconds = active_interval_seconds")
    op.drop_column('user_vehicles', 'parked_interval_seconds')
    op.drop_column('user_vehicles', 'active_interval_seconds')
