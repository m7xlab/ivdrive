"""allow_idle_connected_phantom_drain

Revision ID: a5f9ddf2d0f4
Revises: e2c970bfbee9
Create Date: 2026-03-14 09:40:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a5f9ddf2d0f4'
down_revision: Union[str, None] = 'e2c970bfbee9'

def upgrade() -> None:
    op.execute("""
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
        -- EXCLUDE only active charging (where power > 0)
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
    """)

def downgrade() -> None:
    pass
