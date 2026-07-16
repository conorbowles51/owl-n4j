import csv
import io
import unittest
import zipfile

from services.agent.exports import render_artifact_csv, render_report_docx, render_report_pdf


def read_csv(content: bytes) -> list[dict[str, str]]:
    text = content.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def read_csv_sections(content: bytes) -> list[list[dict[str, str]]]:
    text = content.decode("utf-8-sig").strip()
    return [
        list(csv.DictReader(io.StringIO(section)))
        for section in text.split("\n\n")
        if section.strip()
    ]


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

    def test_csv_export_appends_sources_section(self):
        exported = render_artifact_csv(
            artifact_type="table",
            title="Payments",
            payload={
                "columns": [{"key": "name"}],
                "rows": [{"name": "Acme"}],
            },
            citations=[
                {
                    "label": "Bank statement",
                    "type": "document",
                    "artifact_id": "artifact-1",
                    "result_id": "result-1",
                }
            ],
        )

        sections = read_csv_sections(exported.content)

        self.assertEqual(sections[0][0]["name"], "Acme")
        self.assertEqual(
            sections[1][0],
            {
                "label": "Bank statement",
                "type": "document",
                "artifact_id": "artifact-1",
                "result_id": "result-1",
            },
        )

    def test_table_artifact_flattens_nested_counterparties(self):
        exported = render_artifact_csv(
            artifact_type="table",
            title="Marcus transactions",
            payload={
                "columns": [
                    {"key": "date"},
                    {"key": "name"},
                    {"key": "from_entity.name"},
                    {"key": "to_entity.key"},
                ],
                "rows": [
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

    def test_chart_artifact_exports_source_rows_csv(self):
        exported = render_artifact_csv(
            artifact_type="chart",
            title="Transaction totals",
            payload={
                "chart_type": "bar",
                "x_key": "person",
                "y_keys": ["total_amount"],
                "columns": [{"key": "person"}, {"key": "total_amount"}],
                "rows": [
                    {"person": "Daniel Rook", "total_amount": 145000, "count": 3},
                ],
            },
        )

        rows = read_csv(exported.content)

        self.assertEqual(exported.filename, "transaction-totals-chart.csv")
        self.assertEqual(rows[0]["person"], "Daniel Rook")
        self.assertEqual(rows[0]["total_amount"], "145000")
        self.assertEqual(rows[0]["count"], "3")

    def test_report_artifact_exports_docx(self):
        exported = render_report_docx(
            title="Defense report",
            payload={
                "title": "Defense report",
                "purpose": "Summarize contradictions.",
                "scope": "Witness statements and communications.",
                "included_items": ["Witness contradictions"],
                "sections": [
                    {
                        "heading": "Key contradiction",
                        "content": "Witness accounts conflict on control.",
                        "level": 2,
                        "embeds": [],
                    }
                ],
            },
        )

        self.assertEqual(
            exported.media_type,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertTrue(exported.content.startswith(b"PK"))
        self.assertEqual(exported.filename, "defense-report-report.docx")

    def test_report_artifact_exports_docx_with_embedded_chart(self):
        exported = render_report_docx(
            title="Financial report",
            payload={
                "title": "Financial report",
                "purpose": "Compare payment totals.",
                "sections": [
                    {
                        "heading": "Payment concentration",
                        "content": "The chart compares totals by person.",
                        "level": 2,
                        "embeds": [
                            {
                                "artifact_id": "chart-1",
                                "type": "chart",
                                "title": "Payments by person",
                                "caption": "Totals by person",
                                "available": True,
                                "citations": [{"label": "Ledger extract", "result_id": "result-ledger"}],
                                "data": {
                                    "chart_type": "bar",
                                    "x_key": "person",
                                    "y_keys": ["total_amount"],
                                    "series": [{"key": "total_amount", "label": "Total amount"}],
                                    "rows": [
                                        {"person": "Daniel Rook", "total_amount": 145000},
                                        {"person": "Elena Morrow", "total_amount": 78000},
                                    ],
                                },
                            }
                        ],
                    }
                ],
                "citations": [{"label": "Report source", "page": 7}],
            },
            citations=[{"label": "Run citation", "type": "tool_result", "result_id": "run-1"}],
        )

        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")

        self.assertIn("Embedded chart: Payments by person", document_xml)
        self.assertIn("Chart type: bar; 2 source row(s)", document_xml)
        self.assertIn("Daniel Rook", document_xml)
        self.assertIn("Sources", document_xml)
        self.assertIn("Report source", document_xml)
        self.assertIn("Run citation", document_xml)
        self.assertIn("Ledger extract", document_xml)

    def test_report_artifact_exports_pdf(self):
        exported = render_report_pdf(
            title="Defense report",
            payload={
                "title": "Defense report",
                "purpose": "Summarize contradictions.",
                "scope": "Witness statements and communications.",
                "included_items": ["Witness contradictions"],
                "sections": [
                    {
                        "heading": "Key contradiction",
                        "content": "Witness accounts conflict on control.",
                        "level": 2,
                        "embeds": [],
                    }
                ],
            },
        )

        self.assertEqual(exported.media_type, "application/pdf")
        self.assertTrue(exported.content.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
