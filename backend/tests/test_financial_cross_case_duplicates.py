from unittest.mock import patch, Mock
import unittest
from fastapi import HTTPException
from services.financial.cross_case_duplicates import compare_case_documents
from services.financial.duplicate_query import DuplicateQueryLimitError
from tests.test_financial_duplicates import DuplicateTestCase

class CrossCaseComparisonTests(DuplicateTestCase):
    def test_matching_hash_and_readings_are_separate_without_writes(self):
        left=self.make_copy(sha256='a'*64)
        right=self.make_copy(case=self.other_case,run=self.other_run,account=self.other_account,sha256='a'*64)
        result=compare_case_documents(self.db,self.case.id,self.other_case.id)
        self.assertFalse(result['applied'])
        self.assertEqual(len(result['matches']),1)
        match=result['matches'][0]
        self.assertEqual(match['left']['document_id'],str(left.id))
        self.assertEqual(match['right']['document_id'],str(right.id))
        self.assertTrue(match['matching_ingestion_hash'])
        self.assertFalse(self.db.new or self.db.dirty)
        self.assertEqual(left.status,'admitted')
        self.assertEqual(right.status,'admitted')

    def test_distinct_sources_without_stored_identity_match_are_not_called_duplicates(self):
        self.make_copy()
        self.other_account.identity_key='different-recorded-identity'
        self.db.commit()
        self.make_copy(case=self.other_case,run=self.other_run,account=self.other_account)
        result=compare_case_documents(self.db,self.case.id,self.other_case.id)
        self.assertEqual(result['matches'],[])
        self.assertEqual(result['compared'][str(self.case.id)],1)

    def test_complete_bounds_refuse_partial_scans(self):
        self.make_copy()
        self.make_copy(case=self.other_case,run=self.other_run,account=self.other_account)
        for bound in ('MAX_DOCUMENTS','MAX_ROWS','MAX_MATCHES'):
            with self.subTest(bound=bound), patch('services.financial.cross_case_duplicates.'+bound,0):
                with self.assertRaises(DuplicateQueryLimitError):compare_case_documents(self.db,self.case.id,self.other_case.id)

class CrossCaseAuthorizationTests(unittest.TestCase):
    def test_inaccessible_comparison_never_queries_documents_and_hides_existence(self):
        from routers.financial_ledger import get_cross_case_duplicates
        from uuid import uuid4
        for code in (403,404):
            with patch('routers.case_access.authorize_case_view',side_effect=HTTPException(code,'private')), patch('services.financial.cross_case_duplicates.compare_case_documents') as compare:
                with self.assertRaises(HTTPException) as caught:get_cross_case_duplicates(uuid4(),uuid4(),Mock(),Mock())
                self.assertEqual(caught.exception.status_code,403)
                self.assertNotIn('private',caught.exception.detail)
                compare.assert_not_called()
