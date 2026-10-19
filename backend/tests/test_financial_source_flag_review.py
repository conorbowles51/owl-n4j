"""Source extraction warnings must not masquerade as current arithmetic errors.

Synthetic values only. These tests use the actual proposal/check/admission path;
acknowledging a readable source never waives a missing value or a difference.
"""
from copy import deepcopy
from unittest import TestCase

from services.financial.statement_check_request import StatementCheckRequest, check_statement_request
from services.financial.statement_import_proposal import propose_table
from services.financial.import_batches import initial_request
from tests.test_financial_statement_import_proposal import source


class SourceFlagReviewTests(TestCase):
    def proposal(self):
        proposed = propose_table(source([
            ["Date", "Description", "Credit", "Debit", "Balance"],
            ["2026-04-01", "Opening Balance", "", "", "1000.00"],
            ["2026-04-15", "SYNTHETIC TAX PAYMENT", "", "12.34", "987.66"],
            ["2026-04-30", "Closing Balance", "", "", "987.66"],
            ["", "Total debits", "", "12.34", ""],
        ]), "MXN")
        proposed.update(revision="a" * 64, currency="MXN", page_numbers=[1],
            metadata=dict(institution="Synthetic bank", holder="Synthetic holder",
                account_number="TEST0001", period_start="2026-04-01", period_end="2026-04-30"))
        payment = next(row for row in proposed["rows"] if not row["excluded"])
        payment["issues"] = ["Check which deposit or withdrawal column contains this payment."]
        return proposed, payment["id"]

    def request(self, proposal):
        raw = initial_request(proposal)
        return StatementCheckRequest.model_validate({key: value for key, value in raw.items()
            if key in StatementCheckRequest.model_fields})

    def check(self, proposal, request):
        return check_statement_request(proposal, request)

    def edit(self, request, identifier, **changes):
        raw = request.model_dump(mode="json")
        next(row for row in raw["rows"] if row["id"] == identifier).update(changes)
        return StatementCheckRequest.model_validate(raw)

    def test_matching_row_exposes_source_reason_then_explicit_check_clears_only_that_reason(self):
        proposal, identifier = self.proposal()
        unchanged = deepcopy(proposal)
        request = self.request(proposal)
        first = self.check(proposal, request)
        running = next(check for check in first["checks"] if check["kind"] == "running_balance")
        self.assertEqual(running["status"], "matches")
        self.assertEqual(first["admission"]["calculation"]["difference_minor"], "0")
        self.assertFalse(first["admission"]["can_import"])
        self.assertEqual(len(first["admission"]["blockers"]), 1)
        reason = first["admission"]["blockers"][0]
        self.assertEqual(reason["kind"], "reading")
        self.assertEqual(reason["message"], proposal["rows"][2]["issues"][0])
        self.assertEqual(reason["target"], dict(kind="transaction_field", row_id=identifier, field="review", page=1))
        request = self.edit(request, identifier, reason="Checked against the original statement.")
        checked = self.check(proposal, request)
        self.assertTrue(checked["admission"]["can_import"])
        self.assertEqual(checked["flagged_rows"], 0)
        self.assertEqual(checked["admission"]["blockers"], [])
        # Reopening the persisted request keeps that acknowledgement without
        # deleting the original parser warning or inventing a corrected amount.
        reopened = self.check(proposal, StatementCheckRequest.model_validate(request.model_dump(mode="json")))
        self.assertEqual(reopened, checked)
        self.assertEqual(proposal, unchanged)

    def test_current_valid_correction_replaces_old_flag_but_new_field_and_balance_failures_still_block(self):
        proposal, identifier = self.proposal()
        payment = next(row for row in proposal["rows"] if row["id"] == identifier)
        payment["fields"]["amount_minor"] = "1235"
        original = deepcopy(proposal)
        request = self.request(proposal)
        request = self.edit(request, identifier, amount_minor="1234")
        corrected = self.check(proposal, request)
        self.assertTrue(corrected["admission"]["can_import"])
        self.assertEqual(corrected["flagged_rows"], 0)
        self.assertEqual(proposal, original)
        request = self.edit(request, identifier, reason="Checked against the original statement.")
        for field, value, expected_field in (("date", "2026-04-31", "date"),
            ("amount_minor", "", "amount"), ("direction", None, "direction")):
            with self.subTest(field=field):
                altered = self.edit(request, identifier, **{field: value})
                result = self.check(proposal, altered)["admission"]
                self.assertFalse(result["can_import"])
                problem = next(item for item in result["blockers"] if item.get("field") == expected_field)
                self.assertEqual(problem["target"]["row_id"], identifier)
                self.assertEqual(problem["target"]["field"], expected_field)
                self.assertTrue(problem["expected_format"])
        request = self.edit(request, identifier, amount_minor="1233")
        different = self.check(proposal, request)["admission"]
        self.assertFalse(different["can_import"])
        difference = next(item for item in different["blockers"] if item.get("check") == "running_balance")
        self.assertEqual(difference["target"]["row_id"], identifier)
        self.assertEqual((difference["expected_minor"], difference["printed_minor"], difference["difference_minor"]),
            ("98767", "98766", "1"))
        self.assertFalse(any(item["kind"] == "reading" for item in different["blockers"]))
        self.assertEqual(proposal, original)
