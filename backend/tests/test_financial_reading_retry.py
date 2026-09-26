import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import httpx
from sqlalchemy import select

from postgres.models.evidence import EvidenceFile
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from services.financial import import_batches as service
from services.financial.reading_recovery import missing_reading_reason
from services.financial.reading_job_retry import retry_file_checked
from tests import test_financial_import_batches as fixtures


@pytest.fixture
def fixture():
    batch_fixture = fixtures.BatchImportTests()
    batch_fixture.setUp()
    yield batch_fixture
    batch_fixture.tearDown()


def retry(fixture, batch):
    with fixture.f.SessionLocal() as db:
        return service.retry_file(db, case_id=fixture.f.case.id, batch_id=batch, source_id=fixture.f.file.id)


def test_failed_retained_version_retries_that_version_not_successful_original(fixture):
    f = fixture.f
    batch = fixture.create()
    fixture.advance(batch)
    failed = f.evidence('d' * 64)
    failed.status = 'failed'
    f.db.commit()
    with f.SessionLocal() as db:
        record = db.get(Batch, batch)
        record.files = [{**record.files[0], 'file_id': str(failed.id), 'status': 'error', 'error': 'Reading failed'}]
        db.commit()
    result = retry(fixture, batch)
    assert result['queued']
    assert result['reading_file_id'] == str(failed.id)
    repeated = retry(fixture, batch)
    assert not repeated['queued']
    assert repeated['attempt_id'] == result['attempt_id']
    async def process(db, **kwargs):
        assert kwargs['file_ids'] == [failed.id]
        db.get(EvidenceFile, failed.id).status = 'processing'
        db.commit()
        return {'job_ids': ['retained-failed-reading-job']}
    worker = AsyncMock(side_effect=process)
    asyncio.run(service.advance_batch(f.SessionLocal, batch, Path, worker))
    worker.assert_awaited_once()
    shown = fixture.status(batch)['files'][0]
    assert shown['file_id'] == str(failed.id)
    assert shown['recovery']['attempt_id'] == result['attempt_id']
    assert shown['recovery']['stage'] == 'reading'


@pytest.mark.parametrize('checked', [False, True])
def test_failed_financial_version_retries_while_original_ai_job_remains_running(fixture, checked):
    from uuid import uuid4
    from copy import deepcopy
    from services.financial.statement_reprocessing import create_statement_version
    f = fixture.f
    batch = fixture.create()
    fixture.advance(batch)
    with f.SessionLocal() as db:
        version = create_statement_version(db, case_id=f.case.id, evidence_file_id=f.file.id,
            request_id=uuid4(), actor=f.actor, resolve_path=Path)
        version.status = 'failed'
        version.last_error = 'Synthetic failed Financial reading'
        version_id = version.id
        original = db.get(EvidenceFile, f.file.id)
        original.status = 'processing'
        original.engine_job_id = 'independent-ai-job'
        original.last_processed_profile_snapshot = dict(ingestion_request_id='independent-ai-request', preparation_mode='full')
        record = db.get(Batch, batch)
        record.files = [{**record.files[0], 'file_id': str(version_id), 'status': 'error', 'error': version.last_error}]
        item = db.scalar(select(Item).where(Item.batch_id == batch))
        item.review_request = {'holder': 'Preserve the original review'}
        original_state = (original.status, original.engine_job_id, deepcopy(original.last_processed_profile_snapshot), deepcopy(original.metadata_))
        db.commit()
    ai_job = dict(id='independent-ai-job', case_id=str(f.case.id), source_evidence_file_id=str(f.file.id),
        status='extracting_entities', pipeline_state=dict(ingestion_request_id='independent-ai-request'))
    engine = AsyncMock(return_value=ai_job)
    with patch('services.evidence_engine_client.get_job', engine):
        accepted = checked_retry(fixture, batch) if checked else retry(fixture, batch)
        repeated = checked_retry(fixture, batch) if checked else retry(fixture, batch)
    assert accepted['queued'] and accepted['action'] == 'retry_reading'
    assert accepted['reading_file_id'] == str(version_id)
    assert not repeated['queued'] and repeated['attempt_id'] == accepted['attempt_id']
    engine.assert_not_awaited()
    async def process(db, **kwargs):
        assert kwargs['file_ids'] == [version_id]
        db.get(EvidenceFile, version_id).status = 'processing'
        db.commit()
        return {'job_ids': ['new-financial-job']}
    worker = AsyncMock(side_effect=process)
    asyncio.run(service.advance_batch(f.SessionLocal, batch, Path, worker))
    worker.assert_awaited_once()
    with f.SessionLocal() as db:
        original = db.get(EvidenceFile, f.file.id)
        assert (original.status, original.engine_job_id, original.last_processed_profile_snapshot, original.metadata_) == original_state
        assert db.scalar(select(Item).where(Item.batch_id == batch)).review_request == {'holder': 'Preserve the original review'}
        assert db.get(EvidenceFile, version_id).status == 'processing'


def test_reconciliation_issue_returns_actionable_review_without_queuing(fixture):
    batch = fixture.create()
    fixture.advance(batch)
    result = retry(fixture, batch)
    assert result['action'] == 'review_required'
    assert not result['queued']
    assert result['stage'] == 'statement_review'
    assert 'reconciliation' in result['message']
    assert fixture.status(batch)['files'][0]['recovery']['attempt_id'] == result['attempt_id']


@pytest.mark.parametrize('saved_draft', [False, True])
def test_readable_file_with_stale_batch_error_rebuilds_reviews_without_reading_again(fixture, saved_draft):
    from copy import deepcopy
    f = fixture.f
    batch = fixture.create()
    fixture.advance(batch)
    with f.SessionLocal() as db:
        record = db.get(Batch, batch)
        record.files = [{**record.files[0], 'status': 'error', 'error': 'Statement not found in this case.'}]
        item = db.scalar(select(Item).where(Item.batch_id == batch))
        if saved_draft:
            draft = service.initial_request(service.read_statement_import(db, case_id=f.case.id, evidence_file_id=f.file.id))
            draft['holder'] = 'Investigator corrected holder'
            item.review_request = deepcopy(draft)
            item_id = item.id
        else:
            db.delete(item)
        before_files = set(db.scalars(select(EvidenceFile.id)))
        db.commit()
    accepted = retry(fixture, batch)
    assert accepted['queued'] and accepted['action'] == 'check_statements'
    assert accepted['stage'] == 'checking_statements'
    assert not accepted['fresh_reading']
    repeated = retry(fixture, batch)
    assert not repeated['queued'] and repeated['attempt_id'] == accepted['attempt_id']
    worker = AsyncMock()
    asyncio.run(service.advance_batch(f.SessionLocal, batch, Path, worker))
    worker.assert_not_awaited()
    state = fixture.status(batch)
    assert state['files'][0]['status'] == 'checked'
    assert state['files'][0]['recovery']['stage'] == 'complete'
    assert not state['files'][0].get('error')
    with f.SessionLocal() as db:
        assert set(db.scalars(select(EvidenceFile.id))) == before_files
        items = list(db.scalars(select(Item).where(Item.batch_id == batch)))
        assert len(items) == 1
        if saved_draft:
            assert items[0].id == item_id and items[0].review_request == draft


def test_stale_error_retry_keeps_paused_batch_unchanged(fixture):
    from services.financial.pdf_candidates import PdfMappingError
    f = fixture.f
    batch = fixture.create()
    fixture.advance(batch)
    with f.SessionLocal() as db:
        record = db.get(Batch, batch)
        record.status = 'paused'
        record.files = [{**record.files[0], 'status': 'error', 'error': 'Statement not found in this case.'}]
        db.commit()
    with pytest.raises(PdfMappingError, match='paused'):
        retry(fixture, batch)
    state = fixture.status(batch)
    assert state['status'] == 'paused' and state['files'][0]['status'] == 'error'
    assert not state['files'][0].get('recovery')


@pytest.mark.parametrize('original_has_geometry', [False, True])
def test_old_missing_prepared_pointer_recovers_with_retained_intake_version_without_new_job(fixture, original_has_geometry):
    from copy import deepcopy
    from uuid import NAMESPACE_URL, uuid4, uuid5
    from postgres.models.evidence import EvidenceDocumentText, EvidenceTableGeometry
    from services.financial.statement_reprocessing import create_statement_version
    f = fixture.f
    batch = fixture.create()
    fixture.advance(batch)
    with f.SessionLocal() as db:
        version = create_statement_version(db, case_id=f.case.id, evidence_file_id=f.file.id,
            request_id=uuid5(NAMESPACE_URL, f'loupe-financial-intake:{f.case.id}:{f.file.id}'),
            actor=f.actor, resolve_path=Path)
        version.status = 'processed'
        version.metadata_ = {**version.metadata_, 'investigator_note': 'Retain this saved reading'}
        version_id = version.id
        original_text = db.get(EvidenceDocumentText, f.file.id)
        db.add(EvidenceDocumentText(evidence_file_id=version_id, engine_job_id=original_text.engine_job_id,
            content=original_text.content, content_sha256=original_text.content_sha256,
            character_count=original_text.character_count, source_locations=deepcopy(original_text.source_locations)))
        for geometry in db.scalars(select(EvidenceTableGeometry).where(EvidenceTableGeometry.evidence_file_id == f.file.id)):
            db.add(EvidenceTableGeometry(evidence_file_id=version_id, page_number=geometry.page_number,
                engine_job_id=geometry.engine_job_id, payload=deepcopy(geometry.payload)))
            if not original_has_geometry:
                db.delete(geometry)
        old_item = db.scalar(select(Item).where(Item.batch_id == batch))
        old_item.review_request = {'holder': 'Keep the initial batch correction'}
        old_item_id = old_item.id
        record = db.get(Batch, batch)
        record.files = [{**record.files[0], 'file_id': str(uuid4()), 'status': 'error',
            'error': 'Statement not found in this case.'}]
        record.status = 'review'
        db.commit()
        ids = set(db.scalars(select(EvidenceFile.id)))
    accepted = checked_retry(fixture, batch)
    assert accepted['queued']
    worker = AsyncMock()
    asyncio.run(service.advance_batch(f.SessionLocal, batch, Path, worker))
    worker.assert_not_awaited()
    with f.SessionLocal() as db:
        entry = db.get(Batch, batch).files[0]
        assert entry['status'] == 'checked' and entry['recovery']['stage'] == 'complete'
        assert entry['file_id'] == str(f.file.id if original_has_geometry else version_id)
        assert set(db.scalars(select(EvidenceFile.id))) == ids
        assert db.get(Item, old_item_id).review_request == {'holder': 'Keep the initial batch correction'}
        assert db.get(EvidenceFile, version_id).metadata_['investigator_note'] == 'Retain this saved reading'


def test_stale_error_does_not_reopen_an_import_removal_as_preparation(fixture):
    f = fixture.f
    batch = fixture.create()
    fixture.advance(batch)
    with f.SessionLocal() as db:
        record = db.get(Batch, batch)
        record.files = [{**record.files[0], 'status': 'error', 'error': 'Statement not found in this case.'}]
        file = db.get(EvidenceFile, f.file.id)
        file.metadata_ = {**(file.metadata_ or {}), 'financial_import_removal': {'id': 'synthetic-removal'}}
        db.commit()
    result = retry(fixture, batch)
    assert not result['queued'] and result['action'] == 'source_unavailable'
    assert fixture.status(batch)['files'][0]['status'] == 'error'


@pytest.mark.parametrize('retained', [False, True])
def test_missing_original_persists_actionable_failure_and_only_links_verified_retained_reading(fixture, retained):
    from uuid import uuid4
    f = fixture.f
    batch = fixture.create()
    fixture.advance(batch)
    missing = uuid4()
    with f.SessionLocal() as db:
        record = db.get(Batch, batch)
        record.files = [{**record.files[0], 'source_id': str(missing), 'status': 'error'}]
        if retained:
            file = db.get(EvidenceFile, f.file.id)
            file.metadata_ = {**file.metadata_, 'statement_root_evidence_id': str(missing),
                'statement_parent_evidence_id': str(missing), 'statement_version_request': str(uuid4())}
        db.commit()
        result = asyncio.run(retry_file_checked(db, case_id=f.case.id, batch_id=batch, source_id=missing))
        repeated = service.retry_file(db, case_id=f.case.id, batch_id=batch, source_id=missing)
        assert not result['queued'] and result['action'] == 'source_unavailable'
        assert result['review_file_id'] == (str(f.file.id) if retained else None)
        assert result['attempt_id'] == repeated['attempt_id']
        assert 'Restore the original in Evidence' in db.get(Batch, batch).files[0]['error']
    with f.SessionLocal() as db:
        persisted = db.get(Batch, batch).files[0]['recovery']
        assert persisted['action'] == 'source_unavailable' and persisted['attempt_id'] == result['attempt_id']
    shown = fixture.status(batch)['files'][0]
    assert shown['review_file_id'] == (str(f.file.id) if retained else None)
    assert shown['error'] == result['message']


@pytest.mark.parametrize('fault', ['missing', 'foreign', 'different_bytes', 'different_removal'])
def test_invalid_restart_reference_is_rejected_before_queue_and_again_at_intake(fixture, fault):
    from uuid import uuid4
    from services.financial.evidence_intake import prepare_existing_financial_file
    from services.financial.pdf_candidates import PdfMappingError
    f = fixture.f
    batch = fixture.create()
    fixture.advance(batch)
    restart_id = uuid4()
    if fault != 'missing':
        restart = f.evidence('e' * 64 if fault == 'different_bytes' else f.file.sha256)
        if fault == 'foreign':
            restart.case_id = f.other_case.id
        restart.metadata_ = {'financial_import_removal': {'id': 'other' if fault == 'different_removal' else 'removal'}}
        restart_id = restart.id
        f.db.commit()
    with f.SessionLocal() as db:
        record = db.get(Batch, batch)
        record.files = [{**record.files[0], 'status': 'error'}]
        file = db.get(EvidenceFile, f.file.id)
        file.metadata_ = {**file.metadata_, 'financial_import_removal': {'id': 'removal', 'restart_file_id': str(restart_id)}}
        db.commit()
        result = service.retry_file(db, case_id=f.case.id, batch_id=batch, source_id=f.file.id)
        assert not result['queued'] and result['action'] == 'source_unavailable'
        worker = AsyncMock()
        with pytest.raises(PdfMappingError, match='source recorded for restarting'):
            asyncio.run(prepare_existing_financial_file(db, case_id=f.case.id, evidence_file_id=f.file.id,
                expected_revision='initial', actor=f.actor, resolve_path=Path, process_files=worker))
        worker.assert_not_awaited()
        assert db.get(EvidenceFile, f.file.id).metadata_['financial_import_removal']['id'] == 'removal'


def test_restored_original_can_be_checked_with_a_new_attempt_after_unavailable_receipt(fixture):
    from uuid import uuid4
    f = fixture.f
    batch = fixture.create()
    fixture.advance(batch)
    old_attempt = str(uuid4())
    with f.SessionLocal() as db:
        record = db.get(Batch, batch)
        record.files = [{**record.files[0], 'status': 'error', 'error': 'Source unavailable',
            'recovery': {'attempt_id': old_attempt, 'stage': 'source_unavailable', 'action': 'source_unavailable'}}]
        db.commit()
    result = retry(fixture, batch)
    assert result['queued'] and result['action'] == 'check_statements'
    assert result['attempt_id'] != old_attempt
    fixture.advance(batch)
    assert fixture.status(batch)['files'][0]['status'] == 'checked'


def test_incomplete_reading_attempt_survives_double_click_and_reuses_one_version(fixture):
    f = fixture.f
    batch = fixture.create()
    fixture.advance(batch)
    diagnosis = dict(action='read_again', stage='reading_incomplete', message='Printed activity was omitted.')
    with patch('services.financial.reading_recovery.inspect_completed_reading', return_value=diagnosis):
        accepted = retry(fixture, batch)
        repeated = retry(fixture, batch)
    assert accepted['queued'] and accepted['fresh_reading']
    assert not repeated['queued']
    assert repeated['attempt_id'] == accepted['attempt_id']
    async def process(db, **kwargs):
        version = db.get(EvidenceFile, kwargs['file_ids'][0])
        assert version.id != f.file.id
        assert version.metadata_['statement_version_request'] == accepted['attempt_id']
        assert version.metadata_['statement_pdf_reading_mode'] == 'page_images'
        version.status = 'processing'
        db.commit()
        return {'job_ids': ['fresh-image-reading-job']}
    worker = AsyncMock(side_effect=process)
    asyncio.run(service.advance_batch(f.SessionLocal, batch, Path, worker))
    worker.assert_awaited_once()
    assert retry(fixture, batch)['attempt_id'] == accepted['attempt_id']
    asyncio.run(service.advance_batch(f.SessionLocal, batch, Path, worker))
    worker.assert_awaited_once()
    with f.SessionLocal() as db:
        versions = list(db.scalars(select(EvidenceFile).where(EvidenceFile.metadata_['statement_version_request'].as_string() == accepted['attempt_id'])))
        assert len(versions) == 1
        assert db.get(EvidenceFile, f.file.id).status == 'processed'


def test_review_saved_after_retry_prevents_new_reading(fixture):
    f = fixture.f
    batch = fixture.create()
    fixture.advance(batch)
    with patch('services.financial.reading_recovery.inspect_completed_reading', return_value=dict(
            action='read_again', stage='reading_incomplete', message='Printed activity was omitted.')):
        result = retry(fixture, batch)
    with f.SessionLocal() as db:
        item = db.scalar(select(Item).where(Item.batch_id == batch))
        item.review_request = {'holder': 'Saved after retry was queued'}
        db.commit()
    worker = AsyncMock()
    asyncio.run(service.advance_batch(f.SessionLocal, batch, Path, worker))
    worker.assert_not_awaited()
    shown = fixture.status(batch)['files'][0]
    assert shown['recovery']['stage'] == 'failed'
    assert 'review decision was saved' in shown['error']
    with f.SessionLocal() as db:
        assert db.scalar(select(EvidenceFile).where(EvidenceFile.metadata_['statement_version_request'].as_string() == result['attempt_id'])) is None
        assert db.scalar(select(Item).where(Item.batch_id == batch)).review_request['holder'] == 'Saved after retry was queued'


@pytest.mark.parametrize('after_queued', [False, True])
def test_ignored_duplicate_never_starts_an_automatic_fresh_reading(fixture, after_queued):
    f = fixture.f
    batch = fixture.create()
    fixture.advance(batch)
    diagnosis = dict(action='read_again', stage='reading_incomplete', message='Printed activity was omitted.')
    if after_queued:
        with patch('services.financial.reading_recovery.inspect_completed_reading', return_value=diagnosis):
            assert retry(fixture, batch)['queued']
    with f.SessionLocal() as db:
        item = db.scalar(select(Item).where(Item.batch_id == batch))
        item.status = 'duplicate_ignored'
        db.commit()
    if not after_queued:
        with patch('services.financial.reading_recovery.inspect_completed_reading', return_value=diagnosis):
            result = retry(fixture, batch)
        assert not result['queued'] and result['action'] == 'review_required'
    worker = AsyncMock()
    asyncio.run(service.advance_batch(f.SessionLocal, batch, Path, worker))
    worker.assert_not_awaited()
    with f.SessionLocal() as db:
        assert db.scalar(select(Item).where(Item.batch_id == batch)).status == 'duplicate_ignored'


@pytest.mark.parametrize('rows,currency,missing', [
    ([], '', False),
    ([], 'MXN', False),
    ([dict(kind='balance', fields=dict(balance='0'))], 'MXN', False),
    ([dict(kind='statement_total', fields=dict(total_direction='credit', printed_transaction_count='0', balance='0'))], 'MXN', False),
    ([dict(kind='statement_total', fields=dict(total_direction='credit', printed_transaction_count='NaN', balance=''))], 'MXN', False),
    ([dict(kind='statement_total', fields=dict(total_direction='credit', printed_transaction_count='3', balance='10000'))], 'MXN', True),
    ([dict(kind='transaction', fields=dict(date='')), dict(kind='statement_total', fields=dict(balance='10000'))], 'MXN', False),
])
def test_only_demonstrated_omissions_trigger_automatic_new_reading(rows, currency, missing):
    assert bool(missing_reading_reason(dict(rows=rows, currency=currency))) == missing


def test_known_reading_failure_is_not_hidden_by_text_and_geometry():
    assert missing_reading_reason(dict(reading_failure='Account sections were not separated.', currency='USD', rows=[]))


def active_attempt(fixture, *, job_id='current-engine-job'):
    f = fixture.f
    batch = fixture.create()
    with f.SessionLocal() as db:
        record = db.get(Batch, batch)
        record.files = [{**record.files[0], 'status': 'processing'}]
        file = db.get(EvidenceFile, f.file.id)
        file.status = 'processing'
        file.engine_job_id = job_id
        file.last_processed_profile_snapshot = dict(ingestion_request_id='current-request', preparation_mode='pdf_review')
        db.commit()
    return batch, dict(id=job_id, case_id=str(f.case.id), source_evidence_file_id=str(f.file.id),
        pipeline_state=dict(ingestion_request_id='current-request'), status='extracting_text')


def checked_retry(fixture, batch):
    with fixture.f.SessionLocal() as db:
        return asyncio.run(retry_file_checked(db, case_id=fixture.f.case.id, batch_id=batch, source_id=fixture.f.file.id))


@pytest.mark.parametrize('status,paused,expected', [
    ('failed', False, 'retry_reading'),
    ('extracting_text', False, 'already_running'),
    ('extracting_text', True, 'resume_reading'),
    ('completed', False, 'already_running'),
])
def test_engine_state_not_stale_file_flag_decides_retry(fixture, status, paused, expected):
    batch, payload = active_attempt(fixture)
    payload.update(status=status, paused=paused, error_message='Synthetic interrupted reading')
    with patch('services.evidence_engine_client.get_job', AsyncMock(return_value=payload)):
        result = checked_retry(fixture, batch)
    assert result['action'] == expected
    assert result['queued'] == (status == 'failed')
    if paused:
        assert result['stage'] == 'paused'
    if status == 'completed':
        assert result['stage'] == 'checking_statements'
        fixture.advance(batch)
        assert fixture.status(batch)['files'][0]['status'] == 'checked'


def test_authoritatively_missing_accepted_job_can_be_recovered(fixture):
    batch, _ = active_attempt(fixture)
    request = httpx.Request('GET', 'http://engine.test/jobs/current-engine-job')
    missing = httpx.HTTPStatusError('Missing job', request=request, response=httpx.Response(404, request=request))
    with patch('services.evidence_engine_client.get_job', AsyncMock(side_effect=missing)), \
            patch('services.evidence_engine_client.list_jobs', AsyncMock(return_value=[])):
        result = checked_retry(fixture, batch)
    assert result['queued'] and result['action'] == 'retry_reading'


def test_completed_engine_attempt_reopens_stale_error_batch_for_review(fixture):
    batch, payload = active_attempt(fixture)
    with fixture.f.SessionLocal() as db:
        record = db.get(Batch, batch)
        record.status = 'review'
        record.files = [{**record.files[0], 'status': 'error', 'error': 'Old status failure'}]
        db.commit()
    with patch('services.evidence_engine_client.get_job', AsyncMock(return_value={**payload, 'status': 'completed'})):
        result = checked_retry(fixture, batch)
    assert result['stage'] == 'checking_statements'
    fixture.advance(batch)
    assert fixture.status(batch)['files'][0]['status'] == 'checked'


@pytest.mark.parametrize('prepared_pointer', ['same', 'missing', 'absent'])
def test_verified_active_retry_resumes_error_batch_observation_without_second_job(fixture, prepared_pointer):
    from uuid import uuid4
    batch, payload = active_attempt(fixture)
    with fixture.f.SessionLocal() as db:
        record = db.get(Batch, batch)
        record.status = 'review'
        entry = {**record.files[0], 'status': 'error', 'error': 'Earlier preparation failed'}
        if prepared_pointer != 'same':
            entry['file_id'] = str(uuid4()) if prepared_pointer == 'missing' else None
        record.files = [entry]
        db.commit()
    engine = AsyncMock(return_value=payload)
    with patch('services.evidence_engine_client.get_job', engine):
        result = checked_retry(fixture, batch)
        repeated = checked_retry(fixture, batch)
    assert not result['queued'] and result['action'] == 'already_running'
    assert repeated['attempt_id'] == result['attempt_id']
    with fixture.f.SessionLocal() as db:
        record = db.get(Batch, batch)
        assert record.status == 'preparing'
        assert record.files[0]['status'] == 'processing'
        assert record.files[0]['file_id'] == str(fixture.f.file.id)
        assert 'error' not in record.files[0]
        current = db.get(EvidenceFile, fixture.f.file.id)
        assert current.status == 'processing' and current.engine_job_id == payload['id']
        current.status = 'processed'
        db.commit()
    worker = AsyncMock()
    asyncio.run(service.advance_batch(fixture.f.SessionLocal, batch, Path, worker))
    worker.assert_not_awaited()
    assert fixture.status(batch)['files'][0]['status'] == 'checked'


def test_active_retained_financial_job_remains_the_only_attempt(fixture):
    from uuid import uuid4
    from services.financial.statement_reprocessing import create_statement_version
    f = fixture.f
    batch = fixture.create()
    with f.SessionLocal() as db:
        version = create_statement_version(db, case_id=f.case.id, evidence_file_id=f.file.id,
            request_id=uuid4(), actor=f.actor, resolve_path=Path)
        version_id = version.id
        version.status = 'processing'
        version.engine_job_id = 'retained-financial-job'
        version.last_processed_profile_snapshot = dict(ingestion_request_id='retained-request', preparation_mode='pdf_review')
        original = db.get(EvidenceFile, f.file.id)
        original.status = 'processing'
        original.engine_job_id = 'independent-ai-job'
        original.last_processed_profile_snapshot = dict(ingestion_request_id='independent-request', preparation_mode='full')
        record = db.get(Batch, batch)
        record.status = 'review'
        record.files = [{**record.files[0], 'file_id': str(version_id), 'status': 'error'}]
        ids = set(db.scalars(select(EvidenceFile.id)))
        db.commit()
    payload = dict(id='retained-financial-job', case_id=str(f.case.id), source_evidence_file_id=str(version_id),
        status='extracting_text', pipeline_state=dict(ingestion_request_id='retained-request'))
    engine = AsyncMock(return_value=payload)
    with patch('services.evidence_engine_client.get_job', engine):
        result = checked_retry(fixture, batch)
        repeated = checked_retry(fixture, batch)
    assert not result['queued'] and not repeated['queued']
    assert result['attempt_id'] == repeated['attempt_id']
    assert result['reading_file_id'] == str(version_id)
    assert all(call.args == ('retained-financial-job',) for call in engine.await_args_list)
    worker = AsyncMock()
    asyncio.run(service.advance_batch(f.SessionLocal, batch, Path, worker))
    worker.assert_not_awaited()
    with f.SessionLocal() as db:
        assert set(db.scalars(select(EvidenceFile.id))) == ids
        assert db.get(EvidenceFile, f.file.id).engine_job_id == 'independent-ai-job'
        assert db.get(EvidenceFile, version_id).engine_job_id == 'retained-financial-job'


def test_engine_unavailable_is_not_permission_to_start_duplicate_job(fixture):
    batch, _ = active_attempt(fixture)
    with patch('services.evidence_engine_client.get_job', AsyncMock(side_effect=httpx.ConnectError('Engine unavailable'))):
        result = checked_retry(fixture, batch)
    assert not result['queued'] and result['stage'] == 'status_unavailable'
    with fixture.f.SessionLocal() as db:
        assert db.get(EvidenceFile, fixture.f.file.id).status == 'processing'


def test_unconfirmed_handoff_and_older_attempt_are_not_restarted(fixture):
    batch, payload = active_attempt(fixture, job_id=None)
    payload.update(id='older-job', status='failed', pipeline_state=dict(ingestion_request_id='older-request'))
    with patch('services.evidence_engine_client.list_jobs', AsyncMock(return_value=[payload])):
        result = checked_retry(fixture, batch)
    assert not result['queued'] and result['stage'] == 'awaiting_dispatch'


def test_newer_attempt_wins_race_during_engine_status_check(fixture):
    batch, payload = active_attempt(fixture)
    async def changed_attempt(*args):
        with fixture.f.SessionLocal() as db:
            current = db.get(EvidenceFile, fixture.f.file.id)
            current.engine_job_id = 'new-job'
            current.last_processed_profile_snapshot = dict(ingestion_request_id='new-request')
            db.commit()
        return {**payload, 'status': 'failed'}
    with patch('services.evidence_engine_client.get_job', AsyncMock(side_effect=changed_attempt)):
        with pytest.raises(service.PdfMappingError, match='progressed while'):
            checked_retry(fixture, batch)
    with fixture.f.SessionLocal() as db:
        current = db.get(EvidenceFile, fixture.f.file.id)
        assert current.status == 'processing' and current.engine_job_id == 'new-job'


@pytest.mark.parametrize('changed_bytes', [False, True])
def test_explicit_retained_source_recovery_verifies_bytes_and_preserves_old_work(fixture, changed_bytes):
    from uuid import uuid4
    from copy import deepcopy
    from services.financial.reading_recovery import retry_reference_problem
    from services.financial.pdf_candidates import PdfMappingError
    f = fixture.f
    batch = fixture.create()
    fixture.advance(batch)
    with f.SessionLocal() as db:
        source = db.get(EvidenceFile, f.file.id)
        source.metadata_ = {**source.metadata_, 'financial_import_removal': {
            'id': 'synthetic-removal', 'restart_file_id': str(uuid4())}}
        original_metadata = deepcopy(source.metadata_)
        record = db.get(Batch, batch)
        record.files = [{**record.files[0], 'status': 'error'}]
        item = db.scalar(select(Item).where(Item.batch_id == batch))
        item.review_request = {'holder': 'Preserve investigator correction'}
        item_id = item.id
        db.commit()
        problem = service.retry_file(db, case_id=f.case.id, batch_id=batch, source_id=f.file.id)
        assert problem['retained_source_revision']
        with pytest.raises(PdfMappingError, match='source changed'):
            service.recover_retained_source(db, case_id=f.case.id, batch_id=batch,
                source_id=f.file.id, expected_revision='stale', actor=f.actor)
        db.rollback()
        accepted = service.recover_retained_source(db, case_id=f.case.id, batch_id=batch,
            source_id=f.file.id, expected_revision=problem['retained_source_revision'], actor=f.actor)
        repeated = service.recover_retained_source(db, case_id=f.case.id, batch_id=batch,
            source_id=f.file.id, expected_revision=problem['retained_source_revision'], actor=f.actor)
        assert accepted['queued'] and not repeated['queued']
        assert accepted['attempt_id'] == repeated['attempt_id']
        before_ids = set(db.scalars(select(EvidenceFile.id)))
    if changed_bytes:
        f.path.write_bytes(b'changed synthetic source')
    async def process(db, **kwargs):
        version = db.get(EvidenceFile, kwargs['file_ids'][0])
        assert version.id != f.file.id
        assert version.sha256 == f.file.sha256
        assert version.metadata_['statement_reset_revision'] == 'synthetic-removal'
        assert version.metadata_['statement_version_actor']['user_id'] == str(f.actor.user_id)
        assert Path(version.stored_path).read_bytes() == f.path.read_bytes()
        version.status = 'processing'
        db.commit()
        return {'job_ids': ['synthetic-new-reading']}
    worker = AsyncMock(side_effect=process)
    asyncio.run(service.advance_batch(f.SessionLocal, batch, Path, worker))
    with f.SessionLocal() as db:
        source = db.get(EvidenceFile, f.file.id)
        assert source.metadata_ == original_metadata
        assert db.get(Item, item_id).review_request == {'holder': 'Preserve investigator correction'}
        entry = db.get(Batch, batch).files[0]
        if changed_bytes:
            worker.assert_not_awaited()
            assert entry['status'] == 'error'
            assert 'bytes no longer match' in entry['error']
            assert set(db.scalars(select(EvidenceFile.id))) == before_ids
        else:
            worker.assert_awaited_once()
            assert entry['status'] == 'processing'
            from uuid import UUID
            version = db.get(EvidenceFile, UUID(entry['file_id']))
            assert retry_reference_problem(db, case_id=f.case.id, source_id=f.file.id,
                source=source, prepared=version) is None
            assert len(set(db.scalars(select(EvidenceFile.id))) - before_ids) == 1
            from services.financial.recovery_followup import current_scope
            scope, reopening = current_scope(db, [source, version])
            assert [record.id for record in scope] == [version.id]
            assert reopening['request_id'] == accepted['attempt_id']
