import hashlib
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4
from fastapi import HTTPException
from pydantic import ValidationError
from routers.financial_ledger import TraceSupportDownload, download_trace_support
from services.financial.ledger_summary import LedgerSummaryError


class TraceSupportRouterTests(unittest.TestCase):
    def test_case_and_authenticated_actor_bound_to_download(self):
        case = uuid4()
        user = SimpleNamespace(id=uuid4(), name='Local tester', email='fixture@example.test')
        with patch('services.financial.trace_support_archive.build_trace_support_archive', return_value=b'archive') as build:
            response = download_trace_support(TraceSupportDownload(scenarios=['original'], privilege_marking='confidential'), case_id=case, current_user=user)
        args = build.call_args.kwargs
        self.assertEqual(args['expected_case_id'], case)
        self.assertEqual(args['preparation']['generated_by']['id'], str(user.id))
        self.assertEqual(args['preparation']['privilege_marking'], 'confidential')
        self.assertEqual(response.headers['x-loupe-case-id'], str(case))
        self.assertEqual(response.headers['x-loupe-archive-sha256'], hashlib.sha256(b'archive').hexdigest())
        self.assertEqual(response.headers['x-loupe-scenario-sha256'], hashlib.sha256(b'original').hexdigest())

    def test_bad_scenario_returns_422_and_unknown_fields_refused(self):
        user = SimpleNamespace(id=uuid4(), name='Local', email='local@example.test')
        with patch('services.financial.trace_support_archive.build_trace_support_archive', side_effect=LedgerSummaryError('Scenario changed')):
            with self.assertRaises(HTTPException) as caught:
                download_trace_support(TraceSupportDownload(scenarios=['original']), case_id=uuid4(), current_user=user)
        self.assertEqual(caught.exception.status_code, 422)
        for fields in ({'scenarios':[]}, {'scenarios':['x'], 'generated_by':'spoof'}, {'scenarios':['x'], 'privilege_marking':'arbitrary'}):
            with self.assertRaises(ValidationError): TraceSupportDownload.model_validate(fields)
