"""Deleting an evidence file runs its checks and the move to Deleted items in the thread pool (the route is a plain
function), and touches neither the file on disk nor the engine copy. The 30-day purge then removes them with the
old delete's rules: never a file another row still uses, never a phone production. A real session; graph, vector
store and engine faked."""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.concurrency import run_in_threadpool

from postgres.base import Base
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from routers import evidence as router


@pytest.fixture()
def world(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
    from postgres.models.financial_import_batches import FinancialImportBatch
    # The delete asks Financial whether it still holds the file.
    Base.metadata.create_all(engine, tables=[EvidenceFolder.__table__, EvidenceFile.__table__,
                                             FinancialImportBatch.__table__, FinancialSourceDocument.__table__,
                                             FinancialTransaction.__table__])
    db = Session(engine)
    case_id = uuid4()
    path = tmp_path / "statement.pdf"
    path.write_bytes(b"%PDF")
    record = EvidenceFile(case_id=case_id, original_filename=path.name, stored_path=str(path), sha256="a" * 64,
                          status="processed", engine_job_id="job9")
    db.add(record)
    db.commit()
    loop_sql = []
    watching = threading.Event()

    @event.listens_for(engine, "before_cursor_execute")
    def _on_the_loop(conn, cursor, statement, *rest):
        if watching.is_set() and threading.current_thread() is threading.main_thread():
            loop_sql.append(statement.split("\n")[0][:80])

    yield db, case_id, record.id, path, loop_sql, watching
    db.close()
    engine.dispose()


def _fakes():
    return (patch("services.evidence_casebin._graph_session", return_value=MagicMock()),
            patch("services.evidence_casebin.find_document_key", return_value=None),
            patch("services.evidence_casebin.hide_graph", return_value={"nodes": 0, "relationships": 0}),
            patch("services.evidence_casebin.purge_graph",
                  return_value={"removed_keys": [], "nodes": 0, "relationships": 0}),
            patch("services.evidence_casebin._vector_db", return_value=None),
            patch("services.activity_trail.record"))


def _delete(db, case_id, evidence_id, watching, engine_delete):
    """The route as FastAPI runs a plain function: in the thread pool."""
    assert not asyncio.iscoroutinefunction(router.delete_evidence_file)
    watching.set()
    try:
        with patch("services.case_service.check_case_access"), \
                patch.object(router.evidence_engine_client, "delete_file", new=engine_delete), \
                _fakes()[0], _fakes()[1], _fakes()[2], _fakes()[4], _fakes()[5]:
            return asyncio.run(run_in_threadpool(
                router.delete_evidence_file, str(evidence_id), case_id=str(case_id), delete_exclusive_entities=True,
                current_user=SimpleNamespace(id=None, email="analyst@example.test"), db=db))
    finally:
        watching.clear()


def _purge(db, evidence_id):
    """The 30-day purge of one file (services/casebin_purge.py), engine copy removal recorded."""
    from services import casebin_purge
    removed = []
    fakes = _fakes()
    with fakes[3], fakes[4], fakes[5]:
        details = casebin_purge.purge_file(db, evidence_id, graph_session=MagicMock(),
                                           engine_delete=lambda case_id, job: removed.append((case_id, job)))
    return details, removed


def _hidden(db, evidence_id):
    # A request starts with an empty session; an object already loaded refreshes by its key, past any filter.
    from postgres.soft_delete import showing_deleted
    db.expunge_all()
    hidden = db.get(EvidenceFile, evidence_id) is None
    with showing_deleted(db):
        row = db.get(EvidenceFile, evidence_id)
    return hidden and row is not None and row.deleted_at is not None


def test_a_delete_moves_the_file_to_deleted_items_without_sql_on_the_event_loop(world):
    db, case_id, evidence_id, path, loop_sql, watching = world
    engine_delete = AsyncMock()
    result = _delete(db, case_id, evidence_id, watching, engine_delete)
    assert (result["evidence_id"], result["filename"], result["deleted"]) == (str(evidence_id), "statement.pdf", True)
    engine_delete.assert_not_awaited()
    assert path.exists()
    assert _hidden(db, evidence_id)
    assert loop_sql == []
    details, removed = _purge(db, evidence_id)
    assert details["file_deleted"] is True and not path.exists()
    assert removed == [(str(case_id), "job9")]
    from postgres.soft_delete import showing_deleted
    db.expunge_all()
    with showing_deleted(db):
        assert db.get(EvidenceFile, evidence_id) is None


@pytest.mark.parametrize("status_code", [404, 409])
def test_refusals_keep_their_status_and_touch_nothing(world, status_code):
    db, case_id, evidence_id, path, loop_sql, watching = world
    if status_code == 409:
        db.get(EvidenceFile, evidence_id).status = "processing"
        db.commit()
    engine_delete = AsyncMock()
    with pytest.raises(HTTPException) as refused:
        _delete(db, case_id, uuid4() if status_code == 404 else evidence_id, watching, engine_delete)
    assert refused.value.status_code == status_code
    engine_delete.assert_not_awaited()
    db.expire_all()
    record = db.get(EvidenceFile, evidence_id)
    assert path.exists() and record is not None and record.deleted_at is None
    assert loop_sql == []


def test_a_purge_keeps_the_file_when_another_evidence_row_shares_its_stored_path(world):
    # Live 1 Nov: 8 stored paths were each recorded by two rows; deleting one row removed the other row's file.
    db, case_id, evidence_id, path, loop_sql, watching = world
    twin = EvidenceFile(case_id=case_id, original_filename=path.name, stored_path=str(path), sha256="a" * 64,
                        status="processed")
    db.add(twin)
    db.commit()
    _delete(db, case_id, evidence_id, watching, AsyncMock())
    assert path.exists()
    details, _ = _purge(db, evidence_id)
    assert details["file_deleted"] is False and details["file_kept_shared"] is True
    assert path.exists()
    db.expire_all()
    assert db.get(EvidenceFile, twin.id) is not None


def test_a_folder_delete_keeps_every_file_and_the_purge_keeps_one_still_used_outside_the_folder(world, tmp_path):
    from routers import evidence_folders
    db, case_id, evidence_id, path, loop_sql, watching = world
    folder = EvidenceFolder(case_id=case_id, name="Bank")
    db.add(folder)
    db.flush()
    own = tmp_path / "own.pdf"
    own.write_bytes(b"%PDF own")
    shared = EvidenceFile(case_id=case_id, folder_id=folder.id, original_filename=path.name, stored_path=str(path),
                          sha256="a" * 64, status="processed")
    mine = EvidenceFile(case_id=case_id, folder_id=folder.id, original_filename=own.name, stored_path=str(own),
                        sha256="b" * 64, status="processed")
    db.add_all([shared, mine])
    db.commit()
    shared_id, mine_id = shared.id, mine.id
    fakes = _fakes()
    with patch.object(evidence_folders, "_check_case_access"), fakes[0], fakes[1], fakes[2], fakes[4], fakes[5]:
        result = evidence_folders.delete_folder(str(folder.id), case_id=str(case_id),
                                                current_user=SimpleNamespace(id=None, email="a@example.test"), db=db)
    assert result["deleted_files"] == 2
    assert path.exists() and own.exists()
    assert _hidden(db, shared_id) and _hidden(db, mine_id)
    for row_id in (shared_id, mine_id):
        _purge(db, row_id)
    assert path.exists() and not own.exists()
    db.expire_all()
    assert db.get(EvidenceFile, evidence_id) is not None


@pytest.mark.parametrize("source_type", ["phone_file", "phone_extraction"])
def test_a_purge_never_removes_a_phone_production_file(world, source_type):
    # A phone file added as evidence from a folder upload stores the file's own path inside the uploaded phone
    # production, and a phone report row stores the uploaded report itself (live 3 Nov: 8 report folders, 4 zips).
    # Removing the row from Evidence must leave the production on disk: the phone still reads from it.
    db, case_id, evidence_id, path, loop_sql, watching = world
    db.get(EvidenceFile, evidence_id).source_type = source_type
    db.commit()
    _delete(db, case_id, evidence_id, watching, AsyncMock())
    details, _ = _purge(db, evidence_id)
    assert details["file_deleted"] is False and details["file_kept_production"] is True
    assert path.exists()


def test_a_folder_purge_never_removes_a_phone_production_file(world, tmp_path):
    from routers import evidence_folders
    db, case_id, evidence_id, path, loop_sql, watching = world
    folder = EvidenceFolder(case_id=case_id, name="Dossier media")
    db.add(folder)
    db.flush()
    phone = tmp_path / "IMG_0001.jpg"
    phone.write_bytes(b"\xff\xd8 phone")
    own = tmp_path / "own.pdf"
    own.write_bytes(b"%PDF own")
    rows = [EvidenceFile(case_id=case_id, folder_id=folder.id, original_filename=phone.name,
                         stored_path=str(phone), sha256="c" * 64, status="processed", source_type="phone_file"),
            EvidenceFile(case_id=case_id, folder_id=folder.id, original_filename=own.name,
                         stored_path=str(own), sha256="b" * 64, status="processed")]
    db.add_all(rows)
    db.commit()
    row_ids = [row.id for row in rows]
    fakes = _fakes()
    with patch.object(evidence_folders, "_check_case_access"), fakes[0], fakes[1], fakes[2], fakes[4], fakes[5]:
        result = evidence_folders.delete_folder(str(folder.id), case_id=str(case_id),
                                                current_user=SimpleNamespace(id=None, email="a@example.test"), db=db)
    assert result["deleted_files"] == 2
    for row_id in row_ids:
        _purge(db, row_id)
    assert phone.exists() and not own.exists()
