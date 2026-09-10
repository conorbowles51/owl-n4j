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

report_path=ROOT/'data/local-runtime/backward-review-check.json'
if report_path.exists(): raise RuntimeError('Network fixture exists; do not create it again.')
engine=create_engine('postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local')
f=DuplicateTestCase();f.SessionLocal=sessionmaker(bind=engine,autoflush=False);f.db=f.SessionLocal()
try:
    f.user=f.db.scalar(select(User).where(User.email=='loupe-local@example.com'))
    f.case=Case(id=uuid4(),title='LOCAL TEST — explicit backward timing trace',created_by_user_id=f.user.id,owner_user_id=f.user.id)
    f.db.add(f.case);f.db.commit()
    report={'case_id':str(f.case.id),'status':'started'};report_path.write_text(json.dumps(report,indent=2))
    accounts=[f._account(f.case.id,identity_key='synthetic-backward-'+label) for label in ['A','B','C']]
    f.account=accounts[0];f.db.add_all(accounts);f.db.commit()
    f.run=open_ingestion_run(case_id=f.case.id,actor=f.user,session_factory=f.SessionLocal)
    f._file_index=f._row_index=0
    source=ROOT/'data/local-runtime/synthetic-backward-source.txt'
    source.write_text('SYNTHETIC BACKWARD TIMING TEST ONLY. B receives100 January1 and sends60 toC January2; C pays20 January3. A receives two100deposits January4 and pays100 January5. Conditional links are test assumptions, not bank evidence.\n')
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    ids=[]
    movements=[(0,10000,'credit',4,'Root claim'),(0,10000,'credit',4,'Other funds'),(0,10000,'debit',5,'A sends to B'),(1,10000,'credit',1,'B receives from A'),(1,6000,'debit',2,'B sends to C'),(2,6000,'credit',2,'C receives from B'),(2,2000,'debit',3,'C pays outside scope')]
    for account_index,amount,direction,day,label in movements:
        account=accounts[account_index]
        document=f.make_document();period=f.make_period(document,account=account)
        row=f.add_row(period,document,account=account,amount=amount,direction=TransactionDirection(direction))
        file=f.db.get(EvidenceFile,document.evidence_file_id);file.stored_path=str(source);file.sha256=digest;file.original_filename=source.name
        document.sha256_at_ingestion=digest
        row.value_date=row.posted_date=row.effective_date=None
        row.proof_class='p3';row.description='Synthetic only — '+label
        row.transaction_date=row.ordering_date=date(2026,1,day)
        f.db.commit();ids.append(str(row.id))
    f.run.document_seen(7);f.run.transaction_admitted(7);f.run.terminate(IngestionRunStatus.completed)
    report.update(status='ready',ordered_ids=[ids[i] for i in (3,4,5,6,0,1,2)],account_ids=[str(a.id) for a in accounts],root_id=ids[0],pairs=[dict(debit_id=ids[2],credit_id=ids[3]),dict(debit_id=ids[4],credit_id=ids[5])])
    report_path.write_text(json.dumps(report,indent=2));print(json.dumps(report))

finally:
    f.db.close();engine.dispose()
