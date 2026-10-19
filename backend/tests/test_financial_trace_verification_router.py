import io
import json
import unittest
from unittest.mock import patch
from uuid import uuid4
from fastapi import UploadFile, HTTPException
from routers.financial_ledger import verify_saved_trace_support
from services.financial.ledger_summary import LedgerSummaryError


class TraceVerificationRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_case_pin_and_content_passed_and_upload_closed(self):
        case = uuid4(); upload = UploadFile(file=io.BytesIO(b'archive'))
        with patch('services.financial.trace_support_archive.verify_trace_support_archive', return_value={'case_id':str(case)}) as verify:
            response = await verify_saved_trace_support(case_id=case, archive=upload, expected_sha256='a'*64)
        verify.assert_called_once_with(b'archive', expected_case_id=case, expected_sha256='a'*64)
        self.assertEqual(json.loads(response.body), {'case_id':str(case)})
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertTrue(upload.file.closed)

    async def test_invalid_or_internal_error_closes_file_without_leaking_details(self):
        for exception, status in [(LedgerSummaryError('Invalid bundle'), 422), (RuntimeError('private storage details'), 500)]:
            upload = UploadFile(file=io.BytesIO(b'archive'))
            with patch('services.financial.trace_support_archive.verify_trace_support_archive', side_effect=exception):
                with self.assertRaises(HTTPException) as caught:
                    await verify_saved_trace_support(case_id=uuid4(), archive=upload, expected_sha256=None)
            self.assertEqual(caught.exception.status_code, status)
            self.assertNotIn('private storage', caught.exception.detail)
            self.assertTrue(upload.file.closed)
