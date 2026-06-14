"""Add v_climate_penalty_breakdown view — per-trip HVAC state attribution.

The existing v_winter_penalty_stats view buckets drive consumption by outside
temperature only, with no way to distinguish heating (cold weather) from
cooling (hot weather). This new view joins each trip to the dominant HVAC
state during the trip, bucketed by outside temperature.

This makes the "winter penalty" actually a climate penalty: at low temps
HEATING drives the kWh/100km up, at high temps COOLING does it, with OFF as
the baseline. Heating and cooling penalties can then be derived as the
delta vs. the OFF baseline at similar temperatures.

Revision ID: 5c0a1b2c3d4e
Revises: f5a6b7c8d9e0
Create Date: 2026-06-08 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "5c0a1b2c3d4e"
# Re-pointed from the production bridge (f4b2c3d4e5f6) to the AI-base catch-up
# (f5a6b7c8d9e0) so a production restore creates the missing vector/AI/RLS base
# before 8b3c4d5e6f71 resizes ai_embeddings. See f5a6b7c8d9e0 for the full why.
down_revision: Union[str, None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW v_climate_penalty_breakdown AS
        WITH trip_state_count AS (
            SELECT
                t.id AS trip_id,
                t.user_vehicle_id,
                t.kwh_consumed,
                t.distance_km,
                t.avg_temp_celsius,
                acs.state,
                COUNT(*) AS samples
            FROM trips t
            JOIN air_conditioning_states acs
              ON acs.user_vehicle_id = t.user_vehicle_id
             AND acs.captured_at BETWEEN t.start_date
                                    AND COALESCE(t.end_date, t.start_date + INTERVAL '4 hours')
             AND acs.state IN ('HEATING', 'COOLING', 'OFF')
            WHERE t.distance_km > 2
              AND t.kwh_consumed IS NOT NULL
              AND t.kwh_consumed > 0
              AND t.avg_temp_celsius IS NOT NULL
            GROUP BY t.id, t.user_vehicle_id, t.kwh_consumed,
                     t.distance_km, t.avg_temp_celsius, acs.state
        ),
        dominant_state AS (
            SELECT DISTINCT ON (trip_id)
                trip_id,
                user_vehicle_id,
                kwh_consumed,
                distance_km,
                avg_temp_celsius,
                state AS hvac_state
            FROM trip_state_count
            ORDER BY trip_id, samples DESC
        )
        SELECT
            user_vehicle_id,
            ROUND(avg_temp_celsius::numeric) AS temperature,
            hvac_state,
            COUNT(*) AS trip_count,
            ROUND(AVG((kwh_consumed / NULLIF(distance_km, 0)) * 100.0)::numeric, 2)
                AS avg_consumption_kwh_100km
        FROM dominant_state
        GROUP BY user_vehicle_id,
                 ROUND(avg_temp_celsius::numeric),
                 hvac_state;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_climate_penalty_breakdown;")
