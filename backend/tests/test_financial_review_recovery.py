from copy import deepcopy
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
        page = self.f.db.get(EvidenceTableGeometry, (self.f.file.id, 1))
        payload = deepcopy(page.payload)
        payload[0]['table']['unlocated_values'] = 1
        page.payload = payload
        self.f.db.commit()
        proposal = self.f.preview()
        self.assertNotEqual(proposal['revision'], item.review_request['expected_revision'])
        self.assertTrue(proposal['review_recovery']['required'])
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
