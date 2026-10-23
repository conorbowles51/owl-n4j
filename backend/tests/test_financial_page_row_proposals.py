import os
import unittest
from unittest import mock

from services.financial import page_row_proposals as prp


def _cell(text, x):
    return dict(column_index=x, expected_text=text,
                locator=dict(kind='page_rectangle', page=1, rect=[x * 1000, 0, x * 1000 + 900, 900]))


def _row(row_id, page, kind, texts, *, excluded=True, fields=None):
    return dict(id=row_id, page_number=page, table_index=0, row_index=int(row_id.split(':')[-1]),
                source_cells=[_cell(t, i) for i, t in enumerate(texts)], fields=fields or {}, issues=[],
                excluded=excluded, kind=kind)


def _proposal(rows, convention='asset_balance'):
    return dict(revision='r' * 64, statement_id=None, currency='USD', page_numbers=[1, 2], statement_page_numbers=[1, 2],
                metadata=dict(holder='A Holder', account_number='1234', institution='Bank', period_start='2024-03-01',
                              period_end='2024-03-31', balance_convention=convention),
                rows=rows)


def _opening(value):
    return _row('1:0:0', 1, 'balance', ['Opening balance', value], fields=dict(description='Opening Balance',
                                                                                balance=value.replace('.', '').replace(',', '')))


def _closing(value, page=2):
    return _row(f'{page}:0:9', page, 'balance', ['Closing balance', value],
                fields=dict(description='Closing Balance', balance=value.replace('.', '').replace(',', '')))


def _statement(lines_page1, lines_page2, closing='1,050.00'):
    rows = [_opening('1,000.00')]
    rows += [_row(f'1:0:{i + 1}', 1, 'header', t) for i, t in enumerate(lines_page1)]
    rows += [_row(f'2:0:{i + 1}', 2, 'header', t) for i, t in enumerate(lines_page2)]
    rows.append(_closing(closing))
    return _proposal(rows)


class _On(unittest.TestCase):
    def setUp(self):
        switch = mock.patch.dict(os.environ, {'LOUPE_FINANCIAL_PAGE_ROW_PROPOSALS': '1'})
        switch.start()
        self.addCleanup(switch.stop)


class LineDateTests(unittest.TestCase):
    def test_reads_a_leading_date_inside_the_period(self):
        self.assertEqual(prp.read_line_date('15/03 Grocery', '2024-03-01', '2024-03-31'), '2024-03-15')
        # 03/04 is 3 April or 4 March, both near a March period: nothing is chosen.
        self.assertIsNone(prp.read_line_date('03/04 Grocery', '2024-03-01', '2024-03-31'))
        self.assertEqual(prp.read_line_date('24ABR | Transfer', '2024-04-01', '2024-04-30'), '2024-04-24')
        self.assertEqual(prp.read_line_date('05 ENE 2024', '2024-01-01', '2024-01-31'), '2024-01-05')

    def test_an_ambiguous_order_near_the_period_proposes_nothing(self):
        # 08-05 is 8 May day-first and 5 Aug month-first; a period in April must not choose either.
        self.assertIsNone(prp.read_line_date('08-05 Payment', '2026-04-01', '2026-04-30'))
        self.assertEqual(prp.read_line_date('08-05 Payment', '2020-07-17', '2020-08-16'), '2020-08-05')

    def test_damaged_dates_propose_nothing(self):
        for text in ('O2.EE.2022', '416', '4l9', 'Total', ''):
            self.assertIsNone(prp.read_line_date(text, '2024-03-01', '2024-03-31'))


class PageProposalTests(_On):
    def test_a_page_that_chains_is_confirmable_and_cites_every_value(self):
        proposal = _statement([['03/05', 'Deposit', '100.00', '1,100.00']], [['20/03', 'Card', '50.00', '1,050.00']])
        result = prp.page_proposals(proposal)
        self.assertEqual([p['confirmable'] for p in result['pages']], [True, True])
        line = result['pages'][0]['lines'][0]
        self.assertEqual(line['direction'], 'credit')
        self.assertEqual(line['values']['amount']['value'], 10000)
        self.assertEqual(line['values']['date']['value'], '2024-03-05')
        for name in ('date', 'amount', 'balance_after'):
            self.assertEqual(line['values'][name]['cell']['kind'], 'page_rectangle')
        self.assertEqual(result['pages'][1]['lines'][0]['direction'], 'debit')

    def test_a_line_that_breaks_the_chain_is_shown_on_its_own(self):
        # The second line's printed balance is 5.00 off: neither page closes on the printed figures.
        proposal = _statement([['03/05', 'Deposit', '100.00', '1,100.00']], [['20/03', 'Card', '50.00', '1,055.00']])
        result = prp.page_proposals(proposal)
        self.assertFalse(result['pages'][1]['confirmable'])
        self.assertEqual(result['pages'][1]['reason'], 'chain_broken')
        # Page 1's leaving balance is not confirmed by the next printed step either.
        self.assertFalse(result['pages'][0]['confirmable'])
        self.assertEqual(result['pages'][0]['reason'], 'page_end_unconfirmed')

    def test_the_last_page_must_close_on_the_printed_closing(self):
        proposal = _statement([['03/05', 'Deposit', '100.00', '1,100.00']], [['20/03', 'Card', '50.00', '1,050.00']],
                              closing='1,040.00')
        result = prp.page_proposals(proposal)
        self.assertFalse(result['pages'][1]['confirmable'])
        self.assertEqual(result['pages'][1]['reason'], 'page_end_unconfirmed')

    def test_a_line_without_a_readable_field_needs_its_own_edit(self):
        # The deposit's amount is doubtful: the line is shown incomplete, and the card line after it must not be
        # proved by the balance that skips it (1,000.00 -> 1,050.00 would read as a 50.00 credit).
        proposal = _statement([['03/05', 'Deposit', '100.00?', '1,100.00']], [['20/03', 'Card', '50.00', '1,050.00']])
        result = prp.page_proposals(proposal)
        self.assertFalse(any(p['confirmable'] for p in result['pages']))
        self.assertEqual(result['pages'][0]['lines'][0]['missing'], ['amount', 'balance_after'])

    def test_a_damaged_line_with_no_date_blocks_the_statement(self):
        # Same coincidence with the date unreadable: the line is not proposed, so it must block confirmation.
        proposal = _statement([['O3.0S', 'Deposit', '100.00', '1,100.00']], [['20/03', 'Card', '50.00', '1,050.00']])
        result = prp.page_proposals(proposal)
        self.assertEqual(result['unaccounted_lines'], 1)
        self.assertEqual([p['reason'] for p in result['pages']], ['unread_money_line'])

    def test_no_opening_means_no_confirmation(self):
        proposal = _statement([['03/05', 'Deposit', '100.00', '1,100.00']], [])
        proposal['rows'] = proposal['rows'][1:]
        result = prp.page_proposals(proposal)
        self.assertEqual(result['pages'][0]['reason'], 'opening_not_read')

    def test_a_printed_total_must_agree(self):
        proposal = _statement([['03/05', 'Deposit', '100.00', '1,100.00']], [['20/03', 'Card', '50.00', '1,050.00']])
        proposal['rows'].insert(1, _row('1:0:8', 1, 'statement_total', ['Total deposits', '90.00'],
                                        fields=dict(balance='9000', total_direction='credit')))
        result = prp.page_proposals(proposal)
        self.assertEqual(result['totals'], 'disagree')
        self.assertFalse(any(p['confirmable'] for p in result['pages']))
        proposal['rows'][1]['fields']['balance'] = '10000'
        self.assertTrue(all(p['confirmable'] for p in prp.page_proposals(proposal)['pages']))

    def test_lines_without_a_date_are_not_proposed_from_set_aside_rows(self):
        proposal = _statement([['Deposits', '100.00', '1,100.00']], [])
        result = prp.page_proposals(proposal)
        self.assertEqual(result['pages'], [])
        self.assertEqual(result['unaccounted_lines'], 1)

    def test_owed_balances_take_the_direction_the_other_way(self):
        rows = [_opening('1,000.00'), _row('1:0:1', 1, 'header', ['03/05', 'Purchase', '100.00', '1,100.00']),
                _closing('1,100.00', page=1)]
        result = prp.page_proposals(_proposal(rows, convention='liability_owed'))
        self.assertEqual(result['pages'][0]['lines'][0]['direction'], 'debit')
        self.assertTrue(result['pages'][0]['confirmable'])

    def test_switch_off_offers_nothing(self):
        proposal = _statement([['03/05', 'Deposit', '100.00', '1,100.00']], [['20/03', 'Card', '50.00', '1,050.00']])
        for value in ('0', ''):
            with mock.patch.dict(os.environ, {'LOUPE_FINANCIAL_PAGE_ROW_PROPOSALS': value}):
                self.assertEqual(prp.page_proposals(proposal)['pages'], [])
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(prp.enabled())


class ApplyPageTests(_On):
    def setUp(self):
        super().setUp()
        from services.financial.import_batches import initial_request
        self.proposal = _statement([['03/05', 'Deposit', '100.00', '1,100.00']], [['20/03', 'Card', '50.00', '1,050.00']])
        self.request = initial_request(self.proposal)

    def test_apply_enters_the_lines_and_keeps_the_reading(self):
        page = prp.page_proposals(self.proposal, self.request)['pages'][0]
        before = [dict(r) for r in self.proposal['rows']]
        edited = prp.apply_page(self.proposal, self.request, 1, page['digest'])
        row = next(r for r in edited['rows'] if r['id'] == '1:0:1')
        self.assertEqual((row['excluded'], row['date'], row['amount_minor'], row['direction'], row['balance_minor']),
                         (False, '2024-03-05', '10000', 'credit', '110000'))
        self.assertEqual(row['description'], 'Deposit')
        # The machine reading is untouched; the other page is not entered.
        self.assertEqual(self.proposal['rows'], before)
        self.assertTrue(next(r for r in edited['rows'] if r['id'] == '2:0:1')['excluded'])
        # The original request is not modified in place.
        self.assertTrue(next(r for r in self.request['rows'] if r['id'] == '1:0:1')['excluded'])

    def test_apply_refuses_a_changed_proposal_or_an_unconfirmable_page(self):
        with self.assertRaises(ValueError):
            prp.apply_page(self.proposal, self.request, 1, '0' * 64)
        with self.assertRaises(ValueError):
            prp.apply_page(self.proposal, self.request, 7, '0' * 64)

    def test_a_line_already_edited_by_a_person_is_not_proposed_again(self):
        page = prp.page_proposals(self.proposal, self.request)['pages'][0]
        edited = prp.apply_page(self.proposal, self.request, 1, page['digest'])
        again = prp.page_proposals(self.proposal, edited)
        self.assertEqual([p['page_number'] for p in again['pages']], [2])
        self.assertTrue(again['pages'][0]['confirmable'])

    def test_the_confirmed_request_reconciles_under_the_import_check(self):
        from services.financial import import_batches
        request = self.request
        for page in prp.page_proposals(self.proposal, request)['pages']:
            request = prp.apply_page(self.proposal, request, page['page_number'], page['digest'])
        included = [r for r in request['rows'] if not r['excluded']]
        self.assertEqual(len(included), 2)
        total = 100000 + sum(int(r['amount_minor']) * (1 if r['direction'] == 'credit' else -1) for r in included)
        self.assertEqual(total, 105000)
        self.assertTrue(hasattr(import_batches, 'save_review'))


class HarnessSimulationTests(_On):
    """The benchmark counts a page the product lets a person confirm as one action, and only then."""

    def _simulate(self, truth_rows):
        from benchmarks.statement_automation import harness
        from services.financial.import_batches import initial_request
        proposal = _statement([['03/05', 'Deposit', '100.00', '1,100.00']], [['20/03', 'Card', '50.00', '1,050.00']])
        truth = dict(currency='USD', holder='A Holder', holder_printed=True, account='1234', account_printed=True,
                     institution='Bank', period_end='2024-03-31', period_start='2024-03-01', start_printed=True,
                     opening_minor=100000, closing_minor=105000, added_in='real', rows=truth_rows)
        return harness.simulate_correction(proposal, truth, lambda p, raw: ('attention', dict(can_import=False, problems=[])),
                                           initial_request)

    rows = [dict(date='2024-03-05', amount_minor=10000, direction='credit', description='Deposit'),
            dict(date='2024-03-20', amount_minor=5000, direction='debit', description='Card')]

    def test_each_confirmable_page_is_one_action(self):
        result = self._simulate(self.rows)
        self.assertEqual([(a['kind'], a['field']) for a in result['actions']],
                         [('decision', 'confirm_page'), ('decision', 'confirm_page')])
        self.assertEqual((result['missing_rows'], result['pages_confirmed'], result['page_rows_confirmed']), (0, 2, 2))

    def test_a_page_unlike_the_printed_lines_is_refused_and_typed(self):
        rows = [self.rows[0], dict(self.rows[1], amount_minor=4000)]
        result = self._simulate(rows)
        self.assertEqual(result['page_proposals_refused'], 1)
        self.assertEqual([(a['kind'], a['field']) for a in result['actions']],
                         [('decision', 'confirm_page'), ('add_row', 'missing_row')])

    def test_switch_off_counts_rows_to_add_as_before(self):
        with mock.patch.dict(os.environ, {'LOUPE_FINANCIAL_PAGE_ROW_PROPOSALS': '0'}):
            result = self._simulate(self.rows)
        self.assertEqual([a['kind'] for a in result['actions']], ['add_row', 'add_row'])
        self.assertEqual(result['pages_confirmed'], 0)


if __name__ == '__main__':
    unittest.main()
