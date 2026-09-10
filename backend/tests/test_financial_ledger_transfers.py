import hashlib
import json
from unittest.mock import patch
from services.financial.ledger_snapshot import LedgerExport, LedgerSnapshot, capture_ledger_snapshot, _capture_history
from services.financial.ledger_transfers import ledger_transfer_candidates, evaluate_transfer_scenario
from services.financial.ledger_summary import LedgerSummaryError
from postgres.models.enums import TransactionDirection, LedgerStatus
from tests.test_financial_ledger_summary import LedgerSummaryTests

class LedgerTransferTests(LedgerSummaryTests):
    def capture(self):
        snap = capture_ledger_snapshot(self.db, case_id=self.case.id)
        doc = _capture_history(self.db, json.loads(snap.content), case_id=self.case.id)
        content = json.dumps(doc, sort_keys=True, separators=(',', ':'))
        return LedgerExport(LedgerSnapshot(content, hashlib.sha256(content.encode()).hexdigest(), len(content.encode())), '{}')
    def pair(self):
        account = self._account(self.case.id, identity_key='second-account'); self.db.add(account); self.db.commit()
        debit, _ = self.add(9007199254740993, TransactionDirection.debit)
        doc = self.make_document(); period = self.make_period(doc, account=account)
        credit = self.add_row(period, doc, amount=9007199254740993, account=account)
        debit.proof_class = credit.proof_class = 'p3'; self.db.commit()
        return debit, credit
    def request(self, captured, debit, credit):
        return dict(expected_snapshot_sha256=captured.snapshot.sha256, population='working', tolerance_days=3,
            pairs=[dict(debit_id=str(debit.id), credit_id=str(credit.id))], basis='Synthetic proposed transfer test')
    def test_pair_sources_exact_money_and_single_count_scenario(self):
        debit, credit = self.pair(); export = self.capture()
        found = ledger_transfer_candidates(export)
        self.assertEqual(len(found['candidates']), 1)
        self.assertEqual(found['candidates'][0]['amount_minor'], '9007199254740993')
        self.assertEqual(ledger_transfer_candidates(export, population='verified')['candidates'], [])
        scenario = evaluate_transfer_scenario(export, self.request(export, debit, credit))
        figure = scenario['figures'][0]
        self.assertEqual(figure['movement_count'], 1)
        self.assertEqual(figure['movement_volume_minor'], '9007199254740993')
        self.assertEqual(figure['unpaired_credits_minor'], '0')
        self.assertEqual(figure['unpaired_debits_minor'], '0')
        self.assertFalse(json.loads(scenario['scenario_json'])['pairings_verified'])
        self.assertEqual(self.working_reading_count(), 2)
    def working_reading_count(self):
        from services.financial.working_totals import working_ledger_summary
        return working_ledger_summary(self.db, case_id=self.case.id)['included_rows']
    def test_stale_reused_and_unknown_pair_refused(self):
        debit, credit = self.pair(); export = self.capture(); request = self.request(export, debit, credit)
        for change in [dict(expected_snapshot_sha256='0'*64), dict(pairs=request['pairs']*2), dict(basis=' '), dict(pairs=[dict(debit_id=str(credit.id), credit_id=str(debit.id))])]:
            with self.assertRaises(LedgerSummaryError): evaluate_transfer_scenario(export, {**request, **change})
        credit.ledger_status = LedgerStatus.rejected; self.db.commit()
        with self.assertRaises(LedgerSummaryError): evaluate_transfer_scenario(self.capture(), request)
    def test_ambiguous_candidates_remain_explicit_and_bounds_are_not_partial(self):
        debit, credit = self.pair()
        account = self._account(self.case.id, identity_key='third-account'); self.db.add(account); self.db.commit()
        doc = self.make_document(); period = self.make_period(doc, account=account)
        self.add_row(period, doc, amount=9007199254740993, account=account)
        export = self.capture(); result = ledger_transfer_candidates(export)
        self.assertEqual(len(result['candidates']), 2)
        self.assertTrue(all(p['outcome']=='ambiguous' for p in result['candidates']))
        with patch('services.financial.ledger_transfers.MAX_TRANSFER_ROWS', 1):
            with self.assertRaises(LedgerSummaryError): ledger_transfer_candidates(export)
    def test_statement_end_ordering_is_not_a_transaction_date_match(self):
        debit, credit = self.pair()
        debit.provenance = {'date_basis': 'statement_end_ordering_only'}; self.db.commit()
        result = ledger_transfer_candidates(self.capture())
        self.assertEqual(result['candidates'], [])
        self.assertEqual(result['date_unavailable_ids'], [str(debit.id)])
