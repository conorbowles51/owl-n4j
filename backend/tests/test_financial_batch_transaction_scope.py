from unittest import TestCase
from uuid import uuid4
from sqlalchemy import select
from postgres.models.financial import FinancialTransaction
from services.financial.batch_transaction_scope import imported_batch_scope
from services.financial.pdf_candidates import PdfMappingError
from tests import test_financial_import_batches as fixtures


class ImportedBatchScopeTests(TestCase):
    def setUp(self):
        self.fixture = fixtures.BatchImportTests('test_folder_preparation_bulk_confirmation_and_repeat_do_not_duplicate')
        self.fixture.setUp()
        self.f = self.fixture.f

    def tearDown(self):
        self.fixture.tearDown()

    def test_scope_includes_all_imported_items_not_only_the_displayed_page(self):
        from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
        receipt = self.f.confirm()
        batch = self.fixture.create()
        self.fixture.advance(batch)
        with self.f.SessionLocal() as db:
            first = db.scalar(select(Item).where(Item.batch_id == batch))
            # 101 period receipts exercise a full batch beyond the UI page.
            # The repeated source intentionally tests source deduplication too.
            for n in range(100):
                db.add(Item(id=uuid4(), batch_id=batch, file_id=self.f.file.id,
                    statement_key=str(n), status='imported', summary={**first.summary,
                        'source_document_id': receipt['source_document_id']}))
            db.add(Item(id=uuid4(), batch_id=batch, file_id=self.f.file.id,
                statement_key='unresolved', status='attention', summary={}))
            db.commit()
            result = imported_batch_scope(db, case_id=self.f.case.id, batch_id=batch)
            self.assertEqual(result['statement_count'], 101)
            self.assertEqual(result['source_document_ids'], [receipt['source_document_id']])
            self.assertEqual(result['transaction_count'], 12)
            self.assertEqual(result['account_ids'], [receipt['account_id']])
            self.assertEqual(result['start_date'], '2023-03-18')
            self.assertEqual(result['end_date'], '2023-12-28')
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction)))), 12)
            with self.assertRaisesRegex(PdfMappingError, 'not found'):
                imported_batch_scope(db, case_id=uuid4(), batch_id=batch)

    def test_earlier_receipt_can_be_resolved_but_an_ambiguous_source_is_never_guessed(self):
        from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
        receipt = self.f.confirm()
        batch = self.fixture.create(); self.fixture.advance(batch)
        with self.f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == batch))
            item.summary = {k: v for k,v in item.summary.items() if k != 'source_document_id'}
            db.commit()
            old = imported_batch_scope(db, case_id=self.f.case.id, batch_id=batch)
            self.assertEqual(old['source_document_ids'], [receipt['source_document_id']])
            item.statement_key = 'unmatched'
            db.commit()
            with self.assertRaisesRegex(PdfMappingError, 'does not identify one source'):
                imported_batch_scope(db, case_id=self.f.case.id, batch_id=batch)
            item.summary = {**item.summary, 'source_document_id': str(uuid4())}
            db.commit()
            with self.assertRaisesRegex(PdfMappingError, 'source is unavailable'):
                imported_batch_scope(db, case_id=self.f.case.id, batch_id=batch)

    def test_receipt_to_an_earlier_file_version_opens_that_original_import(self):
        from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
        receipt = self.f.confirm()
        batch = self.fixture.create(); self.fixture.advance(batch)
        copy = self.f.evidence('f'*64); self.f.db.commit()
        with self.f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == batch))
            item.file_id = copy.id; db.commit()
            result = imported_batch_scope(db, case_id=self.f.case.id, batch_id=batch)
            self.assertEqual(result['source_document_ids'], [receipt['source_document_id']])
