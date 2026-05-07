import re
from typing import Any

# NUL plus lone surrogates — both break Postgres JSONB / TEXT
_BAD = re.compile(r"[\x00]|[\ud800-\udfff]")


def sanitize_text(s: str) -> str:
    if not s:
        return s
    cleaned = _BAD.sub("", s)
    return cleaned.encode("utf-8", "replace").decode("utf-8", "replace")


def sanitize_json(obj: Any) -> Any:
    """Recursively strip invalid Unicode from strings nested in dicts/lists.
    Returns a new structure; does not mutate inputs."""
    if isinstance(obj, str):
        return sanitize_text(obj)
    if isinstance(obj, dict):
        return {k: sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_json(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(sanitize_json(v) for v in obj)
    return obj
