import unittest
from copy import deepcopy
from services.financial.review_arithmetic import arithmetic_checks, check_proposed_rows, arithmetic_problems, accepted_difference
from services.financial.statement_import_proposal import propose_table
from services.financial.statement_check_request import StatementCheckRequest, check_statement_request
from services.financial.pdf_candidates import PdfMappingError
from tests.test_financial_statement_import_proposal import source


def rows():
    return propose_table(source([
        ['Date', 'Description', 'Credit', 'Debit', 'Balance'],
        ['2020-01-01', 'Opening Balance', '', '', '0'],
        ['2020-01-02', 'First', '10', '', '10'],
        ['2020-01-03', 'Second', '20', '', '30'],
        ['2020-01-04', 'Closing Balance', '', '', '30'],
        ['', 'Total credits', '30', '', ''],
    ]), 'USD')['rows']


def request(proposal):
    return StatementCheckRequest(expected_revision='a'*64, currency='USD', rows=[dict(
        id=r['id'], excluded=r['excluded'], date=r['fields'].get('date',''),
        description=r['fields'].get('description',''), amount_minor=r['fields'].get('amount_minor',''),
        direction=r['fields'].get('direction'), balance_minor=r['fields'].get('balance')) for r in proposal['rows']])


class ReviewArithmeticTests(unittest.TestCase):
    def test_offsetting_mistakes_are_detected_despite_matching_closing_and_total(self):
        proposed = rows()
        proposed[2]['fields']['amount_minor'] = '1100'
        proposed[3]['fields']['amount_minor'] = '1900'
        checks = {c['kind']:c for c in arithmetic_checks(proposed)}
        self.assertEqual(checks['closing_balance']['status'], 'matches')
        self.assertEqual(checks['credit_total']['status'], 'matches')
        self.assertEqual(checks['running_balance']['mismatch_count'], 2)
        self.assertEqual(checks['running_balance']['findings'][0]['row_id'], proposed[2]['id'])

    def test_reverse_source_order_uses_printed_dates(self):
        proposed = rows()
        proposed[2:4] = reversed(proposed[2:4])
        running = arithmetic_checks(proposed)[1]
        self.assertEqual((running['status'], running['order'], running['compared_intervals']), ('matches','reverse_source_order',2))

    def test_missing_opening_checks_intervals_without_inventing_zero(self):
        proposed = rows()[2:4]
        checks = arithmetic_checks(proposed)
        self.assertEqual(checks[0]['status'], 'unavailable')
        self.assertEqual(checks[1]['compared_intervals'], 1)
        self.assertEqual(checks[1]['status'], 'matches')

    def test_manual_and_unknown_order_unavailable_but_closing_still_checked(self):
        proposed = rows()
        proposed[2]['kind'] = 'manual_entry'
        self.assertEqual(arithmetic_checks(proposed)[1]['status'], 'unavailable')
        self.assertEqual(arithmetic_checks(proposed)[0]['status'], 'matches')
        proposed[2]['kind'] = 'transaction'
        proposed[2]['fields']['date'] = '2020-13-01'
        self.assertEqual(arithmetic_checks(proposed)[1]['status'], 'unavailable')

    def test_corrected_and_excluded_rows_recalculate_without_mutating_original(self):
        proposal = dict(revision='a'*64, rows=rows(), currency='USD', metadata={}, page_numbers=[1])
        before = deepcopy(proposal)
        body = request(proposal)
        self.assertFalse(arithmetic_problems(check_statement_request(proposal, body)))
        body.rows[2] = body.rows[2].model_copy(update={'excluded': True})
        failed = check_statement_request(proposal, body)
        self.assertEqual({p['check'] for p in arithmetic_problems(failed)}, {'closing_balance','running_balance','credit_total'})
        body.rows[2] = body.rows[2].model_copy(update={'excluded': False})
        body.rows[2] = body.rows[2].model_copy(update={'amount_minor': '-'})
        self.assertEqual(check_statement_request(proposal, body)['balance_status'], 'unavailable')
        body.rows[2] = body.rows[2].model_copy(update={'amount_minor': '1000'})
        self.assertFalse(arithmetic_problems(check_statement_request(proposal, body)))
        self.assertEqual(proposal, before)

    def test_cannot_omit_source_rows_duplicate_them_or_supply_stale_reading(self):
        proposal = dict(revision='a'*64, rows=rows(), currency='USD', metadata={})
        body = request(proposal)
        for edits in (body.rows[:-1], body.rows + body.rows[:1]):
            with self.assertRaises(PdfMappingError):
                check_proposed_rows(proposal, [r.model_dump() for r in edits])
        body = body.model_copy(update={'expected_revision': 'b'*64})
        with self.assertRaises(PdfMappingError):
            check_statement_request(proposal, body)

    def test_total_label_does_not_discard_dated_payment_or_use_subtotal(self):
        data = source([['Date','Description','Credit'], ['2020-01-01','Total credits','10'],
                       ['', 'Subtotal credits', '10'], ['', 'Total credits', '10']])
        proposed = propose_table(data,'USD')['rows']
        self.assertFalse(proposed[1]['excluded'])
        self.assertFalse(proposed[2]['excluded'])
        self.assertTrue(proposed[3]['excluded'])
        self.assertEqual(proposed[3]['kind'], 'statement_total')
        # Duplicate totals may be page totals, not a full-statement control.
        self.assertEqual(arithmetic_checks(rows() + [rows()[-1]])[2]['status'], 'unavailable')

    def test_difference_explanation_is_bound_to_values_and_control_identity(self):
        proposal = dict(revision='a'*64, rows=rows(), currency='USD', metadata={})
        body = request(proposal).model_dump()
        body['rows'][2]['amount_minor'] = '900'
        checked = check_proposed_rows(proposal, body['rows'])
        exception = dict(balance_exception_reason='Printed statement has this difference.',
                         balance_exception_revision=checked['checks_revision'])
        self.assertTrue(accepted_difference(checked, exception))
        body['rows'][2]['amount_minor'] = '800'
        self.assertFalse(accepted_difference(check_proposed_rows(proposal, body['rows']), exception))
        # Renaming an excluded control cannot remove it from arithmetic checks.
        body['rows'][4]['description'] = 'Ignore this'
        self.assertEqual(check_proposed_rows(proposal, body['rows'])['checks'][0]['status'], 'difference')
