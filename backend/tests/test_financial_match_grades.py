"""Every possible transfer pair is listed with a strength by rule; no window or name threshold hides one
(Neil 2026-11-04: "We don't want to miss things based on an arbitrary cutoff."). Tiers 0 to 2 are unchanged."""
from __future__ import annotations

import inspect
import unittest

from postgres.models.enums import TransactionDirection
from services.financial import linkage
from services.financial.linkage import (
    NAME_SIMILARITY_THRESHOLD,
    graded_level,
    graded_transfer_pairs,
    link_composite,
    link_probabilistic,
    link_transactions,
    name_similarity,
)
from services.match_strength import LEVELS
from tests.test_financial_linkage import CREDIT, DEBIT, observation


def _pair(day_left=5, day_right=20, debit_cp=None, debit_holder=None, credit_cp=None, credit_holder=None):
    return [observation(1, account=100, document=901, direction=DEBIT, day=day_left, counterparty=debit_cp,
                        holder=debit_holder),
            observation(2, account=200, document=902, direction=CREDIT, day=day_right, counterparty=credit_cp,
                        holder=credit_holder)]


class GradedTransferPairTests(unittest.TestCase):
    def test_a_fifteen_day_pair_is_listed_as_weak(self):
        rows = _pair(day_left=5, day_right=20)
        self.assertEqual(link_probabilistic(rows).links, ())   # the tier-2 window (14 days) never proposes it
        out = graded_transfer_pairs(rows)
        self.assertEqual(len(out["pairs"]), 1)
        p = out["pairs"][0]
        self.assertEqual((p["debit_id"], p["credit_id"], p["gap_days"]), (str(rows[0].transaction_id),
                                                                         str(rows[1].transaction_id), 15))
        self.assertEqual(p["level"], "weak")
        self.assertIn("15 days apart", p["reasons"]["match"])
        self.assertEqual(p["reasons"]["substantiation"], ["each is the other's only possible partner"])

    def test_a_name_pair_at_0_84_is_listed_as_weak(self):
        rows = _pair(day_left=5, day_right=10, debit_cp="BLUE RIVERS CORP", debit_holder="ACME HOLDING SA",
                     credit_cp="ACME HOLDING LLC", credit_holder="BLUE RIVERS LLC")
        sim = name_similarity("BLUE RIVERS CORP", "BLUE RIVERS LLC")
        self.assertTrue(0.83 < sim < NAME_SIMILARITY_THRESHOLD)
        self.assertEqual(link_probabilistic(rows).links, ())   # under 0.85: tier 2 never proposes it
        p = graded_transfer_pairs(rows)["pairs"][0]
        self.assertEqual(p["fits"]["name"], 1)
        self.assertEqual(p["level"], "weak")
        self.assertTrue(any(r.startswith("names alike but under 0.85 (0.84") for r in p["reasons"]["match"]))

    def test_strongest_first_and_a_clean_pair_is_strong(self):
        rows = _pair(day_left=5, day_right=6, debit_cp="BLUE RIVER L.L.C.", debit_holder="ACME HOLDINGS LTD",
                     credit_cp="ACME HOLDINGS LIMITED", credit_holder="BLUE RIVER LLC")
        rows.append(observation(3, account=300, document=903, direction=CREDIT, day=30))
        out = graded_transfer_pairs(rows)
        self.assertEqual([p["level"] for p in out["pairs"]], sorted((p["level"] for p in out["pairs"]),
                                                                    key=LEVELS.index))
        # two possible partners for the debit: not unique, so no substantiation; names agree, a day apart
        self.assertEqual(out["pairs"][0]["credit_id"], str(rows[1].transaction_id))
        self.assertEqual(out["pairs"][0]["level"], "moderate")
        alone = graded_transfer_pairs(rows[:2])["pairs"][0]
        self.assertEqual(alone["level"], "strong")
        self.assertEqual(out["by_level"], {"strong": 0, "moderate": 1, "weak": 1, "faint": 0})

    def test_only_one_payment_keeps_the_strength_of_the_full_list(self):
        rows = _pair(day_left=5, day_right=6, debit_cp="BLUE RIVER L.L.C.", debit_holder="ACME HOLDINGS LTD",
                     credit_cp="ACME HOLDINGS LIMITED", credit_holder="BLUE RIVER LLC")
        rows.append(observation(3, account=300, document=903, direction=CREDIT, day=30))
        rows.append(observation(4, account=400, document=904, direction=DEBIT, day=31))
        full = graded_transfer_pairs(rows, per_row=None)["pairs"]
        me = rows[2].transaction_id
        mine = graded_transfer_pairs(rows, per_row=None, only=me)["pairs"]
        self.assertEqual(mine, [p for p in full if str(me) in (p["debit_id"], p["credit_id"])])
        self.assertEqual(len(mine), 2)

    def test_the_search_bound_is_counted_not_hidden(self):
        rows = [observation(1, account=100, document=901, direction=DEBIT, day=1),
                observation(2, account=200, document=902, direction=CREDIT, day=1, date_field="value_date",
                            value_date=linkage.date(2025, 6, 1))]
        rows[1] = linkage.LinkObservation(**{**rows[1].__dict__, "ordering_date": linkage.date(2025, 6, 1)})
        out = graded_transfer_pairs(rows)
        self.assertEqual(out["pairs"], [])
        self.assertEqual(out["left_out"]["beyond_days"], 1)
        self.assertIn("1 more than 365 days apart", linkage.graded_left_out_words(out["left_out"]))

    def test_a_far_pair_with_nothing_else_is_faint_and_same_account_or_direction_is_not_a_transfer(self):
        far = _pair(day_left=1, day_right=1)
        far[1] = linkage.LinkObservation(**{**far[1].__dict__, "value_date": linkage.date(2024, 5, 20),
                                            "ordering_date": linkage.date(2024, 5, 20)})
        two = far + [observation(3, account=300, document=903, direction=CREDIT, day=2)]
        self.assertEqual([p["level"] for p in graded_transfer_pairs(two)["pairs"]], ["weak", "faint"])
        same_account = [observation(1, account=100, direction=DEBIT), observation(2, account=100, document=901,
                                                                                    direction=CREDIT)]
        self.assertEqual(graded_transfer_pairs(same_account)["pairs"], [])

    def test_tier_one_and_tier_two_output_is_unchanged(self):
        rows = _pair(day_left=5, day_right=6) + _pair(day_left=5, day_right=19)
        rows[2] = observation(3, account=300, document=903, direction=DEBIT, day=5, minor=70_000)
        rows[3] = observation(4, account=400, document=904, direction=CREDIT, day=19, minor=70_000)
        composite = link_composite(rows)
        self.assertEqual({(l.left_id.int, l.right_id.int) for l in composite.links}, {(1, 2)})
        self.assertEqual(link_probabilistic(rows).links, ())
        self.assertEqual({(l.left_id.int, l.right_id.int) for l in link_transactions(rows).links}, {(1, 2)})
        graded = graded_transfer_pairs(rows)
        self.assertEqual({(p["debit_id"][-1], p["credit_id"][-1]) for p in graded["pairs"]}, {("1", "2"), ("3", "4")})

    def test_strength_is_set_by_the_rule_never_by_a_model(self):
        rows = _pair(day_left=5, day_right=6, debit_cp="X", credit_cp="Y")
        for p in graded_transfer_pairs(rows)["pairs"]:
            self.assertEqual(p["level"], graded_level(p["fits"]["date"], p["fits"]["name"], p["substantiation"]))
        source = inspect.getsource(linkage) + inspect.getsource(__import__("services.match_strength").match_strength)
        for word in ("openai", "langchain", "anthropic", "llm", "agent"):
            self.assertNotIn(word, source.lower().replace("agreement", ""))
        self.assertEqual(TransactionDirection.debit, DEBIT)


if __name__ == "__main__":
    unittest.main()
