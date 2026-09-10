import hashlib
import json
import unittest
from datetime import date
from uuid import uuid4
from services.financial.indirect_review import IndirectReviewInput, METHODS, REQUIREMENTS, evaluate_indirect_review
from services.financial.ledger_summary import LedgerSummaryError


class IndirectReviewTests(unittest.TestCase):
    def setUp(self):
        self.case,self.file=uuid4(),uuid4()
        self.source=dict(id=str(self.file),case_id=str(self.case),filename='Synthetic statement',sha256='a'*64)
    def request(self, method='cash_t'):
        reference=dict(basis='Synthetic checked schedule',source_file_id=self.file,source_location='Page1synthetic table')
        return IndirectReviewInput(method=method,currency='GBP',start_date=date(2026,1,1),end_date=date(2026,12,31),subject='Synthetic subject',
            entries={key:dict(amount_minor='0',**reference) for key,_,_,_ in METHODS[method]['terms']},
            requirements={key:dict(status='reviewed',**reference) for key in REQUIREMENTS})
    def result(self, request, sources=None):
        envelope=evaluate_indirect_review(self.case,request,[self.source] if sources is None else sources)
        self.assertEqual(hashlib.sha256(envelope['scenario_json'].encode()).hexdigest(),envelope['scenario_sha256'])
        self.assertEqual(len(envelope['scenario_json'].encode()),envelope['scenario_byte_count'])
        return json.loads(envelope['scenario_json'])
    def test_all_method_signs_and_exact_large_values(self):
        for method in METHODS:
            request=self.request(method)
            for index,entry in enumerate(request.entries.values()):entry.amount_minor=str(9007199254740993+index)
            result=self.result(request)
            expected=sum(sign*int(request.entries[key].amount_minor) for key,_,sign,_ in METHODS[method]['terms'])
            self.assertEqual(result['difference_minor'],str(expected))
            self.assertTrue(result['review_fields_complete'])
            self.assertFalse(result['applied'])
    def test_unknown_amount_is_never_zero(self):
        request=self.request();request.entries['cash_uses'].amount_minor=None
        result=self.result(request)
        self.assertIsNone(result['difference_minor'])
        self.assertEqual(result['missing'][0]['id'],'cash_uses')
    def test_every_prerequisite_requires_review_basis_and_source_location(self):
        for key in REQUIREMENTS:
            for field,value in [('status','unresolved'),('basis',' '),('source_location',''),('source_file_id',None)]:
                request=self.request();setattr(request.requirements[key],field,value)
                result=self.result(request)
                self.assertFalse(result['review_fields_complete'])
                self.assertIsNone(result['difference_minor'])
    def test_wrong_method_keys_sources_dates_and_negative_unsigned_amounts_fail(self):
        request=self.request()
        changes=[request.model_copy(update={'end_date':date(2025,1,1)}),request.model_copy(update={'entries':{'unexpected':next(iter(request.entries.values()))}})]
        negative=self.request();negative.entries['cash_uses'].amount_minor='-1';changes.append(negative)
        for changed in changes:
            with self.assertRaises(LedgerSummaryError):self.result(changed)
        for sources in [[],[self.source,self.source],[{**self.source,'case_id':str(uuid4())}]]:
            with self.assertRaises(LedgerSummaryError):self.result(request,sources)
    def test_negative_difference_is_not_clamped_and_signed_adjustment_is_allowed(self):
        request=self.request();request.entries['cash_sources'].amount_minor='100';self.assertEqual(self.result(request)['difference_minor'],'-100')
        request=self.request('bank_deposits');request.entries['cash_change'].amount_minor='-10';self.assertEqual(self.result(request)['difference_minor'],'-10')


class IndirectReviewRouteTests(unittest.TestCase):
    def test_sources_are_case_scoped_and_missing_sources_do_not_calculate(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from fastapi import HTTPException
        from routers import financial_ledger as router
        case, file = uuid4(), uuid4()
        body = IndirectReviewInput(method='cash_t', currency='GBP', start_date=date(2026,1,1), end_date=date(2026,12,31), subject='Synthetic', entries={'cash_uses': {'source_file_id':file}})
        for source in [None, SimpleNamespace(case_id=uuid4())]:
            with patch.object(router, 'evaluate_indirect_review') as calculate:
                with self.assertRaises(HTTPException) as caught:
                    router.run_indirect_review(body, case, Mock(get=Mock(return_value=source)))
                self.assertEqual(caught.exception.status_code, 404)
                calculate.assert_not_called()
        source=SimpleNamespace(id=file, case_id=case, original_filename='Source.pdf',sha256='a'*64)
        result=router.run_indirect_review(body,case,Mock(get=Mock(return_value=source)))
        value=json.loads(result['scenario_json'])
        self.assertIsNone(value['difference_minor'])
        self.assertEqual(value['sources'][0]['id'], str(file))

    def test_both_routes_inherit_case_view_access(self):
        from routers import financial_ledger as router
        for suffix in ['indirect-review', 'indirect-review-methods']:
            route=next(r for r in router.router.routes if r.path=='/api/financial/'+suffix)
            calls={dependency.call for dependency in route.dependant.dependencies}
            self.assertIn(router.get_current_db_user,calls)
            self.assertIn(router._require_ledger_case_access,calls)

    def test_domain_refusal_and_unexpected_failure_are_distinct(self):
        from unittest.mock import Mock, patch
        from fastapi import HTTPException
        from routers import financial_ledger as router
        body=IndirectReviewInput(method='cash_t',currency='GBP',start_date=date(2026,1,1),end_date=date(2026,12,31),subject='Synthetic')
        for error,status in [(LedgerSummaryError('Missing basis'),422),(RuntimeError('private database detail'),500)]:
            with patch.object(router,'evaluate_indirect_review',side_effect=error):
                with self.assertRaises(HTTPException) as caught:router.run_indirect_review(body,uuid4(),Mock())
                self.assertEqual(caught.exception.status_code,status)
                self.assertNotIn('private',caught.exception.detail)
