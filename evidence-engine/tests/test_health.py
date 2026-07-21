from __future__ import annotations

import pytesseract

from app.api.routes import health as health_module


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
