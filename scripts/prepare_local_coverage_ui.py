"""Create two isolated synthetic accounts with printed period bounds for coverage QA."""
import json
import sys
from datetime import date
from pathlib import Path
from uuid import uuid4
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from tests.test_financial_duplicates import DuplicateTestCase
from postgres.models.case import Case
from postgres.models.user import User
from postgres.models.enums import IngestionRunStatus
from services.financial.runs import open_ingestion_run
from services.financial.periods import PeriodBounds


def main():
    engine=create_engine("postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local")
    fixture=DuplicateTestCase();fixture.SessionLocal=sessionmaker(bind=engine,autoflush=False)
    fixture.db=fixture.SessionLocal()
    try:
        fixture.user=fixture.db.scalar(select(User).where(User.email=="loupe-local@example.com"))
        fixture.case=Case(id=uuid4(),title="LOCAL TEST — statement coverage",created_by_user_id=fixture.user.id,owner_user_id=fixture.user.id)
        fixture.db.add(fixture.case);fixture.db.commit()
        fixture.account=fixture._account(fixture.case.id)
        fixture.account.metadata_={"display_label":"Synthetic account with February gap"}
        other=fixture._account(fixture.case.id,identity_key="synthetic-coverage-second")
        other.metadata_={"display_label":"Synthetic account with enclosing export"}
        fixture.db.add_all([fixture.account,other]);fixture.db.commit()
        fixture.run=open_ingestion_run(case_id=fixture.case.id,actor=fixture.user,session_factory=fixture.SessionLocal)
        fixture._file_index=fixture._row_index=0
        for account in (fixture.account,other):
            for start,end in ((date(2026,1,1),date(2026,1,31)),(date(2026,3,1),date(2026,3,31))):
                fixture.make_copy(account=account,bounds=PeriodBounds.printed(start,end))
        fixture.make_copy(account=other,bounds=PeriodBounds.printed(date(2026,1,1),date(2026,3,31)))
        fixture.db.commit()
        fixture.run.document_seen(5);fixture.run.transaction_admitted(10)
        fixture.run.terminate(IngestionRunStatus.completed)
        report=dict(case_id=str(fixture.case.id),gap_account_id=str(fixture.account.id),enclosing_account_id=str(other.id))
        (ROOT/"data/local-runtime/coverage-check.json").write_text(json.dumps(report,indent=2))
        print(json.dumps(report))
    finally:
        fixture.db.close();engine.dispose()

if __name__=="__main__":main()
