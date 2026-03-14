"""add_geocoding_cache

Revision ID: 3c8e7408b6f0
Revises: a5f9ddf2d0f4
Create Date: 2026-03-14 10:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '3c8e7408b6f0'
down_revision: Union[str, None] = 'a5f9ddf2d0f4'

def upgrade() -> None:
    op.create_table(
        'geocoded_locations',
        sa.Column('latitude', sa.Numeric(precision=9, scale=6), primary_key=True),
        sa.Column('longitude', sa.Numeric(precision=9, scale=6), primary_key=True),
        sa.Column('display_name', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now())
    )
    # Add an index for faster lookups
    op.create_index('ix_geocoded_coords', 'geocoded_locations', ['latitude', 'longitude'])

def downgrade() -> None:
    op.drop_index('ix_geocoded_coords', table_name='geocoded_locations')
    op.drop_table('geocoded_locations')
