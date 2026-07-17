import re
import unittest
from datetime import datetime, timezone

from services.export_common import (
    AIDisclosureLevel,
    ExportMetadata,
    ai_disclosure_statement,
    generate_export_id,
    render_metadata_block_html,
    render_metadata_csv_values,
    safe_filename,
)


class ExportCommonTests(unittest.TestCase):
    def test_generate_export_id_is_short_hex_and_unique(self):
        export_ids = {generate_export_id() for _ in range(50)}

        self.assertEqual(len(export_ids), 50)
        for export_id in export_ids:
            self.assertRegex(export_id, r"^exp_[0-9a-f]{12}$")

    def test_html_metadata_block_contains_scope_id_citations_and_ai_disclosure(self):
        meta = ExportMetadata(
            export_id="exp_123456789abc",
            case_id="case-1",
            generated_at=datetime(2026, 7, 17, 12, 30, tzinfo=timezone.utc),
            generated_by="investigator@example.com",
            filters_description='Search: "wire"',
            scope_description="Selected transactions",
            ai_disclosure=AIDisclosureLevel.AI_GENERATED,
            source_citations=("bank.pdf | p.4",),
        )

        html = render_metadata_block_html(meta)

        self.assertIn("exp_123456789abc", html)
        self.assertIn("Search: &quot;wire&quot; | Selected transactions", html)
        self.assertIn("bank.pdf | p.4", html)
        self.assertIn("AI-generated summaries", html)

    def test_none_ai_disclosure_renders_no_statement(self):
        meta = ExportMetadata(
            export_id="exp_123456789abc",
            case_id="case-1",
            generated_at=datetime(2026, 7, 17, 12, 30, tzinfo=timezone.utc),
            generated_by="investigator@example.com",
        )

        html = render_metadata_block_html(meta)
        csv_values = render_metadata_csv_values(meta)

        self.assertNotIn("AI / human review", html)
        self.assertEqual(csv_values["AI Disclosure"], "")

    def test_disclosure_wording_is_fixed_for_each_level(self):
        self.assertEqual(ai_disclosure_statement(AIDisclosureLevel.NONE), "")
        self.assertIn(
            "has not been independently verified",
            ai_disclosure_statement(AIDisclosureLevel.AI_GENERATED),
        )
        self.assertIn(
            "reviewed by a human investigator",
            ai_disclosure_statement(AIDisclosureLevel.AI_ASSISTED_HUMAN_REVIEWED),
        )

    def test_safe_filename_matches_export_paths(self):
        self.assertEqual(safe_filename('Payments, "Priority"'), "payments-priority")
        self.assertTrue(re.match(r"^[a-z0-9._-]+$", safe_filename("A/B C")))


if __name__ == "__main__":
    unittest.main()
