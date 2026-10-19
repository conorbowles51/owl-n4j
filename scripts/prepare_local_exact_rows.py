"""Create an isolated synthetic bigint transaction for exact HTTP/browser QA."""
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
        fixture.case=Case(id=uuid4(),title="LOCAL TEST — exact ledger money",created_by_user_id=fixture.user.id,owner_user_id=fixture.user.id)
        fixture.db.add(fixture.case);fixture.db.commit()
        fixture.account=fixture._account(fixture.case.id)
        fixture.db.add(fixture.account);fixture.db.commit()
        fixture.run=open_ingestion_run(case_id=fixture.case.id,actor=fixture.user,session_factory=fixture.SessionLocal)
        fixture._file_index=fixture._row_index=0
        document=fixture.make_document()
        period=fixture.make_period(document)
        row=fixture.add_row(period,document,amount=9007199254740993)
        row.running_balance_minor=-9223372036854775808
        fixture.db.commit()
        fixture.run.document_seen(1);fixture.run.transaction_admitted(1)
        fixture.run.terminate(IngestionRunStatus.completed)
        report=dict(case_id=str(fixture.case.id),transaction_id=str(row.id))
        (ROOT/"data/local-runtime/exact-rows-check.json").write_text(json.dumps(report,indent=2))
        print(json.dumps(report))
    finally:
        fixture.db.close();engine.dispose()

if __name__=="__main__":main()
