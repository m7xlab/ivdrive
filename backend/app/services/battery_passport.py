"""Battery Passport — generates and emails the monthly SoH report.

V1: HTML email body (newsletter-style with inline SVG chart).
    PDF attachment generation is a follow-up sprint — the HTML is the primary
    artifact.

API:
  generate_passport_html(vehicle_id)  -> (subject, html_body)
  send_passport_email(vehicle_id)     -> bool
"""
from __future__ import annotations

import html
import logging
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session


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
        return f'<div style="color:{_BRAND["muted"]};font-size:13px;">No historical data yet.</div>'

    padding_l, padding_r, padding_t, padding_b = 40, 16, 16, 32
    chart_w = width - padding_l - padding_r
    chart_h = height - padding_t - padding_b

    # Y-axis: 80-105% range to keep changes visible
    y_min, y_max = 80.0, 105.0
    n = len(monthly)

    def x_for(i: int) -> float:
        if n == 1:
            return padding_l + chart_w / 2
        return padding_l + (i / (n - 1)) * chart_w

    def y_for(v: float) -> float:
        clamped = max(y_min, min(y_max, v))
        return padding_t + chart_h - ((clamped - y_min) / (y_max - y_min)) * chart_h

    points = []
    for i, m in enumerate(monthly):
        points.append(f'<circle cx="{x_for(i):.1f}" cy="{y_for(m["soh_pct"]):.1f}" r="4" fill="{_BRAND["grad_end"]}" />')

    path_d = " ".join(
        f"{'M' if i == 0 else 'L'} {x_for(i):.1f} {y_for(m['soh_pct']):.1f}"
        for i, m in enumerate(monthly)
    )

    # Y-axis labels
    y_ticks = [80, 85, 90, 95, 100, 105]
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
    badge_y = y_for(current_soh) - 28

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
    else:
        delta_12mo = 0.0

    # Range estimates
    wltp = float(meta["wltp_range_km"]) if meta["wltp_range_km"] else None
    range_now = int(wltp * soh / 100.0) if wltp else None
    range_new = int(wltp) if wltp else None
    range_loss_km = (range_new - range_now) if (range_new and range_now) else None

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
            <div style="font-size:22px;font-weight:700;color:{_BRAND["good"] if delta_12mo > -1 else _BRAND["warn"]};margin-top:4px;">{delta_12mo:+.2f}%</div>
          </div>
        </td>
        <td width="50%" style="padding:8px;">
          <div style="background:{_BRAND["bg"]};border:1px solid {_BRAND["border"]};border-radius:8px;padding:14px;">
            <div style="font-size:11px;color:{_BRAND["muted"]};text-transform:uppercase;letter-spacing:1px;">Real-world range</div>
            <div style="font-size:22px;font-weight:700;color:{_BRAND["text"]};margin-top:4px;">{range_now or "—"} km</div>
            {f'<div style="font-size:11px;color:{_BRAND["muted"]};margin-top:2px;">was {range_new} km new</div>' if range_new and range_loss_km else ''}
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

async def send_passport_email(vehicle_id: str, subject: str, html_body: str) -> bool:
    """Send the Passport HTML email to the vehicle owner. Returns True on success."""
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
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.ehlo()
            if settings.smtp_port != 25:
                server.starttls()
                server.ehlo()
            server.login(settings.smtp_user, settings.smtp_pass)
            server.sendmail(msg["From"], [to_email], msg.as_string())
        log.info(f"Passport email sent to {to_email} for {vehicle_name}")
        return True
    except Exception:
        log.exception(f"Failed to send Passport email to {to_email}")
        return False


# Module-level aliases (referenced by battery_scheduler)
async def generate_passport_pdf(vehicle_id: str) -> tuple[bytes, str]:
    """Backwards-compat alias — returns HTML for now, PDF in a future sprint."""
    subject, body = await generate_passport_html(vehicle_id)
    return body.encode("utf-8"), subject


__all__ = [
    "generate_passport_html",
    "generate_passport_pdf",  # alias
    "send_passport_email",
]