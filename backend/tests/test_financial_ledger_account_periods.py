"""Account filters include saved periods without manufacturing ledger activity."""
from unittest.mock import patch
from unittest import IsolatedAsyncioTestCase
from uuid import uuid4

from sqlalchemy import event, func, select

from postgres.models.financial import FinancialStatementPeriod, FinancialTransaction
from services.financial.candidate_store import CandidateStoreError, list_candidate_accounts
from tests.test_financial_duplicates import DuplicateTestCase, FEB, FEB_28, PeriodBounds, PeriodBoundsSource


class LedgerAccountPeriodTests(DuplicateTestCase):
    def directory(self, **kwargs):
        return list_candidate_accounts(self.db, case_id=self.case.id,
            include_statement_periods=True, **kwargs)

    def period(self, document):
        return self.db.scalar(select(FinancialStatementPeriod).where(
            FinancialStatementPeriod.source_document_id == document.id))

    def test_zero_payment_eur_account_retains_registered_currency_and_dates(self):
        document = self.make_copy(rows=())
        period = self.period(document)
        self.account.currency = period.currency = 'EUR'
        self.account.account_type = 'checking'
        self.db.commit()

        account = self.directory()['items'][0]
        self.assertEqual(account['currency'], 'EUR')
        self.assertEqual(account['institution'], 'Barclays')
        self.assertEqual(account['account_type'], 'checking')
        self.assertEqual(account['statement_periods'], [dict(id=str(period.id),
            source_document_id=str(document.id), start='2026-01-01', end='2026-01-31', currency='EUR')])
        self.assertNotIn('no_activity_confirmed', account)
        self.assertNotIn('transaction_count', account)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(FinancialTransaction)), 0)

    def test_paginated_aliases_keep_each_registered_period_once_and_actual_identity(self):
        first = self.make_copy(rows=())
        alias = self._account(self.case.id, identity_key='synthetic-alias')
        alias.metadata_ = {'canonical_account_id':str(self.account.id)}
        self.db.add(alias); self.db.commit()
        second = self.make_copy(rows=(), account=alias, bounds=PeriodBounds.printed(FEB, FEB_28))
        first_page = self.directory(limit=1)
        second_page = self.directory(limit=1, offset=1)
        self.assertTrue(first_page['has_more'])
        self.assertFalse(second_page['has_more'])
        accounts = first_page['items'] + second_page['items']
        self.assertEqual({account['canonical_id'] for account in accounts}, {str(self.account.id)})
        sources = {account['id']:[period['source_document_id'] for period in account['statement_periods']]
            for account in accounts}
        self.assertEqual(sources, {str(self.account.id):[str(first.id)], str(alias.id):[str(second.id)]})
        self.assertEqual(len({period['id'] for account in accounts for period in account['statement_periods']}), 2)

    def test_only_current_case_owned_admitted_periods_are_exposed(self):
        current = self.make_copy(rows=())
        foreign = self.make_copy(rows=(), case=self.other_case, run=self.other_run, account=self.other_account)
        excluded = [self.make_copy(rows=()) for _ in range(8)]
        excluded[0].status = 'superseded'
        excluded[1].status = 'quarantined'
        excluded[1].quarantine_reason = 'unexplained_delta'
        excluded[2].metadata_ = {'financial_import_removal': {'reason':'Synthetic removal'}}
        excluded[3].superseded_by_id = current.id
        self.period(excluded[4]).case_id = self.other_case.id
        self.period(excluded[5]).account_id = self.other_account.id
        self.period(excluded[6]).source_document_id = foreign.id
        excluded[7].evidence_file_id = foreign.evidence_file_id
        self.db.commit()
        account = self.directory()['items'][0]
        self.assertEqual([period['source_document_id'] for period in account['statement_periods']], [str(current.id)])
        self.assertTrue(all(self.db.get(type(document), document.id) is not None for document in excluded))

    def test_unknown_dates_are_not_filled_from_payments_or_other_sources(self):
        document = self.make_copy(bounds=PeriodBounds(start=None, end=None,
            start_source=PeriodBoundsSource.absent, end_source=PeriodBoundsSource.absent))
        self.account.currency = None
        self.db.commit()
        account = self.directory()['items'][0]
        self.assertIsNone(account['currency'])
        self.assertEqual(account['statement_periods'], [dict(id=str(self.period(document).id),
            source_document_id=str(document.id), start=None, end=None, currency='GBP')])
        self.assertEqual(self.db.scalar(select(func.count()).select_from(FinancialTransaction)), 2)

    def test_context_uses_one_scalar_query_per_page_and_does_not_write(self):
        document = self.make_copy(rows=())
        document.metadata_ = {'statement_import_original': {'large_source_body':'x' * 100000}}
        self.db.commit()
        case_id = self.case.id

        def read():
            queries = []
            def capture(_conn, _cursor, sql, _params, _context, _many):
                queries.append(sql)
            event.listen(self.engine, 'before_cursor_execute', capture)
            try:
                result = list_candidate_accounts(self.db, case_id=case_id, include_statement_periods=True)
                self.db.commit()
            finally:
                event.remove(self.engine, 'before_cursor_execute', capture)
            self.assertTrue(all(sql.lstrip().split()[0].upper() == 'SELECT' for sql in queries))
            period_queries = [sql for sql in queries if 'FROM financial_statement_periods' in sql]
            self.assertEqual(len(period_queries), 1)
            self.assertIn('JSON_EXTRACT', period_queries[0])
            self.assertNotIn(', financial_source_documents.metadata', period_queries[0])
            return result, len(queries)

        _, initial_queries = read()
        for number in range(20):
            account = self._account(case_id, identity_key=f'context-{number}')
            self.db.add(account); self.db.commit()
            self.make_copy(rows=(), account=account)
        result, expanded_queries = read()
        self.assertEqual(len(result['items']), 21)
        self.assertEqual(expanded_queries, initial_queries)
        self.assertLessEqual(expanded_queries, 4)

    def test_account_without_period_is_not_a_confirmed_quiet_statement(self):
        account = self.directory()['items'][0]
        self.assertEqual(account['statement_periods'], [])
        self.assertNotIn('no_activity_confirmed', account)

    def test_context_does_not_silently_truncate_coverage(self):
        self.make_copy(rows=()); self.make_copy(rows=())
        with patch('services.financial.candidate_store.MAX_ACCOUNT_DIRECTORY_PERIODS', 1):
            with self.assertRaisesRegex(CandidateStoreError, 'no incomplete coverage'):
                self.directory()

    def test_internal_account_lookup_does_not_require_statement_context(self):
        with patch('services.financial.candidate_store._account_statement_periods',
                side_effect=AssertionError('Unrequested context read')):
            account = list_candidate_accounts(self.db, case_id=self.case.id)['items'][0]
        self.assertNotIn('statement_periods', account)


class LedgerAccountPeriodRouterTests(IsolatedAsyncioTestCase):
    async def test_ledger_directory_requests_period_context_for_every_page(self):
        from routers import financial_ledger
        case_id = uuid4()
        response = {'case_id':str(case_id), 'items':[], 'has_more':False}
        with patch.object(financial_ledger, 'list_candidate_accounts', return_value=response) as read:
            result = await financial_ledger.get_candidate_accounts(case_id=case_id,
                search='Synthetic bank', offset=100, db='session')
        self.assertEqual(result, response)
        read.assert_called_once_with('session', case_id=case_id, search='Synthetic bank', offset=100,
            include_pending=True, include_statement_periods=True)
