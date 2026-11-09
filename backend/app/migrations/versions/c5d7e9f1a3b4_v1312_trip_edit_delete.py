"""v1.3.12: manual trip edit / delete (#209)

Revision ID: c5d7e9f1a3b4
Revises: b4c6d8e0f2a3
Create Date: 2026-11-10

trips.manually_edited / trips.edit_history: a user corrected the trip; automatic sync never rewrites it.
deleted_trips: odometer span of a deleted trip so the Skoda sync does not recreate it.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c5d7e9f1a3b4"
down_revision: Union[str, None] = "b4c6d8e0f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE trips ADD COLUMN IF NOT EXISTS manually_edited BOOLEAN NOT NULL DEFAULT FALSE;")
    op.execute("ALTER TABLE trips ADD COLUMN IF NOT EXISTS edit_history JSONB;")
    op.execute("""
        CREATE TABLE IF NOT EXISTS deleted_trips (
            id BIGSERIAL PRIMARY KEY,
            user_vehicle_id UUID NOT NULL REFERENCES user_vehicles(id) ON DELETE CASCADE,
            start_date TIMESTAMPTZ NOT NULL,
            end_date TIMESTAMPTZ,
            start_odometer DOUBLE PRECISION,
            end_odometer DOUBLE PRECISION,
            deleted_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_deleted_trips_user_vehicle_id ON deleted_trips (user_vehicle_id);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS deleted_trips;")
    op.execute("ALTER TABLE trips DROP COLUMN IF EXISTS edit_history;")
    op.execute("ALTER TABLE trips DROP COLUMN IF EXISTS manually_edited;")
