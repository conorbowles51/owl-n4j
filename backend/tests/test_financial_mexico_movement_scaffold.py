"""Scotiabank movement-table scaffold; synthetic fixtures only.

The movement layout was modelled by the benchmark corpus, not taken from a
real statement (the Monex reader has since been fitted to real productions and
no longer uses the scaffold; see test_financial_statement_import_monex).
These tests pin the scaffold's contract: off by default (a
movement table refuses the statement, as before), and when switched on a
section is read only when every row and printed control can be placed.
"""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch

from services.financial.statement_import_scotiabank import (
    MOVEMENTS_LAYOUT, LAYOUT, propose_scotiabank_movements, scotiabank_catalog)
from services.financial.statement_movement_scaffold import MOVEMENT_SCAFFOLD_FLAG, movement_scaffold_enabled
from services.financial.statement_review_checks import check_statement_rows
from tests.test_financial_statement_import_scotiabank import source, statement as scotiabank_zero_statement

ON = patch.dict('os.environ', {MOVEMENT_SCAFFOLD_FLAG: '1'})


def scotiabank_statement(body=None):
    rows = [
        [(100000,10000,100000,'PAGINA 1 DE 3')],
        [(390000,22000,80000,'Scotiabank')],
        [(330000,34000,60000,'Estado de Cuenta'),(400000,34000,100000,'SCOTIA INV DISP PM +')],
        [(40000,70000,190000,'SERVICIOS EJEMPLO SA DE CV')],
        [(400000,94000,50000,'Cuenta'),(470000,94000,80000,'00087654321')],
        [(400000,106000,50000,'Periodo'),(470000,106000,120000,'01-JUN-24/30-JUN-24')],
        [(400000,118000,50000,'Moneda'),(470000,118000,80000,'NACIONAL')],
        [(240000,250000,190000,'Comportamiento de transacciones en tu cuenta')],
        [(90000,262000,100000,'Resumen de Saldos')],
        [(300000,275000,120000,'Saldo inicial = $12,345.67'),(450000,275000,110000,'Saldo final= $19,995.67')],
        [(50000,290000,100000,'Saldo inicial'),(190000,290000,43000,'$12,345.67')],
        [(50000,305000,100000,'(+) Depósitos'),(190000,305000,43000,'$35,000.00')],
        [(50000,320000,130000,'(+) Intereses recibidos (Tasa 0.00%)'),(210000,320000,23000,'$0.00')],
        [(50000,335000,100000,'(-) Retiros'),(190000,335000,43000,'$27,350.00')],
        [(50000,350000,100000,'(-) Comisiones cobradas'),(210000,350000,23000,'$0.00')],
        [(50000,365000,100000,'(-) Impuestos'),(210000,365000,23000,'$0.00')],
        [(50000,397000,130000,'(=) Saldo final de la cuenta'),(190000,397000,43000,'$19,995.67'),
         (302000,397000,40000,'$35,000.00'),(347000,397000,20000,'$0.00'),(394000,397000,40000,'$27,350.00'),
         (470000,397000,20000,'$0.00'),(532000,397000,20000,'$0.00')],
        [(300000,424000,40000,'Depósitos'),(345000,424000,40000,'Intereses'),(392000,424000,60000,'Retiros en efectivo'),
         (468000,424000,50000,'Otros cargos*'),(530000,424000,40000,'Comisiones')],
        [(40000,455000,130000,'Sdo. Prom. Min. requerido en cuenta'),(190000,455000,43000,'$10,000.00')],
        [(40000,480000,120000,'Detalle de tus movimientos')],
        [(40000,493000,25000,'Fecha'),(100000,493000,40000,'Concepto'),(290000,493000,45000,'Referencia'),
         (400000,493000,40000,'Depósito'),(470000,493000,30000,'Retiro'),(535000,493000,25000,'Saldo')],
    ]
    if body is None:
        body = [('04-JUN-24','TRANSF SPEI RECIBIDA EJEMPLO','SC240600','$35,000.00',None,'$47,345.67'),
                ('11-JUN-24','PAGO PROVEEDOR EJEMPLO','SC240601',None,'$18,200.00','$29,145.67'),
                ('18-JUN-24','COMISION MANEJO DE CUENTA','SC240602',None,'$150.00','$28,995.67'),
                ('26-JUN-24','TRANSF SPEI ENVIADA EJEMPLO','SC240603',None,'$9,000.00','$19,995.67')]
    for n, (day, concept, reference, deposit, withdrawal, balance) in enumerate(body):
        y = 506000 + 13000 * n
        cells = [(40000,y,40000,day),(100000,y,150000,concept),(290000,y,40000,reference)]
        if deposit:
            cells.append((390000,y,50000,deposit))
        if withdrawal:
            cells.append((450000,y,50000,withdrawal))
        cells.append((510000,y,50000,balance))
        rows.append(cells)
    rows.append([(40000,506000 + 13000 * len(body) + 6000,400000,'A PARTIR DEL 01-05-24 LA COMISION SERA $14.66 MAS IVA.')])
    pages = scotiabank_zero_statement()
    for page in pages[1:]:
        for row in page['rows']:
            for cell in row['cells']:
                cell['expected_text'] = cell['expected_text'].replace('00001234567', '00087654321')
    return [source(1, rows)] + pages[1:]


class SwitchTests(TestCase):
    def test_off_unless_explicitly_switched_on(self):
        self.assertFalse(movement_scaffold_enabled({}))
        self.assertFalse(movement_scaffold_enabled({MOVEMENT_SCAFFOLD_FLAG: '0'}))
        self.assertFalse(movement_scaffold_enabled({MOVEMENT_SCAFFOLD_FLAG: 'maybe'}))
        self.assertTrue(movement_scaffold_enabled({MOVEMENT_SCAFFOLD_FLAG: ' On '}))


class ScotiabankMovementTests(TestCase):
    def test_switched_off_a_movement_table_still_refuses_the_statement(self):
        with patch.dict('os.environ', {MOVEMENT_SCAFFOLD_FLAG: ''}):
            self.assertEqual(scotiabank_catalog(scotiabank_statement()), ([], set()))

    def test_switched_on_rows_reconcile_with_every_printed_control(self):
        sources = scotiabank_statement()
        before = deepcopy(sources)
        with ON:
            groups, handled = scotiabank_catalog(sources)
            self.assertEqual(len(groups), 1)
            choice = groups[0]
            rows = propose_scotiabank_movements(sources, 'MXN', choice)['rows']
        self.assertEqual(sources, before)
        self.assertEqual(choice['layout_id'], MOVEMENTS_LAYOUT)
        self.assertNotIn('zero_activity_evidence', choice)
        self.assertEqual((choice['account_reference'], choice['period_start'], choice['period_end'], choice['holder']),
                         ('00087654321', '2024-06-01', '2024-06-30', 'SERVICIOS EJEMPLO SA DE CV'))
        self.assertEqual(len(handled), 3)
        payments = [r for r in rows if not r['excluded']]
        self.assertEqual([(r['kind'], r['fields']['date'], r['fields']['direction'], r['fields']['amount_minor'],
                           r['fields']['balance'], r['fields']['bank_reference']) for r in payments], [
            ('transaction', '2024-06-04', 'credit', '3500000', '4734567', 'SC240600'),
            ('transaction', '2024-06-11', 'debit', '1820000', '2914567', 'SC240601'),
            ('transaction', '2024-06-18', 'debit', '15000', '2899567', 'SC240602'),
            ('transaction', '2024-06-26', 'debit', '900000', '1999567', 'SC240603')])
        self.assertTrue(all(not r['issues'] for r in rows))
        self.assertEqual(sorted((r['kind'], r['fields'].get('total_direction') or r['fields']['description'], r['fields']['balance'])
                                for r in rows if r['kind'] in ('balance', 'statement_total')),
                         [('balance', 'Closing Balance', '1999567'), ('balance', 'Opening Balance', '1234567'),
                          ('statement_total', 'credit', '3500000'), ('statement_total', 'debit', '2735000')])
        checks = check_statement_rows(rows)['checks']
        self.assertEqual({c['kind']: c['status'] for c in checks},
                         {'closing_balance': 'matches', 'running_balance': 'matches',
                          'credit_total': 'matches', 'debit_total': 'matches'})

    def test_a_misread_amount_is_caught_by_the_printed_controls(self):
        sources = scotiabank_statement()
        sources[0]['rows'][22]['cells'][3]['expected_text'] = '$18,800.00'
        with ON:
            choice = scotiabank_catalog(sources)[0][0]
            rows = propose_scotiabank_movements(sources, 'MXN', choice)['rows']
        statuses = {c['kind']: c['status'] for c in check_statement_rows(rows)['checks']}
        self.assertEqual(statuses['closing_balance'], 'difference')
        self.assertEqual(statuses['debit_total'], 'difference')
        self.assertEqual(statuses['running_balance'], 'difference')

    def test_a_row_without_a_single_placed_amount_is_unresolved_not_dropped(self):
        body = [('04-JUN-24','TRANSF SPEI RECIBIDA EJEMPLO','SC240600','$35,000.00','$35,000.00','$47,345.67'),
                ('11-JUN-24','PAGO PROVEEDOR EJEMPLO','SC240601',None,'$27,350.00','$19,995.67')]
        with ON:
            sources = scotiabank_statement(body)
            choice = scotiabank_catalog(sources)[0][0]
            rows = propose_scotiabank_movements(sources, 'MXN', choice)['rows']
        first = next(r for r in rows if r['id'] == '1:0:21')
        self.assertEqual((first['kind'], first['excluded']), ('unresolved', False))
        self.assertIn('Choose the printed deposit or withdrawal amount for this payment.', first['issues'])

    def test_switched_on_anything_short_of_the_full_layout_is_still_refused(self):
        variants = []
        s = scotiabank_statement(); s[0]['rows'][14]['cells'][1]['expected_text'] = '$150.00'; variants.append(s)
        s = scotiabank_statement(); s[0]['rows'][11]['cells'].pop(); variants.append(s)
        s = scotiabank_statement(); s[0]['rows'][10]['cells'][1]['expected_text'] = '$12,345.76'; variants.append(s)
        s = scotiabank_statement(); s[0]['rows'][20]['cells'][2]['expected_text'] = 'Descripcion'; variants.append(s)
        s = scotiabank_statement(); s[0]['rows'][20]['cells'].pop(); variants.append(s)
        s = scotiabank_statement(); s[2]['rows'].append(s[0]['rows'][22]); variants.append(s)
        s = scotiabank_statement(); s[0]['rows'][24]['cells'][0]['locator'] = None; variants.append(s)
        s = scotiabank_statement(); s[0]['rows'][19]['cells'][0]['expected_text'] = 'Detalle de movimientos del mes'; variants.append(s)
        s = scotiabank_statement(); s.pop(); variants.append(s)
        s = scotiabank_statement(); s[0]['rows'][13]['cells'][1]['expected_text'] = '-$27,350.00'; variants.append(s)
        with ON:
            for i, s in enumerate(variants):
                with self.subTest(i=i):
                    self.assertEqual(scotiabank_catalog(s), ([], set()))

    def test_the_zero_activity_layout_is_unchanged_when_switched_on(self):
        with ON:
            groups, _ = scotiabank_catalog(scotiabank_zero_statement())
        self.assertEqual([g['layout_id'] for g in groups], [LAYOUT])
        self.assertIn('zero_activity_evidence', groups[0])
