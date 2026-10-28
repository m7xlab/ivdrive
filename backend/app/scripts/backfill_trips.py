"""Repair historical trip distances from odometer readings (dry-run by default).

  python -m app.scripts.backfill_trips --all --since 2026-01-01            # report
  python -m app.scripts.backfill_trips --vehicle UUID --apply              # fix zero-distance trips
  python -m app.scripts.backfill_trips --all --apply --create-reconstructed  # also add gap trips
  python -m app.scripts.backfill_trips --all --apply --purge-phantom           # delete 0 km <=15 min trips

Back up the database before using --apply.
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from uuid import UUID

sys.path.append(os.getcwd())

from sqlalchemy import select  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.vehicle import UserVehicle  # noqa: E402
from app.services.trip_reconcile import (  # noqa: E402
    create_reconstructed_trips, find_phantom_trips, find_uncovered_gaps, reconcile_zero_distance_trips,
)


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--vehicle", type=UUID)
    g.add_argument("--all", action="store_true")
    ap.add_argument("--since", help="YYYY-MM-DD (default: all history)")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("--create-reconstructed", action="store_true",
                    help="add data_quality='reconstructed' trips for uncovered odometer gaps")
    ap.add_argument("--purge-phantom", action="store_true",
                    help="DELETE closed 0 km trips <= 15 min with no odometer rise (irreversible; back up first)")
    a = ap.parse_args()
    since = datetime.fromisoformat(a.since).replace(tzinfo=timezone.utc) if a.since else None

    async with async_session() as s:
        ids = [a.vehicle] if a.vehicle else list((await s.execute(select(UserVehicle.id))).scalars())
        tot_fix = tot_km = tot_gap_km = tot_new = tot_ph = 0
        for vid in ids:
            fixes = await reconcile_zero_distance_trips(s, vid, since=since, apply=a.apply)
            gaps = await find_uncovered_gaps(s, vid, since=since)
            new = await create_reconstructed_trips(s, vid, gaps) if (a.apply and a.create_reconstructed) else 0
            phantoms = await find_phantom_trips(s, vid, since=since)
            if a.apply and a.purge_phantom:
                for ph in phantoms:
                    await s.delete(ph)
            tot_ph += len(phantoms)
            if fixes or gaps or phantoms:
                print(f"{vid}: {len(fixes)} zero-distance trips fixable (+{sum(f.new_distance for f in fixes):.0f} km), "
                      f"{len(gaps)} uncovered odometer gaps ({sum(x.km for x in gaps):.0f} km), "
                      f"{len(phantoms)} phantom 0 km trips")
            tot_fix += len(fixes); tot_km += sum(f.new_distance for f in fixes)
            tot_gap_km += sum(x.km for x in gaps); tot_new += new
        if a.apply:
            await s.commit()
        mode = "APPLIED" if a.apply else "DRY RUN (nothing written; use --apply)"
        print(f"\n{mode}: {tot_fix} trips / {tot_km:.0f} km repaired; "
              f"{tot_gap_km:.0f} km in uncovered gaps; {tot_new} reconstructed trips created; "
              f"{tot_ph} phantom trips {'deleted' if a.apply and a.purge_phantom else 'found'}")


if __name__ == "__main__":
    asyncio.run(main())
