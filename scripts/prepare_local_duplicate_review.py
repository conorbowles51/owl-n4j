"""Create a bounded synthetic duplicate review case; refuse repeat writes."""
import hashlib
import json
import sys
from pathlib import Path
from uuid import uuid4
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from tests.test_financial_duplicates import DuplicateTestCase
from postgres.models.case import Case
from postgres.models.user import User
from postgres.models.evidence import EvidenceFile
from postgres.models.enums import IngestionRunStatus
from services.financial.runs import open_ingestion_run

report_path=ROOT/'data/local-runtime/duplicate-bulk-review.json'
if report_path.exists(): raise RuntimeError('Duplicate fixture exists; inspect it without repeating writes.')
source=ROOT/'data/local-runtime/synthetic-duplicate-source.txt'
source.write_text('SYNTHETIC DUPLICATE COMPARISON ONLY\nGenerated account interpretations and postings, not bank evidence.\n')
digest=hashlib.sha256(source.read_bytes()).hexdigest()
engine=create_engine('postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local')
f=DuplicateTestCase();f.SessionLocal=sessionmaker(bind=engine,autoflush=False);f.db=f.SessionLocal()
try:
    f.user=f.db.scalar(select(User).where(User.email=='loupe-local@example.com'))
    f.case=Case(id=uuid4(),title='LOCAL TEST — paged duplicate and source-hash review',created_by_user_id=f.user.id,owner_user_id=f.user.id)
    f.db.add(f.case);f.db.commit()
    report=dict(case_id=str(f.case.id),status='started');report_path.write_text(json.dumps(report,indent=2))
    f.run=open_ingestion_run(case_id=f.case.id,actor=f.user,session_factory=f.SessionLocal)
    f._file_index=f._row_index=0
    ids=[]
    for index in range(12):
        f.account=f._account(f.case.id,identity_key=f'synthetic-duplicate-group-{index}')
        f.db.add(f.account);f.db.commit()
        for copy in range(2):
            doc=f.make_copy(sha256=digest,fingerprint=False)
            file=f.db.get(EvidenceFile,doc.evidence_file_id)
            file.sha256=digest
            file.stored_path=str(source);file.original_filename=f'Synthetic comparison {index+1}, copy {copy+1}.txt'
            f.db.commit();ids.append(str(doc.id))
    f.run.document_seen(24);f.run.transaction_admitted(48);f.run.terminate(IngestionRunStatus.completed)
    report.update(status='ready',document_ids=ids,documents=24,rows=48,reading_groups=12,source_sha256=digest)
    report_path.write_text(json.dumps(report,indent=2));print(json.dumps(report))
finally:
    f.db.close();engine.dispose()
