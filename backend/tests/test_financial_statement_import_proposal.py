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
