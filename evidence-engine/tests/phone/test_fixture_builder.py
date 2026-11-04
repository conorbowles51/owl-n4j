"""Tests for the phone fixture builder (07 section 12.1 item A, 01 section 12, UXD-33)."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

try:  # run as package (pytest from evidence-engine) or as a plain module
    from . import fixture_builder as fb
except ImportError:  # pragma: no cover
    import fixture_builder as fb

NS = "{%s}" % fb.NS


def _tree_digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def _catalogue_union():
    fields, enums, types = set(), {}, set()
    for phone in fb.load_catalogue().values():
        types |= set(phone["model_types"])
        for mtype, fname, kind, vtypes in phone["catalog"]:
            for vtype in vtypes:
                fields.add((mtype, fname, kind, vtype))
        for name, values in phone.get("enums", {}).items():
            enums.setdefault(name, set()).update(values)
    return fields, enums, types


class BuilderShapes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="cbux-fx-")
        base = Path(cls.tmp.name)
        cls.po_dir, cls.tr_dir = base / "po", base / "tr"
        cls.po = fb.build_case(fb.phones_only_case(0.01), cls.po_dir)
        cls.tr = fb.build_case(fb.training_case(), cls.tr_dir)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def reports(self):
        for d, m in ((self.po_dir, self.po), (self.tr_dir, self.tr)):
            for phone in m["phones"]:
                yield phone, d / phone["label"] / "Report.xml"

    def test_deterministic(self):
        with tempfile.TemporaryDirectory(prefix="cbux-fx2-") as other:
            fb.build_case(fb.phones_only_case(0.01), Path(other))
            self.assertEqual(_tree_digest(self.po_dir), _tree_digest(Path(other)))

    def test_phones_only_has_no_ledger_and_three_phones(self):
        self.assertIsNone(self.po["ledger"])
        self.assertEqual([p["label"] for p in self.po["phones"]], ["C1", "C2", "C3"])
        self.assertFalse((self.po_dir / "ledger").exists())

    def test_training_has_two_phones_and_a_ledger_naming_phone_contacts(self):
        self.assertEqual(len(self.tr["phones"]), 2)
        rows = list(csv.DictReader(open(self.tr_dir / self.tr["ledger"]["file"])))
        self.assertEqual(len(rows), self.tr["ledger"]["rows"])
        self.assertGreater(len(rows), 20)
        ui = json.loads((self.tr_dir / "ui-fixture.json").read_text())
        names = {p["name"].upper() for p in ui["people"]}
        on_ledger = {r["Description"].split(" ", 2)[2] for r in rows}
        self.assertTrue(on_ledger & names, "some payees must be people on the phones (crossings)")
        # the two phones talk to each other: C6 lists C5's owner as a contact
        c6 = [t for t in ui["threads"] if t["phone"] == "C6"]
        self.assertTrue(any("p0" in t["participants"] for t in c6))

    def test_training_c5_carries_bank_alerts_for_some_of_its_ledger_payments_and_c6_none(self):
        """05 approach 1 on live: each alert on C5 states a ledger row's amount, direction and day and the
        statement's account ending, so money on the phone can be linked to its payment."""
        rows = list(csv.DictReader(open(self.tr_dir / self.tr["ledger"]["file"])))
        by_text = {(f"{abs(float(r['Amount'])):,.2f}", "sent to" if float(r["Amount"]) < 0 else "received from",
                    r["Date"]) for r in rows}
        xml = (self.tr_dir / "C5" / "Report.xml").read_text()
        alerts = re.findall(r"Synthetic Community Bank: account ending 0100, USD ([\d,.]+) (sent to|received from) "
                            r"[^<]*</value></field><field name=\"TimeStamp\"><value type=\"TimeStamp\"[^>]*>"
                            r"(\d{4})-(\d\d)-(\d\d)T10:00", xml)
        self.assertGreaterEqual(len(alerts), 10)
        for amount, way, y, m, d in alerts:
            self.assertIn((amount, way, f"{m}/{d}/{y}"), by_text)
        self.assertEqual(self.tr["phones"][0]["facts"]["bank_alerts"], len(alerts))
        self.assertNotIn("Synthetic Community Bank:", (self.tr_dir / "C6" / "Report.xml").read_text())
        # every other line of C5 is what it was without alerts, the report id included
        import dataclasses
        plain = fb.training_case()
        plain.phones[0] = dataclasses.replace(plain.phones[0], bank_alerts=False)
        with tempfile.TemporaryDirectory(prefix="cbux-fx5-") as out:
            fb.build_case(plain, Path(out))
            before = (Path(out) / "C5" / "Report.xml").read_text().splitlines()
        after = xml.splitlines()
        removed = [ln for ln in before if ln not in set(after)]
        self.assertEqual(len(removed), 1)  # the header line: its model count grows by the alerts
        self.assertIn('ModelCount="%d"' % (int(re.search(r'ModelCount="(\d+)"', removed[0]).group(1)) + len(alerts)),
                      after[1])
        self.assertEqual(re.search(r'<project id="([^"]+)"', removed[0]).group(1),
                         re.search(r'<project id="([^"]+)"', after[1]).group(1))

    def test_training_ledger_is_also_monthly_single_page_pdf_statements_with_every_row(self):
        """The ledger goes through Loupe's real Financial intake, which reads PDF statements (item I)."""
        rows = list(csv.DictReader(open(self.tr_dir / self.tr["ledger"]["file"])))
        printed, closing = [], None
        for name in self.tr["ledger"]["pdfs"]:
            pdf = (self.tr_dir / name).read_bytes()
            self.assertTrue(pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF"))
            self.assertEqual(pdf.count(b"/Type /Page "), 1, name)
            dates = re.findall(rb"\((\d{4}-\d\d-\d\d)\) Tj", pdf)[1:-1]  # between the opening and closing rows
            printed += [d.decode() for d in dates]
            balances = re.findall(rb"Tm \((-?\d+\.\d\d)\) Tj", pdf)
            if closing is not None:  # each month opens at the previous month's closing balance
                self.assertEqual(balances[0].decode(), closing, name)
            closing = balances[-1].decode()
            for word in (b"Opening Balance", b"Closing Balance", b"Account Number", b"Statement Period", b"Currency: USD",
                         fb.SYNTHETIC_MARK.encode()):
                self.assertIn(word, pdf)
        self.assertEqual(printed, ["{2}-{0}-{1}".format(*r["Date"].split("/")) for r in rows])

    def test_failure_states_present(self):
        c2 = self.po["phones"][1]
        self.assertFalse(c2["owner_number_in_report"])  # J-1 / J-2 owner unknown
        self.assertIsNone(c2["zone"])  # J-2 zone unknown
        root = ET.parse(self.po_dir / "C2" / "Report.xml").getroot()
        self.assertIsNone(root.find(f"{NS}projectConfigurations"))
        c1 = self.po["phones"][0]
        self.assertGreater(c1["facts"].get("messages_no_time", 0), 0)  # J-4
        self.assertIsNotNone(c1["no_data_days"])  # J-4 "No data" bands
        total_missing = sum(p["facts"].get("attachments_missing", 0) for p in self.tr["phones"])
        self.assertGreater(total_missing, 0)  # "3 not in the report"

    def test_counts_in_xml_equal_manifest(self):
        for phone, path in self.reports():
            root = ET.parse(path).getroot()
            decoded = root.find(f"{NS}decodedData")
            top = {}
            for mt in decoded:
                top[mt.get("type")] = len(mt.findall(f"{NS}model"))
            self.assertEqual({k: v for k, v in top.items() if v}, phone["top_level"], phone["label"])
            self.assertEqual(int(root.get("ModelCount")), phone["top_level_total"])
            nested = {}
            for mt in decoded:
                for m in mt.findall(f"{NS}model"):
                    for sub in m.iter(f"{NS}model"):
                        if sub is not m:
                            nested[sub.get("type")] = nested.get(sub.get("type"), 0) + 1
            self.assertEqual(nested, phone["nested"], phone["label"])
            files = root.find(f"{NS}taggedFiles").findall(f"{NS}file")
            self.assertEqual(len(files), phone["files"])
            for f in files:
                local = f.find(f"{NS}metadata/{NS}item[@name='Local Path']").text.replace("\\", "/")
                data = (path.parent / local).read_bytes()
                sha = f.find(f"{NS}metadata/{NS}item[@name='SHA256']").text
                self.assertEqual(hashlib.sha256(data).hexdigest(), sha)

    def test_structure_only_uses_catalogue_names_kinds_and_values(self):
        fields, enums, types = _catalogue_union()
        for phone, path in self.reports():
            root = ET.parse(path).getroot()
            for model in root.iter(f"{NS}model"):
                mtype = model.get("type")
                self.assertIn(mtype, types)
                self.assertIn(model.get("deleted_state"), {"Intact", "Deleted", "Trash", "Unknown"})
                for child in model:
                    tag = child.tag.replace(NS, "")
                    if tag not in ("field", "multiField"):
                        continue
                    for v in child.findall(f"{NS}value"):
                        key = (mtype, child.get("name"), tag, v.get("type"))
                        self.assertIn(key, fields, f"{phone['label']}: {key} not in the catalogue")
                        if v.get("type") in enums:
                            self.assertIn(v.text, enums[v.get("type")], key)

    def test_named_set_fields_hold_only_vocabulary(self):
        # a free-text value in a named-set field reaches the global registry as vocabulary (499 on live, 4 Nov 2026)
        plain = {"String", "TimeStamp", "TimeSpan", "Guid", "Boolean", "Int32", "Int64", "Double", "UInt32"}
        seen = set()
        for _, report in self.reports():
            for m in re.finditer(r'<value type="([^"]+)"[^>]*>(?:<!\[CDATA\[)?([^<\]]*)', report.read_text("utf-8")):
                if m.group(1) not in plain:
                    seen.add(m.group(1))
                    self.assertFalse(m.group(2).startswith("synthetic "), m.group(0))
        self.assertIn("DecodingSourceOptions", seen)

    def test_invented_values_only(self):
        number = re.compile(r"\+1\d{3}5550[01]\d\d")
        allowed_names = set(fb.FIRST) | set(fb.LAST)
        for d in (self.po_dir, self.tr_dir):
            ui = json.loads((d / "ui-fixture.json").read_text())
            for p in ui["people"]:
                first, last = p["name"].split(" ")
                self.assertTrue({first, last} <= allowed_names)
                for n in p["numbers"]:
                    self.assertRegex(n, number)
                self.assertRegex(p["email"], r"@example\.(com|org|net)$")
        for phone, path in self.reports():
            text = path.read_text()
            for found in re.findall(r"\+1\d{10}", text):
                self.assertRegex(found, number)
            for found in re.findall(r"[\w.]+@[\w.]+\.\w+", text):
                self.assertRegex(found, r"(@example\.(com|org|net)|@s\.whatsapp\.net)$")
            self.assertIn(fb.SYNTHETIC_MARK, text)

    def test_element_counter_reads_every_fixture_whole(self):
        try:
            from app.phone.counter import count_file
        except ImportError as exc:  # lxml missing outside the engine environment
            self.skipTest(f"element counter not importable here: {exc}")
        for phone, path in self.reports():
            r = count_file(str(path))
            self.assertEqual(r["document"]["parse_state"], "complete")
            self.assertEqual(r["totals"]["models_top"], phone["top_level_total"])
            self.assertEqual(r["totals"]["tagged_files"], phone["files"])
            self.assertEqual(r["totals"]["bad_tails"], 0)

    def test_ui_fixture_agrees_with_manifest(self):
        for d, m in ((self.po_dir, self.po), (self.tr_dir, self.tr)):
            ui = json.loads((d / "ui-fixture.json").read_text())
            for phone in m["phones"]:
                msgs = [x for x in ui["messages"] if x["phone"] == phone["label"]]
                self.assertEqual(len(msgs), phone["facts"]["messages"])
                threads = [t for t in ui["threads"] if t["phone"] == phone["label"]]
                self.assertEqual(sum(t["count"] for t in threads), len(msgs))
                self.assertEqual(phone["nested"].get("InstantMessage", 0), len(msgs))


class FrontendFixtures(unittest.TestCase):
    """The kit stories and the prototype read the builder's ui-fixture.json, committed under frontend_v2.
    Regenerating gives the same bytes, so the screens never drift from the builder."""

    def test_committed_ui_fixtures_equal_the_builder(self):
        target = fb.REPO / "frontend_v2" / "src" / "features" / "phones" / "fixtures"
        for name, case in (("training.json", fb.training_case()), ("phones-only.json", fb.phones_only_case(0.02))):
            with tempfile.TemporaryDirectory(prefix="cbux-fx4-") as out:
                fb.build_case(case, Path(out))
                self.assertEqual((Path(out) / "ui-fixture.json").read_text(), (target / name).read_text(), name)


class RealScale(unittest.TestCase):
    def test_scale_one_follows_catalogue_counts(self):
        """At scale 1.0 every top-level type the builder writes matches the catalogue phone's count."""
        cat = fb.load_catalogue()["P09"]["model_types"]
        with tempfile.TemporaryDirectory(prefix="cbux-fx3-") as out:
            people = fb.invent_people(40, seed=31)
            case = fb.CaseSpec("scale", people, [fb.PhoneSpec("S1", like="P09", scale=1.0,
                                                             contacts=[p.key for p in people[1:]])])
            m = fb.build_case(case, Path(out))
        phone = m["phones"][0]
        self.assertEqual(phone["facts"]["messages"] - phone["facts"].get("messages_no_time", 0), cat["InstantMessage"])
        for mtype, n in phone["top_level"].items():
            if mtype in ("Contact",):
                continue
            self.assertEqual(n, cat[mtype], mtype)


if __name__ == "__main__":
    unittest.main()


def test_a_newer_report_of_c1_keeps_every_record_and_adds_three_later_messages(tmp_path):
    """07 J-13b: the Replace fixture. The newer C1 report is the original, record for record, plus 3 messages in
    its busiest thread dated after the original extraction, which moves 10 days later."""
    import json
    fb.main(["phones-only", str(tmp_path / "a")])
    fb.main(["c1-later", str(tmp_path / "b")])
    a = json.loads((tmp_path / "a" / "ui-fixture.json").read_text())
    b = json.loads((tmp_path / "b" / "ui-fixture.json").read_text())
    old_threads = [t for t in a["threads"] if t["phone"] == "C1"]
    new_threads = b["threads"]
    assert [t["id"] for t in old_threads] == [t["id"] for t in new_threads]
    assert new_threads[0]["count"] == old_threads[0]["count"] + 3 and new_threads[1:] == old_threads[1:]
    old_msgs = [json.dumps(m, sort_keys=True) for m in a["messages"] if m.get("phone", "C1") == "C1"]
    new_msgs = [json.dumps(m, sort_keys=True) for m in b["messages"]]
    assert len(new_msgs) == len(old_msgs) + 3 and set(old_msgs) <= set(new_msgs)
    old_c1 = next(p for p in a["phones"] if p["label"] == "C1")
    assert b["phones"][0]["extraction_date"] > old_c1["extraction_date"]
    assert b["phones"][0]["period_end"] == old_c1["period_end"]



class TypedValuesTest(unittest.TestCase):
    def test_typed_values_are_written_last_and_change_nothing_else(self):
        """cb-vocab: a phone with extra invented typed and searched values holds them, and every other record is
        the one the same phone has without them."""
        people = fb.invent_people(10, seed=31)
        base = dict(like="P09", scale=0.01, contacts=[p.key for p in people[1:]], seed=301)
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            fb.build_case(fb.CaseSpec("Synthetic", people, [fb.PhoneSpec("V1", **base)]), out / "a")
            fb.build_case(fb.CaseSpec("Synthetic", people, [fb.PhoneSpec("V1", typed_values=(
                ("Autofill", "Value", "893.33"), ("DictionaryWord", "Word", "corvane")), **base)]), out / "b")
            a = (out / "a" / "V1" / "Report.xml").read_text()
            b = (out / "b" / "V1" / "Report.xml").read_text()
        self.assertIn("893.33", b)
        self.assertIn("corvane", b)
        self.assertNotIn("corvane", a)
        ma, mb = re.findall(r"<model [^>]*>", a), re.findall(r"<model [^>]*>", b)
        self.assertEqual(len(mb), len(ma) + 2)
        self.assertTrue(set(ma) <= set(mb))
