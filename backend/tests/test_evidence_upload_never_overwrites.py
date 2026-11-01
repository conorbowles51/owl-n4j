"""The old upload route never replaces a different file that already has the same name."""
from __future__ import annotations

import hashlib
from pathlib import Path

from postgres.models.evidence import EvidenceFile
from tests.test_evidence_upload_off_event_loop import app_world  # noqa: F401  (fixture)


def _upload(client, case_id, name, data):
    return client.post("/api/evidence/upload", data={"case_id": str(case_id)},
                       files={"files": (name, data, "application/pdf")})


def test_a_second_file_with_the_same_name_is_kept_beside_the_first(app_world):
    client, SessionLocal, case_id, tmp_path, threads, _ = app_world
    first, second = b"%PDF-1.4 first statement", b"%PDF-1.4 second, different statement"
    assert _upload(client, case_id, "statement.pdf", first).status_code == 200
    assert _upload(client, case_id, "statement.pdf", second).status_code == 200
    with SessionLocal() as db:
        rows = db.query(EvidenceFile).order_by(EvidenceFile.created_at).all()
        assert [r.original_filename for r in rows] == ["statement.pdf", "statement.pdf"]
        paths = [Path(r.stored_path) for r in rows]
        assert paths[0] != paths[1]
        assert paths[1].name == "statement (2).pdf"
        for row, path in zip(rows, paths):
            # Every row's file on disk holds the bytes the row was registered with.
            assert hashlib.sha256(path.read_bytes()).hexdigest() == row.sha256
        assert paths[0].read_bytes() == first


def test_the_same_bytes_again_keep_the_one_file(app_world):
    client, SessionLocal, case_id, tmp_path, threads, _ = app_world
    data = b"%PDF-1.4 same statement"
    assert _upload(client, case_id, "statement.pdf", data).status_code == 200
    assert _upload(client, case_id, "statement.pdf", data).status_code == 200
    with SessionLocal() as db:
        paths = {Path(r.stored_path) for r in db.query(EvidenceFile)}
    assert len(paths) == 1 and next(iter(paths)).read_bytes() == data
    assert not (next(iter(paths)).parent / "statement (2).pdf").exists()
