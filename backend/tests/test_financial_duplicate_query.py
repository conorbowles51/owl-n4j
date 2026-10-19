"""Fresh comparison includes historical imports and reports its coverage."""

from unittest.mock import patch

from sqlalchemy import event, select

from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialStatementPeriod
from services.financial.duplicate_query import (
    DuplicateQueryLimitError, list_duplicate_candidates,
)
from services.financial.duplicates import fingerprint_document, store_fingerprint
from tests.test_financial_duplicates import (
    DuplicateTestCase, FEB, FEB_28, JAN, JAN_31, PeriodBounds,
    PeriodBoundsSource, printed,
)


class DuplicateQueryTests(DuplicateTestCase):
    def test_same_filename_comparisons_identify_each_saved_period_and_source(self):
        documents = []
        for start, end in ((JAN, JAN_31), (FEB, FEB_28)):
            for _ in range(2):
                document = self.make_copy(bounds=PeriodBounds.printed(start, end))
                document.metadata_ = {'statement_import_statement_id': f'{len(documents):064x}'}
                self.db.get(EvidenceFile, document.evidence_file_id).original_filename = 'combined.pdf'
                documents.append(document)
        self.account.holder_name = 'Synthetic Holder'
        self.db.commit()

        result = list_duplicate_candidates(self.db, self.case.id)
        self.assertEqual(len(result['groups']), 2)
        by_id = {str(document.id): document for document in documents}
        seen = set()
        for group in result['groups']:
            dates = set()
            for member in group['members']:
                document = by_id[member['document_id']]
                period = self.db.scalar(select(FinancialStatementPeriod).where(
                    FinancialStatementPeriod.source_document_id == document.id))
                self.assertEqual(member['filename'], 'combined.pdf')
                self.assertEqual(member['evidence_file_id'], str(document.evidence_file_id))
                self.assertEqual(member['statement_id'], document.metadata_['statement_import_statement_id'])
                self.assertEqual(member['statement_context'], [dict(
                    period_id=str(period.id), account_id=str(self.account.id),
                    bank='Barclays', account_holder='Synthetic Holder',
                    account_number=self.account.identifier_as_printed, currency='GBP',
                    period_start=period.period_start.isoformat(), period_end=period.period_end.isoformat())])
                dates.add(member['statement_context'][0]['period_start'])
            self.assertEqual(len(dates), 1)
            seen.update(dates)
        self.assertEqual(seen, {'2026-01-01', '2026-02-01'})

    def test_zero_row_multiperiod_documents_keep_all_saved_context_when_excluded(self):
        from postgres.models.financial_candidates import FinancialCandidateFinalization
        from services.financial.ledger_source import statement_source
        import uuid
        FinancialCandidateFinalization.__table__.create(self.engine)
        other_account = self._account(self.case.id, identity_key='another-account')
        other_account.institution_name = 'Synthetic Bank'
        other_account.holder_name = 'Another Holder'
        self.db.add(other_account)
        self.db.commit()
        expected = {}
        for _ in range(2):
            document = self.make_copy(rows=())
            self.make_period(document, account=other_account, bounds=PeriodBounds.printed(FEB, FEB_28))
            self.db.commit()
            expected[str(document.id)] = {
                str(period.id) for period in self.db.scalars(select(FinancialStatementPeriod).where(
                    FinancialStatementPeriod.source_document_id == document.id))}
        self.resolve()
        self.db.commit()

        result = list_duplicate_candidates(self.db, self.case.id)
        self.assertEqual(len(result['groups']), 1)
        self.assertEqual(len(result['excluded_documents']), 1)
        for member in result['groups'][0]['members'] + result['excluded_documents']:
            self.assertEqual(member['rows_by_status'], {})
            self.assertEqual({row['period_id'] for row in member['statement_context']}, expected[member['document_id']])
            self.assertEqual({row['account_id'] for row in member['statement_context']},
                             {str(self.account.id), str(other_account.id)})
            self.assertEqual([row['period_start'] for row in member['statement_context']],
                             ['2026-01-01', '2026-02-01'])
        for member in result['groups'][0]['members']:
            self.assertIsNone(member['source_transaction_id'])
            for context in member['statement_context']:
                source = statement_source(self.db, case_id=self.case.id,
                                          period_id=uuid.UUID(context['period_id']))
                self.assertEqual(source['period_id'], context['period_id'])
                self.assertEqual(source['source_document_id'], member['document_id'])
                self.assertEqual(source['evidence_file_id'], member['evidence_file_id'])

    def test_context_preserves_cleared_saved_headers_and_unknown_dates(self):
        bounds = PeriodBounds(start=JAN, end=None, start_source=PeriodBoundsSource.printed,
                              end_source=PeriodBoundsSource.absent)
        first = self.make_copy(bounds=bounds)
        self.make_copy(bounds=bounds)
        self.account.holder_name = 'Other statement holder'
        first.document_type = 'statement_review'
        first.metadata_ = {
            'statement_import_statement_id': 'not-a-valid-section-id',
            'statement_import_request': {'institution': 'Saved Bank', 'holder': 'Original Holder',
                                         'account_number': 'Saved Account'},
            'statement_details_review': {'details': {'holder': '', 'account_number': ''}},
        }
        self.db.commit()

        result = list_duplicate_candidates(self.db, self.case.id)
        member = next(row for row in result['groups'][0]['members'] if row['document_id'] == str(first.id))
        context = member['statement_context'][0]
        self.assertEqual(context['bank'], 'Saved Bank')
        self.assertIsNone(context['account_holder'])
        self.assertIsNone(context['account_number'])
        self.assertEqual(context['period_start'], '2026-01-01')
        self.assertIsNone(context['period_end'])  # Never substitute the latest transaction date.
        self.assertIsNone(member['statement_id'])

    def test_context_does_not_leak_foreign_period_account_or_evidence_links(self):
        foreign = self.make_copy(case=self.other_case, run=self.other_run, account=self.other_account)
        self.other_account.holder_name = 'Private foreign holder'
        self.db.get(EvidenceFile, foreign.evidence_file_id).original_filename = 'private-foreign-file.pdf'
        documents = [self.make_copy() for _ in range(3)]
        periods = [self.db.scalar(select(FinancialStatementPeriod).where(
            FinancialStatementPeriod.source_document_id == document.id)) for document in documents]
        # Simulate historical inconsistent links; projections must still enforce case boundaries.
        periods[0].account_id = self.other_account.id
        periods[1].case_id = self.other_case.id
        documents[2].evidence_file_id = foreign.evidence_file_id
        for document in documents:
            document.status = 'quarantined'
            document.quarantine_reason = 'unexplained_delta'
        self.db.commit()

        result = list_duplicate_candidates(self.db, self.case.id)
        by_id = {row['document_id']: row for row in result['skipped']}
        self.assertEqual(result['documents'], 3)
        self.assertNotIn(str(foreign.id), by_id)
        self.assertEqual(by_id[str(documents[0].id)]['statement_context'], [])
        self.assertEqual(by_id[str(documents[1].id)]['statement_context'], [])
        invalid_source = by_id[str(documents[2].id)]
        self.assertIsNone(invalid_source['evidence_file_id'])
        self.assertEqual(invalid_source['filename'], 'Source file unavailable')
        self.assertNotIn('Private foreign holder', str(result))
        self.assertNotIn('private-foreign-file.pdf', str(result))
        for row in by_id.values():
            self.assertNotIn('rows_by_status', row)  # Held rows were not compared: their count is unknown.

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

    def test_same_source_hash_survives_different_account_identity(self):
        other = self._account(self.case.id, identity_key='separately-recorded-account')
        self.db.add(other)
        self.db.commit()
        self.make_copy(sha256='a'*64)
        self.make_copy(sha256='a'*64, account=other)
        result = list_duplicate_candidates(self.db, self.case.id)
        self.assertEqual(result['groups'], [])
        self.assertEqual(len(result['source_hash_groups']), 1)
        self.assertEqual(len(result['source_hash_groups'][0]['members']), 2)
        self.assertIn('different or unavailable', result['source_hash_groups'][0]['limitation'])
        members = result['source_hash_groups'][0]['members']
        self.assertEqual({member['statement_context'][0]['account_id'] for member in members},
                         {str(self.account.id), str(other.id)})
        self.assertTrue(all(member['evidence_file_id'] for member in members))
        self.assertTrue(all(member['rows_by_status'] == {'admitted': 2} for member in members))

    def test_bulk_scan_revisions_match_the_locked_writer_with_bounded_queries(self):
        from services.financial.duplicate_decisions import duplicate_revision
        for _ in range(20): self.make_copy(fingerprint=False)
        case_id = self.case.id
        statements = []
        def capture(_conn, _cursor, sql, _params, _context, _many):
            statements.append(sql)
        event.listen(self.engine, 'before_cursor_execute', capture)
        try:
            result = list_duplicate_candidates(self.db, case_id)
        finally:
            event.remove(self.engine, 'before_cursor_execute', capture)
        self.assertLessEqual(len(statements), 10)
        self.assertEqual(result['stored_rows_in_case'], 40)
        from postgres.models.financial import FinancialSourceDocument
        for row in result['groups'][0]['members']:
            import uuid
            document = self.db.get(FinancialSourceDocument, uuid.UUID(row['document_id']))
            self.assertEqual(row['revision'], duplicate_revision(self.db, document))

    def test_reading_and_period_limits_refuse_the_whole_comparison(self):
        self.make_copy()
        for name in ('MAX_COMPARISON_ROWS', 'MAX_COMPARISON_PERIODS'):
            with patch('services.financial.duplicate_query.'+name, 0):
                with self.assertRaises(DuplicateQueryLimitError):
                    list_duplicate_candidates(self.db, self.case.id)

    def test_held_source_hash_match_is_visible_without_comparing_held_readings(self):
        self.make_copy(sha256='c'*64)
        held=self.make_copy(sha256='c'*64)
        held.status='quarantined';held.quarantine_reason='unexplained_delta'
        self.db.commit()
        result=list_duplicate_candidates(self.db,self.case.id)
        self.assertEqual(result['compared'],1)
        self.assertEqual(len(result['skipped']),1)
        self.assertEqual(len(result['source_hash_groups']),1)
        self.assertIn('quarantined',[r['status'] for r in result['source_hash_groups'][0]['members']])
