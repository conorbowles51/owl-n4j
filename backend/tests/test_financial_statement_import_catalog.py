import unittest
from services.financial.statement_import_catalog import statement_catalog
from tests.test_financial_statement_import_proposal import source


def page(number, period='May 12, 2020 - Jun. 11, 2020 | 31 days in Billing Cycle', card='3539'):
    result=source([['Platinum MasterCard Account Ending in '+card],[period],['Visit www.capitalone.com to see detailed transactions.']])
    result['page_number']=number
    return result


class StatementCatalogTests(unittest.TestCase):
    def test_summary_and_terms_use_context_on_the_same_page(self):
        header=page(1);header['table_index']=2
        summary=source([['Account Summary'],['Previous Balance','$100.00'],['New Balance','$200.00']])
        result=statement_catalog([summary,header])
        self.assertEqual(len(result['statements']),1)
        self.assertEqual([s['table_index'] for s in result['statements'][0]['sources']],[0,2])
        # A second printed account on that page invalidates page-wide context.
        conflicting=page(1,card='9999');conflicting['table_index']=3
        self.assertEqual(statement_catalog([summary,header,conflicting])['statements'],[])

    def test_continuation_needs_an_exact_established_account_and_period(self):
        continuation=page(2);continuation['rows']=continuation['rows'][:2]
        self.assertEqual(statement_catalog([continuation])['statements'],[])
        self.assertEqual(statement_catalog([page(1),continuation])['statements'][0]['page_numbers'],[1,2])
        continuation['rows'][0]['cells'][0]['expected_text']='Platinum MasterCard Account Ending in 9999'
        result=statement_catalog([page(1),continuation])
        self.assertEqual(result['statements'][0]['page_numbers'],[1])
        self.assertEqual(result['unclassified_sources'],[dict(page_number=2,table_index=0)])

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

    def test_secured_card_product_names_retain_account_and_period_grouping(self):
        sources = [page(1), page(2), page(3, card='9999')]
        sources[1]['rows'][0]['cells'][0]['expected_text'] = 'Secured Card | Platinum Mastercard ending in 3539'
        sources[2]['rows'][0]['cells'][0]['expected_text'] = 'Platinum Secured Card | Platinum Mastercard ending in 9999'
        result = statement_catalog(sources)
        self.assertEqual(len(result['statements']), 2)
        self.assertEqual(result['statements'][0]['page_numbers'], [1, 2])
        self.assertEqual(result['statements'][1]['account_reference'], '****9999')
        self.assertTrue(result['complete_coverage'])

    def test_near_matching_secured_headings_and_conflicting_accounts_remain_unclassified(self):
        for heading in ('Secured Card | Platinum Mastercard ending in 35O9',
                        'Some Card | Platinum Mastercard ending in 3539',
                        'Platinum Secured Card | Platinum Mastercard ending in 3539 text'):
            value = page(1)
            value['rows'][0]['cells'][0]['expected_text'] = heading
            self.assertEqual(statement_catalog([value])['statements'], [])
        value = page(1)
        value['rows'] += source([['Secured Card | Platinum Mastercard ending in 9999']])['rows']
        self.assertEqual(statement_catalog([value])['statements'], [])
