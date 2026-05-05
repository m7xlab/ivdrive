"""add index on vehicle_positions for elevation lookups

Revision ID: d1e2f3a4bb5c
Revises: f493b86626a
Create Date: 2026-04-30 16:50:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4bb5c'
down_revision: str = 'a1b2c3d4e5f8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Composite index for _get_nearest_elevation spatial lookup
    # Query: ORDER BY ((latitude-?)^2+(longitude-?)^2) WHERE user_vehicle_id=? AND elevation_m IS NOT NULL
    op.create_index(
        'ix_vp_vehicle_elevation_lat_lon',
        'vehicle_positions',
        ['user_vehicle_id', 'elevation_m', 'latitude', 'longitude']
    )


def downgrade() -> None:
    op.drop_index('ix_vp_vehicle_elevation_lat_lon', table_name='vehicle_positions')