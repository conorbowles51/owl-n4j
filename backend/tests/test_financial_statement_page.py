"""The statement page shown beside the Transactions table for naming a payment, and the saved name's origin."""
from datetime import date
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import unittest.mock

from sqlalchemy import select

from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialTransaction
from routers import financial_adjudication, financial_ledger
from services.financial.ledger_source import LedgerSourceError
from services.financial.payment_labels import (PaymentLabelsRequest, RemovePaymentLabelsRequest, payment_label_view,
                                               remove_payment_labels, update_payment_labels)
from services.financial.statement_page import find_on_page, payment_page, payment_page_png
from services.financial.transactions import LOCATOR_PROVENANCE_KEY
from tests.test_financial_duplicates import DuplicateTestCase


class FakePage:
    def __init__(self, words=()):
        self.rect = SimpleNamespace(width=600.0, height=800.0)
        self._words = list(words)

    def get_text(self, kind):
        assert kind == 'words'
        return self._words

    def get_pixmap(self, matrix):
        return SimpleNamespace(tobytes=lambda kind: b'png-of-page')


class FakeDocument:
    def __init__(self, pages):
        self.pages = pages
        self.page_count = len(pages)
        self.loaded = []
        self.closed = False

    def load_page(self, index):
        self.loaded.append(index + 1)
        return self.pages[index]

    def close(self):
        self.closed = True


def rectangle(page, top, bottom):
    return {'kind': 'page_rectangle', 'page': page, 'rect': [10000, top, 590000, bottom],
            'page_size': [600000, 800000], 'units': 'millipoints', 'space': 'pdf_displayed'}


class FindOnPageTests(unittest.TestCase):
    def test_amount_and_dates_are_found_as_printed_and_reported_as_page_fractions(self):
        page = FakePage([
            (30, 100, 60, 110, '15/01', 0, 0, 0), (70, 100, 200, 110, 'PAGO', 0, 0, 1),
            (400, 100, 460, 110, '$1,234.56', 0, 0, 2), (500, 100, 560, 110, '11,234.56', 0, 0, 3),
            (30, 200, 45, 210, '15', 0, 1, 0), (46, 200, 70, 210, 'ENE', 0, 1, 1),
            (400, 300, 460, 310, '1234.56-', 0, 2, 0),
        ])
        result = find_on_page(page, amount_minor=123456, currency='MXN', dates=[date(2024, 1, 15)])
        self.assertTrue(result['text_layer'])
        kinds = [(f['kind'], f['text']) for f in result['found']]
        # 11,234.56 is another figure, not this amount; both printed forms of this amount are offered.
        self.assertEqual(kinds, [('date', '15/01'), ('amount', '$1,234.56'), ('date', '15 ENE'), ('amount', '1234.56-')])
        self.assertEqual(result['found'][1]['rect'], [round(400 / 600, 5), 0.125, round(460 / 600, 5), 0.1375])

    def test_a_scanned_page_finds_nothing_and_says_it_has_no_text(self):
        result = find_on_page(FakePage(), amount_minor=100, currency='USD', dates=[date(2024, 1, 1)])
        self.assertEqual(result, dict(found=[], text_layer=False))


class StatementPageTests(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        self.document = self.make_copy()
        rows = self.db.scalars(select(FinancialTransaction).where(
            FinancialTransaction.source_document_id == self.document.id).order_by(FinancialTransaction.row_index)).all()
        self.row = rows[0]
        self.others = rows[1:]
        self.file = self.db.get(EvidenceFile, self.document.evidence_file_id)
        self.directory = Path(tempfile.mkdtemp(prefix='loupe-statement-page-'))
        self.pdf = self.directory / 'statement.pdf'
        self.pdf.write_bytes(b'%PDF-1.4 stand-in')
        self.file.stored_path = str(self.pdf)
        self.row.provenance = {LOCATOR_PROVENANCE_KEY: rectangle(2, 700000, 712000)}
        self.db.commit()
        self.opened = []

    def open_pdf(self, path):
        self.opened.append(path)
        self.fake = FakeDocument([FakePage(), FakePage(), FakePage()])
        return self.fake

    def page(self, **extra):
        return payment_page(self.db, **{'case_id': self.case.id, 'transaction_id': self.row.id,
                                        'resolve_path': Path, 'open_pdf': self.open_pdf, **extra})

    def image(self, page, **extra):
        return payment_page_png(self.db, **{'case_id': self.case.id, 'transaction_id': self.row.id, 'page': page,
                                            'width': 800, 'resolve_path': Path, 'open_pdf': self.open_pdf, **extra})

    def test_rectangle_payment_reports_its_page_and_whether_it_is_the_last_on_the_page(self):
        result = self.page()
        self.assertEqual((result['page'], result['page_count'], result['locator']['kind']), (2, 3, 'page_rectangle'))
        self.assertTrue(result['last_on_page'])
        self.assertEqual(result['found'], [])
        self.assertTrue(self.fake.closed)
        if self.others:
            self.others[0].provenance = {LOCATOR_PROVENANCE_KEY: rectangle(2, 720000, 730000)}
            self.db.commit()
            self.assertFalse(self.page()['last_on_page'])
        self.assertFalse(self.db.dirty)

    def test_page_only_payment_searches_its_amount_and_date_on_its_page(self):
        self.row.provenance = {LOCATOR_PROVENANCE_KEY: {'kind': 'page_only', 'page': 1}}
        self.db.commit()
        with unittest.mock.patch('services.financial.statement_page.find_on_page',
                                 return_value=dict(found=[{'kind': 'amount'}], text_layer=True)) as find:
            result = self.page()
        self.assertEqual(result['found'], [{'kind': 'amount'}])
        self.assertEqual(find.call_args.kwargs['amount_minor'], str(self.row.amount_minor))
        self.assertIn(self.row.ordering_date, find.call_args.kwargs['dates'])
        self.assertEqual(self.fake.loaded, [1])

    def test_only_the_payment_page_and_its_neighbours_are_rendered(self):
        for page in (1, 2, 3):
            png, count = self.image(page)
            self.assertEqual((png, count), (b'png-of-page', 3))
        for page in (0, 4):
            with self.assertRaises(LedgerSourceError) as caught:
                self.image(page)
            self.assertEqual(caught.exception.status_code, 422)

    def test_another_case_cannot_reach_the_page_or_its_image(self):
        for call in (lambda: self.page(case_id=self.other_case.id), lambda: self.image(2, case_id=self.other_case.id)):
            with self.assertRaises(LedgerSourceError) as caught:
                call()
            self.assertEqual(caught.exception.status_code, 404)
        self.file.case_id = self.other_case.id
        self.db.commit()
        with self.assertRaises(LedgerSourceError) as caught:
            self.image(2)
        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(self.opened, [])

    def test_a_payment_without_a_stored_page_has_no_image(self):
        self.row.provenance = {}
        self.db.commit()
        self.assertIsNone(self.page()['page'])
        with self.assertRaises(LedgerSourceError) as caught:
            self.image(1)
        self.assertEqual(caught.exception.status_code, 404)

    def test_routes_require_case_view_access(self):
        for path in ('/api/financial/ledger/{transaction_id}/statement-page',
                     '/api/financial/ledger/{transaction_id}/statement-page/{page}/image'):
            route = next(r for r in financial_ledger.router.routes if r.path == path)
            calls = {dependency.call for dependency in route.dependant.dependencies}
            self.assertIn(financial_ledger._require_ledger_case_access, calls)
            self.assertEqual(route.methods, {'GET'})
        route = next(r for r in financial_adjudication.router.routes
                     if r.path == '/api/financial/ledger/payment-labels/remove')
        calls = {dependency.call for dependency in route.dependant.dependencies}
        self.assertIn(financial_adjudication._require_adjudication_case_access, calls)


class NamedFromStatementTests(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        self.document = self.make_copy()
        self.rows = self.db.scalars(select(FinancialTransaction).where(
            FinancialTransaction.source_document_id == self.document.id)).all()
        self.row = self.rows[0]

    def save(self, rows, **body):
        return update_payment_labels(self.db, case_id=self.case.id, actor=self.actor, request=PaymentLabelsRequest(
            transactions=[{'id': r.id, 'version': (r.metadata_ or {}).get('investigation_labels', {}).get('version', 0)}
                          for r in rows], **body))

    def other_side(self, row):
        return 'from_name' if row.direction == 'credit' else 'to_name'

    def test_named_from_the_statement_wins_shows_its_origin_and_changes_nothing_else(self):
        before = {c: getattr(self.row, c) for c in ('amount_minor', 'direction', 'description', 'ordering_date')}
        self.save([self.row], counterparty_name='ACME SA DE CV', named_from='statement')
        self.db.refresh(self.row)
        view = payment_label_view(self.row, self.row.account)
        side = self.other_side(self.row)
        self.assertEqual(view[side], 'ACME SA DE CV')
        self.assertEqual(view['label_sources'][side]['source'], 'investigator')
        self.assertTrue(view['label_sources'][side]['explanation'].startswith('Named by Investigator from the statement on '))
        entry = self.row.metadata_['investigation_label_history'][-1]
        self.assertEqual((entry['via'], entry['reason'], entry['actor_email']),
                         ('statement', 'Named from the statement.', 'investigator@example.test'))
        self.assertEqual(before, {c: getattr(self.row, c) for c in before})

    def test_similar_payments_record_which_payment_they_were_named_like(self):
        if len(self.rows) < 2:
            self.skipTest('fixture has one row')
        self.save(self.rows[1:2], counterparty_name='ACME', named_from='statement', same_as=self.row.id)
        self.db.refresh(self.rows[1])
        entry = self.rows[1].metadata_['investigation_label_history'][-1]
        self.assertEqual(entry['same_as'], str(self.row.id))
        view = payment_label_view(self.rows[1], self.rows[1].account)
        self.assertIn('the same name as a payment like it', view['label_sources'][self.other_side(self.rows[1])]['explanation'])

    def test_removing_the_name_restores_the_reading_and_is_audited(self):
        original = payment_label_view(self.row, self.row.account)
        side = self.other_side(self.row)
        self.save([self.row], counterparty_name='ACME', named_from='statement')
        self.db.refresh(self.row)
        result = remove_payment_labels(self.db, case_id=self.case.id, actor=self.actor, request=RemovePaymentLabelsRequest(
            transactions=[{'id': self.row.id, 'version': 1}], fields=['counterparty_name']))
        self.assertEqual(result['updated'], 1)
        self.db.refresh(self.row)
        view = payment_label_view(self.row, self.row.account)
        self.assertEqual((view[side], view['label_sources'][side]), (original[side], original['label_sources'][side]))
        entry = self.row.metadata_['investigation_label_history'][-1]
        self.assertEqual((entry['removed'], entry['before'], entry['version']), ([side], {side: 'ACME'}, 2))

    def test_removal_refuses_a_stale_version_and_another_case(self):
        self.save([self.row], counterparty_name='ACME', named_from='statement')
        from services.financial.payment_labels import PaymentLabelsError
        with self.assertRaises(PaymentLabelsError):
            remove_payment_labels(self.db, case_id=self.case.id, actor=self.actor, request=RemovePaymentLabelsRequest(
                transactions=[{'id': self.row.id, 'version': 0}], fields=['counterparty_name']))
        with self.assertRaises(PaymentLabelsError) as caught:
            remove_payment_labels(self.db, case_id=self.other_case.id, actor=self.actor, request=RemovePaymentLabelsRequest(
                transactions=[{'id': self.row.id, 'version': 1}], fields=['counterparty_name']))
        self.assertEqual(caught.exception.status_code, 404)


if __name__ == '__main__':
    unittest.main()
