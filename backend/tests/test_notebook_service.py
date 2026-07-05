import unittest

from services import notebook_service


class NotebookServiceValidationTests(unittest.TestCase):
    def test_sanitize_links_deduplicates_and_keeps_labels(self):
        links = notebook_service._sanitize_links(
            [
                {
                    "target_type": "entity",
                    "target_id": "person-1",
                    "target_label": "Timothy",
                    "metadata": {"source": "selection"},
                },
                {
                    "target_type": "entity",
                    "target_id": "person-1",
                    "target_label": "Duplicate",
                },
                {
                    "target_type": "evidence",
                    "target_id": "file-1",
                    "target_label": "call.wav",
                },
            ]
        )

        self.assertEqual(len(links), 2)
        self.assertEqual(links[0]["target_label"], "Timothy")
        self.assertEqual(links[0]["metadata"], {"source": "selection"})
        self.assertEqual(links[1]["target_type"], "evidence")

    def test_sanitize_links_rejects_unknown_target_type(self):
        with self.assertRaises(ValueError):
            notebook_service._sanitize_links(
                [{"target_type": "job_id", "target_id": "system-field"}]
            )

    def test_clean_body_requires_text(self):
        with self.assertRaises(ValueError):
            notebook_service._clean_body("   ")


if __name__ == "__main__":
    unittest.main()
