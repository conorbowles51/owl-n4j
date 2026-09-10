"""Create an isolated synthetic transfer comparison case; refuses repeat writes."""
import json
import sys
from pathlib import Path
from uuid import uuid4
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from tests.test_financial_duplicates import DuplicateTestCase
from postgres.models.case import Case
from postgres.models.user import User
from postgres.models.enums import IngestionRunStatus, TransactionDirection
from services.financial.runs import open_ingestion_run

report_path=ROOT/'data/local-runtime/transfer-review-check.json'
if report_path.exists(): raise RuntimeError('Transfer fixture exists; do not create it again.')
engine=create_engine('postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local')
f=DuplicateTestCase();f.SessionLocal=sessionmaker(bind=engine,autoflush=False);f.db=f.SessionLocal()
try:
    f.user=f.db.scalar(select(User).where(User.email=='loupe-local@example.com'))
    f.case=Case(id=uuid4(),title='LOCAL TEST — transfer scenario',created_by_user_id=f.user.id,owner_user_id=f.user.id)
    f.db.add(f.case);f.db.commit()
    report={'case_id':str(f.case.id),'status':'started'};report_path.write_text(json.dumps(report,indent=2))
    f.account=f._account(f.case.id,identity_key='transfer-source');other=f._account(f.case.id,identity_key='transfer-destination')
    f.db.add_all([f.account,other]);f.db.commit()
    f.run=open_ingestion_run(case_id=f.case.id,actor=f.user,session_factory=f.SessionLocal)
    f._file_index=f._row_index=0
    ids=[]
    for account,direction in [(f.account,TransactionDirection.debit),(other,TransactionDirection.credit)]:
        document=f.make_document();period=f.make_period(document,account=account)
        row=f.add_row(period,document,account=account,amount=1234567890123456,direction=direction)
        row.proof_class='p3';row.description='Synthetic matching transfer — no real bank evidence';f.db.commit();ids.append(str(row.id))
    f.run.document_seen(2);f.run.transaction_admitted(2);f.run.terminate(IngestionRunStatus.completed)
    report.update(status='ready',debit_id=ids[0],credit_id=ids[1],amount_minor='1234567890123456');report_path.write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    f.db.close();engine.dispose()
