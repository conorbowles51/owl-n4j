"""Reader-failure alarm (fin-holes B): a held statement the reader got nothing out of, from pages that carry text,
is a reader problem: listed under the reader fix with every action, registered and reported."""
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from services.financial import reader_gaps as rg
from services.financial import statement_engine_profiles as profiles
from services.financial.statement_engine import read_statements
from services.financial.statement_engine_routing import _profiled

FIXTURE = os.path.join(os.path.dirname(__file__), 'financial_truist_consolidated_fixture.json')


def _summary_of(statement):
    """The counts the batch summary carries for one engine statement (import_batches.assess): payments, lines read
    but not understood, period, and the printed balances its closing-balance check uses."""
    rows = statement.get('_rows') or []
    transactions = sum(r['kind'] == 'transaction' and not r.get('excluded') for r in rows)
    unclassified = sum(r['kind'] in ('unresolved', 'unclassified') for r in rows)
    balances = {(r.get('fields') or {}).get('description', '').lower(): (r.get('fields') or {}).get('balance')
                for r in rows if r['kind'] == 'balance'}
    return dict(transaction_count=transactions, record_count=transactions, incomplete_count=0,
                unclassified_count=unclassified, period_start=statement.get('period_start') or '',
                period_end=statement.get('period_end') or '',
                checks=[dict(kind='closing_balance', opening_minor=balances.get('opening balance'),
                             printed_minor=balances.get('closing balance'))])


# The live summary of OPDMD66 'CommitmentLetter (3).pdf' as read before the Truist reader (2026-10-27 18:02;
# currency and holder from the review a person saved at 18:03): queued as "Needs you", not as a reader problem.
OPDMD66_BEFORE = {'transaction_count': 0, 'record_count': None, 'incomplete_count': None, 'unclassified_count': 249,
                  'period_start': '', 'period_end': '', 'holder': 'Keny V Alvarado Gomez', 'currency': 'USD',
                  'institution': 'Truist Bank', 'problems': [{'row_id': None, 'message': 'Enter at least one printed '
                  'opening or closing balance to save a statement without transactions.'}],
                  'checks': [{'kind': 'closing_balance', 'status': 'unavailable', 'opening_minor': None}]}


class ReaderGapTest(unittest.TestCase):
    def test_truist_before_its_reader_is_a_reader_gap_and_after_it_is_not(self):
        with open(FIXTURE) as handle:
            sources = json.load(handle)
        without = [p for p in profiles.PROFILES if p['name'] != 'truist-consolidated']
        with mock.patch.object(profiles, 'PROFILES', without):
            before, profile = _profiled(sources, read_statements(sources))
        self.assertIsNone(profile)
        self.assertTrue(before)
        for statement in before:
            summary = _summary_of(statement)
            self.assertEqual(summary['transaction_count'], 0)
            self.assertGreater(summary['unclassified_count'], 0)
            self.assertTrue(rg.reader_gap(summary))
        after, profile = _profiled(sources, read_statements(sources))
        self.assertEqual(profile, 'truist-consolidated')
        self.assertFalse(any(rg.reader_gap(_summary_of(statement)) for statement in after))

    def test_the_live_opdmd66_reading_is_flagged(self):
        self.assertTrue(rg.reader_gap(OPDMD66_BEFORE))

    def test_what_is_not_a_reader_gap(self):
        self.assertFalse(rg.reader_gap(OPDMD66_BEFORE, status='ready'))
        self.assertFalse(rg.reader_gap(dict(OPDMD66_BEFORE, period_end='2024-02-12')))  # a quiet period
        self.assertFalse(rg.reader_gap(dict(OPDMD66_BEFORE, transaction_count=1)))
        self.assertFalse(rg.reader_gap(dict(OPDMD66_BEFORE, record_count=0, incomplete_count=2)))
        self.assertFalse(rg.reader_gap(dict(OPDMD66_BEFORE, unclassified_count=0)))  # no text: the image reader's
        self.assertFalse(rg.reader_gap(dict(OPDMD66_BEFORE, checks=[{'kind': 'closing_balance', 'printed_minor': '0'}])))
        self.assertFalse(rg.reader_gap(dict(OPDMD66_BEFORE, not_payment_statement={'kind': 'fund'})))
        self.assertFalse(rg.reader_gap(dict(OPDMD66_BEFORE, assignment_only=True)))
        with mock.patch.object(rg, 'ENABLED', False):
            self.assertFalse(rg.reader_gap(OPDMD66_BEFORE))


TRUIST_PAGE = ['467-11-01-00 60309 0 C 001 07 S | 66 002', 'KENY | V | ALVARADO | GOMEZ', '7509 | AXTON | ST',
               'Your consolidated statement | Contact us', 'For 02/12/2024 | Truist.com | (844) 487-8478',
               'If you are traveling outside of the USA and have concerns about accessing your account while you are traveling, please contact your',
               'Summary of your accounts', 'ACCOUNT NAME | ACCOUNT NUMBER | BALANCE($) | DETAILS ON',
               'Checking and money market savings accounts', 'Account summary']


class FingerprintTest(unittest.TestCase):
    def test_labels_not_names_addresses_or_notices(self):
        self.assertEqual(rg.label_lines(TRUIST_PAGE)[:3], ['your consolidated statement contact us',
                                                           'summary of your accounts',
                                                           'checking and money market savings accounts'])

    def test_another_holder_s_statement_of_the_layout_has_the_same_fingerprint(self):
        other = ['JOHN | Q | PUBLIC', '1 MAIN ST'] + TRUIST_PAGE[3:6] + ['A different notice this month, please read it carefully before you call us.'] + TRUIST_PAGE[6:]
        self.assertEqual(rg.fingerprint(other)[0], rg.fingerprint(TRUIST_PAGE)[0])
        self.assertNotEqual(rg.fingerprint(['Your account statement | Contact us'] + TRUIST_PAGE[6:])[0],
                            rg.fingerprint(TRUIST_PAGE)[0])

    def test_bank_guess(self):
        self.assertEqual(rg.bank_guess({'institution': 'Truist Bank'}, []), 'Truist Bank')
        self.assertEqual(rg.bank_guess({'institution': 'refer to the Commercial Bank Services Agreement.)'}, TRUIST_PAGE), 'Truist')


class RegisterTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), 'gaps.json')

    def _entry(self, file_id, mark='abc'):
        return dict(case_id='c1', file_id=file_id, statement_key='', filename=file_id + '.pdf', bank='Truist',
                    fingerprint=mark, labels=['x'], text_pages=[1, 2], page_count=2, unclassified_lines=5)

    def test_first_seen_counted_by_layout_resolved_never_deleted(self):
        found = {'f1:': self._entry('f1'), 'f2:': self._entry('f2')}
        new = rg.record(found, now='t1', path=self.path)
        self.assertEqual(len(new), 2)
        self.assertEqual(rg.record(found, now='t2', path=self.path), [])
        data = rg.read_register(self.path)
        self.assertEqual(data['statements']['f1:']['first_seen'], 't1')
        self.assertEqual(data['statements']['f1:']['last_seen'], 't2')
        self.assertEqual(data['statements']['f1:']['files_with_layout'], 2)
        self.assertEqual(data['layouts']['abc']['held_files'], 2)
        rg.record({'f2:': self._entry('f2')}, now='t3', path=self.path)
        data = rg.read_register(self.path)
        self.assertEqual(data['statements']['f1:']['resolved_at'], 't3')
        self.assertEqual(data['layouts']['abc']['files'], 2)
        self.assertEqual(data['layouts']['abc']['held_files'], 1)
        again = rg.record(found, now='t4', path=self.path)
        self.assertEqual([e['file_id'] for e in again], ['f1'])
        self.assertEqual(rg.read_register(self.path)['statements']['f1:']['reopened_at'], 't4')

    def test_sweep_warns_once_per_newly_seen_statement(self):
        found = {'f1:': self._entry('f1')}

        class Factory:
            def __call__(self):
                return self

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def rollback(self):
                pass
        with mock.patch.object(rg, 'scan', return_value=found), self.assertLogs(rg.log, level='WARNING') as logs:
            self.assertEqual(rg.sweep(Factory(), path=self.path), dict(held=1, new=1))
        self.assertIn('READER GAP: case c1 file f1 "f1.pdf"', logs.output[0])
        with mock.patch.object(rg, 'scan', return_value=found), mock.patch.object(rg.log, 'warning') as warning:
            self.assertEqual(rg.sweep(Factory(), path=self.path), dict(held=1, new=0))
        warning.assert_not_called()
        self.assertEqual(rg.summary_for_admin(self.path)['held'], 1)


class QueueTest(unittest.TestCase):
    def _item(self, summary):
        return SimpleNamespace(id='i1', file_id='f1', statement_key='', status='attention',
                               summary=dict(dict(filename='CommitmentLetter (3).pdf'), **summary))

    def test_a_reader_gap_leaves_needs_you_for_the_reader_fix_with_its_actions(self):
        from services.financial import review_queue as rq
        self.assertEqual(rq.classify(self._item(OPDMD66_BEFORE)), 'waiting')  # before: a person's task
        entries = [dict(rq._entry(self._item(OPDMD66_BEFORE), 'b1'), bucket='reader_fix', root='r1', held_bucket='waiting',
                        reader_gap=True)]
        files = rq.reader_files(entries)
        self.assertTrue(files[0]['reader_gap'])
        self.assertIn('could not read this layout yet', files[0]['message'])
        self.assertIn('it has been reported', files[0]['message'])


if __name__ == '__main__':
    unittest.main()
