"""Source-proven quiet periods on Mexican statements: printed zero totals.

Synthetic geometry only (the reader fixtures of each family); no client data.
A section is admitted without a person only when its own printed deposit and
withdrawal totals read zero and its opening and closing balances are equal,
with no line that could be an unread payment. Everything else stays held.
"""
from copy import deepcopy
from unittest import TestCase

from services.financial.statement_admission import assess_admission
from services.financial.statement_currency import currencies_by_statement
from services.financial.statement_import import StatementImportRequest
from services.financial.statement_import_kapital import kapital_catalog, propose_kapital_statement, kapital_no_activity_evidence
from services.financial.statement_import_monex import monex_catalog, propose_monex_statement, monex_no_activity_evidence
from services.financial.statement_import_santander import santander_catalog, propose_santander_statement, santander_no_activity_evidence
from services.financial.statement_import_scotiabank import scotiabank_catalog, propose_scotiabank_statement, scotiabank_no_activity_evidence
from tests import test_financial_statement_import_kapital as kapital
from tests import test_financial_statement_import_monex as monex
from tests import test_financial_statement_import_santander as santander
from tests import test_financial_statement_import_scotiabank as scotiabank


def santander_quiet(sources):
    """The fixture's Dinero Creciente (investment) section has no movements."""
    choice = next(c for c in santander_catalog(sources)[0] if c['account_reference'] == '66-00001234-0')
    rows = propose_santander_statement(sources, 'MXN', choice)['rows']
    return choice, rows, santander_no_activity_evidence(sources, choice, rows, 'MXN')


def kapital_quiet(sources, currency='USD'):
    choice = next(c for c in currencies_by_statement(kapital_catalog(sources)[0], sources) if c['currency'] == 'USD')
    rows = propose_kapital_statement(sources, currency, choice)['rows']
    return choice, rows, kapital_no_activity_evidence(sources, choice, rows, currency)


def monex_quiet(sources, index=0, choice=None):
    choice = choice or currencies_by_statement(monex_catalog(sources)[0], sources)[index]
    rows = propose_monex_statement(sources, choice['currency'], choice)['rows']
    return choice, rows, monex_no_activity_evidence(sources, choice, rows, choice['currency'])


def scotiabank_quiet(sources, currency='MXN', choice=None):
    choice = choice or scotiabank_catalog(sources)[0][0]
    rows = propose_scotiabank_statement(sources, currency, choice)['rows']
    return choice, rows, scotiabank_no_activity_evidence(sources, choice, rows, currency)


def admission(choice, rows, evidence, currency='MXN', edit=None):
    proposal = dict(rows=rows, revision='a' * 64, metadata={'balance_convention': 'asset_balance'},
                    no_activity_evidence=evidence)
    raw = dict(expected_revision='a' * 64, currency=currency, account_number='EXAMPLE123', holder='EXAMPLE SERVICES',
        institution='Example bank', period_start=choice['period_start'], period_end=choice['period_end'],
        rows=[dict(id=r['id'], excluded=r['excluded'], description=r['fields'].get('description', ''),
                   date=r['fields'].get('date', ''), direction=r['fields'].get('direction'),
                   amount_minor=r['fields'].get('amount_minor') or '0', balance_minor=r['fields'].get('balance'))
              for r in rows])
    if edit:
        edit(raw)
    return assess_admission(proposal, StatementImportRequest.model_validate(raw))


class SantanderNoActivityTests(TestCase):
    def test_zero_total_line_and_equal_balances_prove_the_section_quiet(self):
        sources = santander.statement(); before = deepcopy(sources)
        choice, rows, evidence = santander_quiet(sources)
        self.assertTrue(evidence['verified'], evidence)
        self.assertEqual((evidence['basis'], evidence['family'], evidence['balance_minor'], evidence['currency']),
                         ('printed_zero_totals', 'santander-mexico', '0', 'MXN'))
        self.assertEqual(len(evidence['zero_total_row_ids']), 2)
        self.assertTrue(any('TOTAL' in c['text'] for c in evidence['cited']))
        result = admission(choice, rows, evidence)
        self.assertTrue(result['can_import'], result['blockers'])
        self.assertEqual((result['status'], result['no_activity_basis']), ('confirmed_no_activity', 'printed_zero_totals'))
        self.assertEqual(sources, before)

    def test_merged_ocr_columns_still_prove_quiet_section(self):
        self.assertTrue(santander_quiet(santander.statement(merged=True))[2]['verified'])

    def test_section_with_payments_is_not_a_quiet_question(self):
        sources = santander.statement()
        choice = next(c for c in santander_catalog(sources)[0] if c['account_reference'] == '65-00001234-0')
        rows = propose_santander_statement(sources, 'MXN', choice)['rows']
        self.assertIsNone(santander_no_activity_evidence(sources, choice, rows, 'MXN'))

    def test_nonzero_total_unequal_balances_or_missing_total_stay_held(self):
        cases = []
        s = santander.statement(); s[0]['rows'][16]['cells'][1]['expected_text'] = '5.00'; cases.append((s, 'totals_not_zero'))
        s = santander.statement(); s[0]['rows'][16]['cells'][2]['expected_text'] = '5.00'; cases.append((s, 'totals_not_zero'))
        s = santander.statement(); s[0]['rows'][17]['cells'][1]['expected_text'] = '$1.00'; cases.append((s, 'endpoints_differ'))
        s = santander.statement(); s[0]['rows'][16]['cells'][1]['expected_text'] = '0.0O'; cases.append((s, 'controls_missing'))
        s = santander.statement(); del s[0]['rows'][16]; cases.append((s, 'controls_missing'))
        for i, (s, reason) in enumerate(cases):
            with self.subTest(i=i):
                for n, row in enumerate(s[0]['rows']):
                    row['row_index'] = n
                choice, rows, evidence = santander_quiet(s)
                self.assertFalse(evidence['verified'])
                self.assertEqual(evidence['reason'], reason)
                result = admission(choice, rows, evidence)
                self.assertFalse(result['can_import'])
                self.assertTrue(any(b['kind'] == 'no_activity' for b in result['blockers']))

    def test_text_between_heading_and_total_or_a_dated_line_stays_held(self):
        s = santander.statement()
        s[0]['rows'].insert(16, s[0]['rows'][16] | dict(cells=[dict(s[0]['rows'][16]['cells'][0], expected_text='INTERES DEL MES',
            locator=dict(s[0]['rows'][16]['cells'][0]['locator'], rect=[120000, 400000, 200000, 406000]))]))
        for n, row in enumerate(s[0]['rows']):
            row['row_index'] = n
        self.assertEqual(santander_quiet(s)[2]['reason'], 'rows_between_heading_and_total')
        s = santander.statement()
        s[0]['rows'][14]['cells'][0]['expected_text'] = 'SALDO FINAL DEL PERIODO ANTERIOR AL 31-AGO-2024:'
        self.assertEqual(santander_quiet(s)[2]['reason'], 'dated_line')

    def test_review_currency_must_match_the_printed_currency(self):
        sources = santander.statement()
        choice = next(c for c in santander_catalog(sources)[0] if c['account_reference'] == '66-00001234-0')
        rows = propose_santander_statement(sources, 'USD', choice)['rows']
        self.assertEqual(santander_no_activity_evidence(sources, choice, rows, 'USD')['reason'], 'currency_differs')

    def test_edits_to_cited_values_move_the_basis_to_the_investigator(self):
        choice, rows, evidence = santander_quiet(santander.statement())
        total_id = evidence['zero_total_row_ids'][0]

        def total(raw):
            next(r for r in raw['rows'] if r['id'] == total_id)['balance_minor'] = '100'

        def closing(raw):
            next(r for r in raw['rows'] if r['id'] == evidence['closing_row_id'])['balance_minor'] = '5'

        def period(raw):
            raw['period_end'] = '2024-09-29'
        for edit, currency in ((total, 'MXN'), (closing, 'MXN'), (period, 'MXN'), (None, 'USD')):
            with self.subTest(edit=edit, currency=currency):
                result = admission(choice, rows, evidence, currency=currency, edit=edit)
                self.assertFalse(result['can_import'])
                self.assertTrue(any(b['kind'] == 'no_activity' for b in result['blockers']))


class KapitalNoActivityTests(TestCase):
    def test_zero_depositos_and_retiros_with_equal_saldos_prove_the_product_quiet(self):
        sources = kapital.statement(); before = deepcopy(sources)
        choice, rows, evidence = kapital_quiet(sources)
        self.assertTrue(evidence['verified'], evidence)
        self.assertEqual((evidence['family'], evidence['currency'], evidence['balance_minor']), ('kapital-mexico', 'USD', '0'))
        result = admission(choice, rows, evidence, currency='USD')
        self.assertTrue(result['can_import'], result['blockers'])
        self.assertEqual(result['no_activity_basis'], 'printed_zero_totals')
        self.assertEqual(sources, before)

    def test_peso_product_with_movements_is_not_a_quiet_question(self):
        sources = kapital.statement()
        choice = currencies_by_statement(kapital_catalog(sources)[0], sources)[0]
        rows = propose_kapital_statement(sources, 'MXN', choice)['rows']
        self.assertIsNone(kapital_no_activity_evidence(sources, choice, rows, 'MXN'))

    def test_nonzero_total_unequal_saldos_or_wrong_currency_stay_held(self):
        s = kapital.statement(); s[1]['rows'][8]['cells'][1]['expected_text'] = '0.01 USD'
        self.assertEqual(kapital_quiet(s)[2]['reason'], 'totals_not_zero')
        s = kapital.statement(); s[1]['rows'][10]['cells'][1]['expected_text'] = '0.10'
        self.assertEqual(kapital_quiet(s)[2]['reason'], 'endpoints_differ')
        # A peso review of the printed USD amounts: each control has an issue.
        self.assertEqual(kapital_quiet(kapital.statement(), currency='MXN')[2]['reason'], 'control_unreadable')

    def test_movement_heading_or_payment_line_in_the_product_stays_held(self):
        s = kapital.statement()
        s[1]['rows'].append(kapital.source(2, [[(245000, 600000, 46000, 'CONCEPTO'), (400000, 600000, 46000, 'FOLIO')]])['rows'][0])
        s[1]['rows'][-1]['row_index'] = len(s[1]['rows']) - 1
        self.assertEqual(kapital_quiet(s)[2]['reason'], 'movement_table')
        s = kapital.statement()
        s[1]['rows'].append(kapital.source(2, [[(370000, 600000, 23000, 'Total')]])['rows'][0])
        s[1]['rows'][-1]['row_index'] = len(s[1]['rows']) - 1
        self.assertEqual(kapital_quiet(s)[2]['reason'], 'payment_line')

    def test_the_tables_own_zero_total_line_is_a_printed_control_not_a_payment(self):
        _, rows, _ = kapital_quiet(kapital.statement())
        closing = int(next(r for r in rows if r['fields'].get('description') == 'Closing Balance')['fields']['balance'])
        printed = f'{closing // 100:,}.{closing % 100:02d} USD'
        for cells, reason in ((['Total', '0.00 USD', '0.00 USD', printed], 'printed_zero_totals'),
                              (['Total', '0.00 USD', '5.00 USD', printed], 'payment_line'),
                              (['Total', '0.00 USD', '0.00 USD', '999.99 USD'], 'payment_line'),
                              (['Total', '0.00 USD', '0.00 USD'], 'payment_line')):
            s = kapital.statement()
            line = [(370000 + 90000 * i, 600000, 40000, text) for i, text in enumerate(cells)]
            s[1]['rows'].append(kapital.source(2, [line])['rows'][0])
            s[1]['rows'][-1]['row_index'] = len(s[1]['rows']) - 1
            with self.subTest(cells=cells):
                self.assertEqual(kapital_quiet(s)[2]['reason'], reason)


class MonexNoActivityTests(TestCase):
    def test_each_currency_summary_with_zero_totals_proves_its_section_quiet(self):
        sources = monex.statement(); before = deepcopy(sources)
        for index, (currency, balance) in enumerate((('MXN', '32145'), ('EUR', '79'))):
            with self.subTest(currency=currency):
                choice, rows, evidence = monex_quiet(sources, index)
                self.assertTrue(evidence['verified'], evidence)
                self.assertEqual((evidence['currency'], evidence['balance_minor']), (currency, balance))
                self.assertEqual({c['page_number'] for c in evidence['cited']}, {choice['summary_page']})
                result = admission(choice, rows, evidence, currency=currency)
                self.assertTrue(result['can_import'], result['blockers'])
                self.assertEqual(result['no_activity_basis'], 'printed_zero_totals')
        self.assertEqual(sources, before)

    def test_nonzero_total_or_unequal_endpoints_stay_held(self):
        choice = currencies_by_statement(monex_catalog(monex.statement())[0], monex.statement())[0]

        def changed(value, *labels):
            s = monex.statement()
            for label in labels:
                next(r for r in s[1]['rows'] if any(c['expected_text'] == label for c in r['cells']))['cells'][-1]['expected_text'] = value
            return s
        self.assertEqual(monex_quiet(changed('12.00', '+ Total abonos:'), choice=choice)[2]['reason'], 'totals_not_zero')
        self.assertEqual(monex_quiet(changed('310.45', 'Saldo vista:', 'Saldo total:'), choice=choice)[2]['reason'], 'endpoints_differ')
        # A total balance that differs from the available balance is itself held for a person.
        self.assertIsNone(monex_quiet(changed('310.45', 'Saldo vista:'), choice=choice)[2])

    def test_a_dated_line_with_money_outside_a_movement_table_refuses_the_contract(self):
        s = monex.statement()
        s[1]['rows'].append(monex.source(2, [[(20000, 400000, 60000, '15/May'), (90000, 400000, 200000, 'TRASPASO'),
                                              (340000, 400000, 30000, '5.00'), (420000, 400000, 30000, '0.00')]])['rows'][0])
        s[1]['rows'][-1]['row_index'] = len(s[1]['rows']) - 1
        self.assertEqual(monex_catalog(s), ([], set()))

    def test_a_section_with_movements_is_not_a_quiet_question(self):
        sources = monex.landscape()
        peso = currencies_by_statement(monex_catalog(sources)[0], sources)[0]
        self.assertIsNone(monex_quiet(sources, choice=peso)[2])


class ScotiabankNoActivityTests(TestCase):
    def test_five_zero_chart_amounts_and_equal_saldos_prove_the_period_quiet(self):
        sources = scotiabank.statement(); before = deepcopy(sources)
        choice, rows, evidence = scotiabank_quiet(sources)
        self.assertTrue(evidence['verified'], evidence)
        self.assertEqual((evidence['family'], evidence['currency'], evidence['zero_total_row_ids']),
                         ('scotiabank-mexico', 'MXN', []))
        self.assertEqual(sum(c['text'] == '$0.00' and 'locator' in c for c in evidence['cited']), 5)
        result = admission(choice, rows, evidence)
        self.assertTrue(result['can_import'], result['blockers'])
        self.assertEqual(result['no_activity_basis'], 'printed_zero_totals')
        self.assertEqual(sources, before)

    def test_nonzero_or_unreadable_chart_amount_stays_held(self):
        # The reader itself refuses such a page; the proof re-reads the chart
        # independently, so it is checked against the changed page directly.
        choice, rows, _ = scotiabank_quiet(scotiabank.statement())
        for value in ('$5.00', '$O.00', ''):
            with self.subTest(value=value):
                s = scotiabank.statement(); s[0]['rows'][16]['cells'][3]['expected_text'] = value
                evidence = scotiabank_no_activity_evidence(s, choice, rows, 'MXN')
                self.assertFalse(evidence['verified'])
                self.assertEqual(evidence['reason'], 'chart_unreadable')
                self.assertFalse(admission(choice, rows, evidence)['can_import'])

    def test_review_currency_must_be_the_printed_peso(self):
        self.assertEqual(scotiabank_quiet(scotiabank.statement(), currency='USD')[2]['reason'], 'currency_differs')

    def test_edited_opening_balance_requires_the_investigator(self):
        choice, rows, evidence = scotiabank_quiet(scotiabank.statement())

        def opening(raw):
            next(r for r in raw['rows'] if r['id'] == evidence['opening_row_id'])['balance_minor'] = '1'
        self.assertFalse(admission(choice, rows, evidence, edit=opening)['can_import'])


class AndrewsBasisUnchangedTests(TestCase):
    def test_reader_proof_without_a_basis_keeps_source_verified(self):
        choice, rows, evidence = santander_quiet(santander.statement())
        evidence = {k: v for k, v in evidence.items() if k not in ('basis', 'currency', 'zero_total_row_ids')}
        self.assertEqual(admission(choice, rows, evidence)['no_activity_basis'], 'source_verified')
