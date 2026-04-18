"""add temperature_celsius to drive_consumptions

Revision ID: 33abc4d5e6f9
Revises: 32abc4d5e6f8
Create Date: 2026-04-18 16:58:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '33abc4d5e6f9'
down_revision: Union[str, None] = '32abc4d5e6f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('drive_consumptions', sa.Column('temperature_celsius', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('drive_consumptions', 'temperature_celsius')
