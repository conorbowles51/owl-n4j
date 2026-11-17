"""The case search service (lx-casesearch B): question understanding, reranking with a score and reason per hit,
duplicates removed, grades with weaker results counted and pageable, whole units, one result shape.

Every test here fails on the code before the service (no ``services.case_search``): D12 (no relevance scoring),
D13 (results were 60- to 400-character snippets), D19 (no shared result shape), D1 (no shared search)."""
from __future__ import annotations

import json
from datetime import date

import pytest

from services.case_search import rerank as R
from services.case_search import service as S
from services.case_search import shape, units
from services.case_search import understand as U


# ---- understanding --------------------------------------------------------------------------------------------------

def test_dates_become_day_windows():
    spans = U.date_spans("What happened on 12 April 2024 and on April 15, 2024?")
    assert [(a, b) for a, b, _ in spans] == [(date(2024, 4, 12), date(2024, 4, 12)), (date(2024, 4, 15), date(2024, 4, 15))]


def test_a_span_of_days_and_a_between_take_the_questions_year():
    assert [(a, b) for a, b, _ in U.date_spans("the night of 12-13 April 2024")] == [(date(2024, 4, 12), date(2024, 4, 13))]
    assert [(a, b) for a, b, _ in U.date_spans("between 23 May and 7 June 2024")] == [(date(2024, 5, 23), date(2024, 6, 7))]


def test_a_month_is_a_window_of_the_whole_month():
    assert [(a, b) for a, b, _ in U.date_spans("payments in May 2024")] == [(date(2024, 5, 1), date(2024, 5, 31))]


def test_a_day_with_no_year_is_not_guessed():
    w = U.windows(None, "c", "where was he on 12 April?")
    assert w["windows"] == []
    assert any("no year" in n for n in w["notes"])


def test_windows_run_local_midnight_to_local_midnight():
    class Conn:
        def execute(self, *a, **k):
            class R:
                def scalar(self):
                    return "America/New_York"
            return R()
    w = U.windows(Conn(), "c", "on 12 April 2024")
    assert w["zone"] == "America/New_York"
    assert w["windows"][0]["from"] == "2024-04-12T04:00:00+00:00"
    assert w["windows"][0]["to"] == "2024-04-13T04:00:00+00:00"


def test_names_are_found_without_question_words():
    assert U.names("Did Harold Vint call Mateo on Friday?") == ["Harold Vint", "Harold", "Vint", "Mateo"]


# ---- reranking ------------------------------------------------------------------------------------------------------

def _cands(n, area="ledger"):
    return [{"area": area, "key": str(i), "text": "row %d" % i, "cite": "txn://%d" % i, "fused": 1.0 / (i + 1),
             "kind": "ledger", "kind_label": "statement row"} for i in range(n)]


def test_every_candidate_gets_a_score_and_a_reason():
    def model(prompt):
        items = [l for l in prompt.splitlines() if l.startswith("[") and "] (" in l]
        return json.dumps({"scores": [{"i": k + 1, "score": 10 - k, "reason": "why %d" % k} for k in range(len(items))]})
    c = _cands(3)
    r = R.rerank("who paid", c, terms=["paid"], model_call=model)
    assert r["reranked"] and r["scored"] == 3 and r["not_scored"] == 0
    assert [x["score"] for x in c] == [10, 9, 8]
    assert all(x["reason"] for x in c)


def test_a_model_failure_keeps_every_candidate_unscored_and_says_so():
    def model(prompt):
        raise RuntimeError("402 Insufficient Balance")
    c = _cands(4)
    r = R.rerank("q", c, terms=[], model_call=model)
    assert not r["reranked"] and r["not_scored"] == 4
    assert "did not answer" in r["note"]
    assert len(c) == 4 and all(x["score"] is None for x in c)


def test_candidates_beyond_the_scored_ones_are_counted_not_dropped():
    def model(prompt):
        items = [l for l in prompt.splitlines() if l.startswith("[") and "] (" in l]
        return json.dumps({"scores": [{"i": k + 1, "score": 5, "reason": "r"} for k in range(len(items))]})
    c = _cands(R.MAX_CANDIDATES + 7)
    r = R.rerank("q", c, terms=[], model_call=model)
    assert r["scored"] == R.MAX_CANDIDATES and r["not_scored"] == 7
    assert "7 of" in r["note"]


# ---- duplicates, order, grades --------------------------------------------------------------------------------------

def test_the_same_message_on_two_phones_is_kept_once_with_the_other_place():
    a = {"area": "phone_text", "key": "1", "cite": "rec://a", "text": "Meet at the yard [rec://a]", "sources": ["words"]}
    b = {"area": "phone_text", "key": "2", "cite": "rec://b", "text": "Meet at the yard [rec://b]", "sources": ["meaning"]}
    out, removed = S.dedupe([a, b])
    assert removed == 1 and out == [a]
    assert a["also_at"] == ["rec://b"] and a["sources"] == ["meaning", "words"]


def test_grades_follow_the_stated_rule():
    assert [S.grade(s) for s in (10, 7, 6.5, 4, 3.9, 0, None)] == [
        "strong", "strong", "moderate", "moderate", "weak", "weak", "ungraded"]


def test_order_puts_scored_first_and_kinds_take_turns_within_a_score():
    c = [dict(area="ledger", key="l1", score=8, fused=0.9), dict(area="ledger", key="l2", score=8, fused=0.8),
         dict(area="phone_text", key="p1", score=8, fused=0.1), dict(area="documents", key="d1", score=None, fused=1),
         dict(area="casework", key="w1", score=2, fused=0.5)]
    assert [x["key"] for x in S.order(c)] == ["l1", "p1", "l2", "w1", "d1"]


# ---- the service: totals, paging, weaker results never dropped, shape ----------------------------------------------

@pytest.fixture
def fake_gather(monkeypatch):
    def install(cands, notes=()):
        monkeypatch.setattr(S, "understand", lambda conn, case, q: {
            "terms": ["vint"], "names": [], "expansions": [], "windows": [], "zone": "UTC", "notes": [],
            "phrasings": []})
        monkeypatch.setattr(S.net, "gather", lambda *a, **k: {
            "candidates": [dict(c) for c in cands], "searched": ["ledger (meaning and words)"], "not_searched": [],
            "notes": list(notes), "meaning_search": True, "documents_by_words": None, "clock": {}})
        monkeypatch.setattr(S.units, "build", lambda conn, case, h, terms: dict(h, unit="record", chars_not_shown=0))
    return install


def _scoring(scores):
    def model(prompt):
        items = [l for l in prompt.splitlines() if l.startswith("[") and "] (" in l]
        return json.dumps({"scores": [{"i": k + 1, "score": scores[k], "reason": "r%d" % k} for k in range(len(items))]})
    return model


def test_weaker_results_are_counted_and_pageable(fake_gather):
    fake_gather(_cands(5))
    model = _scoring([9, 2, 5, 1, 8])
    p1 = S.search(None, "case", "who paid vint", limit=2, phrase=False, model_call=model, use_cache=False)
    assert p1["total"] == 5 and p1["shown"] == 2 and p1["next_offset"] == 2
    assert p1["grades"] == {"strong": 2, "moderate": 1, "weak": 2, "ungraded": 0}
    assert [h["score"] for h in p1["hits"]] == [9, 8]
    assert all(h["reason"] and h["grade"] == "strong" for h in p1["hits"])
    p3 = S.search(None, "case", "who paid vint", offset=4, limit=2, phrase=False, model_call=model, use_cache=False)
    assert p3["shown"] == 1 and p3["next_offset"] is None and p3["hits"][0]["grade"] == "weak"
    assert shape.check(p1) == [] and shape.check(p3) == []


def test_min_grade_says_how_many_are_below_it(fake_gather):
    fake_gather(_cands(4))
    r = S.search(None, "case", "q", min_grade="strong", phrase=False, model_call=_scoring([9, 2, 3, 1]),
                 use_cache=False)
    assert r["total"] == 1 and r["below_grade"] == 3
    assert any("3 weaker results" in n for n in r["notes"])


def test_an_empty_search_says_why(fake_gather):
    fake_gather([])
    r = S.search(None, "case", "brightwater", phrase=False, model_call=_scoring([]), use_cache=False)
    assert r["total"] == 0 and r["why_empty"] and "not proof of absence" in r["why_empty"]
    assert shape.check(r) == []


def test_no_model_still_answers_in_search_order_and_says_so(fake_gather, monkeypatch):
    fake_gather(_cands(3))
    monkeypatch.setattr(S.R, "default_model_call", lambda: None)
    r = S.search(None, "case", "q", use_cache=False)
    assert r["total"] == 3 and not r["reranked"]
    assert all(h["grade"] == "ungraded" for h in r["hits"])
    assert any("No ranking model" in n for n in r["notes"])


def test_paging_reads_the_cached_order_without_asking_the_model_again(fake_gather):
    fake_gather(_cands(4))
    calls = []

    def model(prompt):
        calls.append(1)
        return _scoring([1, 2, 3, 4])(prompt)
    S._cache.clear()
    S.search(None, "case-x", "same question", limit=2, phrase=False, model_call=model)
    S.search(None, "case-x", "same question", offset=2, limit=2, phrase=False, model_call=model)
    assert len(calls) == 1


# ---- whole units ----------------------------------------------------------------------------------------------------

def test_a_long_unit_is_cut_around_the_match_and_the_cut_is_said():
    body = "x" * 9000 + " the tow invoice " + "y" * 9000
    text_, left = units._cut(body, ["tow invoice"], "documents")
    assert "tow invoice" in text_ and left == len(body) - units.UNIT_CHARS
    assert "characters of this record are not shown" in text_ and "get_document_text" in text_


def test_a_unit_is_not_a_sliver():
    body = "line %d of the thread\n" * 100 % tuple(range(100))
    hit = units.build(None, "c", {"area": "phone_text", "key": "k", "text": body}, ["thread"])
    assert hit["text"] == body and hit["unit"] == "message window" and hit["chars_not_shown"] == 0


# ---- the shape checker itself ---------------------------------------------------------------------------------------

def test_shape_check_catches_a_zero_with_no_reason_and_a_missing_key():
    assert shape.check({"total": 0, "shown": 0, "next_offset": None, "searched": ["x"], "not_searched": [],
                        "why_empty": None}) == ["an empty result must say why"]
    assert shape.check({"total": 3}) and "missing" in shape.check({"total": 3})[0]


def test_conform_fills_the_shape_from_a_tools_own_keys():
    d = shape.conform({"total_matching": 0, "returned": 0, "items": [], "limitation": "Nothing matched."},
                      searched="phone messages by words")
    assert shape.check(d) == [] and d["why_empty"] == "Nothing matched."


# ---- the Search page's route ----------------------------------------------------------------------------------------

def test_the_search_page_result_keeps_the_dialogs_fields_beside_the_grades():
    from routers.search import search_page_result
    res = {"question": "q", "total": 30, "shown": 1, "offset": 0, "next_offset": 1, "searched": ["ledger"],
           "not_searched": [], "why_empty": None, "notes": [], "meaning_search": True, "grades": {"strong": 1},
           "hits": [{"n": 1, "area": "ledger", "cite": "txn://t1", "text": "Payment on 15 Apr 2024:\n USD 185.00",
                     "grade": "strong", "score": 9.0, "reason": "the tow payment", "matched": ["meaning", "words"],
                     "read_by_a_model": False}]}
    out = search_page_result(res)
    h = out["hits"][0]
    assert out["query"] == "q" and out["areas_searched"] == ["ledger"] and out["total"] == 30
    assert h["matched"] == "both" and h["snippet"] == "Payment on 15 Apr 2024: USD 185.00" and h["key"] == "txn://t1"
    assert h["grade"] == "strong" and h["reason"] == "the tow payment" and h["as_read"] is False


def test_hits_past_the_page_budget_are_listed_as_excerpts_never_left_out(fake_gather, monkeypatch):
    long = [dict(c, text="row %d " % i + "x" * 900 + " vint " + "y" * 900) for i, c in enumerate(_cands(6))]
    fake_gather(long)
    monkeypatch.setattr(S.units, "build", lambda conn, case, h, terms: dict(h, unit="record", chars_not_shown=0))
    r = S.search(None, "case", "q", limit=6, phrase=False, model_call=_scoring([9, 8, 7, 6, 5, 4]), use_cache=False,
                 page_chars=4000)
    assert r["shown"] == 6 and r["next_offset"] is None
    assert [h["unit"] for h in r["hits"]] == ["record", "record", "excerpt", "excerpt", "excerpt", "excerpt"]
    assert all("vint" in h["text"] and len(h["text"]) <= S.EXCERPT_CHARS + 2 for h in r["hits"][2:])
    assert any("Pass offset=2 to read them whole" in n for n in r["notes"])
