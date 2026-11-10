"""A row whose file is gone says so, in the list, the download and the daily check; and its copy comes back by hash."""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile, IngestionLog
from postgres.models.user import User
from services import evidence_file_check as check
from services.evidence_db_storage import EvidenceDBStorage


@pytest.fixture
def world(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[User.__table__, Case.__table__, EvidenceFile.__table__,
                                             IngestionLog.__table__, _folders()])
    root = tmp_path / "evidence"
    root.mkdir()
    (root / "marker").write_text("x")
    with Session(engine, expire_on_commit=False) as db:
        user = User(id=uuid.uuid4(), email="a@example.com", name="A", password_hash="x", global_role="user")
        case = Case(id=uuid.uuid4(), title="Case", created_by_user_id=user.id, owner_user_id=user.id)
        db.add_all([user, case])
        db.commit()
        yield db, root, case.id
    engine.dispose()


def _folders():
    from postgres.models.evidence import EvidenceFolder
    return EvidenceFolder.__table__


def _row(db, root, case_id, name, data=b"bytes", *, on_disk=True, metadata=None):
    path = root / name
    if on_disk:
        path.write_bytes(data)
    row = EvidenceFile(id=uuid.uuid4(), case_id=case_id, original_filename=name, stored_path=str(path), size=len(data),
                       sha256=hashlib.sha256(data).hexdigest(), status="unprocessed", metadata_=metadata or {})
    db.add(row)
    db.commit()
    return row


def test_a_row_with_no_file_is_marked_once_and_a_present_row_is_left_alone(world):
    db, root, case_id = world
    present = _row(db, root, case_id, "here.pdf")
    gone = _row(db, root, case_id, "gone.mp4", on_disk=False)

    first = check.check_files(db, root)
    assert (first.rows, first.missing, [r.id for r in first.new]) == (2, 1, [gone.id])
    db.refresh(gone), db.refresh(present)
    since = check.file_missing_since(gone)
    assert since and check.file_missing_since(present) is None
    assert [log.level for log in db.query(IngestionLog).filter_by(evidence_file_id=gone.id)] == ["error"]

    second = check.check_files(db, root)  # the same row is not news the next day, and keeps its first date
    assert (second.missing, second.new) == (1, [])
    db.refresh(gone)
    assert check.file_missing_since(gone) == since


def test_the_row_stays_and_a_dry_run_writes_nothing(world):
    db, root, case_id = world
    gone = _row(db, root, case_id, "gone.mp4", on_disk=False)
    result = check.check_files(db, root, apply=False)
    assert [r.id for r in result.new] == [gone.id]
    db.refresh(gone)
    assert check.file_missing_since(gone) is None and db.query(IngestionLog).count() == 0
    assert db.get(EvidenceFile, gone.id).deleted_at is None


def test_an_unmounted_disk_marks_nothing(world):
    db, root, case_id = world
    rows = [_row(db, root, case_id, f"{n}.pdf") for n in range(60)]
    for path in root.iterdir():
        path.unlink()
    assert "absent or empty" in check.check_files(db, root).refused
    (root / "marker").write_text("x")  # root there, nearly every file not: a half-mounted store reads the same
    result = check.check_files(db, root)
    assert "too many to be real" in result.refused
    for row in rows:
        db.refresh(row)
        assert check.file_missing_since(row) is None


def test_a_file_back_with_its_bytes_clears_the_mark_and_other_bytes_do_not(world):
    db, root, case_id = world
    good = _row(db, root, case_id, "good.pdf", b"good", on_disk=False)
    bad = _row(db, root, case_id, "bad.pdf", b"right", on_disk=False)
    check.check_files(db, root)
    (root / "good.pdf").write_bytes(b"good")
    (root / "bad.pdf").write_bytes(b"other content")
    result = check.check_files(db, root)
    assert [r.id for r in result.back] == [good.id] and [r.id for r in result.wrong_bytes] == [bad.id]
    db.refresh(good), db.refresh(bad)
    assert check.file_missing_since(good) is None and check.file_missing_since(bad)


def test_phone_rows_with_no_path_of_their_own_are_not_files(world):
    db, root, case_id = world
    db.add(EvidenceFile(id=uuid.uuid4(), case_id=case_id, original_filename="chat.txt", size=1, sha256="a" * 64,
                        stored_path=f"phone-text://{case_id}/chat", status="unprocessed"))
    db.commit()
    result = check.check_files(db, root)
    assert (result.rows, result.missing) == (0, 0)


def test_the_list_says_gone_without_touching_the_disk(world):
    db, root, case_id = world
    gone = _row(db, root, case_id, "gone.mp4", on_disk=False)
    check.check_files(db, root)
    db.refresh(gone)
    with patch("pathlib.Path.exists", side_effect=AssertionError("a list stats nothing")), \
            patch("os.stat", side_effect=AssertionError("a list stats nothing")):
        listed = EvidenceDBStorage._file_to_dict(gone)
    assert listed["file_missing_since"] == check.file_missing_since(gone)


def test_a_download_of_a_gone_file_says_what_happened(world):
    from routers import evidence
    from postgres.session import get_db
    from routers.evidence import _require_evidence_case_access, _require_evidence_object_access
    from routers.auth import get_current_user
    db, root, case_id = world
    gone = _row(db, root, case_id, "gone.mp4", on_disk=False)
    app = FastAPI()
    app.include_router(evidence.router)
    for dependency in (_require_evidence_case_access, _require_evidence_object_access, get_current_user):
        app.dependency_overrides[dependency] = lambda: {}
    app.dependency_overrides[evidence.get_current_db_user] = lambda: None
    app.dependency_overrides[get_db] = lambda: db
    with patch("routers.evidence.EVIDENCE_ROOT_DIR", root):
        response = TestClient(app).get(f"/api/evidence/{gone.id}/file")
    assert (response.status_code, response.json()["detail"]) == (404, check.FILE_MISSING_DETAIL)


def test_restore_takes_only_a_copy_with_the_row_hash_and_a_dry_run_moves_nothing(world, tmp_path):
    db, root, case_id = world
    gone = _row(db, root, case_id, "ELSUR.csv", b"the evidence", on_disk=False)
    lost = _row(db, root, case_id, "lost.xls", b"no copy here", on_disk=False)
    check.check_files(db, root)
    copies = tmp_path / "copies" / "job"
    copies.mkdir(parents=True)
    (copies / "renamed.csv").write_bytes(b"the evidence")
    (copies / "same-size.csv").write_bytes(b"not evidence")  # the size of both rows, the bytes of neither

    planned = {r.name: r for r in check.restore_files(db, case_id, root, [tmp_path / "copies"])}
    assert planned["ELSUR.csv"].outcome == "would restore" and planned["lost.xls"].outcome == "no copy found"
    assert not Path(gone.stored_path).exists()

    done = {r.name: r for r in check.restore_files(db, case_id, root, [tmp_path / "copies"], apply=True)}
    assert done["ELSUR.csv"].outcome == "restored"
    assert Path(gone.stored_path).read_bytes() == b"the evidence"
    assert [p.name for p in root.iterdir() if p.name.startswith(".")] == []
    db.refresh(gone), db.refresh(lost)
    assert check.file_missing_since(gone) is None and check.file_missing_since(lost)
    assert check.check_files(db, root).missing == 1


def test_restore_never_replaces_a_file_that_arrived_meanwhile(world, tmp_path):
    db, root, case_id = world
    gone = _row(db, root, case_id, "a.csv", b"bytes", on_disk=False)
    source = tmp_path / "copy.csv"
    source.write_bytes(b"bytes")
    target = Path(gone.stored_path)
    target.write_bytes(b"someone else")
    with pytest.raises(FileExistsError):
        check._place(source, target, gone.sha256)
    assert target.read_bytes() == b"someone else"


def test_the_daily_check_prints_its_result_last(world, capsys):
    """evidence-file-check.sh keeps the last line as the day's result; 9 Nov the signature line came after it and
    status.tsv read 'evidence-files ok: signatures: {}'."""
    from contextlib import contextmanager
    from scripts import evidence_file_check as cli

    db, root, case_id = world
    _row(db, root, case_id, "here.pdf")
    _row(db, root, case_id, "gone.pdf", on_disk=False)

    @contextmanager
    def session():
        yield db

    with patch.object(cli, "get_background_session", session), patch.object(cli, "EVIDENCE_DATA_ROOT", root), \
            patch.object(cli, "read_unread", lambda *a, **k: {"read": 0}):
        code = cli.check(dry_run=True)
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert code == cli.FOUND
    assert last == "ok: 2 rows checked, 1 have no file, 1 new, 0 back"
