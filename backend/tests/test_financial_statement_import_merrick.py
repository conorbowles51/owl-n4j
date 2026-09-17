import unittest
from copy import deepcopy
from services.financial.statement_import_merrick import merrick_statement, propose_merrick_table
from services.financial.statement_import_card_balances import merrick_summary_balances
from tests.test_financial_statement_import_proposal import source
from tests.test_financial_pdf_geometry_candidates import rectangle


def statement():
    return source([['Statement Date: 04/25121'],['Account Number: 1111 2222 3333 4444'],
        ['MERRICK BANK'],['Send Payments to:','EXAMPLE HOLDER'],
        ['Transactions, Payments and Credits'],['TransDfla','Item Description','Amount'],
        ['04/22','24137463GEJBPDNXO','EXAMPLE SHOP','14.00'],
        ['04/23','24137463JHEZKK04F','EXAMPLE CAFE','100.00'],
        ['Fees'],['TOTAL FEES FOR THIS PERIOD','0.00'],['Interest Charged'],
        ['04/25','Interest Charge on Purchases','0.00'],['TOTAL INTEREST FOR THIS PERIOD','0.00'],
        ['2021 Totals Year-to-Date']])


def summary_statement():
    data = statement()
    data['rows'][0]['cells'][0]['expected_text'] = 'Statement Date: 04/25/21'
    summary = source([
        ['New Balance', '$999.00'],  # Payment coupon, deliberately different.
        ['MERRICK ACCOUNT SUMMARY'],
        ['| Summary of Account Activity', '| Payment Information'],
        ['Previous Balance', '$0.00', 'New Balance', '$888.00'],
        ['Purchases', '+ $114.00', 'Minimum Payment Due', '$35.00'],
        ['New Balance', '$114.00'],
        ['Credit Limit', '$1,000.00'],
    ])
    positions = [
        [(90, 50, 60), (240, 50, 35)],
        [(90, 150, 145)],
        [(90, 180, 130), (285, 180, 100)],
        [(95, 200, 80), (245, 200, 30), (290, 200, 70), (480, 200, 35)],
        [(95, 225, 70), (230, 225, 45), (290, 225, 100), (480, 225, 35)],
        [(95, 255, 70), (240, 255, 35)],
        [(95, 280, 70), (235, 280, 40)],
    ]
    for row, boxes in zip(summary['rows'], positions):
        row['row_index'] += 100
        for cell, (x, y, width) in zip(row['cells'], boxes):
            cell['locator'] = rectangle(y, x=x, width=width, height=8)
    for row in data['rows']:
        for cell in row['cells']:
            cell['locator'] = rectangle(350 + row['row_index'] * 15,
                                         x=20 + cell['column_index'] * 140, width=130, height=8)
    data['rows'] = summary['rows'] + data['rows']
    return data


def measured_statement():
    data = statement()
    for row in data['rows']:
        y = 20 + row['row_index'] * 20 if row['row_index'] < 5 else 210 + (row['row_index'] - 8) * 20
        for cell in row['cells']:
            cell['locator'] = rectangle(y, x=20 + cell['column_index'] * 140, width=130, height=8)
    data['rows'][5]['cells'][0]['expected_text'] = 'Trans Date'
    for cell, (x, width) in zip(data['rows'][5]['cells'], ((30, 45), (270, 80), (490, 35))):
        cell['locator'] = rectangle(120, x=x, width=width)
    for row in data['rows'][6:8]:
        for cell, (x, width) in zip(row['cells'], ((30, 35), (150, 90), (270, 150), (490, 35))):
            cell['locator'] = rectangle(150 + 30 * (row['row_index'] - 6), x=x, width=width)
    return data


class MerrickStatementTests(unittest.TestCase):
    def test_damaged_heading_uses_two_readable_positioned_dates_without_repairing_a_payment_date(self):
        data = measured_statement()
        data['rows'][5]['cells'][0]['expected_text'] = 'TransDfla'
        extra = deepcopy(data['rows'][6])
        extra['row_index'] = 99
        extra['cells'][0]['expected_text'] = '04/24'
        for cell in extra['cells']:
            cell['locator']['rect'][1] += 45_000
            cell['locator']['rect'][3] += 45_000
        data['rows'].insert(8, extra)
        data['rows'][6]['cells'][0]['expected_text'] = 'O4/22'
        original = deepcopy(data)
        result = propose_merrick_table(data, 'USD', merrick_statement(data))['rows'][6]
        self.assertEqual(result['fields']['amount_minor'], '1400')
        self.assertEqual(result['fields']['description'], 'EXAMPLE SHOP')
        self.assertNotIn('date', result['fields'])
        self.assertEqual(len(result['issues']), 1)
        self.assertEqual(data, original)
        for bad_heading in ('Unknown', 'Trans 2020', 'Trans Date 2020', 'Settlement'):
            data['rows'][5]['cells'][0]['expected_text'] = bad_heading
            self.assertEqual(propose_merrick_table(data, 'USD', merrick_statement(data))['rows'][6]['fields'], {})

    def test_damaged_date_keeps_measured_description_reference_and_amount_without_guessing(self):
        data = measured_statement()
        data['rows'][6]['cells'][0]['expected_text'] = 'O4/22'
        before = deepcopy(data)
        row = propose_merrick_table(data, 'USD', merrick_statement(data))['rows'][6]
        self.assertEqual(row['kind'], 'unresolved')
        self.assertFalse(row['excluded'])
        self.assertEqual(row['fields']['description'], 'EXAMPLE SHOP')
        self.assertEqual(row['fields']['bank_reference'], '24137463GEJBPDNXO')
        self.assertEqual(row['fields']['amount_minor'], '1400')
        self.assertEqual(row['fields']['direction'], 'debit')
        self.assertNotIn('date', row['fields'])
        self.assertEqual(len(row['issues']), 1)
        self.assertIn('other recognised fields have been kept', row['issues'][0])
        self.assertEqual(data, before)

    def test_damaged_date_and_amount_stay_separate_review_problems(self):
        data = measured_statement()
        data['rows'][6]['cells'][0]['expected_text'] = 'O4/22'
        data['rows'][6]['cells'][-1]['expected_text'] = '14O0'
        row = propose_merrick_table(data, 'USD', merrick_statement(data))['rows'][6]
        self.assertEqual(row['fields']['description'], 'EXAMPLE SHOP')
        self.assertNotIn('amount_minor', row['fields'])
        self.assertNotIn('direction', row['fields'])
        self.assertNotIn('date', row['fields'])
        self.assertEqual(len(row['issues']), 2)

    def test_unclear_header_or_row_positions_never_fill_other_fields_for_a_damaged_date(self):
        for damage in ('missing-header', 'duplicate-header', 'wrong-page', 'other-column', 'other-line', 'missing-rectangle'):
            data = measured_statement()
            cells = data['rows'][6]['cells']
            cells[0]['expected_text'] = 'O4/22'
            if damage == 'missing-header':
                data['rows'][5]['cells'][0]['expected_text'] = 'TransDfla'
            elif damage == 'duplicate-header':
                data['rows'][5]['cells'].append(deepcopy(data['rows'][5]['cells'][-1]))
            elif damage == 'wrong-page':
                cells[0]['locator']['page'] = 2
            elif damage == 'other-column':
                cells[-1]['locator'] = rectangle(150, x=410, width=35)
            elif damage == 'other-line':
                cells[-1]['locator'] = rectangle(195, x=490, width=35)
            else:
                cells[-1]['locator'] = {'kind': 'page_only', 'page': 1}
            with self.subTest(damage=damage):
                row = propose_merrick_table(data, 'USD', merrick_statement(data))['rows'][6]
                self.assertEqual(row['fields'], {})
                self.assertEqual(row['kind'], 'unresolved')
                self.assertTrue(row['issues'])

    def test_damaged_date_on_a_zero_value_is_not_silently_dropped(self):
        data = measured_statement()
        data['rows'][6]['cells'][0]['expected_text'] = 'O4/22'
        data['rows'][6]['cells'][-1]['expected_text'] = '0.00'
        row = propose_merrick_table(data, 'USD', merrick_statement(data))['rows'][6]
        self.assertFalse(row['excluded'])
        self.assertEqual(row['fields']['amount_minor'], '0')
        self.assertTrue(row['issues'])

    def test_detached_payment_minus_uses_the_same_line_without_changing_source_cells(self):
        data = statement()
        cells = source([['04/22', '7412061 3P00XTMJGS',
                         'MOBILE PAYMENT-THANK YOU EXAMPLE CITY', '114.00', '-']])['rows'][0]['cells']
        data['rows'][6]['cells'] = cells
        cells[-2]['locator'] = rectangle(420, x=480, width=20, height=5)
        cells[-1]['locator'] = rectangle(423, x=506, width=2, height=1)
        before = deepcopy(data)
        row = propose_merrick_table(data, 'USD', merrick_statement(data))['rows'][6]
        self.assertEqual(row['fields']['amount_minor'], '11400')
        self.assertEqual(row['fields']['direction'], 'credit')
        self.assertEqual(row['fields']['amount_column'], '3')
        self.assertEqual(row['fields']['bank_reference'], '7412061 3P00XTMJGS')
        self.assertEqual(row['fields']['description'], 'MOBILE PAYMENT-THANK YOU EXAMPLE CITY')
        self.assertEqual(row['issues'], [])
        self.assertEqual(data, before)
        for box in (rectangle(450, x=506, width=2, height=1),
                    rectangle(423, x=550, width=2, height=1), {'kind': 'page_only', 'page': 1}):
            cells[-1]['locator'] = box
            row = propose_merrick_table(data, 'USD', merrick_statement(data))['rows'][6]
            self.assertNotIn('amount_minor', row['fields'])
            self.assertNotIn('direction', row['fields'])
            self.assertTrue(row['issues'])

    def test_amounts_require_printed_cents_and_a_single_sign(self):
        for text, expected in (('114.00-', ('11400', 'credit')),
                               ('- $114.00', ('11400', 'credit')),
                               ('$ -114.00', ('11400', 'credit')),
                               ('+14.00', ('1400', 'debit')),
                               ('1,234.56', ('123456', 'debit')),
                               ('275', None), ('2.7', None), ('-14.00-', None),
                               ('14.O0', None), ('+ -14.00', None)):
            with self.subTest(text=text):
                data = statement()
                data['rows'][6]['cells'][-1]['expected_text'] = text
                row = propose_merrick_table(data, 'USD', merrick_statement(data))['rows'][6]
                if expected:
                    self.assertEqual((row['fields']['amount_minor'], row['fields']['direction']), expected)
                    self.assertEqual(row['issues'], [])
                else:
                    self.assertNotIn('amount_minor', row['fields'])
                    self.assertTrue(row['issues'])
        data = statement()
        data['rows'][6]['cells'][-1]['expected_text'] = 'USD 14.00'
        row = propose_merrick_table(data, 'EUR', merrick_statement(data))['rows'][6]
        self.assertNotIn('amount_minor', row['fields'])
        self.assertTrue(row['issues'])

    def test_payment_without_readable_credit_marker_never_becomes_a_charge(self):
        data = statement()
        data['rows'][6]['cells'][2]['expected_text'] = 'MOBILE PAYMENT-THANK YOU EXAMPLE CITY'
        row = propose_merrick_table(data, 'USD', merrick_statement(data))['rows'][6]
        self.assertEqual(row['fields']['amount_minor'], '1400')
        self.assertNotIn('direction', row['fields'])
        self.assertIn('no minus sign', row['issues'][0])

    def test_uppercase_description_words_are_not_removed_as_a_bank_reference(self):
        data = statement()
        data['rows'][6]['cells'][1]['expected_text'] = 'EXAMPLE STORE GROUP'
        row = propose_merrick_table(data, 'USD', merrick_statement(data))['rows'][6]
        self.assertNotIn('bank_reference', row['fields'])
        self.assertEqual(row['fields']['description'], 'EXAMPLE STORE GROUP EXAMPLE SHOP')

    def test_summary_balances_use_activity_box_and_preserve_original_cells(self):
        data = summary_statement()
        before = deepcopy(data)
        proposal = propose_merrick_table(data, 'USD', merrick_statement(data))
        controls = [r for r in proposal['rows'] if r['kind'] == 'balance']
        self.assertEqual([r['fields']['balance'] for r in controls], ['0', '11400'])
        self.assertTrue(all(r['excluded'] for r in controls))
        self.assertEqual([r['row_index'] for r in controls], [103, 105])
        self.assertEqual(controls[0]['fields']['balance_column'], '1')
        self.assertEqual(len([r for r in proposal['rows'] if not r['excluded']]), 2)
        self.assertEqual(proposal['issues'], [])
        self.assertEqual(data, before)

    def test_missing_or_ambiguous_summary_geometry_never_uses_payment_box(self):
        for change in ('missing-heading', 'duplicate-opening', 'overlapping-boxes', 'missing-value'):
            data = summary_statement()
            if change == 'missing-heading':
                data['rows'][2]['cells'][0]['locator'] = {'kind': 'page_only', 'page': 1}
            elif change == 'duplicate-opening':
                duplicate = deepcopy(data['rows'][3]); duplicate['row_index'] = 200
                data['rows'].append(duplicate)
            elif change == 'overlapping-boxes':
                data['rows'][2]['cells'][1]['locator'] = rectangle(180, x=100, width=100)
            else:
                del data['rows'][3]['cells'][1]
            with self.subTest(change=change):
                controls, issues = merrick_summary_balances(data, 'USD')
                self.assertEqual(controls, {})
                self.assertTrue(issues)

    def test_duplicate_closing_preserves_only_opening_and_requires_review(self):
        for missing_value in (False, True):
            data = summary_statement()
            duplicate = deepcopy(data['rows'][5]); duplicate['row_index'] = 200
            if missing_value:
                duplicate['cells'] = duplicate['cells'][:1]
            data['rows'].append(duplicate)
            controls, issues = merrick_summary_balances(data, 'USD')
            self.assertEqual(set(controls), {103})
            self.assertTrue(issues)

    def test_unreadable_and_negative_owed_balances_preserve_exact_printed_values(self):
        for text, amount in (('$11O.00', None), ('- $12.50', '-1250'), ('$0.00', '0')):
            data = summary_statement()
            data['rows'][5]['cells'][1]['expected_text'] = text
            controls, _ = merrick_summary_balances(data, 'USD')
            self.assertEqual(controls[105]['fields'].get('balance'), amount)
            self.assertEqual(bool(controls[105]['issues']), amount is None)

    def test_ocr_box_border_is_ignored_but_currency_digit_is_never_repaired(self):
        data = summary_statement()
        data['rows'][2]['cells'][0]['expected_text'] = '[ Summary of Account Activity'
        data['rows'][2]['cells'][1]['expected_text'] = '| | Payment Information'
        data['rows'][3]['cells'][1]['expected_text'] = '31,861.84'
        before = deepcopy(data)
        controls, issues = merrick_summary_balances(data, 'USD')
        self.assertEqual(issues, [])
        self.assertNotIn('balance', controls[103]['fields'])
        self.assertIn('dollar sign', controls[103]['issues'][0])
        self.assertEqual(controls[105]['fields']['balance'], '11400')
        self.assertEqual(data, before)

    def test_split_account_digits_are_read_only_after_the_account_label(self):
        for values, expected in ((['Account Number: 1111', '2222', '3333', '4444'], '1111 2222 3333 4444'),
                                 (['Account Number:', '1111', '2222', '3333', '4444'], '1111 2222 3333 4444'),
                                 (['Account Number: 1111', '2222', '3333', '444O'], ''),
                                 (['1111', '2222', '3333', '4444'], '')):
            data = statement()
            data['rows'][1]['cells'] = source([values])['rows'][0]['cells']
            self.assertEqual(merrick_statement(data)['account_reference'], expected)

    def test_disagreeing_closing_dates_require_transaction_date_review(self):
        data = statement()
        data['rows'][0]['cells'][0]['expected_text'] = 'Statement Date: 04/25/21'
        data['rows'].extend(source([['Billing Cycle Closing Date', '04/25/24']])['rows'])
        group = merrick_statement(data)
        self.assertTrue(group['date_conflict'])
        self.assertIsNone(group['date_year'])
        rows = [r for r in propose_merrick_table(data, 'USD', group)['rows'] if not r['excluded']]
        self.assertTrue(all('date' not in r['fields'] and r['issues'] for r in rows))
        data['rows'][-1]['cells'][1]['expected_text'] = '04/25/2021'
        self.assertFalse(merrick_statement(data)['date_conflict'])

    def test_header_damage_is_not_repaired_but_transaction_dates_use_printed_year_context(self):
        data=statement();group=merrick_statement(data)
        self.assertEqual(group['statement_date'],'')
        self.assertEqual(group['printed_statement_date'],'04/25121')
        self.assertEqual(group['holder'],'EXAMPLE HOLDER')
        proposal=propose_merrick_table(data,'USD',group)
        rows=[r for r in proposal['rows'] if not r['excluded']]
        self.assertEqual(len(rows),2)
        self.assertEqual([r['fields']['date'] for r in rows],['2021-04-22','2021-04-23'])
        self.assertEqual([r['fields']['amount_minor'] for r in rows],['1400','10000'])
        self.assertEqual(rows[0]['fields']['bank_reference'],'24137463GEJBPDNXO')
        self.assertFalse(any(r['issues'] for r in rows))

    def test_out_of_context_date_and_unreadable_money_are_retained_as_exceptions(self):
        data=statement()
        data['rows'][6]['cells'][0]['expected_text']='12/22'
        data['rows'][7]['cells'][-1]['expected_text']='1O0.00'
        rows=[r for r in propose_merrick_table(data,'USD',merrick_statement(data))['rows'] if not r['excluded']]
        self.assertEqual(len(rows),2)
        self.assertNotIn('date',rows[0]['fields'])
        self.assertTrue(rows[0]['issues'])
        self.assertNotIn('amount_minor',rows[1]['fields'])
        self.assertTrue(rows[1]['issues'])

    def test_conflicting_statement_year_is_not_used_to_fill_transaction_dates(self):
        data=statement()
        data['rows'][0]['cells'][0]['expected_text']='Statement Date: 04/25/22'
        group=merrick_statement(data)
        self.assertIsNone(group['date_year'])
        rows=[r for r in propose_merrick_table(data,'USD',group)['rows'] if not r['excluded']]
        self.assertTrue(all('date' not in r['fields'] for r in rows))


class MerrickClosingDateFallbackTests(unittest.TestCase):
    def example(self):
        data=statement()
        data['rows'][0]['cells'][0]['expected_text']='Statement heading unreadable'
        extra=source([['Billing Cycle Closing Date','04/25/21']])['rows'][0]
        extra['row_index']=100
        data['rows'].append(extra)
        return data

    def test_unique_labelled_closing_date_and_full_ytd_year_supply_context_without_rewriting_header(self):
        data=self.example();before=deepcopy(data);group=merrick_statement(data)
        self.assertEqual(group['statement_date'],'2021-04-25')
        self.assertEqual(group['printed_statement_date'],'')
        self.assertEqual(group['printed_closing_date'],'04/25/21')
        self.assertEqual(group['statement_date_basis'],'billing_cycle_closing_date')
        self.assertEqual((group['period_start'],group['period_end']),('',''))
        rows=[r for r in propose_merrick_table(data,'USD',group)['rows'] if not r['excluded']]
        self.assertEqual([r['fields']['date'] for r in rows],['2021-04-22','2021-04-23'])
        self.assertTrue(all('closing date' in r['fields']['date_context'] for r in rows))
        self.assertEqual([r['fields']['amount_minor'] for r in rows],['1400','10000'])
        self.assertEqual(data,before)

    def test_missing_conflicting_invalid_or_unlabelled_context_cannot_create_dates(self):
        for change in ('year','no_year','invalid','duplicate','unlabelled','present_heading'):
            data=self.example()
            if change=='year':data['rows'][-2]['cells'][0]['expected_text']='2022 Totals Year-to-Date'
            elif change=='no_year':data['rows'][-2]['cells'][0]['expected_text']='Totals Year-to-Date'
            elif change=='invalid':data['rows'][-1]['cells'][1]['expected_text']='04/35/21'
            elif change=='duplicate':data['rows'].extend(source([['Billing Cycle Closing Date','04/26/21']])['rows'])
            elif change=='unlabelled':data['rows'][-1]['cells'][0]['expected_text']='Date'
            elif change=='present_heading':data['rows'][0]['cells'][0]['expected_text']='Statement Date: 04/25/24'
            with self.subTest(change=change):
                group=merrick_statement(data)
                self.assertNotIn('statement_date_basis',group)
                self.assertIsNone(group['date_year'])
                rows=[r for r in propose_merrick_table(data,'USD',group)['rows'] if not r['excluded']]
                self.assertTrue(all('date' not in r['fields'] for r in rows))

    def test_interest_date_difference_is_flagged_without_changing_the_printed_day_or_month(self):
        data=self.example()
        data['rows'][11]['cells'][-1]['expected_text']='2.50'
        group=merrick_statement(data)
        row=propose_merrick_table(data,'USD',group)['rows'][11]
        self.assertEqual(row['fields']['date'],'2021-04-25')
        self.assertFalse(row['issues'])
        data['rows'][11]['cells'][0]['expected_text']='03/25'
        row=propose_merrick_table(data,'USD',group)['rows'][11]
        self.assertEqual(row['fields']['date'],'2021-03-25')
        self.assertEqual(row['fields']['amount_minor'],'250')
        self.assertTrue(any('interest-charge date differs' in issue for issue in row['issues']))
        self.assertEqual(row['source_cells'][0]['expected_text'],'03/25')
