from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID, uuid4

from sqlalchemy import select
from postgres.models.evidence import EvidenceDocumentText, EvidenceTableGeometry, EvidenceFile
from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from services.financial import bulk_statement_details as service, import_batches
from services.financial.pdf_candidates import PdfMappingError, _digest
from services.financial.statement_details import read_statement_details
from services.financial.statement_import import read_statement_import, confirm_statement_import
from tests.test_financial_statement_import import StatementImportTests as Fixture


class BulkStatementDetailsTests(TestCase):
    def setUp(self):
        self.f = Fixture('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()
        path = Path(self.f._directory) / 'second.pdf'
        path.write_bytes(b'%PDF-1.4\nSecond synthetic statement')
        self.second = self.f.evidence(sha256(path.read_bytes()).hexdigest())
        self.second.stored_path = str(path)
        text = self.f.db.get(EvidenceDocumentText, self.f.file.id)
        content = text.content.replace('Test Company', 'Second Company').replace('TEST123', 'TEST456')
        job_id = uuid4()
        self.f.db.add(EvidenceDocumentText(evidence_file_id=self.second.id,
            content=content, content_sha256=sha256(content.encode()).hexdigest(),
            character_count=len(content), engine_job_id=job_id, source_locations=text.source_locations))
        geometry = self.f.db.scalar(select(EvidenceTableGeometry).where(EvidenceTableGeometry.evidence_file_id==self.f.file.id))
        self.f.db.add(EvidenceTableGeometry(evidence_file_id=self.second.id, page_number=1,
            engine_job_id=job_id, payload=deepcopy(geometry.payload)))
        self.f.db.commit()

    def tearDown(self):
        self.f.tearDown()

    def listing(self, selection=None):
        with self.f.SessionLocal() as db:
            return service.list_statements(db, case_id=self.f.case.id,
                selection=selection or service.Selection(file_ids=[self.f.file.id, self.second.id]))

    def request(self, changes=None, mode='replace'):
        rows = self.listing()['items']
        self.assertEqual(len(rows), 2)
        request = service.BulkEdit(targets=[{key: row[key] for key in ('file_id','source_id','statement_id','revision')} for row in rows],
            changes=changes or dict(holder='Reviewed Company'), mode=mode, request_id=uuid4())
        with self.f.SessionLocal() as db:
            preview = service.preview(db, case_id=self.f.case.id, request=request)
        return request.model_copy(update={'preview_revision': preview['preview_revision']})

    def save(self, request, case_id=None):
        with self.f.SessionLocal() as db:
            return service.save(db, case_id=case_id or self.f.case.id, request=request, actor=self.f.actor)

    def import_second(self):
        with self.f.SessionLocal() as db:
            proposal = read_statement_import(db, case_id=self.f.case.id, evidence_file_id=self.second.id)
        return confirm_statement_import(session_factory=self.f.SessionLocal, case_id=self.f.case.id,
            evidence_file_id=self.second.id, request=import_batches.initial_request(proposal), actor=self.f.actor, resolve_path=Path)

    def test_mixed_saved_and_draft_fill_missing_then_replace_reopen_preserves_payments(self):
        receipt = self.f.confirm()
        with self.f.SessionLocal() as db:
            original = deepcopy(db.get(FinancialSourceDocument, UUID(receipt['source_document_id'])).metadata_['statement_import_original'])
            payments = {r.id: (r.amount_minor, r.transaction_date) for r in db.scalars(select(FinancialTransaction))}
        request = self.request(dict(holder='Should not replace', institution='Reviewed Bank'), mode='fill_missing')
        result = self.save(request)
        self.assertEqual((result['updated'], result['imported'], result['drafts']), (0,0,0))
        rows = self.listing()['items']
        self.assertEqual({row['values']['holder'] for row in rows}, {'Test Company', 'Second Company'})
        self.assertEqual({row['values']['institution'] for row in rows}, {'Synthetic Bank'})
        self.save(self.request(dict(institution='Reviewed Bank')))
        self.assertEqual({row['values']['institution'] for row in self.listing()['items']}, {'Reviewed Bank'})
        self.save(self.request())
        self.assertEqual({row['values']['holder'] for row in self.listing()['items']}, {'Reviewed Company'})
        with self.f.SessionLocal() as db:
            self.assertEqual({r.id: (r.amount_minor, r.transaction_date) for r in db.scalars(select(FinancialTransaction))}, payments)
            self.assertEqual(db.get(FinancialSourceDocument, UUID(receipt['source_document_id'])).metadata_['statement_import_original'], original)

    def test_saved_retry_returns_same_receipt_and_no_duplicate_history(self):
        first = self.f.confirm(); self.import_second()
        request = self.request()
        result = self.save(request)
        self.assertEqual(self.save(request), result)
        with self.f.SessionLocal() as db:
            history = db.get(FinancialSourceDocument, UUID(first['source_document_id'])).metadata_['statement_details_history']
            self.assertEqual(len(history), 1)
        with self.assertRaisesRegex(PdfMappingError, 'different changes'):
            self.save(request.model_copy(update={'mode':'fill_missing'}))

    def test_stale_preview_changes_nothing(self):
        self.f.confirm()
        stale = self.request()
        self.save(self.request(dict(institution='Other reviewer bank')))
        before = self.listing()
        with self.assertRaisesRegex(PdfMappingError, 'changed since selection'):
            self.save(stale)
        self.assertEqual(self.listing(), before)

    def test_late_failure_rolls_back_all_saved_statements(self):
        self.f.confirm(); self.import_second()
        request = self.request()
        before = self.listing()
        actual = service.update_statement_details
        calls = []
        def failing(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise RuntimeError('injected second statement failure')
            return actual(*args, **kwargs)
        with patch.object(service, 'update_statement_details', side_effect=failing):
            with self.assertRaisesRegex(RuntimeError, 'injected'):
                self.save(request)
        self.assertEqual(self.listing(), before)

    def test_currency_keeps_printed_values_and_draft_row_corrections(self):
        self.f.confirm()
        with self.f.SessionLocal() as db:
            proposal = read_statement_import(db, case_id=self.f.case.id, evidence_file_id=self.second.id)
            raw = import_batches.initial_request(proposal)
            payment = next(r for r in raw['rows'] if not r['excluded'])
            payment['description'] = 'Investigator corrected description'
            file = db.get(EvidenceFile, self.second.id)
            file.metadata_ = dict(financial_review_progress={'': dict(request=raw, review_revision=_digest(raw), saved_at='test', saved_by={})})
            db.commit()
        self.save(self.request(dict(currency='KWD')))
        rows = self.listing()['items']
        self.assertEqual({row['values']['currency'] for row in rows}, {'KWD'})
        with self.f.SessionLocal() as db:
            changed = db.get(EvidenceFile, self.second.id).metadata_['financial_review_progress']['']['request']
            new = next(r for r in changed['rows'] if r['id']==payment['id'])
            self.assertEqual(new['description'], payment['description'])
            self.assertEqual(int(new['amount_minor']), int(payment['amount_minor']) * 10)

    def test_pending_import_and_active_worker_are_not_overwritten(self):
        request = self.request()
        batch_id = uuid4()
        with self.f.SessionLocal() as db:
            db.add(Batch(id=batch_id, case_id=self.f.case.id, created_by=self.f.user.id,
                status='ready', actor={}, files=[]))
            db.flush()
            db.add(Item(id=uuid4(), batch_id=batch_id, file_id=self.second.id, statement_key='', status='pending_import', summary={}))
            db.commit()
        with self.assertRaisesRegex(PdfMappingError, 'importing'):
            self.save(request)
        with self.f.SessionLocal() as db:
            batch = db.get(Batch, batch_id)
            batch.worker_token = str(uuid4()); batch.lease_until = datetime.now(timezone.utc)+timedelta(minutes=1); db.commit()
        with self.assertRaisesRegex(PdfMappingError, 'still being processed'):
            self.save(request)

    def test_batch_and_individual_draft_share_saved_fields_and_import_them(self):
        batch_id = uuid4()
        with self.f.SessionLocal() as db:
            batch = Batch(id=batch_id, case_id=self.f.case.id, created_by=self.f.user.id, status='ready', actor={}, files=[])
            db.add(batch); db.commit()
            for file in (self.f.file, self.second):
                import_batches.prepare_reviews(db, batch, dict(file_id=str(file.id), source_id=str(file.id), filename=file.original_filename))
        self.assertEqual(len(self.listing(service.Selection(batch_id=batch_id))['items']), 2)
        self.save(self.request())
        with self.f.SessionLocal() as db:
            items = list(db.scalars(select(Item).where(Item.batch_id==batch_id)))
            self.assertEqual({item.review_request['holder'] for item in items}, {'Reviewed Company'})
            raw = next(i.review_request for i in items if i.file_id==self.second.id)
        result = confirm_statement_import(session_factory=self.f.SessionLocal, case_id=self.f.case.id,
            evidence_file_id=self.second.id, request=raw, actor=self.f.actor, resolve_path=Path)
        with self.f.SessionLocal() as db:
            saved = read_statement_details(db, case_id=self.f.case.id, source_id=UUID(result['source_document_id']))
            self.assertEqual(saved['details']['holder'], 'Reviewed Company')

    def test_case_boundaries_and_preview_required(self):
        request = self.request()
        with self.assertRaisesRegex(PdfMappingError, 'not in this case'):
            self.save(request, uuid4())
        with self.assertRaisesRegex(PdfMappingError, 'preview'):
            self.save(request.model_copy(update={'preview_revision': None}))
        with self.assertRaisesRegex(PdfMappingError, 'Select each'):
            self.save(request.model_copy(update={'targets': [request.targets[0]]*2}))

    def test_invalid_dates_are_rejected_against_each_statement(self):
        with self.assertRaisesRegex(PdfMappingError, 'start must'):
            self.request(dict(period_start='2026-02-01', period_end='2026-01-01'))
        with self.assertRaises(ValueError):
            service.Changes(period_start='2026-02-30')

    def test_unprepared_file_is_explained_not_silently_included(self):
        with self.f.SessionLocal() as db:
            db.delete(db.get(EvidenceDocumentText, self.second.id)); db.commit()
        result = self.listing()
        self.assertEqual(len(result['items']), 1)
        self.assertIn('Prepare this PDF', result['notices'][0]['message'])
