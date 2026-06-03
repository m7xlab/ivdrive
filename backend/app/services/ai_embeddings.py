"""
iVDrive AI Embedding Service
Ingests trip/charging data into pgvector for RAG.
"""
import os
import json
import uuid
import asyncio
import logging
from datetime import datetime
from typing import Literal

import httpx
from openai import OpenAI
from sqlalchemy import select, text, and_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.ai_embedding import AIEmbedding, AIEmbeddingsQueue

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Fallback to MiniMax embeddings if no OpenAI key
MINIMAX_EMBED_URL = "https://api.minimax.io/anthropic/v1/embeddings"
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")


def get_embedding_client() -> OpenAI | None:
    """Return OpenAI client if key is configured, else None (use MiniMax fallback)."""
    if OPENAI_API_KEY and OPENAI_API_KEY != "local":
        return OpenAI(api_key=OPENAI_API_KEY)
    return None


async def embed_text_openai(text: str) -> list[float]:
    """Embed using OpenAI text-embedding-3-small."""
    client = get_embedding_client()
    if not client:
        raise ValueError("No OpenAI API key configured")
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=text[:8192])
    return resp.data[0].embedding


async def embed_text_minimax(text: str) -> list[float]:
    """Embed using MiniMax API."""
    if not MINIMAX_API_KEY:
        raise ValueError("No MINIMAX_API_KEY configured")
    headers = {"Authorization": f"Bearer {MINIMAX_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "embo-01", "input": text[:8192]}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(MINIMAX_EMBED_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["data"][0]["embedding"]


async def embed_text(text: str) -> list[float]:
    """Embed text using available provider (OpenAI preferred)."""
    try:
        return await embed_text_openai(text)
    except Exception as e:
        logger.warning("OpenAI embedding failed (%s), trying MiniMax", e)
        try:
            return await embed_text_minimax(text)
        except Exception as e2:
            logger.error("MiniMax embedding also failed: %s", e2)
            raise ValueError(f"All embedding providers failed: {e}, {e2}")


def _vector_to_json(vector: list[float]) -> str:
    """Convert list to pgvector JSON string format."""
    return json.dumps(vector)


async def upsert_embedding(
    session: AsyncSession,
    user_id: uuid.UUID,
    vehicle_id: uuid.UUID,
    chunk_type: str,
    chunk_text: str,
    embedding: list[float],
    source_id: str,
    metadata: dict | None = None,
) -> AIEmbedding:
    """Insert or update a single embedding (upsert by user+vehicle+type+source_id)."""
    meta = metadata or {}
    meta["source_id"] = source_id
    meta["created_at"] = datetime.utcnow().isoformat()

    stmt = insert(AIEmbedding).values(
        id=uuid.uuid4(),
        user_id=user_id,
        vehicle_id=vehicle_id,
        chunk_type=chunk_type,
        chunk_text=chunk_text,
        embedding=_vector_to_json(embedding),
        metadata=meta,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_ai_emb_source",
        set_={
            "chunk_text": stmt.excluded.chunk_text,
            "embedding": stmt.excluded.embedding,
            "metadata": stmt.excluded.metadata,
            "updated_at": datetime.utcnow(),
        },
    )
    await session.execute(stmt)
    result = await session.execute(
        select(AIEmbedding).where(
            and_(
                AIEmbedding.user_id == user_id,
                AIEmbedding.vehicle_id == vehicle_id,
                AIEmbedding.chunk_type == chunk_type,
            )
        ).where(text(f"metadata->>'source_id' = :source_id")).params(source_id=source_id)
    )
    return result.scalar_one_or_none()


async def search_embeddings(
    user_id: uuid.UUID,
    vehicle_ids: list[uuid.UUID],
    query: str,
    top_k: int = 5,
    chunk_types: list[str] | None = None,
) -> list[dict]:
    """
    Search pgvector for user + vehicle scoped embeddings.
    HARD FILTER: user_id AND vehicle_id IN (...) — always applied.
    """
    if not vehicle_ids:
        return []

    query_emb = await embed_text(query)
    vehicle_ids_str = ",".join(f"'{v}'" for v in vehicle_ids)

    type_filter = ""
    if chunk_types:
        types_str = ",".join(f"'{t}'" for t in chunk_types)
        type_filter = f"AND chunk_type IN ({types_str})"

    sql = text(f"""
        SELECT id, chunk_text, metadata, chunk_type,
               1 - (embedding <=> :query_emb::vector) AS score
        FROM ai_embeddings
        WHERE user_id = :user_id
          AND vehicle_id IN ({vehicle_ids_str})
          {type_filter}
        ORDER BY embedding <=> :query_emb::vector
        LIMIT {top_k}
    """)

    async with async_session() as session:
        result = await session.execute(
            sql,
            {"user_id": str(user_id), "query_emb": json.dumps(query_emb)},
        )
        rows = result.fetchall()
        return [
            {
                "id": str(row[0]),
                "chunk_text": row[1],
                "metadata": row[2],
                "chunk_type": row[3],
                "score": float(row[4]) if row[4] is not None else 0.0,
            }
            for row in rows
        ]


def _format_trip_chunk(trip) -> str:
    """Format a trip record into a human-readable chunk."""
    return (
        f"Trip: {(trip.start_address or 'Unknown')} → {(trip.end_address or 'Unknown')}. "
        f"Distance: {getattr(trip, 'distance_km', 0) or 0}km. "
        f"Duration: {getattr(trip, 'duration_min', 0) or 0}min. "
        f"Avg speed: {getattr(trip, 'avg_speed_kmh', 0) or 0}km/h. "
        f"Consumption: {getattr(trip, 'avg_consumption_kwh100km', 0) or 0}kWh/100km."
    )


def _format_charging_chunk(charge) -> str:
    """Format a charging session into a human-readable chunk."""
    return (
        f"Charging session: Start SOC {getattr(charge, 'soc_pct_start', '?') or '?'}% → "
        f"End SOC {getattr(charge, 'soc_pct_end', '?') or '?'}%. "
        f"Energy added: {getattr(charge, 'energy_kwh', 0) or 0}kWh. "
        f"Duration: {getattr(charge, 'duration_minutes', 0) or 0}min. "
        f"Cost: {getattr(charge, 'base_cost_eur', 0) or 0}EUR."
    )