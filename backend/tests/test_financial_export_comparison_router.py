import io
import unittest
from unittest.mock import patch
from uuid import uuid4
from fastapi import UploadFile, HTTPException
from routers.financial_ledger import compare_saved_ledger_exports
from services.financial.ledger_summary import LedgerSummaryError


class ExportComparisonRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_uploaded_captures_bound_to_case_and_files_closed(self):
        case = uuid4()
        before, after = UploadFile(file=io.BytesIO(b'before')), UploadFile(file=io.BytesIO(b'after'))
        with patch('services.financial.export_comparison.compare_ledger_exports', return_value={'status':'same_captured_content'}) as compare:
            result = await compare_saved_ledger_exports(case_id=case, before=before, after=after)
        compare.assert_called_once_with(b'before', b'after', expected_case_id=case)
        self.assertEqual(result['status'], 'same_captured_content')
        self.assertTrue(before.file.closed and after.file.closed)

    async def test_invalid_capture_refused_and_uploaded_files_closed(self):
        before, after = UploadFile(file=io.BytesIO(b'before')), UploadFile(file=io.BytesIO(b'after'))
        with patch('services.financial.export_comparison.compare_ledger_exports', side_effect=LedgerSummaryError('Invalid bundle')):
            with self.assertRaises(HTTPException) as caught:
                await compare_saved_ledger_exports(case_id=uuid4(), before=before, after=after)
        self.assertEqual(caught.exception.status_code, 422)
        self.assertTrue(before.file.closed and after.file.closed)
