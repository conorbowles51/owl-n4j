"""Opt-in real PostgreSQL: the engine jobs poll's recheck skips re-reading a case's records while none of its
evidence rows has been written since the settled reconcile, and reconciles again after any write."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from services import evidence_job_sync

pytestmark = pytest.mark.skipif(os.getenv("LOUPE_TEST_LOCAL_POSTGRES") != "1",
                                reason="Requires isolated local PostgreSQL")


@pytest.fixture()
def Session():
    url = make_url(os.environ["LOUPE_TEST_LOCAL_POSTGRES_URL"])
    assert url.host in {"127.0.0.1", "localhost"}, "local PostgreSQL only"
    engine = create_engine(url, future=True)
    schema = f"jobs_poll_{uuid4().hex[:8]}"
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, future=True, connect_args={"options": f"-csearch_path={schema}"})
    with engine.begin() as conn:
        # Stand-ins for the referenced tables: only the evidence rows matter here.
        conn.execute(text("CREATE TABLE cases (id uuid PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE users (id uuid PRIMARY KEY)"))
    Base.metadata.create_all(engine, tables=[EvidenceFolder.__table__, EvidenceFile.__table__])
    evidence_job_sync._poll_settled.clear()
    yield sessionmaker(bind=engine, future=True)
    evidence_job_sync._poll_settled.clear()
    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    engine.dispose()


def test_recheck_skips_until_a_row_of_the_case_is_written(Session, monkeypatch):
    case_id = uuid4()
    with Session() as db:
        db.execute(text("INSERT INTO cases (id) VALUES (:id)"), dict(id=case_id))
        record = EvidenceFile(id=uuid4(), case_id=case_id, original_filename="a.pdf", stored_path="/tmp/a.pdf",
                              size=1, sha256="a" * 64, status="processing")
        db.add(record)
        db.commit()
        file_id = record.id
    calls = []
    real = evidence_job_sync._reconcile
    monkeypatch.setattr(evidence_job_sync, "_reconcile", lambda db, jobs, **kw: calls.append(1) or real(db, jobs, **kw))
    monkeypatch.setattr(evidence_job_sync, "POLL_RECHECK_SECONDS", 0.0)
    job = dict(id=str(uuid4()), source_evidence_file_id=str(file_id), status="completed", entity_count=3)

    with Session() as db:
        assert evidence_job_sync.reconcile_case_poll(db, str(case_id), [job]) == 1
        assert evidence_job_sync.reconcile_case_poll(db, str(case_id), [job]) == 0  # own write renewed the version
        assert len(calls) == 2
        for _ in range(3):
            assert evidence_job_sync.reconcile_case_poll(db, str(case_id), [job]) == 0
        assert len(calls) == 2
        db.commit()

    # Another writer puts the record back; the next recheck must see it and repair it.
    with Session() as other:
        other.execute(text("UPDATE evidence_files SET status = 'failed', entity_count = 0 WHERE id = :id"),
                      dict(id=file_id))
        other.commit()
    with Session() as db:
        assert evidence_job_sync.reconcile_case_poll(db, str(case_id), [job]) == 1
        assert len(calls) == 3
        assert (db.get(EvidenceFile, file_id).status, db.get(EvidenceFile, file_id).entity_count) == ("processed", 3)
        db.commit()

    # A new row in the case also changes the version.
    with Session() as db:
        assert evidence_job_sync.reconcile_case_poll(db, str(case_id), [job]) == 0
        assert len(calls) == 4
        assert evidence_job_sync.reconcile_case_poll(db, str(case_id), [job]) == 0
        assert len(calls) == 4
        db.add(EvidenceFile(id=uuid4(), case_id=case_id, original_filename="b.pdf", stored_path="/tmp/b.pdf",
                            size=1, sha256="b" * 64, status="processed"))
        db.commit()
        evidence_job_sync.reconcile_case_poll(db, str(case_id), [job])
        assert len(calls) == 5
