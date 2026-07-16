import csv
import io
import unittest
import zipfile
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from routers import agent
from services.case_service import CaseAccessDenied
from services.agent.exports import render_artifact_csv, render_report_docx, render_report_pdf


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


class AgentArtifactRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_export_agent_artifact_sets_download_security_headers(self):
        exported = SimpleNamespace(
            content=b"a,b\n1,2\n",
            filename="Evidence Résumé.csv",
            media_type="text/csv; charset=utf-8",
        )

        with patch.object(agent.agent_service, "export_artifact", return_value=exported) as export_artifact:
            response = await agent.export_agent_artifact(
                artifact_id=uuid4(),
                format="csv",
                db=object(),
                current_user=object(),
            )

        export_artifact.assert_called_once()
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-agent-export-format"], "csv")
        self.assertIn("filename*=UTF-8''Evidence%20R%C3%A9sum%C3%A9.csv", response.headers["content-disposition"])

    async def test_export_agent_artifact_permission_denied_does_not_build_response(self):
        with patch.object(
            agent.agent_service,
            "export_artifact",
            side_effect=CaseAccessDenied("denied"),
        ):
            with self.assertRaises(HTTPException) as caught:
                await agent.export_agent_artifact(
                    artifact_id=uuid4(),
                    format="csv",
                    db=object(),
                    current_user=object(),
                )

        self.assertEqual(caught.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
