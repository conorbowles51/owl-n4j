"""Quiet saved sources contribute directory context without becoming payments."""
from unittest.mock import patch

from sqlalchemy import event, select, func

from postgres.models.financial import FinancialStatementPeriod, FinancialTransaction
from services.financial.account_parties import (
    AccountPartyError, AccountPartyRequest, account_parties, set_account_party,
)
from tests.test_financial_duplicates import (
    DuplicateTestCase, FEB, FEB_28, PeriodBounds, PeriodBoundsSource,
)


class AccountPartyPeriodTests(DuplicateTestCase):
    def directory(self):
        return account_parties(self.db, case_id=self.case.id)

    def period(self, document):
        return self.db.scalar(select(FinancialStatementPeriod).where(
            FinancialStatementPeriod.source_document_id == document.id))

    def test_quiet_saved_statement_has_source_dates_and_account_type_without_payments(self):
        document = self.make_copy(rows=())
        self.account.account_type = 'credit_card'
        self.account.holder_name = 'Synthetic holder'
        self.db.commit()
        period = self.period(document)

        result = self.directory()
        account = result['accounts'][0]
        self.assertEqual(account['account_type'], 'credit_card')
        self.assertEqual(account['holder_as_recorded'], 'Synthetic holder')
        self.assertEqual(account['institution'], 'Barclays')
        self.assertEqual(account['currency'], 'GBP')
        self.assertEqual(account['statement_periods'], [dict(
            id=str(period.id), source_document_id=str(document.id),
            start='2026-01-01', end='2026-01-31')])
        # No page-bearing original and no payment exist; context comes from the registered period.
        self.assertEqual(result['source_choices'], [])
        self.assertEqual(self.db.scalar(select(func.count()).select_from(FinancialTransaction)), 0)
        self.assertIsNone(account['party'])
        self.assertEqual(account['relationships'], [])
        self.assertFalse(result['applied'])

    def test_multiple_accounts_keep_separate_sources_and_unknown_statement_dates(self):
        first = self.make_copy(rows=())
        other = self._account(self.case.id, identity_key='second-account')
        other.holder_name = self.account.holder_name = 'Shared printed name'
        other.account_type = 'checking'
        self.db.add(other)
        self.db.commit()
        second = self.make_copy(rows=(), account=other, bounds=PeriodBounds.printed(FEB, FEB_28))
        unknown = self.make_copy(rows=(), account=other, bounds=PeriodBounds(
            start=None, end=None, start_source=PeriodBoundsSource.absent,
            end_source=PeriodBoundsSource.absent))

        result = self.directory()
        by_id = {account['id']: account for account in result['accounts']}
        self.assertEqual({p['source_document_id'] for p in by_id[str(self.account.id)]['statement_periods']},
                         {str(first.id)})
        periods = by_id[str(other.id)]['statement_periods']
        self.assertEqual({p['source_document_id'] for p in periods}, {str(second.id), str(unknown.id)})
        missing = next(p for p in periods if p['source_document_id'] == str(unknown.id))
        self.assertIsNone(missing['start'])
        self.assertIsNone(missing['end'])
        self.assertEqual(result['parties'], [])
        self.assertTrue(all(not account['holder_parties'] for account in result['accounts']))

    def test_excluded_removed_held_and_stale_sources_do_not_count_as_current_periods(self):
        current = self.make_copy(rows=())
        hidden = [self.make_copy(rows=()) for _ in range(5)]
        hidden[0].status = 'superseded'
        hidden[0].superseded_by_id = current.id
        hidden[1].status = 'rejected'
        hidden[2].status = 'quarantined'
        hidden[2].quarantine_reason = 'unexplained_delta'
        hidden[3].metadata_ = {'financial_import_removal': {'reason': 'Investigator removed import'}}
        hidden[4].superseded_by_id = current.id  # Inconsistent historical admitted status must not count twice.
        self.db.commit()

        account = self.directory()['accounts'][0]
        self.assertEqual([p['source_document_id'] for p in account['statement_periods']], [str(current.id)])
        for document in hidden:
            self.assertIsNotNone(self.db.get(type(document), document.id))

    def test_foreign_case_and_inconsistent_period_account_source_or_evidence_links_are_excluded(self):
        current = self.make_copy(rows=())
        foreign = self.make_copy(rows=(), case=self.other_case, run=self.other_run, account=self.other_account)
        malformed = [self.make_copy(rows=()) for _ in range(4)]
        self.period(malformed[0]).case_id = self.other_case.id
        self.period(malformed[1]).account_id = self.other_account.id
        self.period(malformed[2]).source_document_id = foreign.id
        malformed[3].evidence_file_id = foreign.evidence_file_id
        self.db.commit()

        result = self.directory()
        self.assertEqual([account['id'] for account in result['accounts']], [str(self.account.id)])
        self.assertEqual([p['source_document_id'] for p in result['accounts'][0]['statement_periods']],
                         [str(current.id)])

    def test_unknown_dates_are_not_filled_from_existing_payments(self):
        document = self.make_copy(bounds=PeriodBounds(
            start=None, end=None, start_source=PeriodBoundsSource.absent,
            end_source=PeriodBoundsSource.absent))
        account = self.directory()['accounts'][0]
        self.assertEqual(account['statement_periods'], [dict(
            id=str(self.period(document).id), source_document_id=str(document.id), start=None, end=None)])
        self.assertEqual(self.db.scalar(select(func.count()).select_from(FinancialTransaction)), 2)

    def test_account_without_saved_periods_stays_distinct_from_quiet_statement(self):
        self.account.account_type = 'savings'
        self.db.commit()
        account = self.directory()['accounts'][0]
        self.assertEqual(account['account_type'], 'savings')
        self.assertEqual(account['statement_periods'], [])
        self.assertNotIn('no_activity_confirmed', account)

    def test_period_change_invalidates_directory_revision_without_changing_ownership(self):
        document = self.make_copy(rows=())
        before = self.directory()
        period = self.period(document)
        period.period_start, period.period_end = FEB, FEB_28
        self.db.commit()
        after = self.directory()
        self.assertNotEqual(before['revision'], after['revision'])
        with self.assertRaises(AccountPartyError) as error:
            set_account_party(self.db, case_id=self.case.id, actor=self.actor,
                request=AccountPartyRequest(expected_revision=before['revision'],
                    account_ids=[self.account.id], new_party_name='Synthetic person',
                    reason='Checked the printed holder'))
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.directory()['history'], [])

    def test_directory_periods_are_one_batched_read_and_do_not_write(self):
        self.make_copy(rows=())
        case_id = self.case.id

        def read():
            queries, writes = [], []
            def capture(_conn, _cursor, sql, _params, _context, _many):
                queries.append(sql)
                if sql.lstrip().split()[0].upper() in {'INSERT', 'UPDATE', 'DELETE'}:
                    writes.append(sql)
            event.listen(self.engine, 'before_cursor_execute', capture)
            try:
                result = account_parties(self.db, case_id=case_id)
                self.db.commit()
            finally:
                event.remove(self.engine, 'before_cursor_execute', capture)
            self.assertEqual(writes, [])
            return result, len(queries)

        _, initial_queries = read()
        for index in range(20):
            account = self._account(case_id, identity_key=f'directory-{index}')
            self.db.add(account)
            self.db.commit()
            self.make_copy(rows=(), account=account)
        result, expanded_queries = read()
        self.assertEqual(len(result['accounts']), 21)
        self.assertTrue(all(len(account['statement_periods']) == 1 for account in result['accounts']))
        self.assertEqual(expanded_queries, initial_queries)
        self.assertLessEqual(expanded_queries, 8)

    def test_directory_does_not_silently_truncate_registered_periods(self):
        self.make_copy(rows=())
        self.make_copy(rows=())
        with patch('services.financial.account_parties.MAX_DIRECTORY_STATEMENT_PERIODS', 1):
            with self.assertRaisesRegex(AccountPartyError, 'no incomplete account directory'):
                self.directory()
