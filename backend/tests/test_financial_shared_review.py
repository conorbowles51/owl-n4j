"""Saved work must reach group import without revisiting each statement."""
import hashlib
from copy import deepcopy
from unittest import TestCase
from sqlalchemy import select

from postgres.models.evidence import EvidenceDocumentText
from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
from services.financial import import_batches as batches
from services.financial.statement_import import StatementReviewDraft
from services.financial.statement_progress import save_progress
from services.financial.statement_file_status import statement_file_status
from services.financial.pdf_candidates import PdfMappingError
from tests import test_financial_import_batches as batch_fixture


class SharedReviewTests(TestCase):
    def setUp(self):
        self.fixture = batch_fixture.BatchImportTests()
        self.fixture.setUp()
        self.f = self.fixture.f
        from postgres.base import Base
        from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
        Base.metadata.create_all(self.f.db.connection(), tables=[WorkspaceEntry.__table__, WorkspaceEntryLink.__table__])
        self.f.db.commit()
        with self.f.SessionLocal() as db:
            text = db.scalar(select(EvidenceDocumentText).where(EvidenceDocumentText.evidence_file_id == self.f.file.id))
            text.content = text.content.replace('Account Name: Test Company\n', '')
            text.content_sha256 = hashlib.sha256(text.content.encode()).hexdigest()
            text.character_count = len(text.content)
            db.commit()
        self.batch = self.fixture.create()
        self.fixture.advance(self.batch)

    def tearDown(self):
        self.fixture.tearDown()

    def save(self, holder='Reviewed Company', revision='initial'):
        request = self.f.request()
        request['holder'] = holder
        with self.f.SessionLocal() as db:
            return save_progress(db, case_id=self.f.case.id, evidence_file_id=self.f.file.id,
                request=StatementReviewDraft.model_validate(request), expected_review_revision=revision, actor=self.f.actor)

    def test_saved_correction_reaches_batch_and_file_without_resaving_each_period(self):
        self.assertFalse(self.fixture.status(self.batch)['items'][0]['can_import'])
        self.save()
        item = self.fixture.status(self.batch)['items'][0]
        self.assertTrue(item['can_import'], item)
        self.assertEqual(item['holder'], 'Reviewed Company')
        with self.f.SessionLocal() as db:
            result = statement_file_status(db, case_id=self.f.case.id)
            file = next(f for f in result['files'] if f['evidence_file_id'] == str(self.f.file.id))
            self.assertEqual(file['available_periods'], 1)
            self.assertEqual(file['ready_periods'][0]['holder'], 'Reviewed Company')

    def test_refresh_adopts_existing_draft_and_follows_its_next_revision(self):
        first = self.save()
        with self.f.SessionLocal() as db:
            batches.refresh_statement_list(db, case_id=self.f.case.id, batch_id=self.batch)
        self.fixture.advance(self.batch)
        with self.f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == self.batch))
            self.assertEqual(item.review_request['holder'], 'Reviewed Company')
        self.save('Updated Company', first['review_revision'])
        self.assertEqual(self.fixture.status(self.batch)['items'][0]['holder'], 'Updated Company')

    def test_distinct_batch_edits_are_retained_and_block_group_admission(self):
        self.save()
        with self.f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == self.batch))
            edited = self.f.request()
            edited['holder'] = 'Independent Batch Edit'
            item.review_request = deepcopy(edited)
            db.commit()
        item = self.fixture.status(self.batch)['items'][0]
        self.assertFalse(item['can_import'])
        self.assertTrue(any(p.get('kind') == 'review_conflict' for p in item['problems']))
        with self.f.SessionLocal() as db:
            stored = db.scalar(select(Item).where(Item.batch_id == self.batch))
            self.assertEqual(stored.review_request['holder'], 'Independent Batch Edit')

    def test_group_import_uses_saved_draft_once_and_locks_it_until_receipt(self):
        saved = self.save()
        state = self.fixture.status(self.batch)
        with self.f.SessionLocal() as db:
            first = batches.queue_import(db, case_id=self.f.case.id, batch_id=self.batch,
                expected_revision=state['ready_revision'], actor=self.f.actor)
            repeated = batches.queue_import(db, case_id=self.f.case.id, batch_id=self.batch,
                expected_revision=state['ready_revision'], actor=self.f.actor)
            self.assertEqual(first['operation']['id'], repeated['operation']['id'])
        with self.assertRaisesRegex(PdfMappingError, 'being imported'):
            self.save('Concurrent Edit', saved['review_revision'])
        self.fixture.advance(self.batch)
        current = self.f.preview()['current_import']
        self.assertEqual(current['transaction_count'], 12)
        self.assertEqual(self.fixture.status(self.batch)['counts']['imported'], 1)

    def test_saved_change_invalidates_old_group_confirmation(self):
        first = self.save()
        state = self.fixture.status(self.batch)
        self.save('Updated Company', first['review_revision'])
        with self.f.SessionLocal() as db:
            with self.assertRaisesRegex(PdfMappingError, 'ready statements changed'):
                batches.queue_import(db, case_id=self.f.case.id, batch_id=self.batch,
                    expected_revision=state['ready_revision'], actor=self.f.actor)

    def test_refresh_preserves_independent_batch_draft_from_an_older_reading(self):
        with self.f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == self.batch))
            draft = self.f.request()
            draft.update(holder='Independent retained edit', expected_revision='a'*64)
            item.review_request = deepcopy(draft)
            db.commit()
            batches.refresh_statement_list(db, case_id=self.f.case.id, batch_id=self.batch)
        self.fixture.advance(self.batch)
        with self.f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == self.batch))
            self.assertEqual(item.review_request, draft)

    def test_list_reuses_saved_assessment_without_reparsing_the_pdf(self):
        from unittest.mock import patch
        self.save()
        with patch.object(batches, 'read_statement_import', side_effect=AssertionError('List reparsed saved source')):
            self.assertTrue(self.fixture.status(self.batch)['items'][0]['can_import'])

    def test_batch_edit_updates_shared_draft_and_stale_batch_editor_is_rejected(self):
        saved = self.save()
        with self.f.SessionLocal() as db:
            stored = db.scalar(select(Item).where(Item.batch_id == self.batch))
            opened = batches.checked_batch_items(db, self.f.case.id, [stored])[0]
        self.save('New shared edit', saved['review_revision'])
        edited = StatementReviewDraft.model_validate({**opened.review_request, 'holder': 'Batch edit'})
        with self.f.SessionLocal() as db:
            with self.assertRaisesRegex(PdfMappingError, 'Another user saved'):
                batches.save_review(db, case_id=self.f.case.id, batch_id=self.batch, item_id=opened.id,
                    request=edited, expected_review_revision=opened.review_revision, actor=self.f.actor)
        with self.f.SessionLocal() as db:
            stored = db.get(Item, opened.id)
            current = batches.checked_batch_items(db, self.f.case.id, [stored])[0]
            batches.save_review(db, case_id=self.f.case.id, batch_id=self.batch, item_id=opened.id,
                request=edited, expected_review_revision=current.review_revision, actor=self.f.actor)
        self.assertEqual(self.f.preview()['saved_review']['request']['holder'], 'Batch edit')
        self.assertTrue(self.fixture.status(self.batch)['items'][0]['can_import'])
