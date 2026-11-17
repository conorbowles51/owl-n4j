"""lx-relevancetest A: the second invented case builds deterministically, carries every answer-key string and every
judged record of its relevance set, holds only invented values, and shares no name with the demo case."""
from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "phone"))
import second_case as sc  # noqa: E402
import demo_case as dc  # noqa: E402
from test_demo_case import _text  # noqa: E402
from test_relevance_sets import norm  # noqa: E402

KEY = json.loads((HERE / "second-truths.json").read_text())
SET = json.loads((HERE / "second-relevance-set.json").read_text())


def _digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.name.endswith("manifest.json"):
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


class SecondCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="lx-second-")
        cls.out = Path(cls.tmp.name) / "a"
        sc.build_second(cls.out)
        cls.texts = {str(p.relative_to(cls.out)): html.unescape(_text(p)) for p in cls.out.rglob("*")
                     if p.is_file() and p.suffix in (".pdf", ".docx", ".xml", ".csv")}
        cls.corpus = norm("\n".join(list(cls.texts) + list(cls.texts.values())))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_answer_key_carrier_is_in_its_file(self):
        missing = [(e["id"], c["file"]) for e in KEY["entries"] for c in e["carriers"]
                   if c["text"] not in self.texts.get(c["file"], "")]
        self.assertEqual(missing, [])

    def test_every_judged_record_of_the_word_kinds_is_in_the_bytes(self):
        missing = []
        for q in SET["queries"]:
            if q["kind"] not in {"phones", "documents", "exact", "ledger"}:
                continue
            for item in (q.get("relevant") or []) + (q.get("decoys") or []):
                anys, alls = item.get("any") or [], item.get("all") or []
                if not ((not anys or any(norm(a) in self.corpus for a in anys)) and
                        all(norm(a) in self.corpus for a in alls)):
                    missing.append((q["id"], item["id"]))
        self.assertEqual(missing, [])

    def test_the_refunds_add_up_to_the_complaint(self):
        self.assertEqual(round(sum(r[4] for r in sc.REFUNDS), 2), 18640.00)
        self.assertIn("$18,640.00", self.texts["documents/complaint-letter-brackley-2024-05-02.pdf"])

    def test_values_are_invented_and_names_are_not_the_demo_cases(self):
        numbers = set(re.findall(r"\+1\d{10}", " ".join(self.texts.values())))
        self.assertTrue(numbers and all(n[5:8] == "555" and n[8:10] == "02" for n in numbers
                                         if n[2:5] == "717"), numbers)
        demo = {n.lower() for n in dc.INVENTED_NAMES + dc.INVENTED_PLACES}
        self.assertEqual({n.lower() for n in sc.INVENTED_NAMES + sc.INVENTED_PLACES} & demo, set())

    def test_every_document_and_statement_page_carries_the_banner(self):
        for rel, text in self.texts.items():
            if rel.endswith((".pdf", ".docx")):
                self.assertIn(sc.BANNER, text, rel)

    def test_deterministic(self):
        again = Path(self.tmp.name) / "b"
        sc.build_second(again)
        self.assertEqual(_digest(self.out), _digest(again))


if __name__ == "__main__":
    unittest.main()
