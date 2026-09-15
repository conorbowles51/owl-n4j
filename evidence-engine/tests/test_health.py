from __future__ import annotations

import pytesseract
import pytest
from fastapi import Response

from app.api.routes import health as health_module


@pytest.fixture
def healthy_runtime(monkeypatch):
    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, *_args):
            return None

    async def healthy_async_service():
        return True

    monkeypatch.setattr(health_module, "async_session", FakeSession)
    monkeypatch.setattr(health_module.neo4j_client, "check_connection", healthy_async_service)
    monkeypatch.setattr(health_module.chroma_client, "check_connection", lambda: True)
    monkeypatch.setattr(health_module.redis_client, "check_connection", healthy_async_service)
    monkeypatch.setattr(health_module, "_storage_available", lambda: True)
    monkeypatch.setattr(health_module.settings, "tesseract_lang", "eng")
    monkeypatch.setattr(pytesseract, "get_languages", lambda config="": ["eng", "osd"])
    for provider in ("openai", "anthropic", "gemini", "deepseek"):
        monkeypatch.setattr(health_module.settings, f"{provider}_api_key", "")


async def test_pdf_runtime_is_healthy_and_ready_without_ai_credentials(healthy_runtime):
    response = Response()
    health = await health_module.health_check()
    ready = await health_module.readiness_check(response)

    assert health["status"] == "ok"
    assert ready["status"] == "ready"
    assert response.status_code == 200
    assert health["checks"] == ready["checks"] == {
        "postgres": True,
        "neo4j": True,
        "chromadb": True,
        "redis": True,
        "ocr": True,
        "storage": True,
    }


@pytest.mark.parametrize("dependency", ["postgres", "neo4j", "chromadb", "redis", "ocr", "storage"])
async def test_required_runtime_failure_still_prevents_worker_start(
    healthy_runtime, monkeypatch, dependency,
):
    checks = await health_module._runtime_checks()
    checks[dependency] = False

    async def failed_runtime():
        return checks

    monkeypatch.setattr(health_module, "_runtime_checks", failed_runtime)
    response = Response()
    assert (await health_module.health_check())["status"] == "degraded"
    assert (await health_module.readiness_check(response))["status"] == "not_ready"
    assert response.status_code == 503


async def test_health_is_degraded_when_configured_ocr_language_is_missing(
    monkeypatch,
) -> None:
    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, *_args):
            return None

    async def healthy_async_service():
        return True

    monkeypatch.setattr(health_module, "async_session", FakeSession)
    monkeypatch.setattr(health_module.neo4j_client, "check_connection", healthy_async_service)
    monkeypatch.setattr(health_module.chroma_client, "check_connection", lambda: True)
    monkeypatch.setattr(health_module.redis_client, "check_connection", healthy_async_service)
    monkeypatch.setattr(health_module.settings, "tesseract_lang", "eng+spa")
    monkeypatch.setattr(pytesseract, "get_languages", lambda config="": ["eng", "osd"])

    result = await health_module.health_check()

    assert result["status"] == "degraded"
    assert result["checks"]["ocr"] is False
