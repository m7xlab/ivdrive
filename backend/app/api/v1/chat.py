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
    provider: Literal["minimax", "gemini", "openai"] = "minimax"


class SourceRef(BaseModel):
    type: str
    id: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceRef] = []
    session_id: str | None = None


# ─── LLM calls ─────────────────────────────────────────────────────────────────
async def call_llm(
    prompt: str,
    context_chunks: list[dict],
    provider: str = "minimax",
    model: str | None = None,
) -> str:
    """Call LLM with RAG context. Falls back between providers on failure."""
    if not prompt.strip():
        return "I didn't receive a message. Please try again."

    # Build context from retrieved chunks
    context_block = ""
    if context_chunks:
        context_lines = []
        for i, chunk in enumerate(context_chunks[:5], 1):
            meta = chunk.get("metadata", {}) or {}
            source = meta.get("source", chunk.get("type", "unknown"))
            context_lines.append(f"[{i}] ({source}) {chunk.get('chunk', '')[:400]}")
        context_block = "Context from your vehicle data:\n" + "\n".join(context_lines) + "\n\n"

    system_prompt = (
        "You are iVDrive AI assistant. Answer questions based ONLY on the provided vehicle data context. "
        "If the context doesn't contain relevant information, say you don't have that data. "
        "Be specific with numbers, dates, and locations when available. "
        "Format answers clearly. Keep it concise."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": context_block + f"Question: {prompt}"},
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
]
ARITHMETIC_PATTERNS = [
    r"cost", r"spend", r"spent", r"eur", r"kwh total", r"energy total",
    r"distance total", r"total km", r"total distance", r"total cost",
]
TEMPORAL_PATTERNS = [
    r"\blast\b", r"\blatest\b", r"\bmost recent\b",
    r"\bprevious\b", r"\bprior\b", r"\bthis year\b",
]

# Month name → (year, month) for "May 2026" style queries
import re as _re


def extract_date_range(query: str):
    """Extract (from_date, to_date) from query. Returns (None, None) if not found."""
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
            from_date = f"{year}-{month_num:02d}-01"
            to_date = f"{year}-{month_num:02d}-31"
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

        # Charging cost
        if any(k in q for k in ["cost", "spend", "spent", "eur", "price"]):
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
    # Skip temporal fallback for cost/spent/price queries — cost section handles those.
    # Run temporal for: "when did I last charge", "last charging session", etc.
    asked_about_money = any(k in q for k in ["cost", "spend", "spent", "eur", "price", "how much", "total charge", "total cost"])
    if is_temporal_query(q) and any(k in q for k in ["charge", "charging", "kwh"]) and not asked_about_money:
        charge_params = {"uid": str(user_id), "vid": vehicle_id} if vehicle_id else {"uid": str(user_id)}
        rows = await _run(text(f"""
            SELECT c.session_start, COALESCE(c.energy_kwh, 0)::float, COALESCE(c.charging_type, 'unknown')::text,
                   COALESCE(c.start_level, 0)::float, COALESCE(c.end_level, 0)::float,
                   COALESCE(c.actual_cost_eur, 0)::float, v.display_name
            FROM charging_sessions c
            JOIN user_vehicles v ON v.id = c.user_vehicle_id
            WHERE c.user_vehicle_id IN {vid_subq} {cid_filter}
            ORDER BY c.session_start DESC LIMIT 1
        """), charge_params)
        if rows:
            r = rows[0]
            date_str = r[0].strftime("%Y-%m-%d %H:%M") if r[0] else "?"
            cost_str = f", €{r[5]:.2f}" if r[5] else ""
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
    """
    from sqlalchemy import text
    import httpx

    user_id = user.id

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

    # Step 2: Detect vehicle from query if not explicitly filtered
    detected_vehicle_id = None
    if not req.vehicle_id:
        q_lower = req.message.lower()
        for name, v_id in vehicle_name_to_id.items():
            # Match whole word to avoid "enyaq" matching "enyaq85"
            if any(w.lower() == name or w.lower().startswith(name + " ") or w.lower().endswith(" " + name)
                   for w in _re.split(r"[\s,.!?;:+-]+", q_lower)):
                detected_vehicle_id = v_id
                break

    # Explicit filter only; detected_vehicle_id is used for aggregate DB search + post-filtering
    # (NOT passed to search_similar SQL filter because ai_embeddings.vehicle_id is only set for
    # vehicle_stats — trip/charging chunks have NULL and would be lost.)
    vehicle_ids = ([uuid.UUID(req.vehicle_id)] if req.vehicle_id and req.vehicle_id in user_vehicle_ids else None)

    # Detect vehicle name for post-filtering (before SQL search so we can keep unfiltered chunks)
    detected_vehicle_name = None
    if not req.vehicle_id and not vehicle_ids:
        q_lower = req.message.lower()
        for name, v_id in vehicle_name_to_id.items():
            q_words = set(_re.split(r"[\s,.!?;:+-]+", q_lower))
            if name in q_words or any(w.startswith(name + " ") or w.endswith(" " + name) for w in q_words):
                detected_vehicle_id = v_id
                detected_vehicle_name = name
                break

    # Step 3: Check if query needs direct DB aggregation (arithmetic / counts / totals)
    chunks = []
    agg_chunks = []
    effective_vid = req.vehicle_id if req.vehicle_id and req.vehicle_id in user_vehicle_ids else (
        str(detected_vehicle_id) if detected_vehicle_id else None)
    if is_aggregate_query(req.message) or is_temporal_query(req.message):
        agg_chunks = await aggregate_db_search(db, user_id, req.message, effective_vid)
        logger.info(f"aggregate_db_search returned {len(agg_chunks)} chunks")

    # Inject vehicle name into aggregate chunks so LLM knows the result is vehicle-specific
    if effective_vid and detected_vehicle_name and agg_chunks:
        # Prepend vehicle name to each aggregate chunk
        vname = next((row[1] for row in vehicle_rows if str(row[0]) == str(effective_vid)), detected_vehicle_name)
        for c in agg_chunks:
            if c.get("id") == "aggregate":
                c["chunk"] = f"{vname}: {c["chunk"]}"

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

    # Step 5: Post-filter by detected vehicle name (covers NULL-vehicle_id trip/charging chunks)
    if detected_vehicle_name and not vehicle_ids:
        vid_str = str(detected_vehicle_id)

        def _matches_vehicle(c: dict) -> bool:
            chunk_lower = c.get("chunk", "").lower()
            meta = c.get("metadata") or {}
            return (detected_vehicle_name.lower() in chunk_lower or
                    vid_str in chunk_lower or
                    detected_vehicle_name.lower() in str(meta).lower())

        before = len(vec_chunks)
        vec_chunks = [c for c in vec_chunks if _matches_vehicle(c)]
        logger.info(f"post-filtered to {len(vec_chunks)}/{before} chunks for vehicle '{detected_vehicle_name}'")

    # Combine: aggregate data first (for correct numbers), then semantic context
    chunks = agg_chunks + vec_chunks

    # Step 6: If no results at all, fall back to direct DB
    if not chunks:
        chunks = await direct_db_search(db, user_id, req.message, effective_vid)
        logger.info(f"direct_db_search returned {len(chunks)} chunks")

    # Step 7: Call LLM
    answer = await call_llm(req.message, chunks, provider=req.provider)

    # Step 8: Build source references (exclude aggregate chunks from sources)
    sources = [
        SourceRef(type=c["type"], id=c["id"], score=c["score"])
        for c in chunks[:5]
        if c.get("score", 0) > 0.6 and c.get("id") != "aggregate"
    ]

    return ChatResponse(answer=answer, sources=sources)