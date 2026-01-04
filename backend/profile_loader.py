"""
Profile configuration loader.

Loads domain-specific prompts and settings from JSON profiles.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any

# Get profile from environment variable, default to 'generic'
PROFILE_NAME = os.getenv("PROFILE", "generic")
PROFILES_DIR = Path(__file__).parent.parent / "profiles"


def load_profile(profile_name: str | None = None) -> dict[str, Any]:
    """
    Load a profile configuration by name.
    
    Args:
        profile_name: Profile name (without .json). Defaults to 'generic'.
    
    Returns:
        Profile configuration dictionary.
    """
    name = profile_name or "generic"
    
    
    profile_path = PROFILES_DIR / f"{name}.json"
    
    if not profile_path.exists():
        profile_path = PROFILES_DIR / "generic.json"
        name = "generic"
    
    with open(profile_path, "r", encoding="utf-8") as f:
        profile = json.load(f)
    
    return profile


def get_ingestion_config(profile_name: str | None = None) -> dict[str, Any]:
    """Get the ingestion configuration section from a profile."""
    return load_profile(profile_name).get("ingestion", {})


def get_chat_config(profile_name: str | None = None) -> dict[str, Any]:
    """Get the chat configuration section from a profile."""
    return load_profile(profile_name).get("chat", {})