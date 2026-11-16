"""lx-embedall D: the agent searches by meaning and words together. ``search_by_meaning`` is a tool; ``search_case`` adds
the meaning results beside its words by default and not when ``exact`` is set."""
from __future__ import annotations

from services.agent import phone_cross_tools as T
from services.embed_all import search as ES
from services.search import search as S


def fake_search(*a, **k):
    return {"query": "q", "hits": [{"area": "phone_text", "key": "k", "title": "C3 thread", "cite": "rec://u1",
                                    "matched": "meaning", "snippet": "sent the watchman cash [rec://u1]", "as_read": False},
                                   {"area": "ledger", "key": "t", "title": "t", "cite": "txn://t", "matched": "both",
                                    "snippet": "Payment", "as_read": False}],
            "terms": ["guard"], "areas_searched": ["phone_text", "ledger"], "not_searched": [], "notes": [],
            "meaning_search": True, "counts": {}}


def test_search_by_meaning_is_a_tool_and_cites_each_hit(monkeypatch):
    monkeypatch.setattr(ES, "search", fake_search)
    assert "search_by_meaning" in {name for name, *_ in T.TOOLS}
    out = T.search_by_meaning(object(), "c1", "paying the guard")
    assert out["coverage"] == "Searched phone_text, ledger by meaning and words."
    assert [(i["matched"], i["cite"]) for i in out["items"]] == [("meaning", "rec://u1"), ("both", "txn://t")]
    assert out["items"][0]["rec"] == "rec://u1" and out["items"][1]["rec"] is None


def test_search_case_adds_meaning_results_by_default_and_not_for_exact_words(monkeypatch):
    monkeypatch.setattr(ES, "search", fake_search)
    monkeypatch.setattr(T, "_phone_ids", lambda *a, **k: ([], []))
    monkeypatch.setattr(S, "search", lambda *a, **k: {"groups": [{"group": "messages", "total": 0, "items": [],
                                                                  "next_cursor": None}], "complete": True, "limits": []})
    default = T.search_case(object(), "c1", "guard")
    assert default["by_meaning"]["items"] and default["by_meaning"]["meaning_search"] is True
    assert T.search_case(object(), "c1", "guard", exact=True)["by_meaning"] is None


def test_a_meaning_failure_never_hides_the_word_results(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(ES, "search", boom)
    monkeypatch.setattr(T, "_phone_ids", lambda *a, **k: ([], []))
    monkeypatch.setattr(S, "search", lambda *a, **k: {"groups": [{"group": "messages", "total": 0, "items": [],
                                                                  "next_cursor": None}], "complete": True, "limits": []})
    out = T.search_case(object(), "c1", "guard")
    assert out["available"] and "Search by meaning failed" in out["by_meaning"]["reason"]
