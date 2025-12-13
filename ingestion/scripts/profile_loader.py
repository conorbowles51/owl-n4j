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
PROFILES_DIR = Path(__file__).parent.parent.parent / "profiles"


def load_profile(profile_name: str = None) -> Dict[str, Any]:
    """
    Load a profile configuration by name.
    
    Args:
        profile_name: Name of the profile (without .json extension).
                      If None, uses PROFILE environment variable.
    
    Returns:
        Profile configuration dictionary
    """
    name = profile_name or PROFILE_NAME
    profile_path = PROFILES_DIR / f"{name}.json"
    
    if not profile_path.exists():
        print(f"Warning: Profile '{name}' not found, falling back to 'generic'")
        profile_path = PROFILES_DIR / "generic.json"
    
    with open(profile_path, 'r', encoding='utf-8') as f:
        return json.load(f)


# Load profile once at import time
_profile = load_profile()


def get_profile() -> Dict[str, Any]:
    """Get the current loaded profile."""
    return _profile


def get_ingestion_config() -> Dict[str, Any]:
    """Get ingestion-specific configuration."""
    return _profile.get("ingestion", {})


def get_chat_config() -> Dict[str, Any]:
    """Get chat-specific configuration."""
    return _profile.get("chat", {})