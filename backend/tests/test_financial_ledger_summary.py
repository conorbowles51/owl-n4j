from datetime import date
from unittest.mock import patch
from postgres.models.enums import LedgerStatus, TransactionDirection
from services.financial.ledger_summary import ledger_summary, LedgerSummaryError
from tests import test_financial_duplicates as fixture

class LedgerSummaryTests(fixture.DuplicateTestCase):
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
