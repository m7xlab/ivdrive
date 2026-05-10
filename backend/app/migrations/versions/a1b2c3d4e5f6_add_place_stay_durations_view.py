"""add place stay durations view

Revision ID: a1b2c3d4e5f6
Revises: f2da1da148a9
Create Date: 2026-05-10 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f2da1da148a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE OR REPLACE VIEW v_place_stay_durations AS
    WITH parked_with_location AS (
      SELECT 
        vs.user_vehicle_id,
        vs.first_date,
        vs.last_date,
        vs.state,
        EXTRACT(EPOCH FROM (vs.last_date - vs.first_date)) as duration_seconds,
        (
          SELECT vp.latitude 
          FROM vehicle_positions vp 
          WHERE vp.user_vehicle_id = vs.user_vehicle_id 
            AND vp.captured_at >= vs.first_date - INTERVAL '10 minutes'
            AND vp.captured_at <= vs.last_date + INTERVAL '10 minutes'
          ORDER BY ABS(EXTRACT(EPOCH FROM (vp.captured_at - vs.first_date)))
          LIMIT 1
        ) as parked_lat,
        (
          SELECT vp.longitude 
          FROM vehicle_positions vp 
          WHERE vp.user_vehicle_id = vs.user_vehicle_id 
            AND vp.captured_at >= vs.first_date - INTERVAL '10 minutes'
            AND vp.captured_at <= vs.last_date + INTERVAL '10 minutes'
          ORDER BY ABS(EXTRACT(EPOCH FROM (vp.captured_at - vs.first_date)))
          LIMIT 1
        ) as parked_lon
      FROM vehicle_states vs
      WHERE vs.state = 'PARKED'
    ),
    parked_with_geofence AS (
      SELECT 
        pwl.user_vehicle_id,
        pwl.first_date,
        pwl.last_date,
        pwl.duration_seconds,
        pwl.parked_lat,
        pwl.parked_lon,
        g.id as geofence_id,
        g.name as geofence_name,
        g.radius_meters,
        g.address as geofence_address,
        CASE WHEN g.id IS NOT NULL THEN false ELSE true END as is_unknown_location,
        CASE WHEN g.id IS NOT NULL THEN
          (6371000 * 2 * asin(sqrt( 
            sin((radians(g.latitude - pwl.parked_lat))/2)^2 +
            cos(radians(pwl.parked_lat)) * cos(radians(g.latitude)) *
            sin((radians(g.longitude - pwl.parked_lon))/2)^2
          )))
        ELSE NULL END as distance_to_geofence_m
      FROM parked_with_location pwl
      LEFT JOIN LATERAL (
        SELECT g2.id, g2.name, g2.radius_meters, g2.address, g2.latitude, g2.longitude
        FROM geofences g2
        JOIN user_vehicles uv ON uv.user_id = g2.user_id
        WHERE uv.id = pwl.user_vehicle_id
          AND (6371000 * 2 * asin(sqrt( 
            sin((radians(g2.latitude - pwl.parked_lat))/2)^2 +
            cos(radians(pwl.parked_lat)) * cos(radians(g2.latitude)) *
            sin((radians(g2.longitude - pwl.parked_lon))/2)^2
          ))) <= g2.radius_meters + 50
        ORDER BY 
          (6371000 * 2 * asin(sqrt( 
            sin((radians(g2.latitude - pwl.parked_lat))/2)^2 +
            cos(radians(pwl.parked_lat)) * cos(radians(g2.latitude)) *
            sin((radians(g2.longitude - pwl.parked_lon))/2)^2
          )))
        LIMIT 1
      ) g ON true
    )
    SELECT 
      user_vehicle_id,
      first_date,
      last_date,
      duration_seconds,
      parked_lat,
      parked_lon,
      geofence_id,
      geofence_name,
      geofence_address,
      is_unknown_location,
      distance_to_geofence_m
    FROM parked_with_geofence;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_place_stay_durations;")