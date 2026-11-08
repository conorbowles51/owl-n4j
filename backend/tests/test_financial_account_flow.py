"""Whole-case account flow: the browser view's exact classification, computed where the rows are."""
import json
from uuid import uuid4

from services.financial.account_flow import account_flow, whole_case_account_flow
from services.financial.ledger_summary import LedgerSummaryError
from services.financial.ledger_transfers import TransferPairChoice
from tests import test_financial_network_tracing as _network


def _pairs(pairs):
    return [TransferPairChoice.model_validate(pair) for pair in pairs]


class AccountFlowView(_network.NetworkTracingTests):
    def scope(self):
        from services.financial.ledger_transfers import ledger_transfer_candidates
        export, request, rows = self.network()
        result = ledger_transfer_candidates(export, population='working', tolerance_days=3, whole_case=True)
        candidates = {(pair['debit_id'], pair['credit_id']) for pair in result['candidates']}
        return export, request, rows, result, candidates

    def test_transfers_into_and_out_of_the_selected_account_classify_and_reconcile(self):
        export, request, rows, result, candidates = self.scope()
        middle = str(rows[3].account_id)
        totals, movements, groups = account_flow(result['rows'], candidates, [middle], _pairs(request['pairs']))
        self.assertEqual([m['kind'] for m in movements], ['incoming', 'outgoing'])
        self.assertEqual([m['amount_minor'] for m in movements], ['10000', '6000'])
        self.assertEqual(totals, [dict(currency='GBP', incoming_minor='10000', outgoing_minor='6000',
                                       internal_minor='0', net_minor='4000', internal_count=0, movement_count=2)])
        self.assertEqual([ (g['credits_minor'], g['debits_minor'], g['net_minor']) for g in groups],
                         [('10000', '0', '10000'), ('0', '6000', '-6000')])
        self.assertTrue(all(g['label'] for g in groups))

    def test_an_internal_transfer_counts_once_and_stays_out_of_the_groups(self):
        export, request, rows, result, candidates = self.scope()
        first, middle = str(rows[0].account_id), str(rows[3].account_id)
        totals, movements, groups = account_flow(result['rows'], candidates, [first, middle], _pairs(request['pairs']))
        internal = [m for m in movements if m['kind'] == 'internal']
        self.assertEqual(len(internal), 1)
        self.assertEqual(internal[0]['label'], 'Within selected accounts')
        self.assertFalse(any(ids in g['transaction_ids'] for g in groups for ids in internal[0]['transaction_ids']))
        self.assertEqual(totals[0]['internal_minor'], '10000')
        self.assertEqual(totals[0]['internal_count'], 1)
        # Unpaired postings of the selected accounts appear once each, under their account.
        unpaired = [m for m in movements if len(m['transaction_ids']) == 1]
        self.assertEqual({m['transaction_ids'][0] for m in unpaired}, {str(rows[0].id), str(rows[1].id)})
        self.assertTrue(all('unpaired' in m['label'] for m in unpaired))
        # incoming - outgoing equals the selected accounts' own postings net.
        self.assertEqual(int(totals[0]['incoming_minor']) - int(totals[0]['outgoing_minor']),
                         10000 + 10000 - 6000)

    def test_bad_selections_are_refused_in_words(self):
        export, request, rows, result, candidates = self.scope()
        middle = str(rows[3].account_id)
        with self.assertRaisesRegex(LedgerSummaryError, 'distinct accounts in the captured scope'):
            account_flow(result['rows'], candidates, [middle, middle], _pairs(request['pairs']))
        with self.assertRaisesRegex(LedgerSummaryError, 'distinct accounts in the captured scope'):
            account_flow(result['rows'], candidates, [str(uuid4())], _pairs(request['pairs']))
        with self.assertRaisesRegex(LedgerSummaryError, 'Invalid or reused transfer pairing'):
            account_flow(result['rows'], candidates, [middle], _pairs(request['pairs'] * 2))
        unproposed = [dict(debit_id=str(rows[2].id), credit_id=str(rows[5].id))]
        with self.assertRaisesRegex(LedgerSummaryError, 'Invalid or reused transfer pairing'):
            account_flow(result['rows'], candidates, [middle], _pairs(unproposed))

    def test_a_view_that_does_not_reconcile_is_refused_not_returned(self):
        # A pair whose recorded credit amount differs from its debit breaks the reconciliation on the credit side.
        doctored = _pairs([dict(debit_id='00000000-0000-4000-8000-000000000001',
                                credit_id='00000000-0000-4000-8000-000000000002')])
        first, second = str(uuid4()), str(uuid4())
        keyed = [dict(key=str(doctored[0].debit_id), account_id=first, account_label='A', direction='debit',
                      currency='USD', amount_minor='100', counterparty_raw=None),
                 dict(key=str(doctored[0].credit_id), account_id=second, account_label='B', direction='credit',
                      currency='USD', amount_minor='60', counterparty_raw=None)]
        with self.assertRaisesRegex(LedgerSummaryError, 'does not reconcile'):
            account_flow(keyed, {(keyed[0]['key'], keyed[1]['key'])}, [second], doctored)

    def test_the_whole_case_flow_run_pages_movements_by_kind_with_true_counts(self):
        from services.financial.whole_case_runs import compute_flow
        export, request, rows, result, candidates = self.scope()
        middle = str(rows[3].account_id)
        params = dict(expected_snapshot_sha256=export.snapshot.sha256, population='working', tolerance_days=3,
                      start_date='2026-01-01', end_date='2026-01-31', account_ids=[middle], pairs=request['pairs'])
        summary, sections = compute_flow(export, {**params, 'case_id': str(self.case.id), 'run_id': 'x' * 32}, None)
        self.assertEqual(summary['movements'], 2)
        self.assertEqual(summary['groups'], 2)
        self.assertEqual(summary['selected_accounts'][0]['account_id'], middle)
        self.assertEqual(summary['totals'][0]['net_minor'], '4000')
        kinds = [subset for _, subset, _ in sections['movements']]
        self.assertEqual(kinds, ['incoming', 'outgoing'])
        for group, _, words in sections['groups']:
            self.assertIn(group['label'], ' '.join(str(word) for word in words))
        with self.assertRaisesRegex(LedgerSummaryError, 'Captured ledger or date scope changed'):
            whole_case_account_flow(export, {**params, 'expected_snapshot_sha256': '0' * 64})

    def test_group_identity_matches_the_browser_views_json_identity(self):
        export, request, rows, result, candidates = self.scope()
        middle = str(rows[3].account_id)
        _, movements, groups = account_flow(result['rows'], candidates, [middle], _pairs(request['pairs']))
        for group in groups:
            parsed = json.loads(group['id'])
            self.assertEqual(parsed[1], group['currency'])
            self.assertTrue(parsed[0].startswith('account:'))
