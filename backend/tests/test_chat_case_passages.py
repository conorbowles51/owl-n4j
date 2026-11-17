"""Chat cites payments (txn://) and graph entities (entity://) from the case search (lx-chatcite B-D). Each test fails
on the code before: chat took phone and document hits only, entity:// parsed as nothing, and an answer's link to a
record that is not in the case was kept."""
from __future__ import annotations

import uuid
from contextlib import contextmanager

import services.case_search as CS
from services import case_citations as C
from services import chat_case_passages as P
from services.rag_service import RAGService


def _hit(n, cite, grade="strong", title=None, text="row text"):
    return {"n": n, "area": "ledger" if cite.startswith("txn") else "graph", "cite": cite, "key": cite.split("://")[1],
            "title": title or "T%d" % n, "text": text, "grade": grade, "reason": "why", "unit": "statement row"}


def _install(monkeypatch, hits, facts):
    @contextmanager
    def conn():
        yield object()

    class Engine:
        def connect(self):
            return conn()
    import postgres.session as PS
    monkeypatch.setattr(PS, "_get_engine", lambda: Engine())
    monkeypatch.setattr(CS, "search", lambda *a, **k: {"total": len(hits), "grades": {}, "reranked": True, "hits": hits})
    monkeypatch.setattr(P, "payment_facts", lambda c, case, ids: {i: facts[i] for i in ids if i in facts})


def test_chat_asks_the_case_search_for_payments_and_graph_entities(monkeypatch):
    seen = {}

    def fake(*a, **k):
        seen.update(k)
        return {"total": 0, "grades": {}, "reranked": False, "hits": []}
    _install(monkeypatch, [], {})
    monkeypatch.setattr(CS, "search", fake)
    RAGService._case_search_passages(RAGService.__new__(RAGService), "q", "case", [], {})
    assert {"ledger", "graph"} <= set(seen["kinds"]) and {"ledger", "graph"} <= set(seen["areas"])


def test_a_payment_and_an_entity_become_passages_with_citations_that_open_them(monkeypatch):
    tid = str(uuid.uuid4())
    facts = {tid: {"line": "Payment · 2024-04-12 · USD 150.00 out · to Harold Vint · statement page 3", "page": 3}}
    _install(monkeypatch, [_hit(1, "txn://" + tid, title="Tow"), _hit(2, "entity://harold-vint", title="Harold Vint (Person)")],
             facts)
    log = {}
    added = RAGService._case_search_passages(RAGService.__new__(RAGService), "q", "case", [], log)
    by_id = {a["id"]: a for a in added}
    pay = by_id["case:txn://" + tid]
    assert pay["metadata"]["cite"] == "txn://" + tid and "page_start" not in pay["metadata"]
    assert pay["text"].startswith("Payment · 2024-04-12 · USD 150.00 out") and pay["_case_other_rank"] == 1 and "_case_rank" not in pay
    assert by_id["case:entity://harold-vint"]["metadata"]["cite"] == "entity://harold-vint"
    assert log["case_search"]["added"] == 2


def test_a_payment_that_is_not_a_row_of_the_case_is_left_out(monkeypatch):
    _install(monkeypatch, [_hit(1, "txn://" + str(uuid.uuid4()))], {})
    assert RAGService._case_search_passages(RAGService.__new__(RAGService), "q", "case", [], {}) == []


def test_a_key_with_spaces_is_cited_encoded_and_read_back_whole():
    made = P.passage(_hit(1, "entity://Harold Vint"), "entity://Harold Vint", {}, "case")
    cite = made["metadata"]["cite"]
    assert " " not in cite
    assert C.parse_citation(cite).target == "Harold Vint"


def test_entity_citations_parse_and_are_found_in_answers():
    cit = C.parse_citation("entity://harold-vint")
    assert (cit.scheme, cit.target) == ("entity", "harold-vint")
    assert [c.href for c in C.citations_in("see [Vint](entity://harold-vint) and [x](https://example.com)")] == [
        "entity://harold-vint"]
    assert C.parse_citation("entity://") is None


def _patch_case(monkeypatch, txns, entities):
    monkeypatch.setattr(C, "_transactions", lambda s, c, ids: {i: txns[i] for i in ids if i in txns})
    monkeypatch.setattr(C, "_entities", lambda c, keys: {k: entities[k] for k in keys if k in entities})
    monkeypatch.setattr(C, "_records", lambda s, c, ids: set())
    monkeypatch.setattr(C, "_with_production_numbers", lambda s, c, r: r)


def test_a_cited_id_that_is_not_in_the_case_is_dropped_and_counted(monkeypatch):
    good, bad = str(uuid.uuid4()), str(uuid.uuid4())
    _patch_case(monkeypatch, {good: {"ledger_status": "admitted", "superseded_by_id": None, "page": 2,
                                     "evidence_file_id": None}}, {"harold-vint": "Harold Vint"})
    text = f"Paid [the tow]({'txn://' + good}); also [a ghost](txn://{bad}) and [a ghost entity](entity://nobody) and [Vint](entity://harold-vint)."
    out, dropped = C.drop_unresolved(None, str(uuid.uuid4()), text)
    assert dropped == 2
    assert "[the tow](txn://%s)" % good in out and "[Vint](entity://harold-vint)" in out
    assert bad not in out and "nobody" not in out and "a ghost entity" in out


def test_a_citation_that_could_not_be_checked_is_kept_not_dropped(monkeypatch):
    _patch_case(monkeypatch, {}, {})

    def down(c, keys):
        raise RuntimeError("graph down")
    monkeypatch.setattr(C, "_entities", down)
    out, dropped = C.drop_unresolved(None, str(uuid.uuid4()), "[Vint](entity://harold-vint)")
    assert dropped == 0 and "entity://harold-vint" in out


def test_the_answer_says_how_many_citations_were_removed():
    rag = RAGService.__new__(RAGService)
    out, n = rag._pin_citations(None, "")
    assert (out, n) == ("", 0)


def test_payments_and_entities_never_move_a_phone_or_document_in_the_fusion():
    from services import retrieval_fusion as F
    docs = [{"id": "case:doc://f%d/1" % i, "text": "d", "_case_search": True, "_case_rank": i} for i in (1, 2, 3)]
    others = [{"id": "case:txn://t%d" % i, "text": "p", "_case_search": True, "_case_other_rank": i} for i in (1, 2)]
    _, alone, _ = F.fuse([dict(d) for d in docs], [], [])
    _, mixed, stats = F.fuse([dict(d) for d in docs] + [dict(o) for o in others], [], [])
    assert {c["id"]: c["_rrf"] for c in alone} == {c["id"]: c["_rrf"] for c in mixed if c["id"] in {d["id"] for d in docs}}
    assert stats["case_search_other"] == 2 and stats["case_search"] == 3


def test_payments_do_not_use_up_the_phone_and_document_cap(monkeypatch):
    tids = [str(uuid.uuid4()) for _ in range(12)]
    facts = {t: {"line": "Payment", "page": 1} for t in tids}
    hits = [_hit(i, "txn://" + t) for i, t in enumerate(tids, 1)] + [_hit(99, "doc://f9/1")]
    hits[-1]["area"] = "documents"
    _install(monkeypatch, hits, facts)
    added = RAGService._case_search_passages(RAGService.__new__(RAGService), "q", "case", [], {})
    assert [a["id"] for a in added if a.get("_case_rank")] == ["case:doc://f9/1"]
    assert sum(1 for a in added if a.get("_case_other_rank")) == RAGService.CASE_SEARCH_OTHER_PASSAGES
