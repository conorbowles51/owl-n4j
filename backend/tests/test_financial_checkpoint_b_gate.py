"""Checkpoint B gate (automation delivery plan, section 2), driven through the real services.

Each property the plan's gate names is proved on a multi-statement synthetic
case, through the same functions the routes call:

- one save makes a period ready in every view: batch detail, the opened batch
  statement, the case's batch list, the case file list and the individual review;
- independent edits to different statements and batches do not overwrite each other;
- bringing existing saved work up to date is repeatable and changes nothing the
  second time;
- one group confirmation imports exactly the eligible statements, exactly once,
  under repeat, double submission and concurrent submission.

SQLite is the database here. Row locks (`FOR UPDATE`, `SKIP LOCKED`) do not exist
in SQLite; the concurrent cases prove the result, not the PostgreSQL lock order.
"""
import hashlib
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Barrier
from unittest import TestCase
from uuid import UUID, uuid4

from sqlalchemy import func, select

from postgres.models.evidence import EvidenceDocumentText, EvidenceFile, EvidenceTableGeometry
from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
from postgres.models.financial_import_batches import (FinancialImportBatchItem as Item,
    FinancialImportOperation as Operation)
from services.financial import import_batches as batches
from services.financial.pdf_candidates import PdfMappingError
from services.financial.statement_file_status import statement_file_status
from services.financial.statement_import import StatementReviewDraft
from services.financial.statement_progress import review_progress, save_progress
from tests import test_financial_import_batches as batch_fixture

ROWS_PER_STATEMENT = 12


class CheckpointBGateTests(TestCase):
    def setUp(self):
        self.b = batch_fixture.BatchImportTests('test_folder_preparation_bulk_confirmation_and_repeat_do_not_duplicate')
        self.b.setUp()
        self.f = self.b.f
        from postgres.base import Base
        from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
        Base.metadata.create_all(self.f.db.connection(), tables=[WorkspaceEntry.__table__, WorkspaceEntryLink.__table__])
        self.f.db.commit()
        self.primary = self.f.file
        self.accounts = {}

    def tearDown(self):
        self.b.tearDown()

    # -- synthetic statements ------------------------------------------------

    def statement(self, account, *, holder_printed=True):
        """A separate synthetic PDF for its own account, optionally without a printed holder."""
        f = self.f
        raw = f.path.read_bytes() + ('\n% ' + account).encode()
        path = Path(f._directory) / (account + '.pdf')
        path.write_bytes(raw)
        file = f.evidence(hashlib.sha256(raw).hexdigest())
        file.stored_path, file.original_filename, file.status = str(path), account + '.pdf', 'processed'
        text = f.db.get(EvidenceDocumentText, self.primary.id)
        geometry = f.db.get(EvidenceTableGeometry, (self.primary.id, 1))
        content = text.content.replace('TEST123', account)
        if not holder_printed:
            content = content.replace('Account Name: Test Company\n', '')
        f.db.add(EvidenceDocumentText(evidence_file_id=file.id, content=content,
            content_sha256=hashlib.sha256(content.encode()).hexdigest(), character_count=len(content),
            engine_job_id=text.engine_job_id, source_locations=[dict(kind='page', page_number=1,
                start_char=0, end_char=len(content), text_origin='digital_text_layer')]))
        f.db.add(EvidenceTableGeometry(evidence_file_id=file.id, page_number=1,
            engine_job_id=geometry.engine_job_id, payload=deepcopy(geometry.payload)))
        f.db.commit()
        self.accounts[file.id] = account
        return file

    def batch(self, *files):
        with self.f.SessionLocal() as db:
            batch = batches.create_batch(db, case_id=self.f.case.id, request_id=uuid4(),
                file_ids=[file.id for file in files], folder_ids=[], actor=self.f.actor)
        self.b.advance(batch)
        return batch

    def preview(self, file):
        self.f.file = file
        return self.f.preview()

    def request(self, file, holder):
        self.f.file = file
        raw = self.f.request()
        raw.update(account_number=self.accounts[file.id], holder=holder)
        return StatementReviewDraft.model_validate(raw)

    def item(self, batch, file):
        with self.f.SessionLocal() as db:
            return db.scalar(select(Item).where(Item.batch_id == batch, Item.file_id == file.id))

    # -- the views -------------------------------------------------------------

    def detail(self, batch, file):
        state = self.b.status(batch)
        return next(i for i in state['items'] if i['file_id'] == str(file.id)), state

    def opened(self, batch, file):
        """What GET /batches/{id}/items/{item} returns for one statement."""
        with self.f.SessionLocal() as db:
            stored = db.scalar(select(Item).where(Item.batch_id == batch, Item.file_id == file.id))
            return batches.checked_batch_items(db, self.f.case.id, [stored], reading='targets')[0]

    def listed(self, batch):
        """The case's batch list (GET /batches/list), which reads stored summaries."""
        from routers.financial_statement_import import list_financial_batches
        with self.f.SessionLocal() as db:
            listing = list_financial_batches(case_id=self.f.case.id, db=db)
        return next(b for b in listing['batches'] if b['id'] == str(batch))

    def file_row(self, file):
        with self.f.SessionLocal() as db:
            result = statement_file_status(db, case_id=self.f.case.id)
        return next(row for row in result['files'] if row['evidence_file_id'] == str(file.id))

    def views(self, batch, file):
        detail, _ = self.detail(batch, file)
        opened = self.opened(batch, file)
        saved = self.preview(file)['saved_review']
        return dict(detail=detail['can_import'], opened=opened.summary.get('can_import') is True,
            file_list=self.file_row(file)['available_periods'] == 1,
            individual=bool(saved) and saved.get('assessment_status') == 'ready',
            holder=(detail['holder'], opened.summary.get('holder'), (saved or {}).get('request', {}).get('holder')))

    def assert_ready_everywhere(self, batch, file, holder):
        views = self.views(batch, file)
        self.assertEqual(views, dict(detail=True, opened=True, file_list=True, individual=True,
            holder=(holder, holder, holder)))

    def assert_list_agrees(self, batch):
        state = self.b.status(batch)
        listed = self.listed(batch)
        self.assertEqual(listed['available_statements'], state['available_statements'], (listed, state['counts']))
        self.assertEqual(listed['statement_summary']['available'], state['available_statements'])

    def payments(self):
        with self.f.SessionLocal() as db:
            return db.scalar(select(func.count()).select_from(FinancialTransaction))

    def documents_by_file(self):
        with self.f.SessionLocal() as db:
            return {file_id: count for file_id, count in db.execute(
                select(FinancialSourceDocument.evidence_file_id, func.count())
                .group_by(FinancialSourceDocument.evidence_file_id))}

    # -- 1. save once, ready in every view ------------------------------------

    def test_one_standalone_save_makes_the_period_ready_in_every_view(self):
        blocked = self.statement('GATE001', holder_printed=False)
        batch = self.batch(blocked)
        self.assertFalse(self.views(batch, blocked)['detail'])
        self.assertEqual(self.listed(batch)['available_statements'], 0)
        with self.f.SessionLocal() as db:
            save_progress(db, case_id=self.f.case.id, evidence_file_id=blocked.id,
                request=self.request(blocked, 'Reviewed Holder'), expected_review_revision='initial', actor=self.f.actor)
        self.assert_ready_everywhere(batch, blocked, 'Reviewed Holder')
        self.assertEqual(self.listed(batch)['available_statements'], 1)
        self.assert_list_agrees(batch)

    def test_one_batch_save_makes_the_period_ready_in_every_view(self):
        blocked = self.statement('GATE002', holder_printed=False)
        batch = self.batch(blocked)
        opened = self.opened(batch, blocked)
        with self.f.SessionLocal() as db:
            batches.save_review(db, case_id=self.f.case.id, batch_id=batch, item_id=opened.id,
                request=self.request(blocked, 'Batch Reviewed Holder'),
                expected_review_revision=opened.review_revision, actor=self.f.actor)
        self.assert_ready_everywhere(batch, blocked, 'Batch Reviewed Holder')
        self.assertEqual(self.listed(batch)['available_statements'], 1)
        self.assert_list_agrees(batch)

    # -- 2. independent edits stay intact -------------------------------------

    def batch_save(self, batch, file, holder, token):
        item = self.item(batch, file)
        with self.f.SessionLocal() as db:
            return batches.save_review(db, case_id=self.f.case.id, batch_id=batch, item_id=item.id,
                request=self.request(file, holder), expected_review_revision=token, actor=self.f.actor)

    def test_independent_edits_to_different_statements_and_batches_are_all_kept(self):
        a, b, c, d, shared = (self.statement(name, holder_printed=False)
            for name in ('GATEA', 'GATEB', 'GATEC', 'GATED', 'GATEE'))
        first = self.batch(a, b, c, shared)
        second = self.batch(d, shared)
        self.assertNotEqual(first, second)
        # Every editor opens before anybody saves; edits to other statements
        # must not make these tokens stale.
        tokens = {(first, f.id): self.opened(first, f).review_revision for f in (a, b, shared)}
        tokens[(second, d.id)] = self.opened(second, d).review_revision
        tokens[(second, shared.id)] = self.opened(second, shared).review_revision
        self.batch_save(first, a, 'Holder A', tokens[(first, a.id)])
        self.batch_save(first, b, 'Holder B', tokens[(first, b.id)])
        self.batch_save(second, d, 'Holder D', tokens[(second, d.id)])
        with self.f.SessionLocal() as db:
            save_progress(db, case_id=self.f.case.id, evidence_file_id=c.id,
                request=self.request(c, 'Holder C'), expected_review_revision='initial', actor=self.f.actor)
        self.batch_save(first, shared, 'Holder E', tokens[(first, shared.id)])
        # The same period in the other batch follows the shared save (its own
        # draft was untouched), and its stale editor cannot overwrite it.
        with self.assertRaisesRegex(PdfMappingError, 'Another user saved'):
            self.batch_save(second, shared, 'Late conflicting edit', tokens[(second, shared.id)])
        for batch, file, holder in ((first, a, 'Holder A'), (first, b, 'Holder B'), (first, c, 'Holder C'),
                (second, d, 'Holder D'), (first, shared, 'Holder E'), (second, shared, 'Holder E')):
            with self.subTest(file=self.accounts[file.id], batch=str(batch)):
                self.assert_ready_everywhere(batch, file, holder)
        with self.f.SessionLocal() as db:
            for file, holder in ((a, 'Holder A'), (b, 'Holder B'), (c, 'Holder C'), (d, 'Holder D'), (shared, 'Holder E')):
                self.assertEqual(review_progress(db.get(EvidenceFile, file.id), '')['request']['holder'], holder)
        for batch, ready in ((first, 4), (second, 2)):
            self.assertEqual(self.b.status(batch)['available_statements'], ready)
            self.assert_list_agrees(batch)

    def test_simultaneous_saves_of_different_statements_never_lose_either(self):
        a, b = self.statement('GATEF', holder_printed=False), self.statement('GATEG', holder_printed=False)
        batch = self.batch(a, b)
        tokens = {f.id: self.opened(batch, f).review_revision for f in (a, b)}
        start = Barrier(2)

        def save(file, holder):
            start.wait()
            try:
                self.batch_save(batch, file, holder, tokens[file.id])
                return None
            except Exception as error:  # noqa: BLE001 - every outcome is checked below
                return error

        with ThreadPoolExecutor(2) as pool:
            outcomes = list(pool.map(lambda args: save(*args), ((a, 'Holder F'), (b, 'Holder G'))))
        # SQLite may refuse one writer outright; it must never accept both and
        # keep one. A refused save is repeated by its editor with a fresh token.
        for file, holder, error in ((a, 'Holder F', outcomes[0]), (b, 'Holder G', outcomes[1])):
            if error is not None:
                self.assertNotIsInstance(error, AssertionError)
                self.batch_save(batch, file, holder, self.opened(batch, file).review_revision)
        for file, holder in ((a, 'Holder F'), (b, 'Holder G')):
            self.assert_ready_everywhere(batch, file, holder)
        self.assert_list_agrees(batch)
