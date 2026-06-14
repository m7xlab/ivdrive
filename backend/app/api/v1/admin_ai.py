"""AI Assistant admin endpoints.

Mounted under /api/v1/admin. All routes require a superuser.
- GET   /ai/usage                 — usage log with filters (user, date range, tier)
- GET   /ai/usage/summary         — aggregate stats (today's calls, top users, costs)
- PUT   /ai/users/{user_id}       — set ai_enabled + ai_tier for a user
- PUT   /ai/tier-configs/{tier}   — edit tier defaults (caps, model)
- GET   /ai/tier-configs          — list all tier configs (free, pro, team)
- GET   /ai/users                 — quick per-user view of their AI access state
"""
import uuid
from datetime import datetime, date, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.api.v1.dependencies import get_current_superuser

router = APIRouter()


# ─── Schemas ────────────────────────────────────────────────────────────────
class AITierUpdate(BaseModel):
    ai_enabled: bool | None = Field(None, description="Master switch for this user")
    ai_tier: Literal["free", "pro", "team"] | None = Field(None, description="Tier label")
    # Optional per-user override (admin can grant this user a custom cap)
    max_questions_per_day: int | None = Field(None, ge=0, le=100000)
    max_questions_per_month: int | None = Field(None, ge=0, le=1000000)
    model_provider: str | None = None
    model_name: str | None = None
    note: str | None = Field(None, description="Admin note (e.g. 'promoted 2026-06-08')")


class AITierConfigUpdate(BaseModel):
    max_questions_per_day: int | None = Field(None, ge=0, le=100000)
    max_questions_per_month: int | None = Field(None, ge=0, le=1000000)
    model_provider: str | None = None
    model_name: str | None = None
    daily_cost_limit_usd: float | None = Field(None, ge=0)
    description: str | None = None


class EmbeddingBackfillRequest(BaseModel):
    mode: Literal["missing", "all"] = Field(
        "missing",
        description="'missing' = only enqueue vehicle/content pairs not yet embedded "
                    "(safe, cheap, idempotent). 'all' = re-enqueue every pair, forcing a "
                    "full re-embed (use after an embedding model/dimension change).",
    )


# ─── User AI access (per-user overrides) ───────────────────────────────────
@router.get("/ai/users")
async def list_user_ai_access(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser),
    tier: Literal["free", "pro", "team"] | None = Query(None, description="Filter by tier"),
    enabled: bool | None = Query(None, description="Filter by enabled flag"),
    limit: int = Query(50, ge=1, le=500),
):
    """Per-user view of AI access state. Joined with today's usage."""
    sql = """
        SELECT
          u.id::text AS user_id,
          u.email,
          u.display_name,
          u.ai_enabled,
          u.ai_tier,
          o.tier_override,
          o.ai_enabled_override,
          COALESCE(o.max_questions_per_day, t.max_questions_per_day) AS effective_max_day,
          COALESCE(o.max_questions_per_month, t.max_questions_per_month) AS effective_max_month,
          t.model_provider,
          t.model_name,
          COALESCE(today.n, 0) AS used_today,
          COALESCE(monthly.n, 0) AS used_this_month,
          u.created_at
        FROM users u
        LEFT JOIN ai_user_overrides o ON o.user_id = u.id
        LEFT JOIN ai_tier_configs t ON t.tier = u.ai_tier
        LEFT JOIN (
          SELECT user_id, COUNT(*)::int AS n FROM ai_usage_log
          WHERE blocked_reason IS NULL
            AND requested_at >= date_trunc('day', NOW() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
          GROUP BY user_id
        ) today ON today.user_id = u.id
        LEFT JOIN (
          SELECT user_id, COUNT(*)::int AS n FROM ai_usage_log
          WHERE blocked_reason IS NULL
            AND requested_at >= date_trunc('month', NOW() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
          GROUP BY user_id
        ) monthly ON monthly.user_id = u.id
        WHERE 1=1
    """
    params: dict = {"limit": limit}
    if tier:
        sql += " AND u.ai_tier = :tier"
        params["tier"] = tier
    if enabled is not None:
        sql += " AND u.ai_enabled = :enabled"
        params["enabled"] = enabled
    sql += " ORDER BY u.created_at ASC LIMIT :limit"

    rows = (await db.execute(text(sql), params)).mappings().all()
    return [dict(r) for r in rows]


@router.put("/ai/users/{user_id}")
async def update_user_ai_access(
    user_id: uuid.UUID,
    body: AITierUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser),
):
    """Update a user's AI access. Sets users.ai_enabled/ai_tier, and upserts
    ai_user_overrides if any per-user override fields are provided."""
    # Verify user exists
    u = (await db.execute(text("SELECT id FROM users WHERE id = :uid"), {"uid": str(user_id)})).fetchone()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    # Update users table (master fields)
    sets = []
    params: dict = {"uid": str(user_id)}
    if body.ai_enabled is not None:
        sets.append("ai_enabled = :ai_enabled")
        params["ai_enabled"] = body.ai_enabled
    if body.ai_tier is not None:
        sets.append("ai_tier = :ai_tier")
        params["ai_tier"] = body.ai_tier
    if sets:
        await db.execute(
            text(f"UPDATE users SET {', '.join(sets)} WHERE id = :uid"),
            params,
        )

    # Upsert override row if any override field present
    has_override = any(
        v is not None for v in (
            body.max_questions_per_day, body.max_questions_per_month,
            body.model_provider, body.model_name, body.note
        )
    )
    if has_override:
        await db.execute(
            text("""
                INSERT INTO ai_user_overrides (
                  user_id, max_questions_per_day, max_questions_per_month,
                  model_provider, model_name, note, updated_by_user_id, updated_at
                ) VALUES (
                  :uid, :max_d, :max_m, :prov, :model, :note, :admin_id, NOW()
                )
                ON CONFLICT (user_id) DO UPDATE SET
                  -- Preserve existing values when a field is omitted from the
                  -- request (passed as NULL). A bare EXCLUDED.x here would wipe
                  -- every other override when an admin edits just one field.
                  max_questions_per_day = COALESCE(EXCLUDED.max_questions_per_day, ai_user_overrides.max_questions_per_day),
                  max_questions_per_month = COALESCE(EXCLUDED.max_questions_per_month, ai_user_overrides.max_questions_per_month),
                  model_provider = COALESCE(EXCLUDED.model_provider, ai_user_overrides.model_provider),
                  model_name = COALESCE(EXCLUDED.model_name, ai_user_overrides.model_name),
                  note = COALESCE(EXCLUDED.note, ai_user_overrides.note),
                  updated_by_user_id = EXCLUDED.updated_by_user_id,
                  updated_at = NOW()
            """),
            {
                "uid": str(user_id),
                "max_d": body.max_questions_per_day,
                "max_m": body.max_questions_per_month,
                "prov": body.model_provider,
                "model": body.model_name,
                "note": body.note,
                "admin_id": str(admin.id),
            },
        )

    await db.commit()
    return {"ok": True, "user_id": str(user_id)}


# ─── Tier configs (admin-editable defaults) ───────────────────────────────
@router.get("/ai/tier-configs")
async def list_tier_configs(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser),
):
    rows = (await db.execute(
        text("SELECT tier, max_questions_per_day, max_questions_per_month, model_provider, model_name, daily_cost_limit_usd, description, updated_at FROM ai_tier_configs ORDER BY tier")
    )).mappings().all()
    return [dict(r) for r in rows]


@router.put("/ai/tier-configs/{tier}")
async def update_tier_config(
    tier: Literal["free", "pro", "team"],
    body: AITierConfigUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser),
):
    sets, params = [], {"tier": tier}
    for field, col in [
        ("max_questions_per_day", "max_questions_per_day"),
        ("max_questions_per_month", "max_questions_per_month"),
        ("model_provider", "model_provider"),
        ("model_name", "model_name"),
        ("daily_cost_limit_usd", "daily_cost_limit_usd"),
        ("description", "description"),
    ]:
        val = getattr(body, field)
        if val is not None:
            sets.append(f"{col} = :{col}")
            params[col] = val
    if not sets:
        raise HTTPException(status_code=400, detail="No fields to update")
    await db.execute(
        text(f"UPDATE ai_tier_configs SET {', '.join(sets)} WHERE tier = :tier"),
        params,
    )
    await db.commit()
    return {"ok": True, "tier": tier}


# ─── Usage log + summary ───────────────────────────────────────────────────
@router.get("/ai/usage")
async def list_ai_usage(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser),
    user_id: str | None = Query(None, description="Filter by user UUID"),
    user_email: str | None = Query(None, description="Filter by user email (LIKE)"),
    blocked_only: bool | None = Query(None, description="Show only blocked requests"),
    from_date: date | None = Query(None, description="UTC start date (inclusive)"),
    to_date: date | None = Query(None, description="UTC end date (inclusive)"),
    limit: int = Query(100, ge=1, le=1000),
):
    """Paginated usage log. Most recent first."""
    where = ["1=1"]
    params: dict = {"limit": limit}
    if user_id:
        where.append("u.id = :uid")
        params["uid"] = user_id
    if user_email:
        where.append("u.email ILIKE :uemail")
        params["uemail"] = f"%{user_email}%"
    if blocked_only is not None:
        if blocked_only:
            where.append("l.blocked_reason IS NOT NULL")
        else:
            where.append("l.blocked_reason IS NULL")
    if from_date:
        where.append("l.requested_at >= :from_ts")
        params["from_ts"] = datetime.combine(from_date, datetime.min.time(), tzinfo=timezone.utc)
    if to_date:
        where.append("l.requested_at < :to_ts")
        params["to_ts"] = datetime.combine(to_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)

    sql = f"""
        SELECT
          l.id::text,
          l.user_id::text,
          u.email,
          u.ai_tier,
          l.vehicle_id::text,
          l.session_id::text,
          l.requested_at,
          l.model_provider,
          l.model_name,
          l.prompt_tokens,
          l.completion_tokens,
          l.cached_tokens,
          l.estimated_cost_usd,
          l.blocked_reason,
          l.question_chars
        FROM ai_usage_log l
        JOIN users u ON u.id = l.user_id
        WHERE {' AND '.join(where)}
        ORDER BY l.requested_at DESC
        LIMIT :limit
    """
    rows = (await db.execute(text(sql), params)).mappings().all()
    return [dict(r) for r in rows]


@router.get("/ai/usage/summary")
async def ai_usage_summary(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser),
):
    """Aggregate stats for the admin dashboard."""
    sql = text("""
        WITH today AS (
          SELECT
            COUNT(*)::int AS calls_today,
            COUNT(*) FILTER (WHERE blocked_reason IS NULL)::int AS allowed_today,
            COUNT(*) FILTER (WHERE blocked_reason IS NOT NULL)::int AS blocked_today,
            COALESCE(SUM(estimated_cost_usd), 0)::float AS cost_today
          FROM ai_usage_log
          WHERE requested_at >= date_trunc('day', NOW() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
        ),
        month AS (
          SELECT
            COUNT(*)::int AS calls_month,
            COALESCE(SUM(estimated_cost_usd), 0)::float AS cost_month
          FROM ai_usage_log
          WHERE requested_at >= date_trunc('month', NOW() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
        ),
        all_time AS (
          SELECT
            COUNT(*)::int AS calls_total,
            COUNT(DISTINCT user_id)::int AS unique_users,
            COALESCE(SUM(estimated_cost_usd), 0)::float AS cost_total
          FROM ai_usage_log
        ),
        top_users AS (
          SELECT u.email, u.ai_tier, COUNT(*)::int AS calls
          FROM ai_usage_log l JOIN users u ON u.id = l.user_id
          WHERE l.blocked_reason IS NULL
            AND l.requested_at >= date_trunc('day', NOW() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
          GROUP BY u.email, u.ai_tier
          ORDER BY calls DESC
          LIMIT 5
        ),
        blocked_breakdown AS (
          SELECT blocked_reason, COUNT(*)::int AS n
          FROM ai_usage_log
          WHERE blocked_reason IS NOT NULL
            AND requested_at >= date_trunc('day', NOW() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'
          GROUP BY blocked_reason
        )
        SELECT
          (SELECT calls_today FROM today) AS calls_today,
          (SELECT allowed_today FROM today) AS allowed_today,
          (SELECT blocked_today FROM today) AS blocked_today,
          (SELECT cost_today FROM today) AS cost_today_usd,
          (SELECT calls_month FROM month) AS calls_month,
          (SELECT cost_month FROM month) AS cost_month_usd,
          (SELECT calls_total FROM all_time) AS calls_total,
          (SELECT unique_users FROM all_time) AS unique_users,
          (SELECT cost_total FROM all_time) AS cost_total_usd,
          COALESCE((SELECT json_agg(row_to_json(t)) FROM top_users t), '[]'::json) AS top_users,
          COALESCE((SELECT json_agg(row_to_json(b)) FROM blocked_breakdown b), '[]'::json) AS blocked_breakdown
    """)
    row = (await db.execute(sql)).mappings().first()
    return dict(row) if row else {}


# ─── RAG embeddings: status + manual backfill ──────────────────────────────
@router.get("/ai/embeddings/status")
async def ai_embeddings_status(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser),
):
    """RAG corpus health for the admin console.

    `expected` = vehicles × registered content types. `embedded` counts rows
    actually present in ai_embeddings for those registered types. The queue
    counts show in-flight backfill work the collector worker is draining.
    """
    from app.services.embedding_builders import CONTENT_TYPES

    content_types = list(CONTENT_TYPES.keys())

    scalars = (await db.execute(
        text("""
            SELECT
              (SELECT COUNT(*) FROM user_vehicles)::int                                  AS vehicles,
              (SELECT COUNT(*) FROM ai_embeddings WHERE content_type = ANY(:cts))::int   AS embedded,
              (SELECT COUNT(*) FROM ai_embeddings_queue WHERE status = 'pending')::int    AS queue_pending,
              (SELECT COUNT(*) FROM ai_embeddings_queue WHERE status = 'processing')::int AS queue_processing,
              (SELECT COUNT(*) FROM ai_embeddings_queue WHERE status = 'error')::int       AS queue_error,
              (SELECT MAX(updated_at) FROM ai_embeddings)                                  AS last_embedded_at
        """),
        {"cts": content_types},
    )).mappings().first()

    by_type = (await db.execute(
        text("""
            SELECT content_type, COUNT(*)::int AS embedded
            FROM ai_embeddings
            WHERE content_type = ANY(:cts)
            GROUP BY content_type
        """),
        {"cts": content_types},
    )).mappings().all()

    out = dict(scalars) if scalars else {}
    out["content_types"] = content_types
    out["expected"] = (out.get("vehicles", 0) or 0) * len(content_types)
    out["by_type"] = [dict(r) for r in by_type]
    return out


@router.post("/ai/embeddings/backfill")
async def ai_embeddings_backfill(
    body: EmbeddingBackfillRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser),
):
    """Enqueue RAG embedding work for every vehicle × registered content type.

    This does NOT call the embedding API — it only inserts 'pending' rows into
    ai_embeddings_queue (pure SQL, fast, bounded). The collector's embedding
    worker drains the queue asynchronously, building each doc and calling the
    configured provider, with its own retry/attempts handling.

    mode='missing' (default): skip pairs already embedded — cheap top-up.
    mode='all': re-enqueue everything — full re-embed after a model change.

    In both modes, pairs already 'pending' in the queue are skipped so repeated
    clicks don't pile up duplicate work.
    """
    from app.services.embedding_builders import CONTENT_TYPES

    ct_items = list(CONTENT_TYPES.items())  # [(content_type, (prefix, builder)), ...]
    if not ct_items:
        return {"ok": True, "enqueued": 0, "mode": body.mode, "detail": "no content builders registered"}

    # Pass the registry as two parallel text[] arrays and unnest them into a
    # (content_type, prefix) derived table. NOTE: we avoid the `:param::text`
    # cast form — SQLAlchemy's text() bind-param regex does NOT match a param
    # immediately followed by `::`, so `:cts::text[]` would leave a literal
    # ":cts" in the SQL. Use CAST(:param AS ...) instead.
    params = {
        "cts": [c for c, _ in ct_items],
        "pfxs": [p for _, (p, _b) in ct_items],
    }

    # mode='missing' additionally skips pairs that already have an embedding row.
    missing_clause = ""
    if body.mode == "missing":
        missing_clause = """
              AND NOT EXISTS (
                SELECT 1 FROM ai_embeddings e
                WHERE e.content_type = ct.content_type
                  AND e.content_id = ct.prefix || ':' || v.id::text
              )"""

    result = await db.execute(
        text(f"""
            INSERT INTO ai_embeddings_queue
              (id, user_id, vehicle_id, content_type, content_id, status, priority, created_at, updated_at)
            SELECT
              gen_random_uuid(), v.user_id, v.id,
              ct.content_type, ct.prefix || ':' || v.id::text,
              'pending', 0, NOW(), NOW()
            FROM user_vehicles v
            CROSS JOIN unnest(CAST(:cts AS text[]), CAST(:pfxs AS text[])) AS ct(content_type, prefix)
            WHERE NOT EXISTS (
                SELECT 1 FROM ai_embeddings_queue q
                WHERE q.content_type = ct.content_type
                  AND q.content_id = ct.prefix || ':' || v.id::text
                  AND q.status = 'pending'
              ){missing_clause}
        """),
        params,
    )
    await db.commit()

    enqueued = result.rowcount if result.rowcount is not None and result.rowcount >= 0 else 0
    return {
        "ok": True,
        "mode": body.mode,
        "enqueued": enqueued,
        "content_types": [c for c, _ in ct_items],
        "detail": "Queued for the background embedding worker. Watch the queue depth fall on the status card.",
    }
