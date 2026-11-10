"""Cache-stable requests (lx-agentcost B): DeepSeek reads a prompt from its cache only up to the end of an earlier
request, so a request must start with the previous one byte for byte.

Measured 10 Nov 2026 with a 30-tool request: appending a turn read the whole earlier request from the cache (8,704
of 12,727 tokens); the same turn with the first result turned into a digest read only the first request (4,736 of
12,789). The fixture is the 7-batch BNB2 shape of test_agent_lean_history."""
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from services.agent import lean_history
from tests.test_agent_lean_history import BATCHES, DRAFT, Recorder, run


def _same(a, b):
    return (type(a), a.content, getattr(a, "tool_call_id", None), getattr(a, "tool_calls", None)) == \
        (type(b), b.content, getattr(b, "tool_call_id", None), getattr(b, "tool_calls", None))


def starts_with(longer, shorter):
    return len(longer) >= len(shorter) and all(_same(a, b) for a, b in zip(longer, shorter))


class PrefixRecorder(Recorder):
    """The scripted model, with ``bind`` (tool_choice) on the tool-bound model as a chat model has."""

    def bind_tools(self, tools):
        bound = super().bind_tools(tools)
        owner = self

        class WithBind:
            def invoke(self, messages):
                return bound.invoke(messages)

            def bind(self, **kwargs):
                owner.final_kwargs = kwargs

                class Final:
                    def invoke(self, messages):
                        owner.requests.append(("finalizer-on-prefix", list(messages)))
                        return AIMessage(content="Final answer.")
                return Final()
        return WithBind()


STABLE = {lean_history.CACHE_STABLE_SETTING: "1"}
BOTH = {**STABLE, lean_history.FINALIZER_ON_AGENT_PREFIX_SETTING: "1"}


class CacheStableTests(unittest.TestCase):
    def test_each_agent_request_starts_with_the_previous_one(self):
        recorder = Recorder(BATCHES)
        with patch.dict("os.environ", STABLE):
            run(recorder)
        agent = [messages for kind, messages in recorder.requests if kind == "agent"]
        self.assertEqual(len(agent), 8)
        for earlier, later in zip(agent, agent[1:]):
            self.assertTrue(starts_with(later, earlier))

    def test_the_default_still_digests(self):
        recorder = Recorder(BATCHES)
        run(recorder)
        agent = [messages for kind, messages in recorder.requests if kind == "agent"]
        self.assertFalse(starts_with(agent[3], agent[2]))

    def test_the_finalizer_on_the_agent_prefix_repeats_the_agents_last_request(self):
        recorder = PrefixRecorder(BATCHES)
        with patch.dict("os.environ", BOTH):
            run(recorder)
        kind, final = recorder.requests[-1]
        self.assertEqual(kind, "finalizer-on-prefix")
        self.assertEqual(recorder.final_kwargs, {"tool_choice": "none"})
        last_agent = [messages for kind, messages in recorder.requests if kind == "agent"][-1]
        self.assertTrue(starts_with(final, last_agent))
        # Then the draft the agent wrote, then the rules and the request.
        self.assertEqual(final[len(last_agent)].content, DRAFT)
        self.assertIsInstance(final[-1], HumanMessage)
        self.assertIn("Write the final answer from the completed tool results.", final[-1].content)
        self.assertIn("Now write the final answer to my question", final[-1].content)
        self.assertEqual(len(final), len(last_agent) + 2)
        from services import writing_standard
        self.assertIn(writing_standard.MARKER, final[0].content)

    def test_the_finalizer_on_the_prefix_still_gets_every_result_whole(self):
        recorder = PrefixRecorder(BATCHES)
        with patch.dict("os.environ", BOTH):
            run(recorder)
        _, final = recorder.requests[-1]
        text = "\n".join(str(m.content) for m in final)
        self.assertNotIn('"%s"' % lean_history.DIGEST_MARK, text)
        self.assertIn("014790605468140368", text)

    def test_the_default_finalizer_is_unchanged(self):
        recorder = PrefixRecorder(BATCHES)
        run(recorder)
        kind, final = recorder.requests[-1]
        self.assertEqual(kind, "finalizer")
        self.assertIsInstance(final[0], SystemMessage)
        self.assertTrue(final[0].content.startswith("Write the final answer from the completed tool results."))


if __name__ == "__main__":
    unittest.main()
