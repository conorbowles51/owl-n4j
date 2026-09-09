from datetime import date
from unittest.mock import patch
from postgres.models.enums import LedgerStatus, TransactionDirection
from services.financial.ledger_summary import ledger_summary, LedgerSummaryError
from tests import test_financial_duplicates as fixture

class LedgerSummaryTests(fixture.DuplicateTestCase):
    def setUp(self):
        super().setUp()
        from postgres.base import Base
        from postgres.models.financial_candidates import FinancialCandidateMapping, FinancialExtractionCandidate, FinancialCandidateReview, FinancialCandidateFinalization, FinancialCandidateTransaction
        Base.metadata.create_all(self.engine,tables=[m.__table__ for m in (FinancialCandidateMapping,FinancialExtractionCandidate,FinancialCandidateReview,FinancialCandidateFinalization,FinancialCandidateTransaction)])

    def read(self, **changes):
        return ledger_summary(self.db, **{**dict(case_id=self.case.id), **changes})
    def add(self, amount=100, direction=TransactionDirection.credit, status=LedgerStatus.admitted):
        doc=self.make_document();period=self.make_period(doc)
        return self.add_row(period,doc,amount=amount,direction=direction,status=status),doc

    def test_exact_totals_beyond_javascript_precision_and_negative_net(self):
        self.add(9007199254740993)
        self.add(9007199254740995,TransactionDirection.debit)
        result=self.read();group=result['currencies'][0]
        self.assertEqual(group['credits_minor'],'9007199254740993')
        self.assertEqual(group['debits_minor'],'9007199254740995')
        self.assertEqual(group['net_minor'],'-2')
        self.assertEqual(result['included_rows'],2)
        self.assertEqual(result['excluded_rows'],0)
        self.assertEqual(result['included_classes'],['p0','p1','p2'])
        self.assertFalse(result['applied'])
        self.assertFalse(self.db.new or self.db.dirty)

    def test_exclusions_are_disjoint_and_original_is_not_double_counted(self):
        for status in (LedgerStatus.quarantined,LedgerStatus.superseded,LedgerStatus.rejected):self.add(status=status)
        row,doc=self.add();row.proof_class='p3';self.db.commit()
        row,doc=self.add();doc.proof_class='p3';self.db.commit()
        row,doc=self.add();doc.status='superseded';self.db.commit()
        replacement,doc=self.add(125)
        result=self.read()
        self.assertEqual(result['considered_rows'],7)
        self.assertEqual(result['included_rows'],1)
        self.assertEqual(result['exclusions'],dict(quarantined=1,superseded=1,rejected=1,source_not_admitted=1,proof_class_not_included=2))
        self.assertEqual(result['currencies'][0]['credits_minor'],'125')

    def test_currency_totals_are_not_combined(self):
        self.add(100)
        row,_=self.add(200);row.currency='USD';self.db.commit()
        groups=self.read()['currencies']
        self.assertEqual([(g['currency'],g['credits_minor']) for g in groups],[('GBP','100'),('USD','200')])

    def test_case_account_and_inclusive_ordering_dates(self):
        row,_=self.add();row.ordering_date=date(2026,2,1);self.db.commit()
        self.assertEqual(self.read(start_date=date(2026,2,1),end_date=date(2026,2,1))['included_rows'],1)
        self.assertEqual(self.read(end_date=date(2026,1,31))['included_rows'],0)
        self.assertEqual(self.read(account_id=self.other_account.id)['included_rows'],0)
        self.assertEqual(self.read(case_id=self.other_case.id)['included_rows'],0)

    def test_size_limit_never_returns_partial_money_or_counts(self):
        self.add();self.add()
        with patch('services.financial.ledger_summary.MAX_SUMMARY_ROWS',1):result=self.read()
        self.assertFalse(result['available'])
        self.assertIsNone(result['considered_rows'])
        self.assertIsNone(result['exclusions'])
        self.assertEqual(result['currencies'],[])

    def test_inconsistent_ownership_is_not_counted(self):
        row,doc=self.add();doc.case_id=self.other_case.id;self.db.commit()
        with self.assertRaises(LedgerSummaryError):self.read()

    def test_inconsistent_admitted_replacement_link_is_refused(self):
        original,_=self.add();replacement,_=self.add()
        original.superseded_by_id=replacement.id;self.db.commit()
        with self.assertRaises(LedgerSummaryError):self.read()

    def test_invalid_dates_are_refused(self):
        for changes in (dict(start_date='2026-01-01'),dict(start_date=date(2026,3,1),end_date=date(2026,1,1))):
            with self.assertRaises(LedgerSummaryError):self.read(**changes)


import unittest
from uuid import uuid4
class LedgerSummaryRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_scope_and_error_translation(self):
        from routers import financial_ledger as router
        from fastapi import HTTPException
        case,account=uuid4(),uuid4()
        with patch.object(router,'ledger_summary',return_value={}) as call:
            await router.get_ledger_summary(case,account,None,None,'db')
            call.assert_called_once_with('db',case_id=case,account_id=account,start_date=None,end_date=None)
        for error,status in ((LedgerSummaryError('Invalid range'),422),(RuntimeError('private'),500)):
            with patch.object(router,'ledger_summary',side_effect=error):
                with self.assertRaises(HTTPException) as caught:
                    await router.get_ledger_summary(case,None,None,None,'db')
                self.assertEqual(caught.exception.status_code,status)
                self.assertNotIn('private',caught.exception.detail)

class LedgerTrendTests(LedgerSummaryTests):
    def test_monthly_points_equal_summary_and_keep_sources(self):
        first,doc=self.add(9007199254740993)
        second,_=self.add(12,TransactionDirection.debit)
        second.ordering_date=date(2026,2,28);self.db.commit()
        self.add(999,status=LedgerStatus.rejected)
        result=self.read(grouping='monthly')
        self.assertEqual(result['date_basis'],'ordering_date')
        self.assertEqual([p['date'] for p in result['points']],['2026-01-01','2026-02-01'])
        self.assertEqual(result['points'][0]['transaction_ids'],[str(first.id)])
        self.assertEqual(result['points'][0]['source_document_ids'],[str(doc.id)])
        for group in result['currencies']:
            points=[p for p in result['points'] if p['currency']==group['currency']]
            for field in ('credits_minor','debits_minor','net_minor'):
                self.assertEqual(sum(int(p[field]) for p in points),int(group[field]))
            self.assertEqual(sum(p['rows'] for p in points),group['rows'])
        self.assertEqual(result['excluded_rows'],1)

    def test_daily_currency_groups_do_not_invent_empty_dates(self):
        first,_=self.add(100);first.ordering_date=date(2024,2,29)
        second,_=self.add(200);second.currency='USD';second.ordering_date=date(2024,2,29)
        third,_=self.add(300);third.ordering_date=date.max;self.db.commit()
        result=self.read(grouping='daily')
        self.assertEqual([(p['date'],p['currency']) for p in result['points']],
            [('2024-02-29','GBP'),('2024-02-29','USD'),('9999-12-31','GBP')])
        self.assertEqual(len(self.read(grouping='monthly')['points']),3)

    def test_filtered_and_oversized_trends_never_give_partial_points(self):
        self.add();self.add()
        self.assertEqual(self.read(grouping='daily',start_date=date(2026,2,1))['points'],[])
        with patch('services.financial.ledger_summary.MAX_SUMMARY_ROWS',1):result=self.read(grouping='daily')
        self.assertFalse(result['available'])
        self.assertEqual(result['points'],[])
        self.assertIsNone(result['included_rows'])
        with self.assertRaises(LedgerSummaryError):self.read(grouping='weekly')


class LedgerCounterpartyTests(LedgerSummaryTests):
    def counterparty_read(self, **scope):
        from services.financial.ledger_summary import ledger_counterparties
        return ledger_counterparties(self.db, case_id=self.case.id, **scope)

    def test_verbatim_labels_missing_values_currencies_and_exact_totals(self):
        for label, currency, amount in (
            (None, 'GBP', 3), ('', 'GBP', 5), ('Acme', 'GBP', 9007199254740993),
            ('Acme', 'GBP', 7), ('acme', 'GBP', 11), ('Acme ', 'GBP', 13), ('Acme', 'USD', 17),
        ):
            row, _ = self.add(amount)
            row.counterparty_raw, row.currency = label, currency
            self.db.commit()
        excluded, _ = self.add(999, status=LedgerStatus.rejected)
        excluded.counterparty_raw = 'Acme'; self.db.commit()
        result = self.counterparty_read()
        groups = {(g['label'], g['currency']): g for g in result['counterparties']}
        self.assertEqual(len(groups), 6)
        self.assertEqual(groups[('Acme', 'GBP')]['credits_minor'], '9007199254741000')
        self.assertEqual(result['excluded_rows'], 1)
        self.assertNotIn(str(excluded.id), [key for g in groups.values() for key in g['transaction_ids']])
        for currency in result['currencies']:
            matching = [g for g in groups.values() if g['currency'] == currency['currency']]
            for field in ('credits_minor', 'debits_minor', 'net_minor'):
                self.assertEqual(sum(int(g[field]) for g in matching), int(currency[field]))
        self.assertNotIn('readings', result)
        self.assertIn('without identity resolution', result['counterparty_limitation'])

    def test_scope_limits_and_current_decisions(self):
        first, _ = self.add(100)
        second, _ = self.add(25, TransactionDirection.debit)
        first.counterparty_raw = second.counterparty_raw = 'Source label'; self.db.commit()
        result = self.counterparty_read()
        group = result['counterparties'][0]
        self.assertEqual(group['net_minor'], '75')
        self.assertEqual(set(group['transaction_ids']), {str(first.id), str(second.id)})
        self.assertEqual(len(group['source_document_ids']), 2)
        from services.financial.quarantine_row import quarantine_case_row
        quarantine_case_row(self.db, case_id=self.case.id, transaction_id=first.id, actor=self.user, reason='Counterparty totals check')
        self.assertEqual(self.counterparty_read()['counterparties'][0]['net_minor'], '-25')
        self.assertEqual(self.counterparty_read(account_id=self.other_account.id)['counterparties'], [])
        self.assertEqual(self.counterparty_read(start_date=date(2027,1,1))['counterparties'], [])
        with patch('services.financial.ledger_summary.MAX_SUMMARY_ROWS', 1):
            result = self.counterparty_read()
        self.assertFalse(result['available'])
        self.assertEqual(result['counterparties'], [])
        self.assertIsNone(result['included_rows'])

class LedgerCounterpartyRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_scope_and_failure_responses(self):
        from routers import financial_ledger as router
        from fastapi import HTTPException
        case, account = uuid4(), uuid4()
        with patch('services.financial.ledger_summary.ledger_counterparties', return_value={}) as call:
            await router.get_ledger_counterparties(case, account, None, None, 'db')
            call.assert_called_once_with('db', case_id=case, account_id=account, start_date=None, end_date=None)
        for error, status in ((LedgerSummaryError('Invalid range'),422), (RuntimeError('private'),500)):
            with patch('services.financial.ledger_summary.ledger_counterparties', side_effect=error):
                with self.assertRaises(HTTPException) as caught:
                    await router.get_ledger_counterparties(case,None,None,None,'db')
                self.assertEqual(caught.exception.status_code,status)
                self.assertNotIn('private',caught.exception.detail)
