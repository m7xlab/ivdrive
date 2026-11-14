"""The in-memory power-reading lookup must return exactly the rows the per-session query returned:
first_date < session_end and last_date > session_start (review of #221, N+1 removed)."""
from datetime import datetime, timedelta, timezone

from app.services.battery_health_v2 import _PowerReadings

T0 = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)


def _t(hours: float) -> datetime:
    return T0 + timedelta(hours=hours)


def _brute(rows, start, end):
    return sorted(r for r in rows if r[0] < end and r[1] > start)


def test_overlap_matches_the_query_including_the_boundaries():
    rows = [
        (_t(10), _t(12), 11.0),   # ends exactly at session start: excluded
        (_t(12), _t(13), 11.0),   # inside
        (_t(13.5), _t(16), 7.0),  # runs past the end: included
        (_t(16), _t(17), 7.0),    # starts exactly at session end: excluded
        (_t(1), _t(14), 3.0),     # a long early row spanning the session: included
        (_t(2), _t(3), 5.0),      # early and short: excluded
    ]
    r = _PowerReadings(rows)
    assert sorted(r.overlapping(_t(12), _t(16))) == _brute(rows, _t(12), _t(16))
    assert r.overlapping(_t(20), _t(21)) == []
    assert _PowerReadings([]).overlapping(_t(0), _t(1)) == []


def test_lookup_agrees_with_a_brute_force_scan_on_unsorted_overlapping_rows():
    import random
    rng = random.Random(218)
    rows = []
    for _ in range(400):
        a = rng.uniform(0, 500)
        rows.append((_t(a), _t(a + rng.uniform(0.1, 30)), rng.uniform(1, 11)))
    rng.shuffle(rows)
    r = _PowerReadings(rows)
    for _ in range(200):
        a = rng.uniform(0, 500)
        start, end = _t(a), _t(a + rng.uniform(0.5, 6))
        assert sorted(r.overlapping(start, end)) == _brute(rows, start, end)
