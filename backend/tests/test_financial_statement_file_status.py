from services.financial.statement_file_status import statement_file_status
from tests.test_financial_duplicates import DuplicateTestCase


class StatementFileStatusTests(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        from postgres.base import Base
        from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
        from postgres.models.financial_import_batches import FinancialImportBatch, FinancialImportBatchItem
        Base.metadata.create_all(self.db.connection(), tables=[WorkspaceEntry.__table__, WorkspaceEntryLink.__table__, FinancialImportBatch.__table__, FinancialImportBatchItem.__table__])

    def test_individual_import_cannot_still_be_offered_as_ready_by_old_batch_snapshot(self):
        from uuid import uuid4
        from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
        document = self.make_document()
        document.document_type = 'statement_review'
        document.metadata_ = {'statement_import_statement_id': 'saved-period'}
        self.make_period(document)
        batch = Batch(id=uuid4(), case_id=self.case.id, created_by=self.user.id, actor={}, files=[], status='review')
        self.db.add(batch); self.db.flush()
        for key in ('saved-period', 'new-period'):
            self.db.add(Item(id=uuid4(), batch_id=batch.id, file_id=document.evidence_file_id,
                statement_key=key, status='ready', summary={'can_import': True}))
        self.db.commit()
        file = statement_file_status(self.db, case_id=self.case.id)['files'][0]
        self.assertEqual(file['prepared_periods'], 2)
        self.assertEqual(file['available_periods'], 1)
        self.assertEqual([p['statement_id'] for p in file['ready_periods']], ['new-period'])
        self.assertEqual(len(file['periods']), 1)

    def test_ready_period_destinations_use_latest_case_scoped_importable_snapshot(self):
        from uuid import uuid4
        from datetime import datetime, timedelta, timezone
        from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
        document = self.make_document()
        now = datetime.now(timezone.utc)
        summary = dict(can_import=True, holder='Synthetic holder', institution='Synthetic bank',
            account='TEST-ACCOUNT', currency='USD', period_start='2024-01-01', period_end='2024-01-31',
            transaction_count=7, incomplete_count=1, problem_count=2)
        for index, batch_state in enumerate(('review', 'review', 'removed')):
            batch = Batch(id=uuid4(), case_id=self.case.id, created_by=self.user.id, actor={}, files=[], status=batch_state)
            self.db.add(batch); self.db.flush()
            self.db.add(Item(id=uuid4(), batch_id=batch.id, file_id=document.evidence_file_id,
                statement_key='one-period', status='attention', summary={**summary, 'transaction_count': index+6},
                updated_at=now+timedelta(seconds=index)))
            if index == 1:
                for key, state, can_import in [('blocked', 'attention', False), ('pending', 'pending_import', True), ('skipped', 'skipped', True)]:
                    self.db.add(Item(id=uuid4(), batch_id=batch.id, file_id=document.evidence_file_id,
                        statement_key=key, status=state, summary={**summary, 'can_import': can_import}))
        self.db.commit()
        status = statement_file_status(self.db, case_id=self.case.id)['files'][0]
        self.assertEqual(status['available_periods'], 1)
        self.assertEqual(status['ready_periods'], [dict(statement_id='one-period', **{key:value for key,value in summary.items() if key != 'can_import'})])
        self.assertEqual(statement_file_status(self.db, case_id=self.other_case.id)['files'], [])

    def test_saved_file_status_counts_current_payments_and_preserves_periods(self):
        document = self.make_document()
        period = self.make_period(document)
        original = self.add_row(period, document, amount=100)
        replacement = self.add_row(period, document, amount=200)
        original.ledger_status = 'superseded'
        original.superseded_by_id = replacement.id
        self.db.commit()
        result = statement_file_status(self.db, case_id=self.case.id)
        item = next(f for f in result['files'] if f['evidence_file_id'] == str(document.evidence_file_id))
        self.assertEqual(item['current_transactions'], 1)
        self.assertEqual(item['periods'][0]['account_id'], str(period.account_id))
        self.assertEqual(item['periods'][0]['start'], period.period_start.isoformat())
        document.status = 'superseded'
        self.db.commit()
        result = statement_file_status(self.db, case_id=self.case.id)
        self.assertEqual(result['files'][0]['current_transactions'], 0)
        self.assertEqual(result['files'][0]['periods'][0]['source_status'], 'superseded')
        self.assertEqual(statement_file_status(self.db, case_id=self.other_case.id)['files'], [])

    def test_saved_file_status_omits_a_file_with_inconsistent_case_ownership(self):
        from postgres.models.evidence import EvidenceFile
        document = self.make_document()
        self.make_period(document)
        self.db.get(EvidenceFile, document.evidence_file_id).case_id = self.other_case.id
        self.db.commit()
        self.assertEqual(statement_file_status(self.db, case_id=self.case.id)['files'], [])

    def test_incomplete_records_without_a_period_are_visible_and_not_counted_as_payments(self):
        document = self.make_document()
        document.document_type = 'statement_review'
        document.metadata_ = {'statement_incomplete_records': [dict(id='one'), dict(id='two'), dict(id='resolved', resolved_transaction_id='saved')]}
        self.db.commit()
        item = statement_file_status(self.db, case_id=self.case.id)['files'][0]
        self.assertEqual(item['current_transactions'], 0)
        self.assertEqual(item['incomplete_count'], 2)
        self.assertEqual(item['periods'], [])
        document.status = 'superseded'
        self.db.commit()
        self.assertEqual(statement_file_status(self.db, case_id=self.case.id)['files'], [])
