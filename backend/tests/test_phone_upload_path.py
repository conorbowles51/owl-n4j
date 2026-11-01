"""Phone report containers on the evidence side (01 sections 4.1 and 4.4): the container's evidence row is never
sent for processing or statement reading. Synthetic rows only."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.user import User


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[User.__table__, Case.__table__, EvidenceFolder.__table__,
                                             EvidenceFile.__table__])
    with Session(engine) as session:
        yield session
    engine.dispose()


def row(db, case_id, source_type, name):
    ef = EvidenceFile(case_id=case_id, original_filename=name, stored_path="/synthetic/" + name, size=1,
                      sha256=uuid4().hex * 2, status="unprocessed", source_type=source_type, metadata_={})
    db.add(ef)
    db.flush()
    return ef


def test_process_routes_refuse_only_a_selection_of_phone_reports_alone(db):
    """A phone report among ordinary files does not stop them (processing skips it and says so); a selection of
    nothing but phone reports is refused with the reason."""
    from routers.evidence import PHONE_PROCESS_REFUSED, _refuse_phone_containers
    case_id = uuid4()
    phone, ordinary = row(db, case_id, "phone_extraction", "Export.zip"), row(db, case_id, None, "notes.txt")
    _refuse_phone_containers(db, [str(ordinary.id), "not-a-uuid"])  # ordinary files pass
    _refuse_phone_containers(db, [str(ordinary.id), str(phone.id)])  # mixed: the ordinary file goes ahead
    with pytest.raises(HTTPException) as e:
        _refuse_phone_containers(db, [str(phone.id)])
    assert (e.value.status_code, e.value.detail) == (409, PHONE_PROCESS_REFUSED)
    assert PHONE_PROCESS_REFUSED == "Phone reports are read automatically when uploaded."


def test_a_folder_processed_as_a_whole_leaves_the_phone_report_out(db, monkeypatch):
    from services import evidence_processing_service as service
    case_id = uuid4()
    phone = row(db, case_id, "phone_extraction", "Handset")
    phone.status = "processing"  # as registered: the reading owns it
    monkeypatch.setattr(service.EvidenceDBStorage, "get_files_by_ids", lambda session, ids: [phone])
    out = service._prepare_files(db, case_id=case_id, file_ids=[phone.id], force_reprocess=False,
                                 preparation_mode="full", requested_by_user_id=None, ingestion_request_id="r")
    assert out["file_count"] == 0 and out["skipped_count"] == 1
    assert "1 phone report(s) are read automatically when uploaded" in out["message"]


def test_auto_read_never_marks_a_phone_report_row(monkeypatch):
    from services.financial import auto_read
    monkeypatch.setattr(auto_read, "detect_enabled", lambda: True)
    for source_type in ("phone_extraction", "cellebrite"):
        record = SimpleNamespace(original_filename="Export.pdf", source_type=source_type, metadata_={})
        auto_read.mark_registered(record)
        assert record.metadata_ == {}
    ordinary = SimpleNamespace(original_filename="statement.pdf", source_type=None, metadata_={})
    auto_read.mark_registered(ordinary)
    assert ordinary.metadata_[auto_read.MARK]["state"] == "pending"


def test_a_copy_interrupted_by_a_kill_leaves_nothing_that_changes_a_report_folder(tmp_path, monkeypatch):
    """copy_verified writes through a named temporary file; one left by a killed server is removed before the next
    finish copies or detects anything, so the folder's digest is over the report's own files only."""
    from routers import evidence_upload_groups as groups
    folder = tmp_path / "payload" / "Phone" / "files"
    folder.mkdir(parents=True)
    (folder / "a.jpg").write_bytes(b"one")
    leftover = folder / (groups.PARTIAL_PREFIX + "abc123")
    leftover.write_bytes(b"half")
    groups.remove_partials(tmp_path / "payload")
    assert sorted(p.name for p in folder.iterdir()) == ["a.jpg"]
    source = tmp_path / "src.bin"
    source.write_bytes(b"two!")
    import hashlib
    groups.copy_verified(source, folder / "b.bin", hashlib.sha256(b"two!").hexdigest(), 4)
    with pytest.raises(HTTPException):
        groups.copy_verified(source, folder / "c.bin", "0" * 64, 4)
    assert sorted(p.name for p in folder.iterdir()) == ["a.jpg", "b.bin"]  # no partial left on a refused copy
    groups.remove_partials(tmp_path / "missing")  # nothing there: no error


def test_with_the_engine_off_a_sync_still_finds_report_folders_locally(tmp_path, monkeypatch):
    from routers import evidence
    monkeypatch.setattr(evidence, "USE_EVIDENCE_ENGINE", False)
    report = tmp_path / "Report A"
    (report / "files" / "Image").mkdir(parents=True)
    (report / "report.xml").write_bytes(b'<?xml version="1.0"?><project xmlns="http://pa.cellebrite.com/report/2.0">')
    (report / "files" / "Image" / "inner.xml").write_bytes(b"<x/>")
    plain = tmp_path / "Statements"
    plain.mkdir()
    (plain / "notes.xml").write_bytes(b"<notes/>")
    staged = tmp_path / evidence._UPLOAD_STAGING_NAME / "Report B"
    staged.mkdir(parents=True)
    (staged / "report.xml").write_bytes((report / "report.xml").read_bytes())
    (tmp_path / "top.xml").write_bytes((report / "report.xml").read_bytes())
    assert evidence._phone_report_dirs("case", tmp_path) == {report}


def test_files_beside_a_report_folder_in_a_phone_zip_are_ordinary_evidence(tmp_path):
    import zipfile
    from routers import evidence_upload_groups as groups
    source = tmp_path / "phone.zip"
    with zipfile.ZipFile(source, "w") as z:
        z.writestr("Report/report.xml", b"<project/>")
        z.writestr("Report/files/a.jpg", b"img")
        z.writestr("Cover letter.txt", b"letter")
        z.writestr("Notes/list.csv", b"a,b")
        z.writestr("__MACOSX/._x", b"junk")
        z.writestr("phone.zip", b"same name as the container")
    root = tmp_path / "payload"
    readable = dict(outcome="readable", roots=[dict(root_path="Report")])
    out = groups.outside_report(source, root, readable, "phone.zip")
    assert sorted(m["path"] for m in out) == ["Cover letter.txt", "Notes/list.csv"]
    assert (root / "Notes" / "list.csv").read_bytes() == b"a,b" and not (root / "Report").exists()
    assert groups.outside_report(source, tmp_path / "p2", dict(outcome="readable", roots=[dict(root_path="")]),
                                 "phone.zip") == []
    assert groups.outside_report(source, tmp_path / "p3", dict(outcome="protected_or_invalid", roots=[]),
                                 "phone.zip") == []
    only_report = tmp_path / "only.zip"
    with zipfile.ZipFile(only_report, "w") as z:
        z.writestr("Report/report.xml", b"<project/>")
    assert groups.outside_report(only_report, tmp_path / "p4", readable, "only.zip") == []
