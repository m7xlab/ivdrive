"""fix_advanced_trip_stats_math

Revision ID: 93b2a201b1a4
Revises: f3f2d2b1c4c9
Create Date: 2026-03-24 18:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '93b2a201b1a4'
down_revision: Union[str, None] = 'f3f2d2b1c4c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop and recreate view to fix mathematically flawed "average of ratios" calculation
    # which balloons efficiency values due to short trips dropping 1% SoC boundaries.
    op.execute("DROP VIEW IF EXISTS v_advanced_trip_stats;")
    op.execute("""
    CREATE OR REPLACE VIEW v_advanced_trip_stats AS
    SELECT 
        user_vehicle_id,
        COUNT(*) as total_trips,
        COUNT(*) FILTER (WHERE distance_km < 15) as short_trips_count,
        COUNT(*) FILTER (WHERE distance_km >= 15 AND distance_km < 80) as medium_trips_count,
        COUNT(*) FILTER (WHERE distance_km >= 80) as long_trips_count,
        (SUM(kwh_consumed) FILTER (WHERE avg_temp_celsius < 7) / NULLIF(SUM(distance_km) FILTER (WHERE avg_temp_celsius < 7), 0)) * 100 as avg_eff_cold,
        (SUM(kwh_consumed) FILTER (WHERE avg_temp_celsius > 12) / NULLIF(SUM(distance_km) FILTER (WHERE avg_temp_celsius > 12), 0)) * 100 as avg_eff_warm,
        (SUM(kwh_consumed) / NULLIF(SUM(distance_km), 0)) * 100 as avg_eff_overall
    FROM trips
    WHERE distance_km > 0 AND kwh_consumed >= 0
    GROUP BY user_vehicle_id;
    """)

def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_advanced_trip_stats;")
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
