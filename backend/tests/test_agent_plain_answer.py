"""Final answers speak plain words: no proof-class codes, field or tool names, or minor units.

Live 8 Nov 2026 (run 8df85211, BNB2) the answer led with "proof_class p3", "proof_class_not_included: 27673" and
"get_financial_coverage(...)" although the finalizer's prompt forbids field and tool names. The finalizer's reply is
now checked and, when it still carries such words, rewritten once; a rewrite that loses a citation is not used.
"""
import unittest

from langchain_core.messages import AIMessage, SystemMessage

from services.agent.graph import _has_jargon
from tests.test_agent_run_record import RunRecordFixture, ScriptedModel

JARGON = ("**Proof-class scope:** every payment is p3 (`proof_class_not_included: 27673`); "
          "`get_financial_coverage(account_holders=[...])` returned 0. See [the row](txn://abc_def).")
PLAIN = ("None of these payments has been checked against printed balances by a person; the accounts check found 0 "
         "accounts. See [the row](txn://abc_def).")


class _RewritingModel(ScriptedModel):
    def __init__(self, steps, answer, rewrite):
        super().__init__(steps, answer)
        self.rewrite, self.rewrites = rewrite, 0

    def invoke(self, messages):
        if isinstance(messages[0], SystemMessage) and messages[0].content.startswith("Rewrite this answer"):
            self.rewrites += 1
            return AIMessage(content=self.rewrite)
        return super().invoke(messages)


class PlainAnswerTests(RunRecordFixture):
    def answer_with(self, answer, rewrite, path):
        from contextlib import contextmanager
        from unittest.mock import patch
        from langchain_core.messages import HumanMessage
        from services.agent.graph import AgentGraphRunner

        runner = object.__new__(AgentGraphRunner)
        runner.base_model = model = _RewritingModel([lambda o: ("get_financial_transactions", {"limit": 2})],
                                                    lambda o: answer, rewrite)
        runner.model_id = "deepseek-v4-pro"

        @contextmanager
        def read_session(*_a, **_k):
            with self.fx.SessionLocal() as session:
                yield session

        kwargs = dict(case_id=str(self.fx.case.id), max_tool_calls=28,
                      messages=[HumanMessage(content="Is verified spending above verified income?")])
        with patch("services.agent.tools._financial_session", read_session):
            result = runner.invoke(**kwargs) if path == "invoke" else list(runner.stream(**kwargs))[-1]["result"]
        return result, model

    def test_answer_with_codes_and_field_names_is_rewritten_in_plain_words(self):
        for path in ("stream", "invoke"):
            result, model = self.answer_with(JARGON, PLAIN, path)
            self.assertEqual(result["answer"], PLAIN, path)
            self.assertEqual(model.rewrites, 1, path)
            self.assertFalse(_has_jargon(result["answer"]))

    def test_plain_answer_is_not_rewritten(self):
        result, model = self.answer_with(PLAIN, "unused", "stream")
        self.assertEqual((result["answer"], model.rewrites), (PLAIN, 0))

    def test_rewrite_that_drops_a_citation_is_not_used(self):
        result, model = self.answer_with(JARGON, "Nothing was checked.", "stream")
        self.assertEqual((result["answer"], model.rewrites), (JARGON, 1))


class JargonDetectionTests(unittest.TestCase):
    def test_codes_fields_tools_and_minor_units_are_jargon(self):
        for text in ("All rows are p3.", "no P0–P2 rows", "P0-P4 codes", "`exclusion_reason` is set",
                     "get_financial_coverage(account_holders=[x])", "proof_class_not_included: 27673",
                     "| Credits (minor) |", "population=verified returned 0"):
            self.assertTrue(_has_jargon(text), text)

    def test_plain_text_pages_links_and_file_names_are_not(self):
        for text in ("See [p.3](doc://02006956/3) of the statement.", "[file](doc://a_b_c/1) page 1",
                     "[ARRENDO_SANTANDER_FEB_24.pdf](doc://x/1)", "Account 65504624034, 12 payments, MXN 490,853.18.",
                     "Statement of 2025-08-28, 4 of 7 months."):
            self.assertFalse(_has_jargon(text), text)


if __name__ == "__main__":
    unittest.main()
