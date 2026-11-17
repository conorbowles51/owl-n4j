"""Every agent search tool answers in one shape (lx-casesearch C/D; D19 search-tools part; plan R4).

total, shown, next_offset, searched, not_searched and why_empty, filled from each tool's own keys in the one place
every tool result passes (``AgentToolContext.result``). A new tool that takes free text and is not listed in
``shape.SEARCH_TOOLS`` (or below, with why it is not a search) fails here. Fails on the code before: no tool result
carried these keys and nothing listed the search tools."""
from __future__ import annotations

import pytest

from services.agent import result_shape
from services.agent.tools import AgentToolContext, make_agent_tools
from services.case_search import shape

CASE = "00000000-0000-0000-0000-0000000000aa"
TEXT_ARGS = {"query", "queries", "search", "searches", "words", "place", "statements", "name"}
# Tools that take free text but do not search case content for it, each with why.
NOT_SEARCHES = {
    "ask_clarification": "asks the person a question",
    "record_working_notes": "writes the agent's own notes",
    "check_statements": "checks claims against several searches; its candidates per claim are lx-agenttools' shape",
    "run_readonly_cypher": "runs a graph query the agent writes",
    "get_dossier": "opens one named dossier",
    "get_theory": "opens one named theory",
    "get_interviews": "lists one person's interviews",
    "find_identifier_across_cases": "an exact identifier in the person's other cases",
    "analyze_financial_transactions": "totals and groups of the ledger rows its filters select, not a list of hits",
    "build_graph_artifact": "draws a graph from a query the agent writes",
    "build_table_artifact": "builds a table from a query the agent writes",
    "propose_entity": "proposes a new entity by name for a person to confirm",
    "list_artifacts": "lists the agent's own saved artifacts, not case material",
    "read_saved_agent_work": "reads the agent's own earlier answers, not case material",
}


def _tools():
    return {t.name: t for t in make_agent_tools(AgentToolContext(case_id=CASE))}


def test_every_tool_that_takes_free_text_is_a_listed_search_or_says_why_not():
    unlisted = []
    for name, tool in _tools().items():
        props = set((tool.args_schema.model_json_schema() if tool.args_schema else {}).get("properties", {}))
        if props & TEXT_ARGS and name not in shape.SEARCH_TOOLS and name not in NOT_SEARCHES \
                and name not in result_shape.READS and name not in result_shape.ACTIONS:
            unlisted.append("%s (%s)" % (name, ", ".join(sorted(props & TEXT_ARGS))))
    assert unlisted == [], "search tools without the shared result shape: %s" % unlisted


def test_every_listed_search_tool_exists():
    names = set(_tools())
    assert sorted(set(shape.SEARCH_TOOLS) - names) == []


def test_the_search_tools_are_the_ones_lx_agenttools_leaves_to_the_case_search_and_no_tool_is_shaped_twice():
    assert set(shape.SEARCH_TOOLS) == set(result_shape.SEARCH_OWNED)
    assert not set(shape.SEARCH_TOOLS) & set(result_shape.READS)


# Each tool's result as its code builds it (its own key names), empty and with hits.
SAMPLES = {
    "search_case": ({"total_matching": 0, "returned": 0, "items": [], "groups": [], "limitation": "Nothing matched."},
                    {"total_matching": 3, "returned": 2, "items": [{}, {}], "next_offset": 2}),
    "search_by_meaning": ({"total_matching": 0, "returned": 0, "items": [], "total": 0, "shown": 0, "next_offset": None,
                           "searched": ["ledger (meaning and words)"], "not_searched": [], "why_empty": "Nothing found."},
                          {"total_matching": 2, "returned": 2, "items": [{}, {}], "total": 2, "shown": 2,
                           "next_offset": None, "searched": ["ledger"], "not_searched": [], "why_empty": None}),
    "search_documents": ({"search": "meaning", "chunks": [], "total_matching": 0, "returned": 0, "next_offset": None,
                          "search_coverage": {"note": "No passage above the relevance floor."}},
                         {"search": "word", "results": [{}], "total": 4, "returned": 1, "next_offset": 1}),
    "search_exact_words": ({"total_documents": 0, "returned_documents": 0, "results": [], "note": "Not found."},
                           {"total_documents": 5, "returned_documents": 2, "results": [{}, {}], "next_offset": 2}),
    "search_graph_entities": ({"entities": [], "count": 0},
                              {"searches": [{"query": "a", "entities": [{}, {}], "count": 2},
                                            {"query": "b", "entities": [{}], "count": 1}], "count": 3}),
    "phone_find_people": ({"total_matching": 0, "returned": 0, "items": [], "has_more": False},
                          {"total_matching": 9, "returned": 4, "items": [{}] * 4, "next_offset": 4}),
    "phone_messages": ({"total_matching": 0, "returned": 0, "items": [], "limitation": "No message holds it."},
                       {"total_matching": 1, "returned": 1, "items": [{}]}),
    "get_financial_transactions": ({"total_matching": 0, "returned": 0, "items": []},
                                   {"searches": [{"total_matching": 2, "returned": 2, "items": [{}, {}]}]}),
}


def test_every_search_tool_has_a_sample():
    assert sorted(set(shape.SEARCH_TOOLS) - set(SAMPLES)) == []


@pytest.mark.parametrize("tool", sorted(SAMPLES))
def test_every_search_tool_result_has_the_shared_shape(tool):
    empty, found = (dict(x) for x in SAMPLES[tool])
    ctx = AgentToolContext(case_id=CASE)
    for data in (empty, found):
        out = ctx.result(tool, data, summary="s")["data"]
        assert shape.check(out) == [], (tool, out)
        # one shape: the same numbers under result_shape, as every other read tool gives them
        rs = out[result_shape.SHAPE_KEY]
        assert (rs["total"], rs["shown"], rs["next"], rs["why_empty"]) == (
            out["total"], out["shown"], out["next_offset"], out["why_empty"])
    e = ctx.result(tool, dict(SAMPLES[tool][0]), summary="s")["data"]
    assert e["total"] == 0 and e["why_empty"]
    f = ctx.result(tool, dict(SAMPLES[tool][1]), summary="s")["data"]
    assert f["total"] >= f["shown"] > 0 and f["why_empty"] is None


def test_a_tool_that_says_why_it_is_empty_keeps_its_own_words():
    out = AgentToolContext(case_id=CASE).result("phone_messages", dict(SAMPLES["phone_messages"][0]), summary="s")
    assert out["data"]["why_empty"] == "No message holds it."


def test_an_error_result_is_left_alone():
    out = AgentToolContext(case_id=CASE).result("search_documents", {"error": "x"}, summary="s", status="error")
    assert "total" not in out["data"]
