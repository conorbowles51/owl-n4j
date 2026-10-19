"""Synthetic candidate-review contention and authenticated HTTP round trip."""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from check_local_candidates import main as create_fixture
from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialAccount
from postgres.models.financial_candidates import FinancialCandidateReview, FinancialExtractionCandidate
from postgres.models.user import User
from services.financial.candidate_reviews import read_candidate_review, review_candidate
from services.financial.candidate_store import CandidateStoreError
from services.financial.decisions import Actor


def main():
    create_fixture()
    fixture = json.loads((ROOT / "data/local-runtime/candidate-check.json").read_text())
    case_id, mapping_id = UUID(fixture["case_id"]), UUID(fixture["mapping_id"])
    application = "loupe-review-check-" + uuid4().hex[:12]
    engine = create_engine("postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local",
                           connect_args={"application_name": application})
    with Session(engine) as session:
        candidate = session.scalar(select(FinancialExtractionCandidate).where(
            FinancialExtractionCandidate.mapping_id == mapping_id).order_by(FinancialExtractionCandidate.row_index))
        candidate_id = candidate.id
        original = read_candidate_review(session, case_id=case_id, candidate_id=candidate_id)
        file_id = session.scalar(select(EvidenceFile.id).where(EvidenceFile.case_id == case_id))
        user = session.scalar(select(User).where(User.email == "loupe-local@example.com"))
        actor = Actor(user.name, user.email, user.id)
        account = FinancialAccount(case_id=case_id, identity_key="synthetic-candidate-review", currency="GBP")
        session.add(account)
        session.commit()
        account_id = account.id
    reading = dict(account_id=str(account_id), currency="GBP", amount_minor="1234", direction="debit",
                   booking_date="2026-02-01", description="Synthetic reviewed reading")

    def decide(status):
        request = dict(expected_revision=original["review_revision"], status=status, reason="Synthetic contention check")
        if status == "resolved":
            request["reading"] = reading
        with Session(engine) as session:
            try:
                return 200, review_candidate(session, case_id=case_id, candidate_id=candidate_id, request=request, actor=actor)
            except CandidateStoreError as exc:
                return exc.status_code, str(exc)

    with Session(engine) as blocker, ThreadPoolExecutor(max_workers=2) as pool:
        blocker.execute(select(EvidenceFile.id).where(EvidenceFile.id == file_id).with_for_update()).all()
        futures = [pool.submit(decide, status) for status in ("resolved", "rejected")]
        try:
            waiting, deadline = 0, time.monotonic() + 10
            while waiting < 2 and time.monotonic() < deadline:
                with engine.connect() as connection:
                    waiting = connection.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE application_name=:app AND wait_event_type='Lock'"), {"app": application})
                if waiting < 2:
                    time.sleep(0.05)
            assert waiting == 2, "Both reviewers must demonstrably wait on the source lock"
        finally:
            blocker.rollback()
        results = [future.result(timeout=30) for future in futures]
    assert sorted(result[0] for result in results) == [200, 409]
    with httpx.Client(base_url="http://127.0.0.1:58002", timeout=30) as client:
        login = client.post("/api/auth/login", json={"username": "loupe-local@example.com", "password": "Loupe-local-test-2026"})
        login.raise_for_status()
        client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
        url = f"/api/financial/candidates/{candidate_id}/review"
        params = {"case_id": str(case_id)}
        response = client.get(url, params=params)
        response.raise_for_status()
        current = response.json()
        assert len(current["history"]) == 1
        assert current["original"] == original["original"]
        reopened = client.post(url, params=params, json=dict(expected_revision=current["review_revision"], status="pending", reason="Synthetic reopen"))
        reopened.raise_for_status()
        resolved = client.post(url, params=params, json=dict(expected_revision=reopened.json()["review_revision"], status="resolved", reason="Synthetic analyst amount correction", reading=reading))
        resolved.raise_for_status()
        final = resolved.json()
        assert final["status"] == "resolved" and final["reading"]["amount_minor"] == "1234"
        assert final["original"]["cells"][1]["text"] == "1234"
        assert len(final["history"]) == 3 and final["applied"] is False
        stale = client.post(url, params=params, json=dict(expected_revision=original["review_revision"], status="rejected", reason="Stale synthetic request"))
        assert stale.status_code == 409
    try:
        with engine.begin() as connection:
            connection.execute(update(FinancialCandidateReview).where(FinancialCandidateReview.candidate_id == candidate_id).values(reason="overwrite"))
    except DBAPIError as exc:
        assert "Extraction originals are immutable" in str(exc.orig)
    else:
        raise AssertionError("PostgreSQL permitted review history overwrite")
    summary = dict(case_id=str(case_id), mapping_id=str(mapping_id), candidate_id=str(candidate_id),
        account_id=str(account_id), observed_lock_waiters=waiting, competing_review_statuses=[200, 409],
        history_entries=3, final_status="resolved", applied=False, immutable_history="passed", authenticated_http="passed")
    (ROOT / "data/local-runtime/candidate-review-check.json").write_text(json.dumps(summary, indent=2)+"\n")
    print(json.dumps(summary, indent=2))
    engine.dispose()


if __name__ == "__main__":
    main()
