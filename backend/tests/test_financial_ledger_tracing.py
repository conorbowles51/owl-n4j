import hashlib
import json
from datetime import date
from unittest.mock import patch
from pydantic import ValidationError
from services.financial.ledger_snapshot import LedgerExport, LedgerSnapshot, capture_ledger_snapshot, _capture_history
from services.financial.ledger_tracing import LedgerTraceInput, ledger_trace_inputs, evaluate_ledger_trace
from services.financial.ledger_summary import LedgerSummaryError
from services.financial.tracing import Doctrine, TracingError
from postgres.models.enums import TransactionDirection, LedgerStatus
from tests.test_financial_ledger_summary import LedgerSummaryTests


class LedgerTracingTests(LedgerSummaryTests):
    def captured(self):
        snap=capture_ledger_snapshot(self.db, case_id=self.case.id, account_id=self.account.id,
                                    start_date=date(2026,1,1), end_date=date(2026,1,31))
        document=_capture_history(self.db,json.loads(snap.content),case_id=self.case.id)
        content=json.dumps(document,sort_keys=True,separators=(',',':'))
        return LedgerExport(LedgerSnapshot(content,hashlib.sha256(content.encode()).hexdigest(),len(content.encode())), '{}')

    def scenario(self):
        first,_=self.add(500000)
        second,_=self.add(500000)
        third,_=self.add(500000,TransactionDirection.debit)
        export=self.captured()
        request=LedgerTraceInput(account_id=self.account.id,start_date=date(2026,1,1),end_date=date(2026,1,31),
            expected_snapshot_sha256=export.snapshot.sha256, opening_balance_minor='0', opening_basis='Synthetic zero opening assumption.',
            order_basis='Explicit synthetic same-day order for comparison.', ordered_transaction_ids=[first.id,second.id,third.id],
            attributions=[dict(transaction_id=first.id,claim_id='claim-a',amount_minor='500000',basis='Synthetic attributed deposit.')],
            doctrines=list(Doctrine))
        return export,request,first,third

    def test_asset_allocation_reuses_method_draw_without_changing_cash(self):
        export, request, first, withdrawal = self.scenario()
        from services.financial.trace_assets import TraceAssetUseInput
        baseline=json.loads(evaluate_ledger_trace(export,request)['scenario_json'])
        use=TraceAssetUseInput(transaction_id=withdrawal.id,asset_label='Synthetic equipment',basis='Explicit synthetic whole-payment interpretation')
        self.assertEqual(set(use.model_dump()), {'transaction_id','asset_label','basis'})
        actual=json.loads(evaluate_ledger_trace(export,request.model_copy(update={'asset_uses':[use]}))['scenario_json'])
        self.assertEqual(actual['comparison'],baseline['comparison'])
        for method, expected in [('first_in_first_out','500000'),('pro_rata','250000'),('last_in_first_out','0')]:
            item=actual['asset_uses'][method][0]
            self.assertEqual(item['allocated_by_claim'].get('claim-a','0'),expected)
            self.assertEqual(int(item['outside_claims_minor'])+int(expected),500000)
            self.assertFalse(item['changes_cash_results'])
        for uses in ([use,use],[use.model_copy(update={'transaction_id':first.id})],[use.model_copy(update={'transaction_id':self.other_account.id})]):
            with self.assertRaises(LedgerSummaryError):evaluate_ledger_trace(export,request.model_copy(update={'asset_uses':uses}))
        for value in ('','   '):
            with self.assertRaises(ValidationError):TraceAssetUseInput(transaction_id=withdrawal.id,asset_label='Asset',basis=value)
        self.assertFalse(self.db.new or self.db.dirty)

    def test_partial_asset_allocation_conserves_amount_and_keeps_cash_unchanged(self):
        from services.financial.trace_assets import TraceAssetUseInput
        export, request, _, withdrawal = self.scenario()
        baseline=json.loads(evaluate_ledger_trace(export,request)['scenario_json'])
        use=TraceAssetUseInput(transaction_id=withdrawal.id,asset_label='Partial equipment purchase',basis='Synthetic purchase portion allocated proportionally',asset_amount_minor='300001',allocation_basis='proportional_share')
        actual=json.loads(evaluate_ledger_trace(export,request.model_copy(update={'asset_uses':[use]}))['scenario_json'])
        self.assertEqual(actual['comparison'],baseline['comparison'])
        for method,expected in [('first_in_first_out','300001'),('pro_rata','150001'),('last_in_first_out','0')]:
            item=actual['asset_uses'][method][0]
            self.assertEqual(item['allocated_by_claim'].get('claim-a','0'),expected)
            self.assertEqual(item['asset_amount_minor'],'300001')
            self.assertEqual(item['remaining_withdrawal_minor'],'199999')
            self.assertEqual(int(item['outside_claims_minor'])+sum(map(int,item['allocated_by_claim'].values())),300001)
            self.assertEqual(item['allocation_basis'],'proportional_share')
        with self.assertRaises(LedgerSummaryError):
            evaluate_ledger_trace(export,request.model_copy(update={'asset_uses':[use.model_copy(update={'asset_amount_minor':'500001'})]}))
        for changes in ({'asset_amount_minor':'0'},{'asset_amount_minor':'-1'},{'allocation_basis':None}):
            with self.assertRaises(ValidationError):TraceAssetUseInput.model_validate({**use.model_dump(),**changes})

    def test_working_population_keeps_p3_class_and_requires_explicit_selection(self):
        _, request, first, _ = self.scenario()
        first.proof_class = 'p3'
        self.db.commit()
        export = self.captured()
        self.assertEqual(ledger_trace_inputs(export)['included_rows'], 2)
        scope = ledger_trace_inputs(export, population='working')
        self.assertEqual(scope['included_rows'], 3)
        self.assertFalse(next(r for r in scope['readings'] if r['row']['key'] == str(first.id))['included'])
        working = request.model_copy(update={'population':'working', 'expected_snapshot_sha256':export.snapshot.sha256})
        saved = json.loads(evaluate_ledger_trace(export, working)['scenario_json'])
        self.assertEqual(saved['inputs']['population'], 'working')
        self.assertIn('p3', saved['comparison']['results']['first_in_first_out']['proof_classes_included'])
        self.assertEqual(first.proof_class, 'p3')
        with self.assertRaises(LedgerSummaryError):
            evaluate_ledger_trace(export, working.model_copy(update={'population':'verified'}))

    def test_multiple_claims_preserve_attribution_and_reject_excess(self):
        export, request, first, _ = self.scenario()
        a = request.attributions[0].model_copy(update={'amount_minor':'200000'})
        b = a.model_copy(update={'claim_id':'claim-b', 'amount_minor':'300000'})
        saved = json.loads(evaluate_ledger_trace(export, request.model_copy(update={'attributions':[a,b]}))['scenario_json'])
        self.assertEqual(set(saved['comparison']['claim_ids']), {'claim-a','claim-b'})
        with self.assertRaises(TracingError):
            evaluate_ledger_trace(export, request.model_copy(update={'attributions':[a,b.model_copy(update={'amount_minor':'300001'})]}))

    def test_methods_compare_exactly_and_preserve_all_assumptions(self):
        export,request,first,third=self.scenario()
        result=evaluate_ledger_trace(export,request)
        scenario=json.loads(result['scenario_json'])
        self.assertFalse(scenario['assumptions_verified'])
        self.assertFalse(scenario['applied'])
        self.assertEqual(scenario['inputs']['ordered_transaction_ids'],[str(i) for i in request.ordered_transaction_ids])
        methods=scenario['comparison']['results']
        self.assertEqual(methods['first_in_first_out']['outcomes']['claim-a']['surviving']['minor_units'],'0')
        self.assertEqual(methods['last_in_first_out']['outcomes']['claim-a']['surviving']['minor_units'],'500000')
        self.assertEqual(scenario['ledger_snapshot'],json.loads(export.snapshot.content))
        canonical=json.dumps(scenario,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
        self.assertEqual(result['scenario_sha256'],hashlib.sha256(canonical).hexdigest())
        self.assertEqual(result['scenario_byte_count'],len(canonical))
        self.assertEqual(result,evaluate_ledger_trace(export,request))
        self.assertFalse(self.db.new or self.db.dirty)

    def test_snapshot_change_and_incomplete_or_duplicate_order_refused(self):
        export,request,_,_=self.scenario()
        for update in ({'expected_snapshot_sha256':'0'*64}, {'account_id':self.other_account.id},
                       {'ordered_transaction_ids':request.ordered_transaction_ids[:-1]},
                       {'ordered_transaction_ids':[request.ordered_transaction_ids[0]]*3},
                       {'doctrines':[Doctrine.first_in_first_out]*2}):
            with self.subTest(update=update), self.assertRaises(LedgerSummaryError):
                evaluate_ledger_trace(export,request.model_copy(update=update))

    def test_ineligible_and_wrong_deposit_attributions_refused(self):
        export,request,first,third=self.scenario()
        wrong=request.attributions[0].model_copy(update={'transaction_id':third.id})
        with self.assertRaises(TracingError):
            evaluate_ledger_trace(export,request.model_copy(update={'attributions':[wrong]}))
        from services.financial.quarantine_row import quarantine_case_row
        quarantine_case_row(self.db,case_id=self.case.id,transaction_id=first.id,actor=self.user,reason='Exclude synthetic claim deposit')
        fresh=self.captured()
        with self.assertRaises(LedgerSummaryError):evaluate_ledger_trace(fresh,request)
        self.assertEqual(ledger_trace_inputs(fresh)['excluded_rows'],1)

    def test_dates_limits_and_missing_assumptions_refused(self):
        export,request,first,third=self.scenario()
        third.ordering_date=date(2026,1,1);first.ordering_date=date(2026,1,2);self.db.commit()
        fresh=self.captured()
        with self.assertRaises(LedgerSummaryError):
            evaluate_ledger_trace(fresh,request.model_copy(update={'expected_snapshot_sha256':fresh.snapshot.sha256}))
        with patch('services.financial.ledger_tracing.MAX_TRACE_ROWS',1):
            with self.assertRaises(LedgerSummaryError):ledger_trace_inputs(export)
        with patch('services.financial.ledger_tracing.MAX_EXPORT_BYTES',1):
            with self.assertRaises(LedgerSummaryError):evaluate_ledger_trace(export,request)
        values=request.model_dump()
        for field in ('opening_basis','order_basis','doctrines'):
            missing={k:v for k,v in values.items() if k!=field}
            with self.assertRaises(ValidationError):LedgerTraceInput(**missing)
        with self.assertRaises(ValidationError):LedgerTraceInput(**{**values,'opening_basis':'   '})


import unittest
from uuid import uuid4
class LedgerTraceRouterTests(unittest.TestCase):
    def test_capture_scope_and_safe_error_responses(self):
        from routers import financial_ledger as router
        from fastapi import HTTPException
        from unittest.mock import Mock
        db=Mock(); case,account=uuid4(),uuid4()
        with patch.object(router,'capture_ledger_export',return_value='captured') as capture, patch.object(router,'ledger_trace_inputs',return_value={'applied':False}):
            result=router.get_ledger_trace_inputs(case,account,date(2026,1,1),date(2026,1,31),"verified",db)
            self.assertFalse(result['applied'])
            capture.assert_called_once_with(db.get_bind(),case_id=case,account_id=account,start_date=date(2026,1,1),end_date=date(2026,1,31))
        with patch.object(router,'capture_ledger_export',side_effect=RuntimeError('private')):
            with self.assertRaises(HTTPException) as caught:router.get_ledger_trace_inputs(case,account,date(2026,1,1),date(2026,1,31),"verified",db)
            self.assertEqual(caught.exception.status_code,500)
            self.assertNotIn('private',caught.exception.detail)
