"""Copies of one statement must not settle each other while none of them is saved (fin-queue lessons 5 and 12).

Live shapes (BNB2, 2026-10-26): every upload of 08 CAAL BBVA MXN AGO 25 and of MONETA BBVA SEP 25 USD sat under
'copies' (set aside for, or held by coverage against, each other) while the ledger had no Aug 2025 / Sep 2025
period for those accounts; nobody was asked. Synthetic values only.
"""
from datetime import date
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from services.financial import review_queue as rq
from services.financial import statement_import_overlap as overlap


class _Ledger:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, _statement):
        return SimpleNamespace(all=lambda: self.rows)


def entry(identifier, bucket='copies', account='0119200843', start='2025-08-01', end='2025-08-31', set_aside=False):
    return dict(id=identifier, bucket=bucket, account=account, currency='MXN', period_start=start, period_end=end,
                set_aside=set_aside, filename='08 SYNTHETIC BBVA MXN AGO 25.pdf')


class CopiesNoneSavedTests(TestCase):
    def test_one_copy_of_a_statement_nobody_saved_waits_with_the_reason(self):
        entries = [entry('b', set_aside=True), entry('a')]
        july = ('0119200843', 'MXN', date(2025, 7, 1), date(2025, 7, 31))
        rq._copies_none_saved(_Ledger([july]), 'case', entries)
        self.assertEqual([(e['id'], e['bucket']) for e in entries], [('b', 'copies'), ('a', 'waiting')])
        self.assertEqual(entries[1]['issue_reason'], 'copies_none_saved')
        self.assertIn('none of them is saved', entries[1]['issue'])

    def test_a_saved_period_of_the_account_or_a_saved_entry_settles_its_copies(self):
        clabe = ('012180001192008435', 'MXN', date(2025, 8, 1), date(2025, 8, 31))  # the account inside its CLABE
        entries = [entry('a')]
        rq._copies_none_saved(_Ledger([clabe]), 'case', entries)
        self.assertEqual(entries[0]['bucket'], 'copies')
        entries = [entry('a'), entry('s', bucket='imported')]
        rq._copies_none_saved(_Ledger([]), 'case', entries)
        self.assertEqual(entries[0]['bucket'], 'copies')
        # A copy left unimported carries a person's reason (live: a Santander movement extract whose 5 movements are
        # all saved from the monthly statements); the statement is decided, not forgotten.
        entries = [entry('a'), entry('l', bucket='left_unimported')]
        rq._copies_none_saved(_Ledger([]), 'case', entries)
        self.assertEqual(entries[0]['bucket'], 'copies')
        other_currency = ('0119200843', 'USD', date(2025, 8, 1), date(2025, 8, 31))
        entries = [entry('a')]
        rq._copies_none_saved(_Ledger([other_currency]), 'case', entries)
        self.assertEqual(entries[0]['bucket'], 'waiting')
        entries = [entry('a')]
        with patch.object(rq, 'COPIES_NONE_SAVED', False):
            rq._copies_none_saved(_Ledger([]), 'case', entries)
        self.assertEqual(entries[0]['bucket'], 'copies')


def _file(identifier, sha, decision=None, key='k'):
    metadata = {'financial_duplicate_dispositions': {key: decision}} if decision else {}
    return SimpleNamespace(id=identifier, sha256=sha, metadata_=metadata)


class UnsavedIdenticalUploadTests(TestCase):
    """The copy the copy rule keeps is not held by an unsaved upload of its very bytes and statement."""

    def setUp(self):
        self.own = _file('f1', 'a' * 64, dict(status='retained', reading_revision='r1'))
        self.other = _file('f2', 'a' * 64, dict(status='needs_comparison'))
        self.candidate = dict(status='awaiting_import', statement_id='k', file_id='f2')
        self.files = {'f2': self.other}

    def held(self, request, candidate=None, files=None):
        return not overlap._copy_of_retained(None, self.own, files or self.files, candidate or self.candidate,
                                             dict(statement_id='k', **request))

    def test_only_the_retained_copy_is_released(self):
        self.assertFalse(self.held(dict(expected_revision='r1')))
        # Decided on another reading, or the projection's own copy rule did not retain it: still held.
        self.assertTrue(self.held(dict(expected_revision='r2')))
        self.assertTrue(self.held(dict(expected_revision='r1', _copy_rule_status='needs_comparison')))
        self.assertFalse(self.held(dict(expected_revision='r9', _copy_rule_status='retained')))
        # Both copies claiming to be retained: never both released.
        both = {'f2': _file('f2', 'a' * 64, dict(status='retained', reading_revision='r1'))}
        self.assertTrue(self.held(dict(expected_revision='r1'), files=both))

    def test_a_saved_copy_other_bytes_or_another_statement_are_still_compared(self):
        self.assertTrue(self.held(dict(expected_revision='r1'), candidate=dict(self.candidate, status='imported')))
        self.assertTrue(self.held(dict(expected_revision='r1'), files={'f2': _file('f2', 'b' * 64)}))
        self.assertTrue(self.held(dict(expected_revision='r1'), candidate=dict(self.candidate, statement_id='other')))
