from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import TypeVar

import httpx
from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError

from app.services.redis_client import get_redis

T = TypeVar("T")
logger = logging.getLogger(__name__)


class CircuitBreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class ProviderUnavailableError(Exception):
    def __init__(
        self,
        provider: str,
        message: str | None = None,
        *,
        retriable: bool = True,
        original: Exception | None = None,
    ):
        self.provider = provider
        self.retriable = retriable
        self.original = original
        super().__init__(message or f"{provider} provider is unavailable")


_TRANSIENT_OPENAI_ERRORS = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    InternalServerError,
)
_TRANSIENT_HTTPX_ERRORS = (
    httpx.TimeoutException,
    httpx.TransportError,
)


def is_transient_provider_error(exc: Exception) -> bool:
    if isinstance(exc, ProviderUnavailableError):
        return exc.retriable
    if isinstance(exc, _TRANSIENT_OPENAI_ERRORS):
        return True
    if isinstance(exc, _TRANSIENT_HTTPX_ERRORS):
        return True
    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if status_code is None and response is not None:
        status_code = getattr(response, "status_code", None)
    if status_code == 429:
        return True
    if isinstance(status_code, int) and status_code >= 500:
        return True
    return False


def _redis_key(provider: str) -> str:
    return f"provider_resilience:{provider.lower()}"


def _failure_threshold() -> int:
    return max(1, int(os.getenv("PROVIDER_CIRCUIT_FAILURE_THRESHOLD", "3")))


def _reset_timeout_seconds() -> float:
    return max(1.0, float(os.getenv("PROVIDER_CIRCUIT_RESET_SECONDS", "60")))


def _retry_attempts() -> int:
    return max(1, int(os.getenv("PROVIDER_RETRY_ATTEMPTS", "3")))


async def _breaker_state(provider: str) -> tuple[CircuitBreakerState, int, float | None]:
    try:
        payload = await get_redis().hgetall(_redis_key(provider))
    except Exception as exc:
        logger.warning("Provider circuit breaker Redis read failed: %s", exc)
        return CircuitBreakerState.CLOSED, 0, None
    state = CircuitBreakerState(payload.get("state") or CircuitBreakerState.CLOSED.value)
    failures = int(payload.get("failures") or 0)
    opened_at = payload.get("opened_at")
    return state, failures, float(opened_at) if opened_at else None


async def _set_breaker(
    provider: str,
    *,
    state: CircuitBreakerState,
    failures: int = 0,
    opened_at: float | None = None,
) -> None:
    try:
        key = _redis_key(provider)
        await get_redis().hset(
            key,
            mapping={
                "state": state.value,
                "failures": str(failures),
                "opened_at": str(opened_at or time.time()),
            },
        )
        await get_redis().expire(key, int(_reset_timeout_seconds() * 2))
    except Exception as exc:
        logger.warning("Provider circuit breaker Redis write failed: %s", exc)


async def _before_call(provider: str) -> None:
    state, failures, opened_at = await _breaker_state(provider)
    if state != CircuitBreakerState.OPEN:
        return
    if opened_at and time.time() - opened_at >= _reset_timeout_seconds():
        await _set_breaker(
            provider,
            state=CircuitBreakerState.HALF_OPEN,
            failures=failures,
            opened_at=opened_at,
        )
        return
    raise ProviderUnavailableError(
        provider,
        f"{provider} provider is temporarily unavailable; retry later.",
        retriable=True,
    )


async def _record_success(provider: str) -> None:
    try:
        await get_redis().delete(_redis_key(provider))
    except Exception as exc:
        logger.warning("Provider circuit breaker Redis reset failed: %s", exc)


async def _record_failure(provider: str) -> None:
    state, failures, _ = await _breaker_state(provider)
    if state == CircuitBreakerState.HALF_OPEN:
        await _set_breaker(
            provider,
            state=CircuitBreakerState.OPEN,
            failures=_failure_threshold(),
            opened_at=time.time(),
        )
        return
    failures += 1
    if failures >= _failure_threshold():
        await _set_breaker(
            provider,
            state=CircuitBreakerState.OPEN,
            failures=failures,
            opened_at=time.time(),
        )
    else:
        await _set_breaker(provider, state=CircuitBreakerState.CLOSED, failures=failures)


async def guard_provider_call(provider: str, fn: Callable[[], Awaitable[T]]) -> T:
    normalized_provider = provider.lower()
    await _before_call(normalized_provider)

    last_exc: Exception | None = None
    for attempt in range(1, _retry_attempts() + 1):
        try:
            result = await fn()
            await _record_success(normalized_provider)
            return result
        except Exception as exc:
            if not is_transient_provider_error(exc):
                raise
            last_exc = exc
            if attempt < _retry_attempts():
                await asyncio.sleep(min(4.0, 0.5 * (2 ** (attempt - 1))))

    await _record_failure(normalized_provider)
    raise ProviderUnavailableError(
        normalized_provider,
        f"{normalized_provider} provider is temporarily unavailable; retry later.",
        retriable=True,
        original=last_exc,
    ) from last_exc
