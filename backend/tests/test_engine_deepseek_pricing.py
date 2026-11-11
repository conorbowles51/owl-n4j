"""The evidence engine prices DeepSeek calls from its own copy of the published table
(evidence-engine/app/services/deepseek_pricing.py); it must match the backend's, or the two halves of the cost ledger
disagree."""
import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path

from services import ai_costs_service

_ENGINE = Path(__file__).resolve().parents[2] / "evidence-engine" / "app" / "services" / "deepseek_pricing.py"


def _engine_module():
    spec = importlib.util.spec_from_file_location("engine_deepseek_pricing", _ENGINE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EngineDeepseekPricingTest(unittest.TestCase):
    def test_tables_match(self):
        engine = _engine_module()
        self.assertEqual(engine.DEEPSEEK_PUBLISHED_VERSION, ai_costs_service.DEEPSEEK_PUBLISHED_VERSION)
        self.assertEqual(engine.DEEPSEEK_PUBLISHED_OFFPEAK, ai_costs_service.DEEPSEEK_PUBLISHED_OFFPEAK)
        self.assertEqual(engine.DEEPSEEK_PEAK_HOURS, ai_costs_service.DEEPSEEK_PEAK_HOURS)

    def test_same_price_for_a_call(self):
        engine = _engine_module()
        for at in (datetime(2026, 11, 11, 22, 30, tzinfo=timezone.utc), datetime(2026, 11, 11, 7, 0, tzinfo=timezone.utc)):
            kw = dict(prompt_tokens=9700, cache_hit_tokens=6400, cache_miss_tokens=3300, completion_tokens=1350, at=at)
            self.assertEqual(engine.deepseek_published_cost("deepseek-v4-pro", **kw),
                             ai_costs_service.deepseek_published_cost("deepseek-v4-pro", **kw))


if __name__ == "__main__":
    unittest.main()
