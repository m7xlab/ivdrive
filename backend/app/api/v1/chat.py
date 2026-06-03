"""
iVDrive AI Chat — /api/v1/chat
Per-user RAG chatbot powered by MiniMax (primary) with Gemini/OpenAI fallbacks.
"""
import os
import uuid
import json
import logging
from datetime import datetime
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_active_user
from app.database import get_db
from app.models.user import User
from app.models.vehicle import UserVehicle
from app.services.ai_embeddings import search_embeddings
from app.models.trip import Trip
from app.models.charging import ChargingSession

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["ai"])

LLM_PROVIDER = os.getenv("AI_LLM_PROVIDER", "minimax")  # minimax | gemini | openai
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "sk-cp-…VNPg")  # from auth-profiles
MINIMAX_BASE_URL = "https://api.minimax.io/anthropic/v1"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


# ─── Schemas ─────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    vehicle_id: str | None = None  # optional filter to specific vehicle
    provider: Literal["minimax", "gemini", "openai"] = "minimax"


class SourceRef(BaseModel):
    type: str
    id: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceRef]
    session_id: str | None = None


# ─── LLM Call Helpers ─────────────────────────────────────────────────

async def _call_minimax(messages: list[dict], model: str = "MiniMax-M2.7") -> str:
    """Call MiniMax chat API (Anthropic-compatible)."""
    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": model,
        "max_tokens": 1024,
        "temperature": 0.3,
        "messages": messages,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{MINIMAX_BASE_URL}/messages",
            headers=headers,
            json=payload,
        )
        if resp.status_code != 200:
            logger.error("MiniMax error: %s %s", resp.status_code, resp.text)
            raise HTTPException(502, f"MiniMax API error: {resp.status_code}")
        data = resp.json()
        return data["content"][0]["text"]


async def _call_gemini(prompt: str, model: str = "gemini-3-flash-preview") -> str:
    """Call Gemini via OpenAI-compatible endpoint."""
    api_key = GEMINI_API_KEY or os.getenv("GOOGLE_API_KEY", "")
    if not api_key:
        raise HTTPException(500, "Gemini API key not configured")
    base_url = "https://generativelanguage.googleapis.com/v1beta/models"
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{base_url}/{model}:generateContent",
            params={"key": api_key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
        )
        if resp.status_code != 200:
            logger.error("Gemini error: %s %s", resp.status_code, resp.text)
            raise HTTPException(502, f"Gemini API error: {resp.status_code}")
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


async def _call_llm(prompt: str, provider: str, context: str) -> str:
    """Call the configured LLM provider. Falls back on error."""
    system_prompt = (
        "You are iVDrive AI Assistant. You help users understand their electric vehicle data. "
        "You have access to the user's vehicle telemetry data (trips, charging sessions, consumption). "
        "Answer based ONLY on the provided data. If you cannot answer from the data, say so honestly. "
        "Be concise, factual, and helpful. Format numbers clearly."
        f"\n\nData context:\n{context}"
    )

    user_message = {"role": "user", "content": prompt}

    # Try primary provider first
    errors = []
    for attempt_provider in [provider, "minimax", "gemini", "openai"]:
        if attempt_provider == "minimax":
            try:
                return await _call_minimax([{"role": "system", "content": system_prompt}, user_message])
            except Exception as e:
                errors.append(f"minimax: {e}")
        elif attempt_provider == "gemini":
            try:
                return await _call_gemini(f"[System]\n{system_prompt}\n\n[User]\n{prompt}")
            except Exception as e:
                errors.append(f"gemini: {e}")
        elif attempt_provider == "openai":
            # Use OpenAI-compatible endpoint
            try:
                api_key = OPENAI_API_KEY
                if not api_key or api_key == "local":
                    api_key = MINIMAX_API_KEY  # fallback
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                payload = {"model": "gpt-4o-mini", "messages": [{"role": "system", "content": system_prompt}, user_message], "max_tokens": 1024, "temperature": 0.3}
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
                    if resp.status_code == 200:
                        return resp.json()["choices"][0]["message"]["content"]
                    errors.append(f"openai: {resp.status_code}")
            except Exception as e:
                errors.append(f"openai: {e}")

    logger.error("All LLM providers failed: %s", errors)
    raise HTTPException(502, f"All LLM providers failed: {errors[0]}")


# ─── Endpoint ─────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Per-user RAG chat endpoint.
    - user_id from JWT
    - vehicle_ids from user's vehicle list (scoped to their account)
    - Only user's data enters the LLM context
    """
    if not req.message.strip():
        raise HTTPException(400, "message cannot be empty")

    # 1. Get user's vehicles
    vehicle_result = await db.execute(
        select(UserVehicle.id).where(UserVehicle.user_id == current_user.id)
    )
    user_vehicle_ids = [row[0] for row in vehicle_result.fetchall()]

    if not user_vehicle_ids:
        return ChatResponse(answer="You have no vehicles connected. Add a vehicle to start chatting.", sources=[])

    # 2. Optional: filter to specific vehicle if requested
    if req.vehicle_id:
        vid = uuid.UUID(req.vehicle_id)
        if vid not in user_vehicle_ids:
            raise HTTPException(403, "Vehicle not owned by user")
        search_vehicle_ids = [vid]
    else:
        search_vehicle_ids = user_vehicle_ids

    # 3. RAG: search embeddings
    try:
        chunks = await search_embeddings(
            user_id=current_user.id,
            vehicle_ids=search_vehicle_ids,
            query=req.message,
            top_k=5,
        )
    except Exception as e:
        logger.warning("Embedding search failed: %s — falling back to direct DB query", e)
        chunks = []

    # 4. If no chunks, try direct DB query as fallback
    if not chunks:
        chunks = await _direct_db_search(db, current_user.id, search_vehicle_ids, req.message)

    # 5. Build context from chunks
    if chunks:
        context = "\n\n".join(
            [f"[{c['chunk_type']}] {c['chunk_text']}" for c in chunks]
        )
    else:
        context = "(No relevant data found. Answer based on general knowledge of electric vehicles.)"

    # 6. Call LLM
    try:
        answer = await _call_llm(req.message, req.provider, context)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("LLM call failed: %s", e)
        raise HTTPException(502, f"LLM error: {e}")

    # 7. Format sources
    sources = [
        SourceRef(type=c["chunk_type"], id=c["metadata"].get("source_id", ""), score=c["score"])
        for c in chunks
    ]

    return ChatResponse(answer=answer, sources=sources)


async def _direct_db_search(
    db: AsyncSession,
    user_id: uuid.UUID,
    vehicle_ids: list[uuid.UUID],
    query: str,
    limit: int = 5,
) -> list[dict]:
    """
    Fallback: search trips/charging directly from DB when no embeddings exist yet.
    Returns formatted chunks from raw SQL data.
    """
    results = []
    vehicle_ids_str = ",".join(f"'{v}'" for v in vehicle_ids)

    # Search trips
    trip_sql = text(f"""
        SELECT id, start_address, end_address, distance_km, duration_min,
               avg_speed_kmh, avg_consumption_kwh100km, start_time
        FROM trips
        WHERE user_vehicle_id IN ({vehicle_ids_str})
        ORDER BY start_time DESC
        LIMIT {limit}
    """)
    trip_result = await db.execute(trip_sql)
    for row in trip_result.fetchall():
        results.append({
            "chunk_type": "trip_summary",
            "chunk_text": (
                f"Trip: {row[1] or 'Unknown'} → {row[2] or 'Unknown'}. "
                f"Distance: {row[3] or 0}km. Duration: {row[4] or 0}min. "
                f"Avg speed: {row[5] or 0}km/h. Consumption: {row[6] or 0}kWh/100km."
            ),
            "metadata": {"source_id": str(row[0])},
            "score": 0.8,
        })

    # Search charging
    charge_sql = text(f"""
        SELECT id, soc_pct_start, soc_pct_end, energy_kwh, duration_minutes,
               base_cost_eur, started_at
        FROM charging_sessions
        WHERE user_vehicle_id IN ({vehicle_ids_str})
        ORDER BY started_at DESC
        LIMIT {limit}
    """)
    charge_result = await db.execute(charge_sql)
    for row in charge_result.fetchall():
        results.append({
            "chunk_type": "charging_event",
            "chunk_text": (
                f"Charging: Start SOC {row[1] or '?'}% → End SOC {row[2] or '?'}%. "
                f"Energy: {row[3] or 0}kWh. Duration: {row[4] or 0}min. Cost: {row[5] or 0}EUR."
            ),
            "metadata": {"source_id": str(row[0])},
            "score": 0.8,
        })

    return results


# ─── Auth dependency (reuses existing logic) ──────────────────────────

async def get_current_user_from_jwt(
    db: AsyncSession = Depends(get_db),
    authorization: str = None,
) -> User:
    """
    Reads Bearer token from Authorization header.
    For API calls from frontend, the existing get_current_active_user dependency handles cookie-based auth.
    This dependency is for external callers passing a Bearer token directly.
    """
    from fastapi import Header
    from app.security import decode_access_token

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header")

    token = authorization.replace("Bearer ", "")
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(401, "Invalid token")
    except Exception:
        raise HTTPException(401, "Invalid or expired token")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(401, "User not found")
    return user