"""Embedding worker — processes the ai_embeddings_queue incrementally.

The collector schedules this via APScheduler (see app.services.collector.start).
Each tick:
  1. Pull up to `batch_size` items with status='pending' (FOR UPDATE SKIP LOCKED).
  2. For each item, call the matching content builder to produce (chunk, meta).
  3. Generate the embedding (deterministic hash-based, no API cost) and upsert into ai_embeddings.
  4. Delete the queue row on success, or mark status='failed' on error.
  5. Sleep `poll_interval_seconds` and repeat.

Configuration (all in app.config.Settings, overridable via env):
  - embedding_worker_enabled              (default True)
  - embedding_worker_poll_interval_seconds (default 300, i.e. 5 min)
  - embedding_worker_batch_size            (default 50)
  - embedding_worker_max_attempts          (default 3; failing items stop being retried)
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.services.embedding_builders import CONTENT_TYPES, parse_queue_content_id

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 768  # gemini-embedding-001 @ 768 (Matryoshka)
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "gemini-embedding-001").lower()
EMBEDDING_FALLBACK = os.getenv("EMBEDDING_FALLBACK", "deterministic").lower()


def text_to_embedding(text_in: str, seed: int = 42) -> list[float]:
    """
    DEPRECATED synchronous fallback (deterministic hash).
    Worker now uses async dispatch via ai_embeddings.generate_embedding.
    Kept only for back-compat with embed_all.py sync script.
    """
    from app.services.ai_embeddings import text_to_deterministic_embedding
    return text_to_deterministic_embedding(text_in, seed=seed)


def emb_str(vec: list[float]) -> str:
    return "[" + ",".join(str(x) for x in vec) + "]"


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


async def process_one(
    session,
    queue_id: str,
    user_id: str,
    vehicle_id: Optional[str],
    content_type: str,
    content_id: str,
    priority: int,
) -> tuple[bool, str]:
    """Process a single queue item. Returns (success, message)."""
    if content_type not in CONTENT_TYPES:
        return False, f"unknown content_type={content_type}"

    _, builder = CONTENT_TYPES[content_type]
    # content_id format: "<prefix>:<vehicle_id>". Builder expects the vehicle id only.
    prefix, target_id = parse_queue_content_id(content_id)
    try:
        result = await builder(session, target_id)
    except Exception as e:
        return False, f"builder error: {e!r}"

    if not result:
        return False, f"no source data for {content_type}/{content_id}"

    chunk, meta = result
    try:
        # Use provider-dispatched async embedding (Gemini with deterministic fallback)
        from app.services.ai_embeddings import generate_embedding
        embedding = await generate_embedding(chunk)
        if embedding is None:
            embedding = text_to_embedding(chunk)
        ch = content_hash(chunk)
        meta_json = json.dumps(meta)
        await session.execute(
            text("""
                INSERT INTO ai_embeddings
                  (id, user_id, vehicle_id, content_type, content_id, content_hash,
                   chunk_index, content_chunk, embedding, extra_metadata,
                   embedding_provider, embedding_model,
                   created_at, updated_at)
                VALUES
                  (gen_random_uuid(), :user_id, :vehicle_id, :content_type, :content_id,
                   :content_hash, 0, :chunk, CAST(:embedding AS vector(768)), :metadata,
                   :provider, :model,
                   NOW(), NOW())
                ON CONFLICT (content_type, content_id, chunk_index)
                DO UPDATE SET
                  content_chunk = EXCLUDED.content_chunk,
                  embedding = EXCLUDED.embedding,
                  content_hash = EXCLUDED.content_hash,
                  extra_metadata = EXCLUDED.extra_metadata,
                  embedding_provider = EXCLUDED.embedding_provider,
                  embedding_model = EXCLUDED.embedding_model,
                  updated_at = NOW()
            """),
            {
                "user_id": user_id,
                "vehicle_id": str(vehicle_id) if vehicle_id else None,
                "content_type": content_type,
                "content_id": content_id,
                "content_hash": ch,
                "chunk": chunk,
                "embedding": emb_str(embedding),
                "metadata": meta_json,
                "provider": EMBEDDING_PROVIDER,
                "model": f"gemini-embedding-001@{EMBEDDING_DIM}",
            },
        )
        await session.execute(
            text("DELETE FROM ai_embeddings_queue WHERE id = :id"),
            {"id": queue_id},
        )
        return True, "ok"
    except Exception as e:
        return False, f"store error: {e!r}"


async def process_pending_batch(session, batch_size: int, max_attempts: int) -> int:
    """Drain up to batch_size pending items. Returns count successfully processed."""
    result = await session.execute(
        text("""
            SELECT id, user_id, vehicle_id, content_type, content_id, priority, attempts
            FROM ai_embeddings_queue
            WHERE status = 'pending' AND attempts < :max_attempts
            ORDER BY priority DESC, created_at ASC
            LIMIT :limit
            FOR UPDATE SKIP LOCKED
        """),
        {"limit": batch_size, "max_attempts": max_attempts},
    )
    rows = result.fetchall()
    if not rows:
        return 0

    success = 0
    for r in rows:
        queue_id, user_id, vehicle_id, content_type, content_id, priority, attempts = r
        ok, msg = await process_one(
            session,
            str(queue_id),
            str(user_id),
            str(vehicle_id) if vehicle_id else None,
            content_type,
            content_id,
            int(priority) if priority is not None else 0,
        )
        if ok:
            success += 1
        else:
            logger.warning(
                "Embedding worker: failed %s/%s queue_id=%s: %s",
                content_type, content_id, queue_id, msg,
            )
            await session.execute(
                text("""
                    UPDATE ai_embeddings_queue
                    SET status = CASE WHEN attempts + 1 >= :max THEN 'failed' ELSE 'pending' END,
                        attempts = attempts + 1,
                        error = :err,
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {"id": queue_id, "err": msg[:500], "max": max_attempts},
            )
    await session.commit()
    return success


async def run_embedding_worker_tick() -> int:
    """Single tick of the worker. Returns number of items successfully processed.

    Called by APScheduler from inside the collector. Uses the existing async engine.
    """
    if not settings.embedding_worker_enabled:
        return 0
    try:
        from app.database import async_session
        async with async_session() as session:
            count = await process_pending_batch(
                session,
                settings.embedding_worker_batch_size,
                settings.embedding_worker_max_attempts,
            )
            if count:
                logger.info("Embedding worker: processed %d item(s)", count)
            return count
    except Exception as e:
        logger.exception("Embedding worker tick failed: %r", e)
        return 0
