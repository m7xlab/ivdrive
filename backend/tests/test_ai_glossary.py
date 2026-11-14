"""Domain glossary: CONNECT_CABLE means *not* plugged in, and the assistant must say so.

The three "misreading" sentences below are verbatim from production answers.
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.services import ai_glossary as g


PROD_MISREADINGS = [
    "One nice detail: the cable is connected (CONNECT_CABLE), so it's plugged in and ready whenever you are.",
    'The car is currently showing a **"CONNECT_CABLE"** state, which means it\'s connected to a charger but might not be actively charging at this moment.',
    'It looks like the vehicle is currently in a "CONNECT_CABLE" state, suggesting it\'s ready to charge or has just been plugged in.',
]
CONTEXT_WITH_CONNECT_CABLE = "BlackMagic: Current battery state (as of 2026-11-14 13:12):\n- State of Charge (SOC): 54%\n- Charging state: CONNECT_CABLE"


def test_describe_connect_cable_says_not_plugged_in_and_never_echoes_the_token():
    text = g.describe_charging_state("CONNECT_CABLE")
    assert "NOT plugged in" in text
    assert "waiting for a charging cable" in text
    assert "CONNECT_CABLE" not in text


@pytest.mark.parametrize("state", ["READY_FOR_CHARGING", "CHARGING", "CHARGING_INTERRUPTED", "CONSERVING", "CHARGING_ERROR"])
def test_every_plugged_in_state_says_plugged_in(state):
    text = g.describe_charging_state(state)
    assert "plugged in" in text
    assert state not in text


def test_describe_charging_reports_power_only_while_charging():
    assert "7.2 kW" in g.describe_charging_state("CHARGING", 7.2)
    assert "kW" not in g.describe_charging_state("CONNECT_CABLE", 7.2)


def test_unknown_and_missing_states_do_not_guess():
    assert "unknown" in g.describe_charging_state(None)
    assert "not recognised" in g.describe_charging_state("SOMETHING_NEW")


def test_vehicle_state_and_data_health_phrases():
    assert g.describe_vehicle_state("PARKED") == "parked"
    assert g.describe_vehicle_state("IGNITION_ON") == "switched on, stationary"
    assert g.describe_data_health("down").startswith("down (")
    assert "24 hours" in g.describe_data_health("DOWN")


def test_glossary_block_defines_only_the_tokens_present_in_the_context():
    block = g.glossary_block(CONTEXT_WITH_CONNECT_CABLE)
    assert "CONNECT_CABLE: the car is NOT plugged in" in block
    assert "READY_FOR_CHARGING" not in block.split("Never print")[0]
    # Product facts are always there.
    assert "95.0 %" in block
    assert "Deleting a vehicle" in block


def test_glossary_block_matches_whole_tokens_only():
    # "DOWNLOAD" must not pull in the DOWN definition; "down" in prose must not either.
    block = g.glossary_block("Please DOWNLOAD the report; the car was down the road.")
    assert "data health DOWN" not in block


def test_scrub_replaces_leaked_tokens_in_every_wrapping():
    assert g.scrub_raw_terms("state: CONNECT_CABLE.") == "state: not plugged in (waiting for a cable)."
    assert g.scrub_raw_terms("a `CONNECT_CABLE` state") == "a not plugged in (waiting for a cable) state"
    assert g.scrub_raw_terms('showing a **"CONNECT_CABLE"** state') == "showing a not plugged in (waiting for a cable) state"
    assert g.scrub_raw_terms("the cable is connected (CONNECT_CABLE), so") == "the cable is connected, so"
    assert g.scrub_raw_terms("It is **PARKED** and **LIVE**.") == "It is parked and live."


def test_scrub_leaves_ordinary_words_alone():
    text = "The car is parked and live; download the data when it is down the road."
    assert g.scrub_raw_terms(text) == text


@pytest.mark.parametrize("answer", PROD_MISREADINGS)
def test_production_misreadings_are_detected(answer):
    assert g.find_term_misreadings(answer, CONTEXT_WITH_CONNECT_CABLE) == ["CONNECT_CABLE read as plugged in"]


def test_correct_reading_is_not_flagged():
    answer = "The car is not plugged in right now — it is waiting for a cable — with the battery at 54 %."
    assert g.find_term_misreadings(answer, CONTEXT_WITH_CONNECT_CABLE) == []


def test_plugged_in_is_fine_when_the_data_said_charging():
    answer = "It's plugged in and charging at 7 kW."
    assert g.find_term_misreadings(answer, "Charging state: CHARGING") == []


def test_down_described_as_live_is_flagged_but_recovery_is_not():
    ctx = "Data health: DOWN"
    assert g.find_term_misreadings("Your car is currently live and sending telemetry.", ctx) == ["DOWN described as live"]
    assert g.find_term_misreadings("It was down yesterday and is now live.", ctx) == []


# ── The tool that feeds the model must use the glossary wording ──────────────

class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeDb:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, sql, params=None):
        return _FakeResult(self.rows)


@pytest.mark.asyncio
async def test_current_battery_state_tool_never_hands_the_model_a_raw_token():
    from app.services.chat_tools import get_current_battery_state

    row = (datetime(2026, 11, 14, 13, 12, tzinfo=UTC), 54, 142000, "CONNECT_CABLE", 0.0, "BlackMagic")
    text = await get_current_battery_state(_FakeDb([row]), uuid.uuid4(), "BlackMagic")
    assert "CONNECT_CABLE" not in text
    assert "NOT plugged in" in text
    assert "54%" in text and "142.0 km" in text


@pytest.mark.asyncio
async def test_current_battery_state_tool_reports_power_while_charging():
    from app.services.chat_tools import get_current_battery_state

    row = (datetime(2026, 11, 14, 13, 12, tzinfo=UTC), 54, 142000, "CHARGING", 10.6, "BlackMagic")
    text = await get_current_battery_state(_FakeDb([row]), uuid.uuid4(), "BlackMagic")
    assert "actively charging" in text and "10.6 kW" in text
