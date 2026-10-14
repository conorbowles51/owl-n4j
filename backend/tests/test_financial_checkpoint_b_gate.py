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
in SQLite, and plain reads run outside a transaction, so the concurrent cases prove
only what holds without those locks. Two workers writing the same accepted statement
at once are kept to one ledger entry by the Case row lock in the strict writer, with
no database constraint behind it; on SQLite they write it twice. That property is
covered only by tests/test_financial_batch_import_lock_postgres.py, which needs the
disposable local PostgreSQL.
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

    def statement(self, account, *, holder_printed=True, revised=False):
        """A separate synthetic PDF for its own account, optionally without a printed holder.

        `revised` reads one payment description and its date differently, as a
        second reading or version of the same account and period would. (Equal
        money with other wording is a duplicate since r1-reproduced.)
        """
        f = self.f
        name = account + ('-revised' if revised else '')
        raw = f.path.read_bytes() + ('\n% ' + name).encode()
        path = Path(f._directory) / (name + '.pdf')
        path.write_bytes(raw)
        file = f.evidence(hashlib.sha256(raw).hexdigest())
        file.stored_path, file.original_filename, file.status = str(path), name + '.pdf', 'processed'
        text = f.db.get(EvidenceDocumentText, self.primary.id)
        geometry = f.db.get(EvidenceTableGeometry, (self.primary.id, 1))
        content = text.content.replace('TEST123', account)
        if not holder_printed:
            content = content.replace('Account Name: Test Company\n', '')
        f.db.add(EvidenceDocumentText(evidence_file_id=file.id, content=content,
            content_sha256=hashlib.sha256(content.encode()).hexdigest(), character_count=len(content),
            engine_job_id=text.engine_job_id, source_locations=[dict(kind='page', page_number=1,
                start_char=0, end_char=len(content), text_origin='digital_text_layer')]))
        payload = deepcopy(geometry.payload)
        if revised:
            cell = next(v for v in payload[0]['table']['values'] if v['row'] == 2 and v['column'] == 1)
            cell['text'] = 'Revised source payment detail'
            cell = next(v for v in payload[0]['table']['values'] if v['row'] == 2 and v['column'] == 0)
            cell['text'] = '2023-03-19'
        f.db.add(EvidenceTableGeometry(evidence_file_id=file.id, page_number=1,
            engine_job_id=geometry.engine_job_id, payload=payload))
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

    def test_batch_list_applies_the_same_overlap_hold_as_batch_detail(self):
        """Two readings of one account and period: both are held for a comparison decision."""
        copy = self.statement('OV12345678')
        overlapping = self.statement('OV12345678', revised=True)
        batch = self.batch(copy, overlapping)
        opened = self.opened(batch, overlapping)
        with self.f.SessionLocal() as db:
            batches.save_review(db, case_id=self.f.case.id, batch_id=batch, item_id=opened.id,
                request=self.request(overlapping, 'Test Company'),
                expected_review_revision=opened.review_revision, actor=self.f.actor)
        state = self.b.status(batch)
        self.assertEqual(state['available_statements'], 0, state['counts'])
        self.assertTrue(all(i['coverage_review']['candidates'] for i in state['items']))
        self.assert_list_agrees(batch)
        with self.f.SessionLocal() as db:
            with self.assertRaisesRegex(PdfMappingError, 'no new statement records'):
                batches.queue_import(db, case_id=self.f.case.id, batch_id=batch,
                    expected_revision=state['ready_revision'], actor=self.f.actor)

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

    # -- 3. bringing existing saved work up to date is repeatable --------------

    def stored_state(self, batch):
        with self.f.SessionLocal() as db:
            items = {str(i.file_id): (i.status, i.review_request, i.summary)
                for i in db.scalars(select(Item).where(Item.batch_id == batch))}
            files = {str(f.id): f.metadata_ for f in db.scalars(select(EvidenceFile).where(
                EvidenceFile.case_id == self.f.case.id))}
        return deepcopy(items), deepcopy(files)

    def save_without_batch_refresh(self, file, holder):
        """A save as the code before 541b15b9 left it: shared draft written, batch item untouched."""
        from unittest.mock import patch
        with self.f.SessionLocal() as db, patch.object(batches, 'refresh_file_readiness',
                return_value=dict(refreshed=0, skipped=0, remaining=0)):
            save_progress(db, case_id=self.f.case.id, evidence_file_id=file.id,
                request=self.request(file, holder), expected_review_revision='initial', actor=self.f.actor)

    def assert_upgrade_repeatable(self, upgrade):
        a, b = self.statement('GATEH', holder_printed=False), self.statement('GATEI', holder_printed=False)
        untouched = self.statement('GATEJ', holder_printed=False)
        batch = self.batch(a, b, untouched)
        self.save_without_batch_refresh(a, 'Earlier Holder A')
        self.save_without_batch_refresh(b, 'Earlier Holder B')
        upgrade(batch)
        once = self.stored_state(batch)
        for file, holder in ((a, 'Earlier Holder A'), (b, 'Earlier Holder B')):
            self.assert_ready_everywhere(batch, file, holder)
        self.assertFalse(self.views(batch, untouched)['detail'])
        self.assertEqual(self.listed(batch)['available_statements'], 2)
        self.assert_list_agrees(batch)
        upgrade(batch)
        upgrade(batch)
        self.assertEqual(self.stored_state(batch), once)
        self.assertEqual(self.listed(batch)['available_statements'], 2)

    def test_background_readiness_sweep_upgrades_existing_drafts_repeatably(self):
        self.assert_upgrade_repeatable(lambda batch: batches.refresh_stale_readiness(self.f.SessionLocal))

    def test_batch_readiness_refresh_upgrades_existing_drafts_repeatably(self):
        def upgrade(batch):
            with self.f.SessionLocal() as db:
                batches.refresh_batch_readiness(db, case_id=self.f.case.id, batch_id=batch)
        self.assert_upgrade_repeatable(upgrade)

    def test_refresh_statement_list_upgrades_existing_drafts_repeatably(self):
        def upgrade(batch):
            with self.f.SessionLocal() as db:
                batches.refresh_statement_list(db, case_id=self.f.case.id, batch_id=batch)
            self.b.advance(batch)
        self.assert_upgrade_repeatable(upgrade)

    def test_draft_saved_before_the_batch_existed_is_ready_when_the_batch_is_prepared(self):
        early = self.statement('GATEK', holder_printed=False)
        with self.f.SessionLocal() as db:
            save_progress(db, case_id=self.f.case.id, evidence_file_id=early.id,
                request=self.request(early, 'Saved Before Batch'), expected_review_revision='initial', actor=self.f.actor)
        batch = self.batch(early)
        self.assert_ready_everywhere(batch, early, 'Saved Before Batch')
        self.assertEqual(self.listed(batch)['available_statements'], 1)
        self.assert_list_agrees(batch)

    # -- 4. one group confirmation imports the exact eligible set once ---------

    def mixed_batch(self):
        """Two ready (one only after a saved correction), one blocked, one left unimported."""
        ready = self.statement('GATER1')
        corrected = self.statement('GATER2', holder_printed=False)
        blocked = self.statement('GATEH1', holder_printed=False)
        skipped = self.statement('GATES1')
        batch = self.batch(ready, corrected, blocked, skipped)
        with self.f.SessionLocal() as db:
            save_progress(db, case_id=self.f.case.id, evidence_file_id=corrected.id,
                request=self.request(corrected, 'Corrected Holder'), expected_review_revision='initial', actor=self.f.actor)
        detail, _ = self.detail(batch, skipped)
        with self.f.SessionLocal() as db:
            batches.leave_unimported(db, case_id=self.f.case.id, batch_id=batch, item_id=UUID(detail['id']),
                action='skip', reason='Synthetic: not part of this import.',
                expected_revision=detail['disposition_revision'], actor=self.f.actor)
        return batch, dict(ready=ready, corrected=corrected, blocked=blocked, skipped=skipped)

    def confirm(self, batch, revision, request_id=None):
        with self.f.SessionLocal() as db:
            return batches.queue_import(db, case_id=self.f.case.id, batch_id=batch,
                expected_revision=revision, actor=self.f.actor, request_id=request_id)

    def operations(self):
        with self.f.SessionLocal() as db:
            return list(db.scalars(select(Operation)))

    def assert_imported_exactly(self, files, absent):
        documents = self.documents_by_file()
        for file in files:
            self.assertEqual(documents.get(file.id), 1, self.accounts[file.id])
        for file in absent:
            self.assertNotIn(file.id, documents, self.accounts[file.id])
        self.assertEqual(self.payments(), ROWS_PER_STATEMENT * len(files))

    def test_group_confirmation_imports_exactly_the_eligible_set_once(self):
        batch, s = self.mixed_batch()
        state = self.b.status(batch)
        self.assertEqual(state['available_statements'], 2)
        self.assert_list_agrees(batch)
        first = self.confirm(batch, state['ready_revision'])
        submitted = {row['file_id'] for row in first['operation']['outcomes']}
        self.assertEqual(submitted, {str(s['ready'].id), str(s['corrected'].id)})
        # Repeat of the same confirmation (lost response) and a second click
        # with its own request id: one job, nothing added.
        self.assertEqual(self.confirm(batch, state['ready_revision'])['operation']['id'], first['operation']['id'])
        with self.assertRaisesRegex(PdfMappingError, 'ready statements changed'):
            self.confirm(batch, state['ready_revision'], request_id=uuid4())
        self.assertEqual(len(self.operations()), 1)
        self.b.advance(batch)
        self.assert_imported_exactly([s['ready'], s['corrected']], [s['blocked'], s['skipped']])
        # Re-confirming the old screen after the import reuses its receipt;
        # the worker running again imports nothing more.
        again = self.confirm(batch, state['ready_revision'])
        self.assertEqual(again['operation']['id'], first['operation']['id'])
        self.assertEqual(again['operation']['imported'], 2)
        self.b.advance(batch)
        self.assert_imported_exactly([s['ready'], s['corrected']], [s['blocked'], s['skipped']])
        after = self.b.status(batch)
        self.assertEqual((after['counts']['imported'], after['available_statements']), (2, 0))
        with self.assertRaisesRegex(PdfMappingError, 'no new statement records'):
            self.confirm(batch, after['ready_revision'])
        self.assert_list_agrees(batch)
        # Resolving the remaining decision makes only that statement eligible.
        with self.f.SessionLocal() as db:
            save_progress(db, case_id=self.f.case.id, evidence_file_id=s['blocked'].id,
                request=self.request(s['blocked'], 'Later Holder'), expected_review_revision='initial', actor=self.f.actor)
        later = self.b.status(batch)
        self.assertEqual(later['available_statements'], 1)
        second = self.confirm(batch, later['ready_revision'])
        self.assertEqual({row['file_id'] for row in second['operation']['outcomes']}, {str(s['blocked'].id)})
        self.b.advance(batch)
        self.assert_imported_exactly([s['ready'], s['corrected'], s['blocked']], [s['skipped']])
        self.assertEqual(len(self.operations()), 2)

    def test_concurrent_group_confirmations_queue_one_job(self):
        batch, s = self.mixed_batch()
        revision = self.b.status(batch)['ready_revision']
        start = Barrier(3)

        def confirm(request_id):
            start.wait()
            try:
                return self.confirm(batch, revision, request_id=request_id)
            except Exception as error:  # noqa: BLE001 - every outcome is checked below
                return error

        # Two tabs with their own request ids and one repeated default id.
        with ThreadPoolExecutor(3) as pool:
            outcomes = list(pool.map(confirm, (uuid4(), uuid4(), None)))
        accepted = [o for o in outcomes if isinstance(o, dict)]
        refused = [o for o in outcomes if not isinstance(o, dict)]
        for error in refused:
            self.assertNotIsInstance(error, AssertionError)
        operations = self.operations()
        self.assertEqual(len(operations), 1, outcomes)
        self.assertTrue(accepted)
        self.assertEqual({o['operation']['id'] for o in accepted}, {str(operations[0].id)})
        self.assertEqual({row['file_id'] for row in operations[0].outcomes},
            {str(s['ready'].id), str(s['corrected'].id)})
        self.b.advance(batch)
        self.assert_imported_exactly([s['ready'], s['corrected']], [s['blocked'], s['skipped']])

    def test_worker_interrupted_after_the_ledger_write_imports_once_on_rerun(self):
        """Concurrent workers are a PostgreSQL-only property (see the module notes).

        What holds without row locks: a worker that stops after the ledger write
        but before recording its outcome leaves the statement accepted, and
        running the worker again finds the saved statement instead of adding it.
        """
        from unittest.mock import patch
        from services.financial import import_operations
        batch, s = self.mixed_batch()
        first = self.confirm(batch, self.b.status(batch)['ready_revision'])
        items = [self.item(batch, s['ready']).id, self.item(batch, s['corrected']).id]
        with patch.object(import_operations, 'record_outcome', side_effect=RuntimeError('Synthetic worker stop')):
            for item_id in items:
                with self.assertRaisesRegex(RuntimeError, 'Synthetic worker stop'):
                    batches._import_item(self.f.SessionLocal, self.f.case.id, batch, item_id, Path)
        self.assert_imported_exactly([s['ready'], s['corrected']], [s['blocked'], s['skipped']])
        with self.f.SessionLocal() as db:
            self.assertEqual({i.status for i in db.scalars(select(Item).where(Item.id.in_(items)))}, {'pending_import'})
        for _ in range(2):
            for item_id in items:
                batches._import_item(self.f.SessionLocal, self.f.case.id, batch, item_id, Path)
        self.assert_imported_exactly([s['ready'], s['corrected']], [s['blocked'], s['skipped']])
        with self.f.SessionLocal() as db:
            self.assertEqual({i.status for i in db.scalars(select(Item).where(Item.id.in_(items)))}, {'imported'})
            operation = db.get(Operation, UUID(first['operation']['id']))
            self.assertEqual(sorted(row['status'] for row in operation.outcomes), ['already_present', 'already_present'])
