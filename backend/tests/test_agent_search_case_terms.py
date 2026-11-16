"""lx-agentquick E: search_case finds the messages holding the query's terms, best first, whole with their thread
window, and a zero says why and what to try (fails on the code before: a sentence matched as one substring)."""
import unittest
from unittest.mock import patch

from services.agent import phone_cross_tools as PC
from services.phone import chat_retrieval as R
from services.search import search as S


def _window(n, terms):
    return {"id": "phone:%d" % n, "text": "Kell: the trailer is at the yard [rec://u%d]\nMateo: ok" % n, "distance": 0.4,
            "metadata": {"doc_name": "Phone 2 thread %d" % n, "record_uid": "u%d" % n, "extraction_id": "x1",
                         "first_record_uid": "u%d" % n, "last_record_uid": "u%d" % n, "matched_terms": terms}}


def _empty_search(conn, case_id, query, **k):
    return {"groups": [], "complete": True, "limits": [], "not_searched": []}


class SearchCaseTerms(unittest.TestCase):
    def _call(self, query, found, total, **kw):
        def windows(conn, case, q, *, max_windows, total_out=None, extraction_ids=None):
            self.seen = (q, max_windows)
            if total_out is not None:
                total_out.append(total)
            return found[:max_windows]
        with patch.object(R, "windows", windows), patch.object(S, "search", _empty_search), \
                patch.object(PC, "_phone_ids", lambda conn, case, phones: ([], [])):
            return PC.search_case.__wrapped__(None, "c", query, **kw)

    def test_a_sentence_finds_messages_by_its_terms_with_the_whole_window(self):
        out = self._call("where did Kell leave the trailer", [_window(1, ["kell", "trailer"]), _window(2, ["trailer"])], 2)
        self.assertEqual(out["total_matching"], 2)
        item = out["items"][0]
        self.assertEqual(item["group"], "message_windows")
        self.assertIn("the trailer is at the yard", item["text"])
        self.assertIn("Mateo: ok", item["text"])  # the thread window, not a snippet
        self.assertEqual(item["matched_terms"], ["kell", "trailer"])
        self.assertEqual(item["rec"], PC._rec("u1"))

    def test_the_group_pages(self):
        out = self._call("kell trailer", [_window(i, ["kell"]) for i in range(5)], 5, group="message_windows", limit=2, offset=2)
        self.assertEqual(out["returned"], 2)
        self.assertEqual(out["groups"][0]["total"], 5)
        self.assertEqual(out["groups"][0]["next_offset"], 4)

    def test_a_zero_says_what_was_searched_and_what_to_try(self):
        out = self._call("brightwater trailer", [], 0)
        self.assertEqual(out["total_matching"], 0)
        self.assertIn("brightwater", out["limitation"])
        self.assertIn("Try single words", out["limitation"])
        self.assertIn("not proof of absence", out["limitation"])

    def test_a_date_range_skips_the_window_search_and_says_so(self):
        out = self._call("kell trailer", [_window(1, ["kell"])], 1, start="2024-03-01")
        self.assertEqual(out["total_matching"], 0)
        self.assertIn("date range", out["limitation"])


if __name__ == "__main__":
    unittest.main()
