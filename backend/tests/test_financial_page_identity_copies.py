"""Two files whose pages render identically are one document for the copy rule (r10-copies).

Synthetic statements only (the overlap fixture: one statement, 12 payments),
stored as real one-page PDFs so their pages can be rendered. A copy here has
other bytes (a trailing comment, as a second production would add) and the
same pages. Whatever either file's reading says, the statement is saved once,
from the better proved reading, and the other file is set aside as a linked
copy: never deleted, never offered, never a question for the investigator.
"""
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4
import hashlib

from sqlalchemy import select

from postgres.models.evidence import EvidenceDocumentText, EvidenceFile, EvidenceTableGeometry
from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
from services.financial import import_batches as batches
from services.financial import page_identity
from services.financial import queue_save
from services.financial import statement_import
from tests import test_financial_statement_overlap as overlap_fixture

try:
    import fitz
except ImportError:  # pragma: no cover - the suite's interpreter carries PyMuPDF
    fitz = None


def _pdf(lines):
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    for index, line in enumerate(lines):
        page.insert_text((72, 72 + 16 * index), line, fontsize=11)
    data = document.tobytes()
    document.close()
    return data


STATEMENT = ['Synthetic Bank', 'Statement Period: January 1, 2023 - December 31, 2023',
             'Opening balance 12,450', 'Incoming 125,000', 'Outgoing 120,000']
OTHER_STATEMENT = ['Synthetic Bank', 'Statement Period: January 1, 2023 - December 31, 2023',
                   'Opening balance 12,450', 'Incoming 125,000', 'Outgoing 119,000']


class _Page:
    def __init__(self, samples, width=10, height=12):
        self.samples, self.width, self.height = samples, width, height

    def get_pixmap(self, matrix, alpha):
        return SimpleNamespace(samples=self.samples, width=self.width, height=self.height)


class _Document:
    def __init__(self, *samples):
        self.pages = [_Page(s) for s in samples]
        self.page_count = len(self.pages)

    def load_page(self, index):
        return self.pages[index]


class PageIdentityUnitTests(TestCase):
    def test_identity_is_the_ordered_page_images(self):
        one = page_identity.compute(_Document(b'a', b'b'), renderer='r')
        self.assertEqual(one, page_identity.compute(_Document(b'a', b'b'), renderer='r'))
        self.assertNotEqual(one['identity'], page_identity.compute(_Document(b'b', b'a'), renderer='r')['identity'])
        self.assertNotEqual(one['identity'], page_identity.compute(_Document(b'a'), renderer='r')['identity'])
        self.assertIsNone(page_identity.compute(_Document(), renderer='r'))

    def test_a_stored_identity_counts_only_for_its_own_bytes_version_and_renderer(self):
        value = dict(page_identity.compute(_Document(b'a'), renderer='r'), source_sha256='1' * 64)
        file = SimpleNamespace(sha256='1' * 64, metadata_={page_identity.METADATA_KEY: value})
        twin = SimpleNamespace(sha256='2' * 64, metadata_={page_identity.METADATA_KEY: dict(value, source_sha256='2' * 64)})
        self.assertTrue(page_identity.same_pages(file, twin))
        self.assertIsNone(page_identity.stored(SimpleNamespace(sha256='3' * 64, metadata_=file.metadata_)))
        other_renderer = SimpleNamespace(sha256='2' * 64, metadata_={page_identity.METADATA_KEY: dict(
            value, source_sha256='2' * 64, renderer='other')})
        self.assertFalse(page_identity.same_pages(file, other_renderer))
        older = SimpleNamespace(sha256='2' * 64, metadata_={page_identity.METADATA_KEY: dict(
            value, source_sha256='2' * 64, version='page-identity-v0')})
        self.assertFalse(page_identity.same_pages(file, older))
        with patch.object(page_identity, 'ENABLED', False):
            self.assertFalse(page_identity.same_pages(file, twin))

    def test_bytes_different_copy_of_a_real_pdf_has_the_same_identity(self):
        if fitz is None:
            self.skipTest('PyMuPDF is not installed')
        import tempfile
        data = _pdf(STATEMENT)
        with tempfile.TemporaryDirectory() as root:
            first, second, third = Path(root) / 'a.pdf', Path(root) / 'b.pdf', Path(root) / 'c.pdf'
            first.write_bytes(data)
            second.write_bytes(data + b'\n% another production\n')
            third.write_bytes(_pdf(OTHER_STATEMENT))
            a, b, c = (page_identity.identity_of_path(p, 'x') for p in (first, second, third))
            self.assertEqual(a['identity'], b['identity'])
            self.assertNotEqual(a['identity'], c['identity'])
            self.assertIsNone(page_identity.identity_of_path(Path(root) / 'missing.pdf', 'x'))


class PageCopyTests(TestCase):
    """The copy rule for files whose pages are identical, through preparation and the automatic save."""

    def setUp(self):
        if fitz is None:
            self.skipTest('PyMuPDF is not installed')
        self.fixture = overlap_fixture.StatementOverlapTests('test_reason_bound_to_coverage_stays_valid_when_peer_imports')
        self.fixture.setUp()
        self.f = self.fixture.f
        self.primary = self.f.file
        self.pdf = _pdf(STATEMENT)
        self._store(self.primary, self.pdf, 'Statement.pdf')

    def tearDown(self):
        self.fixture.tearDown()

    def _store(self, file, data, name):
        path = Path(self.f._directory) / (str(uuid4()) + '.pdf')
        path.write_bytes(data)
        with self.f.SessionLocal() as db:
            record = db.get(EvidenceFile, file.id)
            record.stored_path, record.sha256 = str(path), hashlib.sha256(data).hexdigest()
            record.original_filename = name
            db.commit()

    def copy(self, *, data=None, revised=False):
        """Another file holding the primary's reading (bytes differ, pages identical unless ``data``)."""
        other = self.fixture.copy_file(revised=revised)
        self._store(other, data if data is not None else self.pdf + b'\n% second production\n', 'Second production.pdf')
        return other

    def spoil(self, file):
        """Read badly: one payment's amount unreadable and the bank name lost."""
        with self.f.SessionLocal() as db:
            geometry = db.get(EvidenceTableGeometry, (file.id, 1))
            payload = [dict(entry) for entry in geometry.payload]
            table = dict(payload[0]['table'])
            table['values'] = [dict(value, text='€12S,0O0') if (value['row'], value['column']) == (2, 2) else value
                               for value in table['values']]
            payload[0] = dict(payload[0], table=table)
            geometry.payload = payload
            text = db.get(EvidenceDocumentText, file.id)
            text.content = text.content.replace('Bank: Synthetic Bank\n', '')
            text.content_sha256 = hashlib.sha256(text.content.encode()).hexdigest()
            text.character_count = len(text.content)
            db.commit()

    def batch(self, *files):
        with self.f.SessionLocal() as db:
            return batches.create_batch(db, case_id=self.f.case.id, request_id=uuid4(),
                file_ids=[file.id for file in files], folder_ids=[], actor=self.f.actor)

    def drain(self, batch, limit=40):
        for _ in range(limit):
            process = AsyncMock(side_effect=AssertionError('Existing geometry must be reused'))
            with patch.object(queue_save, 'AUTO_SAVE_READY', True), \
                    patch.object(queue_save, 'fully_reconciled', return_value=True):
                asyncio.run(batches.advance_batch(self.f.SessionLocal, batch, Path, process))
            with self.f.SessionLocal() as db:
                if batches.batch_for(db, self.f.case.id, batch).status != 'preparing':
                    return
        self.fail('batch did not finish')

    def items(self):
        with self.f.SessionLocal() as db:
            return {item.file_id: (item.status, dict(item.summary)) for item in db.scalars(select(Item))
                    if item.status not in ('removed', 'superseded_reading')}

    def saved(self, *files):
        with self.f.SessionLocal() as db:
            sources = list(db.scalars(select(FinancialSourceDocument).where(
                FinancialSourceDocument.case_id == self.f.case.id, FinancialSourceDocument.status == 'admitted',
                FinancialSourceDocument.evidence_file_id.in_([file.id for file in files]))))
            rows = len(list(db.scalars(select(FinancialTransaction).where(
                FinancialTransaction.source_document_id.in_([s.id for s in sources]))))) if sources else 0
        return sources, rows

    def assert_one_statement(self, kept, copy, basis='identical_pages'):
        sources, rows = self.saved(kept, copy)
        self.assertEqual([s.evidence_file_id for s in sources], [kept.id])
        self.assertEqual(rows, 12)
        items = self.items()
        self.assertEqual(items[kept.id][0], 'imported')
        status, summary = items[copy.id]
        self.assertEqual(status, 'duplicate_ignored', summary.get('problems'))
        disposition = summary['duplicate_disposition']
        self.assertEqual((disposition['status'], disposition['basis']), ('ignored', basis))
        self.assertEqual(disposition['retained']['evidence_file_id'], str(kept.id))
        self.assertFalse(summary.get('can_import'))
        with self.f.SessionLocal() as db:
            # Never deleted: the set-aside file and its reading are still there.
            self.assertIsNotNone(db.get(EvidenceFile, copy.id))
            self.assertIsNotNone(db.get(EvidenceDocumentText, copy.id))
        return disposition

    def test_identities_are_recorded_at_preparation(self):
        copy = self.copy()
        self.drain(self.batch(self.primary, copy))
        with self.f.SessionLocal() as db:
            first, second = db.get(EvidenceFile, self.primary.id), db.get(EvidenceFile, copy.id)
            self.assertNotEqual(first.sha256, second.sha256)
            self.assertTrue(page_identity.same_pages(first, second))
            self.assertEqual(page_identity.same_document_files(db, self.f.case.id, first), {str(copy.id): 'identical_pages'})

    def test_unreadable_copy_is_set_aside_linked_to_the_readable_original(self):
        copy = self.copy()
        self.spoil(copy)
        self.drain(self.batch(self.primary, copy))
        self.assert_one_statement(self.primary, copy)

    def test_readable_copy_is_kept_and_the_unreadable_original_is_covered_by_it(self):
        copy = self.copy()
        self.spoil(self.primary)
        self.drain(self.batch(self.primary, copy))
        disposition = self.assert_one_statement(copy, self.primary)
        self.assertIn('Every page of this file is identical', disposition['reason'])
        # The original's queue entry says it is a copy of the saved file, not work.
        from services.financial.review_queue import case_review_queue
        with self.f.SessionLocal() as db:
            queue = case_review_queue(db, case_id=self.f.case.id, use_cache=False)
        entries = [entry for key, values in queue.items() if isinstance(values, list) for entry in values
                   if isinstance(entry, dict) and entry.get('file_id') == str(self.primary.id)]
        self.assertTrue(entries)
        self.assertTrue(all(entry.get('bucket') == 'copies' and entry.get('set_aside') for entry in entries), entries)

    def test_copy_prepared_in_a_later_batch_after_the_original_was_saved(self):
        self.drain(self.batch(self.primary))
        copy = self.copy()
        self.spoil(copy)
        self.drain(self.batch(copy))
        self.assert_one_statement(self.primary, copy)

    def _other_reader(self, file):
        """The file read by another reader: other bank wording and another product type."""
        real_read = statement_import.read_statement_import

        def read(session, **kwargs):
            proposal = real_read(session, **kwargs)
            if str(kwargs.get('evidence_file_id')) == str(file.id) and proposal.get('metadata'):
                proposal = {**proposal, 'metadata': {**proposal['metadata'], 'account_type': 'savings',
                                                     'institution': 'SYNTHETIC BANK SA INSTITUCION DE BANCA'}}
            return proposal
        return patch.multiple(statement_import, read_statement_import=read), \
            patch.object(batches, 'read_statement_import', read)

    def test_copies_read_by_different_readers_are_one_statement(self):
        copy = self.copy()
        first, second = self._other_reader(copy)
        with first, second:
            self.drain(self.batch(self.primary, copy))
        self.assert_one_statement(self.primary, copy)

    def test_without_page_identity_the_differently_read_copy_was_saved_twice(self):
        # The defect this fixes (r9-engine-santander finding 2), kept as a check
        # that the test above exercises the page rule and not another one.
        copy = self.copy()
        first, second = self._other_reader(copy)
        with first, second, patch.object(page_identity, 'ENABLED', False):
            self.drain(self.batch(self.primary, copy))
        sources, rows = self.saved(self.primary, copy)
        self.assertEqual(len(sources), 2)

    def test_a_different_statement_with_equal_metadata_is_not_a_copy(self):
        other = self.copy(data=_pdf(OTHER_STATEMENT), revised=True)
        self.drain(self.batch(self.primary, other))
        with self.f.SessionLocal() as db:
            first, second = db.get(EvidenceFile, self.primary.id), db.get(EvidenceFile, other.id)
            self.assertFalse(page_identity.same_pages(first, second))
        items = self.items()
        for file in (self.primary, other):
            status, summary = items[file.id]
            disposition = summary.get('duplicate_disposition') or {}
            self.assertNotEqual(status, 'duplicate_ignored')
            self.assertNotEqual(disposition.get('basis'), 'identical_pages')
        # Equal account and dates, different money: held for comparison, nothing saved.
        self.assertEqual(self.saved(self.primary, other), ([], 0))

    def _edit(self, batch, file, description):
        from services.financial.statement_import import StatementReviewDraft
        item = next(i for i in self.fixture.b.status(batch)['items'] if i['file_id'] == str(file.id))
        self.f.file = file
        raw = self.f.request()
        raw['rows'][1]['description'] = description
        raw['rows'][1]['reason'] = 'Checked against the printed page.'
        with self.f.SessionLocal() as db:
            batches.save_review(db, case_id=self.f.case.id, batch_id=batch, item_id=UUID(item['id']),
                request=StatementReviewDraft.model_validate(raw), expected_review_revision=batches._digest({}))

    def test_copy_of_an_investigator_edited_statement_keeps_the_edited_one(self):
        with patch.object(queue_save, 'AUTO_SAVE_READY', False):
            first = self.batch(self.primary)
            self.fixture.b.advance(first)
        self._edit(first, self.primary, 'Corrected by the investigator')
        copy = self.copy()
        with patch.object(queue_save, 'AUTO_SAVE_READY', False):
            second = self.batch(copy)
            for _ in range(10):
                self.fixture.b.advance(second)
        items = self.items()
        status, summary = items[copy.id]
        self.assertEqual(status, 'duplicate_ignored', summary.get('problems'))
        self.assertEqual(summary['duplicate_disposition']['retained']['evidence_file_id'], str(self.primary.id))
        self.assertNotEqual(items[self.primary.id][0], 'duplicate_ignored')

    def test_two_different_edits_of_one_statement_are_compared_by_a_person(self):
        with patch.object(queue_save, 'AUTO_SAVE_READY', False):
            batch = self.batch(self.primary)
            self.fixture.b.advance(batch)
        copy = self.copy()
        with patch.object(queue_save, 'AUTO_SAVE_READY', False):
            second = self.batch(copy)
            for _ in range(10):
                self.fixture.b.advance(second)
        self._edit(batch, self.primary, 'First correction')
        self._edit(second, copy, 'A different correction')
        with patch.object(queue_save, 'AUTO_SAVE_READY', False):
            third = self.batch(self.primary, copy)
            for _ in range(10):
                self.fixture.b.advance(third)
        with self.f.SessionLocal() as db:
            decisions = [((db.get(EvidenceFile, file.id).metadata_ or {}).get('financial_duplicate_dispositions') or {})
                         for file in (self.primary, copy)]
        statuses = {decision.get('status') for values in decisions for decision in values.values()}
        self.assertNotIn('ignored', statuses)
        self.assertIn('needs_comparison', statuses)
        self.assertEqual(self.saved(self.primary, copy), ([], 0))
