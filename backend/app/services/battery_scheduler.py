"""Battery SoH scheduler — runs the ops model continuously.

Three job types:
  - recompute_vehicle   (per-vehicle, daily cadence)
  - detect_anomalies    (fleet-wide, every 6h)
  - monthly_passport    (1st of month, per eligible vehicle)

All jobs are idempotent and write to battery_soh_usage_log for audit.

Uses AsyncIOScheduler, same pattern as services/collector.py.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.vehicle import UserVehicle
from app.services.battery_soh import (
    compute_and_store_estimate,
    detect_sudden_drop,
)


log = logging.getLogger("app.battery_scheduler")


# ─── Job: recompute single vehicle ──────────────────────────────────────────

async def job_recompute_vehicle(vehicle_id: str, lookback_days: int = 365) -> dict[str, Any]:
    async with async_session() as db:
        v = (await db.execute(
            text("SELECT battery_capacity_kwh FROM user_vehicles WHERE id = :vid"),
            {"vid": vehicle_id},
        )).fetchone()
        if not v or not v.battery_capacity_kwh:
            return {"vehicle_id": vehicle_id, "skipped": "no_capacity"}

        result = await compute_and_store_estimate(db, vehicle_id, float(v.battery_capacity_kwh), lookback_days)
        if not result:
            return {"vehicle_id": vehicle_id, "skipped": "no_data"}

        await db.execute(text("""
            INSERT INTO battery_soh_usage_log (user_id, user_vehicle_id, event_type, soh_pct, confidence)
            SELECT user_id, :vid, 'estimate_generated', :soh, :conf
            FROM user_vehicles WHERE id = :vid
        """), {"vid": vehicle_id, "soh": result.soh_pct, "conf": result.confidence})
        await db.commit()

        return {
            "vehicle_id": vehicle_id,
            "soh_pct": result.soh_pct,
            "estimated_kwh": result.estimated_kwh,
            "confidence": result.confidence,
        }


# ─── Job: detect anomalies ──────────────────────────────────────────────────

async def job_detect_anomalies() -> dict[str, Any]:
    """Scan all vehicles for sudden drops and write alerts."""
    alerts_fired = 0

    async with async_session() as db:
        vehicles = (await db.execute(
            text("SELECT id::text FROM user_vehicles WHERE collection_enabled = true")
        )).fetchall()

        for row in vehicles:
            vid = row[0]
            try:
                alert = await detect_sudden_drop(db, vid, window_days=30)
            except Exception as e:
                log.warning(f"anomaly detect failed for {vid}: {e}")
                continue

            if alert:
                # Check if an unacknowledged alert of the same type already exists
                existing = (await db.execute(text("""
                    SELECT id FROM battery_soh_alerts
                    WHERE user_vehicle_id = :vid
                      AND alert_type = :atype
                      AND acknowledged_at IS NULL
                    LIMIT 1
                """), {"vid": vid, "atype": alert["alert_type"]})).fetchone()

                if not existing:
                    await db.execute(text("""
                        INSERT INTO battery_soh_alerts (
                            user_vehicle_id, alert_type, severity,
                            soh_before, soh_after, delta_pct, message
                        ) VALUES (
                            :vid, :atype, :sev, :before, :after, :delta, :msg
                        )
                    """), {
                        "vid": vid,
                        "atype": alert["alert_type"],
                        "sev": alert["severity"],
                        "before": alert["soh_before"],
                        "after": alert["soh_after"],
                        "delta": alert["delta_pct"],
                        "msg": alert["message"],
                    })
                    await db.execute(text("""
                        INSERT INTO battery_soh_usage_log (user_id, user_vehicle_id, event_type, soh_pct, metadata_json)
                        SELECT user_id, :vid, 'alert_fired', :soh, CAST(:meta AS JSONB)
                        FROM user_vehicles WHERE id = :vid
                    """), {
                        "vid": vid,
                        "soh": alert["soh_after"],
                        "meta": f'{{"alert_type": "{alert["alert_type"]}", "severity": "{alert["severity"]}"}}',
                    })
                    alerts_fired += 1
        await db.commit()

    return {"vehicles_scanned": len(vehicles), "alerts_fired": alerts_fired}


# ─── Job: monthly Passport ─────────────────────────────────────────────────

async def job_monthly_passport() -> dict[str, Any]:
    """Generate monthly Passport PDFs for all eligible vehicles.

    Eligibility (from battery_tier_configs):
      - tier_override IS NULL OR tier_override IN ('plus', 'pro')
      - pdf_enabled_override is not FALSE (when set)
      - latest aggregate estimate confidence meets min_confidence_required
    """
    pdfs_queued = 0
    eligible_vehicles: list[tuple[str, str]] = []  # (vehicle_id, tier)

    async with async_session() as db:
        rows = (await db.execute(text("""
            WITH latest AS (
              SELECT DISTINCT ON (user_vehicle_id)
                user_vehicle_id, soh_pct, confidence
              FROM battery_soh_estimates
              WHERE method = 'aggregate'
              ORDER BY user_vehicle_id, estimated_at DESC
            )
            SELECT
              uv.id::text AS vehicle_id,
              uv.user_id::text AS user_id,
              uv.display_name,
              COALESCE(o.tier_override, 'free') AS tier,
              COALESCE(o.pdf_enabled_override, t.pdf_enabled) AS pdf_enabled,
              t.min_confidence_required,
              latest.soh_pct,
              latest.confidence
            FROM user_vehicles uv
            LEFT JOIN battery_user_overrides o ON o.user_id = uv.user_id
            CROSS JOIN battery_tier_configs t
            LEFT JOIN latest ON latest.user_vehicle_id = uv.id
            WHERE t.tier = COALESCE(o.tier_override, 'free')
              AND COALESCE(o.pdf_enabled_override, t.pdf_enabled) = true
              AND latest.soh_pct IS NOT NULL
        """))).fetchall()

        confidence_rank = {"low": 0, "medium": 1, "high": 2}
        for r in rows:
            required = r.min_confidence_required or "medium"
            actual = r.confidence or "low"
            if confidence_rank.get(actual, 0) >= confidence_rank.get(required, 1):
                eligible_vehicles.append((r.vehicle_id, r.tier))

    # Generate PDF + upload to object storage + email with link + attachment
    from app.services.battery_passport import (
        generate_passport_html,
        generate_passport_pdf,
        upload_passport_pdf,
        generate_passport_download_url,
        send_passport_email,
    )

    for vehicle_id, tier in eligible_vehicles:
        try:
            subject, html_body = await generate_passport_html(vehicle_id)

            # Generate real PDF in parallel with the HTML (independent work)
            pdf_bytes = await generate_passport_pdf(vehicle_id)

            # Upload PDF to S3/GCS (async, non-blocking) and get download URL
            storage_key = await upload_passport_pdf(vehicle_id, pdf_bytes)
            download_url = None
            if storage_key:
                download_url = await generate_passport_download_url(storage_key, expiration_days=7)

            sent_ok = await send_passport_email(
                vehicle_id, subject, html_body,
                pdf_bytes=pdf_bytes,
                download_url=download_url,
            )
            if not sent_ok:
                log.warning(f"passport email send failed for {vehicle_id}")
                continue

            async with async_session() as db:
                await db.execute(text("""
                    INSERT INTO battery_soh_usage_log (user_id, user_vehicle_id, event_type, soh_pct, confidence, metadata_json)
                    SELECT user_id, :vid, 'pdf_sent', :soh, :conf, CAST(:meta AS JSONB)
                    FROM user_vehicles WHERE id = :vid
                """), {
                    "vid": vehicle_id,
                    "soh": None,
                    "conf": None,
                    "meta": f'{{"tier": "{tier}", "html_size_chars": {len(html_body)}, "pdf_size_bytes": {len(pdf_bytes)}, "storage_key": "{storage_key or "none"}", "download_url_provided": {bool(download_url)}}}',
                })
                await db.commit()
            pdfs_queued += 1
        except Exception as e:
            log.exception(f"passport generation failed for {vehicle_id}: {e}")

    return {"eligible": len(eligible_vehicles), "pdfs_sent": pdfs_queued}


# ─── Scheduler lifecycle ────────────────────────────────────────────────────

class BatteryScheduler:
    """Owns the AsyncIOScheduler instance + registers all battery jobs."""

    def __init__(self) -> None:
        self._scheduler: AsyncIOScheduler | None = None

    async def start(self) -> None:
        self._scheduler = AsyncIOScheduler(timezone="UTC")
        # Detect anomalies every 6 hours
        self._scheduler.add_job(
            job_detect_anomalies,
            CronTrigger(hour="*/6", minute=15),
            id="battery_anomaly_detect",
            name="Battery anomaly detection (every 6h)",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        # Monthly Passport on the 1st of each month at 09:00 UTC
        self._scheduler.add_job(
            job_monthly_passport,
            CronTrigger(day=1, hour=9, minute=0),
            id="battery_monthly_passport",
            name="Battery monthly Passport PDFs (1st @ 09:00 UTC)",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.start()
        log.info("battery_scheduler started: 2 jobs registered")

    async def stop(self) -> None:
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            log.info("battery_scheduler stopped")

    def schedule_vehicle_recompute(self, vehicle_id: str, delay_seconds: int = 0) -> None:
        """Schedule a one-off recompute for a vehicle (used by collector post-charge)."""
        if not self._scheduler:
            return
        self._scheduler.add_job(
            job_recompute_vehicle,
            "date",
            run_date=datetime.now(timezone.utc).timestamp() + delay_seconds,
            args=[vehicle_id],
            id=f"battery_recompute_{vehicle_id}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )


# Module-level singleton (mirrors DataCollector pattern)
scheduler = BatteryScheduler()


__all__ = ["scheduler", "job_recompute_vehicle", "job_detect_anomalies", "job_monthly_passport"]