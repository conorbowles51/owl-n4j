"""Choosing a held Andrews money cell's printed reading by the page's agreed controls; synthetic data only.

The fixture holds three pages of the synthetic benchmark corpus (v4 Andrews
150 dpi, 100 dpi and combined-damage scans) as the engine reads them, with
each held money cell in its held form and its six crop readings. The
compensating Andrews page comes from the page-controls fixture.
"""
import copy
import json
import unittest
from pathlib import Path

from services.financial.statement_reading_quality import pinned_andrews_values
from tests.test_financial_generic_reading_quality import statement
from tests.test_financial_page_controls_reconcile import ANDREWS, FIXTURE as CONTROLS

FIXTURE = json.loads((Path(__file__).parent / 'financial_andrews_pinned_reading_fixture.json').read_text())
P150 = 'andrews-v4-2022-04-scan-150dpi.pdf'
P100 = 'andrews-v4-2022-05-scan-100dpi.pdf'
COMBINED = 'andrews-v4-2022-08-scan-combined.pdf'


def page(name):
    return copy.deepcopy(FIXTURE[name]['tables'])


class PinnedAndrewsValuesTests(unittest.TestCase):
    def test_crop_reading_of_an_unreadable_sign_is_accepted_when_the_running_balances_pin_it(self):
        result = pinned_andrews_values(page(P150), {(0, 15, 2): ['-61.27']})
        self.assertEqual(result['values'], {(0, 15, 2): dict(text='-61.27', pinned_by=[[0, 14, 3], [0, 15, 3]])})
        self.assertTrue(result['controls']['reconciles'])

    def test_page_reading_beats_a_crop_majority_that_the_running_balances_contradict(self):
        # Four of six crops drop the minus and read 7,180.20; the printed balances fix -61.28 and 7,150.20.
        result = pinned_andrews_values(page(P100), {(0, 15, 2): ['-61.28', '61.28'],
                                                    (0, 17, 3): ['7,150.20', '7,180.20']})
        self.assertEqual({key: value['text'] for key, value in result['values'].items()},
                         {(0, 15, 2): '-61.28', (0, 17, 3): '7,150.20'})
        self.assertEqual(result['values'][(0, 17, 3)]['pinned_by'], [[0, 16, 3], [0, 17, 2]])

    def test_crop_readings_alone_that_the_controls_contradict_are_refused(self):
        self.assertEqual(pinned_andrews_values(page(P100), {(0, 15, 2): ['61.28'], (0, 17, 3): ['7,180.20']}), {})
        # One cell resolved is not enough: all or nothing.
        self.assertEqual(pinned_andrews_values(page(P100), {(0, 15, 2): ['-61.28'], (0, 17, 3): ['7,180.20']}), {})

    def test_a_withdrawal_whose_sign_glyph_no_reader_named_takes_the_sign_its_balances_fix(self):
        result = pinned_andrews_values(page(COMBINED), {(0, 15, 2): ['61.31', '-61.31']})
        self.assertEqual(result['values'][(0, 15, 2)]['text'], '-61.31')
        # Without the minus the printed verb contradicts the amount: no equation, nothing accepted.
        self.assertEqual(pinned_andrews_values(page(COMBINED), {(0, 15, 2): ['61.31']}), {})

    def test_compensating_misreads_that_share_their_equations_stay_held(self):
        # Amount, running balance and ending balance disputed together: no
        # equation holds only one of them, so neither reading is pinned.
        controls = CONTROLS[ANDREWS]
        tables = copy.deepcopy(controls['tables'])
        candidates = {tuple(d['cell']): [d['page_reading'], d['image']] for d in controls['disputed']}
        self.assertEqual(pinned_andrews_values(tables, candidates), {})

    def test_two_readings_each_pinned_by_a_different_equation_are_refused(self):
        # The running balance after 04/08 is the only disputed cell of two
        # equations. With the next payment changed, each equation fixes a
        # different reading, so the controls do not choose one.
        tables = page(P150)
        for value in tables[0]['table']['values']:
            if (value['row'], value['column']) == (15, 2):
                value['text'] = '-61.27'
            if (value['row'], value['column']) == (16, 2):
                value['text'] = '1,240.00'  # 6,488.88 - 1,240.00 = 5,248.88
        self.assertEqual(pinned_andrews_values(tables, {(0, 15, 3): ['5,278.88', '5,248.88']}), {})
        # Either reading alone is pinned, but the changed payment breaks the page's controls.
        self.assertEqual(pinned_andrews_values(tables, {(0, 15, 3): ['5,278.88']}), {})

    def test_other_layouts_and_empty_requests_are_not_assessed(self):
        self.assertIsNone(pinned_andrews_values(statement(), {(0, 7, 2): ['85.13']}))
        self.assertEqual(pinned_andrews_values(page(P150), {}), {})
        self.assertEqual(pinned_andrews_values(page(P150), {(0, 15, 2): []}), {})

    def test_unparseable_candidate_is_refused(self):
        self.assertEqual(pinned_andrews_values(page(P150), {(0, 15, 2): ['-6l.27']}), {})


if __name__ == '__main__':
    unittest.main()
