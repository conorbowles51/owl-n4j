"""Check the browser's export receipt against local audit history and exact ZIP bytes."""
import hashlib
import json
import os
import sys
from pathlib import Path
from uuid import UUID
from zipfile import ZipFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
os.environ['PYTHON_DOTENV_DISABLED']='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from services.financial.audit_chain import capture_financial_audit_chain
receipt=json.loads(Path('/tmp/loupe-case-review-export-receipt.json').read_text())
archive=Path('/tmp/loupe-case-review-export.zip')
with ZipFile(archive) as zipped:
    manifest=json.loads(zipped.read('manifest.json'))
    snapshot=json.loads(zipped.read('ledger-snapshot.json'))
engine=create_engine('postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local')
try:
    with Session(engine) as db:
        captured=capture_financial_audit_chain(db,case_id=UUID(receipt['case_id']))
        event=captured['entries'][receipt['sequence']-1]
        assert event['entry_sha256']==receipt['entry_sha256']
        body=json.loads(event['payload_text'])
        assert body['source_table']=='ledger_exports' and body['operation']=='EXPORT_PREPARED'
        assert body['source_id']==receipt['export_id']
        assert body['actor']['user_id']==snapshot['export_context']['generated_by']['id']
        assert body['after']['artifact_sha256']==hashlib.sha256(archive.read_bytes()).hexdigest()
        assert body['after']['byte_count']==archive.stat().st_size
        assert body['after']['scope']['snapshot_sha256']==manifest['document_sha256']
        assert body['after']['scope']['include_case_financial_history'] is True
        assert body['after']['delivery_status']=='prepared_not_delivery_confirmed'
    print('PASS: browser receipt matches verified database chain, authenticated exporter, captured snapshot and exact downloaded ZIP bytes. No ledger/source changes.')
finally:engine.dispose()
