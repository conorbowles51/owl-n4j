"""Encrypted, deployment-wide credentials for Loupe's cloud AI providers."""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from config import (
    AI_CREDENTIAL_ENCRYPTION_KEY,
    ANTHROPIC_API_KEY,
    GEMINI_API_KEY,
    OPENAI_API_KEY,
)
from postgres.models.runtime_state import AIProviderCredential


SUPPORTED_PROVIDERS = ("openai", "anthropic", "gemini")


class CredentialRevisionConflict(RuntimeError):
    pass


class CredentialDecryptionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderConnection:
    provider: str
    configured: bool
    status: str
    source: str | None
    key_last_four: str | None
    revision: int
    validated_at: datetime | None
    validation_error_code: str | None


def _fernet_key(secret: str) -> bytes:
    if not secret:
        raise ValueError("AI credential encryption key is not configured")
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


class AIProviderCredentialStore:
    def __init__(
        self,
        *,
        encryption_key: str,
        environment_keys: Mapping[str, str | None] | None = None,
    ) -> None:
        self._cipher = Fernet(_fernet_key(encryption_key))
        self._environment_keys = {
            provider: (value or "").strip()
            for provider, value in (environment_keys or {}).items()
            if provider in SUPPORTED_PROVIDERS
        }

    @staticmethod
    def _provider(provider: str) -> str:
        normalized = provider.strip().lower()
        if normalized not in SUPPORTED_PROVIDERS:
            raise ValueError(f"Unsupported AI provider: {provider}")
        return normalized

    def _encrypt(self, api_key: str) -> str:
        return self._cipher.encrypt(api_key.encode("utf-8")).decode("ascii")

    def _decrypt(self, encrypted_api_key: str) -> str:
        try:
            return self._cipher.decrypt(encrypted_api_key.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeError) as exc:
            raise CredentialDecryptionError(
                "The stored AI credential cannot be decrypted with the configured master key"
            ) from exc

    def get_api_key(self, db: Session, provider: str) -> str | None:
        normalized = self._provider(provider)
        record = db.get(AIProviderCredential, normalized)
        if record is not None:
            if record.status == "disconnected" or not record.encrypted_api_key:
                return None
            return self._decrypt(record.encrypted_api_key)
        return self._environment_keys.get(normalized) or None

    def get_connection(self, db: Session, provider: str) -> ProviderConnection:
        normalized = self._provider(provider)
        record = db.get(AIProviderCredential, normalized)
        if record is not None:
            configured = bool(record.encrypted_api_key) and record.status == "connected"
            return ProviderConnection(
                provider=normalized,
                configured=configured,
                status=record.status,
                source=record.source,
                key_last_four=record.key_last_four,
                revision=record.revision,
                validated_at=record.validated_at,
                validation_error_code=record.validation_error_code,
            )
        environment_key = self._environment_keys.get(normalized) or ""
        return ProviderConnection(
            provider=normalized,
            configured=bool(environment_key),
            status="connected" if environment_key else "disconnected",
            source="environment" if environment_key else None,
            key_last_four=environment_key[-4:] if environment_key else None,
            revision=0,
            validated_at=None,
            validation_error_code=None,
        )

    def list_connections(self, db: Session) -> list[ProviderConnection]:
        return [self.get_connection(db, provider) for provider in SUPPORTED_PROVIDERS]

    def save(
        self,
        db: Session,
        *,
        provider: str,
        api_key: str,
        expected_revision: int | None,
        updated_by: str | None,
        validated_at: datetime | None = None,
    ) -> ProviderConnection:
        normalized = self._provider(provider)
        clean_key = api_key.strip()
        if not clean_key:
            raise ValueError("API key cannot be empty")
        record = db.get(AIProviderCredential, normalized)
        current_revision = record.revision if record is not None else 0
        if expected_revision is not None and expected_revision != current_revision:
            raise CredentialRevisionConflict(
                "AI provider credentials changed in another session. Reload before saving."
            )
        now = datetime.now(timezone.utc)
        if record is None:
            record = AIProviderCredential(
                provider=normalized,
                encrypted_api_key=self._encrypt(clean_key),
                key_last_four=clean_key[-4:],
                status="connected",
                source="database",
                revision=1,
                validated_at=validated_at or now,
                validation_error_code=None,
                created_by=updated_by,
                updated_by=updated_by,
            )
            db.add(record)
        else:
            record.encrypted_api_key = self._encrypt(clean_key)
            record.key_last_four = clean_key[-4:]
            record.status = "connected"
            record.source = "database"
            record.revision += 1
            record.validated_at = validated_at or now
            record.validation_error_code = None
            record.updated_by = updated_by
        db.commit()
        return self.get_connection(db, normalized)

    def disconnect(
        self,
        db: Session,
        *,
        provider: str,
        expected_revision: int | None,
        updated_by: str | None,
    ) -> ProviderConnection:
        normalized = self._provider(provider)
        record = db.get(AIProviderCredential, normalized)
        current_revision = record.revision if record is not None else 0
        if expected_revision is not None and expected_revision != current_revision:
            raise CredentialRevisionConflict(
                "AI provider credentials changed in another session. Reload before disconnecting."
            )
        if record is None:
            record = AIProviderCredential(
                provider=normalized,
                encrypted_api_key=None,
                key_last_four=None,
                status="disconnected",
                source="database",
                revision=1,
                created_by=updated_by,
                updated_by=updated_by,
            )
            db.add(record)
        else:
            record.encrypted_api_key = None
            record.key_last_four = None
            record.status = "disconnected"
            record.source = "database"
            record.revision += 1
            record.validated_at = None
            record.validation_error_code = None
            record.updated_by = updated_by
        db.commit()
        return self.get_connection(db, normalized)

    def mark_validation(
        self,
        db: Session,
        *,
        provider: str,
        status: str,
        error_code: str | None = None,
    ) -> ProviderConnection:
        normalized = self._provider(provider)
        record = db.get(AIProviderCredential, normalized)
        if record is None:
            return self.get_connection(db, normalized)
        record.status = status
        record.validation_error_code = error_code
        record.validated_at = datetime.now(timezone.utc)
        db.commit()
        return self.get_connection(db, normalized)


credential_store = AIProviderCredentialStore(
    encryption_key=AI_CREDENTIAL_ENCRYPTION_KEY,
    environment_keys={
        "openai": OPENAI_API_KEY,
        "anthropic": ANTHROPIC_API_KEY,
        "gemini": GEMINI_API_KEY,
    },
)


def get_provider_api_key(db: Session, provider: str) -> str | None:
    return credential_store.get_api_key(db, provider)
