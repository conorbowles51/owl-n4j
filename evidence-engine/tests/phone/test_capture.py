"""Capture pass and recount on synthetic XML (01 units 1.3 and 1.4). No case material, no database.

Every test captures synthetic bytes into memory, recounts from what was stored and requires the recount to equal
the lxml counter on the same bytes, path by path and measure by measure (01 section 8.3).
"""
import io

import pytest

from app.phone.capture import Capture, CaptureMemoryBudgetExceeded
from app.phone.counter import count_stream
from app.phone.reconcile import reconcile
from app.phone.recount import MemoryRows, Recount

NS = 'xmlns="http://pa.cellebrite.com/report/2.0"'

REPORT = """<?xml version="1.0" encoding="utf-8"?>
<project id="p1" extractionType="Logical" {ns}>
  <sourceExtractions><extractionInfo id="0" name="E" /></sourceExtractions>
  <metadata section="Extraction Data"><item name="Time zone settings (ID)">Synthetic/Zone</item></metadata>
  <taggedFiles>
    <file id="f1" size="3" fs="x">
      <metadata section="File"><item name="Local Path">files\\Image\\a.jpg</item><item name="MD5">abc</item>
      <item name="SHA256"></item><item name="Tags">Image</item></metadata>
      <RelatedNodes><file id="f1r" size="0"><metadata section="File"><item name="Local Path">files/b</item></metadata></file></RelatedNodes>
    </file>
    <file id="f2" size="0"><accessInfo><timestamp name="ModifyTime" formattedTimestamp="x">2020-01-01T00:00:00+00:00</timestamp></accessInfo></file>
  </taggedFiles>
  <decodedData>
    <modelType type="Chat">
      <model type="Chat" id="c1" deleted_state="Intact">
        <field name="Name"><value type="String">  </value></field>
        <multiField name="Tags"><value type="String">a</value><value type="String">b</value></multiField>
        <multiModelField name="Messages">
          <model type="InstantMessage" id="m1"><field name="Body"><value type="String"><![CDATA[x < y]]></value></field>
            <modelField name="From"><model type="Party" id="p"><field name="Identifier"><value type="String">1</value></field></model></modelField>
          </model>
          <model type="InstantMessage" id="m1"><field name="Body"><value type="String">dup id</value></field>
            <field name="Body"><empty /></field></model>
        </multiModelField>
        <RelatedModels><model type="Chat" id="c1x" isrelated="True"><field name="Name"><value type="String">copy</value></field></model></RelatedModels>
      </model>
      <model type="Chat" id="c2"><field name="Name"><value type="String"></value></field></model>
    </modelType>
    <modelType type="Call"><model type="Call" id="k1"><jumptargets name=""><targetid ismodel="false">f1</targetid></jumptargets></model></modelType>
  </decodedData>
  <extraInfos>
    <extraInfo id="m1" type="Model"><sourceInfo><nodeInfo id="f1" name="db" path="/a/db" tableName="t" offset="1" size="2" /></sourceInfo></extraInfo>
    <extraInfo id="k1" type="Model"><sourceInfo><nodeInfos><nodeInfo id="f2" name="db2" path="/b" tableName="u" offset="3" size="4" /></nodeInfos></sourceInfo></extraInfo>
  </extraInfos>
  <x:foreign xmlns:x="urn:synthetic" x:attr="1">t</x:foreign>
</project>
""".replace("{ns}", NS)


class MemorySink:
    def __init__(self, flush_rows=3):
        self.rows = {"r": {}, "f": {}, "x": {}}
        self.pending = []
        self.flush_rows = flush_rows
        self.cursors = []

    def row(self, kind, row):
        self.pending.append((kind, row))

    def flush_due(self):
        return len(self.pending) >= self.flush_rows

    def flush(self, cursor):
        for kind, row in self.pending:
            assert row["ordinal"] not in self.rows[kind], "a row was written twice"
            self.rows[kind][row["ordinal"]] = row
        self.pending = []
        self.cursors.append(dict(cursor))

    def drop_above(self, cursor):
        for kind, key in (("r", "record_ordinal"), ("f", "file_ordinal"), ("x", "extra_ordinal")):
            for o in [o for o in self.rows[kind] if o > cursor[key]]:
                del self.rows[kind][o]

    def memory_rows(self, skeleton, parse_state="complete"):
        return MemoryRows(skeleton, {k: {o: (r.get("parent_ordinal"), r["body"]) for o, r in v.items()}
                                     for k, v in self.rows.items()}, parse_state)


def capture(xml, sink=None, cursor=None, chunk=None):
    sink = sink or MemorySink()
    data = xml.encode("utf-8") if isinstance(xml, str) else xml
    cap = Capture(sink, cursor=cursor)
    res = cap.run(io.BytesIO(data))
    return sink, res


def check_exact(xml):
    sink, res = capture(xml)
    data = xml.encode("utf-8")
    source = count_stream(io.BytesIO(data))
    captured = Recount(sink.memory_rows(res["skeleton"], res["parse_state"])).run()
    result, diffs = reconcile(source, captured)
    assert diffs == [] and result == "exact"
    assert captured["rows_unreached"] == 0
    return sink, res, source, captured


def test_report_captures_exactly_and_rows_follow_the_rules():
    sink, res, source, captured = check_exact(REPORT)
    records = sink.rows["r"]
    # every model is a record row, RelatedModels copies included (02 decision 39)
    assert sorted((o, r["model_type"], r["parent_ordinal"], r["depth"], r["top_ordinal"]) for o, r in records.items()) == [
        (1, "Chat", None, 0, 1), (2, "InstantMessage", 1, 1, 1), (3, "Party", 2, 2, 1), (4, "InstantMessage", 1, 1, 1),
        (5, "Chat", 1, 1, 1), (6, "Chat", None, 0, 6), (7, "Call", None, 0, 7)]
    assert source["totals"]["models_top"] == 3
    assert [records[o]["source_model_id"] for o in (2, 4)] == ["m1", "m1"]  # the Cellebrite id is not a key
    assert records[1]["deleted_state"] == "Intact"
    # nested records are markers inside the owner's body
    body = records[1]["body"]
    assert ["@", 2] in body[3][2][3] and ["@", 5] in body[3][3][3]
    # files: RelatedNodes child is a row of its own with its owner (decision D23)
    files = sink.rows["f"]
    assert sorted((o, r["source_file_id"], r["parent_ordinal"]) for o, r in files.items()) == [
        (1, "f1", None), (2, "f1r", 1), (3, "f2", None)]
    assert files[1]["local_path"] == "files\\Image\\a.jpg" and files[1]["declared_md5"] == "abc"
    assert files[1]["declared_sha256"] is None and files[1]["tags"] == "Image" and files[1]["declared_size"] == 3
    # extraInfos are rows (decision D24)
    assert sorted((o, r["source_id"]) for o, r in sink.rows["x"].items()) == [(1, "m1"), (2, "k1")]
    # skeleton spans: one per run of row children (decision D25)
    sk = res["skeleton"]
    flat = repr(sk)
    assert "['@r', 1, 6]" in flat and "['@r', 7, 7]" in flat and "['@f', 1, 3]" in flat and "['@x', 1, 2]" in flat
    assert res["parse_state"] == "complete" and res["counts"] == {"r": 7, "f": 3, "x": 2}


def test_whitespace_leaf_and_empty_leaf_are_kept_as_parsed():
    sink, res, *_ = check_exact(REPORT)
    name_field = sink.rows["r"][1]["body"][3][0]
    assert name_field[3][0][2] == "  "  # a leaf keeps whitespace-only text
    empty = sink.rows["r"][6]["body"][3][0][3][0]
    assert empty[2] is None


def test_foreign_namespace_stays_visible():
    sink, res, *_ = check_exact(REPORT)
    last = res["skeleton"][3][-1]
    assert last[0] == "{urn:synthetic}foreign" and last[1] == {"{urn:synthetic}attr": "1"}


def test_section_without_namespace_captures_exactly():
    xml = '<decodedData><modelType type="Note"><model type="Note" id="1"><field name="T"><value type="String">a</value></field></model></modelType></decodedData>'
    sink, res, *_ = check_exact(xml)
    assert res["root_element"] == "decodedData" and len(sink.rows["r"]) == 1


@pytest.mark.parametrize("flush_rows", [1, 2, 5, 1000])
def test_resume_from_every_cursor_gives_identical_rows(flush_rows):
    full_sink, full_res = capture(REPORT, MemorySink(flush_rows=1000))
    flushes = len(capture(REPORT, MemorySink(flush_rows=flush_rows))[0].cursors)
    for k in range(1, flushes + 1):
        # a kill after flush k: the rows of flushes 1..k are stored with cursor k
        stop = _StoppingSink(flush_rows, k)
        try:
            capture(REPORT, stop)
        except _Stop:
            pass
        cursor = stop.cursors[-1]
        stop.drop_above(cursor)  # decision D26
        _, res = capture(REPORT, stop, cursor=cursor)
        assert _rows(stop) == _rows(full_sink)
        assert res["skeleton"] == full_res["skeleton"]


class _Stop(Exception):
    pass


class _StoppingSink(MemorySink):
    def __init__(self, flush_rows, stop_after):
        super().__init__(flush_rows)
        self.stop_after = stop_after
        self.armed = True

    def flush(self, cursor):
        super().flush(cursor)
        if self.armed and len(self.cursors) >= self.stop_after:
            self.armed = False
            raise _Stop()


def _rows(sink):
    return {k: {o: (r["body"], r.get("parent_ordinal")) for o, r in v.items()} for k, v in sink.rows.items()}


def test_truncated_document_keeps_everything_read_and_reconciles():
    cut = REPORT.index("<item name=\"MD5\">")
    xml = REPORT[:cut + 10]
    sink, res = capture(xml)
    assert res["parse_state"] == "truncated"
    assert res["truncation"]["open_path"].startswith("project/taggedFiles/file/metadata[File]")
    assert sink.rows["f"][1]["is_partial"] is True
    source = count_stream(io.BytesIO(xml.encode()))
    assert source["document"]["parse_state"] == "truncated"
    captured = Recount(sink.memory_rows(res["skeleton"], "truncated")).run()
    assert reconcile(source, captured) == ("exact", [])


def test_the_budget_reads_memory_held_now_not_the_worker_process_high_water_mark(monkeypatch):
    """A long-lived worker whose earlier job peaked above the budget still reads a small report (10 Nov 2026)."""
    import resource
    import app.phone.capture as capture_mod
    real = resource.getrusage

    class Usage:
        def __init__(self, u):
            self._u = u
        def __getattr__(self, name):
            return (600 * 1024) if name == "ru_maxrss" else getattr(self._u, name)  # 600 MB high-water mark, in KiB
    monkeypatch.setattr(capture_mod.resource, "getrusage", lambda who: Usage(real(who)))
    res = Capture(MemorySink()).run(io.BytesIO(REPORT.encode()))
    assert res["parse_state"] == "complete"
    assert res["peak_rss"] < capture_mod.MEMORY_BUDGET_BYTES


def test_memory_budget_stops_with_the_stated_message():
    sink = MemorySink(flush_rows=1)
    with pytest.raises(CaptureMemoryBudgetExceeded) as e:
        Capture(sink, memory_budget=1).run(io.BytesIO(REPORT.encode()))
    assert "Nothing read so far is lost" in str(e.value)
    assert sink.cursors  # what was flushed stays


def _altered(fn):
    sink, res = capture(REPORT)
    source = count_stream(io.BytesIO(REPORT.encode()))
    fn(sink, res)
    return reconcile(source, Recount(sink.memory_rows(res["skeleton"])).run())


def test_one_deleted_value_is_named_by_path():
    def drop(sink, res):
        tags = sink.rows["r"][1]["body"][3][1]
        tags[3].pop()  # the second value of multiField[Tags]
    result, diffs = _altered(drop)
    assert result == "differs"
    paths = {(d["path"], d["measure"]) for d in diffs}
    p = "project/decodedData/modelType[Chat]/model[Chat]/multiField[Tags]/value"
    assert (p, "elements") in paths and (p, "text_hash") in paths and (p, "texts") in paths


def test_one_altered_attribute_is_named_by_path_and_attribute():
    def alter(sink, res):
        sink.rows["r"][7]["body"][1]["id"] = "k2"
    result, diffs = _altered(alter)
    assert diffs == [{"path": "project/decodedData/modelType[Call]/model[Call]", "measure": "attr_hash",
                      "attribute": "id", "source": diffs[0]["source"], "captured": diffs[0]["captured"]}]


def test_one_appended_element_is_named():
    def add(sink, res):
        sink.rows["r"][6]["body"][3].append(["field", {"name": "Extra"}, None, None])
    result, diffs = _altered(add)
    assert result == "differs"
    assert {d["path"] for d in diffs} == {"project/decodedData/modelType[Chat]/model[Chat]/field[Extra]"}


def test_a_stored_row_no_marker_reaches_is_a_difference():
    def orphan(sink, res):
        sink.rows["r"][99] = {"ordinal": 99, "parent_ordinal": 1, "body": ["model", {"type": "X"}, None, None]}
    result, diffs = _altered(orphan)
    assert result == "differs" and any(d["measure"] == "rows_unreached" for d in diffs)


def test_non_whitespace_tail_fails_reconciliation():
    xml = "<decodedData><a>t</a>tail<b/></decodedData>"
    sink, res = capture(xml)
    source = count_stream(io.BytesIO(xml.encode()))
    result, diffs = reconcile(source, Recount(sink.memory_rows(res["skeleton"])).run())
    assert result == "differs" and diffs[0]["measure"] == "bad_tails"


def test_an_accepted_difference_passes_only_when_the_differences_are_exactly_the_accepted_ones():
    """02 decision 37, 07 J-1: Accept the difference lets the capture continue past exactly those differences."""
    from app.phone.reconcile import is_accepted
    xml = "<decodedData><a>t</a>tail<b/></decodedData>"
    sink, res = capture(xml)
    source = count_stream(io.BytesIO(xml.encode()))
    result, diffs = reconcile(source, Recount(sink.memory_rows(res["skeleton"])).run())
    assert result == "differs"
    assert is_accepted({0: list(reversed(diffs))}, 0, diffs)
    assert not is_accepted({}, 0, diffs) and not is_accepted({1: diffs}, 0, diffs)
    assert not is_accepted({0: [dict(diffs[0], source=diffs[0]["source"] + 1)] + diffs[1:]}, 0, diffs)
