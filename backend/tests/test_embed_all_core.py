"""lx-embedall C: one shared path keeps the index in step with its sources: new items are embedded, a changed item
replaces its old vector (a correction embeds the corrected value only), a deleted item is removed, a refused embedding
stops the run but still removes what was deleted. Invented data; no database, no model."""
from __future__ import annotations

from datetime import datetime, timezone

from services.embed_all import core
from services.embed_all.core import Item


class FakeStore:
    def __init__(self):
        self.rows, self.vectors = {}, {}

    def existing(self, case_id, area):
        return {k: (h, n) for (c, a, k), (h, n) in self.rows.items() if c == case_id and a == area}

    def put(self, case_id, area, items, vectors):
        for it, vecs in zip(items, vectors):
            for n in range(self.rows.get((case_id, area, it.key), (0, 0))[1]):
                self.vectors.pop((area, it.key, n), None)  # an older, longer text leaves no pieces behind
            for n, (piece, vec) in enumerate(zip(it.pieces, vecs)):
                self.vectors[(area, it.key, n)] = (piece, vec)
            self.rows[(case_id, area, it.key)] = (it.digest(), len(it.pieces))

    def remove(self, case_id, area, keys):
        for k, count in keys.items():
            self.rows.pop((case_id, area, k), None)
            for n in range(count):
                self.vectors.pop((area, k, n), None)


class Embedder:
    def __init__(self):
        self.seen, self.fail = [], None

    def __call__(self, texts):
        if self.fail:
            raise RuntimeError(self.fail)
        self.seen.extend(texts)
        return [[float(len(t)), 0.0] for t in texts]


def ledger_item(key, text, **kw):
    return Item("ledger", key, text, title=key, cite="txn://" + key, **kw)


def test_new_items_are_embedded_once_and_unchanged_items_are_left_alone():
    store, emb = FakeStore(), Embedder()
    items = [ledger_item("a", "Payment 1 to guard"), ledger_item("b", "Payment 2 to landlord")]
    first = core.reconcile("c1", "ledger", items, store, emb)
    assert first["embedded"] == 2 and len(emb.seen) == 2
    again = core.reconcile("c1", "ledger", items, store, emb)
    assert again["embedded"] == 0 and again["updated"] == 0 and again["unchanged"] == 2 and len(emb.seen) == 2


def test_a_correction_embeds_the_corrected_value_only():
    store, emb = FakeStore(), Embedder()
    core.reconcile("c1", "ledger", [ledger_item("a", "Payment of 100.00 USD to Garcia")], store, emb)
    res = core.reconcile("c1", "ledger", [ledger_item("a", "Payment of 1,000.00 USD to Garcia")], store, emb)
    assert res["updated"] == 1
    held = [p for p, _ in store.vectors.values()]
    assert held == ["Payment of 1,000.00 USD to Garcia"]  # the old value is not searchable any more


def test_a_changed_citation_or_date_re_embeds_the_item():
    store, emb = FakeStore(), Embedder()
    core.reconcile("c1", "ledger", [ledger_item("a", "same text")], store, emb)
    moved = ledger_item("a", "same text", date=datetime(2024, 1, 2, tzinfo=timezone.utc))
    assert core.reconcile("c1", "ledger", [moved], store, emb)["updated"] == 1


def test_a_deleted_item_is_removed_from_the_index_and_the_vectors():
    store, emb = FakeStore(), Embedder()
    core.reconcile("c1", "ledger", [ledger_item("a", "one"), ledger_item("b", "two")], store, emb)
    res = core.reconcile("c1", "ledger", [ledger_item("a", "one")], store, emb)
    assert res["removed"] == 1
    assert [k for (_, _, k) in store.rows] == ["a"] and [k for (_, k, _) in store.vectors] == ["a"]


def test_a_refused_embedding_stops_the_run_keeps_what_was_done_and_still_removes_deleted_items():
    store, emb = FakeStore(), Embedder()
    core.reconcile("c1", "ledger", [ledger_item("a", "one"), ledger_item("gone", "two")], store, emb)
    emb.fail = "429 insufficient_quota"
    res = core.reconcile("c1", "ledger", [ledger_item("a", "one"), ledger_item("new", "three")], store, emb)
    assert res["stopped"].startswith("429") and res["pending"] == 1 and res["embedded"] == 0
    assert res["removed"] == 1 and ("c1", "ledger", "gone") not in store.rows  # a delete needs no embedding
    assert ("c1", "ledger", "new") not in store.rows  # retried next pass: its signature was not saved


def test_a_long_text_is_split_in_overlapping_pieces_and_a_shorter_text_leaves_none_behind():
    store, emb = FakeStore(), Embedder()
    long_text = " ".join("word%d" % i for i in range(3000))
    core.reconcile("c1", "statement_pages", [Item("statement_pages", "p", long_text)], store, emb)
    pieces = [k for k in store.vectors if k[1] == "p"]
    assert len(pieces) >= 3 and all(len(p) <= core.PIECE_CHARS for p, _ in store.vectors.values())
    core.reconcile("c1", "statement_pages", [Item("statement_pages", "p", "short now")], store, emb)
    assert [p for p, _ in store.vectors.values()] == ["short now"]


def test_a_wrong_number_of_vectors_is_a_refusal_not_a_silent_drop():
    store = FakeStore()
    res = core.reconcile("c1", "ledger", [ledger_item("a", "one"), ledger_item("b", "two")], store,
                         lambda texts: [[0.0]])
    assert "returned 1 vectors for 2 texts" in res["stopped"] and not store.rows


def test_a_text_the_service_cannot_take_fails_that_item_only_and_never_stops_the_run():
    """Live 17 Nov: one thread line over the 8,192-token limit stopped the sweep at the same file in every pass and kept
    every later case from being embedded."""
    store = FakeStore()

    def embed(texts):
        return [None if "too long" in t else [1.0, 0.0] for t in texts]
    res = core.reconcile("c1", "ledger", [ledger_item("a", "fine"), ledger_item("b", "too long"), ledger_item("c", "also fine")],
                         store, embed)
    assert res["stopped"] is None and res["embedded"] == 2 and res["failed"] == 1
    assert sorted(k for (_, _, k) in store.rows) == ["a", "c"]


def test_clamp_keeps_any_text_under_the_input_limit_of_the_embedding_model():
    assert core.clamp("short text") == "short text"
    assert len(core.clamp("x" * 20000)) == core.MAX_TOKEN_WEIGHT
    assert len(core.clamp("\U0001F600" * 20000)) == core.MAX_TOKEN_WEIGHT // 3  # emoji count as three


def test_the_default_embedder_asks_one_by_one_when_a_batch_loses_a_text_and_returns_none_for_invalid_input(monkeypatch):
    from services import embedding_service
    from services.embed_all import runner

    class Bad(Exception):
        status_code = 400

    class Svc:
        def generate_embeddings_batch(self, texts, batch_size=64):
            return [[0.0]]  # the batch call hides which text failed and returns fewer vectors

        def generate_embedding(self, text):
            if text == "bad":
                raise Bad("Invalid 'input[1]': maximum input length is 8192 tokens.")
            if text == "down":
                raise RuntimeError("Error code: 429 insufficient_quota")
            return [1.0]
    monkeypatch.setattr(embedding_service, "EmbeddingService", Svc)
    embed = runner.default_embed()
    assert embed(["ok", "bad"]) == [[1.0], None]
    import pytest
    with pytest.raises(RuntimeError):
        embed(["ok", "down"])  # a refusal stops the run: it is not a bad text


def test_a_new_reader_version_changes_every_area_signature(monkeypatch):
    from services.embed_all import sources

    class Conn:
        def execute(self, *a, **k):
            return type("R", (), {"scalar": lambda self: "3|2026-11-01"})()
    before = sources.signature(Conn(), "c", "casework")
    monkeypatch.setattr(sources, "SOURCES_VERSION", "s3")
    assert sources.signature(Conn(), "c", "casework") != before
