"""The payments search group: ledger rows by description, counterparty or amount, with totals, case-scoped."""
import unittest

from services.search.payments import amount_query, search_payments
from tests.test_agent_financial_ledger_tools import LedgerToolFixture


class PaymentSearchTests(LedgerToolFixture):
    def test_description_counterparty_amount_totals_and_case_scope(self):
        _, _, rows = self.source(rows=3, amount=123456)  # EUR 1,234.56, 1,234.57, 1,234.58
        rows[0].description = "Wire to ACME Holdings"
        rows[1].counterparty_raw = "Beta Supplies"
        self.db.commit()
        conn = self.db.connection()
        total, items, totals = search_payments(conn, self.case.id, "acme")
        self.assertEqual((total, [i["transaction_id"] for i in items]), (1, [str(rows[0].id)]))
        self.assertEqual(items[0]["cite"], f"txn://{rows[0].id}")
        self.assertEqual(items[0]["open"], {"screen": "payment", "params": {"transaction_id": str(rows[0].id)}})
        self.assertEqual(search_payments(conn, self.case.id, "beta supplies")[0], 1)
        # every row of the fixture has "Exact source company" as counterparty
        total, items, totals = search_payments(conn, self.case.id, "exact source")
        self.assertEqual(total, 2)
        self.assertEqual(totals["counted_rows"] + totals["not_counted_rows"], 2)
        by_amount = search_payments(conn, self.case.id, "1,234.57")
        self.assertEqual([i["transaction_id"] for i in by_amount[1]], [str(rows[1].id)])
        self.assertEqual(search_payments(conn, self.case.id, "€1234.56")[0], 1)
        self.assertEqual(search_payments(conn, self.case.id, "1234.5")[0], 0)  # no partial amount match
        # another case never sees these rows
        self.assertEqual(search_payments(conn, self.other_case.id, "acme")[0], 0)

    def test_totals_are_per_currency_and_direction_of_counted_rows(self):
        _, _, rows = self.source(rows=2, amount=1000)
        for row in rows:
            row.description = "Synthetic rent"
        self.db.commit()
        total, _, totals = search_payments(self.db.connection(), self.case.id, "synthetic rent")
        self.assertEqual(total, 2)
        [eur] = totals["currencies"]
        self.assertEqual(eur["currency"], "EUR")
        # the fixture's statements are p2: verified, and nothing is stated as p3
        self.assertEqual((eur["verified"]["credits_minor"], eur["verified"]["debits_minor"]), ("1000", "1001"))
        self.assertEqual((eur["p3"]["credits_minor"], eur["p3"]["debits_minor"]), ("0", "0"))

    def test_p3_rows_are_stated_apart_from_verified(self):
        document, _, rows = self.source(rows=1, amount=500)
        document.proof_class = "p3"
        rows[0].proof_class = "p3"
        rows[0].description = "Synthetic p3 line"
        self.db.commit()
        _, _, totals = search_payments(self.db.connection(), self.case.id, "synthetic p3")
        [eur] = totals["currencies"]
        self.assertEqual(eur["verified"]["credits_minor"], "0")
        self.assertEqual(eur["p3"]["credits_minor"], "500")

    def test_amount_queries(self):
        self.assertEqual(str(amount_query("$1,234.56")), "1234.56")
        self.assertEqual(str(amount_query("42")), "42")
        self.assertIsNone(amount_query("acme 42"))
        self.assertIsNone(amount_query("1,23.4"))


if __name__ == "__main__":
    unittest.main()
