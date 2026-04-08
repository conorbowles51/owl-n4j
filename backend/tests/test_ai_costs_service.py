from datetime import date
from decimal import Decimal
import unittest

from postgres.models.ai_pricing_rate import AIPricingRate
from services.ai_costs_service import BillingBasis, UsageMetrics, calculate_cost


def make_rate(
    *,
    billing_basis: str,
    input_cost_per_million: str | None = None,
    output_cost_per_million: str | None = None,
    duration_cost_per_minute: str | None = None,
) -> AIPricingRate:
    return AIPricingRate(
        provider="openai",
        model_pattern="test-model*",
        operation_kind="test_operation",
        billing_basis=billing_basis,
        input_cost_per_million=Decimal(input_cost_per_million) if input_cost_per_million is not None else None,
        output_cost_per_million=Decimal(output_cost_per_million) if output_cost_per_million is not None else None,
        duration_cost_per_minute=Decimal(duration_cost_per_minute) if duration_cost_per_minute is not None else None,
        pricing_version="test",
        effective_from=date(2026, 4, 8),
        effective_to=None,
        priority=0,
    )


class AICostsServiceTests(unittest.TestCase):
    def test_calculate_cost_for_chat_completion_tokens(self):
        rate = make_rate(
            billing_basis=BillingBasis.INPUT_OUTPUT_TOKENS,
            input_cost_per_million="2.50",
            output_cost_per_million="10.00",
        )

        cost = calculate_cost(
            rate,
            UsageMetrics(prompt_tokens=2_000_000, completion_tokens=500_000),
        )

        self.assertEqual(cost, Decimal("10.00"))

    def test_calculate_cost_for_embedding_input_tokens(self):
        rate = make_rate(
            billing_basis=BillingBasis.INPUT_TOKENS,
            input_cost_per_million="0.13",
        )

        cost = calculate_cost(
            rate,
            UsageMetrics(prompt_tokens=1_000_000, total_tokens=1_000_000),
        )

        self.assertEqual(cost, Decimal("0.13"))

    def test_calculate_cost_for_transcription_duration(self):
        rate = make_rate(
            billing_basis=BillingBasis.DURATION_MINUTES,
            duration_cost_per_minute="0.006",
        )

        cost = calculate_cost(
            rate,
            UsageMetrics(duration_seconds=90),
        )

        self.assertEqual(cost, Decimal("0.0090"))


if __name__ == "__main__":
    unittest.main()
