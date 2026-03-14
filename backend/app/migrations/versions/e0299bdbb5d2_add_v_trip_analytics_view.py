"""add_v_trip_analytics_view

Revision ID: e0299bdbb5d2
Revises: e0299bdbb5d1
Create Date: 2026-03-12 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e0299bdbb5d2'
down_revision: Union[str, None] = 'e0299bdbb5d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE OR REPLACE VIEW v_trip_analytics AS
    SELECT
        t.*,
        (EXTRACT(EPOCH FROM (t.end_date - t.start_date)) / 60) AS duration_minutes,
        CASE 
            WHEN (EXTRACT(EPOCH FROM (t.end_date - t.start_date)) / 60) > 0 
            THEN t.distance_km / ((EXTRACT(EPOCH FROM (t.end_date - t.start_date)) / 60) / 60) 
            ELSE 0 
        END AS average_speed_kmh,
        COALESCE(
            t.kwh_consumed,
            (
                (
                    (SELECT cs.battery_pct FROM charging_states cs WHERE cs.user_vehicle_id = t.user_vehicle_id AND cs.first_date <= t.start_date ORDER BY cs.first_date DESC LIMIT 1) -
                    (SELECT cs.battery_pct FROM charging_states cs WHERE cs.user_vehicle_id = t.user_vehicle_id AND cs.first_date <= t.end_date ORDER BY cs.first_date DESC LIMIT 1)
                ) / 100.0
            ) * uv.battery_capacity_kwh
        ) AS total_kwh_consumed,
        CASE
            WHEN t.distance_km > 0 THEN
                (
                    COALESCE(
                        t.kwh_consumed,
                        (
                            (
                                (SELECT cs.battery_pct FROM charging_states cs WHERE cs.user_vehicle_id = t.user_vehicle_id AND cs.first_date <= t.start_date ORDER BY cs.first_date DESC LIMIT 1) -
                                (SELECT cs.battery_pct FROM charging_states cs WHERE cs.user_vehicle_id = t.user_vehicle_id AND cs.first_date <= t.end_date ORDER BY cs.first_date DESC LIMIT 1)
                            ) / 100.0
                        ) * uv.battery_capacity_kwh
                    ) / t.distance_km
                ) * 100
            ELSE 0
        END AS efficiency_kwh_per_100km
    FROM
        trips t
    JOIN
        user_vehicles uv ON t.user_vehicle_id = uv.id;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_trip_analytics;")
