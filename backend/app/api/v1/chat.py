"""
RAG Chat endpoint — /api/v1/chat
Multi-tenant: user can only query their own vehicles' data.
"""
import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Literal

import httpx

from sqlalchemy import text

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_db, get_current_user
from app.services.ai_embeddings import generate_embedding, search_similar
from app.services.valkey_client import get_valkey, get_session_flag, set_session_flag

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])

# ─── LLM providers ──────────────────────────────────────────────────────────────
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

LLM_URLS = {
    "minimax": "https://api.minimax.io/v1/chat/completions",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
    "openai": "https://api.openai.com/v1/chat/completions",
}

LLM_MODELS = {
    "minimax": "MiniMax-M3",
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4o-mini",
}


# ─── Request/Response models ─────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    vehicle_id: str | None = None
    session_id: str | None = None
    provider: Literal["minimax", "gemini", "openai"] = "minimax"


class SourceRef(BaseModel):
    type: str
    id: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceRef] = []
    session_id: str | None = None


# ─── Chat session management ─────────────────────────────────────────────────────


def _build_conversation_context(history: list[dict]) -> str:
    """Build a conversation summary from chat history for LLM context."""
    if not history:
        return ""
    lines = ["Previous conversation (treat as ground truth):"]
    for msg in history[-6:]:  # last 6 messages max
        role = msg.get("role", "?").capitalize()
        content = msg.get("content", "")[:200]
        lines.append(f"- {role}: {content}")
    return "\n".join(lines) + "\n\n"


async def _ensure_chat_tables(db: AsyncSession) -> None:
    """Create chat tables using a separate autocommit connection so DDL doesn't affect main tx."""
    try:
        # Run DDL in full autocommit mode — DDL commits automatically in PostgreSQL
        # and should never share a transaction with our main queries
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
        from app.config import settings

        engine = create_async_engine(settings.database_url, isolation_level="AUTOCOMMIT")
        async with engine.begin() as conn:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id UUID PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """))
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id UUID PRIMARY KEY,
                    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    role VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    sources_json TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_chat_sessions_user ON chat_sessions(user_id)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_chat_messages_session ON chat_messages(session_id)"))
        await engine.dispose()
    except Exception as e:
        logger.warning(f"_ensure_chat_tables: {e}")


async def _get_or_create_session(db: AsyncSession, user_id: str, session_id: str | None) -> str:
    """Return existing session_id or create a new one. Returns session_id string."""
    await _ensure_chat_tables(db)
    if session_id:
        # Verify session belongs to user
        result = await db.execute(
            text("SELECT id FROM chat_sessions WHERE id = :sid AND user_id = :uid"),
            {"sid": session_id, "uid": user_id},
        )
        if result.fetchone():
            return session_id
        # Session not found or wrong user — create new
    new_id = session_id or str(uuid.uuid4())
    try:
        await db.execute(
            text("INSERT INTO chat_sessions (id, user_id) VALUES (:id, :uid) ON CONFLICT DO NOTHING"),
            {"id": new_id, "uid": user_id},
        )
        await db.commit()
    except Exception as e:
        logger.warning(f"_get_or_create_session insert: {e}")
        await db.rollback()
        new_id = str(uuid.uuid4())
        try:
            await db.execute(
                text("INSERT INTO chat_sessions (id, user_id) VALUES (:id, :uid)"),
                {"id": new_id, "uid": user_id},
            )
            await db.commit()
        except Exception as e2:
            logger.warning(f"_get_or_create_session retry: {e2}")
            await db.rollback()
    return new_id


async def _load_session_history(db: AsyncSession, session_id: str) -> list[dict]:
    """Load conversation history for a session, most recent last."""
    try:
        result = await db.execute(
            text("""
                SELECT role, content, sources_json, created_at
                FROM chat_messages
                WHERE session_id = :sid
                ORDER BY created_at ASC
                LIMIT 20
            """),
            {"sid": session_id},
        )
        rows = result.fetchall()
        history = []
        for r in rows:
            msg = {"role": r[0], "content": r[1]}
            if r[2]:
                try:
                    msg["sources"] = json.loads(r[2])
                except Exception:
                    pass
            history.append(msg)
        return history
    except Exception as e:
        logger.warning(f"_load_session_history: {e}")
        return []


async def _save_message(db: AsyncSession, session_id: str, role: str, content: str, sources: list) -> None:
    """Save a single chat message."""
    try:
        sources_json = json.dumps([{"type": s.type, "id": s.id, "score": s.score} for s in sources]) if sources else None
        await db.execute(
            text("""
                INSERT INTO chat_messages (id, session_id, role, content, sources_json)
                VALUES (:id, :sid, :role, :content, :sources_json)
            """),
            {
                "id": str(uuid.uuid4()),
                "sid": session_id,
                "role": role,
                "content": content,
                "sources_json": sources_json,
            },
        )
        await db.execute(
            text("UPDATE chat_sessions SET updated_at = now() WHERE id = :sid"),
            {"sid": session_id},
        )
        await db.commit()
    except Exception as e:
        logger.warning(f"_save_message: {e}")
        try:
            await db.rollback()
        except Exception:
            pass


async def _upload_session_to_s3(session_id: str, user_id: str, messages: list[dict]) -> None:
    """Upload full session to S3 in background — fire and forget."""
    try:
        from app.services.storage import StorageProvider
        storage = StorageProvider()
        if not getattr(storage, "use_s3", False):
            return
        asyncio.create_task(storage.upload_chat_session(session_id, user_id, messages))
    except Exception as e:
        logger.warning(f"_upload_session_to_s3: {e}")


# ─── LLM calls ─────────────────────────────────────────────────────────────────
async def call_llm(
    prompt: str,
    context_chunks: list[dict],
    provider: str = "minimax",
    model: str | None = None,
    conversation_history: list[dict] | None = None,
    detected_vehicle_name_for_llm: str | None = None,
    session_id: str | None = None,
    detected_vehicle_id: str | None = None,
    system_override: str | None = None,
    usage_stats: dict | None = None,
) -> str:
    """
    Call LLM with RAG context + optional conversation history + KV cache.
    Falls back between providers on failure.
    Cache: stored per session in Valkey, invalidated on vehicle change.
    """
    if not prompt.strip():
        return "I didn't receive a message. Please try again."

    # Build context from retrieved chunks
    context_block = ""
    if context_chunks:
        context_lines = []
        for i, chunk in enumerate(context_chunks[:5], 1):
            meta = chunk.get("metadata", {}) or {}
            raw_type = chunk.get("type", "unknown")
            # Source label for display — never expose raw content_type names
            source = meta.get("source") or {
                "trip_summary": "Trip",
                "charging_event": "Charge",
                "vehicle_stats": "Stats",
                "location": "Place",
            }.get(raw_type, raw_type.title())
            context_lines.append(f"[{i}] ({source}) {chunk.get('chunk', '')[:400]}")
        context_block = "Context from your vehicle data:\n" + "\n".join(context_lines) + "\n\n"

    # Build conversation context from history
    conv_block = _build_conversation_context(conversation_history or []) if conversation_history else ""

    system_prompt = system_override or (
        "You are iVDrive AI assistant, an expert in EV telemetry, driving data, and the European EV ecosystem. Answer questions based on the provided vehicle data context, BUT you are also allowed to use your general world knowledge (e.g., to compare charging prices, explain EV concepts, or discuss DC vs AC charging).\n"
        "IMPORTANT RULES:\n"
        "1. When previous conversation is provided, treat it as GROUND TRUTH — the user already confirmed facts there.\n"
        "2. If a previous answer stated something specific (e.g., 'last trip was May 24 at 09:34'), do NOT contradict it unless given new conflicting data.\n"
        "3. If the user asks to verify/confirm a previous answer, check the conversation history first — if the answer was there, confirm it.\n"
        "4. If vehicle context is given at the top (e.g., [Vehicle: BlackMagic]), all data in this question refers to that vehicle unless stated otherwise.\n"
        "5. If the user asks a general industry question (e.g., 'Is 0.37 EUR/kWh good in Europe?'), DO NOT say you cannot answer. Use your world knowledge to answer and provide context.\n"
        "6. Be specific with numbers and dates. Format clearly. Keep concise.\n"
        "7. Never expose internal labels like 'trip_summary', 'charging_event', 'location' in your answer.\n"
        "8. ANOMALY ACKNOWLEDGEMENT: If the data explicitly contains an [ANOMALY: ...] tag, you MUST copy the anomaly warning into your final answer word-for-word. If you see SOH is exactly 95.0%, explicitly warn the user that this is likely a hardcoded/stale default from the Škoda API.\n"
        "9. EFFICIENCY ADVISOR: When discussing energy consumption (kWh/100km), act as an advisor. Correlate the efficiency with the provided average ambient temperature. If temperature is below 10°C, explain that cold weather causes higher consumption due to battery heating and HVAC.\n"
        "10. INTERACTIVE CHARTS: If you are presenting numeric data (e.g., fleet overview, battery health, or trip/charging stats), append a markdown block starting with ```json_chart and ending with ``` containing a JSON object for a Recharts chart. Schema: {\"title\": \"string\", \"type\": \"bar\"|\"line\"|\"pie\"|\"donut\", \"data\": [{\"name\": \"Label\", \"value1\": 10, ...}], \"categories\": [\"value1\", ...]}. Example for battery: {\"title\": \"Battery Metrics\", \"type\": \"bar\", \"data\": [{\"name\": \"SOH\", \"%\": 95}, {\"name\": \"Degradation\", \"%\": 5}], \"categories\": [\"%\"]}. Example for fleet: {\"title\": \"Fleet Capacity\", \"type\": \"bar\", \"data\": [{\"name\": \"BlackMagic\", \"kWh\": 58}, {\"name\": \"JB_RS\", \"kWh\": 77}], \"categories\": [\"kWh\"]}."
    )

    # Inject vehicle context into context_block so LLM knows what vehicle we're discussing
    if context_chunks and detected_vehicle_name_for_llm:
        context_block = "[Vehicle: " + detected_vehicle_name_for_llm + "]\n" + context_block

    user_content = conv_block + context_block + f"Question: {prompt}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    # Try requested provider first, then fall back
    providers = [provider] + [p for p in LLM_URLS if p != provider]
    last_error = ""

    for prov in providers:
        try:
            if prov == "minimax":
                if not MINIMAX_API_KEY:
                    continue
                req_json = {
                    "model": model or LLM_MODELS.get(prov, "MiniMax-M3"),
                    "messages": messages,
                    "temperature": 0.3,
                }
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        LLM_URLS[prov],
                        headers={
                            "Authorization": f"Bearer {MINIMAX_API_KEY}",
                            "Content-Type": "application/json",
                        },
                        json=req_json,
                    )
                    if resp.status_code != 200:
                        last_error = f"minimax {resp.status_code}: {resp.text[:100]}"
                        continue
                    data = resp.json()
                    if usage_stats is not None and "usage" in data:
                        u = data["usage"]
                        usage_stats["prompt_tokens"] = usage_stats.get("prompt_tokens", 0) + u.get("prompt_tokens", 0)
                        usage_stats["completion_tokens"] = usage_stats.get("completion_tokens", 0) + u.get("completion_tokens", 0)
                        usage_stats["cached_tokens"] = usage_stats.get("cached_tokens", 0) + u.get("cached_tokens", 0)
                    answer = data["choices"][0]["message"]["content"]
                    return answer

            elif prov == "gemini":
                if not GEMINI_API_KEY:
                    continue
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        f"{LLM_URLS[prov]}?key={GEMINI_API_KEY}",
                        headers={"Content-Type": "application/json"},
                        json={
                            "contents": [{"parts": [{"text": messages[1]["content"]}]}],
                            "systemInstruction": {"parts": [{"text": system_prompt}]},
                        },
                    )
                    if resp.status_code != 200:
                        last_error = f"gemini {resp.status_code}: {resp.text[:100]}"
                        continue
                    data = resp.json()
                    if usage_stats is not None and "usageMetadata" in data:
                        u = data["usageMetadata"]
                        usage_stats["prompt_tokens"] = usage_stats.get("prompt_tokens", 0) + u.get("promptTokenCount", 0)
                        usage_stats["completion_tokens"] = usage_stats.get("completion_tokens", 0) + u.get("candidatesTokenCount", 0)
                        usage_stats["cached_tokens"] = usage_stats.get("cached_tokens", 0) + u.get("cachedContentTokenCount", 0)
                    return data["candidates"][0]["content"]["parts"][0]["text"]

            elif prov == "openai":
                if not OPENAI_API_KEY:
                    continue
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        LLM_URLS[prov],
                        headers={
                            "Authorization": f"Bearer {OPENAI_API_KEY}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": model or LLM_MODELS.get(prov, "gpt-4o-mini"),
                            "messages": messages,
                            "temperature": 0.3,
                        },
                    )
                    if resp.status_code != 200:
                        last_error = f"openai {resp.status_code}: {resp.text[:100]}"
                        continue
                    data = resp.json()
                    if usage_stats is not None and "usage" in data:
                        u = data["usage"]
                        usage_stats["prompt_tokens"] = usage_stats.get("prompt_tokens", 0) + u.get("prompt_tokens", 0)
                        usage_stats["completion_tokens"] = usage_stats.get("completion_tokens", 0) + u.get("completion_tokens", 0)
                        # openai might have prompt_tokens_details
                    return data["choices"][0]["message"]["content"]

        except Exception as e:
            last_error = f"{prov} exception: {str(e)[:80]}"
            continue

    logger.error(f"All LLM providers failed. Last error: {last_error}")
    return f"I'm having trouble generating a response right now. Please try again in a moment. ({last_error[:60]})"


# ─── Direct DB fallback search (no vector search) ──────────────────────────────
async def direct_db_search(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    vehicle_id: str | None = None,
) -> list[dict]:
    """
    Fallback when embeddings aren't generated yet.
    Searches raw data tables directly using actual iVDrive schema:
    - trips.user_vehicle_id → user_vehicles.id
    - charging_sessions.user_vehicle_id → user_vehicles.id
    """
    try:
        vehicle_filter = f"AND t.user_vehicle_id = :vehicle_id" if vehicle_id else ""
        # Get trip stats
        result = await db.execute(
            text(f"""
                SELECT
                  t.id::text,
                  t.start_date,
                  t.end_date,
                  COALESCE(t.distance_km, 0),
                  COALESCE(t.kwh_consumed, 0),
                  COALESCE(t.avg_temp_celsius, 0),
                  COALESCE(t.start_soc, 0),
                  COALESCE(t.end_soc, 0)
                FROM trips t
                WHERE t.user_vehicle_id IN (SELECT id FROM user_vehicles WHERE user_id = :user_id) {vehicle_filter}
                ORDER BY t.start_date DESC
                LIMIT 5
            """),
            {"user_id": str(user_id), "vehicle_id": vehicle_id},
        )
        trip_chunks = []
        for r in result.fetchall():
            start_str = r[1].strftime("%Y-%m-%d") if r[1] else "?"
            end_str = r[2].strftime("%Y-%m-%d") if r[2] else "?"
            duration_h = 0.0
            if r[1] and r[2]:
                delta = r[2] - r[1]
                duration_h = delta.total_seconds() / 3600
            avg_speed = round(float(r[3]) / max(0.01, duration_h), 1)
            consumption = round(float(r[4]) / max(0.01, float(r[3])), 2) if r[3] and r[3] > 0 else 0
            trip_chunks.append({
                "type": "trip",
                "id": str(r[0]),
                "chunk": (
                    f"Trip from {start_str} to {end_str}: "
                    f"{r[3]}km distance, {r[4]}kWh consumed, avg speed {avg_speed}km/h, "
                    f"temp {r[5]}C, SOC {r[6]}% → {r[7]}%"
                ),
            })

        # Get charging sessions
        charge_filter = f"AND c.user_vehicle_id = :vehicle_id" if vehicle_id else ""
        result2 = await db.execute(
            text(f"""
                SELECT
                  c.id::text,
                  c.session_start,
                  c.session_end,
                  COALESCE(c.energy_kwh, 0),
                  COALESCE(c.start_level, 0),
                  COALESCE(c.end_level, 0),
                  COALESCE(c.charging_type, 'unknown')
                FROM charging_sessions c
                WHERE c.user_vehicle_id IN (SELECT id FROM user_vehicles WHERE user_id = :user_id) {charge_filter}
                ORDER BY c.session_start DESC
                LIMIT 5
            """),
            {"user_id": str(user_id), "vehicle_id": vehicle_id},
        )
        charge_chunks = []
        for r in result2.fetchall():
            start_str = r[1].strftime("%Y-%m-%d") if r[1] else "?"
            delta_soc = (r[5] - r[4]) if r[4] and r[5] else 0
            charge_chunks.append({
                "type": "charging",
                "id": str(r[0]),
                "chunk": (
                    f"Charging session {start_str}: {r[3]}kWh energy, "
                    f"type {r[6]}, SOC {r[4]}% → {r[5]}% "
                    f"(delta {delta_soc}%)"
                ),
            })

        return trip_chunks + charge_chunks
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.warning(f"direct_db_search error: {e}")
        return []


# ─── Query classification ─────────────────────────────────────────────────────────
AGGREGATE_PATTERNS = [
    r"how many", r"\btotal\b", r"sum of", r"count of",
    r"average", r"avg ", r"how much", r"overall ",
    r"longest", r"shortest", r"performance", r"performing",
    r"\boverview\b", r"\bsummary\b", r"\btell me about\b",
    r"\bwhat is.*status\b", r"\bhow.*doing\b",
]
ARITHMETIC_PATTERNS = [
    r"cost", r"spend", r"spent", r"eur", r"kwh total", r"energy total",
    r"distance total", r"total km", r"total distance", r"total cost",
]
TEMPORAL_PATTERNS = [
    r"\blast\b", r"\blatest\b", r"\bmost recent\b",
    r"\bprevious\b", r"\bprior\b", r"\bthis year\b",
    r"\boverview\b", r"\bsummary\b", r"\btell me about\b",
    r"\bwhat is.*status\b", r"\bhow.*doing\b",
]

# Month name → (year, month) for "May 2026" style queries
import re as _re


def extract_date_range(query: str):
    """Extract (from_date, to_date) from query. Returns (None, None) if not found."""
    import calendar
    q = query.lower()
    month_map = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    # Match "in May 2026", "in May", "for May 2026" etc.
    for month_name, month_num in month_map.items():
        # Match month name preceded by word boundary and followed by optional year
        pattern = rf"\b({month_name})\b(?:\s+2026)?"
        m = _re.search(pattern, q)
        if m:
            year = 2026
            last_day = calendar.monthrange(year, month_num)[1]
            from_date = f"{year}-{month_num:02d}-01"
            to_date = f"{year}-{month_num:02d}-{last_day:02d}"
            return from_date, to_date
    # Match "last week"
    if "last week" in q:
        from datetime import datetime, timedelta
        today = datetime(2026, 5, 24)
        start = today - timedelta(days=7)
        return start.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
    # Match "this year"
    if "this year" in q or "2026" in q:
        return "2026-01-01", "2026-12-31"
    return None, None


def is_aggregate_query(query: str) -> bool:
    q = query.lower()
    for p in AGGREGATE_PATTERNS + ARITHMETIC_PATTERNS:
        if _re.search(p, q):
            return True
    return False


def is_temporal_query(query: str) -> bool:
    q = query.lower()
    for p in TEMPORAL_PATTERNS:
        if _re.search(p, q):
            return True
    return False


async def aggregate_db_search(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    vehicle_id: str | None = None,
    conversation_history: list | None = None,
) -> list[dict]:
    """
    Answer arithmetic / aggregate / temporal queries via direct SQL.
    Used for "how many km total", "total charging cost", "last trip", etc.
    Wraps each query in its own error handler so one failure doesn't abort the session.
    """
    q = query.lower()
    vid_subq = "(SELECT id FROM user_vehicles WHERE user_id = :uid)"
    vid_filter = f"AND t.user_vehicle_id = :vid" if vehicle_id else ""
    cid_filter = f"AND c.user_vehicle_id = :vid" if vehicle_id else ""

    from_date, to_date = extract_date_range(query)
    date_filter_t = f"AND t.start_date >= :from_dt AND t.start_date <= :to_dt" if from_date else ""
    date_filter_c = f"AND c.session_start >= :from_dt AND c.session_start <= :to_dt" if from_date else ""

    base_params = {"uid": str(user_id), "vid": vehicle_id} if vehicle_id else {"uid": str(user_id)}
    if from_date:
        from datetime import datetime as _dt
        base_params = {"uid": str(user_id), "vid": vehicle_id, **base_params} if vehicle_id else {"uid": str(user_id)}
        base_params["from_dt"] = _dt.strptime(from_date + " 00:00:00", "%Y-%m-%d %H:%M:%S")
        base_params["to_dt"] = _dt.strptime(to_date + " 23:59:59", "%Y-%m-%d %H:%M:%S")
    else:
        if vehicle_id:
            base_params = {"uid": str(user_id), "vid": vehicle_id}
        else:
            base_params = {"uid": str(user_id)}

    def _period() -> str:
        """Return period suffix: month (2026-05) for month ranges, year (2026) for full-year."""
        if not from_date:
            return ""
        if from_date == f"{from_date[:4]}-01-01" and to_date and to_date.startswith(from_date[:4]):
            return f" in {from_date[:4]}"
        return f" in {from_date[:7]}"
    if from_date:
        from datetime import datetime as _dt
        base_params = {"uid": str(user_id), "vid": vehicle_id, **base_params} if vehicle_id else {"uid": str(user_id)}
        base_params["from_dt"] = _dt.strptime(from_date + " 00:00:00", "%Y-%m-%d %H:%M:%S")
        base_params["to_dt"] = _dt.strptime(to_date + " 23:59:59", "%Y-%m-%d %H:%M:%S")
    else:
        if vehicle_id:
            base_params = {"uid": str(user_id), "vid": vehicle_id}
        else:
            base_params = {"uid": str(user_id)}

    chunks = []

    async def _run(sql: text, params: dict) -> list:
        """Execute a query, rollback on error, return list of rows."""
        try:
            result = await db.execute(sql, params)
            return result.fetchall()
        except Exception as e:
            logger.warning(f"aggregate_db_search query error: {e}")
            try:
                await db.rollback()
            except Exception:
                pass
            return []

    # ── Overview handler — comprehensive stats for "overview"/"summary" queries ──
    is_overview_query = any(k in q for k in ["overview", "summary", "tell me about", "status"])
    if is_overview_query and vehicle_id:
        # All-time trip stats
        rows = await _run(text(f"""
            SELECT
                COUNT(*)::int AS trip_count,
                COALESCE(SUM(t.distance_km), 0)::float AS total_km,
                COALESCE(SUM(t.kwh_consumed), 0)::float AS total_kwh,
                COALESCE(AVG(t.avg_temp_celsius), 0)::float AS avg_temp,
                MAX(t.start_date) AS last_trip
            FROM trips t
            WHERE t.user_vehicle_id = :vid AND t.end_date IS NOT NULL
        """), {"vid": vehicle_id})
        if rows and rows[0]:
            r = rows[0]
            last_trip_str = r[4].strftime("%Y-%m-%d") if r[4] else "?"
            chunks.append({
                "type": "trip_summary",
                "id": "aggregate",
                "chunk": (
                    f"Total: {r[0]} trips, {r[1]:.0f} km, {r[2]:.1f} kWh consumed, "
                    f"avg temp {r[3]:.1f}°C, last trip {last_trip_str}"
                ),
            })

        # All-time charging stats
        rows2 = await _run(text(f"""
            SELECT
                COUNT(*)::int AS charge_count,
                COALESCE(SUM(c.energy_kwh), 0)::float AS total_kwh,
                COALESCE(SUM(COALESCE(c.actual_cost_eur, c.base_cost_eur)), 0)::float AS total_cost,
                MAX(c.session_start) AS last_charge
            FROM charging_sessions c
            WHERE c.user_vehicle_id = :vid AND c.session_end IS NOT NULL
        """), {"vid": vehicle_id})
        if rows2 and rows2[0]:
            r2 = rows2[0]
            last_charge_str = r2[3].strftime("%Y-%m-%d") if r2[3] else "?"
            chunks.append({
                "type": "charging_event",
                "id": "aggregate",
                "chunk": (
                    f"Charging: {r2[0]} sessions, {r2[1]:.1f} kWh total, "
                    f"€{r2[2]:.2f} total cost, last charge {last_charge_str}"
                ),
            })

    # ── Trip aggregates ──────────────────────────────────────────────────────
    # Also trigger for "performance"/"performing" queries (implicit distance/trip interest)
    # For "performance"/"performing" queries with a specific vehicle, add implicit distance/kwh triggers
    is_perf_query = any(k in q for k in ["performance", "performing", "review"])
    trip_numeric = any(k in q for k in ["km", "distance", "drive", "trip", "longest", "shortest", "average"]) or (is_perf_query and vehicle_id)
    if trip_numeric:
        # Total distance
        dist_specific = any(p in q for p in ["total km", "total distance", "how many km", "distance total", "overall km"])
        dist_implicit = is_perf_query and vehicle_id  # "BlackMagic performance review" → total distance
        if dist_specific or dist_implicit:
            rows = await _run(text(f"""
                SELECT COALESCE(SUM(distance_km), 0)::float, COUNT(*)::int, COALESCE(AVG(distance_km), 0)::float
                FROM trips t
                WHERE t.user_vehicle_id IN {vid_subq} {vid_filter} {date_filter_t}
            """), base_params)
            if rows:
                r = rows[0]
                
                chunks.append({
                    "type": "trip_summary",
                    "id": "aggregate",
                    "chunk": (
                        f"Total distance driven{_period()}: {r[0]:.1f} km across {r[1]} trips "
                        f"(avg {r[2]:.1f} km per trip)"
                    ),
                })

        # Longest trip
        if any(k in q for k in ["longest trip", "longest distance", "max km"]):
            rows = await _run(text(f"""
                SELECT COALESCE(t.distance_km, 0)::float, t.start_date, COALESCE(t.avg_temp_celsius, 0)::float, v.display_name
                FROM trips t
                JOIN user_vehicles v ON v.id = t.user_vehicle_id
                WHERE t.user_vehicle_id IN {vid_subq} {vid_filter} {date_filter_t}
                ORDER BY t.distance_km DESC NULLS LAST LIMIT 1
            """), base_params)
            if rows:
                r = rows[0]
                date_str = r[1].strftime("%Y-%m-%d") if r[1] else "?"
                chunks.append({
                    "type": "trip_summary",
                    "id": "aggregate",
                    "chunk": (
                        f"Longest trip: {r[0]:.0f} km on {date_str} with {r[3]} "
                        f"(avg temp {r[2]:.1f}°C)"
                    ),
                })

        # Trip count
        trip_specific = any(p in q for p in ["how many trips", "number of trips", "count of trips"])
        trip_implicit = is_perf_query and vehicle_id
        if trip_specific or trip_implicit:
            rows = await _run(text(f"""
                SELECT COUNT(*)::int, COALESCE(SUM(distance_km), 0)::float
                FROM trips t
                WHERE t.user_vehicle_id IN {vid_subq} {vid_filter} {date_filter_t}
            """), base_params)
            if rows:
                r = rows[0]
                
                chunks.append({
                    "type": "trip_summary",
                    "id": "aggregate",
                    "chunk": f"Total trips{_period()}: {r[0]} trips covering {r[1]:.1f} km",
                })

        # Average speed across trips (computed: distance_km * 3600 / duration_sec, capped at 200 km/h)
        if any(p in q for p in ["average speed", "avg speed", "average velocity"]):
            rows = await _run(text(f"""
                SELECT COALESCE(AVG(
                    CASE WHEN t.distance_km > 0 AND t.end_date > t.start_date
                    THEN LEAST(t.distance_km * 3600.0 / NULLIF(EXTRACT(EPOCH FROM (t.end_date - t.start_date)), 0), 200)
                    END), 0)::float, COUNT(*)::int
                FROM trips t
                WHERE t.user_vehicle_id IN {vid_subq} {vid_filter} {date_filter_t}
                AND t.distance_km > 0 AND t.end_date > t.start_date
            """), base_params)
            if rows:
                r = rows[0]
                if r[1] > 0:
                    
                    chunks.append({
                        "type": "trip_summary",
                        "id": "aggregate",
                        "chunk": f"Average trip speed{_period()}: {r[0]:.1f} km/h across {r[1]} trips with recorded speed",
                    })

    # ── Charging aggregates ────────────────────────────────────────────────────
    charge_numeric = any(k in q for k in ["charge", "kwh", "energy", "charging", "battery"]) or (is_perf_query and vehicle_id)
    if charge_numeric:
        # Total charging energy
        energy_specific = any(p in q for p in ["kwh total", "energy total", "total energy", "total kwh",
                                           "how many kwh", "total charging energy"])
        energy_implicit = is_perf_query and vehicle_id
        if energy_specific or energy_implicit:
            rows = await _run(text(f"""
                SELECT COALESCE(SUM(energy_kwh), 0)::float, COUNT(*)::int, COALESCE(AVG(energy_kwh), 0)::float
                FROM charging_sessions c
                WHERE c.user_vehicle_id IN {vid_subq} {cid_filter} {date_filter_c}
            """), base_params)
            if rows:
                r = rows[0]
                
                chunks.append({
                    "type": "charging_event",
                    "id": "aggregate",
                    "chunk": (
                        f"Total charging energy{_period()}: {r[0]:.1f} kWh across {r[1]} sessions "
                        f"(avg {r[2]:.1f} kWh per session)"
                    ),
                })

        # Charging cost — check if this is a follow-up "that cost" question (no vehicle specified)
        # Extract vehicle name from conversation history to scope the query correctly
        hist_vehicle = None
        logger.info(f"hist_vehicle detection: history={[(m.get('role'), m.get('content','')[:50]) for m in (conversation_history or [])]}")
        if conversation_history and not vehicle_id:
            for msg in reversed(conversation_history[-4:]):
                c = msg.get("content", "")
                logger.info(f"  msg role={msg.get('role')}, content={c[:80]}")
                if any(v in c for v in ["BlackMagic", "Enyaq", "Elroq", "Enyac", "JB RS"]):
                    for v in ["BlackMagic", "Enyaq", "Elroq", "Enyac", "JB RS"]:
                        if v in c:
                            hist_vehicle = v
                            logger.info(f"  -> hist_vehicle={hist_vehicle}")
                            break
                    if hist_vehicle:
                        break

        is_follow_up_cost = (
            any(k in q for k in ["cost", "spend", "spent", "eur", "price"]) and
            len(conversation_history or []) > 0 and
            not vehicle_id and
            not any(k in q for k in ["total", "all", "month", "year", "may", "april", "march"])
        )
        
        # DEBUG: inject diagnostic chunk
        diag_lines = [
            f"[DEBUG] q={q[:60]}, hist={len(conversation_history or [])}, vid={vehicle_id}",
            f"[DEBUG] hist_vehicle={hist_vehicle}, is_follow_up={is_follow_up_cost}",
            f"[DEBUG] history: {[(m.get('role'), m.get('content','')[:40]) for m in (conversation_history or [])[-4:]]}",
        ]
        chunks.append({"type": "debug", "id": "diag", "chunk": " | ".join(diag_lines)})
        if is_follow_up_cost:
            logger.info(f"is_follow_up_cost=True, hist_vehicle={hist_vehicle}")
            # Build filter for specific vehicle if detected from history
            vid_filter = f"AND v.display_name ILIKE :hveh" if hist_vehicle else ""
            lookup_params = {"uid": str(user_id)}
            if hist_vehicle:
                lookup_params["hveh"] = f"%{hist_vehicle}%"
            rows = await _run(text(f"""
                SELECT c.session_start, COALESCE(c.actual_cost_eur, 0), COALESCE(c.base_cost_eur, 0),
                       v.display_name
                FROM charging_sessions c
                JOIN user_vehicles v ON v.id = c.user_vehicle_id
                WHERE c.user_vehicle_id IN {vid_subq} {vid_filter}
                ORDER BY c.session_start DESC LIMIT 1
            """), lookup_params)
            logger.info(f"follow_up_cost rows: {rows}")
            
            def _add_cost_chunk(r):
                cost_val = r[1] if r[1] else r[2]
                if cost_val:
                    date_str = r[0].strftime("%Y-%m-%d at %H:%M") if r[0] else "last session"
                    chunks.append({
                        "type": "charging_event", "id": "last_cost",
                        "chunk": f"Last charging ({r[3]}, {date_str}): €{cost_val:.2f}",
                    })
                    return True
                return False
            
            added = False
            if rows:
                r = rows[0]
                logger.info(f"follow_up_cost: cost_val={r[1] if r[1] else r[2]}, name={r[3]}")
                added = _add_cost_chunk(r)
            
            if not added:
                # No cost on last session — look for last session WITH cost
                if hist_vehicle:
                    # Vehicle-specific: last session with cost for this vehicle
                    rows2 = await _run(text(f"""
                        SELECT c.session_start, COALESCE(c.actual_cost_eur, 0), COALESCE(c.base_cost_eur, 0),
                               v.display_name
                        FROM charging_sessions c
                        JOIN user_vehicles v ON v.id = c.user_vehicle_id
                        WHERE c.user_vehicle_id IN {vid_subq} AND v.display_name ILIKE :hveh
                          AND COALESCE(c.actual_cost_eur, c.base_cost_eur) > 0
                        ORDER BY c.session_start DESC LIMIT 1
                    """), {"uid": str(user_id), "hveh": f"%{hist_vehicle}%"})
                    if rows2:
                        added = _add_cost_chunk(rows2[0])
                
                if not added and not hist_vehicle:
                    # General: last session with cost across all vehicles
                    rows3 = await _run(text(f"""
                        SELECT c.session_start, COALESCE(c.actual_cost_eur, 0), COALESCE(c.base_cost_eur, 0),
                               v.display_name
                        FROM charging_sessions c
                        JOIN user_vehicles v ON v.id = c.user_vehicle_id
                        WHERE c.user_vehicle_id IN {vid_subq}
                          AND COALESCE(c.actual_cost_eur, c.base_cost_eur) > 0
                        ORDER BY c.session_start DESC LIMIT 1
                    """), {"uid": str(user_id)})
                    if rows3:
                        added = _add_cost_chunk(rows3[0])
        elif any(k in q for k in ["cost", "spend", "spent", "eur", "price"]):
            rows = await _run(text(f"""
                SELECT COALESCE(SUM(COALESCE(c.actual_cost_eur, c.base_cost_eur)), 0)::float,
                       COALESCE(SUM(base_cost_eur), 0)::float, COUNT(*)::int
                FROM charging_sessions c
                WHERE c.user_vehicle_id IN {vid_subq} {cid_filter} {date_filter_c}
            """), base_params)
            if rows:
                r = rows[0]
                
                chunks.append({
                    "type": "charging_event",
                    "id": "aggregate",
                    "chunk": (
                        f"Total charging cost{_period()}: €{r[0]:.2f} across {r[2]} sessions "
                        f"(list price €{r[1]:.2f})"
                    ),
                })

        # Charging count
        if any(p in q for p in ["how many times", "number of charges", "count of charge", "charging count", "charging sessions", "charging session", "how many charging", "how many sessions"]):
            rows = await _run(text(f"""
                SELECT COUNT(*)::int
                FROM charging_sessions c
                WHERE c.user_vehicle_id IN {vid_subq} {cid_filter} {date_filter_c}
            """), base_params)
            if rows:
                r = rows[0]
                
                chunks.append({
                    "type": "charging_event",
                    "id": "aggregate",
                    "chunk": f"Total charging sessions{_period()}: {r[0]} sessions",
                })

    # ── Last / most recent trip ──────────────────────────────────────────────
    trip_params = {"uid": str(user_id), "vid": vehicle_id} if vehicle_id else {"uid": str(user_id)}
    if is_temporal_query(q) and any(k in q for k in ["trip", "drive", "distance"]):
        rows = await _run(text(f"""
            SELECT t.start_date, t.distance_km, COALESCE(t.kwh_consumed, 0)::float, COALESCE(t.avg_temp_celsius, 0)::float,
                   COALESCE(t.start_soc, 0)::int, COALESCE(t.end_soc, 0)::int, v.display_name
            FROM trips t
            JOIN user_vehicles v ON v.id = t.user_vehicle_id
            WHERE t.user_vehicle_id IN {vid_subq} {vid_filter}
            ORDER BY t.start_date DESC LIMIT 1
        """), trip_params)
        if rows:
            r = rows[0]
            date_str = r[0].strftime("%Y-%m-%d %H:%M") if r[0] else "?"
            chunks.append({
                "type": "trip_summary",
                "id": "aggregate",
                "chunk": (
                    f"Most recent trip: {r[6]} on {date_str}, "
                    f"distance {r[1]:.1f}km, consumed {r[2]:.2f}kWh, "
                    f"SOC {r[4]}% → {r[5]}%, avg temp {r[3]:.1f}°C"
                ),
            })

    # ── Last / most recent charging ──────────────────────────────────────────
    # Run temporal for: "when did I last charge", "last charging session", etc.
    # Always include cost (base_cost_eur) in temporal — even if not explicitly asked, the LLM
    # needs it for follow-up "how much did that cost?" questions (conversation carry-forward)
    if is_temporal_query(q) and any(k in q for k in ["charge", "charging", "kwh"]):
        charge_params = {"uid": str(user_id), "vid": vehicle_id} if vehicle_id else {"uid": str(user_id)}
        rows = await _run(text(f"""
            SELECT c.session_start, COALESCE(c.energy_kwh, 0)::float, COALESCE(c.charging_type, 'unknown')::text,
                   COALESCE(c.start_level, 0)::float, COALESCE(c.end_level, 0)::float,
                   COALESCE(c.actual_cost_eur, 0)::float, COALESCE(c.base_cost_eur, 0)::float, v.display_name
            FROM charging_sessions c
            JOIN user_vehicles v ON v.id = c.user_vehicle_id
            WHERE c.user_vehicle_id IN {vid_subq} {cid_filter}
            ORDER BY c.session_start DESC LIMIT 1
        """), charge_params)
        if rows:
            r = rows[0]
            date_str = r[0].strftime("%Y-%m-%d %H:%M") if r[0] else "?"
            cost_val = r[5] if r[5] else (r[6] if r[6] else 0)
            cost_str = f", €{cost_val:.2f}" if cost_val else ""
            chunks.append({
                "type": "charging_event",
                "id": "aggregate",
                "chunk": (
                    f"Most recent charging: {r[6]} on {date_str}, "
                    f"{r[1]:.1f}kWh ({r[2]}), SOC {r[3]:.0f}% → {r[4]:.0f}%{cost_str}"
                ),
            })

    return chunks


# ─── Chat endpoint ──────────────────────────────────────────────────────────────
@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    RAG chat endpoint. Authenticates user, retrieves relevant vehicle data
    chunks via vector search, constructs prompt, calls LLM, returns answer.
    Supports conversation sessions: pass session_id to continue a conversation.
    """
    from sqlalchemy import text
    import httpx
    from app.services.chat_tools import route_intent_via_llm, dispatch_tool_call_extended
    from app.services.ai_gate import check_ai_access, log_ai_usage

    user_id = user.id

    # ── AI Premium gate ──────────────────────────────────────────────────────
    gate = await check_ai_access(db, str(user_id))
    if not gate.allowed:
        reason_msg = {
            "disabled": "Your AI Assistant is currently disabled.",
            "daily_cap": f"You've used {gate.used_today}/{gate.effective_max_per_day} AI questions today. Resets at UTC midnight.",
            "monthly_cap": f"You've used {gate.used_this_month}/{gate.effective_max_per_month} AI questions this month.",
        }.get(gate.reason, "AI Assistant not available.")
        hint = ""
        if gate.reason in ("daily_cap", "monthly_cap") and gate.tier == "free":
            hint = " Ask an admin to upgrade your tier to continue."
        await log_ai_usage(
            db, user_id=str(user_id), vehicle_id=None, session_id=None,
            model_provider="blocked", model_name=None,
            prompt_tokens=None, completion_tokens=None, cached_tokens=None,
            estimated_cost_usd=0, blocked_reason=gate.reason or "unknown",
            question_chars=len(req.message),
        )
        return ChatResponse(
            answer=f"{reason_msg}{hint}",
            sources=[],
            session_id=None,
        )

    # Override provider with the tier-mandated one. Admin controls this.
    req_provider = gate.model_provider
    # (ChatRequest is a Pydantic model without a `model` field; we pass it
    # directly into call_llm below, where it has the final say.)

    # Step 0: Session management — get or create session, load history
    session_id = await _get_or_create_session(db, str(user_id), req.session_id)
    history = await _load_session_history(db, session_id)
    logger.info(f"chat session {session_id}: {len(history)} history messages")

    # Step 1: Get user's vehicle IDs and display names for vehicle-name detection
    vehicle_result = await db.execute(
        text("SELECT id, display_name FROM user_vehicles WHERE user_id = :user_id"),
        {"user_id": str(user_id)},
    )
    vehicle_rows = vehicle_result.fetchall()
    if not vehicle_rows:
        return ChatResponse(answer="You have no vehicles connected yet.", sources=[])

    user_vehicle_ids = [str(row[0]) for row in vehicle_rows]
    user_vehicle_names = [row[1] for row in vehicle_rows]
    # Build name→id map for vehicle-name detection (case-insensitive)
    vehicle_name_to_id = {row[1].lower(): row[0] for row in vehicle_rows}

    # Step 2: Detect vehicle from query if not explicitly filtered.
    # Sets BOTH detected_vehicle_id AND detected_vehicle_name in one pass.
    detected_vehicle_id = None
    detected_vehicle_name = None
    if not req.vehicle_id:
        q_lower = req.message.lower()
        q_words = set(_re.split(r"[\s,.!?;:+-]+", q_lower))
        for name, v_id in vehicle_name_to_id.items():
            name_norm = name.replace('_', ' ').replace('-', ' ')
            name_words = set(name_norm.split())
            matched = name_words <= q_words
            if matched:
                detected_vehicle_id = v_id
                detected_vehicle_name = name
                logger.info(f"Vehicle detected: '{name}' (id={v_id}) words={name_words} q_words={q_words}")
                break

    # Multi-turn fallback: if the current message does NOT mention a vehicle name
    # (e.g. follow-up "how much did that cost?", "what about the last trip?"),
    # try to recover the vehicle from the most recent assistant turn that
    # mentioned one. This unblocks the agentic router, which otherwise has no
    # way to resolve pronouns and ends up refusing the question.
    if not detected_vehicle_name and not req.vehicle_id and history:
        # Walk backwards through history looking for a vehicle name in either
        # the user message OR the assistant response. Assistant turns are more
        # reliable because they always contain the chosen vehicle name.
        for msg in reversed(history[-6:]):
            content = msg.get("content", "") or ""
            content_lower = content.lower()
            for name, v_id in vehicle_name_to_id.items():
                name_norm = name.replace('_', ' ').replace('-', ' ').lower()
                # Word-boundary check (case-insensitive) so we don't false-match
                # "Enyaq" inside "Enyaq_v3" when looking for "Enyaq" etc.
                if _re.search(r"\b" + _re.escape(name_norm) + r"\b", content_lower):
                    detected_vehicle_id = v_id
                    detected_vehicle_name = name
                    logger.info(
                        f"Vehicle resolved from history ({msg.get('role')}): "
                        f"'{name}' (id={v_id})"
                    )
                    break
            if detected_vehicle_name:
                break

    # Explicit filter only; detected_vehicle_id is used for aggregate DB search + post-filtering.
    # NOT passed to search_similar SQL because ai_embeddings.vehicle_id is only populated for
    # vehicle_stats type — trip_summary / charging_event chunks have NULL vehicle_id and
    # would be silently dropped. Instead we use post-filtering (Step 5).
    vehicle_ids = ([uuid.UUID(req.vehicle_id)] if req.vehicle_id and req.vehicle_id in user_vehicle_ids else None)

    # Step 3: Check if query needs direct DB aggregation via Agentic Intent Routing
    chunks = []
    agg_chunks = []
    effective_vid = req.vehicle_id if req.vehicle_id and req.vehicle_id in user_vehicle_ids else (
        str(detected_vehicle_id) if detected_vehicle_id else None)

    # Phase 1: Native Function Calling Route
    logger.info("Routing query to LLM tool dispatcher...")
    
    usage_stats = {"prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0}

    max_loops = 3
    # Pass conversation history so the router can resolve "that" / "it" / "the last one"
    # in follow-up questions. Also pass detected_vehicle_name as a hint.
    tool_calls = await route_intent_via_llm(
        req.message,
        user_vehicle_names,
        call_llm,
        conversation_history=history,
        detected_vehicle_name=detected_vehicle_name,
        usage_stats=usage_stats,
    )
    
    for _ in range(max_loops):
        logger.info(f"LLM tool router decided to call: {tool_calls}")
        if not tool_calls:
            break
            
        executed_any = False
        sql_error = None
        
        for tool_call in tool_calls:
            if "vehicle_name" in tool_call.get("args", {}) and not tool_call["args"]["vehicle_name"]:
                tool_call["args"]["vehicle_name"] = detected_vehicle_name or ""
                
            chunk = await dispatch_tool_call_extended(db, user_id, tool_call)
            if chunk:
                executed_any = True
                agg_chunks.append(chunk)
                
                # Check for SQL error to trigger healing
                if chunk["type"] == "sql_result" and "SQL_ERROR:" in chunk["chunk"]:
                    sql_error = chunk["chunk"]
                # Schema triggers a secondary LLM call to write the SQL
                elif chunk["type"] == "schema":
                    sql_error = f"SCHEMA LOADED: {chunk['chunk']}\nNow write the SQL query based on this schema to answer the user's question."

        if sql_error:
            # Re-feed the error/schema back to the LLM to get a new tool call
            logger.info("Triggering Agentic Healing/Follow-up Loop...")
            follow_up_prompt = req.message + "\n\nPREVIOUS TOOL RESULT:\n" + sql_error
            tool_calls = await route_intent_via_llm(
                follow_up_prompt,
                user_vehicle_names,
                call_llm,
                conversation_history=history,
                detected_vehicle_name=detected_vehicle_name,
                usage_stats=usage_stats,
            )
        else:
            break

    logger.info(f"agentic_tools returned {len(agg_chunks)} chunks")
    for i, c in enumerate(agg_chunks[:3]):
        logger.info(f"  agg_chunk[{i}]: type={c.get('type')} id={c.get('id')} text={c.get('chunk','')[:100]}")

    # Inject vehicle name into aggregate chunks so LLM knows the result is vehicle-specific
    if effective_vid and detected_vehicle_name and agg_chunks:
        # Prepend vehicle name to each aggregate chunk
        vname = next((row[1] for row in vehicle_rows if str(row[0]) == str(effective_vid)), detected_vehicle_name)
        for c in agg_chunks:
            if c.get("id") == "aggregate":
                c["chunk"] = f"{vname}: {c['chunk']}"

    # Step 4: Run vector search WITHOUT vehicle_ids filter (to keep all trip/charging chunks)
    vec_chunks = await search_similar(
        db=db,
        user_id=user_id,
        query=req.message,
        content_types=["trip_summary", "charging_event", "vehicle_stats", "location"],
        vehicle_ids=vehicle_ids,  # Only explicit filter from request
        limit=12,
        provider=req.provider,
    )
    logger.info(f"vector search returned {len(vec_chunks)} chunks")

    # Step 5: Post-filter vector chunks by detected vehicle name.
    # Be permissive: if a chunk mentions a DIFFERENT vehicle, drop it.
    # If no vehicle name in chunk (NULL vehicle_id in DB), keep it as generic context.
    # Only drop chunks that explicitly mention a different vehicle.
    if detected_vehicle_name and not vehicle_ids:
        vid_str = str(detected_vehicle_id)
        # Build set of current user's vehicle name words for dynamic filtering
        current_vehicle_names = {row[1].lower() for row in vehicle_rows}
        # Normalize detected name for exclusion
        detected_words = set(detected_vehicle_name.lower().replace('_', ' ').replace('-', ' ').split())

        def _chunk_is_other_vehicle(c: dict) -> bool:
            chunk_lower = c.get("chunk", "").lower()
            meta_str = str(c.get("metadata") or {}).lower()
            # Drop if chunk mentions a vehicle name that is NOT the detected one
            # and not a substring of the detected name
            for veh_name in current_vehicle_names:
                if veh_name == detected_vehicle_name.lower():
                    continue
                # Check if any word from this vehicle name appears in chunk
                veh_words = set(veh_name.replace('_', ' ').replace('-', ' ').split())
                # Only filter if significant words (len > 2) match
                significant = {w for w in veh_words if len(w) > 2}
                if significant and significant <= set(chunk_lower.split()):
                    return True
            return False

        before = len(vec_chunks)
        vec_chunks = [c for c in vec_chunks if not _chunk_is_other_vehicle(c)]
        logger.info(f"post-filtered to {len(vec_chunks)}/{before} chunks for vehicle '{detected_vehicle_name}'")

        # Inject vehicle name into remaining vector chunks so LLM knows they're for this vehicle
        vname_cap = detected_vehicle_name  # e.g. "BlackMagic"
        for c in vec_chunks:
            if c.get("chunk") and not c["chunk"].startswith(vname_cap):
                c["chunk"] = f"{vname_cap}: {c['chunk']}"

    # Step 5b: If aggregate data was found for the detected vehicle, prepend it to vector chunks
    # so the LLM has authoritative data first (avoids hallucination from sparse vector results)
    if agg_chunks and detected_vehicle_name and not vehicle_ids:
        # Check if agg_chunks already contain vehicle name prefix
        has_vehicle_prefix = any(
            c.get("chunk", "").lower().startswith(detected_vehicle_name.lower() + ":")
            for c in agg_chunks if c.get("id") == "aggregate"
        )
        if not has_vehicle_prefix:
            for c in agg_chunks:
                if c.get("id") == "aggregate" and c.get("chunk"):
                    c["chunk"] = f"{detected_vehicle_name}: {c['chunk']}"

    # Combine: aggregate data first (for correct numbers), then semantic context
    chunks = agg_chunks + vec_chunks

    # Step 6: If no results at all, fall back to direct DB
    if not chunks:
        chunks = await direct_db_search(db, user_id, req.message, effective_vid)
        logger.info(f"direct_db_search returned {len(chunks)} chunks")

    # Step 7: Call LLM with conversation history. Provider/model come from the gate.
    answer = await call_llm(
        req.message, chunks,
        provider=req_provider,
        model=gate.model_name or req.model,
        conversation_history=history,
        detected_vehicle_name_for_llm=detected_vehicle_name,
        session_id=session_id,
        detected_vehicle_id=str(detected_vehicle_id) if detected_vehicle_id else None,
        usage_stats=usage_stats,
    )

    # Compute estimated cost based on the total token usage
    estimated_cost_usd = 0.0
    try:
        provider_key = req_provider.lower()
        # Pricing per 1M tokens (input / output). Cached tokens typically cost half or less.
        PRICING = {
            "minimax": {"input": 0.6, "output": 2.4},  # MiniMax-M3
            "gemini": {"input": 1.25, "output": 5.0},   # Gemini 1.5 Pro
            "openai": {"input": 0.15, "output": 0.6},   # GPT-4o-mini
        }
        prices = PRICING.get(provider_key, {"input": 0, "output": 0})
        
        p_toks = usage_stats.get("prompt_tokens", 0)
        c_toks = usage_stats.get("completion_tokens", 0)
        ca_toks = usage_stats.get("cached_tokens", 0)
        
        cost_in = (p_toks / 1000000.0) * prices["input"]
        cost_out = (c_toks / 1000000.0) * prices["output"]
        cost_cached = (ca_toks / 1000000.0) * (prices["input"] * 0.5)
        estimated_cost_usd = cost_in + cost_out + cost_cached
    except Exception as e:
        logger.warning(f"Cost calculation failed: {e}")

    # Log the successful request to ai_usage_log
    try:
        from app.services.ai_gate import log_ai_usage
        await log_ai_usage(
            db, user_id=str(user_id),
            vehicle_id=str(detected_vehicle_id) if detected_vehicle_id else None,
            session_id=session_id,
            model_provider=req_provider,
            model_name=gate.model_name or None,
            prompt_tokens=usage_stats.get("prompt_tokens"), 
            completion_tokens=usage_stats.get("completion_tokens"), 
            cached_tokens=usage_stats.get("cached_tokens"),
            estimated_cost_usd=estimated_cost_usd,
            blocked_reason=None,
            question_chars=len(req.message),
        )
    except Exception as _e:
        logger.warning(f"post-call usage log failed: {_e}")

    # Step 8: Build source references (exclude aggregate chunks from sources)
    sources = [
        SourceRef(type=c["type"], id=c["id"], score=c["score"])
        for c in chunks[:5]
        if c.get("score", 0) > 0.6 and c.get("id") != "aggregate"
    ]

    # Step 9: Persist messages to DB (fire-and-forget S3 backup)
    await _save_message(db, session_id, "user", req.message, [])
    await _save_message(db, session_id, "assistant", answer, sources)
    # Upload full session to S3 in background
    updated_history = history + [
        {"role": "user", "content": req.message},
        {"role": "assistant", "content": answer},
    ]
    asyncio.create_task(_upload_session_to_s3(session_id, str(user_id), updated_history))

    return ChatResponse(answer=answer, sources=sources, session_id=session_id)

# ─── Session management endpoints ─────────────────────────────────────────────

@router.get("/sessions", response_model=list[dict])
async def list_sessions(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all chat sessions for current user, newest first."""
    from sqlalchemy import text
    await _ensure_chat_tables(db)
    result = await db.execute(text("""
        SELECT s.id, s.created_at, s.updated_at,
               COUNT(m.id) as message_count,
               MAX(m.created_at) as last_message_at
        FROM chat_sessions s
        LEFT JOIN chat_messages m ON m.session_id = s.id
        WHERE s.user_id = :uid
        GROUP BY s.id
        ORDER BY s.updated_at DESC
        LIMIT 20
    """), {"uid": str(user.id)})
    return [
        {
            "id": str(row[0]),
            "created_at": row[1].isoformat() if row[1] else None,
            "updated_at": row[2].isoformat() if row[2] else None,
            "message_count": row[3],
            "last_message_at": row[4].isoformat() if row[4] else None,
        }
        for row in result.fetchall()
    ]


@router.get("/sessions/{session_id}", response_model=dict)
async def get_session(
    session_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all messages in a session."""
    from sqlalchemy import text
    await _ensure_chat_tables(db)
    # Verify ownership
    result = await db.execute(text(
        "SELECT id FROM chat_sessions WHERE id = :sid AND user_id = :uid"
    ), {"sid": session_id, "uid": str(user.id)})
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Session not found")
    
    msgs = await db.execute(text("""
        SELECT role, content, created_at
        FROM chat_messages
        WHERE session_id = :sid
        ORDER BY created_at ASC
    """), {"sid": session_id})
    return {
        "id": session_id,
        "messages": [
            {"role": r[0], "content": r[1], "created_at": r[2].isoformat() if r[2] else None}
            for r in msgs.fetchall()
        ],
    }


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a specific session and all its messages."""
    from sqlalchemy import text
    result = await db.execute(text(
        "DELETE FROM chat_sessions WHERE id = :sid AND user_id = :uid RETURNING id"
    ), {"sid": session_id, "uid": str(user.id)})
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": True}


@router.delete("/sessions")
async def delete_all_sessions(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete all chat sessions for current user."""
    from sqlalchemy import text
    result = await db.execute(text(
        "DELETE FROM chat_sessions WHERE user_id = :uid RETURNING id"
    ), {"uid": str(user.id)})
    deleted = len(result.fetchall())
    return {"deleted_count": deleted}
