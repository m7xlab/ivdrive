"""Fill trips iVDrive's polling missed using MyŠkoda's server-side trip history.

`GET /api/v1/trip-statistics/{vin}/single-trips` returns journeys; each journey has
waypoints (stops) with exact arrival/departure times, SoC, coordinates and the
distance of the leg to the next waypoint. One leg == one iVDrive trip. Legs are
inserted only where no existing trip overlaps them in time; measured trips are never
overwritten or deleted (a 0 km trip overlapping a leg gets that leg's distance).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telemetry import Trip

logger = logging.getLogger(__name__)

DEFAULT_CAPACITY_KWH = 77.0


@dataclass
class Leg:
    start: datetime
    end: datetime
    start_odometer: float
    end_odometer: float
    start_soc: int | None
    end_soc: int | None
    start_lat: float | None
    start_lon: float | None
    end_lat: float | None
    end_lon: float | None
    journey_kwh: float | None = None   # Škoda's energy for the whole journey (0.01 kWh precision)
    journey_km: float | None = None
    times_estimated: bool = False       # Škoda's times were impossible; start/end come from our odometer readings

    @property
    def km(self) -> float:
        return self.end_odometer - self.start_odometer


def _ts(v: str | None) -> datetime | None:
    if not v:
        return None
    return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(timezone.utc)


def parse_legs(payload: dict, stats: dict | None = None) -> list[Leg]:
    """Turn a single-trips response into legs. Malformed journeys are skipped, never guessed.
    `stats['skipped_journeys']` counts journeys whose per-leg distances do not add up to the journey."""
    legs: list[Leg] = []
    for day in payload.get("dailyTrips") or []:
        for trip in day.get("trips") or []:
            wps = trip.get("waypoints") or []
            start_odo = trip.get("startMileageInKm")
            end_odo = trip.get("endMileageInKm")
            if len(wps) < 2 or start_odo is None or end_odo is None:
                continue
            odo = float(start_odo)
            built: list[Leg] = []
            ok = True
            for a, b in zip(wps, wps[1:]):
                dep, arr = _ts(a.get("departureTime")), _ts(b.get("arrivalTime"))
                if dep is None or arr is None or arr < dep:
                    ok = False
                    break
                dist = float(a.get("distanceToNextWaypointInKm") or 0)
                ca, cb = a.get("coordinates") or {}, b.get("coordinates") or {}
                built.append(Leg(
                    dep, arr, odo, odo + dist,
                    a.get("departureStateOfChargeInPercent"), b.get("arrivalStateOfChargeInPercent"),
                    ca.get("latitude"), ca.get("longitude"), cb.get("latitude"), cb.get("longitude"),
                ))
                odo += dist
            if not ok or not built:
                continue
            # The last leg may absorb per-leg km rounding (whole km each). A bigger gap means Škoda left
            # distances out: the last leg would swallow the whole journey's km inside its own short
            # time window (Nov 5: 38 km in 20 min). Skip such a journey instead of guessing.
            if abs(float(end_odo) - built[-1].end_odometer) > max(2.0, 0.5 * len(built) + 1.0):
                if stats is not None:
                    stats["skipped_journeys"] = stats.get("skipped_journeys", 0) + 1
                continue
            built[-1].end_odometer = float(end_odo)
            kwh, jkm = trip.get("electricConsumption"), trip.get("mileageInKm")
            for leg in built:
                leg.journey_kwh = float(kwh) if kwh is not None else None
                leg.journey_km = float(jkm) if jkm else None
            if built[-1].end_odometer < built[-1].start_odometer:
                continue
            legs.extend(built)
    return legs


MAX_PLAUSIBLE_KMH = 220.0
END_SLACK = timedelta(minutes=15)   # Škoda's arrival may come a little after the odometer shows the end value


def _impossible_speed(km: float, start: datetime, end: datetime) -> bool:
    hours = max((end - start).total_seconds(), 1.0) / 3600.0
    return km >= 1 and km / hours > MAX_PLAUSIBLE_KMH


async def _check_times(session: AsyncSession, vehicle_id: UUID, legs: list[Leg]) -> list[Leg]:
    """Škoda sometimes returns right distances with wrong times (Nov 5: 22 km in 63 s, 162 min after our
    own readings already showed the end odometer). A leg is untrusted when its speed is impossible or
    when the odometer had already reached the leg's end value well before the leg says it ended
    (lagging readings only ever come late, so this cannot misfire on a slow odometer). An untrusted
    leg gets the window our readings give (last reading before the start value .. first reading at
    the end value) and is labelled; with no such window it is dropped, never guessed."""
    from bisect import bisect_left

    from app.models.telemetry import OdometerReading

    if not legs:
        return legs
    lo = min(l.start for l in legs) - timedelta(days=2)
    hi = max(l.end for l in legs) + timedelta(days=2)
    rows = (await session.execute(
        select(OdometerReading.captured_at, OdometerReading.mileage_in_km)
        .where(OdometerReading.user_vehicle_id == vehicle_id, OdometerReading.captured_at >= lo, OdometerReading.captured_at <= hi)
        .order_by(OdometerReading.captured_at)
    )).all()
    times = [r[0].astimezone(timezone.utc) for r in rows]
    odos = [float(r[1]) for r in rows]
    kept: list[Leg] = []
    for leg in legs:
        first_at_end = None
        if leg.km >= 2:
            for i in range(bisect_left(times, leg.start - timedelta(hours=12)), len(times)):
                if odos[i] >= leg.end_odometer:
                    first_at_end = times[i]
                    break
        bad = _impossible_speed(leg.km, leg.start, leg.end) or (first_at_end is not None and leg.end > first_at_end + END_SLACK)
        if not bad:
            kept.append(leg)
            continue
        if first_at_end is None:                      # speed was the signal; find when the end value first showed
            for i in range(bisect_left(times, leg.start - timedelta(days=1)), len(times)):
                if odos[i] >= leg.end_odometer:
                    first_at_end = times[i]
                    break
        before = None
        if first_at_end is not None:
            for i in range(bisect_left(times, first_at_end) - 1, -1, -1):
                if odos[i] <= leg.start_odometer + 0.5:
                    before = times[i]
                    break
        if before is None or first_at_end is None or first_at_end <= before:
            logger.info("trip sync: leg %s %.0f km has impossible times and no odometer window; skipped", leg.start, leg.km)
            continue
        leg.start, leg.end, leg.times_estimated = before, first_at_end, True
        kept.append(leg)
    return kept


def _covers(trip: Trip, leg: Leg, now: datetime) -> bool:
    """A recorded trip covers a leg when they share at least half of the shorter span.

    Adjacent legs of one journey (stops of a few minutes) touch but must not count as covered.
    """
    t_start = trip.start_date.astimezone(timezone.utc)
    t_end = (trip.end_date or now).astimezone(timezone.utc)
    overlap = (min(t_end, leg.end) - max(t_start, leg.start)).total_seconds()
    shorter = max(min((t_end - t_start).total_seconds(), (leg.end - leg.start).total_seconds()), 60.0)
    return overlap >= 0.5 * shorter


def _enrich(trip: Trip, leg: Leg, capacity: float, now: datetime, apply: bool) -> bool:
    """Fill NULL energy/SoC/coordinates on a trip that this leg fully accounts for."""
    t_start = trip.start_date.astimezone(timezone.utc)
    t_end = (trip.end_date or now).astimezone(timezone.utc)
    dur = max((t_end - t_start).total_seconds(), 60.0)
    if (min(t_end, leg.end) - max(t_start, leg.start)).total_seconds() < 0.8 * dur:
        return False  # trip spans more than this leg: ambiguous, leave it
    changes: dict = {}
    if trip.start_soc is None and leg.start_soc is not None:
        changes["start_soc"] = leg.start_soc
    if trip.end_soc is None and leg.end_soc is not None:
        changes["end_soc"] = leg.end_soc
    if trip.kwh_consumed is None and leg.start_soc is not None and leg.end_soc is not None and leg.start_soc > leg.end_soc:
        changes["kwh_consumed"] = (leg.start_soc - leg.end_soc) / 100.0 * capacity
    for attr, val in (("start_lat", leg.start_lat), ("start_lon", leg.start_lon), ("end_lat", leg.end_lat), ("end_lon", leg.end_lon)):
        if getattr(trip, attr) is None and val is not None:
            changes[attr] = val
    if changes and apply:
        for k, v in changes.items():
            setattr(trip, k, v)
    return bool(changes)


@dataclass
class SyncResult:
    inserted: int = 0
    rewritten: int = 0       # merged / fragmented recorded trips replaced by Škoda's legs
    removed: int = 0         # duplicate rows deleted (a leg is already represented elsewhere)
    distance_filled: int = 0
    enriched: int = 0
    skipped_covered: int = 0
    error: str | None = None  # set when this vehicle's sync failed; nothing was written
    conflicts: int = 0       # rewrites skipped because another row already starts at that time
    km_added: float = 0.0


# ── matching: odometer first (exact integers on both sides), time only as a fallback ──────
SAME_IOU = 0.7          # odometer ranges that overlap this much are the same trip
INSIDE = 0.8            # share of a trip inside a leg (fragment) / of a leg inside a trip (merged)
NEAR = timedelta(minutes=20)
FRAGMENT_WINDOW = timedelta(hours=24)


def _orange(t: Trip) -> tuple[float, float] | None:
    s, e = t.start_odometer, t.end_odometer
    return (float(s), float(e)) if s is not None and e is not None and e >= s else None


def _inter(a: tuple[float, float], b: tuple[float, float]) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def _lrange(leg: Leg) -> tuple[float, float]:
    return (leg.start_odometer, leg.end_odometer)


def _is_same(t: Trip, leg: Leg, now: datetime) -> bool:
    """Same drive: both odometer ends agree (whole-km rounding, a late or lagging poll). A recorded
    trip that runs past the leg by more than that swallowed the next leg and is handled as merged."""
    tr, lr = _orange(t), _lrange(leg)
    if tr and tr[1] > tr[0] and lr[1] > lr[0]:
        if abs(tr[0] - lr[0]) < 0.5 and abs(tr[1] - lr[1]) < 0.5:
            return True  # the same odometer span cannot be driven twice, whatever time the row says
        tol = max(1.0, 0.1 * (lr[1] - lr[0]))
        ts = t.start_date.astimezone(timezone.utc)
        return (
            abs(tr[0] - lr[0]) <= tol and abs(tr[1] - lr[1]) <= tol
            and leg.start - timedelta(hours=1) <= ts <= leg.end + timedelta(hours=1)
        )
    return _covers(t, leg, now)  # no usable odometer (or a 0 km trip): fall back to time


def _is_fragment_of(t: Trip, leg: Leg) -> bool:
    """A smaller recorded trip lying inside this leg's odometer range and around its time."""
    tr, lr = _orange(t), _lrange(leg)
    if not tr or tr[1] <= tr[0] or lr[1] <= lr[0]:
        return False
    if _inter(tr, lr) / (tr[1] - tr[0]) < INSIDE:
        return False
    ts = t.start_date.astimezone(timezone.utc)
    # The same kilometres cannot be driven twice, so the odometer decides; the time window only
    # guards against a corrupt odometer (Nov 5: live trips 4 h before a leg's own time window).
    return leg.start - FRAGMENT_WINDOW <= ts <= leg.end + FRAGMENT_WINDOW


def _legs_inside(t: Trip, legs: list[Leg]) -> list[int]:
    """Indexes of legs that lie (>= 80 %) inside this recorded trip's odometer range."""
    tr = _orange(t)
    if not tr or tr[1] <= tr[0]:
        return []
    out = []
    for i, leg in enumerate(legs):
        lr = _lrange(leg)
        if lr[1] > lr[0] and _inter(tr, lr) / (lr[1] - lr[0]) >= INSIDE:
            out.append(i)
    return out


def _quality_rank(t: Trip) -> tuple:
    """Prefer rows that already carry Škoda's values, then the most complete one."""
    filled = sum(v is not None for v in (t.start_soc, t.end_soc, t.kwh_consumed, t.start_lat, t.end_lat))
    return (t.data_quality in ("skoda_history", "estimated_times"), filled)


def leg_kwh(leg: Leg, capacity: float) -> float | None:
    """Energy of one leg. SoC only moves in whole percent (1 % = 0.77 kWh), so a 2 km leg would show
    38 kWh/100 km. Use the SoC drop for long legs with a clear drop, otherwise the journey's own
    energy shared by distance."""
    drop = (leg.start_soc - leg.end_soc) if leg.start_soc is not None and leg.end_soc is not None else None
    if drop and drop >= 5 and leg.km >= 15:
        return drop / 100.0 * capacity
    if leg.journey_kwh is not None and leg.journey_km:
        return leg.journey_kwh * leg.km / leg.journey_km
    return drop / 100.0 * capacity if drop and drop > 0 else None


def _rewrite(t: Trip, leg: Leg, capacity: float) -> None:
    t.start_date, t.end_date = leg.start, leg.end
    t.start_odometer, t.end_odometer, t.distance_km = leg.start_odometer, leg.end_odometer, leg.km
    t.start_soc, t.end_soc = leg.start_soc, leg.end_soc
    t.start_lat, t.start_lon, t.end_lat, t.end_lon = leg.start_lat, leg.start_lon, leg.end_lat, leg.end_lon
    t.kwh_consumed = leg_kwh(leg, capacity)
    t.data_quality = "estimated_times" if leg.times_estimated else "skoda_history"


def _km_apart(lat1, lon1, lat2, lon2) -> float:
    from math import cos, radians, sqrt
    return 111.0 * sqrt((lat2 - lat1) ** 2 + ((lon2 - lon1) * cos(radians(lat1))) ** 2)


def _apply_authoritative(row: Trip, leg: Leg, capacity: float, taken: set, apply: bool) -> str | None:
    """A recorded trip that is the same drive as a Škoda leg takes Škoda's values: its start is a
    late poll, its position the last *parked* one, its SoC a late reading. Returns what changed:
    'rewritten' (time / odometer / position corrected), 'enriched' (only empty fields filled),
    'conflict' (another row already starts at the leg's start: left as is) or None."""
    now = datetime.now(timezone.utc)
    t_start, t_end = row.start_date.astimezone(timezone.utc), (row.end_date or now).astimezone(timezone.utc)
    if leg.times_estimated:
        # Škoda's times for this leg are not believable; its distance and odometer are. A recorded row
        # with sound times keeps them; a row with impossible ones (written by v1.3.10) takes the window.
        row_sound = (row.end_date is not None and not _impossible_speed(row.distance_km or 0.0, t_start, t_end)
                     and t_end <= leg.end + END_SLACK)
        if row_sound:
            leg = replace(leg, start=row.start_date, end=row.end_date, times_estimated=False)
    time_off = abs((t_start - leg.start).total_seconds()) > 120 or abs((t_end - leg.end).total_seconds()) > 120
    odo_off = (row.start_odometer is None or row.end_odometer is None
               or abs(float(row.start_odometer) - leg.start_odometer) >= 1 or abs(float(row.end_odometer) - leg.end_odometer) >= 1)
    pos_off = any(
        a is not None and b is not None and c is not None and d is not None and _km_apart(a, b, c, d) > 0.5
        for a, b, c, d in ((row.start_lat, row.start_lon, leg.start_lat, leg.start_lon),
                           (row.end_lat, row.end_lon, leg.end_lat, leg.end_lon)))
    soc_off = (leg.start_soc is not None and row.start_soc != leg.start_soc) or (leg.end_soc is not None and row.end_soc != leg.end_soc)
    kwh = leg_kwh(leg, capacity)
    kwh_off = kwh is not None and (row.kwh_consumed is None or abs(row.kwh_consumed - kwh) > 0.05)
    missing_pos = any(getattr(row, a) is None and v is not None for a, v in (
        ("start_lat", leg.start_lat), ("start_lon", leg.start_lon), ("end_lat", leg.end_lat), ("end_lon", leg.end_lon)))
    if leg.start != row.start_date and leg.start in taken:
        return "conflict"  # another row already starts exactly here; leave this one as is
    material = time_off or odo_off or pos_off
    if not (material or soc_off or kwh_off or missing_pos):
        return None
    if apply:
        keep_quality = row.data_quality
        if material:
            taken.discard(row.start_date)
            _rewrite(row, leg, capacity)
            taken.add(leg.start)
        else:  # only empty / coarse fields: fill them, keep the row's own label
            if leg.start_soc is not None:
                row.start_soc = leg.start_soc
            if leg.end_soc is not None:
                row.end_soc = leg.end_soc
            if kwh is not None:
                row.kwh_consumed = kwh
            for a, v in (("start_lat", leg.start_lat), ("start_lon", leg.start_lon), ("end_lat", leg.end_lat), ("end_lon", leg.end_lon)):
                if getattr(row, a) is None and v is not None:
                    setattr(row, a, v)
            row.data_quality = keep_quality
    return "rewritten" if material else "enriched"


async def sync_legs(
    session: AsyncSession,
    vehicle_id: UUID,
    legs: list[Leg],
    *,
    capacity_kwh: float | None = None,
    apply: bool = True,
) -> SyncResult:
    """Make exactly one trip row per Škoda leg, without losing or double counting distance.

    Order of decisions per leg: an equal recorded trip (odometer overlap >= 70 %) stays and is
    enriched; a recorded trip spanning several legs is rewritten as the first leg that has no row
    yet; smaller fragments inside a leg are folded into it. Duplicates are removed only when the
    leg is already represented by another row. Trips outside Škoda's window are never touched.
    """
    res = SyncResult()
    if not legs:
        return res
    capacity = capacity_kwh or DEFAULT_CAPACITY_KWH
    legs = sorted(await _check_times(session, vehicle_id, legs), key=lambda x: x.start)
    if not legs:
        return res
    now = datetime.now(timezone.utc)
    lo, hi = legs[0].start - timedelta(days=1), legs[-1].end + timedelta(days=1)
    existing = list((await session.execute(
        select(Trip).where(
            Trip.user_vehicle_id == vehicle_id,
            Trip.end_date.is_not(None),          # an open trip belongs to the live poller
            Trip.start_date < hi,
            Trip.end_date > lo,
        ).order_by(Trip.start_date)
    )).scalars())

    assigned: dict[int, Trip] = {}   # leg index -> row that represents it (kept as is)
    reuse: dict[int, Trip] = {}      # leg index -> row to rewrite into this leg
    claimed: set[int] = set()
    delete: list[Trip] = []

    # 1) equal trips: keep the best one per leg, the rest are duplicates of it
    for i, leg in enumerate(legs):
        same = [t for t in existing if t.id not in claimed and _is_same(t, leg, now)]
        if same:
            best = max(same, key=_quality_rank)
            assigned[i] = best
            claimed.update(t.id for t in same)
            delete += [t for t in same if t is not best and _orange(t) and _orange(t)[1] > _orange(t)[0]]
            claimed.update(t.id for t in same)

    # 2) a recorded trip that spans several legs (a stop polling never saw)
    for t in existing:
        if t.id in claimed:
            continue
        hit = _legs_inside(t, legs)
        if len(hit) < 2:
            continue
        tr = _orange(t)
        span, km = tr[1] - tr[0], sum(legs[i].km for i in hit)
        if not (0.85 * span - 1 <= km <= 1.15 * span + 1):
            continue  # does not add up to these legs: leave it alone
        claimed.add(t.id)
        free = [i for i in hit if i not in assigned and i not in reuse]
        if free:
            reuse[free[0]] = t
        else:
            delete.append(t)  # every leg already has its own row

    # 3) fragments inside a leg (a late-detected piece of the same drive)
    frags: dict[int, list[Trip]] = {}
    for t in existing:
        if t.id in claimed:
            continue
        for i, leg in enumerate(legs):
            if _is_fragment_of(t, leg):
                frags.setdefault(i, []).append(t)
                claimed.add(t.id)
                break
    for i, group in frags.items():
        if i in assigned or i in reuse:
            delete += group
        else:
            group.sort(key=lambda x: x.start_date)
            reuse[i] = group[0]
            delete += group[1:]

    # apply: deletions first so a rewritten row cannot collide on (vehicle, start_date)
    for t in delete:
        res.removed += 1
        if apply:
            await session.delete(t)
    if apply and delete:
        await session.flush()
    taken = {t.start_date for t in existing if t not in delete}
    first_start = {t.id: t.start_date for t in existing}
    for i, leg in enumerate(legs):
        if i in reuse:
            row = reuse[i]
            if leg.start in taken and leg.start != row.start_date:
                res.conflicts += 1
                continue  # another row already starts exactly here; leave this one as is
            res.rewritten += 1
            res.km_added += max(0.0, leg.km - (row.distance_km or 0.0))
            if apply:
                taken.discard(row.start_date)
                _rewrite(row, leg, capacity)
                taken.add(leg.start)
        elif i in assigned:
            row = assigned[i]
            had_no_distance = row.distance_km in (None, 0)
            km_before = row.distance_km or 0.0        # _apply_authoritative may overwrite it
            kind = _apply_authoritative(row, leg, capacity, taken, apply)
            if kind == "rewritten":
                res.rewritten += 1
                res.km_added += max(0.0, leg.km - km_before)
            elif kind == "enriched":
                res.enriched += 1
            elif kind == "conflict":
                res.conflicts += 1
            else:
                res.skipped_covered += 1
            if had_no_distance and leg.km > 0:
                res.distance_filled += 1
        elif leg.km > 0 and leg.start not in taken:
            res.inserted += 1
            res.km_added += leg.km
            if apply:
                used = (leg.start_soc - leg.end_soc) if leg.start_soc is not None and leg.end_soc is not None else None
                session.add(Trip(
                    user_vehicle_id=vehicle_id, start_date=leg.start, end_date=leg.end,
                    start_lat=leg.start_lat, start_lon=leg.start_lon, end_lat=leg.end_lat, end_lon=leg.end_lon,
                    start_odometer=leg.start_odometer, end_odometer=leg.end_odometer, distance_km=leg.km,
                    start_soc=leg.start_soc, end_soc=leg.end_soc,
                    kwh_consumed=leg_kwh(leg, capacity),
                    data_quality="estimated_times" if leg.times_estimated else "skoda_history",
                ))
                taken.add(leg.start)
    if apply:
        await _flush_start_moves(session, [t for t in existing if t not in delete], first_start)
    return res


_PARK = datetime(1970, 1, 1, tzinfo=timezone.utc)


async def _flush_start_moves(session: AsyncSession, rows: list[Trip], first_start: dict) -> None:
    """Write rows whose start moved without depending on UPDATE order. The unique key
    (vehicle, start_date) is checked per statement, so row X taking the start that row Y is about
    to give up fails if X is written first. Park the moved rows on unique placeholder times, write
    that, then set the real times: at that point no moved row holds a real start any more."""
    moved = [(t, t.start_date) for t in rows if t.id in first_start and t.start_date != first_start[t.id]]
    final = [st for _, st in moved] + [t.start_date for t in rows if t.id in first_start and t.start_date == first_start[t.id]]
    if len(set(final)) != len(final):
        raise ValueError("trip sync planned two trips with the same start time; nothing was written")
    for i, (t, _) in enumerate(moved):
        t.start_date = _PARK + timedelta(seconds=i)
    if moved:
        await session.flush()
        for t, st in moved:
            t.start_date = st
    await session.flush()


# Škoda's private API can change or be switched off at any time. Polling stays the primary
# record; this layer only repairs. On failure: back off (30 min doubling to 24 h), say so once.
_failures: dict[UUID, tuple[int, datetime]] = {}
MAX_BACKOFF = timedelta(hours=24)


def _note_failure(vid: UUID, why: str) -> None:
    n = _failures.get(vid, (0, None))[0] + 1
    wait = min(MAX_BACKOFF, timedelta(minutes=30) * 2 ** (n - 1))
    _failures[vid] = (n, datetime.now(timezone.utc) + wait)
    log = logger.warning if n == 1 else logger.info
    log("trip sync paused for %s (%s); retry in %s. Polling is unaffected.", vid, why, wait)


def _valid_payload(payload: object) -> bool:
    return isinstance(payload, dict) and isinstance(payload.get("dailyTrips"), list)


def _print_journeys(vid: UUID, payload: dict) -> None:
    """Waypoint times and distances only (no coordinates), for pasting into a bug report."""
    print(f"# {vid}")
    for day in payload.get("dailyTrips") or []:
        for trip in day.get("trips") or []:
            print(f"journey {trip.get('startMileageInKm')} -> {trip.get('endMileageInKm')} km, {trip.get('mileageInKm')} km, {trip.get('electricConsumption')} kWh")
            for w in trip.get("waypoints") or []:
                print(f"  arr={w.get('arrivalTime')} dep={w.get('departureTime')} soc={w.get('arrivalStateOfChargeInPercent')}/{w.get('departureStateOfChargeInPercent')} next_km={w.get('distanceToNextWaypointInKm')}")


async def run_trip_sync(only_vehicle: UUID | None = None, *, apply: bool = True, pause_s: float = 3.0, dump: bool = False) -> dict[str, SyncResult]:
    """One pass over every MyŠkoda-Login vehicle. Never raises; one vehicle failing is logged and skipped.

    Independent of the smart poller: its own schedule, one GET per vehicle per run.
    """
    import asyncio
    import json

    from sqlalchemy.orm import selectinload

    from app.database import async_session
    from app.models.vehicle import UserVehicle
    from app.services.crypto import decrypt_field
    from app.services.skoda_api import SkodaAPIClient
    from app.services.skoda_lifecycle import AuthRequiredError, LoginDeferred, SkodaTokenLifecycle

    out: dict[str, SyncResult] = {}
    skipped: dict[str, int] = {}     # reason -> vehicles; a skip is otherwise invisible
    odd_journeys = 0

    def _skip(reason: str) -> None:
        skipped[reason] = skipped.get(reason, 0) + 1

    async with async_session() as s:
        q = select(UserVehicle.id).where(UserVehicle.collection_enabled.is_(True))
        if only_vehicle:
            q = q.where(UserVehicle.id == only_vehicle)
        ids = list((await s.execute(q)).scalars())

    for vid in ids:
        retry_at = _failures.get(vid, (0, None))[1]
        if retry_at and datetime.now(timezone.utc) < retry_at:
            _skip("backing off after an earlier failure")
            continue
        try:
            async with async_session() as s:
                v = (await s.execute(
                    select(UserVehicle).where(UserVehicle.id == vid).options(selectinload(UserVehicle.connector_session))
                )).scalar_one_or_none()
                cs = v.connector_session if v else None
                if v is None or cs is None or cs.status in ("token_error", "auth_failed"):
                    _skip("no usable MyŠkoda Login session")
                    continue  # no MyŠkoda Login for this vehicle (Public API has no trip history)
                username = password = None
                if v.connector_config_encrypted:
                    try:
                        cfg = json.loads(decrypt_field(v.connector_config_encrypted))
                        username, password = cfg.get("username"), cfg.get("password")
                    except Exception:
                        pass
                try:
                    # The history sync never logs in by itself: with a dead session it skips the vehicle.
                    token = await SkodaTokenLifecycle(s).ensure_valid_token(cs, username, password, allow_login=False)
                except (AuthRequiredError, LoginDeferred) as e:
                    _skip("login needed or deferred" if isinstance(e, LoginDeferred) else "login rejected")
                    continue
                api = SkodaAPIClient(token)
                try:
                    payload = await api.get_single_trips(decrypt_field(v.vin_encrypted))
                except Exception as e:
                    _note_failure(vid, f"history request failed: {type(e).__name__} {str(e)[:60]}")
                    continue
                finally:
                    await api.close()
                if not _valid_payload(payload):
                    _note_failure(vid, "unexpected response format (Škoda may have changed the API)")
                    continue
                if vid in _failures:
                    logger.info("trip sync recovered for %s", vid)
                    _failures.pop(vid, None)
                if dump:
                    _print_journeys(vid, payload)
                    continue
                await s.commit()  # keep a refreshed token whatever happens below
                parse_stats: dict = {}
                legs = parse_legs(payload, parse_stats)
                odd_journeys += parse_stats.get("skipped_journeys", 0)
                # A dry run is the real run, rolled back: it hits the same database rules, so it
                # cannot succeed where --apply would fail.
                res = await sync_legs(s, vid, legs, capacity_kwh=v.battery_capacity_kwh, apply=True)
                if apply:
                    await s.commit()
                else:
                    await s.rollback()
                out[str(vid)] = res
                if res.inserted or res.rewritten or res.removed or res.distance_filled or res.enriched or res.conflicts:
                    logger.info("trip sync %s: +%d trips, %d merged/split, %d duplicates removed, %d distances filled, %d enriched, %d skipped (start time taken), +%.0f km (apply=%s)",
                                vid, res.inserted, res.rewritten, res.removed, res.distance_filled, res.enriched, res.conflicts, res.km_added, apply)
        except Exception as e:  # one vehicle must never stop the rest; its transaction is rolled back
            logger.warning("trip sync failed for %s: %s", vid, str(e)[:200])
            if "Login" not in str(e)[:40]:
                _note_failure(vid, f"{type(e).__name__}")
            out[str(vid)] = SyncResult(error=f"{type(e).__name__}: {str(e)[:120]}")
        await asyncio.sleep(pause_s)
    failed = sum(1 for r in out.values() if r.error)
    msg = "trip sync run: %d vehicles synced, %d failed, skipped %s, %d journeys ignored (distances did not add up) (apply=%s)"
    (logger.warning if failed or skipped or odd_journeys else logger.info)(
        msg, len(out) - failed, failed, skipped or "none", odd_journeys, apply)
    return out
