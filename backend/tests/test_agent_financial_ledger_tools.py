"""Synthetic complete-population agent reads; no graph or client fixtures."""
from copy import deepcopy
from datetime import date
from unittest.mock import patch
import unittest
from uuid import UUID

from sqlalchemy import event

from postgres.base import Base
from postgres.models.enums import LedgerStatus, TransactionDirection
from postgres.models.financial_candidates import (
    FinancialCandidateMapping, FinancialExtractionCandidate,
    FinancialCandidateReview, FinancialCandidateFinalization,
)
from services.agent.financial_ledger_tools import read_financial_ledger, FinancialLedgerToolError
from tests.test_financial_duplicates import DuplicateTestCase


class FinancialAgentLedgerTests(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.engine, tables=[model.__table__ for model in (
            FinancialCandidateMapping, FinancialExtractionCandidate,
            FinancialCandidateReview, FinancialCandidateFinalization)])
        self.account.account_type = 'bank'
        self.account.currency = 'EUR'
        self.account.holder_name = 'Synthetic company'
        self.card = self._account(self.case.id, identity_key='synthetic-card')
        self.card.account_type = 'credit_card'
        self.card.currency = 'USD'
        self.quiet = self._account(self.case.id, identity_key='synthetic-quiet')
        self.quiet.currency = 'EUR'
        self.db.add_all([self.card, self.quiet])
        self.db.commit()

    def source(self, account=None, currency='EUR', rows=0, amount=101):
        account = account or self.account
        document = self.make_document()
        period = self.make_period(document, account=account)
        period.currency = currency
        document.metadata_ = dict(statement_account_id=str(account.id),
            statement_import_request={'currency': currency})
        self.db.commit()
        created = []
        for index in range(rows):
            row = self.add_row(period, document, amount=amount + index, account=account,
                direction=TransactionDirection.debit if index % 2 else TransactionDirection.credit)
            row.currency = currency
            row.counterparty_raw = 'Exact source company'
            created.append(row)
        self.db.commit()
        return document, period, created

    def read(self, **options):
        return read_financial_ledger(self.db, case_id=self.case.id, **options)

    def test_complete_pages_exact_mixed_totals_and_no_writes_or_graph(self):
        self.source(rows=121, amount=9007199254740993)
        self.source(self.card, currency='USD', rows=11, amount=10)
        self.source(self.card, currency='EUR', rows=3, amount=20)
        self.source(self.quiet)
        sql = []
        def record(_connection, _cursor, statement, *_):
            sql.append(statement)
        event.listen(self.engine, 'before_cursor_execute', record)
        try:
            first = self.read(limit=50)
            second = self.read(limit=50, offset=50, expected_revision=first['revision'])
            third = self.read(limit=50, offset=100, expected_revision=first['revision'])
        finally:
            event.remove(self.engine, 'before_cursor_execute', record)
        self.assertEqual(first['total_matching'], 135)
        self.assertEqual([page['returned'] for page in (first, second, third)], [50, 50, 35])
        self.assertEqual(len({r['transaction_id'] for p in (first, second, third) for r in p['items']}), 135)
        self.assertFalse(third['has_more'])
        self.assertIsNone(third['next_offset'])
        self.assertEqual(first['totals'], third['totals'])
        groups = {(g['currency'], g['account_type']): g for g in first['totals']}
        self.assertEqual(set(groups), {('EUR', 'bank'), ('EUR', 'credit_card'), ('USD', 'credit_card')})
        self.assertEqual(groups['EUR', 'bank']['credits_minor'], str(sum(9007199254740993 + i for i in range(0, 121, 2))))
        self.assertEqual(groups['EUR', 'bank']['debits_minor'], str(sum(9007199254740993 + i for i in range(1, 121, 2))))
        self.assertEqual(first['coverage']['registered_accounts'], 3)
        self.assertEqual(first['coverage']['registered_accounts_without_matching_payments'], 1)
        self.assertTrue(all(s.lstrip().upper().startswith('SELECT') for s in sql))
        self.assertFalse(self.db.new or self.db.dirty or self.db.deleted)
        self.assertTrue(all('/cases/' + str(self.case.id) + '/' in r['source']['evidence_href'] for r in first['items']))

    def test_saved_labels_filters_and_changed_revision_refuse_mixed_pages(self):
        from services.financial.payment_labels import PaymentLabelsRequest, update_payment_labels
        document, _, rows = self.source(rows=3)
        before = self.read(limit=1)
        update_payment_labels(self.db, case_id=self.case.id, actor=self.actor,
            request=PaymentLabelsRequest(transactions=[{'id': rows[0].id, 'version': 0}],
                category='Reviewed category', from_name='Reviewed sender'))
        stale = self.read(offset=1, expected_revision=before['revision'])
        self.assertFalse(stale['available'])
        self.assertEqual(stale['reason_code'], 'stale_revision')
        self.assertEqual(stale['items'], [])
        self.assertEqual(stale['totals'], [])
        self.assertIsNone(stale['total_matching'])
        filtered = self.read(filters={'category': 'Reviewed category', 'currency': 'EUR',
            'direction': 'credit', 'minimum_minor': '101', 'maximum_minor': '101'})
        self.assertEqual(filtered['total_matching'], 1)
        self.assertEqual(filtered['items'][0]['from_name'], 'Reviewed sender')
        self.assertEqual(filtered['items'][0]['source']['source_document_id'], str(document.id))
        self.assertEqual(self.read(filters={'search': 'Reviewed sender'})['total_matching'], 1)
        with self.assertRaises(FinancialLedgerToolError):
            self.read(offset=1)

    def test_related_analysis_can_pin_same_capture_across_views_and_filters(self):
        self.source(rows=3)
        first = self.read()
        grouped = self.read(view='groups', group_by='month', filters={'currency': 'EUR'},
            expected_ledger_revision=first['ledger_revision'])
        self.assertTrue(grouped['available'])
        self.assertEqual(grouped['ledger_revision'], first['ledger_revision'])
        self.assertNotEqual(grouped['revision'], first['revision'])
        coverage = self.read(view='coverage', expected_ledger_revision=first['ledger_revision'])
        self.assertEqual(coverage['ledger_revision'], first['ledger_revision'])
        self.source(self.quiet)
        changed = self.read(view='groups', expected_ledger_revision=first['ledger_revision'])
        self.assertFalse(changed['available'])
        self.assertEqual(changed['reason_code'], 'stale_ledger_revision')
        self.assertEqual(changed['totals'], [])

    def test_currency_exponents_do_not_assume_two_decimal_places(self):
        self.source(currency='JPY', rows=1, amount=12345)
        self.source(self.card, currency='KWD', rows=1, amount=12345)
        result = self.read()
        self.assertEqual({t['currency']: t['currency_exponent'] for t in result['totals']}, {'JPY': 0, 'KWD': 3})
        self.assertEqual({r['currency']: r['currency_exponent'] for r in result['items']}, {'JPY': 0, 'KWD': 3})
        self.assertTrue(all(t['credits_minor'] == '12345' for t in result['totals']))

    def test_exclusions_incomplete_and_quiet_periods_remain_separate(self):
        document, period, rows = self.source(rows=4)
        rows[0].ledger_status = 'rejected'
        rows[1].ledger_status = 'superseded'
        rows[2].proof_class = 'p3'
        document.metadata_ = {**document.metadata_, 'statement_incomplete_records': [
            {'id': 'unreadable', 'fields': {'description': 'Unfinished synthetic row', 'date': ''},
             'missing_fields': ['amount'], 'original': {'page_number': 2}},
            {'id': 'resolved', 'resolved_transaction_id': str(rows[3].id), 'fields': {}, 'missing_fields': []}]}
        self.db.commit()
        self.source(self.quiet)
        working = self.read()
        verified = self.read(population='verified')
        self.assertEqual((working['total_matching'], verified['total_matching']), (2, 1))
        self.assertEqual(working['coverage']['exclusions']['rejected'], 1)
        self.assertEqual(working['coverage']['incomplete_records'], 1)
        excluded = self.read(view='excluded')
        self.assertEqual(excluded['total_matching'], 2)
        self.assertTrue(all(not row['included_in_totals'] for row in excluded['items']))
        incomplete = self.read(view='incomplete', start_date='2026-03-01')
        self.assertEqual(incomplete['total_matching'], 1)  # unknown date stays explicit
        self.assertEqual(incomplete['items'][0]['id'], 'unreadable')
        self.assertFalse(incomplete['items'][0]['included_in_totals'])
        self.assertEqual(incomplete['items'][0]['page_number'], 2)
        coverage = self.read(view='coverage')
        quiet = next(a for a in coverage['items'] if a['account_id'] == str(self.quiet.id))
        self.assertEqual(quiet['matching_payments_for_canonical_account'], 0)
        self.assertNotIn('no_activity_confirmed', quiet)
        with self.assertRaisesRegex(FinancialLedgerToolError, 'payment-specific'):
            self.read(view='incomplete', filters={'search': 'synthetic'})

    def test_canonical_accounts_months_counterparties_and_category_groups(self):
        _, _, rows = self.source(rows=3)
        alias = self._account(self.case.id, identity_key='synthetic-alias')
        alias.account_type = 'bank'
        alias.metadata_ = {'canonical_account_id': str(self.account.id)}
        self.db.add(alias)
        self.db.commit()
        self.source(alias, rows=2)
        rows[0].ordering_date = date(2026, 3, 1)
        rows[1].provenance = {'date_basis': 'statement_end_ordering_only'}
        self.db.commit()
        grouped = self.read(view='groups', group_by='account')
        self.assertEqual(grouped['total_matching'], 1)
        self.assertEqual(grouped['items'][0]['transaction_count'], 5)
        self.assertEqual(grouped['items'][0]['group'], str(self.account.id))
        self.assertEqual(self.read(account_ids=[alias.id])['total_matching'], 5)
        months = self.read(view='groups', group_by='month')['items']
        self.assertEqual({p['group'] for p in months}, {'2026-01', '2026-03', 'undated'})
        self.assertEqual(self.read(view='groups', group_by='counterparty')['total_matching'], 1)
        self.assertEqual(self.read(view='groups', group_by='category')['items'][0]['group'], 'Uncategorized')

    def test_case_isolation_and_source_disposition_do_not_leak_or_count(self):
        self.source(rows=2)
        foreign_document = self.make_document(case=self.other_case, run=self.other_run)
        foreign_period = self.make_period(foreign_document, account=self.other_account, run=self.other_run)
        self.add_row(foreign_period, foreign_document, account=self.other_account,
            run=self.other_run, amount=999999)
        own = self.read()
        self.assertEqual(own['total_matching'], 2)
        self.assertNotIn(str(foreign_document.id), str(own))
        self.assertEqual(self.read(account_ids=[self.other_account.id])['total_matching'], 0)
        document, _, _ = self.source(self.quiet, rows=1)
        document.status = 'superseded'
        self.db.commit()
        result = self.read()
        self.assertEqual(result['total_matching'], 2)
        self.assertEqual(result['coverage']['exclusions']['source_not_admitted'], 1)
        self.assertEqual(result['coverage']['registered_accounts'], 2)
        self.assertEqual(result['coverage']['registered_accounts_without_statement_periods'], 1)

    def test_overflow_and_invalid_filters_never_return_partial_totals(self):
        self.source(rows=2)
        with patch('services.financial.ledger_summary.MAX_SUMMARY_ROWS', 1):
            result = self.read()
        self.assertFalse(result['available'])
        self.assertIsNone(result['total_matching'])
        self.assertIsNone(result['coverage'])
        self.assertEqual(result['totals'], [])
        with patch('services.agent.financial_ledger_tools.MAX_CONTEXT_ROWS', 1):
            self.assertFalse(self.read()['available'])
        with self.assertRaises(FinancialLedgerToolError):
            self.read(filters={'arbitrary_key': 'not silently ignored'})
        with self.assertRaises(FinancialLedgerToolError):
            self.read(limit=101)

    def test_coverage_pages_periods_and_unknown_dates_without_assuming_zero_activity(self):
        for _ in range(3):
            self.source(self.quiet)
        first = self.read(view='coverage', account_ids=[self.quiet.id], limit=1)
        self.assertEqual(first['total_matching'], 3)
        self.assertEqual(first['returned'], 1)
        self.assertNotIn('periods', first['items'][0])
        self.assertEqual(first['items'][0]['coverage_unit'], 'registered_statement_period')
        self.assertEqual(first['coverage']['registered_accounts'], 1)
        second = self.read(view='coverage', account_ids=[self.quiet.id], limit=1, offset=1, expected_revision=first['revision'])
        self.assertNotEqual(first['items'][0]['period']['id'], second['items'][0]['period']['id'])
        self.assertEqual(self.read(view='coverage', account_ids=[self.quiet.id], filters={'currency': 'USD'})['total_matching'], 0)

    def test_registered_accounts_without_periods_are_explicit_and_never_quiet_money(self):
        result=self.read(view='coverage',filters={'currency':'EUR'})
        self.assertEqual({r['account_id'] for r in result['items']},{str(self.account.id),str(self.quiet.id)})
        self.assertEqual(result['totals'],[])
        self.assertEqual(result['coverage']['registered_accounts'],2)
        self.assertEqual(result['coverage']['registered_accounts_without_statement_periods'],2)
        self.assertEqual(result['coverage']['registered_accounts_with_statement_periods'],0)
        self.assertEqual(result['coverage']['registered_statement_periods'],0)
        self.assertEqual(result['coverage']['registered_sources'],0)
        for entry in result['items']:
            self.assertEqual(entry['coverage_unit'],'registered_account_without_period')
            self.assertIsNone(entry['period'])
            self.assertEqual(entry['periods'],[])
            self.assertEqual(entry['recorded_account_currency'],'EUR')
            self.assertNotIn('no_activity_confirmed',entry)
        self.assertEqual(self.read(view='coverage',start_date='2026-01-01')['total_matching'],0)
        self.assertEqual(self.read(view='coverage',end_date='2026-12-31')['total_matching'],0)
        self.quiet.currency=None
        self.db.commit()
        self.assertEqual(self.read(view='coverage',filters={'currency':'EUR'})['total_matching'],1)
        unknown=next(r for r in self.read(view='coverage')['items'] if r['account_id']==str(self.quiet.id))
        self.assertIsNone(unknown['recorded_account_currency'])

    def test_period_filters_and_excluded_periods_never_become_empty_directory_entries(self):
        document,period,_=self.source()
        period.period_start=date(2026,1,1);period.period_end=date(2026,1,31)
        self.db.commit()
        scoped=dict(view='coverage',account_ids=[self.account.id])
        self.assertEqual(self.read(**scoped,start_date='2026-02-01')['total_matching'],0)
        self.assertEqual(self.read(**scoped,filters={'currency':'USD'})['total_matching'],0)
        self.assertEqual(self.read(view='coverage',filters={'source_document_id':str(document.id)})['total_matching'],1)
        self.assertEqual(self.read(view='coverage',account_ids=[self.quiet.id],
            filters={'source_document_id':str(document.id)})['total_matching'],0)
        document.status='superseded';self.db.commit()
        self.assertEqual(self.read(**scoped)['total_matching'],0)

    def test_alias_with_period_does_not_make_canonical_directory_look_uncovered(self):
        alias=self._account(self.case.id,identity_key='no-period-canonical-alias')
        alias.currency='EUR';alias.metadata_={'canonical_account_id':str(self.account.id)}
        self.db.add(alias);self.db.commit()
        self.source(alias)
        result=self.read(view='coverage',account_ids=[self.account.id])
        self.assertEqual(result['total_matching'],1)
        self.assertEqual(result['items'][0]['coverage_unit'],'registered_statement_period')
        self.assertEqual(result['coverage']['registered_accounts'],1)
        self.assertEqual(result['coverage']['registered_accounts_without_statement_periods'],0)

    def test_foreign_period_reference_fails_closed_and_foreign_evidence_name_is_hidden(self):
        document, _, rows = self.source(rows=1)
        foreign = self.make_document(case=self.other_case, run=self.other_run)
        period = self.make_period(foreign, account=self.other_account, run=self.other_run)
        rows[0].statement_period_id = period.id
        self.db.commit()
        with self.assertRaisesRegex(FinancialLedgerToolError, 'statement-period'):
            self.read()
        rows[0].statement_period_id = None
        document.evidence_file_id = foreign.evidence_file_id
        self.db.commit()
        result = self.read()
        self.assertIsNone(result['items'][0]['source']['filename'])
        self.assertIsNone(result['items'][0]['source']['evidence_file_id'])
        self.assertFalse(result['items'][0]['source']['source_available'])

    def test_excluded_holder_scope_does_not_require_an_active_source_period(self):
        document, _, _ = self.source(rows=1)
        document.status = 'superseded'
        self.db.commit()
        result = self.read(view='excluded', filters={'account_holder': 'Synthetic company'})
        self.assertEqual(result['total_matching'], 1)
        self.assertEqual(result['items'][0]['exclusion_reason'], 'source_not_admitted')

    def test_pending_corrected_fields_use_saved_missing_fields_without_claiming_admission(self):
        document, _, _ = self.source()
        document.metadata_ = {**document.metadata_, 'statement_incomplete_records': [
            {'id': 'pending', 'fields': {'amount_minor': '', 'description': 'Original'},
             'correction': {'amount_minor': '12345', 'description': 'Saved correction', 'date': ''},
             'missing_fields': [], 'version': 1, 'original': {'page_number': 1}}]}
        self.db.commit()
        result = self.read(view='incomplete')
        record = result['items'][0]
        self.assertEqual(record['fields']['amount_minor'], '12345')
        self.assertEqual(record['missing_fields'], [])
        self.assertEqual(record['record_status'], 'saved_fields_pending_admission')
        self.assertFalse(record['included_in_totals'])
        self.assertEqual(result['totals'], [])

    def test_query_count_is_constant_as_the_payment_population_grows(self):
        document, period, _ = self.source(rows=1)
        case_id = self.case.id
        def capture():
            queries = []
            def record(_connection, _cursor, statement, *_):
                queries.append(statement)
            event.listen(self.engine, 'before_cursor_execute', record)
            try:
                with self.SessionLocal() as fresh:
                    result = read_financial_ledger(fresh, case_id=case_id)
            finally:
                event.remove(self.engine, 'before_cursor_execute', record)
            return result, queries
        first, small_queries = capture()
        for _ in range(200):
            self.add_row(period, document, amount=100)
        last, large_queries = capture()
        self.assertEqual((first['total_matching'], last['total_matching']), (1, 201))
        self.assertEqual(len(small_queries), len(large_queries))
        self.assertLessEqual(len(large_queries), 9)
        self.assertTrue(all(sql.lstrip().upper().startswith('SELECT') for sql in large_queries))

    def test_coverage_bounds_and_empty_foreign_selection_fail_closed(self):
        self.source()
        self.source(self.quiet)
        with patch('services.financial.candidate_store.MAX_ACCOUNT_DIRECTORY_PERIODS', 1):
            result = self.read(view='coverage')
        self.assertFalse(result['available'])
        self.assertEqual(result['totals'], [])
        self.assertIsNone(result['coverage'])
        result = self.read(view='coverage', account_ids=[self.other_account.id])
        self.assertEqual(result['total_matching'], 0)
        self.assertEqual(result['coverage']['registered_accounts'], 0)
        self.assertEqual(result['coverage']['incomplete_records'], 0)


class CorrectedFinancialAgentLedgerTests(unittest.TestCase):
    def test_actual_saved_amount_correction_is_current_and_original_stays_excluded(self):
        from tests.test_financial_payment_edits import PaymentEditTests
        fixture = PaymentEditTests()
        fixture.setUp()
        try:
            from postgres.models.financial import FinancialTransaction
            original = fixture.f.db.get(FinancialTransaction, fixture.ids[0])
            original_id = str(original.id)
            source_reading = deepcopy(original.provenance)
            before = read_financial_ledger(fixture.f.db, case_id=fixture.f.case.id)
            receipt = fixture.save(fixture.request(ids=fixture.ids[:1], amount='123.45',
                description='Reviewed synthetic payment', category='Reviewed travel'))
            fixture.f.db.expire_all()
            result = read_financial_ledger(fixture.f.db, case_id=fixture.f.case.id,
                filters={'category': 'Reviewed travel'})
            self.assertEqual(result['total_matching'], 1)
            self.assertEqual(result['items'][0]['amount_minor'], '12345')
            self.assertEqual(result['items'][0]['description'], 'Reviewed synthetic payment')
            self.assertEqual(result['items'][0]['transaction_id'], receipt['replacements'][0]['id'])
            self.assertEqual(fixture.f.db.get(FinancialTransaction, UUID(original_id)).provenance, source_reading)
            excluded = read_financial_ledger(fixture.f.db, case_id=fixture.f.case.id, view='excluded')
            self.assertIn(original_id, {item['transaction_id'] for item in excluded['items']})
            self.assertFalse(read_financial_ledger(fixture.f.db, case_id=fixture.f.case.id,
                offset=1, expected_revision=before['revision'])['available'])
        finally:
            fixture.tearDown()
