"""Deleted items for evidence files: delete, restore, list and purge (lx-casebin item C).

Deleting a file moves it to Deleted items for ``DELETED_RETENTION_DAYS``. Nothing is removed:

- the evidence row stays, with ``deleted_at``; every database read hides it and every row that points at it
  (postgres/soft_delete.py);
- the file on disk stays where it is;
- its Document node and the entities found only in it stay in Neo4j, hidden in place: their ``case_id`` becomes
  ``deleted-item:<file id>`` and their labels become ``DeletedItem`` (originals kept on the node), and the
  ``case_id`` of every relationship touching them is changed the same way. Every graph query is scoped by case and
  label, so nothing reads them; a restore puts back exactly the labels, properties and relationships (no copy, no
  type conversion, same node count);
- its ChromaDB chunks stay, with ``ingestion_state`` set to ``deleted`` (search already skips every state but active),
  and the entity vectors stay (an entity search reads the entity from Neo4j, where it is hidden).

A restore reverses each step. The purge (services/casebin_purge.py) first reverses the hiding, then runs the delete
used before Deleted items existed (``remove_for_good``): exclusive entities to the graph recycle bin, the Document
node, chunks and entity vectors removed, the file unlinked unless shared or a phone production, the evidence engine's
copy removed, the row deleted.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from postgres import soft_delete
from postgres.models.evidence import EvidenceFile
from postgres.models.user import User

logger = logging.getLogger(__name__)

DELETED_RETENTION_DAYS = 30
MARKER_PREFIX = "deleted-item:"
HIDDEN_LABEL = "DeletedItem"
# Nodes never hidden with a file, as the graph recycle bin never takes them (services/neo4j/entity_service.py).
_NEVER_HIDDEN = ["Case", "RecycleBin", "RecycleBinItem", HIDDEN_LABEL]


class EvidenceNotFound(Exception):
    pass


class EvidenceNotDeleted(Exception):
    pass


class EvidenceAddedAgain(EvidenceNotDeleted):
    """The same phone file was added to Evidence again while this row waited in Deleted items."""


class EvidenceRestoreDenied(Exception):
    pass


def marker(file_id) -> str:
    return MARKER_PREFIX + str(file_id)


# --------------------------------------------------------------------------------------------------------- graph


def hide_graph(graph_session, *, case_id: str, file_id, doc_key: str | None, entity_keys) -> dict:
    """Hide the Document node and the given entities in place. Returns {"nodes": n, "relationships": m}."""
    fid = str(file_id)
    entity_keys = [k for k in (entity_keys or []) if k]

    def work(tx):
        nodes = 0
        if doc_key:
            nodes += tx.run(
                "MATCH (n:Document {key: $key, case_id: $case_id}) WITH n, labels(n) AS ls "
                "SET n.casebin_case_id = n.case_id, n.casebin_labels = ls, n.casebin_file_id = $fid, "
                "n.case_id = $marker REMOVE n:$(ls) SET n:DeletedItem RETURN count(n) AS c",
                key=doc_key, case_id=case_id, fid=fid, marker=marker(fid)).single()["c"]
        if entity_keys:
            nodes += tx.run(
                "MATCH (n {case_id: $case_id}) WHERE n.key IN $keys "
                "AND NONE(l IN labels(n) WHERE l IN $never OR l = 'Document') "
                "AND coalesce(n.system_node, false) <> true AND coalesce(n.financial_identity_managed, false) <> true "
                "WITH n, labels(n) AS ls "
                "SET n.casebin_case_id = n.case_id, n.casebin_labels = ls, n.casebin_file_id = $fid, "
                "n.case_id = $marker REMOVE n:$(ls) SET n:DeletedItem RETURN count(n) AS c",
                keys=entity_keys, case_id=case_id, fid=fid, marker=marker(fid), never=_NEVER_HIDDEN).single()["c"]
        rels = tx.run(
            "MATCH (n:DeletedItem {casebin_file_id: $fid})-[r]-() WITH DISTINCT r WHERE r.casebin_hidden IS NULL "
            "SET r.casebin_hidden = $fid, r.casebin_case_id = r.case_id, r.case_id = $marker RETURN count(r) AS c",
            fid=fid, marker=marker(fid)).single()["c"]
        return dict(nodes=nodes, relationships=rels)

    return graph_session.execute_write(work)


def restore_graph(graph_session, *, case_id: str, file_id) -> dict:
    """Put back what hide_graph hid for this file. A hidden entity whose key now exists again in the case (made
    since by another file) is merged into that entity: its relationships move across, the existing properties are
    kept. Returns {"nodes", "relationships", "merged"}."""
    fid = str(file_id)

    def work(tx):
        rels = tx.run(
            "MATCH (n:DeletedItem {casebin_file_id: $fid})-[r]-() WITH DISTINCT r WHERE r.casebin_hidden = $fid "
            "SET r.case_id = r.casebin_case_id REMOVE r.casebin_hidden, r.casebin_case_id RETURN count(r) AS c",
            fid=fid).single()["c"]
        # Relationships hidden by this file whose node was later hidden by another file are matched from either end.
        rels += tx.run(
            "MATCH ()-[r]-() WHERE r.casebin_hidden = $fid WITH DISTINCT r "
            "SET r.case_id = r.casebin_case_id REMOVE r.casebin_hidden, r.casebin_case_id RETURN count(r) AS c",
            fid=fid).single()["c"]
        # A hidden entity whose key exists again in the case (made since by another file): the live one wins.
        conflicts = {row["key"]: row["live"] for row in tx.run(
            "MATCH (h:DeletedItem {casebin_file_id: $fid}) MATCH (live {case_id: $case_id, key: h.key}) "
            "RETURN h.key AS key, elementId(live) AS live", fid=fid, case_id=case_id)}
        nodes = tx.run(
            "MATCH (h:DeletedItem {casebin_file_id: $fid}) WITH h, h.casebin_labels AS ls "
            "SET h.case_id = h.casebin_case_id SET h:$(ls) REMOVE h:DeletedItem "
            "REMOVE h.casebin_case_id, h.casebin_labels, h.casebin_file_id RETURN count(h) AS c",
            fid=fid).single()["c"]
        merged = 0
        for key, live in conflicts.items():
            # mergeNodes keeps the first node's properties ('discard') and moves the others' relationships to it.
            merged += tx.run(
                "MATCH (live) WHERE elementId(live) = $live MATCH (n {case_id: $case_id, key: $key}) "
                "WHERE elementId(n) <> $live WITH live, collect(n) AS others WHERE size(others) > 0 "
                "CALL apoc.refactor.mergeNodes([live] + others, {properties: 'discard', mergeRels: false}) "
                "YIELD node RETURN count(node) AS c", live=live, case_id=case_id, key=key).single()["c"]
        return dict(nodes=nodes, relationships=rels, merged=merged, merged_keys=sorted(conflicts))

    return graph_session.execute_write(work)


def purge_graph(graph_session, *, case_id: str, file_id) -> dict:
    """Before a purge: put back what hide_graph hid for this file, except a hidden node whose key exists again in the
    case (a later upload made it, e.g. a corrected file under the same name). That one is the deleted file's own copy:
    it is removed with its relationships, and the live node is never touched. Returns
    {"removed_keys": [...], "nodes": restored nodes, "relationships": restored relationships}."""
    fid = str(file_id)

    def work(tx):
        return [row["key"] for row in tx.run(
            "MATCH (h:DeletedItem {casebin_file_id: $fid}) WHERE EXISTS { MATCH (live {case_id: $case_id}) "
            "WHERE live.key = h.key } WITH h, h.key AS key DETACH DELETE h RETURN key", fid=fid, case_id=case_id)]

    removed = sorted(set(graph_session.execute_write(work)))
    back = restore_graph(graph_session, case_id=case_id, file_id=file_id)
    return dict(removed_keys=removed, nodes=back["nodes"], relationships=back["relationships"])


def find_document_key(graph_session, filename: str, case_id: str):
    """The file's Document node, found as the delete always found it (services/neo4j/document_service.py)."""
    row = graph_session.run("MATCH (d:Document {case_id: $case_id}) WHERE d.name = $filename OR d.key = $filename "
                            "RETURN d.key AS key", filename=filename, case_id=case_id).single()
    return row["key"] if row else None


def find_exclusive_entities(graph_session, doc_key: str, case_id: str) -> list:
    """Entities mentioned only in this Document (same query as services/neo4j/document_service.py)."""
    return [dict(r) for r in graph_session.run(
        "MATCH (entity)-[:MENTIONED_IN]->(doc:Document {key: $doc_key, case_id: $case_id}) "
        "WHERE entity.case_id = $case_id WITH entity "
        "OPTIONAL MATCH (entity)-[:MENTIONED_IN]->(other:Document {case_id: $case_id}) WHERE other.key <> $doc_key "
        "WITH entity, count(other) AS other_doc_count WHERE other_doc_count = 0 "
        "RETURN DISTINCT entity.key AS key, entity.name AS name, labels(entity)[0] AS type",
        doc_key=doc_key, case_id=case_id)]


def case_graph_counts(graph_session, case_id: str) -> dict:
    """Nodes and relationships of the case as every graph screen sees them (for the delete/restore proof)."""
    row = graph_session.run(
        "MATCH (n {case_id: $case_id}) OPTIONAL MATCH (n)-[r]-() "
        "RETURN count(DISTINCT n) AS nodes, count(DISTINCT r) AS relationships", case_id=case_id).single()
    return dict(nodes=row["nodes"], relationships=row["relationships"])


def _graph_session():
    from services.neo4j.driver import driver
    return driver.session()


# -------------------------------------------------------------------------------------------------------- vectors


def _document_chunk_ids(vector_db, *, case_id, file_id, doc_key, file_name) -> list:
    selectors = [{"evidence_file_id": str(file_id)}, {"doc_id": str(file_id)}]
    if doc_key:
        selectors.extend(({"doc_key": doc_key}, {"doc_id": doc_key}))
    if file_name:
        selectors.extend(({"doc_id": file_name}, {"file_name": file_name}))
    ids = set()
    for selector in selectors:
        found = vector_db.chunk_collection.get(where={"$and": [{"case_id": case_id}, selector]}, include=[])
        ids.update(str(i) for i in (found.get("ids") or []))
    return sorted(ids)


def hide_chunks(vector_db, *, case_id, file_id, doc_key, file_name) -> dict:
    """Mark the file's chunks deleted; returns {chunk id: previous ingestion_state (None when it had none)}."""
    ids = _document_chunk_ids(vector_db, case_id=case_id, file_id=file_id, doc_key=doc_key, file_name=file_name)
    if not ids:
        return {}
    found = vector_db.chunk_collection.get(ids=ids, include=["metadatas"])
    previous, metadatas = {}, []
    for chunk_id, metadata in zip(found["ids"], found["metadatas"]):
        metadata = dict(metadata or {})
        previous[str(chunk_id)] = metadata.get("ingestion_state")
        metadata["ingestion_state"] = "deleted"
        metadatas.append(metadata)
    vector_db.chunk_collection.update(ids=list(found["ids"]), metadatas=metadatas)
    return previous


def restore_chunks(vector_db, previous: dict) -> int:
    """Put back each chunk's ingestion_state. One that had none gets "active", which search reads the same way
    (services/vector_db_service.py search_chunks accepts none, "" and "active")."""
    if not previous:
        return 0
    found = vector_db.chunk_collection.get(ids=list(previous), include=["metadatas"])
    metadatas = []
    for chunk_id, metadata in zip(found["ids"], found["metadatas"]):
        metadata = dict(metadata or {})
        metadata["ingestion_state"] = previous.get(str(chunk_id)) or "active"
        metadatas.append(metadata)
    if found["ids"]:
        vector_db.chunk_collection.update(ids=list(found["ids"]), metadatas=metadatas)
    return len(found["ids"])


def _vector_db():
    try:
        from services.vector_db_service import get_vector_db_service
        return get_vector_db_service()
    except Exception as exc:  # vector search disabled (no chromadb): nothing to hide or restore
        logger.warning("Deleted items: vector database unavailable: %s", exc)
        return None


# ---------------------------------------------------------------------------------------------------- operations


def _record(db: Session, case_id: UUID, evidence_id: str, *, deleted: bool | None) -> EvidenceFile:
    from services.evidence_db_storage import EvidenceDBStorage
    with soft_delete.showing_deleted(db):
        try:
            record = EvidenceDBStorage.get(db, UUID(evidence_id))
        except (ValueError, AttributeError):
            record = EvidenceDBStorage.get_by_legacy_id(db, evidence_id)
    if record is None or record.case_id != case_id:
        raise EvidenceNotFound("Evidence file not found")
    if deleted is True and record.deleted_at is None:
        raise EvidenceNotDeleted("This file is not in Deleted items")
    if deleted is False and record.deleted_at is not None:
        raise EvidenceNotFound("Evidence file not found")
    return record


def ledger_hold(db: Session, case_id, file_ids) -> str | None:
    """Why these files cannot go to Deleted items while Financial counts payments read from them, or None.

    A deleted file is hidden by its own rows, but the payments read from it hang off its statement source
    (financial_source_documents -> periods and transactions) and many ledger reads are hand-written SQL, so they
    would keep counting. A PDF is already held by services/financial/import_removal.py ``financial_hold`` until its
    imports are removed; this holds any other file type with admitted payments (none on live, 2026-11-04: all 2,765
    statement sources are PDFs), which has no Remove imports path. Rejected and superseded readings do not count in
    totals and do not hold."""
    from sqlalchemy import func, select
    from postgres.models.financial import FinancialSourceDocument as Source, FinancialTransaction as Transaction
    ids = [UUID(str(value)) for value in file_ids or []]
    if not ids:
        return None
    rows = db.execute(
        select(EvidenceFile.original_filename, func.count(Transaction.id))
        .join(Source, Source.evidence_file_id == EvidenceFile.id)
        .join(Transaction, Transaction.source_document_id == Source.id)
        .where(EvidenceFile.case_id == case_id, EvidenceFile.id.in_(ids), Source.status == "admitted",
               Transaction.ledger_status == "admitted")
        .group_by(EvidenceFile.original_filename)).all()
    held = [(name, count) for name, count in rows if not (name or "").lower().endswith(".pdf")]
    if not held:
        return None
    payments = sum(count for _, count in held)
    names = ", ".join(name for name, _ in held[:3]) + (f" and {len(held) - 3} more" if len(held) > 3 else "")
    return (f"{names}: {payments} payment{'s' if payments != 1 else ''} read from "
            f"{'it' if len(held) == 1 else 'them'} still count in this case's Financial totals, so "
            f"{'it' if len(held) == 1 else 'they'} cannot be moved to Deleted items. Nothing was deleted.")


def import_in_progress(db: Session, case_id, file_ids) -> list:
    """Names of open Financial imports still preparing one of these files. Such a file is not moved to Deleted
    items: the import would read it as missing and mark its entry failed (it is refused like a file still
    processing). Finish or remove the import first."""
    from postgres.models.financial_import_batches import FinancialImportBatch as Batch
    from services.financial.import_batches import TERMINAL_FILES
    ids = {str(i) for i in file_ids}
    held = []
    for batch in db.query(Batch).filter(Batch.case_id == case_id, Batch.status != "removed").all():
        for entry in batch.files or []:
            if ({entry.get("file_id"), entry.get("source_id")} & ids) and entry.get("status") not in TERMINAL_FILES:
                held.append(getattr(batch, "name", None) or str(batch.id))
                break
    return held


def delete_file(db: Session, record: EvidenceFile, user: User, *, delete_exclusive_entities: bool = True,
                graph_session=None, vector_db=None) -> dict:
    """Move one evidence file to Deleted items (the caller has checked access, processing and financial holds)."""
    from services import activity_trail
    case_id = str(record.case_id)
    filename = record.original_filename
    own_session = graph_session is None
    gs = graph_session or _graph_session()
    try:
        doc_key = find_document_key(gs, filename, case_id)
        exclusive = find_exclusive_entities(gs, doc_key, case_id) if (doc_key and delete_exclusive_entities) else []
        graph = hide_graph(gs, case_id=case_id, file_id=record.id, doc_key=doc_key,
                           entity_keys=[e["key"] for e in exclusive])
    finally:
        if own_session:
            gs.close()
    vdb = vector_db if vector_db is not None else _vector_db()
    chunks = {}
    try:
        if vdb is not None:
            chunks = hide_chunks(vdb, case_id=case_id, file_id=record.id, doc_key=doc_key, file_name=filename)
    except Exception:
        _undo_graph(case_id, record.id, graph_session)
        raise
    now = datetime.now(timezone.utc)
    record.deleted_at = now
    record.deleted_by_user_id = user.id
    record.deleted_state = dict(doc_key=doc_key, hidden_nodes=graph["nodes"],
                                hidden_relationships=graph["relationships"],
                                exclusive_entities=[dict(key=e["key"], name=e.get("name"), type=e.get("type"))
                                                    for e in exclusive],
                                delete_exclusive_entities=delete_exclusive_entities, chunk_states=chunks,
                                deleted_by_email=user.email)
    details = dict(evidence_id=str(record.id), filename=filename, size=record.size, sha256=record.sha256,
                   hidden_graph_nodes=graph["nodes"], hidden_graph_relationships=graph["relationships"],
                   hidden_chunks=len(chunks), purge_after=(now + timedelta(days=DELETED_RETENTION_DAYS)).isoformat())
    activity_trail.record("evidence_moved_to_deleted_items", db=db, user=user, case_id=record.case_id, details=details)
    try:
        db.commit()
    except Exception:
        db.rollback()
        _undo_graph(case_id, record.id, graph_session)
        if vdb is not None and chunks:
            restore_chunks(vdb, chunks)
        raise
    soft_delete.forget()
    return dict(evidence_id=str(record.id), filename=filename, deleted=True, restorable_days=DELETED_RETENTION_DAYS,
                hidden_graph_nodes=graph["nodes"], hidden_chunks=len(chunks),
                exclusive_entities_hidden=details["hidden_graph_nodes"] - (1 if doc_key else 0))


def _undo_graph(case_id, file_id, graph_session=None):
    own = graph_session is None
    gs = graph_session or _graph_session()
    try:
        restore_graph(gs, case_id=case_id, file_id=file_id)
    except Exception:
        logger.exception("Deleted items: could not put back the graph of %s after a failed delete", file_id)
    finally:
        if own:
            gs.close()


def can_restore(db: Session, case_id: UUID, user: User) -> bool:
    """The case owner or an admin restores a deleted file (lx-casebin decision 1)."""
    from services.case_service import is_super_admin
    from postgres.models.case import Case
    if is_super_admin(user):
        return True
    case = db.get(Case, case_id)
    return case is not None and case.owner_user_id == user.id


def restore_file(db: Session, case_id: UUID, evidence_id: str, user: User, *, graph_session=None,
                 vector_db=None) -> dict:
    from services import activity_trail
    record = _record(db, case_id, evidence_id, deleted=True)
    if not can_restore(db, case_id, user):
        raise EvidenceRestoreDenied("Only the case owner or an admin can restore a deleted file")
    if record.source_type == "phone_file" and record.source_ref and db.scalar(
            select(EvidenceFile.id).where(EvidenceFile.case_id == record.case_id,
                                          EvidenceFile.source_type == "phone_file",
                                          EvidenceFile.source_ref == record.source_ref)):
        # One live evidence row per phone file (uq_evidence_files_case_phone_file, live rows only).
        raise EvidenceAddedAgain(f"{record.original_filename} was added to Evidence again from the phone after it "
                                 "was deleted, so this copy cannot be restored. The file in Evidence is the same "
                                 "phone file.")
    state = record.deleted_state or {}
    own = graph_session is None
    gs = graph_session or _graph_session()
    try:
        graph = restore_graph(gs, case_id=str(case_id), file_id=record.id)
    finally:
        if own:
            gs.close()
    vdb = vector_db if vector_db is not None else _vector_db()
    chunks = restore_chunks(vdb, state.get("chunk_states") or {}) if vdb is not None else 0
    if state.get("folder_id") and record.folder_id is None:
        # Deleted with its folder: back into that folder when it exists again, else at the top of Evidence.
        from postgres.models.evidence import EvidenceFolder
        folder = db.get(EvidenceFolder, UUID(state["folder_id"]))
        if folder is not None and folder.case_id == record.case_id:
            record.folder_id = folder.id
    deleted_at, deleted_by = record.deleted_at, record.deleted_by_user_id
    record.deleted_at = None
    record.deleted_by_user_id = None
    record.deleted_state = None
    activity_trail.record("evidence_restored", db=db, user=user, case_id=case_id, details=dict(
        evidence_id=str(record.id), filename=record.original_filename, deleted_at=deleted_at.isoformat(),
        deleted_by_user_id=str(deleted_by) if deleted_by else None, restored_graph_nodes=graph["nodes"],
        restored_graph_relationships=graph["relationships"], merged_entities=graph["merged_keys"],
        restored_chunks=chunks))
    db.commit()
    soft_delete.forget()
    return dict(evidence_id=str(record.id), filename=record.original_filename, restored=True,
                graph_nodes=graph["nodes"], graph_relationships=graph["relationships"],
                merged_entities=graph["merged_keys"], chunks=chunks)


def list_deleted(db: Session, case_id: UUID) -> list[dict]:
    """The case's deleted files, newest first: who deleted each, when, what it holds, days left."""
    with soft_delete.showing_deleted(db):
        records = (db.query(EvidenceFile)
                   .filter(EvidenceFile.case_id == case_id, EvidenceFile.deleted_at.is_not(None))
                   .order_by(EvidenceFile.deleted_at.desc()).all())
        people = {u.id: u for u in db.query(User).filter(
            User.id.in_({r.deleted_by_user_id for r in records if r.deleted_by_user_id})).all()}
    now = datetime.now(timezone.utc)
    rows = []
    for r in records:
        purge_at = r.deleted_at + timedelta(days=DELETED_RETENTION_DAYS)
        state = r.deleted_state or {}
        who = people.get(r.deleted_by_user_id)
        rows.append(dict(
            id=str(r.id), filename=r.original_filename, size=int(r.size or 0), folder_id=str(r.folder_id) if r.folder_id else None,
            deleted_at=r.deleted_at.isoformat(), purge_at=purge_at.isoformat(),
            days_left=max(0, (purge_at - now).days),
            deleted_by=dict(id=str(who.id), name=who.name, email=who.email) if who else None,
            holds=dict(graph_nodes=state.get("hidden_nodes", 0), entities_only_in_this_file=len(state.get("exclusive_entities") or []),
                       text_chunks=len(state.get("chunk_states") or {})),
        ))
    return rows


def remove_for_good(db: Session, record: EvidenceFile, *, deleted_by_email: str | None,
                    delete_exclusive_entities: bool = True, known: dict | None = None) -> tuple:
    """The evidence delete used before Deleted items existed (routers/evidence.py at 8fe01c61), unchanged in what it
    removes: exclusive entities to the graph recycle bin, the Document node, the chunks and those entities' vectors,
    the file on disk unless it is a phone production or another row uses it. Returns (engine_job_id, result_info);
    the caller removes the engine copy and then the row.

    ``known`` (the 30-day purge): what the delete recorded, {"doc_key", "exclusive_entities", "chunk_ids"}. Then nothing
    is looked up by filename: another live file of the same name, uploaded while this one waited in Deleted items,
    keeps its Document node, its entities and its chunks."""
    from services.neo4j_service import neo4j_service
    from services.evidence_db_storage import EvidenceDBStorage
    case_id = str(record.case_id)
    filename = record.original_filename
    stored_path = record.stored_path
    result_info = {"evidence_id": str(record.id), "filename": filename, "file_deleted": False,
                   "document_deleted": False, "exclusive_entities_recycled": [], "chromadb_cleaned": False}
    doc_key = None
    try:
        if known is not None:
            doc_node = {"key": known["doc_key"]} if known.get("doc_key") else None
        else:
            doc_node = neo4j_service.find_document_node(filename, case_id)
        if doc_node:
            doc_key = doc_node["key"]
            if delete_exclusive_entities:
                exclusive = ([dict(e) for e in known.get("exclusive_entities") or []] if known is not None
                             else neo4j_service.find_exclusive_entities(doc_key, case_id))
                for entity in exclusive:
                    try:
                        neo4j_service.soft_delete_entity(node_key=entity["key"], case_id=case_id,
                                                         deleted_by=deleted_by_email,
                                                         reason=f"file_delete:{filename}", db=db)
                        result_info["exclusive_entities_recycled"].append(entity)
                    except Exception as e:
                        logger.warning("Failed to recycle entity %s: %s", entity["key"], e)
            neo4j_service.delete_node(doc_key, case_id=case_id)
            result_info["document_deleted"] = True
    except ValueError as e:
        logger.info("Neo4j document deletion: %s", e)
    except Exception as e:
        logger.warning("Neo4j cleanup error: %s", e)
    try:
        vector_db = _vector_db()
        if vector_db:
            if known is not None:
                ids = set(known.get("chunk_ids") or []) | set(_document_chunk_ids(
                    vector_db, case_id=case_id, file_id=record.id, doc_key=None, file_name=None))
                if ids:
                    vector_db.chunk_collection.delete(ids=sorted(ids))
            else:
                vector_db.delete_chunks_for_document(case_id=case_id, evidence_file_id=str(record.id),
                                                     doc_key=doc_key, file_name=filename)
            for entity in result_info["exclusive_entities_recycled"]:
                vector_db.delete_entity(entity["key"])
            result_info["chromadb_cleaned"] = True
    except Exception as e:
        logger.warning("ChromaDB cleanup error: %s", e)
    if stored_path and EvidenceDBStorage.keeps_file_on_delete(record.source_type):
        result_info["file_kept_production"] = True
    elif stored_path and EvidenceDBStorage.stored_paths_in_use(db, [stored_path], [record.id]):
        result_info["file_kept_shared"] = True
    elif stored_path:
        from routers.evidence import _resolve_stored_path
        file_path = _resolve_stored_path(stored_path) or Path(stored_path)
        if file_path.exists():
            try:
                file_path.unlink()
                result_info["file_deleted"] = True
            except Exception as e:
                logger.warning("Failed to delete physical file: %s", e)
    return record.engine_job_id, result_info
