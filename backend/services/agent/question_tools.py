"""Question-shaped agent tools built from the simple ones (lx-agentfit D and F).

Each tool does one question's searches in code, with the agent's own simple tools, so a question that took the agent
ten or twenty calls takes one. Nothing here computes a second answer: every search is a call of an existing tool,
and every item carries that tool's own citation.

- ``check_statements``: each statement (a claim, the other side's version, a witness's line) searched on every
  surface (ledger, phones, documents, graph) by the disconfirm sweep's search step (``disconfirm.search_all``), with
  what was searched and what was out of reach. Which records support and which contradict is the agent's reading,
  labelled so; no model call is made here.

Measured 11 Nov 2026 (real cases, last 30 days): defence questions ("government alleges fraud, client says she was a
broker", "consistencies and contradictions for each statement") stopped at the tool budget in 5 of 10 runs; one run
made 19 exact-word searches. The demo's Q1 never compared the State's version of a phone with the other phone.
"""
from __future__ import annotations

import re
from typing import Any

# Pages of one search read per statement before the rest is counted and stated (never silently dropped).
MAX_PAGES = 2
# Candidates shown per statement; the rest are counted and the call says how to narrow it.
MAX_CANDIDATES = 30
MAX_STATEMENTS = 8
READING_LABEL = ("Candidate records found by searching each statement's words on every surface. Which of them support "
                 "or contradict a statement is your reading, not a finding; say so in the answer.")


class _BoundedTools:
    """The disconfirm sweep's tool caller, reading at most MAX_PAGES pages of any one search; a cut search keeps its
    exact total, so the coverage states how many matched and how many were read."""

    def __init__(self, case_id):
        from services.agent.disconfirm import PAGE, Tools
        self._tools, self._page, self.cut = Tools(case_id), PAGE, 0

    def call(self, name, **kwargs):
        data = self._tools.call(name, **kwargs)
        if data.get("has_more") and int(kwargs.get("offset") or 0) >= self._page * (MAX_PAGES - 1):
            self.cut += 1
            return {**data, "has_more": False}
        return data

    def __getattr__(self, name):
        return getattr(self._tools, name)


_WORD = re.compile(r"[a-z0-9à-ſ]{4,}", re.I)


def _rank(claim: str, items: list[dict]) -> list[dict]:
    words = {w.lower() for w in _WORD.findall(claim or "")}
    return sorted(items, key=lambda item: -len(words & {w.lower() for w in _WORD.findall(item.get("text") or "")}))


def _expectation(n: int, statement: dict) -> dict:
    from services.agent.disconfirm import PLACE_WORDS, _clean, _day, _strings
    claim = _clean(statement.get("claim"), 600)
    if not claim:
        raise ValueError("Each statement needs its claim, in words.")
    return dict(id="S%d" % n, claim=claim, would_contradict=None, people=_strings(statement.get("people")),
                terms=_strings(statement.get("terms")), document_queries=_strings(statement.get("document_queries"), 300),
                about_place=statement.get("about_place") is True or bool(PLACE_WORDS.search(claim)),
                start=_day(statement.get("start")), end=_day(statement.get("end")), needs=[])


def check_statements(session, case_id, statements: list[dict]) -> dict:
    """Every statement searched on every surface; per statement the candidates (cite, surface, text), ranked by the
    statement's words, with the coverage of each surface."""
    from services.agent import disconfirm
    statements = [s.model_dump() if hasattr(s, "model_dump") else dict(s or {}) for s in statements or []]
    if not statements:
        raise ValueError("Give at least one statement to check.")
    if len(statements) > MAX_STATEMENTS:
        raise ValueError("Check up to %d statements in one call; split the rest into another call." % MAX_STATEMENTS)
    expectations = [_expectation(i + 1, s) for i, s in enumerate(statements)]
    for e in expectations:
        if not (e["people"] or e["terms"] or e["document_queries"]):
            raise ValueError("Statement %s needs people, terms or document_queries to search for." % e["id"])
    tools = _BoundedTools(case_id)
    census = disconfirm._census(session, tools, case_id)
    files = disconfirm.case_files(session, case_id)
    out = []
    for e in expectations:
        items, coverage = disconfirm.search_all(tools, e, census, files)
        ranked = _rank(e["claim"], items)
        shown = ranked[:MAX_CANDIDATES]
        out.append(dict(id=e["id"], claim=e["claim"], candidates=shown, candidates_found=len(items),
                        candidates_shown=len(shown), coverage=coverage,
                        **({"not_shown": "%d more candidates; check the statement again with narrower terms or a "
                                         "period to see them." % (len(items) - len(shown))}
                           if len(items) > len(shown) else {})))
    found = sum(s["candidates_found"] for s in out)
    return dict(statements=out, total_matching=len(out), returned=len(out), has_more=False, next_offset=None,
                label=READING_LABEL, searches_cut_at_pages=MAX_PAGES if tools.cut else None,
                coverage="Checked %d statement(s) on the ledger, phones, documents and graph: %d candidate record(s)%s."
                         % (len(out), found, "; %d search(es) read %d pages and counted the rest" % (tools.cut, MAX_PAGES)
                                             if tools.cut else ""))
