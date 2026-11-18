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
        want = next((c["area"] for c in where.get("$and", []) if isinstance(c.get("area"), str)), None)
        rows = sorted((r for r in self.rows if want is None or r[1].get("area") in (None, want)),
                      key=lambda r: r[2])[:n_results]
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
    assert {"case_id": "c"} in conds and {"area": "accounts"} in conds  # one query per area
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
    assert all(len(w["embed_text"]) <= 800 + 120 and "[rec://" not in w["embed_text"] for w in wins)
    assert wins[0]["first_record_uid"] == "uid00" and wins[-1]["last_record_uid"] == "uid39"


def test_two_passages_of_one_document_page_are_one_hit():
    chunks = Coll([("p1 part a", {"evidence_file_id": "d", "chunk_index": 0, "doc_name": "d.pdf", "page_start": 1}, 0.5),
                   ("p1 part b", {"evidence_file_id": "d", "chunk_index": 1, "doc_name": "d.pdf", "page_start": 1}, 0.4),
                   ("p2", {"evidence_file_id": "d", "chunk_index": 2, "doc_name": "d.pdf", "page_start": 2}, 0.6)])
    hits = S.meaning_hits("c", [0.1], None, chunks, ["documents"])
    assert [h["text"] for h in hits] == ["p1 part b", "p2"]


def test_the_vector_text_of_a_thread_line_is_its_parties_and_words_not_the_repeated_lead():
    line = "Mon, Jan 1, 2024, 1:40:00 PM UTC | Phone 2 | Message | Owner of Phone 2: Travis Kell -> Mateo garage (+1 443-555-0100) | do not call the other phone"
    assert phone_area.compact(line) == "Travis Kell -> Mateo garage (+1 443-555-0100): do not call the other phone"
    assert phone_area.compact("  Transcript (machine-generated, m 1): hello") == "Transcript (machine-generated, m 1): hello"
    wins = phone_area.build_windows("Phone 2 · Messages · Mateo (part 1 of 1)", line, [{"kind": "phone_record", "start_char": 0, "end_char": len(line), "record_uid": "u1", "field_path": "Body"}])
    assert "Phone 2 | Message" not in wins[0]["embed_text"] and "Mon, Jan 1, 2024, 1:40:00 PM UTC" in wins[0]["embed_text"].splitlines()[0]
    assert "Phone 2 | Message" in wins[0]["text"] and wins[0]["text"].endswith("[rec://u1]")  # the passage keeps the line
    assert len(phone_area.stamp("abc")) == 64 and phone_area.stamp("abc") != phone_area.stamp("abd")  # fits the column


def test_a_new_vector_format_changes_the_area_signature_so_every_file_is_embedded_again(monkeypatch):
    class Conn:
        def execute(self, *a, **k):
            return type("R", (), {"scalar": lambda self: "3|abcdef"})()
    before = phone_area.signature(Conn(), "c")
    monkeypatch.setattr(phone_area, "FORMAT", "e3")
    assert phone_area.signature(Conn(), "c") != before


def test_the_best_hit_of_every_area_comes_before_the_second_hit_of_any():
    items = Coll([("transcript", meta("transcripts", "t"), 1.30), ("pay 1", meta("ledger", "p1"), 1.00),
                  ("pay 2", meta("ledger", "p2"), 1.05), ("pay 3", meta("ledger", "p3"), 1.10)])
    hits = S.meaning_hits("c", [0.1], items, None, ["transcripts", "ledger"])
    order = [h["key"] for h in S.fuse(hits, [], 10)]
    assert order[:2] == ["p1", "t"] and order[2:] == ["p2", "p3"]


def test_one_line_longer_than_a_window_is_cut_into_windows_that_cite_the_same_record():
    line = "Mon | Phone 1 | Message | A -> B | " + ("word " * 3000)
    wins = phone_area.build_windows("T", line, [{"kind": "phone_record", "start_char": 0, "end_char": len(line),
                                                 "record_uid": "u1", "field_path": "Body"}], limit=3500)
    assert len(wins) >= 4 and all(len(w["text"]) <= 3500 + 60 for w in wins)
    assert all("[rec://u1]" in w["text"] for w in wins)


class EntColl:
    def query(self, query_embeddings, n_results, where, include):
        assert where == {"case_id": "c"}
        return {"ids": [["k1"]], "documents": [["Person: Travis Kell \u2014 inside man"]], "metadatas": [[{"name": "Travis Kell"}]],
                "distances": [[0.9]]}


def test_graph_entities_are_searched_by_meaning_in_the_case_only():
    hits = S.meaning_hits("c", [0.1], None, None, ["entities"], entities_collection=EntColl())
    assert [(h["area"], h["title"], h["cite"]) for h in hits] == [("entities", "Travis Kell", "/cases/c/graph")]


def test_the_queries_of_one_search_go_side_by_side_and_read_back_the_same_hits():
    import threading
    rows = [("pay %s" % a, meta(a, "k" + a), 0.1 + i / 100) for i, a in enumerate(("ledger", "accounts", "parties"))]

    class Slow(Coll):
        """Each query waits until three are in flight at once: one after another, they never are."""
        barrier = threading.Barrier(3, timeout=5)

        def query(self, **kw):
            Slow.barrier.wait()
            return Coll.query(self, **kw)
    hits = S.meaning_hits("c", [0.1], Slow(rows), None, ["ledger", "accounts", "parties"])
    serial = S.meaning_hits("c", [0.1], Coll(rows), None, ["ledger", "accounts", "parties"])
    assert [(h["area"], h["key"], h["distance"]) for h in hits] == [(h["area"], h["key"], h["distance"]) for h in serial]
    assert [h["area"] for h in hits] == ["ledger", "accounts", "parties"]


def test_connections_of_one_subject_and_source_are_one_hit_and_rank_after_source_records():
    def rel(key, b, dist):
        title = "storage agreement unit 212 mentioned in %s" % b
        return ("%s. read from: %s" % (title, b),
                meta("relationships", key, title=title, person="storage agreement unit 212 " + b, cite="/cases/c/graph"), dist)
    rows = [rel("r%d" % i, "place %d" % i, 0.5 + i * 0.01) for i in range(5)]
    rows += [("rental agreement page", meta("ledger", "t1", cite="txn://t1"), 0.9),
             ("storage message", meta("ledger", "t2", cite="txn://t2"), 0.95)]
    hits = S.meaning_hits("c", [0.1], Coll(rows), None, ["relationships", "ledger"])
    assert [h["key"] for h in hits if h["area"] == "relationships"] == ["r0"]
    assert [h for h in hits if h["area"] == "relationships"][0]["also"] == 4
    fused = S.fuse(hits, [], 10)
    # Offset 0 (measured 17 Nov): the five connections are one hit, so the two source records sit beside it in the
    # first three instead of behind five copies of the same graph text.
    assert sorted(h["key"] for h in fused[:3]) == ["r0", "t1", "t2"]
    assert [h["key"] for h in fused if h["area"] == "relationships"] == ["r0"]


def test_phone_windows_and_document_passages_are_asked_for_in_separate_queries():
    asked = []

    class Spy(Coll):
        def query(self, query_embeddings, n_results, where, include):
            asked.append(where["$and"])
            return super().query(query_embeddings, n_results, where, include)
    chunks = Spy([("a document passage", {"evidence_file_id": "d", "chunk_index": 2, "doc_name": "d.pdf", "page_start": 4}, 0.4),
                  ("[rec://u1] hello", {"source_kind": "phone_text", "evidence_file_id": "f", "chunk_index": 0,
                                        "url": "rec://u1", "extraction_id": "e1"}, 0.5)])
    hits = S.meaning_hits("c", [0.1], None, chunks, ["phone_text", "documents"])
    assert len(asked) == 2
    assert any({"source_kind": "phone_text"} in a for a in asked)
    assert any({"source_kind": {"$ne": "phone_text"}} in a for a in asked)
    assert sorted(h["area"] for h in hits) == ["documents", "phone_text"]  # no hit twice


def test_a_graph_entity_scores_below_a_source_record_with_the_same_evidence():
    meaning = [{"area": "entities", "key": "e", "distance": 0.4, "text": "x", "person": "", "area_rank": 1},
               {"area": "documents", "key": "d", "distance": 0.4, "text": "y", "person": "", "area_rank": 1}]
    assert [h["key"] for h in S.fuse(meaning, [], 10)][0] == "d"


def test_collapsed_connections_stay_readable_on_the_hit_that_stands_for_them():
    def rel(key, b, dist):
        title = "storage agreement unit 212 mentioned in %s" % b
        return ("%s. read from: quote %s" % (title, b),
                meta("relationships", key, title=title, person="storage agreement unit 212 " + b, cite="/cases/c/graph"), dist)
    hits = S.meaning_hits("c", [0.1], Coll([rel("r%d" % i, "place%d" % i, 0.5 + i * 0.01) for i in range(8)]), None,
                          ["relationships"])
    assert len(hits) == 1 and hits[0]["also"] == 7
    assert len(hits[0]["also_hits"]) == S.ALSO_SHOWN and "quote place1" in hits[0]["also_hits"][0]["text"]


def test_the_snippet_shows_the_window_with_most_of_the_question_words():
    body = "cash note. " + "x " * 300 + "CASH DEPOSIT BR 031 WEXMOOR posted"
    assert "WEXMOOR" in S._snippet(body, ["cash", "deposit", "posted"])
