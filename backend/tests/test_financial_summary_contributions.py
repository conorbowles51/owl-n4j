from unittest.mock import patch
from postgres.models.enums import TransactionDirection, LedgerStatus
from tests.test_financial_ledger_summary import LedgerSummaryTests
from services.financial.summary_contributions import summary_contributions


class SummaryContributionTests(LedgerSummaryTests):
    def contributions(self, **scope):
        return summary_contributions(self.db, case_id=self.case.id, **scope)

    def test_sources_follow_exact_population_and_preserve_large_values(self):
        first, source = self.add(9007199254740993)
        second, _ = self.add(0, TransactionDirection.debit)
        second.proof_class = 'p3'
        self.add(500, status=LedgerStatus.quarantined)
        self.db.commit()
        verified = self.contributions()
        working = self.contributions(population='working')
        self.assertEqual([r['transaction_id'] for r in verified['contributions']], [str(first.id)])
        self.assertEqual(verified['contributions'][0]['amount_minor'], '9007199254740993')
        self.assertEqual(verified['contributions'][0]['source_document_id'], str(source.id))
        self.assertEqual({r['transaction_id'] for r in working['contributions']}, {str(first.id),str(second.id)})
        self.assertEqual(len(working['contributions']), working['included_rows'])
        self.assertEqual(working['currencies'][0]['credits_minor'], '9007199254740993')
        self.assertEqual(second.proof_class, 'p3')
        self.assertNotIn('readings', working)
        self.assertFalse(self.db.new or self.db.dirty)

    def test_scope_and_limits_never_leak_partial_contributions(self):
        self.add()
        self.assertEqual(self.contributions(account_id=self.other_account.id)['contributions'], [])
        for population in ('working', 'verified'):
            with patch('services.financial.ledger_summary.MAX_SUMMARY_ROWS', 0):
                answer = self.contributions(population=population)
            self.assertFalse(answer['available'])
            self.assertEqual(answer['contributions'], [])
            self.assertEqual(answer['currencies'], [])

import unittest
from uuid import uuid4


class SummaryContributionRoutes(unittest.IsolatedAsyncioTestCase):
    async def test_optional_source_capture_uses_each_requested_population(self):
        from routers.financial_ledger import get_ledger_summary, get_working_ledger_summary
        case, account = uuid4(), uuid4()
        for route, population in ((get_ledger_summary, 'verified'), (get_working_ledger_summary, 'working')):
            with patch('services.financial.summary_contributions.summary_contributions', return_value={'contributions': []}) as call:
                result = await route(case, account, None, None, 'db', True)
            self.assertEqual(result, {'contributions': []})
            call.assert_called_once_with('db', case_id=case, account_id=account, start_date=None, end_date=None, population=population)
