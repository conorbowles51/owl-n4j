"""Uploading evidence keeps every database step in the thread pool: the handler is async for the form, staging and
engine calls only. Through the app, with a real session; the engine's phone detector faked. A phone report sent
here is refused with 409 (01 section 4.1); an ordinary zip is unpacked and kept as received."""

from __future__ import annotations

import hashlib
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
    async def detect(case, path):
        full = root / case / path
        phone = full.is_file() and zipfile.is_zipfile(full) and any(
            n.endswith(".xml") and b"http://pa.cellebrite.com/report/2.0" in zipfile.ZipFile(full).read(n)
            for n in zipfile.ZipFile(full).namelist())
        return {"outcome": "readable" if phone else "not_a_phone_report", "roots": []}
    with patch("routers.evidence.EVIDENCE_ROOT_DIR", root), \
            patch("routers.evidence.USE_EVIDENCE_ENGINE", True), \
            patch("services.case_service.check_case_access", return_value=(object(), None)), \
            patch("routers.case_access.check_case_access", return_value=(object(), None)), \
            patch("routers.evidence.evidence_engine_client.detect_phone_container",
                  new=AsyncMock(side_effect=detect)) as detected:
        with TestClient(app) as client:
            threads.clear()
            yield client, SessionLocal, case_id, tmp_path, threads, detected
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


def test_a_phone_report_zip_is_refused_and_nothing_is_registered(app_world):
    client, SessionLocal, case_id, tmp_path, threads, detected = app_world
    archive = tmp_path / "report.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("PhoneReport/PhoneReport.xml", "<project xmlns='http://pa.cellebrite.com/report/2.0' />")
    with archive.open("rb") as handle:
        response = client.post("/api/evidence/upload",
                               data={"case_id": str(case_id), "is_folder": "true", "is_archive": "true"},
                               files={"files": ("report.zip", handle, "application/zip")})
    assert (response.status_code, response.json()["detail"]) == (
        409, "Upload phone reports with the folder or archive upload")
    with SessionLocal() as db:
        assert db.query(EvidenceFile).count() == 0 and db.query(EvidenceFolder).count() == 0
    assert not any((tmp_path / "evidence" / str(case_id)).rglob("*.*"))  # staging removed


def test_an_ordinary_archive_is_unpacked_off_the_event_loop_and_the_zip_is_kept(app_world):
    client, SessionLocal, case_id, tmp_path, threads, detected = app_world
    archive = tmp_path / "bundle.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("Bundle/one.txt", "synthetic one")
        zf.writestr("Bundle/two.txt", "synthetic two")
    with archive.open("rb") as handle:
        response = client.post("/api/evidence/upload",
                               data={"case_id": str(case_id), "is_folder": "true", "is_archive": "true"},
                               files={"files": ("bundle.zip", handle, "application/zip")})
    assert response.status_code == 200, response.text
    seen = list(threads)
    assert sorted(f["original_filename"] for f in response.json()["files"]) == ["one.txt", "two.txt"]
    with SessionLocal() as db:
        rows = db.query(EvidenceFile).all()
        kept = {r.metadata_["original_archive_path"] for r in rows}
        assert len(kept) == 1 and open(kept.pop(), "rb").read() == archive.read_bytes()
        assert {r.metadata_["original_archive_sha256"] for r in rows} == {hashlib.sha256(archive.read_bytes()).hexdigest()}
    assert not (tmp_path / "evidence" / str(case_id) / "_staging").exists() or not any(
        (tmp_path / "evidence" / str(case_id) / "_staging").iterdir())
    _off_the_loop(seen)
