"""EUR-based FX using ECB rates via CurrencyConverter.

Costs stay stored in ``*_eur``. This service converts for display and for
user-entered amounts in the profile currency.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import urllib.request
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import case, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.currency import Currency

log = logging.getLogger("app.fx")

# Display names/symbols for ECB currencies. Unknown codes fall back to the ISO code.
CURRENCY_META: dict[str, tuple[str, str]] = {
    "EUR": ("Euro", "€"),
    "USD": ("US dollar", "$"),
    "GBP": ("Pound sterling", "£"),
    "CHF": ("Swiss franc", "CHF"),
    "PLN": ("Polish zloty", "zł"),
    "CZK": ("Czech koruna", "Kč"),
    "SEK": ("Swedish krona", "kr"),
    "NOK": ("Norwegian krone", "kr"),
    "DKK": ("Danish krone", "kr"),
    "HUF": ("Hungarian forint", "Ft"),
    "RON": ("Romanian leu", "lei"),
    "BGN": ("Bulgarian lev", "лв"),
    "ISK": ("Icelandic króna", "kr"),
    "TRY": ("Turkish lira", "₺"),
    "JPY": ("Japanese yen", "¥"),
    "AUD": ("Australian dollar", "A$"),
    "CAD": ("Canadian dollar", "C$"),
    "CNY": ("Chinese yuan", "¥"),
    "HKD": ("Hong Kong dollar", "HK$"),
    "NZD": ("New Zealand dollar", "NZ$"),
    "SGD": ("Singapore dollar", "S$"),
    "INR": ("Indian rupee", "₹"),
    "BRL": ("Brazilian real", "R$"),
    "KRW": ("South Korean won", "₩"),
    "MXN": ("Mexican peso", "MX$"),
    "ZAR": ("South African rand", "R"),
    "THB": ("Thai baht", "฿"),
    "IDR": ("Indonesian rupiah", "Rp"),
    "ILS": ("Israeli shekel", "₪"),
    "PHP": ("Philippine peso", "₱"),
    "MYR": ("Malaysian ringgit", "RM"),
}

_packaged_converter = None


def convert_from_eur(amount_eur: float | None, rate: float, places: int = 2) -> float | None:
    """EUR → display currency. ``rate`` is units of target per 1 EUR."""
    if amount_eur is None:
        return None
    if rate <= 0:
        raise ValueError("FX rate must be positive")
    return round(float(amount_eur) * rate, places)


def convert_to_eur(amount: float | None, rate: float, places: int = 4) -> float | None:
    """Display currency → EUR."""
    if amount is None:
        return None
    if rate <= 0:
        raise ValueError("FX rate must be positive")
    return round(float(amount) / rate, places)


def _packaged():
    """Lazy CurrencyConverter from the library's embedded ECB file (no HTTP)."""
    global _packaged_converter
    if _packaged_converter is None:
        from currency_converter import CurrencyConverter

        _packaged_converter = CurrencyConverter(
            fallback_on_missing_rate=False,
            fallback_on_wrong_date=False,
        )
    return _packaged_converter


def _download_converter():
    """Latest ECB day only, with an HTTP timeout so startup cannot hang."""
    from currency_converter import SINGLE_DAY_ECB_URL, CurrencyConverter

    req = urllib.request.Request(SINGLE_DAY_ECB_URL)
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = resp.read()
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    try:
        tmp.write(payload)
        tmp.close()
        return CurrencyConverter(
            tmp.name,
            fallback_on_missing_rate=False,
            fallback_on_wrong_date=False,
        )
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _rows_from_converter(converter) -> list[tuple[str, str, str, float, date]]:
    as_of = date.today()
    bounds = getattr(converter, "bounds", {}) or {}
    last_dates = [pair[1] for pair in bounds.values() if pair and pair[1]]
    if last_dates:
        as_of = max(last_dates)

    codes = set(getattr(converter, "currencies", set()) or set())
    codes.add("EUR")
    rows: list[tuple[str, str, str, float, date]] = []
    for code in sorted(codes):
        name, symbol = CURRENCY_META.get(code, (code, code))
        if code == "EUR":
            rows.append((code, name, symbol, 1.0, as_of))
            continue
        last = bounds.get(code, (None, None))[1]
        if last is not None and (as_of - last).days > 14:
            continue
        try:
            rate = float(converter.convert(1, "EUR", code, date=last or as_of))
        except Exception:
            log.warning("skipping currency with no EUR rate: %s", code)
            continue
        if rate <= 0:
            continue
        rows.append((code, name, symbol, rate, last or as_of))
    return rows


def _load_rate_rows(download: bool) -> list[tuple[str, str, str, float, date]]:
    if download:
        try:
            return _rows_from_converter(_download_converter())
        except Exception:
            log.warning("ECB download failed; using packaged CurrencyConverter data", exc_info=True)
    return _rows_from_converter(_packaged())


async def refresh_rates(db: AsyncSession, *, download: bool = True) -> int:
    rows = await asyncio.to_thread(_load_rate_rows, download)
    if not rows:
        return 0
    keep = {code for code, *_ in rows}
    now = datetime.now(UTC)
    payload = [
        {
            "code": code,
            "name": name,
            "symbol": symbol,
            "rate_per_eur": Decimal(str(rate)),
            "as_of": as_of,
            "source": "ECB",
            "created_at": now,
            "updated_at": now,
        }
        for code, name, symbol, rate, as_of in rows
    ]
    stmt = insert(Currency).values(payload)
    stmt = stmt.on_conflict_do_update(
        index_elements=["code"],
        set_={
            "name": stmt.excluded.name,
            "symbol": stmt.excluded.symbol,
            "rate_per_eur": stmt.excluded.rate_per_eur,
            "as_of": stmt.excluded.as_of,
            "source": stmt.excluded.source,
            "updated_at": now,
        },
    )
    await db.execute(stmt)
    stale = await db.execute(select(Currency).where(Currency.code.not_in(keep)))
    for row in stale.scalars():
        await db.delete(row)
    await db.flush()
    log.info("refreshed %s ECB currency rows (download=%s)", len(rows), download)
    return len(rows)


async def ensure_rates(db: AsyncSession) -> None:
    exists = await db.scalar(select(Currency.code).limit(1))
    if exists is None:
        await refresh_rates(db, download=False)


async def list_currencies(db: AsyncSession) -> list[Currency]:
    await ensure_rates(db)
    result = await db.execute(
        select(Currency).order_by(case((Currency.code == "EUR", 0), else_=1), Currency.code)
    )
    return list(result.scalars().all())


async def is_supported(db: AsyncSession, code: str) -> bool:
    code = code.upper()
    if code == "EUR":
        return True
    await ensure_rates(db)
    row = await db.get(Currency, code)
    return row is not None


async def rate_for(db: AsyncSession, code: str) -> tuple[float | None, date | None]:
    """Return (units of ``code`` per 1 EUR, as_of). Never returns 1.0 for a non-EUR code."""
    code = (code or "EUR").upper()
    await ensure_rates(db)
    if code == "EUR":
        eur = await db.get(Currency, "EUR")
        return 1.0, (eur.as_of if eur else date.today())
    row = await db.get(Currency, code)
    if row is not None and float(row.rate_per_eur) > 0:
        return float(row.rate_per_eur), row.as_of
    log.warning("no FX rate for %s; display will stay in EUR until rates exist", code)
    return None, None


async def job_refresh_fx_rates() -> dict:
    from app.database import async_session

    try:
        async with async_session() as db:
            count = await refresh_rates(db, download=True)
            await db.commit()
        return {"currencies": count}
    except Exception:
        log.warning("ECB FX refresh failed", exc_info=True)
        return {"currencies": 0}
