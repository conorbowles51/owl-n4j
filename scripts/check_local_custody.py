"""Exercise custody writes and immutable audit in one rolled-back local transaction."""
import json
import sys
from pathlib import Path
from uuid import UUID, uuid4
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from postgres.models.evidence import EvidenceFile
from postgres.models.financial_custody import FinancialCustodyEvent
from services.financial.custody import record_custody, source_custody, capture_case_custody
from services.financial.audit_chain import capture_financial_audit_chain
from services.financial.ledger_snapshot import capture_ledger_snapshot
from services.financial.processing_provenance import capture_processing_provenance
CASE=UUID('e9cafc92-85a7-497c-aec8-049157e823d0')
FILE=UUID('582d271e-c6ee-4eb1-9441-f632794e1664')
engine=create_engine('postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local')
try:
    with engine.connect() as connection:
        outer=connection.begin()
        try:
            with Session(bind=connection,join_transaction_mode='create_savepoint') as db:
                before=capture_financial_audit_chain(db,case_id=CASE)['verification']['event_count']
                source=db.get(EvidenceFile,FILE)
                actor=dict(name='SYNTHETIC rollback-only reviewer',email='nobody@example.invalid',user_id=None)
                body=dict(event_id=str(uuid4()),expected_source_sha256=source.sha256,event_kind='receipt',
                    received_by='Fictional recipient',reason='SYNTHETIC rollback-only custody acceptance',occurred_at='2026-09-10T12:00:00+01:00')
                first=record_custody(db,case_id=CASE,file_id=FILE,request=body,actor=actor)
                assert record_custody(db,case_id=CASE,file_id=FILE,request=body,actor=actor)==first
                correction=record_custody(db,case_id=CASE,file_id=FILE,actor=actor,request={**body,
                    'event_id':str(uuid4()),'event_kind':'correction','corrects_event_id':first['id'],
                    'reason':'SYNTHETIC corrected recipient','received_by':'Other fictional recipient'})
                assert len(source_custody(db,case_id=CASE,file_id=FILE)['events'])==2
                assert len(capture_case_custody(db,case_id=CASE)['events'])==2
                snapshot=json.loads(capture_ledger_snapshot(db,case_id=CASE).content)
                provenance=capture_processing_provenance(db,case_id=CASE,readings=snapshot['ledger']['readings'])
                assert len(provenance['custody_reports'][0]['events'])==2
                chain=capture_financial_audit_chain(db,case_id=CASE)
                assert chain['verification']['event_count']==before+2
                assert all(json.loads(e['payload_text'])['source_table']=='financial_custody_events' for e in chain['entries'][-2:])
                for statement in ("UPDATE financial_custody_events SET evidence_sha256=evidence_sha256 WHERE id=:id", "DELETE FROM financial_custody_events WHERE id=:id", "TRUNCATE financial_custody_events"):
                    savepoint=connection.begin_nested()
                    try:
                        connection.execute(text(statement),{'id':UUID(first['id'])})
                    except Exception as exc:
                        assert 'append-only' in str(exc)
                    else: raise AssertionError('Custody mutation was not refused')
                    finally: savepoint.rollback()
                with engine.connect() as observer:
                    assert observer.scalar(text('SELECT count(*) FROM financial_custody_events WHERE case_id=:case'),{'case':CASE})==0
        finally: outer.rollback()
        assert connection.scalar(text('SELECT count(*) FROM financial_custody_events WHERE case_id=:case'),{'case':CASE})==0
    print(json.dumps(dict(custody_reports=2,idempotent_retry=True,correction_preserves_original=True,
        source_export_capture=True,case_export_capture=True,verified_audit_events=2,update_delete_truncate_refused=True,
        uncommitted_history_invisible=True,all_writes_rolled_back=True)))
finally:engine.dispose()
