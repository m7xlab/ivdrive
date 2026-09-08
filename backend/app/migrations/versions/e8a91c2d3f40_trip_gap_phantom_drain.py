"""trip-gap phantom drain view

Revision ID: e8a91c2d3f40
Revises: d6e7f8a9b0c1
Create Date: 2026-09-07 21:30:00.000000

Replace v_phantom_drain_stats. The old definition joined vehicle_states PARKED
rows to charging_states SoC samples — those samples are not persisted while
parked, so the view was empty or biased. New definition matches
compute_vampire_drain(): consecutive trip gaps, still odometer, no overlapping
charging session, hour-weighted including 0% integer-SoC nights.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e8a91c2d3f40"
down_revision: Union[str, None] = "d6e7f8a9b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_VIEW = """
CREATE OR REPLACE VIEW v_phantom_drain_stats AS
WITH ordered AS (
    SELECT
        user_vehicle_id,
        start_date,
        end_date,
        start_soc,
        end_soc,
        start_odometer,
        end_odometer,
        LEAD(start_date) OVER (PARTITION BY user_vehicle_id ORDER BY start_date) AS next_start,
        LEAD(start_soc) OVER (PARTITION BY user_vehicle_id ORDER BY start_date) AS next_start_soc,
        LEAD(start_odometer) OVER (PARTITION BY user_vehicle_id ORDER BY start_date) AS next_start_odo
    FROM trips
    WHERE start_soc IS NOT NULL
      AND end_soc IS NOT NULL
      AND end_date IS NOT NULL
),
parked AS (
    SELECT
        o.user_vehicle_id,
        EXTRACT(EPOCH FROM (o.next_start - o.end_date)) / 3600.0 AS parked_h,
        (o.end_soc - o.next_start_soc)::double precision AS dsoc
    FROM ordered o
    WHERE o.next_start IS NOT NULL
      AND EXTRACT(EPOCH FROM (o.next_start - o.end_date)) / 3600.0 > 1.0
      AND EXTRACT(EPOCH FROM (o.next_start - o.end_date)) / 3600.0 < 72.0
      AND o.end_odometer IS NOT NULL
      AND o.next_start_odo IS NOT NULL
      AND ABS(o.next_start_odo - o.end_odometer) <= 1.0
      AND (o.end_soc - o.next_start_soc) >= -1
      AND (o.end_soc - o.next_start_soc) < 15
      AND NOT EXISTS (
          SELECT 1 FROM charging_sessions cs
          WHERE cs.user_vehicle_id = o.user_vehicle_id
            AND cs.session_start IS NOT NULL
            AND (
                (cs.session_end IS NULL
                 AND cs.session_start < o.next_start
                 AND EXTRACT(EPOCH FROM (o.end_date - cs.session_start)) / 3600.0 < 72)
                OR
                (cs.session_end IS NOT NULL
                 AND cs.session_start < o.next_start
                 AND cs.session_end > o.end_date)
            )
      )
)
SELECT
    user_vehicle_id,
    GREATEST(0, SUM(dsoc) / NULLIF(SUM(parked_h), 0) * 24.0) AS avg_drain_pct_per_day,
    SUM(dsoc) AS total_soc_lost,
    COUNT(*)::bigint AS sampled_periods,
    ROUND(SUM(parked_h)::numeric, 1) AS parked_hours,
    COUNT(*) FILTER (WHERE dsoc = 0)::bigint AS zero_drop_count
FROM parked
GROUP BY user_vehicle_id;
"""

OLD_VIEW = """
CREATE OR REPLACE VIEW v_phantom_drain_stats AS
WITH parked_periods AS (
    SELECT
        user_vehicle_id,
        first_date as parked_start,
        last_date as parked_end
    FROM vehicle_states
    WHERE state = 'PARKED'
      AND last_date > first_date
      AND doors_open = 'CLOSED'
      AND windows_open = 'CLOSED'
      AND (last_date - first_date) >= interval '2 hours'
),
soc_changes AS (
    SELECT
        p.user_vehicle_id,
        p.parked_start,
        p.parked_end,
        cs_start.battery_pct as start_soc,
        cs_end.battery_pct as end_soc,
        EXTRACT(EPOCH FROM (p.parked_end - p.parked_start)) / 3600.0 as duration_hours
    FROM parked_periods p
    JOIN LATERAL (
        SELECT battery_pct FROM charging_states
        WHERE user_vehicle_id = p.user_vehicle_id
          AND first_date >= p.parked_start - interval '10 minutes'
          AND first_date <= p.parked_start + interval '60 minutes'
        ORDER BY first_date ASC LIMIT 1
    ) cs_start ON true
    JOIN LATERAL (
        SELECT battery_pct FROM charging_states
        WHERE user_vehicle_id = p.user_vehicle_id
          AND last_date >= p.parked_end - interval '60 minutes'
          AND last_date <= p.parked_end + interval '10 minutes'
        ORDER BY last_date DESC LIMIT 1
    ) cs_end ON true
    WHERE cs_start.battery_pct >= cs_end.battery_pct
      AND NOT EXISTS (
          SELECT 1 FROM charging_states
          WHERE user_vehicle_id = p.user_vehicle_id
            AND first_date > p.parked_start
            AND last_date < p.parked_end
            AND (state = 'CHARGING' OR charge_power_kw > 0)
      )
)
SELECT
    user_vehicle_id,
    AVG((start_soc - end_soc) / NULLIF(duration_hours, 0) * 24.0) as avg_drain_pct_per_day,
    SUM(start_soc - end_soc) as total_soc_lost,
    COUNT(*) as sampled_periods
FROM soc_changes
GROUP BY user_vehicle_id;
"""


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_phantom_drain_stats")
    op.execute(NEW_VIEW)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_phantom_drain_stats")
    op.execute(OLD_VIEW)
