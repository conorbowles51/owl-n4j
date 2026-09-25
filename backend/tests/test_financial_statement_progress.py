from unittest import TestCase
from copy import deepcopy
from uuid import uuid4
from sqlalchemy import select
from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialTransaction
from services.financial.statement_progress import save_progress, previous_review_progress
from services.financial.statement_import import StatementReviewDraft
from services.financial.statement_import import StatementImportRequest, check_import_request
from services.financial.pdf_candidates import PdfMappingError
from tests.test_financial_statement_import import StatementImportTests as Fixture


class StatementProgressTests(TestCase):
    def setUp(self):
        self.f = Fixture('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()

    def tearDown(self):
        self.f.tearDown()

    def save(self, raw, revision='initial', case_id=None):
        with self.f.SessionLocal() as db:
            return save_progress(db, case_id=case_id or self.f.case.id, evidence_file_id=self.f.file.id,
                request=StatementReviewDraft.model_validate(raw), expected_review_revision=revision, actor=self.f.actor)

    def test_printed_total_corrections_reconcile_save_reopen_and_import_once(self):
        """Matching endpoints cannot hide contradictory direction controls.

        Synthetic extraction retained zero for two control cells. The
        investigator corrects those readings; the original cells remain sealed.
        No balance exception or admission-policy override is involved.
        """
        from uuid import UUID
        from postgres.models.evidence import EvidenceTableGeometry
        from postgres.models.financial import FinancialSourceDocument
        from services.financial.statement_admission import assess_admission
        from tests.test_financial_pdf_geometry_candidates import rectangle

        with self.f.SessionLocal() as db:
            geometry = db.get(EvidenceTableGeometry, (self.f.file.id, 1))
            payload = deepcopy(geometry.payload)
            cells = payload[0]['table']['values']
            first = max(cell['row'] for cell in cells) + 1
            for offset, (label, column) in enumerate((('Total credits', 2), ('Total debits', 3))):
                for col, text in ((1, label), (column, '0.00')):
                    cells.append(dict(row=first + offset, column=col, text=text,
                        locator=rectangle(440 + offset * 20, x=20 + col * 100, width=90, height=15)))
            geometry.payload = payload
            db.commit()
        original = self.f.preview()
        controls = {row['fields']['total_direction']: row for row in original['rows']
            if row['kind'] == 'statement_total'}
        self.assertEqual({role: row['fields']['balance'] for role, row in controls.items()},
            {'credit': '0', 'debit': '0'})
        raw = self.f.request()

        def checked(body):
            return assess_admission(self.f.preview(), StatementImportRequest.model_validate(body))

        def blocked(body, expected_checks):
            result = checked(body)
            self.assertFalse(result['can_import'])
            self.assertEqual({blocker['check'] for blocker in result['blockers']}, expected_checks)
            self.assertEqual(next(check['status'] for check in result['checks']
                if check['kind'] == 'closing_balance'), 'matches')
            with self.assertRaisesRegex(PdfMappingError, 'Statement remains in review'):
                self.f.confirm(body)
            with self.f.SessionLocal() as db:
                self.assertEqual(list(db.scalars(select(FinancialTransaction))), [])

        blocked(raw, {'credit_total', 'debit_total'})
        saved = self.save(raw)
        reopened = self.f.preview()['saved_review']
        self.assertEqual(reopened['request'], saved['request'])
        corrected = deepcopy(reopened['request'])
        edits = {row['id']: row for row in corrected['rows']}
        # Independently specified totals of the synthetic source fixture.
        # Payments and endpoint balances are never changed to make them fit.
        edits[controls['credit']['id']].update(balance_minor='103500000',
            reason='Synthetic source comparison: corrected total credits reading.')
        blocked(corrected, {'debit_total'})
        cleared = deepcopy(corrected)
        for row in cleared['rows']:
            if row['id'] in {control['id'] for control in controls.values()}:
                row.update(balance_minor=None, reason='Synthetic check: blank is not a resolved printed total.')
        blocked(cleared, {'credit_total', 'debit_total'})
        edits[controls['debit']['id']].update(balance_minor='100000000',
            reason='Synthetic source comparison: corrected total debits reading.')
        self.assertTrue(checked(corrected)['can_import'])
        saved = self.save(corrected, saved['review_revision'])
        reopened = self.f.preview()
        self.assertEqual(reopened['saved_review']['request'], saved['request'])
        self.assertEqual(reopened['saved_review']['saved_by']['user_id'], str(self.f.actor.user_id))
        self.assertEqual(reopened['rows'], original['rows'])
        first = self.f.confirm(reopened['saved_review']['request'])
        self.assertEqual(first['transaction_count'], 12)
        with self.f.SessionLocal() as db:
            payment_ids = set(db.scalars(select(FinancialTransaction.id)))
            document = db.get(FinancialSourceDocument, UUID(first['source_document_id']))
            self.assertEqual(document.metadata_['statement_import_original']['rows'], original['rows'])
            self.assertEqual(document.metadata_['statement_import_request'], saved['request'])
            self.assertEqual(db.get(EvidenceTableGeometry, (self.f.file.id, 1)).payload, payload)
        current = self.f.preview()['current_import']
        self.assertEqual({row['description']: row['reason'] for row in current['review_decisions']},
            {row['description']: row['reason'] for row in corrected['rows'] if row['reason']})
        again = self.f.confirm(reopened['saved_review']['request'])
        self.assertFalse(again['created'])
        self.assertEqual(again['source_document_id'], first['source_document_id'])
        with self.f.SessionLocal() as db:
            self.assertEqual(set(db.scalars(select(FinancialTransaction.id))), payment_ids)

    def test_incomplete_progress_reopens_without_import_and_detects_concurrent_save(self):
        raw = self.f.request()
        payment = next(row for row in raw['rows'] if not row['excluded'])
        payment.update(date='', description='Corrected description', reason='Checking the printed date')
        saved = self.save(raw)
        reopened = self.f.preview()['saved_review']
        self.assertEqual(reopened['request']['rows'], saved['request']['rows'])
        self.assertEqual(reopened['saved_by']['name'], self.f.actor.name)
        with self.assertRaisesRegex(PdfMappingError, 'Another reviewer'):
            self.save(raw)
        payment['date'] = '2023-03-18'
        newer = self.save(raw, saved['review_revision'])
        self.assertNotEqual(newer['review_revision'], saved['review_revision'])
        with self.f.SessionLocal() as db:
            self.assertFalse(list(db.scalars(select(FinancialTransaction))))

    def _malformed_balance_save_journey(self, *, in_batch):
        from postgres.base import Base
        from postgres.models.evidence import EvidenceTableGeometry, IngestionLog
        from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
        from services.financial import import_batches as batches
        from services.financial.statement_admission import assess_admission
        from tests.test_financial_import_batches import BatchImportTests

        original = next(row for row in self.f.preview()['rows'] if not row['excluded'])
        self.assertEqual(original['fields']['balance'], '13745000')
        with self.f.SessionLocal() as db:
            geometry = db.get(EvidenceTableGeometry, (self.f.file.id, 1))
            payload = deepcopy(geometry.payload)
            cell = next(cell for cell in payload[0]['table']['values'] if cell['row'] == original['row_index']
                and str(cell['column']) == original['fields']['balance_column'])
            cell['text'] = '9187"'
            geometry.payload = payload
            db.commit()
        proposal = self.f.preview()
        malformed = next(row for row in proposal['rows'] if row['id'] == original['id'])
        self.assertTrue(malformed['issues'])
        self.assertTrue(any(cell['expected_text'] == '9187"' for cell in malformed['source_cells']))
        raw = self.f.request()
        edited = next(row for row in raw['rows'] if row['id'] == original['id'])
        edited['balance_minor'] = '223344'
        if in_batch:
            Base.metadata.create_all(self.f.engine, tables=[IngestionLog.__table__])
            self.f.file.status = 'processed'
            self.f.db.commit()
            fixture = BatchImportTests()
            fixture.f = self.f
            batch = fixture.create()
            fixture.advance(batch)
            with self.f.SessionLocal() as db:
                item_id = db.scalar(select(Item.id).where(Item.batch_id == batch))

        def save_and_reopen(revision):
            if not in_batch:
                saved = self.save(raw, revision)
                return saved, self.f.preview()['saved_review']['request']
            with self.f.SessionLocal() as db:
                saved = batches.save_review(db, case_id=self.f.case.id, batch_id=batch, item_id=item_id,
                    request=StatementReviewDraft.model_validate(raw), expected_review_revision=revision)
            with self.f.SessionLocal() as db:
                return saved, deepcopy(db.get(Item, item_id).review_request)

        saved, reopened = save_and_reopen(batches._digest({}) if in_batch else 'initial')
        self.assertEqual(next(row for row in reopened['rows'] if row['id'] == original['id'])['balance_minor'], '223344')
        assessment = assess_admission(self.f.preview(), StatementImportRequest.model_validate(reopened))
        self.assertFalse(assessment['can_import'])
        self.assertEqual([(blocker['kind'], blocker.get('check')) for blocker in assessment['blockers']],
            [('arithmetic', 'running_balance'), ('arithmetic', 'running_balance')])
        with self.assertRaisesRegex(PdfMappingError, 'Statement remains in review'):
            self.f.confirm(reopened)
        with self.f.SessionLocal() as db:
            self.assertEqual(list(db.scalars(select(FinancialTransaction))), [])
        # The exact independently known fixture balance resolves the interval.
        # No note is needed to suppress the earlier malformed-source warning.
        edited['balance_minor'] = '13745000'
        saved, reopened = save_and_reopen(saved['review_revision'])
        self.assertEqual(next(row for row in reopened['rows'] if row['id'] == original['id'])['balance_minor'], '13745000')
        self.assertTrue(assess_admission(self.f.preview(), StatementImportRequest.model_validate(reopened))['can_import'])
        self.assertEqual(self.f.preview()['rows'], proposal['rows'])
        if in_batch:
            ready_revision = fixture.status(batch)['ready_revision']
            with self.f.SessionLocal() as db:
                receipt = batches.queue_import(db, case_id=self.f.case.id, batch_id=batch,
                    expected_revision=ready_revision, actor=self.f.actor)
            fixture.advance(batch)
            self.assertEqual(fixture.status(batch)['counts']['imported'], 1)
        else:
            receipt = self.f.confirm(reopened)
            self.assertEqual(receipt['transaction_count'], 12)
        with self.f.SessionLocal() as db:
            payments = list(db.scalars(select(FinancialTransaction)))
            identities = {payment.id for payment in payments}
            self.assertEqual(len(identities), 12)
            payment = next(payment for payment in payments if payment.provenance['statement_import_original']['id'] == original['id'])
            self.assertEqual(payment.running_balance_minor, 13745000)
            self.assertEqual(payment.provenance['statement_import_review']['balance_minor'], '13745000')
            self.assertEqual(payment.provenance['statement_import_original'], malformed)
            self.assertEqual(db.get(EvidenceTableGeometry, (self.f.file.id, 1)).payload, payload)
        if in_batch:
            with self.f.SessionLocal() as db:
                repeated = batches.queue_import(db, case_id=self.f.case.id, batch_id=batch,
                    expected_revision=ready_revision, actor=self.f.actor)
            self.assertEqual(repeated['operation']['id'], receipt['operation']['id'])
            fixture.advance(batch)
        else:
            repeated = self.f.confirm(reopened)
            self.assertFalse(repeated['created'])
            self.assertEqual(repeated['source_document_id'], receipt['source_document_id'])
        with self.f.SessionLocal() as db:
            self.assertEqual(set(db.scalars(select(FinancialTransaction.id))), identities)

    def test_malformed_source_balance_correction_survives_standalone_save_and_import(self):
        self._malformed_balance_save_journey(in_batch=False)

    def test_malformed_source_balance_correction_survives_batch_save_and_import(self):
        self._malformed_balance_save_journey(in_batch=True)

    def test_scope_source_binding_and_imported_record_guard(self):
        raw = self.f.request()
        with self.assertRaisesRegex(PdfMappingError, 'not found'):
            self.save(raw, case_id=uuid4())
        changed = {**raw, 'expected_revision': 'a'*64}
        with self.assertRaisesRegex(PdfMappingError, 'reading changed'):
            self.save(changed)
        missing = deepcopy(raw)
        missing['rows'].pop()
        with self.assertRaisesRegex(PdfMappingError, 'each original row'):
            self.save(missing)
        self.f.confirm(raw)
        with self.assertRaisesRegex(PdfMappingError, 'is imported'):
            self.save(raw)

    def test_source_change_retains_previous_values_in_history(self):
        raw = self.f.request()
        saved = self.save(raw)
        with self.f.SessionLocal() as db:
            file = db.get(EvidenceFile, self.f.file.id)
            metadata = deepcopy(file.metadata_)
            metadata['financial_review_progress']['']['request']['expected_revision'] = 'a'*64
            file.metadata_ = metadata
            db.commit()
        with self.assertRaisesRegex(PdfMappingError, 'Save progress before importing'):
            check_import_request(self.f.preview(), StatementImportRequest.model_validate(raw))
        self.save(raw, saved['review_revision'])
        with self.f.SessionLocal() as db:
            history = db.get(EvidenceFile, self.f.file.id).metadata_['financial_review_history']
            self.assertEqual(history[0]['request']['expected_revision'], 'a'*64)
            self.assertEqual(history[0]['request']['rows'], saved['request']['rows'])

    def test_reprocessed_file_can_recover_only_its_own_parent_period(self):
        raw = self.f.request()
        saved = self.save(raw)
        with self.f.SessionLocal() as db:
            from types import SimpleNamespace
            version = SimpleNamespace(case_id=self.f.case.id, metadata_={'statement_parent_evidence_id': str(self.f.file.id)})
            previous = previous_review_progress(db, version, None)
            self.assertEqual(previous['request'], saved['request'])
            self.assertEqual(previous['evidence_file_id'], str(self.f.file.id))
            self.assertIsNone(previous_review_progress(db, version, 'a'*64))
            version.case_id = uuid4()
            self.assertIsNone(previous_review_progress(db, version, None))
