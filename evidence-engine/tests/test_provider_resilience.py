import httpx
import pytest

from app.services import provider_resilience


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, dict[str, str]] = {}

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.values.get(key) or {})

    async def hset(self, key: str, mapping: dict[str, str]) -> None:
        self.values[key] = dict(mapping)

    async def expire(self, key: str, seconds: int) -> None:
        return None

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)


@pytest.mark.asyncio
async def test_async_guard_opens_shared_circuit(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = FakeRedis()
    calls = 0

    async def timeout():
        nonlocal calls
        calls += 1
        raise httpx.TimeoutException("read timed out")

    monkeypatch.setenv("PROVIDER_RETRY_ATTEMPTS", "1")
    monkeypatch.setenv("PROVIDER_CIRCUIT_FAILURE_THRESHOLD", "2")
    monkeypatch.setattr(provider_resilience, "get_redis", lambda: fake_redis)

    with pytest.raises(provider_resilience.ProviderUnavailableError):
        await provider_resilience.guard_provider_call("openai", timeout)
    with pytest.raises(provider_resilience.ProviderUnavailableError):
        await provider_resilience.guard_provider_call("openai", timeout)
    with pytest.raises(provider_resilience.ProviderUnavailableError):
        await provider_resilience.guard_provider_call("openai", timeout)

    assert calls == 2


@pytest.mark.asyncio
async def test_async_guard_does_not_retry_non_transient_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = FakeRedis()
    calls = 0

    async def bad_request():
        nonlocal calls
        calls += 1
        raise ValueError("input_too_large")

    monkeypatch.setenv("PROVIDER_RETRY_ATTEMPTS", "3")
    monkeypatch.setattr(provider_resilience, "get_redis", lambda: fake_redis)

    with pytest.raises(ValueError):
        await provider_resilience.guard_provider_call("openai", bad_request)

    assert calls == 1
