import copy
import unittest
from services.financial.pdf_candidates import _digest, PdfMappingError, bind_pdf_mapping
from services.financial.pdf_geometry_candidates import bind_pdf_grid_mapping
from services.financial.pdf_processing_manifest import validate_pdf_processing_manifest
from tests import test_financial_pdf_geometry_candidates as grids
from tests import test_financial_pdf_candidates as texts


def manifest():
    content=dict(schema_version='loupe.pdf_processing_manifest/1',recorded_at='2026-09-10T00:00:00+00:00',
        python_version='3.synthetic',packages={'PyMuPDF':'synthetic','pytesseract':None,'Pillow':None},
        source_files_sha256={name:'a'*64 for name in ('pdf_extraction.py','ocr_geometry.py','pdf_processing_manifest.py')},
        tesseract=dict(status='not_used',version=None),settings=dict(pdf_ocr_dpi=300,pdf_ocr_max_pixels=1000,
            pdf_ocr_page_timeout_seconds=60,pdf_ocr_max_concurrency=1,tesseract_lang='eng',max_pdf_pages=1000),
        limitation='Synthetic software fixture; not an actual extraction.')
    return dict(content=content,sha256=_digest(content))


class ProcessingManifestTests(unittest.TestCase):
    def test_hash_schema_and_private_extra_fields(self):
        self.assertIsNone(validate_pdf_processing_manifest(None))
        raw=manifest();checked=validate_pdf_processing_manifest(raw)
        checked['content']['packages']['Pillow']='changed'
        self.assertIsNone(raw['content']['packages']['Pillow'])
        for mutate in (lambda c:c['packages'].update(Pillow='changed'),lambda c:c.update(api_key='private'),lambda c:c.update(recorded_at='2026-01-01')):
            changed=copy.deepcopy(raw);mutate(changed['content'])
            with self.assertRaises(ValueError):validate_pdf_processing_manifest(changed)
            changed['sha256']=_digest(changed['content'])
            if 'api_key' in changed['content'] or changed['content']['recorded_at']=='2026-01-01':
                with self.assertRaises(ValueError):validate_pdf_processing_manifest(changed)

    def test_grid_provenance_changes_revision_and_is_retained(self):
        f=grids.GridBindingTests();f.setUp()
        try:
            original=f.mapping['source_revision']
            legacy=bind_pdf_grid_mapping(f.db,case_id=f.case,proposal=f.mapping).model_dump(mode='json')
            self.assertNotIn('processing_manifest',legacy)
            f.text.processing_manifest=manifest();f.db.commit()
            with self.assertRaises(PdfMappingError):bind_pdf_grid_mapping(f.db,case_id=f.case,proposal=f.mapping)
            from services.financial.pdf_geometry_candidates import pdf_grid_source_revision
            f.mapping['source_revision']=pdf_grid_source_revision(f.db,case_id=f.case,evidence_file_id=f.file,page_number=1)
            self.assertNotEqual(original,f.mapping['source_revision'])
            bound=bind_pdf_grid_mapping(f.db,case_id=f.case,proposal=f.mapping).model_dump(mode='json')
            self.assertEqual(bound['processing_manifest'],manifest())
            from services.financial.review_methods import pdf_review_methods
            doc={'pdf_review_history':{'mappings':[{'id':'synthetic','evidence_file_id':str(f.file),'snapshot':bound,'snapshot_sha256':_digest(bound)}]}}
            self.assertEqual(pdf_review_methods(doc)['methods'][0]['processing_manifest'],manifest())
        finally:f.tearDown()

    def test_text_mapping_preserves_legacy_and_binds_new_manifest(self):
        f=texts.PdfCandidateTests();f.setUp()
        try:
            self.assertNotIn('processing_manifest',bind_pdf_mapping(f.db,case_id=f.case,proposal=f.mapping).model_dump(mode='json'))
            f.source.processing_manifest=manifest();f.db.commit()
            with self.assertRaises(PdfMappingError):bind_pdf_mapping(f.db,case_id=f.case,proposal=f.mapping)
            f.mapping['source_revision']=f.revision()
            self.assertEqual(bind_pdf_mapping(f.db,case_id=f.case,proposal=f.mapping).processing_manifest,manifest())
        finally:f.tearDown()

    def test_report_groups_identical_preparation_and_retains_unknown_ocr(self):
        import json
        from tests import test_financial_ledger_snapshot as snapshots
        from services.financial.ledger_snapshot import LedgerSnapshot, render_ledger_report
        f=snapshots.LedgerSnapshotTests();f.setUp()
        try:
            document=json.loads(f.capture().content)
            snapshot={
                'proposal':dict(case_id=str(f.case.id),evidence_file_id='synthetic-file',source_revision='a'*64,schema_version='pdf-grid-mapping-v1'),
                'processing_manifest':manifest()}
            document['pdf_review_history']=dict(scope='Synthetic layout check',candidates=[],reviews=[],finalizations=[],review_states=[],
                mappings=[dict(id=str(i),evidence_file_id='synthetic-file',snapshot=snapshot,snapshot_sha256=_digest(snapshot)) for i in range(2)])
            content=json.dumps(document)
            report=render_ledger_report(LedgerSnapshot(content,_digest(document),len(content.encode())))
            self.assertEqual(report.count('Recorded PDF preparation for file'),1)
            self.assertIn('3.synthetic',report)
            self.assertIn('Not used',report)
        finally:f.tearDown()
