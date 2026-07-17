from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SnapshotExport:
    content: bytes
    filename: str
    media_type: str


def render_snapshot_pdf(snapshot: dict[str, Any]) -> SnapshotExport:
    try:
        from weasyprint import HTML
    except Exception as exc:
        raise ValueError(f"PDF export is unavailable: {exc}") from exc

    scope = _snapshot_export_scope(snapshot)
    content_hash = _content_hash(scope)
    html_text = _snapshot_html(snapshot=snapshot, scope=scope, content_hash=content_hash)
    filename = f"{_safe_filename(str(snapshot.get('name') or 'snapshot'))}-{content_hash}.pdf"
    return SnapshotExport(
        content=HTML(string=html_text).write_pdf(),
        filename=filename,
        media_type="application/pdf",
    )


def _snapshot_export_scope(snapshot: dict[str, Any]) -> dict[str, Any]:
    subgraph = snapshot.get("subgraph") if isinstance(snapshot.get("subgraph"), dict) else {}
    return {
        "name": snapshot.get("name"),
        "case_name": snapshot.get("case_name"),
        "case_version": snapshot.get("case_version"),
        "subgraph": {
            "nodes": _dict_rows(subgraph.get("nodes")),
            "links": _dict_rows(subgraph.get("links")),
        },
        "timeline": _dict_rows(snapshot.get("timeline")),
        "notes": snapshot.get("notes") or "",
    }


def _content_hash(scope: dict[str, Any]) -> str:
    encoded = json.dumps(scope, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:12]


def _snapshot_html(
    *,
    snapshot: dict[str, Any],
    scope: dict[str, Any],
    content_hash: str,
) -> str:
    subgraph = scope["subgraph"]
    nodes = _dict_rows(subgraph.get("nodes"))
    links = _dict_rows(subgraph.get("links"))
    events = _dict_rows(scope.get("timeline"))
    title = str(scope.get("name") or "Snapshot")
    case_name = str(scope.get("case_name") or "Unknown case")
    captured_at = str(snapshot.get("timestamp") or snapshot.get("created_at") or "Unknown")
    version = scope.get("case_version")
    version_text = str(version) if version is not None else "unknown"

    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        "<style>",
        "body{font-family:Arial,sans-serif;color:#111827;margin:36px;line-height:1.45}",
        "h1{font-size:28px;margin:0 0 8px}h2{font-size:18px;margin:24px 0 8px}",
        ".meta{color:#4b5563;font-size:12px;margin-bottom:18px}.summary{display:flex;gap:12px;margin:16px 0 20px}",
        ".pill{border:1px solid #d1d5db;border-radius:4px;padding:6px 8px;font-size:12px;background:#f9fafb}",
        "table{border-collapse:collapse;width:100%;font-size:11px;margin-top:6px;break-inside:auto}",
        "th,td{border:1px solid #d1d5db;padding:5px;text-align:left;vertical-align:top}th{background:#f3f4f6}",
        ".notes p{margin:0 0 8px}.muted{color:#6b7280}.section{break-inside:avoid}",
        "</style></head><body>",
        f"<h1>{html.escape(title)}</h1>",
        (
            f"<div class='meta'>Case: {html.escape(case_name)}<br>"
            f"Captured: {html.escape(captured_at)}<br>"
            f"Version {html.escape(version_text)} - Hash {html.escape(content_hash)}</div>"
        ),
        "<div class='summary'>",
        f"<div class='pill'>{len(nodes)} entities</div>",
        f"<div class='pill'>{len(links)} relationships</div>",
        f"<div class='pill'>{len(events)} events</div>",
        "</div>",
        "<div class='section'><h2>Entities</h2>",
        _html_table(_entity_columns(nodes), nodes),
        "</div>",
        "<div class='section'><h2>Relationships</h2>",
        _html_table(_relationship_columns(links), links),
        "</div>",
        "<div class='section'><h2>Events</h2>",
        _html_table(_timeline_columns(events), events),
        "</div>",
        "<div class='section'><h2>Notes</h2>",
        _notes_html(str(scope.get("notes") or "")),
        "</div>",
        "</body></html>",
    ]
    return "".join(parts)


def _entity_columns(nodes: list[dict[str, Any]]) -> list[str]:
    preferred = ["key", "id", "name", "label", "type", "summary", "description"]
    return _dedupe([*preferred, *_flattened_keys(nodes)])[:10]


def _relationship_columns(links: list[dict[str, Any]]) -> list[str]:
    preferred = [
        "source",
        "target",
        "from",
        "to",
        "type",
        "relationship",
        "summary",
        "description",
        "date",
    ]
    return _dedupe([*preferred, *_flattened_keys(links)])[:10]


def _timeline_columns(events: list[dict[str, Any]]) -> list[str]:
    preferred = [
        "date",
        "time",
        "title",
        "description",
        "summary",
        "name",
        "type",
        "notes",
    ]
    flattened = _flattened_keys(events)
    return _dedupe([*preferred, *flattened])[:10]


def _html_table(columns: list[str], rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<p class='muted'>No rows.</p>"
    if not columns:
        columns = _flattened_keys(rows)[:10] or ["value"]
    header = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
    body = []
    for row in rows:
        flattened = _flatten_dict(row)
        body.append(
            "<tr>"
            + "".join(
                f"<td>{html.escape(_cell_value(flattened.get(column)))}</td>"
                for column in columns
            )
            + "</tr>"
        )
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _notes_html(notes: str) -> str:
    paragraphs = [line.strip() for line in notes.splitlines() if line.strip()]
    if not paragraphs:
        return "<p class='muted'>No notes.</p>"
    rendered = "".join(f"<p>{html.escape(item)}</p>" for item in paragraphs)
    return f"<div class='notes'>{rendered}</div>"


def _flattened_keys(rows: list[dict[str, Any]]) -> list[str]:
    keys: list[str] = []
    for row in rows:
        for key in _flatten_dict(row):
            if key not in keys:
                keys.append(key)
    return keys


def _flatten_dict(value: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, item in value.items():
        next_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(item, dict):
            flattened.update(_flatten_dict(item, next_key))
        else:
            flattened[next_key] = item
    return flattened


def _cell_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _safe_filename(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower())
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-._")
    return (normalized or "snapshot")[:80]
