import unittest
from datetime import date
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy import select
from services.financial.coverage_query import list_statement_coverage, _coverage, CoverageQueryError
from services.financial.periods import PeriodBounds
from postgres.models.financial import FinancialStatementPeriod
from tests import test_financial_duplicates as fixture


def period(key,start,end):return dict(period_id=key,start=start,end=end)

class CoverageArithmeticTests(unittest.TestCase):
    def test_union_including_enclosing_export_does_not_invent_a_gap(self):
        result=_coverage("GBP",[period("j","2026-01-01","2026-01-31"),period("m","2026-03-01","2026-03-31"),period("export","2026-01-01","2026-03-31")])
        self.assertEqual(result["uncovered_days"],0)
        self.assertEqual(result["covered_days"],90)
        self.assertEqual(len(result["windows"]),1)
        self.assertEqual(set(result["windows"][0]["period_ids"]),{"j","m","export"})
        self.assertEqual(len(result["overlaps"]),2)
    def test_gap_dates_and_leap_day_are_exact(self):
        result=_coverage("GBP",[period("a","2024-02-01","2024-02-28"),period("b","2024-03-01","2024-03-31")])
        self.assertEqual(result["gaps"],[dict(start="2024-02-29",end="2024-02-29",days=1)])
    def test_contiguous_and_duplicate_bounds_do_not_double_count(self):
        result=_coverage("GBP",[period("a","2026-01-01","2026-01-02"),period("b","2026-01-03","2026-01-04"),period("c","2026-01-01","2026-01-02")])
        self.assertEqual(result["covered_days"],4);self.assertEqual(result["gaps"],[])
    def test_maximum_calendar_date_does_not_overflow(self):
        result=_coverage("GBP",[period("a","9999-12-30","9999-12-31"),period("b","9999-12-31","9999-12-31")])
        self.assertEqual(result["covered_days"],2)

class CoverageQueryTests(fixture.DuplicateTestCase):
    def read(self,**updates):return list_statement_coverage(self.db,**{**dict(case_id=self.case.id),**updates})
    def test_scoped_read_retains_exclusions_and_no_writes(self):
        first=self.make_copy()
        other=self.make_copy(bounds=PeriodBounds.printed(date(2026,3,1),date(2026,3,31)))
        other.status="superseded";self.db.commit()
        result=self.read();item=result["items"][0]
        self.assertEqual(len(item["periods"]),2)
        self.assertEqual(item["currencies"][0]["period_count"],1)
        self.assertEqual({p["exclusion_reason"] for p in item["periods"]},{None,"source_not_admitted"})
        self.assertEqual({p["source_document_id"] for p in item["periods"]},{str(first.id),str(other.id)})
        self.assertFalse(result["applied"]);self.assertFalse(self.db.new or self.db.dirty)
        self.assertFalse(any(i["periods"] for i in self.read(case_id=self.other_case.id)["items"]))
    def test_derived_and_missing_bounds_are_not_coverage(self):
        document=self.make_copy()
        row=self.db.scalar(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id==document.id))
        row.period_start_source="derived";self.db.commit()
        self.assertEqual(self.read()["items"][0]["currencies"],[])
    def test_cross_case_document_link_is_not_silently_counted(self):
        document=self.make_copy()
        document.case_id=self.other_case.id;self.db.commit()
        item=self.read()["items"][0]
        self.assertFalse(item["available"])
        self.assertEqual(item["periods"],[])

    def test_large_account_is_unavailable_without_partial_coverage(self):
        from datetime import timedelta
        document=self.make_copy()
        original=self.db.scalar(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id==document.id))
        values={prop.key:getattr(original,prop.key) for prop in FinancialStatementPeriod.__mapper__.column_attrs
                if prop.key not in {"id","created_at","updated_at"}}
        for index in range(500):
            day=date(2027,1,1)+timedelta(days=index)
            self.db.add(FinancialStatementPeriod(**{**values,"id":uuid4(),"period_start":day,"period_end":day}))
        self.db.commit()
        item=self.read()["items"][0]
        self.assertFalse(item["available"])
        self.assertEqual(item["currencies"],[])
        self.assertIn("500",item["reason"])
        from services.financial.coverage_query import requested_statement_coverage
        requested=requested_statement_coverage(self.db,case_id=self.case.id,account_id=self.account.id,
            start_date=date(2026,1,1),end_date=date(2026,1,31))
        self.assertFalse(requested["available"])
        self.assertEqual(requested["currencies"],[])

    def test_account_page_is_explicit_and_bounded(self):
        self.assertEqual(self.read(offset=100)["items"],[])
        for changes in ({"limit":26},{"offset":-1},{"limit":True}):
            with self.assertRaises(CoverageQueryError):self.read(**changes)

class CoverageRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_scope_and_generic_failure(self):
        from routers import financial_ledger as router
        from fastapi import HTTPException
        case=uuid4()
        with patch.object(router,"list_statement_coverage",return_value={}) as call:
            await router.get_statement_coverage(case,25,"db")
            call.assert_called_once_with("db",case_id=case,offset=25)
        with patch.object(router,"list_statement_coverage",side_effect=RuntimeError("private")):
            with self.assertRaises(HTTPException) as caught:await router.get_statement_coverage(case,0,"db")
            self.assertNotIn("private",caught.exception.detail)

class RequestedCoverageTests(fixture.DuplicateTestCase):
    def requested(self, start=date(2026,2,1), end=date(2026,2,28), **changes):
        from services.financial.coverage_query import requested_statement_coverage
        return requested_statement_coverage(self.db, **{**dict(case_id=self.case.id,
            account_id=self.account.id, start_date=start, end_date=end), **changes})

    def test_gap_then_enclosing_export_and_precise_citations(self):
        self.make_copy(bounds=PeriodBounds.printed(date(2026,1,1),date(2026,1,31)))
        self.make_copy(bounds=PeriodBounds.printed(date(2026,3,1),date(2026,3,31)))
        result=self.requested();group=result["currencies"][0]
        self.assertEqual(group["covered_days"],0)
        self.assertEqual(group["gaps"],[dict(start="2026-02-01",end="2026-02-28",days=28)])
        export=self.make_copy(bounds=PeriodBounds.printed(date(2026,1,1),date(2026,3,31)))
        result=self.requested();group=result["currencies"][0]
        self.assertEqual(group["covered_days"],28)
        self.assertEqual(group["uncovered_days"],0)
        self.assertEqual(group["windows"][0]["period_ids"],
            [p["period_id"] for p in result["periods"] if p["source_document_id"]==str(export.id)])
        self.assertFalse(result["applied"])
        self.assertFalse(self.db.new or self.db.dirty)

    def test_both_requested_tails_count_and_currencies_remain_separate(self):
        self.make_copy(bounds=PeriodBounds.printed(date(2026,2,10),date(2026,2,20)))
        group=self.requested()["currencies"][0]
        self.assertEqual(group["covered_days"],11)
        self.assertEqual(group["uncovered_days"],17)
        self.assertEqual(group["gaps"],[dict(start="2026-02-01",end="2026-02-09",days=9),dict(start="2026-02-21",end="2026-02-28",days=8)])
        document=self.make_copy(bounds=PeriodBounds.printed(date(2026,2,1),date(2026,2,28)))
        row=self.db.scalar(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id==document.id))
        row.currency="USD";self.db.commit()
        groups={g["currency"]:g for g in self.requested()["currencies"]}
        self.assertEqual(len(groups),2)
        self.assertEqual(groups["USD"]["uncovered_days"],0)
        self.assertEqual(sum(g["uncovered_days"] for g in groups.values()),17)

    def test_inclusive_leap_day_and_maximum_date(self):
        for day in (date(2024,2,29),date.max):
            self.make_copy(bounds=PeriodBounds.printed(day,day))
            result=self.requested(day,day)
            self.assertEqual(result["requested_days"],1)
            self.assertEqual(result["currencies"][0]["covered_days"],1)
            self.assertEqual(result["currencies"][0]["gaps"],[])

    def test_no_eligible_bounds_is_unknown(self):
        self.assertFalse(self.requested()["available"])
        document=self.make_copy();document.status="superseded";self.db.commit()
        result=self.requested()
        self.assertFalse(result["available"])
        self.assertEqual(result["currencies"],[])
        self.assertEqual(result["periods"][0]["exclusion_reason"],"source_not_admitted")

    def test_foreign_account_and_source_never_supply_coverage(self):
        with self.assertRaises(CoverageQueryError) as caught:self.requested(case_id=self.other_case.id)
        self.assertEqual(caught.exception.status_code,404)
        with self.assertRaises(CoverageQueryError):self.requested(account_id=uuid4())
        document=self.make_copy();document.case_id=self.other_case.id;self.db.commit()
        result=self.requested()
        self.assertFalse(result["available"])
        self.assertEqual(result["periods"],[])
        self.assertEqual(result["currencies"],[])

    def test_invalid_dates_are_refused(self):
        with self.assertRaises(CoverageQueryError):self.requested(account_id=None)
        for start,end in ((date(2026,3,1),date(2026,2,1)),(None,date.today()),("2026-01-01",date.today())):
            with self.assertRaises(CoverageQueryError):self.requested(start,end)

class RequestedCoverageRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_route_scope_and_generic_failure(self):
        from routers import financial_ledger as router
        from fastapi import HTTPException
        case,account=uuid4(),uuid4();start,end=date(2026,2,1),date(2026,2,28)
        with patch.object(router,"requested_statement_coverage",return_value={}) as call:
            await router.get_requested_statement_coverage(case,account,start,end,"db")
            call.assert_called_once_with("db",case_id=case,account_id=account,start_date=start,end_date=end)
        for error,status in ((CoverageQueryError("Not found",404),404),(RuntimeError("private"),500)):
            with patch.object(router,"requested_statement_coverage",side_effect=error):
                with self.assertRaises(HTTPException) as caught:
                    await router.get_requested_statement_coverage(case,account,start,end,"db")
                self.assertEqual(caught.exception.status_code,status)
                self.assertNotIn("private",caught.exception.detail)
