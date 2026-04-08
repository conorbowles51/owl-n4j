import unittest

from services.financial_export_service import build_financial_export_html


class FinancialExportServiceTests(unittest.TestCase):
    def test_html_contains_filters_and_provenance(self):
        html = build_financial_export_html(
            transactions=[
                {
                    "key": "tx-1",
                    "date": "2026-04-01",
                    "name": "Wire transfer",
                    "amount": 1200.0,
                    "category": "Legal/Professional",
                    "from_entity": {"key": "sender-a", "name": "Sender A"},
                    "to_entity": {"key": "beneficiary-a", "name": "Beneficiary A"},
                    "summary": "Transfer to outside counsel",
                    "source_filename": "bank_statement.pdf",
                    "source_page": 4,
                    "evidence_source_type": "bank_statement",
                }
            ],
            case_name="Case Alpha",
            filters_description='Search: "counsel"',
            entity_flow={
                "senders": [{"key": "sender-a", "name": "Sender A", "count": 1, "totalAmount": 1200.0}],
                "beneficiaries": [{"key": "beneficiary-a", "name": "Beneficiary A", "count": 1, "totalAmount": 1200.0}],
            },
        )

        self.assertIn("Active filters: Search: &quot;counsel&quot;", html)
        self.assertIn("bank_statement.pdf", html)
        self.assertIn("Senders", html)
        self.assertIn("Beneficiaries", html)
        self.assertIn("Money Out", html)


if __name__ == "__main__":
    unittest.main()
