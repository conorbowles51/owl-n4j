"""lx-agenttools D9: the agent's timeline tool filters by person and by words in the event text."""
from unittest.mock import patch

from services.agent.tools import AgentToolContext, make_agent_tools
from services.neo4j.timeline_service import TimelineService

CASE = "00000000-0000-0000-0000-0000000000a9"
PAGE = {"events": [{"key": "e1", "date": "2026-01-02", "name": "Meeting"}], "count": 1, "total": 1,
        "next_cursor": None}


def _tool(**context):
    tools = {t.name: t for t in make_agent_tools(AgentToolContext(case_id=CASE, **context))}
    return tools["get_timeline_events"]


def test_build_filters_person_and_words_are_in_the_where_clause_and_the_params():
    where, params = TimelineService._build_filters(None, None, None, CASE, person_keys=["p1", "p1", "p2"],
                                                   text_words=["cash", "garage"])
    assert "n.key IN $person_keys" in where and "ALL(w IN $text_words" in where
    assert params["person_keys"] == ["p1", "p2"] and params["text_words"] == ["cash", "garage"]
    plain, plain_params = TimelineService._build_filters(None, None, None, CASE)
    assert "person_keys" not in plain and "person_keys" not in plain_params


def test_tool_resolves_names_to_keys_and_passes_person_and_words_to_the_service():
    rows = [{"key": "person-lena", "name": "Lena Marsh"}]
    with patch("services.agent.tools.graph_service.search_nodes", return_value=rows) as found, \
            patch("services.agent.tools.timeline_service.get_timeline_page", return_value=dict(PAGE)) as page:
        out = _tool().invoke({"people": ["Lena"], "text": "Cash  Garage"})
    kwargs = page.call_args.kwargs
    assert kwargs["person_keys"] == ["person-lena"] and kwargs["text_words"] == ["cash", "garage"]
    assert found.call_args.kwargs["case_id"] == CASE
    data = out["data"]
    assert data["filters"]["people"]["matched"][0]["entities"][0]["name"] == "Lena Marsh"
    assert data["filters"]["text_words"] == ["cash", "garage"]


def test_a_name_that_matches_no_entity_is_a_stated_zero_not_the_whole_timeline():
    with patch("services.agent.tools.graph_service.search_nodes", return_value=[]), \
            patch("services.agent.tools.timeline_service.get_timeline_page") as page:
        out = _tool().invoke({"people": ["Nobody Here"]})
    page.assert_not_called()
    assert out["data"]["total"] == 0 and out["data"]["filters"]["people"]["unmatched"] == ["Nobody Here"]
    assert "No entity in this case matches 'Nobody Here'" in out["summary"]
