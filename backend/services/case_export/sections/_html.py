"""HTML helpers for case export sections."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from html import escape
from typing import Any


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def html_text(value: Any) -> str:
    return escape(clean_text(value))


def format_datetime(value: datetime | str | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def empty_state(message: str) -> str:
    return f'<p class="empty-state">{escape(message)}</p>'


def badge(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    return f'<span class="badge">{escape(text)}</span>'


def badge_list(values: list[Any]) -> str:
    badges = "".join(badge(value) for value in values if clean_text(value))
    return f'<div class="badge-list">{badges}</div>' if badges else ""


def preformatted(value: Any) -> str:
    return f'<div class="preformatted">{html_text(value)}</div>'


def details_json(value: Any) -> str:
    try:
        return json.dumps(value or {}, sort_keys=True, default=str, indent=2)
    except TypeError:
        return str(value or {})
