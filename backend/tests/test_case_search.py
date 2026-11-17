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


def test_hits_that_share_a_page_link_are_different_records_and_all_kept():
    # graph connections all cite the case's graph page and bank accounts its financial page (demo case, gate 17 Nov:
    # 43 connections in origin's first 50 were one after duplicates were removed); a page link is not a record
    r1 = {"area": "relationships", "key": "rel:1", "cite": "/cases/c/graph",
          "text": "Penn's Used Tools LLC received payment CARD SALE M RUIZ 05/22/2024", "sources": ["meaning"]}
    r2 = {"area": "relationships", "key": "rel:2", "cite": "/cases/c/graph",
          "text": "Penn's Used Tools LLC sent payment CARD SALE C RUIZ 05/08/2024", "sources": ["meaning"]}
    a1 = {"area": "accounts", "key": "acct:1", "cite": "/cases/c/financial", "text": "bank 0042118830",
          "sources": ["words"]}
    again = dict(r1, sources=["words"])
    out, removed = S.dedupe([r1, r2, a1, again])
    assert out == [r1, r2, a1] and removed == 1
    assert r1["sources"] == ["meaning", "words"] and "also_at" not in r1


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


def test_phone_messages_take_turns_with_the_other_areas_and_never_all_rank_below_them(monkeypatch):
    """Fails on the code before: the dated areas' list (phone messages, documents) was joined after the other areas'
    list, so with no model ranking a phone question's best message sat below every statement row (gate 17 Nov: phone
    MRR 0.64 -> 0.50, a message found before lost)."""
    from services.case_search import net
    from services.embed_all import search as ES

    def meaning(case_id, vec, items, chunks, areas, **kw):
        out = []
        for a in areas:
            for i in range(1, 9):
                out.append({"area": a, "key": "%s%d" % (a, i), "text": "t", "distance": 0.1 * i + (0.3 if a == "phone_text" else 0),
                            "area_rank": i})
        return out
    monkeypatch.setattr(ES, "meaning_hits", meaning)
    monkeypatch.setattr(ES, "word_hits", lambda *a, **k: [])
    got = net.gather(object(), "c", "q", {"phrasings": [], "expansions": []}, ("phones", "ledger"),
                     areas=["phone_text", "ledger"], embed_query=lambda q: [0.0], collections=(object(), object()))
    keys = [c["key"] for c in got["candidates"]]
    assert keys.index("phone_text1") < 2 and keys.index("phone_text2") < 4


def test_graph_entities_take_their_turn_in_the_shared_lists_not_lists_of_their_own(monkeypatch):
    """Fails on the code before: graph entities by name and by meaning were two more lists, so each one's first hit
    scored beside the best of every other area together (gate 17 Nov: 30 of a question's first 60 places)."""
    from services.case_search import net
    from services.embed_all import search as ES
    import importlib
    G = importlib.import_module("services.neo4j.graph_service")
    from services import vector_db_service as V

    def meaning(case_id, vec, items, chunks, areas, **kw):
        return [{"area": a, "key": "%s%d" % (a, i), "text": "t", "distance": 0.1 * i, "area_rank": i}
                for a in areas for i in range(1, 6)]

    class Vec:
        def search_entities(self, *a, **k):
            return [{"id": "e%d" % i, "text": "e", "distance": 0.1 * i, "metadata": {}} for i in range(1, 6)]

    monkeypatch.setattr(ES, "meaning_hits", meaning)
    monkeypatch.setattr(ES, "word_hits", lambda *a, **k: [])
    monkeypatch.setattr(G.graph_service, "search_nodes",
                        lambda p, **k: [{"key": "n%d" % i, "name": "N%d" % i} for i in range(1, 6)])
    monkeypatch.setattr(V, "get_vector_db_service", lambda: Vec())
    got = net.gather(object(), "c", "q", {"phrasings": [], "expansions": [], "names": ["Ann"], "terms": []},
                     ("ledger", "casework", "graph"), embed_query=lambda q: [0.0], collections=(object(), object()))
    keys = [c["key"] for c in got["candidates"]]
    # the nearest entity takes its turn after each other area's best, as a ledger row or a note does
    assert keys.index("e1") > keys.index("casework1"), keys[:14]


def test_graph_names_are_looked_up_for_names_and_identifiers_not_ordinary_words(monkeypatch):
    """Fails on the code before: every question word was looked up as a graph name, so "patients" brought every
    entity holding the word (18 of a question's first 64 places on the second demo case, 17 Nov)."""
    import importlib
    from services.case_search import net
    G = importlib.import_module("services.neo4j.graph_service")
    from services import vector_db_service as V
    asked = []
    monkeypatch.setattr(G.graph_service, "search_nodes", lambda p, **k: asked.append(p) or [])

    class Vec:
        def search_entities(self, *a, **k):
            return []
    monkeypatch.setattr(V, "get_vector_db_service", lambda: Vec())
    net._graph("c", "q", ["Ann Ross"], ["patients", "refund", "2204"], embed_query=lambda q: [0.0])
    assert asked == ["Ann Ross", "2204"]


def test_graph_connections_and_entities_are_searched_as_the_graph(monkeypatch):
    """Fails on the code before: the graph's embedded connections ("relationships") were never searched, and asking
    for "entities" (the embedded-records search's name for them) searched no graph at all."""
    import importlib
    from services.case_search import net
    from services.embed_all import search as ES
    G = importlib.import_module("services.neo4j.graph_service")
    from services import vector_db_service as V
    seen = {"areas": set(), "graph": 0}
    monkeypatch.setattr(ES, "meaning_hits", lambda c, v, i, ch, areas, **k: seen["areas"].update(areas) or [])
    monkeypatch.setattr(ES, "word_hits", lambda c, k, t, areas, **kw: seen["areas"].update(areas) or [])
    monkeypatch.setattr(G.graph_service, "search_nodes", lambda p, **k: [])

    class Vec:
        def search_entities(self, *a, **k):
            seen["graph"] += 1
            return []
    monkeypatch.setattr(V, "get_vector_db_service", lambda: Vec())
    kw = dict(embed_query=lambda q: [0.0], collections=(object(), object()))
    u = {"phrasings": [], "expansions": [], "names": [], "terms": []}
    net.gather(object(), "c", "q", u, net.KINDS, **kw)
    assert "relationships" in seen["areas"] and seen["graph"] == 1
    seen["areas"].clear()
    net.gather(object(), "c", "q", u, ("graph",), areas=["entities"], **kw)
    assert seen["graph"] == 2 and "relationships" not in seen["areas"]


def test_documents_by_their_words_join_the_shared_word_list(monkeypatch):
    """Fails on the code before: documents found by their words were a list of their own, so the first of them
    scored beside the best word hit of every other area (gate 17 Nov: two document records origin showed in its
    first 50 fell past 50)."""
    from services.case_search import net
    from services.embed_all import search as ES
    monkeypatch.setattr(ES, "meaning_hits", lambda *a, **k: [])
    monkeypatch.setattr(ES, "word_hits", lambda c, k, t, areas, **kw: [
        {"area": a, "key": "%s%d" % (a, i), "text": "refund", "words": 2} for i in range(1, 4) for a in areas])
    monkeypatch.setattr(net, "_documents_by_words", lambda conn, c, q: ([
        {"area": "documents", "key": "d%d" % i, "text": "refund", "sources": ["document words"]} for i in range(1, 4)],
        {}))
    got = net.gather(object(), "c", "refund patients", {"phrasings": [], "expansions": []}, ("ledger", "documents"),
                     embed_query=lambda q: [0.0], collections=(object(), object()))
    keys = [c["key"] for c in got["candidates"]]
    assert keys.index("d1") > keys.index("ledger1") and keys.index("d1") > keys.index("statement_pages1"), keys


def test_name_ties_share_one_list_and_far_entities_are_left_out(monkeypatch):
    """Fails on the code before: each name tie was a list of its own, so a row found by three ties of one account
    scored three credits (demo case, 17 Nov: 40 of a question's first 50 places were one account's ledger rows), and
    the graph's nearest 20 entities came in however far their meaning was."""
    import importlib
    from services.case_search import net
    from services.embed_all import search as ES
    G = importlib.import_module("services.neo4j.graph_service")
    from services import vector_db_service as V
    monkeypatch.setattr(ES, "meaning_hits", lambda c, v, i, ch, areas, **k: [
        {"area": "casework", "key": "note%d" % n, "text": "t", "distance": 0.1 * n, "area_rank": n} for n in range(1, 4)])

    def words(c, k, terms, areas, **kw):
        if terms and terms[0].startswith("004"):
            return [{"area": "ledger", "key": "row%d" % n, "text": "t", "words": 1} for n in range(1, 4)]
        return []
    monkeypatch.setattr(ES, "word_hits", words)
    monkeypatch.setattr(G.graph_service, "search_nodes", lambda p, **k: [])

    class Vec:
        def search_entities(self, *a, **k):
            return [{"id": "near", "text": "e", "distance": 0.9, "metadata": {}},
                    {"id": "far", "text": "e", "distance": 1.9, "metadata": {}}]
    monkeypatch.setattr(V, "get_vector_db_service", lambda: Vec())
    u = {"phrasings": [], "expansions": [{"term": "0042118830"}, {"term": "0042118847"}, {"term": "0042118851"}],
         "names": [], "terms": []}
    got = net.gather(object(), "c", "q", u, ("ledger", "casework", "graph"), embed_query=lambda q: [0.0],
                     collections=(object(), object()))
    keys = [c["key"] for c in got["candidates"]]
    assert keys.index("note1") < keys.index("row1") and "far" not in keys and "near" in keys, keys


def test_one_file_uploaded_twice_shows_each_page_once_with_the_other_copy_listed():
    """Fails on the code before: the same statement uploaded twice (one content hash, two files) showed each page
    twice, once a place each (second demo case, 17 Nov: four statements, eight places)."""
    a, b, c = ("%08d-0000-0000-0000-000000000000" % n for n in (1, 2, 3))
    cands = [{"area": "statement_pages", "key": "a1", "cite": "doc://%s/1" % a, "text": "statement page one"},
             {"area": "documents", "key": "b1", "cite": "doc://%s/1" % b, "text": "page one as a passage"},
             {"area": "documents", "key": "c1", "cite": "doc://%s/1" % c, "text": "another file"},
             {"area": "documents", "key": "b2", "cite": "doc://%s/2" % b, "text": "page two"}]
    out, removed = S.dedupe(cands, {a: "h1", b: "h1", c: "h2"})
    assert [h["key"] for h in out] == ["a1", "c1", "b2"] and removed == 1
    assert out[0]["also_at"] == ["doc://%s/1" % b]
