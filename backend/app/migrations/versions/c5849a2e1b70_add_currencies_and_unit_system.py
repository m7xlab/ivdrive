"""add currencies table and user unit_system

Revision ID: c5849a2e1b70
Revises: b473841e9399
Create Date: 2026-09-08 19:30:00.000000

ECB FX catalog (CurrencyConverter) plus metric/imperial preference.
Costs and distances stay stored as EUR / km / °C.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c5849a2e1b70"
down_revision: Union[str, None] = "b473841e9399"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "currencies",
        sa.Column("code", sa.String(length=3), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("symbol", sa.String(length=8), nullable=False),
        sa.Column("rate_per_eur", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=32), server_default="ECB", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("code"),
    )
    op.add_column(
        "users",
        sa.Column("unit_system", sa.String(length=16), server_default="metric", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "unit_system")
    op.drop_table("currencies")
