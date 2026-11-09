"""Deleted items for all deleted work (lx-deletebin): a case owner deletes evidence folders; a deleted folder, its
files and other deleted work come back exactly on Restore; a file stays on disk until the purge; the purge removes
files no other row uses and keeps a shared one, and reports the counts. A real SQLite session; graph, vector store
and evidence engine faked."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import postgres.models  # noqa: F401 - every mapper
from postgres.base import Base
from postgres.models.case import Case
from postgres.models.case_membership import CaseMembership
from postgres.models.enums import CaseMembershipRole
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.removed_record import RemovedRecord
from postgres.models.user import User
from postgres.permissions import EDITOR_PERMISSIONS, clone_permissions

# The owner rights stored on memberships made before 2026-11-08 (no evidence.delete).
OLD_OWNER_PERMISSIONS = {"case": {"view": True, "edit": True, "delete": True},
                         "collaborators": {"invite": True, "remove": True}, "evidence": {"upload": True}}


@pytest.fixture(autouse=True)
def _deleted_items_on():
    with patch("config.DELETED_ITEMS_ENABLED", True):
        yield


def _tables():
    from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
    from postgres.models.financial_import_batches import FinancialImportBatch
    from postgres.models.activity_event import ActivityEvent
    from postgres.models.timeline_view import TimelineView
    from postgres.models.work import CaseTask
    from postgres.models.workspace_entry import (WorkspaceEntry, WorkspaceEntryEvent, WorkspaceEntryLink,
                                                 WorkspaceEntryRevision)
    from postgres.models.evidence_upload import EvidenceUploadGroup, EvidenceUploadSession
    return [EvidenceUploadGroup.__table__, EvidenceUploadSession.__table__, WorkspaceEntryRevision.__table__, WorkspaceEntryEvent.__table__, CaseTask.__table__, TimelineView.__table__, ActivityEvent.__table__, User.__table__, Case.__table__, CaseMembership.__table__, EvidenceFolder.__table__,
            EvidenceFile.__table__, RemovedRecord.__table__, FinancialImportBatch.__table__,
            FinancialSourceDocument.__table__, FinancialTransaction.__table__, WorkspaceEntry.__table__,
            WorkspaceEntryLink.__table__]


@pytest.fixture()
def world(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=_tables())
    # The graph recycle bin's snapshot column is Postgres JSONB only: a copy of the table with JSON for SQLite.
    from sqlalchemy import JSON, MetaData
    from postgres.models.graph_recycle_bin import GraphRecycleBinItem
    copy = MetaData()
    Case.__table__.to_metadata(copy)
    User.__table__.to_metadata(copy)
    recycle = GraphRecycleBinItem.__table__.to_metadata(copy)
    recycle.c.snapshot.type = JSON()
    copy.create_all(engine, tables=[recycle])
    db = Session(engine)
    owner = User(id=uuid.uuid4(), email="owner@x.test", name="Owner", password_hash="x", is_active=True)
    editor = User(id=uuid.uuid4(), email="editor@x.test", name="Editor", password_hash="x", is_active=True)
    db.add_all([owner, editor])
    db.flush()
    case = Case(id=uuid.uuid4(), title="Check case", created_by_user_id=owner.id, owner_user_id=owner.id)
    db.add(case)
    db.flush()
    db.add_all([
        CaseMembership(case_id=case.id, user_id=owner.id, membership_role=CaseMembershipRole.owner,
                       permissions=dict(OLD_OWNER_PERMISSIONS), added_by_user_id=owner.id),
        CaseMembership(case_id=case.id, user_id=editor.id, membership_role=CaseMembershipRole.collaborator,
                       permissions=clone_permissions(EDITOR_PERMISSIONS), added_by_user_id=owner.id)])
    top = EvidenceFolder(id=uuid.uuid4(), case_id=case.id, name="uploadfollow-2000")
    db.add(top)
    db.flush()
    inner = EvidenceFolder(id=uuid.uuid4(), case_id=case.id, name="d01", parent_id=top.id)
    db.add(inner)
    db.flush()
    paths = {}
    for name in ("a.bin", "b.bin", "shared.bin"):
        paths[name] = tmp_path / name
        paths[name].write_bytes(b"x" * 10)
    files = {}
    for name, folder in (("a.bin", top), ("b.bin", inner), ("shared.bin", inner)):
        files[name] = EvidenceFile(id=uuid.uuid4(), case_id=case.id, folder_id=folder.id, original_filename=name,
                                   stored_path=str(paths[name]), sha256=name[0] * 64, status="processed", size=10)
        db.add(files[name])
    # Another live row (elsewhere in the case) points at the same file on disk as shared.bin.
    db.add(EvidenceFile(id=uuid.uuid4(), case_id=case.id, original_filename="shared-copy.bin",
                        stored_path=str(paths["shared.bin"]), sha256="s" * 64, status="processed", size=10))
    db.commit()
    yield dict(db=db, case=case, owner=owner, editor=editor, top=top, inner=inner, files=files, paths=paths)
    db.close()
    engine.dispose()


def _fakes():
    return [patch("services.evidence_casebin._graph_session", return_value=MagicMock()),
            patch("services.evidence_casebin.find_document_key", return_value=None),
            patch("services.evidence_casebin.hide_graph", return_value={"nodes": 0, "relationships": 0}),
            patch("services.evidence_casebin.restore_graph",
                  return_value={"nodes": 0, "relationships": 0, "merged_keys": []}),
            patch("services.evidence_casebin.purge_graph",
                  return_value={"removed_keys": [], "nodes": 0, "relationships": 0}),
            patch("services.evidence_casebin._vector_db", return_value=None),
            patch("services.neo4j_service.neo4j_service", MagicMock())]


class _Fakes:
    def __enter__(self):
        self.patches = _fakes()
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self.patches):
            p.stop()


def _delete_folder(w, user):
    from routers import evidence_folders
    with _Fakes():
        return evidence_folders.delete_folder(folder_id=str(w["top"].id), case_id=str(w["case"].id),
                                              current_user=user, db=w["db"])


def _folder_rows(db, case_id):
    return sorted((f.id, f.name, f.parent_id) for f in db.query(EvidenceFolder).filter(EvidenceFolder.case_id == case_id))


def _file_rows(db, case_id):
    return sorted((f.id, f.folder_id, f.stored_path, f.deleted_at is None)
                  for f in db.query(EvidenceFile).filter(EvidenceFile.case_id == case_id))


# ----------------------------------------------------------------------------------------------------------- A


def test_case_owner_has_evidence_delete_even_on_a_membership_stored_before_it_existed(world):
    from services.case_service import has_permission
    db = world["db"]
    owner_m = db.query(CaseMembership).filter(CaseMembership.user_id == world["owner"].id).one()
    editor_m = db.query(CaseMembership).filter(CaseMembership.user_id == world["editor"].id).one()
    assert "delete" not in owner_m.permissions["evidence"]
    assert has_permission(owner_m, "evidence", "delete") is True
    assert has_permission(editor_m, "evidence", "delete") is False  # collaborators keep what they were given


def test_case_owner_deletes_a_folder_and_a_collaborator_without_the_right_is_refused(world):
    with pytest.raises(HTTPException) as refused:
        _delete_folder(world, world["editor"])
    assert refused.value.status_code == 403
    out = _delete_folder(world, world["owner"])
    assert out["deleted_files"] == 3 and out["deleted_folders"] == 2 and out["deleted_item_id"]


# ----------------------------------------------------------------------------------------------------------- B


def test_folder_delete_then_restore_returns_the_folders_and_files_unchanged(world):
    from services import deleted_items
    db, case_id = world["db"], world["case"].id
    folders_before, files_before = _folder_rows(db, case_id), _file_rows(db, case_id)
    out = _delete_folder(world, world["owner"])
    assert _folder_rows(db, case_id) == []
    listed = deleted_items.list_items(db, case_id, world["owner"])
    [item] = [i for i in listed["items"] if i["kind"] == "evidence_folder"]
    assert item["id"] == out["deleted_item_id"] and item["label"] == "uploadfollow-2000" and item["files"] == 3
    assert item["deleted_by"]["name"] == "Owner" and item["days_left"] in (29, 30)
    assert not [i for i in listed["items"] if i["kind"] == "evidence_file"]  # the files are inside the folder item
    with _Fakes():
        restored = deleted_items.restore(db, case_id, "evidence_folder", item["id"], world["owner"])
    assert restored["folders"] == 2 and restored["files"] == 3
    assert _folder_rows(db, case_id) == folders_before
    assert _file_rows(db, case_id) == files_before
    assert deleted_items.list_items(db, case_id, world["owner"])["items"] == []


def test_a_collaborator_cannot_restore_or_purge(world):
    from services import deleted_items
    out = _delete_folder(world, world["owner"])
    for action in (deleted_items.restore, deleted_items.purge):
        with pytest.raises(deleted_items.DeletedItemError) as refused:
            action(world["db"], world["case"].id, "evidence_folder", out["deleted_item_id"], world["editor"])
        assert refused.value.status_code == 403


def test_a_removed_entry_link_is_kept_and_restored_exactly(world):
    from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
    from services import deleted_items, removed_records
    db, case_id, owner = world["db"], world["case"].id, world["owner"]
    entry = WorkspaceEntry(id=uuid.uuid4(), case_id=case_id, entry_type="note", title="Key date", body="b",
                           version=1)
    db.add(entry)
    db.flush()
    link = WorkspaceEntryLink(id=uuid.uuid4(), entry_id=entry.id, case_id=case_id, target_type="evidence",
                              target_id=str(world["files"]["a.bin"].id))
    db.add(link)
    db.commit()
    before = removed_records.row_values(link)
    from services.workspace_entry_service import remove_entry_link
    with patch("services.workspace_entry_service._record_revision"), \
            patch("services.workspace_entry_service._record_event"):
        remove_entry_link(db, case_id=case_id, entry_id=entry.id, link_id=link.id, current_user=owner,
                          expected_version=1)
    assert db.get(WorkspaceEntryLink, link.id) is None
    [item] = [i for i in deleted_items.list_items(db, case_id, owner)["items"] if i["kind"] == "entry_link"]
    assert item["label"] == "Link on 'Key date'"
    deleted_items.restore(db, case_id, "entry_link", item["id"], owner)
    db.expire_all()
    assert removed_records.row_values(db.get(WorkspaceEntryLink, link.id)) == before


# ----------------------------------------------------------------------------------------------------------- C


def test_a_deleted_file_stays_on_disk_until_the_purge(world):
    from services import deleted_items
    db, case_id, paths = world["db"], world["case"].id, world["paths"]
    out = _delete_folder(world, world["owner"])
    assert all(p.exists() for p in paths.values())
    with _Fakes():
        result = deleted_items.purge(db, case_id, "evidence_folder", out["deleted_item_id"], world["owner"],
                                     engine_delete=lambda *a: None)
    assert not paths["a.bin"].exists() and not paths["b.bin"].exists()
    assert result["counts"]["files_removed"] == 2


def test_purge_removes_unshared_files_keeps_a_shared_one_and_reports_counts(world):
    from postgres import soft_delete
    from services import deleted_items
    db, case_id, paths = world["db"], world["case"].id, world["paths"]
    out = _delete_folder(world, world["owner"])
    with _Fakes():
        result = deleted_items.purge(db, case_id, "evidence_folder", out["deleted_item_id"], world["owner"],
                                     engine_delete=lambda *a: None)
    assert paths["shared.bin"].exists()  # shared-copy.bin still uses it
    c = result["counts"]
    assert (c["rows_removed"], c["files_removed"], c["files_kept_shared"], c["folders_removed"]) == (3, 2, 1, 2)
    assert c["bytes_on_disk_freed"] == 20
    with soft_delete.showing_deleted(db):
        left = [f.original_filename for f in db.query(EvidenceFile).filter(EvidenceFile.case_id == case_id)]
    assert left == ["shared-copy.bin"]
    assert db.query(RemovedRecord).count() == 0  # nothing left behind
    assert deleted_items.list_items(db, case_id, world["owner"])["items"] == []


def test_the_30_day_purge_takes_kept_copies_and_folders_only_when_due(world):
    from services import deleted_items
    db, case_id = world["db"], world["case"].id
    out = _delete_folder(world, world["owner"])
    now = datetime.now(timezone.utc)
    # Copies deleted before Deleted items were switched on are never purged; this one counts as after.
    with _Fakes(), patch.object(deleted_items, "ROW_PURGE_FROM", now - timedelta(days=365)):
        assert deleted_items.purge_due_rows(db, now - timedelta(days=30), engine_delete=lambda *a: None) == []
        record = db.get(RemovedRecord, uuid.UUID(out["deleted_item_id"]))
        record.removed_at = now - timedelta(days=31)
        db.commit()
        [done] = deleted_items.purge_due_rows(db, now - timedelta(days=30), engine_delete=lambda *a: None)
    assert done["kind"] == "evidence_folder" and done["counts"]["folders_removed"] == 2


# ----------------------------------------------------------------------------------------------------------- D1


def test_deleted_case_folders_dry_run_then_apply_keeps_referenced_and_live_ones(tmp_path):
    """Postgres-only SQL (information_schema, ~): the folder purge's selection is tested with the reference lookup
    faked. History rows do not hold a folder; the engine's own job rows are removed through the engine first; any
    other row keeps it. The refusal on a missing or empty root needs no database."""
    from services import casebin_purge
    root = tmp_path / "evidence-data"
    root.mkdir()
    live, gone, engine_held, referenced = (str(uuid.uuid4()) for _ in range(4))
    for name in (live, gone, engine_held, referenced, "not-a-case"):
        (root / name).mkdir()
        (root / name / "f.bin").write_bytes(b"12345")
    db = MagicMock()
    db.execute.return_value.scalars.return_value = [live]
    before = {gone: ["activity_events.case_id"], engine_held: ["jobs.case_id", "jobs.file_path"],
              referenced: ["evidence_files.stored_path"]}
    after = {gone: ["activity_events.case_id"], engine_held: [], referenced: ["evidence_files.stored_path"]}
    removed_jobs = []
    with patch.object(casebin_purge, "_references", side_effect=[before, before, after]), \
            patch.object(casebin_purge, "_engine_jobs", return_value=[("job-1", True)]), \
            patch("services.activity_trail.record") as audit:
        dry = casebin_purge.purge_deleted_case_folders(db, [root])
        assert sorted(e["case_id"] for e in dry["remove"]) == sorted([gone, engine_held])
        assert [e["engine_jobs"] for e in dry["remove"] if e["case_id"] == engine_held] == [1]
        assert [e["case_id"] for e in dry["kept"]] == [referenced]
        assert all((root / n).exists() for n in (gone, engine_held, referenced))
        done = casebin_purge.purge_deleted_case_folders(
            db, [root], apply=True, user_email="jobs@x.test",
            engine_remove=lambda case_id, job_id, has_file: removed_jobs.append((case_id, job_id, has_file)))
    assert removed_jobs == [(engine_held, "job-1", True)]  # only the case nothing else holds
    assert not (root / gone).exists() and not (root / engine_held).exists()
    assert (root / live).exists() and (root / referenced).exists() and (root / "not-a-case").exists()
    assert (done["files_removed"], done["bytes_freed"], done["engine_jobs_removed"]) == (2, 10, 1)
    assert audit.call_args.args[0] == "deleted_case_folders_purged"
    empty = tmp_path / "unmounted"
    empty.mkdir()
    with pytest.raises(RuntimeError, match="missing or empty"):
        casebin_purge.purge_deleted_case_folders(db, [empty])
    with pytest.raises(RuntimeError, match="missing or empty"):
        casebin_purge.purge_deleted_case_folders(db, [tmp_path / "absent"])


# --------------------------------------------------------------------------------------------- review fixes


def test_a_file_restored_then_deleted_on_its_own_is_not_taken_by_its_old_folder(world):
    from services import deleted_items, evidence_casebin
    db, case_id, owner = world["db"], world["case"].id, world["owner"]
    out = _delete_folder(world, owner)
    a = world["files"]["a.bin"].id
    with _Fakes():
        evidence_casebin.restore_file(db, case_id, str(a), owner)
        evidence_casebin.delete_file(db, db.get(EvidenceFile, a), owner)
        listed = deleted_items.list_items(db, case_id, owner)["items"]
        assert [i["id"] for i in listed if i["kind"] == "evidence_file"] == [str(a)]  # its own item
        result = deleted_items.purge(db, case_id, "evidence_folder", out["deleted_item_id"], owner,
                                     engine_delete=lambda *x: None)
    assert result["counts"]["rows_removed"] == 2  # b.bin and shared.bin only
    assert world["paths"]["a.bin"].exists()
    assert [i["id"] for i in deleted_items.list_items(db, case_id, owner)["items"]] == [str(a)]


def test_kept_copies_from_before_the_switch_are_never_purged(world):
    from services import deleted_items, removed_records
    db, case_id = world["db"], world["case"].id
    old = removed_records.keep(db, kind="dossier_link", case_id=case_id, subject_id="x", label="old link",
                               rows=[], user=world["owner"])
    old.removed_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    db.commit()
    assert deleted_items.purge_due_rows(db, datetime.now(timezone.utc) - timedelta(days=30)) == []
    [item] = deleted_items.list_items(db, case_id, world["owner"])["items"]
    assert item["label"] == "old link" and item["days_left"] is None  # restorable, no purge date


def test_graph_recycle_bin_entities_are_listed_and_a_snapshot_is_private(world):
    from postgres.models.graph_recycle_bin import GraphRecycleBinItem
    from services import deleted_items, removed_records
    db, case_id = world["db"], world["case"].id
    now = datetime.now(timezone.utc)
    db.add(GraphRecycleBinItem(case_id=case_id, recycle_key="rb-1", original_key="p-1", original_name="J. Doe",
                               reason="file_delete:a.bin", deleted_at=now, status="active", relationship_count=2))
    db.add(GraphRecycleBinItem(case_id=case_id, recycle_key="rb-2", original_key="p-2", original_name="stuck",
                               reason="x", deleted_at=now, status="pending_delete", relationship_count=0))
    removed_records.keep(db, kind="snapshot", case_id=case_id, subject_id="s1", label="My snapshot", rows=[],
                         user=world["editor"])
    record = db.query(RemovedRecord).filter(RemovedRecord.kind == "snapshot").one()
    record.data = {"rows": [{"table": "snapshots", "values": {"owner": "editor@x.test"}}]}
    db.commit()
    owner_sees = {(i["kind"], i["label"]) for i in deleted_items.list_items(db, case_id, world["owner"])["items"]}
    assert owner_sees == {("graph_entity", "J. Doe")}
    editor_sees = {(i["kind"], i["label"]) for i in deleted_items.list_items(db, case_id, world["editor"])["items"]}
    assert ("snapshot", "My snapshot") in editor_sees
    with pytest.raises(deleted_items.DeletedItemError) as refused:
        deleted_items.purge(db, case_id, "snapshot", str(record.id), world["owner"])
    assert refused.value.status_code == 403


class _Chunks:
    """ChromaDB collection calls used by the batched move: get by ids or by where ($and of equalities / $in)."""

    def __init__(self, rows):
        self.rows = {k: dict(v) for k, v in rows.items()}

    def _match(self, metadata, where):
        if "$and" in where:
            return all(self._match(metadata, w) for w in where["$and"])
        for key, value in where.items():
            if isinstance(value, dict) and "$in" in value:
                if metadata.get(key) not in value["$in"]:
                    return False
            elif metadata.get(key) != value:
                return False
        return True

    def get(self, ids=None, where=None, include=None):
        keys = [i for i in (ids or self.rows) if i in self.rows and (where is None or self._match(self.rows[i], where))]
        return {"ids": keys, "metadatas": [dict(self.rows[k]) for k in keys]}

    def update(self, ids, metadatas):
        for i, m in zip(ids, metadatas):
            self.rows[i] = dict(m)


def test_a_folder_move_hides_graph_and_search_entries_of_exactly_the_files_that_have_them(world):
    from services import deleted_items, evidence_casebin
    db, case_id, owner, files = world["db"], str(world["case"].id), world["owner"], world["files"]
    a, b = files["a.bin"], files["b.bin"]
    chunks = _Chunks({"c1": {"case_id": case_id, "evidence_file_id": str(a.id)},
                      "c2": {"case_id": case_id, "file_name": "b.bin", "ingestion_state": "active"},
                      "c3": {"case_id": case_id, "evidence_file_id": "someone-else"}})
    graph = MagicMock()
    graph.run.return_value = [{"name": "a.bin", "key": "doc-a"}]
    vdb = MagicMock(chunk_collection=chunks)
    hidden = []
    from routers import evidence_folders
    with patch("services.evidence_casebin._graph_session", return_value=graph), \
            patch("services.evidence_casebin._vector_db", return_value=vdb), \
            patch("services.evidence_casebin.find_exclusive_entities", return_value=[]), \
            patch("services.evidence_casebin.hide_graph",
                  side_effect=lambda gs, **kw: hidden.append(kw["doc_key"]) or {"nodes": 1, "relationships": 0}):
        out = evidence_folders.delete_folder(folder_id=str(world["top"].id), case_id=case_id, current_user=owner,
                                             db=db)
    assert out["deleted_files"] == 3 and hidden == ["doc-a"]  # one Document; the other files had none
    assert graph.run.call_count == 1  # one lookup for every name, not one per file
    assert {k: v.get("ingestion_state") for k, v in chunks.rows.items()} == {"c1": "deleted", "c2": "deleted",
                                                                             "c3": None}
    db.expire_all()
    assert db.get(EvidenceFile, a.id).deleted_state["chunk_states"] == {"c1": None}
    assert db.get(EvidenceFile, b.id).deleted_state["chunk_states"] == {"c2": "active"}
    with patch("services.evidence_casebin._graph_session", return_value=graph), \
            patch("services.evidence_casebin._vector_db", return_value=vdb), \
            patch("services.evidence_casebin.restore_graph",
                  return_value={"nodes": 1, "relationships": 0, "merged_keys": []}):
        deleted_items.restore(db, case_id, "evidence_folder", out["deleted_item_id"], owner)
    assert {k: v.get("ingestion_state") for k, v in chunks.rows.items()} == {"c1": "active", "c2": "active",
                                                                             "c3": None}


def test_a_large_folder_purge_commits_in_parts_so_the_case_audit_lock_is_not_held_throughout(world):
    """A 5,000-file purge in one commit held the case audit lock 807.5 s on 9 Nov (merges and processing presses in
    the case waited). Each part of PURGE_COMMIT_EVERY files commits on its own; the result is the same."""
    from postgres import soft_delete
    from services import deleted_items
    db, case_id, paths = world["db"], world["case"].id, world["paths"]
    out = _delete_folder(world, world["owner"])
    commits = []
    real_commit = db.commit

    def counting_commit():
        with soft_delete.showing_deleted(db):
            commits.append(db.query(EvidenceFile).filter(EvidenceFile.case_id == case_id).count())
        real_commit()

    with _Fakes(), patch.object(deleted_items, "PURGE_COMMIT_EVERY", 1), patch.object(db, "commit", counting_commit):
        result = deleted_items.purge(db, case_id, "evidence_folder", out["deleted_item_id"], world["owner"],
                                     engine_delete=lambda *a: None)
    # 4 rows before (3 in the folder, 1 outside); one commit per file, each with one fewer row, then the item's own.
    assert commits[-4:] == [3, 2, 1, 1]
    c = result["counts"]
    assert (c["rows_removed"], c["files_removed"], c["files_kept_shared"], c["folders_removed"]) == (3, 2, 1, 2)
    assert paths["shared.bin"].exists() and not paths["a.bin"].exists()
    from postgres.models.activity_event import ActivityEvent
    purged = [e for e in db.query(ActivityEvent).all() if e.action == "evidence_purged"]
    assert len(purged) == 3 and all(e.details["with_folder"] == out["deleted_item_id"] for e in purged)


def test_a_purge_stopped_part_way_leaves_the_rest_in_deleted_items_and_a_second_purge_takes_them(world):
    from postgres import soft_delete
    from services import deleted_items
    db, case_id = world["db"], world["case"].id
    out = _delete_folder(world, world["owner"])
    real_commit, calls = db.commit, []

    def failing_second_part():
        calls.append(1)
        if len(calls) == 3:  # the first commit is before any file; the second ends part one
            raise RuntimeError("stopped")
        real_commit()

    with _Fakes(), patch.object(deleted_items, "PURGE_COMMIT_EVERY", 1):
        with patch.object(db, "commit", failing_second_part), pytest.raises(RuntimeError):
            deleted_items.purge(db, case_id, "evidence_folder", out["deleted_item_id"], world["owner"],
                                engine_delete=lambda *a: None)
        db.rollback()
        with soft_delete.showing_deleted(db):
            assert db.query(EvidenceFile).filter(EvidenceFile.case_id == case_id).count() == 3
        assert [i["kind"] for i in deleted_items.list_items(db, case_id, world["owner"])["items"]] == ["evidence_folder"]
        deleted_items.purge(db, case_id, "evidence_folder", out["deleted_item_id"], world["owner"],
                            engine_delete=lambda *a: None)
    with soft_delete.showing_deleted(db):
        assert [f.original_filename for f in db.query(EvidenceFile).filter(EvidenceFile.case_id == case_id)] == ["shared-copy.bin"]
    assert deleted_items.list_items(db, case_id, world["owner"])["items"] == []


# ------------------------------------------------------------------ upload copies (live 9 Nov 2026: 6.16 GB reported
# freed by purging 28,000 folder-upload files, about none freed: each file's upload copy kept the same bytes)

def _old(*paths):
    import os
    import time
    then = time.time() - 7200
    for path in paths:
        for base, dirs, files in os.walk(path):
            for name in dirs + files:
                os.utime(os.path.join(base, name), (then, then))
        os.utime(path, (then, then))


def _folder_upload(world, root, members, *, status="completed", kind="folder"):
    """A folder upload as the app saves it: <case>/_uploads/<session>/<name>, hard-linked into the group's payload,
    the evidence row pointing at the payload name. ``members``: {relative path: evidence folder or None}."""
    import os
    from postgres.models.evidence_upload import EvidenceUploadGroup, EvidenceUploadSession
    db, case, owner = world["db"], world["case"], world["owner"]
    group = EvidenceUploadGroup(id=uuid.uuid4(), case_id=case.id, user_id=owner.id, name="upload", kind=kind,
                                manifest=[], status=status)
    db.add(group)
    db.flush()
    case_dir = root / str(case.id)
    out = {}
    for rel, folder in members.items():
        sid = uuid.uuid5(group.id, rel)
        copy = case_dir / "_uploads" / str(sid) / rel.split("/")[-1]
        copy.parent.mkdir(parents=True)
        copy.write_bytes(b"u" * 7)
        payload = case_dir / "_upload_groups" / str(group.id) / "payload" / rel
        payload.parent.mkdir(parents=True, exist_ok=True)
        os.link(copy, payload)
        db.add(EvidenceUploadSession(id=sid, case_id=case.id, user_id=owner.id, group_id=group.id,
                                     filename=rel.split("/")[-1], size=7, sha256="u" * 64, chunk_size=4194304,
                                     chunks=[], status="completed"))
        row = EvidenceFile(id=uuid.uuid4(), case_id=case.id, folder_id=folder.id if folder else None,
                           original_filename=rel.split("/")[-1], stored_path=str(payload), sha256="u" * 64,
                           status="processed", size=7,
                           metadata_={"upload_group_id": str(group.id), "relative_path": rel})
        db.add(row)
        out[rel] = dict(session_dir=copy.parent, payload=payload, row=row)
    db.commit()
    _old(case_dir)
    return group, out


def test_purge_removes_a_folder_uploads_copy_and_counts_only_bytes_really_freed(world, tmp_path):
    from services import deleted_items
    root = tmp_path / "evidence-data"
    db, case_id = world["db"], world["case"].id
    with patch("config.EVIDENCE_DATA_ROOT", root):
        group, up = _folder_upload(world, root, {"f/c.bin": world["top"], "f/d.bin": None})
        out = _delete_folder(world, world["owner"])
        with _Fakes():
            result = deleted_items.purge(db, case_id, "evidence_folder", out["deleted_item_id"], world["owner"],
                                         engine_delete=lambda *a: None)
    c = result["counts"]
    # c.bin: its payload name and its upload copy are gone, so its 7 bytes are freed; a.bin and b.bin 10 each.
    assert not up["f/c.bin"]["payload"].exists() and not up["f/c.bin"]["session_dir"].exists()
    assert c["files_removed"] == 3 and c["upload_copies_removed"] == 1
    assert c["bytes_on_disk_freed"] == 27
    # d.bin is live: its upload copy, its payload and the group folder stay.
    assert up["f/d.bin"]["session_dir"].exists() and up["f/d.bin"]["payload"].exists()
    assert (root / str(case_id) / "_upload_groups" / str(group.id)).exists()
    with patch("config.EVIDENCE_DATA_ROOT", root):
        from services import upload_leftovers
        again = upload_leftovers.remove(db, case_id, None, apply=False)
    assert again["would_remove"] == []  # nothing a live row uses is ever offered


def test_a_purged_files_bytes_still_named_elsewhere_are_not_reported_freed(world, tmp_path):
    """Without its upload copy removed (the copy is younger than an hour), the payload name goes but the bytes stay:
    the count says 0 freed, not 7."""
    from services import deleted_items
    root = tmp_path / "evidence-data"
    db, case_id = world["db"], world["case"].id
    with patch("config.EVIDENCE_DATA_ROOT", root):
        _group, up = _folder_upload(world, root, {"f/c.bin": world["top"]})
        up["f/c.bin"]["session_dir"].joinpath("c.bin").touch()  # changed just now: an upload may be writing it
        out = _delete_folder(world, world["owner"])
        with _Fakes():
            result = deleted_items.purge(db, case_id, "evidence_folder", out["deleted_item_id"], world["owner"],
                                         engine_delete=lambda *a: None)
    assert up["f/c.bin"]["session_dir"].joinpath("c.bin").exists()
    assert result["counts"]["bytes_on_disk_freed"] == 20  # a.bin and b.bin only


def test_upload_leftovers_command_removes_unused_copies_keeps_what_is_used_or_in_progress(world, tmp_path):
    from postgres.models.evidence_upload import EvidenceUploadSession
    from services import casebin_purge
    root = tmp_path / "evidence-data"
    db, case = world["db"], world["case"]
    case_dir = root / str(case.id)
    with patch("config.EVIDENCE_DATA_ROOT", root):
        group, up = _folder_upload(world, root, {"f/live.bin": None, "f/gone.bin": None})
        gone = up["f/gone.bin"]["row"]
        db.delete(gone)  # removed before the purge removed upload copies
        db.commit()
        up["f/gone.bin"]["payload"].unlink()
        # A single-file upload still going on, and an orphan copy with no upload row at all.
        paused = EvidenceUploadSession(id=uuid.uuid4(), case_id=case.id, user_id=world["owner"].id, filename="p.bin",
                                       size=7, sha256="p" * 64, chunk_size=4194304, chunks=[], status="paused")
        db.add(paused)
        db.commit()
        for sid in (paused.id, uuid.uuid4()):
            (case_dir / "_uploads" / str(sid)).mkdir(parents=True)
            (case_dir / "_uploads" / str(sid) / "x.bin").write_bytes(b"o" * 5)
        orphan = [p for p in (case_dir / "_uploads").iterdir() if p.name not in
                  {str(paused.id), up["f/live.bin"]["session_dir"].name, up["f/gone.bin"]["session_dir"].name}][0]
        _old(case_dir)
        dry = casebin_purge.purge_upload_leftovers(db, case.id)
        assert sorted(dry["would_remove"]) == sorted([str(up["f/gone.bin"]["session_dir"]), str(orphan)])
        assert up["f/gone.bin"]["session_dir"].exists()  # a dry run removes nothing
        done = casebin_purge.purge_upload_leftovers(db, case.id, apply=True)
    assert (done["upload_folders_removed"], done["upload_files_removed"], done["upload_bytes_freed"]) == (2, 2, 12)
    assert not up["f/gone.bin"]["session_dir"].exists() and not orphan.exists()
    assert up["f/live.bin"]["session_dir"].exists() and up["f/live.bin"]["payload"].exists()
    assert (case_dir / "_uploads" / str(paused.id) / "x.bin").exists()
    from postgres.models.activity_event import ActivityEvent
    assert db.query(ActivityEvent).filter(ActivityEvent.action == "evidence_upload_copies_removed").count() == 1


def test_upload_leftovers_command_refuses_a_missing_or_empty_case_folder(world, tmp_path):
    from services import casebin_purge
    root = tmp_path / "evidence-data"
    with patch("config.EVIDENCE_DATA_ROOT", root):
        with pytest.raises(SystemExit):
            casebin_purge.purge_upload_leftovers(world["db"], world["case"].id)
        (root / str(world["case"].id)).mkdir(parents=True)
        with pytest.raises(SystemExit):
            casebin_purge.purge_upload_leftovers(world["db"], world["case"].id, apply=True)


def test_a_phone_reports_upload_copies_stay_while_its_row_does_and_go_with_its_group_folder(world, tmp_path):
    """A phone report is one row whose stored path is the report folder, not one row per member: every upload copy
    of its group stays while that row exists. Once the group's last row is gone, removing the group folder takes
    its sessions' copies with it."""
    from services import upload_leftovers
    root = tmp_path / "evidence-data"
    db, case_id = world["db"], world["case"].id
    with patch("config.EVIDENCE_DATA_ROOT", root):
        group, up = _folder_upload(world, root, {"report/a.db": None, "report/b.db": None})
        report = EvidenceFile(id=uuid.uuid4(), case_id=case_id, original_filename="report",
                              stored_path=str(up["report/a.db"]["payload"].parent), sha256="r" * 64,
                              status="processed", size=0,
                              metadata_={"upload_group_id": str(group.id), "relative_path": "report"})
        for member in up.values():
            db.delete(member["row"])
        db.add(report)
        db.commit()
        kept = upload_leftovers.remove(db, case_id, None, apply=False)
        assert kept["would_remove"] == []
        db.delete(report)
        db.commit()
        group_dir = root / str(case_id) / "_upload_groups" / str(group.id)
        out = upload_leftovers.remove(db, case_id, {group_dir})
    assert not group_dir.exists()
    assert not any(m["session_dir"].exists() for m in up.values())
    assert (out["upload_folders_removed"], out["upload_files_removed"], out["upload_bytes_freed"]) == (3, 4, 14)
