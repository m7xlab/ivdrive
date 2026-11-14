"""Presentation layer: figures become metrics, a chart survives only as a real series.

The mixed-unit charts are verbatim from production answers.
"""

import json

from app.services import ai_presentation as p

PROD_MIXED_UNITS_CHART = (
    "Here's the quick picture.\n\n"
    "```json_chart\n"
    '{"title":"BlackMagic — Last 30 Days Overview","type":"bar","data":[{"name":"Distance","km":565},'
    '{"name":"Energy","kWh":159.4},{"name":"Charged","kWh":218.9},{"name":"Cost","EUR":79.86}],'
    '"categories":["km","kWh","EUR"]}\n'
    "```"
)
PROD_SEVEN_UNIT_CHART = {
    "title": "BlackMagic Performance Last Week (Oct 21-28, 2026)",
    "type": "bar",
    "data": [
        {"name": "Trips", "Count": 12},
        {"name": "Distance", "km": 73},
        {"name": "Energy Consumed", "kWh": 19.7},
        {"name": "Avg. Efficiency", "kWh/100km": 27.0},
        {"name": "Charging Sessions", "Count": 1},
        {"name": "Energy Charged", "kWh": 46.5},
        {"name": "Charging Cost", "€": 21.88},
    ],
    "categories": ["Count", "km", "kWh", "kWh/100km", "€"],
}
REAL_SERIES_CHART = {
    "title": "BlackMagic: Consumption vs Temperature",
    "type": "bar",
    "data": [
        {"name": "Below 0°C", "kWh/100km": 21.2},
        {"name": "0–5°C", "kWh/100km": 31.2},
        {"name": "5–10°C", "kWh/100km": 29.1},
    ],
    "categories": ["kWh/100km"],
}


def _blocks(answer: str) -> list[tuple[str, dict]]:
    return [(m.group(1), json.loads(m.group(2))) for m in p._BLOCK_RE.finditer(answer)]


def test_mixed_unit_chart_becomes_metrics_and_prose_is_untouched():
    out = p.normalize_presentation(PROD_MIXED_UNITS_CHART)
    assert out.startswith("Here's the quick picture.")
    kinds = _blocks(out)
    assert [k for k, _ in kinds] == ["json_metrics"]
    items = kinds[0][1]["items"]
    assert items[0] == {"label": "Distance", "value": "565", "unit": "km"}
    assert items[3] == {"label": "Cost", "value": "79.9", "unit": "EUR"}


def test_seven_unit_chart_becomes_metrics():
    answer = "Last week.\n```json_chart\n" + json.dumps(PROD_SEVEN_UNIT_CHART) + "\n```"
    kinds = _blocks(p.normalize_presentation(answer))
    assert [k for k, _ in kinds] == ["json_metrics"]
    labels = [i["label"] for i in kinds[0][1]["items"]]
    assert labels == ["Trips", "Distance", "Energy Consumed", "Avg. Efficiency", "Charging Sessions", "Energy Charged", "Charging Cost"]


def test_real_series_chart_is_kept():
    answer = "Cold shows up.\n```json_chart\n" + json.dumps(REAL_SERIES_CHART) + "\n```"
    kinds = _blocks(p.normalize_presentation(answer))
    assert [k for k, _ in kinds] == ["json_chart"]
    assert kinds[0][1]["data"][1]["kWh/100km"] == 31.2


def test_two_point_chart_is_not_a_series():
    chart = {"type": "bar", "data": [{"name": "SOH", "%": 95}, {"name": "Degradation", "%": 5}], "categories": ["%"]}
    kinds = _blocks(p.normalize_presentation("```json_chart\n" + json.dumps(chart) + "\n```"))
    assert [k for k, _ in kinds] == ["json_metrics"]
    assert kinds[0][1]["items"] == [{"label": "SOH", "value": "95", "unit": "%"}, {"label": "Degradation", "value": "5", "unit": "%"}]


def test_donut_with_one_non_zero_slice_becomes_metrics():
    chart = {"title": "Októberi töltések (kWh)", "type": "donut", "data": [{"name": "AC töltés", "value": 408.9}, {"name": "DC töltés", "value": 0}], "categories": ["value"]}
    kinds = _blocks(p.normalize_presentation("```json_chart\n" + json.dumps(chart) + "\n```"))
    assert [k for k, _ in kinds] == ["json_metrics"]
    assert kinds[0][1]["items"][0] == {"label": "AC töltés", "value": "408.9", "unit": ""}


def test_only_one_chart_survives():
    block = "```json_chart\n" + json.dumps(REAL_SERIES_CHART) + "\n```"
    kinds = _blocks(p.normalize_presentation("A.\n" + block + "\nB.\n" + block))
    assert [k for k, _ in kinds] == ["json_chart", "json_metrics"]


def test_unreadable_chart_is_dropped():
    out = p.normalize_presentation("Numbers.\n```json_chart\n{not json\n```\nDone.")
    assert out == "Numbers.\n\nDone."
    assert "```" not in out


def test_metrics_block_is_validated_and_capped():
    items = [{"label": f"m{i}", "value": i, "unit": "km"} for i in range(12)] + [{"label": "", "value": 1}, {"value": 2}, "junk"]
    out = p.normalize_presentation("```json_metrics\n" + json.dumps({"items": items}) + "\n```")
    kept = _blocks(out)[0][1]["items"]
    assert len(kept) == p.MAX_METRIC_ITEMS
    assert kept[0] == {"label": "m0", "value": "0", "unit": "km"}


def test_followups_are_cleaned_capped_and_deduplicated():
    qs = ["How does that compare with October?", "  how does that compare with october? ", "", "x" * 200, "What did charging cost?", "Is my data up to date?", "One more?"]
    out = p.normalize_presentation("Answer.\n```json_followups\n" + json.dumps({"questions": qs}) + "\n```")
    assert p.extract_followups(out) == ["How does that compare with October?", "What did charging cost?", "Is my data up to date?"]


def test_answer_without_blocks_is_returned_unchanged():
    text = "In May 2026, BlackMagic made 80 trips covering 733 km."
    assert p.normalize_presentation(text) == text
    assert p.extract_followups(text) == []


def test_system_prompt_asks_for_metrics_and_followups_not_a_chart_per_answer():
    from app.api.v1.chat import build_system_prompt

    prompt = build_system_prompt("DOMAIN GLOSSARY: x")
    assert "DOMAIN GLOSSARY: x" in prompt
    assert "json_metrics" in prompt and "json_followups" in prompt
    assert "Do not append a chart by default" in prompt
    assert "If you are presenting numeric data" not in prompt
