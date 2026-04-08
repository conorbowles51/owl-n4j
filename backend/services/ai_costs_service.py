from __future__ import annotations

import fnmatch
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from postgres.models.ai_pricing_rate import AIPricingRate
from postgres.models.cost_record import CostJobType, CostRecord


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
class UsageMetrics:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    duration_seconds: float | None = None


@dataclass
class AICostContext:
    job_type: CostJobType
    case_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    description: str | None = None
    engine_job_id: str | None = None
    evidence_file_id: uuid.UUID | None = None
    extra_metadata: dict[str, Any] | None = None


_current_cost_context: ContextVar[AICostContext | None] = ContextVar(
    "backend_ai_cost_context",
    default=None,
)


def _as_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _matching_score(pattern: str, model_id: str, priority: int) -> tuple[int, int, int]:
    wildcard_penalty = pattern.count("*") + pattern.count("?")
    exact_match = 1 if pattern == model_id else 0
    return (exact_match, len(pattern) - wildcard_penalty, priority)


def _normalize_usage(
    *,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    duration_seconds: float | None = None,
) -> UsageMetrics:
    resolved_total = total_tokens
    if resolved_total is None and prompt_tokens is not None and completion_tokens is not None:
        resolved_total = prompt_tokens + completion_tokens
    return UsageMetrics(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=resolved_total,
        duration_seconds=duration_seconds,
    )


@contextmanager
def ai_cost_context(
    *,
    job_type: CostJobType,
    case_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    description: str | None = None,
    engine_job_id: str | None = None,
    evidence_file_id: uuid.UUID | None = None,
    extra_metadata: dict[str, Any] | None = None,
):
    previous = _current_cost_context.get()
    merged = AICostContext(
        job_type=job_type,
        case_id=case_id if case_id is not None else (previous.case_id if previous else None),
        user_id=user_id if user_id is not None else (previous.user_id if previous else None),
        description=description or (previous.description if previous else None),
        engine_job_id=engine_job_id if engine_job_id is not None else (previous.engine_job_id if previous else None),
        evidence_file_id=evidence_file_id if evidence_file_id is not None else (previous.evidence_file_id if previous else None),
        extra_metadata={
            **(previous.extra_metadata or {} if previous else {}),
            **(extra_metadata or {}),
        }
        or None,
    )
    token = _current_cost_context.set(merged)
    try:
        yield merged
    finally:
        _current_cost_context.reset(token)


def get_current_ai_cost_context() -> AICostContext | None:
    return _current_cost_context.get()


def resolve_pricing_rate(
    db: Session,
    *,
    provider: str,
    model_id: str,
    operation_kind: str,
    as_of: date | None = None,
) -> AIPricingRate | None:
    today = as_of or date.today()
    candidates = (
        db.query(AIPricingRate)
        .filter(AIPricingRate.provider == provider)
        .filter(AIPricingRate.operation_kind == operation_kind)
        .filter(AIPricingRate.effective_from <= today)
        .filter(
            (AIPricingRate.effective_to.is_(None))
            | (AIPricingRate.effective_to >= today)
        )
        .all()
    )
    matches = [
        rate
        for rate in candidates
        if fnmatch.fnmatch(model_id, rate.model_pattern)
    ]
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


def calculate_cost(rate: AIPricingRate | None, usage: UsageMetrics) -> Decimal:
    if rate is None:
        return Decimal("0")

    if rate.billing_basis == BillingBasis.INPUT_OUTPUT_TOKENS:
        prompt = usage.prompt_tokens or 0
        completion = usage.completion_tokens or 0
        prompt_cost = (Decimal(prompt) / Decimal("1000000")) * _as_decimal(rate.input_cost_per_million)
        completion_cost = (Decimal(completion) / Decimal("1000000")) * _as_decimal(rate.output_cost_per_million)
        return prompt_cost + completion_cost

    if rate.billing_basis == BillingBasis.INPUT_TOKENS:
        input_tokens = usage.prompt_tokens if usage.prompt_tokens is not None else (usage.total_tokens or 0)
        return (Decimal(input_tokens) / Decimal("1000000")) * _as_decimal(rate.input_cost_per_million)

    if rate.billing_basis == BillingBasis.DURATION_MINUTES:
        if usage.duration_seconds is None:
            return Decimal("0")
        return (Decimal(str(usage.duration_seconds)) / Decimal("60")) * _as_decimal(rate.duration_cost_per_minute)

    return Decimal("0")


def record_cost(
    *,
    db: Session,
    job_type: CostJobType,
    provider: str,
    model_id: str,
    operation_kind: str,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    duration_seconds: float | None = None,
    case_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    engine_job_id: str | None = None,
    evidence_file_id: uuid.UUID | None = None,
    description: str | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> CostRecord:
    usage = _normalize_usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        duration_seconds=duration_seconds,
    )
    rate = resolve_pricing_rate(
        db,
        provider=provider,
        model_id=model_id,
        operation_kind=operation_kind,
    )
    cost_usd = calculate_cost(rate, usage)

    payload = dict(extra_metadata or {})
    if usage.duration_seconds is not None:
        payload.setdefault("duration_seconds", usage.duration_seconds)

    cost_record = CostRecord(
        job_type=job_type.value,
        provider=provider,
        model_id=model_id,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
        cost_usd=float(cost_usd),
        operation_kind=operation_kind,
        engine_job_id=engine_job_id,
        evidence_file_id=evidence_file_id,
        pricing_version=rate.pricing_version if rate else None,
        case_id=case_id,
        user_id=user_id,
        description=description,
        extra_metadata=payload or None,
    )
    db.add(cost_record)
    db.flush()
    db.refresh(cost_record)
    return cost_record


def normalize_openai_usage(usage: Any) -> UsageMetrics:
    if usage is None:
        return UsageMetrics()

    if isinstance(usage, dict):
        prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
        completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
        total_tokens = usage.get("total_tokens")
        duration_seconds = (
            usage.get("duration_seconds")
            or usage.get("seconds")
            or usage.get("audio_duration_seconds")
        )
        return _normalize_usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_seconds=duration_seconds,
        )

    prompt_tokens = getattr(usage, "prompt_tokens", None)
    completion_tokens = getattr(usage, "completion_tokens", None)
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    total_tokens = getattr(usage, "total_tokens", None)
    duration_seconds = (
        getattr(usage, "duration_seconds", None)
        or getattr(usage, "seconds", None)
        or getattr(usage, "audio_duration_seconds", None)
    )
    return _normalize_usage(
        prompt_tokens=prompt_tokens if prompt_tokens is not None else input_tokens,
        completion_tokens=completion_tokens if completion_tokens is not None else output_tokens,
        total_tokens=total_tokens,
        duration_seconds=duration_seconds,
    )
