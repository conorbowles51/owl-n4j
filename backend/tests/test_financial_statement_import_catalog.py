import unittest
from services.financial.statement_import_catalog import statement_catalog
from tests.test_financial_statement_import_proposal import source


def page(number, period='May 12, 2020 - Jun. 11, 2020 | 31 days in Billing Cycle', card='3539'):
    result=source([['Platinum MasterCard Account Ending in '+card],[period],['Visit www.capitalone.com to see detailed transactions.']])
    result['page_number']=number
    return result


class StatementCatalogTests(unittest.TestCase):
    def test_groups_repeated_period_headers_but_keeps_other_periods_separate(self):
        result=statement_catalog([page(1),page(3),page(4,'Jun. 12, 2020 - Jul. 11, 2020 | 30 days in Billing Cycle')])
        self.assertEqual(len(result['statements']),2)
        self.assertEqual(result['statements'][0]['page_numbers'],[1,3])
        self.assertEqual(result['statements'][0]['account_reference'],'****3539')
        self.assertTrue(result['complete_coverage'])

    def test_unknown_pages_and_conflicting_periods_are_not_assigned_by_proximity(self):
        legal=source([['Legal terms and conditions']]);legal['page_number']=2
        conflict=page(4);conflict['rows']+=source([['Jun. 12, 2020 - Jul. 11, 2020 | 30 days in Billing Cycle']])['rows']
        result=statement_catalog([page(1),legal,conflict])
        self.assertEqual(result['statements'][0]['page_numbers'],[1])
        self.assertEqual([s['page_number'] for s in result['unclassified_sources']],[2,4])
        self.assertFalse(result['complete_coverage'])

    def test_different_printed_accounts_do_not_share_a_statement_group(self):
        result=statement_catalog([page(1),page(2,card='9999')])
        self.assertEqual(len(result['statements']),2)
        self.assertNotEqual(result['statements'][0]['id'],result['statements'][1]['id'])
