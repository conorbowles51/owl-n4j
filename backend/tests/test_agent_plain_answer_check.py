"""The agent's answer reaches the investigator in plain words (lx-agentlive C).

A live answer (run 8df85211, 8 Nov 2026) opened with proof-class codes, a field name with its count and a tool call.
These tests fail on the code before services.agent.plain_answer: nothing rewrote an answer, the finalizer's prompt
had no plain-words rule, and neither service path recorded a plain_check.
"""
from unittest.mock import patch
import re
import unittest

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from services.agent import plain_answer as P
from services.agent.workflows import registered_tool_names

# An excerpt of the live answer of run 8df85211-3495-494d-835d-48d9bd9e401a, as stored.
LIVE = (
    "## Hidden assets — Jose Alejandro Reyes Zeind\n\n"
    "**Proof-class scope:** The \"verified\" population is empty in this case. Every one of the 27,673 usable imported "
    "payments is admitted at `proof_class` **p3** only, and the verified policy excludes all of them "
    "(`proof_class_not_included: 27673`). There are **no p0–p2 verified rows at all**. The \"verified spending vs "
    "verified income\" comparison therefore cannot be computed with p0–p2 data — it returns zero. I report the "
    "*working* (p3) figures only, clearly labelled, and never present them as \"verified.\"\n\n"
    "**The subject holds no account registered in this case's financial ledger.** "
    "`get_financial_coverage(account_holders=[\"Jose Alejandro Reyes Zeind\"])` returns zero accounts, zero periods, "
    "zero payments.\n\n"
    "1. **Santander — CLABE `014790605468140368`** (also printed as account **65504624034**, user 21261814), e.g. "
    "[2026-07-31, MXN 490,853.18](txn://69d98f64-7f48-4f23-81d2-8d69ed97385f). The printed account header shows "
    "\"Saldo Inicial: $7,493,948…\" at [02 ARRENDO SANTANDER MOVIMIENTOS A FEB 24.pdf, p.1]"
    "(doc://02006956-f000-4d1a-ad9a-5fb88a97dfa8/1).\n\n"
    "**Not determinable with verified rows: none exist.** The verified analysis "
    "`analyze_financial_transactions(population=\"verified\")` returns `total_matching: 0`, with "
    "`proof_class_not_included: 27673`. There are no p0–p2 payments to compare.\n\n"
    "| MXN credit_card | 5,022,142 | 382,931 | +4,639,211 |\n"
    "| `propose_entity` (Account) | Santander `014790605468140368` (acct 65504624034) | Recorded, pending: "
    "**6f0d53c5-1c13-4293-a4b5-28c7f473989f** |\n\n"
    "- Every counterparty reading is a **processor/model reading** (`from_name`/`to_name`). No phone identity is "
    "linked to him (`get_person_phones` returns 0).\n"
    "- **Verified income against verified spending (population=verified):** *ran, returned no data* — the verified "
    "population is empty (all rows are p3, none p0–p2). Working population summarized above.\n"
)

CODE = re.compile(r"(?<![\w./:#\-])[pP][0-4](?![\w\-])")
LINKS = re.compile(r"\]\(([^)]*)\)")


def leaks(text):
    """Internal terms left in text outside its citation links."""
    bare = re.sub(r"\[[^\]]*\]\([^)]*\)", "", text)
    found = CODE.findall(bare) + re.findall(r"(?i)proof[-_ ]class|population", bare)
    found += [n for n in registered_tool_names() if re.search(r"(?<![\w])%s(?![\w])" % n, bare)]
    found += [f for f in P.FIELD_WORDS if re.search(r"(?<![\w])%s(?![\w])" % f, bare)]
    return found


class PlainAnswerTests(unittest.TestCase):
    def test_the_live_answer_is_rewritten_and_keeps_every_citation_and_number(self):
        self.assertTrue(leaks(LIVE))  # the fixture is the leak
        out, check = P.plain(LIVE)
        self.assertEqual(leaks(out), [])
        self.assertEqual(LINKS.findall(out), LINKS.findall(LIVE))
        for kept in ("`014790605468140368`", "65504624034", "21261814", "27,673", "27673",
                     "**6f0d53c5-1c13-4293-a4b5-28c7f473989f**", "Jose Alejandro Reyes Zeind",
                     "[02 ARRENDO SANTANDER MOVIMIENTOS A FEB 24.pdf, p.1](doc://02006956-f000-4d1a-ad9a-5fb88a97dfa8/1)"):
            self.assertIn(kept, out)
        self.assertIn("**What could be checked:** The set of verified payments is empty", out)
        self.assertIn("admitted at check status **left out of verified totals (read from a PDF statement, which stays out by rule even when it balances, or its checks are incomplete)** only", out)
        self.assertIn("(left out of verified totals (read from a PDF statement, or not fully checked): 27673)", out)
        self.assertIn("**no verified rows at all**", out)
        self.assertIn("The “Checked financial coverage” step (account holders: Jose Alejandro Reyes Zeind) "
                      "returns zero accounts", out)
        self.assertIn("“Analysed imported payments” step (verified payments only) returns payments matching: 0",
                      out)
        self.assertIn("(payer name/payee name)", out)
        self.assertIn("| MXN credit card |", out)
        self.assertGreater(check["rewritten"], 20)
        self.assertEqual(check["flagged"], [])

    def test_a_clean_answer_is_unchanged(self):
        clean = ("Between 1 and 31 March the account received 12 payments ([3 Mar payment](txn://1b2c), "
                 "[statement.pdf, p.3](doc://9f/3)). None could be checked against the statement's printed balances, "
                 "so the figures are as read and labelled unverified. CLABE `014790605468140368`.")
        self.assertEqual(P.plain(clean), (clean, {"available": True, "rewritten": 0, "terms": {}, "flagged": []}))

    def test_codes_inside_ids_links_handles_and_file_names_are_not_words(self):
        text = ("Record ABC-p3 and ref p3x, [file.pdf, p3](doc://ab/3), rec://p3-77 and "
                "<https://x.test/p2>, mail jose_reyes@mail.test, @get_trades_fan, file my_notes.pdf, "
                "code `p3_backup` and ```\nproof_class = p3\n```")
        out, check = P.plain(text)
        self.assertEqual(out, text)
        self.assertEqual(check["rewritten"], 0)
        flagged = {f["text"] for f in check["flagged"]}
        self.assertIn("p3_backup", flagged)  # left as written, and said
        self.assertTrue({"p3", "proof_class"} & flagged)  # a code inside a code block or link label is flagged

    def test_every_registered_tool_is_named_in_words(self):
        tools = registered_tool_names()
        self.assertGreater(len(tools), 50)
        for name in sorted(tools):
            with self.subTest(name=name):
                out, check = P.plain("I used %s and then `%s(limit=5)`." % (name, name))
                self.assertNotIn(name, out)
                self.assertIn("step", out)
                self.assertIn("limit: 5", out)
                self.assertEqual(check["terms"], {"tool name": 1, "tool call": 1})

    def test_a_new_tool_is_covered_through_the_registry(self):
        with patch.object(P, "_tool_names", return_value=frozenset({"get_brand_new_reading"})):
            out, _ = P.checked("Ran get_brand_new_reading(account_id=\"a1\").")
        self.assertEqual(out, "Ran the “Get brand new reading” step (account id: a1).")

    def test_unknown_field_names_are_flagged_not_dropped(self):
        out, check = P.plain("The result had `weird_field: 3` and some_other_thing.")
        self.assertEqual(out, "The result had `weird_field: 3` and some_other_thing.")
        self.assertEqual({f["text"] for f in check["flagged"]}, {"weird_field: 3", "some_other_thing"})

    def test_a_failed_check_keeps_the_answer_and_says_so(self):
        with patch.object(P, "plain", side_effect=RuntimeError("x")), self.assertLogs(P.log, level="ERROR"):
            out, check = P.checked("p3 rows")
        self.assertEqual(out, "p3 rows")
        self.assertFalse(check["available"])


class _Model:
    """Calls no tool and answers; records every system prompt, the finalizer's apart."""

    def __init__(self):
        self.loop_prompts, self.final_prompts = [], []

    def bind_tools(self, tools):
        owner = self

        class Bound:
            def invoke(self, messages):
                owner.loop_prompts.append(messages[0].content)
                return AIMessage(content="", tool_calls=[{"id": "c1", "name": "get_case_overview", "args": {}}]) \
                    if len(owner.loop_prompts) == 1 else AIMessage(content="draft")

        return Bound()

    def invoke(self, messages):
        self.final_prompts.append(next(m.content for m in messages if isinstance(m, SystemMessage)))
        return AIMessage(content="final")


class _Overview:
    name = "get_case_overview"

    def invoke(self, args):
        return {"result_id": "r1", "summary": "ok", "data": {}}


class PromptRuleTests(unittest.TestCase):
    def test_finalizer_and_tool_loop_prompts_carry_the_plain_words_rule(self):
        from services.agent.graph import AgentGraphRunner
        for path in ("invoke", "stream"):
            with self.subTest(path=path):
                runner = object.__new__(AgentGraphRunner)
                runner.base_model = _Model()
                runner.model_id = "m"
                with patch("services.agent.graph.make_agent_tools", return_value=[_Overview()]):
                    kw = dict(case_id="c", messages=[HumanMessage(content="q")])
                    list(runner.stream(**kw)) if path == "stream" else runner.invoke(**kw)
                final = runner.base_model.final_prompts[0]
                self.assertIn(P.PROMPT_RULE, final)
                for words in ("plain words", "p3 is not fully checked", "proof_class_not_included",
                              "checked against the statements' printed balances", "not which tool you called"):
                    self.assertIn(words, final)
                self.assertIn("never write a check-status code (p0 to p4)", runner.base_model.loop_prompts[0])


try:
    from tests.test_agent_run_record import RunRecordFixture
except Exception:  # noqa: BLE001 - the service tests need the ledger fixture's packages
    RunRecordFixture = None


if RunRecordFixture is not None:
    class ServicePathTests(RunRecordFixture):
        """Both service paths store and return the answer in plain words, and record what was done."""

        def run_service(self, path):
            from types import SimpleNamespace
            from services.agent import service as svc
            from services.agent.schemas import AgentMessageRequest
            from postgres.models.agent import AgentRun
            result = {"answer": LIVE, "tool_trace": [], "artifacts": [], "usage": None}

            class FakeRunner:
                def __init__(self, **_k):
                    pass

                def spent_so_far(self):
                    return None

                def stream(self, **_k):
                    yield {"type": "final", "result": result}

                def invoke(self, **_k):
                    return result

            mandate = SimpleNamespace(override=None, block="")
            with patch.object(svc, "check_case_access"), \
                    patch.object(svc, "get_workload_model", return_value=("deepseek", "deepseek-v4-pro")), \
                    patch.object(svc, "get_provider_api_key", return_value="k"), \
                    patch.object(svc, "AgentGraphRunner", FakeRunner), \
                    patch.object(svc.mandate_context_service, "resolve", return_value=mandate), \
                    patch.object(svc.mandate_context_service, "active_version", return_value=None), \
                    patch.object(svc.mandate_context_service, "metadata", return_value={}), \
                    patch.object(svc.system_log_service, "log"), \
                    patch.object(svc.AgentService, "_proposal_feedback", return_value=None), \
                    patch.object(svc.storage, "check_case_access"):
                request = AgentMessageRequest(message="Hidden assets?", case_id=self.fx.case.id)
                if path == "stream":
                    out = list(svc.agent_service.stream_message(db=self.fx.db, user=self.fx.user, request=request))
                    self.assertEqual(out[-1]["type"], "done", out[-1])
                    answer, run_id = out[-1]["response"]["answer"], out[-1]["response"]["run_id"]
                else:
                    response = svc.agent_service.handle_message(db=self.fx.db, user=self.fx.user, request=request)
                    answer, run_id = response.answer, response.run_id
            run = self.fx.db.get(AgentRun, __import__("uuid").UUID(str(run_id)))
            return answer, run

        def test_both_paths_store_and_return_plain_words(self):
            for path in ("stream", "handle"):
                with self.subTest(path=path):
                    answer, run = self.run_service(path)
                    self.assertEqual(leaks(answer), [])
                    self.assertEqual(run.final_answer, answer)
                    self.assertEqual(LINKS.findall(answer), LINKS.findall(LIVE))
                    check = run.extra_metadata["plain_check"]
                    self.assertTrue(check["available"])
                    self.assertGreater(check["rewritten"], 20)
                    self.assertIn("citation_check", run.extra_metadata)


if __name__ == "__main__":
    unittest.main()


class CodeBeforeANounTests(unittest.TestCase):
    """lx-plainwords m110900300316083: a live answer (agent_messages afcba983, 8 Nov 23:34) kept 'admitted P3
    readings'; the code before a noun becomes a clause after it, so the sentence still reads."""

    def test_the_live_sentence_speaks_without_the_code(self):
        from services.agent.plain_answer import checked
        out, check = checked("Working totals include admitted P3 readings; 11 rows were excluded as rejected.",
                             tools=lambda: frozenset())
        self.assertNotRegex(out, r"(?i)\bp3\b")
        self.assertTrue(out.startswith("Working totals include readings left out of verified totals ("))
        self.assertTrue(out.endswith("; 11 rows were excluded as rejected."))
        self.assertEqual(check["rewritten"], 1)
