"""v1.3.5: repair AI tier seed/defaults; charging SoC-change clock; trip data_quality

Revision ID: b4c6d8e0f2a3
Revises: a9f3c2d1e8b7
Create Date: 2026-10-28

1. Self-hosted installs whose AI tables were created outside migration
   6a0b2c3d4e5f (e.g. via init_db/create_all) have an empty ai_tier_configs and
   no server defaults, so the AI gate finds no tier ("AI Assistant not
   available") and ai_usage_log inserts fail. Re-apply defaults and seed rows
   idempotently; existing rows (admin edits) are never overwritten.
2. charging_sessions.last_soc_change_at: activity clock for the flat-SoC auto-close.
3. trips.data_quality: marks trips whose start was reconstructed from odometer.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b4c6d8e0f2a3"
down_revision: Union[str, None] = "a9f3c2d1e8b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE charging_sessions ADD COLUMN IF NOT EXISTS last_soc_change_at TIMESTAMPTZ;")
    op.execute("ALTER TABLE trips ADD COLUMN IF NOT EXISTS data_quality VARCHAR(30);")
    op.execute("""
        DO $$
        BEGIN
          IF to_regclass('public.ai_usage_log') IS NOT NULL THEN
            ALTER TABLE ai_usage_log ALTER COLUMN id SET DEFAULT gen_random_uuid();
            ALTER TABLE ai_usage_log ALTER COLUMN requested_at SET DEFAULT NOW();
            ALTER TABLE ai_usage_log ALTER COLUMN estimated_cost_usd SET DEFAULT 0;
          END IF;
          IF to_regclass('public.ai_tier_configs') IS NOT NULL THEN
            ALTER TABLE ai_tier_configs ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
            ALTER TABLE ai_tier_configs ALTER COLUMN created_at SET DEFAULT NOW();
            ALTER TABLE ai_tier_configs ALTER COLUMN max_questions_per_day SET DEFAULT 0;
            ALTER TABLE ai_tier_configs ALTER COLUMN max_questions_per_month SET DEFAULT 0;
            ALTER TABLE ai_tier_configs ALTER COLUMN model_provider SET DEFAULT 'deterministic';
            ALTER TABLE ai_tier_configs ALTER COLUMN model_name SET DEFAULT '';
            ALTER TABLE ai_tier_configs ALTER COLUMN daily_cost_limit_usd SET DEFAULT 0;
            ALTER TABLE ai_tier_configs ALTER COLUMN description SET DEFAULT '';
            ALTER TABLE ai_tier_configs ALTER COLUMN updated_at SET DEFAULT NOW();
            INSERT INTO ai_tier_configs
              (tier, max_questions_per_day, max_questions_per_month, model_provider, model_name, description)
            VALUES
              ('free', 0,   0,    'deterministic', '', 'AI Assistant disabled. Free tier. Widget hidden.'),
              ('pro',  50,  1000, 'gemini', 'gemini-2.5-flash', 'Pro tier: 50 questions/day.'),
              ('team', 200, 5000, 'gemini', 'gemini-2.5-flash', 'Team tier: 200 questions/day.')
            ON CONFLICT (tier) DO NOTHING;
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE trips DROP COLUMN IF EXISTS data_quality;")
    op.execute("ALTER TABLE charging_sessions DROP COLUMN IF EXISTS last_soc_change_at;")
