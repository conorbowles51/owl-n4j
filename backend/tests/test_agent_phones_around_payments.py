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

    def test_a_statement_read_names_the_week_before_its_payments(self):
        # 23 Nov, live: the follow-up read only the statement's text (penn-used-tools-old-ferrow-2024.csv, 23 rows)
        # and was never told the phones held records before its checks.
        from services.agent.source_read_tools import _statement_around
        doc, _period, rows = self.source(rows=2)
        for row, d in zip(rows, (date(2024, 5, 10), date(2024, 6, 1))):
            row.transaction_date = row.posted_date = row.ordering_date = d
        self.db.commit()
        with patch.object(PA, "_counts", _counts):
            got = _statement_around(self.db, self.case.id, doc.evidence_file_id)
        self.assertIn("counted in around_on_phones.windows", got["sentence"])
        self.assertEqual([w["day"] for w in got["windows"]], ["2024-05-10", "2024-06-01"])
        self.assertEqual(got["windows"][0]["read_with"],
                         "phone_messages(start='2024-05-03', end='2024-05-10', include_groups=true)")
        # A file that is not a ledger statement names no payments.
        import uuid
        self.assertIsNone(_statement_around(self.db, self.case.id, uuid.uuid4()))

    def test_a_failed_count_is_said_and_the_ledger_read_still_answers(self):
        self.rows([date(2024, 5, 10)])
        with patch.object(PA, "_counts", side_effect=RuntimeError("synthetic")):
            out = self.tool().func(limit=50)
        self.assertEqual(out["status"], "success")
        self.assertEqual(out["data"]["returned"], 1)
        self.assertFalse(out["data"]["around_on_phones"]["available"])
        self.assertIn("could not be counted", out["summary"])


SAID = ("Read 23 of 23 matching transactions. The phones hold 598 messages, 64 calls and 10 emails from 7 days before "
        "the first of these 23 payments to the last (counted in around_on_phones.windows, not read).")


def _t(name, summary="", status="success"):
    return {"name": name, "summary": summary, "status": status, "arguments": {}}


def test_a_run_that_read_payments_with_phone_records_around_goes_back_once_before_it_answers():
    from services.agent import answer_check
    state = {}
    msg = answer_check.around_message([_t("get_financial_coverage"), _t("get_financial_transactions", SAID)], state)
    assert msg and "The phones hold 598 messages" in msg and "read_with" in msg
    assert "say in the answer that the phones around these payments were not read" in msg
    assert answer_check.around_message([_t("get_financial_transactions", SAID)], state) is None  # once per run


def test_no_return_when_the_phones_were_read_after_or_the_read_named_none():
    from services.agent import answer_check
    for later in ("phone_messages", "search_case", "read_scope_with_model"):
        assert answer_check.around_message([_t("get_financial_transactions", SAID), _t(later)], {}) is None
    assert answer_check.around_message([_t("get_financial_transactions", "Read 5 of 5.")], {}) is None
    assert answer_check.around_message([_t("get_financial_transactions", SAID, status="error")], {}) is None


STATEMENT_SAID = ("Read 1 of 1 stored pages/parts of penn-used-tools-old-ferrow-2024.csv. The phones hold 598 messages, "
                  "64 calls and 10 emails from 7 days before the first of these 23 payments to the last (counted in "
                  "around_on_phones.windows, not read).")


def test_a_statement_text_read_alone_goes_back_to_the_phones_once():
    # Live 23 Nov, run 1 of check-b17: the follow-up's only call was get_document_text on the statement.
    from services.agent import answer_check
    msg = answer_check.around_message([_t("get_document_text", STATEMENT_SAID)], {})
    assert msg and "The phones hold 598 messages" in msg
    assert answer_check.around_message([_t("get_document_text", "Read 3 of 3 stored pages/parts of x.pdf. ")], {}) is None


def test_a_contact_and_money_summary_is_not_a_read_of_the_windows():
    # Live 23 Nov, run 5 of check-b17: ledger reads, then get_contact_and_money_between, and the price list was missed.
    from services.agent import answer_check
    trace = [_t("get_financial_transactions", SAID), _t("get_document_text", "Read 3 of 3."),
             _t("get_contact_and_money_between"), _t("read_tool_result_page")]
    assert answer_check.around_message(trace, {})
