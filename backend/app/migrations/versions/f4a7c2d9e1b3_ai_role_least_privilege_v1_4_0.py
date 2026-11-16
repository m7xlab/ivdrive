"""v1.4.0: the AI assistant's role can read the allow-listed analytical relations and nothing else

Migration c1a4e0b7d2f9 revoked a fixed list of tables. A review found it had missed one that the
role could still read across users (``geocoded_locations``: cached addresses and coordinates, no
row-level security), because earlier migrations granted tables from a list nobody re-derived. This
revision replaces list-keeping with a rule: every table or view in ``public`` that the role can
SELECT and that is not in ``ALLOWED`` loses the grant. It also makes sure the five base tables the
fenced tables' policies read have their own row-level security policy and grant, whichever way the
install was created.

Idempotent; relations that do not exist are skipped. The downgrade is a no-op: re-granting what
this revision removed would reopen the exposure it closes.

Revision ID: f4a7c2d9e1b3
Revises: d2b5f1c8e3a0
Create Date: 2026-11-16
"""
from typing import Sequence, Union

from alembic import op

revision: str = "f4a7c2d9e1b3"
down_revision: Union[str, None] = "d2b5f1c8e3a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AI_ROLE = "ivdrive_ai_readonly"

# Keep in step with app/services/ai_sql_guard.py ALLOWED_TABLES (a test compares the two).
ALLOWED = [
    "user_vehicles", "trips", "charging_sessions", "charging_states",
    "vehicle_states", "battery_health", "vehicle_positions", "charging_curves",
    "drives", "drive_consumptions", "drive_ranges", "odometer_readings",
    "outside_temperatures", "connection_states", "climatization_states",
    "v_trip_analytics", "v_advanced_trip_stats", "v_charging_sessions_analytics",
    "v_climate_penalty_breakdown", "v_winter_penalty_stats", "v_phantom_drain_stats",
    "v_vehicle_state_durations", "v_place_stay_durations",
]

BASE_TABLES = ["trips", "charging_sessions", "battery_health", "vehicle_states", "user_vehicles"]

_USER_ID = "(current_setting('app.current_user_id'::text, true))::uuid"
_PREDICATES = {
    "user_vehicle_id": f"user_vehicle_id IN (SELECT id FROM user_vehicles WHERE user_id = {_USER_ID})",
    "user_id": f"user_id = {_USER_ID}",
}


def _do(sql: str) -> None:
    op.execute(f"DO $body$ BEGIN {sql} END $body$;")


def upgrade() -> None:
    # 1. Base tables: a policy if the install lacks one, RLS on, and the grant.
    for table in BASE_TABLES:
        policy = "isolate_user_vehicles" if table == "user_vehicles" else f"isolate_{table}"
        for column, predicate in _PREDICATES.items():
            _do(
                f"IF to_regclass('public.{table}') IS NOT NULL AND EXISTS ("
                f"  SELECT 1 FROM information_schema.columns"
                f"  WHERE table_schema = 'public' AND table_name = '{table}' AND column_name = '{column}') "
                f"AND NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = '{table}' AND policyname = '{policy}') THEN "
                f"  CREATE POLICY {policy} ON {table} FOR SELECT USING ({predicate}); END IF;"
            )
        _do(
            f"IF to_regclass('public.{table}') IS NOT NULL AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{AI_ROLE}') THEN "
            f"  ALTER TABLE {table} ENABLE ROW LEVEL SECURITY; GRANT SELECT ON {table} TO {AI_ROLE}; END IF;"
        )

    # 2. Least privilege: revoke SELECT on every other relation in public.
    allowed = ", ".join(f"'{name}'" for name in ALLOWED)
    _do(
        f"IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{AI_ROLE}') THEN "
        f"  DECLARE r record; BEGIN "
        f"    FOR r IN SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        f"             WHERE n.nspname = 'public' AND c.relkind IN ('r', 'v', 'm', 'p', 'f') "
        f"               AND c.relname NOT IN ({allowed}) "
        f"               AND has_table_privilege('{AI_ROLE}', c.oid, 'SELECT') LOOP "
        f"      EXECUTE format('REVOKE SELECT ON public.%I FROM {AI_ROLE}', r.relname); "
        f"    END LOOP; "
        f"  END; END IF;"
    )


def downgrade() -> None:
    pass
