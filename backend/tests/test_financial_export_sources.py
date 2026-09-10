import hashlib
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
from postgres.models.evidence import EvidenceFile
from services.financial.export_sources import capture_export_sources
from services.financial.ledger_summary import LedgerSummaryError
from services.financial.ledger_snapshot import LedgerExport, LedgerSnapshot, ledger_export_archive
from tests import test_financial_duplicates as fixture

class ExportSourceTests(fixture.DuplicateTestCase):
    def setUp(self):
        super().setUp()
        self.doc=self.make_copy()
        self.file=self.db.get(EvidenceFile,self.doc.evidence_file_id)
        self.content=b'%PDF-1.4\noriginal test bytes\n'
        self.path=Path(self._directory)/'original.pdf';self.path.write_bytes(self.content)
        self.digest=hashlib.sha256(self.content).hexdigest()
        self.file.sha256=self.doc.sha256_at_ingestion=self.digest
        self.file.stored_path=str(self.path);self.db.commit()
        self.snapshot={'ledger':{'readings':[{'source':{'evidence_file_id':str(self.file.id),'sha256_at_ingestion':self.digest}}]}}
    def capture(self,**changes):
        return capture_export_sources(self.db,self.snapshot,**{'case_id':self.case.id,'resolve_path':lambda p:Path(p),**changes})
    def test_exact_bytes_verified_once_per_file_and_no_disk_path_exported(self):
        self.snapshot['ledger']['readings']*=2
        files=self.capture()
        self.assertEqual(len(files),1)
        self.assertEqual(files[0]['content'],self.content)
        self.assertEqual(files[0]['sha256'],self.digest)
        self.assertNotIn('stored_path',files[0])
        self.assertFalse(self.db.dirty or self.db.new)
        self.assertEqual(self.path.read_bytes(),self.content)
    def test_byte_drift_refuses_whole_bundle(self):
        self.path.write_bytes(b'changed')
        with self.assertRaises(LedgerSummaryError):self.capture()
    def test_missing_file_and_non_regular_file_refused(self):
        self.path.unlink()
        with self.assertRaises(LedgerSummaryError):self.capture()
        self.path.mkdir()
        with self.assertRaises(LedgerSummaryError):self.capture()
    def test_scope_and_recorded_digest_drift_refused(self):
        with self.assertRaises(LedgerSummaryError):self.capture(case_id=self.other_case.id)
        self.file.sha256='f'*64;self.db.commit()
        with self.assertRaises(LedgerSummaryError):self.capture()
    def test_no_registered_file_and_conflicting_digests_refused(self):
        self.snapshot['ledger']['readings'].append({'source':{'evidence_file_id':str(self.file.id),'sha256_at_ingestion':'f'*64}})
        with self.assertRaises(LedgerSummaryError):self.capture()
        self.snapshot['ledger']['readings']=[{'source':{'evidence_file_id':None,'sha256_at_ingestion':self.digest}}]
        with self.assertRaises(LedgerSummaryError):self.capture()
    def test_limits_refuse_without_returning_a_partial_bundle(self):
        with patch('services.financial.export_sources.MAX_SOURCE_BYTES',2):
            with self.assertRaises(LedgerSummaryError):self.capture()
        with patch('services.financial.export_sources.MAX_SOURCE_FILES',0):
            with self.assertRaises(LedgerSummaryError):self.capture()
    def test_archive_path_does_not_follow_original_filename(self):
        self.file.original_filename='../../escape.PDF';self.db.commit()
        files=self.capture()
        self.assertEqual(files[0]['archive_path'],f'source-files/{self.file.id}.pdf')
        self.assertNotIn('..',files[0]['archive_path'])
    def test_archive_contains_identical_verified_bytes_and_manifest_hash(self):
        files=self.capture()
        raw=json.dumps({'ledger':{'case_id':str(self.case.id),'readings':[]}})
        snapshot=LedgerSnapshot(raw,hashlib.sha256(raw.encode()).hexdigest(),len(raw.encode()))
        export=LedgerExport(snapshot,'{}',files,True)
        with patch('services.financial.ledger_snapshot.render_ledger_report',return_value='<html>report</html>'):
            archive=ledger_export_archive(export)
        with ZipFile(io.BytesIO(archive)) as zipfile:
            manifest=json.loads(zipfile.read('manifest.json'))
            record=manifest['source_files'][0]
            self.assertEqual(zipfile.read(record['archive_path']),self.content)
            self.assertEqual(record['sha256'],hashlib.sha256(zipfile.read(record['archive_path'])).hexdigest())
            self.assertTrue(manifest['source_files_verified_against_ingestion'])
            self.assertNotIn('content',record)
