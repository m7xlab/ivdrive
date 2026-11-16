"""Vehicle identification numbers as they may appear in a URL.

A VIN is 17 characters from [A-HJ-NPR-Z0-9] (no I, O, Q). Every Škoda endpoint takes the VIN as a
path segment, so a value that is not a VIN must never reach an f-string that builds a URL: a
string with a slash or dot segments would address a different resource on Škoda's host.
"""
from __future__ import annotations

import re

VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")


class InvalidVINError(ValueError):
    """The value is not a 17-character VIN."""


def normalize_vin(value: str) -> str:
    """Upper-case, trimmed VIN; raises InvalidVINError for anything that is not one."""
    vin = (value or "").strip().upper()
    if not VIN_RE.match(vin):
        raise InvalidVINError("A VIN is 17 letters and digits (no I, O or Q).")
    return vin


def vin_path(value: str) -> str:
    """The VIN as a URL path segment. Same check as normalize_vin; exists so the call reads as
    what it is at the URL-building site."""
    return normalize_vin(value)
