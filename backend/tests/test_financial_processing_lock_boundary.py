"""Financial reading handoff releases network waits, then rechecks visibility.

SQLite does not enforce FOR UPDATE. Record the ORM lock/commit boundaries and
use independent sessions to verify durable state and removal guards instead of
claiming this test reproduces PostgreSQL blocking itself.
"""
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import event

from postgres.models.evidence import EvidenceFile
from services import evidence_processing_service as processing
from services.financial.file_visibility import set_financial_file_visibility
from services.financial.pdf_candidates import PdfMappingError
from services.financial.statement_reprocessing import create_statement_version


@pytest.fixture
def intake():
    from tests.test_financial_file_intake import FinancialFileIntakeTests
    fixture = FinancialFileIntakeTests('test_retry_does_not_duplicate_events_and_case_scope_is_checked')
    fixture.setUp()
    fixture.file.status = 'failed'
    fixture.db.commit()
    try:
        yield fixture
    finally:
        fixture.tearDown()


@pytest.fixture
def handoff(intake, monkeypatch):
    locks, milestones = [], []

    def observe(state):
        if state.is_select and getattr(state.statement, '_for_update_arg', None) is not None:
            locks.extend(str(table) for table in state.statement.get_final_froms())

    def release(session):
        locks.clear()
        milestones.append('commit')

    event.listen(intake.db, 'do_orm_execute', observe)
    event.listen(intake.db, 'after_commit', release)

    async def reconcile(db, case_id):
        assert not locks, locks
        assert not db.in_transaction()
        milestones.append('reconcile')
        return 0

    original_mark = processing.EvidenceDBStorage.mark_processing

    def mark(db, file_ids, force=False):
        assert 'cases' in locks and 'evidence_files' in locks
        milestones.append('mark')
        return original_mark(db, file_ids, force=force)

    async def upload(**kwargs):
        assert not locks, locks
        assert not intake.db.in_transaction()
        milestones.append('upload')
        identifier = kwargs['processing_metadata'][0]['source_evidence_file_id']
        from uuid import UUID
        with intake.SessionLocal() as observer:
            file = observer.get(EvidenceFile, UUID(identifier))
            assert file.status == 'processing'
            assert file.last_processed_profile_snapshot['ingestion_request_id'] == kwargs['processing_metadata'][0]['ingestion_request_id']
            with pytest.raises(PdfMappingError, match='still processing'):
                set_financial_file_visibility(observer, case_id=intake.case.id, evidence_file_id=file.id,
                    removed=True, expected_revision='initial', actor=intake.actor)
        return [{'id': str(uuid4())}]

    monkeypatch.setattr(processing, 'reconcile_case_jobs', reconcile)
    monkeypatch.setattr(processing, 'build_processing_snapshot', lambda *args, **kwargs: {})
    monkeypatch.setattr(processing.EvidenceDBStorage, 'mark_processing', mark)
    monkeypatch.setattr(processing.evidence_engine_client, 'upload_file_paths_batch', upload)
    subscriber = SimpleNamespace(track_jobs=AsyncMock())
    monkeypatch.setattr(processing, 'get_subscriber', lambda: subscriber)
    try:
        yield locks, milestones
    finally:
        event.remove(intake.db, 'do_orm_execute', observe)
        event.remove(intake.db, 'after_commit', release)


def test_visible_failed_preparation_releases_before_status_check_and_locks_handoff(intake, handoff):
    result = intake.prepare(process=processing.process_db_files)
    assert result['outcome'] == 'queued'
    _, milestones = handoff
    assert milestones == ['commit', 'reconcile', 'mark', 'commit', 'upload', 'commit']


def test_idempotent_reprocess_handler_releases_existing_version_locks(intake, handoff):
    request_id = uuid4()
    version = create_statement_version(intake.db, case_id=intake.case.id,
        evidence_file_id=intake.file.id, request_id=request_id, actor=intake.actor, resolve_path=Path)
    version.status = 'failed'
    intake.db.commit()
    handoff[1].clear()
    from routers.financial_statement_import import ReprocessRequest, reprocess
    result = asyncio.run(reprocess(intake.file.id, ReprocessRequest(request_id=request_id),
        case_id=intake.case.id, user=intake.user, db=intake.db))
    assert result['evidence_file_id'] == str(version.id)
    assert handoff[1] == ['commit', 'reconcile', 'mark', 'commit', 'upload', 'commit']


def test_removal_during_status_check_is_revalidated_before_any_dispatch(intake, handoff, monkeypatch):
    case_id, file_id = intake.case.id, intake.file.id

    async def remove_during_check(db, ignored_case_id):
        assert not handoff[0] and not db.in_transaction()
        with intake.SessionLocal() as other:
            set_financial_file_visibility(other, case_id=case_id, evidence_file_id=file_id,
                removed=True, expected_revision='initial', actor=intake.actor)
        return 0

    monkeypatch.setattr(processing, 'reconcile_case_jobs', remove_during_check)
    with pytest.raises(PdfMappingError, match='removed from Financial'):
        intake.prepare(process=processing.process_db_files)
    intake.db.rollback()
    assert 'mark' not in handoff[1] and 'upload' not in handoff[1]
    assert intake.file.status == 'failed'
    assert not intake.file.last_processed_profile_snapshot


def test_authoritative_running_attempt_prevents_dispatch_for_stale_failed_status(intake, handoff, monkeypatch):
    case_id, file_id, job_id = intake.case.id, intake.file.id, str(uuid4())

    async def current_running_job(db, ignored_case_id):
        assert not handoff[0] and not db.in_transaction()
        with intake.SessionLocal() as other:
            file = other.get(EvidenceFile, file_id)
            file.status = 'processing'
            file.engine_job_id = job_id
            other.commit()
        return 1

    monkeypatch.setattr(processing, 'reconcile_case_jobs', current_running_job)
    with pytest.raises(PdfMappingError, match='job could not be confirmed'):
        intake.prepare(process=processing.process_db_files)
    intake.db.rollback()
    assert intake.file.engine_job_id == job_id
    assert intake.file.status == 'processing'
    assert 'mark' not in handoff[1] and 'upload' not in handoff[1]


def test_full_ingestion_keeps_its_existing_status_reconciliation(intake, monkeypatch):
    reconcile = AsyncMock(return_value=0)
    upload = AsyncMock(return_value=[{'id': str(uuid4())}])
    monkeypatch.setattr(processing, 'reconcile_case_jobs', reconcile)
    monkeypatch.setattr(processing, 'build_processing_snapshot', lambda *args, **kwargs: {})
    monkeypatch.setattr(processing.evidence_engine_client, 'upload_file_paths_batch', upload)
    monkeypatch.setattr(processing, 'get_subscriber', lambda: SimpleNamespace(track_jobs=AsyncMock()))
    result = asyncio.run(processing.process_db_files(intake.db, case_id=intake.case.id,
        file_ids=[intake.file.id], preparation_mode='full'))
    assert len(result['job_ids']) == 1
    reconcile.assert_awaited_once_with(intake.db, str(intake.case.id))
    upload.assert_awaited_once()
