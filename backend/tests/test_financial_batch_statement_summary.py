"""File progress, prepared reviews and overlapping reasons are different counts."""
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from uuid import uuid4

from sqlalchemy import event, select

from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from services.financial import import_batches as service
from services.financial.batch_review_summary import statement_summary
from services.financial.statement_admission import assess_admission
from services.financial.statement_import import StatementImportRequest
from tests.financial_reconciled_fixture import install_reconciled_source
from tests import test_financial_import_batches as fixtures


class BatchStatementSummaryTests(TestCase):
    def test_whole_batch_counts_are_independent_of_files_filters_and_pagination(self):
        fixture = fixtures.BatchImportTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        f = fixture.f
        install_reconciled_source(f, quiet=True)
        proposal = f.preview()
        raw = service.initial_request(proposal)
        unconfirmed = assess_admission(proposal, StatementImportRequest.model_validate(raw))
        self.assertFalse(unconfirmed['can_import'])
        raw.update(no_activity_confirmed=True, no_activity_revision=unconfirmed['revision'])
        _, quiet = service.assess(proposal, raw)
        self.assertTrue(quiet['can_import'])
        self.assertEqual(quiet['admission']['status'], 'confirmed_no_activity')
        files = [f.file]
        for index in range(10):
            file = f.evidence(f'{index + 100:064x}')
            file.original_filename = f'Synthetic collection {index + 2}.pdf'
            file.status = 'processed'
            files.append(file)
        f.db.commit()
        batch_id = uuid4()
        with f.SessionLocal() as db:
            db.add(Batch(id=batch_id, case_id=f.case.id, created_by=f.user.id,
                actor=dict(user_id=str(f.user.id), name='Synthetic reviewer'), status='review',
                files=[dict(source_id=str(file.id), file_id=str(file.id), filename=file.original_filename,
                    status='checked') for file in files]))
            for index in range(14):
                summary = {**deepcopy(quiet), 'account': f'SYNTHETIC{index:04}',
                    'filename': files[index % 11].original_filename}
                state = 'ready' if index < 7 else 'attention' if index < 13 else 'imported'
                if state == 'attention':
                    summary.update(can_import=False, problem_count=2, problems=[
                        dict(kind='statement_detail', field='holder', message='Enter the account holder.'),
                        dict(kind='statement_detail', field='period', message='Check the statement period.')])
                elif state == 'imported':
                    summary.update(can_import=False, problem_count=1,
                        problems=[dict(kind='reading', message='Check the retained source note.')])
                db.add(Item(id=uuid4(), batch_id=batch_id, file_id=files[index % 11].id,
                    statement_key=f'period-{index:02}', status=state, summary=summary))
            db.commit()
            before = [(item.id, item.status, deepcopy(item.summary)) for item in db.scalars(select(Item).where(Item.batch_id == batch_id))]
            queries = []
            def observe(_connection, _cursor, statement, *_args):
                queries.append(statement)
            event.listen(f.engine, 'before_cursor_execute', observe)
            try:
                full = service.batch_status(db, case_id=f.case.id, batch_id=batch_id, limit=2)
                filtered = service.batch_status(db, case_id=f.case.id, batch_id=batch_id,
                    review_group='holder', only_problems=True, offset=2, limit=2)
            finally:
                event.remove(f.engine, 'before_cursor_execute', observe)
            self.assertTrue(all(query.lstrip().upper().startswith('SELECT') for query in queries))
            self.assertEqual(before, [(item.id, item.status, item.summary) for item in db.scalars(select(Item).where(Item.batch_id == batch_id))])
        summary = full['statement_summary']
        self.assertEqual(summary, dict(total=14, available=7, blocked=6, imported=1,
            pending_import=0, skipped=0, duplicate_ignored=0, assigned=0, other=0,
            available_with_payments=0, available_no_activity=7, available_other=0))
        self.assertEqual(len(full['files']), 11)
        self.assertEqual(sum(file['status'] == 'checked' for file in full['files']), 11)
        self.assertEqual(full['available_transactions'], 0)
        self.assertEqual(full['available_statements'], 7)
        self.assertEqual(filtered['statement_summary'], summary)
        self.assertEqual((full['total'], filtered['total'], len(filtered['items'])), (14, 6, 2))
        reasons = {reason['id']: reason for reason in full['review_summary']['groups']}
        self.assertEqual(reasons['holder']['statement_count'], 6)
        self.assertEqual(reasons['dates']['statement_count'], 6)
        self.assertEqual(full['review_summary']['blocked_statements'], 6)
        self.assertEqual(full['review_summary']['imported_with_checks'], 1)

    def test_unknown_zero_rows_and_stale_confirmation_never_count_as_quiet(self):
        current = dict(can_import=True, assessment_current=True,
            status='confirmed_no_activity', no_activity_confirmed=True)
        items = [SimpleNamespace(status='ready', summary=dict(transaction_count=0, can_import=True,
            admission=admission)) for admission in ({}, {**current, 'assessment_current': False},
                {**current, 'can_import': False}, {**current, 'no_activity_confirmed': False}, current)]
        items.extend([
            SimpleNamespace(status='attention', summary=dict(transaction_count=0, can_import=False,
                reading_failure='No payments could be read.')),
            SimpleNamespace(status='ready', summary=dict(can_import=True)),
            SimpleNamespace(status='ready', summary=dict(transaction_count=3, can_import=True)),
        ])
        before = deepcopy([vars(item) for item in items])
        result = statement_summary(items)
        self.assertEqual((result['total'], result['available'], result['blocked']), (8, 7, 1))
        self.assertEqual((result['available_with_payments'], result['available_no_activity'], result['available_other']), (1, 1, 5))
        self.assertEqual([vars(item) for item in items], before)
        for payment_count, admission in ((False, current), ('0', current), (None, current), (0, 'legacy')):
            with self.subTest(payment_count=payment_count, admission=admission):
                unknown = statement_summary([SimpleNamespace(status='ready', summary=dict(
                    can_import=True, transaction_count=payment_count, admission=admission))])
                self.assertEqual(unknown['available_no_activity'], 0)
                self.assertEqual(unknown['available_other'], 1)

    def test_other_dispositions_partition_once_and_removed_readings_are_not_current(self):
        statuses = ['imported', 'pending_import', 'skipped', 'duplicate_ignored', 'assigned',
            'future_status', 'removed', 'superseded_reading']
        result = statement_summary([SimpleNamespace(status=status, summary={}) for status in statuses])
        self.assertEqual(result['total'], 6)
        self.assertEqual(sum(result[key] for key in ('available', 'blocked', 'imported', 'pending_import',
            'skipped', 'duplicate_ignored', 'assigned', 'other')), 6)
        self.assertTrue(all(result[key] == 1 for key in ('imported', 'pending_import', 'skipped',
            'duplicate_ignored', 'assigned', 'other')))
