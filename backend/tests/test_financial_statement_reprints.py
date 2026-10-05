"""A card statement printed twice in one PDF reaches the ledger once.

Synthetic Capital One pages only. Each printing restarts its printed page
count; the reprint is set aside as a copy of the first printing when its money
is equal, and both printings are held when it is not.
"""
import hashlib
from copy import deepcopy
from unittest import TestCase
from sqlalchemy import select
from postgres.models.evidence import EvidenceDocumentText, EvidenceFile, EvidenceTableGeometry
from postgres.models.financial import FinancialTransaction
from services.financial.import_batches import assess, initial_request
from services.financial.pdf_candidates import PdfMappingError
from services.financial.pending_statement_duplicates import apply_duplicate_disposition
from services.financial.statement_import import read_statement_import
from tests.test_financial_pdf_geometry_candidates import rectangle
from tests import test_financial_statement_import as statement_fixture
from tests.test_financial_statement_import_card import summary_source
from tests.test_financial_statement_import_proposal import source


def transactions(shop_amount='$61.62'):
    return source([
        ['Platinum MasterCard Account Ending in 1234'],
        ['May 12, 2020 - Jun. 11, 2020 | 31 days in Billing Cycle'],
        ['Visit www.capitalone.com to see detailed transactions.'],
        ['SAMPLE HOLDER #1234: Payments, Credits and Adjustments'],
        ['Date', 'Description', 'Amount'], ['May 30', 'PAYMENT', '- $180.00'],
        ['SAMPLE HOLDER #1234: Transactions'], ['Date', 'Description', 'Amount'],
        ['May 29', 'EXAMPLE SHOP', shop_amount], ['Total Transactions for This Period', shop_amount],
        ['Interest Charged'], ['Interest Charge on Purchases', '$56.16'],
        ['Total Interest for This Period', '$56.16'], ['Page 1 of 1']])


def table(grid, page, *, positioned):
    values = []
    for row in grid['rows']:
        for cell in row['cells']:
            locator = cell['locator'] if positioned else rectangle(20 + row['row_index'] * 20,
                x=20 + cell['column_index'] * 150, width=140, height=15)
            values.append(dict(row=row['row_index'], column=cell['column_index'], text=cell['expected_text'],
                               locator={**locator, 'page': page}))
    return dict(table_source='text_alignment', geometry_source='cell_rectangles',
                table=dict(page=page, table={**rectangle(0, x=0, width=600, height=800), 'page': page},
                           unlocated_values=0, values=values))


class StatementReprintTests(TestCase):
    def setUp(self):
        self.fixture = statement_fixture.StatementImportTests('test_closed_payment_share_saves_notice_without_inventing_a_final_balance')
        self.fixture.setUp()
        for name in ('db', 'file', 'case', 'SessionLocal', 'confirm'):
            setattr(self, name, getattr(self.fixture, name))

    def tearDown(self):
        self.fixture.tearDown()

    def install(self, *printings):
        job = self.db.get(EvidenceDocumentText, self.file.id).engine_job_id
        for geometry in self.db.scalars(select(EvidenceTableGeometry).where(
                EvidenceTableGeometry.evidence_file_id == self.file.id)):
            self.db.delete(geometry)
        self.db.flush()
        for page, grid in enumerate(printings, start=1):
            self.db.add(EvidenceTableGeometry(evidence_file_id=self.file.id, page_number=page, engine_job_id=job,
                payload=[table(summary_source(), page, positioned=True), table(grid, page, positioned=False)]))
        text = self.db.get(EvidenceDocumentText, self.file.id)
        text.content = 'Capital One\n'
        text.content_sha256 = hashlib.sha256(text.content.encode()).hexdigest()
        text.character_count = len(text.content)
        text.source_locations = [dict(kind='page', page_number=page, start_char=0, end_char=len(text.content),
            text_origin='digital_text_layer') for page in range(1, len(printings) + 1)]
        self.db.commit()

    def read(self, statement_id=None):
        with self.SessionLocal() as db:
            return read_statement_import(db, case_id=self.case.id, evidence_file_id=self.file.id,
                                         statement_id=statement_id, currency='USD')

    def printings(self):
        choices = self.read()['statement_choices']
        self.assertEqual(len(choices), 2, choices)
        first, second = sorted(choices, key=lambda choice: choice['printing'])
        return self.read(first['id']), self.read(second['id'])

    def disposition(self, proposal):
        with self.SessionLocal() as db:
            result = apply_duplicate_disposition(db, case_id=self.case.id,
                file=db.get(EvidenceFile, self.file.id), proposal=proposal)
            db.commit()
            return result

    def test_an_identical_reprint_is_set_aside_and_the_period_imports_once(self):
        self.install(transactions(), transactions())
        first, second = self.printings()
        self.assertEqual(second['printed_copies']['first'], first['statement_id'])
        self.assertTrue(first['printed_copies']['identical'])
        self.assertEqual(assess(first)[1]['can_import'], True, assess(first)[1]['problems'])
        decision = self.disposition(second)
        self.assertEqual(decision['status'], 'ignored', decision)
        self.assertTrue(decision['printed_copy'])
        self.assertEqual(decision['retained']['statement_id'], first['statement_id'])
        self.assertEqual(self.disposition(first)['status'], 'retained')
        receipt = self.confirm(initial_request(first))
        self.assertEqual(receipt['transaction_count'], 3)
        reprint = self.confirm(initial_request(self.read(second['statement_id'])))
        self.assertEqual(reprint['outcome'], 'duplicate_ignored')
        self.assertTrue(self.read(second['statement_id'])['duplicate_disposition']['current'])
        with self.SessionLocal() as db:
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction)))), 3)

    def test_a_reprint_whose_money_differs_holds_both_printings(self):
        self.install(transactions(), transactions('$61.63'))
        first, second = self.printings()
        self.assertFalse(first['printed_copies']['identical'])
        for proposal in (first, second):
            state, summary = assess(proposal)
            self.assertFalse(summary['can_import'])
            self.assertTrue(any(problem.get('kind') == 'printed_copies' for problem in summary['problems']))
        self.assertEqual(self.disposition(second)['status'], 'needs_comparison')
        with self.assertRaisesRegex(PdfMappingError, 'printed more than once'):
            self.confirm(initial_request(first))
        # An investigator who compared both printings can record why one is imported.
        request = {**initial_request(first), 'coverage_review_reason': 'Second printing misprinted; first matches the summary.'}
        self.assertTrue(assess(first, request)[1]['can_import'], assess(first, request)[1]['problems'])

    def test_an_edited_reprint_is_not_hidden(self):
        self.install(transactions(), transactions())
        _, second = self.printings()
        request = deepcopy(initial_request(second))
        next(row for row in request['rows'] if not row['excluded'])['description'] = 'Investigator correction'
        with self.SessionLocal() as db:
            result = apply_duplicate_disposition(db, case_id=self.case.id,
                file=db.get(EvidenceFile, self.file.id), proposal=second, request=request)
        self.assertEqual(result['status'], 'needs_comparison')

