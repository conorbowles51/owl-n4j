"""Santander online movement query ("Consulta de Movimientos"): invented printouts, no client data."""
from copy import deepcopy
from unittest import TestCase, mock

from services.financial import statement_import_santander_query as Q
from services.financial.statement_currency import currencies_by_statement
from services.financial.statement_import_catalog import library_catalog
from services.financial.statement_import_santander import propose_santander_statement
from services.financial.statement_review_checks import check_statement_rows

ACCOUNT = '11112222333'
HEADING = ['Cuenta', 'Fecha', 'Hora', 'Sucursal', 'Descripción', 'Importe Cargo', 'Importe Abono', 'Saldo',
           'Referencia', 'Concepto']
# Oldest first. The bank prints "Saldo Inicial" as the balance after the first movement (1,000.00 - 50.00).
MOVES = [('01102024', '50.00', '0.00', '950.00', 'COMISION'),
         ('03102024', '0.00', '200.00', '1,150.00', 'ABONO SPEI'),
         ('09102024', '25.50', '0.00', '1,124.50', 'PAGO SERVICIO'),
         ('15102024', '0.00', '0.25', '1,124.75', 'INTERESES')]


def _cell(page, column, text, x, y):
    return dict(column_index=column, expected_text=text, locator=dict(
        kind='page_rectangle', page=page, rect=[x, y, x + 60000, y + 6000], page_size=[841890, 595276],
        units='millipoints', space='pdf_displayed'))


def query(*, pages=1, opening='950.00', closing='1,124.75', credits=2, debits=2, rows=4, credits_total='200.25',
          debits_total='75.50', currency='MXN', moves=MOVES, page_total=None, holder='EMPRESA EJEMPLO SA DE CV',
          second_holder=None):
    """A printout split over ``pages`` pages (movements dealt in order); every page repeats the header."""
    chunks = [moves[i::pages] for i in range(pages)] if pages > 1 else [moves]
    chunks = [moves[:len(moves) // 2], moves[len(moves) // 2:]] if pages == 2 else chunks
    sources = []
    for index, chunk in enumerate(chunks, 1):
        name = holder if index == 1 or second_holder is None else second_holder
        header = [[f'Página {index} de {page_total or pages}'], ['Consulta de Movimientos de la Cuenta de Cheques'],
                  [f'Contrato CMC: 90000001 {name}', 'Periodo: 01/10/2024 al 15/10/2024',
                   f'Número de Abonos: {credits}', f'Importe Total Abonos: ${credits_total} {currency}'],
                  [f'Número de Cuenta: {ACCOUNT}', f'Saldo Inicial: ${opening} {currency}',
                   f'Número de Cargos: {debits}', f'Importe Total Cargos: ${debits_total} {currency}'],
                  ['Usuario: 1 USUARIO EJEMPLO', f'Saldo Final: ${closing} {currency}', f'Total de Movimientos: {rows}']]
        text = [dict(row_index=i, cells=[_cell(index, j, t, 30000 + j * 200000, 20000 + i * 12000)
                                         for j, t in enumerate(line)]) for i, line in enumerate(header)]
        footer = len(text)
        text.append(dict(row_index=footer, cells=[_cell(index, 0, 'Banco Santander México S.A., Institución de Banca '
                                                         'Múltiple, Grupo Financiero Santander México.', 30000, 560000)]))
        table = [dict(row_index=0, cells=[_cell(index, j, t, 25000 + j * 70000, 125000) for j, t in enumerate(HEADING)])]
        for i, (day, debit, credit, balance, desc) in enumerate(chunk, 1):
            values = [ACCOUNT, day, '10:00', '0001', desc, debit, credit, balance, '0000001', 'CONCEPTO EJEMPLO']
            table.append(dict(row_index=i, cells=[_cell(index, j, t, 25000 + j * 70000, 125000 + i * 20000)
                                                  for j, t in enumerate(values)]))
        sources.append(dict(page_number=index, table_index=0, source_revision='a' * 64, table_source='drawn_geometry',
                            rows=table))
        sources.append(dict(page_number=index, table_index=1, source_revision='a' * 64,
                            table_source='text_alignment', rows=text))
    return sources


def read(sources):
    catalog = library_catalog(sources)
    choices = currencies_by_statement(catalog['statements'], sources)
    return catalog, choices


def proposal(sources):
    catalog, choices = read(sources)
    choice, = choices
    return choice, propose_santander_statement(sources, choice['currency'], choice)['rows']


class MovementQueryTests(TestCase):
    def test_one_period_with_printed_identity_and_derived_opening(self):
        sources = query()
        before = deepcopy(sources)
        catalog, choices = read(sources)
        self.assertEqual(sources, before)
        self.assertTrue(catalog['complete_coverage'])
        choice, = choices
        self.assertEqual((choice['layout_id'], choice['form'], choice['institution'], choice['account_reference'],
                          choice['holder'], choice['currency'], choice['period_start'], choice['period_end']),
                         ('santander-mexico-movements', 'movement_query', 'Santander', ACCOUNT,
                          'EMPRESA EJEMPLO SA DE CV', 'MXN', '2024-10-01', '2024-10-15'))
        rows = propose_santander_statement(sources, 'MXN', choice)['rows']
        opening, = [r for r in rows if r['fields'].get('description') == 'Opening Balance']
        # 950.00 printed is the balance after the first movement (a 50.00 debit): the opening is 1,000.00.
        self.assertEqual(opening['fields']['balance'], '100000')
        self.assertEqual(opening['fields']['balance_basis'], Q.OPENING_BASIS)
        self.assertEqual(opening['fields']['balance_derivation']['printed_opening_minor'], '95000')
        self.assertTrue(opening['excluded'])
        moves = [(r['fields']['date'], r['fields']['direction'], r['fields']['amount_minor'], r['fields']['balance'])
                 for r in rows if not r['excluded']]
        self.assertEqual(moves, [('2024-10-01', 'debit', '5000', '95000'), ('2024-10-03', 'credit', '20000', '115000'),
                                 ('2024-10-09', 'debit', '2550', '112450'), ('2024-10-15', 'credit', '25', '112475')])
        checks = check_statement_rows(rows)
        self.assertEqual({c['kind']: c['status'] for c in checks['checks']},
                         dict(closing_balance='matches', running_balance='matches', credit_total='matches',
                              debit_total='matches'))
        self.assertFalse(any(r['issues'] for r in rows))

    def test_two_pages_read_as_one_period(self):
        choice, rows = proposal(query(pages=2))
        self.assertEqual(sum(1 for r in rows if not r['excluded']), 4)
        self.assertFalse(any(r['issues'] for r in rows))
        self.assertEqual(check_statement_rows(rows)['balance_status'], 'matches')

    def held(self, rows):
        return [r for r in rows if not r['excluded'] and r['issues']]

    def test_saldo_inicial_that_is_not_the_first_running_balance_holds_without_an_opening(self):
        choice, rows = proposal(query(opening='1,000.00'))
        opening, = [r for r in rows if r['fields'].get('description') == 'Opening Balance']
        self.assertNotIn('balance', opening['fields'])
        self.assertTrue(self.held(rows))
        self.assertEqual(check_statement_rows(rows)['balance_status'], 'unavailable')

    def test_printed_counts_must_equal_the_lines_read(self):
        for wrong in (dict(credits=3), dict(debits=1), dict(rows=5)):
            choice, rows = proposal(query(**wrong))
            self.assertTrue(self.held(rows), wrong)

    def test_printed_totals_are_checked(self):
        choice, rows = proposal(query(credits_total='200.00'))
        self.assertEqual({c['kind']: c['status'] for c in check_statement_rows(rows)['checks']}['credit_total'],
                         'difference')

    def test_movements_not_oldest_first_hold(self):
        moves = [MOVES[1], MOVES[0]] + MOVES[2:]
        choice, rows = proposal(query(moves=moves, opening='1,150.00'))
        opening, = [r for r in rows if r['fields'].get('description') == 'Opening Balance']
        self.assertNotIn('balance', opening['fields'])
        self.assertTrue(self.held(rows))

    def test_a_missing_page_holds(self):
        choice, rows = proposal(query(page_total=2))
        self.assertFalse(choice['pages_complete'])
        self.assertTrue(self.held(rows))

    def test_pages_that_disagree_are_not_one_query(self):
        self.assertEqual(read(query(pages=2, second_holder='OTRA EMPRESA SA DE CV'))[0]['statements'], [])

    def test_a_line_printing_another_account_holds(self):
        sources = query()
        sources[0]['rows'][2]['cells'][0]['expected_text'] = '99998888777'
        choice, rows = proposal(sources)
        self.assertTrue(self.held(rows))

    def test_mixed_currency_codes_read_no_currency(self):
        sources = query()
        cell = sources[1]['rows'][4]['cells'][1]
        cell['expected_text'] = cell['expected_text'].replace('MXN', 'USD')
        choice, = read(sources)[1]
        self.assertEqual(choice['currency'], '')

    def test_switched_off_the_printout_is_not_claimed(self):
        with mock.patch.object(Q, 'MOVEMENT_QUERY', False):
            self.assertEqual(Q.santander_query_catalog(query()), ([], set()))
