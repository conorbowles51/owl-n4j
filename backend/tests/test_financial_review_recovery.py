from copy import deepcopy
from datetime import datetime, timezone
from unittest import TestCase
from uuid import uuid4
from sqlalchemy import select
from postgres.base import Base
from postgres.models.evidence import EvidenceFile, EvidenceDocumentText, EvidenceTableGeometry
from postgres.models.financial import FinancialTransaction
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from services.financial import review_recovery, import_batches
from services.financial.pdf_candidates import PdfMappingError
from services.financial.statement_import import StatementImportRequest, check_import_request
from tests import test_financial_statement_import as fixtures


class ReviewRecoveryTests(TestCase):
    def setUp(self):
        self.f = fixtures.StatementImportTests('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()
        Base.metadata.create_all(self.f.db.connection(), tables=[Batch.__table__, Item.__table__])
        self.f.db.commit()

    def tearDown(self):
        self.f.tearDown()

    def batch_draft(self, statement_id=None):
        raw = self.f.request()
        raw['statement_id'] = statement_id
        next(r for r in raw['rows'] if not r['excluded']).update(description='Earlier corrected wording', reason='Compared with the original PDF')
        batch = Batch(id=uuid4(), case_id=self.f.case.id, created_by=self.f.user.id,
            status='review', files=[], actor={'name': self.f.user.name})
        self.f.db.add(batch)
        self.f.db.flush()
        item = Item(id=uuid4(), batch_id=batch.id, file_id=self.f.file.id, statement_key=statement_id or '',
            status='attention', summary={}, review_request=raw)
        self.f.db.add(item)
        self.f.db.commit()
        return item

    def new_version(self):
        previous = self.f.file
        file = self.f.evidence(previous.sha256)
        file.metadata_ = {'statement_parent_evidence_id': str(previous.id)}
        file.stored_path = previous.stored_path
        text = self.f.db.get(EvidenceDocumentText, previous.id)
        page = self.f.db.get(EvidenceTableGeometry, (previous.id, 1))
        self.f.db.add(EvidenceDocumentText(evidence_file_id=file.id, content=text.content,
            content_sha256=text.content_sha256, character_count=text.character_count,
            engine_job_id=text.engine_job_id, source_locations=deepcopy(text.source_locations)))
        self.f.db.add(EvidenceTableGeometry(evidence_file_id=file.id, page_number=1,
            engine_job_id=page.engine_job_id, payload=deepcopy(page.payload)))
        self.f.db.commit()
        self.f.file = file
        return previous

    def compare(self, revision):
        with self.f.SessionLocal() as db:
            return review_recovery.acknowledge_recovery(db, case_id=self.f.case.id,
                evidence_file_id=self.f.file.id, expected_revision=revision, actor=self.f.actor)

    def test_batch_only_review_recovers_through_multiple_versions_without_changing_rows(self):
        item = self.batch_draft()
        original = self.new_version()
        self.new_version()
        proposal = self.f.preview()
        self.assertEqual(proposal['previous_saved_review']['request'], item.review_request)
        self.assertEqual(proposal['previous_saved_review']['evidence_file_id'], str(original.id))
        # Source revisions bind to their file too. A cloned file can retain
        # identical numbers but still needs comparison before carrying edits.
        self.assertTrue(proposal['review_recovery']['required'])
        self.assertEqual(proposal['review_recovery']['reviews'][0]['origin'], 'Bulk review')
        self.assertNotEqual(next(r for r in proposal['rows'] if not r['excluded'])['fields']['description'], 'Earlier corrected wording')

    def test_post_import_details_and_balances_remain_available_after_rereading(self):
        from uuid import UUID
        from services.financial.statement_details import read_statement_details, update_statement_details, StatementDetailsRequest
        receipt = self.f.confirm()
        with self.f.SessionLocal() as db:
            source_id = UUID(receipt['source_document_id'])
            view = read_statement_details(db, case_id=self.f.case.id, source_id=source_id)
            update_statement_details(db, case_id=self.f.case.id, source_id=source_id,
                request=StatementDetailsRequest(expected_revision=view['revision'], holder=view['details']['holder'],
                    account_number='00123456789', institution=view['details']['institution'],
                    opening={'amount_minor': '6000', 'page': 1}), actor=self.f.actor)
        self.new_version()
        records = review_recovery.saved_ancestor_reviews(self.f.db, self.f.file)
        late = next(r for r in records if r['origin'] == 'Account and balances corrected after import')
        self.assertEqual(late['request']['account_number'], '00123456789')
        self.assertEqual(late['request']['_saved_balance_corrections']['opening'], {'amount_minor': '6000', 'page': 1})
        self.assertEqual(late['saved_by']['user_id'], str(self.f.actor.user_id))

    def test_new_reading_with_shifted_rows_retains_manual_additions_for_comparison(self):
        item = self.batch_draft()
        saved = deepcopy(item.review_request)
        saved['rows'].append(dict(id='manual:checked-payment', manual_page=1,
            date='2023-12-29', description='Manually checked payment',
            amount_minor='1250', direction='debit', excluded=False,
            reason='Entered from the printed page'))
        item.review_request = deepcopy(saved)
        self.f.db.commit()
        previous = self.new_version()
        # A newly recovered control above a payment can shift physical row
        # indices, even though the underlying PDF and statement are unchanged.
        page = self.f.db.get(EvidenceTableGeometry, (self.f.file.id, 1))
        payload = deepcopy(page.payload)
        for cell in payload[0]['table']['values']:
            cell['row'] += 1
        page.payload = payload
        self.f.db.commit()
        proposal = self.f.preview()
        recovery = proposal['review_recovery']
        self.assertTrue(recovery['required'])
        self.assertFalse(recovery['acknowledged'])
        with self.f.SessionLocal() as db:
            detail = review_recovery.previous_review_detail(db, case_id=self.f.case.id,
                evidence_file_id=self.f.file.id, review_id=recovery['reviews'][0]['id'])
            self.assertEqual(detail['request']['rows'], saved['rows'])
            self.assertEqual(db.get(Item, item.id).review_request, saved)
            self.assertFalse(list(db.scalars(select(FinancialTransaction))))
        self.assertEqual(proposal['previous_saved_review']['evidence_file_id'], str(previous.id))
        self.assertNotIn('manual:checked-payment', [r['id'] for r in proposal['rows']])
        self.assertNotIn('Earlier corrected wording',
            [r['fields'].get('description') for r in proposal['rows']])
        with self.assertRaisesRegex(PdfMappingError, 'Compare the earlier'):
            check_import_request(proposal, StatementImportRequest.model_validate(self.f.request()))

    def test_changed_period_requires_saved_comparison_and_never_attaches_the_old_rows(self):
        item = self.batch_draft('a' * 64)
        self.new_version()
        proposal = self.f.preview()
        recovery = proposal['review_recovery']
        self.assertIsNone(proposal['previous_saved_review'])
        self.assertEqual(recovery['unmatched_count'], 1)
        request = StatementImportRequest.model_validate(self.f.request())
        with self.assertRaisesRegex(PdfMappingError, 'Compare the earlier'):
            check_import_request(proposal, request)
        self.assertEqual(import_batches.assess(proposal)[0], 'attention')
        batch = Batch(id=uuid4(), case_id=self.f.case.id, created_by=self.f.user.id,
            status='review', files=[], actor={'name': self.f.user.name})
        self.f.db.add(batch); self.f.db.commit()
        with self.f.SessionLocal() as db:
            import_batches.prepare_reviews(db, db.get(Batch, batch.id), dict(file_id=str(self.f.file.id),
                source_id=str(self.f.file.id), filename='New reading.pdf', currency='EUR'))
            self.assertEqual(db.scalar(select(Item).where(Item.batch_id == batch.id)).status, 'attention')
        with self.f.SessionLocal() as db:
            detail = review_recovery.previous_review_detail(db, case_id=self.f.case.id,
                evidence_file_id=self.f.file.id, review_id=recovery['reviews'][0]['id'], offset=1, limit=2)
            self.assertEqual(detail['request']['rows'], item.review_request['rows'][1:3])
            self.assertEqual(detail['row_count'], len(item.review_request['rows']))
        self.compare(recovery['revision'])
        after = self.f.preview()
        self.assertTrue(after['review_recovery']['acknowledged'])
        self.assertEqual(import_batches.assess(after)[0], 'ready')
        check_import_request(after, request)
        with self.f.SessionLocal() as db:
            self.assertFalse(list(db.scalars(select(FinancialTransaction))))
            self.assertEqual(db.scalar(select(Item).where(Item.batch_id == batch.id)).status, 'ready')
            saved = db.get(EvidenceFile, self.f.file.id).metadata_['financial_review_comparison_history']
            self.assertEqual(saved[0]['saved_by']['user_id'], str(self.f.actor.user_id))

    def test_changed_earlier_values_invalidate_comparison_and_case_boundary_is_enforced(self):
        item = self.batch_draft('a' * 64)
        self.new_version()
        recovery = self.f.preview()['review_recovery']
        self.compare(recovery['revision'])
        item.review_request = {**item.review_request, 'details_reason': 'New information checked'}
        self.f.db.commit()
        updated = self.f.preview()['review_recovery']
        self.assertFalse(updated['acknowledged'])
        with self.assertRaisesRegex(PdfMappingError, 'changed'):
            self.compare(recovery['revision'])
        with self.f.SessionLocal() as db:
            with self.assertRaisesRegex(PdfMappingError, 'not found'):
                review_recovery.previous_review_detail(db, case_id=uuid4(), evidence_file_id=self.f.file.id,
                    review_id=updated['reviews'][0]['id'])
            current = db.get(EvidenceFile, self.f.file.id)
            current.case_id = uuid4()
            with db.no_autoflush:
                self.assertEqual(review_recovery.saved_ancestor_reviews(db, current), [])

    def test_conflicting_saved_alternatives_are_not_resolved_by_last_write_wins(self):
        first = self.batch_draft()
        second = self.batch_draft()
        # Duplicate saved requests are collapsed, but genuinely different
        # corrections remain separately accessible.
        self.new_version()
        self.assertEqual(len(self.f.preview()['review_recovery']['reviews']), 1)
        second.review_request = {**second.review_request, 'holder': 'Different corrected holder'}
        self.f.db.commit()
        proposal = self.f.preview()
        self.assertIsNone(proposal['previous_saved_review'])
        self.assertEqual(len(proposal['review_recovery']['reviews']), 2)
        self.assertTrue(proposal['review_recovery']['required'])
        self.assertEqual(first.review_request['holder'], 'Test Company')

    def test_changed_source_keeps_batch_editable_but_out_of_ready_imports(self):
        item = self.batch_draft()
        previous = self.new_version()
        # The older candidate must win duplicate ranking, independently of
        # timestamp precision or randomly generated evidence IDs.
        previous.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        self.f.file.created_at = datetime(2024, 1, 2, tzinfo=timezone.utc)
        page = self.f.db.get(EvidenceTableGeometry, (self.f.file.id, 1))
        payload = deepcopy(page.payload)
        payload[0]['table']['unlocated_values'] = 1
        page.payload = payload
        self.f.db.commit()
        proposal = self.f.preview()
        self.assertNotEqual(proposal['revision'], item.review_request['expected_revision'])
        self.assertTrue(proposal['review_recovery']['required'])
        from services.financial.pending_statement_duplicates import decide_duplicate_disposition
        with self.f.SessionLocal() as db:
            result = decide_duplicate_disposition(db, case_id=self.f.case.id, evidence_file_id=self.f.file.id,
                action='check', expected_reading_revision=proposal['revision'], actor=self.f.actor)
            self.assertEqual(result['duplicate_disposition']['status'], 'needs_comparison')
        batch = Batch(id=uuid4(), case_id=self.f.case.id, created_by=self.f.user.id,
            status='preparing', files=[], actor={'name': self.f.user.name})
        self.f.db.add(batch); self.f.db.commit()
        with self.f.SessionLocal() as db:
            import_batches.prepare_reviews(db, db.get(Batch, batch.id), dict(file_id=str(self.f.file.id),
                source_id=str(previous.id), filename='Reprocessed.pdf', currency='EUR'))
            prepared = db.scalar(select(Item).where(Item.batch_id == batch.id))
            self.assertEqual(prepared.status, 'attention')
            self.assertIsNone(prepared.review_request)
            self.assertIn('earlier saved reviews', prepared.summary['problems'][0]['message'])
            self.assertEqual(prepared.summary['duplicate_disposition']['status'], 'needs_comparison')
            self.assertEqual(db.get(Item, item.id).review_request, item.review_request)
        # Completing the explicit comparison releases this hold. The retained
        # older source still carries the correction, so its matching copy can
        # now be ignored without discarding unresolved investigator work.
        self.compare(proposal['review_recovery']['revision'])
        current = self.f.preview()
        self.assertTrue(current['review_recovery']['acknowledged'])
        with self.f.SessionLocal() as db:
            result = decide_duplicate_disposition(db, case_id=self.f.case.id, evidence_file_id=self.f.file.id,
                action='check', expected_reading_revision=current['revision'], actor=self.f.actor)
            self.assertEqual(result['duplicate_disposition']['status'], 'ignored')
            self.assertEqual(db.get(Item, item.id).review_request, item.review_request)
