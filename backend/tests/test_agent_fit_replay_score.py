"""The demo key's expected-word match (scripts/financial_agent_fit_replay.py expect_hit) passes the cases the live
journey's scorer passes (frontend_v2/journeys/demo-key-score-cases.json; demo-key-score.test.mjs runs them in node)."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "scripts"))
import financial_agent_fit_replay as replay  # noqa: E402

SHARED = json.loads((ROOT / "frontend_v2" / "journeys" / "demo-key-score-cases.json").read_text())
CASES = SHARED["cases"]
Q1 = {"id": "Q1", "expect": ["Travis Kell", "apartment", "14"], "must_not": ["Mateo Ruiz's phone was with it"]}


class ExpectHitTests(unittest.TestCase):
    def test_each_shared_case_scores_as_written(self):
        for case in CASES:
            with self.subTest(case=case):
                self.assertEqual(replay.expect_hit(case["term"], case["text"]), case["hit"])

    def test_a_caveat_and_a_seizure_date_no_longer_find_q1(self):
        answer = ("The glovebox phone was with Travis Kell's phone most evenings. The cell sector covers both the "
                  "garage and Larkmont Apartments, so the place is not settled. The phone was seized on 14 June 2024.")
        score = replay.score_key(answer, Q1, {"ok": 2, "total": 2})
        self.assertEqual((score["result"], score["missing"]), ("missed", ["apartment", "14"]))

    def test_an_answer_that_states_the_place_and_count_is_found(self):
        answer = "It was with Travis Kell's phone at Kell's apartment in the evenings, on 14 of the 16 days."
        self.assertEqual(replay.score_key(answer, Q1, {"ok": 1})["result"], "found")


class WrongWordTests(unittest.TestCase):
    def test_each_shared_wrong_case_scores_as_written(self):
        for case in SHARED["wrong_cases"]:
            with self.subTest(text=case["text"]):
                self.assertEqual(replay.wrong_words(case["must_not"], case["text"]), case["wrong"])

    def test_a_right_answer_naming_the_other_version_is_not_wrong(self):
        key = {"id": "Q2", "expect": ["hospital"], "must_not": ["Brightwater"]}
        answer = ("He was at the hospital [note](doc://a/1).\n\nOther version for 3 May 2024. That night is one of "
                  "the Brightwater theft nights [report](doc://b/1).")
        self.assertEqual(replay.score_key(answer, key, {"ok": 2})["result"], "found")


if __name__ == "__main__":
    unittest.main()
