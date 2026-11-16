"""lx-agentquick D: every Cypher the prompt or a tool description gives passes the checker that runs it (33 of 188
recorded run_readonly_cypher calls were refused because the prompt taught WITH and UNWIND)."""
import inspect
import os
import re
import unittest
from unittest.mock import patch

from services.agent import graph, tool_errors
from services.agent.cypher_safety import UnsafeCypherError, validate_readonly_cypher

_EXAMPLE = re.compile(r"\b(?:OPTIONAL\s+)?MATCH\s*\(.*?\bRETURN\b.*?(?:\bLIMIT\s+\d+|(?=[\"'\n]|$))", re.S)


def _surfaces():
    out = {"rule lines": graph._cypher_rule_lines(), "example": tool_errors.CYPHER_EXAMPLE}
    for name in dir(tool_errors):
        value = getattr(tool_errors, name)
        if isinstance(value, str) and "MATCH" in value:
            out["tool_errors." + name] = value
    from services.agent.tools import _cypher_description
    out["description"] = _cypher_description()
    for name, fn in inspect.getmembers(graph, inspect.isfunction):
        if "prompt" in name.lower():
            try:
                out["graph." + name] = fn()
            except TypeError:
                pass
    return out


class CypherExamples(unittest.TestCase):
    def test_every_example_given_to_the_model_is_accepted(self):
        for env in ({"LOUPE_AGENT_FIT": ""}, {"LOUPE_AGENT_FIT": "T"}):
            with patch.dict(os.environ, env):
                found = 0
                for where, text in _surfaces().items():
                    for m in _EXAMPLE.finditer(text):
                        found += 1
                        try:
                            validate_readonly_cypher(m.group(0).strip(), limit=50)
                        except UnsafeCypherError as exc:
                            self.fail("%s teaches a query the checker refuses (%s): %s" % (where, exc, m.group(0)))
                self.assertGreaterEqual(found, 1)

    def test_the_prompt_never_teaches_with_or_unwind_as_allowed(self):
        with patch.dict(os.environ, {"LOUPE_AGENT_FIT": ""}):
            lines = graph._cypher_rule_lines()
        self.assertNotIn("MATCH/OPTIONAL MATCH/WITH/UNWIND", lines)
        self.assertIn("No WITH, UNWIND", lines)

    def test_a_literal_list_is_accepted_without_a_switch(self):
        with patch.dict(os.environ, {"LOUPE_AGENT_FIT": ""}):
            validate_readonly_cypher("MATCH (n {case_id: $case_id}) WHERE n.key IN ['a', 'b'] RETURN n.key LIMIT 5")


if __name__ == "__main__":
    unittest.main()
