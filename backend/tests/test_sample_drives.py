"""Sample Drive helpers — one container per vehicle, no trip-per-poll."""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

# collector imports analytics → external_apis → nordpool (not needed here)
sys.modules.setdefault("nordpool", MagicMock())
sys.modules.setdefault("nordpool.elspot", MagicMock())

from app.services.collector import (
    _append_drive_level,
    _append_drive_range,
    _get_or_create_sample_drive,
)


class _Result:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _Session:
    """Minimal async session stub for helper unit tests."""

    def __init__(self, existing=None):
        self.existing = existing
        self.added = []

    async def execute(self, _stmt):
        return _Result(self.existing)

    def add(self, obj):
        self.added.append(obj)
        if self.existing is None:
            self.existing = obj

    async def flush(self):
        return None


def test_sample_drive_is_reused_not_per_poll():
    async def run():
        session = _Session()
        drive = SimpleNamespace(id=1, user_vehicle_id="uv", drive_id="official")
        session.existing = drive
        d1 = await _get_or_create_sample_drive(session, "uv", drive_id="official", type="electric")
        d2 = await _get_or_create_sample_drive(session, "uv", drive_id="official", type="electric")
        assert d1 is drive and d2 is drive
        assert session.added == []

    asyncio.run(run())


def test_sample_drive_created_once_when_missing():
    async def run():
        session = _Session(existing=None)
        d1 = await _get_or_create_sample_drive(session, "uv", drive_id="official", type="electric")
        assert d1.drive_id == "official"
        assert len(session.added) == 1

    asyncio.run(run())


def test_append_drive_level_merges_unchanged_within_gap():
    async def run():
        t0 = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
        last = SimpleNamespace(level=50.0, first_date=t0, last_date=t0)
        session = _Session(existing=last)
        drive = SimpleNamespace(id=1)
        await _append_drive_level(session, drive, level=50.0, ts=t0 + timedelta(minutes=5), max_gap_s=900)
        assert session.added == []
        assert last.last_date == t0 + timedelta(minutes=5)

        session2 = _Session(existing=last)
        await _append_drive_level(session2, drive, level=49.0, ts=t0 + timedelta(minutes=20), max_gap_s=900)
        assert len(session2.added) == 1
        assert session2.added[0].level == 49.0

    asyncio.run(run())


def test_append_drive_range_merges_unchanged_within_gap():
    async def run():
        t0 = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
        last = SimpleNamespace(range_km=200.0, first_date=t0, last_date=t0)
        session = _Session(existing=last)
        drive = SimpleNamespace(id=1)
        await _append_drive_range(session, drive, range_km=200.0, ts=t0 + timedelta(minutes=5), max_gap_s=900)
        assert session.added == []

        session2 = _Session(existing=None)
        await _append_drive_range(session2, drive, range_km=180.0, ts=t0, max_gap_s=900)
        assert len(session2.added) == 1

    asyncio.run(run())
