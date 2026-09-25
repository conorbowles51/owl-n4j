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
    def test_calculation_keeps_one_minor_unit_above_javascript_safe_integer(self):
        proposed = rows()
        opening = 9007199254740993
        proposed[1]['fields']['balance'] = str(opening)
        proposed[2]['fields']['balance'] = str(opening + 1000)
        proposed[3]['fields']['balance'] = str(opening + 3000)
        proposed[4]['fields']['balance'] = str(opening + 3001)
        closing = arithmetic_checks(proposed)[0]
        self.assertEqual(closing['opening_minor'], str(opening))
        self.assertEqual(closing['credit_minor'], '3000')
        self.assertEqual(closing['debit_minor'], '0')
        self.assertEqual(closing['expected_minor'], str(opening + 3000))
        self.assertEqual(closing['difference_minor'], '-1')

    def test_card_calculation_uses_amount_owed_without_reversing_displayed_totals(self):
        proposed = rows()
        proposed[1]['fields']['balance'] = '10000'
        proposed[2]['fields']['balance'] = '9000'
        proposed[3]['fields'].update(direction='debit', balance='11000')
        proposed[4]['fields']['balance'] = '11000'
        closing = arithmetic_checks(proposed, liability=True)[0]
        self.assertEqual(closing['balance_convention'], 'liability_owed')
        self.assertEqual((closing['credit_minor'], closing['debit_minor']), ('1000', '2000'))
        self.assertEqual((closing['expected_minor'], closing['difference_minor']), ('11000', '0'))

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

class ManualSourcePlacementTests(unittest.TestCase):
    def proposal_and_edits(self):
        proposed = rows()
        for index in (3, 4, 5):
            proposed[index]['fields']['balance'] = '3500'
        proposal = dict(revision='a'*64, rows=proposed, currency='USD', metadata={}, page_numbers=[1])
        edits = [row.model_dump() for row in request(proposal).rows]
        edits.append(dict(id='manual:missing', excluded=False, manual_page=1, date='2020-01-03',
            description='Missed source payment', amount_minor='500', direction='credit', balance_minor=None))
        return proposal, edits

    def test_declared_position_checks_interval_and_does_not_mutate_evidence(self):
        proposal, edits = self.proposal_and_edits()
        original = deepcopy(proposal)
        before = check_proposed_rows(proposal, edits)
        self.assertEqual(before['checks'][0]['status'], 'matches')
        self.assertEqual(before['checks'][1]['status'], 'unavailable')
        self.assertEqual(before['checks'][1]['unplaced_row_ids'], ['manual:missing'])
        edits[-1]['source_order_anchor'] = dict(relation='before', row_id=proposal['rows'][3]['id'])
        after = check_proposed_rows(proposal, edits)
        self.assertEqual(after['checks'][1]['status'], 'matches')
        self.assertEqual(after['checks'][1]['compared_intervals'], 2)
        self.assertNotEqual(before['checks_revision'], after['checks_revision'])
        self.assertEqual(proposal, original)

    def test_unplaced_manual_does_not_disable_an_unrelated_bad_interval(self):
        proposed = rows()
        proposed[3]['page_number'] = 2
        proposed.insert(4, dict(id='printed:third', kind='transaction', excluded=False, page_number=3,
            fields=dict(date='2020-01-04', description='Third', direction='credit', amount_minor='100', balance='3300')))
        proposed.append(dict(id='manual:page-one', kind='manual_entry', excluded=False, page_number=1,
            fields=dict(date='2020-01-02', direction='credit', description='Missed', amount_minor='500')))
        running = arithmetic_checks(proposed)[1]
        self.assertEqual(running['status'], 'difference')
        self.assertEqual(running['compared_intervals'], 1)
        self.assertEqual(len(running['unavailable_intervals']), 2)
        self.assertEqual(running['findings'][0]['row_id'], 'printed:third')
        self.assertEqual(running['findings'][0]['difference_minor'], '-200')

    def test_anchor_cannot_reorder_source_or_cross_page_period_or_manual_rows(self):
        proposal, edits = self.proposal_and_edits()
        for anchor in ('another-period:row', 'manual:other', proposal['rows'][1]['id']):
            with self.subTest(anchor=anchor), self.assertRaises(PdfMappingError):
                changed = deepcopy(edits)
                changed[-1]['source_order_anchor'] = dict(relation='after', row_id=anchor)
                check_proposed_rows(proposal, changed)
        proposal['rows'][3]['page_number'] = 2
        edits[-1]['source_order_anchor'] = dict(relation='before', row_id=proposal['rows'][3]['id'])
        with self.assertRaises(PdfMappingError):
            check_proposed_rows(proposal, edits)
        edits[-1].pop('source_order_anchor')
        edits[2]['source_order_anchor'] = dict(relation='before', row_id=proposal['rows'][3]['id'])
        with self.assertRaises(PdfMappingError):
            check_proposed_rows(proposal, edits)

    def test_multiple_added_payments_keep_declared_order_and_reverse_source_is_supported(self):
        from services.financial.manual_row_placement import place_manual_rows
        proposal, edits = self.proposal_and_edits()
        first_id, second_id = proposal['rows'][2]['id'], proposal['rows'][3]['id']
        anchor = dict(relation='after', row_id=first_id)
        added = [dict(id='manual:'+str(number), kind='manual_entry', excluded=False, page_number=1,
            fields=dict(source_order_anchor=anchor)) for number in (1, 2)]
        placed = place_manual_rows(proposal['rows'] + added, {row['id']: row for row in proposal['rows']})
        ids = [row['id'] for row in placed]
        start = ids.index(first_id)
        self.assertEqual(ids[start:start+4], [first_id, 'manual:1', 'manual:2', second_id])
        proposal['rows'][2:4] = reversed(proposal['rows'][2:4])
        # After the newer printed row is before that row in chronological order.
        edits[-1]['source_order_anchor'] = dict(relation='after', row_id=second_id)
        result = check_proposed_rows(proposal, edits)
        self.assertEqual(result['checks'][1]['order'], 'reverse_source_order')
        self.assertEqual(result['checks'][1]['status'], 'matches')

    def test_unplaced_with_running_controls_is_an_actionable_admission_blocker(self):
        from services.financial.statement_import import StatementImportRequest
        from services.financial.statement_admission import assess_admission
        proposal, edits = self.proposal_and_edits()
        raw = dict(expected_revision=proposal['revision'], currency='USD', holder='Synthetic Holder',
            account_number='000123', institution='Synthetic Bank', period_start='2020-01-01', period_end='2020-01-31', rows=edits)
        before = assess_admission(proposal, StatementImportRequest.model_validate(raw))
        blocker = next(item for item in before['blockers'] if item['kind'] == 'manual_placement')
        self.assertEqual(blocker['target']['field'], 'source_order_anchor')
        self.assertEqual(blocker['target']['row_id'], 'manual:missing')
        raw['rows'][-1]['source_order_anchor'] = dict(relation='before', row_id=proposal['rows'][3]['id'])
        after = assess_admission(proposal, StatementImportRequest.model_validate(raw))
        self.assertTrue(after['can_import'], after['blockers'])

    def test_liability_uses_declared_position_with_exact_minor_unit_math(self):
        proposal, edits = self.proposal_and_edits()
        proposal['metadata']['balance_convention'] = 'liability_owed'
        for original, edit in zip(proposal['rows'], edits):
            if not original['excluded']:
                original['fields']['direction'] = 'debit'
                edit['direction'] = 'debit'
        # This credit total is a synthetic debit total for a card liability.
        proposal['rows'][5]['fields']['total_direction'] = 'debit'
        edits[-1]['direction'] = 'debit'
        edits[-1]['source_order_anchor'] = dict(relation='before', row_id=proposal['rows'][3]['id'])
        result = check_proposed_rows(proposal, edits)
        self.assertEqual(result['checks'][0]['status'], 'matches')
        self.assertEqual(result['checks'][0]['expected_minor'], '3500')
        self.assertEqual(result['checks'][1]['status'], 'matches')

    def empty_page_proposal(self, reverse=False):
        proposal, edits = self.proposal_and_edits()
        proposal['page_numbers'] = [1, 2, 3, 4]
        proposal['statement_page_numbers'] = [1, 2, 3]
        proposal['rows'][2]['page_number'] = 3 if reverse else 1
        proposal['rows'][3]['page_number'] = 1 if reverse else 3
        proposal['rows'][1]['page_number'] = 3 if reverse else 1
        for row in proposal['rows'][4:]:
            row['page_number'] = 1 if reverse else 3
        if reverse:
            proposal['rows'][2:4] = reversed(proposal['rows'][2:4])
        edits[-1]['manual_page'] = 2
        return proposal, edits

    def test_explicit_empty_page_boundaries_reconcile_in_forward_and_reverse_order(self):
        from services.financial.statement_import import StatementImportRequest
        from services.financial.statement_admission import assess_admission
        for reverse in (False, True):
            for relation, index in (('after', 2), ('before', 3)):
                with self.subTest(reverse=reverse, relation=relation):
                    proposal, edits = self.empty_page_proposal(reverse)
                    edits[-1]['source_order_anchor'] = dict(relation=relation, row_id=proposal['rows'][index]['id'])
                    checked = check_proposed_rows(proposal, edits)
                    self.assertEqual(checked['checks'][1]['status'], 'matches')
                    self.assertEqual(checked['checks'][1]['order'], 'reverse_source_order' if reverse else 'source_order')
                    self.assertEqual(checked['checks'][1]['compared_intervals'], 2)
                    raw = dict(expected_revision=proposal['revision'], currency='USD', holder='Synthetic Holder',
                        account_number='000123', institution='Synthetic Bank', period_start='2020-01-01',
                        period_end='2020-01-31', rows=edits)
                    admission = assess_admission(proposal, StatementImportRequest.model_validate(raw))
                    self.assertTrue(admission['can_import'], admission['blockers'])
                    self.assertEqual(edits[-1]['manual_page'], 2)

    def test_empty_page_boundary_rejects_wrong_side_other_period_and_newly_read_page(self):
        proposal, edits = self.empty_page_proposal()
        for relation, index in (('before', 2), ('after', 3)):
            with self.subTest(relation=relation), self.assertRaises(PdfMappingError):
                edits[-1]['source_order_anchor'] = dict(relation=relation, row_id=proposal['rows'][index]['id'])
                check_proposed_rows(proposal, edits)
        edits[-1]['source_order_anchor'] = dict(relation='after', row_id=proposal['rows'][2]['id'])
        edits[-1]['manual_page'] = 4  # In this PDF, outside this statement period.
        with self.assertRaises(PdfMappingError):
            check_proposed_rows(proposal, edits)
        edits[-1]['manual_page'] = 2
        proposal['rows'][3]['page_number'] = 2  # A fresh reading now offers a local anchor.
        with self.assertRaises(PdfMappingError):
            check_proposed_rows(proposal, edits)

    def test_empty_page_anchor_is_nearest_boundary_and_preserves_page_then_entry_order(self):
        from services.financial.manual_row_placement import allowed_source_positions, place_manual_rows
        original = [dict(id=id, kind='transaction', page_number=page, fields={})
                    for id, page in [('first', 1), ('last', 1), ('next', 4), ('later', 4)]]
        originals = {row['id']: row for row in original}
        self.assertEqual(allowed_source_positions(originals, 2, [1, 2, 3, 4]),
                         {('after', 'last'), ('before', 'next')})
        entries = [dict(id=id, kind='manual_entry', page_number=page,
                       fields=dict(source_order_anchor=dict(relation='after', row_id='last')))
                   for id, page in [('manual:page3', 3), ('manual:page2-a', 2), ('manual:page2-b', 2)]]
        ordered = place_manual_rows(original + entries, originals, statement_pages=[1, 2, 3, 4])
        self.assertEqual([row['id'] for row in ordered],
                         ['first', 'last', 'manual:page2-a', 'manual:page2-b', 'manual:page3', 'next', 'later'])
