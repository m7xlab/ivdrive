"""add v_daily_consumption view

Revision ID: e0299bdbb5d1
Revises: f2da1da148a9
Create Date: 2026-03-12 16:05:02.239923

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e0299bdbb5d1'
down_revision: Union[str, None] = 'f2da1da148a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE OR REPLACE VIEW v_daily_consumption AS
    WITH parked_periods AS (
        SELECT
            user_vehicle_id,
            first_date AS park_start_time,
            LEAD(first_date, 1) OVER (PARTITION BY user_vehicle_id ORDER BY first_date) AS next_park_start_time
        FROM
            vehicle_states
        WHERE
            state = 'PARKED'
    ),
    consumption_cycles AS (
        SELECT
            p.user_vehicle_id,
            p.park_start_time,
            p.next_park_start_time,
            (SELECT cs.battery_pct FROM charging_states cs WHERE cs.user_vehicle_id = p.user_vehicle_id AND cs.first_date <= p.park_start_time ORDER BY cs.first_date DESC LIMIT 1) AS start_soc,
            (SELECT cs.battery_pct FROM charging_states cs WHERE cs.user_vehicle_id = p.user_vehicle_id AND cs.first_date <= p.next_park_start_time ORDER BY cs.first_date DESC LIMIT 1) AS end_soc
        FROM
            parked_periods p
        WHERE
            p.next_park_start_time IS NOT NULL
    ),
    consumption_per_cycle AS (
        SELECT
            c.user_vehicle_id,
            c.park_start_time,
            uv.battery_capacity_kwh,
            (c.start_soc - c.end_soc) AS soc_delta
        FROM
            consumption_cycles c
        JOIN
            user_vehicles uv ON c.user_vehicle_id = uv.id
        WHERE
            c.start_soc IS NOT NULL
            AND c.end_soc IS NOT NULL
            AND (c.start_soc - c.end_soc) > 0
            AND uv.battery_capacity_kwh IS NOT NULL
    )
    SELECT
        user_vehicle_id,
        DATE_TRUNC('day', park_start_time AT TIME ZONE 'UTC')::timestamptz AS consumption_day,
        SUM((soc_delta / 100.0) * battery_capacity_kwh) AS total_kwh_consumed
    FROM
        consumption_per_cycle
    GROUP BY
        user_vehicle_id,
        consumption_day;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_daily_consumption;")
