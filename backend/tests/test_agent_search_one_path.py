"""lx-searchfix A: every agent search of case content goes through the case search (``services.case_search``).

The agent's ledger, document and graph searches each had a search of their own (the ledger's every-word filter, the
passage vectors, the graph's name lookup) that never read meaning or the forms records use. This test counts the
direct calls to those searches in the agent's modules: each is listed with why it stays (an exact mode a person asks
for, a fallback, a name to a key). A new one fails the test: search through ``services.case_search`` instead.
Fails on the code before lx-searchfix: tools.py called the graph lookup and the passage vectors by default.
"""
from __future__ import annotations

import re
from pathlib import Path

AGENT = Path(__file__).resolve().parents[1] / "services" / "agent"
DIRECT = re.compile(r"\bsearch_nodes\(|\b_document_passages\(|\bsearch_chunks\(|\bsearch_entities\(|"
                    r"\btransaction_search\(|\bword_search_documents\(|\.query\(\s*query_embeddings")

ALLOWED = {
    "tools.py": (6, "exact=true of search_graph_entities (the graph lookup with the words as typed); the older "
                    "passage search behind search_documents' exact=true, include_below_floor and the Significant "
                    "layer (its definition, its call and its vector query); the words fallback when meaning search "
                    "is down; get_timeline_events turning a person's name into graph keys"),
}


def direct_calls() -> dict[str, int]:
    out = {}
    for p in sorted(AGENT.glob("*.py")):
        n = sum(1 for line in p.read_text(encoding="utf-8").splitlines()
                if DIRECT.search(line) and not line.lstrip().startswith("#"))
        if n:
            out[p.name] = n
    return out


def test_agent_searches_go_through_the_case_search_beyond_the_listed_exact_modes():
    bad = ["%s: %d direct search calls, %d listed" % (f, n, ALLOWED.get(f, (0,))[0])
           for f, n in direct_calls().items() if n > ALLOWED.get(f, (0,))[0]]
    assert bad == [], "search through services.case_search: %s" % bad


def test_the_list_cannot_grow_back():
    now = direct_calls()
    assert {f: n for f, (n, _) in ALLOWED.items()} == {f: now.get(f, 0) for f in ALLOWED}


def test_the_default_agent_searches_call_the_case_search():
    src = (AGENT / "tools.py").read_text(encoding="utf-8")
    for fn in ("def ranked_ledger", "def graph_search", "def case_documents"):
        body = src.split(fn, 1)[1].split("\n    def ", 1)[0]
        assert "CS.ranked(" in body or "CS.search(" in body, fn
