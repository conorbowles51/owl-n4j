"""lx-agenttools D19 / plan R4: every agent read tool states total, shown, next, searched, not searched, why empty."""
import pytest

from services.agent import result_shape as RS
from services.agent.tools import AgentToolContext, make_agent_tools

CASE = "00000000-0000-0000-0000-0000000000b1"
KEYS = {"total", "shown", "next", "searched", "not_searched", "why_empty"}


def _all_tool_names():
    names = {t.name for t in make_agent_tools(AgentToolContext(case_id=CASE))}
    names |= {t.name for t in make_agent_tools(AgentToolContext(case_id=CASE, all_cases=True, user_id="u"))}
    return names


def test_every_agent_tool_is_a_read_with_a_scope_entry_an_action_or_a_search_tool():
    missing = sorted(n for n in _all_tool_names() if not RS.covered(n))
    assert missing == [], f"add each to services.agent.result_shape (READS, ACTIONS or SEARCH_OWNED): {missing}"


def test_the_three_lists_do_not_overlap_and_name_no_removed_tool():
    assert not (RS.READS.keys() & RS.ACTIONS) and not (RS.READS.keys() & RS.SEARCH_OWNED)
    assert not (RS.ACTIONS & RS.SEARCH_OWNED)
    gone = sorted((set(RS.READS) | RS.ACTIONS | RS.SEARCH_OWNED) - _all_tool_names() - {"deep_checklist"})
    assert gone == [], f"result_shape names tools the agent no longer has: {gone}"


def test_every_read_entry_has_searched_not_searched_and_a_reason_for_empty():
    for name, entry in RS.READS.items():
        assert all(len(entry[k]) > 10 for k in ("searched", "not_searched", "empty")), name


@pytest.mark.parametrize("name", sorted(RS.READS))
def test_context_result_adds_the_full_shape_to_an_empty_list_and_says_why(name):
    ctx = AgentToolContext(case_id=CASE)
    out = ctx.result(name, {"items": [], "total_matching": 0, "returned": 0}, summary="Read 0.")
    shape = out["data"][RS.SHAPE_KEY]
    assert set(shape) == KEYS
    assert shape["total"] == 0 and shape["shown"] == 0 and shape["why_empty"]
    assert shape["why_empty"] in out["summary"], "the summary the model reads first must give the reason"


def test_a_page_states_total_shown_and_next_and_has_no_empty_reason():
    ctx = AgentToolContext(case_id=CASE)
    out = ctx.result("get_decisions", {"items": [{"a": 1}] * 25, "total": 60, "returned": 25, "next_offset": 25},
                     summary="Read 25 of 60.")
    shape = out["data"][RS.SHAPE_KEY]
    assert (shape["total"], shape["shown"], shape["next"], shape["why_empty"]) == (60, 25, 25, None)
    assert "Nothing found" not in out["summary"]


def test_a_single_record_is_one_of_one_and_a_tool_own_reason_wins():
    ctx = AgentToolContext(case_id=CASE)
    one = ctx.result("get_entity_details", {"entity": {"key": "k", "connections": []}}, summary="Loaded.")
    assert (one["data"][RS.SHAPE_KEY]["total"], one["data"][RS.SHAPE_KEY]["why_empty"]) == (1, None)
    own = ctx.result("phone_coverage", {"items": [], "total_matching": 0, "reason": "No phone is loaded here."},
                     summary="Read 0.")
    assert own["data"][RS.SHAPE_KEY]["why_empty"] == "No phone is loaded here."


def test_errors_and_actions_are_left_as_they_are_and_search_tools_take_the_case_searchs_shape():
    ctx = AgentToolContext(case_id=CASE)
    err = ctx.result("get_dossier", {"available": False, "reason": "x"}, summary="x", status="error", error="x")
    assert RS.SHAPE_KEY not in err["data"]
    assert RS.SHAPE_KEY not in ctx.result("propose_entity", {"proposal": {}}, summary="x")["data"]
    # a search tool is shaped once, by the case search (services/case_search/shape.py), under the same key
    searched = ctx.result("search_case", {"items": [], "total_matching": 0}, summary="x")["data"]
    assert searched[RS.SHAPE_KEY]["total"] == 0 and searched[RS.SHAPE_KEY]["why_empty"]
    assert searched[RS.SHAPE_KEY]["next"] is None and searched["total"] == 0
