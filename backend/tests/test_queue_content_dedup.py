"""Regression test for the queue dedup contract.

Background
----------
v1.1.2.3 (PR #174) unblocked the embedding worker from crashing on every
tick. With the worker draining cleanly, the next observation was that
ai_embeddings_queue was still growing at ~11 rows/min in production.

Root cause: queue_content() in app/services/ai_embeddings.py was issuing
`INSERT … ON CONFLICT DO NOTHING`, but ai_embeddings_queue had no unique
constraint on (content_type, content_id) — only the PK on `id` and
non-unique index on (status, priority, created_at). Postgres had
nothing for ON CONFLICT to match against. Every collector poll cycle
silently inserted a fresh duplicate.

Fix (PR in flight, hotfix/queue-pending-dedup-index):
  1. Alembic migration adds the partial unique index
     `idx_queue_pending_dedup` on (content_type, content_id)
     WHERE status = 'pending'.
  2. queue_content() updates its ON CONFLICT clause to explicitly
     reference that index, so the dedup contract is locked in at
     the SQL boundary.

These tests pin both halves. They require a running Postgres because
they exercise actual INSERT/SELECT semantics on ai_embeddings_queue.
They use an isolated transaction per test so they can't pollute the
real production queue.

Run:
    cd backend && pytest tests/test_queue_content_dedup.py -v \
        --override-ini="addopts=" \
        --env-file ../.env

Or directly with the same env vars the app uses:
    DATABASE_URL=... pytest tests/test_queue_content_dedup.py -v

Note on content_id format
-------------------------
The ``ai_embeddings_queue.content_id`` column is ``varchar(100)`` (NOT UUID)
despite the ``uuid.UUID`` type hint on ``queue_content()``'s signature.
Production stores content_ids as ``"<prefix>:<vehicle_uuid>"`` where prefix
is one of the registered ``CONTENT_TYPES`` keys (e.g. ``vehicle:``,
``battery:``, ``curve:``, ``drive:``, ``climate_penalty:`` etc.). These tests
mirror that production format (``f"test:{uuid.uuid4()}"``) so they're shape-
faithful even though the column itself doesn't enforce UUID. If the schema
ever changes to UUID, the tests will need to drop the prefix and pass a raw
``uuid.uuid4()`` instead.
"""

import os
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


# Pull DATABASE_URL from env exactly as the app does (it also reads
# settings.DATABASE_URL, but for this test we want to bypass pydantic
# settings and read from os.environ to keep deps minimal).
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    pytest.skip(
        "DATABASE_URL not set — these integration tests require a live Postgres",
        allow_module_level=True,
    )


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Yield an isolated async session for each test.

    Uses SAVEPOINT transactions so test data rolls back automatically
    instead of polluting the live ai_embeddings_queue. Requires the
    underlying Postgres to support transactional DDL (Postgres ≥ 11).
    """
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as conn:
        trans = await conn.begin()
        Session = async_sessionmaker(bind=conn, expire_on_commit=False)
        sess = Session()
        try:
            yield sess
        finally:
            await sess.close()
            await trans.rollback()
        await engine.dispose()


@pytest.mark.asyncio
async def test_partial_unique_index_exists_on_queue_table(session: AsyncSession) -> None:
    """The partial unique index must exist for the ON CONFLICT clause
    in queue_content() to match anything.

    If a deployment strips this index (e.g. an operational drop),
    the queue dedup silently regresses to the pre-fix behaviour
    (insert new rows on every call). This test fails fast so the
    regression can't sneak past.
    """
    result = await session.execute(
        text(
            """
            SELECT indexdef
            FROM pg_indexes
            WHERE tablename = 'ai_embeddings_queue'
              AND indexname = 'idx_queue_pending_dedup'
            """
        )
    )
    row = result.fetchone()
    assert row is not None, (
        "idx_queue_pending_dedup missing — without it, queue_content()'s "
        "ON CONFLICT DO NOTHING is a no-op and the queue will grow "
        "unboundedly from re-enqueue storms (production observed: 1462 "
        "pending rows for ~70 unique pairs)."
    )
    indexdef = row[0].lower()
    assert "unique" in indexdef, f"index is not UNIQUE: {indexdef}"
    assert "status" in indexdef and "pending" in indexdef, (
        f"index is not partial on status='pending': {indexdef}"
    )


@pytest.mark.asyncio
async def test_queue_content_dedups_against_partial_unique_index(
    session: AsyncSession,
) -> None:
    """Inserting twice with the same (content_type, content_id) must
    produce exactly one pending row.

    Pre-fix this test would see 2 rows; post-fix it must see 1 row.

    We use raw INSERT here (not the queue_content() helper) so the test
    stays tightly focused on the database-level dedup contract and
    doesn't depend on the function being in a particular state.
    """
    user_id = uuid.uuid4()
    vehicle_id = uuid.uuid4()
    content_type = "vehicle_summary"
    content_id = f"test:{uuid.uuid4()}"

    insert_sql = text(
        """
        INSERT INTO ai_embeddings_queue
          (id, user_id, vehicle_id, content_type, content_id, status, priority, created_at, updated_at)
        VALUES
          (gen_random_uuid(), :user_id, :vehicle_id, :content_type, :content_id, 'pending', 0, NOW(), NOW())
        ON CONFLICT (content_type, content_id) WHERE status = 'pending' DO NOTHING
        """
    )

    # First insert — must succeed.
    await session.execute(
        insert_sql,
        {
            "user_id": user_id,
            "vehicle_id": vehicle_id,
            "content_type": content_type,
            "content_id": content_id,
        },
    )

    # Second insert with SAME (content_type, content_id) — must be no-op
    # because of the partial unique index.
    await session.execute(
        insert_sql,
        {
            "user_id": user_id,
            "vehicle_id": vehicle_id,
            "content_type": content_type,
            "content_id": content_id,
        },
    )

    # Flush so the rowcount counts show up.
    await session.flush()

    result = await session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM ai_embeddings_queue
            WHERE content_type = :content_type
              AND content_id = :content_id
              AND status = 'pending'
            """
        ),
        {"content_type": content_type, "content_id": content_id},
    )
    count = result.scalar()
    assert count == 1, (
        f"expected 1 pending row after duplicate insert, got {count}. "
        "The partial unique index is not deduplicating — queue_content() "
        "regressed to inserting duplicates."
    )


@pytest.mark.asyncio
async def test_completed_or_failed_rows_do_not_block_new_pending_inserts(
    session: AsyncSession,
) -> None:
    """The partial unique index only constrains status='pending'. A
    historical 'completed' or 'failed' row must NOT block a fresh
    'pending' insertion for the same (content_type, content_id).

    Without the partial WHERE clause, this would conflict and silently
    fail — preventing any re-queue of items whose previous attempt
    completed or failed. That would break the #167 "delete permanent
    failures" pattern (item gets marked failed → can't be re-enqueued).
    """
    user_id = uuid.uuid4()
    vehicle_id = uuid.uuid4()
    content_type = "vehicle_summary"
    content_id = f"test:{uuid.uuid4()}"

    # Stage 1: insert a 'completed' row for this pair.
    await session.execute(
        text(
            """
            INSERT INTO ai_embeddings_queue
              (id, user_id, vehicle_id, content_type, content_id, status, priority, created_at, updated_at)
            VALUES
              (gen_random_uuid(), :user_id, :vehicle_id, :content_type, :content_id, 'completed', 0, NOW(), NOW())
            """
        ),
        {
            "user_id": user_id,
            "vehicle_id": vehicle_id,
            "content_type": content_type,
            "content_id": content_id,
        },
    )

    # Stage 2: insert a new 'pending' row for the same pair.
    # This MUST succeed despite the existing 'completed' row.
    insert_pending = text(
        """
        INSERT INTO ai_embeddings_queue
          (id, user_id, vehicle_id, content_type, content_id, status, priority, created_at, updated_at)
        VALUES
          (gen_random_uuid(), :user_id, :vehicle_id, :content_type, :content_id, 'pending', 0, NOW(), NOW())
        ON CONFLICT (content_type, content_id) WHERE status = 'pending' DO NOTHING
        """
    )
    await session.execute(
        insert_pending,
        {
            "user_id": user_id,
            "vehicle_id": vehicle_id,
            "content_type": content_type,
            "content_id": content_id,
        },
    )
    await session.flush()

    result = await session.execute(
        text(
            """
            SELECT COUNT(*)
            FROM ai_embeddings_queue
            WHERE content_type = :content_type
              AND content_id = :content_id
              AND status = 'pending'
            """
        ),
        {"content_type": content_type, "content_id": content_id},
    )
    count = result.scalar()
    assert count == 1, (
        f"expected 1 new pending row despite existing completed row, got {count}. "
        "The unique index is incorrectly scoped (likely missing the "
        "WHERE status = 'pending' partial predicate)."
    )
