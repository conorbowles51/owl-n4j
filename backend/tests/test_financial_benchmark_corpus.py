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


if __name__ == '__main__':
    unittest.main()
