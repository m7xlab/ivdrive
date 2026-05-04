"""add composite index on vehicle_positions for elevation spatial queries

Revision ID: a1b2c3d4e5f8
Revises: f493b86626a
Create Date: 2026-04-30 20:45:00.000000

Composite index on (user_vehicle_id, elevation_m, latitude, longitude) covers
the _fetch_elevation() spatial ORDER BY query pattern:
  ORDER BY elevation_m, latitude, longitude
  WHERE user_vehicle_id = ?
Without this index the query does a full table scan on vehicle_positions.

TaskTrove: c2d3e4f5-a6b7-4c8d-9e0f-1a2b3c4d5e6f
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f8'
down_revision: Union[str, None] = 'f493b86626a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_vp_vehicle_elevation_lat_lon',
        'vehicle_positions',
        ['user_vehicle_id', 'elevation_m', 'latitude', 'longitude'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        'ix_vp_vehicle_elevation_lat_lon',
        table_name='vehicle_positions',
    )
