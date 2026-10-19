import unittest
from copy import deepcopy
from services.financial.review_methods import pdf_review_methods
from services.financial.pdf_candidates import _digest
from services.financial.ledger_summary import LedgerSummaryError

class ReviewMethodsTests(unittest.TestCase):
    def document(self, model=False):
        proposal=dict(case_id='case',evidence_file_id='file',source_revision='a'*64,schema_version='pdf-grid-mapping-v1')
        snapshot={'proposal':proposal}
        if model:
            proposal['nomination_id']='attempt'
            request=dict(source_revision='a'*64,provider='synthetic',model_id='synthetic-model',schema_version='pdf-cell-nomination-v1',execution_mode='simulated_test',prompt_sha256='b'*64)
            snapshot['nomination_snapshot']=dict(id='attempt',case_id='case',evidence_file_id='file',request=request,request_sha256=_digest(request),created_at='2026-09-10T00:00:00Z')
        return {'pdf_review_history':{'mappings':[dict(id='mapping',evidence_file_id='file',snapshot=snapshot,snapshot_sha256=_digest(snapshot))]}}

    def test_manual_review_does_not_claim_absence_of_upstream_models(self):
        result=pdf_review_methods(self.document())
        self.assertIsNone(result['methods'][0]['model'])
        self.assertIn('not an extraction accuracy measurement',result['validation'])
        self.assertIn('not a complete case custody',result['scope'])

    def test_model_version_and_simulated_status_retained_without_changing_input(self):
        document=self.document(True);before=deepcopy(document)
        result=pdf_review_methods(document)
        self.assertEqual(result['methods'][0]['model']['execution_mode'],'simulated_test')
        self.assertEqual(result['methods'][0]['model']['model_id'],'synthetic-model')
        self.assertEqual(document,before)

    def test_refuses_tampered_mapping_or_model_provenance(self):
        document=self.document(True)
        record=document['pdf_review_history']['mappings'][0]
        record['snapshot']['nomination_snapshot']['request']['model_id']='replacement'
        with self.assertRaises(LedgerSummaryError):pdf_review_methods(document)
        record['snapshot_sha256']=_digest(record['snapshot'])
        with self.assertRaises(LedgerSummaryError):pdf_review_methods(document)

    def test_legacy_snapshot_without_history_does_not_invent_methods(self):
        self.assertIsNone(pdf_review_methods({}))

    def test_transport_metadata_and_argument_digest_are_retained_and_verified(self):
        import hashlib, json
        document = self.document(True)
        record = document['pdf_review_history']['mappings'][0]
        arguments = {'model':'requested', 'messages':[{'role':'user','content':'Synthetic source'}]}
        digest = hashlib.sha256(json.dumps(arguments,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        record['snapshot']['nomination_snapshot']['result'] = {'transport':dict(status='captured',request_arguments=arguments,
            request_arguments_sha256=digest,adapter_sha256='c'*64,response_metadata={'reported_model':'reported-revision'})}
        record['snapshot_sha256'] = _digest(record['snapshot'])
        model = pdf_review_methods(document)['methods'][0]['model']
        self.assertEqual(model['provider_reported_model'], 'reported-revision')
        self.assertEqual(model['request_arguments_sha256'], digest)
        arguments['model'] = 'changed'
        record['snapshot_sha256'] = _digest(record['snapshot'])
        with self.assertRaisesRegex(LedgerSummaryError, 'arguments'): pdf_review_methods(document)
