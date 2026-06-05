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
from app.services.phase3_handlers import detect_phase3_intent, add_trip_annotation, set_charging_reminder, list_charging_reminders, cancel_charging_reminder, run_data_quality_check, get_weekly_summary, get_trip_annotations

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])

# ─── LLM providers ──────────────────────────────────────────────────────────────
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

LLM_URLS = {
    "minimax": "https://api.minimax.chat/v1/text/chatcompletion_v2",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
    "openai": "https://api.openai.com/v1/chat/completions",
}

LLM_MODELS = {
    "minimax": "MiniMax-Text-01",
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
) -> str:
    """Call LLM with RAG context + optional conversation history. Falls back between providers on failure."""
    if not prompt.strip():
        return "I didn't receive a message. Please try again."

    # Build context from retrieved chunks
    context_block = ""
    if context_chunks:
        context_lines = []
        for i, chunk in enumerate(context_chunks[:3], 1):
            meta = chunk.get("metadata", {}) or {}
            raw_type = chunk.get("type", "unknown")
            # Source label for display — never expose raw content_type names
            source = meta.get("source") or {
                "trip_summary": "Trip",
                "charging_event": "Charge",
                "vehicle_stats": "Stats",
                "location": "Place",
            }.get(raw_type, raw_type.title())
            context_lines.append(f"[{i}] ({chunk.get('id','')}) {chunk.get('chunk', '')[:400]}")
        context_block = "Context from your vehicle data:\n" + "\n".join(context_lines) + "\n\n"

    # Build conversation context from history
    conv_block = _build_conversation_context(conversation_history or []) if conversation_history else ""

    system_prompt = (
        "You are iVDrive AI assistant — an expert in electric vehicles, driving analytics, and Skoda vehicles.\n"
        "\n"
        "TYPE 1 — VEHICLE DATA (always prefer when available):\n"
        "Context marked [aggregate] contains the user's actual vehicle data from the iVDrive database.\n"
        "This is GROUND TRUTH for all questions about the user's cars.\n"
        "Rules: Dates in YYYY-MM-DD HH:MM as provided. [aggregate] is always authoritative.\n"
        "Never contradict conversation history unless given new conflicting data.\n"
        "Never expose internal labels ('trip_summary', 'charging_event', 'location', 'aggregate').\n"
        "When answering charging questions, ALWAYS include the energy kWh value.\n"
        "\n"
        "TYPE 2 — GENERAL EV KNOWLEDGE (use when vehicle data is absent or for background context):\n"
        "When no vehicle-specific data is available, or for general EV topics, use your training knowledge:\n"
        "- Skoda Enyaq 85: WLTP ~0.17 kWh/km, 82 kWh battery\n"
        "- Skoda Enyaq 80 (iV): WLTP ~0.17 kWh/km, 77 kWh battery\n"
        "- Skoda Elroq: WLTP ~0.17 kWh/km, 77 kWh battery\n"
        "- Temperature effect: below 10C adds 15-25% consumption\n"
        "- HVAC effect: climate control adds 10-30% in extreme temps\n"
        "- Optimal efficiency: 0.15-0.20 kWh/km; real-world mixed: 0.18-0.28 kWh/km\n"
        "- AC charging: 0.2-0.3 kWh/min (11-22 kW); DC fast: 0.5-4 kWh/min (10-80% fastest)\n"
        "- Battery SoH: starts 100%, degrades 2-3% per year\n"
        "\n"
        "HYBRID RULE: When vehicle data exists AND user asks 'how is my X?', answer from vehicle data \
"
        "PRIMARY, then enrich with EV domain knowledge as context. Example: 'Your 0.24 kWh/km — \
"
        "Skoda WLTP is 0.17 kWh/km, your higher figure is normal for mixed driving.'\n"
        "If vehicle data is empty/irrelevant, answer freely from general EV knowledge.\n"
        "Never say 'I don't have that information' when you have general EV knowledge.\n"
        "\n"
        "IMPORTANT: When previous conversation provides facts, NEVER contradict them.\n"
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
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        LLM_URLS[prov],
                        headers={
                            "Authorization": f"Bearer {MINIMAX_API_KEY}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": model or LLM_MODELS.get(prov, "MiniMax-Text-01"),
                            "messages": messages,
                            "temperature": 0.3,
                        },
                    )
                    if resp.status_code != 200:
                        last_error = f"minimax {resp.status_code}: {resp.text[:100]}"
                        continue
                    data = resp.json()
                    return data["choices"][0]["message"]["content"]

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
    r"how many vehicles", r"\bnumber of vehicles\b",
]
ARITHMETIC_PATTERNS = [
    r"cost", r"spend", r"spent", r"eur", r"kwh total", r"energy total",
    r"distance total", r"total km", r"total distance", r"total cost",
]
TEMPORAL_PATTERNS = [
    r"\blast\b", r"\blatest\b", r"\bmost recent\b",
    r"\bprevious\b", r"\bprior\b", r"\bthis year\b",
]

TREND_PATTERNS = [
    r"trend", r"over time", r"over the (last|past|month|year)",
    r"changing", r"increasing", r"decreasing", r"improving", r"worsening",
    r"monthly", r"weekly", r"comparison over", r"month.over.month",
    r"vs last month", r"compare to previous", r"historical",
]

BREAKDOWN_PATTERNS = [
    r"breakdown", r"by temperature", r"by (time|hour|day|month)",
    r"distribution", r"split by", r"segment", r"per temperature",
    r"cold trips", r"warm trips", r"hot trips", r"mild trips",
    r"weekday", r"weekend", r"morning trips", r"evening trips",
]

COMPARISON_PATTERNS = [
    r"compare", r"comparison", r"vs ", r"versus", r"which (is |are )?(better|worse|more|less|most|least)",
    r"difference between", r"different from", r"other vehicle",
    r"across vehicles", r"fleet", r"all my vehicles",
    r"most efficient", r"least efficient", r"best efficiency", r"worst efficiency",
]

EFFICIENCY_PATTERNS = [
    r"efficiency", r"kwh/km", r"consumption", r"efficent", r"km/kwh",
    r"consuming", r"consumed", r"energy usage", r"energy efficiency",
]

CAUSAL_PATTERNS = [
    r"why is", r"why does", r"why did", r"why was", r"what caused",
    r"explain why", r"reason for", r"due to", r"because of",
    r"what's causing", r"what is causing", r"what made",
]

DIAGNOSTIC_PATTERNS = [
    r"diagnostic", r"check.*battery", r"battery.*okay", r"battery.*problem",
    r"anything wrong", r"anything unusual", r"any issues", r"anomal",
    r"spike", r"dropped", r"increased.*suddenly", r"decreased.*suddenly",
]

INSIGHT_PATTERNS = [
    r"insight", r"interesting", r"notable", r"worth noting",
    r"you.*notice", r"you.*see", r"tell me something",
    r"surprise", r"unexpected", r"unusual pattern",
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
    for p in (AGGREGATE_PATTERNS + ARITHMETIC_PATTERNS + TREND_PATTERNS +
              BREAKDOWN_PATTERNS + COMPARISON_PATTERNS + EFFICIENCY_PATTERNS +
              CAUSAL_PATTERNS + DIAGNOSTIC_PATTERNS + INSIGHT_PATTERNS):
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

 # ── Vehicle count ───────────────────────────────────────────────────────
    if any(p in q for p in ["how many vehicles", "number of vehicles", "vehicle count", "total vehicles"]):
        rows = await _run(text("SELECT COUNT(*)::int FROM user_vehicles WHERE user_id = :uid"), {"uid": str(user_id)})
        if rows:
            chunks.append({
                "type": "vehicle_stats",
                "id": "aggregate",
                "chunk": f"Total vehicles: {rows[0][0]}",
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
                AND t.end_date IS NOT NULL
            """), base_params)
            if rows:
                r = rows[0]
                
                chunks.append({
                    "type": "trip_summary",
                    "id": "aggregate",
                    "chunk": f"Total trips{_period()}: {r[0]} trips covering {r[1]:.1f} km",
                })

        # Average speed across trips (computed: distance_km * 3600 / duration_sec, capped at 200 km/h)
        if any(p in q for p in ["average speed", "avg speed", "average velocity", "average trip speed"]):
            rows = await _run(text(f"""
                SELECT COALESCE(AVG(
                    CASE WHEN t.distance_km > 0 AND t.end_date > t.start_date
                    THEN LEAST(t.distance_km * 3600.0 / NULLIF(EXTRACT(EPOCH FROM (t.end_date - t.start_date)), 0), 200)
                    END), 0)::float, COUNT(*)::int
                FROM trips t
                WHERE t.user_vehicle_id IN {vid_subq} {vid_filter} {date_filter_t}
                AND t.end_date IS NOT NULL AND t.distance_km > 0 AND t.end_date > t.start_date
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
        if any(p in q for p in ["how many times", "number of charges", "count of charge", "charging count"]):
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
            AND t.end_date IS NOT NULL
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
            AND c.session_end IS NOT NULL
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


    # ── Trend queries ─────────────────────────────────────────────────────────
    if any(_re.search(p, q) for p in TREND_PATTERNS):
        if any(k in q for k in ["consumption", "efficiency", "kwh", "distance", "km", "trend"]):
            rows = await _run(text(f"""
                SELECT
                    DATE_TRUNC('month', t.start_date) AS month,
                    COUNT(*)::int AS trips,
                    COALESCE(SUM(t.distance_km), 0)::float AS total_km,
                    COALESCE(SUM(t.kwh_consumed), 0)::float AS total_kwh,
                    CASE WHEN COALESCE(SUM(t.distance_km), 0) > 0
                         THEN COALESCE(SUM(t.kwh_consumed), 0) / COALESCE(SUM(t.distance_km), 0) * 100
                         ELSE 0 END AS kwh_per_100km,
                    COALESCE(AVG(t.avg_temp_celsius), 0)::float AS avg_temp
                FROM trips t
                WHERE t.user_vehicle_id IN {vid_subq} {vid_filter} {date_filter_t}
                AND t.end_date IS NOT NULL AND t.distance_km > 0
                GROUP BY DATE_TRUNC('month', t.start_date)
                ORDER BY month DESC
                LIMIT 6
            """), base_params)
            if rows:
                lines = ["Monthly consumption trend:"]
                for r in reversed(rows):
                    mn = r[0].strftime("%Y-%m") if r[0] else "?"
                    eff = r[4]
                    lines.append(
                        "  " + mn + ": " + f"{eff:.2f}" + " kWh/100km, " + f"{r[2]:.0f}" + " km, " + f"{r[5]:.1f}" + "C avg (" + str(r[1]) + " trips)"
                    )
                chunks.append({
                    "type": "trend_analysis",
                    "id": "aggregate",
                    "chunk": "\n".join(lines),
                })

        if any(k in q for k in ["charging", "charge", "energy"]):
            rows = await _run(text(f"""
                SELECT
                    DATE_TRUNC('month', c.session_start) AS month,
                    COUNT(*)::int AS sessions,
                    COALESCE(SUM(c.energy_kwh), 0)::float AS total_kwh,
                    COALESCE(SUM(COALESCE(c.actual_cost_eur, c.base_cost_eur)), 0)::float AS total_cost
                FROM charging_sessions c
                WHERE c.user_vehicle_id IN {vid_subq} {cid_filter} {date_filter_c}
                AND c.session_end IS NOT NULL
                GROUP BY DATE_TRUNC('month', c.session_start)
                ORDER BY month DESC
                LIMIT 6
            """), base_params)
            if rows:
                lines = ["Monthly charging trend:"]
                for r in reversed(rows):
                    mn = r[0].strftime("%Y-%m") if r[0] else "?"
                    lines.append(
                        "  " + mn + ": " + f"{r[2]:.1f}" + " kWh, EUR" + f"{r[3]:.2f}" + " (" + str(r[1]) + " sessions)"
                    )
                chunks.append({
                    "type": "trend_analysis",
                    "id": "aggregate",
                    "chunk": "\n".join(lines),
                })

    # ── Breakdown queries ────────────────────────────────────────────────────
    if any(_re.search(p, q) for p in BREAKDOWN_PATTERNS):
        if any(k in q for k in ["temperature", "cold", "warm", "hot", "mild", "weather"]):
            rows = await _run(text(f"""
                SELECT
                    CASE
                        WHEN t.avg_temp_celsius < 0 THEN 'Freezing (<0C)'
                        WHEN t.avg_temp_celsius < 10 THEN 'Cold (0-10C)'
                        WHEN t.avg_temp_celsius < 20 THEN 'Mild (10-20C)'
                        WHEN t.avg_temp_celsius < 30 THEN 'Warm (20-30C)'
                        ELSE 'Hot (>30C)'
                    END AS temp_band,
                    COUNT(*)::int AS trips,
                    COALESCE(SUM(t.distance_km), 0)::float AS total_km,
                    CASE WHEN COALESCE(SUM(t.distance_km), 0) > 0
                         THEN COALESCE(SUM(t.kwh_consumed), 0) / COALESCE(SUM(t.distance_km), 0) * 100
                         ELSE 0 END AS kwh_per_100km,
                    COALESCE(AVG(t.avg_temp_celsius), 0)::float AS avg_temp
                FROM trips t
                WHERE t.user_vehicle_id IN {vid_subq} {vid_filter} {date_filter_t}
                AND t.end_date IS NOT NULL AND t.distance_km > 0
                GROUP BY
                    CASE
                        WHEN t.avg_temp_celsius < 0 THEN 'Freezing (<0C)'
                        WHEN t.avg_temp_celsius < 10 THEN 'Cold (0-10C)'
                        WHEN t.avg_temp_celsius < 20 THEN 'Mild (10-20C)'
                        WHEN t.avg_temp_celsius < 30 THEN 'Warm (20-30C)'
                        ELSE 'Hot (>30C)'
                    END
                ORDER BY avg_temp
            """), base_params)
            if rows:
                lines = ["Consumption by temperature band:"]
                for r in rows:
                    eff = r[3]
                    lines.append(
                        "  " + r[0] + ": " + f"{eff:.2f}" + " kWh/100km (" + f"{r[2]:.0f}" + " km across " + str(r[1]) + " trips)"
                    )
                chunks.append({
                    "type": "breakdown_analysis",
                    "id": "aggregate",
                    "chunk": "\n".join(lines),
                })

        if any(k in q for k in ["weekday", "weekend", "day of week", "by day"]):
            rows = await _run(text(f"""
                SELECT
                    CASE WHEN EXTRACT(DOW FROM t.start_date) IN (0, 6) THEN 'Weekend' ELSE 'Weekday' END AS day_type,
                    COUNT(*)::int AS trips,
                    COALESCE(SUM(t.distance_km), 0)::float AS total_km,
                    CASE WHEN COALESCE(SUM(t.distance_km), 0) > 0
                         THEN COALESCE(SUM(t.kwh_consumed), 0) / COALESCE(SUM(t.distance_km), 0) * 100
                         ELSE 0 END AS kwh_per_100km
                FROM trips t
                WHERE t.user_vehicle_id IN {vid_subq} {vid_filter} {date_filter_t}
                AND t.end_date IS NOT NULL AND t.distance_km > 0
                GROUP BY CASE WHEN EXTRACT(DOW FROM t.start_date) IN (0, 6) THEN 'Weekend' ELSE 'Weekday' END
            """), base_params)
            if rows:
                lines = ["Consumption by day type:"]
                for r in rows:
                    eff = r[3]
                    lines.append(
                        "  " + r[0] + ": " + f"{eff:.2f}" + " kWh/100km (" + f"{r[2]:.0f}" + " km, " + str(r[1]) + " trips)"
                    )
                chunks.append({
                    "type": "breakdown_analysis",
                    "id": "aggregate",
                    "chunk": "\n".join(lines),
                })

    # ── Comparison queries (across user's fleet) ─────────────────────────────
    if any(_re.search(p, q) for p in COMPARISON_PATTERNS) and not vehicle_id:
        if any(k in q for k in ["consumption", "efficiency", "distance", "km", "trip", "vehicle"]):
            rows = await _run(text(f"""
                SELECT
                    v.display_name,
                    COUNT(t.id)::int AS trips,
                    COALESCE(SUM(t.distance_km), 0)::float AS total_km,
                    CASE WHEN COALESCE(SUM(t.distance_km), 0) > 0
                         THEN COALESCE(SUM(t.kwh_consumed), 0) / COALESCE(SUM(t.distance_km), 0) * 100
                         ELSE 0 END AS kwh_per_100km,
                    COALESCE(AVG(
                        CASE WHEN t.distance_km > 0 AND t.end_date > t.start_date
                        THEN LEAST(t.distance_km * 3600.0 / NULLIF(EXTRACT(EPOCH FROM (t.end_date - t.start_date)), 0), 200)
                        END), 0)::float AS avg_speed
                FROM user_vehicles v
                LEFT JOIN trips t ON t.user_vehicle_id = v.id AND t.end_date IS NOT NULL
                WHERE v.user_id = :uid
                GROUP BY v.display_name
                ORDER BY kwh_per_100km ASC
            """), {"uid": str(user_id)})
            if rows:
                lines = ["Fleet comparison (most efficient first):"]
                for r in rows:
                    eff = r[3]
                    spd = r[4]
                    lines.append(
                        "  " + r[0] + ": " + f"{eff:.2f}" + " kWh/100km, avg speed " + f"{spd:.1f}" + " km/h (" + str(r[1]) + " trips, " + f"{r[2]:.0f}" + " km)"
                    )
                chunks.append({
                    "type": "fleet_comparison",
                    "id": "aggregate",
                    "chunk": "\n".join(lines),
                })

    # ── Efficiency query with WLTP comparison ──────────────────────────────
    if any(_re.search(p, q) for p in EFFICIENCY_PATTERNS):
        if not any(p in q for p in TREND_PATTERNS):
            rows = await _run(text(f"""
                SELECT
                    COUNT(*)::int AS trips,
                    COALESCE(SUM(t.distance_km), 0)::float AS total_km,
                    COALESCE(SUM(t.kwh_consumed), 0)::float AS total_kwh,
                    CASE WHEN COALESCE(SUM(t.distance_km), 0) > 0
                         THEN COALESCE(SUM(t.kwh_consumed), 0) / COALESCE(SUM(t.distance_km), 0) * 100
                         ELSE 0 END AS kwh_per_100km,
                    CASE WHEN COALESCE(SUM(t.distance_km), 0) > 0
                         THEN COALESCE(SUM(t.distance_km), 0) / NULLIF(COALESCE(SUM(t.kwh_consumed), 0), 0)
                         ELSE 0 END AS km_per_kwh,
                    COALESCE(AVG(t.avg_temp_celsius), 0)::float AS avg_temp
                FROM trips t
                WHERE t.user_vehicle_id IN {vid_subq} {vid_filter} {date_filter_t}
                AND t.end_date IS NOT NULL AND t.distance_km > 0 AND t.kwh_consumed > 0
            """), base_params)
            if rows:
                r = rows[0]
                if r[0] > 0:
                    wltp_ref = 17.0
                    per100 = r[2] / r[1] * 100 if r[1] > 0 else 0
                    diff_pct = (per100 - wltp_ref) / wltp_ref * 100
                    direction = "above" if diff_pct > 0 else "below"
                    temp_note = " (avg temp " + f"{r[5]:.1f}" + "C - cold weather may increase consumption)" if r[5] < 10 else ""
                    eff_chunk = (
                        "Real-world efficiency" + _period() + ": " + f"{r[2]:.1f}" + " kWh / " + f"{r[1]:.0f}" + " km = " +
                        f"{per100:.2f}" + " kWh/100km (" + f"{r[4]:.2f}" + " km/kWh) across " + str(r[0]) + " trips. " +
                        "Skoda WLTP reference: " + f"{wltp_ref:.1f}" + " kWh/100km -- " +
                        "your consumption is " + f"{abs(diff_pct):.0f}" + "% " + direction + " WLTP." + temp_note
                    )
                    chunks.append({
                        "type": "efficiency_analysis",
                        "id": "aggregate",
                        "chunk": eff_chunk,
                    })


    # ═══════════════════════════════════════════════════════════════════════
    # PHASE 2: COMPOSITE CAUSAL + DIAGNOSTIC + INSIGHT ENGINE
    # ═══════════════════════════════════════════════════════════════════════

    # ── CAUSAL: Why is consumption up/down? ─────────────────────────────────
    # Multi-step: compare periods, correlate with temperature, check driving patterns
    if any(_re.search(p, q) for p in CAUSAL_PATTERNS):
        if any(k in q for k in ["consumption", "efficiency", "kwh", "spending", "cost"]):
            # Get current period (last 30 days) vs previous period (30-60 days ago)
            rows_current = await _run(text(f"""
                SELECT
                    COUNT(*)::int AS trips,
                    COALESCE(SUM(t.distance_km), 0)::float AS total_km,
                    COALESCE(SUM(t.kwh_consumed), 0)::float AS total_kwh,
                    CASE WHEN COALESCE(SUM(t.distance_km), 0) > 0
                         THEN COALESCE(SUM(t.kwh_consumed), 0) / COALESCE(SUM(t.distance_km), 0) * 100
                         ELSE 0 END AS kwh_per_100km,
                    COALESCE(AVG(t.avg_temp_celsius), 0)::float AS avg_temp,
                    COALESCE(AVG(
                        CASE WHEN t.distance_km > 0 AND t.end_date > t.start_date
                        THEN LEAST(t.distance_km * 3600.0 / NULLIF(EXTRACT(EPOCH FROM (t.end_date - t.start_date)), 0), 200)
                        END), 0)::float AS avg_speed
                FROM trips t
                WHERE t.user_vehicle_id IN {vid_subq} {vid_filter}
                AND t.end_date IS NOT NULL AND t.distance_km > 0 AND t.kwh_consumed > 0
                AND t.start_date >= NOW() - INTERVAL '30 days'
            """), base_params)

            rows_previous = await _run(text(f"""
                SELECT
                    COUNT(*)::int AS trips,
                    COALESCE(SUM(t.distance_km), 0)::float AS total_km,
                    COALESCE(SUM(t.kwh_consumed), 0)::float AS total_kwh,
                    CASE WHEN COALESCE(SUM(t.distance_km), 0) > 0
                         THEN COALESCE(SUM(t.kwh_consumed), 0) / COALESCE(SUM(t.distance_km), 0) * 100
                         ELSE 0 END AS kwh_per_100km,
                    COALESCE(AVG(t.avg_temp_celsius), 0)::float AS avg_temp,
                    COALESCE(AVG(
                        CASE WHEN t.distance_km > 0 AND t.end_date > t.start_date
                        THEN LEAST(t.distance_km * 3600.0 / NULLIF(EXTRACT(EPOCH FROM (t.end_date - t.start_date)), 0), 200)
                        END), 0)::float AS avg_speed
                FROM trips t
                WHERE t.user_vehicle_id IN {vid_subq} {vid_filter}
                AND t.end_date IS NOT NULL AND t.distance_km > 0 AND t.kwh_consumed > 0
                AND t.start_date >= NOW() - INTERVAL '60 days'
                AND t.start_date < NOW() - INTERVAL '30 days'
            """), base_params)

            if rows_current and rows_current[0][0] > 0 and rows_previous and rows_previous[0][0] > 0:
                curr = rows_current[0]
                prev = rows_previous[0]
                curr_eff = curr[3]
                prev_eff = prev[3]
                eff_change = curr_eff - prev_eff
                temp_change = curr[4] - prev[4]  # temperature change (positive = warmer)
                speed_change = curr[5] - prev[5]    # speed change

                # Temperature explanation: ~2% per degreeC deviation from 20C
                temp_explainer = ""
                if temp_change < -5:
                    temp_explainer = " Colder weather (down " + f"{abs(temp_change):.1f}" + "C) typically adds 10-20% consumption."
                elif temp_change < -2:
                    temp_explainer = " Slightly colder weather (down " + f"{abs(temp_change):.1f}" + "C) may add 4-8% consumption."
                elif temp_change > 5:
                    temp_explainer = " Warmer weather (up " + f"{temp_change:.1f}" + "C) usually reduces consumption."

                # Speed explanation
                speed_explainer = ""
                if speed_change > 10:
                    speed_explainer = " Higher average speed (+" + f"{speed_change:.1f}" + " km/h) increases consumption."
                elif speed_change < -10:
                    speed_explainer = " Lower average speed (-" + f"{abs(speed_change):.1f}" + " km/h) may indicate more city driving."

                # Build causal explanation
                if abs(eff_change) > 0.5:
                    direction = "increased" if eff_change > 0 else "decreased"
                    pct_change = abs(eff_change / prev_eff * 100) if prev_eff > 0 else 0
                    explanation = (
                        "Consumption " + direction + " by " + f"{abs(eff_change):.2f}" + " kWh/100km (" +
                        f"{pct_change:.0f}" + "%) comparing last 30 days vs previous 30 days." +
                        temp_explainer + speed_explainer
                    )
                    chunks.append({
                        "type": "causal_analysis",
                        "id": "aggregate",
                        "chunk": explanation,
                    })

    # ── DIAGNOSTIC: Anything unusual? Anomalies? ────────────────────────────
    if any(_re.search(p, q) for p in DIAGNOSTIC_PATTERNS) or any(k in q for k in ["anything wrong", "check my car", "any issues", "diagnostic"]):
        # Check for consumption spike (last 7 days vs previous 7 days)
        spike_rows = await _run(text(f"""
            SELECT
                COUNT(*)::int AS recent_trips,
                CASE WHEN COALESCE(SUM(prev.distance_km), 0) > 0
                     THEN COALESCE(SUM(prev.kwh_consumed), 0) / COALESCE(SUM(prev.distance_km), 0) * 100
                     ELSE 0 END AS prev_eff,
                CASE WHEN COALESCE(SUM(curr.distance_km), 0) > 0
                     THEN COALESCE(SUM(curr.kwh_consumed), 0) / COALESCE(SUM(curr.distance_km), 0) * 100
                     ELSE 0 END AS curr_eff
            FROM trips prev, trips curr
            WHERE prev.user_vehicle_id IN {vid_subq} {vid_filter}
            AND curr.user_vehicle_id = prev.user_vehicle_id
            AND prev.end_date IS NOT NULL AND prev.start_date >= NOW() - INTERVAL '14 days'
            AND prev.start_date < NOW() - INTERVAL '7 days'
            AND curr.end_date IS NOT NULL AND curr.start_date >= NOW() - INTERVAL '7 days'
        """), base_params)

        # Check for phantom trips (0km trips with high kWh — unusual)
        phantom_rows = await _run(text(f"""
            SELECT COUNT(*)::int AS phantom_count
            FROM trips t
            WHERE t.user_vehicle_id IN {vid_subq} {vid_filter}
            AND t.end_date IS NOT NULL AND t.distance_km = 0 AND t.kwh_consumed > 5
        """), base_params)

        # Check for high-cost charging sessions (>EUR 20 in last 30 days)
        highcost_rows = await _run(text(f"""
            SELECT COUNT(*)::int AS highcost_count
            FROM charging_sessions c
            WHERE c.user_vehicle_id IN {vid_subq} {cid_filter}
            AND c.session_end IS NOT NULL
            AND COALESCE(c.actual_cost_eur, c.base_cost_eur) > 20
            AND c.session_start >= NOW() - INTERVAL '30 days'
        """), base_params)

        # Check for very long trips (>200km in single trip)
        longtrip_rows = await _run(text(f"""
            SELECT COUNT(*)::int AS longtrip_count
            FROM trips t
            WHERE t.user_vehicle_id IN {vid_subq} {vid_filter}
            AND t.end_date IS NOT NULL AND t.distance_km > 200
            AND t.start_date >= NOW() - INTERVAL '30 days'
        """), base_params)

        anomalies = []
        if spike_rows and spike_rows[0][0] > 0:
            prev_eff = spike_rows[0][1] or 0
            curr_eff = spike_rows[0][2] or 0
            if prev_eff > 0 and curr_eff > prev_eff * 1.2:
                anomalies.append(
                    "Consumption spike: recent avg " + f"{curr_eff:.2f}" + " kWh/100km vs " +
                    f"{prev_eff:.2f}" + " kWh/100km before (20%+ increase)"
                )
        if phantom_rows and phantom_rows[0][0] > 0:
            pc = phantom_rows[0][0]
            anomalies.append(
                str(pc) + " phantom trip(s) found: trips with 0 km but >5 kWh consumed (may indicate idling with climate on)"
            )
        if highcost_rows and highcost_rows[0][0] > 0:
            hc = highcost_rows[0][0]
            anomalies.append(
                str(hc) + " high-cost charging session(s) (>EUR 20) in last 30 days"
            )
        if longtrip_rows and longtrip_rows[0][0] > 0:
            lt = longtrip_rows[0][0]
            anomalies.append(
                str(lt) + " long trip(s) (>200km) in last 30 days"
            )

        if anomalies:
            chunks.append({
                "type": "diagnostic_insight",
                "id": "aggregate",
                "chunk": "Diagnostic check: " + "; ".join(anomalies) + ".",
            })
        elif any(k in q for k in ["anything wrong", "check my car", "any issues", "diagnostic"]):
            chunks.append({
                "type": "diagnostic_insight",
                "id": "aggregate",
                "chunk": "Diagnostic check: No anomalies detected. All metrics look normal.",
            })

    # ── INSIGHT: Tell me something interesting ─────────────────────────────
    if any(_re.search(p, q) for p in INSIGHT_PATTERNS) or any(k in q for k in ["tell me something", "surprise me", "interesting fact", "notable"]):
        insights = []

        # Best efficiency month
        best_month = await _run(text(f"""
            SELECT
                DATE_TRUNC('month', t.start_date) AS month,
                CASE WHEN COALESCE(SUM(t.distance_km), 0) > 0
                     THEN COALESCE(SUM(t.kwh_consumed), 0) / COALESCE(SUM(t.distance_km), 0) * 100
                     ELSE 0 END AS kwh_per_100km,
                COUNT(*)::int AS trips
            FROM trips t
            WHERE t.user_vehicle_id IN {vid_subq} {vid_filter}
            AND t.end_date IS NOT NULL AND t.distance_km > 0 AND t.kwh_consumed > 0
            GROUP BY DATE_TRUNC('month', t.start_date)
            HAVING COUNT(*) >= 5
            ORDER BY kwh_per_100km ASC
            LIMIT 1
        """), base_params)
        if best_month and best_month[0][0]:
            m = best_month[0][0].strftime("%Y-%m")
            e = best_month[0][1]
            insights.append("Your best efficiency month was " + m + " at " + f"{e:.1f}" + " kWh/100km")

        # Most efficient vehicle
        best_veh = await _run(text(f"""
            SELECT
                v.display_name,
                CASE WHEN COALESCE(SUM(t.distance_km), 0) > 0
                     THEN COALESCE(SUM(t.kwh_consumed), 0) / COALESCE(SUM(t.distance_km), 0) * 100
                     ELSE 0 END AS kwh_per_100km,
                COUNT(t.id)::int AS trips
            FROM user_vehicles v
            LEFT JOIN trips t ON t.user_vehicle_id = v.id AND t.end_date IS NOT NULL
            WHERE v.user_id = :uid AND v.display_name NOT LIKE '%RaceBlue%'
            GROUP BY v.display_name
            HAVING COUNT(t.id) >= 10
            ORDER BY kwh_per_100km ASC
            LIMIT 1
        """), {"uid": str(user_id)})
        if best_veh and best_veh[0][0]:
            vname = best_veh[0][0]
            veff = best_veh[0][1]
            insights.append("Your most efficient vehicle is " + vname + " at " + f"{veff:.1f}" + " kWh/100km")

        # Longest single trip
        longest = await _run(text(f"""
            SELECT
                t.distance_km, t.kwh_consumed, t.start_date::date
            FROM trips t
            WHERE t.user_vehicle_id IN {vid_subq} {vid_filter}
            AND t.end_date IS NOT NULL AND t.distance_km > 0
            ORDER BY t.distance_km DESC
            LIMIT 1
        """), base_params)
        if longest and longest[0][0]:
            dist = longest[0][0]
            kwh = longest[0][1]
            date = longest[0][2].strftime("%Y-%m-%d") if hasattr(longest[0][2], 'strftime') else str(longest[0][2])
            insights.append("Your longest trip: " + f"{dist:.0f}" + " km on " + date + " using " + f"{kwh:.1f}" + " kWh")

        # Total energy consumed (all time)
        total_energy = await _run(text(f"""
            SELECT COALESCE(SUM(t.kwh_consumed), 0)::float AS total_kwh
            FROM trips t
            WHERE t.user_vehicle_id IN {vid_subq} {vid_filter}
            AND t.end_date IS NOT NULL
        """), base_params)
        if total_energy and total_energy[0][0] > 0:
            te = total_energy[0][0]
            if te > 10000:
                insights.append("You've consumed " + f"{te:.0f}" + " kWh total — equivalent to ~EUR " + f"{te*0.30:.0f}" + " at average EU prices")

        if insights:
            chunks.append({
                "type": "insight",
                "id": "aggregate",
                "chunk": "Insights from your data: " + "; ".join(insights) + ".",
            })
        else:
            chunks.append({
                "type": "insight",
                "id": "aggregate",
                "chunk": "Not enough data to generate insights yet.",
            })

    # ── TEMPERATURE CORRELATION: detailed consumption vs temperature ────────
    if any(k in q for k in ["temperature effect", "weather effect", "cold weather", "hot weather", "correlation"]):
        rows = await _run(text(f"""
            SELECT
                CASE
                    WHEN t.avg_temp_celsius < -5 THEN 'Freezing (<-5C)'
                    WHEN t.avg_temp_celsius < 0 THEN 'Very cold (-5 to 0C)'
                    WHEN t.avg_temp_celsius < 5 THEN 'Cold (0-5C)'
                    WHEN t.avg_temp_celsius < 10 THEN 'Cool (5-10C)'
                    WHEN t.avg_temp_celsius < 15 THEN 'Mild (10-15C)'
                    WHEN t.avg_temp_celsius < 20 THEN 'Comfortable (15-20C)'
                    WHEN t.avg_temp_celsius < 25 THEN 'Warm (20-25C)'
                    ELSE 'Hot (>25C)'
                END AS temp_band,
                COUNT(*)::int AS trips,
                COALESCE(SUM(t.distance_km), 0)::float AS total_km,
                CASE WHEN COALESCE(SUM(t.distance_km), 0) > 0
                     THEN COALESCE(SUM(t.kwh_consumed), 0) / COALESCE(SUM(t.distance_km), 0) * 100
                     ELSE 0 END AS kwh_per_100km,
                COALESCE(MIN(t.avg_temp_celsius), 0)::float AS min_temp,
                COALESCE(MAX(t.avg_temp_celsius), 0)::float AS max_temp
            FROM trips t
            WHERE t.user_vehicle_id IN {vid_subq} {vid_filter}
            AND t.end_date IS NOT NULL AND t.distance_km > 0 AND t.kwh_consumed > 0
            GROUP BY
                CASE
                    WHEN t.avg_temp_celsius < -5 THEN 'Freezing (<-5C)'
                    WHEN t.avg_temp_celsius < 0 THEN 'Very cold (-5 to 0C)'
                    WHEN t.avg_temp_celsius < 5 THEN 'Cold (0-5C)'
                    WHEN t.avg_temp_celsius < 10 THEN 'Cool (5-10C)'
                    WHEN t.avg_temp_celsius < 15 THEN 'Mild (10-15C)'
                    WHEN t.avg_temp_celsius < 20 THEN 'Comfortable (15-20C)'
                    WHEN t.avg_temp_celsius < 25 THEN 'Warm (20-25C)'
                    ELSE 'Hot (>25C)'
                END
            ORDER BY min_temp
        """), base_params)
        if rows:
            lines = ["Consumption by temperature band:"]
            prev_eff = None
            for r in rows:
                band = r[0]
                eff = r[3]
                n = r[1]
                km = r[2]
                delta = ""
                if prev_eff and prev_eff > 0:
                    pct = (eff - prev_eff) / prev_eff * 100
                    delta = " (" + ("+" if pct > 0 else "") + f"{pct:.0f}%" + " vs previous band)"
                lines.append(
                    "  " + band + ": " + f"{eff:.2f}" + " kWh/100km (" + str(n) + " trips, " +
                    f"{km:.0f}" + " km)" + delta
                )
                prev_eff = eff
            # Add summary
            cold_eff = next((r[3] for r in rows if r[0] in ['Freezing (<-5C)', 'Very cold (-5 to 0C)', 'Cold (0-5C)']), None)
            warm_eff = next((r[3] for r in rows if r[0] in ['Warm (20-25C)', 'Hot (>25C)']), None)
            if cold_eff and warm_eff and warm_eff > 0:
                cold_premium = (cold_eff - warm_eff) / warm_eff * 100
                lines.append("")
                lines.append("  Cold vs warm: " + f"{cold_premium:.0f}" + "% higher consumption in cold conditions")
            chunks.append({
                "type": "temperature_correlation",
                "id": "aggregate",
                "chunk": chr(10).join(lines),
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

    user_id = user.id

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
    # Build name→id map for vehicle-name detection (case-insensitive)
    vehicle_name_to_id = {row[1].lower(): row[0] for row in vehicle_rows}

    # Step 2: Detect vehicle from query if not explicitly filtered.
    # Sets BOTH detected_vehicle_id AND detected_vehicle_name in one pass.
    # Priority: exact/full-phrase match first (longest first), then word-set fallback.
    detected_vehicle_id = None
    detected_vehicle_name = None
    if not req.vehicle_id:
        q_lower = req.message.lower()
        q_words = set(_re.split(r"[\s,.!?;:+-]+", q_lower))
        # Pass 1: full phrase / longest-substring match first
        sorted_vehicles = sorted(vehicle_name_to_id.items(), key=lambda x: len(x[0]), reverse=True)
        for name, v_id in sorted_vehicles:
            name_norm = name.replace('_', ' ').replace('-', ' ')
            if name_norm in q_lower:  # full phrase in query
                detected_vehicle_id = v_id
                detected_vehicle_name = name
                break
        # Pass 2: word-set fallback (only if no phrase match found)
        if not detected_vehicle_id:
            for name, v_id in sorted_vehicles:
                name_norm = name.replace('_', ' ').replace('-', ' ')
                name_words = set(name_norm.split())
                matched = bool(name_words & q_words)
                if matched:
                    detected_vehicle_id = v_id
                    detected_vehicle_name = name
                    break

    # Explicit filter only; detected_vehicle_id is used for aggregate DB search + post-filtering.
    # NOT passed to search_similar SQL because ai_embeddings.vehicle_id is only populated for
    # vehicle_stats type — trip_summary / charging_event chunks have NULL vehicle_id and
    # would be silently dropped. Instead we use post-filtering (Step 5).
    vehicle_ids = ([str(uuid.UUID(req.vehicle_id))] if req.vehicle_id and str(req.vehicle_id) in user_vehicle_ids else None)

    # Step 3: Check if query needs direct DB aggregation (arithmetic / counts / totals)
    chunks = []
    agg_chunks = []
    effective_vid = str(req.vehicle_id) if req.vehicle_id and str(req.vehicle_id) in user_vehicle_ids else (
        str(detected_vehicle_id) if detected_vehicle_id else None)
    if is_aggregate_query(req.message) or is_temporal_query(req.message):
        agg_chunks = await aggregate_db_search(db, user_id, req.message, effective_vid, conversation_history=history)
        logger.info(f"aggregate_db_search returned {len(agg_chunks)} chunks")

    # Inject vehicle name into aggregate chunks so LLM knows the result is vehicle-specific
    if effective_vid and agg_chunks:
        # Get vehicle name: detected from query, or looked up from explicit vehicle_id
        vname = detected_vehicle_name
        if not vname and effective_vid:
            vname = next((row[1] for row in vehicle_rows if str(row[0]) == str(effective_vid)), None)
        if vname:
            for c in agg_chunks:
                if c.get("id") == "aggregate":
                    if not c["chunk"].lower().startswith(vname.lower() + ":"):
                        c["chunk"] = vname + ": " + c["chunk"]
                    c["score"] = 1.0

    # ── Phase 3: Autonomous actions ──────────────────────────────────────────
    phase3_intent = detect_phase3_intent(req.message)
    phase3_result = None
    vid_required = {"annotate_trip"}
    if phase3_intent and (effective_vid or phase3_intent not in vid_required):
        logger.info(f"Phase 3 intent detected: {phase3_intent}")
        try:
            if phase3_intent == "annotate_trip":
                # Extract annotation text from message
                ann_text = req.message
                for prefix in ["annotate this trip", "add note", "note:", "tag this trip", "flag this trip"]:
                    ann_text = ann_text.replace(prefix, "", 1).strip()
                if ann_text and len(ann_text) > 2:
                    ann = await add_trip_annotation(db, user_id, effective_vid, ann_text)
                    phase3_result = f"trip_annotation_added: annotation '{ann_text}' saved to this trip"

            elif phase3_intent == "set_reminder":
                # Extract time from message (simple heuristic)
                from datetime import timedelta
                import re
                time_match = re.search(r'(\d{1,2})(?:\s)*(?:am|pm|AM|PM)?', req.message)
                if time_match:
                    hour = int(time_match.group(1))
                    is_pm = "pm" in req.message.lower()
                    if is_pm and hour < 12:
                        hour += 12
                    from datetime import datetime, timezone
                    now = datetime.now(timezone.utc)
                    remind_at = now.replace(hour=hour, minute=0, second=0, microsecond=0)
                    if remind_at <= now:
                        remind_at += timedelta(days=1)
                    rem = await set_charging_reminder(db, user_id, remind_at, effective_vid)
                    phase3_result = f"charging_reminder_set: reminder created for {remind_at.strftime('%Y-%m-%d %H:%M')}"

            elif phase3_intent == "list_reminders":
                logger.info(f"[DEBUG] list_reminders: user_id={user_id}")
                reminders = await list_charging_reminders(db, user_id)
                logger.info(f"[DEBUG] list_reminders: got {len(reminders)} reminders")
                if reminders:
                    lines = ["Your charging reminders:"]
                    for r in reminders[:5]:
                        status = "🔔 active" if not r.fired_at and not r.cancelled_at else "❌ cancelled" if r.cancelled_at else "✅ fired"
                        lines.append(f"  • {r.remind_at.strftime('%Y-%m-%d %H:%M')} — {r.message or 'Charging reminder'} [{status}]")
                    phase3_result = "list_reminders:\n" + "\n".join(lines)
                else:
                    phase3_result = "no_charging_reminders: You have no charging reminders set."

            elif phase3_intent == "data_quality":
                dq = await run_data_quality_check(db, user_id)
                if dq["status"] == "ok":
                    phase3_result = "data_quality_ok: No data quality issues detected."
                else:
                    phase3_result = "data_quality_issues:\n" + "\n".join(dq["issues"])

            elif phase3_intent == "weekly_summary":
                summary = await get_weekly_summary(db, user_id)
                lines = ["Weekly summary:"]
                for v in summary.get("vehicles", []):
                    if v["trips"] > 0:
                        lines.append(
                            f"  {v['vehicle']}: {v['trips']} trips, {v['total_km']}km, "
                            f"{v['efficiency']}kWh/100km, {v['charge_sessions']} charges"
                        )
                    else:
                        lines.append(f"  {v['vehicle']}: No trips this week")
                phase3_result = "weekly_summary:\n" + "\n".join(lines)

        except Exception as e:
            logger.error(f"Phase 3 handler error: {e}", exc_info=True)
            phase3_result = None

        if phase3_result:
            chunks.append({
                "type": "phase3_action",
                "id": "phase3",
                "chunk": phase3_result,
                "score": 1.0,
            })

    # Step 4: Run vector search WITHOUT vehicle_ids filter (to keep all trip/charging chunks)
    vec_chunks = await search_similar(
        db=db,
        user_id=user_id,
        query=req.message,
        content_types=["trip_summary", "charging_event", "vehicle_stats", "location"],
        vehicle_ids=vehicle_ids,  # Only explicit filter from request
        limit=4,
        provider=req.provider,
    )
    logger.info(f"vector search returned {len(vec_chunks)} chunks")

    # Step 5: Post-filter vector chunks by detected vehicle name.
    # Be permissive: if a chunk mentions a DIFFERENT vehicle, drop it.
    # If no vehicle name in chunk (NULL vehicle_id in DB), keep it as generic context.
    # Only drop chunks that explicitly mention a different vehicle.
    if detected_vehicle_name and not vehicle_ids:
        vid_str = str(detected_vehicle_id)

        def _chunk_is_other_vehicle(c: dict) -> bool:
            chunk_lower = c.get("chunk", "").lower()
            meta_str = str(c.get("metadata") or {}).lower()
            # Drop if chunk explicitly mentions a different vehicle (but not "BlackMagic" itself)
            other_vehicles = {"enyaq", "enyaq_v3", "skoda enyaq", "octavia", "superb"}
            for other in other_vehicles:
                if other in chunk_lower or other in meta_str:
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
    # Preserve phase3 action chunks (already appended to chunks earlier)
    phase3_chunks = [c for c in chunks if c.get("type") == "phase3_action"]
    chunks = phase3_chunks + agg_chunks + vec_chunks

    # Step 6: If no results at all, fall back to direct DB
    if not chunks:
        chunks = await direct_db_search(db, user_id, req.message, effective_vid)
        logger.info(f"direct_db_search returned {len(chunks)} chunks")

    # Step 7: Call LLM with conversation history
    answer = await call_llm(
        req.message, chunks,
        provider=req.provider,
        conversation_history=history,
        detected_vehicle_name_for_llm=detected_vehicle_name,
    )

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
