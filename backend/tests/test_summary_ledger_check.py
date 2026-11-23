"""Entity summaries take money figures from the ledger, not from a misread page (demo trap F38)."""

import json
from datetime import date
from types import SimpleNamespace

import pytest

from services import summary_ledger_check as check
from services.summary_ledger_check import LedgerRow, check_text

KELL = "kell-2024-03.pdf"
CITE = f"[{KELL}, p.1](doc://{KELL}/1)"


def _rows():
    def row(day, amount, balance=None):
        return LedgerRow(KELL, date(2024, 3, day), amount, balance)
    return {
        (KELL, date(2024, 3, 16)): [row(16, 50000)],
        (KELL, date(2024, 3, 18)): [row(18, 980000, balance=1234500)],
        (KELL, date(2024, 3, 1)): [row(1, 65000), row(1, 135000), row(1, 184000)],
    }


# The live demo summary, 15 Nov 2026 (graph search for Travis Kell, case b75f3f2c).
LIVE_PASSAGE = (
    f"Other transactions include a $500.00 Pocketwire transfer to Lena Marsh on 16 March 2024 {CITE}, "
    f"a $800.00 cash deposit at Branch 014 Fenwick on 18 March 2024 {CITE}, and more."
)


def test_misread_cash_deposit_takes_the_ledger_amount_and_keeps_the_reading_visible():
    result = check_text(LIVE_PASSAGE, _rows())
    assert "$9,800.00 (the ledger amount; the AI reading was $800.00) cash deposit" in result.text
    assert "$500.00 Pocketwire" in result.text
    assert [(f.figure, f.ledger_figure, f.action) for f in result.findings] == [("$800.00", "$9,800.00", "replaced")]
    assert result.checked == 2


def test_rerun_on_checked_text_changes_nothing():
    once = check_text(LIVE_PASSAGE, _rows()).text
    assert check_text(once, _rows()).text == once
    assert check.strip_notes(once) == LIVE_PASSAGE


def test_agreeing_and_unjudgeable_figures_are_left_alone():
    text = (
        f"Kell paid $650.00 and $1,350.00 on 1 March 2024 {CITE}; [{KELL}, p.1](doc://{KELL}/1). "
        f"He said $650 was his cut on 18 March 2024 [proffer.docx](evidence://proffer.docx). "
        f"The closing balance was $12.00 on 18 March 2024 {CITE}. "
        f"Payroll of $1,840.00 arrived in March 2024 {CITE}. "
        f"A $77.00 debit on 20 March 2024 {CITE}."
    )
    result = check_text(text, _rows())
    assert result.text == text
    assert result.findings == []


def test_figure_with_no_ledger_source_on_a_busy_day_is_flagged():
    text = f"A $999.00 debit on 1 March 2024 {CITE}."
    result = check_text(text, _rows())
    assert result.text == f"A $999.00{check.FLAG_NOTE} debit on 1 March 2024 {CITE}."
    assert result.findings[0].action == "flagged"


def test_month_first_dates_and_file_names_with_parentheses():
    name = "Kell (2) statement.pdf"
    rows = {(name, date(2024, 3, 18)): [LedgerRow(name, date(2024, 3, 18), 980000)]}
    text = f"A $800.00 deposit on March 18, 2024 [{name}, p.1](doc://{name.replace(' ', '%20')}/1)."
    assert "$9,800.00 (the ledger amount" in check_text(text, rows).text


class FakeGraph:
    def __init__(self, nodes):
        self.nodes = nodes
        self.writes = []

    def run(self, query, **params):
        if "SET n.summary" in query:
            node = self.nodes[params["key"]]
            if node["summary"] != params["expected"]:
                return SimpleNamespace(single=lambda: None)
            node.update(summary=params["summary"], model_text=params["model_text"],
                        checked_text=params["summary"], findings=params["findings"])
            self.writes.append(params["key"])
            return SimpleNamespace(single=lambda: {"key": params["key"]})
        if "amount IS NOT NULL" in query:
            return []  # no dated amounts in these graphs
        return [dict(key=k, name=k, summary=n["summary"], model_text=n.get("model_text"),
                     checked_text=n.get("checked_text"), manual_fields=n.get("manual_fields", []))
                for k, n in self.nodes.items()]


@pytest.fixture
def ledger(monkeypatch):
    state = {"rows": _rows()}
    monkeypatch.setattr(check, "ledger_rows", lambda session, case_id: state["rows"])
    monkeypatch.setattr(check, "file_names", lambda session, case_id: {})
    import services.entity_vectors as vectors
    refreshed = []
    monkeypatch.setattr(vectors, "refresh_entities", lambda case_id, keys, **kw: refreshed.extend(keys))
    state["refreshed"] = refreshed
    return state


def test_check_case_writes_model_summaries_and_never_a_person_written_one(ledger):
    graph = FakeGraph({
        "kell": {"summary": LIVE_PASSAGE},
        "edited": {"summary": LIVE_PASSAGE, "manual_fields": ["summary"]},
        "other": {"summary": "No ledger file cited [x.pdf, p.1](doc://x.pdf/1)."},
    })
    report = check.check_case("case", apply=True, db_session=object(), graph_session=graph)
    assert graph.writes == ["kell"]
    assert graph.nodes["kell"]["model_text"] == LIVE_PASSAGE
    assert "$9,800.00 (the ledger amount" in graph.nodes["kell"]["summary"]
    assert json.loads(graph.nodes["kell"]["findings"])[0]["ledger_figure"] == "$9,800.00"
    assert graph.nodes["edited"]["summary"] == LIVE_PASSAGE
    assert (report["summaries"], report["disagreeing_summaries"], report["person_written_disagreeing"],
            report["written"]) == (2, 2, 1, 1)
    assert ledger["refreshed"] == ["kell"]

    # Second run: the checked text is the check's own output, so nothing is written again.
    again = check.check_case("case", apply=True, db_session=object(), graph_session=graph)
    assert again["written"] == 0 and graph.writes == ["kell"]


def test_dry_run_writes_nothing(ledger):
    graph = FakeGraph({"kell": {"summary": LIVE_PASSAGE}})
    report = check.check_case("case", apply=False, db_session=object(), graph_session=graph)
    assert report["disagreeing_summaries"] == 1 and report["replaced"] == 1
    assert graph.writes == [] and graph.nodes["kell"]["summary"] == LIVE_PASSAGE


def test_ledger_correction_back_to_the_model_figure_restores_the_model_text(ledger):
    graph = FakeGraph({"kell": {"summary": LIVE_PASSAGE}})
    check.check_case("case", apply=True, db_session=object(), graph_session=graph)
    ledger["rows"][(KELL, date(2024, 3, 18))] = [LedgerRow(KELL, date(2024, 3, 18), 80000)]
    check.check_case("case", apply=True, db_session=object(), graph_session=graph)
    assert graph.nodes["kell"]["summary"] == LIVE_PASSAGE


def test_a_new_model_summary_is_checked_from_its_own_text(ledger):
    graph = FakeGraph({"kell": {"summary": LIVE_PASSAGE}})
    check.check_case("case", apply=True, db_session=object(), graph_session=graph)
    newer = LIVE_PASSAGE.replace("and more", "and a newer sentence")
    graph.nodes["kell"]["summary"] = newer  # the engine wrote a new summary
    check.check_case("case", apply=True, db_session=object(), graph_session=graph)
    assert graph.nodes["kell"]["model_text"] == newer
    assert "a newer sentence" in graph.nodes["kell"]["summary"]
    assert "$9,800.00 (the ledger amount" in graph.nodes["kell"]["summary"]


def test_a_finished_file_and_a_ledger_redraw_schedule_the_check(monkeypatch):
    calls = []
    monkeypatch.setattr(check, "schedule_case_check", lambda case_id: calls.append(str(case_id)))
    from services import evidence_job_sync
    record = SimpleNamespace(id="f", case_id="case-1", engine_job_id="j", status="processing", last_error=None,
                             processing_stale=False, processed_at=None, summary=None, transcription=None,
                             transcription_segments=None, entity_count=None, relationship_count=None,
                             metadata_={})
    evidence_job_sync._sync_db_record_from_job(record, {"status": "completed", "id": "j"})
    assert calls == ["case-1"]

    from services.financial import graph_followup
    graph_followup._notify_summary_check("case-2")
    assert calls == ["case-1", "case-2"]


def test_switch_off_stops_automatic_runs(monkeypatch):
    started = []
    monkeypatch.setenv("SUMMARY_LEDGER_CHECK", "0")
    monkeypatch.setattr(check.threading, "Thread", lambda *a, **k: started.append(1))
    check.schedule_case_check("case")
    assert started == []


# --- 23 Nov: the same misread deposit in forms the first check missed (demo case b75f3f2c, payment 459c951a) ------

FILE_ID = "e941f20d-3001-40f4-a7db-deb6c6ad4d51"
NAMES = {FILE_ID: KELL}

# The live Transaction node summary, 23 Nov: it cites the statement by its evidence file id and writes "800.00 USD".
LIVE_NODE_SUMMARY = (
    "## Transaction Details\nA cash deposit of 800.00 USD was made on 2024-03-18 at branch 014 Fenwick "
    f"[kell-2024-03.pdf, p.1](doc://{FILE_ID}/1)."
)


def test_summary_citing_a_file_id_with_a_code_after_the_figure_takes_the_ledger_amount():
    result = check_text(LIVE_NODE_SUMMARY, _rows(), NAMES)
    assert "9,800.00 USD (the ledger amount; the AI reading was 800.00 USD) was made" in result.text
    assert check.strip_notes(result.text) == LIVE_NODE_SUMMARY
    assert check_text(result.text, _rows(), NAMES).text == result.text
    # Without the id map the citation names no ledger file, so nothing is judged.
    assert check_text(LIVE_NODE_SUMMARY, _rows()).findings == []


class FigureGraph:
    """Nodes and connections with an amount, as the graph holds them."""

    def __init__(self, records):
        self.records = records
        self.writes = []

    def run(self, query, **params):
        if "SET n.amount" in query or "SET r.amount" in query:
            rec = self.records[params["key"]]
            if str(rec["amount"]) != params["expected"]:
                return SimpleNamespace(single=lambda: None)
            rec.update(amount=params["amount"], as_read=params["as_read"], checked=params["checked"])
            self.writes.append(params["key"])
            return SimpleNamespace(single=lambda: {"key": params["key"]})
        if "n.amount IS NOT NULL" in query:
            return [dict(key=k, what=r.get("what", "node"), name=r["name"], amount=r["amount"], as_read=r.get("as_read"),
                         checked=r.get("checked"), date=r["date"], files=r.get("files"), locations=r.get("locations"),
                         manual_fields=r.get("manual_fields", [])) for k, r in self.records.items()]
        return []


def _figure_graph():
    loc = json.dumps([{"source_document_id": FILE_ID, "source_file": KELL, "page_start": 1}])
    return FigureGraph({
        "deposit": {"name": "Cash Deposit BR 014 Fenwick on 2024-03-18", "amount": 800.0, "date": "2024-03-18",
                    "files": str([KELL])},
        "received": {"what": "connection", "name": "Cash Deposit BR 014 Fenwick on 2024-03-18 Travis Kell",
                     "amount": 800.0, "date": "2024-03-18", "locations": loc},
        "agrees": {"name": "Pocketwire to Lena Marsh", "amount": 500.0, "date": "2024-03-16", "files": [KELL]},
        "opening": {"name": "Opening Balance 2024-03-18", "amount": 12345.0, "date": "2024-03-18", "files": [KELL]},
        "edited": {"name": "Deposit a person typed", "amount": 800.0, "date": "2024-03-18", "files": [KELL],
                   "manual_fields": ["amount"]},
        "other_file": {"name": "Deposit", "amount": 800.0, "date": "2024-03-18", "files": ["other.pdf"]},
    })


def test_graph_amounts_take_the_ledger_amount_and_keep_the_page_reading(ledger, monkeypatch):
    graph = _figure_graph()
    monkeypatch.setattr(check, "file_names", lambda session, case_id: NAMES)
    report = check.check_case("case", apply=True, db_session=object(), graph_session=graph)
    assert sorted(graph.writes) == ["deposit", "received"]
    for key in ("deposit", "received"):
        rec = graph.records[key]
        assert (rec["amount"], rec["as_read"], rec["checked"]) == (9800.0, 800.0, 9800.0)
    assert graph.records["edited"]["amount"] == 800.0 and graph.records["opening"]["amount"] == 12345.0
    assert (report["amounts_replaced"], report["amounts_written"]) == (3, 2)  # the person-typed one only counted
    assert ledger["refreshed"] == ["deposit"]

    again = check.check_case("case", apply=True, db_session=object(), graph_session=graph)
    assert again["amounts_written"] == 0 and sorted(graph.writes) == ["deposit", "received"]

    ledger["rows"][(KELL, date(2024, 3, 18))] = [LedgerRow(KELL, date(2024, 3, 18), 80000)]
    check.check_case("case", apply=True, db_session=object(), graph_session=graph)
    assert (graph.records["deposit"]["amount"], graph.records["deposit"]["as_read"]) == (800.0, None)


def test_graph_amount_switch_off_leaves_amounts(ledger, monkeypatch):
    monkeypatch.setenv("GRAPH_AMOUNT_LEDGER_CHECK", "0")
    monkeypatch.setattr(check, "file_names", lambda session, case_id: NAMES)
    graph = _figure_graph()
    check.check_case("case", apply=True, db_session=object(), graph_session=graph)
    assert graph.writes == []


def test_connection_search_text_shows_the_ledger_amount_beside_the_reading():
    from services.embed_all.sources import relationship_item
    row = {"id": "r1", "a": "Travis Kell", "type": "RECEIVED_PAYMENT", "b": "Cash Deposit BR 014 Fenwick on 2024-03-18",
           "detail": "Travis Kell made a cash deposit at branch 014 Fenwick.", "date": "2024-03-18", "amount": 9800.0,
           "amount_as_read": 800.0, "quotes": ["2024-03-18\nCASH DEPOSIT BR 014 FENWICK\n800.00"],
           "locations": json.dumps([{"source_document_id": FILE_ID, "page_start": 1}])}
    item = relationship_item("case", row, {"src-doc": FILE_ID})
    assert "Amount: 9800.0 (the ledger amount; read from the page as 800.0)." in item.text
    assert item.cite == f"doc://{FILE_ID}/1"
