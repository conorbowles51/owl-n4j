"""Prepare a fresh synthetic PDF's reviewed rows for the finalization UI check."""
import json
import sys
from pathlib import Path
from uuid import UUID
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from check_local_candidates import main as create_fixture
from postgres.models.financial import FinancialAccount
from postgres.models.financial_candidates import FinancialExtractionCandidate
from postgres.models.user import User
from services.financial.candidate_reviews import read_candidate_review, review_candidate
from services.financial.decisions import Actor

def main():
    create_fixture()
    fixture=json.loads((ROOT/"data/local-runtime/candidate-check.json").read_text())
    case,mapping=UUID(fixture["case_id"]),UUID(fixture["mapping_id"])
    engine=create_engine("postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local")
    with Session(engine) as session:
        user=session.scalar(select(User).where(User.email=="loupe-local@example.com"))
        actor=Actor(user.name,user.email,user.id)
        account=FinancialAccount(case_id=case,identity_key="synthetic-finalization-ui",currency="GBP")
        session.add(account);session.commit()
        account_id=account.id
        candidates=list(session.scalars(select(FinancialExtractionCandidate.id).where(FinancialExtractionCandidate.mapping_id==mapping)))
    for candidate in candidates:
        with Session(engine) as session:
            state=read_candidate_review(session,case_id=case,candidate_id=candidate)
            review_candidate(session,case_id=case,candidate_id=candidate,actor=actor,
                request=dict(expected_revision=state["review_revision"],status="resolved",reason="Synthetic UI preparation",
                    reading=dict(account_id=str(account_id),currency="GBP",amount_minor="1234",direction="debit",booking_date="2026-02-01",description="Synthetic finalization UI reading")))
    engine.dispose()
    print("Fresh synthetic readings resolved; not yet finalized.")
if __name__=="__main__":main()
