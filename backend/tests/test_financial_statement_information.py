"""Information-page classification must never clear genuine payment problems."""
from copy import deepcopy
from unittest import TestCase
from services.financial.statement_import_catalog import statement_catalog
from services.financial.statement_import_card import propose_card_table
from services.financial.statement_import_merrick import merrick_statement, propose_merrick_table
from services.financial.statement_layout_context import statement_layout_context
from tests.test_financial_statement_import_proposal import source
from tests.test_financial_statement_import_card import card_source
from tests.test_financial_statement_import_merrick import statement as merrick_source
from tests.test_financial_statement_import_andrews import source as andrews_source, selected
from tests.test_financial_pdf_geometry_candidates import rectangle

class StatementInformationTests(TestCase):
    def test_account_forms_are_information_only_when_no_payment_table_shares_the_page(self):
        for lines, kind in [
            (['Andrews Federal Credit Union', 'MEMBERSHIP APPLICATION AND SIGNATURE CARD', 'SECTION 1 - MINOR INFORMATION'], 'account_application'),
            (['Andrews Federal Credit Union', 'MEMBERSHIP APPLICATION AND SIGNATURE CARD', 'SECTION 1 - PRIMARY MEMBER INFORMATION', 'STATE ID'], 'account_application'),
            (['Andrews Federal Credit Union', 'MEMBERSHIP APPLICATION AND SIGNATURE CARD', 'SECTION 4 - BENEFICIARIES'], 'account_application'),
            (['Andrews Federal Credit Union', 'Guaranty and Indemnification Agreement', 'RECITALS'], 'account_agreement'),
            (['Andrews', 'Right to Proceed Directly Against the Guarantor', 'Waiver', 'Amendments', 'Severability'], 'account_agreement')]:
            original = source([[line] for line in lines]); before = deepcopy(original)
            self.assertEqual(statement_catalog([original])['information_sources'], [dict(page_number=1,table_index=0,kind=kind)])
            self.assertEqual(original, before)
            for row in ([['Date','Description','Amount']], [['06/02','SHOP','12.00']], [['Account Statement']], [['O6/02','Withdrawal','12.00']], [['06/02 ID 0000']]):
                mixed = source(row); mixed['table_index'] = 1
                self.assertFalse(statement_catalog([original, mixed])['information_sources'])
            original['rows'][0]['cells'][0]['expected_text'] = 'Other bank'
            self.assertFalse(statement_catalog([original])['information_sources'])

    def test_fee_summary_with_scanned_borders_keeps_all_original_cells(self):
        data = andrews_source([
            [(15, '| Total Returned Item Fees'), (210, '|'), (250, '0.00 |'), (310, '0.00 |')],
            [(15, '| --- 222 2o nnn eee --- |')],
            [(15, '| Total Overdraft Fees'), (210, '|'), (250, '0.00 |'), (310, '0.00 |')],
            [(75, 'Total Dividends Paid Year to Date'), (350, '0.22')],
            [(15, '55,901')], [(540, '000463')]], printed_page=3, names=False)
        original = deepcopy(data)
        self.assertEqual(statement_catalog([data])['information_sources'], [dict(page_number=1,table_index=0,kind='fee_summary')])
        self.assertEqual(data, original)
        for text in ('| --- Withdrawal 12.00 |', '| --- 06/02 SHOP 12.00 |', 'Unknown payment 12.00'):
            data['rows'][6]['cells'][0]['expected_text'] = text
            self.assertFalse(statement_catalog([data])['information_sources'])

    def test_dividend_summary_does_not_hide_dated_or_unrecognised_amounts(self):
        data = andrews_source([
            [(75, 'Total Dividends Paid Year to Date'), (350, '0.00')],
            [(75, 'Your current account relationship is')], [(75, 'Member')],
            [(15, '70,802')]], printed_page=7, names=False)
        original = deepcopy(data)
        result = statement_catalog([data])
        self.assertEqual(result['information_sources'], [dict(page_number=1, table_index=0, kind='fee_summary')])
        self.assertEqual(data, original)
        for cells in ([('06/02'), ('Deposit'), ('20.00')], [('Unknown charge'), ('20.00')]):
            mixed = deepcopy(data)
            extra = source([cells])['rows'][0]
            extra['row_index'] = 100
            mixed['rows'].append(extra)
            self.assertFalse(statement_catalog([mixed])['information_sources'])
        other_table = source([['06/02', 'SHOP', '20.00']]); other_table['table_index'] = 1
        mixed = statement_catalog([data, other_table])
        self.assertIn(dict(page_number=1, table_index=1), mixed['unclassified_sources'])
        self.assertFalse(mixed['complete_coverage'])

    def test_complete_notices_are_retained_as_information_not_unassigned_statements(self):
        for lines, kind in [
            (['Capital One', 'WHAT DOES CAPITAL ONE DO WITH YOUR PERSONAL INFORMATION?', 'Financial companies choose how they share your personal information.', 'To limit our sharing'], 'privacy_notice'),
            (['Capital One', 'Who is providing this notice?', 'We protect your personal information', 'computer safeguards and secured files'], 'privacy_notice'),
            (['Capital One', 'Your Billing Cycle End Date', 'Starting with your next statement', 'Your Payment Due Date will stay the same'], 'billing_notice'),
            (['capitalone.com/referfriendsnow', 'Refer a friend and earn a bonus'], 'advertisement'),
            (['How can I Avoid Paying Interest Charges?', 'How can I Close My Account?', 'Billing Rights Summary'], 'card_terms')]:
            with self.subTest(kind=kind):
                data=source([[line] for line in lines]);before=deepcopy(data)
                result=statement_catalog([data])
                self.assertEqual(result['information_sources'],[dict(page_number=1,table_index=0,kind=kind)])
                self.assertFalse(result['unclassified_sources']);self.assertFalse(result['statements'])
                self.assertEqual(data,before)
                # Same notice with a table or even a dated amount must stay open
                # for review, including when its table is a separate OCR region.
                for grid in ([['Date','Description','Amount']], [['Sep 20','SHOP','$20.00']], [['Platinum MasterCard Account Ending in 1234']]):
                    payment=source(grid);payment['table_index']=1
                    mixed=statement_catalog([data,payment])
                    self.assertFalse(mixed['information_sources'])
                    self.assertEqual(len(mixed['unclassified_sources']),2)
        unknown=source([['Privacy notice'],['Some unrelated bank','Monthly payment 30.00']])
        self.assertTrue(statement_catalog([unknown])['unclassified_sources'])

    def test_damaged_card_date_keeps_amount_description_and_problem(self):
        data=card_source();data['rows'][5]['cells'][0]['expected_text']='M?y ??'
        data['layout_context']=statement_layout_context(data['rows'])
        result=propose_card_table(data,'USD',dict(period_start='2020-05-12',period_end='2020-06-11',account_reference='****1234'))
        payment=result['rows'][5]
        self.assertFalse(payment['excluded'])
        self.assertEqual(payment['fields']['amount_minor'],'18000')
        self.assertEqual(payment['fields']['description'],'PAYMENT')
        self.assertNotIn('date',payment['fields'])
        self.assertEqual(payment['issues'],['Check the transaction date against this billing period.'])

    def test_missing_card_cell_is_not_discarded_and_side_advert_is_not_a_payment(self):
        data=card_source()
        for row in data['rows']:
            for c in row['cells']:
                c['locator']=rectangle(20+row['row_index']*25,x=20+c['column_index']*170,width=150,height=10)
        data['rows'][5]['cells']=data['rows'][5]['cells'][1:]
        data['layout_context']=statement_layout_context(data['rows'])
        proposal=propose_card_table(data,'USD',dict(period_start='2020-05-12',period_end='2020-06-11',account_reference='****1234'))
        self.assertEqual(proposal['rows'][5]['kind'],'unresolved')
        self.assertFalse(proposal['rows'][5]['excluded'])
        self.assertTrue(proposal['rows'][5]['issues'])
        # Do not pull an unrelated pair of cells beside the amount column in.
        for c in data['rows'][5]['cells']:
            c['locator']=rectangle(145,x=510,width=50,height=10)
        data['layout_context']=statement_layout_context(data['rows'])
        self.assertEqual(data['layout_context']['unresolved_rows'],[])

    def test_damaged_section_heading_needs_explicit_nearby_total_and_no_amount(self):
        for label, index in [('Feos',8),('lntere,;t Charged',10),('Inter$$! Charged',10)]:
            data=merrick_source();data['rows'][index]['cells'][0]['expected_text']=label
            result=propose_merrick_table(data,'USD',merrick_statement(data))
            self.assertTrue(result['rows'][index]['excluded'])
            self.assertEqual(result['rows'][index]['source_cells'],data['rows'][index]['cells'])
            # Even a heading-like string must be reviewed if it has an amount.
            data['rows'][index]['cells'].append(dict(column_index=1,expected_text='12.50',locator={}))
            result=propose_merrick_table(data,'USD',merrick_statement(data))
            self.assertFalse(result['rows'][index]['excluded'])
        data=merrick_source();data['rows'][8]['cells'][0]['expected_text']='Feos'
        data['rows'][9]['cells'][0]['expected_text']='Unrecognised total'
        self.assertFalse(propose_merrick_table(data,'USD',merrick_statement(data))['rows'][8]['excluded'])

    def test_fee_summary_is_not_another_payment_or_part_of_a_payment_description(self):
        data=andrews_source([
            [(15,'06/01 ID 0040 FREE CHECKING Previous Balance'),(350,'100.00')],
            [(15,'Total Returned Item Fees'),(310,'10.00'),(350,'50.00')],
            [(15,'06/03'),(75,'Withdrawal Fee'),(310,'-10.00'),(350,'90.00')],
            [(15,'Total Overdraft Fees'),(310,'0. 00'),(350,'0.00')],
            [(15,'06/30'),(75,'Ending Balance'),(350,'90.00')]])
        _,proposal=selected([data])
        payments=[r for r in proposal['rows'] if not r['excluded']]
        self.assertEqual(len(payments),1)
        self.assertEqual(payments[0]['fields']['description'],'Withdrawal Fee')
        self.assertEqual(payments[0]['fields']['amount_minor'],'1000')
        self.assertEqual(payments[0]['issues'],[])
        summaries=[r for r in proposal['rows'] if r['source_cells'][0]['expected_text'].startswith('Total ')]
        self.assertEqual(len(summaries),2)
        self.assertTrue(all(r['excluded'] and not r['issues'] for r in summaries))

    def test_damaged_closing_date_does_not_turn_balance_and_following_summary_into_payments(self):
        first=andrews_source([
            [(15,'06/01 ID 0040 FREE CHECKING Previous Balance'),(350,'100.00')],
            [(15,'06/03'),(75,'Withdrawal Fee'),(310,'-10.00'),(350,'90.00')],
            [(15,'O6/30'),(75,'Ending Balance'),(350,'90.00')],
            [(75,'Continued on following page')]])
        summary=andrews_source([
            [(15,'Total Returned Item Fees'),(310,'10.00'),(350,'50.00')],
            [(15,'Total Overdraft Fees'),(310,'0.00'),(350,'0.00')],
            [(75,'Total Dividends Paid Year to Date'),(350,'0.00')]],page=2,printed_page=2,names=False)
        catalog=statement_catalog([first,summary])
        self.assertEqual(catalog['information_sources'],[dict(page_number=2,table_index=0,kind='fee_summary')])
        _,proposal=selected([first,summary])
        self.assertEqual(sum(not r['excluded'] for r in proposal['rows']),1)
        closing=next(r for r in proposal['rows'] if r['fields'].get('description')=='Closing Balance')
        self.assertEqual(closing['fields']['balance'],'9000')
        self.assertEqual(closing['fields']['date'],'')
        self.assertEqual(closing['source_cells'][0]['expected_text'],'O6/30')
        self.assertEqual(closing['issues'],[])
        self.assertFalse(any(r.get('continuation_sources') for r in proposal['rows']))
        # An unknown amount-bearing row prevents classifying the whole page.
        summary['rows'].append(dict(row_index=99,cells=[dict(column_index=0,expected_text='Unclear transaction 100.00',locator={})]))
        self.assertFalse(statement_catalog([first,summary])['information_sources'])

    def test_merrick_supporting_pages_keep_sources_and_never_absorb_a_payment_table(self):
        examples=[
            (['Merrick Bank', 'In response to the request received', 'Copies of the monthly billing statements', 'Copies of the payments made on the account'], 'records_cover_letter'),
            (['Merrick Bank', 'Original Application Information', 'Applicant', 'Auth User'], 'account_application'),
            (['App Info', 'App Received Date', 'Solicitation Number', 'Applicant Signature?', 'Original App Employment'], 'account_application'),
            (['merrickbank.com', 'Cardholder News', 'Cardholder Center', 'Enroll'], 'cardholder_notice'),
            (['Merrick Bank', 'Interest Charge Calculation', 'Your Annual Percentage Rate (APR)', 'Type of Balance', 'Purchases', 'Cash Advances'], 'interest_calculation'),
            (['Merrick Bank', "State's Attorney's Subpoena", 'obtaining documents', 'Certification from Custodian of Records'], 'records_request'),
            (['Any surveillance video and pictures of access', 'All account reviews from', 'Correspondences to or from the account holder', 'not just received'], 'records_request'),
            (['Certificate of Service', 'State’s Attorney’s Subpoena', 'postage prepaid', 'Financial Institutions'], 'records_request_service'),
            (['Merrick Bank', 'Certification of Custodian of Records', 'or other qualified individual', 'true and correct copies'], 'records_certification'),
        ]
        for lines,kind in examples:
            with self.subTest(kind=kind):
                data=source([[line] for line in lines]);before=deepcopy(data)
                catalog=statement_catalog([data])
                self.assertEqual(catalog['information_sources'],[dict(page_number=1,table_index=0,kind=kind)])
                self.assertFalse(catalog['unclassified_sources'])
                self.assertEqual(data,before)
                for grid in ([['Payment History']], [['Trans Date','Item Description','Amount']],
                             [['09/20/2024','EXAMPLE SHOP','14.00']], [['Sep 20','EXAMPLE SHOP','$14.00']],
                             [['Summary of Account Activity']], [['Previous Balance','100.00']]):
                    payments=source(grid);payments['table_index']=1
                    mixed=statement_catalog([data,payments])
                    self.assertFalse(mixed['information_sources'])
                    self.assertEqual(len(mixed['unclassified_sources']),2)
                # Remove a required phrase. Unfamiliar or incomplete notices
                # cannot be marked as understood based on the title alone.
                data['rows'].pop()
                self.assertFalse(statement_catalog([data])['information_sources'])

    def test_merrick_payment_history_remains_financial_review_even_without_a_statement_heading(self):
        data=source([['Payment History'],['Date','From Account','Amount','Fee','Status'],
            ['10/02/2024','EXAMPLE CREDIT UNION /123456789','500.00','0.00','Posted']])
        catalog=statement_catalog([data])
        self.assertEqual(catalog['unclassified_sources'],[dict(page_number=1,table_index=0)])
        self.assertFalse(catalog['information_sources'])
        self.assertFalse(catalog['statements'])
