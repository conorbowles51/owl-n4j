"""Chat reads the case search's ranked phone and document hits (lx-casesearch B). Fails on the code before: chat had
no reranked list, names were never tied to their numbers, and a passage only the case search finds never reached
the answer."""
from __future__ import annotations

from contextlib import contextmanager

import services.case_search as CS
from services import retrieval_fusion as F
from services.rag_service import RAGService


def _res(hits):
    return {"total": len(hits), "grades": {}, "reranked": True, "hits": hits}


def _hit(n, cite, grade="strong", key="", unit="message window"):
    return {"n": n, "area": "phone_text" if cite.startswith("rec://") else "documents", "cite": cite, "key": key,
            "title": "T%d" % n, "text": "text %d" % n, "grade": grade, "reason": "why", "unit": unit}


def _install(monkeypatch, hits):
    @contextmanager
    def conn():
        yield object()

    class Engine:
        def connect(self):
            return conn()
    import postgres.session as PS
    monkeypatch.setattr(PS, "_get_engine", lambda: Engine())
    monkeypatch.setattr(CS, "search", lambda *a, **k: _res(hits))


def test_strong_and_moderate_hits_join_and_a_hit_chat_already_found_is_not_sent_twice(monkeypatch):
    found = [{"id": "c1", "text": "old", "distance": 0.5,
              "metadata": {"evidence_file_id": "f1", "page_start": "2", "doc_name": "Invoice"}}]
    _install(monkeypatch, [_hit(1, "doc://f1/2"), _hit(2, "rec://r2", key="f9:10"), _hit(3, "rec://r3", "weak"),
                           _hit(4, "txn://t4"), _hit(5, "doc://f5/1", "moderate"), _hit(6, "doc://f6/1", unit="excerpt")])
    log = {}
    added = RAGService._case_search_passages(RAGService.__new__(RAGService), "q", "case", found, log)
    assert found[0]["_case_rank"] == 1
    assert [a["id"] for a in added] == ["case:rec://r2", "case:doc://f5/1"]
    assert added[0]["metadata"]["record_uid"] == "r2" and added[0]["metadata"]["evidence_file_id"] == "f9"
    assert added[1]["metadata"]["page_start"] == "1" and added[1]["_case_rank"] == 3
    assert log["case_search"]["added"] == 2 and log["case_search"]["already_found"] == 1


def test_the_switch_turns_it_off(monkeypatch):
    _install(monkeypatch, [_hit(1, "doc://f1/2")])
    monkeypatch.setenv("LOUPE_CHAT_CASE_SEARCH", "off")
    assert RAGService._case_search_passages(RAGService.__new__(RAGService), "q", "case", [], {}) == []


def test_the_case_searchs_order_counts_as_one_list_in_the_fusion():
    vec = [{"id": "v%d" % i, "text": "v", "distance": 0.1 * i} for i in range(1, 4)]
    found_by_both = dict(vec[2], _case_rank=1)
    only_case = {"id": "case:rec://x", "text": "c", "_case_search": True, "_case_rank": 2}
    pinned, fused, stats = F.fuse([vec[0], vec[1], found_by_both, only_case], [], [])
    order = [c["id"] for c in fused]
    # v3 is third by distance but first in the case search: two lists put it first
    assert order[0] == "v3" and "case:rec://x" in order and stats["case_search"] == 2
