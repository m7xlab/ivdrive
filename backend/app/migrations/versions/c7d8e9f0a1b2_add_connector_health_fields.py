"""Add connector health fields (last_success_at, consecutive_failures, last_error_text)."""

from alembic import op
import sqlalchemy as sa


revision = "c7d8e9f0a1b2"
down_revision = "b7e4f1a9c2d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "connector_sessions",
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "connector_sessions",
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "connector_sessions",
        sa.Column("last_error_text", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("connector_sessions", "last_error_text")
    op.drop_column("connector_sessions", "consecutive_failures")
    op.drop_column("connector_sessions", "last_success_at")
