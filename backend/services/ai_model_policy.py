"""Durable routing policy for the application's generative AI workloads."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from config import ANTHROPIC_API_KEY, DEEPSEEK_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY, OPENAI_VISION_MODEL
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
    "workspace_analysis": {
        "label": "Workspace analysis",
        "description": "Cited statement summaries, comparisons, and balanced Theory analysis.",
        "group": "Investigation",
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
    "financial_vision": {
        "label": "Statement page images",
        "description": "Reads held bank statement pages from their images; saved only when the figures reconcile exactly.",
        "group": "Financial",
    },
}

# Statement page images are read by a chain of models, in order (Neil, 2026-10-28): DeepSeek first ("the reader of
# choice": deepseek-flash, the DeepSeek model that takes images, measured on 20 statements against an image-checked
# answer key: 1 line error where OpenAI made 4), OpenAI the failsafe when DeepSeek fails or its reading does not prove.
# OpenAI model: gpt-5.6-terra, Loupe's default OpenAI model, measured on held BNB2 statements in document mode to
# prove 7 of 24 where gpt-4o (OPENAI_VISION_MODEL) proved 2. LOUPE_FINANCIAL_VISION_MODEL overrides the OpenAI model;
# the AI settings page edits the chain. Only models that read images may be in it (ai_model_capabilities).
def _financial_vision_model() -> str:
    import os
    chosen = (os.environ.get("LOUPE_FINANCIAL_VISION_MODEL") or "gpt-5.6-terra").strip()
    model = get_model_by_id(chosen)
    return chosen if model and model.provider == LLMProvider.OPENAI else (
        OPENAI_VISION_MODEL if get_model_by_id(OPENAI_VISION_MODEL) else "gpt-4o")


# Workloads read by an ordered chain of models (the first that proves its reading is used).
CHAIN_WORKLOADS = frozenset({"financial_vision"})
MAX_CHAIN = 3
FINANCIAL_VISION_DEEPSEEK = {"provider": "deepseek", "model_id": "deepseek-flash"}
FINANCIAL_VISION_OPENAI = {"provider": "openai", "model_id": _financial_vision_model()}
FINANCIAL_VISION_CHAIN = [dict(FINANCIAL_VISION_DEEPSEEK), dict(FINANCIAL_VISION_OPENAI)]
FINANCIAL_VISION_DEFAULT = {**FINANCIAL_VISION_CHAIN[0], "chain": deepcopy(FINANCIAL_VISION_CHAIN)}


DEFAULT_POLICY: dict[str, dict[str, str]] = {
    "chat": {"provider": "openai", "model_id": "gpt-5.6-terra"},
    "agent": {"provider": "openai", "model_id": "gpt-5.6-sol"},
    "workspace_analysis": {"provider": "openai", "model_id": "gpt-5.6-sol"},
    "ingestion_extraction": {"provider": "openai", "model_id": "gpt-5.6-terra"},
    "ingestion_resolution": {"provider": "openai", "model_id": "gpt-5.6-terra"},
    "ingestion_entity_summary": {"provider": "openai", "model_id": "gpt-5.6-terra"},
    "ingestion_document_summary": {"provider": "openai", "model_id": "gpt-5.6-sol"},
    "ingestion_quality": {"provider": "openai", "model_id": "gpt-5.6-terra"},
    "financial_vision": dict(FINANCIAL_VISION_DEFAULT),
}

PROVIDER_DEFAULTS: dict[str, dict[str, dict[str, str]]] = {
    "openai": deepcopy(DEFAULT_POLICY),
    "anthropic": {
        "chat": {"provider": "anthropic", "model_id": "claude-sonnet-5"},
        "agent": {"provider": "anthropic", "model_id": "claude-opus-4-8"},
        "workspace_analysis": {"provider": "anthropic", "model_id": "claude-opus-4-8"},
        "ingestion_extraction": {"provider": "anthropic", "model_id": "claude-sonnet-5"},
        "ingestion_resolution": {"provider": "anthropic", "model_id": "claude-sonnet-5"},
        "ingestion_entity_summary": {"provider": "anthropic", "model_id": "claude-sonnet-5"},
        "ingestion_document_summary": {"provider": "anthropic", "model_id": "claude-opus-4-8"},
        "ingestion_quality": {"provider": "anthropic", "model_id": "claude-sonnet-5"},
        "financial_vision": dict(FINANCIAL_VISION_DEFAULT),
    },
    "gemini": {
        "chat": {"provider": "gemini", "model_id": "gemini-3.6-flash"},
        "agent": {"provider": "gemini", "model_id": "gemini-3.5-flash"},
        "workspace_analysis": {"provider": "gemini", "model_id": "gemini-3.5-flash"},
        "ingestion_extraction": {"provider": "gemini", "model_id": "gemini-3.6-flash"},
        "ingestion_resolution": {"provider": "gemini", "model_id": "gemini-3.6-flash"},
        "ingestion_entity_summary": {"provider": "gemini", "model_id": "gemini-3.6-flash"},
        "ingestion_document_summary": {"provider": "gemini", "model_id": "gemini-3.5-flash"},
        "ingestion_quality": {"provider": "gemini", "model_id": "gemini-3.6-flash"},
        "financial_vision": dict(FINANCIAL_VISION_DEFAULT),
    },
    "deepseek": {
        "chat": {"provider": "deepseek", "model_id": "deepseek-v4-flash"},
        "agent": {"provider": "deepseek", "model_id": "deepseek-v4-pro"},
        "workspace_analysis": {"provider": "deepseek", "model_id": "deepseek-v4-pro"},
        "ingestion_extraction": {"provider": "deepseek", "model_id": "deepseek-v4-flash"},
        "ingestion_resolution": {"provider": "deepseek", "model_id": "deepseek-v4-flash"},
        "ingestion_entity_summary": {"provider": "deepseek", "model_id": "deepseek-v4-flash"},
        "ingestion_document_summary": {"provider": "deepseek", "model_id": "deepseek-v4-pro"},
        "ingestion_quality": {"provider": "deepseek", "model_id": "deepseek-v4-flash"},
        "financial_vision": dict(FINANCIAL_VISION_DEFAULT),
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
        "deepseek": bool(DEEPSEEK_API_KEY),
    }.get(provider.lower(), False)


def _entry(value: Any) -> dict[str, str] | None:
    """{provider, model_id} when ``value`` names a known model of that provider, else None."""
    if not isinstance(value, dict):
        return None
    provider = str(value.get("provider") or "").strip().lower()
    model_id = str(value.get("model_id") or "").strip()
    model = get_model_by_id(model_id)
    if model and model.provider.value == provider:
        return {"provider": provider, "model_id": model_id}
    return None


def _stored_chain(entry: dict[str, Any]) -> list[dict[str, str]]:
    """A stored chain workload's models in order. A setting saved before chains existed (one model) keeps that model
    as the failsafe of its provider behind the default chain's other providers."""
    if isinstance(entry.get("chain"), list):
        chain: list[dict[str, str]] = []
        for value in entry["chain"]:
            found = _entry(value)
            if found and found not in chain:
                chain.append(found)
        return chain[:MAX_CHAIN] or deepcopy(FINANCIAL_VISION_CHAIN)
    single = _entry(entry)
    if single is None:
        return deepcopy(FINANCIAL_VISION_CHAIN)
    return [dict(e) if e["provider"] != single["provider"] else single for e in FINANCIAL_VISION_CHAIN]


def _with_chain(chain: list[dict[str, str]]) -> dict[str, Any]:
    return {**chain[0], "chain": deepcopy(chain)}


def _normalized_configuration(configuration: Any) -> dict[str, dict[str, Any]]:
    result = deepcopy(DEFAULT_POLICY)
    if not isinstance(configuration, dict):
        return result
    for workload in WORKLOADS:
        entry = configuration.get(workload)
        if not isinstance(entry, dict):
            continue
        if workload in CHAIN_WORKLOADS:
            result[workload] = _with_chain(_stored_chain(entry))
            continue
        found = _entry(entry)
        if found:
            result[workload] = found
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


def get_workload_chain(db: Session, workload: str) -> list[dict[str, str]]:
    """The workload's models in the order they are tried (a workload without a chain: its one model)."""
    if workload not in WORKLOADS:
        raise ValueError(f"Unknown AI workload: {workload}")
    policy, _ = get_policy(db)
    entry = policy[workload]
    return deepcopy(entry.get("chain") or [{"provider": entry["provider"], "model_id": entry["model_id"]}])


# Workloads that send page images (each must use a model that takes images).
IMAGE_WORKLOADS = frozenset({"financial_vision"})


def _provider_key(provider: str, db: Session | None) -> str | None:
    if db is None:
        return DEEPSEEK_API_KEY if provider == "deepseek" else None
    try:
        from services.ai_provider_credentials import get_provider_api_key
        return get_provider_api_key(db, provider)
    except Exception:  # noqa: BLE001 - no key: the capability check fails closed
        return None


def _validated_entry(workload: str, entry: Any, db: Session | None) -> dict[str, str]:
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
    if (workload.startswith("ingestion_") or workload in ("workspace_analysis", "financial_vision")) and not model.supports_structured_output:
        raise ValueError(f"{model_id} does not support reliable structured output")
    if workload in IMAGE_WORKLOADS:
        # Page images only go to a model that takes images (services/ai_model_capabilities): a text-only model
        # can accept the request and answer without having read the page.
        from services.ai_model_capabilities import accepts_images
        api_key = None
        if provider == "deepseek":
            api_key = _provider_key(provider, db)
        readable, why = accepts_images(provider, model_id, api_key=api_key)
        if not readable:
            raise ValueError(
                f"{model.name} cannot read page images, so it "
                f"cannot be used for {WORKLOADS[workload]['label']} ({why}). Choose a model that reads images."
            )
    return {"provider": provider, "model_id": model_id}


def validate_policy(
    configuration: Any,
    *,
    require_configured_provider: bool = True,
    db: Session | None = None,
) -> dict[str, dict[str, Any]]:
    if not isinstance(configuration, dict):
        raise ValueError("configuration must be an object")
    missing = sorted(set(WORKLOADS) - set(configuration))
    unknown = sorted(set(configuration) - set(WORKLOADS))
    if missing:
        raise ValueError(f"Missing workloads: {', '.join(missing)}")
    if unknown:
        raise ValueError(f"Unknown workloads: {', '.join(unknown)}")

    validated: dict[str, dict[str, Any]] = {}
    for workload, entry in configuration.items():
        if workload in CHAIN_WORKLOADS and isinstance(entry, dict) and entry.get("chain") is not None:
            values = entry["chain"]
            if not isinstance(values, list) or not values:
                raise ValueError(f"{WORKLOADS[workload]['label']} needs at least one model")
            if len(values) > MAX_CHAIN:
                raise ValueError(f"{WORKLOADS[workload]['label']} takes at most {MAX_CHAIN} models")
            chain = [_validated_entry(workload, value, db) for value in values]
            if len({(e["provider"], e["model_id"]) for e in chain}) != len(chain):
                raise ValueError(f"{WORKLOADS[workload]['label']} lists the same model twice")
            # The chain starts at the first connected provider; at least one must be connected.
            if require_configured_provider and not any(provider_is_configured(e["provider"], db) for e in chain):
                raise ValueError(
                    f"No provider of {WORKLOADS[workload]['label']} is configured on the server. Add an API key first."
                )
            validated[workload] = _with_chain(chain)
            continue
        found = _validated_entry(workload, entry, db)
        if require_configured_provider and not provider_is_configured(found["provider"], db):
            raise ValueError(
                f"{found['provider'].title()} is not configured on the server. Add its API key first."
            )
        validated[workload] = _with_chain([found]) if workload in CHAIN_WORKLOADS else found
    return validated


def _keep_chains(db: Session, configuration: Any) -> Any:
    """A save that names only a chain workload's first model (a client that does not edit chains) keeps the rest
    of the current chain: the named model goes first, the current chain's models of other providers follow."""
    if not isinstance(configuration, dict):
        return configuration
    current, _ = get_policy(db)
    result = dict(configuration)
    for workload in CHAIN_WORKLOADS:
        entry = result.get(workload)
        if not isinstance(entry, dict) or entry.get("chain") is not None:
            continue
        first = {"provider": str(entry.get("provider") or "").strip().lower(),
                 "model_id": str(entry.get("model_id") or "").strip()}
        rest = [e for e in current[workload].get("chain") or [] if e["provider"] != first["provider"]]
        result[workload] = {**first, "chain": [first, *rest]}
    return result


def save_policy(
    db: Session,
    *,
    configuration: Any,
    expected_revision: int | None,
    updated_by: str | None,
) -> AIModelPolicy:
    validated = validate_policy(_keep_chains(db, configuration), db=db)
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
