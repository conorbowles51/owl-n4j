import unittest
from copy import deepcopy
from services.financial.statement_import_proposal import propose_table, exact_amount
from tests.test_financial_ruled_statement_alignment import PAYMENTS


def source(grid):
    return dict(case_id='case', evidence_file_id='file', page_number=1, table_index=0,
        source_revision='a'*64, rows=[dict(row_index=i, cells=[dict(column_index=j,
            expected_text=value, locator={'source':f'{i}:{j}'}) for j,value in enumerate(row) if value])
            for i,row in enumerate(grid)])


def statement():
    return source([['Date','Description','Credit','Debit','Balance'],
        ['2023-01-01','Opening Balance','','','€12,450']] +
        [[d,'Incoming' if c else 'Outgoing',c,w,b] for d,c,w,b in PAYMENTS])


class AutomaticStatementProposalTests(unittest.TestCase):
    def test_page_counters_are_retained_without_becoming_payments(self):
        data = source([['Page 1 of 31'], ['Page 2 / 31'], ['Page 3 of 31 fee 100.00']])
        result = propose_table(data, 'EUR', page_has_transaction_table=True)
        self.assertEqual([r['excluded'] for r in result['rows']], [True, True, False])
        self.assertEqual(result['rows'][0]['source_cells'], data['rows'][0]['cells'])
        self.assertEqual(result['transaction_count'], 1)
        # A page-number-like payment description does not discard a payment.
        payment = source([['Date', 'Description', 'Credit'], ['2024-01-01', 'Page 1 of 31', '100.00']])
        self.assertFalse(propose_table(payment, 'EUR')['rows'][1]['excluded'])
        self.assertFalse(propose_table(source([['Page 1 of 31']]), 'EUR')['rows'][0]['excluded'])

    def test_separate_page_headings_are_not_payments_but_unknown_text_needs_review(self):
        data=source([['Account Name: Example Person'],['TRANSACTION HISTORY'],['Unexplained value 100.00']])
        result=propose_table(data,'USD',page_has_transaction_table=True)
        self.assertTrue(result['rows'][0]['excluded'])
        self.assertTrue(result['rows'][1]['excluded'])
        self.assertFalse(result['rows'][2]['excluded'])
        self.assertEqual(result['rows'][2]['kind'],'unresolved')

    def test_complete_nexus_without_manual_columns_or_row_selection(self):
        original=statement(); before=deepcopy(original)
        result=propose_table(original,'EUR')
        self.assertEqual(result['transaction_count'],12)
        self.assertEqual(result['needs_attention'],0)
        payments=[r for r in result['rows'] if not r['excluded']]
        self.assertEqual(sum(int(r['fields']['amount_minor']) for r in payments if r['fields']['direction']=='credit'),103500000)
        self.assertEqual(sum(int(r['fields']['amount_minor']) for r in payments if r['fields']['direction']=='debit'),100000000)
        self.assertEqual(payments[-1]['fields']['balance'],'4745000')
        self.assertEqual([r['fields']['date'] for r in payments],[p[0] for p in PAYMENTS])
        self.assertEqual(original,before)
        self.assertEqual(result,propose_table(original,'EUR'))

    def test_omitted_payment_flags_next_balance_instead_of_silently_balancing(self):
        data=statement(); del data['rows'][3]
        result=propose_table(data,'EUR')
        self.assertGreater(result['needs_attention'],0)
        affected=next(r for r in result['rows'] if r['fields'].get('date')=='2023-05-25')
        self.assertEqual(affected['fields']['balance_difference_minor'],'-12000000')

    def test_description_named_opening_balance_with_payment_is_not_discarded(self):
        data=source([['Date','Description','Credit','Debit','Balance'],
            ['2023-03-18','Opening Balance','100','','100']])
        self.assertFalse(propose_table(data,'EUR')['rows'][1]['excluded'])

    def test_unknown_table_is_retained_as_exception(self):
        result=propose_table(source([['Reference','Unlabelled value'],['abc','100']]),'EUR')
        self.assertEqual(result['needs_attention'],2)
        self.assertTrue(all(not r['excluded'] for r in result['rows']))

    def test_ambiguous_date_and_signed_amount_require_attention(self):
        result=propose_table(source([['Date','Description','Amount'],['01/02/2023','Payment','-20.00']]),'EUR')
        row=result['rows'][1]
        self.assertNotIn('direction',row['fields'])
        self.assertTrue(row['issues'])

    def test_exact_decimal_currency_and_precision(self):
        self.assertEqual(exact_amount('1,234.56','EUR'),'123456')
        self.assertEqual(exact_amount('1.234','KWD'),'1234')
        self.assertEqual(exact_amount('1234','JPY'),'1234')
        for value in ('1.234','1,23','12O.00','1.000,00','NaN','1e3'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                exact_amount(value,'EUR')


class ReviewedDateMeaningTests(unittest.TestCase):
    def test_import_requires_explicit_credit_or_debit_for_included_rows(self):
        from pydantic import ValidationError
        from services.financial.statement_import import ImportRow
        values = dict(id='payment', date='2023-01-02', description='Payment', amount_minor='1400')
        with self.assertRaisesRegex(ValidationError, 'Choose Credit or Debit'):
            ImportRow(**values)
        with self.assertRaisesRegex(ValidationError, 'Choose Credit or Debit'):
            ImportRow(**values, direction=None)
        self.assertEqual(ImportRow(**values, direction='credit').direction, 'credit')
        self.assertIsNone(ImportRow(id='header', excluded=True).direction)

    def test_booking_and_value_dates_are_not_relabelled_as_transaction_dates(self):
        from datetime import date
        from services.financial.statement_import import _reading_dates
        self.assertEqual(_reading_dates({'booking_date':'2023-01-03','value_date':'2023-01-04'}, '2023-01-02'),
                         {'posted_date':date(2023,1,2),'value_date':date(2023,1,4)})

    def test_running_balance_must_fit_database_range_even_for_excluded_control(self):
        from pydantic import ValidationError
        from services.financial.statement_import import ImportRow
        for value in ('9223372036854775808','-9223372036854775809'):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                ImportRow(id='control', excluded=True, balance_minor=value)


class TextPositionStatementTests(unittest.TestCase):
    def right_aligned_amounts(self):
        from tests.test_financial_pdf_geometry_candidates import rectangle
        grid = [
            [(31,49,'Date'), (113,157,'Description'), (391,415,'Credit'), (465,485,'Debit'), (537,569,'Balance')],
            [(31,76,'2020-07-01'), (113,181,'Opening Balance'), (570,598,'220.00')],
            [(31,76,'2020-07-02'), (113,222,'Wire from Alpha Consulting'), (424,452,'900.00'), (566,598,'1120.00')],
            [(31,76,'2020-07-03'), (113,228,'Transfer to Example Savings'), (497,525,'300.00'), (570,598,'820.00')],
            [(31,76,'2020-07-31'), (113,181,'Closing Balance'), (570,598,'820.00')],
        ]
        data = source([])
        data['table_source'] = 'text_alignment'
        data['rows'] = [dict(row_index=i, cells=[dict(column_index=j, expected_text=value,
            locator=rectangle(190+i*26, x=x, width=right-x)) for j,(x,right,value) in enumerate(values)])
            for i,values in enumerate(grid)]
        return data

    def test_left_aligned_headings_and_right_aligned_numbers_keep_blank_columns(self):
        data = self.right_aligned_amounts()
        original = deepcopy(data)
        result = propose_table(data, 'USD')
        self.assertEqual(result['transaction_count'], 2)
        self.assertEqual(result['needs_attention'], 0)
        incoming, outgoing = result['rows'][2:4]
        self.assertEqual([incoming['fields']['direction'], outgoing['fields']['direction']], ['credit', 'debit'])
        self.assertEqual([incoming['fields']['amount_minor'], outgoing['fields']['amount_minor']], ['90000', '30000'])
        self.assertEqual([incoming['fields']['balance'], outgoing['fields']['balance']], ['112000', '82000'])
        self.assertEqual(outgoing['fields']['debit_column'], '2')
        self.assertEqual(outgoing['fields']['balance_column'], '3')
        self.assertEqual([r['fields'].get('balance_difference_minor') for r in (incoming,outgoing)], ['0','0'])
        self.assertEqual(data, original)

    def test_lone_amount_between_credit_and_debit_headings_stays_unresolved(self):
        data = self.right_aligned_amounts()
        # Without a debit row, both alignments fit the geometry. Arithmetic is
        # not used to guess which printed money column owns the payment.
        del data['rows'][3]
        result = propose_table(data, 'USD')
        incoming = result['rows'][2]
        self.assertEqual(incoming['kind'], 'unresolved')
        self.assertNotIn('direction', incoming['fields'])
        self.assertTrue(incoming['issues'])

    def test_a_new_printed_header_starts_a_separate_alignment(self):
        data = self.right_aligned_amounts()
        left_aligned = self.fixture()['rows'][4:]
        for index, row in enumerate(left_aligned, len(data['rows'])):
            row['row_index'] = index
        data['rows'].extend(left_aligned)
        result = propose_table(data, 'USD')
        self.assertEqual(result['transaction_count'], 4)
        self.assertEqual(result['needs_attention'], 0)
        self.assertEqual([r['fields']['direction'] for r in result['rows'] if not r['excluded']],
                         ['credit','debit','credit','debit'])

    def fixture(self):
        from tests.test_financial_pdf_geometry_candidates import rectangle
        grid=[[(20,'BANK STATEMENT - EXAMPLE RECEIVER')],[(20,'SYNTHETIC TEST BANK')],
              [(20,'Account Number: TEST-120')],[(20,'Currency: USD')],
              [(20,'Date'),(100,'Description'),(370,'Credit'),(440,'Debit'),(510,'Balance')],
              [(20,'2021-03-01'),(100,'Opening Balance'),(510,'100.00')],
              [(20,'2021-03-23'),(100,'Wire TEST-REFERENCE'),(370,'120.00'),(510,'220.00')],
              [(20,'2021-03-24'),(100,'Outgoing'),(440,'20.00'),(510,'200.00')],
              [(20,'2021-03-31'),(100,'Closing Balance'),(510,'200.00')]]
        result=source([]); result['table_source']='text_alignment'
        result['rows']=[dict(row_index=i,cells=[dict(column_index=j,expected_text=t,
            locator=rectangle(20+i*24,x=x,width=len(t)*3,height=10)) for j,(x,t) in enumerate(row)]) for i,row in enumerate(grid)]
        return result

    def test_blank_cells_follow_printed_positions_and_keep_original_source_indices(self):
        data=self.fixture();before=deepcopy(data);result=propose_table(data,'USD')
        self.assertEqual(result['transaction_count'],2);self.assertEqual(result['needs_attention'],0)
        rows=[r for r in result['rows'] if not r['excluded']]
        self.assertEqual([r['fields']['amount_minor'] for r in rows],['12000','2000'])
        self.assertEqual([r['fields']['direction'] for r in rows],['credit','debit'])
        self.assertEqual([r['fields']['balance'] for r in rows],['22000','20000'])
        self.assertEqual(rows[1]['fields']['debit_column'],'2')
        self.assertEqual(rows[1]['fields']['balance_column'],'3')
        self.assertTrue(all(r['excluded'] for r in result['rows'][:6]))
        self.assertEqual(data,before)

    def test_crossing_or_unlocated_text_does_not_fall_back_to_shifted_indices(self):
        for damaged in ('crossing','missing'):
            data=self.fixture();cell=data['rows'][6]['cells'][3]
            if damaged=='crossing': cell['locator']['rect'][0]=400
            else: cell['locator']={'kind':'page_only','page':1}
            row=propose_table(data,'USD')['rows'][6]
            self.assertEqual(row['kind'],'unresolved')
            self.assertNotIn('amount_minor',row['fields'])
            self.assertNotIn('balance',row['fields'])
            self.assertTrue(row['issues'])

    def test_unknown_rows_before_a_header_are_not_silently_discarded(self):
        data=self.fixture();data['rows'][0]['cells'][0]['expected_text']='2021-03-01 Unlabelled payment 450.00'
        row=propose_table(data,'USD')['rows'][0]
        self.assertFalse(row['excluded']);self.assertTrue(row['issues'])
