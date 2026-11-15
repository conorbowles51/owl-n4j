"""After a graph merge: theory, finding and note links and saved groups follow the merged entity, and the merged entity
can say what it was merged from (lineage).

A merge replaces several graph entities with one (the engine writes it; ``job_status_subscriber`` settles the job and
recycles the sources). Significant marks and dossiers already move (``significant_service``, ``dossier_service``).
This module moves the rest of the case's own work that points at a source key:

* a Workspace entry's ``graph_entity`` link is re-pointed to the merged key. The link keeps its id, relationship,
  reason, who added it and its narratives; ``metadata.merged_from`` records the key and name it pointed at before,
  the merge and when. Where the entry already links the merged key (two sources in one theory, or the merged key
  itself), the source link is folded into that one: its record is appended to the kept link's ``merged_from`` and
  its narratives move to the kept link, so nothing a person wrote is lost;
* a saved group (``case_selections``) holding a source key holds the merged key instead, once, with the member's
  ``merged_from``; the member count follows, and the collection index of every link to that group follows too.

``lineage`` reads the merge records (``merge_jobs``) and the recycled sources' names (``graph_recycle_bin``): the
merges that made an entity, oldest first, each with the keys and names merged and who merged them. Reads only.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import select, update

GRAPH = "graph_entity"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _names(db, case_id, keys: list[str]) -> dict[str, str]:
    from postgres.models.graph_recycle_bin import GraphRecycleBinItem as R
    if not keys:
        return {}
    rows = db.execute(select(R.original_key, R.original_name).where(R.case_id == case_id, R.original_key.in_(keys))
                      .order_by(R.created_at)).all()
    return {key: name for key, name in rows if name}


def carry_casework_after_merge(db, *, case_id, source_entity_keys: Iterable[str], merged_entity_key: str,
                               merge_job_id=None) -> dict[str, int]:
    """Move entry links and saved-group members from the source keys to the merged key. Commits nothing; the caller
    commits with the rest of the merge. Returns counts: links re-pointed, links folded, groups changed."""
    from postgres.models.case_selection import CaseSelection
    from postgres.models.collection_membership import CollectionMembership
    from postgres.models.theory_narrative import TheoryNarrative
    from postgres.models.workspace_entry import WorkspaceEntryLink as L
    keys = [k for k in dict.fromkeys(filter(None, source_entity_keys)) if k != merged_entity_key]
    counts = {"links_moved": 0, "links_folded": 0, "groups": 0}
    if not keys or not merged_entity_key:
        return counts
    names = _names(db, case_id, keys)
    stamp = {"merge_job_id": str(merge_job_id) if merge_job_id else None, "at": _now(), "into": merged_entity_key}

    def record(link) -> dict[str, Any]:
        return {**stamp, "key": link.target_id, "name": names.get(link.target_id) or link.target_label,
                "relationship": link.relationship_type, "link_id": str(link.id)}

    from services.theory_additions import _added_order
    sources = sorted(db.scalars(select(L).where(L.case_id == case_id, L.target_type == GRAPH,
                                                L.target_id.in_(keys))).all(), key=_added_order)
    kept_by_entry = {row.entry_id: row for row in db.scalars(select(L).where(
        L.case_id == case_id, L.target_type == GRAPH, L.target_id == merged_entity_key))}
    for link in sources:
        kept = kept_by_entry.get(link.entry_id)
        if kept is None:
            meta = dict(link.link_metadata or {})
            meta["merged_from"] = [*(meta.get("merged_from") or []), record(link)]
            link.link_metadata = meta
            link.target_id = merged_entity_key
            kept_by_entry[link.entry_id] = link
            counts["links_moved"] += 1
            continue
        meta = dict(kept.link_metadata or {})
        folded = record(link)
        folded["why"] = ((link.link_metadata or {}).get("addition") or {}).get("why")
        meta["merged_from"] = [*(meta.get("merged_from") or []), folded]
        kept.link_metadata = meta
        db.execute(update(TheoryNarrative).where(TheoryNarrative.link_id == link.id).values(link_id=kept.id))
        db.flush()
        db.delete(link)
        counts["links_folded"] += 1
    db.flush()

    refs = {f"{GRAPH}:{k}" for k in keys}
    merged_ref = f"{GRAPH}:{merged_entity_key}"
    for group in db.scalars(select(CaseSelection).where(CaseSelection.case_id == case_id)):
        members = list(group.members or [])
        if not any(m.get("type") == GRAPH and m.get("id") in keys for m in members):
            continue
        result: list[dict[str, Any]] = []
        merged_at: int | None = None
        for m in members:
            is_graph = m.get("type") == GRAPH
            if is_graph and m.get("id") in keys:
                notes = [{**stamp, "key": m["id"], "name": names.get(m["id"]) or m.get("label")}]
            elif is_graph and m.get("id") == merged_entity_key:
                notes = list(m.get("merged_from") or [])
            else:
                result.append(m)
                continue
            if merged_at is None:  # the merged entity takes the place of the first of its members
                merged_at = len(result)
                result.append({**m, "id": merged_entity_key, "merged_from": notes})
            else:
                held = result[merged_at]
                result[merged_at] = {**held, "merged_from": [*(held.get("merged_from") or []), *notes]}
        group.members = result
        group.member_count = len(result)
        counts["groups"] += 1
        link_ids = [row for row in db.scalars(select(L.id).where(L.case_id == case_id, L.target_id == str(group.id)))]
        for link_id in link_ids:
            held = set(db.scalars(select(CollectionMembership.record_id).where(CollectionMembership.link_id == link_id)))
            for ref in refs & held:
                if merged_ref in held:
                    db.execute(CollectionMembership.__table__.delete().where(
                        CollectionMembership.link_id == link_id, CollectionMembership.record_id == ref))
                else:
                    db.execute(update(CollectionMembership).where(
                        CollectionMembership.link_id == link_id, CollectionMembership.record_id == ref)
                        .values(record_id=merged_ref))
                    held.add(merged_ref)
    db.flush()
    return counts


def lineage(db, *, case_id, entity_key: str, depth: int = 10) -> list[dict[str, Any]]:
    """The merges that made this entity, oldest first: each with the keys and names merged, who merged them, when, and
    whether every source was recycled. A source that was itself a merge brings its own merges first."""
    from postgres.models.merge_job import MergeJob
    case = case_id if isinstance(case_id, uuid.UUID) else uuid.UUID(str(case_id))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def walk(key: str, level: int):
        if level > depth or key in seen:
            return
        seen.add(key)
        jobs = db.scalars(select(MergeJob).where(MergeJob.case_id == case, MergeJob.merged_entity_key == key,
                                                 MergeJob.status.in_(("completed", "partial")))
                          .order_by(MergeJob.created_at)).all()
        for job in jobs:
            sources = [k for k in (job.source_entity_keys or []) if k != key]
            for source in sources:
                walk(source, level + 1)
            names = _names(db, case, sources)
            out.append({"merge_job_id": str(job.id), "into": key, "by": job.created_by,
                        "at": job.updated_at.isoformat() if getattr(job, "updated_at", None) else None,
                        "status": job.status,
                        "sources": [{"key": k, "name": names.get(k)} for k in sources]})

    walk(entity_key, 0)
    return out
