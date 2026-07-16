import unittest

from services.agent.tool_policy import (
    READ_ONLY_TOOL_NAMES,
    requires_confirmation,
    tier_for_tool,
    tool_call_signature,
)
from services.agent.tools import AgentToolContext, make_agent_tools


class AgentToolPolicyTests(unittest.TestCase):
    def test_read_only_allowlist_matches_registered_tools(self):
        tools = make_agent_tools(AgentToolContext(case_id="case-1"))

        self.assertEqual({tool.name for tool in tools}, set(READ_ONLY_TOOL_NAMES))

    def test_unregistered_tool_fails_closed_as_mutation(self):
        self.assertEqual(tier_for_tool("delete_case"), "mutation")
        self.assertTrue(requires_confirmation("delete_case"))

    def test_signature_is_scoped_to_exact_name_and_arguments(self):
        first = tool_call_signature("dangerous_write", {"case_id": "case-1", "value": 1})
        reordered = tool_call_signature("dangerous_write", {"value": 1, "case_id": "case-1"})
        changed = tool_call_signature("dangerous_write", {"case_id": "case-1", "value": 2})

        self.assertEqual(first, reordered)
        self.assertNotEqual(first, changed)


if __name__ == "__main__":
    unittest.main()
