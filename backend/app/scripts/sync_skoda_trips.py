"""Fill missing trips from MyŠkoda's server-side trip history (dry run by default).

  python -m app.scripts.sync_skoda_trips --all            # report what would be added
  python -m app.scripts.sync_skoda_trips --vehicle UUID --apply

Only vehicles connected with MyŠkoda Login are supported (the Public API has no trip history).
Existing trips are never deleted or overwritten; back up the database before --apply.
"""

import argparse
import asyncio
import os
import sys
from uuid import UUID

sys.path.append(os.getcwd())

from app.services.trip_sync import run_trip_sync  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--vehicle", type=UUID)
    g.add_argument("--all", action="store_true")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    a = ap.parse_args()
    res = await run_trip_sync(a.vehicle, apply=a.apply)
    for vid, r in res.items():
        print(f"{vid}: +{r.inserted} trips ({r.km_added:.0f} km), {r.distance_filled} distances filled, {r.enriched} enriched, {r.skipped_covered} already covered")
    print(f"\n{'APPLIED' if a.apply else 'DRY RUN (nothing written; use --apply)'}: {len(res)} vehicles checked")


if __name__ == "__main__":
    asyncio.run(main())
