"""Task-local view of the centralized AI model routing policy."""

from __future__ import annotations

import logging
import base64
import hashlib
from contextvars import ContextVar
from copy import deepcopy
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


logger = logging.getLogger(__name__)

DEFAULT_POLICY = {
    "ingestion_extraction": {"provider": "openai", "model_id": settings.openai_extraction_model},
    "ingestion_resolution": {"provider": "openai", "model_id": settings.openai_resolution_model},
    "ingestion_entity_summary": {"provider": "openai", "model_id": settings.openai_summary_model},
    "ingestion_document_summary": {"provider": "openai", "model_id": settings.openai_document_summary_model},
    "ingestion_quality": {"provider": "openai", "model_id": settings.openai_quality_model},
}

_current_policy: ContextVar[dict[str, dict[str, str]]] = ContextVar(
    "evidence_engine_ai_model_policy",
    default=DEFAULT_POLICY,
)
_current_credentials: ContextVar[dict[str, dict[str, Any]]] = ContextVar(
    "evidence_engine_ai_provider_credentials",
    default={},
)


def _normalize(configuration: Any) -> dict[str, dict[str, str]]:
    policy = deepcopy(DEFAULT_POLICY)
    if not isinstance(configuration, dict):
        return policy
    for workload in policy:
        entry = configuration.get(workload)
        if not isinstance(entry, dict):
            continue
        provider = str(entry.get("provider") or "").strip().lower()
        model_id = str(entry.get("model_id") or "").strip()
        if provider in {"openai", "anthropic", "gemini"} and model_id:
            policy[workload] = {"provider": provider, "model_id": model_id}
    return policy


async def load_ai_model_policy(db: AsyncSession) -> dict[str, dict[str, str]]:
    try:
        result = await db.execute(
            text("SELECT configuration FROM ai_model_policies WHERE key = 'default'")
        )
        configuration = result.scalar_one_or_none()
    except Exception:
        # This fallback keeps tests and a rolling deployment functional before
        # the backend migration has reached every process.
        rollback = getattr(db, "rollback", None)
        if rollback is not None:
            await rollback()
        logger.warning("Central AI model policy unavailable; using environment defaults")
        configuration = None
    policy = _normalize(configuration)
    _current_policy.set(policy)
    credentials: dict[str, dict[str, Any]] = {}
    try:
        credential_result = await db.execute(
            text(
                "SELECT provider, encrypted_api_key, revision, source, status "
                "FROM ai_provider_credentials"
            )
        )
        for row in credential_result.mappings().all():
            provider = str(row.get("provider") or "").lower()
            encrypted = row.get("encrypted_api_key")
            status = str(row.get("status") or "")
            api_key = None
            if encrypted and status != "disconnected":
                digest = hashlib.sha256(
                    settings.ai_credential_encryption_key.encode("utf-8")
                ).digest()
                cipher = Fernet(base64.urlsafe_b64encode(digest))
                try:
                    api_key = cipher.decrypt(str(encrypted).encode("ascii")).decode("utf-8")
                except (InvalidToken, UnicodeError) as exc:
                    raise RuntimeError(
                        f"Stored {provider} credential cannot be decrypted with the configured master key"
                    ) from exc
            credentials[provider] = {
                "api_key": api_key,
                "revision": int(row.get("revision") or 0),
                "source": row.get("source"),
                "status": status,
            }
    except RuntimeError:
        raise
    except Exception:
        rollback = getattr(db, "rollback", None)
        if rollback is not None:
            await rollback()
        logger.warning("Central AI credentials unavailable; using environment fallbacks")
    for provider, api_key in {
        "openai": settings.openai_api_key,
        "anthropic": settings.anthropic_api_key,
        "gemini": settings.gemini_api_key,
    }.items():
        if provider not in credentials and api_key:
            credentials[provider] = {
                "api_key": api_key,
                "revision": 0,
                "source": "environment",
                "status": "connected",
            }
    _current_credentials.set(credentials)
    return policy


def resolve_provider_api_key(provider: str) -> str | None:
    normalized = provider.strip().lower()
    entry = _current_credentials.get().get(normalized)
    if entry is not None:
        return entry.get("api_key")
    return {
        "openai": settings.openai_api_key,
        "anthropic": settings.anthropic_api_key,
        "gemini": settings.gemini_api_key,
    }.get(normalized) or None


def get_ai_runtime_snapshot() -> dict[str, Any]:
    return {
        "policy": deepcopy(_current_policy.get()),
        "credentials": {
            provider: {
                "revision": entry.get("revision", 0),
                "source": entry.get("source"),
                "status": entry.get("status"),
            }
            for provider, entry in _current_credentials.get().items()
        },
    }


def resolve_ai_model(
    workload: str | None,
    *,
    model: str | None = None,
    provider: str | None = None,
) -> tuple[str, str]:
    if workload:
        entry = _current_policy.get().get(workload)
        if entry:
            return provider or entry["provider"], model or entry["model_id"]
    return provider or "openai", model or settings.openai_model
