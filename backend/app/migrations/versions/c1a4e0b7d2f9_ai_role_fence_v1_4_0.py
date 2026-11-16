"""v1.4.0: the AI assistant's database role sees only the caller's rows

The analytical SQL tool runs model-written queries as ``ivdrive_ai_readonly``. Before this
revision the role could read six tables that carry other users' data but have no row-level
security (ai_missed_intents, weconnect_errors, vignettes, ai_chat_sessions, ai_chat_messages,
ai_embeddings_queue), while the telemetry tables the tool is documented to answer from
(positions, drives, odometer, charging curves, ...) were not granted at all, and the curated
``v_*`` views ran with their owner's privileges, which would have bypassed row security
had they been granted.

This revision:
  * revokes the six out-of-scope tables from the role;
  * grants the five base tables that already have row-level security (trips, charging_sessions,
    battery_health, vehicle_states, user_vehicles) to installs that lack the grant;
  * adds a SELECT policy keyed on the current user to every telemetry table the tool may
    query, enables row-level security on it and grants SELECT to the role;
  * switches the curated views to ``security_invoker`` so the policies apply through them,
    and grants them to the role;
  * creates the chat tables the API otherwise creates at startup (chat_sessions,
    chat_messages) and drops the unused ai_chat_* pair that no code references.

Every statement is idempotent and skips tables that do not exist on this install.

Revision ID: c1a4e0b7d2f9
Revises: e7f9a1b3c5d7
Create Date: 2026-11-15
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c1a4e0b7d2f9"
down_revision: Union[str, None] = "e7f9a1b3c5d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AI_ROLE = "ivdrive_ai_readonly"

# Never for the assistant: other users' questions, error logs, toll vignettes, embedding queue.
REVOKE_TABLES = [
    "ai_missed_intents", "weconnect_errors", "vignettes",
    "ai_chat_sessions", "ai_chat_messages", "ai_embeddings_queue",
]

# Telemetry the assistant answers from. Policy: the row's vehicle belongs to the current user
# (``user_vehicle_id``), the row itself names the user (``user_id``), or the row belongs to one of
# the user's drives (``drive_id``). Tables with none of these columns are skipped and stay ungranted.
FENCE_TABLES = [
    "vehicle_positions", "drives", "drive_consumptions", "drive_ranges", "odometer_readings",
    "charging_curves", "connection_states", "climatization_states", "outside_temperatures",
    "charging_states", "air_conditioning_states", "geofences",
]

# Curated views (chat_tools._AI_SQL_ALLOWED_TABLES). security_invoker makes the role's policies
# apply inside the view instead of the owner's unrestricted access.
VIEWS = [
    "v_trip_analytics", "v_advanced_trip_stats", "v_charging_sessions_analytics",
    "v_climate_penalty_breakdown", "v_winter_penalty_stats", "v_phantom_drain_stats",
    "v_vehicle_state_durations", "v_place_stay_durations",
]

_USER_ID = "(current_setting('app.current_user_id'::text, true))::uuid"
_PREDICATES = {
    "user_vehicle_id": f"user_vehicle_id IN (SELECT id FROM user_vehicles WHERE user_id = {_USER_ID})",
    "user_id": f"user_id = {_USER_ID}",
    # drive_consumptions / drive_ranges hang off drives, not off the vehicle directly
    "drive_id": f"drive_id IN (SELECT d.id FROM drives d JOIN user_vehicles v ON v.id = d.user_vehicle_id WHERE v.user_id = {_USER_ID})",
}


def _do(sql: str) -> None:
    op.execute(f"DO $body$ BEGIN {sql} END $body$;")


def _if_table(table: str, sql: str) -> None:
    _do(f"IF to_regclass('public.{table}') IS NOT NULL THEN {sql} END IF;")


def _if_role(sql: str) -> None:
    _do(f"IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{AI_ROLE}') THEN {sql} END IF;")


# Tables whose row-level security policies already exist (ea873b9fe6a2). Some installs have the
# policies but never received the grant (the install-path problem behind issue #203), so the
# assistant could read none of them. They are granted only when RLS is on, so this can never
# open an unfenced table.
BASE_FENCED_TABLES = ["trips", "charging_sessions", "battery_health", "vehicle_states", "user_vehicles"]


def upgrade() -> None:
    # 0. Base tables: grant where row-level security is enabled.
    for table in BASE_FENCED_TABLES:
        _do(
            f"IF to_regclass('public.{table}') IS NOT NULL AND EXISTS ("
            f"  SELECT 1 FROM pg_class WHERE oid = to_regclass('public.{table}') AND relrowsecurity) "
            f"AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{AI_ROLE}') THEN "
            f"  GRANT SELECT ON {table} TO {AI_ROLE}; END IF;"
        )

    # 1. Out-of-scope tables.
    for table in REVOKE_TABLES:
        _if_table(table, f"IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{AI_ROLE}') THEN "
                         f"REVOKE SELECT ON {table} FROM {AI_ROLE}; END IF;")

    # 2. Per-user fence on the telemetry tables.
    for table in FENCE_TABLES:
        policy = f"isolate_{table}"
        for column, predicate in _PREDICATES.items():
            _do(
                f"IF to_regclass('public.{table}') IS NOT NULL AND EXISTS ("
                f"  SELECT 1 FROM information_schema.columns"
                f"  WHERE table_schema = 'public' AND table_name = '{table}' AND column_name = '{column}') "
                f"AND NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = '{table}' AND policyname = '{policy}') THEN "
                f"  CREATE POLICY {policy} ON {table} FOR SELECT USING ({predicate}); "
                f"  ALTER TABLE {table} ENABLE ROW LEVEL SECURITY; "
                f"  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{AI_ROLE}') THEN "
                f"    GRANT SELECT ON {table} TO {AI_ROLE}; END IF; "
                f"END IF;"
            )

    # 3. Views run with the caller's privileges, so the policies above apply through them.
    for view in VIEWS:
        _do(
            f"IF to_regclass('public.{view}') IS NOT NULL THEN "
            f"  ALTER VIEW {view} SET (security_invoker = true); "
            f"  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{AI_ROLE}') THEN "
            f"    GRANT SELECT ON {view} TO {AI_ROLE}; END IF; "
            f"END IF;"
        )

    # 4. Chat tables as the API creates them at startup (so a fresh install has them before the
    #    first request), and the unused ai_chat_* pair goes.
    op.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id UUID PRIMARY KEY,
            session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
            role VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            sources_json TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_chat_sessions_user ON chat_sessions(user_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_chat_messages_session ON chat_messages(session_id);")
    op.execute("DROP TABLE IF EXISTS ai_chat_messages;")
    op.execute("DROP TABLE IF EXISTS ai_chat_sessions;")


def downgrade() -> None:
    for view in VIEWS:
        _if_table(view, f"ALTER VIEW {view} SET (security_invoker = false); "
                        f"IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{AI_ROLE}') THEN "
                        f"REVOKE SELECT ON {view} FROM {AI_ROLE}; END IF;")
    for table in FENCE_TABLES:
        _if_table(table, f"DROP POLICY IF EXISTS isolate_{table} ON {table}; "
                         f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY; "
                         f"IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{AI_ROLE}') THEN "
                         f"REVOKE SELECT ON {table} FROM {AI_ROLE}; END IF;")
    # The pre-v1.4.0 grants are restored for completeness; the dropped ai_chat_* tables held no data.
    for table in REVOKE_TABLES:
        _if_table(table, f"IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{AI_ROLE}') THEN "
                         f"GRANT SELECT ON {table} TO {AI_ROLE}; END IF;")
