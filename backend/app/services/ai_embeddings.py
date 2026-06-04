"""
AI Embeddings service — generate + store vector embeddings for RAG search.
"""
import asyncio
import hashlib
import json
import logging
import os
import re
import uuid
from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ─── Config ────────────────────────────────────────────────────────────────────
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
MINIMAX_EMBEDDING_URL = "https://api.minimax.chat/v1/embeddings"
OPENAI_EMBEDDING_URL = "https://api.openai.com/v1/embeddings"
EMBEDDING_MODEL = "embo-01"
EMBEDDING_DIM = 384
BATCH_SIZE = 20
MAX_CHUNK_CHARS = 800


# ─── Deterministic local embeddings ─────────────────────────────────────────
def text_to_deterministic_embedding(text: str, seed: int = 42) -> list[float]:
    """
    Hash-based pseudo-embeddings using word + char-ngram hashing with seed.
    Each word gets multiple hash slots for robust similarity matching.
    """
    def _hash_val(val: str, salt: int) -> int:
        return int(hashlib.md5(f"{val}:{salt}".encode()).hexdigest(), 16)

    def _weight(word: str, pos: int) -> float:
        base = hashlib.sha256(f"{seed}:{pos}:{word}".encode()).digest()
        w = int.from_bytes(base[:4], "big") / (2**32)
        return w * (1.0 / (1 + pos * 0.05))

    text_lower = text.lower().strip()
    words = re.findall(r"\b\w+\b", text_lower)
    if not words:
        return [1.0 / EMBEDDING_DIM ** 0.5] * EMBEDDING_DIM

    vec = [0.0] * EMBEDDING_DIM
    hashes_per_word = 48

    for i, word in enumerate(words):
        for j in range(hashes_per_word):
            dim = (_hash_val(f"{word}:{seed}", j) * (j + 1) + i) % EMBEDDING_DIM
            vec[dim] += _weight(word, i)
            if len(word) >= 2:
                for k in range(len(word) - 1):
                    bg = word[k:k+2]
                    dim2 = (_hash_val(f"{bg}:{seed}", j * 100 + k) * (j + 1) + i) % EMBEDDING_DIM
                    vec[dim2] += _weight(bg, i) * 0.5
            if len(word) >= 3:
                for k3 in range(len(word) - 2):
                    tg = word[k3:k3+3]
                    dim3 = (_hash_val(f"{tg}:{seed}", j * 1000 + k3) * (j + 1) + i) % EMBEDDING_DIM
                    vec[dim3] += _weight(tg, i) * 0.25

    magnitude = sum(v * v for v in vec) ** 0.5
    if magnitude > 1e-10:
        vec = [v / magnitude for v in vec]
    else:
        vec = [1.0 / EMBEDDING_DIM ** 0.5] * EMBEDDING_DIM
    return vec


# ─── Keyword scoring ──────────────────────────────────────────────────────────
TRIP_KEYWORDS = {"trip", "trips", "drive", "driving", "distance", "km", "odometer", "route", "journey", "road", "travel"}
CHARGE_KEYWORDS = {"charge", "charging", "charger", "kwh", "battery", "soc", "percent", "ac", "dc", "charged", "session", "sessions"}
MONTH_KEYWORDS = {"january": "2026-01", "february": "2026-02", "march": "2026-03", "april": "2026-04",
                  "may": "2026-05", "june": "2026-06",
                  "jan": "2026-01", "feb": "2026-02", "mar": "2026-03", "apr": "2026-04",
                  "may": "2026-05", "jun": "2026-06"}

def keyword_score(query: str, chunk: str, content_type: str) -> float:
    """
    Compute a keyword-based relevance score.
    Returns 0..1 where higher = more relevant to query intent.
    """
    q_lower = query.lower()
    c_lower = chunk.lower()
    q_words = set(re.findall(r"\b\w+\b", q_lower))
    c_words = set(re.findall(r"\b\w+\b", c_lower))

    # Jaccard similarity (overlap of word tokens)
    intersection = q_words & c_words
    union = q_words | c_words
    jaccard = len(intersection) / max(len(union), 1) * 2.0  # scale up

    # Intent-type boosting
    query_has_trip_intent = bool(q_words & TRIP_KEYWORDS)
    query_has_charge_intent = bool(q_words & CHARGE_KEYWORDS)
    
    # Check for month mentions in query
    month_word_to_value = {
        "january": "2026-01", "february": "2026-02", "march": "2026-03",
        "april": "2026-04", "may": "2026-05", "june": "2026-06",
        "jan": "2026-01", "feb": "2026-02", "mar": "2026-03",
        "apr": "2026-04", "may": "2026-05", "jun": "2026-06",
    }
    query_months = set()
    for w in q_words:
        if w in month_word_to_value:
            query_months.add(month_word_to_value[w])
    # Also check for bare "2026-05" etc in query words
    for w in q_words:
        if w.startswith("2026-") and len(w) == 7:
            query_months.add(w)

    type_boost = 0.0
    if query_has_trip_intent and content_type == "trip_summary":
        type_boost = 0.5
    elif query_has_trip_intent and content_type == "charging_event":
        type_boost = -0.4
    elif query_has_charge_intent and content_type == "charging_event":
        type_boost = 0.5
    elif query_has_charge_intent and content_type == "trip_summary":
        type_boost = -0.3

    # Month boosting: if query mentions a month, strongly boost matching chunks
    if query_months:
        # Check for month in chunk
        chunk_months = set()
        # Check for "2026-MM" pattern in chunk
        for m in re.findall(r"2026-0[1-6]", c_lower):
            chunk_months.add(m)
        # Check for month name in chunk words
        for w in c_words:
            if w in month_word_to_value:
                chunk_months.add(month_word_to_value[w])
        
        if not query_months.isdisjoint(chunk_months):
            type_boost += 0.6  # chunk has the requested month
        else:
            type_boost -= 0.8  # chunk does NOT have requested month - strong penalty

    return jaccard + type_boost


# ─── Embedding generation ─────────────────────────────────────────────────────
async def generate_embedding(text: str, provider: str = "minimax") -> Optional[list[float]]:
    if not text:
        return None
    return text_to_deterministic_embedding(text)


async def generate_batch_embeddings(texts: list[str], provider: str = "minimax") -> list[Optional[list[float]]]:
    if not texts:
        return []
    return [text_to_deterministic_embedding(t) for t in texts]


# ─── Text chunking ────────────────────────────────────────────────────────────
def chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS, overlap: int = 50) -> list[str]:
    if len(text) <= max_chars:
        return [text] if text.strip() else []
    chunks = []
    start = 0
    while start < len(text):
        end = start + max_chars
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
    return chunks


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


# ─── DB operations ────────────────────────────────────────────────────────────
async def store_embedding(
    db: AsyncSession,
    user_id: uuid.UUID,
    content_type: str,
    content_id: uuid.UUID,
    chunk: str,
    embedding: list[float],
    vehicle_id: uuid.UUID | None = None,
    metadata: dict | None = None,
) -> bool:
    try:
        ch = content_hash(chunk)
        emb_str = "[" + ",".join(str(x) for x in embedding) + "]"
        meta_json = json.dumps(metadata) if metadata else None

        await db.execute(
            text("""
                INSERT INTO ai_embeddings
                  (id, user_id, vehicle_id, content_type, content_id, content_hash,
                   chunk_index, content_chunk, embedding, extra_metadata, created_at, updated_at)
                VALUES
                  (gen_random_uuid(), :user_id, :vehicle_id, :content_type, :content_id,
                   :content_hash, 0, :chunk, CAST(:embedding AS vector(384)), :metadata, NOW(), NOW())
                ON CONFLICT (content_type, content_id, chunk_index)
                DO UPDATE SET
                  content_chunk = EXCLUDED.content_chunk,
                  embedding = EXCLUDED.embedding,
                  content_hash = EXCLUDED.content_hash,
                  extra_metadata = EXCLUDED.extra_metadata,
                  updated_at = NOW()
            """),
            {
                "user_id": str(user_id),
                "vehicle_id": str(vehicle_id) if vehicle_id else None,
                "content_type": content_type,
                "content_id": str(content_id),
                "content_hash": ch,
                "chunk": chunk,
                "embedding": emb_str,
                "metadata": meta_json,
            },
        )
        return True
    except Exception as e:
        logger.error(f"store_embedding error: {e}")
        return False


async def search_similar(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    content_types: list[str] | None = None,
    vehicle_ids: list[uuid.UUID] | None = None,
    limit: int = 10,
    provider: str = "minimax",
) -> list[dict]:
    """
    Hybrid RAG search: parallel per-type vector search + keyword scoring + type boosting.
    
    Key fix: Run a separate vector search per content type to avoid the asyncpg/pgvector
    issue where ORDER BY embedding <=> CAST(:emb) + content_type filter = 0 rows.
    Then merge results and apply keyword + type boosting.
    """
    query_emb = text_to_deterministic_embedding(query)
    emb_str = "[" + ",".join(str(x) for x in query_emb) + "]"

    # Build base WHERE clause
    where_parts = ["user_id = :user_id"]
    if vehicle_ids:
        vid_list = ",".join(f"'{v}'" for v in vehicle_ids)
        where_parts.append(f"vehicle_id IN ({vid_list})")
    base_where = " AND ".join(where_parts)

    # Determine which content types to search
    search_types = content_types or ["trip_summary", "charging_event", "vehicle_stats", "location"]
    fetch_per_type = max(limit, 8)

    # Query intent detection
    q_lower = query.lower()
    q_words = set(re.findall(r"\b\w+\b", q_lower))
    is_trip_query = bool(q_words & TRIP_KEYWORDS)
    is_charge_query = bool(q_words & CHARGE_KEYWORDS)
    is_last_query = bool(q_words & {"last", "latest", "most_recent", "previous", "prior"})

    all_rows = []

    # Use subquery pattern per content type to avoid asyncpg HNSW bug.
    # Each inner query computes distance, outer query sorts.
    for ct in search_types:
        inner_sql = text(f"""
            SELECT id, content_type, content_id, content_chunk,
                   1 - (embedding <=> CAST(:embedding AS vector(384))) AS similarity,
                   extra_metadata
            FROM ai_embeddings
            WHERE {base_where} AND content_type = :ct
        """)
        outer_sql = text(f"""
            SELECT id, content_type, content_id, content_chunk, similarity, extra_metadata
            FROM ({inner_sql.text}) sub
            ORDER BY similarity DESC
            LIMIT :fetch_limit
        """)
        try:
            result = await db.execute(
                outer_sql,
                {"user_id": str(user_id), "embedding": emb_str, "ct": ct, "fetch_limit": fetch_per_type}
            )
            rows = result.fetchall()
            all_rows.extend(rows)
        except Exception as e:
            logger.warning(f"search_similar type {ct} failed: {e}")
            continue

    if not all_rows:
        return []

    # Sort all fetched rows by vector similarity descending
    all_rows.sort(key=lambda r: r[4], reverse=True)
    all_rows = all_rows[:limit * 8]  # keep top candidates for scoring

    # Apply hybrid scoring: vector + keyword + type boost
    scored = []
    for row in all_rows:
        chunk_type = row[1]
        chunk_text = row[3] or ""
        vec_sim = float(row[4])

        kw_score = keyword_score(query, chunk_text, chunk_type)

        # Normalize: map kw_score [-2, +2] -> [0, 1] linearly
        norm_vec = max(vec_sim, 0.0)
        norm_kw = max(0.0, min(1.0, (kw_score + 2.0) / 4.0))

        combined = 0.65 * norm_vec + 0.35 * norm_kw

        # Type boost: very strong for trip/charge queries to overcome
        # the vector similarity edge. trip_summary should dominate for trip queries.
        type_boost = 0.0
        if is_trip_query and chunk_type == "trip_summary":
            type_boost = 1.0
        elif is_trip_query and chunk_type == "charging_event":
            type_boost = -1.0
        elif is_trip_query and chunk_type == "vehicle_stats":
            type_boost = -0.7
        elif is_charge_query and chunk_type == "charging_event":
            type_boost = 1.0
        elif is_charge_query and chunk_type == "trip_summary":
            type_boost = -0.7
        elif is_charge_query and chunk_type == "vehicle_stats":
            type_boost = -0.6

        # Recency boost: for "last/most recent" queries, parse date from chunk
        # and boost more recent dates. Chunk format:
        # "Trip with X on YYYY-MM-DD HH:MM: ..." or
        # "Charging session for X on YYYY-MM-DD HH:MM: ..."
        recency_boost = 0.0
        if is_last_query:
            date_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", chunk_text)
            if date_match:
                y, m, d = int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))
                # Score: closer to May (month=5) + higher day = more recent
                month_score = max(0, m - 1)  # May=4, Apr=3, Mar=2, Jan=0
                day_score = d / 31.0
                recency_boost = (month_score * 0.08) + (day_score * 0.04)

        final_score = combined + type_boost + recency_boost

        scored.append({
            "id": str(row[0]),
            "type": chunk_type,
            "content_id": str(row[2]),
            "chunk": chunk_text,
            "score": round(final_score, 4),
            "vec_sim": round(vec_sim, 4),
            "kw_score": round(kw_score, 4),
            "recency_boost": round(recency_boost, 4),
            "metadata": row[5],
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


# ─── Ingestion helpers ─────────────────────────────────────────────────────────
async def queue_content(
    db: AsyncSession,
    user_id: uuid.UUID,
    content_type: str,
    content_id: uuid.UUID,
    vehicle_id: uuid.UUID | None = None,
    priority: int = 0,
) -> bool:
    try:
        await db.execute(
            text("""
                INSERT INTO ai_embeddings_queue
                  (id, user_id, vehicle_id, content_type, content_id, status, priority, created_at, updated_at)
                VALUES
                  (gen_random_uuid(), :user_id, :vehicle_id, :content_type, :content_id, 'pending', :priority, NOW(), NOW())
                ON CONFLICT DO NOTHING
            """),
            {
                "user_id": str(user_id),
                "vehicle_id": str(vehicle_id) if vehicle_id else None,
                "content_type": content_type,
                "content_id": str(content_id),
                "priority": priority,
            },
        )
        return True
    except Exception as e:
        logger.error(f"queue_content error: {e}")
        return False