"""The statement automation benchmark corpus and its scoring rules.

Corpus v4 appends to v3; results stay comparable only if every earlier file
and ground truth is unchanged and the new statements cannot interact with the
old ones (no shared account). Rendering needs PyMuPDF; the byte check is
skipped where it is not installed.
"""
import hashlib
import json
import unittest
from pathlib import Path

from benchmarks.statement_automation import corpus, harness

MANIFEST = json.loads((Path(corpus.__file__).with_name('corpus') / 'manifest.json').read_text())
V3_FILES = 36

try:
    import fitz  # noqa: F401
except ImportError:  # pragma: no cover - depends on the interpreter
    fitz = None


class CorpusTests(unittest.TestCase):
    def test_v4_appends_after_the_unchanged_v3_files(self):
        self.assertEqual(MANIFEST['version'], 'statement-automation-corpus-v4')
        self.assertEqual([e['filename'] for e in corpus.build()], [f['filename'] for f in MANIFEST['files']])
        for record in MANIFEST['files'][:V3_FILES]:
            for period in record['periods']:
                self.assertNotIn('added_in', period, record['filename'])
        for record in MANIFEST['files'][V3_FILES:]:
            for period in record['periods']:
                self.assertEqual(period['added_in'], 'v4', record['filename'])

    def test_v4_statements_share_no_account_with_v3(self):
        old = {p['account'] for f in MANIFEST['files'][:V3_FILES] for p in f['periods']}
        new = {p['account'] for f in MANIFEST['files'][V3_FILES:] for p in f['periods']}
        self.assertFalse(old & new)

    def test_ground_truth_outcomes_are_explicit(self):
        for record in MANIFEST['files']:
            for period in record['periods']:
                self.assertIn(period['expected'], ('auto', 'decision', 'hold', 'duplicate', 'not_statement'))
            if record.get('missing_pages'):
                self.assertIn('hold', {p['expected'] for p in record['periods']}, record['filename'])

    @unittest.skipIf(fitz is None, 'PyMuPDF is not installed')
    def test_every_file_regenerates_to_its_manifest_bytes(self):
        produced = {}
        for entry, record in zip(corpus.build(), MANIFEST['files']):
            if 'copy_of' in entry:
                data = produced[entry['copy_of']]
            else:
                data = corpus.render(entry['pages'], entry['mode'], entry.get('degrade'), entry.get('rules'))
            produced[entry['filename']] = data
            self.assertEqual(hashlib.sha256(data).hexdigest(), record['sha256'], record['filename'])


class ScoringTests(unittest.TestCase):
    def period(self, expected, can_import, truth_id='x.pdf#1'):
        return dict(item_id='i', filename='x.pdf', statement_id=None, status='ready' if can_import else 'attention',
                    can_import=can_import, truth_id=truth_id, family='f', expected=expected, defects=[],
                    added_in='v4', reasons={}, problems=[], read={})

    def test_a_receipt_offered_for_import_is_a_wrong_admission(self):
        block = harness.metrics(dict(periods=[self.period('not_statement', True)]))['overall']
        self.assertEqual(block['wrongly_ready'], ['x.pdf#1'])
        self.assertEqual(block['hold_periods'], 1)
        self.assertEqual(block['holds_kept'], 0)

    def test_an_unmatched_batch_item_is_not_a_distinct_period(self):
        unmatched = self.period(None, False, truth_id=None)
        block = harness.metrics(dict(periods=[self.period('auto', True), unmatched]))['overall']
        self.assertEqual(block['periods'], 1)
        self.assertEqual(block['unmatched_items'], 1)
        self.assertEqual(block['ready_without_edits'], 1)



class CopyPairingTests(unittest.TestCase):
    """A statement printed twice in one file: whichever identical copy is admitted is scored."""

    def truths(self, second_rows=((500, 'debit'),)):
        rows = [dict(amount_minor=a, direction=d, date='2024-03-05', description='x') for a, d in ((500, 'debit'),)]
        copy = [dict(amount_minor=a, direction=d, date='2024-03-05', description='x') for a, d in second_rows]
        base = dict(currency='USD', opening_minor=100, closing_minor=600, defects=[], truth_status='verified')
        return {'x.pdf#12': dict(base, id='x.pdf#12', expected='auto', duplicate_of=None, rows=rows),
                'x.pdf#13': dict(base, id='x.pdf#13', expected='duplicate', duplicate_of='x.pdf#12', rows=copy,
                                 truth_status='ocr_reconciled')}

    def periods(self):
        return [dict(item_id='a', truth_id='x.pdf#12', expected='auto', scored=True, status='duplicate_ignored',
                     can_import=False, defects=[], family='f', reasons={}, correction=dict(actions=[])),
                dict(item_id='b', truth_id='x.pdf#13', expected='duplicate', scored=False, status='ready',
                     can_import=True, defects=[], family='f', reasons={})]

    def test_the_admitted_identical_copy_is_scored_as_the_statement(self):
        periods = harness.pair_identical_copies(self.periods(), self.truths())
        by_item = {p['item_id']: p for p in periods}
        self.assertEqual((by_item['b']['truth_id'], by_item['b']['expected'], by_item['b']['scored']),
                         ('x.pdf#12', 'auto', True))
        self.assertEqual((by_item['a']['truth_id'], by_item['a']['expected'], by_item['a']['scored']),
                         ('x.pdf#13', 'duplicate', False))
        block = harness.metrics(dict(periods=periods))['overall']
        self.assertEqual((block['ready_without_edits'], block['periods']), (1, 1))

    def test_copies_whose_money_differs_keep_their_pairing(self):
        periods = harness.pair_identical_copies(self.periods(), self.truths(second_rows=((501, 'debit'),)))
        self.assertEqual([p['truth_id'] for p in periods], ['x.pdf#12', 'x.pdf#13'])

    def test_an_admitted_original_or_a_held_copy_is_left_as_paired(self):
        periods = self.periods()
        periods[1].update(status='attention', can_import=False)
        self.assertEqual([p['truth_id'] for p in harness.pair_identical_copies(periods, self.truths())],
                         ['x.pdf#12', 'x.pdf#13'])


class PairingTests(unittest.TestCase):
    """Batch items pair with ground truth by content; currency only breaks ties."""

    def truth(self, period_id, currency, amounts=()):
        return dict(id=period_id, currency=currency, period_end='2024-03-31', share=None,
                    rows=[dict(amount_minor=a, description=f'row {a}', direction='debit', date='2024-03-05')
                          for a in amounts], account='1234')

    def proposal(self, currency, amounts=()):
        rows = [dict(id=str(i), excluded=False, kind='transaction',
                     fields=dict(amount_minor=str(a), description=f'row {a}', direction='debit', date='2024-03-05'))
                for i, a in enumerate(amounts)]
        return dict(currency=currency, metadata={}, rows=rows)

    def test_sections_differing_only_by_currency_pair_by_currency_not_order(self):
        mxn, usd = self.truth('m.pdf#1', 'MXN'), self.truth('m.pdf#2', 'USD')
        item = dict(period_end='2024-03-31', currency='USD')
        self.assertIs(harness.pair_truth(self.proposal('USD'), [mxn, usd], item), usd)
        item = dict(period_end='2024-03-31', currency='MXN')
        self.assertIs(harness.pair_truth(self.proposal('MXN'), [usd, mxn], item), mxn)

    def test_a_misread_currency_still_pairs_by_content(self):
        mxn = self.truth('m.pdf#1', 'MXN', amounts=[1000, 2500])
        usd = self.truth('m.pdf#2', 'USD')
        item = dict(period_end='2024-03-31', currency='USD')
        proposal = self.proposal('USD', amounts=[1000, 2500])
        self.assertIs(harness.pair_truth(proposal, [mxn, usd], item), mxn)
        self.assertEqual(harness.proposal_field_errors(proposal, mxn).get('currency_wrong'), 1)

    def test_no_evidence_at_all_leaves_a_multi_period_item_unmatched(self):
        first, second = self.truth('m.pdf#1', 'MXN'), self.truth('m.pdf#2', 'USD')
        item = dict(period_end='2024-04-30', currency='')
        self.assertIsNone(harness.pair_truth(self.proposal(''), [first, second], item))
        self.assertIs(harness.pair_truth(None, [first], item), first)
        self.assertIsNone(harness.pair_truth(None, [first, second], item))


if __name__ == '__main__':
    unittest.main()
