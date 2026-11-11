"""A result read again is the same result: its own id names the result it was read from, a second whole read and a
repeat of the same page are refused, with or without agent-fit B.

Measured on live 10-11 Nov 2026: runs cd778814, d091677f and b1b87209 (switch B off) each read the newest re-read of
a result already read, 9-12 of their 28 calls, and stopped at the call limit. Every test here fails on the code
before this change."""
import json
import unittest
from unittest.mock import patch

from services.agent.tools import AgentToolContext, make_agent_tools

CASE = "00000000-0000-0000-0000-0000000000ac"


class RereadChainTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict("os.environ", {"LOUPE_AGENT_FIT": "W"})  # live: only W on
        env.start()
        self.addCleanup(env.stop)
        self.context = AgentToolContext(case_id=CASE, page_budget_chars=100_000)
        self.context.model_views["res_1"] = {"data": {"items": [{"k": i, "t": "z" * 100} for i in range(42)],
                                                      "count": 42}}
        self.tool = {t.name: t for t in make_agent_tools(self.context)}["read_tool_result_page"]

    def test_reading_the_newest_re_read_whole_is_refused_with_the_digest(self):
        first = self.tool.invoke({"result_id": "res_1"})
        self.assertEqual(len(first["data"]["data"]["items"]), 42)
        second = self.tool.invoke({"result_id": first["result_id"]})
        self.assertEqual(second["data"]["not_read_again"], "res_1")
        self.assertEqual(second["data"]["digest"]["facts"]["count"], 42)
        self.assertNotIn("record_working_notes", second["summary"])
        self.assertNotIn("working_notes", second["data"])
        # the refusal's own id is the same result too
        third = self.tool.invoke({"result_id": second["result_id"]})
        self.assertEqual(third["data"]["not_read_again"], "res_1")

    def test_a_page_of_a_re_read_is_a_page_of_the_first_result_and_is_read_once(self):
        whole = self.tool.invoke({"result_id": "res_1"})
        page = self.tool.invoke({"result_id": whole["result_id"], "path": ["data", "items"]})
        self.assertEqual(page["data"]["page_of"], "res_1")
        self.assertEqual(len(page["data"]["items"]), 42)
        again = self.tool.invoke({"result_id": page["result_id"], "path": ["data", "items"]})
        self.assertEqual(again["data"]["not_read_again"], "res_1")
        self.assertNotIn("items", again["data"])
        self.assertIn("Nothing else remains", again["summary"])

    def test_another_offset_of_the_same_path_is_read(self):
        self.tool.invoke({"result_id": "res_1", "path": ["data", "items"]})
        later = self.tool.invoke({"result_id": "res_1", "path": ["data", "items"], "offset": 40})
        self.assertEqual([x["k"] for x in later["data"]["items"]], [40, 41])

    def test_the_plain_digest_note_says_a_result_is_read_again_once(self):
        from services.agent import lean_history
        self.assertIn("read again in full once", lean_history.DIGEST_NOTE_PLAIN)


if __name__ == "__main__":
    unittest.main()
