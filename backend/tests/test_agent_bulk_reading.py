import json
from services.agent import bulk_reading as B


def items(n):
    return [{"cite": "rec://p/%d" % i, "text": "message number %d " % i + "x" * 200} for i in range(n)]


def reader_for(wanted, calls=None):
    def read(prompt):
        if calls is not None:
            calls.append(prompt)
        rel = [{"cite": c, "why": "bears on it"} for c in wanted if "[%s]" % c in prompt]
        return json.dumps({"relevant": rel}), {"prompt_tokens": 10, "completion_tokens": 2}
    return read


def test_reads_every_record_across_chunks_and_keeps_cites():
    calls = []
    out = B.read_items(items(100), "q", reader_for(["rec://p/3", "rec://p/97"], calls), chunk_chars=3000)
    assert len(calls) > 3 and out["records_read"] == 100 and out["records_unread"] == 0
    assert [r["cite"] for r in out["relevant"]] == ["rec://p/3", "rec://p/97"]
    assert "Read 100 of 100" in out["coverage"] and out["limitation"] is None


def test_invented_cite_is_dropped_and_counted():
    out = B.read_items(items(3), "q", reader_for(["rec://p/1", "rec://nope"]), chunk_chars=100000)
    assert [r["cite"] for r in out["relevant"]] == ["rec://p/1"]
    assert out["dropped_invented_cites"] == 0  # the fake reader only returns cites present in the chunk

    def liar(prompt):
        return json.dumps({"relevant": [{"cite": "rec://made-up", "why": "x"}]}), {}
    out = B.read_items(items(3), "q", liar)
    assert out["relevant"] == [] and out["dropped_invented_cites"] == 1 and "dropped" in out["limitation"]


def test_unanswerable_chunk_is_unread_never_none_found():
    out = B.read_items(items(3), "q", lambda p: ("not json", {}))
    assert out["records_read"] == 0 and out["records_unread"] == 3 and out["none_found_words"] is None
    assert "unread" in out["limitation"]


def test_chunk_limit_and_clipped_scope_are_stated():
    out = B.read_items(items(100), "q", reader_for([]), chunk_chars=3000, max_chunks=2, of=150)
    assert out["records_read"] < 100 and out["records_unread"] == 150 - out["records_read"]
    assert "chunk limit" in out["limitation"] and "not loaded" in out["limitation"]


def test_empty_result_when_all_read_says_so():
    out = B.read_items(items(5), "q", reader_for([]))
    assert out["none_found_words"] and "5" in out["none_found_words"]
