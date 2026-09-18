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
    def test_date_warning_distinguishes_invalid_characters_calendar_and_missing_context(self):
        for text, message in [('O4/22', 'characters could not be read'),
                              ('04/44', 'invalid month or day'),
                              ('14/22', 'invalid month or day'),
                              ('02/30', 'invalid month or day'),
                              ('02/22', 'outside the closing month')]:
            data = measured_statement()
            data['rows'][0]['cells'][0]['expected_text'] = 'Statement Date: 04/25/21'
            data['rows'][6]['cells'][0]['expected_text'] = text
            row = propose_merrick_table(data, 'USD', merrick_statement(data))['rows'][6]
            self.assertFalse(row['excluded'])
            self.assertNotIn('date', row['fields'])
            self.assertTrue(any(message in issue for issue in row['issues']))
            self.assertEqual(row['fields']['amount_minor'], '1400')
        data = measured_statement()
        data['rows'][0]['cells'][0]['expected_text'] = 'Statement Date: unreadable'
        row = propose_merrick_table(data, 'USD', merrick_statement(data))['rows'][6]
        self.assertTrue(any('could not resolve its year' in issue for issue in row['issues']))
        data['rows'][0]['cells'][0]['expected_text'] = 'Statement Date: 03/25/21'
        data['rows'][6]['cells'][0]['expected_text'] = '02/29'
        row = propose_merrick_table(data, 'USD', merrick_statement(data))['rows'][6]
        self.assertTrue(any('invalid month or day' in issue for issue in row['issues']))

    def test_unreadable_date_on_measured_zero_interest_needs_no_payment_correction(self):
        for label in ('Interest Charge on Purchases', 'Interest Charge on Cash Advances',
                      'Interest Charge on Purchases:'):
            data = measured_statement()
            row = data['rows'][11]
            row['cells'][0]['expected_text'] = 'O4/25'
            row['cells'][1]['expected_text'] = label
            for cell, (x, width) in zip(row['cells'], ((30,35), (270,150), (490,35))):
                cell['locator'] = rectangle(290, x=x, width=width)
            original = deepcopy(data)
            result = propose_merrick_table(data, 'USD', merrick_statement(data))['rows'][11]
            self.assertTrue(result['excluded'])
            self.assertEqual(result['kind'], 'zero_charge')
            self.assertEqual(result['issues'], [])
            self.assertEqual(result['source_cells'], row['cells'])
            self.assertNotIn('date', result['fields'])
            self.assertEqual(data, original)
            for amount in ('0.01', 'O.00', '000', ''):
                row['cells'][2]['expected_text'] = amount
                check = propose_merrick_table(data, 'USD', merrick_statement(data))['rows'][11]
                self.assertFalse(check['excluded'])
                self.assertTrue(check['issues'])
            row['cells'][2]['expected_text'] = '0.00'
            row['cells'][2]['locator']['rect'][0] += 60_000
            row['cells'][2]['locator']['rect'][2] += 60_000
            self.assertFalse(propose_merrick_table(data, 'USD', merrick_statement(data))['rows'][11]['excluded'])

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


class MerrickCouponHolderTests(unittest.TestCase):
    def example(self, split=False):
        data = measured_statement()
        data['rows'][3]['cells'] = []
        coupon = [
            [('MERRICK ACCOUNT SUMMARY', 90, 210, 145, 8)],
            [('MERRICK BANK', 95, 124, 60, 4)],
            [('27 EXAMPLE', 370, 120, 40, 4), ('ST APT 2', 413, 120, 45, 4)],
            [('EXAMPLE CITY DC 20001-1234', 370, 128, 105, 4)],
            [('EXAMPLE A', 370, 113, 39, 4), ('99999', 510, 113, 15, 4)],
            [('HOLDER', 410, 117, 31, 3)],
        ] if split else [
            [('MERRICK ACCOUNT SUMMARY', 90, 210, 145, 8)],
            [('MERRICK BANK', 95, 124, 60, 4)],
            [('27 EXAMPLE ST APT 2', 370, 120, 90, 4)],
            [('EXAMPLE CITY DC 20001-1234', 370, 128, 105, 4)],
            [('EXAMPLE A HOLDER', 370, 113, 71, 4), ('99999', 510, 113, 15, 4)],
        ]
        for index, values in enumerate(coupon):
            data['rows'].append(dict(row_index=100 + index, cells=[dict(column_index=j, expected_text=text,
                locator=rectangle(y, x=x, width=w, height=h)) for j, (text, x, y, w, h) in enumerate(values)]))
        return data

    def test_complete_and_split_coupon_names_keep_exact_sources_and_existing_statement_id(self):
        from unittest.mock import patch
        for split in (False, True):
            data = self.example(split); before = deepcopy(data)
            with patch('services.financial.statement_import_merrick._coupon_holder', return_value=('', [])):
                previous = merrick_statement(data)
            result = merrick_statement(data)
            with self.subTest(split=split):
                self.assertEqual(result['holder'], 'EXAMPLE A HOLDER')
                self.assertEqual(result['id'], previous['id'])
                self.assertEqual(result['account_reference'], previous['account_reference'])
                self.assertEqual((result['period_start'], result['period_end']), ('', ''))
                self.assertEqual(len(result['holder_sources']), 2 if split else 1)
                self.assertEqual(' '.join(s['source_cell']['expected_text'] for s in result['holder_sources']), result['holder'])
                self.assertEqual(data, before)

    def test_missing_damaged_conflicting_or_unlocated_address_context_does_not_fill_a_name(self):
        for change in ('summary', 'bank', 'city', 'street', 'name', 'surname', 'geometry', 'page', 'size', 'two_names', 'two_addresses'):
            data = self.example(True)
            extra = {r['row_index']: r for r in data['rows'] if r['row_index'] >= 100}
            if change == 'summary': extra[100]['cells'][0]['expected_text'] = 'ACCOUNT INFORMATION'
            elif change == 'bank': extra[101]['cells'][0]['locator'] = rectangle(124, x=370, width=60, height=4)
            elif change == 'city': extra[103]['cells'][0]['expected_text'] = 'EXAMPLE CITY DC 2O001-1234'
            elif change == 'street': extra[102]['cells'][0]['expected_text'] = 'OTHER TEXT'
            elif change == 'name': extra[104]['cells'][0]['expected_text'] = 'EXAMPLE 4'
            elif change == 'surname': extra[105]['cells'][0]['expected_text'] = 'Ho1der'
            elif change == 'geometry': extra[105]['cells'][0]['locator'] = None
            elif change == 'page': extra[105]['cells'][0]['locator']['page'] = 2
            elif change == 'size': extra[105]['cells'][0]['locator']['page_size'] = [600000, 792000]
            elif change == 'two_names': extra[105]['cells'][0]['locator'] = rectangle(117, x=370, width=71, height=3)
            elif change == 'two_addresses': data['rows'].append(deepcopy(extra[103]))
            with self.subTest(change=change):
                result = merrick_statement(data)
                self.assertEqual(result['holder'], '')
                self.assertNotIn('holder_sources', result)


class MerrickChargeControlTests(unittest.TestCase):
    def example(self):
        data = measured_statement()
        data['rows'][0]['cells'][0]['expected_text'] = 'Statement Date: 04/25/21'
        data['rows'][11]['cells'][-1]['expected_text'] = '36.52'
        data['rows'][12]['cells'][-1]['expected_text'] = '36.32'
        return data

    def test_spaced_card_payment_with_damaged_reference_cannot_become_a_debit(self):
        for label in ('MOBILE PAYMENT - THANK YOU', 'PAYMENT - THANK YOU', 'Mobile Payment-Thank You'):
            data = measured_statement()
            data['rows'][6]['cells'][1]['expected_text'] = '§123456789012345'
            data['rows'][6]['cells'][2]['expected_text'] = label
            row = propose_merrick_table(data, 'USD', merrick_statement(data))['rows'][6]
            with self.subTest(label=label):
                self.assertEqual(row['fields']['amount_minor'], '1400')
                self.assertNotIn('direction', row['fields'])
                self.assertIn('Check its date', row['issues'][0])
                self.assertTrue(row['fields']['description'].startswith('§'))
            data['rows'][6]['cells'][-1]['expected_text'] = '14.00 -'
            row = propose_merrick_table(data, 'USD', merrick_statement(data))['rows'][6]
            self.assertEqual(row['fields']['direction'], 'credit')
            self.assertFalse(row['issues'])

    def test_printed_interest_total_detects_a_plausible_but_incorrect_amount(self):
        from services.financial.review_arithmetic import arithmetic_checks, arithmetic_problems, check_proposed_rows
        from services.financial.import_batches import initial_request
        data = self.example(); before = deepcopy(data)
        rows = propose_merrick_table(data, 'USD', merrick_statement(data))['rows']
        check = next(c for c in arithmetic_checks(rows, liability=True) if c['kind'] == 'interest_total')
        self.assertEqual((check['expected_minor'], check['printed_minor'], check['difference_minor']), ('3652', '3632', '20'))
        self.assertEqual(check['contributing_row_ids'], [rows[11]['id']])
        self.assertEqual(rows[11]['fields']['amount_minor'], '3652')
        self.assertEqual(rows[12]['kind'], 'statement_total')
        self.assertTrue(rows[12]['excluded'])
        self.assertEqual(data, before)
        proposal = dict(rows=rows, revision='a'*64, metadata={}, currency='USD', page_numbers=[1])
        edits = initial_request(proposal)['rows']
        corrected = next(r for r in edits if r['id'] == rows[11]['id'])
        corrected.update(amount_minor='3632', reason='Amount checked against the original PDF.')
        checks = check_proposed_rows(proposal, edits)
        self.assertFalse(arithmetic_problems(checks))
        self.assertEqual(next(c for c in checks['checks'] if c['kind'] == 'interest_total')['status'], 'matches')
        corrected['excluded'] = True
        self.assertEqual(next(c for c in check_proposed_rows(proposal, edits)['checks'] if c['kind'] == 'interest_total')['status'], 'difference')

    def test_unreadable_or_ambiguous_totals_cannot_claim_a_match(self):
        from services.financial.review_arithmetic import arithmetic_checks
        for change in ('number', 'duplicate', 'manual', 'page', 'overlap', 'ytd', 'heading'):
            data = self.example()
            if change == 'number': data['rows'][12]['cells'][-1]['expected_text'] = '3G.32'
            elif change == 'page': data['rows'][12]['cells'][-1]['locator']['page'] = 2
            elif change == 'overlap': data['rows'][12]['cells'][-1]['locator']['rect'][0] = 20000
            elif change == 'ytd': data['rows'][12]['cells'][0]['expected_text'] = 'Total interest charged in 2021'
            elif change == 'heading': data['rows'][10]['cells'][0]['expected_text'] = 'Other information'
            rows = propose_merrick_table(data, 'USD', merrick_statement(data))['rows']
            if change == 'duplicate': rows.append(deepcopy(rows[12]))
            elif change == 'manual': rows[6]['kind'] = 'manual_entry'
            with self.subTest(change=change):
                checks = [c for c in arithmetic_checks(rows, liability=True) if c['kind'] == 'interest_total']
                self.assertFalse(any(c['status'] in ('matches', 'difference') for c in checks))

    def test_fee_total_is_separate_from_whole_statement_debits_and_refunds_are_net_charges(self):
        from services.financial.review_arithmetic import arithmetic_checks
        data = self.example()
        row = deepcopy(data['rows'][6]);row['row_index']=90
        row['cells'][2]['expected_text']='FEE REFUND';row['cells'][-1]['expected_text']='2.00 -'
        data['rows'].insert(9, row)
        data['rows'][10]['cells'][-1]['expected_text']='-2.00'
        rows = propose_merrick_table(data, 'USD', merrick_statement(data))['rows']
        checks = {c['kind']: c for c in arithmetic_checks(rows, liability=True)}
        self.assertEqual(checks['fee_total']['status'], 'matches')
        self.assertEqual(checks['fee_total']['expected_minor'], '-200')
        self.assertEqual(checks['debit_total']['status'], 'unavailable')
