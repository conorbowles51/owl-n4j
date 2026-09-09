from copy import deepcopy
from pydantic import ValidationError
from sqlalchemy import select, update
from postgres.models.financial import FinancialStatementPeriod
from postgres.models.financial_candidates import FinancialCandidateFinalization
from services.financial.candidate_statement_scopes import ReviewedStatementScope
from services.financial.candidate_store import CandidateStoreError
from services.financial.statement_checks import list_statement_checks
from tests.test_financial_candidate_materialization import MaterializationFixture

class StatementScopeTests(MaterializationFixture):
    def scope(self):
        def cell(row,column,text):
            return dict(page_number=1,table_index=0,row_index=row,column_index=column,
                source_revision=self.proposal['source_revision'],expected_text=text)
        return dict(account_id=str(self.acct.id),currency='GBP',candidate_ids=[str(value) for value in self.candidates],
            start=dict(value='2026-02-01',source=cell(0,0,'01/02')),
            end=dict(value='2026-02-03',source=cell(1,0,'03/02')),
            opening=dict(amount_minor='1234',source=cell(0,1,'1234')),
            closing=dict(amount_minor='1234',source=cell(1,1,'1234')),
            balance_convention='asset_balance',reason='Synthetic controls for selected rows; no complete-statement claim')
    def scoped_request(self,scope=None):
        scope=scope or self.scope()
        preview=self.preview(statement_scopes=[ReviewedStatementScope.model_validate(scope)])
        return dict(expected_revision=preview['revision'],documentary_financial_rows=True,
            accept_incomplete_coverage=True,reason='Synthetic statement-control finalization',statement_scopes=[scope])
    def test_period_observations_and_row_links_are_atomic_and_stay_p3(self):
        request=self.scoped_request();result=self.finalize(request)
        rows=self.transactions()
        period=self.db.get(FinancialStatementPeriod,rows[0].statement_period_id)
        self.assertTrue(all(row.statement_period_id==period.id for row in rows))
        self.assertEqual(period.opening_balance_minor,1234)
        self.assertEqual(period.closing_balance_minor,1234)
        self.assertEqual(str(period.period_start),'2026-02-01')
        self.assertEqual(period.reconciliation_status,'not_attempted')
        self.assertTrue(all(row.proof_class=='p3' for row in rows))
        self.assertFalse(result['included_in_default_totals'])
        receipt=self.db.scalar(select(FinancialCandidateFinalization))
        self.assertEqual(receipt.snapshot['manifest']['statement_scopes'][0]['bound_controls']['opening']['source']['expected_text'],'1234')
        self.assertEqual(receipt.snapshot['statement_periods'][0]['period_id'],str(period.id))
        self.assertEqual(self.finalize(request),{**result,'created':False})
        self.assertEqual(list_statement_checks(self.db,case_id=self.case.id)['items'][0]['status'],'unbalanced')
    def test_changed_controls_require_a_new_preview(self):
        request=self.scoped_request();request['statement_scopes'][0]['opening']['amount_minor']='999'
        with self.assertRaisesRegex(CandidateStoreError,'Reload'):self.finalize(request)
        self.assertEqual(self.transactions(),[])
    def test_wrong_source_text_or_revision_refuses_preview(self):
        for field,value in [('expected_text','fabricated'),('source_revision','f'*64),('row_index',99)]:
            scope=self.scope();scope['start']['source'][field]=value
            with self.assertRaises(CandidateStoreError):self.scoped_request(scope)
    def test_account_currency_unknown_candidate_and_repeated_assignment_refused(self):
        from uuid import uuid4
        for changes in [dict(account_id=str(uuid4())),dict(currency='USD'),dict(candidate_ids=[str(uuid4())])]:
            scope={**self.scope(),**changes}
            with self.assertRaises(CandidateStoreError):self.scoped_request(scope)
        scope=ReviewedStatementScope.model_validate(self.scope())
        with self.assertRaises(CandidateStoreError):self.preview(statement_scopes=[scope,scope])
    def test_missing_balances_are_not_zero(self):
        scope=self.scope();scope['opening']=None;scope['closing']=None
        self.finalize(self.scoped_request(scope))
        period=self.db.get(FinancialStatementPeriod,self.transactions()[0].statement_period_id)
        self.assertIsNone(period.opening_balance_minor)
        self.assertEqual(period.opening_balance_source,'absent')
    def test_liability_owed_balances_keep_originals_and_convert_ledger_sign(self):
        scope=self.scope();scope['balance_convention']='liability_owed'
        self.finalize(self.scoped_request(scope))
        period=self.db.get(FinancialStatementPeriod,self.transactions()[0].statement_period_id)
        self.assertEqual(period.opening_balance_minor,-1234)
        receipt=self.db.scalar(select(FinancialCandidateFinalization))
        self.assertEqual(receipt.snapshot['request']['statement_scopes'][0]['opening']['amount_minor'],'1234')
    def test_invalid_dates_convention_and_overflow_refused(self):
        for changes in [dict(balance_convention='guess'),dict(start={**self.scope()['start'],'value':'2026-02-30'}),
                        dict(balance_convention='liability_owed',opening={**self.scope()['opening'],'amount_minor':'-9223372036854775808'})]:
            with self.assertRaises(ValidationError):ReviewedStatementScope.model_validate({**self.scope(),**changes})
    def test_unassigned_rows_keep_no_period_and_controls_never_claim_full_coverage(self):
        scope=self.scope();scope['candidate_ids']=scope['candidate_ids'][:1]
        self.finalize(self.scoped_request(scope));rows=self.transactions()
        self.assertEqual(sum(row.statement_period_id is not None for row in rows),1)
        self.assertTrue(all(row.proof_class=='p3' for row in rows))
    def test_period_and_document_roll_back_if_transaction_write_fails(self):
        from unittest.mock import patch
        from sqlalchemy import func
        request=self.scoped_request()
        with patch('services.financial.candidate_materialization.record_transactions',side_effect=RuntimeError('test failure')):
            with self.assertRaises(RuntimeError):self.finalize(request)
        self.db.expire_all()
        self.assertEqual(self.db.scalar(select(func.count()).select_from(FinancialStatementPeriod)),0)
        self.assertEqual(self.transactions(),[])
    def test_statement_source_preserves_original_liability_controls(self):
        from services.financial.ledger_source import statement_source
        scope=self.scope();scope['balance_convention']='liability_owed'
        self.finalize(self.scoped_request(scope))
        source=statement_source(self.db,case_id=self.case.id,period_id=self.transactions()[0].statement_period_id)
        controls=source['reviewed_controls']
        self.assertEqual(controls['balance_convention'],'liability_owed')
        self.assertEqual(controls['controls'][2]['reviewed_value'],'1234')
        self.assertEqual(controls['controls'][2]['original_text'],'1234')
        self.assertEqual(controls['controls'][2]['locator']['page'],1)
        self.assertFalse(source['file_bytes_verified'])
    def test_statement_source_refuses_tampered_control_receipt(self):
        from services.financial.ledger_source import statement_source, LedgerSourceError
        self.finalize(self.scoped_request())
        receipt=self.db.scalar(select(FinancialCandidateFinalization))
        changed=deepcopy(receipt.snapshot);changed['statement_periods'][0]['currency']='USD'
        self.db.execute(update(FinancialCandidateFinalization).where(FinancialCandidateFinalization.id==receipt.id).values(snapshot=changed));self.db.expire_all()
        with self.assertRaisesRegex(LedgerSourceError,'inconsistent'):
            statement_source(self.db,case_id=self.case.id,period_id=self.transactions()[0].statement_period_id)
    def test_statement_source_refuses_invalid_sealed_locator_and_foreign_case(self):
        from services.financial.ledger_source import statement_source, LedgerSourceError
        from services.financial.pdf_candidates import _digest
        from uuid import uuid4
        self.finalize(self.scoped_request())
        period=self.transactions()[0].statement_period_id
        with self.assertRaises(LedgerSourceError):statement_source(self.db,case_id=uuid4(),period_id=period)
        receipt=self.db.scalar(select(FinancialCandidateFinalization))
        changed=deepcopy(receipt.snapshot);changed['manifest']['statement_scopes'][0]['bound_controls']['opening']['locator']['page']=99
        self.db.execute(update(FinancialCandidateFinalization).where(FinancialCandidateFinalization.id==receipt.id).values(snapshot=changed,snapshot_sha256=_digest(changed)));self.db.expire_all()
        with self.assertRaisesRegex(LedgerSourceError,'inconsistent'):
            statement_source(self.db,case_id=self.case.id,period_id=period)
    def test_readable_export_preserves_printed_sign_unknown_controls_and_escapes_reason(self):
        import json
        from services.financial.ledger_snapshot import capture_ledger_snapshot, _capture_history, render_ledger_report, LedgerSnapshot
        scope=self.scope();scope['balance_convention']='liability_owed';scope['closing']=None
        scope['reason']='<script>untrusted evidence</script>'
        self.finalize(self.scoped_request(scope))
        captured=capture_ledger_snapshot(self.db,case_id=self.case.id)
        document=_capture_history(self.db,json.loads(captured.content),case_id=self.case.id)
        report=render_ledger_report(LedgerSnapshot(json.dumps(document),'test',0))
        self.assertIn('Reviewed statement controls',report)
        self.assertIn('12.34 GBP',report)
        self.assertIn('Unknown — not supplied',report)
        self.assertIn('Amounts owed (converted to negative ledger balances)',report)
        self.assertIn('&lt;script&gt;untrusted evidence&lt;/script&gt;',report)
        self.assertNotIn('<script>',report)
        self.assertIn('not a complete-statement certification',report)
