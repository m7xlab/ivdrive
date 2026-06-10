"""view_cleanup_and_curve_session_backfill — drop dead view, make climate breakdown deterministic, backfill curve session_id

Addresses review findings:

  * 0-0 — DROP the ``v_daily_consumption`` view. It is dead code: the only live
    reference is vehicles.py:1361, which is a comment explaining the endpoint
    DELIBERATELY skips the view and sources consumption directly from
    ``Trip.kwh_consumed``. No live query selects from it (grep over backend/ and
    frontend/src/ shows hits only in that comment and in prior migrations).
    Drop it so it stops drifting from the real consumption logic. The downgrade
    recreates it verbatim from the definition captured at authoring time, so the
    migration is fully reversible.

  * 0-9 — Recreate ``v_climate_penalty_breakdown`` with a DETERMINISTIC
    tiebreaker. The view picks one dominant HVAC state per trip via
    ``DISTINCT ON (trip_id) ... ORDER BY trip_id, samples DESC``. With no final
    tiebreaker, a trip whose top two states have an EQUAL sample count resolves
    to an arbitrary state that can flip run-to-run, so a trip drifts between the
    HEATING/COOLING/OFF buckets nondeterministically. We append ``state`` to the
    ORDER BY so equal-sample ties always resolve the same way (alphabetically:
    COOLING < HEATING < OFF). All columns and semantics are otherwise unchanged —
    this only makes the tie resolution stable.

  * 0-2 — One-time historical backfill of ``charging_curves.session_id``. Every
    charging_curves row currently has session_id NULL (1243/1243 at authoring
    time); the collector never set it. Link each curve to the charging_session
    whose [session_start, session_end] window (same vehicle) contains the curve's
    ``captured_at``. Verified at authoring time: 887 of the 1243 NULL rows match
    exactly one session (0 rows match more than one, so the UPDATE is
    unambiguous); the remaining ~356 fall outside any recorded session window and
    stay NULL. The UPDATE only touches rows where session_id IS NULL, so it is
    naturally idempotent and safe to re-run, and it never overwrites a value the
    collector may set going forward.

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-06-10 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "b2c3d4e5f6a8"
down_revision: Union[str, None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 0-0: drop the dead v_daily_consumption view ──────────────────────────
    # No live query reads it (vehicles.py uses Trip.kwh_consumed directly).
    op.execute("DROP VIEW IF EXISTS v_daily_consumption;")

    # ── 0-9: deterministic tiebreaker for v_climate_penalty_breakdown ─────────
    # Identical to the current definition except the DISTINCT ON pick now breaks
    # equal-sample ties on `state` (stable, alphabetical) instead of arbitrarily.
    op.execute("""
        CREATE OR REPLACE VIEW v_climate_penalty_breakdown AS
         WITH trip_state_count AS (
                 SELECT t.id AS trip_id,
                    t.user_vehicle_id,
                    t.kwh_consumed,
                    t.distance_km,
                    t.avg_temp_celsius,
                    acs.state,
                    count(*) AS samples
                   FROM trips t
                     JOIN air_conditioning_states acs ON acs.user_vehicle_id = t.user_vehicle_id
                        AND acs.captured_at >= t.start_date
                        AND acs.captured_at <= COALESCE(t.end_date, t.start_date + '04:00:00'::interval)
                        AND (acs.state::text = ANY (ARRAY['HEATING'::character varying, 'COOLING'::character varying, 'OFF'::character varying]::text[]))
                  WHERE t.distance_km > 2::double precision
                    AND t.kwh_consumed IS NOT NULL
                    AND t.kwh_consumed > 0::double precision
                    AND t.avg_temp_celsius IS NOT NULL
                  GROUP BY t.id, t.user_vehicle_id, t.kwh_consumed, t.distance_km, t.avg_temp_celsius, acs.state
                ), dominant_state AS (
                 SELECT DISTINCT ON (trip_state_count.trip_id) trip_state_count.trip_id,
                    trip_state_count.user_vehicle_id,
                    trip_state_count.kwh_consumed,
                    trip_state_count.distance_km,
                    trip_state_count.avg_temp_celsius,
                    trip_state_count.state AS hvac_state
                   FROM trip_state_count
                  ORDER BY trip_state_count.trip_id, trip_state_count.samples DESC, trip_state_count.state
                )
         SELECT user_vehicle_id,
            round(avg_temp_celsius::numeric) AS temperature,
            hvac_state,
            count(*) AS trip_count,
            round(avg(kwh_consumed / NULLIF(distance_km, 0::double precision) * 100.0::double precision)::numeric, 2) AS avg_consumption_kwh_100km
           FROM dominant_state
          GROUP BY user_vehicle_id, (round(avg_temp_celsius::numeric)), hvac_state;
    """)

    # ── 0-2: backfill charging_curves.session_id (one-time, idempotent) ───────
    # Match each NULL curve to the session window containing its captured_at,
    # scoped to the same vehicle. COALESCE handles open (NULL session_end)
    # sessions by treating the curve's own timestamp as the upper bound.
    op.execute("""
        UPDATE charging_curves cc
           SET session_id = cs.id
          FROM charging_sessions cs
         WHERE cc.session_id IS NULL
           AND cc.user_vehicle_id = cs.user_vehicle_id
           AND cc.captured_at >= cs.session_start
           AND cc.captured_at <= COALESCE(cs.session_end, cc.captured_at);
    """)


def downgrade() -> None:
    # ── reverse 0-2 ──────────────────────────────────────────────────────────
    # No-op: this was a data backfill. Nulling session_id back out would also
    # erase any values the collector legitimately set after this ran, so we
    # intentionally leave the populated rows in place.

    # ── reverse 0-9: restore the original (nondeterministic) tiebreaker ───────
    op.execute("""
        CREATE OR REPLACE VIEW v_climate_penalty_breakdown AS
         WITH trip_state_count AS (
                 SELECT t.id AS trip_id,
                    t.user_vehicle_id,
                    t.kwh_consumed,
                    t.distance_km,
                    t.avg_temp_celsius,
                    acs.state,
                    count(*) AS samples
                   FROM trips t
                     JOIN air_conditioning_states acs ON acs.user_vehicle_id = t.user_vehicle_id
                        AND acs.captured_at >= t.start_date
                        AND acs.captured_at <= COALESCE(t.end_date, t.start_date + '04:00:00'::interval)
                        AND (acs.state::text = ANY (ARRAY['HEATING'::character varying, 'COOLING'::character varying, 'OFF'::character varying]::text[]))
                  WHERE t.distance_km > 2::double precision
                    AND t.kwh_consumed IS NOT NULL
                    AND t.kwh_consumed > 0::double precision
                    AND t.avg_temp_celsius IS NOT NULL
                  GROUP BY t.id, t.user_vehicle_id, t.kwh_consumed, t.distance_km, t.avg_temp_celsius, acs.state
                ), dominant_state AS (
                 SELECT DISTINCT ON (trip_state_count.trip_id) trip_state_count.trip_id,
                    trip_state_count.user_vehicle_id,
                    trip_state_count.kwh_consumed,
                    trip_state_count.distance_km,
                    trip_state_count.avg_temp_celsius,
                    trip_state_count.state AS hvac_state
                   FROM trip_state_count
                  ORDER BY trip_state_count.trip_id, trip_state_count.samples DESC
                )
         SELECT user_vehicle_id,
            round(avg_temp_celsius::numeric) AS temperature,
            hvac_state,
            count(*) AS trip_count,
            round(avg(kwh_consumed / NULLIF(distance_km, 0::double precision) * 100.0::double precision)::numeric, 2) AS avg_consumption_kwh_100km
           FROM dominant_state
          GROUP BY user_vehicle_id, (round(avg_temp_celsius::numeric)), hvac_state;
    """)

    # ── reverse 0-0: recreate v_daily_consumption from the captured definition ─
    op.execute("""
        CREATE OR REPLACE VIEW v_daily_consumption AS
         WITH parked_periods AS (
                 SELECT vehicle_states.user_vehicle_id,
                    vehicle_states.first_date AS park_start_time,
                    lead(vehicle_states.first_date, 1) OVER (PARTITION BY vehicle_states.user_vehicle_id ORDER BY vehicle_states.first_date) AS next_park_start_time
                   FROM vehicle_states
                  WHERE vehicle_states.state::text = 'PARKED'::text
                ), consumption_cycles AS (
                 SELECT p.user_vehicle_id,
                    p.park_start_time,
                    p.next_park_start_time,
                    s_soc.battery_pct AS start_soc,
                    e_soc.battery_pct AS end_soc
                   FROM parked_periods p
                     LEFT JOIN LATERAL ( SELECT cs.battery_pct
                           FROM charging_states cs
                          WHERE cs.user_vehicle_id = p.user_vehicle_id AND cs.first_date <= p.park_start_time
                          ORDER BY cs.first_date DESC
                         LIMIT 1) s_soc ON true
                     LEFT JOIN LATERAL ( SELECT cs.battery_pct
                           FROM charging_states cs
                          WHERE cs.user_vehicle_id = p.user_vehicle_id AND cs.first_date <= COALESCE(p.next_park_start_time, now())
                          ORDER BY cs.first_date DESC
                         LIMIT 1) e_soc ON true
                ), consumption_per_cycle AS (
                 SELECT c.user_vehicle_id,
                    c.park_start_time,
                    uv.battery_capacity_kwh,
                    c.start_soc - c.end_soc AS soc_delta
                   FROM consumption_cycles c
                     JOIN user_vehicles uv ON c.user_vehicle_id = uv.id
                  WHERE c.start_soc IS NOT NULL AND c.end_soc IS NOT NULL AND (c.start_soc - c.end_soc) > 0 AND uv.battery_capacity_kwh IS NOT NULL
                )
         SELECT user_vehicle_id,
            date_trunc('day'::text, (park_start_time AT TIME ZONE 'UTC'::text))::timestamp with time zone AS consumption_day,
            sum((soc_delta::numeric / 100.0)::double precision * battery_capacity_kwh) AS total_kwh_consumed
           FROM consumption_per_cycle
          GROUP BY user_vehicle_id, (date_trunc('day'::text, (park_start_time AT TIME ZONE 'UTC'::text))::timestamp with time zone);
    """)
