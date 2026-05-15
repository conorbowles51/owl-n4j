"""
Postgres-backed profile configuration loader for legacy ingestion scripts.

This module keeps the historical ingestion API shape, but it no longer reads
profiles/*.json at runtime. Runtime profile data is loaded through the backend
profile loader, which resolves Postgres processing profiles and environment
defaults.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from threading import Lock
from typing import Any

from logging_utils import log_progress


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
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
                "events, dates, and their connections. Be thorough but precise."
            ),
        ),
        "special_entity_types": [],
        "mandatory_instructions": [],
        "temperature": _float_env("INGESTION_TEMPERATURE", 1.0),
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
        "temperature": _float_env("CHAT_TEMPERATURE", 1.0),
    },
    "llm_config": None,
    "folder_processing": None,
}

_cache: dict[str, dict[str, Any]] = {}
_cache_lock = Lock()


def _database_url() -> str | None:
    try:
        from dotenv import load_dotenv

        project_root = Path(__file__).resolve().parents[2]
        load_dotenv(project_root / ".env")
        load_dotenv()
    except Exception:
        pass

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return None
    if db_url.startswith("postgresql://") and "+psycopg" not in db_url:
        return db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if db_url.startswith("postgres://") and "+psycopg" not in db_url:
        return db_url.replace("postgres://", "postgresql+psycopg://", 1)
    return db_url


def _json_value(value: Any, default: Any) -> Any:
    if value is None:
        return copy.deepcopy(default)
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return copy.deepcopy(default)
    return value


def _load_postgres_profile(profile_name: str) -> dict[str, Any] | None:
    db_url = _database_url()
    if not db_url:
        return None

    try:
        from sqlalchemy import create_engine, text
    except Exception:
        return None

    connect_args = {}
    if db_url.startswith("postgresql+psycopg://"):
        connect_args["connect_timeout"] = int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "2"))

    engine = None
    try:
        engine = create_engine(db_url, pool_pre_ping=True, connect_args=connect_args)
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT name,
                           description,
                           context_instructions,
                           mandatory_instructions,
                           special_entity_types,
                           chat_config,
                           llm_config,
                           folder_processing
                    FROM processing_profiles
                    WHERE name = :name
                    """
                ),
                {"name": profile_name},
            ).mappings().first()
            if row is None and profile_name != "generic":
                row = conn.execute(
                    text(
                        """
                        SELECT name,
                               description,
                               context_instructions,
                               mandatory_instructions,
                               special_entity_types,
                               chat_config,
                               llm_config,
                               folder_processing
                        FROM processing_profiles
                        WHERE name = 'generic'
                        """
                    )
                ).mappings().first()
    except Exception:
        return None
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                pass

    if row is None:
        return None

    profile = copy.deepcopy(DEFAULT_PROFILE)
    profile["name"] = row["name"]
    profile["description"] = row["description"] or profile["description"]
    if row["context_instructions"]:
        profile["ingestion"]["system_context"] = row["context_instructions"]
    profile["ingestion"]["mandatory_instructions"] = _json_value(row["mandatory_instructions"], [])
    profile["ingestion"]["special_entity_types"] = _json_value(row["special_entity_types"], [])
    chat_config = _json_value(row["chat_config"], {})
    if isinstance(chat_config, dict):
        profile["chat"].update(chat_config)
    profile["llm_config"] = _json_value(row["llm_config"], None)
    profile["folder_processing"] = _json_value(row["folder_processing"], None)
    return profile


def load_profile(profile_name: str | None = None, force_reload: bool = False) -> dict[str, Any]:
    """Load a profile configuration from Postgres-backed runtime configuration."""
    name = profile_name or os.getenv("PROFILE", "generic")

    if force_reload:
        with _cache_lock:
            _cache.pop(name, None)

    if name in _cache and not force_reload:
        return copy.deepcopy(_cache[name])

    with _cache_lock:
        if name in _cache and not force_reload:
            return copy.deepcopy(_cache[name])

        profile = _load_postgres_profile(name)
        if profile is None:
            profile = copy.deepcopy(DEFAULT_PROFILE)
            profile["name"] = name

        _cache[name] = copy.deepcopy(profile)
        log_progress(f"[profile_loader] Loaded Postgres-backed profile: {profile.get('name') or name}")
        return copy.deepcopy(profile)


def get_ingestion_config(profile_name: str | None = None) -> dict[str, Any]:
    """Get the ingestion configuration section from a profile."""
    return load_profile(profile_name).get("ingestion", {})


def get_chat_config(profile_name: str | None = None) -> dict[str, Any]:
    """Get the chat configuration section from a profile."""
    return load_profile(profile_name).get("chat", {})


def get_llm_config(profile_name: str | None = None, force_reload: bool = True) -> dict[str, Any] | None:
    """Get the optional LLM configuration from a profile."""
    return load_profile(profile_name, force_reload=force_reload).get("llm_config")


def get_folder_processing_config(profile_name: str | None = None) -> dict[str, Any] | None:
    """Get the optional folder-processing configuration from a profile."""
    return load_profile(profile_name).get("folder_processing")


def clear_profile_cache(profile_name: str | None = None) -> None:
    """Clear the cache for a specific profile or all profiles."""
    with _cache_lock:
        if profile_name:
            _cache.pop(profile_name, None)
            log_progress(f"[profile_loader] Cleared cache for profile: {profile_name}")
        else:
            _cache.clear()
            log_progress("[profile_loader] Cleared all profile caches")
