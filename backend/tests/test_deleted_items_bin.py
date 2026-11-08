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
    return [WorkspaceEntryRevision.__table__, WorkspaceEntryEvent.__table__, CaseTask.__table__, TimelineView.__table__, ActivityEvent.__table__, User.__table__, Case.__table__, CaseMembership.__table__, EvidenceFolder.__table__,
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
