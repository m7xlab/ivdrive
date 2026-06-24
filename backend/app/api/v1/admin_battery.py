"""Battery SoH admin endpoints.

Mirrors /admin/ai/ shape. All routes require superuser.

Endpoints:
  GET    /battery/tier-configs                 — list free/plus/pro
  PUT    /battery/tier-configs/{tier}         — edit tier defaults
  GET    /battery/users                       — per-user battery access state
  PUT    /battery/users/{user_id}             — set per-user override
  GET    /battery/usage                       — usage log (estimates, PDFs, alerts)
  GET    /battery/usage/summary               — fleet-wide aggregates
  GET    /battery/health                      — fleet ops monitoring (stale/anomalous)
  POST   /battery/vehicles/{vehicle_id}/recompute  — force re-estimate
"""
import uuid
from datetime import datetime, timedelta, timezone
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

class BatteryTierConfigUpdate(BaseModel):
    pdf_enabled: bool | None = None
    alerts_enabled: bool | None = None
    resale_calc_enabled: bool | None = None
    estimate_frequency: Literal["daily", "weekly", "monthly"] | None = None
    min_confidence_required: Literal["low", "medium", "high"] | None = None
    monthly_price_eur: float | None = Field(None, ge=0)
    description: str | None = None


class BatteryUserOverrideUpdate(BaseModel):
    tier_override: Literal["free", "plus", "pro"] | None = None
    pdf_enabled_override: bool | None = None
    alerts_enabled_override: bool | None = None
    note: str | None = None


class RecomputeRequest(BaseModel):
    lookback_days: int = Field(365, ge=30, le=730)


# ─── Tier configs ───────────────────────────────────────────────────────────

@router.get("/battery/tier-configs")
async def list_tier_configs(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser),
):
    rows = (await db.execute(
        text("""
            SELECT tier, pdf_enabled, alerts_enabled, resale_calc_enabled,
                   estimate_frequency, min_confidence_required, monthly_price_eur,
                   description, updated_at
            FROM battery_tier_configs
            ORDER BY CASE tier WHEN 'free' THEN 1 WHEN 'plus' THEN 2 WHEN 'pro' THEN 3 END
        """)
    )).mappings().all()
    return [dict(r) for r in rows]


@router.put("/battery/tier-configs/{tier}")
async def update_tier_config(
    tier: Literal["free", "plus", "pro"],
    body: BatteryTierConfigUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser),
):
    sets = []
    params: dict = {"tier": tier}
    for field_name in (
        "pdf_enabled", "alerts_enabled", "resale_calc_enabled",
        "estimate_frequency", "min_confidence_required",
        "monthly_price_eur", "description",
    ):
        v = getattr(body, field_name)
        if v is not None:
            sets.append(f"{field_name} = :{field_name}")
            params[field_name] = v
    if not sets:
        raise HTTPException(status_code=400, detail="No fields to update")
    sets.append("updated_at = NOW()")

    result = await db.execute(
        text(f"UPDATE battery_tier_configs SET {', '.join(sets)} WHERE tier = :tier"),
        params,
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Unknown tier: {tier}")
    await db.commit()
    return {"tier": tier, "updated": True}


# ─── Users (per-user overrides) ─────────────────────────────────────────────

@router.get("/battery/users")
async def list_user_battery_access(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser),
    limit: int = Query(50, ge=1, le=500),
):
    """Per-user battery state — joined with latest estimate + open alerts."""
    rows = (await db.execute(text("""
        SELECT
          uv.user_id::text AS user_id,
          u.email,
          u.display_name,
          uv.id::text AS user_vehicle_id,
          uv.display_name AS vehicle_name,
          uv.battery_capacity_kwh,
          o.tier_override,
          o.pdf_enabled_override,
          o.alerts_enabled_override,
          o.note,
          latest.soh_pct AS latest_soh_pct,
          latest.estimated_at AS latest_estimated_at,
          latest.confidence AS latest_confidence,
          alerts.open_alerts
        FROM user_vehicles uv
        JOIN users u ON u.id = uv.user_id
        LEFT JOIN battery_user_overrides o ON o.user_id = uv.user_id
        LEFT JOIN LATERAL (
          SELECT soh_pct, estimated_at, confidence
          FROM battery_soh_estimates
          WHERE user_vehicle_id = uv.id AND method = 'aggregate'
          ORDER BY estimated_at DESC LIMIT 1
        ) latest ON true
        LEFT JOIN LATERAL (
          SELECT COUNT(*)::int AS open_alerts
          FROM battery_soh_alerts
          WHERE user_vehicle_id = uv.id AND acknowledged_at IS NULL
        ) alerts ON true
        ORDER BY uv.created_at DESC
        LIMIT :limit
    """), {"limit": limit})).mappings().all()
    return [dict(r) for r in rows]


@router.put("/battery/users/{user_id}")
async def update_user_battery_override(
    user_id: uuid.UUID,
    body: BatteryUserOverrideUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser),
):
    u = (await db.execute(
        text("SELECT id FROM users WHERE id = :uid"),
        {"uid": str(user_id)},
    )).fetchone()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")

    await db.execute(text("""
        INSERT INTO battery_user_overrides (
          user_id, tier_override, pdf_enabled_override, alerts_enabled_override,
          note, updated_by_user_id, updated_at
        ) VALUES (
          :uid, :tier, :pdf, :alerts, :note, :admin_id, NOW()
        )
        ON CONFLICT (user_id) DO UPDATE SET
          tier_override = COALESCE(EXCLUDED.tier_override, battery_user_overrides.tier_override),
          pdf_enabled_override = COALESCE(EXCLUDED.pdf_enabled_override, battery_user_overrides.pdf_enabled_override),
          alerts_enabled_override = COALESCE(EXCLUDED.alerts_enabled_override, battery_user_overrides.alerts_enabled_override),
          note = EXCLUDED.note,
          updated_by_user_id = EXCLUDED.updated_by_user_id,
          updated_at = NOW()
    """), {
        "uid": str(user_id),
        "tier": body.tier_override,
        "pdf": body.pdf_enabled_override,
        "alerts": body.alerts_enabled_override,
        "note": body.note,
        "admin_id": str(admin.id),
    })

    # Audit log
    await db.execute(text("""
        INSERT INTO battery_soh_usage_log (user_id, event_type, metadata_json)
        VALUES (:uid, 'admin_override', CAST(:meta AS JSONB))
    """), {
        "uid": str(user_id),
        "meta": f'{{"tier_override": "{body.tier_override}", "by_admin": "{admin.id}"}}',
    })
    await db.commit()
    return {"user_id": str(user_id), "updated": True}


# ─── Usage log + summary ────────────────────────────────────────────────────

@router.get("/battery/usage")
async def list_usage(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser),
    event_type: Literal["estimate_generated", "pdf_sent", "alert_fired", "admin_override", "tier_change"] | None = None,
    user_id: uuid.UUID | None = None,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(100, ge=1, le=1000),
):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    sql = """
        SELECT
          l.id::text, l.user_id::text, l.user_vehicle_id::text,
          l.event_type, l.event_at, l.soh_pct, l.confidence, l.metadata_json,
          u.email, uv.display_name AS vehicle_name
        FROM battery_soh_usage_log l
        LEFT JOIN users u ON u.id = l.user_id
        LEFT JOIN user_vehicles uv ON uv.id = l.user_vehicle_id
        WHERE l.event_at >= :cutoff
    """
    params: dict = {"cutoff": cutoff, "limit": limit}
    if event_type:
        sql += " AND l.event_type = :event_type"
        params["event_type"] = event_type
    if user_id:
        sql += " AND l.user_id = :uid"
        params["uid"] = str(user_id)
    sql += " ORDER BY l.event_at DESC LIMIT :limit"

    rows = (await db.execute(text(sql), params)).mappings().all()
    return [dict(r) for r in rows]


@router.get("/battery/usage/summary")
async def usage_summary(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser),
    days: int = Query(30, ge=1, le=365),
):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (await db.execute(text("""
        SELECT
          event_type,
          COUNT(*)::int AS n,
          COUNT(DISTINCT user_id)::int AS unique_users,
          COUNT(DISTINCT user_vehicle_id)::int AS unique_vehicles
        FROM battery_soh_usage_log
        WHERE event_at >= :cutoff
        GROUP BY event_type
        ORDER BY n DESC
    """), {"cutoff": cutoff})).mappings().all()
    return [dict(r) for r in rows]


# ─── Fleet health (ops monitoring) ──────────────────────────────────────────

@router.get("/battery/health")
async def fleet_health(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser),
):
    """Fleet-wide battery ops dashboard for Gedas.

    Returns:
      - total_vehicles: count of all user_vehicles
      - vehicles_with_estimate: count with at least 1 aggregate estimate
      - stale_vehicles: count whose latest estimate is >30 days old
      - vehicles_with_alerts: count with open alerts
      - fleet_avg_soh: weighted average across all vehicles' latest aggregate
      - tier_distribution: how many vehicles on each tier (no tier table for users; derived from overrides)
    """
    rows = (await db.execute(text("""
        WITH latest AS (
          SELECT DISTINCT ON (user_vehicle_id)
            user_vehicle_id, soh_pct, confidence, estimated_at
          FROM battery_soh_estimates
          WHERE method = 'aggregate'
          ORDER BY user_vehicle_id, estimated_at DESC
        ),
        alert_counts AS (
          SELECT user_vehicle_id, COUNT(*)::int AS n
          FROM battery_soh_alerts WHERE acknowledged_at IS NULL
          GROUP BY user_vehicle_id
        )
        SELECT
          (SELECT COUNT(*)::int FROM user_vehicles) AS total_vehicles,
          (SELECT COUNT(DISTINCT user_vehicle_id)::int FROM latest) AS vehicles_with_estimate,
          (SELECT COUNT(*)::int FROM latest WHERE estimated_at < NOW() - INTERVAL '30 days') AS stale_vehicles,
          (SELECT COUNT(*)::int FROM alert_counts) AS vehicles_with_alerts,
          (SELECT ROUND(AVG(soh_pct)::numeric, 2) FROM latest) AS fleet_avg_soh,
          (SELECT MIN(soh_pct) FROM latest) AS fleet_min_soh,
          (SELECT MAX(soh_pct) FROM latest) AS fleet_max_soh
    """))).mappings().first()
    return dict(rows) if rows else {}


# ─── Manual recompute ───────────────────────────────────────────────────────

@router.post("/battery/vehicles/{vehicle_id}/recompute")
async def recompute_estimate(
    vehicle_id: uuid.UUID,
    body: RecomputeRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser),
):
    """Force a fresh SoH estimate for one vehicle. Useful for QA + manual fixes."""
    v = (await db.execute(
        text("SELECT id, battery_capacity_kwh FROM user_vehicles WHERE id = :vid"),
        {"vid": str(vehicle_id)},
    )).fetchone()
    if not v:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    if not v.battery_capacity_kwh:
        raise HTTPException(status_code=400, detail="Vehicle has no factory battery_capacity_kwh")

    from app.services.battery_soh import compute_and_store_estimate
    result = await compute_and_store_estimate(db, vehicle_id, float(v.battery_capacity_kwh), body.lookback_days)

    # Audit
    await db.execute(text("""
        INSERT INTO battery_soh_usage_log (user_id, user_vehicle_id, event_type, soh_pct, confidence, metadata_json)
        SELECT user_id, :vid, 'estimate_generated', :soh, :conf, CAST(:meta AS JSONB)
        FROM user_vehicles WHERE id = :vid
    """), {
        "vid": str(vehicle_id),
        "soh": result.soh_pct if result else None,
        "conf": result.confidence if result else None,
        "meta": f'{{"trigger": "manual", "by_admin": "{admin.id}", "lookback_days": {body.lookback_days}}}',
    })
    await db.commit()

    if not result:
        raise HTTPException(status_code=422, detail="No valid data to compute estimate")
    return {
        "vehicle_id": str(vehicle_id),
        "soh_pct": result.soh_pct,
        "estimated_kwh": result.estimated_kwh,
        "confidence": result.confidence,
        "sample_count": result.sample_count,
    }


__all__ = ["router"]