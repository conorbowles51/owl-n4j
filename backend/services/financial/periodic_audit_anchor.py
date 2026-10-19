"""Explicit operator-run timestamp checkpoints; no automatic startup or default TSA."""
import fcntl
import json
import os
from pathlib import Path
from uuid import UUID, uuid4
from sqlalchemy import select
from sqlalchemy.orm import Session
from postgres.models.case import Case
from services.financial.audit_chain import capture_financial_audit_chain
from services.financial.audit_timestamp import checkpoint, submit_financial_audit_timestamp, verify_financial_audit_timestamp_response
from services.financial.ledger_snapshot import capture_ledger_export, ledger_export_archive


def _json(value): return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def _save(path, value):
    temporary=path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    with temporary.open('xb') as target:
        target.write(_json(value));target.flush();os.fsync(target.fileno())
    os.replace(temporary,path)


def _read(path):
    if path.stat().st_size>65536: raise ValueError('Anchor pointer exceeds its size limit.')
    from services.financial.reference_reviews import parse_review_json
    return parse_review_json(path.read_bytes())


def _current_chain(engine, case_id):
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
        with connection.begin():
            connection.exec_driver_sql('SET TRANSACTION READ ONLY')
            with Session(bind=connection,autoflush=False) as session:
                if session.scalar(select(Case.id).where(Case.id==case_id)) is None:
                    raise ValueError('Selected case does not exist.')
                return capture_financial_audit_chain(session,case_id=case_id)


def anchor_financial_case_once(engine, *, case_id, output, tsa_url, ca_file, openssl='openssl', untrusted=None, retry_failed=False):
    """At most one new submission; an uncertain prior attempt requires explicit retry.

    Full captured ledger/audit bytes stay locally. Only the RFC3161 imprint query
    is sent by the shared submission helper. No source, ledger or audit rows change.
    A common output directory supplies the cross-process lock; deployments with
    separate filesystems must designate one runner, not multiple independent stores.
    """
    case_id=UUID(str(case_id));folder=Path(output)/str(case_id);folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (folder/'runner.lock').open('a+b') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: return dict(case_id=str(case_id),status='already_running')
        latest=folder/'latest.json';pending=folder/'pending.json'
        chain=_current_chain(engine,case_id)
        current=chain['verification']
        previous=None
        if latest.exists():
            pointer=_read(latest);attempt=str(UUID(pointer['attempt_id']));directory=folder/attempt
            previous=verify_financial_audit_timestamp_response(directory/'captured-ledger.zip',directory/'timestamp',
                directory/'timestamp/response.tsr',ca_file,openssl=openssl,untrusted=untrusted)['checkpoint']
            if previous['case_id']!=str(case_id): raise ValueError('Retained timestamp belongs to a different case.')
            count=previous['event_count']
            if count>current['event_count'] or (count>0 and chain['entries'][count-1]['entry_sha256']!=previous['head_sha256']):
                raise ValueError('Current audit history does not extend the previously timestamped head. Investigation is required.')
        if pending.exists():
            interrupted=_read(pending);pending_id=str(UUID(interrupted['attempt_id']));interrupted_dir=folder/pending_id
            if (interrupted_dir/'timestamp/response.tsr').is_file():
                try:
                    recovered=verify_financial_audit_timestamp_response(interrupted_dir/'captured-ledger.zip',
                        interrupted_dir/'timestamp',interrupted_dir/'timestamp/response.tsr',ca_file,
                        openssl=openssl,untrusted=untrusted)['checkpoint']
                    count=recovered['event_count']
                    if recovered['case_id']!=str(case_id) or count>current['event_count'] or (count>0 and chain['entries'][count-1]['entry_sha256']!=recovered['head_sha256']):
                        raise ValueError('Retained pending timestamp does not match current case history.')
                    if previous is not None and count<previous['event_count']:
                        raise ValueError('Pending receipt predates the latest verified anchor.')
                except Exception:
                    if not retry_failed:
                        return dict(case_id=str(case_id),status='attention_required',reason='Retained response could not be verified against current trust and case history.')
                else:
                    _save(latest,dict(attempt_id=pending_id,case_id=str(case_id),checkpoint=recovered))
                    pending.unlink()
                    return dict(case_id=str(case_id),status='recovered_verified_timestamp',event_count=count,attempt_id=pending_id)
            if pending.exists() and not retry_failed:
                return dict(case_id=str(case_id),status='attention_required',reason='A prior attempt may have been submitted. Review its retained files before an explicit one-time retry.')
        if previous is not None and previous['head_sha256']==current['head_sha256']:
            if pending.exists() and retry_failed: pending.unlink()
            return dict(case_id=str(case_id),status='unchanged_verified_head',event_count=current['event_count'])
        if current['event_count']==0:
            return dict(case_id=str(case_id),status='no_recorded_events',event_count=0)
        attempt=str(uuid4());directory=folder/attempt;directory.mkdir(mode=0o700)
        # A pending pointer is persisted before work that could contact the TSA.
        # Crashes and uncertain responses cannot trigger blind scheduled retries.
        _save(pending,dict(attempt_id=attempt,case_id=str(case_id),status='preparing'))
        try:
            export=capture_ledger_export(engine,case_id=case_id,include_case_financial_history=True)
            archive=ledger_export_archive(export)
            (directory/'captured-ledger.zip').write_bytes(archive)
            captured=json.loads(checkpoint(directory/'captured-ledger.zip'))
            if captured['case_id']!=str(case_id): raise ValueError('Captured export belongs to a different case.')
            # Verify continuity again in the actual later export snapshot, which
            # may contain events appended after the initial read.
            document=json.loads(export.snapshot.content)
            captured_chain=document['case_financial_history']['audit_chain']
            count=current['event_count']
            if count>captured['event_count'] or (count>0 and captured_chain['entries'][count-1]['entry_sha256']!=current['head_sha256']):
                raise ValueError('Captured export does not extend the preflight audit head.')
            if previous is not None:
                count=previous['event_count']
                if count>captured['event_count'] or (count>0 and captured_chain['entries'][count-1]['entry_sha256']!=previous['head_sha256']):
                    raise ValueError('Captured export does not extend the previously timestamped head.')
            _save(pending,dict(attempt_id=attempt,case_id=str(case_id),status='submission_may_start'))
            submit_financial_audit_timestamp(directory/'captured-ledger.zip',directory/'timestamp',tsa_url=tsa_url,
                ca_file=ca_file,openssl=openssl,untrusted=untrusted)
            # Independently read/reverify retained files; do not trust a status
            # string or a journal as proof of a valid timestamp.
            verified=verify_financial_audit_timestamp_response(directory/'captured-ledger.zip',directory/'timestamp',
                directory/'timestamp/response.tsr',ca_file,openssl=openssl,untrusted=untrusted)
            if verified['checkpoint']!=captured: raise ValueError('Retained timestamp does not match this checkpoint.')
            _save(latest,dict(attempt_id=attempt,case_id=str(case_id),checkpoint=captured))
            pending.unlink()
            return dict(case_id=str(case_id),status='timestamp_verified',event_count=captured['event_count'],
                head_sha256=captured['head_sha256'],attempt_id=attempt)
        except Exception as exc:
            _save(pending,dict(attempt_id=attempt,case_id=str(case_id),status='attention_required',error_type=type(exc).__name__))
            raise
