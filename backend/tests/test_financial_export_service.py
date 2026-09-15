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
        self.assertIn("Positive amounts", html)


if __name__ == "__main__":
    unittest.main()


class FinancialReportCurrencyTests(unittest.TestCase):
    def test_currencies_signs_missing_values_and_corrections_remain_distinct(self):
        html = build_financial_export_html([
            dict(key='eur-a', name='First', amount=123.45, currency='EUR', amount_corrected=True, original_amount=120, correction_reason='Checked page <2>'),
            dict(key='eur-b', name='Second', amount=-23.45, currency='EUR'),
            dict(key='usd-a', name='Third', amount=500, currency='USD'),
            dict(key='unknown', name='Unknown currency', amount=999),
        ], 'Synthetic case', dataset_mode='intelligence')
        import re
        summary = re.search(r'<tbody>(.*?)</tbody>', html, re.S).group(1)
        self.assertIn('100.00', summary)
        self.assertIn('500.00', summary)
        self.assertNotIn('1,599.00', summary)
        self.assertIn('Currency not recorded', summary)
        self.assertIn('Not totalled', summary)
        self.assertIn('-23.45 EUR', html)
        self.assertIn('Original amount: 120.00 EUR', html)
        self.assertIn('Latest correction: Checked page &lt;2&gt;', html)
        self.assertIn('Other financial records', html)
        self.assertNotIn('$', html)
        self.assertNotIn('PRIVILEGED', html)
        self.assertNotIn('Attorney-Client', html)
        self.assertNotIn('Money In', html)
        self.assertNotIn('Money Out', html)

    def test_an_unreadable_amount_does_not_become_zero_or_a_total(self):
        html = build_financial_export_html([dict(key='bad', amount=None, currency='EUR')], 'Synthetic case')
        self.assertIn('Amount not recorded', html)
        self.assertIn('Not totalled', html)
        self.assertNotIn('0.00 EUR', html)
