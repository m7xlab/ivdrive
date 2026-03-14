"""improve_phantom_drain_logic

Revision ID: 51eeee5e29ed
Revises: ba81d9f38011
Create Date: 2026-03-14 09:10:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '51eeee5e29ed'
down_revision: Union[str, None] = 'ba81d9f38011'

def upgrade() -> None:
    # Update Phantom Drain view with strict "Deep Sleep" conditions
    op.execute("""
    CREATE OR REPLACE VIEW v_phantom_drain_stats AS
    WITH parked_periods AS (
        -- Only count periods where the car is fully closed and locked
        SELECT 
            user_vehicle_id, 
            first_date as parked_start, 
            last_date as parked_end
        FROM vehicle_states
        WHERE state = 'PARKED' 
          AND last_date > first_date
          AND doors_open = 'CLOSED'
          AND windows_open = 'CLOSED'
          AND (lights_on = 'OFF' OR lights_on IS NULL)
          AND (trunk_open = false OR trunk_open IS NULL)
          AND (bonnet_open = false OR bonnet_open IS NULL)
          -- Minimum 2 hours to get a meaningful SoC change
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
        -- Find SoC at the very beginning of this parked state
        JOIN LATERAL (
            SELECT battery_pct FROM charging_states 
            WHERE user_vehicle_id = p.user_vehicle_id 
              AND first_date >= p.parked_start - interval '5 minutes'
              AND first_date <= p.parked_start + interval '30 minutes'
            ORDER BY first_date ASC LIMIT 1
        ) cs_start ON true
        -- Find SoC at the very end of this parked state
        JOIN LATERAL (
            SELECT battery_pct FROM charging_states 
            WHERE user_vehicle_id = p.user_vehicle_id 
              AND last_date >= p.parked_end - interval '30 minutes'
              AND last_date <= p.parked_end + interval '5 minutes'
            ORDER BY last_date DESC LIMIT 1
        ) cs_end ON true
        WHERE (p.parked_end - p.parked_start) > interval '1 hour'
    )
    SELECT 
        user_vehicle_id,
        -- Calculate daily loss: (Drop / Hours) * 24
        -- If start_soc == end_soc, loss is 0. If car charged, we ignore it.
        AVG(CASE WHEN start_soc >= end_soc THEN (start_soc - end_soc) / NULLIF(duration_hours, 0) * 24.0 ELSE 0 END) as avg_drain_pct_per_day,
        SUM(CASE WHEN start_soc >= end_soc THEN start_soc - end_soc ELSE 0 END) as total_soc_lost,
        COUNT(*) as sampled_periods
    FROM soc_changes
    GROUP BY user_vehicle_id;
    """)

def downgrade() -> None:
    # We don't drop the view, just leave it as is or restore previous simpler logic if needed
    pass
