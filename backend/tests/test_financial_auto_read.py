"""Statements are read and prepared without anyone starting a batch.

Pins: a Financial reading request joins the case's automatic batch (actor
System) and its statements reach the review queue with no batch click; exact
copies are not read again; the flag switches it all off; files already in
Financial are read only through the explicit action; the worker keeps few
automatic readings in flight; the status line says what is being read; the
Evidence detector recognises statement furniture and nothing else.
"""
import asyncio
import os
from pathlib import Path
from unittest import TestCase
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from postgres.base import Base
from postgres.models.financial_candidates import FinancialCandidateMapping, FinancialStatementReviewDraft
from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
from postgres.models.evidence import EvidenceFile, IngestionLog
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from services.financial import auto_read, import_batches as service
from services.financial.review_queue import case_review_queue, status_line
from services.financial.statement_detection import classify_text, detect
from tests import test_financial_statement_import as fixture_module

# The Financial file library (unread statement files) reads these.
FINANCIAL_SCOPE_TABLES = [FinancialCandidateMapping.__table__, FinancialStatementReviewDraft.__table__,
                          WorkspaceEntry.__table__, WorkspaceEntryLink.__table__]
STATEMENT_TEXT = ('Synthetic Bank N.A. Member FDIC\nAccount Number: TEST123\nStatement Period: January 1, 2023 - January 31, 2023\n'
                  'Opening Balance 100.00\nDate Description Deposits Withdrawals Balance\n01/02 Payment 10.00 110.00\n'
                  'Closing Balance 110.00\n' + 'Transaction detail line for the synthetic statement.\n' * 4)
BILLING_TEXT = ('Synthetic Residence Care\nSTATEMENT DATE DUE DATE ACCOUNT NUMBER 1234\nPrevious Balance 100.00\n'
                'Charges 50.00 Payments 25.00 Balance 125.00\n' + 'Monthly care charge line for the synthetic resident.\n' * 4)


class DetectorTests(TestCase):
    def test_statement_furniture_is_recognised_and_a_billing_statement_is_not(self):
        self.assertTrue(classify_text(STATEMENT_TEXT)['statement'])
        self.assertFalse(classify_text(BILLING_TEXT)['statement'])
        self.assertFalse(classify_text('')['statement'])
        self.assertFalse(classify_text('Opening Balance Account Number Bank')['statement'])  # too little text

    def test_a_pdf_without_text_or_an_unreadable_file_is_not_a_statement(self):
        import tempfile
        import fitz
        with tempfile.TemporaryDirectory() as directory:
            blank = Path(directory) / 'scan.pdf'
            with fitz.open() as document:
                document.new_page()
                document.save(blank)
            self.assertEqual(detect(blank)['reason'], 'no_text_layer')
            broken = Path(directory) / 'broken.pdf'
            broken.write_bytes(b'not a pdf')
            self.assertFalse(detect(broken)['statement'])
            self.assertFalse(detect(Path(directory) / 'missing.pdf')['statement'])


class TurnTests(TestCase):
    def test_automatic_files_start_reading_only_while_few_are_in_flight(self):
        files = [dict(status='processing', auto_read={}, last_checked_at='2'),
                 *[dict(status='waiting', auto_read={}) for _ in range(5)]]
        chosen = service._turn_candidates(files)
        self.assertEqual([i for i, _ in chosen], [0, 1])  # one reading + one start (IN_FLIGHT 2)
        files[1]['status'] = 'processing'
        self.assertEqual(sorted(i for i, _ in service._turn_candidates(files)), [0, 1])  # full: nothing new starts
        # A batch an investigator started keeps today's behaviour.
        manual = [dict(status='waiting') for _ in range(6)]
        self.assertEqual(len(service._turn_candidates(manual)), service.FILES_PER_TURN)

    def test_status_line_leads_with_reading_progress(self):
        counts = {k: 0 for k in ('imported', 'waiting', 'ready', 'copies', 'unreadable', 'unreadable_files', 'saving',
                                 'rechecking', 'left_unimported')}
        line = status_line(counts, dict(files_total=40, files_done=11, files_reading=29, files_waiting_to_start=0, paused=False))
        self.assertTrue(line.startswith('Reading 12 of 40 files…'), line)
        self.assertFalse(status_line(counts, dict(files_total=40, files_done=40, files_reading=0)).startswith('Reading'))
        paused = status_line(counts, dict(files_total=4, files_done=1, files_reading=3, paused=True))
        self.assertTrue(paused.startswith('Reading paused at 1 of 4 files'), paused)


class AutoReadBase(TestCase):
    def setUp(self):
        self.f = fixture_module.StatementImportTests('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()
        self.f.file.status = 'processed'
        Base.metadata.create_all(self.f.db.connection(), tables=[Batch.__table__, Item.__table__, IngestionLog.__table__,
            *FINANCIAL_SCOPE_TABLES])
        self.f.db.commit()

    def tearDown(self):
        self.f.tearDown()

    def advance(self, batch_id):
        process = AsyncMock(side_effect=AssertionError('Existing geometry must be reused'))
        asyncio.run(service.advance_batch(self.f.SessionLocal, batch_id, Path, process))

    def sweep(self):
        with patch('services.financial.auto_read.detect_enabled', return_value=False):
            return auto_read.sweep(self.f.SessionLocal, Path)

    def intake(self, *ids):
        with self.f.SessionLocal() as db:
            return auto_read.intake_pdf_review(db, case_id=self.f.case.id, file_ids=list(ids))

    def batches(self):
        with self.f.SessionLocal() as db:
            return list(db.query(Batch).filter(Batch.case_id == self.f.case.id))


class AutoReadTests(AutoReadBase):
    def test_a_financial_reading_reaches_the_queue_without_a_batch_click(self):
        to_read, copies = self.intake(self.f.file.id)
        self.assertEqual((to_read, copies), ([self.f.file.id], []))
        self.assertEqual(self.sweep()['added'], 1)
        [batch] = self.batches()
        self.assertEqual((batch.actor['name'], batch.actor['auto_read'], batch.status), ('System', True, 'preparing'))
        self.assertEqual(batch.files[0]['auto_read']['reason'], 'financial_upload')
        self.advance(batch.id)
        with self.f.SessionLocal() as db:
            self.assertEqual(db.get(Batch, batch.id).status, 'review')
            queue = case_review_queue(db, case_id=self.f.case.id, use_cache=False)
            history = [log.extra['action'] for log in db.query(IngestionLog).filter(IngestionLog.evidence_file_id == self.f.file.id)]
            mark = db.get(EvidenceFile, self.f.file.id).metadata_[auto_read.MARK]
        self.assertEqual(queue['counts']['ready'], 1, queue['counts'])
        self.assertEqual(queue['reading']['files_reading'], 0)
        self.assertIn('financial_auto_read', history)
        self.assertEqual(mark['state'], 'enrolled')
        # A second sweep, or the same file read again, adds nothing new.
        self.assertEqual(self.sweep()['added'], 0)
        self.intake(self.f.file.id)
        self.sweep()
        self.assertEqual(len(self.batches()), 1)
        self.assertEqual(len(self.batches()[0].files), 1)

    def test_an_exact_copy_is_named_and_not_read_again(self):
        self.intake(self.f.file.id)
        self.sweep()
        copy = self.f.evidence(self.f.file.sha256)
        self.f.db.commit()
        to_read, copies = self.intake(copy.id)
        self.assertEqual(to_read, [])
        self.assertEqual(copies[0]['copy_of_file_id'], str(self.f.file.id))
        self.sweep()
        [batch] = self.batches()
        self.assertEqual([f['file_id'] for f in batch.files], [str(self.f.file.id)])
        with self.f.SessionLocal() as db:
            self.assertEqual(db.get(EvidenceFile, copy.id).metadata_[auto_read.MARK]['state'], 'copy')

    def test_the_flag_switches_it_off(self):
        with patch.dict(os.environ, {'LOUPE_FINANCIAL_AUTO_READ_STATEMENTS': '0'}):
            self.assertEqual(self.intake(self.f.file.id), ([self.f.file.id], []))
            self.assertEqual(auto_read.sweep(self.f.SessionLocal, Path), dict(checked=0, added=0))
            record = EvidenceFile(case_id=self.f.case.id, original_filename='x.pdf', stored_path='/x.pdf', sha256='0' * 64)
            auto_read.mark_registered(record)
            self.assertNotIn(auto_read.MARK, record.metadata_ or {})
        self.assertEqual(self.batches(), [])

    def test_files_in_financial_never_read_are_read_only_by_the_explicit_action(self):
        from services.financial.file_scope import mark_financial_workspace
        with self.f.SessionLocal() as db:
            file = db.get(EvidenceFile, self.f.file.id)
            mark_financial_workspace(file, user_id=self.f.user.id)
            db.commit()
        self.sweep()
        self.assertEqual(self.batches(), [])  # nothing on deploy
        with self.f.SessionLocal() as db:
            self.assertEqual([f.id for f in auto_read.unread_statement_files(db, case_id=self.f.case.id)], [self.f.file.id])
            self.assertEqual(case_review_queue(db, case_id=self.f.case.id, use_cache=False)['reading']['unread_statement_files'], 1)
            result = auto_read.read_unread(db, case_id=self.f.case.id, actor=self.f.actor)
        self.assertEqual(result['added'], 1)
        with self.f.SessionLocal() as db:
            self.assertEqual(auto_read.unread_statement_files(db, case_id=self.f.case.id), [])
            progress = auto_read.reading_progress(db, case_id=self.f.case.id)
        self.assertEqual((progress['files_total'], progress['files_reading']), (1, 1))
        self.assertEqual(self.batches()[0].files[0]['auto_read']['requested_by']['name'], self.f.user.name)

    def test_an_evidence_upload_recognised_as_a_statement_is_read(self):
        import fitz
        path = Path(self.f._directory) / 'upload.pdf'
        with fitz.open() as document:
            page = document.new_page()
            page.insert_text((40, 60), STATEMENT_TEXT, fontsize=8)
            document.save(path)
        other = Path(self.f._directory) / 'letter.pdf'
        with fitz.open() as document:
            document.new_page().insert_text((40, 60), BILLING_TEXT, fontsize=8)
            document.save(other)
        with patch('services.financial.auto_read.detect_enabled', return_value=True), self.f.SessionLocal() as db:
            from services.evidence_db_storage import EvidenceDBStorage
            rows = EvidenceDBStorage.add_files(db, case_id=self.f.case.id, created_by_id=self.f.user.id, files_data=[
                dict(original_filename='upload.pdf', stored_path=str(path), sha256='d' * 64, size=1),
                dict(original_filename='letter.pdf', stored_path=str(other), sha256='e' * 64, size=1),
                dict(original_filename='photo.jpg', stored_path='/photo.jpg', sha256='c' * 64, size=1)])
            db.commit()
            ids = [row.id for row in rows]
            self.assertEqual([(row.metadata_ or {}).get(auto_read.MARK, {}).get('state') for row in rows],
                             ['pending', 'pending', None])
            result = auto_read.sweep(self.f.SessionLocal, Path)
        # The fixture's older unmarked PDF (not on disk) is checked too: the evidence backfill.
        self.assertEqual(result, dict(checked=3, added=1))
        with self.f.SessionLocal() as db:
            states = [db.get(EvidenceFile, i).metadata_.get(auto_read.MARK, {}).get('state') for i in ids]
        self.assertEqual(states, ['enrolled', 'not_statement', None])
        [batch] = self.batches()
        self.assertEqual([f['file_id'] for f in batch.files], [str(ids[0])])

    def test_evidence_pdfs_uploaded_before_detection_are_checked_too(self):
        """Files registered before automatic detection had no mark and were never checked (OPDMD66).

        The sweep gives them the same statement check as a new upload; a PDF
        already in Financial is still left to the explicit action.
        """
        import fitz
        from services.financial.file_scope import mark_financial_workspace
        paths = []
        for name, text in (('old-statement.pdf', STATEMENT_TEXT), ('old-letter.pdf', BILLING_TEXT),
                           ('old-financial.pdf', STATEMENT_TEXT + 'kept')):
            path = Path(self.f._directory) / name
            with fitz.open() as document:
                document.new_page().insert_text((40, 60), text, fontsize=8)
                document.save(path)
            paths.append(path)
        with self.f.SessionLocal() as db:
            rows = [EvidenceFile(id=uuid4(), case_id=self.f.case.id, original_filename=path.name, stored_path=str(path),
                                 sha256=str(i) * 64, status='unprocessed') for i, path in enumerate(paths)]
            db.add_all(rows)
            mark_financial_workspace(rows[2], user_id=self.f.user.id)
            db.commit()
            ids = [row.id for row in rows]
        with patch('services.financial.auto_read.detect_enabled', return_value=True):
            result = auto_read.sweep(self.f.SessionLocal, Path)
        # Also the fixture's own older PDFs: the saved one is in Financial, the other is checked.
        self.assertEqual(result, dict(checked=3, added=1))
        with self.f.SessionLocal() as db:
            states = [db.get(EvidenceFile, i).metadata_.get(auto_read.MARK, {}).get('state') for i in ids]
            fixture = {f.original_filename: (f.metadata_ or {}).get(auto_read.MARK, {}).get('state')
                       for f in db.query(EvidenceFile) if f.id not in ids}
        self.assertEqual(states, ['enrolled', 'not_statement', 'in_financial'])
        self.assertEqual(fixture, {'january-statement.pdf': 'in_financial', 'statement-1.pdf': 'not_statement'})
        [batch] = self.batches()
        self.assertEqual([(f['source_id'], f['auto_read']['reason']) for f in batch.files], [(str(ids[0]), 'detected')])
        with patch.dict(os.environ, {'LOUPE_FINANCIAL_AUTO_DETECT_BACKFILL': '0'}):
            self.assertFalse(auto_read.backfill_enabled())


class EvidenceProcessingTests(AutoReadBase):
    """Who put the file in Financial decides which file the statement reading runs on."""

    def pdf(self, name, text):
        import fitz
        path = Path(self.f._directory) / name
        with fitz.open() as document:
            document.new_page().insert_text((40, 60), text, fontsize=8)
            document.save(path)
        import hashlib
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def register(self, name, detect):
        from services.evidence_db_storage import EvidenceDBStorage
        path, sha = self.pdf(name, STATEMENT_TEXT + name)
        with patch('services.financial.auto_read.detect_enabled', return_value=detect), self.f.SessionLocal() as db:
            [row] = EvidenceDBStorage.add_files(db, case_id=self.f.case.id, created_by_id=self.f.user.id,
                files_data=[dict(original_filename=name, stored_path=str(path), sha256=sha, size=1)])
            db.commit()
            return row.id

    def run_batch(self):
        """One worker turn; returns the evidence ids the reading was requested for."""
        asked = []

        async def process(session, *, case_id, file_ids, **kwargs):
            asked.extend(file_ids)
            for identifier in file_ids:
                session.get(EvidenceFile, identifier).status = 'processing'
            session.commit()
            return dict(job_ids=[str(uuid4()) for _ in file_ids])
        [batch] = self.batches()
        asyncio.run(service.advance_batch(self.f.SessionLocal, batch.id, Path, process))
        return asked

    def test_a_detected_evidence_upload_is_read_from_a_copy_and_keeps_its_evidence_processing(self):
        original = self.register('detected.pdf', detect=True)
        with patch('services.financial.auto_read.detect_enabled', return_value=True):
            self.assertEqual(auto_read.sweep(self.f.SessionLocal, Path)['added'], 1)
        asked = self.run_batch()
        self.assertEqual(len(asked), 1)
        self.assertNotEqual(asked[0], original)
        with self.f.SessionLocal() as db:
            source = db.get(EvidenceFile, original)
            version = db.get(EvidenceFile, asked[0])
            self.assertEqual(source.status, 'unprocessed')  # the Evidence pipeline still processes it
            self.assertEqual(version.metadata_['statement_root_evidence_id'], str(original))
            self.assertEqual(version.sha256, source.sha256)
        # Evidence processing of the original is not refused or skipped.
        from services.evidence_processing_service import process_db_files
        with self.f.SessionLocal() as db, \
                patch('services.evidence_processing_service.reconcile_case_jobs', AsyncMock()), \
                patch('services.evidence_processing_service.gate_document_processing'), \
                patch('services.evidence_processing_service.build_processing_snapshot', return_value={}), \
                patch('services.evidence_processing_service.evidence_engine_client.upload_file_paths_batch',
                      AsyncMock(return_value=[dict(id=str(uuid4()))])), \
                patch('services.evidence_processing_service.get_subscriber') as subscriber:
            subscriber.return_value.track_jobs = AsyncMock()
            result = asyncio.run(process_db_files(db, case_id=self.f.case.id, file_ids=[original]))
        self.assertEqual(result['file_count'], 1)

    def test_a_file_put_in_financial_is_read_itself(self):
        original = self.register('chosen.pdf', detect=False)
        self.intake(original)
        self.assertEqual(self.sweep()['added'], 1)
        self.assertEqual(self.run_batch(), [original])
