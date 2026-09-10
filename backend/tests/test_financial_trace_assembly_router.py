import hashlib
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4
from fastapi import UploadFile, HTTPException
from routers.financial_ledger import assemble_saved_trace_support


class TraceAssemblyRouterTests(unittest.IsolatedAsyncioTestCase):
    def upload(self, content=b'scenario'):
        return UploadFile(file=io.BytesIO(content))

    async def call(self, scenarios, **kwargs):
        return await assemble_saved_trace_support(scenarios=scenarios, case_id=kwargs.pop('case_id',uuid4()),
            ledger=kwargs.pop('ledger',None), review=kwargs.pop('review',None), predictions=kwargs.pop('predictions',None),
            privilege_marking='confidential', current_user=SimpleNamespace(id=uuid4(),name='Tester',email='fixture@example.test'),
            db=MagicMock(), **kwargs)

    async def test_selected_bytes_case_actor_and_receipt_are_bound_to_response(self):
        case=uuid4(); scenario=self.upload(); ledger=self.upload(b'ledger');review=self.upload(b'{"review":true}');predictions=self.upload(b'{"predictions":true}')
        with patch('services.financial.trace_support_archive.build_trace_support_archive',return_value=b'archive') as build, patch('routers.financial_ledger.record_prepared_export',return_value=dict(export_id='id',entry_sha256='a'*64,sequence=1)) as receipt:
            response=await self.call([scenario],case_id=case,ledger=ledger,review=review,predictions=predictions)
        self.assertEqual(build.call_args.args[0],[b'scenario'])
        options=build.call_args.kwargs
        self.assertEqual(options['expected_case_id'],case)
        self.assertEqual(options['reference_review'],{'review':True})
        self.assertEqual(options['ledger_archive'],b'ledger')
        self.assertEqual(options['preparation']['privilege_marking'],'confidential')
        selected=options['preparation']['selected_input_sha256']
        self.assertEqual(response.headers['x-loupe-assembly-inputs-sha256'],hashlib.sha256(json.dumps(selected,sort_keys=True,separators=(',',':')).encode()).hexdigest())
        self.assertEqual(receipt.call_args.kwargs['content'],response.body)
        self.assertTrue(all(upload.file.closed for upload in (scenario,ledger,review,predictions)))

    async def test_partial_validation_and_ambiguous_json_fail_before_assembly(self):
        for review_bytes,include_predictions in [(b'{}',False),(b'{"a":1,"a":2}',True)]:
            scenario=self.upload();review=self.upload(review_bytes);predictions=self.upload(b'{}') if include_predictions else None
            with patch('services.financial.trace_support_archive.build_trace_support_archive') as build:
                with self.assertRaises(HTTPException) as caught:
                    await self.call([scenario],review=review,predictions=predictions)
            self.assertEqual(caught.exception.status_code,422)
            build.assert_not_called()
            self.assertTrue(scenario.file.closed and review.file.closed)
            if predictions:self.assertTrue(predictions.file.closed)

    async def test_audit_failure_withholds_archive_and_closes_upload(self):
        scenario=self.upload()
        with patch('services.financial.trace_support_archive.build_trace_support_archive',return_value=b'archive'), patch('routers.financial_ledger.record_prepared_export',side_effect=RuntimeError('private database error')):
            with self.assertRaises(HTTPException) as caught:
                await self.call([scenario])
        self.assertEqual(caught.exception.status_code,500)
        self.assertNotIn('private database',caught.exception.detail)
        self.assertTrue(scenario.file.closed)
