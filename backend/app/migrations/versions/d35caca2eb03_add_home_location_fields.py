"""Add home_lat, home_lon, home_tz to user_vehicles

Revision ID: d35caca2eb03
Revises: 585b1cc2eb03
Create Date: 2026-05-08 22:45:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d35caca2eb03"
down_revision: Union[str, None] = "585b1cc2eb03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_vehicles", sa.Column("home_lat", sa.Float(), nullable=True))
    op.add_column("user_vehicles", sa.Column("home_lon", sa.Float(), nullable=True))
    op.add_column("user_vehicles", sa.Column("home_tz", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("user_vehicles", "home_tz")
    op.drop_column("user_vehicles", "home_lon")
    op.drop_column("user_vehicles", "home_lat")
