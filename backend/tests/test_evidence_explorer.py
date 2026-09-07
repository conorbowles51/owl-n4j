import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, literal, select, union_all
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile, EvidenceFolder, IngestionLog
from postgres.models.user import User
from routers import evidence_folders
from services.evidence_db_storage import EvidenceDBStorage as Storage, EvidenceMoveError, evidence_ordering
from services.evidence_processing_service import process_db_files


@pytest.fixture
def fixture():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[User.__table__, Case.__table__, EvidenceFolder.__table__, EvidenceFile.__table__, IngestionLog.__table__])
    with Session(engine) as db:
        case_id = uuid4()
        def folder(name, parent=None, case=None):
            row = EvidenceFolder(case_id=case or case_id, name=name, parent_id=parent)
            db.add(row); db.flush()
            return row
        def file(name, parent=None, case=None, **kwargs):
            row = EvidenceFile(case_id=case or case_id, original_filename=name, folder_id=parent, stored_path="/untouched/source", sha256="a" * 64, **kwargs)
            db.add(row); db.flush()
            return row
        yield SimpleNamespace(db=db, engine=engine, case=case_id, folder=folder, file=file)
    engine.dispose()


@pytest.mark.parametrize("sort_by,direction", [("name", "asc"), ("name", "desc"), ("date", "asc"), ("date", "desc")])
def test_sort_search_and_location_share_order_across_pages(fixture, sort_by, direction):
    f = fixture
    folder = f.folder("nested")
    rows = [f.file(["alpha.pdf", "ALPHA.pdf", "Zulu.pdf", "beta.pdf"][i % 4], folder.id, created_at=datetime(2026, 1, 1) + timedelta(days=i % 3)) for i in range(507)]
    options = dict(sort_by=sort_by, sort_direction=direction)
    # Independent expected order: UUID tie-breaker, then name, then selected primary.
    expected = sorted(rows, key=lambda row: str(row.id))
    expected.sort(key=lambda row: row.original_filename.lower())
    expected.sort(key=lambda row: row.created_at if sort_by == "date" else row.original_filename.lower(), reverse=direction == "desc")
    ids = []
    for offset in [0, 250, 500]:
        listing = Storage.list_contents(f.db, f.case, folder.id, offset=offset, **options)
        ids.extend(row["id"] for row in listing["files"])
        search = Storage.search_files(f.db, f.case, ".pdf", offset=offset, **options)
        assert [row["id"] for row in search["files"]] == [row["id"] for row in listing["files"]]
    assert ids == [str(row.id) for row in expected]
    for index in [0, 249, 250, 499, 500, 506]:
        location = Storage.get_file_location(f.db, f.case, expected[index].id, **options)
        assert location["file_offset"] == index // 250 * 250


@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_missing_dates_last_and_folders_sorted(fixture, direction):
    f = fixture
    data = union_all(select(literal("c").label("id"), literal("Missing").label("name"), literal(None).label("created_at")),
                     select(literal("b"), literal("New"), literal("2026-02-01")),
                     select(literal("a"), literal("Old"), literal("2026-01-01"))).subquery()
    model = SimpleNamespace(id=data.c.id, name=data.c.name, created_at=data.c.created_at)
    ids = list(f.db.scalars(select(data.c.id).order_by(*evidence_ordering(model, "date", direction))))
    assert ids == (["a", "b", "c"] if direction == "asc" else ["b", "a", "c"])
    for i, name in enumerate(["zulu", "Alpha", "beta"]):
        folder = f.folder(name); folder.created_at = datetime(2026, 1, i + 1)
    f.db.flush()
    result = Storage.list_contents(f.db, f.case, sort_by="name", sort_direction=direction)
    assert [row["name"] for row in result["folders"]] == (["Alpha", "beta", "zulu"] if direction == "asc" else ["zulu", "beta", "Alpha"])


def test_search_unopened_subtree_literal_characters_filters_paths_and_batched_queries(fixture):
    f = fixture
    parent = f.folder("Parent"); child = f.folder("Child", parent.id); elsewhere = f.folder("Elsewhere")
    target = f.file("Report_100%.PDF", child.id, status="processed", processing_stale=True)
    f.file("Report_100%.png", parent.id); f.file("Report_100%.PDF", elsewhere.id)
    f.file("Reportx100z.PDF", child.id); f.file("Report_100%.PDF", case=uuid4())
    statements = []
    def record(*args): statements.append(args[2])
    event.listen(f.engine, "before_cursor_execute", record)
    result = Storage.search_files(f.db, f.case, "REPORT_100%", status="processed", type_category="Document")
    event.remove(f.engine, "before_cursor_execute", record)
    assert result["file_total"] == 1
    assert len(statements) == 3
    assert result["files"][0]["id"] == str(target.id)
    assert result["files"][0]["processing_stale"] is False
    assert result["files"][0]["folder_path"] == [{"id": str(parent.id), "name": "Parent"}, {"id": str(child.id), "name": "Child"}]
    assert Storage.search_files(f.db, f.case, "_100%", scope="subtree", folder_id=parent.id)["file_total"] == 2
    assert Storage.search_files(f.db, f.case, "_100%", scope="case")["file_total"] == 3
    assert Storage.search_files(f.db, f.case, "absent")["files"] == []
    assert Storage.list_contents(f.db, f.case, child.id, status="processed")["file_total"] == 1


@pytest.mark.parametrize("state", ["processed", "processing"])
def test_moves_preserve_files_results_and_running_snapshots(fixture, state):
    f = fixture
    old = f.folder("Old"); target = f.folder("Target")
    file = f.file("duplicate.pdf", old.id, status=state, processing_stale=True, summary="Completed analysis", entity_count=42,
                  engine_job_id="running-job", last_processed_folder_id=old.id, last_processed_profile_snapshot={"context": "captured"})
    duplicate = f.file("duplicate.pdf", target.id)
    before = (file.id, file.stored_path, file.sha256, file.summary, file.entity_count, file.engine_job_id, file.last_processed_folder_id, file.last_processed_profile_snapshot)
    moved = Storage.move_files(f.db, [file.id, duplicate.id, file.id], target.id)
    assert len(moved) == 1 and file.folder_id == target.id
    assert (file.id, file.stored_path, file.sha256, file.summary, file.entity_count, file.engine_job_id, file.last_processed_folder_id, file.last_processed_profile_snapshot) == before
    assert file.status == state
    assert Storage.move_files(f.db, [file.id], target.id) == []
    Storage.move_file(f.db, file.id, None)
    assert file.folder_id is None


def test_invalid_batch_is_atomic_and_cross_case_targets_rejected(fixture):
    f = fixture
    target = f.folder("Target"); foreign = f.folder("Foreign", case=uuid4())
    first = f.file("one.pdf"); other = f.file("private.pdf", case=uuid4())
    for ids, destination in [([first.id, uuid4()], target.id), ([first.id, other.id], target.id), ([first.id], foreign.id), ([first.id], uuid4())]:
        with pytest.raises(EvidenceMoveError): Storage.move_files(f.db, ids, destination)
        assert first.folder_id is None
    f.db.delete(target); f.db.flush()
    with pytest.raises(EvidenceMoveError): Storage.move_file(f.db, first.id, target.id)
    assert first.folder_id is None


def test_folder_moves_cycles_conflicts_and_search_paths(fixture):
    f = fixture
    parent = f.folder("Parent"); child = f.folder("Child", parent.id); target = f.folder("Target")
    file = f.file("proof.pdf", child.id)
    for destination in [parent.id, child.id]:
        with pytest.raises(EvidenceMoveError): Storage.move_folder(f.db, parent.id, destination)
    conflict = f.folder("Parent", target.id)
    with pytest.raises(EvidenceMoveError, match="already exists"): Storage.move_folder(f.db, parent.id, target.id)
    f.db.delete(conflict); f.db.flush()
    Storage.move_folder(f.db, parent.id, target.id)
    assert parent.parent_id == target.id
    assert [p["name"] for p in Storage.search_files(f.db, f.case, "proof")["files"][0]["folder_path"]] == ["Target", "Parent", "Child"]
    assert file.folder_id == child.id
    Storage.move_folder(f.db, parent.id, None)
    assert parent.parent_id is None
    f.folder("Child")
    with pytest.raises(EvidenceMoveError): Storage.move_folder(f.db, child.id, None)


def test_historical_stale_never_reprocesses_without_force(fixture):
    f = fixture
    file = f.file("processed.pdf", status="processed", processing_stale=True, summary="keep")
    Storage.mark_processing(f.db, [file.id])
    assert file.status == "processed" and file.summary == "keep"
    with patch("services.evidence_processing_service.reconcile_case_jobs", new=AsyncMock()):
        result = asyncio.run(process_db_files(f.db, case_id=f.case, file_ids=[file.id]))
    assert result["file_count"] == 0
    Storage.mark_processing(f.db, [file.id], force=True)
    assert file.status == "processing"


@pytest.fixture
def client(fixture):
    app = FastAPI(); app.include_router(evidence_folders.router)
    app.dependency_overrides[evidence_folders.get_db] = lambda: fixture.db
    app.dependency_overrides[evidence_folders.get_current_db_user] = lambda: SimpleNamespace(id=uuid4())
    with TestClient(app) as client:
        yield client


def test_routes_validate_permissions_all_sources_and_move_counts(fixture, client):
    f = fixture
    target = f.folder("Destination"); first = f.file("a"); foreign = f.file("b", case=uuid4())
    f.db.commit()
    with patch.object(evidence_folders, "_check_case_access", side_effect=HTTPException(403)):
        assert client.put(f"/api/evidence-folders/files/{first.id}/move?new_folder_id={target.id}").status_code == 403
        assert client.get(f"/api/evidence-folders/search?case_id={f.case}&query=a").status_code == 403
        assert client.put(f"/api/evidence-folders/{target.id}/move", json={"new_parent_id": None}).status_code == 403
    with patch.object(evidence_folders, "_check_case_access") as access:
        response = client.put(f"/api/evidence-folders/files/move-batch?new_folder_id={target.id}", json=[str(first.id), str(foreign.id)])
        assert response.status_code == 400 and access.call_count == 2
        assert first.folder_id is None
        response = client.put(f"/api/evidence-folders/files/move-batch?new_folder_id={target.id}", json=[str(first.id), str(first.id)])
        assert response.status_code == 200 and response.json()["moved"] == 1
        response = client.put(f"/api/evidence-folders/files/move-batch?new_folder_id={target.id}", json=[str(first.id)])
        assert response.json()["moved"] == 0
        assert client.put("/api/evidence-folders/root/move", json={"new_parent_id": None}).status_code == 422
        assert client.get(f"/api/evidence-folders/root/contents?case_id={f.case}&sort_by=invalid").status_code == 422
        assert client.get(f"/api/evidence-folders/{target.id}/contents?case_id={foreign.case_id}").status_code == 404
        response = client.get(f"/api/evidence-folders/search?case_id={f.case}&query=a")
        assert response.status_code == 200 and response.json()["file_total"] == 1


@pytest.mark.parametrize("force", [False, True])
def test_folder_processing_keeps_explicit_reprocessing_and_ignores_stale(fixture, client, force):
    f = fixture
    parent = f.folder("Parent")
    file = f.file("done.pdf", parent.id, status="processed", processing_stale=True)
    f.db.commit()
    with patch.object(evidence_folders, "_check_case_access"), patch.object(evidence_folders, "process_db_files", new=AsyncMock(return_value={"file_count": 1})) as process, patch.object(evidence_folders, "resolve_effective_profile", return_value={}):
        response = client.post(f"/api/evidence-folders/{parent.id}/process", json={"case_id": str(f.case), "reprocess_completed": force})
        assert response.status_code == 200
        if force:
            assert process.call_args.kwargs["force_reprocess"] is True
            assert process.call_args.kwargs["file_ids"] == [file.id]
        else:
            process.assert_not_called()
            assert response.json()["file_count"] == 0
