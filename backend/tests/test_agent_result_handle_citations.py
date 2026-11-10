"""A tool result's handle never reaches the answer as a citation (lx-demo m11102319473165: demo case Q3, 10 Nov 2026,
cited all 7 sources as doc://res_<hex>, which the case check marks 'Not in this case')."""
from unittest.mock import patch
import unittest

from langchain_core.messages import AIMessage, HumanMessage

from services.agent.citations import replace_result_handles

REC = "rec://6f1c2a7e-0d4b-4c39-9a51-2b8e7f3d1c40"
RESULTS = {
    "res_ec9bf07d95aa": {"phones": [{"label": "Phone 1", "records": 120}]},
    "res_3b42e8f87e7d": {"items": [{"rec": REC, "kind": "contact"}]},
    "res_b77e6e3cea71": {"items": [{"rec": REC}, {"rec": "rec://0a1b2c3d-0000-4000-8000-000000000001"}]},
}
ANSWER = ("Phone 1 is Mateo's ([phone coverage](doc://res_ec9bf07d95aa)); he is a contact ([Mateo Ruiz]"
          "(doc://res_3b42e8f87e7d)); 0 calls ([pair](rec://res_b77e6e3cea71)); kept [12 Mar](txn://abc).")


class ReplaceTests(unittest.TestCase):
    def test_handle_becomes_the_results_one_source_or_plain_text(self):
        out = replace_result_handles(ANSWER, RESULTS)
        self.assertNotIn("res_", out)
        self.assertIn("(phone coverage)", out)
        self.assertIn("[Mateo Ruiz](%s)" % REC, out)
        self.assertIn("(pair)", out)
        self.assertIn("[12 Mar](txn://abc)", out)

    def test_unknown_handle_is_unlinked_and_text_without_one_is_unchanged(self):
        self.assertEqual(replace_result_handles("see [x](doc://res_0123456789ab)", {}), "see x")
        self.assertEqual(replace_result_handles("plain [a](doc://f.pdf/2)", RESULTS), "plain [a](doc://f.pdf/2)")


class _Model:
    def bind_tools(self, tools):
        calls = []

        class Bound:
            def invoke(self, messages):
                calls.append(1)
                return AIMessage(content="", tool_calls=[{"id": "c1", "name": "get_case_overview", "args": {}}]) \
                    if len(calls) == 1 else AIMessage(content="draft")
        return Bound()

    def invoke(self, messages):
        return AIMessage(content=ANSWER)


class _Tool:
    name = "get_case_overview"

    def invoke(self, args):
        return {"result_id": "res_3b42e8f87e7d", "summary": "ok", "data": RESULTS["res_3b42e8f87e7d"]}


class GraphPathTests(unittest.TestCase):
    def test_both_paths_store_no_result_handle(self):
        from services.agent.graph import AgentGraphRunner
        for path in ("invoke", "stream"):
            with self.subTest(path=path):
                runner = object.__new__(AgentGraphRunner)
                runner.base_model = _Model()
                runner.model_id = "m"
                with patch("services.agent.graph.make_agent_tools", return_value=[_Tool()]):
                    kw = dict(case_id="c", messages=[HumanMessage(content="q")])
                    if path == "stream":
                        answer = [e for e in runner.stream(**kw) if e.get("type") == "final"][-1]["result"]["answer"]
                    else:
                        answer = runner.invoke(**kw)["answer"]
                self.assertNotIn("res_", answer)
                self.assertIn("[Mateo Ruiz](%s)" % REC, answer)


if __name__ == "__main__":
    unittest.main()
