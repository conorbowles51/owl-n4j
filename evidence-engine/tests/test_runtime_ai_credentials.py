from __future__ import annotations

import base64
import hashlib

import pytest
from cryptography.fernet import Fernet

from app.services import ai_model_policy


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _MappingRows:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class _FakeDB:
    def __init__(self, policy, credentials):
        self.results = [_ScalarResult(policy), _MappingRows(credentials)]

    async def execute(self, _query):
        return self.results.pop(0)


def _encrypt(secret: str, plaintext: str) -> str:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    cipher = Fernet(base64.urlsafe_b64encode(digest))
    return cipher.encrypt(plaintext.encode("utf-8")).decode("ascii")


@pytest.mark.asyncio
async def test_job_runtime_loads_database_credential_snapshot(monkeypatch) -> None:
    monkeypatch.setattr(
        ai_model_policy.settings,
        "ai_credential_encryption_key",
        "test-master-key",
    )
    db = _FakeDB(
        {"ingestion_extraction": {"provider": "anthropic", "model_id": "claude-sonnet-5"}},
        [
            {
                "provider": "anthropic",
                "encrypted_api_key": _encrypt("test-master-key", "database-key"),
                "revision": 7,
                "source": "database",
                "status": "connected",
            }
        ],
    )

    await ai_model_policy.load_ai_model_policy(db)

    assert ai_model_policy.resolve_provider_api_key("anthropic") == "database-key"
    assert ai_model_policy.get_ai_runtime_snapshot()["credentials"]["anthropic"]["revision"] == 7
