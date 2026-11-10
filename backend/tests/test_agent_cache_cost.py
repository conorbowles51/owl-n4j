"""The assistant's bill: DeepSeek's prompt-cache hits are recorded on every cost row and priced apart from misses.

Before this, 0 of 2,402 assistant cost rows in 7 days (to 10 Nov 2026) carried the cache-hit count, so neither the
real bill nor the hit rate could be read, and every DeepSeek token was priced at one stale input rate."""
from datetime import datetime, timezone
from decimal import Decimal
import unittest
from unittest import mock

from langchain_core.messages import AIMessage, HumanMessage

from services import ai_costs_service as costs
from services.agent.graph import AgentGraphRunner

OFFPEAK = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)   # a Saturday
PEAK = datetime(2026, 11, 10, 2, 30, tzinfo=timezone.utc)     # a Tuesday, 01:00-04:00 UTC


def _step(prompt, hit, completion):
    return AIMessage(content="x", usage_metadata={
        "input_tokens": prompt, "output_tokens": completion, "total_tokens": prompt + completion,
        "input_token_details": {"cache_read": hit}})


class _Db:
    def __init__(self):
        self.added = []

    def add(self, row):
        self.added.append(row)

    def flush(self):
        pass

    def refresh(self, row):
        pass


class PublishedPriceTests(unittest.TestCase):
    def test_hits_are_priced_at_the_cache_rate_and_peak_is_double(self):
        args = dict(prompt_tokens=1_000_000, cache_hit_tokens=900_000, cache_miss_tokens=100_000,
                    completion_tokens=10_000)
        off = costs.deepseek_published_cost("deepseek-v4-pro", at=OFFPEAK, **args)
        # 0.9 x 0.022 + 0.1 x 0.66 + 0.01 x 1.98
        self.assertEqual(off, Decimal("0.1056"))
        self.assertEqual(costs.deepseek_published_cost("deepseek-v4-pro", at=PEAK, **args), off * 2)

    def test_peak_hours(self):
        self.assertTrue(costs.deepseek_peak(datetime(2026, 11, 9, 9, 59, tzinfo=timezone.utc)))
        self.assertFalse(costs.deepseek_peak(datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)))
        self.assertFalse(costs.deepseek_peak(datetime(2026, 11, 9, 4, 0, tzinfo=timezone.utc)))
        self.assertFalse(costs.deepseek_peak(datetime(2026, 11, 8, 2, 0, tzinfo=timezone.utc)))  # Sunday

    def test_an_unlisted_model_is_not_priced_here(self):
        self.assertIsNone(costs.deepseek_published_cost("gpt-5.6-sol", prompt_tokens=1, cache_hit_tokens=0,
                                                        cache_miss_tokens=1, completion_tokens=0))


class CostRecordTests(unittest.TestCase):
    def test_a_deepseek_row_keeps_hits_and_misses_and_is_priced_from_them(self):
        db = _Db()
        with mock.patch.object(costs, "resolve_pricing_rate", return_value=None), \
                mock.patch.object(costs, "deepseek_peak", return_value=False):
            row = costs.record_cost(db=db, job_type=costs.CostJobType.AI_ASSISTANT, provider="deepseek",
                                    model_id="deepseek-v4-pro", operation_kind=costs.CostOperationKind.CHAT_COMPLETION,
                                    prompt_tokens=1_000_000, completion_tokens=0, prompt_cache_hit_tokens=1_000_000,
                                    prompt_cache_miss_tokens=0, extra_metadata={"agent": True})
        self.assertEqual(row.extra_metadata["prompt_cache_hit_tokens"], 1_000_000)
        self.assertEqual(row.extra_metadata["prompt_cache_miss_tokens"], 0)
        self.assertAlmostEqual(row.cost_usd, 0.022)
        self.assertEqual(row.pricing_version, costs.DEEPSEEK_PUBLISHED_VERSION)

    def test_metered_calls_pass_the_cache_counts_on(self):
        seen = {}
        with mock.patch.object(costs, "record_cost", side_effect=lambda **kw: seen.update(kw)), \
                mock.patch("postgres.session.get_background_session") as session:
            session.return_value.__enter__.return_value = object()
            with costs.ai_cost_context(job_type=costs.CostJobType.AI_ASSISTANT, meter_calls=True):
                costs.record_metered_call("deepseek", "deepseek-v4-pro", {
                    "prompt_tokens": 100, "completion_tokens": 5, "total_tokens": 105,
                    "prompt_cache_hit_tokens": 64, "prompt_cache_miss_tokens": 36})
        self.assertEqual((seen["prompt_cache_hit_tokens"], seen["prompt_cache_miss_tokens"]), (64, 36))


class RunUsageTests(unittest.TestCase):
    def test_a_run_sums_cache_hits_and_keeps_each_step(self):
        usage = AgentGraphRunner._extract_usage([HumanMessage(content="q"), _step(30_000, 0, 200),
                                                 _step(40_000, 29_952, 300), _step(52_000, 39_936, 900)])
        self.assertEqual(usage["prompt_tokens"], 122_000)
        self.assertEqual(usage["prompt_cache_hit_tokens"], 69_888)
        self.assertEqual(usage["prompt_cache_miss_tokens"], 122_000 - 69_888)
        self.assertEqual(usage["steps"], [[30_000, 0, 200], [40_000, 29_952, 300], [52_000, 39_936, 900]])

    def test_the_raw_deepseek_counts_win_when_present(self):
        message = AIMessage(content="x", usage_metadata={"input_tokens": 100, "output_tokens": 1,
                                                         "total_tokens": 101},
                            response_metadata={"token_usage": {"prompt_cache_hit_tokens": 64,
                                                               "prompt_cache_miss_tokens": 36}})
        usage = AgentGraphRunner._extract_usage([message])
        self.assertEqual((usage["prompt_cache_hit_tokens"], usage["prompt_cache_miss_tokens"]), (64, 36))

    def test_no_cache_report_stays_unknown_not_zero(self):
        message = AIMessage(content="x", usage_metadata={"input_tokens": 100, "output_tokens": 1,
                                                         "total_tokens": 101})
        usage = AgentGraphRunner._extract_usage([message])
        self.assertIsNone(usage["prompt_cache_hit_tokens"])


class DeepSeekTextCallTests(unittest.TestCase):
    def test_the_text_call_keeps_the_cache_counts(self):
        from services.llm_service import LLMExecutionContext
        response = mock.Mock()
        response.json.return_value = {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                                      "usage": {"prompt_tokens": 1963, "completion_tokens": 2, "total_tokens": 1965,
                                                "prompt_cache_hit_tokens": 1920, "prompt_cache_miss_tokens": 43}}
        with mock.patch("services.llm_service.requests.post", return_value=response), \
                mock.patch("services.ai_costs_service.record_metered_call"):
            call = LLMExecutionContext("deepseek", "deepseek-v4-pro", api_key="k")
            call.call("Say ok.")
        self.assertEqual(call.last_usage["prompt_cache_hit_tokens"], 1920)
        self.assertEqual(call.last_usage["prompt_cache_miss_tokens"], 43)


if __name__ == "__main__":
    unittest.main()
