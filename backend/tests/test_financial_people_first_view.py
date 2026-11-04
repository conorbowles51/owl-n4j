"""The People & businesses list on the server: the browser's own grouping of the same payments and directory.

``frontend_v2/src/features/financial/lib/people-parity.fixture.json`` holds payments and an account directory made to
reach every rule of paymentProfiles and its card, and the server's answers for several choices of currency and
category; the browser test people-first-view.test.ts checks the browser's grouping gives the same cards. This test
checks the server still gives them, and pins the behaviours that differ between Python and the browser unless
written out. The equality over the six live cases is a gate run outside the suite (d5b330d1: 8 choices, 2,185
profiles, every figure equal)."""
import json
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from services.financial.people_first_view import owns_payment, people_view
from services.financial.trends_first_view import Unavailable

FIXTURE = Path(__file__).resolve().parents[2] / 'frontend_v2/src/features/financial/lib/people-parity.fixture.json'


class PeopleParityFixtureTests(unittest.TestCase):
    def test_the_server_gives_the_answers_the_browser_test_checks(self):
        fixture = json.loads(FIXTURE.read_text())
        self.assertEqual(len(fixture['scenarios']), 7)
        for scenario in fixture['scenarios']:
            ask = dict(scenario['ask'])
            categories = ask.pop('categories', [])
            with self.subTest(ask=scenario['ask']):
                self.assertEqual(people_view(fixture['rows'], fixture['case_id'], fixture['directory']['accounts'],
                                             categories, **ask), scenario['server'])


def row(key, **fields):
    base = {'key': key, 'case_id': 'c', 'account_id': 'a', 'currency': 'USD', 'direction': 'debit',
            'amount_minor': '100', 'ordering_date': '2021-02-02', 'to_name': 'Shop', 'source_document_id': 'd'}
    base.update(fields)
    return base


def holder(party, start=None, end=None):
    return {'id': 'r-%s-%s' % (party, start), 'role': 'holder', 'party': {'id': party, 'name': party},
            'effective_from': start, 'effective_to': end}


class BrowserBehaviourTests(unittest.TestCase):
    def test_a_holder_owns_payments_only_within_the_relationship_dates(self):
        inside = row('a', ordering_date='2021-01-15', account_relationships=[holder('p', '2021-01-01', '2021-01-31')])
        outside = row('b', ordering_date='2021-02-15', account_relationships=[holder('p', '2021-01-01', '2021-01-31')])
        undated = row('c', ordering_date=None, account_relationships=[holder('p', '2021-01-01', None)])
        open_link = row('d', ordering_date=None, account_relationships=[holder('p')])
        self.assertEqual([owns_payment(r, 'p') for r in (inside, outside, undated, open_link)],
                         [True, False, False, True])
        # No relationship records: the holder parties decide; records for others: not this party's.
        self.assertTrue(owns_payment(row('e', account_holder_parties=[{'id': 'p', 'name': 'P'}]), 'p'))
        self.assertFalse(owns_payment(row('f', account_relationships=[holder('q')],
                                          account_holder_parties=[{'id': 'p', 'name': 'P'}]), 'p'))

    def test_an_owner_profile_counts_only_its_payments_but_lists_the_account(self):
        rows = [row('in', ordering_date='2021-01-15', account_relationships=[holder('p', '2021-01-01', '2021-01-31')],
                    account_holder_parties=[{'id': 'p', 'name': 'Pat'}]),
                row('out', ordering_date='2021-03-01', account_relationships=[holder('p', '2021-01-01', '2021-01-31')],
                    account_holder_parties=[{'id': 'p', 'name': 'Pat'}])]
        owner = {p['id']: p for p in people_view(rows, 'c', [], [])['profiles']}['owner:p']
        self.assertEqual((owner['payments'], owner['accounts'], owner['first'], owner['last']),
                         (1, 1, '2021-01-15', '2021-01-15'))

    def test_a_blank_name_is_one_unidentified_profile_and_spaces_are_kept_in_the_key(self):
        rows = [row('a', to_name='  '), row('b', to_name=None), row('c', to_name=' Shop ')]
        profiles = {p['id']: p for p in people_view(rows, 'c', [], [])['profiles']}
        self.assertTrue(profiles['name:  ']['unidentified'])
        self.assertTrue(profiles['name:']['unidentified'])
        self.assertEqual(profiles['name: Shop ']['name'], ' Shop ')
        self.assertEqual(profiles['name:']['name'], 'Name not recorded')

    def test_rows_the_port_does_not_reproduce_are_left_to_the_browser(self):
        with self.assertRaises(Unavailable):
            people_view([row('a', ordering_date='0000-01-01')], 'c', [], [])
        with self.assertRaises(Unavailable):
            people_view([row('a', to_name=7)], 'c', [], [])

    def test_an_incomplete_answer_is_not_described(self):
        self.assertEqual(people_view([row('a'), row('a')], 'c', [], []), {'complete': False})
        self.assertEqual(people_view([row('a', case_id='other')], 'c', [], []), {'complete': False})


class RouteTests(unittest.TestCase):
    def call(self, rows, directory_copy, computed=None):
        from routers import financial_ledger
        case = uuid.UUID(rows[0]['case_id']) if rows else uuid.uuid4()
        handler = financial_ledger.get_ledger_people_view.__wrapped__
        with patch.object(financial_ledger, '_overview_ledger_rows', return_value=rows), \
                patch('services.financial.view_cache.kept_copy', return_value=directory_copy), \
                patch.object(financial_ledger, 'account_parties', return_value=computed) as compute:
            answer = handler(case_id=case, source_document_id=None, account_id=None, ledger_status=None,
                             start_date=None, end_date=None, group=None, db=None, account_ids=None,
                             account_holders=None, categories=None)
        return case, answer, compute

    def test_the_route_is_a_kept_view_over_the_ledger_rows(self):
        from routers import financial_ledger
        from services.financial import view_cache
        endpoints = {route.path: route.endpoint for route in financial_ledger.router.routes
                     if 'GET' in getattr(route, 'methods', ())}
        self.assertIs(view_cache.handlers['ledger-people-view'], endpoints['/api/financial/ledger-people-view'])

    def test_the_directory_comes_from_its_kept_copy_or_is_computed(self):
        case = str(uuid.uuid4())
        directory = {'accounts': [{'id': 'acc', 'holder_as_recorded': 'Kept', 'identifier_as_printed': None,
                                   'institution': None, 'currency': 'USD', 'relationships': [], 'holder_parties': []}]}
        _, kept, compute = self.call([row('a', case_id=case)], directory)
        compute.assert_not_called()
        self.assertIn('account:acc', [p['id'] for p in kept['profiles']])
        _, computed, compute = self.call([row('a', case_id=case)], None, computed=directory)
        compute.assert_called_once()
        self.assertEqual(computed, kept)

    def test_unavailable_rows_answer_available_false(self):
        case = str(uuid.uuid4())
        _, answer, _ = self.call([row('a', case_id=case, ordering_date='0000-01-01')], {'accounts': []})
        self.assertEqual(answer, {'case_id': case, 'available': False, 'reason': 'a date in year 0000'})


if __name__ == '__main__':
    unittest.main()
