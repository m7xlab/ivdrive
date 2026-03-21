"""fix charging sessions analytics view

Revision ID: aab0f10c9cd
Revises: f2da1da148a9
Create Date: 2026-03-21 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aab0f10c9cd'
down_revision: Union[str, None] = '43e2b5ce5e97'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the old view
    op.execute("DROP VIEW IF EXISTS v_charging_sessions_analytics;")
    
    # Create new view using actual charging session data
    op.execute("""
    CREATE OR REPLACE VIEW v_charging_sessions_analytics AS
    SELECT 
        user_vehicle_id,
        ROW_NUMBER() OVER (PARTITION BY user_vehicle_id ORDER BY session_start) AS session_group,
        session_start,
        session_end,
        EXTRACT(EPOCH FROM (session_end - session_start)) AS duration_seconds,
        energy_kwh
    FROM charging_sessions
    WHERE session_end IS NOT NULL AND session_start IS NOT NULL AND session_end >= session_start;
    """)


def downgrade() -> None:
    # Revert to the original view based on charging_states
    op.execute("DROP VIEW IF EXISTS v_charging_sessions_analytics;")
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