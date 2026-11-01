"""Path handling for phone requests (01 section 4.3, rules PA-1 to PA-6).

Every path in a request is relative to ``<data root>/<case_id>``. Files and folders follow the same rules.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath

from fastapi import HTTPException

from app.config import settings

OUTSIDE = "Path outside case directory"


def data_root() -> Path:
    configured = Path(settings.cellebrite_data_root)
    if configured.is_absolute():
        return configured
    return Path(__file__).resolve().parents[3] / configured


def clean(raw: str | None) -> str:
    """PA-1: backslashes become forward slashes and leading slashes go. PA-2: '' and '.' mean the case root."""
    cleaned = (raw or "").replace("\\", "/").lstrip("/")
    return "" if cleaned in ("", ".") else cleaned


def resolve(case_id: str, raw: str | None, *, expect: str | None = None, root: Path | None = None):
    """``(relative, full)``. PA-3 and PA-4 give 403 with nothing read; PA-5 and PA-6 give 404.

    ``expect`` is ``"file"``, ``"dir"`` or None (either)."""
    base = ((root or data_root()) / str(case_id)).resolve()
    rel = clean(raw)
    if rel:
        parts = PurePosixPath(rel).parts
        if any(p in ("", ".", "..") for p in rel.split("/")) or not parts:
            raise HTTPException(403, OUTSIDE)
        full = (base / rel).resolve()
        try:
            full.relative_to(base)
        except ValueError:
            raise HTTPException(403, OUTSIDE)
    else:
        full = base
    if not full.exists():
        raise HTTPException(404, "Not found: %s" % (rel or "."))
    if expect == "file" and not full.is_file():
        raise HTTPException(404, "Not found as a file: %s" % (rel or "."))
    if expect == "dir" and not full.is_dir():
        raise HTTPException(404, "Not found as a folder: %s" % (rel or "."))
    return rel, full
