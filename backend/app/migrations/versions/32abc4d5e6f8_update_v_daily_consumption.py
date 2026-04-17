"""update v_daily_consumption for live stats

Revision ID: 32abc4d5e6f8
Revises: 31abc4d5e6f7
Create Date: 2026-04-17 21:16:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '32abc4d5e6f8'
down_revision: Union[str, None] = '31abc4d5e6f7'
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
            s_soc.battery_pct AS start_soc,
            e_soc.battery_pct AS end_soc
        FROM parked_periods p
        LEFT JOIN LATERAL (
            SELECT battery_pct 
            FROM charging_states cs 
            WHERE cs.user_vehicle_id = p.user_vehicle_id AND cs.first_date <= p.park_start_time 
            ORDER BY cs.first_date DESC LIMIT 1
        ) s_soc ON TRUE
        LEFT JOIN LATERAL (
            SELECT battery_pct 
            FROM charging_states cs 
            WHERE cs.user_vehicle_id = p.user_vehicle_id AND cs.first_date <= COALESCE(p.next_park_start_time, NOW()) 
            ORDER BY cs.first_date DESC LIMIT 1
        ) e_soc ON TRUE
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
