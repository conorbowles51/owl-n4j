"""Fresh comparison includes historical imports and reports its coverage."""

from unittest.mock import patch

from sqlalchemy import event, select

from postgres.models.financial import FinancialStatementPeriod
from services.financial.duplicate_query import (
    DuplicateQueryLimitError, list_duplicate_candidates,
)
from services.financial.duplicates import fingerprint_document, store_fingerprint
from tests.test_financial_duplicates import DuplicateTestCase, printed


class DuplicateQueryTests(DuplicateTestCase):
    def test_historical_imports_are_compared_without_writing_fingerprints(self):
        first = self.make_copy(fingerprint=False)
        self.make_copy(fingerprint=False)
        self.make_copy(case=self.other_case, run=self.other_run,
                       account=self.other_account)
        writes = []

        def capture(_conn, _cursor, sql, _params, _context, _many):
            if sql.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
                writes.append(sql)

        event.listen(self.engine, "before_cursor_execute", capture)
        try:
            result = list_duplicate_candidates(self.db, self.case.id)
            self.db.commit()
        finally:
            event.remove(self.engine, "before_cursor_execute", capture)
        self.assertEqual(result["documents"], 2)
        self.assertEqual(result["compared"], 2)
        self.assertEqual(len(result["groups"]), 1)
        self.assertEqual(result["groups"][0]["members"][1]["match"], "identical_reading")
        self.assertIsNone(self.reload(first).duplicate_group_key)
        self.assertEqual(writes, [])

    def test_empty_documents_are_uncompared_not_identical(self):
        first = self.make_document()
        self.make_document()
        store_fingerprint(self.db, first)
        result = list_duplicate_candidates(self.db, self.case.id)
        self.assertEqual(result["compared"], 0)
        self.assertEqual(len(result["skipped"]), 2)
        self.assertEqual(result["groups"], [])
        self.assertIsNone(first.content_fingerprint)

    def test_stale_stored_keys_do_not_hide_changed_rows(self):
        first = self.make_copy()
        second = self.make_copy()
        period = self.db.scalar(select(FinancialStatementPeriod).where(
            FinancialStatementPeriod.source_document_id == second.id
        ))
        self.add_row(period, second, amount=17)
        self.assertEqual(first.content_fingerprint, second.content_fingerprint)
        result = list_duplicate_candidates(self.db, self.case.id)
        self.assertEqual(result["groups"][0]["members"][1]["match"], "shared_coverage")

    def test_same_bytes_can_have_different_readings(self):
        self.make_copy(sha256="a" * 64)
        self.make_copy(sha256="a" * 64, rows=((400_00, "aa"),))
        result = list_duplicate_candidates(self.db, self.case.id)
        self.assertEqual(result["groups"][0]["members"][1]["match"],
                         "same_file_different_reading")

    def test_preview_reports_actual_supersession_and_row_statuses(self):
        self.make_copy()
        self.make_copy()
        self.resolve()
        self.db.commit()
        result = list_duplicate_candidates(self.db, self.case.id)
        first, second = result["groups"][0]["members"]
        self.assertEqual(first["status"], "admitted")
        self.assertEqual(second["status"], "superseded")
        self.assertEqual(second["superseded_by_id"], first["document_id"])
        self.assertEqual(second["rows_by_status"], {"superseded": 2})

    def test_document_cap_fails_whole_instead_of_silently_truncating(self):
        self.make_copy()
        self.make_copy()
        with patch("services.financial.duplicate_query.MAX_COMPARISON_DOCUMENTS", 1):
            with self.assertRaises(DuplicateQueryLimitError):
                list_duplicate_candidates(self.db, self.case.id)

    def test_balance_observations_change_reading_but_not_coverage(self):
        first = self.make_copy(closing=printed(380_00))
        second = self.make_copy(closing=printed(520_00))
        self.assertEqual(first.duplicate_group_key, second.duplicate_group_key)
        self.assertNotEqual(first.content_fingerprint, second.content_fingerprint)

    def test_unlinked_rows_participate_even_alongside_linked_rows(self):
        first = self.make_copy()
        second = self.make_copy()
        # The fixture helper needs a period-shaped object; the stored link is NULL.
        from types import SimpleNamespace
        self.add_row(SimpleNamespace(id=None), second, amount=17)
        self.assertNotEqual(fingerprint_document(self.db, first),
                            fingerprint_document(self.db, second))

    def test_periodless_payment_files_do_not_share_the_empty_digest(self):
        from types import SimpleNamespace
        first = self.make_document()
        second = self.make_document()
        self.add_row(SimpleNamespace(id=None), first, amount=17, content_hash="a" * 64)
        self.add_row(SimpleNamespace(id=None), second, amount=18, content_hash="b" * 64)
        a = fingerprint_document(self.db, first)
        b = fingerprint_document(self.db, second)
        self.assertEqual(a.group_key, b.group_key)
        self.assertNotEqual(a.content_fingerprint, b.content_fingerprint)
