"""Deterministic immutable content for an unfinished ledger export.

Captures rows, source classification and totals from the same bounded SELECT.
This is not an externally exposed export: decision history and an export-event
manifest must be captured before that workflow is complete.
"""
import hashlib
import json
from dataclasses import dataclass
from services.financial.ledger_summary import ledger_summary, LedgerSummaryError


@dataclass(frozen=True)
class LedgerSnapshot:
    content: str
    sha256: str
    byte_count: int


def capture_ledger_snapshot(session, *, case_id, account_id=None, start_date=None, end_date=None):
    result=ledger_summary(session,case_id=case_id,account_id=account_id,start_date=start_date,
        end_date=end_date,capture_readings=True)
    if not result['available']:
        raise LedgerSummaryError(result['reason'])
    document=dict(schema='loupe.financial.ledger_snapshot/1',ledger=result,
        export_ready=False,limitations=['Decision history has not been captured. This is an internal snapshot, not a completed export.',
            'Source digests are recorded ingestion digests; source bytes were not reverified for this snapshot.'])
    # No generation time in the content: equal captured inputs yield equal bytes.
    content=json.dumps(document,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    encoded=content.encode('utf-8')
    return LedgerSnapshot(content=content,sha256=hashlib.sha256(encoded).hexdigest(),byte_count=len(encoded))


MAX_EXPORT_DECISIONS = 10000
MAX_EXPORT_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class LedgerExport:
    snapshot: LedgerSnapshot
    manifest: str


def _capture_history(session, document, *, case_id):
    from uuid import UUID
    from sqlalchemy import select, and_, or_
    from postgres.models.financial import AdjudicationEvent
    from services.financial.decision_log import to_record, _machine_actor_email
    scopes = {name:set() for name in ('transaction','source_document','statement_period','evidence_file')}
    for reading in document['ledger']['readings']:
        row, source = reading['row'], reading['source']
        scopes['transaction'].add(UUID(row['key']))
        scopes['source_document'].add(UUID(source['id']))
        if row['statement_period_id']:scopes['statement_period'].add(UUID(row['statement_period_id']))
        if source['evidence_file_id']:scopes['evidence_file'].add(UUID(source['evidence_file_id']))
    predicates=[and_(AdjudicationEvent.subject_type==kind,AdjudicationEvent.subject_id.in_(ids))
        for kind,ids in scopes.items() if ids]
    events=[]
    if predicates:
        events=list(session.scalars(select(AdjudicationEvent).where(AdjudicationEvent.case_id==case_id,or_(*predicates))
            .order_by(AdjudicationEvent.subject_type,AdjudicationEvent.subject_id,AdjudicationEvent.subject_sequence)
            .limit(MAX_EXPORT_DECISIONS+1)))
    if len(events)>MAX_EXPORT_DECISIONS:
        raise LedgerSummaryError('Too many relevant decisions for a complete export; no truncated export was produced.')
    machine_email=_machine_actor_email()
    document['decisions']=[to_record(event,machine_email=machine_email).as_dict() for event in events]
    document['decision_scope']={kind:sorted(str(value) for value in ids) for kind,ids in scopes.items()}
    document['decision_order']='Per-subject sequence only; ordering across different subjects does not establish chronology.'
    document['ledger']['history_captured']=True
    document['export_ready']=True
    document['schema']='loupe.financial.ledger_snapshot/2'
    document['limitations']=[
        'Source digests are recorded ingestion digests; source bytes were not reverified for this snapshot.',
        'Decision history covers the captured rows and their source documents, statement periods and evidence files. It is not a complete case history.',
        'Structured PDF candidate-review history is not embedded; its preserved readings and finalization references remain in transaction provenance.',
    ]
    return document


def capture_ledger_export(engine, *, case_id, account_id=None, start_date=None, end_date=None, generated_at=None):
    """Own a fresh PostgreSQL repeatable-read read-only transaction for both reads."""
    from datetime import datetime, timezone
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import Session
    from services.financial.version import code_version
    if not isinstance(engine,Engine) or engine.dialect.name!='postgresql':
        raise LedgerSummaryError('Consistent ledger export requires a fresh PostgreSQL engine connection.')
    generated_at=generated_at or datetime.now(timezone.utc)
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise LedgerSummaryError('Export generation time must carry a timezone.')
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
        with connection.begin():
            connection.exec_driver_sql('SET TRANSACTION READ ONLY')
            with Session(bind=connection,autoflush=False) as session:
                snapshot=capture_ledger_snapshot(session,case_id=case_id,account_id=account_id,start_date=start_date,end_date=end_date)
                document=_capture_history(session,json.loads(snapshot.content),case_id=case_id)
                content=json.dumps(document,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    encoded=content.encode('utf-8')
    if len(encoded)>MAX_EXPORT_BYTES:
        raise LedgerSummaryError('Export exceeds 16 MiB; narrow the scope. No partial export was produced.')
    snapshot=LedgerSnapshot(content,hashlib.sha256(encoded).hexdigest(),len(encoded))
    manifest=dict(schema='loupe.financial.ledger_export_manifest/1',digest_covers='ledger_snapshot_json_utf8',
        document_sha256=snapshot.sha256,byte_count=snapshot.byte_count,
        generated_at=generated_at.astimezone(timezone.utc).isoformat(),case_id=str(case_id),
        code_version=code_version(),snapshot_schema=document['schema'],
        decision_count=len(document['decisions']),included_rows=document['ledger']['included_rows'],
        excluded_rows=document['ledger']['excluded_rows'])
    return LedgerExport(snapshot,json.dumps(manifest,sort_keys=True,separators=(',',':')))
