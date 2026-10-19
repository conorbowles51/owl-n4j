"""Recovery preparation yields to investigators and rejects stale proposals."""
from copy import deepcopy
from pathlib import Path

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from postgres.models.evidence import EvidenceFile, EvidenceDocumentText, EvidenceTableGeometry
from postgres.models.financial import FinancialSourceDocument as Source, FinancialStatementPeriod as Period, FinancialTransaction as Row
from postgres.models.financial_recovery import FinancialRecoveryItem as Item, FinancialRecoveryRun as Run
from services.financial import deployment_recovery as recovery, recovery_preparation as preparation
from services.financial.pdf_candidates import PdfMappingError
from tests.test_financial_deployment_recovery import f, partial_import, snapshot, outcome, rows


def observe_locks():
    held = {}
    def executing(state):
        if getattr(state.statement, '_for_update_arg', None) is not None:
            held.setdefault(id(state.session), []).append(str(state.statement))
    def ended(session, transaction):
        if transaction.parent is None:
            held.pop(id(session), None)
    event.listen(Session, 'do_orm_execute', executing)
    event.listen(Session, 'after_transaction_end', ended)
    def clean():
        event.remove(Session, 'do_orm_execute', executing)
        event.remove(Session, 'after_transaction_end', ended)
    return held, clean


def test_bytes_parser_and_coverage_run_without_row_locks_and_pause_prevents_commit(f, monkeypatch):
    from services.financial import statement_import, statement_import_overlap
    source = partial_import(f)
    item_id = snapshot(f)
    held, clean = observe_locks()
    called = []
    verify, read, coverage = recovery._verify_bytes, statement_import.read_statement_import, statement_import_overlap.comparison_sources
    def unlocked(name, function):
        def call(*args, **kwargs):
            assert not held, held
            called.append(name)
            return function(*args, **kwargs)
        return call
    def pause_after_read(*args, **kwargs):
        value = unlocked('read', read)(*args, **kwargs)
        with f.SessionLocal() as db:
            assert recovery.control(db, f.case.id, 'pause')['status'] == 'paused'
        return value
    monkeypatch.setattr(recovery, '_verify_bytes', unlocked('verify', verify))
    monkeypatch.setattr(statement_import, 'read_statement_import', pause_after_read)
    monkeypatch.setattr(statement_import_overlap, 'comparison_sources', unlocked('coverage', coverage))
    try:
        recovery.recover_one(f.SessionLocal, item_id, Path)
    finally:
        clean()
    assert {'verify', 'read'} <= set(called)
    assert 'coverage' not in called  # Pause stops before the next expensive phase.
    assert len(rows(f, source)) == 11
    assert outcome(f, item_id)[0] == 'pending'
    with f.SessionLocal() as db:
        assert db.get(Run, db.get(Item, item_id).run_id).status == 'paused'


@pytest.mark.parametrize('change', ['review', 'geometry', 'text', 'saved_source', 'payment', 'period', 'new_file'])
def test_changed_inputs_discard_preparation_without_overwriting_work(f, monkeypatch, change):
    from services.financial import statement_import
    source = partial_import(f)
    item_id = snapshot(f)
    original = statement_import.read_statement_import
    changed = False
    def read(*args, **kwargs):
        nonlocal changed
        value = original(*args, **kwargs)
        if not changed:
            changed = True
            with f.SessionLocal() as db:
                if change == 'review':
                    file = db.get(EvidenceFile, f.file.id)
                    file.metadata_ = {**file.metadata_, 'financial_review_progress': {'': {'request': {'rows': [], 'reason': 'Investigator draft'}}}}
                elif change == 'geometry':
                    geometry = db.get(EvidenceTableGeometry, (f.file.id, 1))
                    payload = deepcopy(geometry.payload)
                    payload[0]['table']['values'][0]['text'] += ' revised'
                    geometry.payload = payload
                elif change == 'text':
                    text = db.get(EvidenceDocumentText, f.file.id)
                    text.source_locations = [*text.source_locations, {'kind': 'reviewed_source'}]
                elif change == 'saved_source':
                    document = db.get(Source, source)
                    document.metadata_ = {**document.metadata_, 'investigator_note': 'Keep my note'}
                elif change == 'payment':
                    row = db.scalar(select(Row).where(Row.source_document_id == source))
                    row.description = 'Investigator corrected description'
                elif change == 'period':
                    period = db.scalar(select(Period).where(Period.source_document_id == source))
                    period.closing_balance_minor += 1
                else:
                    file = f.evidence('b' * 64)
                    f.db.commit()
                    assert file.case_id == f.case.id
                db.commit()
        return value
    monkeypatch.setattr(statement_import, 'read_statement_import', read)
    recovery.recover_one(f.SessionLocal, item_id, Path)
    assert changed
    assert outcome(f, item_id)[0] == 'pending'
    assert len(rows(f, source)) == 11
    with f.SessionLocal() as db:
        assert not db.get(Source, source).metadata_.get('statement_recovery_additions')
        if change == 'saved_source':
            assert db.get(Source, source).metadata_['investigator_note'] == 'Keep my note'
        if change == 'payment':
            assert any(row.description == 'Investigator corrected description' for row in rows(f, source))


def test_concurrent_recovery_winner_invalidates_older_preparation_without_duplicate(f, monkeypatch):
    from services.financial import statement_import
    source = partial_import(f)
    item_id = snapshot(f)
    original = statement_import.read_statement_import
    invoked = False
    def read(*args, **kwargs):
        nonlocal invoked
        value = original(*args, **kwargs)
        if not invoked:
            invoked = True
            recovery.recover_one(f.SessionLocal, item_id, Path)
        return value
    monkeypatch.setattr(statement_import, 'read_statement_import', read)
    recovery.recover_one(f.SessionLocal, item_id, Path)
    assert len(rows(f, source)) == 12
    assert outcome(f, item_id)[0] == 'recovered'
    with f.SessionLocal() as db:
        assert len(db.get(Source, source).metadata_['statement_recovery_additions']) == 1


def test_pause_between_periods_stops_before_reading_the_next_period(f, monkeypatch):
    from services.financial import statement_import, statement_import_overlap
    source = partial_import(f)
    item_id = snapshot(f)
    original = statement_import.read_statement_import
    calls = []
    def read(*args, **kwargs):
        key = kwargs.get('statement_id')
        calls.append(key)
        value = original(*args, **{**kwargs, 'statement_id': None})
        if key is None:
            value['statement_choices'] = [{'id': 'first'}, {'id': 'second'}]
        else:
            with f.SessionLocal() as db:
                recovery.control(db, f.case.id, 'pause')
        return value
    monkeypatch.setattr(statement_import, 'read_statement_import', read)
    monkeypatch.setattr(statement_import_overlap, 'comparison_sources', lambda *a, **k: pytest.fail('Coverage must stop after Pause'))
    recovery.recover_one(f.SessionLocal, item_id, Path)
    assert calls == [None, 'first']
    assert outcome(f, item_id)[0] == 'pending'
    assert len(rows(f, source)) == 11


def test_change_after_preparation_is_rejected_by_final_locked_comparison(f, monkeypatch):
    source = partial_import(f)
    item_id = snapshot(f)
    original = preparation.prepare_readings
    def prepare(*args, **kwargs):
        value = original(*args, **kwargs)
        assert value is not None
        with f.SessionLocal() as db:
            document = db.get(Source, source)
            document.metadata_ = {**document.metadata_, 'investigator_note': 'Changed after preparation'}
            db.commit()
        return value
    monkeypatch.setattr(preparation, 'prepare_readings', prepare)
    recovery.recover_one(f.SessionLocal, item_id, Path)
    assert outcome(f, item_id)[0] == 'pending'
    assert len(rows(f, source)) == 11
    with f.SessionLocal() as db:
        assert db.get(Source, source).metadata_['investigator_note'] == 'Changed after preparation'


@pytest.mark.parametrize('error_type', [PdfMappingError, RuntimeError])
def test_late_preparation_failure_does_not_change_paused_outcome(f, monkeypatch, error_type):
    from services.financial import statement_import
    source = partial_import(f)
    item_id = snapshot(f)
    before = outcome(f, item_id)
    def failure(*args, **kwargs):
        with f.SessionLocal() as db:
            recovery.control(db, f.case.id, 'pause')
        raise error_type('Synthetic reading failed after pause')
    monkeypatch.setattr(statement_import, 'read_statement_import', failure)
    if error_type is RuntimeError:
        with pytest.raises(RuntimeError):
            recovery.recover_one(f.SessionLocal, item_id, Path)
        # This is the daemon's error path after an unexpected preparation error.
        recovery._record_failure(f.SessionLocal, item_id, 'Synthetic failure')
    else:
        recovery.recover_one(f.SessionLocal, item_id, Path)
    assert outcome(f, item_id) == before
    assert len(rows(f, source)) == 11


def test_retained_reading_without_processed_status_does_not_loop(f):
    source = partial_import(f)
    f.file.status = 'unprocessed'
    f.db.commit()
    item_id = snapshot(f)
    recovery.recover_one(f.SessionLocal, item_id, Path)
    assert outcome(f, item_id)[0] == 'recovered', outcome(f, item_id)
    assert len(rows(f, source)) == 12


def test_input_fingerprint_is_case_scoped_and_read_only(f):
    item_id = snapshot(f)
    with f.SessionLocal() as db:
        item = db.get(Item, item_id)
        first = preparation.input_revision(db, f.case.id, item)
    other = f.evidence('c' * 64)
    other.case_id = f.other_case.id
    other.metadata_ = {'private_other_case': 'unrelated'}
    f.db.commit()
    with f.SessionLocal() as db:
        assert preparation.input_revision(db, f.case.id, db.get(Item, item_id)) == first
        assert not db.new and not db.dirty and not db.deleted


def test_retry_diagnosis_is_prepared_before_case_lock(f, monkeypatch):
    from services.financial import reading_recovery
    from tests.test_financial_recovery_followup import failed_batch, finish_old, followup
    failed_batch(f)
    finish_old(f)
    [item_id] = followup(f)
    diagnose = reading_recovery.inspect_completed_reading
    held, clean = observe_locks()
    calls = []
    def unlocked(*args, **kwargs):
        assert not held, held
        calls.append(kwargs['file'].id)
        return diagnose(*args, **kwargs)
    monkeypatch.setattr(reading_recovery, 'inspect_completed_reading', unlocked)
    try:
        recovery.recover_one(f.SessionLocal, item_id, Path)
    finally:
        clean()
    assert calls == [f.file.id]
    assert outcome(f, item_id)[0] == 'waiting'
    assert outcome(f, item_id)[1]['batch_retry_receipts'][0]['action'] == 'check_statements'
