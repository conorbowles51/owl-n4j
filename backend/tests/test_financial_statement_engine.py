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
        moves = [('05/MAR', 'ENTRADA', '500,00', None, '1,500.00'), ('10/MAR', 'SALIDA', None, '200,00', '1,300.00')]
        st = self.one(mx_statement(moves, opening='1,000.00', closing='1,300.00'))
        self.assertFalse(st['engine']['proved'])

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

    def test_a_lone_word_is_not_a_bank_name(self):
        self.assertEqual(E._institution([{'ONE, N.A. YOU MAY CONTINUE TO SEE SOME REFERENCES'}], set()), '')
        self.assertEqual(E._institution([{'CITIBANK, N.A.'}], set()), 'CITIBANK')

    def test_a_currency_value_repeating_the_label_word_is_read(self):
        st = self.one(mx_statement(MOVES, closing='1,250.00', currency_line=('MONEDA', 'MONEDA NACIONAL')))
        self.assertEqual(st['currency'], 'MXN')
