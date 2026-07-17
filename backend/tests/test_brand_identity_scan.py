import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.brand_identity_scan import run_scan  # noqa: E402


class BrandIdentityScanTests(unittest.TestCase):
    def test_story_fixture_has_no_undocumented_customer_visible_legacy(self):
        result = run_scan(REPO_ROOT)

        self.assertEqual(result.undocumented_customer_visible_legacy, [])
        self.assertEqual(result.email_markers, [])

        documented_open_paths = {finding.path for finding in result.documented_open}
        self.assertIn("scripts/generate_user_guide_pdf.py", documented_open_paths)
        self.assertIn("scripts/generate_user_guide_pdf.js", documented_open_paths)
        self.assertIn("frontend_v2/public/owl.webp", documented_open_paths)
        self.assertIn("landing/index.html", documented_open_paths)

        cleared_paths = {finding.path for finding in result.cleared_loupe}
        self.assertIn("frontend_v2/index.html", cleared_paths)
        self.assertIn("frontend_v2/public/loupe-logo.png", cleared_paths)
        self.assertIn("frontend_v2/public/loupe-logo-transparent.png", cleared_paths)

        deduce_findings = [
            finding for finding in result.findings if finding.token == "legacy_deduce"
        ]
        self.assertTrue(deduce_findings)
        self.assertTrue(
            all(finding.status == "retained_internal" for finding in deduce_findings)
        )

    def test_new_customer_visible_legacy_name_is_a_regression(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            component = root / "frontend_v2" / "src" / "components" / "Banner.tsx"
            component.parent.mkdir(parents=True)
            component.write_text(
                'export function Banner() { return <h1>Owl Investigation Platform</h1> }\n',
                encoding="utf-8",
            )

            result = run_scan(root)

        unexpected = result.undocumented_customer_visible_legacy
        self.assertEqual(len(unexpected), 1)
        self.assertEqual(unexpected[0].path, "frontend_v2/src/components/Banner.tsx")
        self.assertEqual(unexpected[0].token, "legacy_owl")

    def test_email_marker_requires_inventory_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            mailer = root / "backend" / "services" / "mailer.py"
            mailer.parent.mkdir(parents=True)
            mailer.write_text(
                "def send_digest():\n    return 'smtp://mail.example.test'\n",
                encoding="utf-8",
            )

            result = run_scan(root)

        self.assertEqual(len(result.email_markers), 1)
        self.assertEqual(result.email_markers[0].path, "backend/services/mailer.py")


if __name__ == "__main__":
    unittest.main()
