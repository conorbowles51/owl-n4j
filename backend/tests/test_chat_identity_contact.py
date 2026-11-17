"""lx-agentquick D10 for chat: chat counts contact between two named people through Loupe's identity suggestions."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services.agent import phone_cross_tools as PC
from services.phone import chat_identity


class Conn:
    def execute(self, stmt, params=None):
        return [SimpleNamespace(id="m1", display_name="Mateo Ruiz"), SimpleNamespace(id="d1", display_name="Desmond Okafor"),
                SimpleNamespace(id="x1", display_name="Kell")]


class ChatContact(unittest.TestCase):
    def test_question_naming_two_people_gets_their_suggested_contact_count(self):
        seen = {}

        def between(conn, case, **k):
            seen.update(k)
            return {"label_line": "2 calls, 6 messages",
                    "communication_through_suggested": {"calls": 2, "messages": 6, "emails": 0,
                                                        "basis": "identities an identity suggestion ties to the person"}}
        with patch.object(PC, "contact_and_money_between", between):
            out = chat_identity.passages(Conn(), "c", "Did Mateo Ruiz ever call or message Desmond Okafor?")
        self.assertEqual(len(out), 1)
        self.assertTrue(seen["suggestions"], "chat must count the suggested identities")
        self.assertIn("2 calls, 6 messages", out[0]["text"])
        self.assertIn("no person has linked", out[0]["text"])
        self.assertIn("Mateo Ruiz", out[0]["metadata"]["filename"])
        self.assertTrue(out[0]["metadata"]["no_cite"], "a count has no file to cite; a doc:// link would open nothing")

    def test_zero_between_their_numbers_says_no_and_a_similar_name_elsewhere_is_not_them(self):
        def between(conn, case, **k):
            return {"label_line": "No calls, messages, emails or payments in this period",
                    "communication_through_suggested": {"calls": 0, "messages": 0, "emails": 0, "basis": "suggestion"},
                    "suggested_pairs": [{"a": "+1 410-555-0141", "b": "+1 443-555-0112"}]}
        with patch.object(PC, "contact_and_money_between", between):
            out = chat_identity.passages(Conn(), "c", "Did Mateo Ruiz ever call or message Desmond Okafor?")
        t = out[0]["text"]
        self.assertIn("the answer is no", t)
        self.assertIn("+1 443-555-0112", t)
        self.assertIn("similar name or nickname", t)

    def test_one_name_or_none_gives_no_passage(self):
        self.assertEqual(chat_identity.passages(Conn(), "c", "What did Mateo Ruiz say about the trailer?"), [])
        self.assertEqual(chat_identity.passages(Conn(), "c", "Who owns the trailer?"), [])

    def test_unreadable_pair_is_skipped_not_fatal(self):
        def boom(*a, **k):
            raise RuntimeError("x")
        with patch.object(PC, "contact_and_money_between", boom):
            self.assertEqual(chat_identity.passages(Conn(), "c", "Mateo Ruiz and Desmond Okafor"), [])

    def test_rag_stage_is_wired_before_phone_windows_are_used(self):
        import os
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        src = open(os.path.join(here, "services", "rag_service.py"), encoding="utf-8").read()
        self.assertIn("_phone_contact_passages(question, case_id, debug_log)", src)
        self.assertEqual(src.count('metadata.get("no_cite")'), 2)  # the context's Cite line and the source list


if __name__ == "__main__":
    unittest.main()
