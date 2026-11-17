"""No new search path outside the case search (lx-casesearch D; D1; plan R1).

Text matching of case content (SQL LIKE/ILIKE, ``position(:x in ...)``, Cypher CONTAINS, SQLAlchemy ``.like`` /
``.ilike`` / ``.contains``, a direct vector query) belongs in ``services/case_search`` and the search modules it
calls. Every other place that matches text today is listed below with how many matches it holds and why. The test
fails when a file not listed matches text, or a listed file matches more than its count: a new search goes through
``services.case_search.search``, or it is an exact-identifier lookup added here with its reason.

Fails on the code before: nothing stopped a seventh search path (six grew side by side, D1)."""
from __future__ import annotations

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PATTERN = re.compile(r"""\bI?LIKE\s+[:'%(]|\bCONTAINS\b|\.ilike\(|\.like\(|\.contains\(|\.query\(\s*query_embeddings|"""
                     r"""position\(\s*:|\s~\*?\s*:\w""")

SEARCH = "a search module the case search calls"
IDENT = "exact identifiers, file names, keys or fixed labels, not a person's free text"
FREE = "free text matched outside the case search; a structured filter of its own tool (a narrower list), counted"

ALLOWED: dict[str, tuple[int, str]] = {
    # the shared search and what it calls
    "services/embed_all/search.py": (5, SEARCH),
    "services/phone/chat_retrieval.py": (2, SEARCH),
    "services/evidence_text_search_service.py": (2, SEARCH),
    "services/search/search.py": (7, SEARCH),
    "services/search/payments.py": (1, SEARCH),
    "services/vector_db_service.py": (1, SEARCH),
    "services/neo4j/graph_service.py": (11, SEARCH),
    # identifiers, keys, file names, fixed labels
    "routers/graph.py": (1, IDENT),
    "services/agent/all_cases.py": (2, IDENT),
    "services/agent/proposal_feedback.py": (1, IDENT),
    "services/agent/proposals.py": (1, IDENT),
    "services/agent/render_checks.py": (1, IDENT),
    "services/agent/tool_errors.py": (1, IDENT),
    "services/casebin_purge.py": (2, IDENT),
    "services/evidence_db_storage.py": (5, IDENT),
    "services/evidence_file_check.py": (3, IDENT),
    "services/evidence_signature.py": (1, IDENT),
    "services/financial/auto_read.py": (3, IDENT),
    "services/financial/closing_only_period.py": (3, IDENT),
    "services/financial/correlation.py": (4, IDENT),
    "services/financial/layout_memory.py": (1, IDENT),
    "services/financial/model_work_migration.py": (3, IDENT),
    "services/guidance.py": (1, IDENT),
    "services/manual_changes.py": (2, IDENT),
    "services/neo4j/document_service.py": (2, IDENT),
    "services/neo4j/timeline_service.py": (3, "two date-format checks; one is the timeline tool's own word filter "
                                              "(lx-deepinvest D9), a narrower list"),
    "services/phone/filters.py": (1, IDENT),
    "services/phone/graph_projection.py": (1, IDENT),
    "services/phone/phone_setup.py": (2, IDENT),
    "services/phone/review_share.py": (2, IDENT),
    "services/phone_analysis/device_users.py": (2, IDENT),
    "services/phone_analysis/reparse_comparison.py": (1, IDENT),
    "services/phone_analysis/vocabulary.py": (2, IDENT),
    "services/relations/sources.py": (2, IDENT),
    "services/step_history.py": (1, IDENT),
    "services/summary_ledger_check.py": (1, IDENT),
    "services/triage/profiler_service.py": (1, IDENT),
    "services/triage/triage_service.py": (1, IDENT),
    "services/corroborate/pasted.py": (1, IDENT),
    "services/corroborate/store.py": (4, "counts how often a phrase occurs in the case's messages, to weigh it; "
                                         "and finds every document, name and payment naming the chosen people: "
                                         "Corroborate counts all of their records in the windows, so a ranked page "
                                         "would drop some"),
    "services/agent/phone_cross_tools.py": (1, "a fixed one-time-code pattern, not a person's words"),
    "services/pattern_of_life/places.py": (2, "a fixed camera-folder pattern on media paths"),
    "services/phone/media_spread.py": (2, "a fixed camera-folder pattern on media paths"),
    # a tool's own narrower filter (its list, then the words); the agent's case-wide search is the case search
    "services/agent/case_material_tools.py": (6, FREE),
    "services/agent/casework_tools.py": (4, FREE),
    "services/dossier_service.py": (1, FREE),
    "services/notebook_service.py": (3, FREE),
    "services/workspace_entry_service.py": (14, FREE),
    "services/workspace_ai_service.py": (1, FREE),
    "services/financial/link_suggestions.py": (2, FREE),
    "services/financial/category_breakdown.py": (2, FREE),
    "services/financial/brokerage_ledger.py": (1, FREE),
    "services/phone/streams.py": (2, FREE),
    "services/phone/timeline_lens.py": (1, FREE),
    "services/phone/link_edges.py": (2, FREE),
}


def matches(text: str) -> int:
    return sum(1 for line in text.splitlines() if PATTERN.search(line) and not line.lstrip().startswith("#"))


def found() -> dict[str, int]:
    out: dict[str, int] = {}
    for root in ("services", "routers"):
        for p in sorted((BACKEND / root).rglob("*.py")):
            rel = p.relative_to(BACKEND).as_posix()
            if rel.startswith("services/case_search/"):
                continue
            n = matches(p.read_text(encoding="utf-8", errors="ignore"))
            if n:
                out[rel] = n
    return out


def test_no_text_matching_outside_the_case_search_beyond_the_listed_places():
    bad = []
    for rel, n in found().items():
        allowed = ALLOWED.get(rel)
        if allowed is None:
            bad.append("%s: %d new text match(es); search through services.case_search.search" % (rel, n))
        elif n > allowed[0]:
            bad.append("%s: %d text matches, %d allowed (%s)" % (rel, n, allowed[0], allowed[1]))
    assert bad == []


def test_the_list_holds_no_place_that_no_longer_matches():
    now = found()
    stale = sorted(rel for rel in ALLOWED if rel not in now)
    shrunk = sorted("%s: %d, listed %d" % (rel, now[rel], ALLOWED[rel][0]) for rel in ALLOWED
                    if rel in now and now[rel] < ALLOWED[rel][0])
    assert stale == [] and shrunk == [], "lower the counts so the list cannot grow back: %s" % (stale + shrunk)


def test_the_check_catches_a_new_search():
    assert matches('rows = conn.execute(text("SELECT * FROM notes WHERE body ILIKE :q"))') == 1
    assert matches("MATCH (n) WHERE toLower(n.name) CONTAINS $q RETURN n") == 1
    assert matches("q = q.filter(Note.body.ilike(term))") == 1
    assert matches("# a comment about LIKE :q") == 0
    assert matches('rows = q("SELECT id FROM texts WHERE content ~* :rx", rx=names)') == 1
    assert matches('rows = q("SELECT id FROM files WHERE name ~* \'\\\\.pdf$\'")') == 0
