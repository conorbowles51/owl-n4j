"""Synthetic Andrews-style sections; no private statement contents."""
import unittest
from copy import deepcopy

from services.financial.statement_import_catalog import statement_catalog
from services.financial.statement_import_andrews import andrews_page, propose_andrews_statement
from tests.test_financial_pdf_geometry_candidates import rectangle


def source(lines, *, page=1, printed_page=1, account='123456789', period='06/01/20 06/30/20', names=True):
    # Tuples explicitly specify the measured x coordinate and printed text.
    header = [[(420, 'Account Statement')], [(40, 'Andrews')], [(300, account)],
              [(300, period)], [(300, str(printed_page))]]
    if names:
        header += [[(20, '>1234567890<')], [(20, 'EXAMPLE PERSON')], [(20, 'JOINT PERSON')], [(20, '1 TEST STREET')]]
    result = dict(page_number=page, table_index=0, source_revision='a'*64, rows=[])
    for i, values in enumerate(header + lines):
        cells = []
        for j, (x, text) in enumerate(values):
            # Header remains within the top fifth; body begins below it.
            y = 20+i*12 if i < len(header) else 220+(i-len(header))*12
            locator = rectangle(y, x=x, width=min(575-x, max(10, len(text)*3)), height=8)
            locator['page'] = page
            cells.append(dict(column_index=j, expected_text=text, locator=locator))
        result['rows'].append(dict(row_index=i, cells=cells))
    return result


def two_shares():
    return source([
        [(15, '06/01 ID 0000 BASE SHARE SAVINGS Previous Balance'), (350, '100.00')],
        [(15, '06/03'), (75, 'Deposit Online Banking Transfer From Share 0040'), (310, '20.00 120.00')],
        [(75, 'Funds Transfer via Mobile')],
        [(15, '06/30'), (75, 'Ending Balance'), (350, '120.00')],
        [(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '200.00')],
        [(15, '06/03'), (75, 'Withdrawal Online Banking Transfer To Share 0000'), (310, '-20.00'), (350, '180.00')],
        [(75, 'Funds Transfer via Mobile')],
        [(15, '06/30'), (75, 'Ending Balance'), (350, '180.00')],
    ])


def selected(sources, share='0040'):
    st = next(s for s in statement_catalog(sources)['statements'] if s['share_reference'] == share)
    keys = {(s['page_number'], s['table_index']) for s in st['sources']}
    return st, propose_andrews_statement([s for s in sources if (s['page_number'], s['table_index']) in keys], 'USD', st)


class AndrewsReaderTests(unittest.TestCase):
    def test_spaces_inside_printed_payment_verbs_retain_source_and_sign_checks(self):
        for description, amount, balance, direction in (
                ('Wi thdrawal Debit Card', '-12.50', '87.50', 'debit'),
                ('Re curring Wi thdrawal Debit Card', '-12.50', '87.50', 'debit'),
                ('De posit Transfer', '12.50', '112.50', 'credit'),
                ('Wi thdrawal Debit Card', '12.50', '112.50', None),
                ('Re curring De posit Transfer', '-12.50', '87.50', None),
                ('Withd rawal Adjustment', '12.50', '112.50', 'credit'),
                ('Withdra walx Debit Card', '-12.50', '87.50', None),
                ('Withdra\u03c9al Debit Card', '-12.50', '87.50', None)):
            with self.subTest(description=description, amount=amount):
                original = source([
                    [(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '100.00')],
                    [(15, '06/03'), (75, description), (310, amount), (350, balance)],
                    [(15, '06/30'), (75, 'Ending Balance'), (350, balance)],
                ])
                before = deepcopy(original)
                _, proposal = selected([original])
                payment = next(row for row in proposal['rows'] if not row['excluded'])
                self.assertEqual(payment['fields']['description'], description)
                self.assertEqual(payment['fields'].get('direction'), direction)
                self.assertEqual(bool(payment['issues']), direction is None)
                self.assertEqual(original, before)

    def test_spaces_inside_separate_money_cells_preserve_digits_and_original_text(self):
        original = source([
            [(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '1 00. 0 0')],
            [(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '-1 2. 50'), (350, '8 7. 5 0')],
            [(15, '06/30'), (75, 'Ending Balance'), (350, '8 7. 5 0')],
        ])
        before=deepcopy(original)
        _, proposal=selected([original])
        payment=next(row for row in proposal['rows'] if row['kind']=='transaction')
        self.assertEqual(payment['fields']['amount_minor'],'1250')
        self.assertEqual(payment['fields']['balance'],'8750')
        self.assertEqual(payment['fields']['balance_difference_minor'],'0')
        self.assertEqual(payment['issues'],[])
        self.assertEqual(original,before)
        self.assertEqual(payment['source_cells'][-1]['expected_text'],'8 7. 5 0')

    def test_spacing_does_not_repair_damaged_digits_decimal_marks_or_joined_numbers(self):
        from services.financial.statement_import_andrews import _amount
        for text in ('8O.00','8:00','8-00','8.0','8.000','8 0.0O','80.00 90.00'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                _amount(text,'USD',separate_cell=True)
        with self.assertRaises(ValueError):_amount('8 0.00','USD')
        original=source([
            [(15,'06/01 ID 0040 FREE CHECKING Previous Balance'),(350,'100.00')],
            [(15,'06/03'),(75,'Withdrawal Debit Card'),(310,'-1 2.50 87.50')],
        ])
        _,proposal=selected([original])
        payment=next(row for row in proposal['rows'] if row['kind']=='transaction')
        self.assertNotIn('amount_minor',payment['fields'])
        self.assertTrue(payment['issues'])

    def test_savings_and_checking_stay_separate_with_original_cells(self):
        original = two_shares(); before = deepcopy(original)
        catalog = statement_catalog([original])
        self.assertEqual(len(catalog['statements']), 2)
        a, savings = selected([original], '0000')
        b, checking = selected([original])
        self.assertNotEqual(a['id'], b['id'])
        self.assertNotEqual(a['account_reference'], b['account_reference'])
        self.assertEqual(a['holder'], 'EXAMPLE PERSON / JOINT PERSON')
        for proposal, direction, balance in ((savings, 'credit', '12000'), (checking, 'debit', '18000')):
            rows = [r for r in proposal['rows'] if not r['excluded']]
            self.assertEqual(len(rows), 1)
            fields = rows[0]['fields']
            self.assertEqual((fields['date'], fields['amount_minor'], fields['direction'], fields['balance']),
                             ('2020-06-03', '2000', direction, balance))
            self.assertEqual(fields['balance_difference_minor'], '0')
            self.assertTrue(fields['description'].endswith('Funds Transfer via Mobile'))
            self.assertEqual(rows[0]['issues'], [])
            self.assertEqual(proposal['issues'], [])
        self.assertEqual(original, before)
        self.assertEqual(next(r for r in savings['rows'] if not r['excluded'])['source_cells'][2]['expected_text'], '20.00 120.00')

    def test_continuation_uses_same_account_period_and_retains_cross_page_description(self):
        a = source([
            [(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '100.00')],
            [(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '-20.00 80.00')],
            [(15, '--- Continued on following page ---')], [(15, '999999 footer')]])
        b = source([[(75, 'EXAMPLE SHOP TEST CITY')],
                    [(15, '06/04'), (75, 'Withdrawal Debit Card'), (310, '-10.00 70.00')],
                    [(15, '06/30'), (75, 'Ending Balance'), (350, '70.00')]], page=2, printed_page=2, names=False)
        st, p = selected([a, b])
        self.assertEqual(st['page_numbers'], [1, 2])
        rows = [r for r in p['rows'] if not r['excluded']]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['fields']['description'], 'Withdrawal Debit Card\nEXAMPLE SHOP TEST CITY')
        self.assertEqual(rows[0]['continuation_sources'][0]['page_number'], 2)
        self.assertEqual(rows[1]['fields']['balance_difference_minor'], '0')
        self.assertNotIn('footer', str(p))
        for change in ('account', 'period', 'page', 'printed_page'):
            values = dict(page=2, printed_page=2, names=False)
            values[change] = {'account':'987654321', 'period':'07/01/20 07/31/20', 'page':3, 'printed_page':4}[change]
            wrong = source([[(15, '06/30'), (75, 'Ending Balance'), (350, '70.00')]], **values)
            st, p = selected([a, wrong])
            self.assertEqual(st['page_numbers'], [1])
            self.assertTrue(p['issues'])

    def test_repeated_account_and_period_stays_a_separate_statement_occurrence(self):
        a = two_shares(); b = deepcopy(a); b['page_number'] = 3
        for r in b['rows']:
            for c in r['cells']: c['locator']['page'] = 3
        result = statement_catalog([a,b])['statements']
        self.assertEqual(len(result), 4)
        self.assertTrue(all(len(s['page_numbers']) == 1 for s in result))
        self.assertEqual(len({s['id'] for s in result}), 4)

    def test_invalid_heading_account_and_period_are_not_repaired(self):
        for changes in ({'account':'12345O789'}, {'period':'06/01/20 06/31/20'}):
            self.assertIsNone(andrews_page(source([], **changes)))
        a = two_shares(); a['rows'][0]['cells'][0]['expected_text'] = 'Membership Application'
        self.assertIsNone(andrews_page(a))
        a = two_shares(); a['rows'][0]['cells'][0]['locator']['rect'] = [0, 0, 0, 0]
        self.assertIsNone(andrews_page(a))

    def test_unrecognised_share_does_not_inherit_previous_account(self):
        a = source([
            [(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '100.00')],
            [(15, '06/03'), (75, 'Deposit ACH Example'), (310, '20.00 120.00')],
            [(15, '06/01 ID OOOO BASE SHARE SAVINGS Previous Balance'), (350, '50.00')],
            [(15, '06/03'), (75, 'Deposit ACH Other'), (310, '30.00 80.00')]])
        _, p = selected([a])
        self.assertEqual(len([r for r in p['rows'] if not r['excluded']]), 1)
        self.assertTrue(statement_catalog([a])['unclassified_sources'])

    def test_damaged_dates_amounts_and_balances_are_independent_exceptions(self):
        for date_text, money, expected in (
            ('O6/03', '-20.00 80.00', {'amount_minor':'2000', 'balance':'8000'}),
            ('06/03', '-2O.00 80.00', {'date':'2020-06-03', 'balance':'8000'}),
            ('06/03', '-20.00 8O.00', {'date':'2020-06-03', 'amount_minor':'2000'}),
            ('07/03', '-20.00 80.00', {'amount_minor':'2000', 'balance':'8000'})):
            a = source([[(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '100.00')],
                        [(15, date_text), (75, 'Withdrawal Debit Card'), (310, money)]])
            _, p = selected([a]); r = next(r for r in p['rows'] if not r['excluded'])
            self.assertTrue(r['issues'])
            for key,value in expected.items(): self.assertEqual(r['fields'][key], value)
            self.assertEqual(r['source_cells'][-1]['expected_text'], money)
            if date_text != '06/03': self.assertNotIn('date', r['fields'])

    def test_missing_minus_and_two_unlabelled_dates_are_flagged(self):
        a = source([[(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '100.00')],
                    [(15, '06/03 06/02 Withdrawal Debit Card'), (310, '20.00 80.00')]])
        _, p = selected([a]); r = next(r for r in p['rows'] if not r['excluded'])
        self.assertNotIn('direction', r['fields'])
        self.assertEqual(r['fields']['additional_printed_date'], '06/02')
        self.assertEqual(len(r['issues']), 2)

    def test_refund_is_credit_and_balance_mismatch_is_reported(self):
        a = source([[(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '100.00')],
                    [(15, '06/03'), (75, 'Withdrawal Adjustment Debit Card Credit Voucher'), (310, '20.00 121.00')]])
        _, p = selected([a]); r = next(r for r in p['rows'] if not r['excluded'])
        self.assertEqual(r['fields']['direction'], 'credit')
        self.assertEqual(r['fields']['balance_difference_minor'], '100')
        self.assertTrue(r['issues'])

    def test_missing_logo_only_continues_an_identified_adjacent_statement(self):
        first = source([
            [(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '100.00')],
            [(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '-20.00 80.00')],
            [(15, '--- Continued on following page ---')]])
        second = source([
            [(75, 'EXAMPLE SHOP')],
            [(15, '06/04'), (75, 'Withdrawal Debit Card'), (310, '-10.00 70.00')],
            [(15, '06/30'), (75, 'Ending Balance'), (350, '70.00')]],
            page=2, printed_page=2, names=False)
        second['rows'] = [r for r in second['rows'] if r['row_index'] != 1]
        self.assertIsNone(andrews_page(second))
        statement, proposal = selected([first, second])
        self.assertEqual(statement['page_numbers'], [1, 2])
        rows = [r for r in proposal['rows'] if not r['excluded']]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]['fields']['balance_difference_minor'], '0')
        self.assertTrue(rows[0]['fields']['description'].endswith('EXAMPLE SHOP'))
        self.assertFalse(statement_catalog([second])['statements'])
        for field, value in (('page_number', 3), ('account', '987654321'),
                             ('period', '07/01/20 07/31/20'), ('printed_page', '1')):
            wrong = deepcopy(second)
            if field == 'page_number':
                wrong[field] = value
            else:
                index = {'account':2, 'period':3, 'printed_page':4}[field]
                next(r for r in wrong['rows'] if r['row_index'] == index)['cells'][0]['expected_text'] = value
            statement, _ = selected([first, wrong])
            self.assertEqual(statement['page_numbers'], [1])
        first['rows'] = first['rows'][:-1]
        statement, _ = selected([first, second])
        self.assertEqual(statement['page_numbers'], [1])

    def test_spacing_in_printed_period_and_money_keeps_all_original_digits(self):
        original = source([
            [(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '100 . 00')],
            [(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '- 20 . 00 80. 00')],
            [(15, '06/30'), (75, 'Ending Balance'), (350, '80 .00')]],
            period='0 6/01 /2 0 06/3 0/20')
        original['rows'][0]['cells'][0]['expected_text'] = 'Account ·Statement'
        original['rows'][1]['cells'][0]['expected_text'] = '.Andrews'
        before = deepcopy(original)
        statement, proposal = selected([original])
        self.assertEqual((statement['period_start'], statement['period_end']), ('2020-06-01', '2020-06-30'))
        row = next(r for r in proposal['rows'] if not r['excluded'])
        self.assertEqual((row['fields']['amount_minor'], row['fields']['balance']), ('2000', '8000'))
        self.assertEqual(row['fields']['balance_difference_minor'], '0')
        self.assertFalse(row['issues'])
        self.assertEqual(original, before)
        for value in ('-2 0.00', '-2O.00', '-20.0 0', '-20,00', '--20.00'):
            damaged = deepcopy(original)
            damaged['rows'][10]['cells'][-1]['expected_text'] = value + ' 80.00'
            _, p = selected([damaged])
            item = next(r for r in p['rows'] if not r['excluded'])
            self.assertNotIn('amount_minor', item['fields'])
            self.assertTrue(item['issues'])

    def test_out_of_order_pages_use_unique_printed_numbers_without_changing_pdf_addresses(self):
        first = source([
            [(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '100.00')],
            [(15, '06/03'), (75, 'Withdrawal Debit Card'), (310, '-20.00 80.00')],
            [(15, '--- Continued on following page ---')]], page=3, printed_page=1)
        second = source([
            [(75, 'EXAMPLE SHOP')],
            [(15, '06/04'), (75, 'Withdrawal Debit Card'), (310, '-10.00 70.00')],
            [(15, '--- Continued on following page ---')]], page=2, printed_page=2, names=False)
        third = source([
            [(15, '06/05'), (75, 'Deposit ACH Example'), (310, '30.00 100.00')],
            [(15, '06/30'), (75, 'Ending Balance'), (350, '100.00')]], page=1, printed_page=3, names=False)
        original = [third, second, first]; before = deepcopy(original)
        statement, proposal = selected(original)
        self.assertTrue(statement['uses_printed_page_order'])
        self.assertEqual(statement['page_numbers'], [3, 2, 1])
        rows = [r for r in proposal['rows'] if not r['excluded']]
        self.assertEqual([r['fields']['date'] for r in rows], ['2020-06-03', '2020-06-04', '2020-06-05'])
        self.assertEqual([r['page_number'] for r in rows], [3, 2, 1])
        self.assertEqual([r['fields']['balance_difference_minor'] for r in rows], ['0', '0', '0'])
        self.assertEqual(rows[0]['continuation_sources'][0]['page_number'], 2)
        self.assertEqual(original, before)
        for value in ('2', '4'):
            damaged = deepcopy(original)
            damaged[0]['rows'][4]['cells'][0]['expected_text'] = value
            st, p = selected(damaged)
            self.assertNotIn('uses_printed_page_order', st)
            self.assertEqual(st['page_numbers'], [3])
        # A readable 1,2 prefix may be ordered, but neither an unreadable page
        # outside it nor a page across a physical gap is pulled into that prefix.
        damaged = deepcopy(original)
        damaged[0]['rows'][4]['cells'][0]['expected_text'] = 'unreadable'
        st, p = selected(damaged)
        self.assertEqual(st['page_numbers'], [3, 2])
        self.assertTrue(p['issues'])
        gap = deepcopy(original); gap[0]['page_number'] = 8
        st, _ = selected(gap)
        self.assertEqual(st['page_numbers'], [3, 2])

    def test_payment_share_and_closure_are_account_information_not_card_debt_or_payments(self):
        for end in ('06/30 Ending Balance', '06/29 ID 0011 VISA PAYMENT Closed'):
            closing = [(15, end)] + ([(350, '0.00')] if 'Ending' in end else [])
            data=source([[(15, '06/01 ID 0011 VISA PAYMENT Previous Balance'), (350, '0.00')], closing,
                         [(15, '*** This is the final statement you will receive for this account***')],
                         [(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '200.00')],
                         [(15, '06/30 Ending Balance'), (350, '200.00')]])
            st, proposal=selected([data], '0011')
            self.assertEqual(st['account_type'],'other');self.assertEqual(st['account_label'],'VISA PAYMENT')
            self.assertFalse(any(not r['excluded'] for r in proposal['rows']))
            self.assertNotIn('FREE CHECKING',str(proposal))
            if 'Closed' in end:
                self.assertEqual(st['account_closure']['date'],'2020-06-29')
                self.assertFalse(any(r['fields'].get('description')=='Closing Balance' for r in proposal['rows']))
                self.assertEqual(proposal['issues'],[])
            else:
                self.assertNotIn('account_closure',st)
                self.assertEqual(len([r for r in proposal['rows'] if r['kind']=='balance']),2)

    def test_different_share_or_outside_period_closure_is_not_accepted(self):
        for text in ('06/29 ID 0040 VISA PAYMENT Closed','07/29 ID 0011 VISA PAYMENT Closed'):
            data=source([[(15, '06/01 ID 0011 VISA PAYMENT Previous Balance'), (350, '0.00')],[(15,text)]])
            st, proposal=selected([data], '0011')
            self.assertNotIn('account_closure',st)
            self.assertTrue(any(not r['excluded'] for r in proposal['rows']))
            self.assertTrue(proposal['issues'])

    def test_spaced_fixed_headings_keep_original_text_and_matching_continuations(self):
        first = source([[(15, '06/01 ID 0040 FREE CHECKING Pre vious Bal ance'), (350, '100.00')],
                        [(15, '--- Continued on following page ---')]])
        second = source([[(15, '06/03'), (75, 'Deposit ACH Example'), (310, '20.00 120.00')],
                         [(15, '06/30 Ending Balance'), (350, '120.00')]], page=2, printed_page=2, names=False)
        second['rows'][0]['cells'][0]['expected_text'] = 'Ac count State ment'
        second['rows'][1]['cells'][0]['expected_text'] = 'Unreadable logo'
        before = deepcopy([first, second])
        st, p = selected([first, second])
        self.assertEqual(st['page_numbers'], [1, 2])
        payment = next(r for r in p['rows'] if not r['excluded'])
        self.assertEqual(payment['fields']['amount_minor'], '2000')
        self.assertEqual(payment['fields']['balance'], '12000')
        self.assertEqual(p['issues'], [])
        self.assertEqual([first, second], before)
        self.assertTrue(any('Pre vious Bal ance' in c['expected_text'] for r in p['rows'] for c in r['source_cells']))
        second['rows'][0]['cells'][0]['expected_text'] = 'Acc0unt Statement'
        self.assertIsNone(andrews_page(second, allow_unbranded=True))
        self.assertEqual(selected([first, second])[0]['page_numbers'], [1])

    def test_damaged_previous_balance_label_cannot_inherit_another_share(self):
        grid = source([[(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '100.00')],
                       [(15, '06/03'), (75, 'Deposit ACH Example'), (310, '20.00 120.00')],
                       [(15, '06/01 ID 0000 BASE SHARE SAVINGS Previ0us Balance'), (350, '300.00')],
                       [(15, '06/04'), (75, 'Deposit ACH Other share'), (310, '40.00 340.00')]])
        st, p = selected([grid])
        self.assertEqual(len([r for r in p['rows'] if not r['excluded']]), 1)
        self.assertNotIn('Other share', str(p))
        self.assertTrue(statement_catalog([grid])['unclassified_sources'])
