"""lx-agentfit: an error the agent can correct says what to correct. The demo's Q6 sent an amount range without a
currency twice and was told only "Invalid transaction filters." (fails on the code before this change)."""
import unittest

from services.agent.financial_ledger_tools import FinancialLedgerToolError, read_financial_ledger


class FilterReasonTests(unittest.TestCase):
    def test_an_invalid_filter_names_what_to_fix(self):
        with self.assertRaises(FinancialLedgerToolError) as caught:
            read_financial_ledger(None, case_id="00000000-0000-0000-0000-0000000000ab",
                                  filters={"minimum_minor": "65000", "maximum_minor": "65000"})
        self.assertIn("Select a currency for an amount range", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
