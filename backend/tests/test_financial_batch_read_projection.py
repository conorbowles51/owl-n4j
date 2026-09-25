"""Fresh batch reads share parsing work without caching admission across requests."""
from collections import Counter
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import select

from postgres.models.evidence import EvidenceFile, EvidenceDocumentText, EvidenceTableGeometry
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from services.financial import import_batches as service
from services.financial import statement_import as reader
from tests import test_financial_import_batches as fixtures


class BatchReadProjectionTests(TestCase):
    def setUp(self):
        self.fixture = fixtures.BatchImportTests()
        self.fixture.setUp()
        self.f = self.fixture.f
        self.batch_id = self.fixture.create()
        self.fixture.advance(self.batch_id)
        with self.f.SessionLocal() as db:
            file = db.get(EvidenceFile, self.f.file.id)
            text = db.get(EvidenceDocumentText, file.id)
            geometry = db.get(EvidenceTableGeometry, (file.id, 1))
            original = db.scalar(select(Item).where(Item.batch_id == self.batch_id))
            legacy = {key: value for key, value in original.summary.items()
                if key not in ('institution', 'account_type', 'review_model', 'can_import')}
            original.summary = deepcopy(legacy)
            self.item_ids = [original.id]
            self.file_ids = [file.id]
            batch = db.get(Batch, self.batch_id)
            files = deepcopy(batch.files)
            for index in range(7):
                identifier, item_id = uuid4(), uuid4()
                name = f'synthetic-reading-{index}.pdf'
                db.add(EvidenceFile(id=identifier, case_id=file.case_id, original_filename=name,
                    stored_path=file.stored_path, sha256=file.sha256, status='processed', metadata_={}))
                db.add(EvidenceDocumentText(evidence_file_id=identifier, content=text.content,
                    content_sha256=text.content_sha256, character_count=text.character_count,
                    engine_job_id=text.engine_job_id, source_locations=deepcopy(text.source_locations)))
                db.add(EvidenceTableGeometry(evidence_file_id=identifier, page_number=1,
                    engine_job_id=geometry.engine_job_id, payload=deepcopy(geometry.payload)))
                db.add(Item(id=item_id, batch_id=batch.id, file_id=identifier,
                    statement_key=original.statement_key, status='attention',
                    summary={**deepcopy(legacy), 'filename': name, 'source_id': str(identifier)}))
                files.append({**files[0], 'source_id': str(identifier), 'file_id': str(identifier),
                    'filename': name, 'status': 'checked'})
                self.item_ids.append(item_id)
                self.file_ids.append(identifier)
            batch.files = files
            db.commit()

    def tearDown(self):
        self.fixture.tearDown()

    def project(self, subset=False):
        calls = []
        original = reader.read_statement_import
        def reading(*args, **kwargs):
            calls.append((kwargs['evidence_file_id'], kwargs.get('_include_period_checks', True)))
            return original(*args, **kwargs)
        with self.f.SessionLocal() as db:
            before = {item.id: (deepcopy(item.summary), deepcopy(item.review_request), item.status)
                for item in db.scalars(select(Item).where(Item.batch_id == self.batch_id))}
            with patch.object(service, 'read_statement_import', side_effect=reading), patch.object(reader, 'read_statement_import', side_effect=reading):
                if subset:
                    result = service.checked_batch_items(db, self.f.case.id, [db.get(Item, self.item_ids[0])])
                else:
                    result = service.batch_status(db, case_id=self.f.case.id, batch_id=self.batch_id)['items']
            after = {item.id: (item.summary, item.review_request, item.status)
                for item in db.scalars(select(Item).where(Item.batch_id == self.batch_id))}
            self.assertEqual(after, before)
            self.assertFalse(db.new or db.dirty or db.deleted)
        return result, calls

    def test_legacy_targets_parse_once_and_keep_every_duplicate_hold(self):
        result, calls = self.project()
        self.assertEqual(Counter(identifier for identifier, _ in calls), Counter(self.file_ids))
        self.assertTrue(all(full for _, full in calls))
        self.assertEqual(len(result), 8)
        for item in result:
            self.assertFalse(item['can_import'])
            self.assertTrue(item['coverage_review']['matching_statement'])
            self.assertEqual(len(item['coverage_review']['candidates']), 7)

    def test_other_pending_sources_remain_compared_and_next_read_observes_changes(self):
        result, calls = self.project(subset=True)
        self.assertEqual(Counter(identifier for identifier, _ in calls), Counter(self.file_ids))
        self.assertEqual(dict(calls)[self.file_ids[0]], True)
        self.assertTrue(all(not full for identifier, full in calls if identifier != self.file_ids[0]))
        self.assertEqual(len(result[0].summary['coverage_review']['candidates']), 7)
        before = result[0].summary['revision']
        with self.f.SessionLocal() as db:
            geometry = db.get(EvidenceTableGeometry, (self.file_ids[0], 1))
            payload = deepcopy(geometry.payload)
            value = next(value for value in payload[0]['table']['values'] if value['text'] == '€47,450')
            value['text'] = '€47,451'
            geometry.payload = payload
            db.commit()
        changed, _ = self.project(subset=True)
        self.assertNotEqual(changed[0].summary['revision'], before)
        self.assertFalse(changed[0].summary['can_import'])
        self.assertTrue(any(check.get('status') == 'difference' for check in changed[0].summary['checks']))

    def test_null_legacy_headers_remain_unknown_without_breaking_batch_or_navigation(self):
        with self.f.SessionLocal() as db:
            for item in db.scalars(select(Item).where(Item.batch_id == self.batch_id)):
                item.summary = {**item.summary, 'filename': 'Repeated source name.pdf',
                    'institution': 'Synthetic Bank', 'account_type': 'bank',
                    'review_model': service.REVIEW_MODEL, 'can_import': False}
            item = db.get(Item, self.item_ids[-1])
            item.summary = {**item.summary, 'account': None, 'period_start': None, 'period_end': None}
            missing_name = db.get(Item, self.item_ids[-2])
            missing_name.summary = {**missing_name.summary, 'filename': None}
            db.commit()
        result, _ = self.project()
        shown = next(item for item in result if item['id'] == str(self.item_ids[-1]))
        self.assertEqual((shown['account'], shown['period_start'], shown['period_end']), ('', '', ''))
        self.assertFalse(shown['can_import'])
        named = next(item for item in result if item['id'] == str(self.item_ids[-2]))
        self.assertEqual(named['filename'], 'synthetic-reading-5.pdf')
        with self.f.SessionLocal() as db:
            self.assertIsNone(db.get(Item, self.item_ids[-1]).summary['account'])
            self.assertIsNone(db.get(Item, self.item_ids[-2]).summary['filename'])
            # Navigation shares the same projected sort, including repeated
            # filenames whose unknown account/date used to crash the GET.
            from uuid import UUID
            next_item = service.next_statement(db, case_id=self.f.case.id, batch_id=self.batch_id,
                item_id=UUID(result[0]['id']))
            self.assertEqual(next_item['item_id'], result[1]['id'])
