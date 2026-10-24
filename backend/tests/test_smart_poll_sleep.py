"""Deep-sleep polling policy tests (no network / no DB)."""

from datetime import UTC, datetime
from uuid import uuid4

from app.services.analytics import is_actively_charging, is_plugged_in


def test_active_requires_real_charge_or_motion_signal():
    # Cable at 0 kW must not look "actively charging"
    assert is_actively_charging("CONNECT_CABLE", 0.0) is False
    assert is_plugged_in("CONNECT_CABLE") is True  # sessions still care
    assert is_actively_charging("CHARGING") is True
    assert is_actively_charging("CONNECT_CABLE", 7.2) is True


def test_sleep_wake_probe_default():
    from app.config import settings

    assert settings.sleep_wake_probe_every_n == 4


def test_actively_charging_detected_without_readiness():
    """Readiness ping can fail while the car is charging — sensors must still see it."""
    # Mirrors collector: charging probe runs even when conn status is None/unreachable.
    charge_state, charge_power = "CHARGING", 11.0
    assert is_actively_charging(charge_state, charge_power) is True
    # Home AC at 1–2 kW must also count as active (not a 0 kW cable).
    assert is_actively_charging("CONNECT_CABLE", 1.5) is True


def test_update_vehicle_intervals_preserves_active_job():
    """vehicle_updated must not force an Active job down to parked rate."""

    class FakeJob:
        def __init__(self, seconds):
            interval = type("I", (), {"total_seconds": lambda self=None, s=seconds: s})()
            self.trigger = type("T", (), {"interval": interval})()

    class FakeScheduler:
        def __init__(self):
            self.rescheduled = []
            self.jobs = {}

        def get_job(self, job_id):
            return self.jobs.get(job_id)

        def reschedule_job(self, job_id, trigger=None, seconds=None):
            self.rescheduled.append((job_id, seconds))

        def add_job(self, *a, **k):
            self.jobs[k.get("id", "x")] = FakeJob(k.get("seconds", 0))

        def remove_job(self, job_id):
            self.jobs.pop(job_id, None)

    from app.services.collector import DataCollector

    c = DataCollector()
    sched = FakeScheduler()
    c._scheduler = sched
    vid = uuid4()
    job_id = f"collect_{vid}"
    sched.jobs[job_id] = FakeJob(180)  # currently Active 3 min
    c._poll_mode[vid] = "active"

    c.update_vehicle_intervals(vid, active_interval=180, parked_interval=900)
    assert sched.rescheduled == [], "must not reschedule while Active matches DB active_interval"

    # Parked mode should follow parked_interval
    c._poll_mode[vid] = "sleep"
    c.update_vehicle_intervals(vid, active_interval=180, parked_interval=900)
    assert sched.rescheduled == [(job_id, 900)]


def test_update_vehicle_intervals_registers_missing_job():
    class FakeScheduler:
        def __init__(self):
            self.added = []

        def get_job(self, job_id):
            return None

        def add_job(self, *a, **k):
            self.added.append(k)

        def reschedule_job(self, *a, **k):
            pass

    from app.services.collector import DataCollector

    c = DataCollector()
    c._scheduler = FakeScheduler()
    vid = uuid4()
    c.update_vehicle_intervals(vid, active_interval=180, parked_interval=900)
    assert c._scheduler.added and c._scheduler.added[0]["seconds"] == 900
