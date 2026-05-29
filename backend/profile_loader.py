"""
Profile configuration loader.

Runtime profile configuration is sourced from Postgres processing profiles and
environment defaults. The backend no longer reads profiles/*.json at startup.
"""

from __future__ import annotations

import copy
import os
from typing import Any


PROFILE_NAME = os.getenv("PROFILE", "generic")


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        print(f"Warning: Invalid {name}={raw!r}; using {default}")
        return default


DEFAULT_PROFILE: dict[str, Any] = {
    "name": "generic",
    "description": "General purpose knowledge extraction",
    "case_type": "General Analysis",
    "ingestion": {
        "system_context": os.getenv(
            "INGESTION_SYSTEM_CONTEXT",
            (
                "You are an expert analyst extracting entities and relationships from "
                "documents. Focus on identifying key people, organizations, locations, "
                "events, dates, and their connections. Capture relevant details that "
                "establish relationships between entities. Be thorough but precise."
            ),
        ),
        "special_entity_types": [],
        "mandatory_instructions": [],
        "temperature": _env_float("INGESTION_TEMPERATURE", 1.0),
    },
    "chat": {
        "system_context": os.getenv(
            "CHAT_SYSTEM_CONTEXT",
            "You are an AI assistant helping to analyze and understand documents.",
        ),
        "analysis_guidance": os.getenv(
            "CHAT_ANALYSIS_GUIDANCE",
            "Provide clear explanations and highlight important connections.",
        ),
        "temperature": _env_float("CHAT_TEMPERATURE", 1.0),
    },
    "llm_config": None,
    "folder_processing": None,
}


def _load_postgres_profile(profile_name: str) -> dict[str, Any] | None:
    try:
        from sqlalchemy import select

        from postgres.models.processing_profile import ProcessingProfile
        from postgres.session import get_background_session

        with get_background_session() as db:
            row = db.execute(
                select(
                    ProcessingProfile.name,
                    ProcessingProfile.description,
                    ProcessingProfile.context_instructions,
                    ProcessingProfile.mandatory_instructions,
                    ProcessingProfile.special_entity_types,
                    ProcessingProfile.chat_config,
                    ProcessingProfile.llm_config,
                    ProcessingProfile.folder_processing,
                ).where(ProcessingProfile.name == profile_name)
            ).mappings().first()
            return dict(row) if row else None
    except Exception:
        return None


def load_profile(profile_name: str | None = None, *, allow_postgres: bool = True) -> dict[str, Any]:
    """
    Load a profile configuration by name.

    Falls back to environment defaults if Postgres is unavailable or the named
    processing profile does not exist.
    """
    name = profile_name or PROFILE_NAME or "generic"
    profile = copy.deepcopy(DEFAULT_PROFILE)
    profile["name"] = name

    db_profile = _load_postgres_profile(name) if allow_postgres else None
    if db_profile is None and allow_postgres and name != "generic":
        db_profile = _load_postgres_profile("generic")

    if db_profile is not None:
        profile["name"] = db_profile["name"]
        profile["description"] = db_profile.get("description") or profile["description"]
        if db_profile.get("context_instructions"):
            profile["ingestion"]["system_context"] = db_profile["context_instructions"]
        profile["ingestion"]["mandatory_instructions"] = list(
            db_profile.get("mandatory_instructions") or []
        )
        profile["ingestion"]["special_entity_types"] = list(
            db_profile.get("special_entity_types") or []
        )
        if db_profile.get("chat_config"):
            profile["chat"].update(dict(db_profile["chat_config"]))
        if db_profile.get("llm_config"):
            profile["llm_config"] = dict(db_profile["llm_config"])
        if db_profile.get("folder_processing"):
            profile["folder_processing"] = dict(db_profile["folder_processing"])

    return profile


def get_ingestion_config(profile_name: str | None = None, *, allow_postgres: bool = True) -> dict[str, Any]:
    """Get the ingestion configuration section from a profile."""
    return load_profile(profile_name, allow_postgres=allow_postgres).get("ingestion", {})


def get_chat_config(profile_name: str | None = None, *, allow_postgres: bool = True) -> dict[str, Any]:
    """Get the chat configuration section from a profile."""
    return load_profile(profile_name, allow_postgres=allow_postgres).get("chat", {})


def get_llm_config(
    profile_name: str | None = None,
    *,
    force_reload: bool = False,
    allow_postgres: bool = True,
) -> dict[str, Any] | None:
    """Get the optional LLM override configuration from a profile."""
    _ = force_reload
    return load_profile(profile_name, allow_postgres=allow_postgres).get("llm_config")


def get_folder_processing_config(
    profile_name: str | None = None,
    *,
    allow_postgres: bool = True,
) -> dict[str, Any] | None:
    """Get the optional folder-processing configuration from a profile."""
    return load_profile(profile_name, allow_postgres=allow_postgres).get("folder_processing")
