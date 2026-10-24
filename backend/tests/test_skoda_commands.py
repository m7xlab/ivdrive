"""Tests for command capability matrix and Login-first router."""

from __future__ import annotations

import pytest

from app.services.skoda_commands import CommandUnsupported, command_supported, run_command


def test_wake_requires_login():
    assert command_supported("wake", has_login=True, has_public=False) is True
    assert command_supported("wake", has_login=False, has_public=True) is False


def test_charge_start_any_source():
    assert command_supported("charge_start", has_login=False, has_public=True) is True
    assert command_supported("charge_start", has_login=True, has_public=False) is True
    assert command_supported("charge_start", has_login=False, has_public=False) is False


def test_unknown_op_unsupported():
    assert command_supported("honk", has_login=True, has_public=True) is False


class FakeBFF:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def wake(self, vin: str) -> None:
        self.calls.append(("wake", vin))

    async def start_charging(self, vin: str) -> None:
        self.calls.append(("charge_start", vin))

    async def set_charge_limit(self, vin: str, percent: int) -> None:
        self.calls.append(("charge_limit", vin, percent))


class FakePublic:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def start_charging(self, vin: str) -> None:
        self.calls.append(("public_charge_start", vin))

    async def set_charge_limit(self, vin: str, percent: int) -> None:
        self.calls.append(("public_charge_limit", vin, percent))


@pytest.mark.asyncio
async def test_login_wins_for_commands():
    bff, pub = FakeBFF(), FakePublic()
    await run_command(
        "wake", vin="TESTVIN0000000001", login_client=bff, public_client=pub
    )
    await run_command(
        "charge_start", vin="TESTVIN0000000001", login_client=bff, public_client=pub
    )
    assert ("wake", "TESTVIN0000000001") in bff.calls
    assert ("charge_start", "TESTVIN0000000001") in bff.calls
    assert pub.calls == []


@pytest.mark.asyncio
async def test_public_used_when_no_login():
    pub = FakePublic()
    await run_command(
        "charge_start", vin="TESTVIN0000000001", login_client=None, public_client=pub
    )
    assert pub.calls == [("public_charge_start", "TESTVIN0000000001")]


@pytest.mark.asyncio
async def test_wake_without_login_raises_human_error():
    pub = FakePublic()
    with pytest.raises(CommandUnsupported) as exc:
        await run_command(
            "wake", vin="TESTVIN0000000001", login_client=None, public_client=pub
        )
    assert "Connect MyŠkoda Login to unlock / wake the car." in str(exc.value)


@pytest.mark.asyncio
async def test_charge_limit_params_passed():
    bff = FakeBFF()
    await run_command(
        "charge_limit",
        vin="TESTVIN0000000001",
        login_client=bff,
        public_client=None,
        percent=80,
    )
    assert ("charge_limit", "TESTVIN0000000001", 80) in bff.calls


class FakeBFFUnlock(FakeBFF):
    async def unlock(self, vin: str, spin: str | None = None) -> None:
        self.calls.append(("unlock", vin, spin))


@pytest.mark.asyncio
async def test_unlock_forwards_spin():
    bff = FakeBFFUnlock()
    await run_command(
        "unlock",
        vin="TESTVIN0000000001",
        login_client=bff,
        public_client=None,
        spin="1234",
    )
    assert ("unlock", "TESTVIN0000000001", "1234") in bff.calls
