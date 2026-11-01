"""Unit tests for the element-level counters (01 unit 0.2), on synthetic XML only.

Every test runs both counters (lxml and expat) and requires identical output, then checks the measure
the case is about.
"""
import hashlib
import io
import unittest

from app.phone import counter, counter_expat
from app.phone.counts import compare, bad_tail_paths, h64

NS = "http://pa.cellebrite.com/report/2.0"

BASE = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<project xmlns="%s" reportVersion="7.48" NodeCount="1" ModelCount="2">\n'
    ' <metadata section="Extraction Data"><item name="UFED_PA_Version">7.59</item></metadata>\n'
    ' <taggedFiles><file id="f1"><metadata section="MetaData"><item name="Local Path">files/a.jpg</item>'
    '</metadata></file></taggedFiles>\n'
    ' <decodedData><modelType type="Chat">\n'
    '  <model type="Chat" id="1"><field name="Source"><value type="String">WhatsApp</value></field>\n'
    '   <multiModelField name="Messages"><model type="InstantMessage" id="2">'
    '<field name="Body"><value type="String">hello there</value></field>'
    '<field name="TimeStamp"><value type="TimeStamp" formattedTimestamp="x">2022-12-01T10:00:00.000+00:00</value></field>'
    '<field name="Empty"><value type="String">   </value></field>'
    '</model></multiModelField></model>\n'
    '  <model type="Chat" id="3"><field name="Source"><value type="String">Telegram</value></field></model>\n'
    ' </modelType></decodedData>\n'
    '</project>\n'
) % NS


def run(xml):
    data = xml.encode("utf-8") if isinstance(xml, str) else xml
    a = counter.count_stream(io.BytesIO(data))
    b = counter_expat.count_stream(io.BytesIO(data))
    return a, b, data


class BothCountersAgree(unittest.TestCase):
    def check(self, xml):
        a, b, data = run(xml)
        self.assertEqual(compare(a, b), [])
        self.assertEqual(a["totals"], b["totals"])
        self.assertEqual(a["paths"], b["paths"])
        self.assertEqual(a["document"]["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(a["document"]["md5"], hashlib.md5(data).hexdigest())
        self.assertEqual(a["document"]["sha256"], b["document"]["sha256"])
        return a

    def test_basic_counts_and_paths(self):
        r = self.check(BASE)
        t = r["totals"]
        self.assertEqual(t["models_top"], 2)
        self.assertEqual(t["models_nested"], 1)
        self.assertEqual(t["values"], 5)
        self.assertEqual(t["tagged_files"], 1)
        self.assertEqual(t["bad_tails"], 0)
        p = ("project/decodedData/modelType[Chat]/model[Chat]/multiModelField[Messages]/"
             "model[InstantMessage]/field[Body]/value")
        self.assertIn(p, r["paths"])
        self.assertEqual(r["paths"][p]["texts"], 1)
        self.assertEqual(r["paths"][p]["text_chars"], len("hello there"))
        self.assertEqual(r["paths"][p]["text_hash"], "%016x" % h64("hello there"))
        self.assertIn("project/taggedFiles/file/metadata[MetaData]/item[Local Path]", r["paths"])
        src = "project/decodedData/modelType[Chat]/model[Chat]/field[Source]/value"
        self.assertEqual(r["paths"][src]["elements"], 2)
        self.assertEqual(r["paths"][src]["texts"], 2)
        self.assertEqual(r["root_attributes"]["ModelCount"], "2")

    def test_whitespace_leaf_text_counts_but_whitespace_between_children_does_not(self):
        r = self.check(BASE)
        ws_leaf = ("project/decodedData/modelType[Chat]/model[Chat]/multiModelField[Messages]/"
                   "model[InstantMessage]/field[Empty]/value")
        self.assertEqual(r["paths"][ws_leaf]["texts"], 1)
        self.assertEqual(r["paths"][ws_leaf]["text_chars"], 3)
        self.assertEqual(r["paths"]["project"]["texts"], 0)
        self.assertEqual(r["paths"]["project/decodedData/modelType[Chat]"]["texts"], 0)

    def test_attribute_counts_and_hashes(self):
        r = self.check(BASE)
        ts = ("project/decodedData/modelType[Chat]/model[Chat]/multiModelField[Messages]/"
              "model[InstantMessage]/field[TimeStamp]/value")
        self.assertEqual(r["paths"][ts]["attributes"], {"formattedTimestamp": 1, "type": 1})
        self.assertEqual(r["paths"][ts]["attr_hash"]["type"], "%016x" % h64("TimeStamp"))

    def test_mixed_content_tail_is_counted(self):
        xml = ('<r><field name="A"><value>x</value>stray words<value>y</value></field>'
               '<b>t<c/>more</b></r>')
        r = self.check(xml)
        self.assertEqual(r["totals"]["bad_tails"], 2)
        self.assertEqual(r["paths"]["r/field[A]/value"]["bad_tails"], 1)
        self.assertEqual(r["paths"]["r/b/c"]["bad_tails"], 1)
        self.assertEqual(sorted(bad_tail_paths(r)), ["r/b/c", "r/field[A]/value"])
        # text before the first child is the element's text
        self.assertEqual(r["paths"]["r/b"]["texts"], 1)

    def test_foreign_namespace_counted_by_local_name(self):
        xml = ('<project xmlns="%s" xmlns:x="urn:other" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
               '<x:extra x:kind="k" xsi:nil="true">v</x:extra><extra kind="k">v</extra>'
               '<model type="T" xml:lang="en"/></project>') % NS
        r = self.check(xml)
        self.assertEqual(r["paths"]["project/extra"]["elements"], 2)
        self.assertEqual(r["paths"]["project/extra"]["attributes"], {"kind": 2, "nil": 1})
        self.assertEqual(r["paths"]["project/model[T]"]["attributes"], {"lang": 1, "type": 1})
        self.assertEqual(r["paths"]["project/extra"]["texts"], 2)

    def test_repeated_field_name_in_one_model(self):
        xml = ('<r><model type="M"><field name="Body"><value>a</value></field>'
               '<field name="Body"><value>b</value></field></model></r>')
        r = self.check(xml)
        p = "r/model[M]/field[Body]/value"
        self.assertEqual(r["paths"][p]["elements"], 2)
        self.assertEqual(r["paths"][p]["text_hash"], "%016x" % ((h64("a") + h64("b")) % (1 << 64)))

    def test_order_independent(self):
        one = '<r><model type="M"><f>a</f></model><model type="M"><f>b</f></model></r>'
        two = '<r><model type="M"><f>b</f></model><model type="M"><f>a</f></model></r>'
        a1, _, _ = run(one)
        a2, _, _ = run(two)
        self.assertEqual(a1["paths"], a2["paths"])
        self.assertEqual(compare(a1, a2), [])

    def test_stable_across_runs(self):
        a1, b1, _ = run(BASE)
        a2, b2, _ = run(BASE)
        self.assertEqual(a1, a2)
        self.assertEqual(b1, b2)

    def test_comment_and_processing_instruction(self):
        xml = '<r><?pi x?><a>t<!-- c -->after</a><b/><!-- d --></r>'
        r = self.check(xml)
        self.assertEqual(r["totals"]["comments"], 2)
        self.assertEqual(r["totals"]["processing_instructions"], 1)
        self.assertEqual(r["paths"]["r/a"]["texts"], 1)
        self.assertEqual(r["paths"]["r/a"]["text_chars"], 1)
        self.assertEqual(r["paths"]["r/a"]["bad_tails"], 1)

    def test_entities_cdata_and_non_bmp_text(self):
        xml = '<r><a>&amp;&lt;x&#x1D4D0;</a><b><![CDATA[<raw>]]></b><c> </c></r>'
        r = self.check(xml)
        self.assertEqual(r["paths"]["r/a"]["text_chars"], 4)
        self.assertEqual(r["paths"]["r/b"]["text_hash"], "%016x" % h64("<raw>"))
        # a no-break space is content, not whitespace
        self.assertEqual(r["totals"]["nonws_texts"], 3)

    def test_missing_naming_attribute(self):
        r = self.check('<r><model><field>v</field></model><metadata/></r>')
        self.assertIn("r/model/field", r["paths"])
        self.assertIn("r/metadata", r["paths"])


class OneValueChange(unittest.TestCase):
    def test_injected_attribute_change_is_found_by_both(self):
        changed = BASE.replace('id="3"', 'id="4"')
        for mod in (counter, counter_expat):
            a = mod.count_stream(io.BytesIO(BASE.encode()))
            b = mod.count_stream(io.BytesIO(changed.encode()))
            diffs = compare(a, b)
            self.assertEqual(len(diffs), 1, diffs)
            d = diffs[0]
            self.assertEqual(d["path"], "project/decodedData/modelType[Chat]/model[Chat]")
            self.assertEqual(d["measure"], "attr_hash")
            self.assertEqual(d["attribute"], "id")
            self.assertEqual(a["totals"], b["totals"])

    def test_injected_text_change_is_found_by_both(self):
        changed = BASE.replace("hello there", "hello thers")
        for mod in (counter, counter_expat):
            a = mod.count_stream(io.BytesIO(BASE.encode()))
            b = mod.count_stream(io.BytesIO(changed.encode()))
            diffs = compare(a, b)
            self.assertEqual([(d["measure"], d["attribute"]) for d in diffs], [("text_hash", None)])
            self.assertTrue(diffs[0]["path"].endswith("field[Body]/value"))

    def test_removed_value_changes_counts(self):
        changed = BASE.replace('<field name="Source"><value type="String">Telegram</value></field>',
                               '<field name="Source"></field>')
        a = counter.count_stream(io.BytesIO(BASE.encode()))
        b = counter.count_stream(io.BytesIO(changed.encode()))
        measures = {d["measure"] for d in compare(a, b)}
        self.assertTrue({"elements", "texts", "text_chars", "text_hash", "attributes", "attr_hash"} <= measures)


class Truncated(unittest.TestCase):
    def test_cut_off_document_reports_open_path_in_both(self):
        data = BASE.encode()
        cut = data[: data.index(b"Local Path") + 14]
        a = counter.count_stream(io.BytesIO(cut))
        b = counter_expat.count_stream(io.BytesIO(cut))
        for r in (a, b):
            self.assertEqual(r["document"]["parse_state"], "truncated")
            self.assertEqual(r["document"]["error"]["open_path"],
                             "project/taggedFiles/file/metadata[MetaData]/item[Local Path]")
            self.assertEqual(r["document"]["bytes"], len(cut))
            self.assertEqual(r["document"]["sha256"], hashlib.sha256(cut).hexdigest())
        self.assertEqual(a["totals"]["elements"], b["totals"]["elements"])
        self.assertEqual(a["totals"]["attributes"], b["totals"]["attributes"])
        self.assertEqual(compare(a, b), [])

    def test_complete_document_has_no_error(self):
        a, b, _ = run(BASE)
        self.assertEqual(a["document"]["parse_state"], "complete")
        self.assertIsNone(a["document"]["error"])
        self.assertIsNone(b["document"]["error"])


class FlatMemory(unittest.TestCase):
    def test_tree_does_not_grow_with_records(self):
        """The lxml walker removes finished siblings, so the parent holds at most one child."""
        from lxml import etree
        seen = []
        orig = counter._Walker.start

        def spy(self, el):
            orig(self, el)
            parent = el.getparent()
            if parent is not None:
                seen.append(len(parent))

        counter._Walker.start = spy
        chunk = counter.CHUNK
        counter.CHUNK = 256  # the parser builds ahead by at most one fed chunk
        try:
            body = "".join('<model type="M" id="%d"><f>v%d</f></model>' % (i, i) for i in range(5000))
            counter.count_stream(io.BytesIO(("<r><modelType type=\"M\">%s</modelType></r>" % body).encode()))
        finally:
            counter._Walker.start = orig
            counter.CHUNK = chunk
        self.assertLessEqual(max(seen), 12)
        self.assertIsNotNone(etree)


if __name__ == "__main__":
    unittest.main()
