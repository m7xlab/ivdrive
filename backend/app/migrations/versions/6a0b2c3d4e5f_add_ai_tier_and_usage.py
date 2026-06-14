"""Add AI Assistant tier gating + per-user usage log.

Makes the AI Assistant a configurable premium feature. Two layers:

1. Per-user enable/tier on users table:
   - ai_enabled: bool master switch (default false → no AI)
   - ai_tier: 'free' / 'pro' / 'team' (only matters when enabled)

2. Per-tier defaults on ai_tier_configs (admin-editable in the AI Assistant tab):
   - max_questions_per_day, max_questions_per_month (soft warn + hard cap)
   - model_provider, model_name (which LLM tier uses)
   - daily_cost_limit_usd (0 = no cap)

3. Per-user overrides on ai_user_overrides (NULL fields = use tier default):
   - Lets admin temporarily grant one user 200/day even though their tier says 50

4. Append-only ai_usage_log for billing + admin visibility:
   - Every request: tokens used, cost, blocked_reason (NULL = allowed)

RLS: users see their own usage, admins see all. existing_app.current_user_id
session var is set by the API middleware.

Revision ID: 6a0b2c3d4e5f
Revises: 5c0a1b2c3d4e
Create Date: 2026-06-08 19:55:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "6a0b2c3d4e5f"
down_revision: Union[str, None] = "5c0a1b2c3d4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. User-level master switch + tier
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_enabled BOOLEAN NOT NULL DEFAULT FALSE;")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_tier TEXT NOT NULL DEFAULT 'free' CHECK (ai_tier IN ('free', 'pro', 'team'));")

    # 2. Per-tier config (admin-editable defaults)
    op.execute("""
        CREATE TABLE IF NOT EXISTS ai_tier_configs (
          tier                      TEXT PRIMARY KEY
                                     CHECK (tier IN ('free', 'pro', 'team')),
          max_questions_per_day     INT NOT NULL DEFAULT 0,
          max_questions_per_month   INT NOT NULL DEFAULT 0,
          model_provider            TEXT NOT NULL DEFAULT 'deterministic',
          model_name                TEXT NOT NULL DEFAULT '',
          daily_cost_limit_usd      NUMERIC(10,4) NOT NULL DEFAULT 0,
          description               TEXT NOT NULL DEFAULT '',
          updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    # Seed the three tiers with safe defaults
    op.execute("""
        INSERT INTO ai_tier_configs
          (tier, max_questions_per_day, max_questions_per_month, model_provider, model_name, description)
        VALUES
          ('free', 0,    0,    'deterministic', '',
            'AI Assistant disabled. Free tier. Widget hidden.'),
          ('pro',  50,   1000, 'gemini', 'gemini-3.1-pro-preview',
            'Pro tier: 50 questions/day, Gemini 3.1 Pro.'),
          ('team', 200,  5000, 'gemini', 'gemini-3.1-pro-preview',
            'Team tier: 200 questions/day, Gemini 3.1 Pro.')
        ON CONFLICT (tier) DO NOTHING;
    """)

    # 3. Per-user overrides (NULL = use tier default)
    op.execute("""
        CREATE TABLE IF NOT EXISTS ai_user_overrides (
          user_id                UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
          ai_enabled_override    BOOLEAN,             -- NULL = use users.ai_enabled
          tier_override          TEXT                 -- NULL = use users.ai_tier
                                CHECK (tier_override IS NULL OR tier_override IN ('free', 'pro', 'team')),
          max_questions_per_day  INT,                 -- NULL = use tier default
          max_questions_per_month INT,
          model_provider         TEXT,
          model_name             TEXT,
          note                   TEXT,                -- admin note: "promoted for test 2026-06-08"
          updated_by_user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
          updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    # 4. Append-only usage log
    op.execute("""
        CREATE TABLE IF NOT EXISTS ai_usage_log (
          id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          user_id              UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          vehicle_id           UUID REFERENCES user_vehicles(id) ON DELETE SET NULL,
          session_id           UUID,
          requested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          model_provider       TEXT NOT NULL,         -- 'gemini', 'minimax', 'deterministic', 'blocked'
          model_name           TEXT,
          prompt_tokens        INT,
          completion_tokens    INT,
          cached_tokens        INT,                   -- from MiniMax prompt caching
          estimated_cost_usd   NUMERIC(10,6) NOT NULL DEFAULT 0,
          blocked_reason       TEXT,                  -- NULL = allowed; 'disabled', 'daily_cap', etc.
          question_chars       INT
        );
    """)

    # 5. Indexes for the queries we actually run
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_usage_user_day ON ai_usage_log (user_id, date_trunc('day', requested_at AT TIME ZONE 'UTC'));")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_usage_user_month ON ai_usage_log (user_id, date_trunc('month', requested_at AT TIME ZONE 'UTC'));")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_usage_session ON ai_usage_log (session_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ai_usage_requested ON ai_usage_log (requested_at DESC);")

    # 6. RLS — users see their own usage, admins see all
    op.execute("""
        ALTER TABLE ai_usage_log ENABLE ROW LEVEL SECURITY;
    """)

    op.execute("""
        CREATE POLICY ai_usage_self ON ai_usage_log
          FOR SELECT
          USING (user_id = current_setting('app.current_user_id', true)::uuid);
    """)

    op.execute("""
        CREATE POLICY ai_usage_admin ON ai_usage_log
          FOR SELECT
          USING (current_setting('app.is_admin', true)::boolean = true);
    """)

    # Service role (no session var) can INSERT and SELECT everything
    op.execute("""
        CREATE POLICY ai_usage_service_insert ON ai_usage_log
          FOR INSERT
          WITH CHECK (true);
    """)

    op.execute("""
        CREATE POLICY ai_usage_service_select ON ai_usage_log
          FOR SELECT
          USING (current_setting('app.current_user_id', true) IS NULL
                 OR current_setting('app.current_user_id', true) = '');
    """)

    # 7. updated_at trigger for tier configs
    op.execute("""
        CREATE OR REPLACE FUNCTION trg_update_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
          NEW.updated_at = NOW();
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("DROP TRIGGER IF EXISTS ai_tier_configs_updated_at ON ai_tier_configs;")
    op.execute("CREATE TRIGGER ai_tier_configs_updated_at BEFORE UPDATE ON ai_tier_configs FOR EACH ROW EXECUTE FUNCTION trg_update_updated_at();")

    op.execute("DROP TRIGGER IF EXISTS ai_user_overrides_updated_at ON ai_user_overrides;")
    op.execute("CREATE TRIGGER ai_user_overrides_updated_at BEFORE UPDATE ON ai_user_overrides FOR EACH ROW EXECUTE FUNCTION trg_update_updated_at();")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS ai_user_overrides_updated_at ON ai_user_overrides;")
    op.execute("DROP TRIGGER IF EXISTS ai_tier_configs_updated_at ON ai_tier_configs;")
    op.execute("DROP TABLE IF EXISTS ai_usage_log CASCADE;")
    op.execute("DROP TABLE IF EXISTS ai_user_overrides CASCADE;")
    op.execute("DROP TABLE IF EXISTS ai_tier_configs CASCADE;")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS ai_tier;")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS ai_enabled;")
