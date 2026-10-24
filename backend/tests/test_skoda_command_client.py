"""Facade-level tests for SkodaCommandClient spin forwarding."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.api.v1.commands import humanize_command_error
from app.services.skoda_commands import CommandError, CommandUnsupported
from app.services.skoda_commands_client import SkodaCommandClient

VIN = "TESTVIN0000000001"


@pytest.mark.asyncio
async def test_unlock_forwards_call_spin():
    client = SkodaCommandClient()
    client._run = AsyncMock()
    await client.unlock(VIN, spin="1234")
    client._run.assert_awaited_once_with(VIN, "unlock", spin="1234")


@pytest.mark.asyncio
async def test_unlock_call_spin_wins_over_constructor_spin():
    client = SkodaCommandClient(spin="9999")
    client._run = AsyncMock()
    await client.unlock(VIN, spin="1234")
    client._run.assert_awaited_once_with(VIN, "unlock", spin="1234")


@pytest.mark.asyncio
async def test_unlock_falls_back_to_constructor_spin():
    client = SkodaCommandClient(spin="9999")
    client._run = AsyncMock()
    await client.unlock(VIN)
    client._run.assert_awaited_once_with(VIN, "unlock", spin="9999")


@pytest.mark.asyncio
async def test_unlock_empty_spin_is_none():
    client = SkodaCommandClient()
    client._run = AsyncMock()
    await client.unlock(VIN, spin="")
    client._run.assert_awaited_once_with(VIN, "unlock", spin=None)


@pytest.mark.asyncio
async def test_unlock_whitespace_spin_is_none():
    client = SkodaCommandClient(spin="   ")
    client._run = AsyncMock()
    await client.unlock(VIN, spin="  ")
    client._run.assert_awaited_once_with(VIN, "unlock", spin=None)


@pytest.mark.asyncio
async def test_honk_flash_is_unsupported_not_lock():
    client = SkodaCommandClient(access_token="tok")
    with pytest.raises(CommandUnsupported) as exc:
        await client.honk_flash("TESTVIN0000000001")
    text = str(exc.value).lower()
    assert "not available" in text
    # must never imply it locked the car
    assert "locked" not in text and "lock request" not in text


def test_humanize_unsupported_keeps_human_text():
    msg = humanize_command_error(CommandUnsupported("Connect MyŠkoda Login for this action."))
    assert msg == "Connect MyŠkoda Login for this action."


def test_humanize_auth_style_error():
    msg = humanize_command_error(CommandError("BFF POST /x -> HTTP 401"))
    assert "expired" in msg.lower() or "reconnect" in msg.lower()
    assert "401" not in msg
    assert "BFF" not in msg


def test_humanize_token_rejected():
    msg = humanize_command_error(CommandError("token rejected"))
    assert "reconnect" in msg.lower() or "expired" in msg.lower()
    assert "rejected" not in msg.lower()


def test_humanize_timeout():
    msg = humanize_command_error(TimeoutError("timed out waiting"))
    assert msg == "Couldn’t reach the car. Try again in a moment."


def test_humanize_pin_error():
    msg = humanize_command_error(CommandError("spin rejected"))
    assert "pin" in msg.lower() or "s-pin" in msg.lower()


def test_humanize_generic_error():
    msg = humanize_command_error(RuntimeError("boom stack"))
    assert "stack" not in msg
    assert "try again" in msg.lower()
