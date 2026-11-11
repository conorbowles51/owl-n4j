"""lx-agentfit R1: the trace replay's simulated DeepSeek cache stores a request's output unit in that request's own
wording. Built from the next request's wording instead, the finalizer's request (its own system prompt) and history
whose results became digests were read from cache in full in the simulation, which DeepSeek's prefix units do not
allow (api-docs.deepseek.com/guides/kv_cache). Fails on the code before: the unit began with the next request."""
import importlib.util
import os
import unittest

_PATH = os.path.join(os.path.dirname(__file__), '..', 'scripts', 'financial_agent_trace_replay.py')
_spec = importlib.util.spec_from_file_location('trace_replay_under_test', _PATH)
replay = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(replay)


def ids(payload):
    return [hash(part) % 100_000 for part in replay._render(payload)]


AGENT = {'role': 'system', 'content': 'You are the OWL AI Agent.'}
ASK = {'role': 'user', 'content': 'Who paid?'}
REPLY = {'role': 'assistant', 'content': 'CLANA paid.'}
WHOLE = {'role': 'tool', 'content': 'x' * 400, 'tool_call_id': 'c1'}
DIGEST = {'role': 'tool', 'content': 'digest', 'tool_call_id': 'c1'}


class OutputUnitTests(unittest.TestCase):
    def test_the_finalizers_own_request_is_not_read_from_cache(self):
        agent = {'messages': [AGENT, ASK, WHOLE], 'tools': [{'name': 't'}]}
        final = {'messages': [{'role': 'system', 'content': 'Write the final answer.'}, ASK, WHOLE, REPLY]}
        unit = replay._output_unit(agent, final)
        self.assertEqual(unit['messages'][0], AGENT)
        hits = replay.simulate_cache([ids(agent), ids(final)], [ids(unit), None])
        self.assertEqual(hits[1]['hit_strict'], 0)

    def test_a_result_turned_digest_ends_the_hit_at_the_unit_before_it(self):
        first = {'messages': [AGENT, ASK, WHOLE]}
        second = {'messages': [AGENT, ASK, DIGEST, REPLY, {'role': 'user', 'content': 'and?'}]}
        unit = replay._output_unit(first, second)
        hits = replay.simulate_cache([ids(first), ids(second)], [ids(unit), None])
        self.assertLess(hits[1]['hit_strict'], len(ids(second)) - 2)
        self.assertEqual(hits[1]['hit_strict'], 0)

    def test_an_unchanged_history_reads_the_whole_earlier_request_and_reply(self):
        first = {'messages': [AGENT, ASK, WHOLE]}
        second = {'messages': [AGENT, ASK, WHOLE, REPLY, {'role': 'user', 'content': 'and?'}]}
        unit = replay._output_unit(first, second)
        hits = replay.simulate_cache([ids(first), ids(second)], [ids(unit), None])
        self.assertEqual(hits[1]['hit_strict'], len(ids(unit)))


if __name__ == '__main__':
    unittest.main()
