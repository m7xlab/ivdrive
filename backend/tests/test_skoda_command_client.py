"""Facade-level tests for SkodaCommandClient spin forwarding."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

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
