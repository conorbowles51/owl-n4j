"""A ledger read that returns payments says what the phones hold in the week before each (followups 22 Nov 2026).

Live, 22 Nov: 'What comes before each of those checks?' was answered from the ledger rows alone, although the phones
held the price list emailed six days before one check. The payments result now counts the phone records in the
7 days before each payment and names the phone read that lists them. These tests fail on code without it.
"""
from contextlib import contextmanager
from datetime import date
from unittest.mock import patch

from services.agent import phones_around_payments as PA
from tests.test_agent_financial_ledger_tools import LedgerToolFixture

COUNTS = {date(2024, 5, 3): {"records": 68, "messages": 61, "calls": 3, "emails": 4}}


def _counts(_conn, _case, first, _last):
    return dict(COUNTS.get(first) or {"records": 0, "messages": 0, "calls": 0, "emails": 0})


class PhonesAroundPaymentsTests(LedgerToolFixture):
    def setUp(self):
        super().setUp()
        self.phones = True  # the harness is SQLite, which never holds phone records: the check is stubbed
        held = patch.object(PA, "_has_phone_records", lambda *_: self.phones)
        held.start()
        self.addCleanup(held.stop)

    def tool(self):
        from services.agent.tools import AgentToolContext, make_agent_tools

        @contextmanager
        def session():
            with self.SessionLocal() as s:
                yield s
        ctx = AgentToolContext(case_id=str(self.case.id), ledger_session_factory=session)
        return {t.name: t for t in make_agent_tools(ctx)}["get_financial_transactions"]

    def rows(self, days):
        _doc, _period, rows = self.source(rows=len(days))
        for row, d in zip(rows, days):
            row.transaction_date = row.posted_date = row.ordering_date = d
        self.db.commit()
        return rows

    def call(self, **kw):
        with patch.object(PA, "_counts", _counts):
            return self.tool().func(**kw)

    def test_each_returned_payment_gets_its_week_before_with_the_read_that_lists_it(self):
        rows = self.rows([date(2024, 5, 10), date(2024, 3, 22)])
        out = self.call(limit=50)
        block = out["data"]["around_on_phones"]
        by_day = {w["day"]: w for w in block["windows"]}
        self.assertEqual(set(by_day), {"2024-05-10", "2024-03-22"})
        w = by_day["2024-05-10"]
        self.assertEqual((w["start"], w["end"], w["emails"]), ("2024-05-03", "2024-05-10", 4))
        self.assertIn("phone_messages(start='2024-05-03', end='2024-05-10'", w["read_with"])
        self.assertIn(w["payment"], {"txn://%s" % r.id for r in rows})
        self.assertIsNone(by_day["2024-03-22"]["read_with"])  # nothing on the phones that week: nothing to read
        self.assertIn("in the 7 days before 1 of these 2 payments", out["summary"])
        self.assertIn("not linked to the payments", block["note"])

    def test_many_payments_share_one_span(self):
        self.rows([date(2024, 5, d) for d in range(1, 13)])
        with patch.object(PA, "_counts", lambda *_a: {"records": 10, "messages": 9, "calls": 0, "emails": 1}):
            out = self.tool().func(limit=50)
        (w,) = out["data"]["around_on_phones"]["windows"]
        self.assertEqual((w["start"], w["end"]), ("2024-04-24", "2024-05-12"))
        self.assertIn("9 messages, 0 calls and 1 emails", out["summary"])

    def test_a_case_without_phone_records_adds_nothing(self):
        self.phones = False
        self.rows([date(2024, 5, 10)])
        out = self.call(limit=50)
        self.assertNotIn("around_on_phones", out["data"])
        self.assertNotIn("phones hold", out["summary"])

    def test_sqlite_has_no_phone_records_and_the_read_stays_select_only(self):
        patch.stopall()  # the real check, not the stub
        with self.SessionLocal() as s:
            self.assertFalse(PA._has_phone_records(s.connection(), self.case.id))

    def test_a_failed_count_is_said_and_the_ledger_read_still_answers(self):
        self.rows([date(2024, 5, 10)])
        with patch.object(PA, "_counts", side_effect=RuntimeError("synthetic")):
            out = self.tool().func(limit=50)
        self.assertEqual(out["status"], "success")
        self.assertEqual(out["data"]["returned"], 1)
        self.assertFalse(out["data"]["around_on_phones"]["available"])
        self.assertIn("could not be counted", out["summary"])
