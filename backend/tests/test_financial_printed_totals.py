from copy import deepcopy
from unittest import TestCase
from services.financial.printed_totals import compare_printed_totals
from services.financial.candidate_statement_scopes import ReviewedStatementScope
from services.financial.correction_preview import preview_amount_correction
from services.financial.corrections import correct_transaction
from services.financial.ledger_source import statement_source
from services.financial.statement_checks import list_statement_checks
from tests.test_financial_candidate_statement_scopes import StatementScopeTests
from postgres.models.financial import FinancialStatementPeriod, AdjudicationEvent

class PrintedArithmeticTests(TestCase):
    def controls(self, amount='9007199254740993'):
        return dict(controls=[dict(role='credits_total',reviewed_value=amount,original_text='printed total',locator={})])
    def test_exact_sides_and_unknown_not_zero(self):
        result=compare_printed_totals(self.controls(),credits=9007199254740994,debits=0)
        self.assertEqual(result['checks'][0]['difference_minor'],'1')
        self.assertEqual(result['checks'][1]['status'],'unavailable')
        self.assertIsNone(result['checks'][1]['printed_minor'])
        self.assertEqual(compare_printed_totals(self.controls('0'),credits=0,debits=0)['checks'][0]['status'],'balanced')
    def test_malformed_and_duplicate_controls_refuse(self):
        for raw in ['-1','1.2','9999999999999999999999999']:
            with self.assertRaises(ValueError):compare_printed_totals(self.controls(raw),credits=1,debits=0)
        c=self.controls();c['controls']*=2
        with self.assertRaises(ValueError):compare_printed_totals(c,credits=1,debits=0)

class PrintedTotalsJourneyTests(StatementScopeTests):
    def totals_scope(self):
        scope=self.scope()
        scope['credits_total']=deepcopy(scope['opening'])
        scope['credits_total']['amount_minor']='0'
        scope['debits_total']=deepcopy(scope['closing'])
        scope['debits_total']['amount_minor']='2468'
        return scope
    def test_old_scope_serialization_and_repeated_finalization_are_unchanged(self):
        original=self.scope()
        self.assertEqual(ReviewedStatementScope.model_validate(original).model_dump(mode='json'),original)
        self.assertNotIn('credits_total',self.preview(statement_scopes=[ReviewedStatementScope.model_validate(original)])['statement_scopes'][0]['bound_controls'])
    def test_saved_controls_checks_and_correction_audit(self):
        self.finalize(self.scoped_request(self.totals_scope()))
        rows=self.transactions();period=self.db.get(FinancialStatementPeriod,rows[0].statement_period_id)
        current=list_statement_checks(self.db,case_id=self.case.id)['items'][0]['printed_totals']
        self.assertEqual([c['status'] for c in current['checks']],['balanced','balanced'])
        source=statement_source(self.db,case_id=self.case.id,period_id=period.id)
        self.assertEqual(len(source['reviewed_controls']['controls']),6)
        preview=preview_amount_correction(self.db,case_id=self.case.id,transaction_id=rows[0].id,amount_minor=1235,direction='debit')
        self.assertEqual(preview['printed_totals']['proposed']['checks'][1]['difference_minor'],'1')
        result=correct_transaction(self.db,case_id=self.case.id,transaction_id=rows[0].id,amount_minor=1235,direction='debit',expected_revision=preview['document_revision'],actor=self.actor,reason='Synthetic amount correction')
        self.assertEqual(result['proof_class'],'p3')
        from uuid import UUID
        event=self.db.get(AdjudicationEvent,UUID(result['adjudication_id']))
        self.assertEqual(event.after['printed_total_comparison'],preview['printed_totals'])
        updated=list_statement_checks(self.db,case_id=self.case.id)['items'][0]['printed_totals']
        self.assertEqual(updated['checks'][1]['difference_minor'],'1')
    def test_total_source_drift_and_negative_total_refuse(self):
        from pydantic import ValidationError
        from services.financial.candidate_store import CandidateStoreError
        scope=self.totals_scope();scope['credits_total']['amount_minor']='-1'
        with self.assertRaises(ValidationError):ReviewedStatementScope.model_validate(scope)
        scope=self.totals_scope();scope['credits_total']['source']['expected_text']='changed'
        with self.assertRaises(CandidateStoreError):self.scoped_request(scope)
