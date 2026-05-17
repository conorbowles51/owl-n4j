#!/usr/bin/env python3
"""
One-off migration: strip the "Location (X)" wrapper from Cellebrite Location
nodes' `name` property AND backfill `location_type` for rows where it was
left null at ingestion time.

Background:
    `ingestion/scripts/cellebrite/neo4j_writer.py` used to write
        name = "Location (X)"
        location_type = <raw or NULL>
    on every Location node. When `location_type` was NULL, the frontend
    Locations table fell back to `loc.label` (which serialises from `name`)
    and rendered "Location (Unknown)" / "Location (WhatsApp)" etc. — values
    the `type:` search suggestions endpoint can't match against because it
    only reads DISTINCT `location_type`.

    The writer now writes the bare token to both `name` and `location_type`.
    This script applies the same shape to existing rows so re-deployment
    doesn't leave the old wrapped values around.

Idempotent: re-running is safe (only matches rows still in the old shape).

Run:
    python scripts/migrate_strip_location_wrapper.py             # dry-run
    python scripts/migrate_strip_location_wrapper.py --apply     # write
"""

from __future__ import annotations

import argparse
import os
import sys

from neo4j import GraphDatabase

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "testpassword")


BACKFILL_TYPE_CYPHER = """
MATCH (n:Location {source_type: 'cellebrite'})
WHERE n.location_type IS NULL OR n.location_type = ''
WITH n, coalesce(n.source_app, 'Unknown') AS fallback
SET n.location_type = fallback
RETURN count(n) AS updated
"""

STRIP_NAME_WRAPPER_CYPHER = """
MATCH (n:Location {source_type: 'cellebrite'})
WHERE n.name STARTS WITH 'Location (' AND n.name ENDS WITH ')'
WITH n, substring(n.name, 10, size(n.name) - 11) AS unwrapped
SET n.name = unwrapped
RETURN count(n) AS updated
"""

PREVIEW_CYPHER = """
MATCH (n:Location {source_type: 'cellebrite'})
WHERE n.name STARTS WITH 'Location ('
   OR n.location_type IS NULL
   OR n.location_type = ''
RETURN count(n) AS rows_needing_update
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write changes (default: dry-run).",
    )
    args = parser.parse_args()

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            before = session.run(PREVIEW_CYPHER).single()["rows_needing_update"]
            print(f"Rows still in the old shape: {before}")

            if not args.apply:
                print("Dry-run. Re-run with --apply to write changes.")
                return 0

            if before == 0:
                print("Nothing to do.")
                return 0

            type_updated = session.run(BACKFILL_TYPE_CYPHER).single()["updated"]
            print(f"Backfilled location_type on {type_updated} rows")

            name_updated = session.run(STRIP_NAME_WRAPPER_CYPHER).single()["updated"]
            print(f"Stripped 'Location (...)' wrapper from {name_updated} names")

            after = session.run(PREVIEW_CYPHER).single()["rows_needing_update"]
            print(f"Rows remaining in old shape: {after}")
    finally:
        driver.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
