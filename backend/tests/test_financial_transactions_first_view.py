"""The Transactions page's first view on the server: the browser's own calculations over the same ledger rows.

The equality with the browser's code over the six live cases is a gate run outside the suite; these tests pin the
behaviours that differ between Python and the browser unless written out (JavaScript's trim, truthiness and BigInt,
the table's page clamp) and the shape the page reads."""
import unittest

from services.financial.transactions_first_view import (Unavailable, first_view, js_bigint, needs_confirm,
                                                         needs_name, page_index, touched)

NO_CALLS = {'judgements': [], 'transactions': {}, 'documents': {}}


def row(key, **fields):
    base = {'key': key, 'case_id': 'c1', 'account_id': 'acc-1', 'source_document_id': 'doc-1', 'currency': 'MXN',
            'direction': 'debit', 'amount_minor': '100', 'ordering_date': '2025-01-02', 'to_name': 'Shop'}
    base.update(fields)
    return base


class NeedsNameTests(unittest.TestCase):
    def test_the_other_side_is_the_payer_for_money_in_and_the_payee_otherwise(self):
        self.assertTrue(needs_name(row('a', direction='credit', from_name=None, to_name='Me')))
        self.assertFalse(needs_name(row('b', direction='debit', from_name=None, to_name='Shop')))

    def test_javascript_trim_counts_unicode_spaces_as_empty(self):
        self.assertTrue(needs_name(row('a', to_name='   ', counterparty_raw='﻿')))
        self.assertFalse(needs_name(row('b', to_name=None, counterparty_raw=' raw ')))

    def test_a_link_or_a_persons_label_names_the_payment(self):
        self.assertFalse(needs_name(row('a', to_name='', counterparty_link={'party_id': 'p'})))
        self.assertTrue(needs_name(row('b', to_name='', counterparty_link='')))
        self.assertFalse(needs_name(row('c', to_name='', label_sources={'to_name': {'source': 'investigator'}})))
        self.assertTrue(needs_name(row('d', to_name='', label_sources={'from_name': {'source': 'investigator'}})))

    def test_a_name_that_is_not_text_is_left_to_the_browser(self):
        with self.assertRaises(Unavailable):
            needs_name(row('a', to_name=5))


class NeedsConfirmTests(unittest.TestCase):
    def test_a_model_reading_on_either_side_needs_a_person(self):
        self.assertTrue(needs_confirm(row('a', label_sources={'from_name': {'source': 'model_reading'}})))
        self.assertTrue(needs_confirm(row('b', label_sources={'to_name': {'source': 'model_reading'}})))
        self.assertFalse(needs_confirm(row('c', label_sources={'to_name': {'source': 'investigator'}})))
        self.assertFalse(needs_confirm(row('d', label_sources=None)))


class TouchedTests(unittest.TestCase):
    def test_a_call_on_the_payment_or_on_its_whole_statement_touches_it(self):
        calls = {'judgements': [{'id': 'j1'}, {'id': 'j2'}], 'transactions': {'a': ['j1']},
                 'documents': {'doc-2': ['j2']}}
        self.assertTrue(touched(row('a'), calls))
        self.assertTrue(touched(row('b', source_document_id='doc-2'), calls))
        self.assertFalse(touched(row('c'), calls))

    def test_an_id_with_no_call_behind_it_touches_nothing(self):
        calls = {'judgements': [], 'transactions': {'a': ['gone']}, 'documents': {'doc-1': ['gone']}}
        self.assertFalse(touched(row('a'), calls))


class AmountTests(unittest.TestCase):
    def test_bigint_accepts_what_it_accepts_and_refuses_the_rest(self):
        self.assertEqual(js_bigint(' -12 '), -12)
        self.assertEqual(js_bigint(''), 0)
        self.assertEqual(js_bigint('0x1f'), 31)
        self.assertEqual(js_bigint(7), 7)
        for value in ('1.5', None, 1.5, '-0x1', 'abc'):
            with self.assertRaises(Unavailable):
                js_bigint(value)


class FirstViewTests(unittest.TestCase):
    def test_figures_per_currency_in_first_met_order_and_counts_over_every_row(self):
        rows = [row('a', currency='USD', direction='credit', amount_minor='500', from_name=None),
                row('b', amount_minor='70'),
                row('c', direction='credit', amount_minor='30', from_name='Payer',
                    label_sources={'from_name': {'source': 'model_reading'}}),
                row('d', direction='reversal', amount_minor='5')]
        view = first_view(rows, {'judgements': [{'id': 'j'}], 'transactions': {'b': ['j']}, 'documents': {}})
        self.assertEqual(view['currencies'], [
            {'currency': 'USD', 'count': 1, 'credit': '500', 'debit': '0'},
            {'currency': 'MXN', 'count': 3, 'credit': '30', 'debit': '75'}])
        self.assertEqual((view['total'], view['unnamed'], view['unconfirmed'], view['touched']), (4, 1, 1, 1))
        self.assertEqual([r['key'] for r in view['rows']], ['a', 'b', 'c', 'd'])

    def test_the_page_is_clamped_as_the_table_clamps_it(self):
        rows = [row(str(i)) for i in range(60)]
        view = first_view(rows, NO_CALLS, page=9, page_size=25)
        self.assertEqual((view['page'], [r['key'] for r in view['rows']][:1], len(view['rows'])), (2, ['50'], 10))
        self.assertEqual(page_index(3, 50, 0), 0)
        self.assertEqual(first_view([], NO_CALLS, page=4)['rows'], [])

    def test_an_amount_bigint_refuses_makes_the_page_read_every_row(self):
        with self.assertRaises(Unavailable):
            first_view([row('a'), row('b', amount_minor='1.25')], NO_CALLS)


if __name__ == '__main__':
    unittest.main()
