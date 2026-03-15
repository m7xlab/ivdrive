"""
Add missing Skoda API endpoints to collector_raw_responses table

Revision ID: f1e8a9b4c7d9
Revises: e3f4a5b6c7d8
Create Date: 2026-03-15 19:15:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = 'f1e8a9b4c7d9'
down_revision: Union[str, None] = 'e3f4a5b6c7d8' 
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