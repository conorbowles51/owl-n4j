import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from services.case_export.registry import ExportContext
from services.case_export.sections.visualizations import (
    render_graph_section,
    render_map_section,
    render_timeline_section,
)
from services.case_export.service import list_export_sections, render_case_export_html
from services.case_export.visualizations import (
    png_data_uri,
    render_graph_svg,
    render_map_png,
    render_timeline_svg,
    svg_data_uri,
)


class _User:
    name = "Investigator"
    email = "investigator@example.com"


def _context():
    return ExportContext(case_id=uuid4(), case_name="Case Alpha", current_user=_User())


class CaseExportVisualizationTests(unittest.TestCase):
    def test_visualization_sections_are_registered(self):
        keys = [section["key"] for section in list_export_sections()]

        self.assertIn("graph", keys)
        self.assertIn("timeline", keys)
        self.assertIn("map", keys)

    def test_graph_renderer_outputs_svg_data_uri_and_reflects_state_changes(self):
        first = {
            "nodes": [{"key": "a", "name": "Alice", "type": "Person"}],
            "links": [],
        }
        second = {
            "nodes": [
                {"key": "a", "name": "Alice", "type": "Person"},
                {"key": "b", "name": "Bravo LLC", "type": "Organization"},
            ],
            "links": [{"source": "a", "target": "b", "type": "KNOWS"}],
        }

        first_uri = svg_data_uri(render_graph_svg(first))
        second_uri = svg_data_uri(render_graph_svg(second))

        self.assertTrue(first_uri.startswith("data:image/svg+xml"))
        self.assertNotEqual(first_uri, second_uri)

    def test_timeline_renderer_outputs_svg_data_uri(self):
        svg = render_timeline_svg(
            [
                {
                    "key": "e1",
                    "name": "Call",
                    "type": "Communication",
                    "date": "2026-01-02",
                },
                {
                    "key": "e2",
                    "name": "Payment",
                    "type": "Transaction",
                    "date": "2026-01-03",
                },
            ]
        )

        uri = svg_data_uri(svg)

        self.assertTrue(uri.startswith("data:image/svg+xml"))
        self.assertIn("%3Csvg", uri)

    def test_map_renderer_outputs_png_data_uri_with_offline_fallback(self):
        locations = [
            {"key": "l1", "name": "Warehouse", "latitude": "40.7", "longitude": "-74.0"},
            {"key": "l2", "name": "Office", "latitude": "40.8", "longitude": "-73.9"},
        ]

        with patch(
            "services.case_export.visualizations._render_staticmap_png",
            side_effect=RuntimeError("offline"),
        ):
            png = render_map_png(locations)

        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertTrue(png_data_uri(png).startswith("data:image/png;base64,"))

    def test_registered_sections_embed_current_case_visualization_data(self):
        context = _context()
        graph_service = SimpleNamespace(
            get_full_graph=lambda case_id: {
                "nodes": [{"key": "a", "name": "Alice", "type": "Person"}],
                "links": [],
            }
        )
        with patch(
            "services.case_export.sections.visualizations._get_neo4j_service",
            return_value=graph_service,
        ):
            graph_html = render_graph_section(context)

        timeline_service = SimpleNamespace(
            get_timeline_events=lambda case_id: [
                {"key": "e1", "name": "Event", "type": "Event", "date": "2026-02-03"}
            ]
        )
        with patch(
            "services.case_export.sections.visualizations._get_neo4j_service",
            return_value=timeline_service,
        ):
            timeline_html = render_timeline_section(context)

        map_service = SimpleNamespace(
            get_entities_with_locations=lambda case_id: [
                {"key": "l1", "name": "Port", "latitude": 40.7, "longitude": -74.0}
            ]
        )
        with patch(
            "services.case_export.sections.visualizations._get_neo4j_service",
            return_value=map_service,
        ), patch(
            "services.case_export.sections.visualizations.render_map_png",
            return_value=b"\x89PNG\r\n\x1a\nfake",
        ):
            map_html = render_map_section(context)

        self.assertIn("data:image/svg+xml", graph_html)
        self.assertIn("data:image/svg+xml", timeline_html)
        self.assertIn("data:image/png;base64", map_html)

    def test_case_export_html_composes_selected_visualization_sections(self):
        context = _context()
        graph_service = SimpleNamespace(
            get_full_graph=lambda case_id: {"nodes": [], "links": []}
        )
        with patch(
            "services.case_export.sections.visualizations._get_neo4j_service",
            return_value=graph_service,
        ):
            html = render_case_export_html(context, section_keys=["graph"])

        self.assertIn("Graph Visualization", html)
        self.assertNotIn("Timeline Visualization", html)
        self.assertIn("data:image/svg+xml", html)


if __name__ == "__main__":
    unittest.main()
