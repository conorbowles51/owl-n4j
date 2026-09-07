import unittest
from types import SimpleNamespace
from unittest.mock import patch
from services.financial.correction_balances import correction_running_balances
from services.financial.periods import BalanceObservation
from services.financial.money import Money


def row(index, amount, balance, **updates):
    return SimpleNamespace(**{**dict(id=index, row_index=index, ref_id=f"TX-{index}", amount_minor=amount,
        running_balance_minor=balance, direction="credit", account_id="a", currency="GBP",
        ledger_status="admitted", superseded_by_id=None), **updates})


class RunningBalanceTests(unittest.TestCase):
    def check(self, rows, opening=0, **updates):
        observation=BalanceObservation.absent() if opening is None else BalanceObservation.printed(Money(opening,"GBP"))
        with patch("services.financial.correction_balances.read_opening", return_value=observation):
            return correction_running_balances(SimpleNamespace(account_id="a",currency="GBP"),rows,
                **{**dict(transaction_id=0, amount_minor=11, direction="credit"),**updates})

    def test_exact_current_and_proposed_intervals(self):
        result=self.check([row(0,10,10),row(1,20,30)])
        forward=result["interpretations"][0]
        self.assertEqual(forward["current"]["mismatch_count"],0)
        self.assertEqual(forward["proposed"]["mismatch_count"],1)
        self.assertEqual(forward["proposed"]["findings"][0]["delta_minor"],"-1")
        self.assertEqual(forward["proposed"]["findings"][0]["after_transaction_id"],"0")
        self.assertGreater(result["interpretations"][1]["current"]["mismatch_count"],0)

    def test_reverse_source_order_is_not_silently_selected(self):
        result=self.check([row(0,20,30),row(1,10,10)])
        self.assertGreater(result["interpretations"][0]["current"]["mismatch_count"],0)
        self.assertEqual(result["interpretations"][1]["current"]["mismatch_count"],0)
        self.assertIn("Neither row order",result["limitation"])

    def test_missing_balances_accumulate_movement_and_leave_tail_explicit(self):
        current=self.check([row(0,10,None),row(1,20,30),row(2,5,None)])["interpretations"][0]["current"]
        self.assertEqual(current["compared_intervals"],1)
        self.assertEqual(current["mismatch_count"],0)
        self.assertEqual(current["trailing_rows_without_balance"],1)

    def test_absent_opening_is_not_zero(self):
        current=self.check([row(0,10,10),row(1,20,30)],opening=None)["interpretations"][0]["current"]
        self.assertEqual(current["unanchored_balances"],1)
        self.assertEqual(current["compared_intervals"],1)

    def test_excluded_row_breaks_chain_and_held_correction_has_no_effect(self):
        result=self.check([row(0,10,10),row(1,500,510,ledger_status="quarantined"),row(2,20,530)],transaction_id=1)
        current=result["interpretations"][0]["current"]
        self.assertEqual(current["excluded_rows"],1)
        self.assertEqual(current["unanchored_balances"],1)
        self.assertEqual(current,result["interpretations"][0]["proposed"])

    def test_superseded_version_not_counted_twice(self):
        result=self.check([row(0,99,99,ledger_status="superseded",superseded_by_id=2),row(0,10,10)])
        self.assertEqual(result["interpretations"][0]["current"]["mismatch_count"],0)

    def test_ambiguous_positions_missing_balances_mixed_accounts_and_limits_unavailable(self):
        for rows in ([row(0,10,10),row(0,20,30)], [row(0,10,None)], [row(0,10,10,account_id="b")],
                     [row(0,10,10,currency="USD")], [row(0,1.1,10)], [row(i,1,i+1) for i in range(1001)]):
            with self.subTest(rows=len(rows)):
                self.assertFalse(self.check(rows)["available"])

    def test_large_and_signed_balances_remain_exact(self):
        value=9007199254740993
        result=self.check([row(0,value,-value,direction="debit")],amount_minor=value+1,direction="debit")
        finding=result["interpretations"][0]["proposed"]["findings"][0]
        self.assertEqual(finding["expected_minor"],str(-value-1))
        self.assertEqual(finding["delta_minor"],"1")

    def test_findings_limit_does_not_limit_comparison_count(self):
        result=self.check([row(i,1,0) for i in range(101)])["interpretations"][0]["current"]
        self.assertEqual(result["mismatch_count"],101)
        self.assertEqual(len(result["findings"]),100)
        self.assertTrue(result["findings_truncated"])
