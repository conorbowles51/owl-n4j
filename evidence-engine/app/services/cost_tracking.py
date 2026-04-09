from __future__ import annotations

import fnmatch
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.dependencies import async_session
from app.models.cost_tracking import AIPricingRate, CostRecord


class CostOperationKind:
    CHAT_COMPLETION = "chat_completion"
    EMBEDDING = "embedding"
    TRANSCRIPTION = "transcription"
    VISION = "vision"


class BillingBasis:
    INPUT_OUTPUT_TOKENS = "input_output_tokens"
    INPUT_TOKENS = "input_tokens"
    DURATION_MINUTES = "duration_minutes"


@dataclass
class IngestionCostContext:
    case_id: str | None = None
    requested_by_user_id: str | None = None
    engine_job_id: str | None = None
    source_evidence_file_id: str | None = None
    description: str | None = None
    extra_metadata: dict[str, Any] = field(default_factory=dict)
    job_type: str = "ingestion"


_current_context: ContextVar[IngestionCostContext | None] = ContextVar(
    "evidence_engine_cost_context",
    default=None,
)


@asynccontextmanager
async def ingestion_cost_context(**kwargs: Any):
    previous = _current_context.get()
    merged = IngestionCostContext(
        case_id=kwargs.get("case_id") or (previous.case_id if previous else None),
        requested_by_user_id=kwargs.get("requested_by_user_id") or (previous.requested_by_user_id if previous else None),
        engine_job_id=kwargs.get("engine_job_id") if "engine_job_id" in kwargs else (previous.engine_job_id if previous else None),
        source_evidence_file_id=kwargs.get("source_evidence_file_id") if "source_evidence_file_id" in kwargs else (previous.source_evidence_file_id if previous else None),
        description=kwargs.get("description") or (previous.description if previous else None),
        extra_metadata={
            **(previous.extra_metadata if previous else {}),
            **(kwargs.get("extra_metadata") or {}),
        },
        job_type=kwargs.get("job_type") or (previous.job_type if previous else "ingestion"),
    )
    token = _current_context.set(merged)
    try:
        yield merged
    finally:
        _current_context.reset(token)


def _parse_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _matching_score(pattern: str, model_id: str, priority: int) -> tuple[int, int, int]:
    wildcard_penalty = pattern.count("*") + pattern.count("?")
    exact_match = 1 if pattern == model_id else 0
    return (exact_match, len(pattern) - wildcard_penalty, priority)


def _as_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def normalize_usage(usage: Any, duration_seconds: float | None = None) -> dict[str, Any]:
    if usage is None:
        return {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "duration_seconds": duration_seconds,
        }

    if isinstance(usage, dict):
        prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
        completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
        total_tokens = usage.get("total_tokens")
        resolved_duration = duration_seconds or usage.get("duration_seconds") or usage.get("seconds")
    else:
        prompt_tokens = getattr(usage, "prompt_tokens", None) or getattr(usage, "input_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None) or getattr(usage, "output_tokens", None)
        total_tokens = getattr(usage, "total_tokens", None)
        resolved_duration = duration_seconds or getattr(usage, "duration_seconds", None) or getattr(usage, "seconds", None)

    if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
        total_tokens = prompt_tokens + completion_tokens

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "duration_seconds": resolved_duration,
    }


async def _resolve_pricing_rate(provider: str, model_id: str, operation_kind: str) -> AIPricingRate | None:
    today = date.today()
    async with async_session() as db:
        result = await db.execute(
            select(AIPricingRate).where(
                AIPricingRate.provider == provider,
                AIPricingRate.operation_kind == operation_kind,
                AIPricingRate.effective_from <= today,
                (AIPricingRate.effective_to.is_(None)) | (AIPricingRate.effective_to >= today),
            )
        )
        rates = list(result.scalars().all())

    matches = [rate for rate in rates if fnmatch.fnmatch(model_id, rate.model_pattern)]
    if not matches:
        return None
    matches.sort(
        key=lambda rate: (
            _matching_score(rate.model_pattern, model_id, rate.priority),
            rate.effective_from,
        ),
        reverse=True,
    )
    return matches[0]


def _calculate_cost(rate: AIPricingRate | None, usage: dict[str, Any]) -> Decimal:
    if rate is None:
        return Decimal("0")

    if rate.billing_basis == BillingBasis.INPUT_OUTPUT_TOKENS:
        prompt_cost = (Decimal(usage.get("prompt_tokens") or 0) / Decimal("1000000")) * _as_decimal(rate.input_cost_per_million)
        completion_cost = (Decimal(usage.get("completion_tokens") or 0) / Decimal("1000000")) * _as_decimal(rate.output_cost_per_million)
        return prompt_cost + completion_cost

    if rate.billing_basis == BillingBasis.INPUT_TOKENS:
        input_tokens = usage.get("prompt_tokens")
        if input_tokens is None:
            input_tokens = usage.get("total_tokens") or 0
        return (Decimal(input_tokens) / Decimal("1000000")) * _as_decimal(rate.input_cost_per_million)

    if rate.billing_basis == BillingBasis.DURATION_MINUTES:
        duration = usage.get("duration_seconds")
        if duration is None:
            return Decimal("0")
        return (Decimal(str(duration)) / Decimal("60")) * _as_decimal(rate.duration_cost_per_minute)

    return Decimal("0")


async def record_openai_cost(
    *,
    model_id: str,
    operation_kind: str,
    usage: Any = None,
    duration_seconds: float | None = None,
    description: str | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> None:
    context = _current_context.get()
    normalized_usage = normalize_usage(usage, duration_seconds=duration_seconds)
    rate = await _resolve_pricing_rate("openai", model_id, operation_kind)
    metadata = {
        "source": "evidence_engine",
        **(context.extra_metadata if context else {}),
        **(extra_metadata or {}),
    }
    async with async_session() as db:
        db.add(
            CostRecord(
                job_type=context.job_type if context else "ingestion",
                provider="openai",
                model_id=model_id,
                prompt_tokens=normalized_usage.get("prompt_tokens"),
                completion_tokens=normalized_usage.get("completion_tokens"),
                total_tokens=normalized_usage.get("total_tokens"),
                cost_usd=float(_calculate_cost(rate, normalized_usage)),
                operation_kind=operation_kind,
                engine_job_id=context.engine_job_id if context else None,
                evidence_file_id=_parse_uuid(context.source_evidence_file_id if context else None),
                pricing_version=rate.pricing_version if rate else None,
                case_id=_parse_uuid(context.case_id if context else None),
                user_id=_parse_uuid(context.requested_by_user_id if context else None),
                description=description or (context.description if context else None),
                extra_metadata=metadata or None,
            )
        )
        await db.commit()
