"""Secrets a production server must set for itself.

``LOUPE_ENV=production`` turns this on. A server so marked refuses to start on a missing, shipped or placeholder
secret, naming which and never showing a value. Development and test (no ``LOUPE_ENV``) keep starting on the defaults
in ``config.py``. Pure standard library: ``config.py`` calls it, and it holds no secret of its own beyond the values
this repository already ships.
"""
from __future__ import annotations

from typing import Mapping

MINIMUM_LENGTH = 32
# The values this repository ships, in config.py, docker-compose.yml and .env.example.
SHIPPED = frozenset({
    "supersecretchange",
    "loupe-development-ai-credentials-change-me",
    "replace-with-a-long-random-service-secret",
    "replace-with-a-long-random-encryption-secret",
})
PLACEHOLDER_WORDS = ("replace-with", "change-me", "changeme")


def is_production(environment: Mapping[str, str | None]) -> bool:
    return (environment.get("LOUPE_ENV") or "").strip().lower() == "production"


def required_names(environment: Mapping[str, str | None]) -> tuple[str, ...]:
    names = ["AUTH_SECRET_KEY", "AI_CREDENTIAL_ENCRYPTION_KEY"]
    # Without the engine there is no service link to protect.
    if (environment.get("USE_EVIDENCE_ENGINE") or "true").strip().lower() == "true":
        names.append("EVIDENCE_ENGINE_API_KEY")
    return tuple(names)


def problems(environment: Mapping[str, str | None]) -> list[str]:
    """One plain line per unusable secret. The name and the reason, never the value."""
    found = []
    for name in required_names(environment):
        value = (environment.get(name) or "").strip()
        if not value:
            found.append(f"{name} is not set")
        elif value in SHIPPED or any(word in value.lower() for word in PLACEHOLDER_WORDS):
            found.append(f"{name} is still the value shipped with the code")
        elif len(value) < MINIMUM_LENGTH:
            found.append(f"{name} is shorter than {MINIMUM_LENGTH} characters")
    return found


def refuse_unsafe_start(environment: Mapping[str, str | None]) -> None:
    if not is_production(environment):
        return
    found = problems(environment)
    if found:
        raise SystemExit("Loupe will not start with LOUPE_ENV=production: " + "; ".join(found)
                         + ". Set a long random value for each in the server's .env.")
