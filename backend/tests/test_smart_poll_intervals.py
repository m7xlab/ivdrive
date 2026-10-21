"""Smart-poll interval switching: parked ↔ active."""

from __future__ import annotations

from uuid import uuid4

from app.services.collector import DataCollector


class _FakeTrigger:
    def __init__(self, seconds: int) -> None:
        self.interval = __import__("datetime").timedelta(seconds=seconds)


class _FakeJob:
    def __init__(self, seconds: int) -> None:
        self.trigger = _FakeTrigger(seconds)


class _FakeScheduler:
    def __init__(self, seconds: int) -> None:
        self.seconds = seconds
        self.reschedules: list[int] = []

    def get_job(self, job_id: str):
        return _FakeJob(self.seconds)

    def reschedule_job(self, job_id: str, trigger: str = "interval", seconds: int | None = None):
        self.seconds = int(seconds)
        self.reschedules.append(self.seconds)


class _FakeVehicle:
    def __init__(self) -> None:
        self.active_interval_seconds = 180
        self.parked_interval_seconds = 900


def test_activity_switches_job_to_active_interval():
    c = DataCollector.__new__(DataCollector)
    vid = uuid4()
    c._poll_mode = {}
    c._sleep_ticks = {}
    c._stale_active_counters = {}
    c._scheduler = _FakeScheduler(900)
    v = _FakeVehicle()

    assert c._note_vehicle_activity(vid, v, active=True, reason="moving") is True
    assert c._scheduler.seconds == 180
    assert c._poll_mode[vid] == "active"


def test_inactive_uses_stabilization_then_parked_interval():
    c = DataCollector.__new__(DataCollector)
    vid = uuid4()
    c._poll_mode = {}
    c._sleep_ticks = {}
    c._stale_active_counters = {}
    c._scheduler = _FakeScheduler(180)
    v = _FakeVehicle()

    c._note_vehicle_activity(vid, v, active=True)
    # Three stabilization cycles at active rate
    assert c._note_vehicle_activity(vid, v, active=False) is True
    assert c._scheduler.seconds == 180
    assert c._note_vehicle_activity(vid, v, active=False) is True
    assert c._note_vehicle_activity(vid, v, active=False) is True
    # Then parked
    assert c._note_vehicle_activity(vid, v, active=False) is False
    assert c._scheduler.seconds == 900
    assert c._poll_mode[vid] == "sleep"


def test_reschedule_runs_even_when_current_unknown():
    c = DataCollector.__new__(DataCollector)
    vid = uuid4()
    c._poll_mode = {}
    c._sleep_ticks = {}
    c._stale_active_counters = {}
    c._scheduler = _FakeScheduler(900)
    c._get_job_interval_seconds = lambda job_id: None  # type: ignore
    v = _FakeVehicle()
    assert c._note_vehicle_activity(vid, v, active=True) is True
    assert 180 in c._scheduler.reschedules


def test_pause_for_reauth_stretches_job_interval():
    c = DataCollector.__new__(DataCollector)
    vid = uuid4()
    c._poll_mode = {}
    c._sleep_ticks = {}
    c._stale_active_counters = {}
    c._auth_paused = set()
    c._scheduler = _FakeScheduler(180)
    c.pause_for_reauth(vid, "bad password")
    assert vid in c._auth_paused
    assert c._scheduler.seconds == DataCollector.AUTH_FAILED_INTERVAL_SECONDS
    c.resume_after_reauth(vid, 900)
    assert vid not in c._auth_paused
    assert c._scheduler.seconds == 900
