from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from routers import evidence_ws
from services import evidence_engine_client


class FakeWebSocket:
    def __init__(self, token: str | None) -> None:
        self.cookies = {"access_token": token} if token else {}
        self.closed = None

    async def close(self, *, code: int, reason: str) -> None:
        self.closed = (code, reason)


@pytest.mark.asyncio
async def test_evidence_progress_subscription_requires_login() -> None:
    websocket = FakeWebSocket(None)

    allowed = await evidence_ws._authorize_job_subscription(websocket, "job-1")

    assert allowed is False
    assert websocket.closed == (1008, "Authentication required")


@pytest.mark.asyncio
async def test_evidence_progress_subscription_checks_case_access(monkeypatch) -> None:
    case_id = uuid4()
    websocket = FakeWebSocket("signed-token")
    user = SimpleNamespace(is_active=True)

    async def fake_get_job(_job_id: str):
        return {"case_id": str(case_id)}

    class FakeQuery:
        def filter(self, *_args):
            return self

        def first(self):
            return user

    class FakeDb:
        def query(self, *_args):
            return FakeQuery()

    @contextmanager
    def fake_session():
        yield FakeDb()

    checked = []
    monkeypatch.setattr(evidence_engine_client, "get_job", fake_get_job)
    monkeypatch.setitem(
        evidence_ws.auth_service,
        "verify_access_token",
        lambda _token: {"username": "investigator@example.com"},
    )
    monkeypatch.setattr(evidence_ws, "get_background_session", fake_session)
    monkeypatch.setattr(
        evidence_ws,
        "get_case_if_allowed",
        lambda _db, actual_case_id, actual_user: checked.append(
            (actual_case_id, actual_user)
        ),
    )

    allowed = await evidence_ws._authorize_job_subscription(websocket, "job-1")

    assert allowed is True
    assert websocket.closed is None
    assert checked == [(case_id, user)]
