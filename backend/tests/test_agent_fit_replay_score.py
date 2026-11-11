"""The demo key's expected-word match (scripts/financial_agent_fit_replay.py expect_hit) passes the cases the live
journey's scorer passes (frontend_v2/journeys/demo-key-score-cases.json; demo-key-score.test.mjs runs them in node)."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "scripts"))
import financial_agent_fit_replay as replay  # noqa: E402

CASES = json.loads((ROOT / "frontend_v2" / "journeys" / "demo-key-score-cases.json").read_text())["cases"]
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


if __name__ == "__main__":
    unittest.main()
