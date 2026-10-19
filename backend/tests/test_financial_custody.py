import unittest
from uuid import uuid4
from pydantic import ValidationError
from services.financial.custody import CustodyRequest, record_custody, source_custody
from services.financial.candidate_store import CandidateStoreError
from postgres.models.evidence import EvidenceFile
from tests import test_financial_duplicates as fixture


class CustodyTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.DuplicateTestCase(); self.f.setUp()
        self.document = self.f.make_document()
        self.file = self.f.db.get(EvidenceFile, self.document.evidence_file_id)
        self.actor = dict(name='Synthetic tester', email='test@example.invalid', user_id=str(self.f.user.id))
        self.body = dict(event_id=str(uuid4()), expected_source_sha256=self.file.sha256,
            event_kind='receipt', received_by='Synthetic recipient', reason='Synthetic test report only')
    def tearDown(self): self.f.tearDown()
    def write(self, **changes):
        return record_custody(self.f.db, case_id=self.f.case.id, file_id=self.file.id,
            request={**self.body, **changes}, actor=self.actor)
    def read(self): return source_custody(self.f.db, case_id=self.f.case.id, file_id=self.file.id)
    def test_empty_history_and_exact_retry(self):
        self.assertEqual(self.read()['events'], [])
        first=self.write(); self.f.db.commit()
        self.assertEqual(self.write(), first)
        self.assertEqual(len(self.read()['events']), 1)
        self.assertIsNone(first['report']['occurred_at'])
        self.assertEqual(first['evidence_sha256'], self.file.sha256)
        with self.assertRaises(CandidateStoreError): self.write(reason='Changed content')
    def test_correction_preserves_original_and_requires_same_source(self):
        original=self.write()
        corrected=self.write(event_id=str(uuid4()), event_kind='correction',
            corrects_event_id=original['id'], reason='Corrected recipient', received_by='Other recipient')
        self.assertEqual(len(self.read()['events']), 2)
        self.assertEqual(next(e for e in self.read()['events'] if e['id'] == original['id'])['report']['reason'], original['report']['reason'])
        self.assertEqual(corrected['report']['corrects_event_id'], original['id'])
        with self.assertRaises(CandidateStoreError): self.write(event_id=str(uuid4()), event_kind='correction', corrects_event_id=str(uuid4()))
    def test_changed_hash_and_foreign_case_refused(self):
        with self.assertRaises(CandidateStoreError): self.write(expected_source_sha256='0'*64)
        with self.assertRaises(CandidateStoreError):
            source_custody(self.f.db, case_id=self.f.other_case.id, file_id=self.file.id)
        with self.assertRaises(CandidateStoreError):
            record_custody(self.f.db, case_id=self.f.other_case.id, file_id=self.file.id, request=self.body, actor=self.actor)
        self.assertEqual(self.read()['events'], [])
    def test_certification_must_be_distinct_same_case_and_captures_hash(self):
        with self.assertRaises(CandidateStoreError): self.write(certification_file_id=str(self.file.id))
        with self.assertRaises(CandidateStoreError): self.write(certification_file_id=str(uuid4()))
        certificate_doc=self.f.make_document()
        certificate=self.f.db.get(EvidenceFile,certificate_doc.evidence_file_id)
        result=self.write(certification_file_id=str(certificate.id))
        self.assertEqual(result['report']['certification_sha256'], certificate.sha256)
    def test_timezone_and_receiver_and_correction_contract(self):
        for change in (dict(occurred_at='2026-09-10T12:00:00'),dict(received_by=None),dict(reason='  '),dict(event_kind='correction'),dict(corrects_event_id=str(uuid4()))):
            with self.assertRaises(ValidationError): CustodyRequest.model_validate({**self.body,**change})
        request=CustodyRequest.model_validate({**self.body,'occurred_at':'2026-09-10T12:00:00+01:00'})
        self.assertEqual(request.model_dump(mode='json')['occurred_at'],'2026-09-10T12:00:00+01:00')

    def test_readable_report_keeps_custody_fields_and_escapes_report_text(self):
        import hashlib, json
        from services.financial.ledger_snapshot import LedgerSnapshot, render_ledger_report, capture_ledger_snapshot
        self.write(reason='<script>untrusted</script>', acquisition_method='subpoena', native_file_status='requested')
        ledger=json.loads(capture_ledger_snapshot(self.f.db,case_id=self.f.case.id).content)['ledger']
        document=dict(ledger=ledger,limitations=[],processing_provenance=dict(limitation='Test scope',runs=[],custody_reports=[self.read()]))
        content=json.dumps(document)
        snapshot=LedgerSnapshot(content=content,sha256=hashlib.sha256(content.encode()).hexdigest(),byte_count=len(content.encode()))
        report=render_ledger_report(snapshot)
        self.assertIn('Received by',report)
        self.assertIn('Synthetic recipient',report)
        self.assertIn('subpoena',report)
        self.assertIn('requested',report)
        self.assertIn('&lt;script&gt;untrusted&lt;/script&gt;',report)
        self.assertNotIn('<script>untrusted',report)
