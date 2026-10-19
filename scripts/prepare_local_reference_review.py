"""Create an isolated synthetic cross-account tracing case; refuses repeat writes."""
import hashlib
from datetime import date
import json
import sys
from pathlib import Path
from uuid import uuid4
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from tests.test_financial_duplicates import DuplicateTestCase
from postgres.models.evidence import EvidenceFile
from postgres.models.case import Case
from postgres.models.user import User
from postgres.models.enums import IngestionRunStatus, TransactionDirection
from services.financial.runs import open_ingestion_run

report_path=ROOT/'data/local-runtime/reference-review-check.json'
if report_path.exists(): raise RuntimeError('Network fixture exists; do not create it again.')
engine=create_engine('postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local')
f=DuplicateTestCase();f.SessionLocal=sessionmaker(bind=engine,autoflush=False);f.db=f.SessionLocal()
try:
    f.user=f.db.scalar(select(User).where(User.email=='loupe-local@example.com'))
    f.case=Case(id=uuid4(),title='LOCAL TEST — payment identifier review',created_by_user_id=f.user.id,owner_user_id=f.user.id)
    f.db.add(f.case);f.db.commit()
    report={'case_id':str(f.case.id),'status':'started'};report_path.write_text(json.dumps(report,indent=2))
    accounts=[f._account(f.case.id,identity_key='synthetic-reference-'+label) for label in ['A','B','C']]
    f.account=accounts[0];f.db.add_all(accounts);f.db.commit()
    f.run=open_ingestion_run(case_id=f.case.id,actor=f.user,session_factory=f.SessionLocal)
    f._file_index=f._row_index=0
    ids=[]
    source=ROOT/'data/local-runtime/synthetic-reference-source.txt'
    source.write_text('SYNTHETIC IDENTIFIER ACCEPTANCE ONLY.\nA pays100 onJanuary1; B receives100 onJanuary20 with shared UUID. C records101 with the same UUID, retained as conflict. Not bank evidence.\n')
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    movements=[(0,10000,'debit',1,'Payer'),(1,10000,'credit',20,'Payee'),(2,10100,'credit',20,'Conflicting amount')]
    for account_index,amount,direction,day,label in movements:
        account=accounts[account_index]
        document=f.make_document();period=f.make_period(document,account=account)
        row=f.add_row(period,document,account=account,amount=amount,direction=TransactionDirection(direction))
        file=f.db.get(EvidenceFile,document.evidence_file_id)
        file.stored_path=str(source);file.sha256=digest;file.original_filename=source.name
        document.sha256_at_ingestion=digest
        row.bank_reference='28a7c567-7115-4462-958a-e6db7e3a9552'
        row.posted_date=row.value_date=row.effective_date=None
        row.proof_class='p3';row.description='Synthetic only — '+label
        row.transaction_date=row.ordering_date=date(2026,1,day)
        f.db.commit();ids.append(str(row.id))
    f.run.document_seen(3);f.run.transaction_admitted(3);f.run.terminate(IngestionRunStatus.completed)
    report.update(status='ready',ordered_ids=ids,account_ids=[str(a.id) for a in accounts],pairs=[dict(debit_id=ids[0],credit_id=ids[1])])
    report_path.write_text(json.dumps(report,indent=2));print(json.dumps(report))

finally:
    f.db.close();engine.dispose()
