"""fix_vehicle_state_durations_view_and_time_budget

Filter YES/NO states from v_vehicle_state_durations:
YES/NO are door lock states from Skoda API (overall.locked), NOT movement states.
They should never have been included in time-budget calculations.

Revision ID: f493b86626b
Revises: f493b86626a
Create Date: 2026-05-24 21:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f493b86626b'
down_revision: Union[str, Sequence[str], None] = 'f493b86626a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Fix view: only include real movement states, cap intervals at 24h
    op.execute("""
    CREATE OR REPLACE VIEW v_vehicle_state_durations AS
    WITH state_and_next_ts AS (
        SELECT
            user_vehicle_id,
            state,
            first_date,
            LEAD(first_date, 1) OVER (PARTITION BY user_vehicle_id ORDER BY first_date) AS next_state_start
        FROM
            public.vehicle_states
        WHERE
            state IN ('PARKED', 'DRIVING', 'IGNITION_ON', 'OFFLINE')
    )
    SELECT
        user_vehicle_id,
        state,
        first_date,
        next_state_start AS state_end_date,
        EXTRACT(EPOCH FROM (next_state_start - first_date)) AS duration_seconds
    FROM
        state_and_next_ts
    WHERE
        next_state_start IS NOT NULL;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_vehicle_state_durations;")
    op.execute("""
    CREATE OR REPLACE VIEW v_vehicle_state_durations AS
    WITH state_and_next_ts AS (
        SELECT
            user_vehicle_id,
            state,
            first_date,
            LEAD(first_date, 1) OVER (PARTITION BY user_vehicle_id ORDER BY first_date) AS next_state_start
        FROM
            public.vehicle_states
    )
    SELECT
        user_vehicle_id,
        state,
        first_date,
        next_state_start AS state_end_date,
        EXTRACT(EPOCH FROM (next_state_start - first_date)) AS duration_seconds
    FROM
        state_and_next_ts
    WHERE
        next_state_start IS NOT NULL;
    """)
