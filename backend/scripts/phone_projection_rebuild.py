"""Rebuild the case graph's phone layer from Postgres (02 section 9.5).

    python backend/scripts/phone_projection_rebuild.py --case <uuid> [--drop-first]

``--drop-first`` deletes every managed phone node of the case before projecting, which shows the rebuild needs
nothing from the graph. Prints counts only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--case", required=True, type=uuid.UUID)
    ap.add_argument("--drop-first", action="store_true")
    args = ap.parse_args(argv)
    from postgres.session import _get_engine
    from services.neo4j_service import neo4j_service
    from services.phone import graph_projection
    engine = _get_engine()
    with neo4j_service.session() as s:
        dropped = graph_projection.drop(s, args.case) if args.drop_first else 0
        out = graph_projection.project_case(engine, args.case, s)
    print(json.dumps(dict(out, dropped_first=dropped), default=str, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
