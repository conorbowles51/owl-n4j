from unittest import TestCase
from uuid import uuid4, UUID
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

    def quiet_import(self):
        from services.financial import import_batches as service
        from services.financial.statement_import import StatementImportRequest, StatementReviewDraft
        from services.financial.statement_admission import assess_admission
        from tests.financial_reconciled_fixture import install_reconciled_source
        install_reconciled_source(self.f, quiet=True)
        batch = self.fixture.create()
        self.fixture.advance(batch)
        before = self.fixture.status(batch)
        proposal = self.f.preview()
        raw = service.initial_request(proposal)
        assessment = assess_admission(proposal, StatementImportRequest.model_validate(raw))
        raw.update(no_activity_confirmed=True, no_activity_revision=assessment['revision'])
        with self.f.SessionLocal() as db:
            service.save_review(db, case_id=self.f.case.id, batch_id=batch,
                item_id=UUID(before['items'][0]['id']), request=StatementReviewDraft.model_validate(raw),
                expected_review_revision=service._digest({}))
        ready = self.fixture.status(batch)
        self.assertEqual(ready['statement_summary']['available_no_activity'], 1)
        operation = uuid4()
        with self.f.SessionLocal() as db:
            service.queue_import(db, case_id=self.f.case.id, batch_id=batch,
                expected_revision=ready['ready_revision'], actor=self.f.actor, request_id=operation)
        self.fixture.advance(batch)
        self.assertEqual(self.fixture.status(batch)['counts']['imported'], 1)
        return batch, operation

    def test_real_quiet_import_receipt_opens_saved_account_history_without_payments(self):
        from services.financial.account_history import account_history
        batch, operation = self.quiet_import()
        with self.f.SessionLocal() as db:
            receipt = imported_batch_scope(db, case_id=self.f.case.id, batch_id=batch, operation_id=operation)
            self.assertEqual(receipt['transaction_count'], 0)
            self.assertEqual(receipt['statement_count'], 1)
            self.assertEqual(len(receipt['account_ids']), 1)
            history = account_history(db, case_id=self.f.case.id,
                account_ids=[UUID(value) for value in receipt['account_ids']])
            self.assertEqual([group['account_id'] for group in history['groups']], receipt['account_ids'])
            period = history['groups'][0]['periods'][0]
            self.assertEqual(period['status'], 'confirmed_no_activity')
            self.assertEqual(period['source_document_id'], receipt['source_document_ids'][0])
            self.assertEqual(period['opening_minor'], period['closing_minor'])
            self.assertEqual(period['transaction_count'], 0)
            self.assertFalse(list(db.scalars(select(FinancialTransaction))))
            with self.assertRaisesRegex(PdfMappingError, 'not found'):
                imported_batch_scope(db, case_id=uuid4(), batch_id=batch, operation_id=operation)
            with self.assertRaisesRegex(PdfMappingError, 'not found'):
                imported_batch_scope(db, case_id=self.f.case.id, batch_id=batch, operation_id=uuid4())

    def test_quiet_receipt_resolves_canonical_account_like_history(self):
        from postgres.models.financial import FinancialAccount
        from services.financial.account_history import account_history
        batch, operation = self.quiet_import()
        with self.f.SessionLocal() as db:
            first = imported_batch_scope(db, case_id=self.f.case.id, batch_id=batch, operation_id=operation)
            account = db.get(FinancialAccount, UUID(first['account_ids'][0]))
            retained = FinancialAccount(id=uuid4(), case_id=self.f.case.id,
                identity_key='synthetic-retained-' + uuid4().hex,
                holder_name='Synthetic retained holder', institution_name=account.institution_name,
                identifier_as_printed='RETAINED001', currency=account.currency, account_type=account.account_type)
            db.add(retained)
            account.metadata_ = {**(account.metadata_ or {}), 'canonical_account_id': str(retained.id)}
            db.commit()
            receipt = imported_batch_scope(db, case_id=self.f.case.id, batch_id=batch, operation_id=operation)
            self.assertEqual(receipt['account_ids'], [str(retained.id)])
            history = account_history(db, case_id=self.f.case.id, account_ids=[retained.id])
            self.assertEqual([group['account_id'] for group in history['groups']], receipt['account_ids'])
            self.assertEqual(len(history['groups'][0]['periods']), 1)

    def test_quiet_receipt_does_not_use_foreign_or_removed_period_context(self):
        from postgres.models.financial import FinancialStatementPeriod, FinancialSourceDocument
        from postgres.models.evidence import EvidenceFile
        batch, operation = self.quiet_import()
        with self.f.SessionLocal() as db:
            receipt = imported_batch_scope(db, case_id=self.f.case.id, batch_id=batch, operation_id=operation)
            source = db.get(FinancialSourceDocument, UUID(receipt['source_document_ids'][0]))
            period = db.scalar(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id == source.id))
            file = db.get(EvidenceFile, source.evidence_file_id)
            for entity in (period, file):
                original = entity.case_id
                entity.case_id = self.f.other_case.id
                db.flush()
                self.assertEqual(imported_batch_scope(db, case_id=self.f.case.id,
                    batch_id=batch, operation_id=operation)['account_ids'], [])
                entity.case_id = original
                db.flush()
            source.metadata_ = {**source.metadata_, 'financial_import_removal': {'reason': 'synthetic removal'}}
            db.flush()
            self.assertEqual(imported_batch_scope(db, case_id=self.f.case.id,
                batch_id=batch, operation_id=operation)['account_ids'], [])

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
