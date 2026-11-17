"""lx-embedall D, carried by lx-casesearch: the agent searches by meaning and words together. ``search_by_meaning`` is
the case search (``services.case_search``: reranked, graded, whole units); ``search_case`` adds its ranked list
beside the word groups by default and not when ``exact`` is set."""
from __future__ import annotations

import services.case_search as CS
from services.agent import phone_cross_tools as T
from services.search import search as S


def fake_search(*a, **k):
    hits = [{"n": 1, "kind": "phones", "area": "phone_text", "kind_label": "phone messages", "title": "C3 thread",
             "cite": "rec://u1", "rec": "rec://u1", "text": "sent the watchman cash [rec://u1]", "unit": "message window",
             "chars_not_shown": 0, "score": 9.0, "grade": "strong", "reason": "pays the guard", "matched": ["meaning"],
             "also_at": [], "read_by_a_model": False},
            {"n": 2, "kind": "ledger", "area": "ledger", "kind_label": "statement row", "title": "t", "cite": "txn://t",
             "rec": None, "text": "Payment", "unit": "statement row with its month", "chars_not_shown": 0, "score": 3.0,
             "grade": "weak", "reason": "a payment, not to the guard", "matched": ["meaning", "words"], "also_at": [],
             "read_by_a_model": False}]
    return {"question": "q", "total": 2, "shown": 2, "offset": 0, "next_offset": None,
            "grades": {"strong": 1, "moderate": 0, "weak": 1, "ungraded": 0}, "grade_rule": "rule", "below_grade": 0,
            "hits": hits, "searched": ["phones (meaning and words)", "ledger (meaning and words)"], "not_searched": [],
            "notes": [], "why_empty": None, "meaning_search": True, "reranked": True, "ranking_model": "m",
            "duplicates_removed": 0, "seconds": {}, "understood": {"terms": ["guard"]}}


def test_search_by_meaning_is_a_tool_and_cites_each_hit_with_its_grade(monkeypatch):
    monkeypatch.setattr(CS, "search", fake_search)
    assert "search_by_meaning" in {name for name, *_ in T.TOOLS}
    out = T.search_by_meaning(object(), "c1", "paying the guard")
    assert out["coverage"].startswith("Searched phones (meaning and words); ledger (meaning and words). 2 found")
    assert [(i["matched"], i["cite"], i["grade"]) for i in out["items"]] == [
        (["meaning"], "rec://u1", "strong"), (["meaning", "words"], "txn://t", "weak")]
    assert out["items"][0]["rec"] == "rec://u1" and out["items"][1]["rec"] is None
    assert out["total"] == 2 and out["next_offset"] is None and out["items"][0]["reason"]


def test_search_case_adds_the_ranked_list_by_default_and_not_for_exact_words(monkeypatch):
    monkeypatch.setattr(CS, "search", fake_search)
    monkeypatch.setattr(T, "_phone_ids", lambda *a, **k: ([], []))
    monkeypatch.setattr(S, "search", lambda *a, **k: {"groups": [{"group": "messages", "total": 0, "items": [],
                                                                  "next_cursor": None}], "complete": True, "limits": []})
    default = T.search_case(object(), "c1", "guard")
    assert default["ranked"]["items"] and default["ranked"]["meaning_search"] is True
    assert default["total"] == 2 and default["why_empty"] is None
    exact = T.search_case(object(), "c1", "guard", exact=True)
    assert exact["ranked"] is None and exact["total"] == 0 and exact["why_empty"]


def test_a_case_search_failure_never_hides_the_word_results(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(CS, "search", boom)
    monkeypatch.setattr(T, "_phone_ids", lambda *a, **k: ([], []))
    monkeypatch.setattr(S, "search", lambda *a, **k: {"groups": [{"group": "messages", "total": 1, "items": [
        {"record_uid": "u2", "snippet": "guard"}], "next_cursor": None}], "complete": True, "limits": []})
    out = T.search_case(object(), "c1", "guard")
    assert out["available"] and "The ranked case search failed" in out["ranked"]["reason"]
    assert out["total"] == 1 and out["items"][0]["rec"] == "rec://u2"
