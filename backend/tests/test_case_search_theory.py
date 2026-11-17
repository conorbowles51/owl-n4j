"""The theory test ("test both directions") reads the files the case search ranks most relevant to the theory
(lx-casesearch B). Fails on the code before: candidates were any document holding a theory word or a word such as
"support", newest first, with no ranking."""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import services.case_search as CS
from services import phone_files, workspace_ai_service as W

CASE = uuid.UUID("00000000-0000-0000-0000-0000000000c1")


class FakeDb:
    def __init__(self, files):
        self.files = files

    def get(self, model, key):
        return self.files.get(key)

    def connection(self):
        return object()


def _hits(ids):
    out = []
    for n, (area, eid) in enumerate(ids, 1):
        cite = "doc://%s/1" % eid if area == "documents" else "rec://r%d" % n
        out.append({"n": n, "area": area, "key": "%s:%d" % (eid, n * 10), "cite": cite, "grade": "strong"})
    return out


def test_candidates_are_the_ranked_files_in_order_each_once(monkeypatch):
    a, b, c = (uuid.uuid4() for _ in range(3))
    files = {x: SimpleNamespace(id=x, case_id=CASE, source_type=None) for x in (a, b, c)}
    seen = {}

    def fake(conn, case_id, question, **kw):
        seen.update(question=question, kinds=kw.get("kinds"))
        return {"hits": _hits([("documents", b), ("phone_text", a), ("documents", b), ("documents", c)]), "total": 4,
                "grades": {"strong": 4}, "reranked": True, "notes": []}
    monkeypatch.setattr(CS, "search", fake)
    monkeypatch.setattr(phone_files, "external_processing_allowed", lambda db, item: True)
    theory = SimpleNamespace(title="Kell kept the trailer", body="at the yard in May")
    ids, how = W._ranked_candidate_ids(FakeDb(files), case_id=CASE, theory=theory)
    assert ids == [b, a, c]
    assert seen["question"] == "Kell kept the trailer\nat the yard in May" and set(seen["kinds"]) == {"documents", "phones"}
    assert how["search"] == "case search" and how["reranked"] is True


def test_a_file_kept_out_by_the_external_processing_decision_takes_no_place(monkeypatch):
    a, b = uuid.uuid4(), uuid.uuid4()
    files = {a: SimpleNamespace(id=a, case_id=CASE, source_type="phone_file"), b: SimpleNamespace(id=b, case_id=CASE)}
    monkeypatch.setattr(CS, "search", lambda *x, **k: {"hits": _hits([("documents", a), ("documents", b)]), "total": 2,
                                                        "grades": {}, "reranked": True, "notes": []})
    monkeypatch.setattr(phone_files, "external_processing_allowed", lambda db, item: item.id != a)
    ids, _ = W._ranked_candidate_ids(FakeDb(files), case_id=CASE, theory=SimpleNamespace(title="t", body="b"))
    assert ids == [b]


def test_at_most_twelve_places(monkeypatch):
    many = [uuid.uuid4() for _ in range(20)]
    files = {x: SimpleNamespace(id=x, case_id=CASE) for x in many}
    monkeypatch.setattr(CS, "search", lambda *x, **k: {"hits": _hits([("documents", m) for m in many]), "total": 20,
                                                        "grades": {}, "reranked": True, "notes": []})
    monkeypatch.setattr(phone_files, "external_processing_allowed", lambda db, item: True)
    ids, _ = W._ranked_candidate_ids(FakeDb(files), case_id=CASE, theory=SimpleNamespace(title="t", body="b"))
    assert ids == many[:W.CANDIDATE_PLACES]
