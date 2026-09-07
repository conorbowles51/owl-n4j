import asyncio
import unittest
from copy import deepcopy
from uuid import uuid4
from unittest.mock import patch
from fastapi import HTTPException
from services.financial.candidate_sources import list_candidate_sources, read_candidate_source
from services.financial.pdf_candidates import PdfMappingError
from services.financial.pdf_geometry_candidates import bind_pdf_grid_mapping
from tests import test_financial_pdf_geometry_candidates as fixture


class CandidateSourceTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.GridBindingTests()
        self.f.setUp()

    def tearDown(self):
        self.f.tearDown()

    def read(self, **changes):
        f = self.f
        return read_candidate_source(f.db, **dict(case_id=f.case, evidence_file_id=f.file,
            page_number=1, table_index=0, **changes))

    def test_listing_is_case_scoped_and_paginated(self):
        f = self.f
        page = list_candidate_sources(f.db, case_id=f.case, limit=1)
        self.assertEqual(page['items'], [dict(evidence_file_id=str(f.file), filename='synthetic.pdf', page_number=1)])
        self.assertFalse(page['has_more'])
        self.assertEqual(list_candidate_sources(f.db, case_id=uuid4())['items'], [])
        self.assertEqual(list_candidate_sources(f.db, case_id=f.case, offset=1)['items'], [])

    def test_exact_cells_can_be_submitted_without_offsets_or_guesses(self):
        source = self.read()
        proposal = dict(schema_version='pdf-grid-mapping-v1', case_id=source['case_id'],
            evidence_file_id=source['evidence_file_id'], page_number=source['page_number'],
            table_index=source['table_index'], source_revision=source['source_revision'],
            columns=[dict(column_index=c, meaning='unknown') for c in source['columns']],
            rows=[dict(row_index=r['row_index'], cells=[{k:c[k] for k in ('column_index','expected_text')}
                  for c in r['cells']]) for r in source['rows']])
        result = bind_pdf_grid_mapping(self.f.db, case_id=self.f.case, proposal=proposal)
        self.assertEqual(len(result.candidates), 2)
        self.assertEqual(result.candidates[1].cells[1].text, '1234')
        self.assertFalse(source['applied'])
        self.assertFalse(self.f.db.new or self.f.db.dirty or self.f.db.deleted)

    def test_wrong_case_refused(self):
        with self.assertRaises(PdfMappingError) as caught:
            read_candidate_source(self.f.db, case_id=uuid4(), evidence_file_id=self.f.file, page_number=1)
        self.assertEqual(caught.exception.status_code, 404)

    def test_missing_table_is_not_an_empty_success(self):
        with self.assertRaises(PdfMappingError) as caught:
            read_candidate_source(self.f.db, case_id=self.f.case, evidence_file_id=self.f.file, page_number=1, table_index=2)
        self.assertEqual(caught.exception.status_code, 404)

    def test_stale_text_job_refused(self):
        self.f.geometry.engine_job_id = uuid4()
        self.f.db.commit()
        with self.assertRaises(PdfMappingError): self.read()

    def test_overlapping_cells_refused(self):
        payload = deepcopy(self.f.payload)
        payload[0]['table']['values'][1]['locator'] = payload[0]['table']['values'][0]['locator']
        self.f.update_geometry(payload)
        with self.assertRaises(PdfMappingError): self.read()

    def test_long_text_is_not_silently_truncated(self):
        payload = deepcopy(self.f.payload)
        payload[0]['table']['values'][0]['text'] = 'x' * 4097
        self.f.update_geometry(payload)
        with self.assertRaises(PdfMappingError) as caught: self.read()
        self.assertEqual(caught.exception.status_code, 422)

    def test_invalid_limits(self):
        for params in ({'limit':0}, {'offset':-1}, {'limit':True}, {'limit':101}):
            with self.subTest(params=params), self.assertRaises(PdfMappingError):
                list_candidate_sources(self.f.db, case_id=self.f.case, **params)

    def test_routes_preserve_scope_and_errors(self):
        from routers import financial_ledger as router
        f = self.f
        with patch.object(router, 'read_candidate_source', return_value={'source':'checked'}) as call:
            self.assertEqual(asyncio.run(router.get_candidate_source(f.file, 1, f.case, 0, f.db)), {'source':'checked'})
            call.assert_called_once_with(f.db, case_id=f.case, evidence_file_id=f.file, page_number=1, table_index=0)
        with patch.object(router, 'list_candidate_sources', side_effect=PdfMappingError('Source changed',409)):
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(router.get_candidate_sources(f.case, 25, 0, f.db))
            self.assertEqual(caught.exception.status_code,409)
