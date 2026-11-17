"""Add claims that pass a later check ("Check them", app.services.claim_backfill) to the graph.

At ingestion only checked claims reach the graph; a claim left unreviewed stays out. When the later check passes it,
nothing used to add it, so the graph never showed it (15 Nov 2026: 1,812 passed claims in the Verification case, none in
the graph). This places each passed claim on the nodes the file's reading already produced and writes it through the
ingestion graph write (app.pipeline.write_graph):

- The graph records which claims made each node (``source_claim_ids``). A claim's subject is a person or thing the same
  file read (its ``subject_id``); the node holding any mention or fact claim of that subject from that file is where the
  claim belongs. Nothing is matched by name.
- A link (``relationship``) between two placed nodes goes through ``write_graph`` like any ingested link: it merges with
  the same link from other files and keeps its quote, file, place and claim id.
- A fact (``entity_fact``) is merged into the node's facts with the ingestion merge (same text, file and page is not
  added twice), its claim id joins the node's, and the node's search vector is rebuilt with the new facts.
- A claim whose person or thing is not in the graph (dropped at ingestion, or in the recycle bin) is not placed. It is
  counted with its reason; nothing is invented and nothing is restored from the recycle bin.

Idempotent: a claim whose id is already on a node or link is counted as already in the graph and not written again.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

PLACEABLE = ("entity_fact", "relationship")
NOT_PLACED_SUBJECT = "Its person or thing is not in the graph."
NOT_PLACED_TARGET = "The other side of the link is not in the graph."
NOT_PLACED_CONFIDENCE = "Below the confidence an ingested link needs."


@dataclass
class Outcome:
    case_id: str
    checked: int = 0
    already: int = 0
    facts_added: int = 0
    links_added: int = 0
    nodes_touched: int = 0
    not_placed: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def as_dict(self) -> dict[str, Any]:
        return {"case_id": self.case_id, "checked": self.checked, "already_in_graph": self.already,
                "facts_added": self.facts_added, "links_added": self.links_added,
                "nodes_touched": self.nodes_touched, "not_placed": dict(self.not_placed)}


async def _passed_claims(db, case_id: str, claim_ids: list[str] | None) -> list[dict[str, Any]]:
    """Claims the later check passed. Claims passed at ingestion went through the ingestion write already."""
    from app.services.claim_backfill import SYSTEM_DESCRIPTION
    sql = ("SELECT id, evidence_file_id::text AS evidence_file_id, claim_type, subject_id, predicate, object_value, "
           "quote, source_location, confidence FROM evidence_claims WHERE case_id = CAST(:c AS uuid) "
           "AND status = 'verified' AND claim_type IN ('entity_fact', 'relationship') "
           "AND object_value->>'verification_run' = :run")
    params: dict[str, Any] = {"c": case_id, "run": SYSTEM_DESCRIPTION}
    if claim_ids is not None:
        if not claim_ids:
            return []
        sql += " AND id = ANY(:ids)"
        params["ids"] = list(claim_ids)
    return [dict(r) for r in (await db.execute(text(sql + " ORDER BY id"), params)).mappings().all()]


async def _subject_claims(db, case_id: str, file_ids: list[str]) -> dict[tuple[str, str], list[str]]:
    """(file, subject) -> the ids of that subject's claims the ingestion projected (mentions and facts)."""
    rows = (await db.execute(text(
        "SELECT id, evidence_file_id::text AS f, subject_id FROM evidence_claims WHERE case_id = CAST(:c AS uuid) "
        "AND evidence_file_id::text = ANY(:files) AND claim_type IN ('entity_mention', 'entity_fact') "
        "AND status IN ('grounded', 'verified')"), {"c": case_id, "files": file_ids})).mappings().all()
    found: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in rows:
        found[(row["f"], row["subject_id"])].append(row["id"])
    return found


async def _graph_index(case_id: str) -> tuple[dict[str, dict[str, Any]], set[str]]:
    """claim id -> live node (id, name, labels, description, aliases, facts, claim ids); every claim id on a link."""
    from app.services import neo4j_client
    from app.services.graph_identity import ENTITY_LABEL_EXPRESSION
    nodes = await neo4j_client.execute_query(
        f"MATCH (n:{ENTITY_LABEL_EXPRESSION} {{case_id: $c}}) WHERE NOT n:RecycleBin "
        "AND size(coalesce(n.source_claim_ids, [])) > 0 "
        "RETURN n.id AS id, n.name AS name, labels(n) AS labels, n.specific_type AS specific_type, "
        "n.description AS description, n.aliases AS aliases, n.verified_facts AS verified_facts, "
        "n.source_claim_ids AS claim_ids", {"c": case_id})
    by_claim: dict[str, dict[str, Any]] = {}
    for node in nodes:
        for claim_id in node["claim_ids"] or []:
            by_claim.setdefault(claim_id, node)
    links = await neo4j_client.execute_query(
        "MATCH ()-[r {case_id: $c}]->() WHERE size(coalesce(r.source_claim_ids, [])) > 0 "
        "RETURN r.source_claim_ids AS claim_ids", {"c": case_id})
    on_links = {claim_id for link in links for claim_id in link["claim_ids"] or []}
    return by_claim, on_links


def _node_for(subject_claims: dict[tuple[str, str], list[str]], by_claim: dict[str, dict[str, Any]],
              file_id: str, subject_id: str) -> dict[str, Any] | None:
    for claim_id in subject_claims.get((file_id, subject_id), []):
        if claim_id in by_claim:
            return by_claim[claim_id]
    return None


def _fact(claim: dict[str, Any]) -> dict[str, Any]:
    """The fact as ingestion stores it on a node (claim_ledger.rebuild_observations_from_claims)."""
    value, location = claim["object_value"] or {}, claim["source_location"] or {}
    return {"text": str(value.get("text") or ""), "quote": claim["quote"], "page": location.get("page_start"),
            "importance": value.get("importance", 3), "source_doc": location.get("source_file", ""),
            "source_location": dict(location), "verification_status": "verified",
            "verification_reason": value.get("verification_reason", "")}


def _link(claim: dict[str, Any], source_id: str, target_id: str):
    """The link as ingestion resolves it (resolve_entities: remap relationships)."""
    from app.pipeline.resolve_entities import ResolvedRelationship
    value, location = claim["object_value"] or {}, dict(claim["source_location"] or {})
    return ResolvedRelationship(
        source_entity_id=source_id, target_entity_id=target_id, type=claim["predicate"],
        detail=str(value.get("detail") or ""), properties=dict(value.get("properties") or {}),
        source_quotes=[claim["quote"]] if claim["quote"] else [], confidence=float(claim["confidence"] or 0),
        source_files=[location["source_file"]] if location.get("source_file") else [],
        source_locations=[{**location, "quote": claim["quote"]}] if location else [],
        source_claim_ids=[claim["id"]])


def _category(node: dict[str, Any]) -> str:
    from app.services.graph_identity import ENTITY_LABELS
    return next((label for label in node["labels"] if label in ENTITY_LABELS), "Other")


async def add_passed_claims(session_factory, case_id: str, *, apply: bool,
                            claim_ids: list[str] | None = None) -> Outcome:
    """Place the case's passed claims that are not in the graph yet; ``apply`` False counts only, no write.
    ``claim_ids``: only these claims (the ones a check run just passed)."""
    from app.config import settings
    from app.pipeline.resolve_entities import ResolvedEntity, _merge_verified_facts, _parse_json_list

    case_id = case_id.lower()
    outcome = Outcome(case_id)
    async with session_factory() as db:
        claims = await _passed_claims(db, case_id, claim_ids)
        if not claims:
            return outcome
        subject_claims = await _subject_claims(db, case_id, sorted({c["evidence_file_id"] for c in claims}))
    by_claim, on_links = await _graph_index(case_id)
    outcome.checked = len(claims)

    facts: dict[str, list[dict[str, Any]]] = defaultdict(list)   # node id -> new facts
    fact_claims: dict[str, list[str]] = defaultdict(list)
    nodes: dict[str, dict[str, Any]] = {}
    links = []
    for claim in claims:
        if claim["id"] in by_claim or claim["id"] in on_links:
            outcome.already += 1
            continue
        node = _node_for(subject_claims, by_claim, claim["evidence_file_id"], claim["subject_id"])
        if node is None:
            outcome.not_placed[NOT_PLACED_SUBJECT] += 1
            continue
        if claim["claim_type"] == "entity_fact":
            nodes[node["id"]] = node
            facts[node["id"]].append(_fact(claim))
            fact_claims[node["id"]].append(claim["id"])
            continue
        target_subject = str((claim["object_value"] or {}).get("target_entity_id") or "")
        target = _node_for(subject_claims, by_claim, claim["evidence_file_id"], target_subject)
        if target is None:
            outcome.not_placed[NOT_PLACED_TARGET] += 1
        elif float(claim["confidence"] or 0) < settings.relationship_confidence_threshold:
            outcome.not_placed[NOT_PLACED_CONFIDENCE] += 1
        else:
            links.append(_link(claim, node["id"], target["id"]))

    updates = []
    for node_id, new_facts in facts.items():
        node = nodes[node_id]
        existing = _parse_json_list(node["verified_facts"])
        merged = _merge_verified_facts(existing, new_facts)
        updates.append({"added": len(merged) - len(existing),
            "entity": ResolvedEntity(
                id=node_id, category=_category(node), specific_type=node["specific_type"] or "",
                name=node["name"] or "", aliases=list(node["aliases"] or []),
                properties={"description": node["description"] or ""}, verified_facts=merged),
            "previous_facts": node["verified_facts"], "claim_ids": fact_claims[node_id]})
    if links:
        from app.pipeline.resolve_relationships import _canonicalize_semantics, _group_key, _merge_group
        grouped: dict[tuple, list] = defaultdict(list)
        for link in _canonicalize_semantics(links, None):
            grouped[_group_key(link)].append(link)
        links = [_merge_group(group) for group in grouped.values()]
    outcome.facts_added = sum(u["added"] for u in updates)
    outcome.links_added = sum(len(link.source_claim_ids) for link in links)
    outcome.nodes_touched = len(updates) + len({n for link in links for n in (link.source_entity_id,
                                                                               link.target_entity_id)} - set(facts))
    if apply and (updates or links):
        from app.pipeline.write_graph import add_checked_facts, write_graph
        written = await add_checked_facts(updates, case_id)
        changed = [u for u in updates if u["entity"].id not in written]
        if changed:  # changed since read: counted, placed by the next run
            outcome.facts_added -= sum(u["added"] for u in changed)
            outcome.not_placed["Its node changed while this ran; the next run adds it."] += sum(
                len(u["claim_ids"]) for u in changed)
        await write_graph([], links, case_id, "claim-check")
    logger.info("Passed claims to the graph, case %s (%s): %s", case_id, "applied" if apply else "dry run",
                json.dumps(outcome.as_dict()))
    return outcome
