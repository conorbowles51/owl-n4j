"""Verify PostgreSQL repeatable-read export against concurrent synthetic decisions."""
import sys,json,hashlib
from pathlib import Path
from uuid import UUID
from unittest.mock import patch
from datetime import datetime,timezone
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root/'backend'))
from postgres.models.financial import FinancialTransaction
from postgres.models.user import User
from services.financial.ledger_snapshot import capture_ledger_export
import importlib
snapshots=importlib.import_module('services.financial.ledger_snapshot')
from services.financial.quarantine_row import quarantine_case_row,release_case_row
fixture=json.loads((root/'data/local-runtime/coverage-check.json').read_text())
case_id=UUID(fixture['case_id'])
engine=create_engine('postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local')
with Session(engine) as db:
    row_id=db.scalar(select(FinancialTransaction.id).where(FinancialTransaction.case_id==case_id,FinancialTransaction.ledger_status=='admitted').order_by(FinancialTransaction.id).limit(1))
    user=db.scalar(select(User).where(User.email=='loupe-local@example.com'))
    db.expunge(user)
now=datetime(2026,9,7,9,45,tzinfo=timezone.utc)
baseline=capture_ledger_export(engine,case_id=case_id,generated_at=now)
original=snapshots.capture_ledger_snapshot
changed=False
try:
    def interleave(*args,**kwargs):
        global changed
        value=original(*args,**kwargs)
        with Session(engine) as writer:
            quarantine_case_row(writer,case_id=case_id,transaction_id=row_id,actor=user,reason='Synthetic concurrent export consistency check')
        changed=True
        return value
    with patch.object(snapshots,'capture_ledger_snapshot',side_effect=interleave):
        during=capture_ledger_export(engine,case_id=case_id,generated_at=now)
    assert during.snapshot==baseline.snapshot, 'Concurrent decision leaked into the earlier snapshot'
    after=capture_ledger_export(engine,case_id=case_id,generated_at=now)
    before_data=json.loads(baseline.snapshot.content);after_data=json.loads(after.snapshot.content)
    assert after_data['ledger']['included_rows']==before_data['ledger']['included_rows']-1
    assert len(after_data['decisions'])==len(before_data['decisions'])+1
    manifest=json.loads(after.manifest)
    assert manifest['digest_covers']=='ledger_snapshot_json_utf8'
    assert manifest['document_sha256']==hashlib.sha256(after.snapshot.content.encode('utf-8')).hexdigest()
    assert manifest['byte_count']==len(after.snapshot.content.encode('utf-8'))
    with patch.object(snapshots,'MAX_EXPORT_BYTES',1):
        try:capture_ledger_export(engine,case_id=case_id)
        except ValueError:pass
        else:raise AssertionError('Oversized export not refused')
    report=dict(case_id=str(case_id),consistent_concurrent_snapshot=True,decision_count_before=len(before_data['decisions']),decision_count_after=len(after_data['decisions']),digest_verified=True)
finally:
    if changed:
        with Session(engine) as writer:
            release_case_row(writer,case_id=case_id,transaction_id=row_id,actor=user,reason='Restore synthetic row after export consistency check')
    engine.dispose()
report['restored']=True
(root/'data/local-runtime/ledger-export-check.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
