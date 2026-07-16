import unittest

from services.agent.graph import _execute_tool_calls
from services.agent.tool_policy import tool_call_signature


class FakeTool:
    def __init__(self):
        self.calls: list[dict] = []

    def invoke(self, args):
        self.calls.append(args)
        return {"summary": "mutated", "data": {"ok": True}}


class AgentConfirmationGateTests(unittest.TestCase):
    def test_mutation_tool_without_approval_is_blocked(self):
        tool = FakeTool()

        result = _execute_tool_calls(
            tool_calls=[{"id": "call_1", "name": "dangerous_write", "args": {"target": "a"}}],
            tools_by_name={"dangerous_write": tool},
            state={"tool_iterations": 0},
        )

        self.assertEqual(tool.calls, [])
        self.assertEqual(result["tool_trace"][0]["status"], "error")
        self.assertEqual(result["clarifications"][0]["context"]["reason"], "tool_confirmation_required")
        self.assertEqual(result["clarifications"][0]["context"]["tool_name"], "dangerous_write")

    def test_matching_approval_signature_executes_once(self):
        tool = FakeTool()
        args = {"target": "a"}
        signature = tool_call_signature("dangerous_write", args)

        result = _execute_tool_calls(
            tool_calls=[
                {"id": "call_1", "name": "dangerous_write", "args": args},
                {"id": "call_2", "name": "dangerous_write", "args": args},
            ],
            tools_by_name={"dangerous_write": tool},
            state={"tool_iterations": 0},
            approved_tool_signature=signature,
        )

        self.assertEqual(tool.calls, [args])
        self.assertEqual(result["tool_trace"][0]["status"], "success")
        self.assertEqual(result["tool_trace"][1]["status"], "error")
        self.assertTrue(result["approved_tool_signature_consumed"])

    def test_approval_for_one_call_does_not_authorize_different_args(self):
        tool = FakeTool()

        result = _execute_tool_calls(
            tool_calls=[{"id": "call_1", "name": "dangerous_write", "args": {"target": "b"}}],
            tools_by_name={"dangerous_write": tool},
            state={"tool_iterations": 0},
            approved_tool_signature=tool_call_signature("dangerous_write", {"target": "a"}),
        )

        self.assertEqual(tool.calls, [])
        self.assertEqual(result["tool_trace"][0]["status"], "error")
        self.assertEqual(result["clarifications"][0]["context"]["signature"], tool_call_signature("dangerous_write", {"target": "b"}))


if __name__ == "__main__":
    unittest.main()
