import asyncio
import uuid
from typing import Any

from sqlalchemy import func, select

from app.dependencies import async_session
from app.models.job import EvidenceClaim, Job
from app.services import chroma_client, neo4j_client


def reconcile_projection_snapshot(
    *,
    ledger_claim_ids: set[str],
    graph_claim_ids: set[str],
    chunk_metadatas: list[dict[str, Any]],
    pending_publications: int,
) -> dict[str, Any]:
    states = {"active": 0, "draft": 0, "inactive": 0, "legacy": 0}
    active_revisions: set[str] = set()
    for metadata in chunk_metadatas:
        state = str(metadata.get("ingestion_state") or "legacy")
        if state not in states:
            state = "legacy"
        states[state] += 1
        if state == "active" and metadata.get("revision_id"):
            active_revisions.add(str(metadata["revision_id"]))

    orphan_ids = sorted(graph_claim_ids - ledger_claim_ids)
    missing_ids = sorted(ledger_claim_ids - graph_claim_ids)
    degraded = bool(
        orphan_ids
        or missing_ids
        or states["draft"]
        or pending_publications
    )
    return {
        "status": "degraded" if degraded else "ok",
        "claims": {
            "ledger_count": len(ledger_claim_ids),
            "graph_count": len(graph_claim_ids),
            "orphan_graph_claim_ids": orphan_ids,
            "missing_graph_claim_ids": missing_ids,
        },
        "chunks": {
            **states,
            "active_revisions": sorted(active_revisions),
        },
        "pending_publications": pending_publications,
    }


async def audit_case_projection(case_id: str) -> dict[str, Any]:
    case_uuid = uuid.UUID(case_id)
    async with async_session() as db:
        claim_result = await db.execute(
            select(EvidenceClaim.id).where(
                EvidenceClaim.case_id == case_uuid,
                EvidenceClaim.status.in_(["grounded", "verified"]),
            )
        )
        ledger_claim_ids = {str(claim_id) for claim_id in claim_result.scalars().all()}
        pending_result = await db.execute(
            select(func.count(Job.id)).where(
                Job.case_id == case_id,
                Job.pipeline_state["chunk_publication"]["state"].astext.in_(
                    ["staged", "ready", "publishing", "retry"]
                ),
            )
        )
        pending_publications = int(pending_result.scalar_one() or 0)

    graph_rows = await neo4j_client.execute_query(
        "MATCH (n {case_id: $case_id}) "
        "UNWIND coalesce(n.source_claim_ids, []) AS claim_id "
        "RETURN DISTINCT claim_id "
        "UNION "
        "MATCH ()-[r]->() WHERE r.case_id = $case_id "
        "UNWIND coalesce(r.source_claim_ids, []) AS claim_id "
        "RETURN DISTINCT claim_id",
        {"case_id": case_id},
    )
    graph_claim_ids = {
        str(row["claim_id"])
        for row in graph_rows
        if row.get("claim_id")
    }

    def load_chunk_metadatas() -> list[dict[str, Any]]:
        collection = chroma_client.get_or_create_collection("chunks")
        result = collection.get(where={"case_id": case_id}, include=["metadatas"])
        return [dict(metadata or {}) for metadata in (result.get("metadatas") or [])]

    chunk_metadatas = await asyncio.to_thread(load_chunk_metadatas)
    return reconcile_projection_snapshot(
        ledger_claim_ids=ledger_claim_ids,
        graph_claim_ids=graph_claim_ids,
        chunk_metadatas=chunk_metadatas,
        pending_publications=pending_publications,
    )
