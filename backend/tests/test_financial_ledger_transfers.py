import hashlib
import json
from unittest.mock import patch
from services.financial.ledger_snapshot import LedgerExport, LedgerSnapshot, capture_ledger_snapshot, _capture_history
from services.financial.ledger_transfers import ledger_transfer_candidates, evaluate_transfer_scenario
from services.financial.ledger_summary import LedgerSummaryError
from postgres.models.enums import TransactionDirection, LedgerStatus
from tests import test_financial_ledger_summary as _test_financial_ledger_summary

class LedgerTransferTests(_test_financial_ledger_summary.LedgerSummaryTests):
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

    def test_reference_match_outside_date_window_retains_exact_scenario(self):
        from datetime import timedelta
        debit, credit = self.pair()
        debit.bank_reference = '28A7C567-7115-4462-958A-E6DB7E3A9552'
        credit.bank_reference = debit.bank_reference.lower()
        credit.transaction_date += timedelta(days=20)
        credit.ordering_date += timedelta(days=20)
        credit.posted_date = credit.value_date = credit.effective_date = None
        self.db.commit()
        export = self.capture(); result = ledger_transfer_candidates(export, tolerance_days=0)
        pair = result['candidates'][0]
        self.assertEqual(pair['match_basis'], 'exact_reference')
        self.assertEqual(len(result['reference_evidence']), 1)
        scenario = evaluate_transfer_scenario(export, {**self.request(export,debit,credit), 'tolerance_days':0})
        self.assertEqual(json.loads(scenario['scenario_json'])['selected_pairs'][0]['reference']['value'], credit.bank_reference)

    def test_identifier_amount_conflict_is_visible_but_not_selectable(self):
        debit, credit = self.pair()
        debit.bank_reference = credit.bank_reference = '28a7c567-7115-4462-958a-e6db7e3a9552'
        credit.amount_minor += 1; self.db.commit()
        result = ledger_transfer_candidates(self.capture())
        self.assertEqual(result['candidates'], [])
        self.assertFalse(result['reference_evidence'][0]['amounts_agree'])
        self.assertIn('amounts or currencies differ',result['reference_evidence'][0]['reason'])

    def test_unscoped_and_nil_identifiers_are_not_promoted(self):
        debit, credit = self.pair()
        for value in ('123456789012345', '1001', '00000000-0000-0000-0000-000000000000'):
            debit.bank_reference = credit.bank_reference = value; self.db.commit()
            result = ledger_transfer_candidates(self.capture())
            self.assertEqual(result['reference_evidence'], [])
            self.assertEqual(len(result['unscoped_reference_ids']),2)
            self.assertEqual(result['candidates'][0]['match_basis'],'amount_date')

    def test_ach_requires_native_parser_and_same_explicit_effective_date(self):
        from datetime import date
        from postgres.models.financial import FinancialSourceDocument
        debit, credit = self.pair()
        debit.bank_reference = credit.bank_reference = '123456780000123'
        for row in (debit, credit):
            self.db.get(FinancialSourceDocument,row.source_document_id).parser_name = 'loupe.nacha'
            row.effective_date = date(2026,1,1)
        self.db.commit()
        result=ledger_transfer_candidates(self.capture())
        self.assertEqual(result['reference_evidence'][0]['reference']['scope_key'],'12345678:2026-01-01')
        credit.effective_date = date(2026,1,2); self.db.commit()
        self.assertEqual(ledger_transfer_candidates(self.capture())['reference_evidence'],[])
        credit.effective_date = None; self.db.commit()
        result=ledger_transfer_candidates(self.capture())
        self.assertEqual(result['reference_evidence'],[])
        self.assertIn(str(credit.id), result['unscoped_reference_ids'])

    def test_reference_candidates_preserve_multiple_partners_and_limits(self):
        debit, credit = self.pair()
        account = self._account(self.case.id, identity_key='reference-third'); self.db.add(account); self.db.commit()
        doc=self.make_document(); period=self.make_period(doc,account=account)
        other=self.add_row(period,doc,amount=credit.amount_minor,account=account)
        for row in (debit,credit,other): row.bank_reference='28a7c567-7115-4462-958a-e6db7e3a9552'
        self.db.commit()
        result=ledger_transfer_candidates(self.capture())
        self.assertTrue(all(p['outcome']=='ambiguous' for p in result['candidates']))
        self.assertTrue(any(p['relation']=='conflict' for p in result['reference_evidence']))
        with patch('services.financial.ledger_transfers.MAX_TRANSFER_PAIRS',1):
            with self.assertRaises(LedgerSummaryError): ledger_transfer_candidates(self.capture())

    def test_a_pair_beyond_the_tolerance_is_listed_graded_and_never_selectable(self):
        """Neil 2026-11-04: no cutoff hides a match. A pair 15 days apart is beyond every tolerance the workbench
        offers (0 to 7 days); it is listed in ``graded`` as weak with its reasons, and a scenario cannot select it."""
        from datetime import timedelta
        debit, credit = self.pair()
        credit.transaction_date += timedelta(days=15)
        credit.ordering_date += timedelta(days=15)
        credit.posted_date = credit.value_date = credit.effective_date = None
        self.db.commit()
        export = self.capture(); result = ledger_transfer_candidates(export, tolerance_days=7)
        self.assertEqual(result['candidates'], [])
        graded = result['graded']
        self.assertEqual(len(graded['pairs']), 1)
        p = graded['pairs'][0]
        self.assertEqual((p['debit_id'], p['credit_id'], p['gap_days'], p['level']), (str(debit.id), str(credit.id), 15, 'weak'))
        self.assertFalse(p['within_tolerance'])
        self.assertIn('15 days apart', p['reasons']['match'])
        self.assertEqual(graded['by_level'], {'strong': 0, 'moderate': 0, 'weak': 1, 'faint': 0})
        with self.assertRaises(LedgerSummaryError):
            evaluate_transfer_scenario(export, {**self.request(export, debit, credit), 'tolerance_days': 7})

    def test_graded_list_holds_the_selectable_pair_too(self):
        debit, credit = self.pair(); result = ledger_transfer_candidates(self.capture())
        self.assertEqual(len(result['candidates']), 1)
        self.assertEqual([(p['debit_id'], p['credit_id'], p['within_tolerance']) for p in result['graded']['pairs']],
                         [(str(debit.id), str(credit.id), True)])
