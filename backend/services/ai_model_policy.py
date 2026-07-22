"""Durable routing policy for the application's generative AI workloads."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from config import ANTHROPIC_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY
from models.llm_models import LLMProvider, get_model_by_id
from postgres.models.runtime_state import AIModelPolicy


POLICY_KEY = "default"

WORKLOADS: dict[str, dict[str, str]] = {
    "chat": {
        "label": "AI chat",
        "description": "The main AI Chat tab and the right-rail chat.",
        "group": "Interactive",
    },
    "agent": {
        "label": "AI agent",
        "description": "Tool-using investigation agents.",
        "group": "Interactive",
    },
    "ingestion_extraction": {
        "label": "Entity extraction",
        "description": "Entities, facts, and relationships extracted from source text.",
        "group": "Ingestion",
    },
    "ingestion_resolution": {
        "label": "Entity resolution",
        "description": "Deduplication and canonical identity decisions.",
        "group": "Ingestion",
    },
    "ingestion_entity_summary": {
        "label": "Entity summaries",
        "description": "Evidence-bound summaries shown on graph entities.",
        "group": "Ingestion",
    },
    "ingestion_document_summary": {
        "label": "Document summaries",
        "description": "Comprehensive summaries shown with evidence files.",
        "group": "Ingestion",
    },
    "ingestion_quality": {
        "label": "Fact checking",
        "description": "Claim entailment and final summary quality checks.",
        "group": "Ingestion",
    },
}


DEFAULT_POLICY: dict[str, dict[str, str]] = {
    "chat": {"provider": "openai", "model_id": "gpt-5.6-terra"},
    "agent": {"provider": "openai", "model_id": "gpt-5.6-sol"},
    "ingestion_extraction": {"provider": "openai", "model_id": "gpt-5.6-terra"},
    "ingestion_resolution": {"provider": "openai", "model_id": "gpt-5.6-terra"},
    "ingestion_entity_summary": {"provider": "openai", "model_id": "gpt-5.6-terra"},
    "ingestion_document_summary": {"provider": "openai", "model_id": "gpt-5.6-sol"},
    "ingestion_quality": {"provider": "openai", "model_id": "gpt-5.6-terra"},
}

PROVIDER_DEFAULTS: dict[str, dict[str, dict[str, str]]] = {
    "openai": deepcopy(DEFAULT_POLICY),
    "anthropic": {
        "chat": {"provider": "anthropic", "model_id": "claude-sonnet-5"},
        "agent": {"provider": "anthropic", "model_id": "claude-opus-4-8"},
        "ingestion_extraction": {"provider": "anthropic", "model_id": "claude-sonnet-5"},
        "ingestion_resolution": {"provider": "anthropic", "model_id": "claude-sonnet-5"},
        "ingestion_entity_summary": {"provider": "anthropic", "model_id": "claude-sonnet-5"},
        "ingestion_document_summary": {"provider": "anthropic", "model_id": "claude-opus-4-8"},
        "ingestion_quality": {"provider": "anthropic", "model_id": "claude-sonnet-5"},
    },
    "gemini": {
        "chat": {"provider": "gemini", "model_id": "gemini-3.6-flash"},
        "agent": {"provider": "gemini", "model_id": "gemini-3.5-flash"},
        "ingestion_extraction": {"provider": "gemini", "model_id": "gemini-3.6-flash"},
        "ingestion_resolution": {"provider": "gemini", "model_id": "gemini-3.6-flash"},
        "ingestion_entity_summary": {"provider": "gemini", "model_id": "gemini-3.6-flash"},
        "ingestion_document_summary": {"provider": "gemini", "model_id": "gemini-3.5-flash"},
        "ingestion_quality": {"provider": "gemini", "model_id": "gemini-3.6-flash"},
    },
}


def provider_is_configured(provider: str, db: Session | None = None) -> bool:
    if db is not None:
        from services.ai_provider_credentials import credential_store

        try:
            return credential_store.get_connection(db, provider).configured
        except ValueError:
            return False
    return {
        "openai": bool(OPENAI_API_KEY),
        "anthropic": bool(ANTHROPIC_API_KEY),
        "gemini": bool(GEMINI_API_KEY),
    }.get(provider.lower(), False)


def _normalized_configuration(configuration: Any) -> dict[str, dict[str, str]]:
    result = deepcopy(DEFAULT_POLICY)
    if not isinstance(configuration, dict):
        return result
    for workload in WORKLOADS:
        entry = configuration.get(workload)
        if not isinstance(entry, dict):
            continue
        provider = str(entry.get("provider") or "").strip().lower()
        model_id = str(entry.get("model_id") or "").strip()
        model = get_model_by_id(model_id)
        if model and model.provider.value == provider:
            result[workload] = {"provider": provider, "model_id": model_id}
    return result


def get_policy(db: Session) -> tuple[dict[str, dict[str, str]], int]:
    record = db.get(AIModelPolicy, POLICY_KEY)
    if record is None:
        return deepcopy(DEFAULT_POLICY), 0
    return _normalized_configuration(record.configuration), record.revision


def get_workload_model(db: Session, workload: str) -> tuple[str, str]:
    if workload not in WORKLOADS:
        raise ValueError(f"Unknown AI workload: {workload}")
    policy, _ = get_policy(db)
    entry = policy[workload]
    return entry["provider"], entry["model_id"]


def validate_policy(
    configuration: Any,
    *,
    require_configured_provider: bool = True,
    db: Session | None = None,
) -> dict[str, dict[str, str]]:
    if not isinstance(configuration, dict):
        raise ValueError("configuration must be an object")
    missing = sorted(set(WORKLOADS) - set(configuration))
    unknown = sorted(set(configuration) - set(WORKLOADS))
    if missing:
        raise ValueError(f"Missing workloads: {', '.join(missing)}")
    if unknown:
        raise ValueError(f"Unknown workloads: {', '.join(unknown)}")

    validated: dict[str, dict[str, str]] = {}
    for workload, entry in configuration.items():
        if not isinstance(entry, dict):
            raise ValueError(f"{workload} must be an object")
        provider = str(entry.get("provider") or "").strip().lower()
        model_id = str(entry.get("model_id") or "").strip()
        try:
            provider_enum = LLMProvider(provider)
        except ValueError as exc:
            raise ValueError(f"Unsupported provider for {workload}: {provider}") from exc
        model = get_model_by_id(model_id)
        if model is None:
            raise ValueError(f"Unknown model for {workload}: {model_id}")
        if model.provider != provider_enum:
            raise ValueError(f"{model_id} does not belong to {provider}")
        if workload == "agent" and not model.supports_agent:
            raise ValueError(f"{model_id} does not support agent tool use")
        if workload.startswith("ingestion_") and not model.supports_structured_output:
            raise ValueError(f"{model_id} does not support reliable structured output")
        if require_configured_provider and not provider_is_configured(provider, db):
            raise ValueError(
                f"{provider.title()} is not configured on the server. Add its API key first."
            )
        validated[workload] = {"provider": provider, "model_id": model_id}
    return validated


def save_policy(
    db: Session,
    *,
    configuration: Any,
    expected_revision: int | None,
    updated_by: str | None,
) -> AIModelPolicy:
    validated = validate_policy(configuration, db=db)
    record = db.get(AIModelPolicy, POLICY_KEY)
    current_revision = record.revision if record else 0
    if expected_revision is not None and expected_revision != current_revision:
        raise RuntimeError(
            "AI settings changed in another session. Reload them before saving."
        )
    if record is None:
        record = AIModelPolicy(
            key=POLICY_KEY,
            revision=1,
            configuration=validated,
            updated_by=updated_by,
        )
        db.add(record)
    else:
        record.revision += 1
        record.configuration = validated
        record.updated_by = updated_by
    db.commit()
    db.refresh(record)
    return record
