import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from routers import evidence


class EvidenceFileRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_evidence_file_sets_inline_security_headers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "stored.txt"
            file_path.write_text("evidence", encoding="utf-8")
            record = SimpleNamespace(
                id=uuid4(),
                original_filename='Evidence "Résumé".txt',
                stored_path=str(file_path),
            )

            with (
                patch.object(evidence.EvidenceDBStorage, "get", return_value=record),
                patch.object(evidence, "_resolve_stored_path", return_value=file_path),
            ):
                response = await evidence.get_evidence_file(
                    evidence_id=str(record.id),
                    user={"email": "investigator@example.test"},
                    db=object(),
                )

        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertTrue(response.headers["content-disposition"].startswith("inline; "))
        self.assertIn("filename*=UTF-8''Evidence%20%22R%C3%A9sum%C3%A9%22.txt", response.headers["content-disposition"])


if __name__ == "__main__":
    unittest.main()
