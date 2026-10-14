"""Synthetic BBVA and Capital One page readings; no client documents or values."""
import unittest

from services.financial.statement_reading_quality import assess_statement_reading, page_controls_reconcile


def table(lines, page=1):
    def locator(x, y, width, height=8):
        return dict(kind='page_rectangle', page=page, rect=[int(v * 1000) for v in (x, y, x + width, y + height)],
                    page_size=[600000, 800000], units='millipoints', space='pdf_displayed')
    return [dict(table_source='text_alignment', table=dict(page=page, values=[
        dict(row=i, column=j, text=text, locator=locator(x, y, width))
        for i, (y, row) in enumerate(lines) for j, (x, width, text) in enumerate(row)]))]


def capital(amount='$38.74', interest='$1.25'):
    return table([
        (20, [(40, 60, 'Capital One')]),
        (40, [(330, 160, 'Platinum Mastercard ending in 4821')]),
        (52, [(330, 230, 'Feb 16, 2025 - Mar 15, 2025 | 28 days in Billing Cycle')]),
        (80, [(40, 80, 'Account Summary')]),
        (92, [(40, 70, 'Previous Balance'), (150, 30, '$10.00')]),
        (104, [(40, 50, 'New Balance'), (150, 30, '$49.99')]),
        (130, [(40, 220, 'Visit capitalone.com to see detailed transactions.')]),
        (150, [(40, 230, 'EXAMPLE CARDHOLDER #4821: Transactions')]),
        (162, [(40, 40, 'Trans Date'), (100, 40, 'Post Date'), (160, 60, 'Description'), (530, 30, 'Amount')]),
        (174, [(40, 30, 'Feb 19'), (100, 30, 'Feb 20'), (160, 120, 'EXAMPLE GROCERY'), (537, 23, amount)]),
        (186, [(40, 230, 'EXAMPLE CARDHOLDER #4821: Total Transactions'), (537, 23, '$38.74')]),
        (210, [(40, 80, 'Interest Charged')]),
        (222, [(40, 120, 'Interest Charge on Purchases'), (537, 23, interest)])])


def bbva(page_line='PAGINA 1/2', period=True, amount='12.94'):
    lines = [(20, [(534, 55, 'Estado de Cuenta')]), (33, [(514, 76, 'MAESTRA PYME BBVA')]),
             (45, [(548, 41, page_line)]), (57, [(330, 35, 'No. Cuenta'), (470, 38, '0000012345')])]
    if period:
        lines.append((107, [(330, 23, 'Periodo'), (430, 97, 'DEL 01/09/2024 AL 30/09/2024')]))
    lines += [
        (143, [(10, 187, 'BBVA MEXICO, S.A., INSTITUCION DE BANCA MULTIPLE')]),
        (167, [(316, 84, 'Saldo de Liquidaci6n Inicial'), (555, 34, '1,000.00')]),
        (179, [(316, 81, 'Saldo de Operacidn Inicial'), (555, 34, '1,000.00')]),
        (215, [(316, 45, 'Saldo Final (+)'), (555, 34, '987.06')]),
        (227, [(316, 78, 'Saldo de Operacion Final'), (555, 34, '987.06')]),
        (251, [(18, 19, 'OPER'), (51, 11, 'LIQ'), (86, 67, 'COD. DESCRIPCION'), (230, 44, 'REFERENCIA'),
               (367, 30, 'CARGOS'), (429, 29, 'ABONOS'), (488, 41, 'OPERACION'), (553, 45, 'LIQUIDACION')]),
        (265, [(12, 22, '05/SEP'), (53, 22, '05/SEP'), (90, 120, 'T17 SPEI ENVIADO PROVEEDOR'),
               (365, 33, amount), (490, 35, '987.06'), (558, 35, '987.06')]),
        (451, [(10, 66, 'Total de Movimientos')])]
    return table(lines)


class CapitalOneReadingQualityTests(unittest.TestCase):
    def test_complete_page_is_assessed_with_nothing_unreadable(self):
        result = assess_statement_reading(capital())
        self.assertEqual(result['identity'], ['capital-one-card', '****4821', '2025-02-16', '2025-03-15'])
        self.assertEqual((result['payments'], result['balances'], result['unreadable']), (2, 2, 0))

    def test_interest_charge_without_a_printed_date_is_not_an_unreadable_date(self):
        # Otherwise every digital card page with interest would be sent for an image reread.
        result = assess_statement_reading(capital(interest='$7.00'))
        self.assertEqual(result['missing_fields']['date'], 0)
        self.assertEqual(result['unreadable'], 0)

    def test_damaged_amount_is_unreadable(self):
        result = assess_statement_reading(capital(amount='$3B.74'))
        self.assertEqual(result['missing_fields']['amount_minor'], 1)
        self.assertEqual(result['missing_fields']['direction'], 1)

    def test_page_without_the_issuer_is_not_claimed(self):
        tables = capital()
        tables[0]['table']['values'] = [v for v in tables[0]['table']['values']
                                         if v['text'] not in ('Capital One', 'Visit capitalone.com to see detailed transactions.')]
        self.assertIsNone(assess_statement_reading(tables))


class BbvaReadingQualityTests(unittest.TestCase):
    def test_page_with_its_own_period_is_assessed(self):
        result = assess_statement_reading(bbva())
        self.assertEqual(result['identity'], ['bbva-mexico-cash-management', '0000012345', '2024-09-01', '2024-09-30'])
        self.assertEqual((result['payments'], result['balances'], result['unreadable']), (1, 2, 0))
        self.assertEqual(page_controls_reconcile(bbva())['reconciles'], True)

    def test_damaged_charge_is_unreadable(self):
        result = assess_statement_reading(bbva(amount='1Z.94'))
        self.assertEqual(result['missing_fields']['amount_minor'], 1)
        self.assertEqual(page_controls_reconcile(bbva(amount='1Z.94'))['reconciles'], False)

    def test_continuation_page_without_its_period_is_not_assessed(self):
        self.assertIsNone(assess_statement_reading(bbva(page_line='PAGINA 2/2', period=False)))


if __name__ == '__main__':
    unittest.main()
