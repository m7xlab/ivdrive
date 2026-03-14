"""add_advanced_analytics_views

Revision ID: ba81d9f38011
Revises: e0299bdbb5d2
Create Date: 2026-03-14 08:35:56.115322
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ba81d9f38011'
down_revision: Union[str, None] = 'e0299bdbb5d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # View for Trip Type and Weather Impact Analytics
    op.execute("""
    CREATE OR REPLACE VIEW v_advanced_trip_stats AS
    SELECT 
        user_vehicle_id,
        COUNT(*) as total_trips,
        COUNT(*) FILTER (WHERE distance_km < 15) as short_trips_count,
        COUNT(*) FILTER (WHERE distance_km >= 15 AND distance_km < 80) as medium_trips_count,
        COUNT(*) FILTER (WHERE distance_km >= 80) as long_trips_count,
        AVG(kwh_consumed / NULLIF(distance_km, 0) * 100) FILTER (WHERE avg_temp_celsius < 7) as avg_eff_cold,
        AVG(kwh_consumed / NULLIF(distance_km, 0) * 100) FILTER (WHERE avg_temp_celsius > 12) as avg_eff_warm,
        AVG(kwh_consumed / NULLIF(distance_km, 0) * 100) as avg_eff_overall
    FROM trips
    WHERE distance_km > 0 AND kwh_consumed > 0
    GROUP BY user_vehicle_id;
    """)

    # View for Phantom Drain (SoC loss per hour while PARKED)
    op.execute("""
    CREATE OR REPLACE VIEW v_phantom_drain_stats AS
    WITH parked_periods AS (
        SELECT user_vehicle_id, first_date as parked_start, last_date as parked_end
        FROM vehicle_states
        WHERE state = 'PARKED' AND last_date > first_date
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
            WHERE user_vehicle_id = p.user_vehicle_id AND first_date >= p.parked_start 
            ORDER BY first_date ASC LIMIT 1
        ) cs_start ON true
        JOIN LATERAL (
            SELECT battery_pct FROM charging_states 
            WHERE user_vehicle_id = p.user_vehicle_id AND last_date <= p.parked_end 
            ORDER BY last_date DESC LIMIT 1
        ) cs_end ON true
        WHERE cs_start.battery_pct > cs_end.battery_pct
          AND (p.parked_end - p.parked_start) > interval '1 hour'
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
    op.execute("DROP VIEW IF EXISTS v_phantom_drain_stats;")
    op.execute("DROP VIEW IF EXISTS v_advanced_trip_stats;")
