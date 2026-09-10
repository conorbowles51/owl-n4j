"""Real PostgreSQL rollback and concurrent candidate materialization, synthetic only."""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from check_local_candidates import main as create_fixture
from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialAccount, FinancialSourceDocument, FinancialTransaction
from postgres.models.financial_candidates import FinancialExtractionCandidate, FinancialCandidateFinalization
from postgres.models.user import User
from services.financial import candidate_materialization as module
from services.financial.candidate_reviews import read_candidate_review, review_candidate
from services.financial.candidate_store import CandidateStoreError
from services.financial.decisions import Actor


def main(fixture_report="candidate-check.json", result_report="candidate-materialization-check.json"):
    create_fixture(report_name=fixture_report)
    fixture = json.loads((ROOT / "data/local-runtime" / fixture_report).read_text())
    case_id, mapping_id = UUID(fixture["case_id"]), UUID(fixture["mapping_id"])
    application = "loupe-materialization-" + uuid4().hex[:12]
    engine = create_engine("postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local",
                           connect_args={"application_name": application})
    sessions = sessionmaker(bind=engine)
    with sessions() as session:
        file_id = session.scalar(select(EvidenceFile.id).where(EvidenceFile.case_id == case_id))
        user = session.scalar(select(User).where(User.email == "loupe-local@example.com"))
        actor = Actor(user.name, user.email, user.id)
        account = FinancialAccount(case_id=case_id, identity_key="synthetic-materialization", currency="GBP")
        session.add(account); session.commit()
        account_id = account.id
        candidates = list(session.scalars(select(FinancialExtractionCandidate.id).where(
            FinancialExtractionCandidate.mapping_id == mapping_id).order_by(FinancialExtractionCandidate.row_index)))
    for candidate_id in candidates:
        with sessions() as session:
            state = read_candidate_review(session, case_id=case_id, candidate_id=candidate_id)
            review_candidate(session, case_id=case_id, candidate_id=candidate_id, actor=actor,
                request=dict(expected_revision=state["review_revision"], status="resolved", reason="Synthetic exact-amount review",
                    reading=dict(account_id=str(account_id), currency="GBP", amount_minor="1234", direction="debit",
                        booking_date="2026-02-01", description="Synthetic identical reading on distinct source row")))
    with sessions() as session:
        preview = module.preview_candidate_finalization(session, case_id=case_id,evidence_file_id=file_id,resolve_path=Path)
    request = dict(expected_revision=preview["revision"], documentary_financial_rows=True,
        accept_incomplete_coverage=True, reason="Synthetic documentary financial rows with incomplete coverage")

    def finalize():
        return module.finalize_candidates(session_factory=sessions, case_id=case_id,
            evidence_file_id=file_id, request=request, actor=actor, resolve_path=Path)

    original_receipt = module._receipt
    def fail_after_flush(*args, **kwargs):
        original_receipt(*args, **kwargs)
        raise RuntimeError("Synthetic fault after transaction/link flush")
    with patch.object(module, "_receipt", side_effect=fail_after_flush):
        try:
            finalize()
        except RuntimeError as exc:
            assert "Synthetic fault" in str(exc)
        else:
            raise AssertionError("Injected failure did not occur")
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(FinancialSourceDocument).where(
            FinancialSourceDocument.evidence_file_id == file_id)) == 0
        assert session.scalar(select(func.count()).select_from(FinancialCandidateFinalization).where(
            FinancialCandidateFinalization.evidence_file_id == file_id)) == 0

    with sessions() as blocker, ThreadPoolExecutor(max_workers=2) as pool:
        blocker.execute(select(EvidenceFile.id).where(EvidenceFile.id == file_id).with_for_update()).all()
        futures = [pool.submit(finalize) for _ in range(2)]
        try:
            waiting, deadline = 0, time.monotonic() + 15
            while waiting < 2 and time.monotonic() < deadline:
                with engine.connect() as observer:
                    waiting = observer.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE application_name=:app AND wait_event_type='Lock'"), {"app": application})
                if waiting < 2: time.sleep(0.05)
            assert waiting == 2, "Both finalizers must demonstrably wait on locks"
        finally:
            blocker.rollback()
        results = [future.result(timeout=60) for future in futures]
    assert sorted(result["created"] for result in results) == [False, True]
    assert results[0]["finalization_id"] == results[1]["finalization_id"]
    assert results[0]["transactions"] == results[1]["transactions"]
    repeated = finalize()
    assert repeated["created"] is False and repeated["transactions"] == results[0]["transactions"]
    with sessions() as session:
        rows = list(session.scalars(select(FinancialTransaction).where(FinancialTransaction.case_id == case_id)))
        assert len(rows) == 2 and len({row.ref_id for row in rows}) == 2
        assert [row.amount_minor for row in rows] == [1234, 1234]
        assert {row.proof_class for row in rows} == {"p3"}
        assert {row.extraction_layer for row in rows} == {4}
        state = read_candidate_review(session,case_id=case_id,candidate_id=candidates[0])
        try:
            review_candidate(session,case_id=case_id,candidate_id=candidates[0],actor=actor,
                request=dict(expected_revision=state["review_revision"],status="pending",reason="Try reopening finalized source"))
        except CandidateStoreError as exc:
            assert exc.status_code == 409 and "finalized" in str(exc)
        else: raise AssertionError("Finalized review reopened")
    report = dict(**repeated,
                  concurrent_waiters=waiting, failure_rolled_back=True)
    (ROOT / "data/local-runtime" / result_report).write_text(json.dumps(report, indent=2))
    print("PASS: atomic rollback; two concurrent waiters; one receipt; two exact P3 transactions; retry and review seal.")
    print(json.dumps(report, indent=2))
    engine.dispose()


if __name__ == "__main__": main()
