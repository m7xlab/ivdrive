"""Add ai_missed_intents table — log queries the agentic router refused to answer.

The agentic chat router (chat_tools.route_intent_via_llm) calls
`log_missing_capability(query)` when NONE of the available tools can answer
the user's question. The intent is to capture these gaps so the team can
prioritize building the missing capability.

The table was referenced in code from the day the agentic router was added
but the corresponding migration was never written, which caused the router
to 500 the whole chat request whenever a follow-up question could not be
answered. This migration creates the table and adds the minimum RLS/grants
needed by the AI readonly role.

Revision ID: 8b3c4d5e6f70
Revises: 6a0b2c3d4e5f
Create Date: 2026-06-09 08:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "8b3c4d5e6f70"
down_revision: Union[str, None] = "6a0b2c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS ai_missed_intents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            query TEXT NOT NULL,
            session_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_missed_intents_user_created
            ON ai_missed_intents(user_id, created_at DESC);
    """)

    # Grant SELECT to the AI readonly role if it exists. The role is created
    # by the ea873b9fe6a2_add_ai_rls_security migration; if that migration
    # hasn't been applied yet, this GRANT is a no-op (the role doesn't
    # exist) and will be re-issued when that migration runs.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'ivdrive_ai_readonly') THEN
                GRANT SELECT ON ai_missed_intents TO ivdrive_ai_readonly;
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_missed_intents_user_created;")
    op.execute("DROP TABLE IF EXISTS ai_missed_intents;")
