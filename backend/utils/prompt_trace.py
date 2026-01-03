"""Prompt tracing utility.

When enabled, writes prompt-building steps and final LLM payloads to a log file.

Enable with environment variable:
    PROMPT_TRACE_ENABLED=true

Optional:
    PROMPT_TRACE_FILE=<path to log file>
    PROMPT_TRACE_WRAP_WIDTH=160            # soft-wrap long lines for readability
    PROMPT_TRACE_STRING_THRESHOLD=1000     # extract large strings from JSON into RAW blocks

This is intended for local debugging. It may log sensitive data.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4


_TRACE_ID: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("prompt_trace_id", default=None)
_ENABLED: contextvars.ContextVar[bool] = contextvars.ContextVar("prompt_trace_enabled", default=False)
_LOG_PATH: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("prompt_trace_path", default=None)

_LOCK = threading.Lock()


def _project_root() -> Path:
    # backend/utils/prompt_trace.py -> backend/utils -> backend -> <root>
    return Path(__file__).resolve().parents[2]


def _default_log_path() -> Path:
    root = _project_root()
    log_dir = root / "backend" / "logs" / "prompt_traces"
    log_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    return log_dir / f"prompt_trace_{date_str}.log"


def _env_enabled() -> bool:
    return os.getenv("PROMPT_TRACE_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _wrap_width() -> int:
    raw = os.getenv("PROMPT_TRACE_WRAP_WIDTH", "160").strip()
    try:
        width = int(raw)
    except ValueError:
        return 160
    return max(40, min(width, 400))


def _string_threshold() -> int:
    raw = os.getenv("PROMPT_TRACE_STRING_THRESHOLD", "1000").strip()
    try:
        threshold = int(raw)
    except ValueError:
        return 1000
    return max(200, min(threshold, 20000))


def is_enabled() -> bool:
    return _ENABLED.get() and _env_enabled()


def get_trace_id() -> Optional[str]:
    return _TRACE_ID.get()


def _resolve_log_path() -> Path:
    explicit = os.getenv("PROMPT_TRACE_FILE", "").strip()
    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = _project_root() / p
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    ctx = _LOG_PATH.get()
    if ctx:
        return Path(ctx)

    return _default_log_path()


def _rel_path(path_str: str) -> str:
    try:
        p = Path(path_str).resolve()
        root = _project_root()
        return p.relative_to(root).as_posix()
    except Exception:
        return str(path_str)


def _write_block(text: str) -> None:
    if not is_enabled():
        return

    log_path = _resolve_log_path()
    wrapped = _wrap_text(text, width=_wrap_width())
    with _LOCK:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(wrapped)
            if not wrapped.endswith("\n"):
                f.write("\n")


def _wrap_text(text: str, *, width: int) -> str:
    """Soft-wrap long lines while preserving existing newlines."""
    if width <= 0:
        return text

    out: list[str] = []
    # keepends=True so we preserve original line breaks
    for line in text.splitlines(keepends=True):
        newline = ""
        if line.endswith("\r\n"):
            newline = "\r\n"
            core = line[:-2]
        elif line.endswith("\n"):
            newline = "\n"
            core = line[:-1]
        else:
            core = line

        if len(core) <= width:
            out.append(core + newline)
            continue

        # break long line into chunks; keep the same newline at the end
        i = 0
        while i < len(core):
            out.append(core[i : i + width] + (newline if i + width >= len(core) else "\n"))
            i += width

    return "".join(out)


def _extract_large_strings(obj: Any, *, threshold: int, path: str = "", max_depth: int = 8):
    """Return (sanitized_obj, extracted) where extracted is a list of (path, raw_string).

    Extracts strings that are multiline or longer than threshold.
    """
    extracted: list[tuple[str, str]] = []

    def _walk(value: Any, p: str, depth: int):
        if depth > max_depth:
            return value

        if isinstance(value, str):
            if "\n" in value or len(value) >= threshold:
                extracted.append((p or "<root>", value))
                preview = value[:200].replace("\n", "\\n")
                return f"<<RAW:{p or '<root>'} len={len(value)} preview={preview!r}>>"
            return value

        if isinstance(value, dict):
            return {k: _walk(v, f"{p}.{k}" if p else str(k), depth + 1) for k, v in value.items()}

        if isinstance(value, list):
            return [_walk(v, f"{p}[{i}]" if p else f"[{i}]", depth + 1) for i, v in enumerate(value)]

        if isinstance(value, tuple):
            return tuple(_walk(v, f"{p}[{i}]" if p else f"[{i}]", depth + 1) for i, v in enumerate(value))

        return value

    sanitized = _walk(obj, path, 0)
    return sanitized, extracted


@contextlib.contextmanager
def start_trace(meta: Optional[Dict[str, Any]] = None, trace_id: Optional[str] = None):
    """Start a prompt trace for the current request context."""

    if not _env_enabled():
        yield None
        return

    tid = trace_id or str(uuid4())

    token_enabled = _ENABLED.set(True)
    token_id = _TRACE_ID.set(tid)

    header = {
        "timestamp": datetime.now().isoformat(),
        "trace_id": tid,
        "meta": meta or {},
    }
    _write_block("\n" + "=" * 80)
    _write_block("PROMPT TRACE START")
    _write_block(json.dumps(header, ensure_ascii=False, indent=2))
    _write_block("=" * 80)

    try:
        yield tid
    finally:
        footer = {
            "timestamp": datetime.now().isoformat(),
            "trace_id": tid,
        }
        _write_block("PROMPT TRACE END")
        _write_block(json.dumps(footer, ensure_ascii=False, indent=2))
        _write_block("=" * 80 + "\n")

        _TRACE_ID.reset(token_id)
        _ENABLED.reset(token_enabled)


def log_section(
    *,
    source_file: str,
    source_func: str,
    title: str,
    content: Any,
    as_json: bool = False,
) -> None:
    """Write a labeled section into the trace log."""

    if not is_enabled():
        return

    tid = get_trace_id() or "(no-trace-id)"
    ts = datetime.now().isoformat()
    source = f"{_rel_path(source_file)}::{source_func}"

    if as_json:
        threshold = _string_threshold()
        sanitized, extracted = _extract_large_strings(content, threshold=threshold)
        body = json.dumps(sanitized, ensure_ascii=False, indent=2, default=str)
    else:
        extracted = []
        body = "" if content is None else str(content)

    block = (
        f"--- {source} | {title} | {ts} | trace_id={tid} ---\n"
        f"{body}\n"
        f"--- END {source} | {title} ---\n"
    )
    _write_block(block)

    # If we extracted large strings, write them as raw multiline blocks for readability.
    for raw_path, raw_value in extracted:
        raw_header = f"+++ RAW {source} | {title} | {raw_path} | len={len(raw_value)} +++\n"
        raw_footer = f"+++ END RAW {source} | {title} | {raw_path} +++\n"
        _write_block(raw_header)
        _write_block(raw_value)
        _write_block("\n" + raw_footer)
