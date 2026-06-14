"""ai_base_catchup_for_production — create the AI/vector base on production restores

WHY THIS EXISTS
---------------
The production DB was restored at alembic revision ``f4b2c3d4e5f6``
(``f4b2c3d4e5f6_bridge_production_revision.py``). That bridge is a *no-op* that
asserts production's state is "equivalent to ``ea873b9fe6a2``" — i.e. that the
AI/vector base (vector extension, ``ai_embeddings`` + companion tables, RLS
policies, the ``ivdrive_ai_readonly`` role and its grants) already exists.

That assertion is FALSE for the actual production database. Verified against a
production restore: it has the full analytical schema and data (e.g. 3,544 trips)
but **none** of the ``ea873b9fe6a2`` objects — no ``vector`` extension, no
``ai_embeddings`` table, no RLS. Because production is *stamped* at
``f4b2c3d4e5f6``, alembic considers ``ea873b9fe6a2`` (an ancestor of the bridge)
already applied and will never run it. The next pending migration that touches
the AI base, ``8b3c4d5e6f71`` (``TRUNCATE ai_embeddings`` / ``ALTER COLUMN
embedding TYPE vector(768)``), then aborts with
``relation "ai_embeddings" does not exist`` and leaves a half-migrated DB.

WHAT THIS DOES
--------------
Recreates the exact object set from ``ea873b9fe6a2`` (vector extension, the four
AI base tables at ``vector(384)``, indexes, RLS policies, role + grants), but
**fully idempotent** (``IF NOT EXISTS`` / ``DROP POLICY IF EXISTS`` guards). It is
inserted immediately after the production stamp ``f4b2c3d4e5f6`` and before
``5c0a1b2c3d4e``, so on a production restore it creates the missing base; on the
dev database (already at head with these objects) it is an ancestor of the
current head and never executes. Subsequent migrations (``8b3c4d5e6f71`` resize
to 768, ``a1b2c3d4e5f7`` RLS/grant hardening) then run exactly as they did on dev.

This is deliberately NOT a substitute for ``ea873b9fe6a2`` on fresh installs —
on a fresh DB the normal chain runs ``ea873b9fe6a2`` first, and this migration's
guards make it a no-op when it is reached.

Revision ID: f5a6b7c8d9e0
Revises: f4b2c3d4e5f6
Create Date: 2026-06-14 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, None] = "f4b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The five analytical tables that get per-user RLS, mirroring ea873b9fe6a2.
_RLS_TABLES = {
    "trips": "user_vehicle_id IN (SELECT id FROM user_vehicles WHERE user_id = (current_setting('app.current_user_id'::text, true))::uuid)",
    "charging_sessions": "user_vehicle_id IN (SELECT id FROM user_vehicles WHERE user_id = (current_setting('app.current_user_id'::text, true))::uuid)",
    "battery_health": "user_vehicle_id IN (SELECT id FROM user_vehicles WHERE user_id = (current_setting('app.current_user_id'::text, true))::uuid)",
    "vehicle_states": "user_vehicle_id IN (SELECT id FROM user_vehicles WHERE user_id = (current_setting('app.current_user_id'::text, true))::uuid)",
    "user_vehicles": "user_id = (current_setting('app.current_user_id'::text, true))::uuid",
}

_GRANT_TABLES = [
    "trips", "charging_sessions", "battery_health",
    "vehicle_states", "user_vehicles", "users",
    "geocoded_locations", "vignettes", "weconnect_errors",
    "ai_embeddings", "ai_embeddings_queue",
    "ai_chat_sessions", "ai_chat_messages",
]


def _policy_name(table: str) -> str:
    return "isolate_user_vehicles" if table == "user_vehicles" else f"isolate_{table}"


def upgrade() -> None:
    # ── 1. Vector extension ──────────────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # ── 2. AI read-only role (global; may already exist from another DB) ──────
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'ivdrive_ai_readonly') THEN
                CREATE ROLE ivdrive_ai_readonly WITH NOLOGIN;
            END IF;
        END
        $$;
    """)
    op.execute("GRANT ivdrive_ai_readonly TO ivdrive;")

    # ── 3. ai_embeddings (vector(384) — resized to 768 later by 8b3c4d5e6f71) ─
    op.execute("""
        CREATE TABLE IF NOT EXISTS ai_embeddings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            vehicle_id UUID,
            content_type VARCHAR(50) NOT NULL,
            content_id VARCHAR(100) NOT NULL,
            content_hash VARCHAR(64) NOT NULL,
            chunk_index INTEGER NOT NULL DEFAULT 0,
            content_chunk TEXT NOT NULL,
            embedding vector(384),
            extra_metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(content_type, content_id, chunk_index)
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_user_content ON ai_embeddings(user_id, content_type);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_vehicle ON ai_embeddings(vehicle_id) WHERE vehicle_id IS NOT NULL;")
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_embeddings_embedding
            ON ai_embeddings USING hnsw(embedding vector_cosine_ops)
            WITH (m=16, ef_construction=200);
    """)

    # ── 4. ai_embeddings_queue ────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS ai_embeddings_queue (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            vehicle_id UUID,
            content_type VARCHAR(50) NOT NULL,
            content_id VARCHAR(100) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            priority INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_queue_status ON ai_embeddings_queue(status, priority, created_at);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_queue_user ON ai_embeddings_queue(user_id);")

    # ── 5. ai_chat_sessions ───────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS ai_chat_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            vehicle_id UUID,
            provider VARCHAR(20) NOT NULL DEFAULT 'minimax',
            model VARCHAR(100),
            title VARCHAR(255),
            message_count INTEGER NOT NULL DEFAULT 0,
            last_message_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON ai_chat_sessions(user_id);")

    # ── 6. ai_chat_messages ───────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS ai_chat_messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id UUID NOT NULL REFERENCES ai_chat_sessions(id) ON DELETE CASCADE,
            role VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            token_count INTEGER,
            sources JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON ai_chat_messages(session_id, created_at);")

    # ── 7. RLS on analytical tables (idempotent: drop-then-create) ────────────
    for table, predicate in _RLS_TABLES.items():
        pol = _policy_name(table)
        op.execute(f"DROP POLICY IF EXISTS {pol} ON {table};")
        op.execute(f"CREATE POLICY {pol} ON {table} FOR SELECT USING ({predicate});")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")

    # ── 8. Grants for ivdrive_ai_readonly (a1b2c3d4e5f7 later tightens these) ─
    for table in _GRANT_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO ivdrive_ai_readonly;")


def downgrade() -> None:
    # Mirror ea873b9fe6a2.downgrade() so a full downgrade past this point is clean.
    for table in _GRANT_TABLES:
        op.execute(f"REVOKE SELECT ON {table} FROM ivdrive_ai_readonly;")

    for table in _RLS_TABLES:
        pol = _policy_name(table)
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
        op.execute(f"DROP POLICY IF EXISTS {pol} ON {table};")

    op.execute("REVOKE ivdrive_ai_readonly FROM ivdrive;")
    op.execute("DROP TABLE IF EXISTS ai_chat_messages;")
    op.execute("DROP TABLE IF EXISTS ai_chat_sessions;")
    op.execute("DROP TABLE IF EXISTS ai_embeddings_queue;")
    op.execute("DROP TABLE IF EXISTS ai_embeddings;")
    # Intentionally NOT dropping the vector extension or the role here: both are
    # shared / global and may be in use by other databases on the cluster.
