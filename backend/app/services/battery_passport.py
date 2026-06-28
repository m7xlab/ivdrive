"""Battery Passport — generates and emails the monthly SoH report.

Produces two artifacts:
  1. HTML body (newsletter-style with inline SVG chart) — for inline email rendering
  2. Real PDF (fpdf2 + Pillow chart) — downloadable, printable, archivable

PDF delivery uses the existing async StorageProvider (S3 by default, GCS
available). The email contains a download link (7-day presigned URL) and
the PDF is attached inline.

API:
  generate_passport_html(vehicle_id)        -> (subject, html_body)
  generate_passport_pdf(vehicle_id)         -> bytes          (PDF binary)
  upload_passport_pdf(vehicle_id, pdf_bytes) -> str            (storage key)
  generate_passport_download_url(key, days) -> str            (presigned URL)
  send_passport_email(vehicle_id, subject, html, pdf_bytes=None) -> bool
"""
from __future__ import annotations

import html
import io
import logging
import os
import smtplib
import uuid
from datetime import datetime, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.services.storage import StorageProvider


log = logging.getLogger("app.battery_passport")


# ─── HTML builder ──────────────────────────────────────────────────────────

_BRAND = {
    "grad_start": "#00e676",
    "grad_end": "#00bcd4",
    "bg": "#0a0a0f",
    "card": "#141419",
    "border": "#1e1e2a",
    "text": "#e0f7fa",
    "muted": "#888",
    "good": "#10b981",
    "warn": "#f59e0b",
    "bad": "#ef4444",
}


def _svg_chart(monthly: list[dict[str, Any]], current_soh: float, width: int = 560, height: int = 220) -> str:
    """Build an inline SVG line chart of monthly SoH trend."""
    if not monthly:
        return f'''<div style="height:{height - 40}px;display:flex;align-items:center;justify-content:center;color:{_BRAND["muted"]};font-size:13px;font-style:italic;">
            No historical data yet. Check back next month for trends.
        </div>'''

    if len(monthly) == 1:
        # Single data point — can't draw a line, just show the current value
        m = monthly[0]
        return f'''<div style="height:{height - 40}px;display:flex;flex-direction:column;align-items:center;justify-content:center;color:{_BRAND["muted"]};font-size:13px;">
            <div style="font-size:32px;font-weight:700;background:linear-gradient(135deg,{_BRAND["grad_start"]},{_BRAND["grad_end"]});-webkit-background-clip:text;-webkit-text-fill-color:transparent;">{current_soh:.1f}%</div>
            <div style="margin-top:4px;">First measurement: {html.escape(m["month"])}</div>
            <div style="margin-top:12px;font-style:italic;">Trends will appear after 2+ months of data.</div>
        </div>'''

    padding_l, padding_r, padding_t, padding_b = 40, 16, 16, 32
    chart_w = width - padding_l - padding_r
    chart_h = height - padding_t - padding_b

    # Y-axis: dynamic floor (80% default) so degraded batteries don't get clamped,
    # padded 5% below the worst data point for visual headroom. Y-max stays 105%.
    data_floor = 80.0
    if monthly:
        data_floor = min(m["soh_pct"] for m in monthly) - 5.0
    y_min = min(80.0, data_floor)
    y_max = 105.0
    n = len(monthly)

    def x_for(i: int) -> float:
        if n == 1:
            return padding_l + chart_w / 2
        return padding_l + (i / (n - 1)) * chart_w

    def y_for(v: float) -> float:
        clamped = max(y_min, min(y_max, v))
        return padding_t + chart_h - ((clamped - y_min) / (y_max - y_min)) * chart_h

    points = "".join(
        f'<circle cx="{x_for(i):.1f}" cy="{y_for(m["soh_pct"]):.1f}" r="4" fill="{_BRAND["grad_end"]}" />'
        for i, m in enumerate(monthly)
    )

    path_d = " ".join(
        f"{'M' if i == 0 else 'L'} {x_for(i):.1f} {y_for(m['soh_pct']):.1f}"
        for i, m in enumerate(monthly)
    )

    # Y-axis labels — ticks follow y_min so degraded batteries get a useful chart
    y_ticks = list(range(int(y_min // 5) * 5, int(y_max) + 1, 5))
    y_labels = "".join(
        f'<text x="{padding_l - 8}" y="{y_for(t) + 4:.1f}" text-anchor="end" font-size="11" fill="{_BRAND["muted"]}">{t}%</text>'
        for t in y_ticks
    )

    # X-axis labels (first, middle, last)
    if n >= 3:
        x_label_idxs = [0, n // 2, n - 1]
    elif n == 2:
        x_label_idxs = [0, 1]
    else:
        x_label_idxs = [0]
    x_labels = "".join(
        f'<text x="{x_for(i):.1f}" y="{height - 8}" text-anchor="middle" font-size="11" fill="{_BRAND["muted"]}">{html.escape(monthly[i]["month"])}</text>'
        for i in x_label_idxs
    )

    # Current value badge
    badge_x = x_for(n - 1) - 60
    badge_y = max(0, y_for(current_soh) - 28)

    return f'''
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" style="display:block;">
      <rect x="0" y="0" width="{width}" height="{height}" fill="transparent" />
      <line x1="{padding_l}" y1="{padding_t}" x2="{padding_l}" y2="{padding_t + chart_h}" stroke="{_BRAND["border"]}" />
      <line x1="{padding_l}" y1="{padding_t + chart_h}" x2="{padding_l + chart_w}" y2="{padding_t + chart_h}" stroke="{_BRAND["border"]}" />
      {y_labels}
      {x_labels}
      <path d="{path_d}" fill="none" stroke="{_BRAND["grad_end"]}" stroke-width="2.5" />
      {points}
      <g transform="translate({badge_x:.1f}, {badge_y:.1f})">
        <rect x="0" y="0" width="56" height="22" rx="11" fill="{_BRAND["grad_end"]}" opacity="0.15" />
        <text x="28" y="15" text-anchor="middle" font-size="12" font-weight="600" fill="{_BRAND["grad_end"]}">{current_soh:.1f}%</text>
      </g>
    </svg>
    '''


def _bar(percent: float, label: str, score: float | None = None) -> str:
    """A progress bar component."""
    color = _BRAND["good"] if percent >= 7 else _BRAND["warn"] if percent >= 4 else _BRAND["bad"]
    score_text = f"{score:.1f}/10" if score is not None else ""
    return f'''
    <div style="margin:12px 0;">
      <div style="display:flex;justify-content:space-between;font-size:13px;color:{_BRAND["text"]};margin-bottom:4px;">
        <span>{html.escape(label)}</span>
        <span style="color:{_BRAND["muted"]};">{score_text}</span>
      </div>
      <div style="height:8px;background:{_BRAND["border"]};border-radius:4px;overflow:hidden;">
        <div style="width:{percent * 10:.0f}%;height:100%;background:{color};"></div>
      </div>
    </div>
    '''


async def generate_passport_html(vehicle_id: str) -> tuple[str, str]:
    """Returns (subject, html_body) for the monthly Passport.

    Pulls the latest aggregate estimate + 12-month trend from
    battery_soh_estimates, then composes a branded newsletter-style HTML doc.
    """
    async with async_session() as db:
        # Vehicle + user details
        meta = (await db.execute(text("""
            SELECT
              uv.id::text AS vehicle_id,
              uv.display_name AS vehicle_name,
              uv.manufacturer,
              uv.model,
              uv.model_year,
              uv.battery_capacity_kwh,
              uv.wltp_range_km,
              u.id::text AS user_id,
              u.email,
              u.display_name AS user_name
            FROM user_vehicles uv
            JOIN users u ON u.id = uv.user_id
            WHERE uv.id = :vid
        """), {"vid": vehicle_id})).mappings().first()

        if not meta:
            raise ValueError(f"vehicle {vehicle_id} not found")

        # Latest aggregate
        latest = (await db.execute(text("""
            SELECT soh_pct, estimated_kwh, confidence, estimated_at, sample_count
            FROM battery_soh_estimates
            WHERE user_vehicle_id = :vid AND method = 'aggregate'
            ORDER BY estimated_at DESC LIMIT 1
        """), {"vid": vehicle_id})).mappings().first()

        # 12-month trend
        trend_rows = (await db.execute(text("""
            SELECT
              TO_CHAR(DATE_TRUNC('month', estimated_at), 'YYYY-MM') AS month,
              ROUND(AVG(soh_pct)::numeric, 2) AS soh_pct,
              COUNT(*)::int AS sample_count
            FROM battery_soh_estimates
            WHERE user_vehicle_id = :vid
              AND method = 'aggregate'
              AND estimated_at >= NOW() - INTERVAL '12 months'
            GROUP BY 1
            ORDER BY 1
        """), {"vid": vehicle_id})).fetchall()
        trend = [
            {"month": r.month, "soh_pct": float(r.soh_pct), "sample_count": r.sample_count}
            for r in trend_rows
        ]

        # Charging habit (DC vs AC split over last 30 days)
        habit = (await db.execute(text("""
            SELECT
              charging_type,
              COUNT(*)::int AS n,
              SUM(energy_kwh)::numeric(10,2) AS total_kwh
            FROM charging_sessions
            WHERE user_vehicle_id = :vid
              AND session_start >= NOW() - INTERVAL '30 days'
              AND charging_type IS NOT NULL
            GROUP BY charging_type
        """), {"vid": vehicle_id})).fetchall()
        habit_map = {r.charging_type: {"n": r.n, "total_kwh": float(r.total_kwh or 0)} for r in habit}
        dc_count = habit_map.get("DC", {}).get("n", 0)
        ac_count = habit_map.get("AC", {}).get("n", 0)
        dc_total_kwh = habit_map.get("DC", {}).get("total_kwh", 0.0)
        total_sessions = dc_count + ac_count
        dc_pct = (dc_count / total_sessions * 100) if total_sessions else 0

        # Odometer for warranty check
        odo = (await db.execute(text("""
            SELECT mileage_in_km FROM odometer_readings
            WHERE user_vehicle_id = :vid
            ORDER BY captured_at DESC LIMIT 1
        """), {"vid": vehicle_id})).fetchone()
        odo_km = float(odo.mileage_in_km) if odo and odo.mileage_in_km else None

        # Open alerts
        alerts = (await db.execute(text("""
            SELECT alert_type, severity, message
            FROM battery_soh_alerts
            WHERE user_vehicle_id = :vid AND acknowledged_at IS NULL
            ORDER BY detected_at DESC
        """), {"vid": vehicle_id})).fetchall()

    if not latest:
        return (
            f"Battery report — {meta['vehicle_name']}",
            f"<p>No battery health data available yet for {html.escape(meta['vehicle_name'])}.</p>",
        )

    soh = float(latest.soh_pct)
    est_kwh = float(latest.estimated_kwh) if latest.estimated_kwh else meta["battery_capacity_kwh"] * soh / 100.0
    factory_kwh = float(meta["battery_capacity_kwh"]) if meta["battery_capacity_kwh"] else est_kwh / (soh / 100.0)
    confidence = latest.confidence or "low"

    # 12-month delta
    if len(trend) >= 2:
        delta_12mo = trend[-1]["soh_pct"] - trend[0]["soh_pct"]
        delta_12mo_label = f"{delta_12mo:+.2f}%"
    else:
        delta_12mo = 0.0
        delta_12mo_label = "—"

    # Range estimates
    wltp = float(meta["wltp_range_km"]) if meta["wltp_range_km"] else None
    range_new = int(wltp) if wltp else None
    range_now = int(wltp * soh / 100.0) if wltp else None
    if range_now is not None and range_new is not None:
        range_diff_km = range_now - range_new  # negative = lost range
    else:
        range_diff_km = None

    # Charging habit score (lower DC% = better, penalize heavy DC)
    if total_sessions == 0:
        habit_score = 5.0
        habit_tip = "No charging data in the last 30 days."
        dc_pct = 0
    elif dc_pct < 25:
        habit_score = 9.5
        habit_tip = "Excellent — you mostly AC charge. Battery health stays optimal."
    elif dc_pct < 50:
        habit_score = 7.5
        habit_tip = "Healthy mix. A bit more AC would extend battery life further."
    elif dc_pct < 75:
        habit_score = 5.0
        habit_tip = "Heavy DC fast charging accelerates degradation. Try to AC charge overnight when possible."
    else:
        habit_score = 3.0
        habit_tip = "⚠️ Predominantly DC fast charging. Consider AC slow charging for daily use to protect long-term capacity."

    # Warranty status
    warranty_limit_km = 160000
    warranty_limit_years = 8
    model_year = int(meta["model_year"]) if meta["model_year"] else None
    years_old = (datetime.now().year - model_year) if model_year else 0
    warranty_ok = (
        odo_km is not None and odo_km < warranty_limit_km
        and years_old < warranty_limit_years
    )

    month_label = datetime.now(timezone.utc).strftime("%B %Y")

    chart_svg = _svg_chart(trend, soh)

    # Build alert section (if any)
    alert_html = ""
    if alerts:
        items = "".join(
            f'<li style="margin:6px 0;color:{_BRAND["warn"]};font-size:13px;">'
            f'<strong>[{a.severity.upper()}]</strong> {html.escape(a.message or a.alert_type)}'
            f'</li>'
            for a in alerts
        )
        alert_html = f'''
        <tr><td style="padding:16px 32px;">
          <div style="background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.3);border-radius:8px;padding:16px;">
            <div style="font-size:13px;font-weight:600;color:{_BRAND["warn"]};margin-bottom:8px;">⚠️ Active alerts</div>
            <ul style="margin:0;padding-left:20px;">{items}</ul>
          </div>
        </td></tr>
        '''

    subject = f"🔋 Battery Health Report — {meta['vehicle_name']} ({month_label})"

    body = f'''<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:{_BRAND["bg"]};font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:{_BRAND["bg"]};">
<tr><td align="center" style="padding:40px 20px;">
<table role="presentation" width="560" cellspacing="0" cellpadding="0" style="background:{_BRAND["card"]};border-radius:16px;border:1px solid {_BRAND["border"]};overflow:hidden;">

  <!-- Header -->
  <tr><td style="padding:32px 32px 16px;text-align:center;">
    <h1 style="margin:0;font-size:24px;font-weight:700;letter-spacing:-0.5px;">
      <span style="background:linear-gradient(135deg,{_BRAND["grad_start"]},{_BRAND["grad_end"]});-webkit-background-clip:text;-webkit-text-fill-color:transparent;">iV</span><span style="color:{_BRAND["text"]};">Drive</span>
    </h1>
    <p style="margin:6px 0 0;font-size:12px;color:{_BRAND["muted"]};text-transform:uppercase;letter-spacing:2px;font-weight:600;">Battery Health Report</p>
    <p style="margin:12px 0 0;font-size:14px;color:{_BRAND["muted"]};">{month_label} · {html.escape(meta["vehicle_name"])}</p>
  </td></tr>

  <tr><td style="padding:0 32px;"><div style="height:1px;background:linear-gradient(90deg,transparent,{_BRAND["border"]},transparent);"></div></td></tr>

  <!-- Hero metric -->
  <tr><td style="padding:24px 32px 8px;text-align:center;">
    <div style="font-size:64px;font-weight:700;line-height:1;background:linear-gradient(135deg,{_BRAND["grad_start"]},{_BRAND["grad_end"]});-webkit-background-clip:text;-webkit-text-fill-color:transparent;">{soh:.1f}%</div>
    <div style="font-size:13px;color:{_BRAND["muted"]};margin-top:6px;text-transform:uppercase;letter-spacing:1px;">State of Health</div>
    <div style="font-size:12px;color:{_BRAND["muted"]};margin-top:4px;">Confidence: {confidence} · Estimated capacity: {est_kwh:.1f} kWh (factory {factory_kwh:.1f} kWh)</div>
  </td></tr>

  <!-- Chart -->
  <tr><td style="padding:16px 32px;">{chart_svg}</td></tr>

  <!-- Stats grid -->
  <tr><td style="padding:8px 32px 16px;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
      <tr>
        <td width="50%" style="padding:8px;">
          <div style="background:{_BRAND["bg"]};border:1px solid {_BRAND["border"]};border-radius:8px;padding:14px;">
            <div style="font-size:11px;color:{_BRAND["muted"]};text-transform:uppercase;letter-spacing:1px;">12-month change</div>
            <div style="font-size:22px;font-weight:700;color:{_BRAND["good"] if delta_12mo > -1 else _BRAND["warn"]};margin-top:4px;">{delta_12mo_label}</div>
          </div>
        </td>
        <td width="50%" style="padding:8px;">
          <div style="background:{_BRAND["bg"]};border:1px solid {_BRAND["border"]};border-radius:8px;padding:14px;">
            <div style="font-size:11px;color:{_BRAND["muted"]};text-transform:uppercase;letter-spacing:1px;">Real-world range</div>
            <div style="font-size:22px;font-weight:700;color:{_BRAND["text"]};margin-top:4px;">{range_now or "—"} km</div>
            {f'<div style="font-size:11px;color:{_BRAND["muted"]};margin-top:2px;">was {range_new} km when new</div>' if range_new and range_diff_km is not None else ''}
          </div>
        </td>
      </tr>
    </table>
  </td></tr>

  <!-- Charging habit -->
  <tr><td style="padding:0 32px 16px;">
    <div style="font-size:14px;font-weight:600;color:{_BRAND["text"]};margin-bottom:8px;">Charging habit</div>
    {_bar(habit_score, "Habit score", habit_score)}
    <div style="font-size:13px;color:{_BRAND["muted"]};margin-top:8px;">
      Last 30 days: {dc_count} DC + {ac_count} AC sessions ({dc_pct:.0f}% DC). {html.escape(habit_tip)}
    </div>
  </td></tr>

  <!-- Warranty -->
  <tr><td style="padding:0 32px 16px;">
    <div style="background:{_BRAND["bg"]};border:1px solid {'rgba(16,185,129,0.4)' if warranty_ok else 'rgba(239,68,68,0.4)'};border-radius:8px;padding:14px;">
      <div style="font-size:11px;color:{_BRAND["muted"]};text-transform:uppercase;letter-spacing:1px;">Warranty status</div>
      <div style="font-size:16px;font-weight:600;color:{_BRAND["good"] if warranty_ok else _BRAND["bad"]};margin-top:4px;">
        {'✅ Within 8-year / 160,000 km' if warranty_ok else '⚠️ Outside warranty window'}
      </div>
      {f'<div style="font-size:12px;color:{_BRAND["muted"]};margin-top:4px;">Odometer: {odo_km:,.0f} km · Vehicle age: {years_old} years</div>' if odo_km else ''}
    </div>
  </td></tr>

  {alert_html}

  <!-- Footer -->
  <tr><td style="padding:24px 32px;text-align:center;border-top:1px solid {_BRAND["border"]};">
    <p style="margin:0;font-size:11px;color:{_BRAND["muted"]};">
      Generated by iVDrive Team ® · View full history at ivdrive.eu
    </p>
    <p style="margin:6px 0 0;font-size:10px;color:{_BRAND["muted"]};opacity:0.7;">
      Based on {latest.sample_count} telemetry samples from your vehicle.
    </p>
  </td></tr>

</table>
</td></tr>
</table>
</body></html>'''

    return subject, body


# ─── Email send ────────────────────────────────────────────────────────────

async def send_passport_email_legacy(vehicle_id: str, subject: str, html_body: str) -> bool:
    """Send the Passport HTML email to the vehicle owner. Returns True on success.

    Deprecated — use the version below that supports PDF attachment + download URL.
    Kept temporarily for backward compat with tests that haven't been updated.
    """
    async with async_session() as db:
        row = (await db.execute(text("""
            SELECT u.email, uv.display_name AS vehicle_name
            FROM user_vehicles uv
            JOIN users u ON u.id = uv.user_id
            WHERE uv.id = :vid
        """), {"vid": vehicle_id})).first()

    if not row:
        log.error(f"send_passport_email_legacy: vehicle {vehicle_id} not found")
        return False

    to_email = row[0]
    vehicle_name = row[1]

    if not all([settings.smtp_host, settings.smtp_user, settings.smtp_pass]):
        # Dev fallback — log to stdout instead of failing
        log.warning(
            f"[DEV MODE] Would send Passport to {to_email} for {vehicle_name}:\n"
            f"  Subject: {subject}\n"
            f"  HTML body: {len(html_body)} chars"
        )
        return True  # non-blocking

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    try:
        def _send_sync():
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
                server.ehlo()
                if settings.smtp_port != 25:
                    server.starttls()
                    server.ehlo()
                server.login(settings.smtp_user, settings.smtp_pass)
                server.sendmail(msg["From"], [to_email], msg.as_string())
        await asyncio.to_thread(_send_sync)
        log.info(f"Passport email sent to {to_email} for {vehicle_name}")
        return True
    except Exception:
        log.exception(f"Failed to send Passport email to {to_email}")
        return False


# ─── PDF generation (fpdf2 + Pillow chart) ─────────────────────────────────

import asyncio
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from PIL import Image, ImageDraw, ImageFont


def _chart_png(monthly: list[dict[str, Any]], width: int = 900, height: int = 280) -> bytes:
    """Render the SoH trend as a PNG via Pillow. Returns PNG bytes.

    Pure-Python (no matplotlib dependency). The result is embedded into
    the PDF as an image.
    """
    if not monthly:
        # Empty-state placeholder
        img = Image.new("RGB", (width, height), (10, 10, 15))
        draw = ImageDraw.Draw(img)
        draw.text((width // 2 - 100, height // 2 - 10), "No historical data yet", fill=(136, 136, 136))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    padding_l, padding_r, padding_t, padding_b = 60, 20, 20, 40
    chart_w = width - padding_l - padding_r
    chart_h = height - padding_t - padding_b
    data_floor = 80.0
    if monthly:
        data_floor = min(m["soh_pct"] for m in monthly) - 5.0
    y_min = min(80.0, data_floor)
    y_max = 105.0

    img = Image.new("RGB", (width, height), (10, 10, 15))
    draw = ImageDraw.Draw(img)

    # Y-axis grid + labels — ticks follow y_min so degraded batteries get a useful chart
    ticks = list(range(int(y_min // 5) * 5, int(y_max) + 1, 5))
    for tick in ticks:
        y = padding_t + chart_h - ((tick - y_min) / (y_max - y_min)) * chart_h
        draw.line([(padding_l, y), (padding_l + chart_w, y)], fill=(30, 30, 42), width=1)
        draw.text((padding_l - 40, y - 6), f"{tick}%", fill=(136, 136, 136))

    n = len(monthly)
    if n == 1:
        m = monthly[0]
        x = padding_l + chart_w // 2
        y = padding_t + chart_h - ((m["soh_pct"] - y_min) / (y_max - y_min)) * chart_h
        draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=(0, 188, 212))
        draw.text((width // 2 - 60, height - 30), f"First measurement: {m['month']}", fill=(136, 136, 136))
    else:
        pts = []
        for i, m in enumerate(monthly):
            x = padding_l + (i / (n - 1)) * chart_w
            y = padding_t + chart_h - ((m["soh_pct"] - y_min) / (y_max - y_min)) * chart_h
            pts.append((x, y))
        # Polyline approximation
        for i in range(len(pts) - 1):
            draw.line([pts[i], pts[i + 1]], fill=(0, 188, 212), width=3)
        for x, y in pts:
            draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=(0, 188, 212))
        # X-axis labels (first, mid, last)
        for i in (0, n // 2, n - 1):
            x = padding_l + (i / (n - 1)) * chart_w
            draw.text((x - 18, height - 28), monthly[i]["month"], fill=(136, 136, 136))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class _PassportPDF(FPDF):
    """A4 PDF with iVDrive branding. Header colors are RGB triplets."""
    BRAND_GREEN = (0, 230, 118)
    BRAND_CYAN = (0, 188, 212)
    BG = (10, 10, 15)
    CARD = (20, 20, 25)
    TEXT = (224, 247, 250)
    MUTED = (136, 136, 136)
    GOOD = (16, 185, 129)
    WARN = (245, 158, 11)
    BAD = (239, 68, 68)

    def header(self):
        self.set_fill_color(*self.BG)
        self.rect(0, 0, 210, 297, "F")
        self.set_y(12)

    def footer(self):
        self.set_y(-18)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*self.MUTED)
        self.cell(0, 6, "Generated by iVDrive Team (R)", align="C")

    def brand_title(self, subtitle: str = "", title: str = "iVDrive"):
        self.set_font("Helvetica", "B", 24)
        # Draw the brand as a single word — gradient via two-color cell would
        # need the deprecated `ln` kwarg in old fpdf2, simpler to do it as
        # one cell here (white) with a small green accent.
        self.set_text_color(*self.BRAND_GREEN)
        self.cell(0, 12, "iVDrive", align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if subtitle:
            self.set_font("Helvetica", "", 10)
            self.set_text_color(*self.MUTED)
            self.cell(0, 6, subtitle, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(4)

    def metric_card(self, label: str, value: str, color=None):
        self.set_fill_color(*self.CARD)
        self.set_draw_color(30, 30, 42)
        x, y = self.get_x(), self.get_y()
        self.set_xy(x + 2, y)
        self.cell(60, 22, "", fill=True, border=0, ln=0)
        self.set_xy(x + 6, y + 4)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*self.MUTED)
        self.cell(54, 4, label.upper(), ln=1)
        self.set_xy(x + 6, y + 10)
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(*(color or self.TEXT))
        self.cell(54, 10, value, ln=1)
        self.set_xy(x + 64, y)


async def generate_passport_pdf(vehicle_id: str) -> bytes:
    """Generate the Passport as a real PDF (A4). Returns bytes."""
    subject, html_body = await generate_passport_html(vehicle_id)

    # Parse the html_body to extract the headline metrics we already computed.
    # We do this by re-running the same data queries (simpler than parsing HTML).
    async with async_session() as db:
        meta = (await db.execute(text("""
            SELECT uv.id::text, uv.display_name, uv.model, uv.battery_capacity_kwh,
                   uv.wltp_range_km, uv.model_year, u.email, u.display_name AS user_name
            FROM user_vehicles uv JOIN users u ON u.id = uv.user_id
            WHERE uv.id = :vid
        """), {"vid": vehicle_id})).mappings().first()

        latest = (await db.execute(text("""
            SELECT soh_pct, estimated_kwh, confidence, estimated_at, sample_count
            FROM battery_soh_estimates
            WHERE user_vehicle_id = :vid AND method = 'aggregate'
            ORDER BY estimated_at DESC LIMIT 1
        """), {"vid": vehicle_id})).mappings().first()

        trend = (await db.execute(text("""
            SELECT TO_CHAR(DATE_TRUNC('month', estimated_at), 'YYYY-MM') AS month,
                   ROUND(AVG(soh_pct)::numeric, 2) AS soh_pct
            FROM battery_soh_estimates
            WHERE user_vehicle_id = :vid AND method = 'aggregate'
              AND estimated_at >= NOW() - INTERVAL '12 months'
            GROUP BY 1 ORDER BY 1
        """), {"vid": vehicle_id})).fetchall()

        odo = (await db.execute(text("""
            SELECT mileage_in_km FROM odometer_readings
            WHERE user_vehicle_id = :vid ORDER BY captured_at DESC LIMIT 1
        """), {"vid": vehicle_id})).first()

        habit = (await db.execute(text("""
            SELECT charging_type, COUNT(*)::int AS n
            FROM charging_sessions
            WHERE user_vehicle_id = :vid
              AND session_start >= NOW() - INTERVAL '30 days'
              AND charging_type IS NOT NULL
            GROUP BY charging_type
        """), {"vid": vehicle_id})).fetchall()

    if not meta or not latest:
        return _minimal_pdf("No battery health data available yet.")

    soh = float(latest.soh_pct)
    est_kwh = float(latest.estimated_kwh) if latest.estimated_kwh else 0.0
    factory_kwh = float(meta["battery_capacity_kwh"]) if meta["battery_capacity_kwh"] else 0.0
    confidence = latest.confidence or "low"
    wltp = float(meta["wltp_range_km"]) if meta["wltp_range_km"] else None
    range_now = int(wltp * soh / 100.0) if wltp else None
    range_new = int(wltp) if wltp else None
    odo_km = float(odo.mileage_in_km) if odo and odo.mileage_in_km else None

    habit_map = {r.charging_type: r.n for r in habit}
    dc_count = habit_map.get("DC", 0)
    ac_count = habit_map.get("AC", 0)
    total = dc_count + ac_count
    dc_pct = (dc_count / total * 100) if total else 0
    if total == 0:
        habit_score, habit_label, habit_tip = 5.0, "5.0/10", "No charging data in the last 30 days."
    elif dc_pct < 25:
        habit_score, habit_label, habit_tip = 9.5, "9.5/10", "Mostly AC charging. Battery stays optimal."
    elif dc_pct < 50:
        habit_score, habit_label, habit_tip = 7.5, "7.5/10", "Healthy mix. A bit more AC extends life."
    elif dc_pct < 75:
        habit_score, habit_label, habit_tip = 5.0, "5.0/10", "Heavy DC. AC overnight would help longevity."
    else:
        habit_score, habit_label, habit_tip = 3.0, "3.0/10", "Predominantly DC fast charging. Slow AC recommended."

    warranty_ok = (odo_km is not None and odo_km < 160000 and (datetime.now().year - int(meta["model_year"]) if meta["model_year"] else 0) < 8)

    # Render chart as PNG bytes (PIL)
    monthly_list = [{"month": r.month, "soh_pct": float(r.soh_pct)} for r in trend]
    chart_png = _chart_png(monthly_list)

    # Build PDF
    pdf = _PassportPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    pdf.brand_title(
        subtitle=f"Battery Health Report \u00b7 {datetime.now(timezone.utc).strftime('%B %Y')} \u00b7 {meta['display_name']}",
    )

    # Hero metric
    pdf.set_y(45)
    pdf.set_font("Helvetica", "B", 56)
    pdf.set_text_color(*_PassportPDF.BRAND_GREEN)
    pdf.cell(0, 22, f"{soh:.1f}%", align="C", ln=1)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(*_PassportPDF.MUTED)
    pdf.cell(0, 6, "STATE OF HEALTH", align="C", ln=1)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, f"Confidence: {confidence}  \u00b7  Estimated capacity: {est_kwh:.1f} kWh (factory {factory_kwh:.1f} kWh)", align="C", ln=1)
    pdf.ln(4)

    # Chart image
    chart_y = pdf.get_y()
    pdf.image(io.BytesIO(chart_png), x=15, y=chart_y, w=180)
    pdf.set_y(chart_y + 60)

    # Stats grid (two columns)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*_PassportPDF.MUTED)
    delta = (monthly_list[-1]["soh_pct"] - monthly_list[0]["soh_pct"]) if len(monthly_list) >= 2 else 0
    pdf.metric_card("12-month change", f"{delta:+.2f}%", _PassportPDF.GOOD if delta > -1 else _PassportPDF.WARN)
    pdf.metric_card("Real-world range", f"{range_now} km" if range_now else "\u2014",
                    _PassportPDF.TEXT)
    pdf.set_y(pdf.get_y() + 24)

    # Charging habit bar
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*_PassportPDF.TEXT)
    pdf.cell(0, 6, "Charging habit", ln=1)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*_PassportPDF.MUTED)
    pdf.cell(0, 5, f"Habit score: {habit_label}", ln=1)
    bar_y = pdf.get_y()
    bar_w = 180
    pdf.set_fill_color(30, 30, 42)
    pdf.rect(15, bar_y, bar_w, 4, "F")
    fill_w = bar_w * (habit_score / 10.0)
    pdf.set_fill_color(*(_PassportPDF.GOOD if habit_score >= 7 else _PassportPDF.WARN if habit_score >= 4 else _PassportPDF.BAD))
    pdf.rect(15, bar_y, fill_w, 4, "F")
    pdf.set_y(bar_y + 8)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, f"Last 30 days: {dc_count} DC + {ac_count} AC sessions ({dc_pct:.0f}% DC). {habit_tip}", ln=1)
    pdf.ln(4)

    # Warranty
    pdf.set_fill_color(*_PassportPDF.CARD)
    pdf.set_draw_color(30, 30, 42)
    pdf.set_xy(15, pdf.get_y())
    pdf.cell(180, 18, "", fill=True, border=0, ln=1)
    pdf.set_xy(20, pdf.get_y() - 14)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*_PassportPDF.MUTED)
    pdf.cell(50, 4, "WARRANTY STATUS", ln=1)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*(_PassportPDF.GOOD if warranty_ok else _PassportPDF.BAD))
    pdf.cell(50, 6, "Within 8-year / 160,000 km" if warranty_ok else "Outside warranty window", ln=1)
    if odo_km:
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*_PassportPDF.MUTED)
        pdf.cell(50, 4, f"Odometer: {odo_km:,.0f} km", ln=1)

    return bytes(pdf.output())


def _minimal_pdf(text: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "", 14)
    pdf.cell(0, 10, text, ln=1)
    return bytes(pdf.output())


# ─── Object storage integration (async, via StorageProvider) ──────────────

_STORAGE: StorageProvider | None = None


def _get_storage() -> StorageProvider | None:
    """Lazy-init the StorageProvider (S3/GCS). Returns None if neither is configured."""
    global _STORAGE
    if _STORAGE is not None:
        return _STORAGE
    use_gcs = bool(getattr(settings, "use_gcs_storage", False))
    try:
        _STORAGE = StorageProvider(use_gcs=use_gcs)
        return _STORAGE
    except Exception as e:
        log.warning(f"[storage] init failed: {e}")
        return None


async def upload_passport_pdf(vehicle_id: str, pdf_bytes: bytes) -> str | None:
    """Upload the PDF to S3/GCS. Returns the storage key (or None if no storage configured).

    Uses the dedicated BATTERY_PASSPORTS_BUCKET — same pattern as chat-sessions
    uses CONVERSATION_SESSIONS_BUCKET. Falls back to the default S3_BUCKET
    (data-extract) only if the env var is not set, which is the legacy path.
    """
    storage = _get_storage()
    if storage is None:
        return None
    ts = datetime.now(timezone.utc)
    key = f"battery-passports/{ts.strftime('%Y-%m')}/{vehicle_id}/{ts.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}.pdf"

    # Dedicated bucket mirrors chat-sessions pattern. If env var not set, fall
    # back to legacy S3_BUCKET so we don't silently mix PDFs into data-extract.
    bucket_name = os.environ.get("BATTERY_PASSPORTS_BUCKET") or os.environ.get("S3_BUCKET")
    if not os.environ.get("BATTERY_PASSPORTS_BUCKET"):
        log.warning(
            f"[storage] BATTERY_PASSPORTS_BUCKET not set — falling back to "
            f"{bucket_name} (should be a dedicated bucket, not data-extract)"
        )

    try:
        # upload_content expects str; PDFs are 8-bit-clean so latin-1 preserves bytes
        ok = await storage.upload_content(
            pdf_bytes.decode("latin-1"),
            key,
            bucket_name=bucket_name,
        )
        if ok:
            log.info(
                f"[storage] uploaded Passport PDF: s3://{bucket_name}/{key} "
                f"({len(pdf_bytes)} bytes)"
            )
            return key
        log.warning(f"[storage] upload returned False for s3://{bucket_name}/{key}")
        return None
    except Exception as e:
        log.exception(f"[storage] upload failed for s3://{bucket_name}/{key}: {e}")
        return None


async def generate_passport_download_url(key: str, expiration_days: int = 7) -> str | None:
    """Return a presigned download URL for a previously uploaded PDF."""
    storage = _get_storage()
    if storage is None:
        return None
    try:
        # boto3 generate_presigned_url is sync; wrap in asyncio.to_thread
        from datetime import timedelta
        url = await asyncio.to_thread(
            storage.generate_download_url,
            key,
            timedelta(days=expiration_days),
        )
        return url
    except Exception as e:
        log.exception(f"[storage] presign failed for {key}: {e}")
        return None


async def send_passport_email(
    vehicle_id: str,
    subject: str,
    html_body: str,
    pdf_bytes: bytes | None = None,
    download_url: str | None = None,
) -> bool:
    """Send the Passport HTML email. Optionally attach PDF and embed download URL."""
    async with async_session() as db:
        row = (await db.execute(text("""
            SELECT u.email, uv.display_name AS vehicle_name
            FROM user_vehicles uv
            JOIN users u ON u.id = uv.user_id
            WHERE uv.id = :vid
        """), {"vid": vehicle_id})).first()

    if not row:
        log.error(f"send_passport_email: vehicle {vehicle_id} not found")
        return False

    to_email = row[0]
    vehicle_name = row[1]

    if not all([settings.smtp_host, settings.smtp_user, settings.smtp_pass]):
        log.warning(
            f"[DEV MODE] Would send Passport to {to_email} for {vehicle_name}: "
            f"subject={subject!r}, html={len(html_body)} chars, "
            f"pdf={len(pdf_bytes) if pdf_bytes else 0} bytes, "
            f"download_url={download_url!r}"
        )
        return True

    # Optionally inject the download URL into the HTML body just above the footer
    body = html_body
    if download_url:
        download_block = (
            f'<tr><td style="padding:16px 32px;text-align:center;">'
            f'<a href="{download_url}" style="display:inline-block;padding:12px 24px;'
            f'background:linear-gradient(135deg,#00e676,#00bcd4);color:#0a0a0f;'
            f'text-decoration:none;border-radius:8px;font-weight:600;font-size:14px;">'
            f'Download PDF Passport</a>'
            f'<div style="margin-top:6px;font-size:11px;color:#888;">Link valid for 7 days</div>'
            f'</td></tr>'
        )
        body = body.replace(
            '<tr><td style="padding:24px 32px;text-align:center;border-top:1px solid #1e1e2a;">',
            download_block + '<tr><td style="padding:24px 32px;text-align:center;border-top:1px solid #1e1e2a;">',
        )

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to_email
    msg.attach(MIMEText(body, "html"))

    if pdf_bytes:
        attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
        attachment.add_header(
            "Content-Disposition", "attachment",
            filename=f"battery-passport-{vehicle_id[:8]}-{datetime.now(timezone.utc).strftime('%Y%m%d')}.pdf",
        )
        msg.attach(attachment)

    try:
        def _send_sync():
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
                server.ehlo()
                if settings.smtp_port != 25:
                    server.starttls()
                    server.ehlo()
                server.login(settings.smtp_user, settings.smtp_pass)
                server.sendmail(msg["From"], [to_email], msg.as_string())
        await asyncio.to_thread(_send_sync)
        log.info(
            f"Passport email sent to {to_email} for {vehicle_name} "
            f"(pdf={'attached' if pdf_bytes else 'no'}, download_link={'yes' if download_url else 'no'})"
        )
        return True
    except Exception:
        log.exception(f"Failed to send Passport email to {to_email}")
        return False


__all__ = [
    "generate_passport_html",
    "generate_passport_pdf",
    "upload_passport_pdf",
    "generate_passport_download_url",
    "send_passport_email",
]