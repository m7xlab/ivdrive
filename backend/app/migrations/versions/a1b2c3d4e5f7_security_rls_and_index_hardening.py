"""security_rls_and_index_hardening — lock down AI read role, RLS ai_embeddings, fix indexes

Addresses review findings:

  * C1 — The ``ivdrive_ai_readonly`` role was granted SELECT on ``users`` (PII:
    email, password hash, 2FA secrets, etc.) and on ``ai_embeddings`` (which
    has NO row-level security, so the AI role could read every user's embedded
    content cross-tenant). Revoke both grants. The AI service does not need to
    read the raw ``users`` table, and ``ai_embeddings`` access must go through
    RLS scoped to the current user — not a blanket SELECT.

  * 3-3 — ``ai_embeddings`` had no RLS policy even though every other
    analytical table (trips, charging_sessions, battery_health,
    vehicle_states, user_vehicles — see ea873b9fe6a2) does. ENABLE RLS and add an
    ``isolate_ai_embeddings`` policy mirroring the exact GUC pattern used in
    ea873b9fe6a2: ``current_setting('app.current_user_id'::text, true)::uuid``.

    NOTE: this uses ENABLE (not FORCE), exactly like ea873b9fe6a2. The application
    connects as the table owner (``ivdrive``), which bypasses RLS; the RAG
    retrieval path (ai_embeddings.search_similar) and the embedding worker's
    upsert both run as the owner and scope by an explicit ``WHERE user_id = ...``
    rather than the GUC, so FORCE would break retrieval (0 rows) and writes
    (the SELECT-only policy denies owner INSERT/UPDATE under FORCE). The real
    C1 fix is the REVOKE below; the policy is defense-in-depth for any future
    non-owner reader (which, like the AI role, must SET app.current_user_id).

  * 3-6 — Index hygiene on charging tables:
      - Add ``ix_charging_curves_session_id`` (charging_curves.session_id had no
        index, so session-scoped curve lookups did sequential scans).
      - Drop ``ix_cs_vehicle_session_start`` — it is byte-for-byte redundant
        with the unique index ``uq_charging_sessions_vehicle_start`` (both are
        btree on (user_vehicle_id, session_start)). A non-unique duplicate of a
        unique index only costs write/maintenance overhead.

Data note (verified at authoring time): ai_embeddings has 7 rows, all with a
NON-NULL user_id, and the column is defined NOT NULL — so the new RLS policy
hides nothing that was previously visible to a correctly-scoped session. There
are no global/system embeddings with NULL user_id to worry about.

Revision ID: a1b2c3d4e5f7
Revises: 8b3c4d5e6f71
Create Date: 2026-06-10 17:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, None] = "8b3c4d5e6f71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── C1: revoke over-broad grants from the AI read-only role ──────────────
    # users holds PII (email, hashed password, TOTP secrets); the AI role must
    # never read it directly.
    op.execute("REVOKE SELECT ON users FROM ivdrive_ai_readonly;")
    # ai_embeddings is now protected by RLS (below); a blanket SELECT grant
    # would let the role read every tenant's chunks, so revoke it. Access is
    # expected via the application user under the RLS policy.
    op.execute("REVOKE SELECT ON ai_embeddings FROM ivdrive_ai_readonly;")

    # ── 3-3: RLS on ai_embeddings (mirror ea873b9fe6a2 pattern, ENABLE only) ──
    op.execute("""
        CREATE POLICY isolate_ai_embeddings ON ai_embeddings
            FOR SELECT USING (
                user_id = (current_setting('app.current_user_id'::text, true))::uuid
            );
    """)
    op.execute("ALTER TABLE ai_embeddings ENABLE ROW LEVEL SECURITY;")

    # ── 3-6: index hygiene on charging tables ────────────────────────────────
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_charging_curves_session_id
            ON charging_curves (session_id);
    """)
    # Redundant with uq_charging_sessions_vehicle_start (both btree on
    # (user_vehicle_id, session_start)); the unique index already serves any
    # query the non-unique one could.
    op.execute("DROP INDEX IF EXISTS ix_cs_vehicle_session_start;")


def downgrade() -> None:
    # ── reverse 3-6 ──────────────────────────────────────────────────────────
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_cs_vehicle_session_start
            ON charging_sessions (user_vehicle_id, session_start);
    """)
    op.execute("DROP INDEX IF EXISTS ix_charging_curves_session_id;")

    # ── reverse 3-3 ──────────────────────────────────────────────────────────
    op.execute("ALTER TABLE ai_embeddings DISABLE ROW LEVEL SECURITY;")
    op.execute("DROP POLICY IF EXISTS isolate_ai_embeddings ON ai_embeddings;")

    # ── reverse C1 ────────────────────────────────────────────────────────────
    op.execute("GRANT SELECT ON users TO ivdrive_ai_readonly;")
    op.execute("GRANT SELECT ON ai_embeddings TO ivdrive_ai_readonly;")
