"""lx-agentfit: an error the agent can correct says what to correct. The demo's Q6 sent an amount range without a
currency twice and was told only "Invalid transaction filters." (fails on the code before this change)."""
import unittest

from services.agent.financial_ledger_tools import FinancialLedgerToolError, read_financial_ledger


class FilterReasonTests(unittest.TestCase):
    def test_an_invalid_filter_names_what_to_fix(self):
        with self.assertRaises(FinancialLedgerToolError) as caught:
            read_financial_ledger(None, case_id="00000000-0000-0000-0000-0000000000ab",
                                  filters={"minimum_minor": "65000", "maximum_minor": "65000"})
        self.assertIn("Select a currency for an amount range", str(caught.exception))


class ContactOverNoIdentityTests(unittest.TestCase):
    """The between tool said 'No calls, messages, emails or payments' for two people no phone identity is linked to
    (demo Q3, 11 Nov): a count over nothing. With every agent-fit item off it now says contact cannot be counted."""

    def test_a_side_with_no_linked_identity_is_never_counted_as_no_contact(self):
        import os
        from types import SimpleNamespace
        from unittest.mock import patch
        from services.agent import phone_cross_tools as PC
        from services.phone import link_edges
        side = lambda subject: {"subject": subject, "label": "Mateo Ruiz" if subject.get("dossier_id") == "d1"  # noqa: E731
                                else "Desmond Okafor", "keys": [], "dossier_id": subject.get("dossier_id"),
                                "entity_key": None}
        edge = {"a": {"label": "Mateo Ruiz"}, "b": {"label": "Desmond Okafor"}, "label": "No calls, messages, emails "
                "or payments in this period", "communication": {}, "money": [], "money_mentioned_on_phones": 0,
                "money_readings_available": False}
        with patch.dict(os.environ, {"LOUPE_AGENT_FIT": ""}), \
                patch.object(PC, "_dossier", lambda conn, case, p: SimpleNamespace(id="d1" if "Mateo" in p else "d2")), \
                patch.object(link_edges, "resolve_side", lambda conn, case, s: side(s)), \
                patch.object(link_edges, "edges", lambda *a, **k: {"edges": [edge], "limits": [], "money_absent": None,
                                                                    "zone": "UTC"}), \
                patch.object(link_edges, "edge_records", lambda *a, **k: {"items": [], "total": 0}):
            out = PC.contact_and_money_between.__wrapped__(None, "c", person_a="Mateo Ruiz", person_b="Desmond Okafor")
        self.assertIn("Contact cannot be counted", out["coverage"])
        self.assertNotIn("No calls, messages", out["coverage"])
        self.assertIn("No phone identity is linked to Mateo Ruiz", out["limitation"])


if __name__ == "__main__":
    unittest.main()
