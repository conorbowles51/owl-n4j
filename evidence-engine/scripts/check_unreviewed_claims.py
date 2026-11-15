"""Check claims an earlier ingestion left unreviewed, through the ingestion claim check (app.services.claim_backfill).

Without ``--apply`` it reads only: unreviewed claims per case and file, cheapest first, and no model is called.
With ``--apply`` it checks them, case by case and file by file, cheapest first, each case stopping at its AI
spending limit; the cost is recorded to the case. ``--case`` limits it to one case; ``--max-claims`` to about that
many claims per case (whole batches). It prints one JSON summary: counts before, checked, verdicts, and every file it
stopped on with the reason and the claims left.
"""
from __future__ import annotations

import argparse
import asyncio
import json

from app.dependencies import async_session
from app.services import claim_backfill as B


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--case", help="one case id; default every case with unreviewed claims, cheapest first")
    ap.add_argument("--apply", action="store_true", help="check and write; without it nothing is called or written")
    ap.add_argument("--max-claims", type=int, default=None)
    args = ap.parse_args()
    async with async_session() as db:
        counts = await B.unreviewed_counts(db)
    if args.case:
        counts = [c for c in counts if c["case_id"] == args.case]
    if not args.apply:
        print(json.dumps({"apply": False, "cases": [{"case_id": c["case_id"], "unreviewed": c["unreviewed"],
                                                    "files": len(c["files"])} for c in counts],
                          "unreviewed": sum(c["unreviewed"] for c in counts)}, indent=1))
        return
    outcomes = []
    for entry in counts:
        outcome = await B.check_case(async_session, entry["case_id"], apply=True, max_claims=args.max_claims)
        outcomes.append(outcome)
        print(json.dumps({"case_id": outcome.case_id, "before": outcome.before, "checked": outcome.checked}),
              flush=True)
    async with async_session() as db:
        after = {c["case_id"]: c["unreviewed"] for c in await B.unreviewed_counts(db)}
    print(json.dumps({**B.summary(outcomes), "after": {o.case_id: after.get(o.case_id, 0) for o in outcomes}},
                     indent=1))


if __name__ == "__main__":
    asyncio.run(main())
