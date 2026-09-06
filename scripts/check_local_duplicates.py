"""Exercise real HTTP/PG duplicate decisions using synthetic local-only fixtures.

Run with data/local-runtime/backend-venv/bin/python. Leaves its labelled case
available for browser inspection. Never accepts another database or API target.
"""
import sys
import uuid
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import httpx
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from tests.test_financial_duplicates import DuplicateTestCase
from postgres.models.case import Case
from postgres.models.user import User
from postgres.models.financial import AdjudicationEvent, FinancialTransaction, FinancialSourceDocument
from services.financial.runs import open_ingestion_run
from services.financial.duplicate_decisions import duplicate_revision, decide_duplicate, DuplicateDecisionError
from services.financial.decisions import Actor


def main():
    engine = create_engine("postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local")
    client = httpx.Client(base_url="http://127.0.0.1:58002", timeout=30)
    email, password = "loupe-local@example.com", "Loupe-local-test-2026"
    if client.get("/api/setup/status").json()["needs_setup"]:
        response = client.post("/api/setup/initial-user", json={"email": email, "name": "Local Tester", "password": password})
        response.raise_for_status()
    login = client.post("/api/auth/login", json={"username": email, "password": password})
    login.raise_for_status()
    client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
    fixture = DuplicateTestCase()
    fixture.SessionLocal = sessionmaker(bind=engine, autoflush=False)
    fixture.db = fixture.SessionLocal()
    try:
        fixture.user = fixture.db.scalar(select(User).where(User.email == email))
        fixture.case = Case(id=uuid.uuid4(), title="LOCAL TEST — duplicate decisions", created_by_user_id=fixture.user.id, owner_user_id=fixture.user.id)
        fixture.db.add(fixture.case)
        fixture.db.commit()
        fixture.account = fixture._account(fixture.case.id)
        fixture.db.add(fixture.account)
        fixture.db.commit()
        fixture.run = open_ingestion_run(case_id=fixture.case.id, actor=fixture.user, session_factory=fixture.SessionLocal)
        fixture._file_index = fixture._row_index = 0
        copy, primary = fixture.make_copy(), fixture.make_copy()
        case_id = str(fixture.case.id)
        copy_id, primary_id = copy.id, primary.id
        payload = {"action": "exclude", "reason": "Synthetic PostgreSQL concurrency check", "expected_revision": duplicate_revision(fixture.db, copy), "primary_id": str(primary_id), "expected_primary_revision": duplicate_revision(fixture.db, primary)}
        fixture.db.rollback()  # Do not leave a fixture transaction open across HTTP.
        path = f"/api/financial/documents/{copy_id}/duplicate-decision?case_id={case_id}"
        barrier = Barrier(2)
        def submit():
            barrier.wait(timeout=10)
            return client.post(path, json=payload)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: submit(), range(2)))
        assert sorted(r.status_code for r in responses) == [200, 409], [(r.status_code, r.text) for r in responses]
        fixture.db.expire_all()
        events = list(fixture.db.scalars(select(AdjudicationEvent).where(AdjudicationEvent.case_id == fixture.case.id)))
        assert len(events) == 1
        assert events[0].actor_user_id == fixture.user.id
        fixture.db.refresh(copy)
        restore = {"action": "restore", "reason": "Synthetic round-trip restoration", "expected_revision": duplicate_revision(fixture.db, copy)}
        fixture.db.rollback()
        result = client.post(path, json=restore)
        assert result.status_code == 200, result.text
        fixture.db.expire_all()
        rows = list(fixture.db.scalars(select(FinancialTransaction).where(FinancialTransaction.source_document_id.in_([copy_id, primary_id]))))
        assert len(rows) == 4 and all(row.ledger_status == "admitted" for row in rows)
        events = list(fixture.db.scalars(select(AdjudicationEvent).where(AdjudicationEvent.case_id == uuid.UUID(case_id))))
        assert len(events) == 2
        # HTTP handlers can serialize in one event loop. Exercise actual separate
        # PG connections too, proving that both writers wait on a held row lock.
        fixture.db.refresh(copy)
        fixture.db.refresh(primary)
        args = dict(case_id=uuid.UUID(case_id), document_id=copy_id, action="exclude",
                    reason="Synthetic overlapping PostgreSQL writers",
                    expected_revision=duplicate_revision(fixture.db, copy),
                    primary_id=primary_id, expected_primary_revision=duplicate_revision(fixture.db, primary),
                    actor=Actor(name=fixture.user.name, email=fixture.user.email, user_id=fixture.user.id))
        fixture.db.rollback()
        race_engine = create_engine(engine.url, connect_args={"application_name": "loupe-local-duplicate-race"})
        race_sessions = sessionmaker(bind=race_engine)
        def write_decision():
            with race_sessions() as session:
                try:
                    return decide_duplicate(session, **args)["applied"]
                except DuplicateDecisionError as exc:
                    return exc.status_code
        try:
            with engine.connect() as blocker, ThreadPoolExecutor(max_workers=2) as pool:
                transaction = blocker.begin()
                blocker.execute(select(FinancialSourceDocument.id).where(FinancialSourceDocument.id.in_([copy_id, primary_id])).order_by(FinancialSourceDocument.id).with_for_update()).all()
                futures = [pool.submit(write_decision) for _ in range(2)]
                try:
                    deadline = time.monotonic() + 10
                    waiting = 0
                    while time.monotonic() < deadline:
                        with engine.connect() as observer:
                            waiting = observer.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE application_name = 'loupe-local-duplicate-race' AND wait_event_type = 'Lock'"))
                        if waiting == 2:
                            break
                        time.sleep(0.05)
                    assert waiting == 2, "Both writers must demonstrably wait on PostgreSQL locks"
                finally:
                    transaction.rollback()
                assert sorted(f.result(timeout=15) for f in futures) == [True, 409]
        finally:
            race_engine.dispose()
        fixture.db.expire_all()
        fixture.db.refresh(copy)
        restore["expected_revision"] = duplicate_revision(fixture.db, copy)
        fixture.db.rollback()
        result = client.post(path, json=restore)
        assert result.status_code == 200, result.text
        print(f"PASS: HTTP exclusion 200/409 and restoration; two PG writers observed waiting on locks, exactly one applied; restored again. Case {case_id}")
    finally:
        fixture.db.close()
        engine.dispose()
        client.close()


if __name__ == "__main__":
    main()
