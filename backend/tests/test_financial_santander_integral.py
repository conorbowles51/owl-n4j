"""Synthetic older Santander "ESTADO DE CUENTA INTEGRAL" scans; no client source or financial data."""
from copy import deepcopy
from unittest import TestCase

from services.financial import santander_integral
from services.financial.santander_integral import recover_held, recover_rows
from services.financial.statement_review_checks import check_statement_rows
from tests.test_financial_statement_import_scotiabank import source

ACCOUNT = '65-00001234-0'


def scan(*, opening='1,000.00', initial='1,000.00', actual='= SALDO ACTUAL', closing='1, 120.00',
         movements=None, total=None, positions=True):
    """A cover and a cheque detail section read from a noisy scan."""
    movements = movements if movements is not None else [
        ('O2-SEP-2024 0000001 ABONO POR TRANSFERENCIA', ['150', '.00'], 'D', ['1,150', '.00?']),
        ('03-SEP~2024 0000002 COMISION', ['30,00'], 'R', ['1, 120.00']),
    ]
    rows = [
        [(30000, 10000, 100000, 'Santander'), (300000, 10000, 150000, 'ESTADO DE CUENTA INTEGRAL')],
        [(30000, 20000, 150000, 'BANCO SANTANDER (MEXICO), S.A.')],
        [(30000, 40000, 150000, 'EXAMPLE SERVICES SA DE CV')],
        [(250000, 60000, 100000, 'CUENTA DE CHEQUES')],
        [(30000, 70000, 200000, 'CUENTA SANTANDER PYME ' + ACCOUNT)],
        [(30000, 80000, 50000, 'SALDO PROMEDIO'), (165000, 80000, 40000, '900.00'), (220000, 80000, 50000, 'SALDO. INICIAL'),
         (335000, 80000, 40000, initial), (400000, 80000, 60000, '+ INTERESES BRUTOS')],
        [(140000, 90000, 60000, 'CORTE AL 30/09/2024'), (222000, 90000, 50000, actual), (335000, 90000, 40000, closing),
         (396000, 90000, 60000, 'COMISIONES COBRADAS')],
        [(190000, 120000, 220000, 'DETALLE DE MOVIMIENTOS CUENTA DE CHEQUES')],
        [(30000, 130000, 200000, 'CUENTA SANTANDER PYME ' + ACCOUNT)],
        [(30000, 140000, 30000, 'FECHA'), (80000, 140000, 20000, 'FOLIO'), (116000, 140000, 40000, '—_DESCRIPCION'),
         (375000, 140000, 33000, 'DEPOSITOS'), (460000, 140000, 26000, 'RETIROS'), (545000, 140000, 18000, 'SALDO')],
        [(30000, 150000, 40000, '31-AGO-2024'), (110000, 150000, 110000, 'SALDO FINAL DEL PERIODO ANTERIOR'),
         (519000, 150000, 43000, opening)],
    ]
    y = 160000
    for text, amount, column, balance in movements:
        right = 408000 if column == 'D' else 486000
        cells = [(30000, y, 250000, text)]
        width = 20000
        for i, piece in enumerate(amount):
            cells.append((right - width * (len(amount) - i), y, width - 500, piece))
        for i, piece in enumerate(balance):
            cells.append((563000 - width * (len(balance) - i), y, width - 500, piece))
        rows.append(cells)
        rows.append([(110000, y + 8000, 100000, 'COBRO 0,000,000.01')])
        y += 20000
    rows.append([(125000, y, 18000, 'TOTAL')] + (total or []))
    rows.append([(180000, y + 20000, 200000, 'INFORMACION FISCAL')])
    page = source(1, rows)
    if not positions:
        for row in page['rows']:
            for cell in row['cells']:
                cell['locator'] = None
    return [page]


def statement(sources, **extra):
    return dict(dict(id='s1', period_start='2024-09-01', period_end='2024-09-30', account_reference=ACCOUNT,
                     currency='MXN', engine=dict(proved=False, reason='not_reconciled'),
                     sources=[dict(page_number=s['page_number'], table_index=s['table_index'],
                                   source_revision=s['source_revision']) for s in sources]), **extra)


def read(sources, **kwargs):
    rows = recover_rows(statement(sources), sources, kwargs.pop('currency', 'MXN'))
    return rows


class SantanderIntegralTests(TestCase):
    def test_the_running_balance_proves_every_movement_of_a_noisy_scan(self):
        for positions in (True, False):
            with self.subTest(positions=positions):
                sources = scan(positions=positions); before = deepcopy(sources)
                rows = read(sources)
                tx = [r for r in rows if not r['excluded']]
                self.assertEqual([(r['fields']['date'], r['fields']['direction'], r['fields']['amount_minor'],
                                   r['fields']['balance'], r['fields']['bank_reference']) for r in tx],
                                 [('2024-09-02', 'credit', '15000', '115000', '0000001'),
                                  ('2024-09-03', 'debit', '3000', '112000', '0000002')])
                balances = {r['fields']['description']: r['fields']['balance'] for r in rows if r['kind'] == 'balance'}
                self.assertEqual(balances, {'Opening Balance': '100000', 'Closing Balance': '112000'})
                checks = check_statement_rows(rows)
                self.assertEqual((checks['balance_status'], checks['flagged_rows']), ('matches', 0))
                self.assertEqual(sources, before)

    def test_an_amount_that_does_not_move_the_balance_by_itself_is_never_read(self):
        cases = dict(
            amount_misread=[('02-SEP-2024 0000001 ABONO', ['160.00'], 'D', ['1,150.00']),
                            ('03-SEP-2024 0000002 COMISION', ['30.00'], 'R', ['1,120.00'])],
            garbled=[('02-SEP-2024 0000001 ABONO', ['$5O.00?'], 'D', ['1,150.00']),
                     ('03-SEP-2024 0000002 COMISION', ['30.00'], 'R', ['1,120.00'])],
            missing_row=[('03-SEP-2024 0000002 COMISION', ['30.00'], 'R', ['1,120.00'])],
            wrong_column=[('02-SEP-2024 0000001 ABONO', ['150.00'], 'R', ['1,150.00']),
                          ('03-SEP-2024 0000002 COMISION', ['30.00'], 'R', ['1,120.00'])],
            date_back=[('03-SEP-2024 0000001 ABONO', ['150.00'], 'D', ['1,150.00']),
                       ('02-SEP-2024 0000002 COMISION', ['30.00'], 'R', ['1,120.00'])],
            out_of_period=[('02-OCT-2024 0000001 ABONO', ['150.00'], 'D', ['1,150.00']),
                           ('03-SEP-2024 0000002 COMISION', ['30.00'], 'R', ['1,120.00'])],
            no_folio=[('02-SEP-2024 ABONO', ['150.00'], 'D', ['1,150.00']),
                      ('03-SEP-2024 0000002 COMISION', ['30.00'], 'R', ['1,120.00'])],
            ambiguous_month=[('02-MAX-2024 0000001 ABONO', ['150.00'], 'D', ['1,150.00']),
                             ('03-SEP-2024 0000002 COMISION', ['30.00'], 'R', ['1,120.00'])],
        )
        for name, movements in cases.items():
            with self.subTest(name):
                self.assertIsNone(read(scan(movements=movements)))

    def test_the_chain_ends_must_agree_with_balances_printed_elsewhere(self):
        self.assertIsNone(read(scan(initial='1,001.00')))
        self.assertIsNone(read(scan(closing='1,121.00')))
        # The cover's closing unreadable: the TOTAL line's printed balance agrees instead.
        rows = read(scan(closing='l,12O.OO', total=[(380000, 220000, 25000, '150.00'), (460000, 220000, 25000, '30.00'),
                                                    (540000, 220000, 25000, '1,120.00?')]))
        self.assertEqual([r['fields']['balance'] for r in rows if r['fields'].get('description') == 'Closing Balance'], ['112000'])

    def test_other_layouts_currencies_products_and_shared_pages_are_left_to_the_general_reader(self):
        sources = scan()
        sources[0]['rows'][0]['cells'][1]['expected_text'] = 'ESTADO DE CUENTA'
        self.assertIsNone(read(sources))
        self.assertIsNone(read(scan(), currency=''))
        self.assertIsNone(recover_rows(statement(scan(), currency='USD'), scan(), 'MXN'))
        sources = scan()
        sources[0]['rows'][3]['cells'][0]['expected_text'] = 'INVERSION CRECIENTE 66-00001234-0'
        self.assertIsNone(read(sources))
        sources = scan()
        held = statement(sources)
        self.assertIsNotNone(recover_held(held, [held], sources, 'MXN'))
        fragment = statement(sources, id='s2')
        self.assertIsNone(recover_held(held, [held, fragment], sources, 'MXN'))
        self.assertIsNone(recover_held(dict(held, engine=dict(proved=True)), [held], sources, 'MXN'))

    def test_switch_off_leaves_the_held_reading(self):
        try:
            santander_integral.ENABLED = False
            self.assertIsNone(read(scan()))
        finally:
            santander_integral.ENABLED = True
