"""A page of proposed lines is saved only as a person's review, through the ordinary batch review save."""
import os
from unittest import TestCase
from unittest.mock import patch

from sqlalchemy import select

from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialTransaction
from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
from services.financial import import_batches as batches, page_row_proposals as prp
from services.financial.pdf_candidates import PdfMappingError
from services.financial.statement_progress import review_progress
from tests import test_financial_statement_overlap as fixtures


class PageConfirmationTests(TestCase):
    def setUp(self):
        switch = patch.dict(os.environ, {'LOUPE_FINANCIAL_PAGE_ROW_PROPOSALS': '1'})
        switch.start()
        self.addCleanup(switch.stop)
        self.fixture = fixtures.StatementOverlapTests()
        self.fixture.setUp()
        self.f = self.fixture.f
        self.batch = self.fixture.create(self.fixture.primary)
        with self.f.SessionLocal() as db:
            self.item_id = db.scalar(select(Item.id).where(Item.batch_id == self.batch))
            state = prp._item_state(db, self.f.case.id, self.batch, self.item_id)
        _, self.proposal, request, self.review_revision = state
        row = next(r for r in request['rows'] if not r['excluded'])
        self.row_id = row['id']
        line = dict(row_id=row['id'], source='set_aside', missing=[], chained=True, direction=row['direction'],
                    values=dict(date=dict(value=row['date'], cell={}, text=row['date']),
                                amount=dict(value=int(row['amount_minor']), cell={}, text=row['amount_minor']),
                                balance_after=dict(value=int(row['balance_minor'] or 0), cell={}, text='x'),
                                description='Confirmed page line'))
        self.page = dict(page_number=1, confirmable=True, reason=None, lines=[line], digest='a' * 64)
        self.patch = patch.object(prp, 'page_proposals', side_effect=lambda proposal, request=None: dict(
            pages=[self.page], opening=None, closing=None, totals='none', blocked=None))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.fixture.tearDown()

    def _saved(self):
        with self.f.SessionLocal() as db:
            item = db.get(Item, self.item_id)
            return item.review_request, review_progress(db.get(EvidenceFile, item.file_id), item.statement_key)

    def _confirm(self, actor, digest='a' * 64):
        with self.f.SessionLocal() as db:
            return prp.confirm_item_page(db, case_id=self.f.case.id, batch_id=self.batch, item_id=self.item_id,
                                         page_number=1, digest=digest, expected_review_revision=self.review_revision,
                                         actor=actor)

    def test_nothing_is_saved_without_a_person(self):
        before = self._saved()
        with self.assertRaises(PdfMappingError) as raised:
            self._confirm(None)
        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(self._saved(), before)

    def test_nothing_is_saved_when_the_lines_changed(self):
        before = self._saved()
        with self.assertRaises(PdfMappingError) as raised:
            self._confirm(self.f.actor, digest='b' * 64)
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(self._saved(), before)

    def test_a_person_confirming_saves_their_review_and_imports_nothing(self):
        result = self._confirm(self.f.actor)
        self.assertEqual((result['page_number'], result['lines']), (1, 1))
        request, saved = self._saved()
        row = next(r for r in request['rows'] if r['id'] == self.row_id)
        self.assertFalse(row['excluded'])
        self.assertEqual(saved['saved_by']['user_id'], str(self.f.actor.user_id))
        # The machine reading is unchanged: the proposal read again still has its own row.
        with self.f.SessionLocal() as db:
            _, proposal, _, _ = prp._item_state(db, self.f.case.id, self.batch, self.item_id)
            self.assertEqual(proposal['rows'], self.proposal['rows'])
            self.assertEqual(list(db.scalars(select(FinancialTransaction))), [])

    def test_a_stale_review_revision_is_refused(self):
        with self.f.SessionLocal() as db:
            with self.assertRaises(PdfMappingError) as raised:
                prp.confirm_item_page(db, case_id=self.f.case.id, batch_id=self.batch, item_id=self.item_id,
                                      page_number=1, digest='a' * 64, expected_review_revision='c' * 64,
                                      actor=self.f.actor)
        self.assertEqual(raised.exception.status_code, 409)
