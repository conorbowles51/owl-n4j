"""Read-only comparison copies are reused per row only while the row is unchanged.

PostgreSQL row versions (xmin) do not exist in SQLite, so these tests stand
the row's own content in for its version: any change to it is a new version.
"""
import hashlib
from datetime import date
from uuid import uuid4
from unittest import TestCase
from unittest.mock import patch
from sqlalchemy import String, cast, event, select
from postgres.models.evidence import EvidenceFile, EvidenceTableGeometry
from services.financial import effective_statement_review as reviews
from services.financial import pending_duplicate_projection as projection
from services.financial import source_lineage
from services.financial import statement_import_overlap as overlap
from tests import test_financial_statement_import as fixtures


def content_version(session):
    return cast(EvidenceFile.metadata_, String) + EvidenceFile.status


class ComparisonCacheTests(TestCase):
    def setUp(self):
        self.f = fixtures.StatementImportTests('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()
        self.other = self.f.evidence(hashlib.sha256(b'other').hexdigest())
        self.f.db.commit()
        self.case_file_ids = set(self.f.db.scalars(select(EvidenceFile.id).where(EvidenceFile.case_id == self.f.case.id)))
        source_lineage._CASE_FILES.clear()
        projection._DIGESTS.clear()
        reviews._SIGNATURES.clear()

    def tearDown(self):
        source_lineage._CASE_FILES.clear()
        projection._DIGESTS.clear()
        reviews._SIGNATURES.clear()
        self.f.tearDown()

    def files(self, db):
        with patch.object(source_lineage, '_row_version', content_version):
            return source_lineage.case_files(db, self.f.case.id)

    def test_unchanged_rows_are_reused_and_a_changed_row_is_read_again(self):
        with self.f.SessionLocal() as db:
            first = self.files(db)
        with self.f.SessionLocal() as db:
            second = self.files(db)
        self.assertEqual(set(first), self.case_file_ids)
        self.assertIsInstance(first[self.f.file.id], source_lineage.CaseFile)
        self.assertIs(second[self.f.file.id], first[self.f.file.id])
        with self.f.SessionLocal() as db:
            db.get(EvidenceFile, self.other.id).metadata_ = {'financial_review_progress': {'': {'request': {}}}}
            db.commit()
        with self.f.SessionLocal() as db:
            third = self.files(db)
        self.assertIs(third[self.f.file.id], first[self.f.file.id])
        self.assertIsNot(third[self.other.id], first[self.other.id])
        self.assertEqual(third[self.other.id].metadata_, {'financial_review_progress': {'': {'request': {}}}})

    def test_a_deleted_row_is_not_returned(self):
        with self.f.SessionLocal() as db:
            self.files(db)
            db.delete(db.get(EvidenceFile, self.other.id))
            db.commit()
        with self.f.SessionLocal() as db:
            self.assertEqual(set(self.files(db)), self.case_file_ids - {self.other.id})
        self.assertEqual(set(source_lineage._CASE_FILES[str(self.f.case.id)]), self.case_file_ids - {self.other.id})

    def test_a_session_with_unsaved_evidence_edits_reads_its_own_objects(self):
        with self.f.SessionLocal() as db:
            self.files(db)
        with self.f.SessionLocal() as db:
            file = db.get(EvidenceFile, self.other.id)
            file.metadata_ = {'statement_root_evidence_id': str(self.f.file.id)}
            files = self.files(db)
            self.assertIs(files[self.other.id], file)
            self.assertEqual(files[self.other.id].metadata_, {'statement_root_evidence_id': str(self.f.file.id)})

    def test_a_copy_already_held_by_the_session_does_not_hide_a_newer_row(self):
        with self.f.SessionLocal() as db:
            held = db.get(EvidenceFile, self.other.id)
            self.assertEqual(held.metadata_, {})
            with self.f.SessionLocal() as writer:
                writer.get(EvidenceFile, self.other.id).metadata_ = {'statement_parent_evidence_id': 'x'}
                writer.commit()
            self.assertEqual(self.files(db)[self.other.id].metadata_, {'statement_parent_evidence_id': 'x'})

    def test_copies_are_read_only(self):
        with self.f.SessionLocal() as db:
            copy = self.files(db)[self.f.file.id]
        with self.assertRaises(AttributeError):
            copy.metadata_ = {}
        with self.assertRaises(AttributeError):
            copy.stored_path

    def test_comparison_is_the_same_from_copies_and_from_evidence_rows(self):
        def view(db):
            entries, prepared = overlap.comparison_sources(db, self.f.case.id)
            return dict(entries), prepared, entries.families, set(entries.files), entries.unhydrated
        with self.f.SessionLocal() as db:
            plain = view(db)
        with patch.object(source_lineage, '_row_version', content_version), self.f.SessionLocal() as db:
            cold = view(db)
            warm = view(db)
        self.assertEqual(plain, cold)
        self.assertEqual(plain, warm)

    def test_signatures_are_reused_only_for_the_same_content(self):
        request = dict(currency='EUR', period_start='2023-01-01', period_end='2023-12-31', rows=[])
        expected = reviews._request_signature(request)
        self.assertEqual(reviews.request_signature(request), expected)
        with patch.object(reviews, '_request_signature', side_effect=AssertionError('validated again')):
            self.assertEqual(reviews.request_signature(dict(request)), expected)
        changed = {**request, 'currency': 'USD'}
        self.assertEqual(reviews.request_signature(changed), reviews._request_signature(changed))
        self.assertNotEqual(reviews.request_signature(changed), expected)

    def test_a_request_that_cannot_be_hashed_raw_behaves_as_before_and_is_not_kept(self):
        request = dict(currency='EUR', period_start=date(2023, 1, 1), period_end=date(2023, 12, 31), rows=[])
        with self.assertRaises(TypeError):
            reviews._request_signature(request)
        with self.assertRaises(TypeError):
            reviews.request_signature(request)
        self.assertEqual(len(reviews._SIGNATURES), 0)

    def test_payload_hashes_are_reused_until_the_row_changes(self):
        model = EvidenceTableGeometry
        keys, columns = (model.evidence_file_id, model.page_number), (model.engine_job_id,)
        digest = cast(model.payload, String)
        hashing = []
        def digested(db):
            return projection._digested(db, model, keys, columns, digest, model.evidence_file_id == self.f.file.id)
        with patch.object(projection, '_row_version', lambda model: cast(model.payload, String)), self.f.SessionLocal() as db:
            listener = lambda conn, cursor, statement, *args: hashing.append(statement.count('CAST'))
            event.listen(db.get_bind(), 'before_cursor_execute', listener)
            try:
                first = digested(db)
                hashed_first = len(hashing)
                second = digested(db)
                self.assertEqual(second, first)
                self.assertEqual(len(hashing), hashed_first + 1)  # Versions only, no second hashing query.
                geometry = db.scalar(select(model).where(model.evidence_file_id == self.f.file.id))
                geometry.payload = [*geometry.payload, {'changed': True}]
                db.commit()
                third = digested(db)
            finally:
                event.remove(db.get_bind(), 'before_cursor_execute', listener)
        self.assertEqual(len(first), 1)
        self.assertNotEqual(third[0][2], first[0][2])
        self.assertIn('changed', third[0][2])


def all_columns_version(session, model):
    """Stand-in for xmin in SQLite: the row's whole content."""
    from sqlalchemy import func
    return func.json_array(*(cast(column, String) for column in model.__table__.columns))


from services.financial import batch_import_history
from tests import test_financial_batch_import_history as history_tests


class CachedReceiptHistoryTests(history_tests.CurrentBatchImportHistoryTests):
    """Every saved-receipt behaviour holds with receipts reused per row version."""

    def setUp(self):
        batch_import_history._RECEIPTS.clear()
        self._versions = patch.object(batch_import_history, '_row_version', all_columns_version)
        self._versions.start()
        super().setUp()

    def tearDown(self):
        self._versions.stop()
        batch_import_history._RECEIPTS.clear()
        super().tearDown()

    def test_an_unchanged_statement_is_not_assessed_again_and_a_changed_one_is(self):
        with self.f.SessionLocal() as db:
            first = batch_import_history.current_imports(db, self.f.case.id, [self.source_id])
        with patch.object(batch_import_history, '_current_imports', side_effect=AssertionError('assessed again')), \
                self.f.SessionLocal() as db:
            self.assertEqual(batch_import_history.current_imports(db, self.f.case.id, [self.source_id]), first)
        with self.f.SessionLocal() as db:
            row = db.scalar(select(history_tests.FinancialTransaction).where(
                history_tests.FinancialTransaction.source_document_id == self.source_id))
            row.amount_minor += 10000
            db.commit()
        with self.f.SessionLocal() as db:
            changed = batch_import_history.current_imports(db, self.f.case.id, [self.source_id])
        with patch.object(batch_import_history, '_row_version', lambda session, model: None), self.f.SessionLocal() as db:
            self.assertEqual(changed, batch_import_history.current_imports(db, self.f.case.id, [self.source_id]))
        self.assertNotEqual(changed, first)

    def test_returned_receipts_are_private_copies(self):
        with self.f.SessionLocal() as db:
            first = batch_import_history.current_imports(db, self.f.case.id, [self.source_id])
            first[str(self.source_id)]['issues'].append('changed by a caller')
            again = batch_import_history.current_imports(db, self.f.case.id, [self.source_id])
        self.assertNotIn('changed by a caller', again[str(self.source_id)]['issues'])

    def test_repeated_source_receipts_share_bulk_queries_and_assessment(self):
        # Overrides the uncached count of 3: a miss adds three light version
        # reads; a hit reads versions only. Neither grows with repetitions.
        def run():
            statements = []
            with self.f.SessionLocal() as db:
                connection = db.connection()
                collect = lambda _conn, _cursor, statement, *_: statements.append(statement)
                event.listen(connection, 'before_cursor_execute', collect)
                try:
                    with patch.object(batch_import_history, 'current_saved_assessment',
                            wraps=batch_import_history.current_saved_assessment) as assess:
                        result = batch_import_history.current_imports(db, self.f.case.id, [self.source_id] * 143)
                finally:
                    event.remove(connection, 'before_cursor_execute', collect)
            self.assertTrue(all(sql.lstrip().upper().startswith('SELECT') for sql in statements))
            self.assertEqual(result[str(self.source_id)]['transaction_count'], 12)
            return len(statements), assess.call_count
        self.assertEqual(run(), (6, 1))
        self.assertEqual(run(), (3, 0))
        with self.f.SessionLocal() as db:
            self.assertEqual(batch_import_history.current_imports(db, uuid4(), [self.source_id]), {})
