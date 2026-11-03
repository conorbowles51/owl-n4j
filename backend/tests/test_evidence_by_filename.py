"""A file name several files share is a choice, never a guess (followups m110318372022092).

Live 2026-11-03: 1,161 names are shared by 3,991 evidence files, 282 names exist in more than one case. The old
lookup returned the first row by name (.limit(1)), and the backfill lookup did not even look in the right case.
"""
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
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
from services.evidence_db_storage import EvidenceDBStorage as Storage


@pytest.fixture
def f(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[User.__table__, Case.__table__, EvidenceFolder.__table__,
                                             EvidenceFile.__table__])
    with Session(engine) as db:
        case_id, other_case = uuid4(), uuid4()
        clock = iter(range(1, 60))

        def file(name, case=None, path=None, sha="a", **kwargs):
            row = EvidenceFile(case_id=case or case_id, original_filename=name, stored_path=path or "/nowhere",
                               sha256=sha * 64, created_at=datetime(2026, 1, next(clock)), **kwargs)
            db.add(row)
            db.flush()
            return row

        yield SimpleNamespace(db=db, engine=engine, case=case_id, other=other_case, file=file, tmp=tmp_path)
    engine.dispose()


def test_a_shared_name_finds_no_single_file(f):
    first, second = f.file("statement.pdf", sha="a"), f.file("statement.pdf", sha="b")
    assert Storage.find_by_filename(f.db, "statement.pdf", f.case) is None
    assert [r.id for r in Storage.find_all_by_filename(f.db, "statement.pdf", f.case)] == [first.id, second.id]


def test_one_visible_file_is_found_and_other_cases_and_thread_documents_do_not_count(f):
    mine = f.file("letter.pdf")
    f.file("letter.pdf", case=f.other)
    f.file("letter.pdf", sha="c", source_type="phone_text")
    assert Storage.find_by_filename(f.db, "letter.pdf", f.case).id == mine.id


def _endpoints(f):
    from routers import evidence
    return evidence, patch.object(evidence, "_check_engine_jobs_access", lambda *a, **k: None)


def test_by_filename_and_summary_answer_409_with_the_candidates(f):
    first, second = f.file("statement.pdf", sha="a", summary="one"), f.file("statement.pdf", sha="b", summary="two")
    evidence, access = _endpoints(f)
    with access:
        for call in (evidence.get_evidence_by_filename, evidence.get_document_summary):
            with pytest.raises(HTTPException) as err:
                call("statement.pdf", case_id=str(f.case), evidence_file_id=None, current_user=None, db=f.db)
            assert err.value.status_code == 409
            assert [c["evidence_file_id"] for c in err.value.detail["candidates"]] == [str(first.id), str(second.id)]
        chosen = evidence.get_evidence_by_filename("statement.pdf", case_id=str(f.case),
                                                   evidence_file_id=str(second.id), current_user=None, db=f.db)
        assert chosen["evidence_id"] == str(second.id)
        summary = evidence.get_document_summary("statement.pdf", case_id=str(f.case),
                                                evidence_file_id=str(second.id), current_user=None, db=f.db)
        assert summary["summary"] == "two" and summary["evidence_file_id"] == str(second.id)
        assert evidence.get_evidence_by_filename("absent.pdf", case_id=str(f.case), evidence_file_id=None,
                                                 current_user=None, db=f.db)["found"] is False


def test_by_filename_checks_the_case_is_visible_to_the_user(f):
    from routers import evidence
    f.file("letter.pdf")

    def refuse(*_a, **_k):
        raise HTTPException(status_code=403, detail="no")

    with patch.object(evidence, "_check_engine_jobs_access", refuse), pytest.raises(HTTPException) as err:
        evidence.get_evidence_by_filename("letter.pdf", case_id=str(f.case), evidence_file_id=None,
                                          current_user=None, db=f.db)
    assert err.value.status_code == 403


def test_backfill_reads_only_the_documents_own_case_and_never_guesses(f):
    from routers import backfill
    elsewhere = f.tmp / "elsewhere.pdf"
    elsewhere.write_text("other case")
    f.file("report.pdf", case=f.other, path=str(elsewhere))
    (f.tmp / str(f.other)).mkdir()
    (f.tmp / str(f.other) / "report.pdf").write_text("other case on disk")
    a, b = f.tmp / "a.pdf", f.tmp / "b.pdf"
    a.write_text("a")
    b.write_text("b")
    f.file("twice.pdf", path=str(a), sha="a")
    f.file("twice.pdf", path=str(b), sha="b")
    f.file("once.pdf", path=str(a), sha="c")

    @contextmanager
    def session():
        yield f.db

    with patch.object(backfill, "get_background_session", session), patch.object(backfill, "EVIDENCE_ROOT_DIR", f.tmp):
        assert backfill.find_evidence_file("report.pdf", str(f.case)) is None
        assert backfill.find_evidence_file("twice.pdf", str(f.case)) is None
        assert backfill.find_evidence_file("once.pdf", str(f.case)) == a
        assert backfill.find_evidence_file("once.pdf", "") is None
