"""#203 - init_db + `alembic stamp head` must leave a usable AI gate."""

import uuid

import pytest
from sqlalchemy import text

from .conftest import *  # noqa: F401,F403  (fixtures)
from app.services.ai_seed import ensure_ai_defaults


@pytest.mark.asyncio
async def test_seed_populates_tiers_and_defaults_on_create_all_schema(replay_sessionmaker):
    async with replay_sessionmaker() as s:
        conn = await s.connection()
        assert (await s.execute(text("SELECT count(*) FROM ai_tier_configs"))).scalar() == 0
        assert await ensure_ai_defaults(conn)
        await ensure_ai_defaults(conn)  # idempotent
        tiers = dict((await s.execute(text("SELECT tier, model_provider FROM ai_tier_configs"))).all())
        assert set(tiers) == {"free", "pro", "team"}


@pytest.mark.asyncio
async def test_seed_keeps_admin_edits_and_usage_log_insert_works(replay_sessionmaker, vehicle_id):
    async with replay_sessionmaker() as s:
        conn = await s.connection()
        await ensure_ai_defaults(conn)
        await s.execute(text("UPDATE ai_tier_configs SET model_provider='ollama', model_name='llama3' WHERE tier='pro'"))
        await ensure_ai_defaults(conn)
        row = (await s.execute(text("SELECT model_provider, model_name FROM ai_tier_configs WHERE tier='pro'"))).one()
        assert tuple(row) == ("ollama", "llama3")
        uid = (await s.execute(text("SELECT id FROM users LIMIT 1"))).scalar()
        # no id/requested_at supplied: relies on the repaired server defaults (the #203 NotNullViolation)
        await s.execute(
            text("INSERT INTO ai_usage_log (user_id, model_provider) VALUES (:u, 'gemini')"), {"u": uid}
        )
        await s.commit()
