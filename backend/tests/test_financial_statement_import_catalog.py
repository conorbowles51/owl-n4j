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

    def test_world_elite_to_quicksilver_product_change_keeps_every_printed_period(self):
        from services.financial.statement_import_card import propose_card_table
        from services.financial.statement_layout_context import statement_layout_context
        old = page(1, 'Mar. 24, 2021 - Apr. 22, 2021 | 30 days in Billing Cycle', '9392')
        old['rows'][0]['cells'][0]['expected_text'] = 'World Elite Mastercard Account Ending in 9392'
        new = page(4, 'Apr 23, 2021 - May 23, 2021 | 31 days in Billing Cycle', '9392')
        new['rows'][0]['cells'][0]['expected_text'] = 'Quicksilver Credit Card | World Elite Mastercard ending in 9392'
        extra = source([['EXAMPLE PERSON #9392: Transactions'], ['Trans Date', 'Post Date', 'Description', 'Amount'],
            ['May 2', 'May 3', 'EXAMPLE SHOP', '$12.34']])['rows']
        new['rows'] += [{**row, 'row_index': row['row_index'] + 3} for row in extra]
        new['layout_context'] = statement_layout_context(new['rows'])
        choices = statement_catalog([old, new])
        self.assertEqual(len(choices['statements']), 2)
        self.assertTrue(choices['complete_coverage'])
        choice = choices['statements'][1]
        self.assertEqual(choice['period_start'], '2021-04-23')
        self.assertEqual(choice['account_reference'], '****9392')
        rows = [row for row in propose_card_table(new, 'USD', choice)['rows'] if not row['excluded']]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['fields']['amount_minor'], '1234')
        self.assertEqual(rows[0]['fields']['date'], '2021-05-02')
        new['rows'][0]['cells'][0]['expected_text'] += ' unverified text'
        self.assertEqual(statement_catalog([new])['statements'], [])

    def test_world_elite_collection_separates_periods_and_keeps_summary_and_terms_out_of_payments(self):
        from services.financial.statement_import_card import propose_card_table
        from services.financial.statement_layout_context import statement_layout_context
        header = page(1, 'Nov. 30, 2020 - Dec. 23, 2020 | 24 days in Billing Cycle', '9392')
        header['rows'][0]['cells'][0]['expected_text'] = 'World Elite Mastercard Account Ending in 9392'
        summary = source([['Payment Information'], ['Minimum Payment', '22 Months', '$547']])
        summary['page_number'] = 1; summary['table_index'] = 1
        terms = source([['How can I Avoid Paying Interest Charges?'], ['How can I Close My Account?'], ['Billing Rights Summary']])
        terms['page_number'] = 2
        transactions = page(3, 'Nov. 30, 2020 - Dec. 23, 2020 | 24 days in Billing Cycle', '9392')
        transactions['rows'][0]['cells'][0]['expected_text'] = 'World Elite Mastercard Account Ending in 9392'
        more = source([['EXAMPLE PERSON #9392: Transactions'], ['Date','Description','Amount'], ['Dec 4','EXAMPLE SHOP','$63.31'], ['Total Transactions for This Period','$63.31']])['rows']
        transactions['rows'] += [{**r, 'row_index': r['row_index']+3} for r in more]
        transactions['layout_context'] = statement_layout_context(transactions['rows'])
        following = page(5, 'Dec. 24, 2020 - Jan. 23, 2021 | 31 days in Billing Cycle', '9392')
        following['rows'][0]['cells'][0]['expected_text'] = 'World Elite Mastercard Account Ending in 9392'
        result = statement_catalog([header, summary, terms, transactions, following])
        self.assertEqual(len(result['statements']), 2)
        first = result['statements'][0]
        self.assertEqual(first['page_numbers'], [1,3])
        self.assertEqual(first['account_reference'], '****9392')
        self.assertEqual(len(result['information_sources']), 1)
        self.assertTrue(all(r['excluded'] for r in propose_card_table(summary, 'USD', first)['rows']))
        payments = [r for r in propose_card_table(transactions, 'USD', first)['rows'] if not r['excluded']]
        self.assertEqual(len(payments), 1)
        self.assertEqual(payments[0]['fields']['date'], '2020-12-04')
        self.assertEqual(payments[0]['fields']['amount_minor'], '6331')
        self.assertEqual(payments[0]['fields']['direction'], 'debit')

    def test_continued_transactions_need_the_matching_printed_total_account_and_cycle(self):
        from copy import deepcopy
        from services.financial.statement_import_card import propose_card_table
        main = page(1, 'Nov 23, 2023 - Dec 23, 2023 | 31 days in Billing Cycle', '9392')
        continuation = page(2, 'Nov 23, 2023 - Dec 23, 2023 | 31 days in Billing Cycle', '9392')
        continuation['rows'] = continuation['rows'][:2]
        extra = source([['Transactions (Continued)'], ['Trans Date', 'Post Date', 'Description', 'Amount'],
            ['Dec 13', 'Dec 14', 'EXAMPLE SHOP', '$11.65'], ['EXAMPLE PERSON #9392: Total Transactions', '$11.65']])['rows']
        continuation['rows'] += [{**row, 'row_index': row['row_index'] + 2} for row in extra]
        choice = statement_catalog([main, continuation])['statements'][0]
        payments = [row for row in propose_card_table(continuation, 'USD', choice)['rows'] if not row['excluded']]
        self.assertEqual(len(payments), 1)
        self.assertEqual(payments[0]['fields']['amount_minor'], '1165')
        self.assertEqual(payments[0]['fields']['date'], '2023-12-13')
        self.assertEqual(payments[0]['fields']['booking_date'], '2023-12-14')
        self.assertEqual(payments[0]['layout_context']['section_source']['expected_text'], 'EXAMPLE PERSON #9392: Total Transactions')
        for changed in ('account', 'period', 'missing_total'):
            with self.subTest(changed=changed):
                bad = deepcopy(continuation)
                if changed == 'account': bad['rows'][-1]['cells'][0]['expected_text'] = 'EXAMPLE PERSON #9999: Total Transactions'
                elif changed == 'period': bad['rows'][1]['cells'][0]['expected_text'] = 'Oct 24, 2023 - Nov 22, 2023 | 30 days in Billing Cycle'
                else: bad['rows'].pop()
                unknown = [row for row in propose_card_table(bad, 'USD', choice)['rows'] if not row['excluded']]
                self.assertTrue(unknown[0]['issues'])
                self.assertNotIn('amount_minor', unknown[0]['fields'])
