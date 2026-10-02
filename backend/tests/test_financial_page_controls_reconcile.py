"""Page-level control check that gates a second reader's value; synthetic data only.

The fixture holds two pages of the synthetic benchmark corpus as the engine
reads them (Credit One cycle 6 and Andrews 2021-05), each with the page
reading restored in its disputed cells and the value the page image prints.
In both, two misreads compensate, so both readings reconcile.
"""
import copy
import json
import unittest
from pathlib import Path

from services.financial.statement_reading_quality import page_controls_reconcile
from tests.test_financial_generic_reading_quality import PAYMENTS, payments_with, statement

FIXTURE = json.loads((Path(__file__).parent / 'financial_page_controls_fixture.json').read_text())


def corpus_page(name, *, image_cells=()):
    """The page reading, with the image's value placed in each listed disputed cell."""
    page = FIXTURE[name]
    tables = copy.deepcopy(page['tables'])
    for index in image_cells:
        table, row, column = page['disputed'][index]['cell']
        cell = next(v for v in tables[table]['table']['values'] if (v['row'], v['column']) == (row, column))
        cell['text'] = page['disputed'][index]['image']
    return tables


CARD = 'credit-one-cycle-6-ocr-valid-but-wrong-cancelling.pdf'
ANDREWS = 'andrews-2021-05-ocr-valid-but-wrong-consistent.pdf'


class PageControlsReconcileTests(unittest.TestCase):
    def test_generic_page_whose_chain_and_closing_balance_match_reconciles(self):
        result = page_controls_reconcile(statement())
        self.assertTrue(result['reconciles'])
        checks = {c['kind']: c['status'] for c in result['statements'][0]['checks']}
        self.assertEqual((checks['closing_balance'], checks['running_balance']), ('matches', 'matches'))

    def test_a_value_the_printed_balances_contradict_is_refused(self):
        result = page_controls_reconcile(statement(payments=payments_with(1, amount='88.13')))
        self.assertFalse(result['reconciles'])
        self.assertIn('difference', {c['status'] for c in result['statements'][0]['checks']})

    def test_an_unreadable_cell_or_a_missing_closing_balance_never_reconciles(self):
        for name, table in (('held amount', statement(payments=payments_with(1, amount='8?.13'))),
                            ('no closing balance', statement(closing='')),
                            ('no opening balance', statement(opening=''))):
            with self.subTest(name):
                self.assertFalse(page_controls_reconcile(table)['reconciles'])

    def test_page_no_layout_claims_is_not_assessed(self):
        header = ['Bank: Example Synthetic Bank', 'Statement Period: March 1, 2023 - March 31, 2023']
        self.assertIsNone(page_controls_reconcile(statement(header=header, payments=PAYMENTS)))
        self.assertIsNone(page_controls_reconcile([]))

    def test_card_page_compensating_readings_both_reconcile_and_either_alone_does_not(self):
        self.assertTrue(page_controls_reconcile(corpus_page(CARD))['reconciles'])
        image = page_controls_reconcile(corpus_page(CARD, image_cells=(0, 1)))
        self.assertTrue(image['reconciles'])
        self.assertEqual(image['statements'][0]['identity'][0], 'credit-one-card')
        for one in (0, 1):
            with self.subTest(cell=one):
                self.assertFalse(page_controls_reconcile(corpus_page(CARD, image_cells=(one,)))['reconciles'])

    def test_every_andrews_share_statement_on_the_page_is_checked(self):
        result = page_controls_reconcile(corpus_page(ANDREWS, image_cells=(0, 1, 2)))
        self.assertTrue(result['reconciles'])
        self.assertEqual([s['identity'][1] for s in result['statements']],
                         ['123456789 / Share 0000', '123456789 / Share 0040'])
        self.assertTrue(page_controls_reconcile(corpus_page(ANDREWS))['reconciles'])
        # The amount alone, or the running balance without the ending balance, breaks a printed control.
        for cells in ((0,), (0, 1), (1, 2)):
            with self.subTest(cells=cells):
                self.assertFalse(page_controls_reconcile(corpus_page(ANDREWS, image_cells=cells))['reconciles'])


if __name__ == '__main__':
    unittest.main()
