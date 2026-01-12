"""
Profile configuration loader.

Loads domain-specific prompts and settings from JSON profiles
for use during document ingestion and chat interactions.
"""

import json
from pathlib import Path
from typing import Any
from threading import Lock

from logging_utils import log_progress, log_warning

PROFILES_DIR = Path(__file__).parent.parent.parent / "profiles"

_cache: dict[str, dict[str, Any]] = {}
_cache_lock = Lock()


def load_profile(profile_name: str | None = None) -> dict[str, Any]:
    """
    Load a profile configuration by name. Thread-safe.

    Args:
        profile_name: Profile name (without .json). Defaults to 'generic'.

    Returns:
        Profile configuration dictionary.
    """
    name = profile_name or "generic"

    # Fast path: check cache without lock first
    if name in _cache:
        return _cache[name]

    # Slow path: acquire lock and load profile
    with _cache_lock:
        # Double-check after acquiring lock
        if name in _cache:
            return _cache[name]

        profile_path = PROFILES_DIR / f"{name}.json"

        if not profile_path.exists():
            log_warning(f"[profile_loader] Profile '{name}' not found, using 'generic'")
            profile_path = PROFILES_DIR / "generic.json"
            name = "generic"
            # Check cache again for generic
            if name in _cache:
                return _cache[name]

        with open(profile_path, "r", encoding="utf-8") as f:
            profile = json.load(f)

        _cache[name] = profile
        log_progress(f"[profile_loader] Loaded profile: {name}")

        return profile


def get_ingestion_config(profile_name: str | None = None) -> dict[str, Any]:
    """Get the ingestion configuration section from a profile."""
    return load_profile(profile_name).get("ingestion", {})


def get_chat_config(profile_name: str | None = None) -> dict[str, Any]:
    """Get the chat configuration section from a profile."""
    return load_profile(profile_name).get("chat", {})


def get_llm_config(profile_name: str | None = None) -> dict[str, Any] | None:
    """Get the LLM configuration from a profile."""
    profile = load_profile(profile_name)
    return profile.get("llm_config")