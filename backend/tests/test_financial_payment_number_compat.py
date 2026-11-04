"""An export taken before payment numbers existed compares unchanged against one taken after (FEAT-006 review)."""
import unittest

from services.financial.export_comparison import _changes, _numbers_comparable


class PaymentNumberCompatibilityTests(unittest.TestCase):
    def test_a_new_number_alone_is_not_a_change(self):
        before = [{"row": {"key": "a", "amount_minor": "5"}}]
        after = [{"row": {"key": "a", "amount_minor": "5", "txn_number": 7}}]
        self.assertEqual(_changes(*_numbers_comparable(before, after), lambda r: r["row"]["key"])["changed"], [])

    def test_a_changed_number_between_two_numbered_exports_is_still_shown(self):
        before = [{"row": {"key": "a", "txn_number": 6}}]
        after = [{"row": {"key": "a", "txn_number": 7}}]
        changed = _changes(*_numbers_comparable(before, after), lambda r: r["row"]["key"])["changed"]
        self.assertEqual(changed[0]["changed_paths"], ["/row/txn_number"])

    def test_the_cost_pdf_footer_prints_the_case_title_as_written(self):
        from services.case_cost_report import css_text
        # A CSS escape takes one following space as its end, so the space after "&" survives as the second one.
        self.assertEqual(css_text('Smith & "Jones"'), 'Smith \\26  \\22 Jones\\22 ')


if __name__ == "__main__":
    unittest.main()
