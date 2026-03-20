"""
Add missing Skoda API endpoints to collector_raw_responses table

Revision ID: b2c8d9e7f6a5
Revises: 3c8e7408b6f0
Create Date: 2026-03-16 20:35:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = 'b2c8d9e7f6a5'
down_revision: Union[str, None] = '3c8e7408b6f0' 
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns for missing API endpoints
    op.add_column('collector_raw_responses',
        sa.Column('raw_garage_vehicle', sa.JSON().with_variant(sa.dialects.postgresql.JSONB, 'postgresql'), nullable=True)
    )
    op.add_column('collector_raw_responses',
        sa.Column('raw_vehicle_renders', sa.JSON().with_variant(sa.dialects.postgresql.JSONB, 'postgresql'), nullable=True)
    )


def downgrade() -> None:
    # Remove the columns
    op.drop_column('collector_raw_responses', 'raw_garage_vehicle')
    op.drop_column('collector_raw_responses', 'raw_vehicle_renders')