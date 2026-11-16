"""lx-embedall D: one search across areas by meaning and by words, fused; each hit says why it matched and what was not
searched. Fake collections and a fake query embedder; no database."""
from __future__ import annotations

from services.embed_all import phone as phone_area
from services.embed_all import search as S


class Coll:
    def __init__(self, rows):
        self.rows, self.where = rows, None

    def query(self, query_embeddings, n_results, where, include):
        self.where = where
        rows = sorted(self.rows, key=lambda r: r[2])[:n_results]
        return {"documents": [[r[0] for r in rows]], "metadatas": [[r[1] for r in rows]], "distances": [[r[2] for r in rows]]}


def meta(area, key, **kw):
    return dict({"area": area, "item_key": key, "title": key, "cite": "txn://" + key, "case_id": "c"}, **kw)


def test_fusion_marks_hits_found_by_meaning_by_words_or_both():
    meaning = [{"area": "ledger", "key": "a", "distance": 0.4, "text": "x", "person": ""},
               {"area": "ledger", "key": "b", "distance": 0.9, "text": "y", "person": ""}]
    words = [{"area": "ledger", "key": "b", "words": 2, "text": "y", "person": ""},
             {"area": "casework", "key": "n", "words": 1, "text": "z", "person": ""}]
    got = {(h["area"], h["key"]): h["matched"] for h in S.fuse(meaning, words, 10)}
    assert got == {("ledger", "a"): "meaning", ("ledger", "b"): "both", ("casework", "n"): "words"}
    assert S.fuse(meaning, words, 10)[0]["key"] == "b"  # in both lists: ranked first


def test_meaning_hits_filter_by_case_area_and_date_and_drop_far_passages():
    items = Coll([("near", meta("ledger", "a"), 0.3), ("far", meta("ledger", "z"), 1.9)])
    from datetime import date
    hits = S.meaning_hits("c", [0.1], items, None, ["ledger", "accounts"], date_from=date(2024, 1, 1), date_to=date(2024, 2, 1))
    assert [h["key"] for h in hits] == ["a"]
    conds = items.where["$and"]
    assert {"case_id": "c"} in conds and {"area": {"$in": ["ledger", "accounts"]}} in conds
    assert any("item_ts" in c and "$gte" in c["item_ts"] for c in conds) and any("$lte" in c.get("item_ts", {}) for c in conds)


def test_person_filter_keeps_only_hits_naming_the_person():
    items = Coll([("paid Garcia", meta("ledger", "a", person="Garcia"), 0.3), ("paid Smith", meta("ledger", "b", person="Smith"), 0.2)])
    hits = S.meaning_hits("c", [0.1], items, None, ["ledger"], person="garcia")
    assert [h["key"] for h in hits] == ["a"]


def test_phone_hits_come_from_the_chunk_collection_with_their_record_link_and_phone_filter():
    chunks = Coll([("[rec://u1] hello", {"source_kind": "phone_text", "evidence_file_id": "f", "chunk_index": 0,
                                         "doc_name": "C3 thread", "url": "rec://u1", "extraction_id": "e1"}, 0.5),
                   ("a document passage", {"evidence_file_id": "d", "chunk_index": 2, "doc_name": "d.pdf", "page_start": 4}, 0.4)])
    hits = S.meaning_hits("c", [0.1], None, chunks, ["phone_text"], phone="e1")
    assert [(h["area"], h["cite"]) for h in hits] == [("phone_text", "rec://u1")]
    assert {"extraction_id": "e1"} in chunks.where["$and"] and {"source_kind": "phone_text"} in chunks.where["$and"]


def test_search_says_when_meaning_search_was_unavailable_and_what_was_not_searched(monkeypatch):
    class Eng:
        def connect(self):
            raise AssertionError("no words search without a connection in this test")
    monkeypatch.setattr(S, "word_hits", lambda *a, **k: [{"area": "ledger", "key": "a", "words": 1, "text": "burner phone paid",
                                                         "person": "", "title": "t", "cite": "txn://a"}])

    class Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
    eng = type("E", (), {"connect": lambda self: Conn()})()

    def refuse(q):
        raise RuntimeError("Error code: 429 insufficient_quota")
    res = S.search(eng, "c", "burner phone", embed_query=refuse, items_collection=Coll([]), chunks_collection=Coll([]))
    assert res["meaning_search"] is False and any("Meaning search unavailable" in n for n in res["notes"])
    assert res["hits"][0]["matched"] == "words"
    res = S.search(eng, "c", "burner", areas=["ledger", "phone_text", "documents", "nope"], date_from="2024-01-01",
                   embed_query=lambda q: [0.0], items_collection=Coll([]), chunks_collection=Coll([]))
    assert "phone_text" in res["not_searched"] and "documents" in res["not_searched"]
    assert res["areas_searched"] == ["ledger"] and any("unknown area: nope" in n for n in res["notes"])


def test_phone_windows_keep_consecutive_lines_of_one_thread_each_with_its_record_link():
    lines = ["Tue | C3 | WhatsApp | Ana -> Me | line number %d with some words in it" % i for i in range(40)]
    content = "\n".join(lines)
    locs, pos = [], 0
    for i, l in enumerate(lines):
        locs.append({"kind": "phone_record", "start_char": pos, "end_char": pos + len(l), "record_uid": "uid%02d" % i,
                     "field_path": "Body"})
        pos += len(l) + 1
    wins = phone_area.build_windows("C3 · WhatsApp · Ana (part 1 of 1)", content, locs, limit=800)
    assert len(wins) > 1
    assert sum(w["text"].count("[rec://") for w in wins) == 40
    flat = [u for w in wins for u in ("uid%02d" % i for i in range(40)) if "[rec://%s]" % u in w["text"]]
    assert flat == ["uid%02d" % i for i in range(40)]  # consecutive, in order, none twice
    assert all(len(w["embed_text"]) <= 800 + 80 and "[rec://" not in w["embed_text"] for w in wins)
    assert wins[0]["first_record_uid"] == "uid00" and wins[-1]["last_record_uid"] == "uid39"
