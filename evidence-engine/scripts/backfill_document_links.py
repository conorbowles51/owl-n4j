"""Backfill Document links for cases written before graph writes made them (lx-retrieval C).

Runs the graph write's own link writer (app/pipeline/document_links.py) over each entity's stored ``source_files``
and ``source_locations``. Dry run by default: prints, per case, the counts before and the links the run would make.

    python -m scripts.backfill_document_links [--case <id> ...] [--apply]
"""
from __future__ import annotations

import argparse
import asyncio
import json

from app.pipeline.document_links import LINK_ORIGIN, plan, write_document_links
from app.services import neo4j_client
from app.services.graph_identity import ENTITY_LABEL_EXPRESSION

ENTITIES = (
    f"MATCH (e:{ENTITY_LABEL_EXPRESSION} {{case_id: $case_id}}) WHERE NOT e:Document "
    "AND (e.source_files IS NOT NULL OR e.source_locations IS NOT NULL) "
    "RETURN e.id AS id, e.source_files AS source_files, e.source_locations AS source_locations"
)
COUNTS = (
    "OPTIONAL MATCH (d:Document {case_id: $case_id}) WITH count(d) AS documents "
    "OPTIONAL MATCH (:Document {case_id: $case_id})<-[m:MENTIONED_IN]-(e {case_id: $case_id}) "
    "RETURN documents, count(m) AS links, count(DISTINCT e) AS linked_entities"
)


async def _counts(case_id: str) -> dict:
    rows = await neo4j_client.execute_query(COUNTS, {"case_id": case_id})
    return dict(rows[0]) if rows else {}


async def _case_ids() -> list[str]:
    rows = await neo4j_client.execute_query(
        f"MATCH (e:{ENTITY_LABEL_EXPRESSION}) WHERE e.case_id IS NOT NULL AND e.source_files IS NOT NULL "
        "AND NOT e.case_id STARTS WITH 'deleted-item:' RETURN DISTINCT e.case_id AS case_id", {})
    return sorted(r["case_id"] for r in rows)


async def _locked_write(query: str, params: dict) -> None:
    # The same case write lock as an ingestion's graph write, so a backfill never races one.
    await neo4j_client.execute_write(
        "MERGE (writeLock:IngestionCaseWriteLock {case_id: $case_id}) "
        "SET writeLock.sequence = coalesce(writeLock.sequence, 0) + 1 WITH writeLock " + query, params)


async def run(case_ids: list[str], apply: bool) -> list[dict]:
    report = []
    for case_id in case_ids:
        entities = [dict(r) for r in await neo4j_client.execute_query(ENTITIES, {"case_id": case_id})]
        files, links = plan(entities)
        row = {"case_id": case_id, "before": await _counts(case_id), "entities_with_sources": len(entities),
               "planned_files": len(files), "planned_links": sum(len(l["files"]) for l in links)}
        if apply:
            await write_document_links(_locked_write, case_id, entities)
            row["after"] = await _counts(case_id)
        report.append(row)
        print(json.dumps(row), flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    async def go():
        try:
            cases = args.case or await _case_ids()
            print(json.dumps({"cases": len(cases), "apply": args.apply, "origin": LINK_ORIGIN}), flush=True)
            await run(cases, args.apply)
        finally:
            await neo4j_client.close_neo4j()

    asyncio.run(go())


if __name__ == "__main__":
    main()
