"""Tests for the demo case (lx-demo B): every answer-key entry is carried by the built bytes, every value is invented,
and every invented name was checked against the live cases and the map before loading."""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import re
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

try:
    from . import demo_case as dc
    from . import fixture_builder as fb
except ImportError:  # pragma: no cover
    import demo_case as dc
    import fixture_builder as fb

HERE = Path(__file__).resolve().parent
KEY = json.loads((HERE / "planted-truths.json").read_text())
NAME_CHECK = json.loads((HERE / "demo-name-check.json").read_text())
MODULES = {"phones", "pattern_of_life", "media", "identities", "timeline", "graph", "financial", "documents", "search",
           "workspace", "deadlines", "theories", "dossiers", "profiles", "interviews", "transcripts", "agent"}


def _pdf_text(data: bytes) -> str:
    """The text a reader sees: every shown string of the builder's PDFs, unescaped, joined by spaces."""
    runs = re.findall(rb"\(((?:\\.|[^\\)])*)\) Tj", data)
    return " ".join(re.sub(rb"\\(.)", rb"\1", r).decode("cp1252") for r in runs)


def _text(path: Path) -> str:
    if path.suffix == ".pdf":
        return _pdf_text(path.read_bytes())
    if path.suffix == ".docx":
        with zipfile.ZipFile(path) as zf:
            return " ".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", zf.read("word/document.xml").decode()))
    return path.read_text(encoding="utf-8")


def _digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


class DemoCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="lx-demo-")
        cls.out = Path(cls.tmp.name) / "a"
        cls.manifest = dc.build_demo(cls.out, voice=False)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def found(self, rel: str, text: str) -> bool:
        path = self.out / rel
        body = _text(path)
        if path.suffix == ".xml":
            return escape(text) in body
        return text in body

    def test_the_answer_key_covers_every_module_with_at_least_30_entries(self):
        entries = KEY["entries"]
        self.assertGreaterEqual(len(entries), 30)
        self.assertEqual(len({e["id"] for e in entries}), len(entries))
        seen = set().union(*(e["modules"] for e in entries))
        self.assertTrue(MODULES <= seen, MODULES - seen)
        decoys = [e for e in entries if e["kind"] == "decoy"]
        self.assertGreaterEqual(len(decoys), 4)
        for e in decoys + [e for e in entries if e["kind"] == "trap"]:
            self.assertEqual(e["strength"] in ("none", "weak", "strong"), True, e["id"])
        self.assertGreaterEqual(len(KEY["agent_questions"]), 8)

    def test_every_answer_key_entry_is_carried_by_the_built_bytes(self):
        for e in KEY["entries"]:
            if e.get("needs") == "voice" and not self.manifest["voice_note_made"]:
                continue  # built without ffmpeg's voice here; test_the_voice_note_is_built covers it
            for c in e.get("carriers", []):
                with self.subTest(entry=e["id"], file=c["file"]):
                    self.assertTrue(self.found(c["file"], c["text"]), f"{e['id']}: {c['text']!r} not in {c['file']}")
            for c in e.get("absent", []):
                with self.subTest(entry=e["id"], absent=c["text"]):
                    self.assertFalse(self.found(c["file"], c["text"]), f"{e['id']}: {c['text']!r} is in {c['file']}")

    def test_every_name_or_number_an_agent_answer_must_give_is_in_the_case(self):
        # an expected word no file carries can never be found: the key, not the product, would be wrong
        corpus = " ".join(_text(p) for p in self.out.rglob("*")
                          if p.is_file() and p.suffix in (".xml", ".pdf", ".docx", ".csv", ".txt"))
        for q in KEY["agent_questions"]:
            for word in q["expect"]:
                if re.search(r"[A-Z0-9]", word):
                    with self.subTest(question=q["id"], word=word):
                        self.assertIn(word, corpus, f"{q['id']} expects {word!r}, which no file of the case carries")

    def test_photo_labels_and_received_photos_are_as_the_key_says(self):
        self.assertTrue(self.manifest["photos_made"])
        f20 = next(e for e in KEY["entries"] if e["id"] == "F20")
        for rel, labels in f20["image_text"].items():
            self.assertTrue((self.out / "phones" / rel.split("phones/", 1)[1]).exists())
            self.assertEqual(labels, dc.PHOTO_SERIALS[Path(rel).name])
        losses = {s for night in dc.LOSSES for _, s in dc.serials(night)}
        self.assertTrue(all(s in losses for labels in dc.PHOTO_SERIALS.values() for s in labels))
        self.assertTrue(all(s in losses for s in dc.LISTED_SERIALS))
        self.assertFalse(any(s in losses for _, s in dc.GARAGE_TOOLS))
        ph5 = (self.out / "phones" / "PH5" / "Report.xml").read_text()
        own = re.findall(r'path="/storage/emulated/0/DCIM/Camera/[^"]+"', ph5)
        self.assertEqual(len(own), 4)
        self.assertEqual(ph5.count("Media Locations"), 6)
        self.assertEqual(ph5.count('<item name="EXIFCameraModel">Phone PH2</item>'), 2)

    def test_kells_phone_has_no_record_inside_any_theft_night_gap(self):
        text = (self.out / "phones" / "PH2" / "Report.xml").read_text()
        stamps = [dt.datetime.strptime(t[:19], "%Y-%m-%dT%H:%M:%S") for t in re.findall(r'<value type="TimeStamp"[^>]*>([^<]+)<', text)]
        self.assertGreater(len(stamps), 400)
        for label, day in dc.NIGHTS:
            a, b = dc._night_gap(day)
            self.assertEqual(b - a, dt.timedelta(hours=5))
            self.assertEqual([t for t in stamps if a <= t < b], [], label)
            self.assertTrue(any(a - dt.timedelta(hours=1) <= t < a for t in stamps), label)  # data up to the gap

    def test_the_glovebox_phone_is_with_kells_phone_on_14_of_16_evenings(self):
        ph3 = (self.out / "phones" / "PH3" / "Report.xml").read_text()
        days = set()
        for t, lat in re.findall(r'<value type="TimeStamp"[^>]*>([^<]+)<.{0,600}?"Latitude"><value type="Double">([\d.]+)<', ph3):
            when = dt.datetime.strptime(t[:19], "%Y-%m-%dT%H:%M:%S")
            if abs(float(lat) - dc.KELL_APT[0]) < 0.0002 and dt.datetime(2024, 5, 23) <= when < dt.datetime(2024, 6, 9):
                days.add((when - dt.timedelta(hours=4)).date())
        self.assertEqual(len(days), 14)
        self.assertNotIn(dt.date(2024, 5, 27), days)

    def test_values_are_invented(self):
        phone = re.compile(r"\+1\d{3}5550[01]\d\d")
        dashed = re.compile(r"\b\d{3}-555-01\d\d\b")
        for path in self.out.rglob("*"):
            if not path.is_file() or path.suffix.lower() in (".jpg", ".png", ".opus"):
                continue
            body = _text(path) if path.suffix in (".pdf", ".docx", ".xml", ".csv", ".eml") else ""
            with self.subTest(file=str(path.relative_to(self.out))):
                for n in re.findall(r"\+1\d{10}", body):
                    self.assertRegex(n, phone)
                for n in re.findall(r"\b\d{3}-\d{3}-\d{4}\b", body):
                    self.assertRegex(n, dashed)
                for m in re.findall(r"[\w.+-]+@[\w.-]+\.\w+", body):
                    self.assertRegex(m, r"(@([\w-]+\.)?example\.(com|org|net)|@s\.whatsapp\.net)$")
        for p in dc.PEOPLE:
            self.assertRegex(p.email, r"@([\w-]+\.)?example\.(com|org|net)$")

    def test_every_document_and_statement_page_carries_the_banner(self):
        for path in list((self.out / "documents").rglob("*")) + list((self.out / "statements").rglob("*")):
            if path.suffix == ".pdf":
                data = path.read_bytes()
                pages = len(re.findall(rb"/Type /Page ", data))
                self.assertEqual(_pdf_text(data).count(dc.BANNER), pages, path.name)
            elif path.suffix in (".csv", ".eml", ".docx"):
                self.assertIn(dc.BANNER, _text(path) if path.suffix != ".docx" else _text(path), path.name)
        for path in (self.out / "phones").glob("PH*/Report.xml"):
            self.assertIn(fb.SYNTHETIC_MARK, path.read_text())

    def test_statements_balance_except_the_planted_missing_page(self):
        for key, acc in dc.ACCOUNTS.items():
            for rel in self.manifest["ledgers"][key]["files"]:
                text = _text(self.out / rel)
                with self.subTest(file=rel):
                    if rel.endswith("kell-2024-05.pdf"):
                        self.assertIn("Page 1 of 2", text)
                        self.assertNotIn("Closing Balance", text)
                    else:
                        self.assertIn("Closing Balance", text)
        march = _text(self.out / "statements/kell/kell-2024-03.pdf")
        self.assertNotIn(dc.MISREAD_AMOUNT, march)  # printed in two pieces
        self.assertIn("800.00", march)
        a = (self.out / "statements/kell/kell-2024-04.pdf").read_bytes()
        b = (self.out / "statements/state-exhibits/states-exhibit-14-kell-april-2024.pdf").read_bytes()
        self.assertNotEqual(a, b)
        self.assertEqual(_pdf_text(a).replace(dc.BANNER, ""), _pdf_text(b).replace(dc.BANNER + "   STATE'S EXHIBIT 14", ""))
        with (self.out / "statements/penn/penn-used-tools-old-ferrow-2024.csv").open() as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(rows[2], ["Date", "Description", "Amount", "Balance"])

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg absent: the demo is built without its voice note")
    def test_the_voice_note_is_built_and_attached_to_okafors_message(self):
        note = dc._voice_note()
        self.assertTrue(note and note[:4] == b"OggS")
        spec = dc.okafor_phone(note)
        with tempfile.TemporaryDirectory() as d:
            fb.build_case(fb.CaseSpec("v", dc.PEOPLE, [spec]), Path(d))
            text = (Path(d) / "PH4" / "Report.xml").read_text()
            self.assertEqual((Path(d) / "PH4" / "files" / "Audio" / "PTT-20240609-0001.opus").read_bytes(), note)
        self.assertIn("PTT-20240609-0001.opus", text)

    def test_deterministic(self):
        other = Path(self.tmp.name) / "b"
        dc.build_demo(other, voice=False)
        self.assertEqual(_digest(self.out), _digest(other))

    def test_every_invented_name_was_checked_and_had_no_hit(self):
        checked = {row["name"]: row for row in NAME_CHECK["names"]}
        names = set(dc.INVENTED_NAMES) | set(dc.INVENTED_PLACES)
        self.assertEqual(names - set(checked), set(), "names added since the live check: re-run it (docs/demo-case.md)")
        for name in names:
            row = checked[name]
            self.assertEqual((row["live_case_hits"], row["map_hits"]), (0, 0), name)

    def test_the_older_fixtures_are_unchanged_by_the_demo_options(self):
        with tempfile.TemporaryDirectory() as d:
            m = fb.build_case(fb.check_seed_case(), Path(d))
            text = (Path(d) / "C7" / "Report.xml").read_text()
        self.assertNotIn("Media Locations", text)
        self.assertEqual(m["phones"][0]["facts"].get("script_messages"), None)
        self.assertIn('extractionType="FileSystem"', text)


if __name__ == "__main__":
    unittest.main()
