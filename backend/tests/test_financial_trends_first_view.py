"""The Trends page's figures on the server: the browser's own calculation over the same ledger rows.

``frontend_v2/src/features/financial/lib/trends-parity.fixture.json`` holds payments made to reach every Trends rule
and the server's answers for several choices of group and periods; the browser test trends-view.test.ts checks the
browser's functions give the same figures from those answers. This test checks the server still gives them, and
pins the behaviours that differ between Python and the browser unless written out. The equality over the six live
cases is a gate run outside the suite (d5b330d1: 34 choices, every figure equal)."""
import json
import unittest
from pathlib import Path

from services.financial.trends_first_view import Unavailable, party, trends_view

FIXTURE = Path(__file__).resolve().parents[2] / 'frontend_v2/src/features/financial/lib/trends-parity.fixture.json'


class TrendsParityFixtureTests(unittest.TestCase):
    def test_the_server_gives_the_answers_the_browser_test_checks(self):
        fixture = json.loads(FIXTURE.read_text())
        self.assertEqual(len(fixture['scenarios']), 7)
        for scenario in fixture['scenarios']:
            ask = dict(scenario['ask'])
            categories = ask.pop('categories', [])
            with self.subTest(ask=scenario['ask']):
                self.assertEqual(trends_view(fixture['rows'], fixture['case_id'], categories, **ask),
                                 scenario['server'])


def row(key, **fields):
    base = {'key': key, 'case_id': 'c', 'account_id': 'a', 'currency': 'USD', 'direction': 'debit',
            'amount_minor': '100', 'ordering_date': '2021-02-02', 'to_name': 'Shop'}
    base.update(fields)
    return base


class BrowserBehaviourTests(unittest.TestCase):
    def test_party_names_collapse_javascript_spaces_and_encode_like_encodeuricomponent(self):
        self.assertEqual(party(row('a', to_name='  Señor  Uno '), 'to')['key'], 'name:Señor Uno')
        linked = party(row('b', to_name='A&B', counterparty_link={'kind': 'party', 'id': 'p'}), 'to')
        self.assertEqual(linked['key'], 'identity:party:p:A%26B')
        unnamed = party(row('c', to_name=None, label_sources={'to_name': {'reason': "Torn (page 2)!"}}), 'to')
        self.assertEqual((unnamed['key'], unnamed['name']), ("unknown:to:Torn%20(page%202)!", "Torn (page 2)!"))
        # An empty printed name is not missing: `??` keeps it, so the raw text is not used.
        self.assertEqual(party(row('d', to_name='', counterparty_raw='Raw'), 'to')['key'], 'unknown:to')

    def test_a_returned_transfer_is_matched_case_blind_and_by_bank_reference(self):
        rows = [row('h%d' % i, ordering_date='2021-01-%02d' % (i + 1)) for i in range(3)] + [
            row('out', ordering_date='2021-02-03', amount_minor='777', bank_reference=' R-1 '),
            row('back', ordering_date='2021-02-05', amount_minor='777', direction='credit', from_name='Bank',
                bank_reference='R-1', description='spei Devuelto')]
        view = trends_view(rows, 'c', [], earlier={'start': '2021-01-01', 'end': '2021-01-31'},
                           later={'start': '2021-02-01', 'end': '2021-02-28'})
        returns = [o for o in view['result']['observations'] if o['kind'] == 'return']
        self.assertEqual([(o['rows'], o['title']) for o in returns], [(['out', 'back'], 'Returned transfer · reference R-1')])

    def test_rows_the_port_does_not_reproduce_are_left_to_the_browser(self):
        with self.assertRaises(Unavailable):
            trends_view([row('a', ordering_date='0000-01-01')], 'c', [])
        with self.assertRaises(Unavailable):
            trends_view([row('a', to_name=7)], 'c', [])

    def test_an_incomplete_answer_is_not_described(self):
        self.assertEqual(trends_view([row('a'), row('a')], 'c', []), {'complete': False})
        self.assertEqual(trends_view([row('a', case_id='other')], 'c', []), {'complete': False})

    def test_the_most_frequent_group_is_chosen_and_a_named_one_is_kept(self):
        rows = [row('a'), row('b'), row('c', currency='MXN')]
        self.assertEqual(trends_view(rows, 'c', [])['group'], 'USD:bank')
        self.assertEqual(trends_view(rows, 'c', [], group='MXN:bank')['group'], 'MXN:bank')
        self.assertEqual(trends_view(rows, 'c', [], group='EUR:bank')['group'], 'USD:bank')


class RouteTests(unittest.TestCase):
    def test_the_route_is_a_kept_view_over_the_ledger_rows(self):
        from routers import financial_ledger
        from services.financial import view_cache
        endpoints = {route.path: route.endpoint for route in financial_ledger.router.routes
                     if 'GET' in getattr(route, 'methods', ())}
        route = endpoints['/api/financial/ledger-trends-view']
        self.assertIs(view_cache.handlers['ledger-trends-view'], route)

    def test_unavailable_rows_answer_available_false(self):
        import uuid
        from unittest.mock import patch
        from routers import financial_ledger
        case = uuid.uuid4()
        bad = [dict(row('a', ordering_date='0000-01-01'), case_id=str(case))]
        handler = financial_ledger.get_ledger_trends_view.__wrapped__
        with patch.object(financial_ledger, '_overview_ledger_rows', return_value=bad):
            answer = handler(case_id=case, source_document_id=None, account_id=None, ledger_status=None,
                             start_date=None, end_date=None, group=None, earlier_start=None, earlier_end=None,
                             later_start=None, later_end=None, db=None, account_ids=None, account_holders=None,
                             categories=None)
        self.assertEqual(answer, {'case_id': str(case), 'available': False, 'reason': 'a date in year 0000'})


if __name__ == '__main__':
    unittest.main()
