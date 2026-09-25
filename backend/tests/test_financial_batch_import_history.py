"""Saved batch receipts stay current without rewriting earlier import evidence."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID, uuid4

from sqlalchemy import event, select

from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
from services.financial import batch_import_history, import_batches
from services.financial.corrections import correct_transaction
from services.financial.duplicate_decisions import duplicate_revision
from services.financial.pdf_candidates import PdfMappingError
from services.financial.statement_import import StatementReviewDraft
from tests import test_financial_import_batches as fixtures


class CurrentBatchImportHistoryTests(TestCase):
    def setUp(self):
        self.batch_fixture = fixtures.BatchImportTests()
        self.batch_fixture.setUp()
        self.f = self.batch_fixture.f
        self.batch = self.batch_fixture.create()
        self.batch_fixture.advance(self.batch)
        self.receipt = self.f.confirm()
        self.source_id = UUID(self.receipt['source_document_id'])
        with self.f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == self.batch))
            self.item_id = item.id
            item.status = 'imported'
            item.summary = {**item.summary, 'source_document_id': str(self.source_id),
                'problems': [dict(message='An obsolete extraction problem.')], 'problem_count': 1}
            db.commit()

    def tearDown(self):
        self.batch_fixture.tearDown()

    def shown(self):
        return self.batch_fixture.status(self.batch)['items'][0]

    def test_saved_amount_edits_update_batch_difference_and_reasons_without_stale_issues(self):
        original_view = self.shown()
        self.assertEqual(original_view['balance_status'], 'matches')
        self.assertEqual(original_view['problems'], [])
        with self.f.SessionLocal() as db:
            document = db.get(FinancialSourceDocument, self.source_id)
            row = db.scalar(select(FinancialTransaction).where(
                FinancialTransaction.source_document_id == self.source_id,
                FinancialTransaction.direction == 'credit'))
            amount = row.amount_minor
            result = correct_transaction(db, case_id=self.f.case.id, transaction_id=row.id,
                amount_minor=amount + 10000, direction=row.direction,
                expected_revision=duplicate_revision(db, document), actor=self.f.actor,
                reason='Synthetic amount correction against the source.')
            # Older deployments may retain these messages after a repair. They
            # are evidence of that earlier import, not the current blockers.
            document.metadata_ = {**document.metadata_, 'statement_import_issues': [
                dict(kind='statement_detail', field='holder', message='A stale holder issue.')]}
            db.commit()
        changed = self.shown()
        self.assertFalse(changed['admission']['can_import'])
        self.assertEqual(changed['balance_status'], 'difference')
        calculation = changed['admission']['calculation']
        self.assertEqual(calculation['printed_closing_minor'], '4745000')
        self.assertEqual(calculation['calculated_closing_minor'], '4755000')
        self.assertEqual(abs(int(calculation['difference_minor'])), 10000)
        self.assertTrue(any(p.get('check') == 'closing_balance' and p.get('target') for p in changed['problems']))
        self.assertNotIn('stale holder', str(changed['problems']))
        self.assertEqual(changed['checks'], changed['admission']['checks'])
        with self.f.SessionLocal() as db:
            document = db.get(FinancialSourceDocument, self.source_id)
            corrected = db.get(FinancialTransaction, UUID(result['replacement_id']))
            correct_transaction(db, case_id=self.f.case.id, transaction_id=corrected.id,
                amount_minor=amount, direction=corrected.direction,
                expected_revision=duplicate_revision(db, document), actor=self.f.actor,
                reason='Synthetic subsequent source correction.')
        restored = self.shown()
        self.assertEqual(restored['balance_status'], 'matches')
        self.assertEqual(restored['problems'], [])
        self.assertEqual(restored['transaction_count'], 12)
        with self.f.SessionLocal() as db:
            self.assertEqual(db.get(Item, self.item_id).summary['problems'],
                [dict(message='An obsolete extraction problem.')])

    def test_legacy_balanced_import_requires_current_confirmation_and_get_does_not_write(self):
        with self.f.SessionLocal() as db:
            document = db.get(FinancialSourceDocument, self.source_id)
            metadata = deepcopy(document.metadata_)
            metadata.pop('statement_admission')
            document.metadata_ = metadata
            db.commit()
        shown = self.shown()
        self.assertEqual(shown['balance_status'], 'unavailable')
        self.assertEqual(shown['admission']['calculation']['difference_minor'], '0')
        self.assertFalse(shown['admission']['assessment_current'])
        self.assertEqual([p['kind'] for p in shown['problems']], ['assessment_missing'])
        with self.f.SessionLocal() as db:
            self.assertEqual(db.get(FinancialSourceDocument, self.source_id).metadata_, metadata)
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction)))), 12)

    def test_repeated_source_receipts_share_bulk_queries_and_assessment(self):
        with self.f.SessionLocal() as db:
            connection = db.connection()
            statements = []

            def collect(_conn, _cursor, statement, _parameters, _context, _many):
                statements.append(statement)

            event.listen(connection, 'before_cursor_execute', collect)
            try:
                with patch.object(batch_import_history, 'current_saved_assessment',
                        wraps=batch_import_history.current_saved_assessment) as assess:
                    result = batch_import_history.current_imports(db, self.f.case.id, [self.source_id] * 143)
                    self.assertEqual(assess.call_count, 1)
            finally:
                event.remove(connection, 'before_cursor_execute', collect)
            self.assertEqual(len(statements), 3)
            self.assertTrue(all(sql.lstrip().upper().startswith('SELECT') for sql in statements))
            self.assertEqual(result[str(self.source_id)]['transaction_count'], 12)
            self.assertEqual(batch_import_history.current_imports(db, uuid4(), [self.source_id]), {})

    def test_superseded_reading_stays_in_history_but_not_active_counts_or_navigation(self):
        with self.f.SessionLocal() as db:
            original = db.get(Item, self.item_id)
            old = Item(id=uuid4(), batch_id=self.batch, file_id=original.file_id,
                statement_key='retained-old-reading', status='superseded_reading',
                summary={**original.summary, 'filename': 'Earlier reading', 'can_import': True},
                review_request={'saved': 'investigator corrections retained'})
            db.add(old)
            db.commit()
            old_id = old.id
            view = import_batches.batch_status(db, case_id=self.f.case.id, batch_id=self.batch)
            self.assertEqual(view['total'], 1)
            self.assertEqual(view['counts']['imported'], 1)
            self.assertEqual(view['issues_count'], 0)
            following = import_batches.next_statement(db, case_id=self.f.case.id,
                batch_id=self.batch, item_id=self.item_id)
            self.assertIsNone(following['item_id'])
            self.assertEqual(following['total'], 1)
            with self.assertRaisesRegex(PdfMappingError, 'replaced by a newer one'):
                import_batches.save_review(db, case_id=self.f.case.id, batch_id=self.batch,
                    item_id=old_id, request=StatementReviewDraft.model_validate(self.f.request()),
                    expected_review_revision=import_batches._digest(old.review_request))
            with self.assertRaisesRegex(PdfMappingError, 'replaced by a newer one'):
                import_batches.leave_unimported(db, case_id=self.f.case.id, batch_id=self.batch,
                    item_id=old_id, action='skip', reason='Old review', expected_revision='', actor=self.f.actor)
            self.assertEqual(db.get(Item, old_id).review_request,
                {'saved': 'investigator corrections retained'})
