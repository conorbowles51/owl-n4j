"""lx-relevancetest A: every judged record of the demo relevance set is carried by the demo case's built bytes, so a
search that misses it misses something that is there. Records of the graph, timeline and casework kinds come from
entity extraction and the seeded workspace, not straight from the bytes; they are checked by the live runs."""
from __future__ import annotations

import html
import json
import re
import sys
import tempfile
import unittest
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "phone"))
import demo_case as dc  # noqa: E402
from test_demo_case import _text  # noqa: E402

BYTES_KINDS = {"phones", "documents", "exact", "ledger"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).translate(str.maketrans({"‘": "'", "’": "'", "“": '"',
                                                                  "”": '"'}))
    return re.sub(r"\s+", " ", s.lower())


class DemoRelevanceSet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="lx-relevance-")
        out = Path(cls.tmp.name) / "a"
        dc.build_demo(out, voice=False)
        parts = []
        for p in sorted(out.rglob("*")):
            if p.is_file() and p.suffix in (".pdf", ".docx", ".xml", ".csv", ".eml", ".txt"):
                parts.append(p.name)
                parts.append(html.unescape(_text(p)))
        cls.corpus = norm("\n".join(parts))
        cls.set = json.loads((HERE / "demo-relevance-set.json").read_text())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def carried(self, item: dict) -> bool:
        anys, alls = item.get("any") or [], item.get("all") or []
        return (not anys or any(norm(a) in self.corpus for a in anys)) and all(norm(a) in self.corpus for a in alls)

    def test_every_judged_record_and_decoy_is_in_the_bytes(self):
        missing = []
        for q in self.set["queries"]:
            if q["kind"] not in BYTES_KINDS:
                continue
            for item in (q.get("relevant") or []) + (q.get("decoys") or []):
                if not self.carried(item):
                    missing.append((q["id"], item["id"]))
        self.assertEqual(missing, [])

    def test_every_query_names_answer_key_entries_that_exist(self):
        key = json.loads((HERE.parent / "phone" / "planted-truths.json").read_text())
        ids = {e["id"] for e in key["entries"]}
        for q in self.set["queries"]:
            self.assertTrue(q["key"] and set(q["key"]) <= ids, q["id"])

    def test_queries_are_not_the_records_own_words(self):
        """Most queries are typed as a person would ask, so the set measures search, not substring lookup: at most
        a quarter of the word-search queries contain a judged record's text."""
        word = [q for q in self.set["queries"] if q["kind"] in {"phones", "documents"}]
        verbatim = [q["id"] for q in word if any(norm(a) in norm(json.dumps(q["args"])) for item in q["relevant"]
                                                 for a in item.get("any") or [])]
        self.assertLessEqual(len(verbatim), len(word) // 4, verbatim)


if __name__ == "__main__":
    unittest.main()
