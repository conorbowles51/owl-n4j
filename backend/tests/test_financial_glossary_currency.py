from unittest import TestCase

from services.financial import statement_engine as engine


class GlossaryCurrencyTests(TestCase):
    """r15-hold-gaps item 3: a glossary entry defining a payment system never names a section's currency."""

    def test_an_acronym_definition_is_recognised_and_ordinary_headings_are_not(self):
        self.assertTrue(engine._defines_acronym('SPID-SISTEMA DE PAGOS INTERBANCARIOS EN DOLARES'))
        self.assertTrue(engine._defines_acronym('SPEI-SISTEMA DE PAGOS ELECTRONICOS SPID-Sistema de Pagos Interbancarios en Dólares'))
        for text in ('CUENTA EJE-DOLARES', 'CHEQUES - DOLARES', 'SALDO EN DOLARES', 'USD-DOLAR ESTADOUNIDENSE', 'ABC-ALPHA BETA'):
            self.assertFalse(engine._defines_acronym(text), text)

    def test_the_glossary_line_names_no_heading_currency(self):
        from tests.test_financial_statement_engine import page
        rows = engine._pages([page(1, [[('SPID-SISTEMA DE PAGOS INTERBANCARIOS EN DOLARES', 20000, 300000)],
                                       [('CUENTA EN DOLARES', 20000, 200000)]])])[1]
        self.assertEqual([engine._heading_currencies([row], 'dot') for row in rows], [set(), {'USD'}])
