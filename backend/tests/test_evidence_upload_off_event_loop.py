"""Uploading evidence and queuing a Cellebrite folder keep every database step in the thread pool: the handlers
are async for the form, staging and engine calls only. Through the app, with a real session; the engine faked."""

from __future__ import annotations

import threading
import uuid
import zipfile
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile, EvidenceFolder, IngestionLog
from postgres.models.user import User
from routers.evidence import get_current_db_user, get_db, router

TABLES = [User.__table__, Case.__table__, EvidenceFolder.__table__, EvidenceFile.__table__, IngestionLog.__table__]


@pytest.fixture()
def app_world(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True, poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=TABLES)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    case_id, user_id = uuid.uuid4(), uuid.uuid4()
    with SessionLocal() as db:
        db.add(User(id=user_id, email="investigator@example.com", name="Investigator", password_hash="hash"))
        db.add(Case(id=case_id, title="Case", created_by_user_id=user_id, owner_user_id=user_id))
        db.commit()
    app = FastAPI()
    app.include_router(router)

    def override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    threads = []

    @event.listens_for(engine, "before_cursor_execute")
    def _thread(conn, cursor, statement, *rest):
        threads.append((threading.current_thread().name, statement.split("\n")[0][:60]))

    def current_user(db=Depends(get_db)):
        # The request's own session, as get_current_db_user gives it, so a commit expires the user.
        return db.get(User, user_id)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_db_user] = current_user
    root = tmp_path / "evidence"
    with patch("routers.evidence.EVIDENCE_ROOT_DIR", root), \
            patch("routers.evidence._UPLOAD_STAGING_ROOT", root / "_staging"), \
            patch("services.case_service.check_case_access", return_value=(object(), None)), \
            patch("routers.case_access.check_case_access", return_value=(object(), None)), \
            patch("routers.evidence.evidence_engine_client.check_cellebrite_folder",
                  new=AsyncMock(return_value={"suitable": True, "report_name": "PhoneReport",
                                              "report_key": "k", "model_count": 1})), \
            patch("routers.evidence.evidence_engine_client.create_cellebrite_job",
                  new=AsyncMock(return_value={"id": "job-1"})) as create_job:
        with TestClient(app) as client:
            threads.clear()
            yield client, SessionLocal, case_id, tmp_path, threads, create_job
    engine.dispose()


def _off_the_loop(threads):
    on_the_loop = [statement for name, statement in threads if not name.startswith("AnyIO worker thread")]
    assert threads and on_the_loop == []


def test_a_file_upload_registers_its_record_off_the_event_loop(app_world):
    client, SessionLocal, case_id, tmp_path, threads, _ = app_world
    response = client.post("/api/evidence/upload", data={"case_id": str(case_id)},
                           files={"files": ("statement.pdf", b"%PDF-1.4 synthetic", "application/pdf")})
    assert response.status_code == 200, response.text
    seen = list(threads)
    assert [f["original_filename"] for f in response.json()["files"]] == ["statement.pdf"]
    with SessionLocal() as db:
        assert [f.original_filename for f in db.query(EvidenceFile)] == ["statement.pdf"]
    _off_the_loop(seen)


def test_an_archive_upload_and_a_cellebrite_folder_queue_off_the_event_loop(app_world):
    client, SessionLocal, case_id, tmp_path, threads, create_job = app_world
    archive = tmp_path / "report.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("PhoneReport/PhoneReport.xml", "<report xmlns='http://pa.cellebrite.com/report/2.0' />")
    with archive.open("rb") as handle:
        response = client.post("/api/evidence/upload",
                               data={"case_id": str(case_id), "is_folder": "true", "is_archive": "true"},
                               files={"files": ("report.zip", handle, "application/zip")})
    assert response.status_code == 200, response.text
    assert response.json()["job_ids"] == ["job-1"]
    assert create_job.await_args.kwargs["owner"] == "investigator@example.com"

    response = client.post("/api/evidence/cellebrite/process",
                           json={"case_id": str(case_id), "folder_path": "PhoneReport"})
    assert response.status_code == 200, response.text
    assert response.json()["job_id"] == "job-1"
    seen = list(threads)
    with SessionLocal() as db:
        assert [f.name for f in db.query(EvidenceFolder)] == ["PhoneReport"]
    _off_the_loop(seen)
