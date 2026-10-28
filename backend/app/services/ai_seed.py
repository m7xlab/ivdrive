"""Idempotent AI tier defaults + seed rows.

Needed because the documented self-host flow is `init_db` (ORM create_all, which
only sets Python-side defaults) followed by `alembic stamp head`, so migration
6a0b2c3d4e5f never runs and ai_tier_configs stays empty (issue #203).
Existing rows (admin edits) are never overwritten. Mirrors migration b4c6d8e0f2a3.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

_STATEMENTS = [
    "ALTER TABLE ai_usage_log ALTER COLUMN id SET DEFAULT gen_random_uuid()",
    "ALTER TABLE ai_usage_log ALTER COLUMN requested_at SET DEFAULT NOW()",
    "ALTER TABLE ai_usage_log ALTER COLUMN estimated_cost_usd SET DEFAULT 0",
    "ALTER TABLE ai_tier_configs ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
    "ALTER TABLE ai_tier_configs ALTER COLUMN created_at SET DEFAULT NOW()",
    "ALTER TABLE ai_tier_configs ALTER COLUMN updated_at SET DEFAULT NOW()",
    "ALTER TABLE ai_tier_configs ALTER COLUMN max_questions_per_day SET DEFAULT 0",
    "ALTER TABLE ai_tier_configs ALTER COLUMN max_questions_per_month SET DEFAULT 0",
    "ALTER TABLE ai_tier_configs ALTER COLUMN model_provider SET DEFAULT 'deterministic'",
    "ALTER TABLE ai_tier_configs ALTER COLUMN model_name SET DEFAULT ''",
    "ALTER TABLE ai_tier_configs ALTER COLUMN daily_cost_limit_usd SET DEFAULT 0",
    "ALTER TABLE ai_tier_configs ALTER COLUMN description SET DEFAULT ''",
    """INSERT INTO ai_tier_configs
         (tier, max_questions_per_day, max_questions_per_month, model_provider, model_name, description)
       VALUES
         ('free', 0,   0,    'deterministic', '', 'AI Assistant disabled. Free tier. Widget hidden.'),
         ('pro',  50,  1000, 'gemini', 'gemini-2.5-flash', 'Pro tier: 50 questions/day.'),
         ('team', 200, 5000, 'gemini', 'gemini-2.5-flash', 'Team tier: 200 questions/day.')
       ON CONFLICT (tier) DO NOTHING""",
]


async def ensure_ai_defaults(conn: AsyncConnection) -> bool:
    """Apply defaults/seed if the AI tables exist. Returns False when they don't."""
    for table in ("ai_usage_log", "ai_tier_configs"):
        if (await conn.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{table}"})).scalar() is None:
            return False
    for stmt in _STATEMENTS:
        await conn.execute(text(stmt))
    return True
