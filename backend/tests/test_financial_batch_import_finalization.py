"""Accepted batch imports release outer locks and keep one durable outcome."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select

from postgres.base import Base
from postgres.models.financial import FinancialTransaction as Payment
from postgres.models.financial_import_batches import FinancialImportBatchItem as Item, FinancialImportOperation as Operation
from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
from services.financial import import_batches as batches
from services.financial.import_removal import preview_removal, remove_imports
from services.financial.pdf_candidates import PdfMappingError
from tests import test_financial_import_batches as fixtures


@pytest.fixture
def accepted():
    fixture = fixtures.BatchImportTests()
    fixture.setUp()
    try:
        f = fixture.f
        Base.metadata.create_all(f.engine, tables=[WorkspaceEntry.__table__, WorkspaceEntryLink.__table__])
        batch = fixture.create()
        fixture.advance(batch)
        with f.SessionLocal() as db:
            queued = batches.queue_import(db, case_id=f.case.id, batch_id=batch,
                expected_revision=fixture.status(batch)['ready_revision'], actor=f.actor)
            item = db.scalar(select(Item).where(Item.batch_id == batch))
            yield_context = dict(f=f, batch=batch, item=item.id, operation=queued['operation']['id'])
        yield yield_context
    finally:
        fixture.tearDown()


def run(ctx):
    batches._import_item(ctx['f'].SessionLocal, ctx['f'].case.id, ctx['batch'], ctx['item'], Path)


def state(ctx):
    with ctx['f'].SessionLocal() as db:
        item = db.get(Item, ctx['item'])
        operation = db.scalar(select(Operation).where(Operation.batch_id == ctx['batch']))
        return dict(status=item.status, summary=deepcopy(item.summary), request=deepcopy(item.review_request),
            outcomes=deepcopy(operation.outcomes), operation=str(operation.id),
            payments=set(db.scalars(select(Payment.id))))


def remove(ctx):
    f = ctx['f']
    with f.SessionLocal() as db:
        preview = preview_removal(db, case_id=f.case.id, batch_ids=[ctx['batch']])
        remove_imports(db, case_id=f.case.id, actor=f.actor, batch_ids=[ctx['batch']],
            expected_revision=preview['revision'])


def test_lost_response_replays_same_accepted_receipt_without_new_payments(accepted):
    actual = batches.confirm_statement_import
    def lost(**kwargs):
        actual(**kwargs)
        raise SystemExit('Synthetic process exit after committed import')
    with patch.object(batches, 'confirm_statement_import', side_effect=lost), pytest.raises(SystemExit):
        run(accepted)
    before = state(accepted)
    assert before['status'] == 'pending_import' and len(before['payments']) == 12
    run(accepted)
    after = state(accepted)
    assert after['status'] == 'imported' and after['payments'] == before['payments']
    assert after['operation'] == accepted['operation']
    assert after['outcomes'][0]['status'] == 'already_present'
    run(accepted)
    assert state(accepted) == after


@pytest.mark.parametrize('late_failure', [False, True])
def test_late_worker_never_overwrites_first_successful_outcome(accepted, late_failure):
    actual = batches.confirm_statement_import
    completed = None
    def overlap(**kwargs):
        nonlocal completed
        with patch.object(batches, 'confirm_statement_import', side_effect=actual):
            run(accepted)
        completed = state(accepted)
        if late_failure:
            raise PdfMappingError('Synthetic late failure.', 409)
        return actual(**kwargs)
    with patch.object(batches, 'confirm_statement_import', side_effect=overlap):
        run(accepted)
    assert state(accepted) == completed
    assert len(completed['payments']) == 12 and completed['outcomes'][0]['status'] == 'imported'


@pytest.mark.parametrize('later_edit', [False, True])
def test_success_resolves_only_its_exact_concurrent_failure(accepted, later_edit):
    actual = batches.confirm_statement_import
    failure_state = None
    def overlap(**kwargs):
        nonlocal failure_state
        receipt = actual(**kwargs)
        with patch.object(batches, 'confirm_statement_import', side_effect=PdfMappingError('Synthetic response failure.', 409)):
            run(accepted)
        if later_edit:
            with accepted['f'].SessionLocal() as db:
                item = db.get(Item, accepted['item'])
                item.review_request = {**(item.review_request or {}), 'holder': 'Later saved investigator correction'}
                db.commit()
        failure_state = state(accepted)
        assert failure_state['status'] == 'attention'
        return receipt
    with patch.object(batches, 'confirm_statement_import', side_effect=overlap):
        run(accepted)
    after = state(accepted)
    if later_edit:
        assert after == failure_state
    else:
        assert after['status'] == 'imported' and len(after['payments']) == 12
        assert not after['summary'].get('import_failed')
        assert after['outcomes'][0]['status'] == 'imported'
        assert not after['outcomes'][0].get('message')
        assert after['operation'] == accepted['operation']


@pytest.mark.parametrize('before_admission', [False, True])
def test_removal_wins_before_admission_and_after_commit_before_finalization(accepted, before_admission):
    actual = batches.confirm_statement_import
    removed_state = None
    def overlap(**kwargs):
        nonlocal removed_state
        if before_admission:
            remove(accepted)
            removed_state = state(accepted)
            return actual(**kwargs)
        receipt = actual(**kwargs)
        remove(accepted)
        removed_state = state(accepted)
        return receipt
    with patch.object(batches, 'confirm_statement_import', side_effect=overlap):
        run(accepted)
    assert state(accepted) == removed_state
    assert removed_state['status'] == 'removed'
    with accepted['f'].SessionLocal() as db:
        from services.financial.transaction_query import list_transactions
        assert list_transactions(db, accepted['f'].case.id) == []
    assert len(removed_state['payments']) == (0 if before_admission else 12)
