"""General statement engine: invented layouts, one fixture per knowledge-file rule.

Every fixture is synthetic (no real statement text). Layouts deliberately
differ from every family reader: English and Spanish, signed and split amount
columns, with and without running balances, multi-page, multi-currency, and
adversarial near-ties that must hold.
"""
import os
import unittest
from unittest import mock

from services.financial import statement_engine as E
from services.financial.statement_engine import read_statements

WIDTH, HEIGHT = 612000, 792000


def cell(text, x0, x1, y, column):
    return dict(column_index=column, expected_text=text,
                locator=dict(page=1, rect=[x0, y, x1, y + 9000], page_size=[WIDTH, HEIGHT]))


def page(number, lines, table=0):
    """lines: [[(text, x0, x1), ...], ...] one visual line each, top to bottom."""
    rows = []
    for index, line in enumerate(lines):
        y = 40000 + index * 12000
        rows.append(dict(row_index=index, cells=[cell(t, x0, x1, y, c) for c, (t, x0, x1) in enumerate(line)]))
        for c in rows[-1]['cells']:
            c['locator']['page'] = number
    return dict(case_id='c', evidence_file_id='f', page_number=number, table_index=table,
                source_revision='r%d' % number, table_source='text_alignment', rows=rows)


def mx_statement(movements, *, opening='1,000.00', closing=None, deposits=None, withdrawals=None, running=True,
                 period='DEL 01/03/2024 AL 31/03/2024', currency_line=('MONEDA', 'PESOS'), page_count=None):
    """An invented Spanish layout: summary block, then FECHA | CONCEPTO | ABONOS | CARGOS | SALDO."""
    lines = [
        [('BANCO EJEMPLO DEL NORTE, S.A., INSTITUCION DE BANCA MULTIPLE', 20000, 400000)],
        [('EMPRESA DE PRUEBA SA DE CV', 20000, 200000), ('PERIODO', 330000, 380000), (period, 390000, 590000)],
        [('CALLE FALSA 123', 20000, 150000), ('NO. DE CUENTA', 330000, 400000), ('0012345678', 410000, 500000)],
        [('COL CENTRO', 20000, 120000), currency_line and (currency_line[0], 330000, 380000), currency_line and (currency_line[1], 390000, 450000)],
        [('CIUDAD DE MEXICO C.P. 06000', 20000, 220000)],
        [('SALDO ANTERIOR', 330000, 430000), (opening, 500000, 560000)],
    ]
    lines = [[c for c in line if c] for line in lines]
    if deposits is not None:
        lines.append([('DEPOSITOS', 330000, 400000), (deposits, 500000, 560000)])
    if withdrawals is not None:
        lines.append([('RETIROS', 330000, 400000), (withdrawals, 500000, 560000)])
    if closing is not None:
        lines.append([('SALDO FINAL', 330000, 400000), (closing, 500000, 560000)])
    lines.append([('FECHA', 20000, 60000), ('CONCEPTO', 80000, 160000), ('ABONOS', 330000, 380000),
                  ('CARGOS', 410000, 460000), ('SALDO', 520000, 560000)])
    for day, text, credit, debit, balance in movements:
        line = [(day, 20000, 60000), (text, 80000, 300000)]
        if credit:
            line.append((credit, 380000 - 6000 * len(credit), 380000))
        if debit:
            line.append((debit, 460000 - 6000 * len(debit), 460000))
        if balance and running:
            line.append((balance, 560000 - 6000 * len(balance), 560000))
        lines.append(line)
    if page_count:
        lines.append([('PAGINA 1 DE %d' % page_count, 500000, 590000)])
    return [page(1, lines)]


MOVES = [('05/MAR', 'TRANSFERENCIA RECIBIDA', '500.00', None, '1,500.00'),
         ('10/MAR', 'PAGO DE SERVICIO', None, '200.00', '1,300.00'),
         ('20/MAR', 'COMISION', None, '50.00', '1,250.00')]


def card_statement(lines_extra=(), interest=None, new_balance='$140.00'):
    """An invented English card layout: summary components, signed Amount column, US address."""
    lines = [
        [('Example Card Services Bank, N.A.', 20000, 300000)],
        [('JANE Q SAMPLE', 20000, 150000), ('Statement Period 02/16/24 - 03/15/24', 330000, 590000)],
        [('100 MAIN ST APT 1', 20000, 150000), ('Account number ending in 4321', 330000, 590000)],
        [('SPRINGFIELD, IL 62701', 20000, 170000)],
        [('Previous Balance', 330000, 430000), ('$100.00', 520000, 560000)],
        [('Payments', 330000, 430000), ('-$50.00', 520000, 560000)],
        [('Purchases', 330000, 430000), ('+$90.00', 520000, 560000)],
        [('Interest Charged', 330000, 430000), ('+$%s' % (interest or '0.00'), 520000, 560000)],
        [('New Balance', 330000, 430000), (new_balance, 520000, 560000)],
        [('Minimum Payment Due', 330000, 450000), ('$25.00', 520000, 560000)],
        [('Date', 20000, 50000), ('Description', 80000, 160000), ('Amount', 500000, 560000)],
        [('Feb 20', 20000, 60000), ('ONLINE PAYMENT THANK YOU', 80000, 300000), ('-$50.00', 510000, 560000)],
        [('Mar 2', 20000, 60000), ('GROCERY STORE 12', 80000, 300000), ('$60.00', 516000, 560000)],
        [('Mar 9', 20000, 60000), ('HARDWARE SHOP', 80000, 300000), ('$30.00', 516000, 560000)],
        *lines_extra,
    ]
    if interest:
        lines.append([('Interest Charge on Purchases', 20000, 200000), ('$' + interest, 516000, 560000)])
    return [page(1, lines)]


class EngineReadingTests(unittest.TestCase):
    def one(self, sources):
        statements = read_statements(sources)
        self.assertEqual(len(statements), 1, [s['engine'] for s in statements])
        return statements[0]

    def movements(self, statement):
        return [(r['fields'].get('date'), r['fields']['direction'], r['fields']['amount_minor'], r['fields'].get('balance'))
                for r in statement['_rows'] if not r['excluded']]

    def test_split_columns_with_running_balance_prove_and_read_every_field(self):
        st = self.one(mx_statement(MOVES, closing='1,250.00'))
        self.assertTrue(st['engine']['proved'], st['engine'])
        self.assertEqual(st['engine']['basis'], 'running_balance')
        self.assertEqual((st['period_start'], st['period_end'], st['currency']), ('2024-03-01', '2024-03-31', 'MXN'))
        self.assertEqual(st['account_reference'], '0012345678')
        self.assertEqual(st['holder'], 'EMPRESA DE PRUEBA SA DE CV')
        self.assertEqual(st['institution'], 'BANCO EJEMPLO DEL NORTE')
        self.assertEqual(self.movements(st), [('2024-03-05', 'credit', '50000', '150000'),
                                              ('2024-03-10', 'debit', '20000', '130000'),
                                              ('2024-03-20', 'debit', '5000', '125000')])
        balances = {r['fields']['description']: r['fields']['balance'] for r in st['_rows'] if r['kind'] == 'balance'}
        self.assertEqual(balances, {'Opening Balance': '100000', 'Closing Balance': '125000'})

    def test_closing_that_does_not_reconcile_is_held_with_a_named_reason(self):
        st = self.one(mx_statement(MOVES, closing='1,260.00'))
        self.assertFalse(st['engine']['proved'])
        self.assertEqual(st['engine']['reason'], 'not_reconciled')
        hold = [r for r in st['_rows'] if r.get('engine_hold')]
        self.assertEqual(len(hold), 1)
        self.assertFalse(hold[0]['excluded'])
        self.assertTrue(hold[0]['issues'])

    def test_printed_totals_prove_a_table_without_running_balance(self):
        st = self.one(mx_statement(MOVES, closing='1,250.00', deposits='500.00', withdrawals='250.00', running=False))
        self.assertTrue(st['engine']['proved'], st['engine'])
        self.assertEqual(st['engine']['basis'], 'printed_totals')

    def test_a_printed_total_that_differs_holds(self):
        st = self.one(mx_statement(MOVES, closing='1,250.00', deposits='500.00', withdrawals='260.00', running=False))
        self.assertFalse(st['engine']['proved'])
        self.assertEqual(st['engine']['reason'], 'printed_total_differs')

    def test_balances_alone_without_chain_or_totals_hold(self):
        st = self.one(mx_statement(MOVES, closing='1,250.00', running=False))
        self.assertFalse(st['engine']['proved'])
        self.assertEqual(st['engine']['reason'], 'no_independent_control')

    def test_symmetric_columns_without_headings_are_a_near_tie_and_hold(self):
        # Equal in and out with no headings: credit/debit could be either column.
        moves = [('05/MAR', 'MOVIMIENTO A', '100.00', None, None), ('06/MAR', 'MOVIMIENTO B', None, '100.00', None)]
        sources = mx_statement(moves, closing='1,000.00', deposits='100.00', withdrawals='100.00', running=False)
        for row in sources[0]['rows']:
            for c in row['cells']:
                if c['expected_text'] in ('ABONOS', 'CARGOS'):
                    c['expected_text'] = 'IMPORTE A' if c['expected_text'] == 'ABONOS' else 'IMPORTE B'
        st = self.one(sources)
        self.assertFalse(st['engine']['proved'])
        self.assertIn(st['engine']['reason'], ('two_readings', 'no_independent_control', 'not_reconciled'))

    def test_card_convention_signed_amounts_and_summary_components(self):
        st = self.one(card_statement())
        self.assertTrue(st['engine']['proved'], st['engine'])
        self.assertEqual(st['balance_convention'], 'liability_owed')
        self.assertEqual(st['currency'], 'USD')
        self.assertEqual(st['currency_source'], 'dollar_us_address')
        self.assertEqual(st['account_reference'], '****4321')
        self.assertEqual(self.movements(st), [('2024-02-20', 'credit', '5000', None), ('2024-03-02', 'debit', '6000', None),
                                              ('2024-03-09', 'debit', '3000', None)])

    def test_card_interest_without_a_date_is_ordered_at_period_end_only(self):
        st = self.one(card_statement(interest='1.25', new_balance='$141.25'))
        self.assertTrue(st['engine']['proved'], st['engine'])
        undated = [r for r in st['_rows'] if r['fields'].get('date_basis') == 'statement_end_ordering_only']
        self.assertEqual(len(undated), 1)
        self.assertNotIn('date', undated[0]['fields'])
        self.assertEqual(undated[0]['fields']['amount_minor'], '125')

    def test_card_component_sum_that_differs_holds(self):
        sources = card_statement()
        for row in sources[0]['rows']:
            if row['cells'][0]['expected_text'] == 'Purchases':
                row['cells'][1]['expected_text'] = '+$95.00'
        st = self.one(sources)
        self.assertFalse(st['engine']['proved'])

    def test_continuation_lines_join_the_description(self):
        sources = mx_statement(MOVES, closing='1,250.00')
        rows = sources[0]['rows']
        y = rows[-2]['cells'][0]['locator']['rect'][1] + 9500
        rows.insert(len(rows) - 1, dict(row_index=99, cells=[dict(column_index=0, expected_text='REF 0000123 CONCEPTO EXTRA',
            locator=dict(page=1, rect=[80000, y, 300000, y + 9000], page_size=[WIDTH, HEIGHT]))]))
        rows.sort(key=lambda r: r['cells'][0]['locator']['rect'][1])
        st = self.one(sources)
        self.assertTrue(st['engine']['proved'], st['engine'])
        second = [r for r in st['_rows'] if not r['excluded']][1]
        self.assertIn('REF 0000123 CONCEPTO EXTRA', second['fields']['description'])
        self.assertEqual(len(second['continuation_sources']), 1)

    def test_zero_padded_references_are_not_amounts(self):
        self.assertIsNone(E.money('0020215057.44', 'dot'))
        self.assertEqual(E.money('1,234.56', 'dot'), 123456)
        self.assertEqual(E.money('1.234,56', 'comma'), 123456)
        self.assertEqual(E.money('(12.50)', 'dot'), -1250)
        self.assertEqual(E.money('12.50-', 'dot'), -1250)
        self.assertEqual(E.money('12.50CR', 'dot'), -1250)
        self.assertIsNone(E.money('-12.50-', 'dot'))

    def test_whole_unit_currency_reads_printed_zero_cents_only(self):
        self.assertEqual(E.money('503,250.00', 'dot', 0), 503250)
        self.assertEqual(E.money('503,250', 'dot', 0), 503250)
        self.assertIsNone(E.money('503,250.50', 'dot', 0))

    def test_comma_decimal_document(self):
        moves = [('05/MAR', 'ENTRADA', '500,00', None, '1.500,00'), ('10/MAR', 'SALIDA', None, '200,00', '1.300,00')]
        st = self.one(mx_statement(moves, opening='1.000,00', closing='1.300,00'))
        self.assertTrue(st['engine']['proved'], st['engine'])
        self.assertEqual(self.movements(st)[0][2], '50000')

    def test_mixed_decimal_conventions_hold(self):
        # Dot thousands with a decimal comma ('1.500,00') beside comma thousands with a decimal point.
        moves = [('05/MAR', 'ENTRADA', '500,00', None, '1.500,00'), ('10/MAR', 'SALIDA', None, '200,00', '1,300.00')]
        st = self.one(mx_statement(moves, opening='1,000.00', closing='1,300.00'))
        self.assertFalse(st['engine']['proved'])
        self.assertEqual(st['engine']['reason'], 'separators_mixed')

    def test_worn_decimal_points_in_a_dot_document_are_read_by_the_dot_convention(self):
        # A scan prints some decimal points as commas; comma thousands show the convention.
        moves = [('05/MAR', 'ENTRADA', '500,00', None, '1,500.00'), ('10/MAR', 'SALIDA', None, '200.00', '1,300,00'),
                 ('12/MAR', 'COMISION', None, '50.00', '1,250.00')]
        sources = mx_statement(moves, opening='1,000.00', closing='1,250.00')
        self.assertEqual(E.separator_style(E._pages(sources)), 'dot_worn')
        st = self.one(sources)
        self.assertTrue(st['engine']['proved'], st['engine'])
        self.assertEqual([m[2:] for m in self.movements(st)], [('50000', '150000'), ('20000', '130000'), ('5000', '125000')])
        self.assertEqual(E.money('147,382,26', 'dot_worn'), 14738226)
        self.assertIsNone(E.money('147,382,26', 'dot'))

    def test_missing_printed_page_holds(self):
        sources = mx_statement(MOVES, closing='1,250.00', page_count=3)
        st = self.one(sources)
        self.assertFalse(st['engine']['proved'])
        self.assertEqual(st['engine']['reason'], 'pages_missing')

    def test_rows_dated_outside_the_period_hold(self):
        moves = [('05/ABR', 'FUERA DEL PERIODO', '500.00', None, '1,500.00')]
        st = self.one(mx_statement(moves, closing='1,500.00'))
        self.assertFalse(st['engine']['proved'])
        self.assertEqual(st['engine']['reason'], 'date_unresolved')

    def test_period_formats(self):
        from datetime import date
        self.assertEqual(E.period_ranges('PERIODO DEL 01-SEP-2025 AL 30-SEP-2025'), [(date(2025, 9, 1), date(2025, 9, 30))])
        self.assertEqual(E.period_ranges('Billing Period: 08/04/24-09/03/24'), [(date(2024, 8, 4), date(2024, 9, 3))])
        self.assertEqual(E.period_ranges('1 AL 30 DE ABRIL DE 2019'), [(date(2019, 4, 1), date(2019, 4, 30))])
        self.assertEqual(E.period_ranges('June 1, 2024 through June 30, 2024'), [(date(2024, 6, 1), date(2024, 6, 30))])
        # Ambiguous day/month with no valid alternative: only the reading that makes a period counts.
        self.assertEqual(E.period_ranges('DEL 01/06/2026 AL 30/06/2026'), [(date(2026, 6, 1), date(2026, 6, 30))])

    def test_holder_labels_on_legal_pages_are_not_the_holder(self):
        sources = mx_statement(MOVES, closing='1,250.00')
        legal = page(2, [[('Unidad de atencion. Titular: OTRA PERSONA DISTINTA', 20000, 400000)],
                         [('PAGINA 2 DE 2', 500000, 590000)]])
        sources[0]['rows'].append(dict(row_index=50, cells=[cell('PAGINA 1 DE 2', 500000, 590000, 700000, 0)]))
        st = self.one(sources + [legal])
        self.assertEqual(st['holder'], 'EMPRESA DE PRUEBA SA DE CV')
        self.assertTrue(st['engine']['proved'], st['engine'])

    def test_two_currency_sections_on_one_page_take_their_own_heading_currency(self):
        lines = [
            [('BANCO EJEMPLO DEL NORTE, S.A., INSTITUCION DE BANCA MULTIPLE', 20000, 400000)],
            [('PERIODO', 330000, 380000), ('DEL 01/03/2024 AL 31/03/2024', 390000, 590000)],
            [('RESUMEN PESO MEXICANO', 20000, 200000)],
            [('SALDO INICIAL', 330000, 430000), ('100.00', 520000, 560000)],
            [('FECHA', 20000, 60000), ('CONCEPTO', 80000, 160000), ('ABONOS', 330000, 380000), ('CARGOS', 410000, 460000), ('SALDO', 520000, 560000)],
            [('04/MAR', 20000, 60000), ('VENTA DIVISA', 80000, 300000), ('40.00', 436000, 460000), ('60.00', 536000, 560000)],
            [('SALDO FINAL', 330000, 430000), ('60.00', 520000, 560000)],
            [('RESUMEN DOLAR AMERICANO', 20000, 200000)],
            [('SALDO INICIAL', 330000, 430000), ('0.00', 530000, 560000)],
            [('FECHA', 20000, 60000), ('CONCEPTO', 80000, 160000), ('ABONOS', 330000, 380000), ('CARGOS', 410000, 460000), ('SALDO', 520000, 560000)],
            [('05/MAR', 20000, 60000), ('COMPRA DIVISA', 80000, 300000), ('10.00', 356000, 380000), ('10.00', 536000, 560000)],
            [('SALDO FINAL', 330000, 430000), ('10.00', 530000, 560000)],
        ]
        statements = read_statements([page(1, lines)])
        self.assertEqual([s['currency'] for s in statements], ['MXN', 'USD'])
        self.assertTrue(all(s['engine']['proved'] for s in statements), [s['engine'] for s in statements])
        # A section on a shared page never borrows the page's other currency.
        lines[7] = [('RESUMEN DE OTRA CUENTA', 20000, 200000)]
        statements = read_statements([page(1, lines)])
        self.assertEqual(statements[1]['currency'], '')
        self.assertEqual(statements[1]['currency_source'], 'printed_account_section')

    def test_statement_account_profile_gives_every_currency_section_the_printed_contract(self):
        lines = [
            [('BANCO EJEMPLO DEL NORTE, S.A., INSTITUCION DE BANCA MULTIPLE', 20000, 400000)],
            [('PERIODO', 330000, 380000), ('DEL 01/03/2024 AL 31/03/2024', 390000, 590000)],
            [('CONTRATO:', 330000, 380000), ('4455667', 390000, 450000)],
            [('RESUMEN PESO MEXICANO', 20000, 200000)],
            [('SALDO INICIAL', 330000, 430000), ('100.00', 520000, 560000)],
            [('FECHA', 20000, 60000), ('CONCEPTO', 80000, 160000), ('ABONOS', 330000, 380000), ('CARGOS', 410000, 460000), ('SALDO', 520000, 560000)],
            [('04/MAR', 20000, 60000), ('VENTA DIVISA', 80000, 300000), ('40.00', 436000, 460000), ('60.00', 536000, 560000)],
            [('SALDO FINAL', 330000, 430000), ('60.00', 520000, 560000)],
            [('RESUMEN DOLAR AMERICANO', 20000, 200000)],
            [('SALDO INICIAL', 330000, 430000), ('0.00', 530000, 560000)],
            [('FECHA', 20000, 60000), ('CONCEPTO', 80000, 160000), ('ABONOS', 330000, 380000), ('CARGOS', 410000, 460000), ('SALDO', 520000, 560000)],
            [('05/MAR', 20000, 60000), ('COMPRA DIVISA', 80000, 300000), ('10.00', 356000, 380000), ('10.00', 536000, 560000)],
            [('SALDO FINAL', 330000, 430000), ('10.00', 530000, 560000)],
        ]
        plain = read_statements([page(1, lines)])
        self.assertEqual([s['account_reference'] for s in plain], ['4455667', ''])
        profile = dict(name='invented-contract', match=dict(any=['banco ejemplo']), statement_account=True)
        profiled = read_statements([page(1, lines)], profile=profile)
        self.assertEqual([s['account_reference'] for s in profiled], ['4455667', '4455667'])
        self.assertTrue(all(s['engine']['proved'] for s in profiled))

    def test_a_balance_column_that_does_not_chain_cannot_prove_and_the_chaining_one_is_kept(self):
        lines = [
            [('BANCO EJEMPLO DEL NORTE, S.A., INSTITUCION DE BANCA MULTIPLE', 20000, 400000)],
            [('PERIODO', 330000, 380000), ('DEL 01/03/2024 AL 31/03/2024', 390000, 590000)],
            [('NO. DE CUENTA', 330000, 400000), ('0012345678', 410000, 500000)],
            [('MONEDA', 330000, 380000), ('PESOS', 390000, 450000)],
            [('SALDO ANTERIOR', 330000, 430000), ('1,000.00', 500000, 560000)],
            [('DEPOSITOS', 330000, 400000), ('500.00', 500000, 560000)],
            [('RETIROS', 330000, 400000), ('250.00', 500000, 560000)],
            [('SALDO FINAL', 330000, 400000), ('1,250.00', 500000, 560000)],
            [('FECHA', 20000, 60000), ('CONCEPTO', 80000, 160000), ('ABONOS', 250000, 290000), ('CARGOS', 320000, 360000),
             ('SALDO GARANTIA', 400000, 470000), ('SALDO', 520000, 560000)],
        ]
        for day, text, credit, debit, balance in MOVES:
            line = [(day, 20000, 60000), (text, 80000, 230000)]
            if credit:
                line.append((credit, 290000 - 6000 * len(credit), 290000))
            if debit:
                line.append((debit, 360000 - 6000 * len(debit), 360000))
            line.append(('0.00', 446000, 470000))
            line.append((balance, 560000 - 6000 * len(balance), 560000))
            lines.append(line)
        st = read_statements([page(1, lines)])[0]
        self.assertTrue(st['engine']['proved'], st['engine'])
        self.assertEqual(st['engine']['basis'], 'running_balance')
        self.assertEqual([r['fields'].get('balance') for r in st['_rows'] if r['kind'] == 'transaction'],
                         ['150000', '130000', '125000'])

    def test_a_second_date_under_a_posting_heading_is_the_posting_date(self):
        def card(heading_above):
            pages = card_statement()
            rows = pages[0]['rows']
            for row in rows:
                texts = [c['expected_text'] for c in row['cells']]
                if texts[:1] == ['Date']:
                    row['cells'][0]['expected_text'] = 'date date' if heading_above else 'Trans date Post date'
                elif texts[:1] and texts[0] in ('Feb 20', 'Mar 2', 'Mar 9'):
                    row['cells'][0]['expected_text'] = texts[0] + ' ' + {'Feb 20': 'Feb 21', 'Mar 2': 'Mar 3', 'Mar 9': 'Mar 10'}[texts[0]]
            if heading_above:
                index = next(i for i, r in enumerate(rows) if r['cells'][0]['expected_text'] == 'date date')
                rows.insert(index, dict(row_index=950, cells=[dict(rows[index]['cells'][0], expected_text='Trans. Post',
                    locator=dict(rows[index]['cells'][0]['locator'], rect=[20000, rows[index]['cells'][0]['locator']['rect'][1] - 6000,
                                                                        60000, rows[index]['cells'][0]['locator']['rect'][1] - 1000]))]))
            return pages
        for heading_above in (False, True):
            st = read_statements(card(heading_above))[0]
            moves = [(r['fields'].get('date'), r['fields'].get('booking_date'), r['fields'].get('value_date'))
                     for r in st['_rows'] if r['kind'] == 'transaction']
            self.assertEqual(moves[0], ('2024-02-20', '2024-02-21', None), heading_above)
        plain = read_statements(mx_statement([('05/MAR 06/MAR', 'TRANSFERENCIA RECIBIDA', '500.00', None, '1,500.00')], closing='1,500.00'))[0]
        self.assertEqual([r['fields'].get('value_date') for r in plain['_rows'] if r['kind'] == 'transaction'], ['2024-03-06'])

    def test_layout_fingerprint_carries_no_values(self):
        a = self.one(mx_statement(MOVES, closing='1,250.00'))
        moves = [(d, t, c and c.replace('5', '7'), dbt, b) for d, t, c, dbt, b in MOVES]
        b = self.one(mx_statement(moves, closing='1,250.00', opening='9,999.99'))
        self.assertEqual(a['layout_fingerprint'], b['layout_fingerprint'])


class EngineRoutingTests(unittest.TestCase):
    def test_engine_serves_pages_no_library_reader_claims(self):
        from services.financial.statement_import_catalog import statement_catalog
        sources = mx_statement(MOVES, closing='1,250.00')
        with mock.patch.dict(os.environ, {'LOUPE_FINANCIAL_GENERIC_READER': '0'}):
            self.assertEqual(statement_catalog(sources)['statements'], [])
        with mock.patch.dict(os.environ, {'LOUPE_FINANCIAL_GENERIC_READER': '1'}):
            catalog = statement_catalog(sources)
        self.assertEqual([s['layout_id'] for s in catalog['statements']], ['generic'])
        self.assertEqual(catalog['unclassified_sources'], [])
        self.assertEqual(catalog['engine_routing']['engine_served'], 1)

    def test_engine_is_on_by_default_and_can_be_switched_off(self):
        from services.financial import statement_engine_routing as R
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('LOUPE_FINANCIAL_GENERIC_READER', None)
            self.assertTrue(R.generic_enabled())
        with mock.patch.dict(os.environ, {'LOUPE_FINANCIAL_GENERIC_READER': '0'}):
            self.assertFalse(R.generic_enabled())
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('LOUPE_FINANCIAL_GENERIC_ONLY', None)
            self.assertFalse(R.generic_only())

    def test_generic_only_switch_skips_every_library_reader(self):
        from services.financial.statement_import_catalog import statement_catalog
        with mock.patch.dict(os.environ, {'LOUPE_FINANCIAL_GENERIC_ONLY': '1'}), \
                mock.patch('services.financial.statement_import_catalog.library_catalog') as library:
            catalog = statement_catalog(mx_statement(MOVES, closing='1,250.00'))
        library.assert_not_called()
        self.assertEqual(catalog['engine_routing']['mode'], 'generic_only')

    def test_route_table_library_first_keeps_the_engine_from_serving(self):
        from services.financial import statement_engine_routing as R
        sources = mx_statement(MOVES, closing='1,250.00')
        fingerprint = read_statements(sources)[0]['layout_fingerprint']
        with mock.patch.dict(os.environ, {'LOUPE_FINANCIAL_GENERIC_READER': '1'}), \
                mock.patch.object(R, 'routes', return_value={fingerprint: 'library_first'}):
            catalog = R.route_catalog(sources, lambda s: dict(statements=[], unclassified_sources=[
                dict(page_number=1, table_index=0)], information_sources=[], complete_coverage=False))
        # Listed for a person, never served: held with the routing reason.
        self.assertEqual([s['engine']['reason'] for s in catalog['statements']], ['route_library_first'])
        self.assertFalse(catalog['statements'][0]['engine']['proved'])
        self.assertEqual(catalog['engine_routing']['library_first'], 1)
        from services.financial.statement_engine import propose_engine_statement
        rows = propose_engine_statement(sources, 'MXN', catalog['statements'][0])['rows']
        self.assertTrue(any(r.get('engine_hold') == 'route_library_first' and not r['excluded'] for r in rows))

    def _library(self, sources, proved_rows):
        group = dict(id='LIB', layout_id='fake-library', institution='', account_reference='0012345678', period_start='2024-03-01',
                     period_end='2024-03-31', currency='MXN', sources=[dict(page_number=1, table_index=0, source_revision='r1')],
                     page_numbers=[1])
        return group, (lambda s: dict(statements=[group], unclassified_sources=[], information_sources=[],
                                      complete_coverage=True))

    def _route(self, sources, library_rows):
        from services.financial import statement_engine_routing as R
        group, library = self._library(sources, library_rows)
        with mock.patch.dict(os.environ, {'LOUPE_FINANCIAL_GENERIC_READER': '1'}), \
                mock.patch('services.financial.statement_review_checks.statement_rows', return_value=library_rows):
            return R.route_catalog(sources, library), group

    def test_agreeing_library_keeps_serving_and_records_agreement(self):
        sources = mx_statement(MOVES, closing='1,250.00')
        engine_rows = read_statements(sources)[0]['_rows']
        catalog, group = self._route(sources, engine_rows)
        self.assertEqual(catalog['statements'], [group])
        self.assertTrue(group.get('engine_agrees'))
        self.assertEqual(catalog['engine_routing']['agreements'], 1)

    def test_an_agreeing_library_period_takes_the_identity_facts_it_left_unread_from_the_engine(self):
        from services.financial import statement_engine_routing as R
        sources = mx_statement(MOVES, closing='1,250.00')
        engine = read_statements(sources)[0]
        self.assertTrue(engine['institution'] and engine['holder'])
        catalog, group = self._route(sources, engine['_rows'])
        self.assertEqual(catalog['statements'], [group])
        self.assertEqual((group['institution'], group['holder'], group['identity_from_engine']),
                         (engine['institution'], engine['holder'], ['institution', 'holder']))
        self.assertEqual(group['account_reference'], '0012345678')  # its own reading stays
        with mock.patch.object(R, 'AGREEMENT_FILLS_IDENTITY', False):
            catalog, group = self._route(sources, engine['_rows'])
        self.assertEqual((group['institution'], group.get('holder'), group.get('identity_from_engine')), ('', None, None))

    def test_an_agreeing_library_period_never_takes_a_currency_or_an_account(self):
        sources = mx_statement(MOVES, closing='1,250.00')
        engine = read_statements(sources)[0]
        self.assertTrue(engine['currency'])
        group, library = self._library(sources, engine['_rows'])
        group.update(currency='', account_reference='')
        from services.financial import statement_engine_routing as R
        with mock.patch.dict(os.environ, {'LOUPE_FINANCIAL_GENERIC_READER': '1'}), \
                mock.patch('services.financial.statement_review_checks.statement_rows', return_value=engine['_rows']):
            R.route_catalog(sources, library)
        self.assertEqual((group['currency'], group['account_reference']), ('', ''))

    def test_an_agreeing_library_period_with_a_conflicting_identity_fact_takes_nothing(self):
        from services.financial import statement_engine_routing as R
        sources = mx_statement(MOVES, closing='1,250.00')
        rows = read_statements(sources)[0]['_rows']
        group, library = self._library(sources, rows)
        group['account_reference'] = '9999999999'
        with mock.patch.dict(os.environ, {'LOUPE_FINANCIAL_GENERIC_READER': '1'}), \
                mock.patch('services.financial.statement_review_checks.statement_rows', return_value=rows):
            catalog = R.route_catalog(sources, library)
        self.assertEqual((group['institution'], group.get('identity_from_engine')), ('', None))

    def test_disagreeing_proved_readings_hold_the_period(self):
        sources = mx_statement(MOVES, closing='1,250.00')
        rows = [dict(r, fields=dict(r['fields'])) for r in read_statements(sources)[0]['_rows']]
        moved = [r for r in rows if not r['excluded']]
        # Another reader that also reconciles: swap two amounts between debit lines of equal sum.
        moved[1]['fields'].update(amount_minor='20000', date='2024-03-11')
        catalog, group = self._route(sources, rows)
        self.assertIn('LIB', catalog['engine_routing']['disagreements'])
        from services.financial.statement_engine_routing import disagreement_row
        hold = disagreement_row(rows, group)
        self.assertFalse(hold['excluded'])
        self.assertTrue(hold['issues'])

    def test_unproved_library_period_is_served_by_the_engine_under_the_library_id(self):
        sources = mx_statement(MOVES, closing='1,250.00')
        rows = [dict(r, fields=dict(r['fields'])) for r in read_statements(sources)[0]['_rows']]
        [r for r in rows if not r['excluded']][0]['fields']['amount_minor'] = '1'
        catalog, group = self._route(sources, rows)
        served = catalog['statements'][0]
        self.assertEqual((served['id'], served['layout_id'], served['replaced_layout']), ('LIB', 'generic', 'fake-library'))
        self.assertEqual(catalog['engine_routing']['replaced'], ['LIB'])

    def test_a_library_reading_that_reconciles_is_never_replaced(self):
        sources = mx_statement(MOVES, closing='1,250.00')
        rows = [dict(r, fields=dict(r['fields'])) for r in read_statements(sources)[0]['_rows']]
        # The library reconciles but is held today for another reason (a flagged control line): it keeps the period.
        rows.append(dict(rows[0], id='x', kind='statement_total', excluded=True, issues=['check'], fields=dict(description='Total credit')))
        catalog, group = self._route(sources, rows)
        self.assertEqual(catalog['statements'], [group])
        self.assertEqual(catalog['engine_routing']['replaced'], [])

    def test_conflicting_identity_keeps_the_library_period(self):
        from services.financial import statement_engine_routing as R
        sources = mx_statement(MOVES, closing='1,250.00')
        rows = [dict(r, fields=dict(r['fields'])) for r in read_statements(sources)[0]['_rows']]
        [r for r in rows if not r['excluded']][0]['fields']['amount_minor'] = '1'
        group, library = self._library(sources, rows)
        group['account_reference'] = '9999999999'
        with mock.patch.dict(os.environ, {'LOUPE_FINANCIAL_GENERIC_READER': '1'}), \
                mock.patch('services.financial.statement_review_checks.statement_rows', return_value=rows):
            catalog = R.route_catalog(sources, library)
        self.assertEqual(catalog['statements'], [group])

    def _scoped(self, library_rows, **group_changes):
        """The library period also claims a continuation page the engine section does not use (row-level scope)."""
        from services.financial import statement_engine_routing as R
        sources = mx_statement(MOVES, closing='1,250.00') + [dict(page_number=2, table_index=0, source_revision='r2', rows=[])]
        group, library = self._library(sources, library_rows)
        group.update(sources=group['sources'] + [dict(page_number=2, table_index=0, source_revision='r2')], page_numbers=[1, 2],
                     **group_changes)
        with mock.patch.dict(os.environ, {'LOUPE_FINANCIAL_GENERIC_READER': '1'}), \
                mock.patch('services.financial.statement_review_checks.statement_rows', return_value=library_rows):
            return R.route_catalog(sources, library), group

    def test_row_level_scope_cross_checks_the_same_printed_period(self):
        rows = read_statements(mx_statement(MOVES, closing='1,250.00'))[0]['_rows']
        catalog, group = self._scoped(rows)
        self.assertEqual(catalog['statements'], [group])
        self.assertTrue(group.get('engine_agrees'))
        self.assertEqual((catalog['engine_routing']['agreements'], catalog['engine_routing'].get('scoped_agreements')), (1, 1))

    def test_row_level_scope_disagreement_holds_and_other_sections_are_not_paired(self):
        base = read_statements(mx_statement(MOVES, closing='1,250.00'))[0]['_rows']
        rows = [dict(r, fields=dict(r['fields'])) for r in base]
        [r for r in rows if not r['excluded']][1]['fields'].update(amount_minor='20000', date='2024-03-11')
        catalog, _ = self._scoped(rows)
        self.assertEqual(catalog['engine_routing']['disagreements'], ['LIB'])
        # Another printed opening balance: another section of the period, never compared.
        other = [dict(r, fields=dict(r['fields'])) for r in base]
        next(r for r in other if r['fields'].get('description') == 'Opening Balance')['fields']['balance'] = '0'
        catalog, _ = self._scoped(other)
        self.assertEqual((catalog['engine_routing']['disagreements'], catalog['engine_routing'].get('scoped_unpaired')), ([], 1))
        # No printed account on the library side: not paired by dates alone.
        catalog, _ = self._scoped(rows, account_reference='')
        self.assertEqual((catalog['engine_routing']['disagreements'], catalog['engine_routing']['agreements']), ([], 0))

    def test_row_level_scope_never_replaces_a_library_period(self):
        rows = [dict(r, fields=dict(r['fields'])) for r in read_statements(mx_statement(MOVES, closing='1,250.00'))[0]['_rows']]
        [r for r in rows if not r['excluded']][0]['fields']['amount_minor'] = '1'
        catalog, group = self._scoped(rows)
        self.assertEqual(catalog['statements'], [group])
        self.assertEqual((catalog['engine_routing']['replaced'], catalog['engine_routing'].get('scoped_unchecked')), ([], 1))


if __name__ == '__main__':
    unittest.main()


class EngineProfileTests(unittest.TestCase):
    PROFILE = dict(name='invented-bank', match=dict(any=['banco ejemplo del norte']), institution='Banco Ejemplo',
                   labels=dict(opening=['SALDO DE APERTURA']), date_order='dmy')

    def sources(self):
        sources = mx_statement(MOVES, closing='1,250.00')
        for row in sources[0]['rows']:
            for c in row['cells']:
                if c['expected_text'] == 'SALDO ANTERIOR':
                    c['expected_text'] = 'SALDO DE APERTURA'
        return sources

    def test_profile_format_is_validated(self):
        from services.financial.statement_engine_profiles import PROFILES, validate
        self.assertEqual(len({p['name'] for p in PROFILES}), len(PROFILES))
        for bad in (dict(name='x', match={}, colour='red'), dict(name='x', match={}, convention='owed'),
                    dict(name='x', match={}, labels=dict(opening_balance=['A'])), dict(name='x', match={}, currency='XYZ')):
            with self.assertRaises(Exception):
                validate(bad)

    def test_two_existing_families_are_expressed_as_profiles(self):
        from services.financial.statement_engine_profiles import PROFILES
        self.assertTrue({'capital-one-card', 'bbva-mexico-cash-management'} <= {p['name'] for p in PROFILES})

    def test_matching_needs_exactly_one_profile(self):
        from services.financial import statement_engine_profiles as P
        with mock.patch.object(P, 'PROFILES', (self.PROFILE,)):
            self.assertEqual(P.matching_profile('BANCO EJEMPLO DEL NORTE, S.A.')['name'], 'invented-bank')
            self.assertIsNone(P.matching_profile('another bank'))
        with mock.patch.object(P, 'PROFILES', (self.PROFILE, dict(self.PROFILE, name='twin'))):
            self.assertIsNone(P.matching_profile('BANCO EJEMPLO DEL NORTE'))

    def test_a_profile_label_reads_a_layout_the_plain_engine_cannot(self):
        plain = read_statements(self.sources())[0]
        self.assertFalse(plain['engine']['proved'])
        self.assertEqual(plain['engine']['reason'], 'no_opening')
        profiled = read_statements(self.sources(), profile=self.PROFILE)[0]
        self.assertTrue(profiled['engine']['proved'], profiled['engine'])
        self.assertEqual(profiled['engine_profile'], 'invented-bank')
        # The profile's institution is used only when no legal-name line is printed.
        self.assertEqual(profiled['institution'], 'BANCO EJEMPLO DEL NORTE')

    def test_account_heading_profile_reads_an_account_printed_after_the_product_name(self):
        def pages(*extra):
            sources = mx_statement(MOVES, closing='1,250.00')
            rows = sources[0]['rows']
            rows[:] = [r for r in rows if not any(c['expected_text'] in ('NO. DE CUENTA', '0012345678') for c in r['cells'])]
            for index, text in enumerate(extra):
                rows.insert(1, dict(row_index=900 + index, cells=[dict(column_index=0, expected_text=text, locator=dict(
                    page=1, rect=[20000, 30000 + index * 1000, 300000, 30900 + index * 1000], page_size=[612000, 792000]))]))
            return sources
        profile = dict(name='invented-heading', match=dict(any=['banco ejemplo']), account_heading=True)
        self.assertEqual(read_statements(pages('CUENTA EJEMPLO PYME 12-34567890-1'))[0]['account_reference'], '')
        st = read_statements(pages('CUENTA EJEMPLO PYME 12-34567890-1'), profile=profile)[0]
        self.assertEqual(st['account_reference'], '12-34567890-1')
        self.assertTrue(st['engine']['proved'])
        # Two different heading numbers, a telephone or a date: no account.
        for extra in (('CUENTA EJEMPLO PYME 12-34567890-1', 'INVERSION EJEMPLO 66-34567890-2'),
                      ('TELEFONO 55-5169-4300-12',), ('CORTE AL 31-03-2024',)):
            self.assertEqual(read_statements(pages(*extra), profile=profile)[0]['account_reference'], '', extra)

    def test_routing_applies_a_matching_profile_and_proposals_reread_with_it(self):
        from services.financial import statement_engine_profiles as P
        from services.financial import statement_engine_routing as R
        from services.financial.statement_engine import propose_engine_statement
        sources = self.sources()
        with mock.patch.object(P, 'PROFILES', (self.PROFILE,)), \
                mock.patch.dict(os.environ, {'LOUPE_FINANCIAL_GENERIC_READER': '1'}):
            catalog = R.route_catalog(sources, lambda s: dict(statements=[], unclassified_sources=[
                dict(page_number=1, table_index=0)], information_sources=[], complete_coverage=False))
            self.assertEqual(catalog['engine_routing']['profile'], 'invented-bank')
            statement = catalog['statements'][0]
            rows = propose_engine_statement(sources, 'MXN', statement)['rows']
        self.assertEqual(sum(not r['excluded'] for r in rows), 3)
        self.assertFalse(any(r.get('engine_hold') for r in rows))


class IdentityReadingTests(unittest.TestCase):
    """r3: identity facts read generically (holder names with letter-digit tokens, legal-name tiers,
    repeated currency label words)."""

    def one(self, sources):
        statements = read_statements(sources)
        self.assertEqual(len(statements), 1)
        return statements[0]

    def replaced(self, old, new, **kwargs):
        pages = mx_statement(MOVES, closing='1,250.00', **kwargs)
        for row in pages[0]['rows']:
            for cell in row['cells']:
                if cell['expected_text'] == old:
                    cell['expected_text'] = new
        return pages

    def test_a_company_name_with_a_letter_digit_token_is_a_holder_but_a_street_number_is_not(self):
        st = self.one(self.replaced('EMPRESA DE PRUEBA SA DE CV', 'SERVICIOS X9 SA DE CV'))
        self.assertEqual(st['holder'], 'SERVICIOS X9 SA DE CV')
        st = self.one(self.replaced('EMPRESA DE PRUEBA SA DE CV', 'AVENIDA CENTRAL 450'))
        self.assertEqual(st['holder'], '')

    def test_the_designated_legal_name_wins_over_headings_and_narrative_lines(self):
        legal = ['BANCO EJEMPLO DEL NORTE, S.A., INSTITUCION DE BANCA MULTIPLE']
        cases = (
            (['ESTADO DE CUENTA BANCO'] + legal, 'BANCO EJEMPLO DEL NORTE'),
            (['DE BANCO EJEMPLO Y EJEMPLO CASA DE BOLSA'] + legal, 'BANCO EJEMPLO DEL NORTE'),
            (['INSTITUCION DE BANCA MULTIPLE, ESTADO DE CUENTA', 'BANCO EJEMPLO DEL NORTE S.A.'], 'BANCO EJEMPLO DEL NORTE'),
            (['2024 EJEMPLO BANK, N.A.'], 'EJEMPLO BANK'),
            (['TRANSFERENCIA BANCO OTRO, S.A. CUENTA 001234567890'], ''),
        )
        for lines, expected in cases:
            self.assertEqual(E._institution([set(lines)], set(lines)), expected, lines)

    def test_a_zip_plus_four_address_anchors_the_addressee_and_the_issuer_is_never_the_holder(self):
        def card(postal):
            pages = card_statement()
            for row in pages[0]['rows']:
                for c in row['cells']:
                    if c['expected_text'] == 'SPRINGFIELD, IL 62701':
                        c['expected_text'] = postal
            return pages
        self.assertEqual(self.one(card('SPRINGFIELD, IL 62701-1234'))['holder'], 'JANE Q SAMPLE')
        issuer = card('SPRINGFIELD, IL 62701-1234')
        for row in issuer[0]['rows']:
            for c in row['cells']:
                if c['expected_text'] == 'JANE Q SAMPLE':
                    c['expected_text'] = 'Example Card'
        profile = dict(name='invented-card', match=dict(any=['example card']), institution='Example Card')
        self.assertEqual(read_statements(issuer, profile=profile)[0]['holder'], '')

    def test_addressee_merged_with_the_right_column_and_a_blank_line_before_the_postcode(self):
        lines = [
            [('BANCO EJEMPLO DEL NORTE, S.A., INSTITUCION DE BANCA MULTIPLE', 20000, 400000)],
            [('EMPRESA DE PRUEBA SA DE CV CLIENTE No. 1234567', 6000, 330000)],
            [('CALLE FALSA 124 PISO 2', 6000, 200000), ('CONTRATO:', 400000, 450000), ('7654321', 460000, 520000)],
            [('CIUDAD DE MEXICO MEXICO', 6000, 160000), ('PERIODO DEL 01/03/2024 AL 31/03/2024', 400000, 590000)],
            [('CTA. SPID:', 400000, 450000), ('999000000012345678', 460000, 590000)],
            [('C.P.: 06000', 10000, 80000), ('FOLIO: D-0000001', 190000, 300000)],
            [('SALDO ANTERIOR', 330000, 430000), ('1,000.00', 500000, 560000)],
            [('SALDO FINAL', 330000, 400000), ('1,250.00', 500000, 560000)],
            [('FECHA', 20000, 60000), ('CONCEPTO', 80000, 160000), ('ABONOS', 330000, 380000), ('CARGOS', 410000, 460000), ('SALDO', 520000, 560000)],
        ]
        for day, text, credit, debit, balance in MOVES:
            line = [(day, 20000, 60000), (text, 80000, 300000)]
            if credit:
                line.append((credit, 380000 - 6000 * len(credit), 380000))
            if debit:
                line.append((debit, 460000 - 6000 * len(debit), 460000))
            line.append((balance, 560000 - 6000 * len(balance), 560000))
            lines.append(line)
        st = self.one([page(1, lines)])
        self.assertEqual(st['holder'], 'EMPRESA DE PRUEBA SA DE CV')
        self.assertTrue(st['engine']['proved'], st['engine'])

    def test_a_lone_word_is_not_a_bank_name(self):
        self.assertEqual(E._institution([{'ONE, N.A. YOU MAY CONTINUE TO SEE SOME REFERENCES'}], set()), '')
        self.assertEqual(E._institution([{'CITIBANK, N.A.'}], set()), 'CITIBANK')

    def test_a_currency_value_repeating_the_label_word_is_read(self):
        st = self.one(mx_statement(MOVES, closing='1,250.00', currency_line=('MONEDA', 'MONEDA NACIONAL')))
        self.assertEqual(st['currency'], 'MXN')


class ScanDamageTests(unittest.TestCase):
    """OCR damage on scanned statements (r4): every repair keeps the printed digits; the proof decides."""

    def one(self, sources):
        statements = read_statements(sources)
        self.assertEqual(len(statements), 1, [s['engine'] for s in statements])
        return statements[0]

    def words(self, text):
        import re
        return [w for _, _, w in E._rejoin_amounts([(m.start(), m.end(), m.group()) for m in re.finditer(r'\S+', text)])]

    def test_noise_and_split_amounts_inside_one_cell_are_rejoined(self):
        self.assertEqual(self.words('650.00?'), ['650.00'])
        self.assertEqual(self.words('8,463,157 .26?'), ['8,463,157,26'])
        self.assertEqual(self.words('135 , 700.06'), ['135,700.06'])
        self.assertEqual(self.words('3,215 , 677.12'), ['3,215,677.12'])
        self.assertEqual(self.words('12,486, 37'), ['12,486,37'])
        self.assertEqual(self.words('5,291 157,82'), ['5,291,157,82'])
        self.assertEqual(self.words('5,733,642 43'), ['5,733,642,43'])
        self.assertEqual(self.words('140,527 ,00'), ['140,527,00'])
        self.assertEqual(self.words('2,617,384,.91'), ['2,617,384.91'])

    def test_a_count_before_an_amount_is_never_joined(self):
        self.assertEqual(self.words('2 100,000.00'), ['2', '100,000.00'])
        self.assertEqual(self.words('12 345.67'), ['12', '345.67'])
        self.assertEqual(self.words('1,234 5,678.90'), ['1,234', '5,678.90'])

    def test_an_amount_split_into_two_cells_at_its_thousands_separator_is_rejoined_only_when_adjacent(self):
        near = page(1, [[('SALDO INICIAL', 100000, 200000), ('157', 400000, 412000), ('913.46', 414000, 438000)]])
        far = page(1, [[('DEPOSITOS', 100000, 200000), ('2', 300000, 304000), ('100,000.00', 400000, 440000)]])
        tokens = [t['t'] for t in E._pages([near])[1][0]['tokens']]
        self.assertEqual(tokens[-1], '157,913.46')
        tokens = [t['t'] for t in E._pages([far])[1][0]['tokens']]
        self.assertEqual(tokens[-2:], ['2', '100,000.00'])

    def test_letter_o_and_digit_zero_confusion_in_dates(self):
        from datetime import date
        self.assertTrue(E.is_date_token('O1-JUN-2021'))
        self.assertTrue(E.is_date_token('02-AG0-2021'))
        self.assertFalse(E.is_date_token('OO-JUN'))
        self.assertEqual(E.period_ranges('PERIODO : O1 AL 31 DE MAYO DE 2022'), [(date(2022, 5, 1), date(2022, 5, 31))])

    def test_a_period_quoted_in_a_damaged_movement_line_is_not_the_statement_period(self):
        moves = [('O5/MAR', 'INTERESES DEL PERIODO 01/02/2024 AL 29/02/2024', '500.00', None, '1,500.00'),
                 ('10/MAR', 'PAGO DE SERVICIO', None, '200.00', '1,300.00'),
                 ('20/MAR', 'COMISION', None, '50.00', '1,250.00')]
        st = self.one(mx_statement(moves, closing='1,250.00'))
        self.assertEqual((st['period_start'], st['period_end']), ('2024-03-01', '2024-03-31'))
        self.assertTrue(st['engine']['proved'], st['engine'])

    def test_slash_period_with_hyphenated_dates_and_a_split_month(self):
        from datetime import date
        self.assertEqual(E.period_ranges('Periodo 04-MAY-26/29-MAY-26'), [(date(2026, 5, 4), date(2026, 5, 29))])
        self.assertEqual(E.period_ranges('Periodo 03-FEB-26/27-F EB-26'), [(date(2026, 2, 3), date(2026, 2, 27))])

    def test_currency_label_values_read_with_ocr_damage_or_split_from_the_label(self):
        self.assertEqual(E.labelled_currency('MONEDA', 'MONEDA NACTONAL'), 'MXN')
        self.assertEqual(E.labelled_currency('MONEDA', 'NONEDA NACTONAL'), 'MXN')
        self.assertEqual(E.labelled_currency('MONEDA', 'NACIONAL'), 'MXN')
        self.assertEqual(E.labelled_currency('MONEDA', 'DOLARES'), 'USD')
        self.assertEqual(E.labelled_currency('MONEDA', 'EXTRANJERA'), '')
        self.assertEqual(E.labelled_currency('MONEDA', 'NACIONALES DEL'), '')
        st = self.one(mx_statement(MOVES, closing='1,250.00', currency_line=('MONEDA', 'MONEDA NACTONAL')))
        self.assertEqual(st['currency'], 'MXN')

    def test_an_impossible_page_number_counts_as_an_unnumbered_page(self):
        facts = E.page_facts(E._pages([page(1, [[('HOJA 10DE 2', 400000, 500000)]])])[1], 'dot')
        self.assertEqual(facts['numbering'], set())

    def test_a_scanned_page_placed_further_right_is_aligned_to_the_first_page(self):
        sources = mx_statement(MOVES[:2], closing='1,250.00')
        shift = 9000  # 1.5% of the width: one printed column lands in a band of its own.
        lines = [[('FECHA', 20000, 60000), ('CONCEPTO', 80000, 160000)],
                 [('20/MAR', 20000 + shift, 60000 + shift), ('COMISION', 80000 + shift, 300000 + shift),
                  ('50.00', 430000 + shift, 460000 + shift), ('1,250.00', 512000 + shift, 560000 + shift)],
                 [('21/MAR', 20000 + shift, 60000 + shift), ('COMISION', 80000 + shift, 300000 + shift),
                  ('0.00', 436000 + shift, 460000 + shift), ('1,250.00', 512000 + shift, 560000 + shift)]]
        sources.append(page(2, lines))
        st = self.one(sources)
        self.assertTrue(st['engine']['proved'], st['engine'])
        self.assertEqual(len([m for m in st['_rows'] if m['kind'] == 'transaction']), 3)

    def test_a_total_line_printing_the_running_balance_closes_the_table(self):
        sources = mx_statement(MOVES)
        sources[0]['rows'].append(dict(row_index=len(sources[0]['rows']), cells=[
            cell('TOTAL', 80000, 120000, 400000, 0), cell('500.00', 350000, 380000, 400000, 1),
            cell('250.00', 430000, 460000, 400000, 2), cell('1,250.00', 512000, 560000, 400000, 3)]))
        st = self.one(sources)
        self.assertTrue(st['engine']['proved'], st['engine'])
        closing = [r['fields']['balance'] for r in st['_rows'] if r['fields'].get('description') == 'Closing Balance']
        self.assertEqual(closing, ['125000'])


def day_column_statement(page_two_heading=True, usd_section=True):
    """An invented two-currency layout: summary, a DIA | FOLIO | CONCEPTO table with day-only dates and a
    Total line, the heading line repeated on the next page, then a quiet second currency section."""
    head = [('Saldo minimo requerido', 20000, 150000), ('0.00', 160000, 190000), ('Saldo Inicial', 330000, 400000),
            ('1,000.00', 500000, 560000)]
    table = [('DIA', 20000, 40000), ('FOLIO', 60000, 100000), ('CONCEPTO', 120000, 200000),
             ('DEPOSITOS', 330000, 380000), ('RETIROS', 410000, 460000), ('SALDO', 520000, 560000)]
    one = [
        [('BANCO EJEMPLO DEL SUR, S.A., INSTITUCION DE BANCA MULTIPLE', 20000, 400000)],
        [('Periodo DEL 2024-03-01 AL 2024-03-31', 330000, 590000)],
        [('EMPRESA DE PRUEBA SA DE CV', 20000, 200000)],
        [('CALLE FALSA 123', 20000, 150000)],
        [('CIUDAD DE MEXICO C.P. 06000', 20000, 220000)],
        [('CUENTA DE CHEQUES 123-45678-001-2', 20000, 300000)],
        [('Moneda', 20000, 80000), ('MN', 100000, 120000)],
        [('Saldo Inicial', 20000, 100000), ('1,000.00', 200000, 250000)],
        [('+ Depositos', 20000, 100000), ('500.00', 200000, 250000)],
        [('- Retiros', 20000, 100000), ('250.00', 200000, 250000)],
        [('Saldo Final', 20000, 100000), ('1,250.00', 200000, 250000)],
        head, table,
        [('5', 20000, 30000), ('101', 60000, 100000), ('TRANSFERENCIA RECIBIDA', 120000, 300000),
         ('500.00', 350000, 380000), ('1,500.00', 512000, 560000)],
    ]
    two = [head] if page_two_heading else []
    two += [table,
            [('28', 20000, 34000), ('102', 60000, 100000), ('PAGO DE SERVICIO', 120000, 300000),
             ('250.00', 430000, 460000), ('1,250.00', 512000, 560000)],
            [('Total', 120000, 160000), ('500.00', 350000, 380000), ('250.00', 430000, 460000),
             ('1,250.00', 512000, 560000)]]
    if usd_section:
        two += [[('CUENTA DE CHEQUES USD 123-45678-002-0', 20000, 300000)],
                [('Moneda', 20000, 80000), ('USD', 100000, 130000)],
                [('Saldo Inicial', 20000, 100000), ('0.00 USD', 200000, 250000)],
                [('+ Depositos', 20000, 100000), ('0.00 USD', 200000, 250000)],
                [('- Retiros', 20000, 100000), ('0.00 USD', 200000, 250000)],
                [('Saldo Final', 20000, 100000), ('0.00', 200000, 250000)]]
    return [page(1, one), page(2, two)]


class DayColumnAndSectionTests(unittest.TestCase):
    def test_a_day_column_dates_rows_inside_the_printed_period(self):
        statements = read_statements(day_column_statement(usd_section=False))
        self.assertEqual(len(statements), 1, [s['engine'] for s in statements])
        st = statements[0]
        self.assertTrue(st['engine']['proved'], st['engine'])
        self.assertEqual([(r['fields']['date'], r['fields']['direction'], r['fields']['amount_minor'])
                          for r in st['_rows'] if r['kind'] == 'transaction'],
                         [('2024-03-05', 'credit', '50000'), ('2024-03-28', 'debit', '25000')])

    def test_a_day_alone_is_not_a_date_without_a_day_column_heading(self):
        sources = day_column_statement(usd_section=False)
        for source in sources:
            for row in source['rows']:
                for c in row['cells']:
                    if c['expected_text'] == 'DIA':
                        c['expected_text'] = 'FECHA'
        st = read_statements(sources)[0]
        self.assertFalse(st['engine']['proved'])

    def test_a_heading_line_repeated_on_the_next_page_continues_the_section(self):
        sources = day_column_statement(page_two_heading=True, usd_section=False)
        for source in sources:
            for row in source['rows']:
                for c in row['cells']:
                    c['expected_text'] = {'5': '05/03', '28': '28/03'}.get(c['expected_text'], c['expected_text'])
        statements = read_statements(sources)
        self.assertEqual(len(statements), 1, [s['engine'] for s in statements])
        self.assertEqual(statements[0]['page_numbers'], [1, 2])
        self.assertTrue(statements[0]['engine']['proved'], statements[0]['engine'])

    def test_a_total_line_ends_the_table_and_the_next_section_takes_its_own_currency(self):
        statements = read_statements(day_column_statement())
        self.assertEqual([(s['currency'], s['engine']['proved']) for s in statements], [('MXN', True), ('USD', True)])


class SharedYearAndStackedAccountTests(unittest.TestCase):
    def test_month_day_range_with_one_printed_year(self):
        from datetime import date
        self.assertEqual(E.period_ranges('MAR.24-APR.23,2024'), [(date(2024, 3, 24), date(2024, 4, 23))])
        self.assertEqual(E.period_ranges('Statement period Dec 24 - Jan 23, 2024'), [(date(2023, 12, 24), date(2024, 1, 23))])
        self.assertEqual(E.period_ranges('FEB.24-MAY.21,2021'), [(date(2021, 2, 24), date(2021, 5, 21))])

    def stacked(self, value, label='ACCOUNT NUMBER', inline=None):
        lines = [[('BANK OF EXAMPLE', 20000, 200000)],
                 [(label, 380000, 470000), ('STATEMENT PERIOD', 480000, 580000)],
                 [(value, 400000, 440000), ('MAR.24-APR.23,2024', 480000, 580000)]]
        if inline:
            lines.append([('ACCOUNT NUMBER ' + inline, 20000, 300000)])
        pages = E._pages([page(1, lines)])
        return E._stacked_accounts(pages[1])

    def test_an_account_number_printed_under_its_column_heading(self):
        self.assertEqual(self.stacked('2489'), [('2489', 3)])
        self.assertEqual(self.stacked('12 3456 7890'), [('1234567890', 3)])
        # Four digits only under a full account-number label; a short reference under 'CUENTA' is not one.
        self.assertEqual(self.stacked('2489', label='CUENTA'), [])
        self.assertEqual(self.stacked('PYME'), [])

    def test_the_same_number_printed_inline_and_stacked_is_one_account(self):
        lines = [[('BANCO EJEMPLO, S.A., INSTITUCION DE BANCA MULTIPLE', 20000, 400000)],
                 [('PERIODO DEL 01/03/2024 AL 31/03/2024', 330000, 590000)],
                 [('NO. DE CUENTA', 380000, 470000)],
                 [('12-34567890-1', 380000, 470000)],
                 [('NO. DE CUENTA 1234567890 1', 20000, 300000)],
                 [('SALDO ANTERIOR', 330000, 430000), ('1,000.00', 500000, 560000)],
                 [('SALDO FINAL', 330000, 430000), ('1,000.00', 500000, 560000)],
                 [('TOTAL DEPOSITOS', 330000, 430000), ('0.00', 500000, 560000)],
                 [('TOTAL RETIROS', 330000, 430000), ('0.00', 500000, 560000)]]
        statements = read_statements([page(1, lines)])
        # Without the digit comparison the two printed forms would be two top-ranked accounts and none would be read.
        self.assertEqual(statements[0]['account_reference'], '12345678901')


class SummaryAndContinuationTests(unittest.TestCase):
    def us_statement(self, summary_opening=True, balance_on_second_line=True):
        """An invented US layout: summary box, then DATE | DESCRIPTION | CREDITS | DEBITS | DAILY BALANCE with the
        day's balance printed on an entry's second line."""
        lines = [[('EXAMPLE SAVINGS BANK, N.A.', 20000, 300000)],
                 [('ACCOUNT NUMBER', 380000, 470000), ('STATEMENT PERIOD', 480000, 580000)],
                 [('987654', 400000, 440000), ('MAR.24-APR.23,2024', 480000, 580000)],
                 [('JANE Q SAMPLE', 20000, 150000)],
                 [('100 MAIN ST', 20000, 150000)],
                 [('SPRINGFIELD, IL 62701', 20000, 170000)]]
        if summary_opening:
            lines.append([('BEGINNING BALANCE', 330000, 430000), ('$1,000.00', 500000, 560000)])
        lines += [[('ENDING BALANCE', 330000, 430000), ('$1,250.00', 500000, 560000)],
                  [('DATE', 20000, 60000), ('DESCRIPTION', 80000, 160000), ('CREDITS', 330000, 380000),
                   ('DEBITS', 410000, 460000), ('BALANCE', 520000, 560000)],
                  [('03/24/2024', 20000, 70000), ('BEGINNING BALANCE', 80000, 200000), ('$1,000.00', 512000, 560000)],
                  [('04/08/2024', 20000, 70000), ('MOBILE DEPOSIT', 80000, 200000), ('$300.00', 344000, 380000)]]
        if balance_on_second_line:
            lines.append([('BRANCH 12 SPRINGFIELD', 80000, 220000), ('1,300.00', 512000, 560000)])
        else:
            lines[-1].append(('1,300.00', 512000, 560000))
        lines += [[('04/09/2024', 20000, 70000), ('SERVICE CHARGE', 80000, 200000), ('50.00', 430000, 460000),
                   ('1,250.00', 512000, 560000)],
                  [('ENDING BALANCE', 80000, 200000), ('$1,250.00', 512000, 560000)]]
        return [page(1, lines)]

    def test_a_balance_printed_on_an_entrys_second_line_belongs_to_the_entry(self):
        statements = read_statements(self.us_statement())
        self.assertEqual(len(statements), 1, [s['engine'] for s in statements])
        st = statements[0]
        self.assertTrue(st['engine']['proved'], st['engine'])
        rows = [r for r in st['_rows'] if r['kind'] == 'transaction']
        self.assertEqual([(r['fields']['amount_minor'], r['fields'].get('balance')) for r in rows],
                         [('30000', '130000'), ('5000', '125000')])
        self.assertEqual(rows[0]['fields']['description'], 'MOBILE DEPOSIT BRANCH 12 SPRINGFIELD')

    def test_a_summary_whose_opening_was_not_read_is_the_tables_heading(self):
        statements = read_statements(self.us_statement(summary_opening=False))
        self.assertEqual(len(statements), 1, [s['engine'] for s in statements])
        self.assertTrue(statements[0]['engine']['proved'], statements[0]['engine'])
        self.assertEqual((statements[0]['currency'], statements[0]['account_reference']), ('USD', '987654'))

    def test_a_section_sharing_a_page_takes_the_one_currency_the_statement_names(self):
        sources = mx_statement(MOVES, closing='1,250.00')
        lines = sources[0]['rows']
        y = 40000 + len(lines) * 12000
        extra = [[('SALDO ANTERIOR', 330000, 430000), ('0.00', 530000, 560000)],
                 [('INVERSION CRECIENTE', 20000, 150000), ('NO. DE CUENTA', 330000, 400000), ('9876543210', 410000, 500000)],
                 [('SALDO FINAL', 330000, 400000), ('0.00', 530000, 560000)],
                 [('DEPOSITOS', 330000, 400000), ('0.00', 530000, 560000)],
                 [('RETIROS', 330000, 400000), ('0.00', 530000, 560000)]]
        for offset, line in enumerate(extra):
            lines.append(dict(row_index=len(lines), cells=[cell(t, x0, x1, y + offset * 12000, c)
                                                           for c, (t, x0, x1) in enumerate(line)]))
        statements = read_statements(sources)
        self.assertEqual(len(statements), 2, [s['engine'] for s in statements])
        self.assertEqual([s['currency'] for s in statements], ['MXN', 'MXN'])
        self.assertEqual(statements[1]['currency_source'], 'printed_statement_currency')
        # A statement naming two currencies leaves the shared section's currency to its own heading.
        dollars = mx_statement(MOVES, closing='1,250.00')
        dollars[0]['rows'].append(dict(row_index=99, cells=[cell('MONEDA DOLARES', 20000, 200000, y - 6000, 0)]))
        dollars[0]['rows'] += [dict(row_index=100 + i, cells=[cell(t, x0, x1, y + i * 12000, c) for c, (t, x0, x1) in enumerate(line)])
                               for i, line in enumerate(extra)]
        self.assertNotEqual(read_statements(dollars)[-1].get('currency_source'), 'printed_statement_currency')
        # A zero block with no account of its own (annex pages) stays out, whatever the statement's currency.
        extra[1] = [('INVERSION CRECIENTE', 20000, 150000)]
        annex = mx_statement(MOVES, closing='1,250.00')
        annex[0]['rows'] += [dict(row_index=100 + i, cells=[cell(t, x0, x1, y + i * 12000, c) for c, (t, x0, x1) in enumerate(line)])
                             for i, line in enumerate(extra)]
        self.assertEqual(len(read_statements(annex)), 1)


class QualifiedDollarTests(unittest.TestCase):
    def test_a_qualified_dollar_heading_is_not_us_dollars(self):
        rows = E._pages([page(1, [[('DOLAR AUSTRALIANO', 20000, 200000)], [('DOLAR CANADA', 20000, 200000)],
                                  [('DOLAR AMERICANO SOBRE CUENTAS', 20000, 200000)], [('DOLARES', 20000, 200000)]])])[1]
        self.assertEqual([E._heading_currencies([row], 'dot') for row in rows], [set(), set(), {'USD'}, {'USD'}])

    def test_a_bare_currency_code_counts_only_when_printed_in_capitals(self):
        # Live: OCR of 'Ciudad de Mexico' as 'Ci cad de Mexico' proposed CAD for a peso statement.
        rows = E._pages([page(1, [[('Cad de Mexico', 20000, 200000)], [('EMPRESA SA DE mn', 20000, 200000)],
                                  [('CAD', 20000, 200000)], [('SALDOS EN MN', 20000, 200000)]])])[1]
        self.assertEqual([E._heading_currencies([row], 'dot') for row in rows], [set(), set(), {'CAD'}, {'MXN'}])


class SettlementDateTests(unittest.TestCase):
    def test_a_settlement_date_after_the_period_keeps_the_row_dated_inside_it(self):
        moves = [('05/MAR 05/MAR', 'TRANSFERENCIA RECIBIDA', '500.00', None, '1,500.00'),
                 ('10/MAR 10/MAR', 'PAGO DE SERVICIO', None, '200.00', '1,300.00'),
                 ('31/MAR 02/ABR', 'PAGO DE NOMINA', None, '50.00', '1,250.00')]
        st = read_statements(mx_statement(moves, closing='1,250.00'))[0]
        self.assertTrue(st['engine']['proved'], st['engine'])
        last = [r for r in st['_rows'] if r['kind'] == 'transaction'][-1]['fields']
        self.assertEqual((last['date'], last['value_date']), ('2024-03-31', '2024-04-02'))

    def test_a_row_dated_before_the_period_is_still_unresolved(self):
        moves = [('29/FEB 01/MAR', 'PAGO DE NOMINA', None, '50.00', '950.00')]
        st = read_statements(mx_statement(moves, closing='950.00'))[0]
        self.assertFalse(st['engine']['proved'])
        self.assertEqual(st['engine']['reason'], 'date_unresolved')


class PriorPeriodBlockTests(unittest.TestCase):
    def test_a_profile_block_of_earlier_periods_operations_is_not_this_periods_movements(self):
        from services.financial.statement_engine_profiles import validate
        sources = mx_statement(MOVES, closing='1,250.00')
        rows = sources[0]['rows']
        y = 40000 + len(rows) * 12000
        block = [[('MOVIMIENTOS DE PERIODOS ANTERIORES DE EJEMPLO', 20000, 400000)],
                 [('28/FEB', 20000, 60000), ('PAGO DE NOMINA', 80000, 300000), ('900.00', 430000, 460000)],
                 [('TOTAL DE MOVIMIENTOS', 20000, 200000)]]
        rows += [dict(row_index=len(rows) + i, cells=[cell(t, x0, x1, y + i * 12000, c) for c, (t, x0, x1) in enumerate(line)])
                 for i, line in enumerate(block)]
        self.assertFalse(read_statements(sources)[0]['engine']['proved'])
        profile = validate(dict(name='example', match=dict(any=['banco ejemplo']),
                                prior_period_block=dict(start=['MOVIMIENTOS DE PERIODOS ANTERIORES'],
                                                        end=['TOTAL DE MOVIMIENTOS'])))
        st = read_statements(sources, profile=profile)[0]
        self.assertTrue(st['engine']['proved'], st['engine'])
        self.assertEqual(len([r for r in st['_rows'] if r['kind'] == 'transaction']), 3)
        with self.assertRaises(ValueError):
            validate(dict(name='bad', match=dict(any=['x']), prior_period_block=dict(start=['X'])))


class RoutingAgreementTests(unittest.TestCase):
    _library = EngineRoutingTests._library
    _route = EngineRoutingTests._route

    def test_a_held_library_period_reading_exactly_what_the_engine_proves_is_served_by_the_engine(self):
        sources = mx_statement(MOVES, closing='1,250.00')
        rows = [dict(r, fields=dict(r['fields']), issues=list(r['issues'])) for r in read_statements(sources)[0]['_rows']]
        # The library reads the same money and dates but holds the period on a flagged field.
        [r for r in rows if not r['excluded']][2]['issues'].append('Check the printed liquidation date.')
        catalog, group = self._route(sources, rows)
        self.assertEqual((catalog['statements'][0]['id'], catalog['statements'][0]['layout_id']), ('LIB', 'generic'))
        self.assertEqual(catalog['engine_routing']['replaced'], ['LIB'])

    def test_a_held_library_period_reconciling_a_different_reading_keeps_the_period(self):
        sources = mx_statement(MOVES, closing='1,250.00')
        rows = [dict(r, fields=dict(r['fields']), issues=list(r['issues'])) for r in read_statements(sources)[0]['_rows']]
        moved = [r for r in rows if not r['excluded']]
        moved[2]['fields'].update(date='2024-03-21')
        moved[2]['issues'].append('Check the printed date.')
        catalog, group = self._route(sources, rows)
        self.assertEqual(catalog['statements'], [group])
        self.assertEqual(catalog['engine_routing']['replaced'], [])

    def test_identity_read_with_case_or_legal_form_differences_is_the_same_fact(self):
        from services.financial.statement_engine_routing import _same_identity
        self.assertTrue(_same_identity('institution', 'BBVA Mexico', 'BBVA MEXICO'))
        self.assertTrue(_same_identity('holder', 'EMPRESA DE PRUEBA', 'EMPRESA DE PRUEBA SA DE CV'))
        self.assertTrue(_same_identity('holder', 'EMPRESA DE PRUEBA S.A. DE C.V.', 'EMPRESA DE PRUEBA SA DE CV'))
        self.assertFalse(_same_identity('holder', 'EMPRESA DE PRUEBA', 'OTRA EMPRESA SA DE CV'))
        self.assertFalse(_same_identity('holder', 'SA DE CV', ''))
        self.assertFalse(_same_identity('currency', 'MXN', 'USD'))
        self.assertTrue(_same_identity('account_reference', '0012345678', '12345678'))


def transfer_statement(postal_line='CIUDAD DE MEXICO C.P. 06000', account_line=None, second_page=True):
    """An invented Spanish layout whose transfer movements print several description lines at one left
    edge, the last ending in a five-digit reference; optionally continued on a second page that opens
    with more transfer lines (the shape of the r4-any-layout wrong admission, with invented text)."""
    lines = [
        [('BANCO EJEMPLO DEL NORTE, S.A., INSTITUCION DE BANCA MULTIPLE', 20000, 400000)],
        [('EMPRESA DE PRUEBA SA DE CV', 20000, 200000), ('PERIODO', 330000, 380000),
         ('DEL 01/03/2024 AL 31/03/2024', 390000, 590000)],
        [('CALLE FALSA 123', 20000, 150000), ('MONEDA', 330000, 380000), ('PESOS', 390000, 450000)],
        [('COL CENTRO', 20000, 120000)],
    ]
    if postal_line:
        lines.append([(postal_line, 20000, 220000)])
    lines.append(account_line or [('CUENTA EJEMPLO PYME 12-34567890-1', 20000, 250000), ('CLABE', 260000, 300000),
                                  ('002180123456789017', 310000, 420000)])
    lines += [
        [('SALDO ANTERIOR', 330000, 430000), ('1,000.00', 500000, 560000)],
        [('SALDO FINAL', 330000, 400000), ('1,250.00', 500000, 560000)],
        [('FECHA', 20000, 60000), ('CONCEPTO', 80000, 160000), ('ABONOS', 330000, 380000),
         ('CARGOS', 410000, 460000), ('SALDO', 520000, 560000)],
        [('05/MAR', 20000, 60000), ('ABONO TRANSFERENCIA', 80000, 300000), ('500.00', 350000, 380000),
         ('1,500.00', 512000, 560000)],
    ]
    description = [[('RECIBIDO DE EJEMPLOMEX', 120000, 300000)],
                   [('DEL CLIENTE COMERCIAL EJEMPLO', 120000, 300000)],
                   [('CONCEPTO OC 54321', 120000, 300000)]]
    page_one = lines + description
    later = [[('10/MAR', 20000, 60000), ('PAGO DE SERVICIO', 80000, 300000), ('200.00', 428000, 460000),
              ('1,300.00', 512000, 560000)],
             [('20/MAR', 20000, 60000), ('COMISION', 80000, 300000), ('50.00', 430000, 460000),
              ('1,250.00', 512000, 560000)]]
    if not second_page:
        return [page(1, page_one + later)]
    page_two = [[('FECHA', 20000, 60000), ('CONCEPTO', 80000, 160000), ('ABONOS', 330000, 380000),
                 ('CARGOS', 410000, 460000), ('SALDO', 520000, 560000)],
                [('ENVIADO A EJEMPLOMEX', 120000, 300000)],
                [('AL CLIENTE COMERCIAL EJEMPLO', 120000, 300000)],
                [('A LA CUENTA 0012345 67812', 120000, 300000)]] + later
    return [page(1, page_one), page(2, page_two)]


class HolderAndInterbankTests(unittest.TestCase):
    """r5-any-layout: the holder never comes from movement text, and the printed account number wins over
    the interbank number that contains it."""

    def first(self, sources):
        return read_statements(sources)[0]

    def test_the_addressee_block_is_still_read(self):
        st = self.first(transfer_statement())
        self.assertTrue(st['engine']['proved'], st['engine'])
        self.assertEqual(st['holder'], 'EMPRESA DE PRUEBA SA DE CV')

    def test_movement_description_lines_ending_in_a_reference_are_never_the_holder(self):
        # The addressee's postal line is unreadable: no address block on the heading; the transfer
        # descriptions on page 1 (below the first movement) and page 2 (a movement table) are not one.
        for second_page in (True, False):
            st = self.first(transfer_statement(postal_line=None, second_page=second_page))
            self.assertTrue(st['engine']['proved'], st['engine'])
            self.assertEqual(st['holder'], '')
            self.assertNotIn('RECIBIDO DE EJEMPLOMEX', st['identity_evidence']['holder'])
            self.assertNotIn('ENVIADO A EJEMPLOMEX', st['identity_evidence']['holder'])

    def test_a_postal_line_must_read_as_an_address_line(self):
        for text in ('CIUDAD DE MEXICO C.P. 06000', 'C.P.: 06000', 'CAP. 06000', 'CAP, 06000', 'CODIGO POSTAL 06000', '06000 CIUDAD DE MEXICO',
                     'SPRINGFIELD, IL 62701', 'SPRINGFIELD, IL 62701-1234', 'CIUDAD EJEMPLO, ESTADO 06000'):
            self.assertTrue(E._postal(E.fold(text)), text)
        for text in ('CONCEPTO OC 54321', 'A LA CUENTA 0012345 67812', 'REF 12345', 'CLAVE DE RASTREO 2024 12345',
                     'TOTAL 12345'):
            self.assertFalse(E._postal(E.fold(text)), text)

    def test_a_line_with_money_or_a_date_at_the_block_edge_is_not_part_of_an_address(self):
        lines = [[('EMPRESA DE PRUEBA SA DE CV', 20000, 200000)],
                 [('05/03/2024 PAGO RECIBIDO', 20000, 200000)],
                 [('CALLE FALSA 123', 20000, 150000)],
                 [('COL CENTRO', 20000, 120000)],
                 [('CIUDAD DE MEXICO C.P. 06000', 20000, 220000)]]
        rows = E._pages([page(1, lines)])[1]
        # The dated line stops the block: three lines remain, topped by the street line (not a name).
        self.assertEqual(E.address_holder(rows), '')
        lines[1] = [('CALLE FALSA 123 INT 4', 20000, 200000), ('DEL 01/03/2024 AL 31/03/2024', 330000, 590000)]
        rows = E._pages([page(1, lines)])[1]
        # A period printed further right beside an address line does not count against it.
        self.assertEqual(E.address_holder(rows), 'EMPRESA DE PRUEBA SA DE CV')

    def test_the_printed_account_number_wins_over_the_interbank_number_containing_it(self):
        st = self.first(transfer_statement())
        self.assertEqual((st['account_reference'], st['account_basis']), ('12-34567890-1', 'account_number'))

    def test_an_interbank_number_alone_stays_the_account_and_says_so(self):
        st = self.first(transfer_statement(account_line=[('CUENTA CLABE', 20000, 120000),
                                                          ('002180012345678901', 130000, 240000)]))
        self.assertEqual((st['account_reference'], st['account_basis']), ('002180012345678901', 'interbank_number'))
        # A number printed beside it that is not its account field is not the account.
        st = self.first(transfer_statement(account_line=[('CUENTA EJEMPLO 98-76543210-1', 20000, 250000),
                                                          ('CLABE', 260000, 300000), ('002180123456789017', 310000, 420000)]))
        self.assertEqual((st['account_reference'], st['account_basis']), ('002180123456789017', 'interbank_number'))

    def test_the_interbank_numbers_own_digit_groups_are_not_a_printed_account(self):
        self.assertEqual(E._printed_over_interbank('002180012345678901', E._pages([page(1, [
            [('CLABE 002 180 01234567890 1', 20000, 300000)]])])[1]), ('002180012345678901', 'interbank_number'))


def addressee_statement(fiscal=(), receipt=None):
    """An invented layout whose addressee block prints no postal line; optionally a fiscal-domicile block
    (lines given) and a fiscal receipt page naming its recipient."""
    lines = [
        [('BANCO EJEMPLO DEL NORTE, S.A., INSTITUCION DE BANCA MULTIPLE', 20000, 400000)],
        [('EMPRESA DE PRUEBA SA DE CV', 20000, 200000), ('PERIODO', 330000, 380000),
         ('DEL 01/03/2024 AL 31/03/2024', 390000, 590000)],
        [('AVENIDA DEL EJEMPLO 45', 20000, 200000), ('MONEDA', 330000, 380000), ('PESOS', 390000, 450000)],
        [('COLONIA CENTRO NORTE', 20000, 200000), ('NO. DE CUENTA', 330000, 400000), ('0012345678', 410000, 500000)],
        [('MUNICIPIO EJEMPLO', 20000, 200000)],
        [],
        *[[(text, 20000, 300000)] for text in fiscal],
        [],
        [('SALDO ANTERIOR', 330000, 430000), ('1,000.00', 500000, 560000)],
        [('SALDO FINAL', 330000, 400000), ('1,250.00', 500000, 560000)],
        [('FECHA', 20000, 60000), ('CONCEPTO', 80000, 160000), ('ABONOS', 330000, 380000),
         ('CARGOS', 410000, 460000), ('SALDO', 520000, 560000)],
    ]
    for day, text, credit, debit, balance in MOVES:
        line = [(day, 20000, 60000), (text, 80000, 300000)]
        if credit:
            line.append((credit, 380000 - 6000 * len(credit), 380000))
        if debit:
            line.append((debit, 460000 - 6000 * len(debit), 460000))
        line.append((balance, 560000 - 6000 * len(balance), 560000))
        lines.append(line)
    pages = [page(1, [line for line in lines if line] if not fiscal else [line or [('', 0, 0)] for line in lines])]
    if receipt:
        pages.append(page(2, [[('INFORMACION FISCAL', 20000, 200000)], [('Nombre del Receptor : ' + receipt, 20000, 300000)]]))
    return pages


class AddresseeConfirmationTests(unittest.TestCase):
    """r5-any-layout: an addressee block without a postal line is read only when a second printed fact
    agrees with it."""

    def holder(self, sources):
        return read_statements(sources)[0]['holder']

    def test_an_addressee_block_without_a_postal_line_is_not_read_alone(self):
        self.assertEqual(self.holder(addressee_statement()), '')

    def test_its_lines_reprinted_in_a_postal_anchored_fiscal_block_confirm_it(self):
        fiscal = ('DOMICILIO FISCAL', 'AVENIDA DEL EJEMPLO 45 INT 2', 'COLONIA CENTRO NORTE', 'MUNICIPIO EJEMPLO C.P. 06000')
        self.assertEqual(self.holder(addressee_statement(fiscal)), 'EMPRESA DE PRUEBA SA DE CV')

    def test_one_reprinted_line_is_not_enough(self):
        fiscal = ('DOMICILIO FISCAL', 'OTRA CALLE 99', 'COLONIA CENTRO NORTE', 'OTRO MUNICIPIO C.P. 06000')
        self.assertEqual(self.holder(addressee_statement(fiscal)), '')

    def test_the_fiscal_receipt_recipient_agreeing_with_the_heading_line_confirms_it(self):
        self.assertEqual(self.holder(addressee_statement(receipt='EMPRESA DE PRUEBA')), 'EMPRESA DE PRUEBA SA DE CV')
        self.assertEqual(self.holder(addressee_statement(receipt='EMPRESA DE PRUEBA SA DE CV')), 'EMPRESA DE PRUEBA SA DE CV')
        # A recipient no heading line prints, or a heading line adding more than a legal form, is not the holder.
        self.assertEqual(self.holder(addressee_statement(receipt='OTRA EMPRESA')), '')
        self.assertEqual(self.holder(addressee_statement(receipt='EMPRESA')), '')


class ScanNoiseAddressTests(unittest.TestCase):
    def holder(self, name_cell, street_cell=('CALLE FALSA 123', 20000, 150000)):
        lines = [[('BANCO EJEMPLO DEL NORTE, S.A., INSTITUCION DE BANCA MULTIPLE', 20000, 400000)],
                 [name_cell, ('PERIODO DEL 01/03/2024 AL 31/03/2024', 330000, 590000)],
                 [street_cell], [('COL CENTRO', 20000, 120000)], [('CIUDAD DE MEXICO C.P. 06000', 20000, 220000)]]
        return E.address_holder(E._pages([page(1, lines)])[1])

    def test_a_noise_glyph_left_of_the_address_edge_is_not_part_of_the_line(self):
        self.assertEqual(self.holder(('N EMPRESA DE PRUEBA SA DE CV', 2000, 200000)), 'EMPRESA DE PRUEBA SA DE CV')
        self.assertEqual(self.holder(('EMPRESA DE PRUEBA SA DE CV', 20000, 200000), ('@ CALLE FALSA 123', 2000, 150000)),
                         'EMPRESA DE PRUEBA SA DE CV')

    def test_an_initial_on_the_address_edge_is_kept_and_a_word_is_never_noise(self):
        self.assertEqual(self.holder(('J PRUEBA EJEMPLO', 20000, 200000)), 'J PRUEBA EJEMPLO')
        # A whole word left of the edge is a different column, not noise: no block.
        self.assertEqual(self.holder(('NOTA EMPRESA DE PRUEBA SA DE CV', 2000, 200000)), '')

    def test_institution_profiles_for_two_more_mexican_banks(self):
        from services.financial.statement_engine_profiles import matching_profile
        self.assertEqual(matching_profile('Scotiabank Inverlat, S.A., Institucion de Banca Multiple')['institution'],
                         'Scotiabank')
        self.assertEqual(matching_profile('Escribenos a aclaraciones@kapital.com')['institution'], 'Kapital')
        # The Kapital bank name alone (other banks' transfer lines print it) does not select the profile.
        self.assertIsNone(matching_profile('SPEI ENVIADO KAPITAL BANK'))


class SharedPageSectionTests(unittest.TestCase):
    """r5-any-layout: two currency sections on shared pages, the first one's movement lines unreadable."""

    LINES = [[('CUENTA EN PESOS', 20000, 200000)],
             [('SALDO INICIAL', 20000, 150000), ('1,000.00', 500000, 560000)],
             [('DEPOSITOS', 20000, 150000), ('500.00', 500000, 560000)],
             [('RETIROS', 20000, 150000), ('500.00', 500000, 560000)],
             [('SALDO FINAL', 20000, 150000), ('1,000.00', 500000, 560000)],
             [('SALDO INICIAL', 330000, 430000), ('1,000.00', 500000, 560000)],
             [('ABONO RECIBIDO', 80000, 300000), ('500.00', 350000, 380000), ('1,500.00', 512000, 560000)],
             [('CARGO ENVIADO', 80000, 300000), ('500.00', 428000, 460000), ('1,000.00', 512000, 560000)],
             [('TOTAL', 80000, 120000), ('500.00', 350000, 380000), ('500.00', 428000, 460000), ('1,000.00', 512000, 560000)],
             [('CUENTA EN DOLARES', 20000, 200000)],
             [('SALDO INICIAL', 20000, 150000), ('0.00', 500000, 560000)],
             [('DEPOSITOS', 20000, 150000), ('0.00', 500000, 560000)],
             [('RETIROS', 20000, 150000), ('0.00', 500000, 560000)],
             [('SALDO FINAL', 20000, 150000), ('0.00', 500000, 560000)]]

    def test_the_sections_own_opening_after_its_closing_keeps_its_table_in_the_section(self):
        pages = E._pages([page(1, self.LINES)])
        sections = E._sections(dict(pages=[1]), pages, 'dot')
        self.assertEqual([[row['text'] for row in section][-1] for section in sections][:1], ['TOTAL 500.00 500.00 1,000.00'])
        self.assertEqual(sections[1][0]['text'], 'CUENTA EN DOLARES')
        self.assertEqual(len(sections), 2)


class RoutingScopeTests(unittest.TestCase):
    """r5-any-layout: row-level scope comparisons between the engine and a library period."""

    @staticmethod
    def scoped(pages_rows):
        return dict(sources=[dict(page_number=p) for p in sorted({p for p, _ in pages_rows})],
                    section_sources=[dict(page_number=p, table_index=0, row_indices=rows) for p, rows in pages_rows])

    def by_address(self, texts):
        return {(1, 0): dict(page_number=1, table_index=0,
                             rows=[dict(row_index=i, cells=[dict(expected_text=t)]) for i, t in enumerate(texts)])}

    def test_a_library_period_is_covered_by_its_recorded_rows_not_its_pages(self):
        from services.financial.statement_engine_routing import _covers
        engine = self.scoped([(2, [5, 6, 7]), (3, [0, 1])])
        self.assertTrue(_covers(engine, self.scoped([(2, [5, 6])])))
        self.assertFalse(_covers(engine, self.scoped([(1, [3]), (2, [5])])))
        # Without a recorded row scope the pages decide, as before.
        self.assertFalse(_covers(engine, dict(sources=[dict(page_number=1), dict(page_number=2)])))

    def test_another_library_period_on_a_shared_page_is_apart_only_without_shared_value_rows(self):
        from services.financial.statement_engine_routing import _rows_apart
        texts = ['SALDO FINAL 1,000.00', 'PAGINA 1 DE 2', 'ABONO 05/03/2024', 'NOTA']
        engine = self.scoped([(1, [1, 3])])
        self.assertTrue(_rows_apart(engine, self.scoped([(1, [0, 1])]), self.by_address(texts)))
        self.assertFalse(_rows_apart(self.scoped([(1, [0])]), self.scoped([(1, [0])]), self.by_address(texts)))
        self.assertFalse(_rows_apart(self.scoped([(1, [2])]), self.scoped([(1, [2])]), self.by_address(texts)))
        self.assertFalse(_rows_apart(engine, dict(sources=[dict(page_number=1)]), self.by_address(texts)))

    def test_an_institution_named_with_or_without_a_banking_word_is_the_same(self):
        from services.financial.statement_engine_routing import _same_identity
        self.assertTrue(_same_identity('institution', 'Ejemplo', 'EJEMPLO BANCO'))
        self.assertTrue(_same_identity('institution', 'Banco Ejemplo, S.A.', 'EJEMPLO'))
        self.assertFalse(_same_identity('institution', 'Ejemplo', 'OTRO BANCO'))
        self.assertFalse(_same_identity('institution', 'BANCO', 'BANK'))
        # One issuer under its current and former names; different issuers stay different.
        self.assertTrue(_same_identity('institution', 'Ejemplo Mexico', 'EJEMPLO ANTERIOR'))
        self.assertFalse(_same_identity('institution', 'Banco del Ejemplo', 'Banco del Otro'))
        self.assertFalse(_same_identity('institution', 'Bank of Example', 'Bank of the Other'))


class ScanDamageR5Tests(unittest.TestCase):
    """r5-any-layout: further scan damage around amounts and dates, and a period printed as a cut date plus
    a day count."""

    words = ScanDamageTests.words

    def test_a_space_beside_the_decimal_mark_inside_one_cell(self):
        self.assertEqual(self.words('715 .00?'), ['715.00'])
        self.assertEqual(self.words('11,206,500. 63?'), ['11,206,500.63'])
        self.assertEqual(self.words('DIC 22 715 .00'), ['DIC', '22', '715.00'])
        # Without a printed mark nothing is joined (a count before an amount stays two words).
        self.assertEqual(self.words('2 00'), ['2', '00'])
        self.assertEqual(self.words('2 100.00'), ['2', '100.00'])

    def test_more_letter_digit_confusions_in_dates(self):
        for text in ('Q1-FEB-2024', 'L1-MAR-2024', '23-FEB~2024', '03-0CT-2024', 'I5/03/2024'):
            self.assertTrue(E.is_date_token(text), text)
        for text in ('QQ-FEB', 'L-MAR-2024', 'CL1-MAR-2024', '0CT'):
            self.assertFalse(E.is_date_token(text), text)

    def lines(self, cut='CORTE AL 31/03/2024', days='DIAS DEL PERIODO 31', printed=None):
        lines = [[('BANCO EJEMPLO DEL NORTE, S.A., INSTITUCION DE BANCA MULTIPLE', 20000, 400000)],
                 [(days, 20000, 200000)], [(cut, 20000, 200000)], [('HOJA 1 DE 2', 400000, 500000)]]
        second = [[('HOJA 2 DE 2', 400000, 500000)]] + ([[(printed, 20000, 300000)]] if printed else [])
        return E._pages([page(1, lines), page(2, second)])

    def segments(self, **kwargs):
        pages = self.lines(**kwargs)
        facts = {p: E.page_facts(rows, 'dot') for p, rows in pages.items()}
        return [(s['period'], s['pages']) for s in E._segments(pages, facts)]

    def test_a_cut_date_and_a_day_count_print_the_period(self):
        from datetime import date
        self.assertEqual(self.segments(), [((date(2024, 3, 1), date(2024, 3, 31)), [1, 2])])
        self.assertEqual(self.segments(days='DIAS DEL PERTODO 31'), [((date(2024, 3, 1), date(2024, 3, 31)), [1, 2])])
        # The period printed on a later page of the same run agrees: one statement.
        self.assertEqual(self.segments(printed='PERIODO : 01 AL 31 DE MARZO DE 2024'),
                         [((date(2024, 3, 1), date(2024, 3, 31)), [1, 2])])

    def test_a_labelled_period_of_the_same_run_wins_over_a_misread_day_count(self):
        from datetime import date
        # The derived 3-31 March is dropped: page 1 continues into page 2's printed period.
        self.assertEqual(self.segments(days='DIAS DEL PERIODO 29', printed='PERIODO : 01 AL 31 DE MARZO DE 2024'),
                         [((date(2024, 3, 1), date(2024, 3, 31)), [1, 2])])

    def test_one_fact_alone_is_not_a_period(self):
        self.assertEqual(self.segments(days='SALDO PROMEDIO'), [(None, [1, 2])])
        self.assertEqual(self.segments(cut='SUCURSAL 123'), [(None, [1, 2])])


class SecondTableTests(unittest.TestCase):
    """r5-any-layout: a table printed after the movement table's total line with other amount columns."""

    def statement(self, heading=(('FECHA', 20000, 60000), ('DESCRIPCION', 80000, 200000), ('ENTRADAS', 500000, 560000)),
                  spaced=False):
        date_word = [('F', 20000, 24000), ('E', 26000, 30000), ('C', 32000, 36000), ('H', 38000, 42000),
                     ('A', 44000, 48000)] if spaced else [('FECHA', 20000, 60000)]
        lines = [
            [('BANCO EJEMPLO DEL NORTE, S.A., INSTITUCION DE BANCA MULTIPLE', 20000, 400000)],
            [('PERIODO DEL 01/03/2024 AL 31/03/2024', 330000, 590000)],
            [('MONEDA', 330000, 380000), ('PESOS', 390000, 450000)],
            [('SALDO ANTERIOR', 330000, 430000), ('1,000.00', 500000, 560000)],
            [('SALDO FINAL', 330000, 400000), ('1,250.00', 500000, 560000)],
            date_word + [('CONCEPTO', 80000, 160000), ('ABONOS', 330000, 380000), ('CARGOS', 410000, 460000),
                         ('SALDO', 520000, 560000)],
        ]
        for day, text, credit, debit, balance in MOVES:
            line = [(day, 20000, 60000), (text, 80000, 300000)]
            if credit:
                line.append((credit, 380000 - 6000 * len(credit), 380000))
            if debit:
                line.append((debit, 460000 - 6000 * len(debit), 460000))
            line.append((balance, 560000 - 6000 * len(balance), 560000))
            lines.append(line)
        lines.append([('TOTAL', 80000, 120000), ('500.00', 350000, 380000), ('250.00', 430000, 460000),
                      ('1,250.00', 512000, 560000)])
        lines.append([('COMISIONES PENDIENTES DE PAGO', 20000, 200000)])
        lines.append(list(heading))
        lines.append([('02/FEB', 20000, 60000), ('COMISION POR MANEJO', 80000, 300000), ('50.00', 530000, 560000)])
        return [page(1, lines)]

    def test_lines_of_another_table_after_the_total_are_not_movements(self):
        st = read_statements(self.statement())[0]
        self.assertTrue(st['engine']['proved'], st['engine'])
        self.assertEqual(sum(1 for r in st['_rows'] if r['kind'] == 'transaction'), 3)

    def test_the_same_columns_again_continue_the_movement_table(self):
        heading = (('FECHA', 20000, 60000), ('CONCEPTO', 80000, 160000), ('ABONOS', 330000, 380000),
                   ('CARGOS', 410000, 460000), ('SALDO', 520000, 560000))
        st = read_statements(self.statement(heading=heading))[0]
        # The extra line is read as a movement again: the period no longer proves (fail closed).
        self.assertFalse(st['engine']['proved'])

    def test_a_letter_spaced_heading_word_is_one_word(self):
        rows = E._pages(self.statement(spaced=True))[1]
        self.assertTrue(E._is_header(next(r for r in rows if r['text'].startswith('F E C H A'))))
        self.assertEqual(E._letter_spaced([dict(t=t, line=0) for t in ('A', 'B', 'SALDO')]), [('A', 0), ('B', 0), ('SALDO', 0)])


class SectionAccountTests(unittest.TestCase):
    """r5-any-layout: a section on shared pages takes the account printed with its own opening."""

    def statement(self):
        page_one = [
            [('BANCO EJEMPLO DEL NORTE, S.A., INSTITUCION DE BANCA MULTIPLE', 20000, 400000)],
            [('PERIODO DEL 01/03/2024 AL 31/03/2024', 330000, 590000)],
            [('MONEDA', 330000, 380000), ('PESOS', 390000, 450000)],
            [('CUENTA EJEMPLO PYME', 20000, 200000), ('12-34567890-1', 210000, 300000)],
            [('SALDO INICIAL', 20000, 150000), ('1,000.00', 500000, 560000)],
            [('DEPOSITOS', 20000, 150000), ('0.00', 500000, 560000)],
            [('RETIROS', 20000, 150000), ('0.00', 500000, 560000)],
            [('SALDO FINAL', 20000, 150000), ('1,000.00', 500000, 560000)],
            # The first section's chart legend, printed after its closing line.
            [('NO. DE CUENTA', 20000, 120000), ('12-34567890-1', 130000, 220000)],
            [('PAGINA 1 DE 2', 400000, 500000)],
        ]
        page_two = [
            [('INVERSION EJEMPLO 98-76543210-2', 20000, 250000), ('ESTADO ENVIADO POR CORREO', 300000, 500000)],
            [('SALDO INICIAL', 20000, 150000), ('0.00', 500000, 560000)],
            [('DEPOSITOS', 20000, 150000), ('0.00', 500000, 560000)],
            [('RETIROS', 20000, 150000), ('0.00', 500000, 560000)],
            [('SALDO FINAL', 20000, 150000), ('0.00', 500000, 560000)],
            [('PAGINA 2 DE 2', 400000, 500000)],
        ]
        return [page(1, page_one), page(2, page_two)]

    def test_a_legend_left_on_an_earlier_page_does_not_name_the_next_section(self):
        profile = dict(name='invented-bank', match=dict(any=['banco ejemplo del norte']), account_heading=True)
        statements = read_statements(self.statement(), profile=profile)
        self.assertEqual([st['account_reference'] for st in statements], ['12-34567890-1', '98-76543210-2'])

    def test_a_heading_account_is_read_from_one_whole_line_of_a_cell(self):
        row = E._pages([page(1, [[('DETALLE DE MOVIMIENTOS\nCUENTA EJEMPLO PYME 12-34567890-1', 20000, 300000)]])])[1][0]
        self.assertEqual(E._heading_account(row), '12-34567890-1')


class CreditLineTests(unittest.TestCase):
    """r5-any-layout: a credit-line statement (amounts owed) with its period over two lines, a detached minus
    sign and the credit's number as its account."""

    def statement(self, minus=True, period=True):
        lines = [
            [('BANCO EJEMPLO DEL NORTE, S.A., INSTITUCION DE BANCA MULTIPLE', 20000, 400000)],
            [('NO. DE CREDITO', 300000, 380000), ('1234', 400000, 430000), ('5678', 435000, 465000),
             ('9012', 470000, 500000), ('3456', 505000, 535000)],
            [('EMPRESA DE PRUEBA SA DE CV', 20000, 200000)],
            [('CALLE FALSA 123', 20000, 150000)],
            [('COL CENTRO', 20000, 120000)],
            [('CIUDAD DE MEXICO C.P. 06000', 20000, 220000)],
            [('MONEDA NACIONAL', 20000, 120000)],
            [('SALDO INICIAL DEL PERIODO', 200000, 300000), ('+$', 323000, 336000)]
            + ([('-', 360000, 362000)] if minus else []) + [('120.45', 389000, 420000)],
            [('DISPOSICIONES', 200000, 300000), ('+$', 323000, 336000), ('0.00', 398000, 415000)],
            [('PAGOS', 200000, 300000), ('-$', 323000, 336000), ('0.00', 398000, 415000)],
            [('PAGO MINIMO', 420000, 480000), ('0.00', 560000, 590000)],
            [('SALDO AL CORTE', 200000, 260000), ('$', 333000, 337000), ('120.45-', 388000, 418000)],
            [('FECHA', 30000, 60000), ('CONCEPTO', 200000, 250000), ('CARGOS', 410000, 450000), ('ABONOS', 510000, 550000)],
            [('TASA ANUAL', 50000, 100000), ('PERIODO', 520000, 560000)],
        ]
        if period:
            lines += [[('0.00 %', 60000, 90000), ('DEL 03/01/26', 510000, 565000)], [('AL 02/02/26', 513000, 561000)]]
        return [page(1, lines)]

    def test_a_quiet_credit_line_with_a_detached_minus_proves(self):
        from datetime import date
        st = read_statements(self.statement())[0]
        self.assertEqual((st['period_start'], st['period_end']), (date(2026, 1, 3).isoformat(), date(2026, 2, 2).isoformat()))
        self.assertEqual([r['fields']['balance'] for r in st['_rows'] if r['kind'] == 'balance'], ['-12045', '-12045'])
        self.assertTrue(st['engine']['proved'], st['engine'])
        self.assertEqual((st['account_reference'], st['balance_convention']), ('1234567890123456', 'liability_owed'))

    def test_without_the_minus_the_balances_disagree_and_it_holds(self):
        self.assertFalse(read_statements(self.statement(minus=False))[0]['engine']['proved'])

    def test_one_period_line_alone_is_not_a_period(self):
        self.assertEqual(read_statements(self.statement(period=False))[0]['period_start'], '')

    def test_a_name_tail_above_an_address_block_withholds_its_top_line(self):
        lines = [[('RESAS SA DE CV', 120000, 200000)],
                 [('AV SAN EJEMPLO', 20000, 150000)], [('COL CENTRO', 20000, 120000)],
                 [('06000 CIUDAD DE MEXICO', 20000, 220000)]]
        self.assertEqual(E.address_holder(E._pages([page(1, lines)])[1]), '')
        # Other text printed above a block whose top line is its name does not withhold it.
        named = [[('CLIENTE PREFERENTE', 120000, 200000)], [('EMPRESA DE PRUEBA SA DE CV', 20000, 200000)]] + lines[1:]
        self.assertEqual(E.address_holder(E._pages([page(1, named)])[1]), 'EMPRESA DE PRUEBA SA DE CV')


class LostDayHeadingTests(unittest.TestCase):
    """r5-any-layout: a day column whose heading word the scan lost; column-rule noise after amounts."""

    def statement(self, heading=True, credit='500.00', tail=''):
        lines = [
            [('BANCO EJEMPLO DEL NORTE, S.A., INSTITUCION DE BANCA MULTIPLE', 20000, 400000)],
            [('PERIODO DEL 01/03/2024 AL 31/03/2024', 330000, 590000)],
            [('MONEDA', 330000, 380000), ('PESOS', 390000, 450000)],
            [('SALDO INICIAL', 330000, 430000), ('1,000.00', 500000, 560000)],
            [('DEPOSITOS', 330000, 430000), ('500.00', 500000, 560000)],
            [('RETIROS', 330000, 430000), ('500.00', 500000, 560000)],
            [('SALDO FINAL', 330000, 430000), ('1,000.00', 500000, 560000)],
        ]
        if heading:
            lines.append([('CONCEPTO', 150000, 200000), ('DEPOSITOS', 300000, 350000), ('RETIROS', 380000, 430000)])
        lines += [
            [('5', 20000, 30000), ('ABONO A CUENTA', 150000, 260000), (credit + tail, 290000, 350000),
             ('1,500.00', 520000, 560000)],
            [('20', 20000, 30000), ('CARGO A CUENTA', 150000, 260000), ('500.00', 400000, 430000),
             ('1,000.00', 520000, 560000)],
            [('TOTAL', 100000, 140000), ('500.00', 320000, 350000), ('500.00', 400000, 430000)],
        ]
        return [page(1, lines)]

    def test_day_numbered_lines_under_a_dateless_heading_are_movements(self):
        st = read_statements(self.statement())[0]
        self.assertTrue(st['engine']['proved'], st['engine'])
        self.assertEqual([(r['fields']['date'], r['fields']['direction']) for r in st['_rows'] if r['kind'] == 'transaction'],
                         [('2024-03-05', 'credit'), ('2024-03-20', 'debit')])

    def test_without_the_heading_no_day_column_is_inferred(self):
        self.assertFalse(read_statements(self.statement(heading=False))[0]['engine']['proved'])

    def test_a_column_rule_or_a_lone_parenthesis_after_an_amount_is_noise(self):
        self.assertTrue(read_statements(self.statement(tail='|'))[0]['engine']['proved'])
        self.assertTrue(read_statements(self.statement(tail=')'))[0]['engine']['proved'])
        # A document printing amounts in parentheses keeps them meaningful: the lone ')' stays unread.
        sources = self.statement(tail=')')
        sources[0]['rows'][0]['cells'].append(cell('(12.00)', 450000, 500000, 40000, 1))
        self.assertFalse(read_statements(sources)[0]['engine']['proved'])


class ChartScaleTests(unittest.TestCase):
    """r5-any-layout: a chart's axis printed beside the summary labels is not a set of amounts."""

    def statement(self, ticks=('0.00', '-75.00', '150.00', '-225.00', '300.00', '375.00')):
        labels = ['(+) DEPOSITOS', '', '(+) INTERESES', '(-) RETIROS', '(-) COMISIONES', '']
        lines = [
            [('BANCO EJEMPLO DEL NORTE, S.A., INSTITUCION DE BANCA MULTIPLE', 20000, 400000)],
            [('PERIODO DEL 01/03/2024 AL 31/03/2024', 330000, 590000)],
            [('MONEDA', 330000, 380000), ('PESOS', 390000, 450000)],
            [('SALDO INICIAL', 20000, 150000), ('$1,000.00', 190000, 240000)],
        ]
        for text, tick in zip(labels, ticks):
            lines.append(([(text, 20000, 150000)] if text else []) + [(tick, 270000, 292000)])
        lines += [
            [('(=) SALDO FINAL DE LA CUENTA', 20000, 160000), ('$750.00', 190000, 240000)],
            [('FECHA', 20000, 60000), ('CONCEPTO', 80000, 160000), ('DEPOSITO', 400000, 450000), ('RETIRO', 460000, 510000),
             ('SALDO', 540000, 580000)],
            [('15 MAR', 20000, 60000), ('COBRO DE COMISION', 80000, 200000), ('$250.00', 480000, 508000),
             ('$750.00', 540000, 582000)],
        ]
        return [page(1, lines)]

    def test_axis_ticks_beside_summary_labels_are_not_totals(self):
        st = read_statements(self.statement())[0]
        self.assertTrue(st['engine']['proved'], st['engine'])
        self.assertEqual([r['fields']['balance'] for r in st['_rows'] if r['kind'] == 'balance'], ['100000', '75000'])

    def test_values_without_a_constant_step_stay_amounts(self):
        st = read_statements(self.statement(ticks=('0.00', '75.00', '120.00', '225.00', '300.00', '375.00')))[0]
        self.assertFalse(st['engine']['proved'])


class ScanDamageRound2Tests(unittest.TestCase):
    words = ScanDamageTests.words

    def test_separators_detached_onto_the_following_groups(self):
        self.assertEqual(self.words('300 ,000 ,00'), ['300,000,00'])
        self.assertEqual(self.words('1,724,615 ,.38'), ['1,724,615.38'])
        # Never a thousands group invented (cents before a group stay apart from it), never a count joined.
        self.assertEqual(self.words('300 ,00 ,000'), ['300,00', ',000'])
        self.assertEqual(self.words('2 100,000.00'), ['2', '100,000.00'])

    def test_a_dot_glued_to_a_word_inside_a_balance_label(self):
        self.assertEqual(E._role_of('SALDO. INICIAL', False), 'opening')
        self.assertEqual(E._role_of('SALDO, FINAL', False), 'closing')
        self.assertEqual(E._role_of('SALDO. PROMEDIO', False), E._role_of('SALDO PROMEDIO', False))
        self.assertIsNone(E._role_of('SALDO. EJEMPLO', False))


class ServedScopeTests(unittest.TestCase):
    """r5-any-layout: a period the engine serves on pages shared with another library period keeps no row,
    and no page region, that would make the other period read as already imported."""

    def sources(self):
        lines = [[('LINEA %d' % i, 20000, 200000)] for i in range(10)]
        pages = [page(1, lines), page(2, lines)]
        for source in pages:
            for row in source['rows']:
                for c in row['cells']:
                    c['locator']['space'] = 'pdf_displayed'
        return pages

    @staticmethod
    def scoped(pages_rows):
        return dict(section_sources=[dict(page_number=p, table_index=0, row_indices=rows) for p, rows in pages_rows])

    def test_shared_footer_rows_are_left_to_the_other_period(self):
        from services.financial.statement_engine_routing import _own_scope
        other = self.scoped([(1, list(range(0, 10)))])
        engine = self.scoped([(1, [8, 9]), (2, [0, 1, 2])])
        self.assertEqual(_own_scope(engine, [other], self.sources()),
                         [dict(page_number=2, table_index=0, row_indices=[0, 1, 2])])

    def test_rows_below_the_other_period_on_its_page_are_kept(self):
        from services.financial.statement_engine_routing import _own_scope
        other = self.scoped([(1, [0, 1, 2, 3])])
        engine = self.scoped([(1, [5, 6, 7])])
        self.assertEqual(_own_scope(engine, [other], self.sources()), engine['section_sources'])

    def test_rows_inside_the_other_periods_region_refuse_the_replacement(self):
        from services.financial.statement_engine_routing import _own_scope
        other = self.scoped([(1, [0, 1, 2, 6, 7])])
        engine = self.scoped([(1, [4, 5])])
        self.assertIsNone(_own_scope(engine, [other], self.sources()))


def box(text, x0, x1, y0, y1, column):
    """One drawn cell holding every printed line of a box (no row rules), as the drawn geometry stores it."""
    return dict(column_index=column, expected_text=text,
                locator=dict(kind='page_rectangle', page=1, rect=[x0, y0, x1, y1], page_size=[WIDTH, HEIGHT],
                             units='millipoints', space='pdf_displayed'))


SUMMARY = ('Previous Balance $1,000.00\n+ New Purchases $240.00\n- Payments $300.00\n'
           '+/- Credits, Fees & Adjustments (net) $35.00\n+/- Interest Charge (net) $12.50')
LINES = ['04/03/2024 04/03/2024 REF0001 PAYMENT - THANK YOU ($300.00)',
         '04/10/2024 04/11/2024 REF0002 HARDWARE STORE $240.00',
         'SAMPLE CITY ST',
         'FEES',
         '04/15/2024 04/15/2024 LATE FEE $35.00',
         'TOTAL FEES FOR THIS PERIOD $35.00',
         'INTEREST CHARGED',
         '04/30/2024 04/30/2024 INTEREST CHARGE ON PURCHASES $12.50',
         'TOTAL INTEREST FOR THIS PERIOD $12.50',
         '2024 Totals Year-to-Date',
         'Total Fees Charged in 2024 $70.00',
         'Total Interest Charged in 2024 $25.00']


def boxed_card(*, summary=SUMMARY, lines=LINES, closing='04/30/2024', days='30', new_balance='$987.50',
               payment_box_balance='$987.50', page_number='PAGE 1 of 1', number=1, account='1234 5678 9012 3456',
               stub_below=False, heading_name=True):
    """An invented US card layout: a summary box beside a payment box (one stored row, a multi-line cell
    each) and a transaction table whose body is ONE cell of printed lines, in sections with their totals."""
    drawn = dict(case_id='c', evidence_file_id='f', page_number=number, table_index=0, source_revision='d%d' % number,
                 table_source='drawn_geometry', rows=[
                     dict(row_index=0, cells=[box('Summary of Account Activity', 36000, 255000, 300000, 312000, 0),
                                              box('Payment Information', 260000, 490000, 300000, 312000, 2)]),
                     dict(row_index=1, cells=[box(summary, 36000, 255000, 312000, 372000, 0),
                                              box('New Balance %s\nTotal Minimum Payment Due $40.00\n'
                                                  'Payment Due Date 05/25/2024' % payment_box_balance,
                                                  260000, 490000, 312000, 372000, 2)]),
                     dict(row_index=2, cells=[box('New Balance %s\nCredit Limit $2,000.00\nAvailable Credit $1,012.50\n'
                                                  'Days in Billing Period %s' % (new_balance, days),
                                                  36000, 255000, 372000, 420000, 0)])])
    body_top = 452000
    table = dict(case_id='c', evidence_file_id='f', page_number=number, table_index=1, source_revision='t%d' % number,
                 table_source='drawn_geometry', rows=[
                     dict(row_index=0, cells=[box('Transaction Summary', 36000, 490000, 430000, 440000, 0)]),
                     dict(row_index=1, cells=[box('Tran Date', 36000, 89000, 440000, 452000, 0),
                                              box('Post Date', 89000, 142000, 440000, 452000, 1),
                                              box('Reference Number', 142000, 245000, 440000, 452000, 2),
                                              box('Description', 245000, 413000, 440000, 452000, 3),
                                              box('Amount', 413000, 490000, 440000, 452000, 4)]),
                     dict(row_index=2, cells=[box('\n'.join(lines), 36000, 490000, body_top,
                                                  body_top + 9000 * len(lines), 0)])])
    heading = [[('EXAMPLE CARD BANK', 40000, 200000)] + ([('JANE Q SAMPLE', 264000, 323000)] if heading_name else []),
               [('Account Number : %s' % account, 264000, 408000)],
               [('Statement Closing Date: %s' % closing, 264000, 392000)],
               [(page_number, 400000, 460000)]]
    text = page(number, heading, table=2)
    for row in text['rows']:  # above the summary box
        for c in row['cells']:
            c['locator']['rect'][1] -= 20000
            c['locator']['rect'][3] -= 20000
    stub = [[('JANE Q SAMPLE', 49000, 108000)], [('100 MAIN ST', 49000, 143000)],
            [('SPRINGFIELD IL 62701', 49000, 160000), ('Make Payment to: EXAMPLE CARD BANK', 244000, 382000)]]
    stub_page = page(number, stub, table=3)
    top = 800000 if stub_below else 200000
    for index, row in enumerate(stub_page['rows']):
        for c in row['cells']:
            c['locator']['rect'][1] = top + index * 8400
            c['locator']['rect'][3] = top + index * 8400 + 8000
    return [drawn, table, text, stub_page]


def rows_of(statement):
    return sorted((r['fields'].get('date'), r['fields']['direction'], r['fields']['amount_minor'])
                  for r in statement['_rows'] if r['kind'] == 'transaction' and not r['excluded'])


class BoxedCardTests(unittest.TestCase):
    """r6: a card table stored as one multi-line cell, a closing date with the days in the billing period,
    net summary lines, section totals and a year-to-date block (any issuer; synthetic fixtures)."""

    def read(self, **kwargs):
        statements = read_statements(boxed_card(**kwargs))
        self.assertEqual(len(statements), 1)
        return statements[0]

    def test_each_printed_line_of_the_body_cell_is_read_and_the_period_proves(self):
        st = self.read()
        self.assertTrue(st['engine']['proved'], st['engine'])
        self.assertEqual(rows_of(st), [('2024-04-03', 'credit', '30000'), ('2024-04-10', 'debit', '24000'),
                                       ('2024-04-15', 'debit', '3500'), ('2024-04-30', 'debit', '1250')])
        self.assertEqual(st['balance_convention'], 'liability_owed')
        balances = {r['fields']['description']: r['fields']['balance'] for r in st['_rows'] if r['kind'] == 'balance'}
        self.assertEqual(balances, {'Opening Balance': '100000', 'Closing Balance': '98750'})
        purchase = next(r for r in st['_rows'] if r['fields'].get('amount_minor') == '24000')
        # The wrapped line joins its movement; the section heading below it does not.
        self.assertEqual(purchase['fields']['description'], 'REF0002 HARDWARE STORE SAMPLE CITY ST')
        self.assertEqual(purchase['fields']['booking_date'], '2024-04-11')
        # One row per printed line, each citing its own line of the stored cell.
        self.assertEqual(purchase['id'], '1:1:2:line1')
        self.assertEqual(purchase['source_cells'][0]['expected_text'], LINES[1])
        self.assertEqual(purchase['source_cells'][0]['cell_line'], dict(line=1, lines=len(LINES)))
        # The section totals are the review's scoped controls over the lines under their headings.
        totals = {r['fields']['total_scope']: r['fields']['balance'] for r in st['_rows'] if r['kind'] == 'statement_total'}
        self.assertEqual(totals, {'fee': '3500', 'interest': '1250'})
        groups = {r['fields']['amount_minor']: r['fields'].get('charge_group') for r in st['_rows'] if r['kind'] == 'transaction'}
        self.assertEqual(groups, {'30000': None, '24000': None, '3500': 'fee', '1250': 'interest'})
        from services.financial.statement_review_checks import check_statement_rows
        checks = {c['kind']: c['status'] for c in check_statement_rows(st['_rows'], liability=True)['checks']}
        self.assertEqual((checks['fee_total'], checks['interest_total'], checks['closing_balance']),
                         ('matches', 'matches', 'matches'))

    def test_the_start_is_derived_from_the_printed_days_never_printed(self):
        st = self.read()
        self.assertEqual((st['period_start'], st['period_end']), ('2024-04-01', '2024-04-30'))
        self.assertEqual(st['period_start_basis'], 'printed_day_count')
        self.assertEqual(st['printed_closing_date'], '2024-04-30')

    def test_year_to_date_lines_are_neither_rows_nor_controls(self):
        st = self.read()
        texts = ' '.join(r['fields'].get('description', '') for r in st['_rows'] if not r['excluded'])
        self.assertNotIn('2024', texts)
        self.assertEqual(len([r for r in st['_rows'] if r['kind'] == 'transaction']), 4)

    def test_a_section_total_that_differs_from_its_lines_holds(self):
        lines = list(LINES)
        lines[5] = 'TOTAL FEES FOR THIS PERIOD $36.00'
        st = self.read(lines=lines)
        self.assertFalse(st['engine']['proved'])
        self.assertEqual(st['engine']['reason'], 'printed_total_differs')

    def test_a_net_summary_line_that_differs_holds(self):
        st = self.read(summary=SUMMARY.replace('(net) $12.50', '(net) $12.60'))
        self.assertFalse(st['engine']['proved'])
        self.assertEqual(st['engine']['reason'], 'printed_total_differs')

    def test_a_credit_the_payments_line_does_not_cover_holds(self):
        # A return credited in the main section: payments printed 300.00, credits read 300.00 + 20.00.
        lines = list(LINES)
        lines.insert(2, '04/12/2024 04/12/2024 REF0003 RETURN ($20.00)')
        st = self.read(lines=lines, summary=SUMMARY.replace('(net) $35.00', '(net) $15.00'), new_balance='$967.50')
        self.assertFalse(st['engine']['proved'])

    def test_the_payment_box_beside_the_summary_is_never_a_control(self):
        st = self.read(payment_box_balance='$5.00')
        self.assertTrue(st['engine']['proved'], st['engine'])
        closing = next(r for r in st['_rows'] if r['fields'].get('description') == 'Closing Balance')
        self.assertEqual((closing['fields']['balance'], closing['row_index']), ('98750', 2))

    def test_an_ambiguous_closing_date_needs_the_profiles_date_order(self):
        lines = [line.replace('04/30/2024', '04/11/2024').replace('04/15/2024', '04/05/2024') for line in LINES]
        self.assertFalse(read_statements(boxed_card(lines=lines, closing='04/11/2024', days='31'))[0]['engine']['proved'])
        profile = dict(name='test-card', match=dict(any=['example card bank']), date_order='mdy')
        st = read_statements(boxed_card(lines=lines, closing='04/11/2024', days='31'), profile=profile)[0]
        self.assertTrue(st['engine']['proved'], st['engine'])
        self.assertEqual((st['period_start'], st['period_end']), ('2024-03-12', '2024-04-11'))

    def test_pages_unread_after_the_tables_printed_end_do_not_hold(self):
        st = self.read(page_number='PAGE 1 of 2')
        self.assertTrue(st['engine']['proved'], st['engine'])
        self.assertTrue(st['engine']['pages_unread_after_table'])
        # Without the year-to-date block the table's end is not printed: the missing page may hold movements.
        st = self.read(page_number='PAGE 1 of 2', lines=LINES[:9])
        self.assertFalse(st['engine']['proved'])
        self.assertEqual(st['engine']['reason'], 'pages_missing')

    def test_a_previous_cycle_in_the_same_file_must_end_the_day_before(self):
        first = boxed_card()
        second = boxed_card(number=2, closing='05/30/2024', days='29', lines=[line.replace('04/', '05/') for line in LINES])
        for source in second:
            for row in source['rows']:
                for c in row['cells']:
                    c['locator']['page'] = 2
        statements = read_statements(first + second)
        later = next(st for st in statements if st['period_end'] == '2024-05-30')
        # 30 May less 29 days is 2 May: the previous cycle closed on 30 April, so 1 May would follow it.
        self.assertFalse(later['engine']['proved'])
        self.assertEqual(later['engine']['reason'], 'period_start_contradicted')
        second = boxed_card(number=2, closing='05/30/2024', days='30', lines=[line.replace('04/', '05/') for line in LINES])
        for source in second:
            for row in source['rows']:
                for c in row['cells']:
                    c['locator']['page'] = 2
        later = next(st for st in read_statements(first + second) if st['period_end'] == '2024-05-30')
        self.assertTrue(later['engine']['proved'], later['engine'])
        self.assertEqual(later['period_start'], '2024-05-01')

    def test_a_dated_line_without_its_amount_keeps_the_cell_whole(self):
        lines = ['04/10/2024 04/11/2024 REF0002 HARDWARE STORE', 'SAMPLE CITY ST $240.00']
        rows = E._pages(boxed_card(lines=lines))[1]
        self.assertFalse(any('line' in r['raw'] for r in rows))

    def test_holder_from_the_stub_below_the_movements_when_printed_above_them(self):
        self.assertEqual(self.read(stub_below=True)['holder'], 'JANE Q SAMPLE')
        self.assertEqual(self.read(stub_below=True, heading_name=False)['holder'], '')

    def test_unlocated_rows_hold_only_when_they_could_be_a_movement_or_a_control(self):
        sources = boxed_card()
        sources.append(dict(case_id='c', evidence_file_id='f', page_number=1, table_index=4, source_revision='u',
                            table_source='drawn_geometry', rows=[dict(row_index=0, cells=[
                                dict(column_index=0, expected_text='Purchases\nPromotional', locator=dict(kind='unlocated')),
                                dict(column_index=1, expected_text='$100.00\n$0.00', locator=dict(kind='unlocated'))])]))
        self.assertTrue(read_statements(sources)[0]['engine']['proved'])
        sources[-1]['rows'][0]['cells'][0]['expected_text'] = '04/20/2024 SHOP\nPromotional'
        st = read_statements(sources)[0]
        self.assertFalse(st['engine']['proved'])
        self.assertEqual(st['engine']['reason'], 'no_geometry')


def _r(text, x1):
    """A right-aligned amount cell ending at ``x1``."""
    return (text, x1 - 6000 * len(text), x1)


def credit_union_statement(*, redacted=False, quiet_line='No Transactions This Period', appendix=True,
                           dividend=True, loc_credit_limit=True):
    """An invented US credit-union 'statement of account': several account sections, each headed
    '<product> - <last digits>', a summary page, a check list after each table, a production's running page
    stamp on every page, and an appended record page after the statement's last numbered page."""
    head = lambda n: [[('Page %d of 2' % n, 480000, 560000)],
                      [('Example Credit Union', 20000, 150000), ('Statement Period', 400000, 480000)],
                      [('PO Box 1 * Sometown, ST 00000', 20000, 200000), ('01/17/24 - 02/16/24', 400000, 490000)]]
    footer = lambda n: [[('Example Federal Credit Union', 70000, 170000), ('Page %d of 9' % n, 300000, 350000)]]
    money_head = [('Date', 14000, 31000), ('Transaction Detail', 43000, 111000), ('Amount($)', 431000, 471000),
                  ('Balance($)', 557000, 597000)]
    first = head(1) + [[('Statement of Account', 250000, 360000)], [('JANE Q SAMPLE', 68000, 176000)],
                       [('Summary of your deposit accounts', 14000, 213000)],
                       [('Totals', 14000, 37000), _r('$620.00', 176000)]] + footer(3)
    rows = [[('01-17', 14000, 35000), ('Beginning Balance', 43000, 110000), _r('100.00', 594000)]]
    if redacted:
        rows += [[('01-18', 14000, 35000)], [('01-19', 14000, 35000)]]
    rows += [[('01-20', 14000, 35000), ('Deposit', 43000, 74000), _r('50.00', 471000), _r('150.00', 594000)],
             [('01-25', 14000, 35000), ('POS Debit - Debit Card 9999 Transaction 01-24-24 EXAMPLE STORE', 43000, 330000)],
             [('Somewhere ST', 43000, 100000), _r('25.00-', 475000), _r('125.00', 594000)],
             [('02-01', 14000, 35000), ('Check 101', 43000, 85000), _r('5.00-', 475000), _r('120.00', 594000)],
             [('02-16', 14000, 35000), ('Ending Balance', 43000, 102000), _r('120.00', 594000)]]
    if dividend:
        rows.append([('Your account earned $0.00 for the dividend period from 01-01-2024 through 01-31-2024', 14000, 560000)])
    rows += [[('Items Paid', 14000, 59000)],
             [('Date', 17000, 35000), ('Item', 140000, 156000), ('Amount($)', 226000, 266000),
              ('Date', 316000, 334000), ('Item', 439000, 455000), ('Amount($)', 525000, 565000)],
             [('02-01', 17000, 38000), ('000101 - Check', 116000, 177000), _r('5.00', 266000)],
             [('Checking Line of Credit - 1111', 14000, 200000)]]
    if loc_credit_limit:
        rows.append([('Credit Limit', 14000, 54000), ('$1,000.00', 137000, 172000)])
    rows += [[('Date', 14000, 31000), ('Transaction Detail', 43000, 111000), ('Amount($)', 248000, 287000),
              ('Balance ($)', 555000, 597000)],
             [('01-17', 14000, 35000), ('Beginning Balance', 43000, 110000), _r('0.00', 594000)],
             [(quiet_line, 200000, 400000)] if quiet_line else [],
             [('02-16', 14000, 35000), ('Ending Balance', 43000, 102000), _r('0.00', 594000)],
             [('Membership Savings - 2222', 14000, 200000)], money_head,
             [('01-17', 14000, 35000), ('Beginning Balance', 43000, 110000), _r('500.00', 594000)],
             [(quiet_line, 200000, 400000)] if quiet_line else [],
             [('02-16', 14000, 35000), ('Ending Balance', 43000, 102000), _r('500.00', 594000)]]
    second = head(2) + [[('Statement of Account', 32000, 125000)], [('For JANE Q SAMPLE', 32000, 137000)],
                        [('Everyday Checking - 1111', 14000, 200000)], money_head] + [r for r in rows if r] + footer(4)
    pages = [page(1, first), page(2, second)]
    if appendix:
        pages.append(page(3, [[('Teller record', 20000, 120000)],
                              [('01/20/2024', 20000, 80000), ('Deposit', 100000, 150000), _r('12.00', 300000)]] + footer(5)))
    return pages


CREDIT_UNION_PROFILE = dict(name='invented-credit-union', match=dict(all=['example federal credit union', 'statement of account']),
                            institution='Example Credit Union', currency='USD', account_suffix_heading=True,
                            holder_heading=dict(title=['STATEMENT OF ACCOUNT'], prefix='FOR'))


class MultiAccountStatementTests(unittest.TestCase):
    """Several accounts in one printed statement (A3, A7, B1, B7, C5, E4, E9)."""

    def sections(self, sources, profile=CREDIT_UNION_PROFILE):
        return [st for st in read_statements(sources, profile=profile) if st['period_start']]

    def moves(self, statement):
        return [(r['fields'].get('date'), r['fields']['direction'], r['fields']['amount_minor'], r['fields'].get('balance'))
                for r in statement['_rows'] if r['kind'] == 'transaction' and not r['excluded']]

    def test_each_account_section_is_read_with_its_own_identity(self):
        checking, line, savings = self.sections(credit_union_statement())
        self.assertEqual((checking['period_start'], checking['period_end']), ('2024-01-17', '2024-02-16'))
        self.assertTrue(checking['engine']['proved'], checking['engine'])
        self.assertEqual(checking['balance_convention'], 'asset_balance')  # the credit line's limit is not its own
        self.assertEqual(self.moves(checking), [('2024-01-20', 'credit', '5000', '15000'),
                                                ('2024-01-25', 'debit', '2500', '12500'),
                                                ('2024-02-01', 'debit', '500', '12000')])
        self.assertEqual([(s['account_reference'], s['holder'], s['currency']) for s in (checking, savings)],
                         [('Everyday Checking 1111', 'JANE Q SAMPLE', 'USD'), ('Membership Savings 2222', 'JANE Q SAMPLE', 'USD')])
        # The appended record page after the statement's last numbered page is not part of it.
        self.assertNotIn(3, savings['page_numbers'])

    def test_a_printed_no_transactions_line_proves_a_quiet_section(self):
        _, _, savings = self.sections(credit_union_statement())
        self.assertTrue(savings['engine']['proved'], savings['engine'])
        self.assertEqual(savings['engine']['basis'], 'printed_no_transactions')
        _, _, unprinted = self.sections(credit_union_statement(quiet_line=None))
        self.assertFalse(unprinted['engine']['proved'])

    def test_a_credit_line_sharing_the_deposit_accounts_number_is_its_own_account(self):
        checking, line, _ = self.sections(credit_union_statement())
        self.assertEqual((line['account_reference'], line['balance_convention']), ('Checking Line of Credit 1111', 'liability_owed'))
        self.assertTrue(line['engine']['proved'], line['engine'])
        self.assertEqual(line['account_reference_kind'], 'credit_line')
        self.assertNotIn('account_reference_kind', checking)
        from services.financial.accounts import AccountDraft
        key = lambda st: AccountDraft.observed(institution_name='Example Federal Credit Union',
            identifier_as_printed=st['account_reference'], metadata=dict(account_reference_kind=st.get('account_reference_kind'))).identity()
        self.assertNotEqual(key(line).key, key(checking).key)

    def test_switched_off_a_credit_line_sharing_the_deposit_accounts_number_is_held(self):
        # The switch is process-wide; the reading caches are keyed on the sources only.
        with mock.patch.object(E, 'SHARED_NUMBER_CREDIT_LINES_SEPARATE', False), \
                mock.patch.object(E, '_READINGS', E.OrderedDict()), mock.patch.object(E, '_LIVE_READINGS', E.OrderedDict()):
            _, line, _ = self.sections(credit_union_statement())
        self.assertFalse(line['engine']['proved'])
        self.assertEqual(line['engine']['reason'], 'account_shared')
        self.assertTrue(any(r.get('engine_hold') == 'account_shared' for r in line['_rows']))
        self.assertNotIn('account_reference_kind', line)

    def test_redacted_rows_never_prove(self):
        checking = self.sections(credit_union_statement(redacted=True))[0]
        self.assertFalse(checking['engine']['proved'])
        self.assertEqual(checking['engine']['reason'], 'line_without_content')

    def test_an_accrual_period_is_not_the_statement_period(self):
        self.assertEqual(E.period_ranges('for the dividend period from 01-01-2024 through 01-31-2024'),
                         [(E.date(2024, 1, 1), E.date(2024, 1, 31))])
        facts = E.page_facts(E._pages(credit_union_statement())[2], 'dot')
        self.assertEqual(facts['periods'], {(E.date(2024, 1, 17), E.date(2024, 2, 16))})
        self.assertEqual(facts['labelled_periods'], {(E.date(2024, 1, 17), E.date(2024, 2, 16))})

    def test_the_productions_page_stamp_is_set_aside_only_beside_the_statements_own_numbering(self):
        pages = E._pages(credit_union_statement())
        facts = {p: E.page_facts(rows, 'dot') for p, rows in pages.items()}
        E._drop_file_numbering(facts)
        self.assertEqual([facts[p]['numbering'] for p in (1, 2, 3)], [{(1, 2)}, {(2, 2)}, set()])
        # A file numbering printed alone (no statement numbering beside it) is kept.
        alone = {p: dict(numbering={(p, 9)}) for p in (1, 2, 3)}
        E._drop_file_numbering(alone)
        self.assertEqual([alone[p]['numbering'] for p in (1, 2, 3)], [{(1, 9)}, {(2, 9)}, {(3, 9)}])

    def test_without_the_profile_no_section_takes_another_sections_account(self):
        for st in self.sections(credit_union_statement(), profile=None):
            self.assertIn(st['account_reference'], ('',), st['account_reference'])

    def test_two_line_entries_need_the_amount_directly_below_in_the_description_band(self):
        sources = credit_union_statement()
        rows = sources[1]['rows']
        index = next(i for i, r in enumerate(rows) if r['cells'][0]['expected_text'] == 'Somewhere ST')
        rows[index]['cells'][0]['locator']['rect'][0] = 2000  # starts left of the description band
        checking = self.sections(sources)[0]
        self.assertFalse(checking['engine']['proved'])

    def test_the_printed_no_transactions_line_is_source_proof_bound_to_the_balances(self):
        from services.financial.statement_engine import propose_engine_statement
        from services.financial.statement_printed_no_activity import printed_line_evidence
        from services.financial.statement_admission import source_proves_no_activity
        sources = credit_union_statement()
        savings = self.sections(sources)[2]
        public = {k: v for k, v in savings.items() if k != '_rows'}
        public['engine'] = dict(public['engine'], no_transactions_row=list(public['engine']['no_transactions_row']))
        with mock.patch('services.financial.statement_engine_profiles.PROFILES', (CREDIT_UNION_PROFILE,)):
            rows = propose_engine_statement(sources, 'USD', public)['rows']
        evidence = printed_line_evidence(rows, public, 'USD', sources, family='generic')
        self.assertTrue(evidence['verified'], evidence)
        self.assertEqual((evidence['basis'], evidence['zero_total_row_ids'], evidence['balance_minor']),
                         ('printed_no_transactions', [], '50000'))
        raw = dict(rows=[dict(id=r['id'], excluded=r['excluded'], balance_minor=r['fields'].get('balance')) for r in rows],
                   currency='USD', period_start=public['period_start'], period_end=public['period_end'])
        self.assertTrue(source_proves_no_activity(evidence, raw))
        edited = dict(raw, rows=[dict(r, balance_minor='1') if r['id'] == evidence['closing_row_id'] else r for r in raw['rows']])
        self.assertFalse(source_proves_no_activity(evidence, edited))
        self.assertEqual(printed_line_evidence(rows, public, 'MXN', sources, family='generic')['reason'], 'currency_differs')
        # Another reader's proof basis is not this proof's question.
        self.assertIsNone(printed_line_evidence(rows, dict(public, engine=dict(public['engine'], basis='running_balance')),
                                                'USD', sources, family='generic'))

    def test_a_profile_matched_by_all_its_phrases_outranks_single_phrase_matches(self):
        from services.financial import statement_engine_profiles as P
        loose = dict(name='loose', match=dict(any=['example card']))
        with mock.patch.object(P, 'PROFILES', (loose, CREDIT_UNION_PROFILE)):
            text = 'Example Federal Credit Union Statement of Account Payment to Example Card'
            self.assertEqual(P.matching_profile(text)['name'], 'invented-credit-union')
            self.assertEqual(P.matching_profile('payment to example card')['name'], 'loose')
        with mock.patch.object(P, 'PROFILES', (loose, dict(loose, name='loose-twin'))):
            self.assertIsNone(P.matching_profile('payment to example card'))
        P.validate(CREDIT_UNION_PROFILE)
        with self.assertRaises(ValueError):
            P.validate(dict(CREDIT_UNION_PROFILE, holder_heading=dict(title=[], prefix='FOR')))

    def test_routing_keeps_a_profile_that_only_adds_an_identity_hold(self):
        from services.financial import statement_engine_profiles as P
        from services.financial import statement_engine_routing as R
        sources = credit_union_statement()
        with mock.patch.object(P, 'PROFILES', (CREDIT_UNION_PROFILE,)), \
                mock.patch.dict(os.environ, {'LOUPE_FINANCIAL_GENERIC_READER': '1'}):
            catalog = R.route_catalog(sources, lambda s: dict(statements=[], unclassified_sources=[],
                                                               information_sources=[], complete_coverage=True))
        self.assertEqual(catalog['engine_routing']['profile'], 'invented-credit-union')
        served = {(st['account_reference'][-4:], st['balance_convention']): st['engine'] for st in catalog['statements']}
        self.assertTrue(served[('1111', 'asset_balance')]['proved'])
        self.assertTrue(served[('1111', 'liability_owed')]['proved'])

    def test_a_summary_closed_before_the_movement_table_does_not_make_it_another_table(self):
        sources = mx_statement(MOVES, closing='1,250.00')
        rows = sources[0]['rows']
        # A summary heading (date and amount words) printed above the summary's closing balance.
        rows.insert(1, dict(row_index=900, cells=[cell('FECHA', 20000, 60000, 33000, 0), cell('IMPORTE', 500000, 560000, 33000, 1)]))
        st = read_statements(sources)[0]
        self.assertTrue(st['engine']['proved'], st['engine'])
        self.assertEqual(len(self.moves(st)), 3)

    def test_a_stray_date_in_another_form_after_the_movements_does_not_hold(self):
        sources = credit_union_statement()
        rows = sources[1]['rows']
        index = next(i for i, r in enumerate(rows) if r['cells'][0]['expected_text'] == '02-01')
        y = rows[index]['cells'][0]['locator']['rect'][1] + 5000
        rows.insert(index + 1, dict(row_index=901, cells=[cell('01-Feb', 14000, 50000, y, 0)]))
        checking = self.sections(sources)[0]
        self.assertTrue(checking['engine']['proved'], checking['engine'])

    def test_a_heading_repeated_with_fewer_columns_after_a_summary_closing_continues_the_table(self):
        sources = mx_statement(MOVES, closing='1,250.00')
        rows = sources[0]['rows']
        index = next(i for i, r in enumerate(rows) if r['cells'][0]['expected_text'] == '10/MAR')
        y = rows[index]['cells'][0]['locator']['rect'][1] - 4000
        # The summary's closing is printed above the table: a heading reprinted inside the table with only
        # some of its column words read is not another table.
        rows.insert(index, dict(row_index=902, cells=[cell('FECHA', 20000, 60000, y, 0), cell('ABONOS', 330000, 380000, y, 1)]))
        st = read_statements(sources)[0]
        self.assertTrue(st['engine']['proved'], st['engine'])
        self.assertEqual(len(self.moves(st)), 3)

    def test_an_unnumbered_first_page_of_the_next_run_is_not_an_appendix(self):
        stamped = lambda numbering: dict(numbering=numbering, periods=set(), labelled_periods=set(), file_numbered=True)
        facts = {1: stamped({(1, 2)}), 2: stamped({(2, 2)}), 3: stamped(set()), 4: stamped({(2, 2)}), 5: stamped(set())}
        segments = E._segments({p: [] for p in facts}, facts)
        self.assertEqual([s['pages'] for s in segments], [[1, 2, 3, 4], [5]])
        self.assertTrue(segments[1].get('appendix'))
        # Without the production's stamp an unnumbered page after a complete run continues it, as before.
        for page in facts.values():
            page.pop('file_numbered')
        self.assertEqual([s['pages'] for s in E._segments({p: [] for p in facts}, facts)], [[1, 2, 3, 4, 5]])
