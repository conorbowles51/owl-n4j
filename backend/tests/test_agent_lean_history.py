"""Lean runs (lx-agentlive item B): each tool result reaches the model whole once, then as a digest that can be
re-opened; a repeated result is a pointer; the tool definitions drop only the repeated null alternative.

The ledger run cache is tested in test_agent_ledger_run_cache.

The prompt-size test replays the shape of live run 8df85211 (BNB2, 7 tool batches, then a draft and the finalizer)
with stub tools returning payloads of the sizes measured in that run. On the code before this change every request
re-sent every earlier result whole and the fixture's tool messages came to 1,049,853 characters (measured); with
this change 376,336 (each result whole once to the agent, then a digest, and every result whole to the finalizer)."""
import json
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from services.agent import lean_history
from services.agent.graph import AgentGraphRunner
from services.agent.lean_history import (DIGEST_MARK, RepeatedResults, digest_content, lean_messages,
                                         tool_definitions)
from services.agent.tools import AgentToolContext, make_agent_tools

CASE = "00000000-0000-0000-0000-0000000000aa"


def ledger_groups(months=100):
    """A month grouping like analyze_financial_transactions on BNB2 (about 50,000 characters for 100 months)."""
    items = [dict(currency="MXN", account_type="checking", group="2019-%02d-%03d" % (1 + i % 12, i), currency_exponent=2,
                  transaction_count=10 + i, credits_minor=str(100000 + i), debits_minor=str(90000 + i),
                  net_minor=str(10000), account_count=1, source_document_count=2, statement_period_count=1, bank_count=1,
                  open_judgement_calls=dict(available=True, open_calls=i % 2, payments_with_open_calls=i % 2,
                                            payments=10 + i, sentence="No open judgement call touches these payments."))
             for i in range(months)]
    return dict(schema="loupe.agent.financial_ledger/1", view="groups", group_by="month", available=True,
                revision="r" * 64, ledger_revision="l" * 64, total_matching=months, returned=months, has_more=False,
                items=items, totals=dict(MXN=dict(credits_minor="1", debits_minor="2")), limitation="L" * 600)


def coverage(accounts=50):
    """A coverage page like get_financial_coverage on BNB2 (about 56,000 characters for 50 periods)."""
    items = [dict(account_id="acc-%03d" % i, account_number="014790605468140%03d" % i, holder="Holder %d" % i,
                  bank="Bank %d" % i, period=dict(id="p-%d" % i, start="2025-01-01", end="2025-01-31",
                  source=dict(filename="statement %d.pdf" % i, evidence_href="/cases/x/evidence?file=%s" % ("f" * 36),
                              financial_review_href="/cases/x/financial?reviewFile=%s" % ("f" * 36),
                              note="n" * 500))) for i in range(accounts)]
    return dict(schema="loupe.agent.financial_ledger/1", view="coverage", available=True, total_matching=1445,
                returned=accounts, has_more=True, next_offset=accounts, items=items, coverage=dict(registered=82))


def hits(count):
    return dict(results=[dict(filename="doc %d.pdf" % i, page=i, text="t" * 900) for i in range(count)], count=count)


# The live run's batches (agent_tool_calls of 8df85211), each call's payload at its measured size class.
BATCHES = [
    [("leads", lambda: dict(items=[], count=0))],
    [("coverage", coverage), ("matches", lambda: dict(items=[], count=0)), ("mentions", lambda: hits(9))],
    [("graph", lambda: hits(4)), ("search", lambda: hits(28)), ("dossier", lambda: dict(items=[1]))],
    [("words", lambda: hits(22)), ("words", lambda: hits(11)), ("phones", lambda: dict(items=[]))],
    [("coverage", coverage), ("coverage", lambda: coverage(2)), ("groups", lambda: ledger_groups(2))],
    [("groups", ledger_groups), ("between", lambda: dict(available=False))],
    [("propose", lambda: dict(proposal="p" * 2500)), ("propose", lambda: dict(proposal="q" * 2500))],
]
DRAFT = "Accounts 014790605468140368 (Santander) and 044180256002444284 (Scotiabank). " + "Draft. " * 300


class Args(BaseModel):
    pass


def stub_tools(context):
    names = {}
    for batch in BATCHES:
        for name, make in batch:
            names.setdefault(name, make)
    page = [t for t in make_agent_tools(context) if t.name == "read_tool_result_page"]
    # The same name may return different sizes per call: each call takes the next maker for its name.
    makers = {}
    for batch in BATCHES:
        for name, make in batch:
            makers.setdefault(name, []).append(make)

    def next_payload(name):
        queue = makers[name]
        return (queue.pop(0) if len(queue) > 1 else queue[0])()
    return [StructuredTool.from_function(func=(lambda _n=name: context.result(_n, next_payload(_n),
                                                                              summary="Read %s." % _n)),
                                         name=name, description="Stub %s." % name, args_schema=Args)
            for name in names] + page


class Recorder:
    """Scripted model: the live run's batches, then a draft; records every request (agent turns and finalizer)."""

    def __init__(self, batches, extra=None):
        self.batches, self.extra, self.requests, self.turn = batches, extra or {}, [], 0

    def bind_tools(self, tools):
        owner = self

        class Bound:
            def invoke(self, messages):
                owner.requests.append(("agent", list(messages)))
                turn, owner.turn = owner.turn, owner.turn + 1
                if turn in owner.extra:
                    return owner.extra[turn](messages)
                index = turn - sum(1 for t in owner.extra if t < turn)
                if index < len(owner.batches):
                    return AIMessage(content="", tool_calls=[
                        {"id": "c%d_%d" % (index, j), "name": name, "args": {}}
                        for j, (name, _make) in enumerate(owner.batches[index])])
                return AIMessage(content=DRAFT)
        return Bound()

    def invoke(self, messages):
        self.requests.append(("finalizer", list(messages)))
        return AIMessage(content="Final answer.")


def run(recorder):
    runner = object.__new__(AgentGraphRunner)
    runner.base_model, runner.model_id, runner.provider = recorder, "deepseek-v4-pro", "deepseek"
    with patch("services.agent.graph.make_agent_tools", side_effect=stub_tools):
        return runner.invoke(case_id=CASE, messages=[HumanMessage(content="Which accounts?")])


def tool_chars(messages):
    return sum(len(m.content) for m in messages if isinstance(m, ToolMessage))


# Tool-message characters across every model request of the 7-batch fixture. Before this change: 1,049,853.
CEILING = 400_000


class LeanRunTests(unittest.TestCase):
    def test_seven_batch_run_stays_under_the_prompt_ceiling(self):
        recorder = Recorder(BATCHES)
        run(recorder)
        self.assertEqual([kind for kind, _ in recorder.requests], ["agent"] * 8 + ["finalizer"])
        total = sum(tool_chars(messages) for _, messages in recorder.requests)
        self.assertLess(total, CEILING)

    def test_each_result_is_sent_whole_on_the_next_turn(self):
        recorder = Recorder(BATCHES)
        run(recorder)
        for turn in range(1, 8):
            latest = [m for m in recorder.requests[turn][1] if isinstance(m, ToolMessage)][-len(BATCHES[turn - 1]):]
            for message in latest:
                self.assertNotIn(DIGEST_MARK, json.loads(message.content))

    def test_a_digest_is_the_same_text_on_every_later_turn(self):
        recorder = Recorder(BATCHES)
        run(recorder)
        seen = {}
        for _, messages in recorder.requests[2:8]:
            for message in messages:
                if isinstance(message, ToolMessage) and DIGEST_MARK in message.content[:40]:
                    self.assertEqual(seen.setdefault(message.tool_call_id, message.content), message.content)
        self.assertTrue(seen)

    def test_the_finalizer_gets_every_result_whole_by_default(self):
        recorder = Recorder(BATCHES)
        run(recorder)
        kind, messages = recorder.requests[-1]
        self.assertEqual(kind, "finalizer")
        tools = [json.loads(m.content) for m in messages if isinstance(m, ToolMessage)]
        self.assertEqual(len(tools), sum(len(b) for b in BATCHES))
        self.assertFalse([t for t in tools if DIGEST_MARK in t])
        groups = [t for t, m in zip(tools, [m for m in messages if isinstance(m, ToolMessage)]) if m.name == "groups"]
        # Whole: the model's view of the result (readable amounts beside the minor figures), nothing dropped.
        from services.agent.model_payloads import model_view
        self.assertEqual(groups[-1]["data"], model_view(ledger_groups())["data"])

    def test_the_lean_finalizer_gets_the_draft_the_last_batch_and_the_ledger_figures(self):
        recorder = Recorder(BATCHES)
        with patch.dict("os.environ", {lean_history.LEAN_FINALIZER_SETTING: "1"}):
            run(recorder)
        kind, messages = recorder.requests[-1]
        self.assertEqual(kind, "finalizer")
        text = "\n".join(str(m.content) for m in messages)
        self.assertIn("014790605468140368", text)
        self.assertIn("044180256002444284", text)
        groups = [json.loads(m.content) for m in messages if isinstance(m, ToolMessage) and m.name == "groups"]
        figures = groups[-1]["facts"]["group_figures"]
        self.assertEqual(len(figures), 100)
        self.assertEqual(figures[5], {"group": "2019-06-005", "currency": "MXN", "account_type": "checking",
                                      "currency_exponent": 2, "transaction_count": 15, "credits_minor": "100005",
                                      "credits": "MXN 1,000.05", "debits_minor": "90005", "debits": "MXN 900.05",
                                      "net_minor": "10000", "net": "MXN 100.00", "account_count": 1,
                                      "open_judgement_calls": 1})

    def test_without_a_draft_the_finalizer_gets_every_result_whole(self):
        messages = [HumanMessage(content="q"), AIMessage(content="", tool_calls=[{"id": "a", "name": "x", "args": {}}]),
                    ToolMessage(content=json.dumps({"result_id": "r1", "summary": "s", "data": {"rows": ["z" * 5000]}}),
                                tool_call_id="a", name="x"),
                    AIMessage(content="", tool_calls=[{"id": "b", "name": "x", "args": {}}]),
                    ToolMessage(content="{}", tool_call_id="b", name="x"),
                    AIMessage(content="")]
        with patch.dict("os.environ", {lean_history.LEAN_FINALIZER_SETTING: "1"}):
            self.assertIs(lean_history.finalizer_messages(messages), messages)
            self.assertIn(DIGEST_MARK, lean_messages(messages)[2].content)
            with_draft = messages[:-1] + [AIMessage(content="Draft.")]
            self.assertIn(DIGEST_MARK, lean_history.finalizer_messages(with_draft)[2].content)
        self.assertIs(lean_history.finalizer_messages(with_draft), with_draft)

    def test_a_digested_result_reopens_whole(self):
        reopened = {}

        def reopen(messages):
            digests = [json.loads(m.content) for m in messages
                       if isinstance(m, ToolMessage) and DIGEST_MARK in m.content[:40] and m.name == "coverage"]
            reopened["id"] = digests[0][DIGEST_MARK]
            return AIMessage(content="", tool_calls=[{"id": "reopen", "name": "read_tool_result_page",
                                                      "args": {"result_id": digests[0][DIGEST_MARK]}}])
        recorder = Recorder(BATCHES, extra={3: reopen})
        run(recorder)
        message = [m for m in recorder.requests[4][1] if isinstance(m, ToolMessage) and m.tool_call_id == "reopen"][0]
        payload = json.loads(message.content)
        self.assertEqual(payload["data"]["page_of"], reopened["id"])
        self.assertEqual(payload["data"]["data"], coverage())
        self.assertNotIn("_paging", payload["data"])

    def test_the_page_tool_still_reads_a_stated_page(self):
        context = AgentToolContext(case_id=CASE, page_budget_chars=12_000)
        context.model_views["res_1"] = {"data": {"rows": [{"k": i, "t": "z" * 900} for i in range(25)]}}
        tool = {t.name: t for t in make_agent_tools(context)}["read_tool_result_page"]
        page = tool.invoke({"result_id": "res_1", "path": ["data", "rows"], "offset": 3})["data"]
        self.assertEqual(page["items"][0]["k"], 3)
        whole = tool.invoke({"result_id": "res_1"})["data"]
        self.assertEqual(len(whole["data"]["rows"]), len([r for r in whole["data"]["rows"]]))
        self.assertIn("_paging", whole)  # larger than the budget: a stated page, never a silent cut
        self.assertEqual(whole["_paging"][0]["total"], 25)

    def test_small_messages_and_digests_are_never_digested(self):
        self.assertIsNone(digest_content(json.dumps({"result_id": "r", "summary": "s", "data": {"a": 1}})))
        digest = digest_content(json.dumps({"result_id": "r", "summary": "s", "data": {"rows": ["x" * 3000]}}))
        self.assertIsNone(digest_content(digest + " " * 3000))
        self.assertIsNone(digest_content(json.dumps({"summary": "no id", "data": {"rows": ["x" * 3000]}})))

    def test_a_digest_keeps_short_facts_paging_and_the_reopen_call(self):
        payload = {"result_id": "res_9", "summary": "Read 50 of 1445.", "_paging": [{"total": 9}],
                   "data": dict(coverage(), totals={"MXN": {"credits_minor": "5"}})}
        digest = json.loads(digest_content(json.dumps(payload)))
        self.assertEqual(digest[DIGEST_MARK], "res_9")
        self.assertEqual(digest["facts"]["total_matching"], 1445)
        self.assertEqual(digest["facts"]["totals"], {"MXN": {"credits_minor": "5"}})
        self.assertEqual(digest["not_in_digest"]["items"], "50 items")
        self.assertEqual(digest["_paging"], [{"total": 9}])
        self.assertIn("read_tool_result_page", digest["note"])

    def test_a_repeated_result_is_a_pointer(self):
        repeated = RepeatedResults()
        first = {"result_id": "res_a", "summary": "s", "data": coverage()}
        self.assertEqual(json.loads(repeated.content(first))["data"], coverage())
        pointer = json.loads(repeated.content(dict(first, result_id="res_b")))
        self.assertEqual((pointer["result_id"], pointer["same_as"]), ("res_b", "res_a"))
        different = json.loads(repeated.content(dict(first, result_id="res_c", data=coverage(3))))
        self.assertNotIn("same_as", different)

    def test_tool_definitions_keep_every_description_and_required_field(self):
        from langchain_core.utils.function_calling import convert_to_openai_tool
        tools = make_agent_tools(AgentToolContext(case_id=CASE, proposer=dict(can_propose=True)))
        full = [convert_to_openai_tool(t) for t in tools]
        lean = tool_definitions(tools)
        self.assertLess(len(json.dumps(lean)), len(json.dumps(full)))

        def descriptions(value):
            if isinstance(value, dict):
                own = [value["description"]] if isinstance(value.get("description"), str) else []
                return own + [d for v in value.values() for d in descriptions(v)]
            if isinstance(value, list):
                return [d for v in value for d in descriptions(v)]
            return []
        for before, after in zip(full, lean):
            self.assertEqual(before["function"]["name"], after["function"]["name"])
            self.assertEqual(sorted(descriptions(before)), sorted(descriptions(after)))
            self.assertEqual(before["function"]["parameters"].get("required"),
                             after["function"]["parameters"].get("required"))
            self.assertEqual(set(before["function"]["parameters"]["properties"]),
                             set(after["function"]["parameters"]["properties"]))
        coverage_tool = {d["function"]["name"]: d for d in lean}["get_financial_coverage"]
        self.assertEqual(coverage_tool["function"]["parameters"]["properties"]["start_date"],
                         {"format": "date", "type": "string"})

    def test_a_chat_model_is_bound_to_the_lean_definitions(self):
        from langchain_openai import ChatOpenAI
        from services.agent.lean_history import tools_for_binding
        tools = make_agent_tools(AgentToolContext(case_id=CASE))
        model = ChatOpenAI(model="deepseek-v4-pro", api_key="not-used", base_url="http://127.0.0.1:9")
        self.assertEqual(tools_for_binding(model, tools), tool_definitions(tools))
        self.assertIs(tools_for_binding(Recorder([]), tools), tools)
        bound = model.bind_tools(tools_for_binding(model, tools))
        self.assertEqual(bound.kwargs["tools"], tool_definitions(tools))

    def test_the_system_prompt_is_first_and_unchanged_across_turns(self):
        recorder = Recorder(BATCHES)
        run(recorder)
        prompts = {m.content for _, ms in recorder.requests[:8] for m in ms[:1] if isinstance(m, SystemMessage)}
        self.assertEqual(len(prompts), 1)


if __name__ == "__main__":
    unittest.main()
