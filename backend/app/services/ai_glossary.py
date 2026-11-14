"""Domain glossary for the AI assistant.

Škoda's API hands back enum-like tokens whose plain English reading is wrong. The
canonical case is ``CONNECT_CABLE``: it is the state of a car that is *not* plugged in
(the Škoda app shows "Connect cable" as a prompt to the driver), yet an LLM reads it as
"the cable is connected". Three production answers made exactly that claim.

Three layers keep the assistant on the right meaning:

1. ``describe_*`` helpers turn a raw token into plain language *before* it reaches the
   model, so the tools never hand over a token at all.
2. ``glossary_block`` builds a short, authoritative glossary of every raw token that is
   still present in the context (SQL results, stored embedding chunks, history) for the
   system prompt.
3. ``scrub_raw_terms`` and ``find_term_misreadings`` run on the finished answer: the first
   replaces any token that leaked through with its plain phrase, the second reports an
   answer that contradicts the glossary so it can be logged and tested.
"""

from __future__ import annotations

import re

# ── Škoda charging state (charging_states.state) ──────────────────────────────
# Meaning, phrased so that "plugged in or not" is unambiguous.
CHARGING_STATE_MEANING: dict[str, str] = {
    "CONNECT_CABLE": (
        "NOT plugged in. The car is waiting for a charging cable to be connected "
        "(the Škoda app shows 'Connect cable'). It is not charging and no cable is attached."
    ),
    "READY_FOR_CHARGING": (
        "plugged in but not drawing power: the car is waiting for a charging timer or "
        "departure time, or it has already reached its target charge level."
    ),
    "CHARGING": "plugged in and actively charging.",
    "CHARGING_INTERRUPTED": (
        "plugged in, but charging stopped before the target was reached (the charger "
        "paused, lost power, or the car paused it)."
    ),
    "CONSERVING": (
        "plugged in with charging finished; the car is holding the battery at its "
        "target level."
    ),
    "CHARGING_ERROR": "plugged in, but the car reports a charging fault.",
}

# Short phrases for inline substitution (no leading "the car is").
CHARGING_STATE_PHRASE: dict[str, str] = {
    "CONNECT_CABLE": "not plugged in (waiting for a cable)",
    "READY_FOR_CHARGING": "plugged in, not charging yet",
    "CHARGING": "charging",
    "CHARGING_INTERRUPTED": "plugged in, charging interrupted",
    "CONSERVING": "plugged in, charge complete",
    "CHARGING_ERROR": "plugged in, charging fault",
}

# ── Vehicle state (vehicle_states.state) ──────────────────────────────────────
VEHICLE_STATE_MEANING: dict[str, str] = {
    "PARKED": "parked and switched off.",
    "DRIVING": "being driven.",
    "IGNITION_ON": "switched on but not moving (ignition on, stationary).",
    "OFFLINE": "not reachable by Škoda's servers right now (asleep or without signal).",
}

VEHICLE_STATE_PHRASE: dict[str, str] = {
    "PARKED": "parked",
    "DRIVING": "driving",
    "IGNITION_ON": "switched on, stationary",
    "OFFLINE": "unreachable (asleep or no signal)",
}

# ── iVDrive data-health roll-up (data_health.status) ──────────────────────────
DATA_HEALTH_MEANING: dict[str, str] = {
    "LIVE": "iVDrive received telemetry from the car within the last hour.",
    "STALE": "the last telemetry iVDrive received is between 1 and 24 hours old.",
    "DOWN": "iVDrive has received no telemetry for more than 24 hours.",
}

# ── Other vendor tokens and product facts that answers have got wrong ─────────
OTHER_TERMS: dict[str, str] = {
    "AC": "alternating-current charging (home wallbox or public AC post, typically up to 11 kW).",
    "DC": "direct-current rapid charging (public rapid charger, 50 kW and above).",
    "MAXIMUM": "max_charge_current_ac MAXIMUM: the car accepts the full AC current the charger offers.",
    "REDUCED": "max_charge_current_ac REDUCED: the driver limited AC charging current (gentler on a home socket).",
    "PERMANENT": "auto_unlock_plug_when_charged PERMANENT: the car releases the plug by itself once charging finishes.",
    "TRUNK_OPENED": "doors_locked TRUNK_OPENED: the car is locked except for the open boot.",
    "OPENED": "doors_locked OPENED: at least one door is open.",
}

PRODUCT_FACTS: list[str] = [
    "A battery state of health of exactly 95.0 % is a placeholder Škoda's API returns, not a measurement.",
    "A charging session's energy (energy_kwh) is estimated from the change in charge level and the "
    "battery's nominal capacity; it is not metered by the charger.",
    "Remaining range is the car's own estimate from recent consumption; cold weather makes it optimistic.",
    "Zero-kilometre 'phantom' trips are entries without distance (the car woke without moving); "
    "they inflate trip counts, not distance.",
    "Deleting a vehicle in iVDrive deletes its recorded data; there is no archive. The app warns before it does so.",
    "Re-authentication with Škoda is offered on the vehicle card only when Škoda rejected the stored login; "
    "there is no re-authenticate option in Settings and nothing to re-authenticate when the login still works.",
    "'Sync enabled' means iVDrive polls the car on the configured intervals; 'Incognito' means positions are not stored.",
    "iVDrive can only receive what Škoda's servers hand out; a car that is asleep or out of coverage yields "
    "nothing until it wakes, which a manual refresh can trigger.",
]

# Tokens the model must never echo, and the phrase that replaces each one.
_SCRUB: dict[str, str] = {
    **CHARGING_STATE_PHRASE,
    **VEHICLE_STATE_PHRASE,
    "LIVE": "live",
    "STALE": "stale",
    "DOWN": "down (no telemetry for more than 24 hours)",
    "TRUNK_OPENED": "locked, boot open",
}

_ALL_TERMS: dict[str, str] = {
    **{k: f"charging state {k}: the car is {v}" for k, v in CHARGING_STATE_MEANING.items()},
    **{k: f"vehicle state {k}: the car is {v}" for k, v in VEHICLE_STATE_MEANING.items()},
    **{k: f"data health {k}: {v}" for k, v in DATA_HEALTH_MEANING.items()},
    **{k: v for k, v in OTHER_TERMS.items()},
}


def _token_re(term: str) -> re.Pattern[str]:
    # Whole, case-sensitive token; underscores are part of the token.
    return re.compile(rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])")


def describe_charging_state(state: str | None, charge_power_kw: float | None = None) -> str:
    """Plain-language sentence for a charging state, for tool output. Never contains the token."""
    if not state:
        return "Charging state unknown (no recent charging data)."
    key = state.strip().upper()
    meaning = CHARGING_STATE_MEANING.get(key)
    if meaning is None:
        return "Charging state not recognised; treat the plug status as unknown."
    sentence = f"Plug and charging: the car is {meaning}"
    if key == "CHARGING" and charge_power_kw:
        sentence += f" Charging power right now: {charge_power_kw:.1f} kW."
    return sentence


def describe_vehicle_state(state: str | None) -> str:
    """Plain-language phrase for a vehicle state (PARKED → 'parked')."""
    if not state:
        return "unknown"
    return VEHICLE_STATE_PHRASE.get(state.strip().upper(), "unknown")


def describe_data_health(status: str | None) -> str:
    """'live (telemetry within the last hour)' style phrase for a data-health status."""
    if not status:
        return "unknown"
    key = status.strip().upper()
    meaning = DATA_HEALTH_MEANING.get(key)
    return f"{key.lower()} ({meaning[:-1]})" if meaning else key.lower()


def terms_in(text: str) -> list[str]:
    """The glossary terms that occur as whole tokens in ``text``, in glossary order."""
    if not text:
        return []
    return [t for t in _ALL_TERMS if _token_re(t).search(text)]


def glossary_block(context_text: str) -> str:
    """System-prompt section defining every vendor token present in the context.

    Product facts are always included; token definitions only for tokens that occur,
    so the prompt stays small. Empty context still yields the product facts.
    """
    lines = [
        "DOMAIN GLOSSARY (authoritative — these meanings override the plain-English reading of the words):",
    ]
    for term in terms_in(context_text):
        lines.append(f"- {_ALL_TERMS[term]}")
    lines.append(
        "- Never print these tokens; say what they mean in your own words. "
        "If the data says CONNECT_CABLE, the car is not plugged in — never call it connected, plugged in or charging."
    )
    for fact in PRODUCT_FACTS:
        lines.append(f"- {fact}")
    return "\n".join(lines)


_WRAP = r"[`\"'“”‘’*]*"


def scrub_raw_terms(answer: str) -> str:
    """Replace any vendor token that leaked into an answer with its plain phrase.

    Handles the token bare, in backticks, in quotes or bold, and in a parenthesis such
    as "(CONNECT_CABLE)". A parenthesised token is removed with its brackets.
    """
    if not answer:
        return answer
    out = answer
    for term, phrase in _SCRUB.items():
        # "(CONNECT_CABLE)" and " (`CONNECT_CABLE`)" → gone
        out = re.sub(rf"\s*\(\s*{_WRAP}{re.escape(term)}{_WRAP}\s*\)", "", out)
        # `CONNECT_CABLE` / "CONNECT_CABLE" / **CONNECT_CABLE** / bare
        out = re.sub(
            rf"{_WRAP}(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_]){_WRAP}",
            phrase,
            out,
        )
    return out


# (token present in context, pattern an answer must not contain, pattern that excuses it, label)
_MISREADING_RULES: list[tuple[str, re.Pattern[str], re.Pattern[str] | None, str]] = [
    (
        "CONNECT_CABLE",
        re.compile(
            r"(cable is connected|cable connected|is plugged in|it's plugged in|been plugged in|plugged in and ready|"
            r"connected to (a|the) charger|currently charging|is charging|ready to charge once)",
            re.IGNORECASE,
        ),
        re.compile(r"(not plugged in|no cable|isn't plugged in|is not connected|unplugged|waiting for a cable)", re.IGNORECASE),
        "CONNECT_CABLE read as plugged in",
    ),
    (
        "DOWN",
        re.compile(r"(is (currently )?live|sending telemetry|telemetry (is )?up to date)", re.IGNORECASE),
        re.compile(r"(was down|had been down|no longer down|is now live|now (showing|shows) as live)", re.IGNORECASE),
        "DOWN described as live",
    ),
]


def find_term_misreadings(answer: str, context_text: str) -> list[str]:
    """Labels of glossary contradictions in ``answer`` given the tokens in ``context_text``.

    Only tokens that are actually in the context count: an answer that says "plugged in"
    when the data said CHARGING is right, not a misreading.
    """
    if not answer or not context_text:
        return []
    present = set(terms_in(context_text))
    found: list[str] = []
    for term, bad, excuse, label in _MISREADING_RULES:
        if term not in present:
            continue
        if bad.search(answer) and not (excuse and excuse.search(answer)):
            found.append(label)
    return found
