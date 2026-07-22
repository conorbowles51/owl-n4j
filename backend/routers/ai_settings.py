"""Deployment-wide AI provider connections and workload routing for Loupe."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import requests
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy.orm import Session

from config import EMBEDDING_PROVIDER
from models.llm_models import AVAILABLE_MODELS
from postgres.models.enums import GlobalRole
from postgres.models.user import User
from postgres.session import get_db
from routers.users import get_current_db_user, require_admin, require_super_admin
from services.ai_model_policy import (
    PROVIDER_DEFAULTS,
    WORKLOADS,
    get_policy,
    save_policy,
)
from services.ai_provider_credentials import (
    SUPPORTED_PROVIDERS,
    CredentialRevisionConflict,
    ProviderConnection,
    credential_store,
)
from services.system_log_service import LogOrigin, LogType, system_log_service


router = APIRouter(prefix="/api/ai-settings", tags=["ai-settings"])

PROVIDER_METADATA = {
    "openai": {
        "display_name": "OpenAI",
        "description": "Generative models, embeddings, audio transcription, and optional vision.",
    },
    "anthropic": {
        "display_name": "Anthropic",
        "description": "Claude models for chat, investigation agents, and evidence analysis.",
    },
    "gemini": {
        "display_name": "Google Gemini",
        "description": "Gemini models for chat, structured extraction, and analysis.",
    },
}


class ProviderConnectionResponse(BaseModel):
    id: str
    display_name: str
    description: str
    configured: bool
    status: str
    source: str | None = None
    key_last_four: str | None = None
    revision: int
    validated_at: datetime | None = None
    validation_error_code: str | None = None
    in_use_by: list[str] = Field(default_factory=list)


class AISettingsResponse(BaseModel):
    policy_revision: int
    default_provider: str
    providers: list[ProviderConnectionResponse]
    models: list[dict[str, Any]]
    workloads: dict[str, dict[str, str]]
    routing: dict[str, dict[str, str]]
    recommended_profiles: dict[str, dict[str, dict[str, str]]]
    supporting_services: list[dict[str, Any]]
    permissions: dict[str, bool]


class CredentialUpdateRequest(BaseModel):
    api_key: SecretStr
    expected_revision: int | None = None


class CredentialTestResponse(BaseModel):
    provider: str
    status: str
    available_models: list[str]
    tested_at: datetime


class PolicyModelConfig(BaseModel):
    provider: str
    model_id: str


class PolicyUpdateRequest(BaseModel):
    revision: int | None = None
    configuration: dict[str, PolicyModelConfig]


class ProviderCredentialInvalid(ValueError):
    pass


class ProviderUnavailable(RuntimeError):
    pass


def _error(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "message": message, "details": details}


def _connection_response(
    connection: ProviderConnection,
    *,
    in_use_by: list[str] | None = None,
) -> ProviderConnectionResponse:
    metadata = PROVIDER_METADATA[connection.provider]
    return ProviderConnectionResponse(
        id=connection.provider,
        display_name=metadata["display_name"],
        description=metadata["description"],
        configured=connection.configured,
        status=connection.status,
        source=connection.source,
        key_last_four=connection.key_last_four,
        revision=connection.revision,
        validated_at=connection.validated_at,
        validation_error_code=connection.validation_error_code,
        in_use_by=in_use_by or [],
    )


def _provider_for_policy(configuration: dict[str, dict[str, str]]) -> str:
    providers = {entry["provider"] for entry in configuration.values()}
    return next(iter(providers)) if len(providers) == 1 else "mixed"


def _provider_usage(configuration: dict[str, dict[str, str]]) -> dict[str, list[str]]:
    usage = {provider: [] for provider in SUPPORTED_PROVIDERS}
    for workload, entry in configuration.items():
        provider = entry.get("provider")
        if provider in usage:
            usage[provider].append(workload)
    return usage


def _supporting_services(db: Session) -> list[dict[str, Any]]:
    openai_ready = credential_store.get_connection(db, "openai").configured
    embedding_provider = "openai" if EMBEDDING_PROVIDER == "openai" else "local"
    return [
        {
            "id": "embeddings",
            "label": "Search embeddings",
            "provider": embedding_provider,
            "status": "ready" if embedding_provider != "openai" or openai_ready else "needs_key",
            "description": "Powers semantic evidence and entity search.",
        },
        {
            "id": "transcription",
            "label": "Audio transcription",
            "provider": "openai",
            "status": "ready" if openai_ready else "needs_key",
            "description": "Transcribes uploaded audio before ingestion.",
        },
        {
            "id": "pdf_ocr",
            "label": "PDF OCR",
            "provider": "tesseract",
            "status": "ready",
            "description": "Runs locally for scanned PDF pages.",
        },
    ]


def _settings_response(db: Session, user: User) -> AISettingsResponse:
    configuration, revision = get_policy(db)
    usage = _provider_usage(configuration)
    connections = credential_store.list_connections(db)
    return AISettingsResponse(
        policy_revision=revision,
        default_provider=_provider_for_policy(configuration),
        providers=[
            _connection_response(connection, in_use_by=usage[connection.provider])
            for connection in connections
        ],
        models=[
            {
                **model.to_dict(),
                "provider_configured": next(
                    connection.configured
                    for connection in connections
                    if connection.provider == model.provider.value
                ),
            }
            for model in AVAILABLE_MODELS
        ],
        workloads=WORKLOADS,
        routing=configuration,
        recommended_profiles=PROVIDER_DEFAULTS,
        supporting_services=_supporting_services(db),
        permissions={
            "can_edit_routing": user.global_role in (GlobalRole.admin, GlobalRole.super_admin),
            "can_manage_credentials": user.global_role == GlobalRole.super_admin,
        },
    )


def validate_provider_credential(provider: str, api_key: str) -> dict[str, Any]:
    """Validate authentication through each provider's non-generating model catalog."""
    try:
        if provider == "openai":
            response = requests.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=(10, 30),
            )
        elif provider == "anthropic":
            response = requests.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                timeout=(10, 30),
            )
        elif provider == "gemini":
            response = requests.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                headers={"x-goog-api-key": api_key},
                timeout=(10, 30),
            )
        else:
            raise ProviderCredentialInvalid(f"Unsupported AI provider: {provider}")
    except requests.RequestException as exc:
        response = getattr(exc, "response", None)
        if response is not None and response.status_code in (401, 403):
            raise ProviderCredentialInvalid(
                f"{PROVIDER_METADATA[provider]['display_name']} rejected this API key."
            ) from exc
        raise ProviderUnavailable(
            f"{PROVIDER_METADATA[provider]['display_name']} could not be reached."
        ) from exc
    if response.status_code in (401, 403):
        raise ProviderCredentialInvalid(
            f"{PROVIDER_METADATA[provider]['display_name']} rejected this API key."
        )
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ProviderUnavailable(
            f"{PROVIDER_METADATA[provider]['display_name']} could not validate this key."
        ) from exc
    payload = response.json()
    raw_models = payload.get("data") or payload.get("models") or []
    models = [str(item.get("id") or item.get("name") or "") for item in raw_models if isinstance(item, dict)]
    return {"models": [model for model in models if model]}


@router.get("", response_model=AISettingsResponse)
def get_ai_settings(
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    response.headers["Cache-Control"] = "no-store"
    return _settings_response(db, current_user)


@router.put(
    "/providers/{provider}/credential",
    response_model=ProviderConnectionResponse,
)
def save_provider_credential(
    provider: str,
    request: CredentialUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
):
    normalized = provider.strip().lower()
    if normalized not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_error("provider_not_found", "Unknown AI provider.", provider=provider),
        )
    api_key = request.api_key.get_secret_value().strip()
    try:
        validate_provider_credential(normalized, api_key)
        connection = credential_store.save(
            db,
            provider=normalized,
            api_key=api_key,
            expected_revision=request.expected_revision,
            updated_by=current_user.email,
        )
    except CredentialRevisionConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_error("credential_revision_conflict", str(exc), provider=normalized),
        ) from exc
    except (ProviderCredentialInvalid, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error("provider_credential_invalid", str(exc), provider=normalized),
        ) from exc
    except ProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error("provider_unavailable", str(exc), provider=normalized),
            headers={"Retry-After": "30"},
        ) from exc
    system_log_service.log(
        log_type=LogType.SYSTEM,
        origin=LogOrigin.BACKEND,
        action="AI provider credential saved",
        details={"provider": normalized, "revision": connection.revision},
        user=current_user.email,
        db=db,
    )
    db.commit()
    return _connection_response(connection)


@router.post(
    "/providers/{provider}:test",
    response_model=CredentialTestResponse,
)
def test_provider_credential(
    provider: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
):
    normalized = provider.strip().lower()
    if normalized not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=404, detail=_error("provider_not_found", "Unknown AI provider."))
    api_key = credential_store.get_api_key(db, normalized)
    if not api_key:
        raise HTTPException(
            status_code=409,
            detail=_error("provider_not_configured", "Add an API key before testing this provider."),
        )
    try:
        result = validate_provider_credential(normalized, api_key)
    except ProviderCredentialInvalid as exc:
        credential_store.mark_validation(
            db,
            provider=normalized,
            status="invalid",
            error_code="provider_credential_invalid",
        )
        raise HTTPException(status_code=422, detail=_error("provider_credential_invalid", str(exc))) from exc
    except ProviderUnavailable as exc:
        credential_store.mark_validation(
            db,
            provider=normalized,
            status="unavailable",
            error_code="provider_unavailable",
        )
        raise HTTPException(
            status_code=503,
            detail=_error("provider_unavailable", str(exc)),
            headers={"Retry-After": "30"},
        ) from exc
    connection = credential_store.mark_validation(
        db,
        provider=normalized,
        status="connected",
        error_code=None,
    )
    tested_at = datetime.now().astimezone()
    system_log_service.log(
        log_type=LogType.SYSTEM,
        origin=LogOrigin.BACKEND,
        action="AI provider credential tested",
        details={"provider": normalized, "revision": connection.revision},
        user=current_user.email,
        db=db,
    )
    db.commit()
    return CredentialTestResponse(
        provider=normalized,
        status="connected",
        available_models=result.get("models") or [],
        tested_at=tested_at,
    )


@router.delete("/providers/{provider}/credential", status_code=204)
def disconnect_provider_credential(
    provider: str,
    expected_revision: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin),
):
    normalized = provider.strip().lower()
    configuration, _ = get_policy(db)
    in_use_by = _provider_usage(configuration).get(normalized, [])
    if in_use_by:
        raise HTTPException(
            status_code=409,
            detail=_error(
                "provider_in_use",
                "Route these workloads to another connected provider before disconnecting.",
                provider=normalized,
                workloads=in_use_by,
            ),
        )
    try:
        connection = credential_store.disconnect(
            db,
            provider=normalized,
            expected_revision=expected_revision,
            updated_by=current_user.email,
        )
    except CredentialRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=_error("credential_revision_conflict", str(exc))) from exc
    system_log_service.log(
        log_type=LogType.SYSTEM,
        origin=LogOrigin.BACKEND,
        action="AI provider credential disconnected",
        details={"provider": normalized, "revision": connection.revision},
        user=current_user.email,
        db=db,
    )
    db.commit()
    return Response(status_code=204)


@router.put("/policy", response_model=AISettingsResponse)
def update_ai_policy(
    request: PolicyUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        record = save_policy(
            db,
            configuration={key: value.model_dump() for key, value in request.configuration.items()},
            expected_revision=request.revision,
            updated_by=current_user.email,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=_error("policy_revision_conflict", str(exc))) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=_error("policy_invalid", str(exc))) from exc
    system_log_service.log(
        log_type=LogType.SYSTEM,
        origin=LogOrigin.BACKEND,
        action="AI model routing saved",
        details={"revision": record.revision},
        user=current_user.email,
        db=db,
    )
    db.commit()
    return _settings_response(db, current_user)
