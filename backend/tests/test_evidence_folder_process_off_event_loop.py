"""Processing a folder selects its files and reads its profile in the thread pool; only the engine send is awaited
on the loop. A real session; access check, send and profile faked."""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from postgres.base import Base
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from routers import evidence_folders as router


@pytest.fixture()
def world():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[EvidenceFolder.__table__, EvidenceFile.__table__])
    db = Session(engine)
    case_id = uuid4()
    folder = EvidenceFolder(id=uuid4(), case_id=case_id, name="Bank")
    db.add(folder)
    db.flush()
    files = {}
    for name, folder_id, status in [("a.pdf", folder.id, "processed"), ("b.pdf", folder.id, "unprocessed"),
                                    ("c.pdf", None, "unprocessed")]:
        record = EvidenceFile(case_id=case_id, folder_id=folder_id, original_filename=name, stored_path=name,
                              sha256="a" * 64, status=status)
        db.add(record)
        files[name] = record
    db.commit()
    loop_sql = []
    watching = threading.Event()

    @event.listens_for(engine, "before_cursor_execute")
    def _on_the_loop(conn, cursor, statement, *rest):
        if watching.is_set() and threading.current_thread() is threading.main_thread():
            loop_sql.append(statement.split("\n")[0][:80])

    yield db, case_id, folder.id, {name: record.id for name, record in files.items()}, loop_sql, watching
    db.close()
    engine.dispose()


def _process(db, case_id, folder_id, watching, **request):
    send = AsyncMock(side_effect=lambda db, **kwargs: {"job_ids": ["job"], "file_count": len(kwargs["file_ids"])})
    user = SimpleNamespace(id=uuid4())
    watching.set()
    try:
        with patch.object(router, "_check_case_access"), patch.object(router, "process_db_files", new=send), \
                patch.object(router, "resolve_effective_profile", return_value={"name": "default"}):
            result = asyncio.run(router.process_folder(
                str(folder_id), router.ProcessFolderRequest(case_id=str(case_id), **request),
                current_user=user, db=db))
    finally:
        watching.clear()
    return result, send, user


def test_a_folder_sends_its_unprocessed_files_without_sql_on_the_event_loop(world):
    db, case_id, folder_id, ids, loop_sql, watching = world
    result, send, user = _process(db, case_id, folder_id, watching)
    assert result == {"job_ids": ["job"], "file_count": 1, "effective_profile": {"name": "default"}}
    assert send.await_args.kwargs["file_ids"] == [ids["b.pdf"]]
    assert send.await_args.kwargs["requested_by_user_id"] == user.id
    assert loop_sql == []


def test_root_and_reprocess_select_as_before(world):
    db, case_id, folder_id, ids, loop_sql, watching = world
    result, send, _ = _process(db, case_id, "root", watching, recursive=False, reprocess_completed=True)
    assert send.await_args.kwargs["file_ids"] == [ids["c.pdf"]] and send.await_args.kwargs["force_reprocess"]
    result, send, _ = _process(db, case_id, "root", watching, recursive=True)
    assert sorted(send.await_args.kwargs["file_ids"]) == sorted([ids["b.pdf"], ids["c.pdf"]])
    assert loop_sql == []


def test_nothing_to_send_answers_without_sending(world):
    db, case_id, folder_id, ids, loop_sql, watching = world
    db.get(EvidenceFile, ids["b.pdf"]).status = "processed"
    db.commit()
    result, send, _ = _process(db, case_id, folder_id, watching, recursive=False)
    assert result == {"job_ids": [], "file_count": 0, "message": "All files already processed"}
    send.assert_not_awaited()
    assert loop_sql == []
