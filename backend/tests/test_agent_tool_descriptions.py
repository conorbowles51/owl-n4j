"""lx-agenttools R7: a tool's description matches what the tool does. Generated from the tool list, so a new tool
or a changed description is checked without anyone adding a case:

* every ``name=value`` the description teaches names a real argument;
* every tool the description points to exists (a renamed or removed tool leaves no stale pointer);
* a description that promises pages (``next_offset``, ``next_cursor``, "paged") has the argument that reads one;
* every word of a "filtered by ..." list matches an argument, so a promised filter is one the tool takes.
"""
import re

import pytest

from services.agent.tools import AgentToolContext, make_agent_tools

CASE = "00000000-0000-0000-0000-0000000000c1"
# Words in descriptions that look like tool names but are fields or labels of a result, not tools.
NOT_TOOLS = {"read_by"}
TOOLISH = re.compile(r"\b((?:get|search|list|phone|propose|build|read|find|draft|inspect|deep|record|plan|check|"
                     r"evaluate|identifier|create|revise|edit|append|calculate|request)_[a-z_]+)\b")
PAGING_ARGS = {"offset", "cursor", "page_offset", "additions_offset", "path"}


def _tools():
    seen = {}
    for ctx in (AgentToolContext(case_id=CASE), AgentToolContext(case_id=CASE, all_cases=True, user_id="u")):
        for tool in make_agent_tools(ctx):
            seen.setdefault(tool.name, tool)
    return seen


TOOLS = _tools()


def _args(tool):
    return set(tool.args_schema.model_fields) if tool.args_schema else set()


def _filter_items(text):
    found = re.search(r"\bfilter(?:ed)? by ([^.;:]+)", text)
    if not found:
        return []
    phrase = re.sub(r"\([^)]*\)", "", found.group(1))
    return [i.strip() for i in re.split(r",| and ", phrase) if i.strip()]


def problems(tool, known=None):
    """Where the description of ``tool`` promises something its arguments or the tool list cannot back."""
    known = TOOLS if known is None else known
    text, arguments, found = tool.description, _args(tool), []
    wrong = sorted(set(re.findall(r"\b([a-z][a-z_]+)=", text)) - arguments)
    if wrong:
        found.append(f"teaches {wrong}, which are not arguments of the tool")
    stale = sorted(t for t in set(TOOLISH.findall(text))
                   if t not in known and t not in arguments and t not in NOT_TOOLS and t != tool.name
                   and not t.endswith(("_id", "_ids", "_key", "_keys", "_date", "_text", "_state", "_type", "_types",
                                       "_minor", "_count")))
    if stale:
        found.append(f"points to tools that do not exist: {stale}")
    if "next_offset" in text and not arguments & {"offset", "page_offset", "additions_offset"}:
        found.append("promises next_offset, has no offset")
    if "next_cursor" in text and "cursor" not in arguments:
        found.append("promises next_cursor, has no cursor")
    if re.search(r"\bpaged\b|page through|in pages", text) and not arguments & PAGING_ARGS:
        found.append("promises pages, has no argument that reads one")
    for item in _filter_items(text):
        words = [w.rstrip("s") for w in re.findall(r"[a-z]{3,}", item.lower())]
        if not any(w in a for w in words for a in arguments):
            found.append(f"promises a filter by '{item}', but no argument matches it")
    return found


@pytest.mark.parametrize("name", sorted(TOOLS))
def test_the_description_promises_nothing_the_tool_cannot_do(name):
    assert problems(TOOLS[name]) == [], f"{name}: {problems(TOOLS[name])}"


def test_the_checks_bite_on_a_description_that_promises_what_the_tool_lacks():
    from pydantic import BaseModel

    class Args(BaseModel):
        query: str = ""

    class Fake:
        name = "fake_tool"
        args_schema = Args
        description = ("Read things filtered by person and date, paged by next_cursor; use show=all, or "
                       "get_removed_thing.")

    found = " | ".join(problems(Fake()))
    assert "show" in found and "get_removed_thing" in found and "no cursor" in found
    assert "filter by 'person" in found and "filter by 'date" in found


def test_the_timeline_description_names_the_person_and_word_filters_it_now_has():
    tool = TOOLS["get_timeline_events"]
    assert {"people", "text"} <= _args(tool)
    assert "people" in tool.description and "words" in tool.description
