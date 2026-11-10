"""Recount relationship_count on jobs that ran in a multi-file batch.

Before the per-file fix, every file of a batch was given the batch's whole relationship total. This command reads,
for each such job, the relationships in the case graph that cite the job's file (the same ``source_files`` test the
batch pipeline now uses) and, with ``--apply``, writes that number to the job. The backend copies it to the evidence
file on its next case sync. Without ``--apply`` it only reports what would change.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import defaultdict
from typing import Any

from sqlalchemy import text

from app.dependencies import async_session
from app.services import neo4j_client
from app.services.graph_identity import ENTITY_LABEL_EXPRESSION

_BATCH_JOBS = text(
    """
    SELECT j.id::text AS id, j.case_id::text AS case_id, j.batch_id::text AS batch_id, j.file_name,
           j.relationship_count
    FROM jobs j
    WHERE j.status = 'completed' AND j.job_type = 'ingestion' AND j.batch_id IN (
        SELECT batch_id FROM jobs WHERE batch_id IS NOT NULL AND job_type = 'ingestion'
        GROUP BY batch_id HAVING count(*) > 1)
      AND (CAST(:case_id AS text) IS NULL OR j.case_id::text = :case_id)
    ORDER BY j.case_id, j.batch_id, j.file_name
    """
)

_CITING = (
    f"MATCH (a:{ENTITY_LABEL_EXPRESSION} {{case_id: $case_id}})-[r]->(b:{ENTITY_LABEL_EXPRESSION} {{case_id: $case_id}}) "
    "WITH r, [f IN $names WHERE f IN coalesce(r.source_files, [])] AS cited "
    "UNWIND cited AS file_name "
    "RETURN file_name, count(DISTINCT r) AS n"
)


def planned_changes(jobs: list[dict[str, Any]], citing: dict[tuple[str, str], int]) -> list[dict[str, Any]]:
    """Jobs whose stored count differs from the relationships citing their file. ``citing`` maps (case, file) to
    a count; a file no relationship cites counts 0."""
    changes = []
    for job in jobs:
        new = int(citing.get((job["case_id"], job["file_name"]), 0))
        if int(job["relationship_count"] or 0) != new:
            changes.append({**job, "new_relationship_count": new})
    return changes


async def recount(case_id: str | None = None, *, apply: bool = False) -> dict[str, Any]:
    async with async_session() as db:
        jobs = [dict(row._mapping) for row in (await db.execute(_BATCH_JOBS, {"case_id": case_id})).all()]
        names_by_case: dict[str, set[str]] = defaultdict(set)
        for job in jobs:
            names_by_case[job["case_id"]].add(job["file_name"])
        citing: dict[tuple[str, str], int] = {}
        for case, names in names_by_case.items():
            for row in await neo4j_client.execute_query(_CITING, {"case_id": case, "names": sorted(names)}):
                citing[(case, row["file_name"])] = int(row["n"])
        changes = planned_changes(jobs, citing)
        if apply and changes:
            for change in changes:
                await db.execute(text("UPDATE jobs SET relationship_count = :n WHERE id = CAST(:id AS uuid)"),
                                 {"n": change["new_relationship_count"], "id": change["id"]})
            await db.commit()
    return {
        "applied": apply,
        "batch_jobs": len(jobs),
        "batches": len({job["batch_id"] for job in jobs}),
        "cases": len(names_by_case),
        "jobs_changed": len(changes),
        "old_total": sum(int(c["relationship_count"] or 0) for c in changes),
        "new_total": sum(c["new_relationship_count"] for c in changes),
        "changes": changes,
    }


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--summary", action="store_true", help="print counts only, not each job")
    args = parser.parse_args()
    try:
        report = await recount(args.case_id, apply=args.apply)
        if args.summary:
            report.pop("changes")
        print(json.dumps(report, indent=2, ensure_ascii=False))
    finally:
        await neo4j_client.close_neo4j()


if __name__ == "__main__":
    asyncio.run(_main())
