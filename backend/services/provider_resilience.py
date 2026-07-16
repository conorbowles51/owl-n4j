from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from enum import Enum
from typing import TypeVar

import requests
from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError
from tenacity import retry_if_exception, stop_after_attempt, wait_exponential
from tenacity import Retrying

T = TypeVar("T")


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
_TRANSIENT_REQUESTS_ERRORS = (
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
)


def is_transient_provider_error(exc: Exception) -> bool:
    if isinstance(exc, ProviderUnavailableError):
        return exc.retriable
    if isinstance(exc, _TRANSIENT_OPENAI_ERRORS):
        return True
    if isinstance(exc, _TRANSIENT_REQUESTS_ERRORS):
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


class CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int | None = None,
        reset_timeout_seconds: float | None = None,
    ):
        self.failure_threshold = failure_threshold or int(
            os.getenv("PROVIDER_CIRCUIT_FAILURE_THRESHOLD", "3")
        )
        self.reset_timeout_seconds = reset_timeout_seconds or float(
            os.getenv("PROVIDER_CIRCUIT_RESET_SECONDS", "60")
        )
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.opened_at: float | None = None
        self._lock = threading.Lock()

    def before_call(self, provider: str) -> None:
        with self._lock:
            if self.state != CircuitBreakerState.OPEN:
                return
            if self.opened_at and time.monotonic() - self.opened_at >= self.reset_timeout_seconds:
                self.state = CircuitBreakerState.HALF_OPEN
                return
            raise ProviderUnavailableError(
                provider,
                f"{provider} provider is temporarily unavailable; retry later.",
                retriable=True,
            )

    def record_success(self) -> None:
        with self._lock:
            self.state = CircuitBreakerState.CLOSED
            self.failure_count = 0
            self.opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            if self.state == CircuitBreakerState.HALF_OPEN:
                self._open()
                return
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self._open()

    def _open(self) -> None:
        self.state = CircuitBreakerState.OPEN
        self.opened_at = time.monotonic()

    def reset(self) -> None:
        with self._lock:
            self.state = CircuitBreakerState.CLOSED
            self.failure_count = 0
            self.opened_at = None


_breakers: dict[str, CircuitBreaker] = {}
_breakers_lock = threading.Lock()


def get_circuit_breaker(provider: str) -> CircuitBreaker:
    key = provider.lower()
    with _breakers_lock:
        breaker = _breakers.get(key)
        if breaker is None:
            breaker = CircuitBreaker()
            _breakers[key] = breaker
        return breaker


def reset_provider_breakers() -> None:
    with _breakers_lock:
        _breakers.clear()


def guard_provider_call(provider: str, fn: Callable[[], T]) -> T:
    normalized_provider = provider.lower()
    breaker = get_circuit_breaker(normalized_provider)
    breaker.before_call(normalized_provider)

    attempts = max(1, int(os.getenv("PROVIDER_RETRY_ATTEMPTS", "3")))
    try:
        for attempt in Retrying(
            stop=stop_after_attempt(attempts),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
            retry=retry_if_exception(is_transient_provider_error),
            reraise=True,
        ):
            with attempt:
                result = fn()
        breaker.record_success()
        return result
    except Exception as exc:
        if is_transient_provider_error(exc):
            breaker.record_failure()
            raise ProviderUnavailableError(
                normalized_provider,
                f"{normalized_provider} provider is temporarily unavailable; retry later.",
                retriable=True,
                original=exc,
            ) from exc
        raise
