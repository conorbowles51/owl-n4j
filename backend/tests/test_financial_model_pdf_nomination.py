import json
import unittest
from uuid import uuid4,UUID
from unittest.mock import patch
from services.financial.model_pdf_nomination import run_pdf_model_nomination,read_pdf_model_nomination,bind_model_answer,build_nomination_prompt
from services.financial.candidate_sources import read_candidate_source
from services.financial.pdf_candidates import PdfMappingError
from services.financial.candidate_store import CandidateStoreError
from postgres.models.financial_pdf_nominations import FinancialPdfNomination
from tests import test_financial_candidate_store as fixture

class ModelNominationTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.CandidateStoreTests();self.f.setUp()
        FinancialPdfNomination.__table__.create(self.f.engine)
        self.request=dict(request_id=str(uuid4()),page_number=1,table_index=0,source_revision=self.f.revision())
        self.calls=[]
        self.policy=patch('services.ai_model_policy.get_workload_model',return_value=('openai','synthetic-model'));self.policy.start()
    def tearDown(self):
        self.policy.stop();self.f.tearDown()
    def answer(self):return json.dumps({'rows':[{'row_index':0,'columns':[{'column_index':0,'meaning':'date'},{'column_index':1,'meaning':'amount'}],'reason':'SYNTHETIC date and amount cells'}]})
    def call(self,*args):
        self.calls.append(args[1:]);return self.answer(),{}
    def run_nomination(self,**updates):
        return run_pdf_model_nomination(self.f.db,**{**dict(case_id=self.f.case,evidence_file_id=self.f.file,request=self.request,actor=self.f.actor,call_model=self.call),**updates})
    def test_existing_cells_and_model_context_persist_without_candidate_or_ledger_writes(self):
        result=self.run_nomination()
        self.assertEqual(result['status'],'completed');self.assertFalse(result['applied'])
        self.assertEqual(result['request']['model_id'],'synthetic-model')
        self.assertEqual(result['result']['rows'][0]['cells'][1]['expected_text'],'1234')
        self.assertEqual(result['result']['rows'][0]['cells'][0]['proposed_meaning'],'date')
        self.assertEqual(self.f.counts(),(0,0))
        self.assertEqual(result,self.run_nomination())
        self.assertEqual(len(self.calls),1)
        self.assertEqual(result,read_pdf_model_nomination(self.f.db,case_id=self.f.case,nomination_id=UUID(result['id'])))
    def test_failed_provider_attempt_is_retained_and_never_automatically_repeated(self):
        def fail(*args):self.calls.append('failed');raise RuntimeError('private credential detail')
        first=self.run_nomination(call_model=fail)
        self.assertEqual(first['status'],'failed');self.assertEqual(first['error_code'],'provider_failed')
        self.assertNotIn('private',json.dumps(first));self.assertIsNone(first['result'])
        self.assertEqual(first,self.run_nomination(call_model=fail));self.assertEqual(len(self.calls),1)
    def test_missing_positions_and_fabricated_values_are_refused(self):
        source=read_candidate_source(self.f.db,case_id=self.f.case,evidence_file_id=self.f.file,page_number=1)
        valid=json.loads(self.answer())
        variants=[{'rows':[{**valid['rows'][0],'amount':'0.01'}]}, {'rows':[{**valid['rows'][0],'row_index':99}]}, {'rows':valid['rows']*2}, {'rows':[{**valid['rows'][0],'columns':[{'column_index':8,'meaning':'amount'}]}]}]
        for answer in variants:
            with self.subTest(answer=answer),self.assertRaises(ValueError):bind_model_answer(json.dumps(answer),source)
        result=self.run_nomination(call_model=lambda *a:('not JSON',{}))
        self.assertEqual(result['error_code'],'invalid_model_response');self.assertIsNone(result['result'])
    def test_source_change_during_model_call_does_not_return_proposals(self):
        def changed(*args):
            self.f.geometry.payload=[];self.f.db.commit();return self.answer(),{}
        result=self.run_nomination(call_model=changed)
        self.assertEqual(result['status'],'failed');self.assertEqual(result['error_code'],'source_changed')
    def test_scope_reuse_input_change_and_large_page_are_refused_before_model_call(self):
        first=self.run_nomination()
        with self.assertRaises(PdfMappingError):self.run_nomination(case_id=uuid4())
        with self.assertRaises(PdfMappingError):self.run_nomination(request={**self.request,'page_number':2})
        with self.assertRaises(PdfMappingError):read_pdf_model_nomination(self.f.db,case_id=uuid4(),nomination_id=UUID(first['id']))
        self.assertEqual(len(self.calls),1)
        with self.assertRaises(PdfMappingError):build_nomination_prompt({'rows':[{'row_index':0,'cells':[{'column_index':0,'expected_text':'a'*24001}]}]})
    def test_terminal_result_cannot_be_rewritten(self):
        result=self.run_nomination();run=self.f.db.get(FinancialPdfNomination,UUID(result['id']))
        run.result={'rows':[]}
        with self.assertRaises(ValueError):self.f.db.commit()
        self.f.db.rollback()
        self.assertEqual(result,read_pdf_model_nomination(self.f.db,case_id=self.f.case,nomination_id=UUID(result['id'])))

    def test_selected_rows_carry_model_audit_while_investigator_roles_remain_separate(self):
        result=self.run_nomination()
        proposal={**self.f.mapping,'nomination_id':result['id'],'rows':self.f.mapping['rows'][:1]}
        saved=self.f.save(proposal=proposal)
        self.assertEqual(saved['original']['nomination_snapshot']['request']['model_id'],'synthetic-model')
        self.assertEqual(saved['original']['nomination_snapshot']['result']['rows'][0]['cells'][0]['proposed_meaning'],'date')
        self.assertEqual(saved['candidates'][0]['original']['cells'][0]['proposed_meaning'],'booking_date')
        self.assertEqual({k:v for k,v in saved.items() if k!="created"},self.f.read(saved))
        from services.financial.candidate_assessment import candidate_source_readings
        source = candidate_source_readings(self.f.db,case_id=self.f.case,candidate_id=UUID(saved['candidates'][0]['id']))
        self.assertEqual(source['model_nomination']['row']['cells'][0]['proposed_meaning'],'date')
        self.assertEqual(source['cells'][0]['proposed_meaning'],'booking_date')
        self.assertNotIn('source_rows',source['model_nomination']['request'])
        with self.assertRaises(CandidateStoreError):self.f.save(proposal={**proposal,'rows':self.f.mapping['rows']})

    def test_legacy_mappings_do_not_acquire_new_null_fields_or_revisions(self):
        saved=self.f.save()
        self.assertNotIn('nomination_id',saved['original']['proposal'])
        self.assertNotIn('nomination_snapshot',saved['original'])
        from services.financial.candidate_assessment import current_candidate_original
        current_candidate_original(self.f.db,case_id=self.f.case,candidate_id=UUID(saved['candidates'][0]['id']))

    def test_abandoned_attempt_cannot_be_overwritten_by_provider_completion(self):
        from services.financial.model_pdf_nomination import abandon_pdf_model_nomination
        def interrupted(*args):
            outcome=abandon_pdf_model_nomination(self.f.db,case_id=self.f.case,nomination_id=UUID(self.request['request_id']),actor=self.f.actor)
            self.assertEqual(outcome['error_code'],'user_abandoned')
            return self.answer(),{}
        result=self.run_nomination(call_model=interrupted)
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['error_code'],'user_abandoned')
        self.assertIsNone(result['result'])
        self.assertEqual(result, self.run_nomination())
        self.assertEqual(self.calls,[])
        with self.assertRaises(PdfMappingError):
            abandon_pdf_model_nomination(self.f.db,case_id=uuid4(),nomination_id=UUID(result['id']),actor=self.f.actor)
        self.assertEqual(result, abandon_pdf_model_nomination(self.f.db,case_id=self.f.case,nomination_id=UUID(result['id']),actor=self.f.actor))

    def test_usage_is_recorded_once_even_when_output_is_invalid(self):
        with patch('services.ai_costs_service.record_cost') as cost:
            result=self.run_nomination(call_model=lambda *args:('invalid JSON', {'prompt_tokens':21,'completion_tokens':4,'total_tokens':25,'private':123}))
            self.assertEqual(result['error_code'],'invalid_model_response')
            self.run_nomination()
            self.assertEqual(cost.call_count,1)
            self.assertEqual(cost.call_args.kwargs['total_tokens'],25)
            self.assertEqual(cost.call_args.kwargs['extra_metadata']['financial_nomination_id'],result['id'])

    def test_success_retains_the_original_response_separately_from_selected_roles(self):
        result=self.run_nomination()
        self.assertEqual(result['result']['raw_response'],self.answer())

    def test_local_disabled_key_is_refused_before_constructing_a_client(self):
        from services.financial.model_pdf_nomination import _call_model
        with patch('services.ai_provider_credentials.get_provider_api_key',return_value='local-test-no-api-key'), patch('services.llm_service.LLMService') as service:
            with self.assertRaises(ValueError): _call_model(self.f.db,'openai','test','synthetic')
            service.assert_not_called()
