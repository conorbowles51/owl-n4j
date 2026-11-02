"""The v1 phone helper ``services/phone_normalise.py`` is retired together with the v1 Cellebrite import.

Spec 02's ``services/phone/identifiers.py`` and ``numbers.py`` (phonenumbers) replace it. Its only caller is
``services/neo4j/cellebrite_service.py``, removed in unit 03-3 (06 section 7). These tests keep the retirement a
one-step removal: no new code may start importing the helper, and the removal table names it beside its caller.
"""
import os
import re
import unittest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(BACKEND)
ALLOWED = {
    os.path.join("services", "neo4j", "cellebrite_service.py"),
    os.path.join("tests", "test_phone_normalise.py"),
    os.path.join("tests", "test_phone_normalise_retirement.py"),
}
IMPORT = re.compile(r"^\s*(from\s+services(\.phone_normalise\b|\s+import\s+[^\n]*\bphone_normalise\b)"
                    r"|import\s+services\.phone_normalise\b)", re.M)


class PhoneNormaliseRetirementTests(unittest.TestCase):
    def test_only_the_v1_cellebrite_import_uses_the_helper(self):
        callers = set()
        for root, dirs, files in os.walk(BACKEND):
            dirs[:] = [d for d in dirs if d not in {"__pycache__", "node_modules", ".venv", "venv"}]
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(root, name)
                with open(path, encoding="utf-8", errors="replace") as fh:
                    if IMPORT.search(fh.read()):
                        callers.add(os.path.relpath(path, BACKEND))
        self.assertEqual(callers - ALLOWED, set(),
                         "new code imports services.phone_normalise; use services/phone/identifiers.py or numbers.py")

    def test_removal_table_names_the_helper_with_its_caller(self):
        path = os.path.join(REPO, "docs", "cellebrite", "06-build-order.md")
        if not os.path.exists(path):
            self.skipTest("docs/cellebrite not in this checkout")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        section = text.split("## 7. Removal of the old Cellebrite code", 1)[1].split("\n## ", 1)[0]
        row = next((line for line in section.splitlines() if "cellebrite_service.py" in line), "")
        self.assertIn("services/phone_normalise.py", row)
        self.assertIn("tests/test_phone_normalise.py", row)


if __name__ == "__main__":
    unittest.main()
