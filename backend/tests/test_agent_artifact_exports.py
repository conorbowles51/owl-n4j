import csv
import io
import unittest

from services.agent.exports import render_artifact_csv


def read_csv(content: bytes) -> list[dict[str, str]]:
    text = content.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


class AgentArtifactExportTests(unittest.TestCase):
    def test_table_artifact_exports_csv_with_explicit_columns_and_escaping(self):
        exported = render_artifact_csv(
            artifact_type="table",
            title='Payments, "Priority"',
            payload={
                "columns": [
                    {"key": "name", "label": "Name"},
                    {"key": "amount", "label": "Amount"},
                ],
                "rows": [
                    {"name": 'Acme, "North"', "amount": 1250, "extra": "included"},
                ],
            },
        )

        rows = read_csv(exported.content)

        self.assertEqual(exported.media_type, "text/csv; charset=utf-8")
        self.assertEqual(exported.filename, "payments-priority-table.csv")
        self.assertEqual(rows[0]["name"], 'Acme, "North"')
        self.assertEqual(rows[0]["amount"], "1250")
        self.assertEqual(rows[0]["extra"], "included")

    def test_financial_artifact_flattens_nested_counterparties(self):
        exported = render_artifact_csv(
            artifact_type="financial",
            title="Marcus transactions",
            payload={
                "transactions": [
                    {
                        "date": "2023-03-18",
                        "name": "Wire transfer",
                        "amount": 125000,
                        "currency": "EUR",
                        "from_entity": {"key": "person_marcus", "name": "Marcus Chen"},
                        "to_entity": {"key": "company_nexus", "name": "Nexus Trading Ltd"},
                    }
                ]
            },
        )

        rows = read_csv(exported.content)

        self.assertEqual(rows[0]["from_entity.name"], "Marcus Chen")
        self.assertEqual(rows[0]["to_entity.key"], "company_nexus")
        self.assertNotIn("counterparty_debug_blob", rows[0])

    def test_financial_artifact_uses_concise_default_columns(self):
        exported = render_artifact_csv(
            artifact_type="financial",
            title="Transactions",
            payload={
                "transactions": [
                    {
                        "date": "2023-03-18",
                        "name": "Wire transfer",
                        "amount": 125000,
                        "currency": "EUR",
                        "from_entity": {"name": "GlobalTech"},
                        "to_entity": {"name": "Nexus"},
                        "counterparty_debug_blob": {"large": True},
                    }
                ]
            },
        )

        header = exported.content.decode("utf-8-sig").splitlines()[0]

        self.assertIn("from_entity.name", header)
        self.assertIn("to_entity.name", header)
        self.assertNotIn("counterparty_debug_blob", header)

    def test_timeline_artifact_exports_headers_when_empty(self):
        exported = render_artifact_csv(
            artifact_type="timeline",
            title="Empty timeline",
            payload={"events": []},
        )

        header = exported.content.decode("utf-8-sig").splitlines()[0]

        self.assertIn("date", header)
        self.assertIn("summary", header)


if __name__ == "__main__":
    unittest.main()
