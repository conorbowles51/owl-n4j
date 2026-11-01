"""Deleting an evidence file runs its checks, graph, vector and disk clean-up and the record delete in the thread
pool; only the engine call is awaited on the loop. A real session; graph, vector store and engine faked."""

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


def _delete(db, case_id, evidence_id, watching, engine_delete):
    graph = MagicMock()
    graph.find_document_node.return_value = None
    watching.set()
    try:
        with patch("services.case_service.check_case_access"), \
                patch.object(router, "neo4j_service", graph), \
                patch("services.vector_db_service.get_vector_db_service", return_value=None), \
                patch.object(router.evidence_engine_client, "delete_file", new=engine_delete):
            return asyncio.run(router.delete_evidence_file(
                str(evidence_id), case_id=str(case_id), delete_exclusive_entities=True,
                current_user=SimpleNamespace(email="analyst@example.test"), db=db))
    finally:
        watching.clear()


def test_a_delete_removes_file_record_and_engine_copy_without_sql_on_the_event_loop(world):
    db, case_id, evidence_id, path, loop_sql, watching = world
    engine_delete = AsyncMock()
    result = _delete(db, case_id, evidence_id, watching, engine_delete)
    assert result == {"evidence_id": str(evidence_id), "filename": "statement.pdf", "file_deleted": True,
                      "document_deleted": False, "exclusive_entities_recycled": [],
                      "shared_entities_unlinked": [], "chromadb_cleaned": False}
    engine_delete.assert_awaited_once_with(str(case_id), "job9")
    assert not path.exists()
    db.expire_all()
    assert db.get(EvidenceFile, evidence_id) is None
    assert loop_sql == []


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
    assert path.exists() and db.get(EvidenceFile, evidence_id) is not None
    assert loop_sql == []


def test_a_delete_keeps_the_file_when_another_evidence_row_shares_its_stored_path(world):
    # Live 1 Nov: 8 stored paths were each recorded by two rows; deleting one row removed the other row's file.
    db, case_id, evidence_id, path, loop_sql, watching = world
    twin = EvidenceFile(case_id=case_id, original_filename=path.name, stored_path=str(path), sha256="a" * 64,
                        status="processed")
    db.add(twin)
    db.commit()
    result = _delete(db, case_id, evidence_id, watching, AsyncMock())
    assert result["file_deleted"] is False and result["file_kept_shared"] is True
    assert path.exists()
    db.expire_all()
    assert db.get(EvidenceFile, evidence_id) is None and db.get(EvidenceFile, twin.id) is not None


def test_a_folder_delete_keeps_a_file_still_used_by_a_row_outside_the_folder(world, tmp_path):
    from routers import evidence_folders
    db, case_id, evidence_id, path, loop_sql, watching = world
    folder = EvidenceFolder(case_id=case_id, name="Bank")
    db.add(folder)
    db.flush()
    own = tmp_path / "own.pdf"
    own.write_bytes(b"%PDF own")
    db.add_all([EvidenceFile(case_id=case_id, folder_id=folder.id, original_filename=path.name,
                             stored_path=str(path), sha256="a" * 64, status="processed"),
                EvidenceFile(case_id=case_id, folder_id=folder.id, original_filename=own.name,
                             stored_path=str(own), sha256="b" * 64, status="processed")])
    db.commit()
    with patch.object(evidence_folders, "_check_case_access"):
        result = evidence_folders.delete_folder(str(folder.id), case_id=str(case_id),
                                                current_user=SimpleNamespace(email="a@example.test"), db=db)
    assert result["deleted_files"] == 1
    assert path.exists() and not own.exists()
    db.expire_all()
    assert db.get(EvidenceFile, evidence_id) is not None
