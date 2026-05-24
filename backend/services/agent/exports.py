from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from postgres.models.agent import AgentArtifactRecord


AgentExportFormat = Literal["csv"]


@dataclass(frozen=True)
class AgentArtifactExport:
    content: bytes
    filename: str
    media_type: str


def render_artifact_export(
    artifact: AgentArtifactRecord,
    export_format: AgentExportFormat,
) -> AgentArtifactExport:
    if export_format != "csv":
        raise ValueError(f"Unsupported artifact export format: {export_format}")
    return render_artifact_csv(
        artifact_type=artifact.type,
        title=artifact.title,
        payload=artifact.payload or {},
    )


def render_artifact_csv(
    *,
    artifact_type: str,
    title: str,
    payload: dict[str, Any],
) -> AgentArtifactExport:
    rows = _rows_for_artifact(artifact_type, payload)
    columns = _columns_for_artifact(artifact_type, payload, rows)
    csv_text = _write_csv(columns, rows)
    filename = f"{_safe_filename(title or 'agent-artifact')}-{artifact_type}.csv"
    return AgentArtifactExport(
        content=csv_text.encode("utf-8-sig"),
        filename=filename,
        media_type="text/csv; charset=utf-8",
    )


def _rows_for_artifact(artifact_type: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    if artifact_type == "table":
        return _dict_rows(payload.get("rows"))
    if artifact_type == "timeline":
        return _dict_rows(payload.get("events"))
    if artifact_type == "financial":
        return _dict_rows(payload.get("transactions"))
    if artifact_type == "map":
        return _dict_rows(payload.get("locations"))
    if artifact_type == "graph":
        return _graph_rows(payload)
    return _dict_rows(payload.get("rows") or payload.get("items") or payload.get("data"))


def _columns_for_artifact(
    artifact_type: str,
    payload: dict[str, Any],
    rows: list[dict[str, Any]],
) -> list[str]:
    if artifact_type == "table":
        explicit = [
            str(column.get("key"))
            for column in _dict_rows(payload.get("columns"))
            if column.get("key") is not None
        ]
        return _dedupe([*explicit, *_flattened_keys(rows)])

    preferred: dict[str, list[str]] = {
        "timeline": [
            "date",
            "time",
            "name",
            "type",
            "summary",
            "notes",
            "key",
            "amount",
        ],
        "financial": [
            "date",
            "name",
            "amount",
            "currency",
            "category",
            "from_entity.name",
            "from_entity.key",
            "to_entity.name",
            "to_entity.key",
            "purpose",
            "counterparty_details",
            "summary",
            "source",
            "key",
        ],
        "map": [
            "name",
            "key",
            "type",
            "latitude",
            "longitude",
            "address",
            "summary",
        ],
        "graph": [
            "row_type",
            "key",
            "name",
            "type",
            "source",
            "target",
            "summary",
            "date",
            "amount",
        ],
    }
    return _dedupe([*preferred.get(artifact_type, []), *_flattened_keys(rows)])


def _graph_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for node in _dict_rows(payload.get("nodes")):
        rows.append({"row_type": "node", **node})
    for link in _dict_rows(payload.get("links")):
        rows.append({"row_type": "relationship", **link})
    return rows


def _write_csv(columns: list[str], rows: list[dict[str, Any]]) -> str:
    if not columns:
        columns = ["value"]

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        flattened = _flatten_dict(row)
        writer.writerow({column: _cell_value(flattened.get(column)) for column in columns})
    return buffer.getvalue()


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
    return (normalized or "agent-artifact")[:80]
