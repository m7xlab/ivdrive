"""add analytics views

Revision ID: f2da1da148a9
Revises: 692fab0b6318
Create Date: 2026-03-11 21:06:30.506931

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2da1da148a9'
down_revision: Union[str, None] = '692fab0b6318'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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

    op.execute("""
    CREATE OR REPLACE VIEW v_charging_sessions_analytics AS
    WITH pts AS (
        SELECT
            user_vehicle_id,
            first_date AS ts,
            LAG(first_date) OVER (PARTITION BY user_vehicle_id ORDER BY first_date) AS prev_ts
        FROM
            charging_states
        WHERE
            state = 'CHARGING'
    ),
    session_ids AS (
        SELECT
            user_vehicle_id,
            ts,
            SUM(CASE WHEN prev_ts IS NULL OR EXTRACT(EPOCH FROM (ts - prev_ts)) > 1800 THEN 1 ELSE 0 END) OVER (PARTITION BY user_vehicle_id ORDER BY ts) AS session_group
        FROM
            pts
    ),
    sessions AS (
        SELECT
            user_vehicle_id,
            session_group,
            MIN(ts) AS session_start,
            MAX(ts) AS session_end
        FROM
            session_ids
        GROUP BY
            user_vehicle_id,
            session_group
    )
    SELECT
        user_vehicle_id,
        session_group,
        session_start,
        session_end,
        EXTRACT(EPOCH FROM (session_end - session_start)) AS duration_seconds
    FROM
        sessions;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_vehicle_state_durations;")
    op.execute("DROP VIEW IF EXISTS v_charging_sessions_analytics;")

