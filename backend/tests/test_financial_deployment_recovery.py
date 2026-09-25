from copy import deepcopy
from pathlib import Path
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select
from postgres.base import Base
from postgres.models.evidence import EvidenceTableGeometry, IngestionLog
from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
from postgres.models.financial_candidates import FinancialCandidateMapping, FinancialStatementReviewDraft
from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
from postgres.models.financial_recovery import FinancialRecoveryRelease, FinancialRecoveryRun, FinancialRecoveryItem
from services.financial import deployment_recovery as recovery
from services.financial.file_scope import mark_financial_workspace
from services.financial.pdf_candidates import PdfMappingError
from tests import test_financial_statement_import as fixtures


@pytest.fixture
def f():
    fixture = fixtures.StatementImportTests(); fixture.setUp()
    Base.metadata.create_all(fixture.engine, tables=[IngestionLog.__table__, FinancialCandidateMapping.__table__,
        FinancialStatementReviewDraft.__table__, WorkspaceEntry.__table__, WorkspaceEntryLink.__table__,
        FinancialRecoveryRelease.__table__, FinancialRecoveryRun.__table__, FinancialRecoveryItem.__table__])
    fixture.file.status = 'processed'
    mark_financial_workspace(fixture.file, user_id=fixture.user.id)
    fixture.db.commit()
    yield fixture
    fixture.tearDown()


def partial_import(f):
    geometry = f.db.get(EvidenceTableGeometry, (f.file.id, 1))
    full = deepcopy(geometry.payload)
    old = deepcopy(full)
    old[0]['table']['values'] = [v for v in old[0]['table']['values'] if v['row'] != 13]
    geometry.payload = old
    f.db.commit()
    receipt = f.confirm_legacy()
    geometry.payload = full
    f.db.commit()
    return UUID(receipt['source_document_id'])


def snapshot(f):
    with f.SessionLocal() as db:
        recovery.snapshot_case(db, f.case.id, recovery.activate(db))
        return db.scalar(select(FinancialRecoveryItem.id).where(FinancialRecoveryItem.file_id == f.file.id))


def outcome(f, item_id):
    with f.SessionLocal() as db:
        item = db.get(FinancialRecoveryItem, item_id)
        return item.status, item.result


def rows(f, document):
    with f.SessionLocal() as db:
        return list(db.scalars(select(FinancialTransaction).where(FinancialTransaction.source_document_id == document)))


def test_recovers_missing_payment_without_replacing_ids_or_repeating(f):
    document = partial_import(f)
    before = {row.id for row in rows(f, document)}
    item = snapshot(f)
    recovery.recover_one(f.SessionLocal, item, Path)
    state, result = outcome(f, item)
    assert state == 'recovered', result
    assert result['added'] == 1
    after = rows(f, document)
    assert len(after) == len(before) + 1
    assert before < {row.id for row in after}
    recovery.recover_one(f.SessionLocal, item, Path)
    assert len(rows(f, document)) == len(after)
    with f.SessionLocal() as db:
        saved = db.get(FinancialSourceDocument, document)
        assert saved.status == 'admitted'
        assert len(saved.metadata_['statement_recovery_additions']) == 1


def test_manual_added_payment_is_kept_for_comparison_not_duplicated(f):
    document = partial_import(f)
    from services.financial.manual_statement_payment import append_payment, ManualStatementPayment
    from services.financial.statement_details import read_statement_details
    with f.SessionLocal() as db:
        view = read_statement_details(db, case_id=f.case.id, source_id=document)
    request_id = uuid4()
    append_payment(session_factory=f.SessionLocal, case_id=f.case.id, source_id=document, actor=f.actor,
        request=ManualStatementPayment(request_id=request_id, expected_revision=view['revision'], row=dict(
            id='manual:' + str(request_id), excluded=False, manual_page=1, date='2023-12-28',
            description='Investigator entered missing payment', counterparty='Supplier', amount_minor='27000000',
            direction='debit', balance_minor=None, reason='')))
    before = {r.id for r in rows(f, document)}
    with f.SessionLocal() as db:
        metadata = db.get(FinancialSourceDocument, document).metadata_
        pending = deepcopy(metadata['statement_incomplete_records'])
        additions = deepcopy(metadata['statement_manual_additions'])
    item = snapshot(f)
    recovery.recover_one(f.SessionLocal, item, Path)
    assert outcome(f, item)[0] == 'review', outcome(f, item)
    assert before == {r.id for r in rows(f, document)}
    with f.SessionLocal() as db:
        metadata = db.get(FinancialSourceDocument, document).metadata_
        assert metadata['statement_incomplete_records'] == pending
        assert metadata['statement_manual_additions'] == additions


def test_existing_investigator_work_stays_on_the_same_payment(f):
    document = partial_import(f)
    with f.SessionLocal() as db:
        row = db.scalar(select(FinancialTransaction).where(FinancialTransaction.source_document_id == document))
        row.metadata_ = {**(row.metadata_ or {}), 'investigator_note': 'Retain this work'}
        identity = row.id
        db.commit()
    item = snapshot(f)
    recovery.recover_one(f.SessionLocal, item, Path)
    assert outcome(f, item)[0] == 'recovered', outcome(f, item)
    with f.SessionLocal() as db:
        assert db.get(FinancialTransaction, identity).metadata_['investigator_note'] == 'Retain this work'


def test_explicitly_excluded_payment_requires_review(f):
    request = f.request()
    next(row for row in reversed(request['rows']) if not row['excluded'])['excluded'] = True
    document = UUID(f.confirm_legacy(request)['source_document_id'])
    count = len(rows(f, document))
    item = snapshot(f)
    recovery.recover_one(f.SessionLocal, item, Path)
    assert outcome(f, item)[0] == 'review', outcome(f, item)
    assert len(rows(f, document)) == count


def test_pause_resume_and_snapshot_idempotence(f):
    partial_import(f)
    item = snapshot(f)
    assert snapshot(f) == item
    with f.SessionLocal() as db:
        recovery.control(db, f.case.id, 'pause')
    recovery.recover_one(f.SessionLocal, item, Path)
    assert outcome(f, item)[0] == 'pending'
    with f.SessionLocal() as db:
        recovery.control(db, f.case.id, 'resume')
    recovery.recover_one(f.SessionLocal, item, Path)
    assert outcome(f, item)[0] == 'recovered', outcome(f, item)


def test_removed_file_is_not_restored_or_processed(f):
    document = partial_import(f)
    item = snapshot(f)
    f.file.metadata_ = {**f.file.metadata_, 'financial_file_visibility': {'removed': True, 'revision': 'removed'}}
    f.db.commit()
    recovery.recover_one(f.SessionLocal, item, Path)
    assert outcome(f, item)[0] == 'kept'
    assert len(rows(f, document)) == 11


def test_active_ai_job_is_not_interrupted(f):
    partial_import(f)
    item = snapshot(f)
    f.file.status = 'processing'; f.db.commit()
    recovery.recover_one(f.SessionLocal, item, Path)
    assert outcome(f, item)[0] == 'waiting'
    f.db.refresh(f.file)
    assert f.file.status == 'processing'


def test_changed_bytes_require_review_without_writes(f):
    document = partial_import(f)
    item = snapshot(f)
    f.path.write_bytes(b'%PDF-Changed synthetic bytes')
    recovery.recover_one(f.SessionLocal, item, Path)
    assert outcome(f, item)[0] == 'review'
    assert len(rows(f, document)) == 11


def test_new_unimported_reading_stays_for_investigator_confirmation(f):
    item = snapshot(f)
    recovery.recover_one(f.SessionLocal, item, Path)
    state, result = outcome(f, item)
    assert state == 'review', result
    assert result['added'] == 0
    assert result['review_file_id'] == str(f.file.id)


def test_status_and_controls_do_not_cross_cases(f):
    item = snapshot(f)
    other = uuid4()
    with f.SessionLocal() as db:
        assert recovery.status(db, other)['run'] is None
        with pytest.raises(PdfMappingError):
            recovery.retry_item(db, other, item)


def test_interrupted_atomic_write_leaves_no_half_added_payments_and_can_resume(f):
    from unittest.mock import patch
    from services.financial.recovery_additions import append_recovered
    document = partial_import(f)
    item = snapshot(f)
    def interrupted(*args, **kwargs):
        append_recovered(*args, **kwargs)
        raise RuntimeError('Synthetic interruption before receipt commit')
    with patch('services.financial.recovery_additions.append_recovered', side_effect=interrupted):
        with pytest.raises(RuntimeError):
            recovery.recover_one(f.SessionLocal, item, Path)
    assert len(rows(f, document)) == 11
    assert outcome(f, item)[0] == 'pending'
    recovery.recover_one(f.SessionLocal, item, Path)
    assert len(rows(f, document)) == 12


def test_restart_between_reading_creation_and_queue_submission_reuses_version(f):
    import asyncio
    from unittest.mock import AsyncMock
    from postgres.models.evidence import EvidenceFile
    partial_import(f)
    geometry = f.db.get(EvidenceTableGeometry, (f.file.id, 1))
    f.db.delete(geometry); f.db.commit()
    item = snapshot(f)
    request = recovery.recover_one(f.SessionLocal, item, Path)
    assert request['needs_reading']
    with pytest.raises(RuntimeError):
        asyncio.run(recovery.start_reading(f.SessionLocal, request, Path, AsyncMock(side_effect=RuntimeError('Lost connection'))))
    request = recovery.recover_one(f.SessionLocal, item, Path)
    assert request['needs_reading']
    async def process(db, **kwargs):
        target = db.get(EvidenceFile, kwargs['file_ids'][0])
        target.status = 'processing'
        db.commit()
        return {'job_ids': [str(uuid4())]}
    asyncio.run(recovery.start_reading(f.SessionLocal, request, Path, process))
    with f.SessionLocal() as db:
        copies = list(db.scalars(select(EvidenceFile).where(EvidenceFile.case_id == f.case.id,
            EvidenceFile.metadata_['statement_parent_evidence_id'].as_string() == str(f.file.id))))
        assert len(copies) == 1
        assert copies[0].status == 'processing'
        assert db.get(EvidenceFile, f.file.id).status == 'processed'
    recovery.recover_one(f.SessionLocal, item, Path)
    assert outcome(f, item)[0] == 'reading'


def test_completed_snapshot_does_not_absorb_later_uploads(f):
    from services.financial.file_scope import mark_financial_workspace
    from datetime import datetime, timedelta, timezone
    item = snapshot(f)
    later = f.evidence('b' * 64)
    later.created_at = datetime.now(timezone.utc) + timedelta(days=1)
    mark_financial_workspace(later, user_id=f.user.id)
    f.db.commit()
    assert snapshot(f) == item
    with f.SessionLocal() as db:
        assert db.scalar(select(FinancialRecoveryItem).where(FinancialRecoveryItem.file_id == later.id)) is None


def test_unknown_system_membership_is_retained_for_content_review(f):
    f.file.metadata_ = {}
    f.file.last_processed_profile_snapshot = {'preparation_mode': 'pdf_review'}
    f.db.commit()
    item = snapshot(f)
    recovery.recover_one(f.SessionLocal, item, Path)
    assert outcome(f, item)[0] == 'review'
    assert 'content check' in outcome(f, item)[1]['message']


def test_preserves_saved_account_and_balance_corrections(f):
    from services.financial.statement_details import read_statement_details, update_statement_details, StatementDetailsRequest
    document = partial_import(f)
    with f.SessionLocal() as db:
        view = read_statement_details(db, case_id=f.case.id, source_id=document)
        corrected = update_statement_details(db, case_id=f.case.id, source_id=document,
            request=StatementDetailsRequest(expected_revision=view['revision'], holder='Reviewed company',
                account_number='000001', institution='Reviewed bank', period_start='2023-01-01', period_end='2023-12-31',
                opening={'amount_minor': '1245000', 'page': 1}, closing={'amount_minor': '4745000', 'page': 1}), actor=f.actor)
    item = snapshot(f)
    recovery.recover_one(f.SessionLocal, item, Path)
    assert outcome(f, item)[0] == 'recovered', outcome(f, item)
    with f.SessionLocal() as db:
        reopened = read_statement_details(db, case_id=f.case.id, source_id=document)
        assert reopened['details'] == corrected['details']
        assert reopened['balances'] == corrected['balances']


def test_recovery_routes_require_case_access_and_edit_permission(f):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from routers import financial_statement_import as router
    from routers.users import get_current_db_user
    from postgres.session import get_db
    from tests.test_route_authorization import _CaseAccessDb
    app = FastAPI(); app.include_router(router.router)
    client = TestClient(app)
    url = '/api/financial/statement-import/deployment-recovery'
    assert client.get(url, params={'case_id': str(f.case.id)}).status_code == 401
    user = SimpleNamespace(id=uuid4(), global_role='user', is_active=True)
    db = _CaseAccessDb()
    app.dependency_overrides[get_current_db_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    assert client.get(url, params={'case_id': str(db.case.id)}).status_code == 403
    assert client.post(url + '/pause', params={'case_id': str(db.case.id)}).status_code == 403
    assert client.post(url + '/items/' + str(uuid4()) + '/retry', params={'case_id': str(db.case.id)}).status_code == 403


def test_legacy_balance_only_import_recovers_untouched_unclassified_rows(f):
    from services.financial.pdf_candidates import _digest
    from services.financial.import_batches import initial_request
    from services.financial.statement_import import StatementImportRequest
    request = f.request()
    for row in request['rows']:
        row['excluded'] = True
    document = UUID(f.confirm_legacy(request)['source_document_id'])
    assert not rows(f, document)
    # Simulate an older reader which left all payment lines as untouched,
    # excluded source text. This is different from an investigator exclusion.
    with f.SessionLocal() as db:
        source = db.get(FinancialSourceDocument, document)
        metadata = deepcopy(source.metadata_)
        old = metadata['statement_import_original']
        old['revision'] = '0' * 64
        for row in old['rows']:
            if row['kind'] == 'transaction':
                row.update(kind='unclassified', excluded=True, fields={})
        old_request = StatementImportRequest.model_validate(initial_request(old)).model_dump(mode='json')
        metadata.update(statement_import_original_sha256=_digest(old),
            statement_import_request=old_request, statement_import_request_sha256=_digest(old_request))
        source.metadata_ = metadata
        db.commit()
    item = snapshot(f)
    recovery.recover_one(f.SessionLocal, item, Path)
    assert outcome(f, item)[0] == 'recovered', outcome(f, item)
    assert outcome(f, item)[1]['added'] == 12
    assert len(rows(f, document)) == 12


def test_amount_correction_and_its_history_survive_additive_recovery(f):
    from services.financial.corrections import correct_transaction
    from services.financial.duplicate_decisions import duplicate_revision
    document = partial_import(f)
    with f.SessionLocal() as db:
        row = db.scalar(select(FinancialTransaction).where(FinancialTransaction.source_document_id == document))
        old_id = row.id
        changed = correct_transaction(db, case_id=f.case.id, transaction_id=row.id,
            amount_minor=row.amount_minor + 1, direction=row.direction,
            expected_revision=duplicate_revision(db, db.get(FinancialSourceDocument, document)),
            actor=f.actor, reason='Synthetic saved correction')
        replacement_id = UUID(changed['replacement_id'])
        corrected_amount = db.get(FinancialTransaction, replacement_id).amount_minor
    before = {r.id for r in rows(f, document)}
    item = snapshot(f)
    recovery.recover_one(f.SessionLocal, item, Path)
    assert outcome(f, item)[0] == 'review', outcome(f, item)
    assert {r.id for r in rows(f, document)} == before
    with f.SessionLocal() as db:
        assert db.get(FinancialTransaction, old_id).superseded_by_id == replacement_id
        assert db.get(FinancialTransaction, replacement_id).amount_minor == corrected_amount
        assert db.get(FinancialTransaction, replacement_id).ledger_status == 'admitted'
        # The real difference caused by the correction remains a review check.
        source = db.get(FinancialSourceDocument, document)
        assert any(check['status'] == 'difference' for check in source.metadata_['statement_import_checks']['checks'])


def test_new_investigator_reading_after_snapshot_is_not_overruled(f):
    from services.financial.statement_reprocessing import create_statement_version
    document = partial_import(f)
    item = snapshot(f)
    with f.SessionLocal() as db:
        version = create_statement_version(db, case_id=f.case.id, evidence_file_id=f.file.id,
            request_id=uuid4(), actor=f.actor, resolve_path=Path)
        assert version.status == 'unprocessed'
    recovery.recover_one(f.SessionLocal, item, Path)
    assert outcome(f, item)[0] == 'review'
    assert 'newer statement reading' in outcome(f, item)[1]['message']
    assert len(rows(f, document)) == 11
