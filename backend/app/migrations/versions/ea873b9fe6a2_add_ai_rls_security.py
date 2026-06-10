"""add_ai_rls_security — AI Chat: vector extension, tables, RLS, and ivdrive_ai_readonly role

Phase 4 AI Implementation:
  * CREATE EXTENSION vector — required for ai_embeddings.embedding (vector(384))
  * CREATE TABLE ai_embeddings — vector store for RAG chunks
  * CREATE TABLE ai_embeddings_queue — pending embedding jobs
  * CREATE TABLE ai_chat_sessions — conversation sessions
  * CREATE TABLE ai_chat_messages — conversation messages
  * CREATE ROLE ivdrive_ai_readonly — restricted SELECT-only role for AI DB access
  * RLS policies on: trips, charging_sessions, battery_health, vehicle_states, user_vehicles
  * GRANT SELECT to ivdrive_ai_readonly on all analytical tables

Revision ID: ea873b9fe6a2
Revises: d35caca2eb03
Create Date: 2026-06-07 22:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "ea873b9fe6a2"
down_revision: Union[str, None] = "d35caca2eb03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Vector extension ──────────────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # ── 2. AI role ───────────────────────────────────────────────────────────
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

    # ── 3. ai_embeddings ─────────────────────────────────────────────────────
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

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_embeddings_user_content
            ON ai_embeddings(user_id, content_type);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_embeddings_vehicle
            ON ai_embeddings(vehicle_id) WHERE vehicle_id IS NOT NULL;
    """)
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
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_queue_status
            ON ai_embeddings_queue(status, priority, created_at);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_queue_user
            ON ai_embeddings_queue(user_id);
    """)

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
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sessions_user
            ON ai_chat_sessions(user_id);
    """)

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
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_session
            ON ai_chat_messages(session_id, created_at);
    """)

    # ── 7. RLS on analytical tables ──────────────────────────────────────────
    # trips
    op.execute("""
        CREATE POLICY isolate_trips ON trips
            FOR SELECT USING (
                user_vehicle_id IN (
                    SELECT id FROM user_vehicles
                    WHERE user_id = (current_setting('app.current_user_id'::text, true))::uuid
                )
            );
    """)
    op.execute("ALTER TABLE trips ENABLE ROW LEVEL SECURITY;")

    # charging_sessions
    op.execute("""
        CREATE POLICY isolate_charging_sessions ON charging_sessions
            FOR SELECT USING (
                user_vehicle_id IN (
                    SELECT id FROM user_vehicles
                    WHERE user_id = (current_setting('app.current_user_id'::text, true))::uuid
                )
            );
    """)
    op.execute("ALTER TABLE charging_sessions ENABLE ROW LEVEL SECURITY;")

    # battery_health
    op.execute("""
        CREATE POLICY isolate_battery_health ON battery_health
            FOR SELECT USING (
                user_vehicle_id IN (
                    SELECT id FROM user_vehicles
                    WHERE user_id = (current_setting('app.current_user_id'::text, true))::uuid
                )
            );
    """)
    op.execute("ALTER TABLE battery_health ENABLE ROW LEVEL SECURITY;")

    # vehicle_states
    op.execute("""
        CREATE POLICY isolate_vehicle_states ON vehicle_states
            FOR SELECT USING (
                user_vehicle_id IN (
                    SELECT id FROM user_vehicles
                    WHERE user_id = (current_setting('app.current_user_id'::text, true))::uuid
                )
            );
    """)
    op.execute("ALTER TABLE vehicle_states ENABLE ROW LEVEL SECURITY;")

    # user_vehicles
    op.execute("""
        CREATE POLICY isolate_user_vehicles ON user_vehicles
            FOR SELECT USING (
                user_id = (current_setting('app.current_user_id'::text, true))::uuid
            );
    """)
    op.execute("ALTER TABLE user_vehicles ENABLE ROW LEVEL SECURITY;")

    # ── 8. Grants for ivdrive_ai_readonly ────────────────────────────────────
    for table in [
        "trips", "charging_sessions", "battery_health",
        "vehicle_states", "user_vehicles", "users",
        "geocoded_locations", "vignettes", "weconnect_errors",
        "ai_embeddings", "ai_embeddings_queue",
        "ai_chat_sessions", "ai_chat_messages",
    ]:
        op.execute(f"GRANT SELECT ON {table} TO ivdrive_ai_readonly;")


def downgrade() -> None:
    # Revoke
    for table in [
        "trips", "charging_sessions", "battery_health",
        "vehicle_states", "user_vehicles", "users",
        "geocoded_locations", "vignettes", "weconnect_errors",
        "ai_embeddings", "ai_embeddings_queue",
        "ai_chat_sessions", "ai_chat_messages",
    ]:
        op.execute(f"REVOKE SELECT ON {table} FROM ivdrive_ai_readonly;")

    # Drop RLS
    op.execute("ALTER TABLE trips DISABLE ROW LEVEL SECURITY;")
    op.execute("DROP POLICY IF EXISTS isolate_trips ON trips;")
    op.execute("ALTER TABLE charging_sessions DISABLE ROW LEVEL SECURITY;")
    op.execute("DROP POLICY IF EXISTS isolate_charging_sessions ON charging_sessions;")
    op.execute("ALTER TABLE battery_health DISABLE ROW LEVEL SECURITY;")
    op.execute("DROP POLICY IF EXISTS isolate_battery_health ON battery_health;")
    op.execute("ALTER TABLE vehicle_states DISABLE ROW LEVEL SECURITY;")
    op.execute("DROP POLICY IF EXISTS isolate_vehicle_states ON vehicle_states;")
    op.execute("ALTER TABLE user_vehicles DISABLE ROW LEVEL SECURITY;")
    op.execute("DROP POLICY IF EXISTS isolate_user_vehicles ON user_vehicles;")

    # Drop AI role
    op.execute("REVOKE ivdrive_ai_readonly FROM ivdrive;")
    op.execute("DROP ROLE IF EXISTS ivdrive_ai_readonly;")

    # Drop tables
    op.execute("DROP TABLE IF EXISTS ai_chat_messages;")
    op.execute("DROP TABLE IF EXISTS ai_chat_sessions;")
    op.execute("DROP TABLE IF EXISTS ai_embeddings_queue;")
    op.execute("DROP TABLE IF EXISTS ai_embeddings;")
    op.execute("DROP EXTENSION IF EXISTS vector;")