import hashlib,json
from datetime import date
from unittest.mock import patch
from services.financial.network_tracing import network_trace_inputs,evaluate_network_trace
from services.financial.ledger_snapshot import LedgerExport,LedgerSnapshot,capture_ledger_snapshot,_capture_history
from services.financial.ledger_summary import LedgerSummaryError
from services.financial.tracing import Doctrine
from postgres.models.enums import TransactionDirection
from tests.test_financial_ledger_summary import LedgerSummaryTests

class NetworkTracingTests(LedgerSummaryTests):
    def network(self):
        b=self._account(self.case.id,identity_key='network-b');c=self._account(self.case.id,identity_key='network-c');self.db.add_all([b,c]);self.db.commit()
        def row(account,amount,direction=TransactionDirection.credit):
            doc=self.make_document();period=self.make_period(doc,account=account)
            result=self.add_row(period,doc,account=account,amount=amount,direction=direction);result.proof_class='p3';self.db.commit();return result
        root=row(self.account,10000);clean=row(self.account,10000);send=row(self.account,10000,TransactionDirection.debit);receive=row(b,10000);send2=row(b,6000,TransactionDirection.debit);receive2=row(c,6000);exit=row(c,2000,TransactionDirection.debit)
        ordered=[root,clean,send,receive,send2,receive2,exit]
        snapshot=capture_ledger_snapshot(self.db,case_id=self.case.id,start_date=date(2026,1,1),end_date=date(2026,1,31));document=_capture_history(self.db,json.loads(snapshot.content),case_id=self.case.id);content=json.dumps(document,sort_keys=True,separators=(',',':'));export=LedgerExport(LedgerSnapshot(content,hashlib.sha256(content.encode()).hexdigest(),len(content.encode())),'{}')
        request=dict(expected_snapshot_sha256=export.snapshot.sha256,population='working',tolerance_days=3,start_date='2026-01-01',end_date='2026-01-31',currency='GBP',
            pairs=[dict(debit_id=str(send.id),credit_id=str(receive.id)),dict(debit_id=str(send2.id),credit_id=str(receive2.id))],basis='Explicit synthetic transfers',
            openings=[dict(account_id=str(a.id),amount_minor='0',basis='Synthetic zero opening') for a in [self.account,b,c]],
            ordered_transaction_ids=[str(r.id) for r in ordered],order_basis='Explicit synthetic order',attributions=[dict(transaction_id=str(root.id),claim_id='claim',amount_minor='10000',basis='Synthetic root attribution')],doctrines=[d.value for d in Doctrine])
        return export,request,ordered
    def test_two_hops_compare_methods_and_conserve_root_claim(self):
        export,request,rows=self.network();result=evaluate_network_trace(export,request);report=json.loads(result['scenario_json'])
        fifo=report['results']['first_in_first_out'];pro=report['results']['pro_rata'];lifo=report['results']['last_in_first_out']
        self.assertEqual([h['propagated_by_claim']['claim'] for h in fifo['hops']],['10000','6000'])
        self.assertEqual(fifo['claims']['claim']['reported_remaining_minor'],'8000')
        self.assertEqual(fifo['claims']['claim']['withdrawn_without_selected_transfer_minor'],'2000')
        self.assertEqual(pro['claims']['claim']['reported_remaining_minor'],'9000')
        self.assertEqual(lifo['claims']['claim']['reported_remaining_minor'],'10000')
        for output in report['results'].values():
            claim=output['claims']['claim'];self.assertEqual(int(claim['reported_remaining_minor'])+int(claim['withdrawn_without_selected_transfer_minor']),10000)
            self.assertEqual(len(output['hops']),2)
        self.assertFalse(report['applied']);self.assertFalse(report['assumptions_verified']);self.assertEqual(report['ledger_snapshot'],json.loads(export.snapshot.content))
        self.assertEqual(hashlib.sha256(result['scenario_json'].encode()).hexdigest(),result['scenario_sha256'])
        self.assertTrue(all(r.proof_class=='p3' for r in rows))
    def test_stale_scope_missing_rows_reused_pairs_and_backward_order_refused(self):
        export,request,rows=self.network();backward=list(request['ordered_transaction_ids']);backward[2],backward[3]=backward[3],backward[2]
        for change in [dict(expected_snapshot_sha256='0'*64),dict(ordered_transaction_ids=backward),dict(ordered_transaction_ids=request['ordered_transaction_ids'][:-1]),dict(pairs=request['pairs']*2),dict(openings=request['openings'][:-1]),dict(population='verified')]:
            with self.subTest(change=change),self.assertRaises(LedgerSummaryError):evaluate_network_trace(export,{**request,**change})
    def test_receiving_credit_cannot_be_double_attributed_as_a_root(self):
        export,request,rows=self.network();wrong={**request['attributions'][0],'transaction_id':str(rows[3].id)}
        with self.assertRaises(LedgerSummaryError):evaluate_network_trace(export,{**request,'attributions':[wrong]})
        with patch('services.financial.network_tracing.MAX_NETWORK_ROWS',2):
            with self.assertRaises(LedgerSummaryError):evaluate_network_trace(export,request)
