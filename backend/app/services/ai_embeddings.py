"""
AI Embeddings service — generate + store vector embeddings for RAG search.

Provider dispatch:
  - gemini-embedding-001  (default) — Matryoshka-truncated to 768 dims
  - deterministic         (fallback) — hash-based, 384 dims, free
  - bge-m3                (stub)     — local, for future deployment
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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_EMBEDDING_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001"
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
MINIMAX_EMBEDDING_URL = "https://api.minimax.chat/v1/embeddings"
OPENAI_EMBEDDING_URL = "https://api.openai.com/v1/embeddings"

# Provider selection. Falls back to deterministic if Gemini fails.
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "gemini-embedding-001").lower()
EMBEDDING_FALLBACK = os.getenv("EMBEDDING_FALLBACK", "deterministic").lower()
EMBEDDING_DIM = 768  # gemini-embedding-001 @ 768 (Matryoshka)
BATCH_SIZE = 20
MAX_CHUNK_CHARS = 800


# ─── Gemini embeddings (semantic, Matryoshka 768-dim) ─────────────────────
async def text_to_gemini_embedding(text: str, dim: int = 768) -> Optional[list[float]]:
    """
    Call gemini-embedding-001 with Matryoshka truncation to `dim`.
    Returns None on any failure (caller falls back).
    """
    if not text or not GEMINI_API_KEY:
        return None
    try:
        url = f"{GEMINI_EMBEDDING_URL}:batchEmbedContents?key={GEMINI_API_KEY}"
        payload = {
            "requests": [
                {
                    "model": "models/gemini-embedding-001",
                    "content": {"parts": [{"text": text[:2000]}]},
                    "outputDimensionality": dim,
                    "taskType": "RETRIEVAL_DOCUMENT",
                }
            ]
        }
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, json=payload)
        if r.status_code != 200:
            logger.warning(f"gemini-embedding-001 HTTP {r.status_code}: {r.text[:200]}")
            return None
        data = r.json()
        return data["embeddings"][0]["values"]
    except Exception as e:
        logger.warning(f"gemini-embedding-001 failed: {e}")
        return None


async def batch_gemini_embeddings(texts: list[str], dim: int = 768) -> list[Optional[list[float]]]:
    """
    Batch call — up to 100 requests per call. Returns list aligned to `texts`.
    None on individual failures.
    """
    if not texts or not GEMINI_API_KEY:
        return [None] * len(texts)
    if len(texts) > 100:
        # chunk the batch to stay under API limit
        out = []
        for i in range(0, len(texts), 100):
            out.extend(await batch_gemini_embeddings(texts[i:i+100], dim))
        return out
    try:
        url = f"{GEMINI_EMBEDDING_URL}:batchEmbedContents?key={GEMINI_API_KEY}"
        payload = {
            "requests": [
                {
                    "model": "models/gemini-embedding-001",
                    "content": {"parts": [{"text": t[:2000]}]},
                    "outputDimensionality": dim,
                    "taskType": "RETRIEVAL_DOCUMENT",
                }
                for t in texts
            ]
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, json=payload)
        if r.status_code != 200:
            logger.warning(f"gemini batch HTTP {r.status_code}")
            return [None] * len(texts)
        data = r.json()
        return [e["values"] for e in data["embeddings"]]
    except Exception as e:
        logger.warning(f"gemini batch failed: {e}")
        return [None] * len(texts)


# ─── BGE-m3 local embeddings (stub for future) ─────────────────────────────
async def text_to_bge_m3_embedding(text: str) -> Optional[list[float]]:
    """
    Stub. To enable: install sentence-transformers and download BAAI/bge-m3
    into the collector image. Will return 1024-dim vectors.
    Currently not implemented — falls back silently.
    """
    # Future: from sentence_transformers import SentenceTransformer
    #         model = SentenceTransformer("BAAI/bge-m3")
    #         return model.encode(text, normalize_embeddings=True).tolist()
    return None


# ─── Deterministic local embeddings (FALLBACK ONLY) ─────────────────────────
def text_to_deterministic_embedding(text: str, seed: int = 42) -> list[float]:
    """
    Hash-based pseudo-embeddings. ONLY used as fallback when primary provider
    (Gemini) fails. NOT recommended for production RAG.
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
TRIP_KEYWORDS = {"trip", "trips", "drive", "driving", "distance", "km", "odometer", "route", "journey", "road", "travel", "consumption", "kwh per 100"}
CHARGE_KEYWORDS = {"charge", "charging", "charger", "kwh", "battery", "soc", "percent", "ac", "dc", "charged", "session", "sessions", "charging_curve", "charge_curve"}
VEHICLE_KEYWORDS = {"vehicle", "car", "make", "model", "year", "spec", "specs", "specifications", "battery", "power", "range", "wltp", "body", "trim", "colour", "color", "options", "about", "what is"}
BATTERY_KEYWORDS = {"soh", "battery health", "degradation", "cell voltage", "cell temp", "hv battery", "12v battery", "battery temperature", "battery voltage", "health"}
STATE_KEYWORDS = {"doors", "windows", "lights", "trunk", "bonnet", "locked", "open", "state", "status", "climate", "climatization", "climate state"}
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
    query_has_vehicle_intent = bool(q_words & VEHICLE_KEYWORDS)
    query_has_battery_intent = bool(q_words & BATTERY_KEYWORDS)
    query_has_state_intent = bool(q_words & STATE_KEYWORDS)
    
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
    # Trip queries
    if query_has_trip_intent and content_type == "trip_summary":
        type_boost = 0.5
    elif query_has_trip_intent and content_type == "charging_event":
        type_boost = -0.4
    elif query_has_trip_intent and content_type == "drive_consumption_summary":
        type_boost = 0.4
    # Charge queries
    if query_has_charge_intent and content_type == "charging_event":
        type_boost = 0.5
    elif query_has_charge_intent and content_type == "trip_summary":
        type_boost = -0.3
    elif query_has_charge_intent and content_type == "charging_session_summary":
        type_boost = 0.5
    elif query_has_charge_intent and content_type == "charging_curve_summary":
        type_boost = 0.4
    # Vehicle info queries
    if query_has_vehicle_intent and content_type == "vehicle_summary":
        type_boost = 1.0
    elif query_has_vehicle_intent and content_type in ("trip_summary", "charging_event"):
        type_boost = -0.5
    # Battery health queries
    if query_has_battery_intent and content_type == "battery_health_summary":
        type_boost = 1.0
    elif query_has_battery_intent and content_type in ("trip_summary", "charging_event"):
        type_boost = -0.5
    # State queries
    if query_has_state_intent and content_type == "vehicle_state_summary":
        type_boost = 1.0

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


# ─── Embedding generation (with provider dispatch + fallback) ─────────────
async def generate_embedding(text: str, provider: str = None) -> Optional[list[float]]:
    """
    Dispatch to the configured embedding provider. On failure, fall back to
    the configured fallback (deterministic by default).
    """
    if not text:
        return None
    provider = (provider or EMBEDDING_PROVIDER).lower()

    # Primary
    if provider in ("gemini", "gemini-embedding-001", "gemini-embedding"):
        result = await text_to_gemini_embedding(text, dim=EMBEDDING_DIM)
        if result is not None:
            return result
        if EMBEDDING_FALLBACK != "gemini":
            logger.warning("gemini-embedding failed, falling back")
            return text_to_deterministic_embedding(text)

    elif provider in ("bge-m3", "bge_m3", "local-bge-m3", "local_bge_m3"):
        result = await text_to_bge_m3_embedding(text)
        if result is not None:
            return result
        return text_to_deterministic_embedding(text)

    # Fallback path
    return text_to_deterministic_embedding(text)


async def generate_batch_embeddings(texts: list[str], provider: str = None) -> list[Optional[list[float]]]:
    """
    Batch dispatch. Uses Gemini batch endpoint when available (up to 100/call).
    """
    if not texts:
        return []
    provider = (provider or EMBEDDING_PROVIDER).lower()

    if provider in ("gemini", "gemini-embedding-001", "gemini-embedding"):
        result = await batch_gemini_embeddings(texts, dim=EMBEDDING_DIM)
        if any(r is not None for r in result):
            # backfill None entries with deterministic so caller never sees gaps
            return [
                r if r is not None else text_to_deterministic_embedding(t)
                for r, t in zip(result, texts)
            ]

    # Fallback / non-gemini
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
                "user_id": str(user_id),
                "vehicle_id": str(vehicle_id) if vehicle_id else None,
                "content_type": content_type,
                "content_id": str(content_id),
                "content_hash": ch,
                "chunk": chunk,
                "embedding": emb_str,
                "metadata": meta_json,
                "provider": EMBEDDING_PROVIDER,
                "model": f"gemini-embedding-001@{EMBEDDING_DIM}",
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
    # Generate query embedding using the same provider as the stored vectors.
    # Falls back gracefully if primary provider fails.
    query_emb = await generate_embedding(query)
    if query_emb is None:
        query_emb = text_to_deterministic_embedding(query)
    emb_str = "[" + ",".join(str(x) for x in query_emb) + "]"

    # Build base WHERE clause
    where_parts = ["user_id = :user_id"]
    if vehicle_ids:
        vid_list = ",".join(f"'{v}'" for v in vehicle_ids)
        where_parts.append(f"vehicle_id IN ({vid_list})")
    base_where = " AND ".join(where_parts)

    # Determine which content types to search
    search_types = content_types or [
        "trip_summary", "charging_event", "vehicle_summary",
        "battery_health_summary", "charging_curve_summary",
        "vehicle_state_summary", "drive_consumption_summary",
        "charging_session_summary", "climate_penalty_summary", "location"
    ]
    fetch_per_type = max(limit * 3, 24)  # summary types need more candidates to overcome low vector similarity

    # Query intent detection
    q_lower = query.lower()
    q_words = set(re.findall(r"\b\w+\b", q_lower))
    is_trip_query = bool(q_words & TRIP_KEYWORDS)
    is_charge_query = bool(q_words & CHARGE_KEYWORDS)
    is_last_query = bool(q_words & {"last", "latest", "most_recent", "previous", "prior"})
    query_has_vehicle_intent = bool(q_words & VEHICLE_KEYWORDS)
    query_has_battery_intent = bool(q_words & BATTERY_KEYWORDS)
    query_has_state_intent = bool(q_words & STATE_KEYWORDS)

    all_rows = []

    # Use subquery pattern per content type to avoid asyncpg HNSW bug.
    # Each inner query computes distance, outer query sorts.
    for ct in search_types:
        inner_sql = text(f"""
            SELECT id, content_type, content_id, content_chunk,
                   1 - (embedding <=> CAST(:embedding AS vector(768))) AS similarity,
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
        elif is_trip_query and chunk_type == "drive_consumption_summary":
            type_boost = 0.8
        elif is_trip_query and chunk_type in ("vehicle_summary", "battery_health_summary",
                                                  "charging_curve_summary", "vehicle_state_summary"):
            type_boost = -0.5
        elif is_charge_query and chunk_type == "charging_event":
            type_boost = 1.0
        elif is_charge_query and chunk_type == "trip_summary":
            type_boost = -0.7
        elif is_charge_query and chunk_type == "charging_session_summary":
            type_boost = 0.9
        elif is_charge_query and chunk_type == "charging_curve_summary":
            type_boost = 0.7
        elif is_charge_query and chunk_type in ("vehicle_summary", "battery_health_summary", "vehicle_state_summary"):
            type_boost = -0.5
        # Vehicle info queries
        elif query_has_vehicle_intent and chunk_type == "vehicle_summary":
            type_boost = 1.5
        # Battery health queries
        elif query_has_battery_intent and chunk_type == "battery_health_summary":
            type_boost = 1.5
        # State queries
        elif query_has_state_intent and chunk_type == "vehicle_state_summary":
            type_boost = 1.5

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