import unittest

from utils.http_export import EXPORT_SECURITY_HEADERS, content_disposition


class HttpExportTests(unittest.TestCase):
    def test_export_security_headers_are_strict(self):
        self.assertEqual(
            EXPORT_SECURITY_HEADERS,
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    def test_content_disposition_includes_ascii_and_utf8_filename(self):
        header = content_disposition("Résumé final.pdf")

        self.assertEqual(
            header,
            "attachment; filename=\"Rsum final.pdf\"; filename*=UTF-8''R%C3%A9sum%C3%A9%20final.pdf",
        )

    def test_content_disposition_strips_header_breaks_and_escapes_quotes(self):
        header = content_disposition('bad"\r\nname.pdf')

        self.assertNotIn("\r", header)
        self.assertNotIn("\n", header)
        self.assertIn('filename="badname.pdf"', header)
        self.assertIn("filename*=UTF-8''bad%22name.pdf", header)


if __name__ == "__main__":
    unittest.main()
