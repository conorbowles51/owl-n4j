"""Batch list reads use stored projections and match the former re-reading path.

Each scenario builds data that the former read path could only project by
re-reading PDFs. It records that path's result (frozen reference copy), then
checks that a list read neither reads a PDF nor writes, holds the affected
items until the write side refreshes them, and afterwards returns the same
projection without reading.
"""
import json
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import select

from postgres.models.evidence import EvidenceFile, EvidenceDocumentText, EvidenceTableGeometry
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from services.financial import import_batches as service
from services.financial import statement_import as reader
from services.financial.statement_import import StatementReviewDraft
from tests import test_financial_import_batches as fixtures
from tests.financial_legacy_batch_read import legacy_checked_batch_items

# Concurrency tokens derived from the stored item status. A refresh may store
# the projected ready/attention status, so these follow the stored item.
STATUS_TOKENS = ('disposition_revision', 'currency_revision')
LEGACY_FIELDS = ('institution', 'account_type', 'review_model', 'can_import')


def _normal(value):
    return json.loads(json.dumps(value, default=str, sort_keys=True))


class StoredBatchReadTests(TestCase):
    maxDiff = None

    def setUp(self):
        self.fixture = fixtures.BatchImportTests()
        self.fixture.setUp()
        self.f = self.fixture.f
        self.batch_id = self.fixture.create()
        self.fixture.advance(self.batch_id)

    def tearDown(self):
        self.fixture.tearDown()

    # -- helpers ---------------------------------------------------------

    def stored_state(self, db):
        items = {str(i.id): _normal((i.status, i.summary, i.review_request)) for i in db.scalars(select(Item))}
        files = {str(f.id): _normal(f.metadata_) for f in db.scalars(select(EvidenceFile))}
        return items, files

    def items(self, db):
        return list(db.scalars(select(Item).where(Item.batch_id == self.batch_id).order_by(Item.id)))

    def view(self, projected, coverage_tokens=True):
        result = {str(i.id): _normal(dict(status=i.status, review_request=i.review_request, review_revision=i.review_revision,
            summary={k: v for k, v in i.summary.items() if k not in STATUS_TOKENS and k != 'readiness'})) for i in projected}
        if not coverage_tokens:
            # The former path built the coverage token of an item without a
            # saved request from its stale stored reading revision while
            # showing the reassessed one. Once the reassessment is stored both
            # use the current revision. No decision can reference the old token:
            # recording a coverage decision always saves a request.
            for value in result.values():
                if not value['review_request'] and 'coverage_review' in value['summary']:
                    value['summary']['coverage_review'].pop('revision', None)
        return result

    def reference(self, coverage_tokens=True):
        """The former path's projection of the current data (it re-reads PDFs)."""
        with self.f.SessionLocal() as db:
            projected = legacy_checked_batch_items(db, self.f.case.id, self.items(db))
            db.rollback()
        return self.view(projected, coverage_tokens), service.ready_revision(projected)

    def read(self):
        """A list read: must not re-read a PDF and must not write."""
        forbidden = AssertionError('A batch list read re-read a statement PDF')
        with self.f.SessionLocal() as db:
            before = self.stored_state(db)
            with patch.object(service, 'read_statement_import', side_effect=forbidden), \
                    patch.object(reader, 'read_statement_import', side_effect=forbidden):
                projected = service.checked_batch_items(db, self.f.case.id, self.items(db))
                status = service.batch_status(db, case_id=self.f.case.id, batch_id=self.batch_id)
                if projected:
                    service.next_problem(db, case_id=self.f.case.id, batch_id=self.batch_id, item_id=projected[0].id)
            self.assertFalse(db.new or db.dirty or db.deleted)
            db.rollback()
            self.assertEqual(self.stored_state(db), before)
            for item in projected:
                self.assertEqual(item.summary['disposition_revision'], service._digest(dict(
                    status=db.get(Item, item.id).status, request=db.get(Item, item.id).review_request,
                    decision=db.get(Item, item.id).summary.get('import_decision'))))
        return projected, status

    def legacy_clones(self, count):
        with self.f.SessionLocal() as db:
            file = db.get(EvidenceFile, self.f.file.id)
            text = db.get(EvidenceDocumentText, file.id)
            geometry = db.get(EvidenceTableGeometry, (file.id, 1))
            original = db.scalar(select(Item).where(Item.batch_id == self.batch_id))
            legacy = {k: v for k, v in original.summary.items() if k not in LEGACY_FIELDS}
            original.summary = deepcopy(legacy)
            batch = db.get(Batch, self.batch_id)
            files = deepcopy(batch.files)
            for index in range(count):
                identifier = uuid4()
                name = f'synthetic-copy-{index}.pdf'
                db.add(EvidenceFile(id=identifier, case_id=file.case_id, original_filename=name,
                    stored_path=file.stored_path, sha256=file.sha256, status='processed', metadata_={}))
                db.add(EvidenceDocumentText(evidence_file_id=identifier, content=text.content,
                    content_sha256=text.content_sha256, character_count=text.character_count,
                    engine_job_id=text.engine_job_id, source_locations=deepcopy(text.source_locations)))
                db.add(EvidenceTableGeometry(evidence_file_id=identifier, page_number=1,
                    engine_job_id=geometry.engine_job_id, payload=deepcopy(geometry.payload)))
                db.add(Item(id=uuid4(), batch_id=batch.id, file_id=identifier, statement_key=original.statement_key,
                    status='attention', summary={**deepcopy(legacy), 'filename': name, 'source_id': str(identifier)}))
                files.append({**files[0], 'source_id': str(identifier), 'file_id': str(identifier),
                    'filename': name, 'status': 'checked'})
            batch.files = files
            db.commit()

    def assert_held_then_identical(self, expected, expected_ready, refresh, coverage_tokens=True):
        held, status = self.read()
        self.assertTrue(any(i.summary.get('readiness_pending') or i.summary.get('comparison_pending') for i in held))
        for item in held:
            if item.summary.get('readiness_pending') or item.summary.get('comparison_pending'):
                self.assertFalse(item.summary['can_import'])
                self.assertFalse(service.import_available(item))
        self.assertGreater(status['readiness_pending'] + status['comparison_pending'], 0)
        outcome = refresh()
        refreshed, status = self.read()
        self.assertEqual(self.view(refreshed, coverage_tokens), expected)
        self.assertEqual(service.ready_revision(refreshed), expected_ready)
        self.assertEqual((status['readiness_pending'], status['comparison_pending']), (0, 0))
        # Idempotent: nothing is left to refresh and the next read is unchanged.
        with self.f.SessionLocal() as db:
            again = service.refresh_case_readiness(db, case_id=self.f.case.id)
        self.assertEqual((again['hydrated'], again['refreshed']), (0, 0))
        self.assertEqual(self.view(self.read()[0], coverage_tokens), expected)
        return outcome

    def refresh_batch(self):
        with self.f.SessionLocal() as db:
            return service.refresh_batch_readiness(db, case_id=self.f.case.id, batch_id=self.batch_id)

    # -- scenarios -------------------------------------------------------

    def test_legacy_summaries_match_the_former_path_after_write_side_refresh(self):
        self.legacy_clones(3)
        expected, ready = self.reference(coverage_tokens=False)
        outcome = self.assert_held_then_identical(expected, ready, self.refresh_batch, coverage_tokens=False)
        self.assertEqual((outcome['hydrated'], outcome['refreshed']), (4, 4))
        # The stored item status and summary now hold each statement's own
        # current assessment for other views. Coverage against other
        # statements stays a read-time comparison, as before.
        with self.f.SessionLocal() as db:
            for item in self.items(db):
                self.assertIn('account_type', item.summary)
                self.assertEqual(item.summary['review_model'], service.REVIEW_MODEL)
                self.assertEqual(item.status, item.summary['readiness']['state'])
                self.assertEqual(item.summary['revision'], expected[str(item.id)]['summary']['revision'])

    def test_saved_review_from_another_reading_matches_after_refresh_and_group_import_accepts(self):
        request = self.f.request()
        request['holder'] = 'Reviewed Company'
        with self.f.SessionLocal() as db:
            from services.financial.statement_progress import save_progress
            save_progress(db, case_id=self.f.case.id, evidence_file_id=self.f.file.id,
                request=StatementReviewDraft.model_validate(request), expected_review_revision='initial', actor=self.f.actor)
            item = db.scalar(select(Item).where(Item.batch_id == self.batch_id))
            # A summary prepared from an earlier reading: the former path
            # re-read the PDF on every list read to reassess it.
            item.summary = {**item.summary, 'revision': 'a' * 64}
            db.commit()
        expected, ready = self.reference()
        self.assert_held_then_identical(expected, ready, self.refresh_batch)
        status = self.read()[1]
        self.assertEqual(status['items'][0]['holder'], 'Reviewed Company')
        self.assertTrue(status['items'][0]['can_import'])
        with self.f.SessionLocal() as db:
            queued = service.queue_import(db, case_id=self.f.case.id, batch_id=self.batch_id,
                expected_revision=status['ready_revision'], actor=self.f.actor)
        self.assertEqual(queued['queued'], 1)

    def test_statement_imported_individually_is_refreshed_by_its_write(self):
        self.f.confirm()  # The standalone import refreshes the file's batch items.
        projected = self.read()[0]
        self.assertEqual(projected[0].status, 'imported')
        self.assertFalse(projected[0].summary.get('readiness_pending'))

    def test_a_write_without_its_own_refresh_is_projected_by_the_background_sweep(self):
        with patch.object(service, 'refresh_file_readiness'):
            self.f.confirm()
        expected, ready = self.reference()
        self.assertEqual(next(iter(expected.values()))['status'], 'imported')
        outcome = self.assert_held_then_identical(expected, ready,
            lambda: service.refresh_stale_readiness(self.f.SessionLocal, budget_seconds=60))
        self.assertEqual(outcome[str(self.f.case.id)]['refreshed'], 1)
        with self.f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == self.batch_id))
            # The batch item keeps its own status; the projection is stored.
            self.assertEqual(item.status, 'ready')
            self.assertEqual(item.summary['readiness']['state'], 'imported')

    def test_a_changed_input_after_refresh_is_held_again_never_trusted(self):
        self.f.confirm()
        self.assertEqual(self.read()[0][0].status, 'imported')
        # Removing the admitted record changes the inputs of the stored
        # 'imported' projection: the list holds it rather than show it.
        from postgres.models.financial import FinancialSourceDocument
        with self.f.SessionLocal() as db:
            for source in db.scalars(select(FinancialSourceDocument)):
                source.status = 'superseded'
            db.commit()
        held = self.read()[0][0]
        self.assertTrue(held.summary['readiness_pending'])
        self.assertEqual(held.status, 'attention')
        self.assertFalse(held.summary['can_import'])
        expected, ready = self.reference()
        with self.f.SessionLocal() as db:
            service.refresh_case_readiness(db, case_id=self.f.case.id)
        self.assertEqual(self.view(self.read()[0]), expected)

    def test_single_review_read_rereads_only_its_own_statement(self):
        self.legacy_clones(2)
        calls = []
        original = reader.read_statement_import
        def reading(*args, **kwargs):
            calls.append(kwargs['evidence_file_id'])
            return original(*args, **kwargs)
        with self.f.SessionLocal() as db, patch.object(service, 'read_statement_import', side_effect=reading), \
                patch.object(reader, 'read_statement_import', side_effect=reading):
            target = db.scalar(select(Item).where(Item.batch_id == self.batch_id, Item.file_id == self.f.file.id))
            projected = service.checked_batch_items(db, self.f.case.id, [target], reading='targets')
            self.assertFalse(db.new or db.dirty or db.deleted)
        self.assertEqual(set(calls), {self.f.file.id})
        self.assertTrue(projected[0].summary['comparison_pending'])


class TimingMiddlewareTests(TestCase):
    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from services.financial.request_timing import FinancialTimingMiddleware, stage, count
        app = FastAPI()

        @app.get('/api/financial/statement-import/batches/{batch_id}')
        def endpoint(batch_id: str):  # Synchronous: runs in the thread pool.
            with stage('batch_projection'):
                count('statement_reads', 0)
            return dict(ok=True)

        @app.get('/api/other')
        def other():
            return dict(ok=True)

        app.add_middleware(FinancialTimingMiddleware)
        return TestClient(app)

    def test_batch_endpoints_return_correlation_id_and_stage_timing(self):
        client = self.client()
        response = client.get('/api/financial/statement-import/batches/x', headers={'X-Request-ID': 'client-123'})
        self.assertEqual(response.headers['x-request-id'], 'client-123')
        self.assertRegex(response.headers['server-timing'], r'^batch_projection;dur=[\d.]+, total;dur=[\d.]+$')
        minted = client.get('/api/financial/statement-import/batches/x', headers={'X-Request-ID': 'bad id\n'})
        self.assertRegex(minted.headers['x-request-id'], r'^[0-9a-f]{32}$')
        self.assertNotIn('server-timing', client.get('/api/other').headers)
