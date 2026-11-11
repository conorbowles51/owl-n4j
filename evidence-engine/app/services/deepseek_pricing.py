"""DeepSeek's published prices, cache hits and misses apart, for the engine's cost records.

The rate table's DeepSeek rows (deepseek_docs_2026_08_07: 0.435 in, 0.87 out for v4-pro) know no cache price and are
out of date, so an engine cost row priced from them did not match the DeepSeek balance. This table is the same as the
backend's (backend/services/ai_costs_service.py DEEPSEEK_PUBLISHED_*); backend/tests/test_engine_deepseek_pricing.py
fails when the two differ. Standard library only, so the backend test can load this file by path.

Prices read from https://api-docs.deepseek.com/quick_start/pricing on 2026-11-10, USD per million tokens:
(cache hit, cache miss, output) at off-peak; peak is double. Peak: 01:00-04:00 and 06:00-10:00 UTC, Monday to Friday.
Chinese public holidays are off-peak too; this table does not know them, so a call on one is priced at peak (too high,
never too low).
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

DEEPSEEK_PUBLISHED_VERSION = "deepseek_published_2026_11_10"
DEEPSEEK_PUBLISHED_OFFPEAK = (
    ("deepseek-v4-pro", (Decimal("0.022"), Decimal("0.66"), Decimal("1.98"))),
    # deepseek-v4-flash is a retired name, "billed at the Flash price".
    ("deepseek-v4-flash", (Decimal("0.003"), Decimal("0.15"), Decimal("0.6"))),
    ("deepseek-flash", (Decimal("0.003"), Decimal("0.15"), Decimal("0.6"))),
)
DEEPSEEK_PEAK_HOURS = ((1, 4), (6, 10))


def deepseek_peak(at: datetime) -> bool:
    """True when ``at`` (UTC; a naive time is read as UTC) falls in DeepSeek's peak hours."""
    if at.tzinfo is not None:
        at = at.astimezone(timezone.utc)
    return at.weekday() < 5 and any(start <= at.hour < end for start, end in DEEPSEEK_PEAK_HOURS)


def deepseek_published_cost(model_id: str, *, prompt_tokens: int | None, cache_hit_tokens: int | None,
                            cache_miss_tokens: int | None, completion_tokens: int | None,
                            at: datetime | None = None) -> Decimal | None:
    """One DeepSeek call priced at the published rates, cache hits and misses apart. None for a model the table does
    not list. Prompt tokens DeepSeek did not report as hit or miss are priced as misses."""
    rates = next((r for prefix, r in DEEPSEEK_PUBLISHED_OFFPEAK if (model_id or "").startswith(prefix)), None)
    if rates is None:
        return None
    factor = Decimal(2) if deepseek_peak(at or datetime.now(timezone.utc)) else Decimal(1)
    hit = int(cache_hit_tokens or 0)
    miss = int(cache_miss_tokens) if cache_miss_tokens is not None else max(int(prompt_tokens or 0) - hit, 0)
    million = Decimal("1000000")
    return factor * (Decimal(hit) * rates[0] + Decimal(miss) * rates[1]
                     + Decimal(int(completion_tokens or 0)) * rates[2]) / million
