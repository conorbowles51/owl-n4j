"""lx-agenttools: a tool error says what was wrong and where the right value comes from. Each text below was a bare or
generic message on the recorded runs (14 days): read_tool_result_page ended on a bare ``'items'`` 49 times,
get_money_between on "Use a valid party or account identifier." 9 times, get_document_text on "That evidence file is not
in this case." 10 times and "Continue with the revision..." 8 times, get_decisions on "Use a valid identifier." 5 times."""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from services.agent import ledger_reading_tools as LR
from services.agent import source_read_tools as SR
from services.agent.tools import AgentToolContext, make_agent_tools
from services.financial import money_between as MB


def test_money_between_names_the_formats_what_was_given_and_where_ids_come_from():
    with pytest.raises(MB.MoneyBetweenError) as named:
        MB.parse_side("Mateo Ruiz")
    text = str(named.value)
    assert "you gave 'Mateo Ruiz'" in text and "get_identity_suggestions" in text and "search_graph_entities" in text
    with pytest.raises(MB.MoneyBetweenError) as bad_id:
        MB.parse_side("party:not-a-uuid")
    assert "'not-a-uuid'" in str(bad_id.value) and "get_financial_coverage" in str(bad_id.value)


def test_a_bad_ledger_identifier_or_subject_says_what_was_given_and_where_ids_come_from():
    with pytest.raises(LR.LedgerReadingError) as bad:
        LR._uuid("garage payment", "payment")
    assert "'garage payment' is not a valid payment" in str(bad.value) and "UUID" in str(bad.value)
    with pytest.raises(LR.LedgerReadingError) as subject:
        LR._subject("the garage payment")
    assert "you gave 'the garage payment'" in str(subject.value) and "get_financial_transactions" in str(subject.value)
    with pytest.raises(LR.LedgerReadingError) as kind:
        LR._subject("invoice:%s" % uuid4())
    assert "'invoice' is not a kind of subject" in str(kind.value)


class _Db:
    """The two reads read_document_text makes before its text read: a file row, then the stored text's revision."""
    def __init__(self, record, row):
        self._record, self._row = record, row

    def scalar(self, _query):
        return self._record

    def execute(self, _query):
        return SimpleNamespace(one_or_none=lambda: self._row)


def test_a_document_read_says_where_the_file_id_comes_from_and_which_argument_carries_the_revision():
    with pytest.raises(ValueError) as shape:
        SR.read_document_text(_Db(None, None), uuid4(), "Lease.pdf")
    assert "'Lease.pdf' is not an evidence file id" in str(shape.value) and "doc://" in str(shape.value)
    with pytest.raises(ValueError) as missing:
        SR.read_document_text(_Db(None, None), uuid4(), str(uuid4()))
    assert "not in this case" in str(missing.value) and "get_evidence_files" in str(missing.value) and "doc://" in str(missing.value)
    row = SimpleNamespace(content_sha256="abc", source_locations=[], character_count=10)
    with pytest.raises(ValueError) as revision:
        SR.read_document_text(_Db(SimpleNamespace(), row), uuid4(), str(uuid4()), page_offset=5)
    assert "expected_revision" in str(revision.value) and "next_offset" in str(revision.value)


def _page_tool(views):
    ctx = AgentToolContext(case_id="00000000-0000-0000-0000-0000000000d1")
    ctx.model_views.update(views)
    return ctx, {t.name: t for t in make_agent_tools(ctx)}["read_tool_result_page"]


@pytest.mark.parametrize("switches", [None, ""])   # fit items on by default, and every item off (live 17 Nov)
def test_a_wrong_result_path_reads_the_largest_part_and_lists_the_paths_not_an_error(switches, monkeypatch):
    # lx-deepinvest 17 Nov: live run defb0282 (switches B and T off) asked paths items, events, items; each was an
    # error, and the stall guard stopped the run with no answer after the third.
    if switches is None:
        monkeypatch.delenv("LOUPE_AGENT_FIT", raising=False)
    else:
        monkeypatch.setenv("LOUPE_AGENT_FIT", switches)
    _ctx, tool = _page_tool({"res_one": {"data": {"items": [{"a": i} for i in range(5)], "total": 5}}})
    out = tool.invoke({"result_id": "res_one", "path": ["data", "results"]})
    assert out["status"] == "success"
    assert out["data"]["path_used"] == ["data", "items"] and out["data"]["items"][0] == {"a": 0}
    assert {"path": ["data", "items"], "items": 5} in out["data"]["paths"]
    assert "no part at data/results" in out["summary"] and "'results'" != out["summary"]
    # the path without its root is read at that root
    root = tool.invoke({"result_id": "res_one", "path": ["items"], "offset": 2})
    assert root["status"] == "success" and root["data"]["items"][0] == {"a": 2}
    # a second wrong path does not read the same first page again
    again = tool.invoke({"result_id": "res_one", "path": ["events"]})
    assert again["status"] == "success" and "already read" in again["summary"] and "items" not in again["data"]


def test_a_right_path_with_an_offset_outside_it_is_still_said_as_an_error():
    _ctx, tool = _page_tool({"res_one": {"data": {"items": [{"a": i} for i in range(5)], "total": 5}}})
    out = tool.invoke({"result_id": "res_one", "path": ["data", "items"], "offset": 9})
    assert out["status"] == "error" and "0 to 5" in out["error"]


def test_a_refused_ledger_read_puts_the_reason_in_the_summary_line_the_model_reads_first():
    from contextlib import contextmanager

    @contextmanager
    def no_db():
        yield None

    ctx = AgentToolContext(case_id="00000000-0000-0000-0000-0000000000d2", ledger_session_factory=no_db)
    tool = {t.name: t for t in make_agent_tools(ctx)}["get_decisions"]
    out = tool.invoke({"subject": "the garage payment"})
    assert out["status"] == "error"
    assert "you gave 'the garage payment'" in out["summary"] and "get_financial_transactions" in out["summary"]
