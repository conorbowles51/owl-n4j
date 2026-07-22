import pytest

from app.config import settings


@pytest.mark.asyncio
async def test_service_key_protects_operational_routes_but_not_health_docs(
    client,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "service_api_key", "service-secret")

    unauthorized = await client.get("/jobs/00000000-0000-0000-0000-000000000000")
    wrong = await client.get(
        "/jobs/00000000-0000-0000-0000-000000000000",
        headers={"X-Evidence-Engine-Key": "wrong"},
    )
    docs = await client.get("/openapi.json")

    assert unauthorized.status_code == 401
    assert wrong.status_code == 401
    assert docs.status_code == 200
