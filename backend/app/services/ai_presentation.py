"""Presentation layer for AI answers: figures as metrics, charts only for real series.

The assistant used to be told to append a ```json_chart block to every numeric answer.
In production every one of those charts crammed unrelated figures with different units
(km, kWh, EUR, a count) into one bar chart, which reads worse than the sentence above it.

The system prompt now asks for a ```json_metrics block for a handful of figures and a
```json_chart block only for a genuine series. ``normalize_presentation`` enforces that on
whatever the model actually produced, so the client never receives a junk chart:

- a chart with mixed units, fewer than three points, or invalid JSON becomes metrics
  (or is dropped when it cannot be read at all);
- at most one chart survives per answer;
- ```json_followups blocks are validated and capped.
"""

from __future__ import annotations

import json
import re
from typing import Any

MIN_CHART_POINTS = 3
MAX_METRIC_ITEMS = 8
MAX_FOLLOWUPS = 3
MAX_FOLLOWUP_CHARS = 80

_BLOCK_RE = re.compile(r"```(json_chart|json_metrics|json_followups)\s*([\s\S]*?)```", re.IGNORECASE)


def _parse(payload: str) -> Any | None:
    try:
        return json.loads(payload)
    except (ValueError, TypeError):
        return None


def _number(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(",", "").strip())
        except ValueError:
            return None
    return None


def _fmt(v: float) -> str:
    if v == int(v) and abs(v) < 1e9:
        return f"{int(v):,}".replace(",", " ")
    return f"{v:,.1f}".replace(",", " ")


def chart_is_valid_series(chart: Any) -> bool:
    """True when a chart object is a real series: one unit, at least MIN_CHART_POINTS points."""
    if not isinstance(chart, dict):
        return False
    data = chart.get("data")
    cats = chart.get("categories")
    ctype = str(chart.get("type") or "").lower()
    if not isinstance(data, list) or not isinstance(cats, list) or not cats:
        return False
    if ctype not in ("bar", "line", "pie", "donut"):
        return False
    if len(data) < MIN_CHART_POINTS:
        return False
    x_key = chart.get("xDataKey") or "name"
    if ctype in ("pie", "donut"):
        if len(cats) != 1:
            return False
        key = cats[0]
        values = [_number(row.get(key)) for row in data if isinstance(row, dict)]
        return sum(1 for v in values if v) >= 2
    # Every point must carry every category (same unit across the series). A chart where
    # each row has its own key ({"km": 565}, {"kWh": 159}, {"EUR": 79}) is a metrics list.
    for row in data:
        if not isinstance(row, dict) or x_key not in row:
            return False
        for key in cats:
            if _number(row.get(key)) is None:
                return False
    return True


def chart_to_metrics(chart: dict) -> list[dict]:
    """Flatten a chart's rows into metric items: label from the x key, one item per value."""
    x_key = chart.get("xDataKey") or "name"
    cats = chart.get("categories") if isinstance(chart.get("categories"), list) else []
    items: list[dict] = []
    for row in chart.get("data") or []:
        if not isinstance(row, dict):
            continue
        label = str(row.get(x_key) or "").strip()
        value_keys = [k for k in cats if k in row] or [k for k in row if k != x_key]
        for key in value_keys:
            v = _number(row.get(key))
            if v is None:
                continue
            items.append({"label": label or str(key), "value": _fmt(v), "unit": "" if key == "value" else str(key)})
    return items[:MAX_METRIC_ITEMS]


def clean_metrics(payload: Any) -> list[dict]:
    """Validate a json_metrics payload into [{label, value, unit, note}] items."""
    if isinstance(payload, dict):
        payload = payload.get("items")
    if not isinstance(payload, list):
        return []
    items: list[dict] = []
    for raw in payload:
        if not isinstance(raw, dict):
            continue
        label = str(raw.get("label") or "").strip()
        value = raw.get("value")
        if label == "" or value is None or value == "":
            continue
        num = _number(value)
        item = {
            "label": label[:40],
            "value": _fmt(num) if num is not None else str(value)[:24],
            "unit": str(raw.get("unit") or "")[:16],
        }
        note = raw.get("note")
        if note:
            item["note"] = str(note)[:80]
        items.append(item)
    return items[:MAX_METRIC_ITEMS]


def clean_followups(payload: Any) -> list[str]:
    """Validate a json_followups payload into at most MAX_FOLLOWUPS short, distinct questions."""
    if isinstance(payload, dict):
        payload = payload.get("questions")
    if not isinstance(payload, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for q in payload:
        if not isinstance(q, str):
            continue
        q = " ".join(q.split()).strip()
        if not q or len(q) > MAX_FOLLOWUP_CHARS or q.lower() in seen:
            continue
        seen.add(q.lower())
        out.append(q)
        if len(out) == MAX_FOLLOWUPS:
            break
    return out


def _metrics_block(items: list[dict]) -> str:
    return "```json_metrics\n" + json.dumps({"items": items}, ensure_ascii=False) + "\n```"


def normalize_presentation(answer: str) -> str:
    """Rewrite the presentation blocks of an answer so the client only gets sound ones.

    Prose is left byte-for-byte; only fenced json_chart / json_metrics / json_followups
    blocks are replaced or removed. Returns the answer unchanged when it has no blocks.
    """
    if not answer or "```" not in answer:
        return answer

    chart_kept = False
    followups_seen = False

    def replace(m: re.Match[str]) -> str:
        nonlocal chart_kept, followups_seen
        kind = m.group(1).lower()
        payload = _parse(m.group(2))
        if kind == "json_chart":
            if payload is None:
                return ""
            if chart_is_valid_series(payload) and not chart_kept:
                chart_kept = True
                return "```json_chart\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
            items = chart_to_metrics(payload) if isinstance(payload, dict) else []
            return _metrics_block(items) if items else ""
        if kind == "json_metrics":
            items = clean_metrics(payload)
            return _metrics_block(items) if items else ""
        # json_followups
        if followups_seen:
            return ""
        qs = clean_followups(payload)
        if not qs:
            return ""
        followups_seen = True
        return "```json_followups\n" + json.dumps({"questions": qs}, ensure_ascii=False) + "\n```"

    out = _BLOCK_RE.sub(replace, answer)
    # Collapse the blank runs left by removed blocks.
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


def extract_followups(answer: str) -> list[str]:
    """The follow-up questions carried by an answer's json_followups block, if any."""
    for m in _BLOCK_RE.finditer(answer or ""):
        if m.group(1).lower() == "json_followups":
            return clean_followups(_parse(m.group(2)))
    return []
