"""lx-searchfix A: the agent's ledger search finds rows by meaning and loose words through the case search.

Measured on origin eae8b3cc (17 Nov, relevance gate, both invented cases): ``get_financial_transactions`` with its
search needing every word as typed found 7 of 23 relevant rows and returned nothing for 9 of 13 questions, e.g.
"cash deposits at a branch" against "CASH DEPOSIT BR 014 FENWICK" and "checks from Penn's Used Tools" against
"MOBILE DEP CHK 1043 PENN'S USED TOOLS". Every test here fails on that code (no loose words, no ranked ledger search).
"""
from __future__ import annotations

import contextlib
import re
import sqlite3

import pytest

from services.case_search import loose
from services.embed_all import search as ES
from services.financial.transaction_search import transaction_search
from services.phone import chat_retrieval
from services.phone import fold as F

CASH = "cash deposits at a branch"
PENN = "checks from Penn's Used Tools"
CASH_ROW = "CASH DEPOSIT BR 014 FENWICK"
PENN_ROW = "MOBILE DEP CHK 1043 PENN'S USED TOOLS"


def _row(description):
    return dict(key="k", from_name="", to_name="", description=description, category="", currency="USD",
                amount_minor="40000", bank_reference="", ordering_date="2024-04-12", account_label="")


def test_the_two_statement_rows_hold_every_question_word_loosely_and_not_as_typed():
    for question, row in ((CASH, CASH_ROW), (PENN, PENN_ROW)):
        assert not transaction_search(question, "terms")(_row(row))  # the old default: every word as typed
        groups = loose.groups(chat_retrieval.terms(question))
        assert groups and all(loose.holds(F.fold(row), g) for g in groups), (question, loose.described(groups))


def test_an_abbreviation_matches_a_whole_word_only_and_generic_money_words_are_dropped():
    br = loose.forms("branch")
    assert "br" in br["whole"]
    assert not loose.holds(F.fold("BROWN STREET GARAGE"), br)
    assert loose.holds(F.fold("CASH DEP BR 14"), br)
    assert [g["term"] for g in loose.groups(chat_retrieval.terms("payments to Lena Marsh"))] == ["marsh", "lena"]
    assert [g["term"] for g in loose.groups(["payments"])] == ["payments"]  # the only word stays
    assert loose.stem("deposits") == "deposit" and loose.stem("towing") == "tow" and loose.stem("glass") == "glass"


class _SqliteConn:
    """Runs the embedded-records word query on SQLite: ``= ANY(:areas)`` as a list, ``::int`` dropped."""

    def __init__(self, rows):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE TABLE embed_items (case_id, area, item_key, title, cite, body, body_folded, person, "
                        "item_date)")
        for area, key, body in rows:
            self.db.execute("INSERT INTO embed_items VALUES ('c', ?, ?, '', ?, ?, ?, '', NULL)",
                            (area, key, "txn://%s" % key, body, F.fold(body)))

    def execute(self, clause, params):
        sql = str(clause).replace("::int", "")
        args = dict(params)
        areas = args.pop("areas")
        sql = sql.replace("area = ANY(:areas)", "area IN (%s)" % ",".join("'%s'" % a for a in areas))
        sql = re.sub(r":(\w+)", r":\1", sql)
        cur = self.db.execute(sql, args)
        names = [d[0] for d in cur.description]

        class Row:
            def __init__(self, values):
                self.__dict__.update(dict(zip(names, values)))
        rows = [Row(v) for v in cur.fetchall()]

        class Result(list):
            def fetchall(self):
                return list(self)
        return Result(rows)


def test_the_word_search_of_the_embedded_records_counts_loose_forms():
    conn = _SqliteConn([("ledger", "fenwick", "Payment: CASH DEPOSIT BR 014 FENWICK."),
                        ("ledger", "penn", "Payment: MOBILE DEP CHK 1043 PENN'S USED TOOLS."),
                        ("ledger", "brown", "Payment: BROWN STREET GARAGE cash.")])
    for question, key, words in ((CASH, "fenwick", 3), (PENN, "penn", 4)):
        groups = loose.groups(chat_retrieval.terms(question))
        hits = ES.word_hits(conn, "c", groups, ["ledger"])
        assert hits[0]["key"] == key and hits[0]["words"] == words, hits
        assert ES.word_hits(conn, "c", chat_retrieval.terms(question), ["ledger"])[0]["words"] < words  # as typed
    brown = [h for h in ES.word_hits(conn, "c", loose.groups(chat_retrieval.terms(CASH)), ["ledger"])
             if h["key"] == "brown"]
    assert brown and brown[0]["words"] == 1  # "cash", not "br" inside "brown"


def test_ranked_rows_keep_the_search_order_inside_the_other_filters():
    from services.financial.ledger_table_view import capture_table_view

    def reading(key, direction, day):
        return {"row": dict(_row("X"), key=key, direction=direction, ordering_date=day, row_index=0,
                            ledger_status="admitted", account_id="a", proof_class="p1")}
    ledger = {"readings": [reading("r1", "credit", "2024-01-01"), reading("r2", "debit", "2024-01-02"),
                           reading("r3", "credit", "2024-01-03"), reading("r4", "credit", "2024-01-04")]}
    out = capture_table_view(ledger, {"payment_ids": ["r3", "r2", "r1"], "sort": "given", "direction": "credit"})
    assert out["row_ids"] == ["r3", "r1"]
    assert "payment_ids" not in capture_table_view(ledger, {})["filters"]  # screens' filters are unchanged


@pytest.fixture
def ledger_tool(monkeypatch):
    from services.agent import financial_ledger_tools as FLT
    from services.agent import tools as T
    from services.case_search import service as CS
    from services.phone import money_presence
    calls = {"ranked": [], "reads": []}

    def ranked(conn, case_id, question, **kw):
        calls["ranked"].append((question, kw))
        return {"candidates": [{"area": "ledger", "cite": "txn://r3"}, {"area": "statement_pages", "cite": "doc://x/1"},
                               {"area": "ledger", "cite": "txn://r1"}],
                "notes": [], "ranking": {"reranked": False}, "meaning_search": True, "searched": ["ledger"]}

    def read(session, *, case_id, view, filters=None, ledger_cache=None, **kw):
        calls["reads"].append(dict(filters or {}))
        f = filters or {}
        ids = f.get("payment_ids") or []
        items = [{"transaction_id": i, "description": i} for i in ids] if ids else []
        return {"available": True, "total_matching": len(items) if ids else 0, "returned": len(items), "offset": 0,
                "next_offset": None, "has_more": False, "items": items, "totals": {"USD": "1.00"},
                "filters": dict(f), "revision": "rev", "coverage": {}}
    monkeypatch.setattr(CS, "ranked", ranked)
    monkeypatch.setattr(FLT, "kept_read_financial_ledger", read)
    monkeypatch.setattr(money_presence, "presence", lambda conn, case: {"has_financial_evidence": True})
    monkeypatch.setattr(T, "_statements_outside_ledger", lambda db, case: None)

    @contextlib.contextmanager
    def session():
        class S:
            def connection(self):
                return None
        yield S()
    ctx = T.AgentToolContext(case_id="00000000-0000-0000-0000-0000000000aa", ledger_session_factory=session)
    tool = {t.name: t for t in T.make_agent_tools(ctx)}["get_financial_transactions"]
    return tool, calls


def test_the_agent_ledger_search_goes_through_the_case_search_and_lists_rows_best_first(ledger_tool):
    tool, calls = ledger_tool
    out = tool.invoke({"search": CASH})
    assert calls["ranked"] and calls["ranked"][0][0] == CASH
    assert calls["ranked"][0][1]["kinds"] == ("ledger",)
    data = out["data"]
    assert [i["transaction_id"] for i in data["items"]] == ["r3", "r1"]
    assert data["totals"] is None and "not a filter" in data["totals_note"]
    assert data["exact_words"]["total_matching"] == 0
    assert any(r.get("payment_ids") == ["r3", "r1"] and r.get("sort") == "given" for r in calls["reads"])
    assert "payment_ids" not in data["filters"]
    assert "next page" in " ".join(data["notes"])


def test_exact_searches_the_words_as_written_without_the_case_search(ledger_tool):
    tool, calls = ledger_tool
    tool.invoke({"search": CASH, "exact": True})
    tool.invoke({"search": "rent AND bay", "search_mode": "boolean"})
    assert calls["ranked"] == []
    assert [r.get("search") for r in calls["reads"]] == [CASH, "rent AND bay"]
