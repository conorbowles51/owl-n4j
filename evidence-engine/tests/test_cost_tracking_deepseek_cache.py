"""An engine DeepSeek cost row keeps the cache hit/miss split DeepSeek reports and is priced from it, so the cost
ledger matches the DeepSeek balance (the old rows priced every prompt token at the out-of-date rate-table price)."""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from app.services import cost_tracking, openai_client
from app.services.deepseek_pricing import DEEPSEEK_PUBLISHED_VERSION, deepseek_published_cost


class _FakeSession:
    def __init__(self, sink: list[Any]):
        self.sink = sink

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def add(self, row):
        self.sink.append(row)

    async def commit(self):
        return None


def _record(monkeypatch, usage, provider="deepseek", model_id="deepseek-v4-pro"):
    rows: list[Any] = []
    old_rate = SimpleNamespace(
        billing_basis=cost_tracking.BillingBasis.INPUT_OUTPUT_TOKENS,
        input_cost_per_million=Decimal("0.435"),
        output_cost_per_million=Decimal("0.87"),
        duration_cost_per_minute=None,
        pricing_version="deepseek_docs_2026_08_07",
    )

    async def fake_rate(*args):
        return old_rate

    monkeypatch.setattr(cost_tracking, "_resolve_pricing_rate", fake_rate)
    monkeypatch.setattr(cost_tracking, "async_session", lambda: _FakeSession(rows))
    asyncio.run(cost_tracking.record_ai_cost(provider=provider, model_id=model_id,
                                             operation_kind=cost_tracking.CostOperationKind.CHAT_COMPLETION,
                                             usage=usage, extra_metadata={"workload": "ingestion_extraction"}))
    return rows[0]


def test_deepseek_row_keeps_cache_split_and_is_priced_from_it(monkeypatch) -> None:
    usage = {"prompt_tokens": 10_000, "completion_tokens": 1_000, "total_tokens": 11_000,
             "prompt_cache_hit_tokens": 8_000, "prompt_cache_miss_tokens": 2_000}
    row = _record(monkeypatch, usage)
    assert row.extra_metadata["prompt_cache_hit_tokens"] == 8_000
    assert row.extra_metadata["prompt_cache_miss_tokens"] == 2_000
    assert row.extra_metadata["workload"] == "ingestion_extraction"
    assert row.pricing_version == DEEPSEEK_PUBLISHED_VERSION
    expected = deepseek_published_cost("deepseek-v4-pro", prompt_tokens=10_000, cache_hit_tokens=8_000,
                                       cache_miss_tokens=2_000, completion_tokens=1_000)
    assert abs(Decimal(str(row.cost_usd)) - expected) < Decimal("0.0000005")


def test_row_without_cache_split_keeps_rate_table_price(monkeypatch) -> None:
    row = _record(monkeypatch, {"prompt_tokens": 1_000_000, "completion_tokens": 0})
    assert row.pricing_version == "deepseek_docs_2026_08_07"
    assert abs(row.cost_usd - 0.435) < 1e-9
    assert "prompt_cache_hit_tokens" not in row.extra_metadata


def test_published_price_offpeak_and_peak() -> None:
    offpeak = datetime(2026, 11, 11, 22, 30, tzinfo=timezone.utc)  # Wednesday 22:30 UTC
    peak = datetime(2026, 11, 11, 7, 0, tzinfo=timezone.utc)
    kw = dict(prompt_tokens=1_000_000, cache_hit_tokens=500_000, cache_miss_tokens=500_000, completion_tokens=0)
    assert deepseek_published_cost("deepseek-v4-pro", at=offpeak, **kw) == Decimal("0.341")
    assert deepseek_published_cost("deepseek-v4-pro", at=peak, **kw) == Decimal("0.682")
    assert deepseek_published_cost("other-model", at=offpeak, **kw) is None


def test_retries_sum_the_cache_split() -> None:
    total: dict[str, Any] = {}
    openai_client._add_token_usage(total, {"prompt_tokens": 100, "prompt_cache_hit_tokens": 64,
                                           "prompt_cache_miss_tokens": 36})
    openai_client._add_token_usage(total, {"prompt_tokens": 120, "prompt_cache_hit_tokens": 64,
                                           "prompt_cache_miss_tokens": 56})
    assert total["prompt_cache_hit_tokens"] == 128
    assert total["prompt_cache_miss_tokens"] == 92
