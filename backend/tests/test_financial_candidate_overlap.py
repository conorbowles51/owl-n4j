import unittest
from copy import deepcopy
from uuid import UUID,uuid4
from unittest.mock import patch
from services.financial.candidate_overlap import check_candidate_source_reuse
from services.financial.candidate_reviews import review_candidate
from services.financial.candidate_store import CandidateStoreError
from services.financial.pdf_candidates import pdf_mapping_source_revision
from tests import test_financial_candidate_store as fixture


class CandidateReuseTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.CandidateStoreTests();self.f.setUp();self.first=self.f.save()

    def tearDown(self):self.f.tearDown()

    def check(self):return check_candidate_source_reuse(self.f.db,case_id=self.f.case,evidence_file_id=self.f.file)

    def second(self):
        self.f.mapping['columns'][1]['meaning']='balance'
        return self.f.save()

    def test_equal_amounts_in_distinct_rows_are_not_source_reuse(self):
        result=self.check()
        self.assertEqual(result['source_reuse_pairs'],0)
        self.assertEqual(result['unavailable_pairs'],0)
        self.assertEqual(result['pairs_examined'],1)
        self.assertFalse(result['applied'])
        self.assertFalse(self.f.db.new or self.f.db.dirty or self.f.db.deleted)

    def test_changed_meanings_cannot_hide_the_same_stored_source_row(self):
        self.second();result=self.check()
        self.assertEqual(result['source_reuse_pairs'],2)
        self.assertEqual({x['kind'] for x in result['findings']},{'same_stored_row'})
        self.assertEqual(result['counts'],dict(pending=4,resolved=0,rejected=0))

    def test_rejection_removes_active_claim_but_remains_counted_and_changes_revision(self):
        second=self.second();before=self.check()
        row=second['candidates'][0]
        review_candidate(self.f.db,case_id=self.f.case,candidate_id=UUID(row['id']),actor=self.f.actor,
            request=dict(expected_revision=row['review_revision'],status='rejected',reason='Repeated source nomination'))
        result=self.check()
        self.assertEqual(result['counts']['rejected'],1)
        self.assertEqual(result['source_reuse_pairs'],1)
        self.assertNotEqual(result['revision'],before['revision'])

    def test_source_drift_is_refused_instead_of_called_clean(self):
        self.f.text.source_locations=[];self.f.db.commit()
        with self.assertRaises(CandidateStoreError):self.check()

    def test_wrong_case_refused(self):
        with self.assertRaises(CandidateStoreError) as caught:
            check_candidate_source_reuse(self.f.db,case_id=uuid4(),evidence_file_id=self.f.file)
        self.assertEqual(caught.exception.status_code,404)

    def test_pair_cap_is_explicitly_incomplete(self):
        self.second()
        with patch('services.financial.candidate_overlap._MAX_PAIRS',1):result=self.check()
        self.assertFalse(result['comparison_complete'])
        self.assertEqual(result['pairs_examined'],1)
        self.assertEqual(result['total_pairs'],6)

    def test_detail_cap_does_not_hide_total_findings(self):
        self.second()
        with patch('services.financial.candidate_overlap._MAX_FINDINGS',1):result=self.check()
        self.assertTrue(result['findings_truncated'])
        self.assertEqual(result['source_reuse_pairs'],2)
        self.assertEqual(len(result['findings']),1)

    def test_mapping_limit_is_refused_without_partial_success(self):
        with patch('services.financial.candidate_overlap._MAX_MAPPINGS',0):
            with self.assertRaises(CandidateStoreError) as caught:self.check()
            self.assertEqual(caught.exception.status_code,422)

    def test_canonical_and_grid_locations_on_same_page_are_not_assumed_comparable(self):
        content=self.f.text.content;start=content.index('1234')
        proposal=dict(schema_version='pdf-text-mapping-v1',case_id=str(self.f.case),evidence_file_id=str(self.f.file),
            source_revision=pdf_mapping_source_revision(self.f.db,case_id=self.f.case,evidence_file_id=self.f.file),
            table_id=str(uuid4()),start_char=0,end_char=len(content),columns=[dict(column_index=0,meaning='amount')],
            rows=[dict(row_index=0,cells=[dict(column_index=0,source=dict(start_char=start,end_char=start+4,text='1234'))])])
        self.f.save(proposal=proposal)
        result=self.check()
        self.assertEqual(result['unavailable_pairs'],2)
        proposal['table_id']=str(uuid4());self.f.save(proposal=proposal)
        result=self.check()
        self.assertEqual(result['source_reuse_pairs'],1)
        self.assertIn('overlapping_source_text',{x['kind'] for x in result['findings']})
