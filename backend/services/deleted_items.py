"""Deleted items of a case: everything a person deleted, in one list, restorable until the purge (lx-deletebin B, C).

Neil 2026-11-08: "create deleted items bin so any deleted work can be undone ... clear other leftovers".

Each kind keeps its deleted work where it already did, and this module lists, restores and removes it for good:

- ``evidence_file``: the row waits with ``deleted_at`` (services/evidence_casebin.py), its file stays on disk, its
  graph and search entries are hidden in place.
- ``evidence_folder``: the folder tree's rows are kept as one copy (``removed_records`` kind evidence_folder) and every
  file it held waits as an evidence_file of that item. Restore puts the folders back, then each file in its folder.
- ``note`` / ``finding`` / ``theory`` (workspace entries), ``task``, ``timeline_view``: rows with ``deleted_at``.
- ``removed_records`` kinds (dossier assessments, interviews, media, links, evidence links, entry links, pins,
  deadlines, chats, snapshots): a kept copy of the rows a hard delete removed.
- ``graph_entity``: an entity in the graph recycle bin (``graph_recycle_bin_items``).

Restore: the case owner or an admin (lx-casebin decision 1); a chat only by the person whose chat it is, or an admin.
Delete now (``purge``): the same people. A purge removes the rows, the graph and search entries and every file no
remaining row uses (services/casebin_purge.py ``purge_file``; EvidenceDBStorage.stored_paths_in_use keeps a file
any other row, deleted or not, still points at) and returns the counts.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from postgres import soft_delete
from postgres.models.user import User

ENTRY_KINDS = ("note", "finding", "theory")
ROW_KINDS = ENTRY_KINDS + ("task", "timeline_view")
RECORD_KINDS = ("dossier_assessment", "dossier_interview", "dossier_media", "dossier_link", "dossier_evidence_link",
                "entry_link", "evidence_pin", "case_deadline", "chat", "snapshot")
KIND_LABELS = {
    "evidence_file": "Evidence file", "evidence_folder": "Evidence folder", "note": "Note", "finding": "Finding",
    "theory": "Theory", "task": "Task", "timeline_view": "Timeline view", "dossier_assessment": "Dossier assessment",
    "dossier_interview": "Dossier interview", "dossier_media": "Dossier media", "dossier_link": "Dossier link",
    "dossier_evidence_link": "Dossier evidence link", "entry_link": "Casework link", "evidence_pin": "Pinned evidence",
    "case_deadline": "Deadline", "chat": "Chat", "snapshot": "Snapshot", "graph_entity": "Graph entity",
}
# Soft-deleted rows (entries, tasks, timeline views) and kept copies (removed_records) were kept forever before
# Deleted items were switched on; only those deleted from this moment on are purged 30 days later (the older ones
# stay restorable, as they were). Reverse: lower this date.
ROW_PURGE_FROM = datetime(2026, 11, 8, tzinfo=timezone.utc)


class DeletedItemError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def retention_days() -> int:
    from services.evidence_casebin import DELETED_RETENTION_DAYS
    return DELETED_RETENTION_DAYS


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _item(kind, item_id, label, deleted_at, deleted_by, *, detail=None, can_restore=True, purge=True, **extra):
    deleted_at = _aware(deleted_at)
    now = datetime.now(timezone.utc)
    purge_at = deleted_at + timedelta(days=retention_days()) if (deleted_at and purge) else None
    return dict(kind=kind, kind_label=KIND_LABELS.get(kind, kind), id=str(item_id), label=label or KIND_LABELS.get(kind),
                deleted_at=deleted_at.isoformat() if deleted_at else None, deleted_by=deleted_by, detail=detail,
                purge_at=purge_at.isoformat() if purge_at else None,
                days_left=max(0, (purge_at - now).days) if purge_at else None, can_restore=can_restore, **extra)


def _is_admin(user) -> bool:
    from services.case_service import is_super_admin
    return bool(is_super_admin(user))


def can_manage(db: Session, case_id, user) -> bool:
    """Restore and Delete now: the case owner or an admin."""
    from services.evidence_casebin import can_restore
    return can_restore(db, uuid.UUID(str(case_id)), user)


def _people(db, ids) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: dict(id=str(u.id), name=u.name, email=u.email) for u in db.query(User).filter(User.id.in_(ids))}


def list_items(db: Session, case_id, user) -> dict[str, Any]:
    """Every deleted item of the case this person may see, newest first."""
    from postgres.models.graph_recycle_bin import GraphRecycleBinItem
    from postgres.models.removed_record import RemovedRecord
    from postgres.models.timeline_view import TimelineView
    from postgres.models.work import CaseTask
    from postgres.models.workspace_entry import WorkspaceEntry
    from services import evidence_casebin
    case_uuid = uuid.UUID(str(case_id))
    manage = can_manage(db, case_uuid, user)
    items = []
    records = list(db.scalars(select(RemovedRecord).where(
        RemovedRecord.case_id == case_uuid, RemovedRecord.restored_at.is_(None),
        RemovedRecord.kind.in_(RECORD_KINDS + ("evidence_folder",))).order_by(RemovedRecord.removed_at.desc())))
    folder_items = {str(r.id): r for r in records if r.kind == "evidence_folder"}
    files = evidence_casebin.list_deleted(db, case_uuid)
    with soft_delete.showing_deleted(db):
        from postgres.models.evidence import EvidenceFile
        states = {str(i): (s or {}) for i, s in db.query(EvidenceFile.id, EvidenceFile.deleted_state).filter(
            EvidenceFile.case_id == case_uuid, EvidenceFile.deleted_at.is_not(None))}
    in_folder: dict[str, list] = {}
    for f in files:
        holder = states.get(f["id"], {}).get("folder_item_id")
        if holder in folder_items:
            in_folder.setdefault(holder, []).append(f)
            continue
        items.append(_item("evidence_file", f["id"], f["filename"], datetime.fromisoformat(f["deleted_at"]),
                           f["deleted_by"], can_restore=manage, size=f["size"],
                           detail=f"{f['holds']['text_chunks']} text passages, "
                                  f"{f['holds']['entities_only_in_this_file']} entities found only in it"))
    people = _people(db, [r.removed_by_user_id for r in records])
    for r in records:
        who = people.get(r.removed_by_user_id) or (dict(id=None, name=r.removed_by, email=r.removed_by)
                                                    if r.removed_by else None)
        if r.kind == "evidence_folder":
            held = in_folder.get(str(r.id), [])
            folders = len((r.data or {}).get("rows") or [])
            items.append(_item("evidence_folder", r.id, r.label, r.removed_at, who, can_restore=manage,
                               files=len(held), size=sum(f["size"] for f in held),
                               detail=f"{len(held):,} files in {folders:,} folder{'s' if folders != 1 else ''}"))
            continue
        if r.kind in ("chat", "snapshot"):
            if not _private_to(r, user):
                continue  # private to the person whose chat or snapshot it is
            detail = (f"{len(r.data.get('rows') or []) - 1} messages" if r.kind == "chat" else None)
            items.append(_item(r.kind, r.id, r.label, r.removed_at, who, can_restore=True, detail=detail,
                               purge=_aware(r.removed_at) >= ROW_PURGE_FROM))
            continue
        items.append(_item(r.kind, r.id, r.label, r.removed_at, who, can_restore=manage,
                           detail=f"{len((r.data or {}).get('rows') or []):,} kept rows",
                           purge=_aware(r.removed_at) >= ROW_PURGE_FROM))
    entries = list(db.scalars(select(WorkspaceEntry).where(WorkspaceEntry.case_id == case_uuid,
                                                         WorkspaceEntry.deleted_at.is_not(None))))
    tasks = list(db.scalars(select(CaseTask).where(CaseTask.case_id == case_uuid, CaseTask.deleted_at.is_not(None))))
    views = list(db.scalars(select(TimelineView).where(TimelineView.case_id == case_uuid,
                                                       TimelineView.deleted_at.is_not(None))))
    people = _people(db, [e.deleted_by_user_id for e in entries] + [getattr(t, "deleted_by_user_id", None)
                                                                     for t in tasks])
    for e in entries:
        items.append(_item(e.entry_type, e.id, e.title, e.deleted_at, people.get(e.deleted_by_user_id),
                           can_restore=manage, purge=_aware(e.deleted_at) >= ROW_PURGE_FROM))
    for t in tasks:
        items.append(_item("task", t.id, t.title, t.deleted_at, people.get(getattr(t, "deleted_by_user_id", None)),
                           can_restore=manage, purge=_aware(t.deleted_at) >= ROW_PURGE_FROM))
    for v in views:
        items.append(_item("timeline_view", v.id, v.title, v.deleted_at,
                           dict(id=None, name=v.owner_name, email=None) if v.owner_name else None,
                           can_restore=manage, purge=_aware(v.deleted_at) >= ROW_PURGE_FROM))
    for g in db.scalars(select(GraphRecycleBinItem).where(GraphRecycleBinItem.case_id == case_uuid,
                                                         GraphRecycleBinItem.status == "active")):
        items.append(_item("graph_entity", g.recycle_key, g.original_name or g.original_key, g.deleted_at,
                           dict(id=None, name=g.deleted_by, email=g.deleted_by) if g.deleted_by else None,
                           can_restore=manage, purge=False,
                           detail=f"{g.original_type or 'Entity'} · {g.relationship_count} relationships · "
                                  f"{g.reason}"))
    items.sort(key=lambda i: i["deleted_at"] or "", reverse=True)
    return dict(enabled=soft_delete.enabled(), items=items, retention_days=retention_days(), can_manage=manage)


# ------------------------------------------------------------------------------------------------------- restore


def _record(db, case_uuid, item_id, kinds):
    from postgres.models.removed_record import RemovedRecord
    try:
        record = db.get(RemovedRecord, uuid.UUID(str(item_id)))
    except ValueError:
        record = None
    if record is None or record.case_id != case_uuid or record.kind not in kinds:
        raise DeletedItemError("That deleted item was not found.", 404)
    if record.restored_at is not None:
        raise DeletedItemError("This item was already restored.", 409)
    return record


def _allowed(db, case_uuid, user, kind, record=None):
    if kind in ("chat", "snapshot"):
        if _private_to(record, user):
            return
        raise DeletedItemError(f"Only the person whose {kind} it is, or an admin, can restore or remove it.", 403)
    if not can_manage(db, case_uuid, user):
        raise DeletedItemError("Only the case owner or an admin can restore or remove deleted items.", 403)


def _row(db, kind, case_uuid, item_id):
    from postgres.models.timeline_view import TimelineView
    from postgres.models.work import CaseTask
    from postgres.models.workspace_entry import WorkspaceEntry
    model = WorkspaceEntry if kind in ENTRY_KINDS else CaseTask if kind == "task" else TimelineView
    try:
        row = db.get(model, uuid.UUID(str(item_id)))
    except ValueError:
        row = None
    if row is None or row.case_id != case_uuid or (kind in ENTRY_KINDS and row.entry_type != kind):
        raise DeletedItemError("That deleted item was not found.", 404)
    if row.deleted_at is None:
        raise DeletedItemError("This item is not in Deleted items.", 409)
    return row


def _folder_files(db, record) -> list[str]:
    """The files still waiting as part of this folder item: not restored on their own since, not deleted again on
    their own (that is an item of its own with its own 30 days), not purged."""
    from postgres.models.evidence import EvidenceFile
    ids = [uuid.UUID(i) for i in (record.data or {}).get("file_ids") or []]
    if not ids:
        return []
    with soft_delete.showing_deleted(db):
        rows = db.query(EvidenceFile.id, EvidenceFile.deleted_at, EvidenceFile.deleted_state).filter(
            EvidenceFile.id.in_(ids)).all()
    return sorted(str(i) for i, at, state in rows
                  if at is not None and (state or {}).get("folder_item_id") == str(record.id))


def _graphless(state: dict) -> bool:
    """A deleted file whose delete hid nothing in the graph (no Document node, no entities): restore and purge
    need no graph call for it."""
    return not state.get("doc_key") and not state.get("hidden_nodes") and not state.get("exclusive_entities")


def _restore_folder_files(db, case_uuid, record, user) -> tuple[int, int]:
    """Restore the folder item's files: graphless ones together in one transaction (chunks put back in one call),
    the others one by one through evidence_casebin.restore_file. Returns (restored, not restored)."""
    from postgres.models.evidence import EvidenceFile, EvidenceFolder
    from services import activity_trail, evidence_casebin
    ids = _folder_files(db, record)
    restored = failed = 0
    with soft_delete.showing_deleted(db):
        rows = db.query(EvidenceFile).filter(EvidenceFile.id.in_([uuid.UUID(i) for i in ids])).all() if ids else []
    folders = {f.id for f in db.query(EvidenceFolder.id).filter(EvidenceFolder.case_id == case_uuid)}
    quick = [r for r in rows if _graphless(r.deleted_state or {}) and r.source_type != "phone_file"]
    slow = [r for r in rows if r not in quick]
    chunk_states: dict = {}
    for r in quick:
        state = r.deleted_state or {}
        chunk_states.update(state.get("chunk_states") or {})
        folder_id = uuid.UUID(state["folder_id"]) if state.get("folder_id") else None
        if folder_id in folders and r.folder_id is None:
            r.folder_id = folder_id
        deleted_at, deleted_by = r.deleted_at, r.deleted_by_user_id
        r.deleted_at = r.deleted_by_user_id = r.deleted_state = None
        activity_trail.record("evidence_restored", db=db, user=user, case_id=case_uuid, details=dict(
            evidence_id=str(r.id), filename=r.original_filename, deleted_at=_aware(deleted_at).isoformat(),
            deleted_by_user_id=str(deleted_by) if deleted_by else None, restored_graph_nodes=0,
            restored_graph_relationships=0, merged_entities=[], restored_chunks=len(state.get("chunk_states") or {}),
            with_folder=str(record.id)))
        restored += 1
    if chunk_states:
        vdb = evidence_casebin._vector_db()
        if vdb is not None:
            evidence_casebin.restore_chunks(vdb, chunk_states)
    db.commit()
    soft_delete.forget()
    for r in slow:
        try:
            evidence_casebin.restore_file(db, case_uuid, str(r.id), user)
            restored += 1
        except (evidence_casebin.EvidenceNotDeleted, evidence_casebin.EvidenceNotFound):
            db.rollback()
            failed += 1
    return restored, failed


def _purge_folder_files(db, record, engine_delete=None) -> dict:
    """Purge the folder item's files: graphless ones together (one search delete, one shared-file check, one
    commit), the others one by one through casebin_purge.purge_file. A file another row still uses stays."""
    from pathlib import Path
    from postgres.models.evidence import EvidenceFile
    from services import activity_trail, evidence_casebin
    from services.casebin_purge import _engine_delete, purge_file
    from services.evidence_db_storage import EvidenceDBStorage
    counts: dict = {}
    ids = _folder_files(db, record)
    with soft_delete.showing_deleted(db):
        rows = db.query(EvidenceFile).filter(EvidenceFile.id.in_([uuid.UUID(i) for i in ids])).all() if ids else []
    quick = [r for r in rows if _graphless(r.deleted_state or {})]
    slow = [r for r in rows if r not in quick]
    for r in slow:
        try:
            _add(counts, _file_counts(purge_file(db, r.id, engine_delete=engine_delete)))
        except evidence_casebin.EvidenceNotDeleted:
            db.rollback()
    if not quick:
        return counts
    chunk_ids = sorted({c for r in quick for c in ((r.deleted_state or {}).get("chunk_states") or {})})
    vdb = evidence_casebin._vector_db()
    if vdb is not None:
        known = set(chunk_ids)
        known.update(c for ids_ in evidence_casebin._chunk_owners(vdb, case_id=str(record.case_id), records=quick,
                                                                  doc_keys={}).values() for c in ids_)
        known = sorted(known)
        for start in range(0, len(known), 1000):
            vdb.chunk_collection.delete(ids=known[start:start + 1000])
        counts["search_cleaned"] = counts.get("search_cleaned", 0) + len(quick)
    quick_ids = [r.id for r in quick]
    paths = [r.stored_path for r in quick if r.stored_path]
    in_use = set()
    for start in range(0, len(paths), 1000):
        in_use |= EvidenceDBStorage.stored_paths_in_use(db, paths[start:start + 1000], quick_ids)
    from routers.evidence import _resolve_stored_path
    removed_paths = set()
    for r in quick:
        details = dict(evidence_id=str(r.id), filename=r.original_filename, size=r.size, sha256=r.sha256,
                       deleted_at=_aware(r.deleted_at).isoformat(), with_folder=str(record.id),
                       deleted_by_user_id=str(r.deleted_by_user_id) if r.deleted_by_user_id else None)
        if r.stored_path and EvidenceDBStorage.keeps_file_on_delete(r.source_type):
            details["file_kept_production"] = True
        elif r.stored_path and r.stored_path in in_use:
            details["file_kept_shared"] = True
        elif r.stored_path and r.stored_path not in removed_paths:
            path = _resolve_stored_path(r.stored_path) or Path(r.stored_path)
            if path.exists():
                try:
                    path.unlink()
                    details["file_deleted"] = True
                    removed_paths.add(r.stored_path)
                except OSError as exc:
                    details["file_error"] = str(exc)[:200]
        if r.engine_job_id:
            try:
                (engine_delete or _engine_delete)(str(r.case_id), r.engine_job_id)
                details["engine_copy_removed"] = True
            except Exception as exc:
                details["engine_copy_error"] = str(exc)[:200]
        _add(counts, _file_counts(details))
        activity_trail.record("evidence_purged", db=db, system=True, case_id=r.case_id, details=details)
        db.delete(r)
    db.commit()
    soft_delete.forget()
    return counts


def _owner_of(record) -> tuple[str | None, str | None]:
    """(owner user id, owner username) of a private kept copy: a chat or a saved snapshot."""
    values = ((record.data or {}).get("rows") or [{}])[0].get("values", {})
    return values.get("owner_user_id"), values.get("owner")


def _private_to(record, user) -> bool:
    """A chat or a snapshot is seen, restored and removed only by its owner (or an admin)."""
    if _is_admin(user):
        return True
    owner_id, owner_name = _owner_of(record)
    if record.kind == "chat":
        return str(owner_id) == str(user.id)
    return owner_name is not None and owner_name in {getattr(user, "email", None), getattr(user, "name", None)}


def restore(db: Session, case_id, kind: str, item_id: str, user) -> dict[str, Any]:
    """Put a deleted item back exactly as it was, with everything that hung off it."""
    from services import activity_trail, evidence_casebin, removed_records
    case_uuid = uuid.UUID(str(case_id))
    out: dict[str, Any] = dict(kind=kind, id=str(item_id), restored=True)
    if kind == "evidence_file":
        _allowed(db, case_uuid, user, kind)
        return dict(out, **evidence_casebin.restore_file(db, case_uuid, item_id, user))
    if kind == "evidence_folder":
        record = _record(db, case_uuid, item_id, ("evidence_folder",))
        _allowed(db, case_uuid, user, kind)
        try:
            removed_records.restore(db, record, user=user)
        except removed_records.RemovedRecordError as exc:
            db.rollback()
            raise DeletedItemError(str(exc).replace("what it belonged to", "a folder of that name or its parent"),
                                   exc.status_code) from exc
        activity_trail.record("deleted_item_restored", db=db, user=user, case_id=case_uuid, details=dict(
            kind=kind, id=str(record.id), label=record.label, folders=len(record.data.get("rows") or [])))
        db.commit()
        restored, failed = _restore_folder_files(db, case_uuid, record, user)
        return dict(out, label=record.label, folders=len(record.data.get("rows") or []), files=restored,
                    files_not_restored=failed)
    if kind in RECORD_KINDS:
        record = _record(db, case_uuid, item_id, RECORD_KINDS)
        if record.kind != kind:
            raise DeletedItemError("That deleted item was not found.", 404)
        _allowed(db, case_uuid, user, kind, record)
        try:
            removed_records.restore(db, record, user=user)
        except removed_records.RemovedRecordError as exc:
            db.rollback()
            raise DeletedItemError(str(exc), exc.status_code) from exc
        if kind == "case_deadline" and record.data.get("linked_task_ids"):
            from postgres.models.work import CaseTask
            db.query(CaseTask).filter(CaseTask.id.in_([uuid.UUID(t) for t in record.data["linked_task_ids"]]),
                                      CaseTask.case_id == case_uuid, CaseTask.deadline_id.is_(None)).update(
                {CaseTask.deadline_id: uuid.UUID(record.subject_id)}, synchronize_session=False)
        activity_trail.record("deleted_item_restored", db=db, user=user, case_id=case_uuid, details=dict(
            kind=kind, id=str(record.id), label=record.label, rows=len(record.data.get("rows") or [])))
        db.commit()
        return dict(out, label=record.label, rows=len(record.data.get("rows") or []))
    if kind in ROW_KINDS:
        _allowed(db, case_uuid, user, kind)
        row = _row(db, kind, case_uuid, item_id)
        if kind in ENTRY_KINDS:
            from services.workspace_entry_service import restore_entry
            restore_entry(db, case_id=case_uuid, entry_id=row.id, current_user=user, expected_version=row.version)
        elif kind == "task":
            from services.work_service import restore_task
            restore_task(db, case_id=case_uuid, task_id=row.id, user=user)
        else:
            row.deleted_at = None
        activity_trail.record("deleted_item_restored", db=db, user=user, case_id=case_uuid,
                              details=dict(kind=kind, id=str(row.id), label=getattr(row, "title", None)))
        db.commit()
        return dict(out, label=getattr(row, "title", None))
    if kind == "graph_entity":
        _allowed(db, case_uuid, user, kind)
        from services.neo4j_service import neo4j_service
        try:
            result = neo4j_service.restore_recycled_entity(item_id, str(case_uuid), db=db, restored_by=user.email)
        except ValueError as exc:
            db.rollback()
            raise DeletedItemError(str(exc), 409 if "already exists" in str(exc) else 404) from exc
        restored_key = (result.get("restored_entity") or {}).get("key")
        if restored_key:  # as the graph recycle-bin route does (routers/graph.py restore_recycled_entity)
            from services.dossier_service import restore_dossier_after_entity_restore
            from services.significant_service import restore_significant_entity_after_restore
            restore_significant_entity_after_restore(db, case_id=case_uuid, entity_key=restored_key)
            restore_dossier_after_entity_restore(db, case_id=case_uuid, entity_key=restored_key)
        activity_trail.record("deleted_item_restored", db=db, user=user, case_id=case_uuid,
                              details=dict(kind=kind, id=str(item_id)), commit=True)
        return dict(out, result=result)
    raise DeletedItemError(f"Unknown kind of deleted item: {kind}", 404)


# --------------------------------------------------------------------------------------------------------- purge


def _file_counts(details: dict) -> dict:
    return dict(rows_removed=1, files_removed=int(bool(details.get("file_deleted"))),
                files_kept_shared=int(bool(details.get("file_kept_shared"))),
                files_kept_production=int(bool(details.get("file_kept_production"))),
                graph_documents_removed=int(bool(details.get("document_deleted"))),
                graph_entities_removed=len(details.get("exclusive_entities_recycled") or []),
                search_cleaned=int(bool(details.get("chromadb_cleaned"))),
                bytes_on_disk_freed=int(details.get("size") or 0) if details.get("file_deleted") else 0)


def _add(total: dict, part: dict) -> dict:
    for key, value in part.items():
        total[key] = total.get(key, 0) + value
    return total


def purge(db: Session, case_id, kind: str, item_id: str, user, *, system: bool = False,
          engine_delete=None) -> dict[str, Any]:
    """Remove a deleted item for good now and return what went: rows, files (and files kept because another row
    still uses them), graph and search entries. ``system``: the 30-day purge (no person)."""
    from services import activity_trail
    from services.casebin_purge import purge_file
    case_uuid = uuid.UUID(str(case_id))
    counts: dict[str, int] = {}
    label = None
    if kind == "evidence_file":
        if not system:
            _allowed(db, case_uuid, user, kind)
        with soft_delete.showing_deleted(db):
            from postgres.models.evidence import EvidenceFile
            try:
                record = db.get(EvidenceFile, uuid.UUID(str(item_id)))
            except ValueError:
                record = None
            if record is None or record.case_id != case_uuid or record.deleted_at is None:
                raise DeletedItemError("That deleted file was not found in Deleted items.", 404)
            label = record.original_filename
        _add(counts, _file_counts(purge_file(db, record.id, engine_delete=engine_delete)))
    elif kind == "evidence_folder":
        record = _record(db, case_uuid, item_id, ("evidence_folder",))
        if not system:
            _allowed(db, case_uuid, user, kind)
        label = record.label
        _add(counts, _purge_folder_files(db, record, engine_delete=engine_delete))
        record = _record(db, case_uuid, item_id, ("evidence_folder",))
        _add(counts, dict(folders_removed=len(record.data.get("rows") or [])))
        db.delete(record)
    elif kind in RECORD_KINDS:
        record = _record(db, case_uuid, item_id, RECORD_KINDS)
        if record.kind != kind:
            raise DeletedItemError("That deleted item was not found.", 404)
        if not system:
            _allowed(db, case_uuid, user, kind, record)
        label = record.label
        _add(counts, dict(rows_removed=len(record.data.get("rows") or [])))
        db.delete(record)  # the rows themselves went at the delete; the kept copy is all that was left
    elif kind in ROW_KINDS:
        if not system:
            _allowed(db, case_uuid, user, kind)
        row = _row(db, kind, case_uuid, item_id)
        label = getattr(row, "title", None)
        _add(counts, dict(rows_removed=1))
        db.delete(row)  # its revisions, links and events go with it (ON DELETE CASCADE)
    elif kind == "graph_entity":
        if not system:
            _allowed(db, case_uuid, user, kind)
        from services.neo4j_service import neo4j_service
        try:
            neo4j_service.permanently_delete_recycled(item_id, str(case_uuid), db=db,
                                                      purged_by=getattr(user, "email", None) or "deleted-items")
        except ValueError as exc:
            db.rollback()
            raise DeletedItemError(str(exc), 404) from exc
        label = item_id
        _add(counts, dict(graph_entities_removed=1))
    else:
        raise DeletedItemError(f"Unknown kind of deleted item: {kind}", 404)
    activity_trail.record("deleted_item_purged", db=db, user=None if system else user, system=system,
                          case_id=case_uuid, details=dict(kind=kind, id=str(item_id), label=label, **counts))
    db.commit()
    soft_delete.forget()
    return dict(kind=kind, id=str(item_id), label=label, purged=True, counts=counts)


def purge_due_rows(db: Session, cutoff: datetime, *, engine_delete=None) -> list[dict]:
    """The 30-day purge of the kinds above other than cases and single evidence files (casebin_purge does those):
    folders whose files are all gone, kept copies, and soft-deleted rows deleted since ROW_PURGE_FROM."""
    from postgres.models.removed_record import RemovedRecord
    from postgres.models.timeline_view import TimelineView
    from postgres.models.work import CaseTask
    from postgres.models.workspace_entry import WorkspaceEntry
    due = [(r.case_id, r.kind, str(r.id)) for r in db.scalars(select(RemovedRecord).where(
        RemovedRecord.restored_at.is_(None), RemovedRecord.removed_at < cutoff, RemovedRecord.case_id.is_not(None),
        RemovedRecord.removed_at >= ROW_PURGE_FROM,
        RemovedRecord.kind.in_(RECORD_KINDS + ("evidence_folder",))))]
    for model, kind_of in ((WorkspaceEntry, lambda r: r.entry_type), (CaseTask, lambda r: "task"),
                           (TimelineView, lambda r: "timeline_view")):
        for r in db.scalars(select(model).where(model.deleted_at.is_not(None), model.deleted_at < cutoff,
                                                model.deleted_at >= ROW_PURGE_FROM)):
            due.append((r.case_id, kind_of(r), str(r.id)))
    db.commit()
    out = []
    for case_id, kind, item_id in due:
        try:
            out.append(purge(db, case_id, kind, item_id, None, system=True, engine_delete=engine_delete))
        except Exception:
            db.rollback()
            import logging
            logging.getLogger(__name__).exception("Deleted items: purge of %s %s failed; it stays", kind, item_id)
    return out
