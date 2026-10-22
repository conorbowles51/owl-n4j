"""Each queue row carries the statement's printed opening and closing balances, so it can be
checked against the PDF at a glance. They are copied from the stored preparation; nothing is read."""
from types import SimpleNamespace
from unittest import TestCase
from uuid import uuid4

from services.financial.review_queue import _entry


def stored(**summary):
    return SimpleNamespace(id=uuid4(), file_id=uuid4(), statement_key='', status='attention',
                           summary=dict(filename='Savings.pdf', period_start='2021-01-01', period_end='2021-01-31', **summary))


class QueueBalancesTests(TestCase):
    def test_a_row_carries_the_printed_opening_and_closing_balances(self):
        entry = _entry(stored(transaction_count=12, balance_status='matches', checks=[
            dict(kind='closing_balance', status='matches', opening_minor='100000', printed_minor='95050',
                 expected_minor='95050', difference_minor='0'),
            dict(kind='running_balance', status='matches')]), uuid4())
        self.assertEqual((entry['opening_minor'], entry['closing_minor']), ('100000', '95050'))
        self.assertEqual((entry['balance_status'], entry['transaction_count']), ('matches', 12))

    def test_a_missing_balance_is_none_not_zero(self):
        entry = _entry(stored(transaction_count=0, balance_status='unavailable', checks=[
            dict(kind='closing_balance', status='unavailable', opening_minor=None, printed_minor='500')]), uuid4())
        self.assertIsNone(entry['opening_minor'])
        self.assertEqual(entry['closing_minor'], '500')
        entry = _entry(stored(), uuid4())
        self.assertEqual((entry['opening_minor'], entry['closing_minor'], entry['balance_status']), (None, None, ''))
