import csv
import io
import unittest
import zipfile
from types import SimpleNamespace
from unittest.mock import Mock, patch

from services.agent.exports import render_artifact_csv, render_report_docx, render_report_pdf
from services.agent.service import AgentService, ExportConfirmationRequired


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
            },
        )

        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")

        self.assertIn("Embedded chart: Payments by person", document_xml)
        self.assertIn("Chart type: bar; 2 source row(s)", document_xml)
        self.assertIn("Daniel Rook", document_xml)

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

    def test_export_artifact_requires_confirmation_before_rendering(self):
        artifact = SimpleNamespace(
            id="artifact-1",
            type="table",
            title="Transactions",
            run=SimpleNamespace(id="run-1", thread_id="thread-1", case_id="case-1", status="completed"),
        )
        service = AgentService()
        db = Mock()

        with patch("services.agent.service.storage.get_artifact_for_user", return_value=artifact), patch(
            "services.agent.service.render_artifact_export"
        ) as render, patch.object(service, "_log_agent_event"):
            with self.assertRaises(ExportConfirmationRequired) as raised:
                service.export_artifact(
                    db=db,
                    user=SimpleNamespace(email="user@example.com"),
                    artifact_id="artifact-1",
                    export_format="csv",
                )

        self.assertEqual(raised.exception.payload["artifact_id"], "artifact-1")
        render.assert_not_called()
        db.commit.assert_called_once()

    def test_export_artifact_confirmed_renders_once(self):
        artifact = SimpleNamespace(
            id="artifact-1",
            type="table",
            title="Transactions",
            run=SimpleNamespace(id="run-1", thread_id="thread-1", case_id="case-1", status="completed"),
        )
        exported = SimpleNamespace(content=b"a,b\n", media_type="text/csv", filename="transactions.csv")
        service = AgentService()
        db = Mock()

        with patch("services.agent.service.storage.get_artifact_for_user", return_value=artifact), patch(
            "services.agent.service.render_artifact_export", return_value=exported
        ) as render, patch.object(service, "_log_agent_event"):
            result = service.export_artifact(
                db=db,
                user=SimpleNamespace(email="user@example.com"),
                artifact_id="artifact-1",
                export_format="csv",
                confirmed=True,
            )

        self.assertIs(result, exported)
        render.assert_called_once_with(artifact, "csv")
        db.commit.assert_called_once()

    def test_export_artifact_wrong_case_raises_before_confirmation(self):
        service = AgentService()

        with patch(
            "services.agent.service.storage.get_artifact_for_user",
            side_effect=PermissionError("Agent artifact belongs to another user"),
        ), patch("services.agent.service.render_artifact_export") as render:
            with self.assertRaises(PermissionError):
                service.export_artifact(
                    db=Mock(),
                    user=SimpleNamespace(email="user@example.com"),
                    artifact_id="artifact-1",
                    export_format="csv",
                    confirmed=True,
                )

        render.assert_not_called()


if __name__ == "__main__":
    unittest.main()
