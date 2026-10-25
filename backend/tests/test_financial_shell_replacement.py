"""An empty legacy import ("shell") of a file gives way to a statement of the same bytes, linked and reversible.

Synthetic statements only. The shell is built as the live ones look (BNB2,
lesson 13 of fin-queue): a saved copy of the file's bytes with no statement
named, a period with no printed dates, no payment and no incomplete record.
It stood as the saved copy of every statement of those bytes, so the import
writer refused the statement ("already has imported transactions") and the
queue held it ("Already saved through another batch"), while nothing of the
statement was in the ledger.
"""
import hashlib
from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select

from postgres.models.evidence import EvidenceDocumentText, EvidenceTableGeometry, IngestionLog
from postgres.models.financial import (AdjudicationEvent, FinancialSourceDocument, FinancialStatementPeriod,
                                       FinancialTransaction)
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from services.financial import queue_save
from services.financial import saved_reading_replacement as replacement
from services.financial.duplicate_decisions import DuplicateDecisionError, decide_duplicate, duplicate_revision
from services.financial.pdf_candidates import PdfMappingError
from tests import test_financial_statement_import as statement_import_fixture
from tests import test_financial_review_queue as review_queue_tests


def _logs(fixture):
    from postgres.base import Base
    Base.metadata.create_all(fixture.db.connection(), tables=[IngestionLog.__table__])
    fixture.db.commit()


def same_bytes_copy(f):
    """Another upload of the fixture's file: same bytes, its own evidence row, text and geometry."""
    original = f.file
    path = Path(f._directory) / f'copy-{uuid4().hex[:8]}.pdf'
    path.write_bytes(Path(original.stored_path).read_bytes())
    copied = f.evidence(original.sha256)
    copied.stored_path = str(path)
    copied.status = original.status
    text = f.db.get(EvidenceDocumentText, original.id)
    geometry = f.db.get(EvidenceTableGeometry, (original.id, 1))
    f.db.add(EvidenceDocumentText(evidence_file_id=copied.id, content=text.content,
        content_sha256=text.content_sha256, character_count=text.character_count,
        engine_job_id=text.engine_job_id, source_locations=deepcopy(text.source_locations)))
    f.db.add(EvidenceTableGeometry(evidence_file_id=copied.id, page_number=1,
        engine_job_id=geometry.engine_job_id, payload=deepcopy(geometry.payload)))
    f.db.commit()
    return copied


def make_shell(f, file, *, keep_payment=False, keep_dates=False):
    """Save ``file`` as the legacy shells were saved: then nothing of it is dated or paid."""
    current = f.file
    f.file = file
    try:
        receipt = f.confirm_legacy(f.request())
    finally:
        f.file = current
    shell_id = UUID(receipt['source_document_id'])
    with f.SessionLocal() as db:
        document = db.get(FinancialSourceDocument, shell_id)
        request = dict(document.metadata_.get('statement_import_request') or {})
        if not keep_dates:
            # As the live shells were saved: no statement details either.
            request.update(period_start='', period_end='', account_number='', holder='', institution='')
        document.metadata_ = {**document.metadata_, 'statement_import_statement_id': None, 'statement_incomplete_records': [],
                              'statement_import_request': request}
        if not keep_dates:
            evidence = db.get(type(file), file.id)
            progress = deepcopy((evidence.metadata_ or {}).get('financial_review_progress') or {})
            for saved in progress.values():
                if isinstance(saved, dict) and isinstance(saved.get('request'), dict):
                    saved['request'].update(period_start='', period_end='', account_number='', holder='', institution='')
            # The live shells' files carry no stored copy decision (they predate them).
            evidence.metadata_ = {**{k: v for k, v in (evidence.metadata_ or {}).items()
                                     if k != 'financial_duplicate_dispositions'}, 'financial_review_progress': progress}
        rows = list(db.scalars(select(FinancialTransaction.id).where(FinancialTransaction.source_document_id == shell_id)))
        if not keep_payment:
            db.execute(delete(FinancialTransaction).where(FinancialTransaction.source_document_id == shell_id))
        if not keep_dates:
            for period in db.scalars(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id == shell_id)):
                period.period_start = period.period_end = None
                period.period_start_source = period.period_end_source = 'absent'
                period.closing_balance_minor, period.closing_balance_source = None, 'absent'
                period.credit_total_minor = period.debit_total_minor = 0
                period.transaction_count = 0
                period.reconciliation_status = 'unavailable'
        db.commit()
        assert rows, 'the fixture statement has payments to take away'
    return shell_id


class ShellWriterTests(TestCase):
    def setUp(self):
        self.f = statement_import_fixture.StatementImportTests('test_file_reading_is_shared_across_requests_and_follows_stored_edits')
        self.f.setUp()
        _logs(self.f)
        self.case_id = self.f.case.id

    def tearDown(self):
        self.f.tearDown()

    def admitted_rows(self):
        with self.f.SessionLocal() as db:
            return db.scalar(select(func.count()).select_from(FinancialTransaction).where(
                FinancialTransaction.ledger_status == 'admitted'))

    def document(self, document_id):
        with self.f.SessionLocal() as db:
            return db.get(FinancialSourceDocument, document_id)

    def saved(self):
        """The statement's import: its new saved copy's id, or None when the writer refused or ignored it."""
        try:
            receipt = self.f.confirm()
        except PdfMappingError:
            return None
        return UUID(receipt['source_document_id']) if receipt.get('created') and receipt.get('source_document_id') else None

    def test_a_statement_of_the_same_bytes_is_saved_and_the_shell_set_aside_linked_and_restorable(self):
        shell_id = make_shell(self.f, same_bytes_copy(self.f))
        with self.f.SessionLocal() as db:
            self.assertTrue(replacement.is_shell(db, db.get(FinancialSourceDocument, shell_id)))
            self.assertTrue(replacement.standing_shell(db, db.get(FinancialSourceDocument, shell_id)))
        self.assertEqual(self.admitted_rows(), 0, 'the shell holds nothing')

        receipt = self.f.confirm()
        new_id = UUID(receipt['source_document_id'])
        self.assertTrue(receipt['created'])
        self.assertGreater(receipt['transaction_count'], 0)
        self.assertEqual(self.admitted_rows(), receipt['transaction_count'])
        shell, new = self.document(shell_id), self.document(new_id)
        self.assertEqual((shell.status, shell.superseded_by_id, new.status), ('superseded', new_id, 'admitted'))
        with self.f.SessionLocal() as db:
            event = db.scalar(select(AdjudicationEvent).where(AdjudicationEvent.subject_id == shell_id)
                              .order_by(AdjudicationEvent.subject_sequence.desc()).limit(1))
            self.assertEqual((event.decision, event.actor_name, event.after['basis']),
                             ('supersede_duplicate', 'system: reader replacement', replacement.SHELL_BASIS))
            self.assertIsNotNone(db.scalar(select(IngestionLog).where(
                IngestionLog.extra['action'].as_string() == 'financial_empty_shell_replaced')))
            # Kept, not deleted: the shell and its period are still there.
            self.assertEqual(db.scalar(select(func.count()).select_from(FinancialStatementPeriod).where(
                FinancialStatementPeriod.source_document_id == shell_id)), 1)

        # Reversible: restoring the shell brings back exactly what it held (nothing).
        with self.f.SessionLocal() as db:
            shell = db.get(FinancialSourceDocument, shell_id)
            decide_duplicate(db, case_id=self.case_id, document_id=shell_id, action='restore',
                             expected_revision=duplicate_revision(db, shell), actor=self.f.actor, reason='test restore')
        self.assertEqual(self.document(shell_id).status, 'admitted')
        self.assertEqual(self.admitted_rows(), receipt['transaction_count'])

    def test_a_saved_copy_with_a_payment_is_not_a_shell_and_still_holds_the_statement(self):
        shell_id = make_shell(self.f, same_bytes_copy(self.f), keep_payment=True)
        with self.f.SessionLocal() as db:
            self.assertFalse(replacement.is_shell(db, db.get(FinancialSourceDocument, shell_id)))
        self.assertIsNone(self.saved())
        self.assertEqual(self.document(shell_id).status, 'admitted')

    def test_a_saved_copy_with_printed_dates_is_not_a_shell(self):
        shell_id = make_shell(self.f, same_bytes_copy(self.f), keep_dates=True)
        with self.f.SessionLocal() as db:
            self.assertFalse(replacement.is_shell(db, db.get(FinancialSourceDocument, shell_id)))
        self.assertIsNone(self.saved())
        self.assertEqual(self.document(shell_id).status, 'admitted')

    def test_switch_off_the_shell_stands_as_before(self):
        shell_id = make_shell(self.f, same_bytes_copy(self.f))
        with patch.object(replacement, 'ENABLED', False):
            self.assertIsNone(self.saved())
        self.assertEqual(self.document(shell_id).status, 'admitted')
        self.assertEqual(self.admitted_rows(), 0)

    def test_the_set_aside_refuses_anything_but_a_shell_of_the_same_bytes(self):
        shell_id = make_shell(self.f, same_bytes_copy(self.f), keep_payment=True)
        with self.f.SessionLocal() as db:
            shell = db.get(FinancialSourceDocument, shell_id)
            other = FinancialSourceDocument(id=uuid4(), case_id=self.case_id, evidence_file_id=shell.evidence_file_id,
                                            sha256_at_ingestion='0' * 64, document_type='statement_review',
                                            status='admitted', proof_class=shell.proof_class, metadata_={})
            self.assertIsNotNone(replacement.shell_link_refusal(db, shell, other))
        with self.f.SessionLocal() as db:
            shell = db.get(FinancialSourceDocument, shell_id)
            with self.assertRaises(DuplicateDecisionError):
                decide_duplicate(db, case_id=self.case_id, document_id=shell_id, action='exclude',
                                 expected_revision=duplicate_revision(db, shell), primary_id=shell_id,
                                 expected_primary_revision=duplicate_revision(db, shell), actor=replacement.ACTOR,
                                 reason='test', match='empty_shell')


class ShellQueueTests(review_queue_tests.QueueReadTests):
    # The queue's own tests run in their module.
    locals().update({name: None for name in dir(review_queue_tests.QueueReadTests) if name.startswith('test_')})

    def setUp(self):
        super().setUp()
        _logs(self.f)

    def save(self, ids):
        with self.f.SessionLocal() as db:
            return queue_save.save_statements(db, case_id=self.f.case.id, item_ids=ids, actor=self.f.actor,
                                              request_id=uuid4())

    def shell(self, **kwargs):
        """A shell of the same bytes on another upload, saved before this file was prepared (the live order)."""
        copy = same_bytes_copy(self.f)
        return copy, make_shell(self.f, copy, **kwargs)

    def items_imported_as(self, batch_id, copy, shell_id):
        """Items of a later batch over the other upload, born 'imported' as the shell for the same statement
        (the live shape)."""
        with self.f.SessionLocal() as db:
            batch = db.get(Batch, batch_id)
            other = Batch(id=uuid4(), case_id=batch.case_id, created_by=batch.created_by, status='review',
                          actor=deepcopy(batch.actor), files=[])
            db.add(other); db.flush()
            for record in db.query(Item).filter(Item.batch_id == batch_id):
                db.add(Item(id=uuid4(), batch_id=other.id, file_id=copy.id, statement_key=record.statement_key,
                            status='imported', summary={**deepcopy(record.summary), 'source_document_id': str(shell_id)}))
            db.commit()

    def test_a_statement_whose_only_saved_copy_is_a_shell_is_saved_from_the_queue(self):
        copy, shell_id = self.shell()
        batch = self.create(); self.advance(batch)
        queue = self.queue()
        self.assertEqual(queue['counts']['ready'], 1, queue['counts'])
        entry = queue['ready'][0]
        self.items_imported_as(batch, copy, shell_id)

        result = self.save([entry['id']])
        self.assertEqual((result['queued'], result['held']), (1, []), result)
        self.advance(batch)
        with self.f.SessionLocal() as db:
            item = db.get(Item, UUID(entry['id']))
            self.assertEqual(item.status, 'imported')
            new_id = UUID(item.summary['source_document_id'])
            self.assertNotEqual(new_id, shell_id)
            shell = db.get(FinancialSourceDocument, shell_id)
            self.assertEqual((shell.status, shell.superseded_by_id), ('superseded', new_id))
            self.assertGreater(db.scalar(select(func.count()).select_from(FinancialTransaction).where(
                FinancialTransaction.source_document_id == new_id, FinancialTransaction.ledger_status == 'admitted')), 0)

    def test_a_real_saved_copy_still_holds_the_statement(self):
        # A saved copy holding a payment is real: the statement reads as saved and is not offered again.
        copy, shell_id = self.shell(keep_payment=True)
        batch = self.create(); self.advance(batch)
        counts = self.queue()['counts']
        self.assertEqual((counts['imported'], counts['ready']), (1, 0), counts)
        with self.f.SessionLocal() as db:
            self.assertEqual(db.get(FinancialSourceDocument, shell_id).status, 'admitted')
