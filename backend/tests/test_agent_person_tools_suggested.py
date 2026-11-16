"""lx-agentquick B: the person tools count suggested and owner-record identities in totals and headline."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services.agent import phone_cross_tools as PC
from services.phone import link_edges


class BetweenCountsSuggested(unittest.TestCase):
    def test_headline_and_totals_carry_the_suggested_records(self):
        comm = {"calls_ab": 1, "calls_ba": 1, "messages_ab": 3, "messages_ba": 3, "emails_ab": 0, "emails_ba": 0}
        empty = dict(comm, calls_ab=0, calls_ba=0, messages_ab=0, messages_ba=0)
        none_label = "No calls, messages, emails or payments in this period"

        def side(conn, case, subject):
            keyed = subject.get("identity_key")
            return {"subject": subject, "label": "Kell" if subject.get("dossier_id") == "d1" or keyed else "Mateo",
                    "keys": [keyed] if keyed else ([] if subject.get("dossier_id") == "d1" else ["k2"]),
                    "dossier_id": subject.get("dossier_id"), "entity_key": None}

        def edges(conn, case, subjects, **k):
            hit = any(s.get("identity_key") == "phone:+1555" for s in subjects)
            label = "2 calls, 6 messages" if hit else none_label
            return {"edges": [{"a": {"label": "Kell"}, "b": {"label": "Mateo"}, "label": label,
                               "communication": comm if hit else empty, "money": [],
                               "money_mentioned_on_phones": 0, "money_readings_available": False}],
                    "limits": [], "money_absent": None, "zone": "UTC"}
        with patch.dict(os.environ, {"LOUPE_AGENT_FIT": ""}), \
                patch.object(PC, "_edge_subject", lambda conn, case, p, i: {"dossier_id": "d1"} if p == "Kell"
                             else {"identity_key": "k2"}), \
                patch.object(PC, "owner_records_naming", lambda conn, case, name: [
                    {"identity_key": "phone:+1555", "basis": "owner record of Phone 2, no person has linked it",
                     "phone": "Phone 2", "owner": "Kell"}]), \
                patch.object(link_edges, "resolve_side", side), patch.object(link_edges, "edges", edges), \
                patch.object(link_edges, "edge_records", lambda *a, **k: {"items": [], "total": 0}):
            out = PC.contact_and_money_between.__wrapped__(None, "c", person_a="Kell", person_b="Mateo")
        self.assertEqual(out["communication_through_suggested"]["calls"], 2)
        self.assertEqual(out["communication_through_suggested"]["messages"], 6)
        self.assertIn("not linked by a person", out["communication_through_suggested"]["basis"])
        self.assertIn("2 calls, 6 messages", out["label_line"])
        self.assertNotIn("No calls, messages", out["label_line"])


class PersonPhonesCountsSuggested(unittest.TestCase):
    def test_total_and_coverage_include_suggested_and_owner_record_identities(self):
        class Rows(list):
            def fetchall(self):
                return list(self)

        class Conn:
            def execute(self, stmt, params=None):
                sql = str(stmt)
                if "pv_comm_party" in sql and "GROUP BY" in sql:
                    return Rows([("phone:+1555", 8)])
                return Rows()
        from services.phone import readings
        from services.pattern_of_life import subjects
        with patch.object(PC, "_dossier", lambda conn, case, p: SimpleNamespace(id="d1", display_name="Kell")), \
                patch.object(readings, "phone_labels", lambda conn, case: {}), \
                patch.object(subjects, "dossiers", lambda conn, case: []), \
                patch.object(PC, "suggested_identities", lambda conn, case, d: [
                    {"identity_key": "phone:+1555", "shown_as": "+1 555", "strength": "strong",
                     "reasons": ["same name on both phones"]}]), \
                patch.object(PC, "owner_records_naming", lambda conn, case, name: [
                    {"identity_key": "phone:+1666", "basis": "owner record of Phone 3", "phone": "Phone 3",
                     "owner": "Kell"}]):
            out = PC.person_phones.__wrapped__(Conn(), "c", "Kell")
        self.assertEqual(out["total_matching"], 2)
        by = {i["identity_key"]: i for i in out["items"]}
        self.assertEqual(by["phone:+1555"]["link_origin"], "suggested")
        self.assertEqual(by["phone:+1555"]["messages_and_calls"], 8)
        self.assertEqual(by["phone:+1666"]["link_origin"], "owner_record")
        self.assertIn("none is a person's link", out["coverage"])


if __name__ == "__main__":
    unittest.main()
