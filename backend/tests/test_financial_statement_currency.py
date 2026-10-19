from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from uuid import uuid4

from services.financial.statement_currency import detect_statement_currency, currencies_by_statement
from services.financial.statement_import import read_statement_import
from services.financial.statement_import_proposal import exact_amount
from services.financial.statement_review_checks import add_period_checks
from tests.test_financial_statement_import_proposal import source


class CurrencyDetectionTests(TestCase):
    def test_national_currency_requires_account_label_and_mexican_issuer_context(self):
        for label in ('MN', 'M.N.', 'M. N.', 'MONEDA NACIONAL'):
            rows = [['SERVICIO EMPRESARIAL FX KAPITAL 194-992-001-6'], ['Moneda', label],
                    ['TOTAL DOLARES'], ['USD 5000.01']]
            self.assertEqual(detect_statement_currency([source(rows)]), 'MXN')
        self.assertEqual(detect_statement_currency([source([['Moneda MN'], ['$5000.01']])]), '')
        self.assertEqual(detect_statement_currency([source([['BANCO KAPITAL'], ['Moneda MN'], ['Moneda USD']])]), '')

    def test_printed_currency_codes_and_unambiguous_symbols(self):
        for cells, expected in [(['Currency:', 'CAD'], 'CAD'), (['Account currency: GBP'], 'GBP'),
                                (['USD 21.19'], 'USD'), (['21.19 EUR'], 'EUR'),
                                (['€21.19'], 'EUR'), (['£21.19'], 'GBP'), (['KWD 1.234'], 'KWD')]:
            with self.subTest(cells=cells):
                self.assertEqual(detect_statement_currency([source([cells])]), expected)

    def test_dollar_and_yen_symbols_need_context(self):
        for value in ('$21.19', '¥219', '21.19'):
            self.assertEqual(detect_statement_currency([source([[value]])]), '')
        self.assertEqual(detect_statement_currency([source([['- $246.92'], ['$28.78'], ['$21.19']])],
                         layout_id='capital-one-card'), 'USD')
        self.assertEqual(detect_statement_currency([source([['CA$21.19'], ['$28.78']])]), 'CAD')

    def test_conflicting_markers_and_account_labels_are_not_guessed(self):
        for rows in ([['USD 21.19'], ['EUR 28.78']], [['€21.19'], ['$28.78']],
                     [['Currency: USD'], ['Currency: CAD']]):
            self.assertEqual(detect_statement_currency([source(rows)]), '')

    def test_foreign_purchase_and_advertisement_text_do_not_set_account_currency(self):
        self.assertEqual(detect_statement_currency([source([['Currency: CAD'],
            ['Original purchase EUR 21.19'], ['$28.78']])]), 'CAD')
        self.assertEqual(detect_statement_currency([source([['Try our USD account'],
            ['EUR currency conversion information'], ['$28.78']])]), '')

    def test_periods_detect_and_check_their_own_currency(self):
        from tests.test_financial_statement_import_card import card_source
        from services.financial.statement_layout_context import statement_layout_context
        first, second = card_source(), card_source()
        second['page_number'] = 2
        second['rows'].append(dict(row_index=99, cells=[dict(column_index=0, expected_text='Currency: CAD', locator={})]))
        second['layout_context'] = statement_layout_context(second['rows'])
        choices = [dict(id=str(page), layout_id='capital-one-card', account_reference='****1234',
            period_start='2020-05-12', period_end='2020-06-11', sources=[dict(page_number=page, table_index=0)]) for page in (1, 2)]
        originals = deepcopy([first, second])
        result = currencies_by_statement(choices, [first, second])
        self.assertEqual([choice['currency'] for choice in result], ['USD', 'CAD'])
        checked = add_period_checks(result, [first, second], None)
        self.assertEqual([c['checks']['flagged_rows'] for c in checked], [0, 0])
        self.assertEqual([first, second], originals)

    def test_currency_conflict_explains_the_readable_value_instead_of_generic_amount_warning(self):
        for amount in ('$21.19', '$28.78', '$246.92'):
            with self.assertRaisesRegex(ValueError, 'review uses EUR. Change the statement currency'):
                exact_amount(amount, 'EUR')
        self.assertEqual(exact_amount('$21.19', 'USD'), '2119')
        with self.assertRaisesRegex(ValueError, 'could not read'):
            exact_amount('$2?.19', 'USD')


class AutomaticCurrencyImportTests(TestCase):
    def setUp(self):
        from tests.test_financial_statement_import import StatementImportTests
        self.fixture = StatementImportTests('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.fixture.setUp()
        self.fixture.card_balance_request()

    def tearDown(self):
        self.fixture.tearDown()

    def test_individual_review_detects_usd_and_imports_the_same_exact_amounts(self):
        from services.financial.import_batches import initial_request
        from services.financial.statement_import import confirm_statement_import
        f = self.fixture
        proposal = f.preview()
        self.assertEqual(proposal['currency'], 'USD')
        self.assertEqual(proposal['detected_currency'], 'USD')
        payments = [r for r in proposal['rows'] if not r['excluded']]
        self.assertEqual([r['fields']['amount_minor'] for r in payments], ['18000', '6162', '5616'])
        self.assertTrue(all(not r['issues'] for r in payments))
        request = initial_request(proposal)
        receipt = confirm_statement_import(session_factory=f.SessionLocal, case_id=f.case.id,
            evidence_file_id=f.file.id, request=request, actor=f.actor, resolve_path=Path)
        self.assertEqual(receipt['transaction_count'], 3)
        # Confirmation explicitly sends the detected currency. Its proposal
        # must have the same revision as the automatic read.
        repeated = confirm_statement_import(session_factory=f.SessionLocal, case_id=f.case.id,
            evidence_file_id=f.file.id, request=request, actor=f.actor, resolve_path=Path)
        self.assertFalse(repeated['created'])

    def test_existing_currency_choice_can_be_corrected_without_reextracting_source(self):
        f = self.fixture
        with f.SessionLocal() as db:
            wrong = read_statement_import(db, case_id=f.case.id, evidence_file_id=f.file.id, currency='EUR')
            corrected = read_statement_import(db, case_id=f.case.id, evidence_file_id=f.file.id)
        self.assertEqual(wrong['currency'], 'EUR')
        self.assertEqual(wrong['detected_currency'], 'USD')
        payment = next(r for r in wrong['rows'] if r['fields'].get('description') == 'PAYMENT')
        self.assertNotIn('amount_minor', payment['fields'])
        self.assertIn('review uses EUR', payment['issues'][0])
        fixed = next(r for r in corrected['rows'] if r['id'] == payment['id'])
        self.assertEqual(fixed['fields']['amount_minor'], '18000')
        self.assertEqual(fixed['fields']['direction'], 'credit')
        self.assertEqual(fixed['source_cells'], payment['source_cells'])

    def test_bulk_review_uses_each_period_currency_in_a_mixed_document(self):
        from postgres.models.evidence import EvidenceTableGeometry
        from postgres.models.financial_import_batches import FinancialImportBatch, FinancialImportBatchItem
        from services.financial.import_batches import create_batch, prepare_reviews
        from sqlalchemy import select
        f = self.fixture
        geometry = f.db.get(EvidenceTableGeometry, (f.file.id, 1))
        payload = deepcopy(geometry.payload)
        for table in payload:
            table['table']['page'] = 2
            table['table']['table']['page'] = 2
            for value in table['table']['values']:
                value['locator']['page'] = 2
                value['text'] = value['text'].replace('1234', '9999')
        cell = deepcopy(payload[0]['table']['values'][0])
        cell.update(row=99, column=0, text='Currency: CAD')
        from tests.test_financial_pdf_geometry_candidates import rectangle
        cell['locator'] = {**rectangle(740, x=25, width=100, height=10), 'page': 2}
        payload[0]['table']['values'].append(cell)
        f.db.add(EvidenceTableGeometry(evidence_file_id=f.file.id, page_number=2,
            engine_job_id=geometry.engine_job_id, payload=payload))
        f.file.status = 'processed'
        f.db.commit()
        self.assertEqual({c['currency'] for c in f.preview()['statement_choices']}, {'USD', 'CAD'})
        with f.SessionLocal() as db:
            batch_id = create_batch(db, case_id=f.case.id, request_id=uuid4(),
                file_ids=[f.file.id], folder_ids=[], actor=f.actor)
            batch = db.get(FinancialImportBatch, batch_id)
            prepare_reviews(db, batch, batch.files[0])
            items = list(db.scalars(select(FinancialImportBatchItem).where(FinancialImportBatchItem.batch_id == batch_id)))
            self.assertEqual(len(items), 2)
            self.assertEqual({i.summary['currency'] for i in items}, {'USD', 'CAD'})
            self.assertEqual([i.summary['transaction_count'] for i in items], [3, 3])
