"""Generated card fixtures only; no client documents or extracted client data."""
import unittest
from copy import deepcopy

from services.financial.statement_import_catalog import statement_catalog
from services.financial.statement_import_credit_one import propose_credit_one_table
from services.financial.statement_currency import currencies_by_statement
from services.financial.statement_review_checks import add_period_checks
from tests.test_financial_pdf_geometry_candidates import rectangle


def source(*, page=1, account='4111 1111 1111 1111',
           period='December 16, 2023 to January 15, 2024', continuation=False):
    lines = [
        (10, [(200, 'CREDIT ONE BANK CREDIT CARD STATEMENT')]),
        (22, [(200, 'Account Number '+account)]),
        (34, [(200, period)]),
    ]
    if continuation:
        lines += [(65, [(200, 'INTEREST CHARGE CALCULATION')]),
                  (80, [(140, 'Purchases'), (440, '$2.00')])]
    else:
        lines += [
            (60, [(150, 'SUMMARY OF ACCOUNT ACTIVITY'), (345, 'PAYMENT INFORMATION')]),
            (72, [(140, 'Previous Balance'), (260, '$100.00'), (300, 'New Balance'), (445, '$87.00')]),
            (84, [(140, 'Payments'), (260, '$40.00'), (300, 'Minimum Payment Due'), (445, '$20.00')]),
            (120, [(140, 'New Balance'), (260, '$87.00')]),
            (245, [(275, 'TRANSACTIONS')]),
            (257, [(140, 'Reference Number'), (218, 'Trans Date Post Date Description of Transaction or Credit'), (445, 'Amount')]),
            (270, [(140, 'REFERENCE123'), (225, '12/15'), (255, '12/16'), (278, 'EXAMPLE SHOP'), (452, '25.00')]),
            (282, [(140, 'REFERENCE124'), (225, '12/20'), (255, '12/20'), (278, 'PAYMENT - MOBILE APP'), (447, '-40.00')]),
            (294, [(278, 'SYNTHETIC REFERENCE CONTINUED')]),
            (306, [(278, 'Fees')]),
            (318, [(278, 'TOTAL FEES FOR THIS PERIOD'), (452, '0.00')]),
            (330, [(278, 'Interest Charged')]),
            (342, [(225, '01/15'), (255, '01/15'), (278, 'Interest Charge on Purchases'), (452, '2.00')]),
            (354, [(225, '01/15'), (255, '01/15'), (278, 'Interest Charge on Cash Advances'), (452, '0.00')]),
            (366, [(278, 'TOTAL INTEREST FOR THIS PERIOD'), (452, '2.00')]),
            (378, [(270, '2024 Totals Year-to-Date')]),
            (390, [(200, 'Total fees charged in 2024'), (440, '$75.00')]),
            (700, [(140, 'CREDIT ONE BANK'), (335, 'EXAMPLE PERSON')]),
            (712, [(140, 'PO BOX 100'), (335, '100 FIRST AVENUE')]),
            (724, [(140, 'EXAMPLE CITY CA 90000'), (335, 'EXAMPLE CITY DC 20000')]),
        ]
    rows = []
    for index, (y, values) in enumerate(lines):
        cells = []
        for column, (x, text) in enumerate(values):
            # Fixed right alignment for monetary cells, independent of digits.
            width = 470-x if x >= 440 else min(140, len(text)*2.5)
            box = rectangle(y, x=x, width=width, height=8)
            box['rect'] = [int(v) for v in box['rect']]
            box['page'] = page
            cells.append(dict(column_index=column, expected_text=text, locator=box))
        rows.append(dict(row_index=index, cells=cells))
    return dict(page_number=page, table_index=0, source_revision='c'*64, rows=rows)


def proposal(data):
    choice = statement_catalog([data])['statements'][0]
    return propose_credit_one_table(data, 'USD', choice)


def install_collection(fixture):
    """The same disposable bank/card collection serves API and browser checks."""
    import hashlib
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceDocumentText, EvidenceTableGeometry
    from tests.test_financial_statement_import_andrews import two_shares
    sources = [two_shares(), source(page=2), source(page=3, continuation=True)]
    document = fixture.db.get(EvidenceDocumentText, fixture.file.id)
    document.content = '\n\n'.join('\n'.join(' '.join(c['expected_text'] for c in r['cells'])
        for r in s['rows']) for s in sources)
    document.content_sha256 = hashlib.sha256(document.content.encode()).hexdigest()
    document.character_count = len(document.content)
    document.source_locations = [dict(kind='page', page_number=i, text_origin='digital_text_layer') for i in range(1, 4)]
    for old in list(fixture.db.scalars(select(EvidenceTableGeometry))):
        fixture.db.delete(old)
    fixture.db.flush()
    fixture.file.original_filename = 'Synthetic bank and card collection.pdf'
    for grid in sources:
        box = rectangle(0, x=0, width=600, height=800)
        box['page'] = grid['page_number']
        payload = [dict(table_source='text_alignment', geometry_source='cell_rectangles',
            table=dict(page=grid['page_number'], table=box, unlocated_values=0,
                values=[dict(row=r['row_index'], column=c['column_index'], text=c['expected_text'], locator=c['locator'])
                    for r in grid['rows'] for c in r['cells']]))]
        fixture.db.add(EvidenceTableGeometry(evidence_file_id=fixture.file.id,
            page_number=grid['page_number'], engine_job_id=document.engine_job_id, payload=payload))
    fixture.db.commit()


class CreditOneReaderTests(unittest.TestCase):
    def test_payments_purchases_interest_and_liability_reconcile_without_summary_duplicates(self):
        data = source()
        original = deepcopy(data)
        choices = currencies_by_statement(statement_catalog([data])['statements'], [data])
        checked = add_period_checks(choices, [data], None)[0]
        self.assertEqual(checked['currency'], 'USD')
        self.assertEqual(checked['holder'], 'EXAMPLE PERSON')
        self.assertEqual(checked['account_reference'], '4111111111111111')
        self.assertEqual(checked['checks']['balance_status'], 'matches')
        self.assertEqual(checked['checks']['flagged_rows'], 0)
        result = proposal(data)
        payments = [r for r in result['rows'] if not r['excluded']]
        self.assertEqual([r['fields']['amount_minor'] for r in payments], ['2500', '4000', '200'])
        self.assertEqual([r['fields']['direction'] for r in payments], ['debit', 'credit', 'debit'])
        self.assertEqual(payments[0]['fields']['date'], '2023-12-15')
        self.assertEqual(payments[0]['fields']['booking_date'], '2023-12-16')
        self.assertEqual(payments[-1]['fields']['date'], '2024-01-15')
        self.assertTrue(payments[1]['fields']['description'].endswith('SYNTHETIC REFERENCE CONTINUED'))
        self.assertEqual(payments[1]['continuation_sources'][0]['page_number'], 1)
        self.assertEqual(data, original)

    def test_mixed_collection_separates_banks_cards_accounts_and_periods(self):
        from tests.test_financial_statement_import_andrews import two_shares
        from tests.test_financial_statement_import_catalog import page
        sources = [two_shares(), source(page=2), source(page=3, continuation=True),
            source(page=4, account='5555 5555 5555 4444'),
            source(page=5, period='January 16, 2024 to February 15, 2024'), page(6)]
        catalog = statement_catalog(sources)
        self.assertEqual(len(catalog['statements']), 6)
        self.assertTrue(catalog['complete_coverage'])
        cards = [s for s in catalog['statements'] if s['layout_id'] == 'credit-one-card']
        self.assertEqual([s['page_numbers'] for s in cards], [[2, 3], [4], [5]])
        self.assertTrue(all(s['account_type'] == 'credit_card' for s in cards))
        self.assertTrue(all(s['account_type'] in ('savings', 'checking') for s in catalog['statements']
            if s['layout_id'] == 'andrews-share-statement'))

    def test_damaged_digits_are_retained_for_review_and_never_inferred_from_totals(self):
        data = source()
        data['rows'][9]['cells'][1]['expected_text'] = '12115'
        data['rows'][9]['cells'][-1]['expected_text'] = '2S.00'
        data['rows'][4]['cells'][1]['expected_text'] = 'S100.00'
        result = proposal(data)
        payment = result['rows'][9]
        self.assertFalse(payment['excluded'])
        self.assertNotIn('date', payment['fields'])
        self.assertNotIn('amount_minor', payment['fields'])
        self.assertEqual(len(payment['issues']), 2)
        self.assertNotIn('balance', result['rows'][4]['fields'])
        self.assertTrue(result['rows'][4]['issues'])

    def test_conflicting_or_unreadable_headings_do_not_borrow_a_neighbours_identity(self):
        for field, text in [(1, 'Account Number 4111 1111 1111 11O1'),
                            (2, 'December 16, 2023 to January 99, 2024')]:
            data = source(page=2)
            data['rows'][field]['cells'][0]['expected_text'] = text
            catalog = statement_catalog([source(), data])
            self.assertEqual(len(catalog['statements']), 1)
            self.assertEqual(catalog['unclassified_sources'], [dict(page_number=2, table_index=0)])
        data = source()
        second = deepcopy(data['rows'][1]); second['row_index'] = 99
        second['cells'][0]['expected_text'] = 'Account Number 5555 5555 5555 4444'
        data['rows'].append(second)
        self.assertEqual(statement_catalog([data])['statements'], [])

    def test_interest_calculation_page_is_not_a_second_charge(self):
        data = source(continuation=True)
        self.assertFalse(any(not r['excluded'] for r in proposal(data)['rows']))

    def test_missing_payment_cells_are_visible_not_silently_skipped(self):
        data = source()
        data['rows'][9]['cells'].pop()
        result = proposal(data)
        self.assertEqual(result['rows'][9]['kind'], 'unresolved')
        self.assertFalse(result['rows'][9]['excluded'])
        self.assertTrue(result['rows'][9]['issues'])

    def test_credit_balance_sign_and_joined_posting_description_keep_original_cells(self):
        data = source()
        data['rows'][4]['cells'][1]['expected_text'] = '$12.50-'
        data['rows'][6]['cells'][1]['expected_text'] = '$25.50-|'
        data['rows'][9]['cells'][2]['expected_text'] = '12/16. EXAMPLE BRANCH'
        data['rows'][10]['cells'][2]['expected_text'] = '12/20,'
        original = deepcopy(data)
        result = proposal(data)
        self.assertEqual(result['rows'][4]['fields']['balance'], '-1250')
        self.assertEqual(result['rows'][6]['fields']['balance'], '-2550')
        self.assertEqual(result['rows'][9]['fields']['booking_date'], '2023-12-16')
        self.assertEqual(result['rows'][9]['fields']['description'], 'EXAMPLE BRANCH EXAMPLE SHOP')
        self.assertEqual(result['rows'][10]['fields']['booking_date'], '2023-12-20')
        self.assertEqual(data, original)


class MixedStatementPersistenceTests(unittest.TestCase):
    def setUp(self):
        from tests.test_financial_statement_import import StatementImportTests
        self.fixture = StatementImportTests('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.fixture.setUp()
        install_collection(self.fixture)

    def tearDown(self):
        self.fixture.tearDown()

    def test_import_and_reopen_keep_bank_shares_card_debt_and_original_pages_separate(self):
        from sqlalchemy import select
        from postgres.models.financial import FinancialAccount, FinancialStatementPeriod, FinancialTransaction
        from services.financial.statement_import import read_statement_import
        from services.financial.import_batches import initial_request
        from services.financial.periods import read_opening, read_closing
        from uuid import UUID
        f = self.fixture
        choices = f.preview()['statement_choices']
        self.assertEqual(len(choices), 3)
        receipts = []
        for choice in choices:
            with f.SessionLocal() as db:
                review = read_statement_import(db, case_id=f.case.id, evidence_file_id=f.file.id, statement_id=choice['id'])
            self.assertEqual(review['currency'], 'USD')
            receipt = f.confirm(initial_request(review))
            receipts.append(receipt)
            self.assertEqual(receipt['transaction_count'], 3 if choice['layout_id'] == 'credit-one-card' else 1)
            repeated = f.confirm(initial_request(review))
            self.assertFalse(repeated['created'])
            self.assertEqual(repeated['source_document_id'], receipt['source_document_id'])
            with f.SessionLocal() as db:
                reopened = read_statement_import(db, case_id=f.case.id, evidence_file_id=f.file.id, statement_id=choice['id'])
                self.assertEqual(reopened['current_import']['account_id'], receipt['account_id'])
                self.assertEqual(reopened['current_import']['transaction_count'], receipt['transaction_count'])
        self.assertEqual(len({r['account_id'] for r in receipts}), 3)
        with f.SessionLocal() as db:
            accounts = list(db.scalars(select(FinancialAccount).where(
                FinancialAccount.id.in_([UUID(r['account_id']) for r in receipts]))))
            self.assertEqual(sorted(a.account_type for a in accounts), ['checking', 'credit_card', 'savings'])
            payments = list(db.scalars(select(FinancialTransaction)))
            self.assertEqual(len(payments), 5)
            card = next(a for a in accounts if a.account_type == 'credit_card')
            period = db.scalar(select(FinancialStatementPeriod).where(FinancialStatementPeriod.account_id == card.id))
            self.assertEqual(read_opening(period).minor_units, -10000)
            self.assertEqual(read_closing(period).minor_units, -8700)
            self.assertEqual({p.provenance['statement_import_original']['page_number'] for p in payments if p.account_id == card.id}, {2})

    def test_other_cases_cannot_read_or_import_the_collection(self):
        from services.financial.statement_import import read_statement_import, confirm_statement_import
        from services.financial.pdf_candidates import PdfMappingError
        from services.financial.import_batches import initial_request
        f = self.fixture
        other_case = f.other_case.id
        choice = f.preview()['statement_choices'][0]
        with f.SessionLocal() as db:
            review = read_statement_import(db, case_id=f.case.id, evidence_file_id=f.file.id, statement_id=choice['id'])
        with f.SessionLocal() as db, self.assertRaises(PdfMappingError):
            read_statement_import(db, case_id=other_case, evidence_file_id=f.file.id)
        with self.assertRaises(PdfMappingError):
            confirm_statement_import(session_factory=f.SessionLocal, case_id=other_case,
                evidence_file_id=f.file.id, request=initial_request(review), actor=f.actor, resolve_path=__import__('pathlib').Path)


class StatementReadingQualityTests(unittest.TestCase):
    @staticmethod
    def table(grid):
        return dict(table=dict(page=grid['page_number'], values=[dict(row=r['row_index'], column=c['column_index'],
            text=c['expected_text'], locator=c['locator']) for r in grid['rows'] for c in r['cells']]))

    def test_reread_requires_same_identity_payment_count_controls_and_fewer_missing_fields(self):
        from services.financial.statement_reading_quality import assess_statement_reading, prefer_image_reading
        clean = source()
        damaged = deepcopy(clean)
        damaged['rows'][9]['cells'][1]['expected_text'] = '12115'
        before = assess_statement_reading([self.table(damaged)])
        after = assess_statement_reading([self.table(clean)])
        self.assertEqual(before['unreadable'], 1)
        self.assertEqual(after['unreadable'], 0)
        self.assertTrue(prefer_image_reading(before, after))
        for changed in (None, before, {**after, 'payments': 2}, {**after, 'balances': 1},
                        {**after, 'identity': ['different-account']}):
            self.assertFalse(prefer_image_reading(before, changed))

    def test_andrews_invalid_money_is_reread_but_arithmetic_alone_does_not_guess_values(self):
        from services.financial.statement_reading_quality import assess_statement_reading
        from tests.test_financial_statement_import_andrews import two_shares
        data = two_shares()
        self.assertEqual(assess_statement_reading([self.table(data)])['unreadable'], 0)
        data['rows'][14]['cells'][2]['expected_text'] = '-2O.00'
        self.assertGreater(assess_statement_reading([self.table(data)])['unreadable'], 0)

    def test_andrews_missing_running_balance_alone_requests_a_better_image_reading(self):
        from services.financial.statement_reading_quality import assess_statement_reading, prefer_image_reading
        from tests.test_financial_statement_import_andrews import two_shares
        clean = two_shares()
        damaged = deepcopy(clean)
        damaged['rows'][14]['cells'][3]['expected_text'] = '18O.00'
        before = assess_statement_reading([self.table(damaged)])
        after = assess_statement_reading([self.table(clean)])
        self.assertEqual(before['unreadable'], 1)
        self.assertEqual(after['unreadable'], 0)
        self.assertTrue(prefer_image_reading(before, after))
        # A complete but inconsistent balance remains for reconciliation;
        # arithmetic is not a reason to substitute another reading.
        damaged['rows'][14]['cells'][3]['expected_text'] = '181.00'
        self.assertEqual(assess_statement_reading([self.table(damaged)])['unreadable'], 0)
        self.assertFalse(prefer_image_reading(before, {**after, 'payments': after['payments'] - 1}))

    def test_readable_zero_interest_keeps_its_physical_row_without_becoming_a_payment(self):
        from services.financial.statement_reading_quality import assess_statement_reading, prefer_image_reading
        clean = source()
        damaged = deepcopy(clean)
        damaged['rows'][16]['cells'][-1]['expected_text'] = 'O.00'
        before = assess_statement_reading([self.table(damaged)])
        after = assess_statement_reading([self.table(clean)])
        self.assertEqual(before['payments'], after['payments'] + 1)
        self.assertEqual(before['payment_rows'], after['payment_rows'])
        self.assertTrue(prefer_image_reading(before, after))
        clean['rows'].pop(9)
        lost = assess_statement_reading([self.table(clean)])
        self.assertFalse(prefer_image_reading(before, lost))

    def test_reading_cannot_trade_a_readable_amount_for_several_better_balances(self):
        from services.financial.statement_reading_quality import prefer_image_reading
        before = dict(identity=['synthetic'], payments=4, balances=2, unreadable=3,
            missing_fields=dict(amount_minor=0, balance=3))
        after = dict(identity=['synthetic'], payments=4, balances=2, unreadable=1,
            missing_fields=dict(amount_minor=1, balance=0))
        self.assertFalse(prefer_image_reading(before, after))
