"""Regression: Evidence uploads must not silently become financial statements."""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from postgres.base import Base
from postgres.models.evidence import EvidenceFile, IngestionLog
from postgres.models.financial import FinancialSourceDocument
from postgres.models.financial_candidates import FinancialCandidateMapping, FinancialStatementReviewDraft
from postgres.models.financial_import_batches import FinancialImportBatch
from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
from services.evidence_db_storage import EvidenceDBStorage
from services.financial.file_scope import financial_file_ids, mark_financial_workspace
from services.financial.file_visibility import set_financial_file_visibility
from services.financial.import_batches import create_batch
from tests import test_financial_statement_import as fixture_module


@pytest.fixture
def f():
    value = fixture_module.StatementImportTests()
    value.setUp()
    # The common ledger fixture also seeds an unrelated, already imported PDF.
    value.seeded_file_ids = set(value.db.scalars(select(EvidenceFile.id))) - {value.file.id}
    Base.metadata.create_all(value.engine, tables=[FinancialCandidateMapping.__table__,
        FinancialStatementReviewDraft.__table__, WorkspaceEntry.__table__, WorkspaceEntryLink.__table__,
        IngestionLog.__table__])
    yield value
    value.tearDown()


def listing(f, financial=False, versions=True):
    from routers.evidence import list_evidence
    with f.SessionLocal() as db:
        rows = asyncio.run(list_evidence(case_id=str(f.case.id), status_filter=None,
            include_cellebrite_artifacts=False, include_reading_versions=versions,
            financial_only=financial, user={}, db=db))['files']
        return [row for row in rows if row['id'] not in {str(value) for value in f.seeded_file_ids}]


def test_unprocessed_upload_and_full_ai_reading_stay_only_in_evidence(f):
    # Fixture already has text and table geometry: those do not prove intent.
    f.file.status = 'unprocessed'
    f.file.original_filename = 'Interview transcript.pdf'
    f.db.commit()
    before = (f.file.stored_path, f.file.sha256, f.file.metadata_, f.file.engine_job_id)
    assert [row['id'] for row in listing(f)] == [str(f.file.id)]
    assert listing(f, financial=True) == []
    for state in ('processing', 'processed', 'failed'):
        f.file.status = state
        f.file.last_processed_profile_snapshot = {'preparation_mode': 'full'}
        f.db.commit()
        assert listing(f, financial=True) == []
        assert listing(f)[0]['status'] == state
    f.db.refresh(f.file)
    assert before == (f.file.stored_path, f.file.sha256, f.file.metadata_, f.file.engine_job_id)
    assert not f.db.scalar(select(FinancialSourceDocument.id).where(FinancialSourceDocument.evidence_file_id == f.file.id))
    assert not f.db.scalar(select(FinancialImportBatch.id))


def test_explicit_selection_enters_financial_before_worker_and_survives_reopen(f):
    other = f.evidence('b' * 64)
    other.original_filename = 'Unrelated chat.pdf'
    f.db.commit()
    with f.SessionLocal() as db:
        create_batch(db, case_id=f.case.id, request_id=uuid4(), file_ids=[f.file.id],
            folder_ids=[], actor=f.actor)
    assert {row['id'] for row in listing(f)} == {str(f.file.id), str(other.id)}
    assert [row['id'] for row in listing(f, financial=True)] == [str(f.file.id)]
    f.db.refresh(f.file)
    assert f.file.engine_job_id is None  # Listing/enrolment does not enqueue a job.
    with f.SessionLocal() as db:
        assert financial_file_ids(db, case_id=f.other_case.id) == set()


def test_existing_import_and_superseded_history_remain_visible(f):
    f.confirm()
    assert [row['id'] for row in listing(f, financial=True)] == [str(f.file.id)]
    # Removed/superseded saved imports still belong in retained financial history.
    with f.SessionLocal() as db:
        source = db.scalar(select(FinancialSourceDocument).where(FinancialSourceDocument.evidence_file_id == f.file.id))
        source.status = 'superseded'
        db.commit()
    assert len(listing(f, financial=True)) == 1


def test_legacy_reviews_and_preparation_are_recognised_without_name_guessing(f):
    for metadata, snapshot in (
        ({'financial_review_progress': {'period': {'request': {}}}}, {}),
        ({}, {'preparation_mode': 'pdf_review'}),
    ):
        f.file.metadata_ = metadata
        f.file.last_processed_profile_snapshot = snapshot
        f.db.commit()
        assert len(listing(f, financial=True)) == 1
    f.file.metadata_ = {}
    f.file.last_processed_profile_snapshot = {}
    f.file.original_filename = 'Bank statement.pdf'
    f.db.commit()
    assert listing(f, financial=True) == []
    f.db.add(FinancialStatementReviewDraft(evidence_file_id=f.file.id, case_id=f.case.id,
        version=1, statement_scopes=[], actor={}))
    f.db.commit()
    assert len(listing(f, financial=True)) == 1


def test_preparation_membership_survives_later_full_processing(f):
    EvidenceDBStorage.set_processing_snapshot(f.db, f.file.id,
        profile_snapshot={'preparation_mode': 'pdf_review'}, folder_id=None)
    f.db.commit()
    first = f.file.metadata_['financial_workspace']
    EvidenceDBStorage.set_processing_snapshot(f.db, f.file.id,
        profile_snapshot={'preparation_mode': 'full'}, folder_id=None)
    f.db.commit()
    assert len(listing(f, financial=True)) == 1
    assert f.file.metadata_['financial_workspace'] == first


def test_reading_family_is_preserved_but_same_hash_upload_is_not_enrolled(f):
    original = f.file
    copy = f.evidence(original.sha256)
    copy.metadata_ = {'statement_root_evidence_id': str(original.id),
        'statement_parent_evidence_id': str(original.id), 'statement_version_request': str(uuid4())}
    independent = f.evidence(original.sha256)
    foreign = f.evidence('f' * 64)
    foreign.case_id = f.other_case.id
    foreign.metadata_ = {'financial_review_progress': {'period': {'request': {}}},
        'statement_root_evidence_id': str(independent.id)}
    f.db.commit()
    assert {row['id'] for row in listing(f, financial=True)} == {str(original.id), str(copy.id)}
    assert [row['id'] for row in listing(f, financial=True, versions=False)] == [str(original.id)]


def test_hidden_file_can_be_restored_and_ordinary_evidence_is_unchanged(f):
    mark_financial_workspace(f.file, user_id=f.user.id)
    f.db.commit()
    result = set_financial_file_visibility(f.db, case_id=f.case.id, evidence_file_id=f.file.id,
        removed=True, expected_revision='initial', actor=f.actor)
    assert listing(f, financial=True)[0]['financial_removed'] is True
    assert len(listing(f)) == 1
    set_financial_file_visibility(f.db, case_id=f.case.id, evidence_file_id=f.file.id,
        removed=False, expected_revision=result['financial_visibility_revision'], actor=f.actor)
    assert listing(f, financial=True)[0]['financial_removed'] is False


def test_explicit_reuse_of_processed_evidence_records_intent_without_ai_job(f):
    from services.financial.evidence_intake import prepare_existing_financial_file
    f.file.status = 'processed'
    f.db.commit()
    assert listing(f, financial=True) == []
    process = AsyncMock()
    result = asyncio.run(prepare_existing_financial_file(f.db, case_id=f.case.id,
        evidence_file_id=f.file.id, expected_revision='initial', actor=f.actor,
        resolve_path=Path, process_files=process))
    assert result['outcome'] == 'ready'
    process.assert_not_called()
    assert len(listing(f, financial=True)) == 1


@pytest.mark.parametrize('extension', ['csv', 'tsv', 'xlsx', 'xls', 'docx', 'doc', 'png', 'jpeg', 'xml', 'dat'])
def test_financial_membership_is_independent_of_format_and_does_not_start_processing(f, extension):
    from routers.financial_statement_import import FinancialSourceChoice
    from services.financial.evidence_intake import include_financial_sources, resolve_financial_selection
    f.file.original_filename = f'Financial source.{extension}'
    f.db.commit()
    assert listing(f, financial=True) == []  # A financial-looking name is not classification.
    preview = resolve_financial_selection(f.db, case_id=f.case.id, file_ids=[f.file.id],
        folder_ids=[], include_other_formats=True)
    assert preview['skipped_non_pdf'] == 0
    assert [item['id'] for item in preview['files']] == [str(f.file.id)]
    choice = FinancialSourceChoice(evidence_file_id=f.file.id, expected_revision='initial')
    before = (f.file.sha256, f.file.stored_path, f.file.status, f.file.engine_job_id)
    result = include_financial_sources(f.db, case_id=f.case.id, selections=[choice], actor=f.actor)
    assert result['file_ids'] == [str(f.file.id)]
    assert len(listing(f, financial=True)) == 1
    assert include_financial_sources(f.db, case_id=f.case.id, selections=[choice], actor=f.actor) == result
    assert len(list(f.db.scalars(select(IngestionLog)))) == 1
    f.db.refresh(f.file)
    assert before == (f.file.sha256, f.file.stored_path, f.file.status, f.file.engine_job_id)
    assert not f.db.scalar(select(FinancialImportBatch.id))
    removed = set_financial_file_visibility(f.db, case_id=f.case.id, evidence_file_id=f.file.id,
        removed=True, expected_revision='initial', actor=f.actor)
    from services.financial.pdf_candidates import PdfMappingError
    with pytest.raises(PdfMappingError, match='changed after the preview'):
        include_financial_sources(f.db, case_id=f.case.id, selections=[choice], actor=f.actor)
    f.db.rollback()
    choice.expected_revision = removed['financial_visibility_revision']
    include_financial_sources(f.db, case_id=f.case.id, selections=[choice], actor=f.actor)
    assert listing(f, financial=True)[0]['financial_removed'] is False
    assert len(listing(f)) == 1  # No copies or deleted originals.


def test_existing_non_pdf_financial_source_survives_scope_filter(f):
    f.confirm()
    f.file.original_filename = 'native-bank-export.xml'
    f.db.commit()
    assert len(listing(f, financial=True)) == 1


def test_source_selection_is_case_scoped_and_all_or_nothing(f):
    from routers.financial_statement_import import FinancialSourceChoice
    from services.financial.evidence_intake import include_financial_sources
    from services.financial.pdf_candidates import PdfMappingError
    foreign = f.evidence('z' * 64)
    foreign.case_id = f.other_case.id
    f.db.commit()
    choices = [FinancialSourceChoice(evidence_file_id=file.id, expected_revision='initial')
        for file in (f.file, foreign)]
    with pytest.raises(PdfMappingError, match='no longer available'):
        include_financial_sources(f.db, case_id=f.case.id, selections=choices, actor=f.actor)
    f.db.rollback()
    assert listing(f, financial=True) == []
    assert not list(f.db.scalars(select(IngestionLog)))


def test_source_selection_route_requires_case_edit_permission(f):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from types import SimpleNamespace
    from unittest.mock import patch
    from routers import financial_statement_import as routes
    from tests.test_route_authorization import _CaseAccessDb
    from postgres.session import get_db
    from routers.users import get_current_db_user
    app = FastAPI()
    app.include_router(routes.router)
    user = SimpleNamespace(id=uuid4(), global_role='user', is_active=True)
    db = _CaseAccessDb(membership=SimpleNamespace(permissions={'case': {'view': True, 'edit': False}}))
    app.dependency_overrides[get_current_db_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    with patch('services.financial.evidence_intake.include_financial_sources') as include:
        response = TestClient(app).post('/api/financial/statement-import/selection/include',
            params={'case_id': str(db.case.id)}, json={'files': [
                {'evidence_file_id': str(f.file.id), 'expected_revision': 'initial'}]})
    assert response.status_code == 403
    include.assert_not_called()
