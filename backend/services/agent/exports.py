from __future__ import annotations

import csv
import html
import io
import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from postgres.models.agent import AgentArtifactRecord


AgentExportFormat = Literal["csv", "pdf", "docx", "html", "xlsx", "pptx", "svg", "png"]


@dataclass(frozen=True)
class AgentArtifactExport:
    content: bytes
    filename: str
    media_type: str


def render_artifact_export(
    artifact: AgentArtifactRecord,
    export_format: AgentExportFormat,
) -> AgentArtifactExport:
    kind, title, payload = artifact.type, artifact.title, dict(artifact.payload or {})
    from services.agent.source_presentation import present_sources
    run = getattr(artifact, 'run', None)
    sources = ((run.extra_metadata or {}).get('execution_checkpoint') or {}).get('result_store', {}) if run else {}
    payload = present_sources(payload, sources)
    payload.setdefault("document_metadata", (getattr(artifact, "extra_metadata", None) or {}).get("document_metadata", {}))
    formats = supported_export_formats(kind)
    if export_format not in formats:
        raise ValueError(f"{export_format} export is not supported for {kind}; available: {', '.join(formats)}")
    if export_format == "csv":
        return render_artifact_csv(artifact_type=kind,title=title,payload=payload)
    if export_format in ("svg", "png"):
        from services.agent.export_visuals import visual_svg,svg_png
        svg=visual_svg(kind,payload,title)
        return AgentArtifactExport(svg.encode() if export_format=="svg" else svg_png(svg),
            f"{_safe_filename(title)}.{export_format}","image/svg+xml" if export_format=="svg" else "image/png")
    if export_format in ("xlsx", "pptx"):
        from services.agent.export_office import workbook_bytes,presentation_bytes
        content=workbook_bytes(kind,title,payload) if export_format=="xlsx" else presentation_bytes(kind,title,payload)
        media="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if export_format=="xlsx" else "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        return AgentArtifactExport(content,f"{_safe_filename(title)}.{export_format}",media)
    if export_format=="html" and kind=="interactive":
        from services.agent.export_office import interactive_html
        return AgentArtifactExport(interactive_html(title,payload).encode("utf-8"),f"{_safe_filename(title)}.html","text/html; charset=utf-8")
    if export_format=="pdf" and kind=="presentation":
        from services.agent.export_office import presentation_bytes
        from services.agent.export_slides import presentation_pdf
        return AgentArtifactExport(presentation_pdf(presentation_bytes(kind,title,payload)),f"{_safe_filename(title)}.pdf","application/pdf")
    document=as_document(kind,title,payload)
    if export_format=="pdf":return render_report_pdf(title=title,payload=document)
    if export_format=="docx":return render_report_docx(title=title,payload=document)
    from services.agent.export_documents import document_html
    return AgentArtifactExport(document_html(title,document).encode("utf-8"),f"{_safe_filename(title)}.html","text/html; charset=utf-8")


def supported_export_formats(kind: str) -> list[str]:
    if kind=="report":return ["pdf","docx","html","pptx"]
    if kind=="presentation":return ["pptx","pdf","html","docx"]
    if kind=="workbook":return ["xlsx","pdf","html","docx"]
    if kind=="interactive":return ["html","pdf","docx","csv","xlsx"]
    if kind in ("graph","diagram","chart","map"):return ["svg","png","pdf","docx","html","csv","xlsx"]
    if kind in ("table","timeline","matrix"):return ["csv","xlsx","pdf","docx","html"]
    return []


def as_document(kind: str,title: str,payload: dict) -> dict:
    if kind=="report":return payload
    common={"title":title,"purpose":payload.get("purpose", ""),"document_metadata":payload.get("document_metadata",{}),"sources":payload.get("sources",[])}
    if kind=="presentation":
        return {**common,"sections":[{"heading":s.get("title") or f"Slide {i+1}","content":s.get("content") or "",
            "page_break_before":True,"embeds":s.get("embeds") or []} for i,s in enumerate(payload.get("slides") or [])]}
    notes = list(dict.fromkeys(str(payload[key]).strip() for key in ('description', 'notes', 'note') if payload.get(key)))
    return {**common,"sections":[{"heading":title,"content":"\n\n".join(notes), "embeds":[{"type":kind,"title":title,"data":payload,"available":True}]}]}


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
    if artifact_type in ("table", "timeline", "matrix", "interactive"):
        return _dict_rows(payload.get("rows"))
    if artifact_type == "chart":
        return _dict_rows(payload.get("rows"))
    if artifact_type == "map":
        return [{**row, 'name': row.get('name', row.get('label', '')),
                 'latitude': row.get('latitude', row.get('lat')),
                 'longitude': row.get('longitude', row.get('lng', row.get('lon')))}
                for row in _dict_rows(payload.get("locations") or payload.get('points') or payload.get('rows'))]
    if artifact_type in ("graph", "diagram"):
        return _graph_rows(payload)
    return _dict_rows(payload.get("rows") or payload.get("items") or payload.get("data"))


def _columns_for_artifact(
    artifact_type: str,
    payload: dict[str, Any],
    rows: list[dict[str, Any]],
) -> list[str]:
    if artifact_type in ("table", "timeline", "matrix", "interactive"):
        explicit = [
            str(column.get("key"))
            for column in _dict_rows(payload.get("columns"))
            if column.get("key") is not None
        ]
        return _dedupe([*explicit, *_flattened_keys(rows)])
    if artifact_type == "chart":
        explicit = [
            str(column.get("key"))
            for column in _dict_rows(payload.get("columns"))
            if column.get("key") is not None
        ]
        chart_keys = [
            str(payload.get("x_key") or ""),
            str(payload.get("category_key") or ""),
            str(payload.get("value_key") or ""),
            *[str(key) for key in payload.get("y_keys") or []],
        ]
        return _dedupe([*chart_keys, *explicit, *_flattened_keys(rows)])

    preferred: dict[str, list[str]] = {
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
            "properties.date",
            "properties.amount",
            "properties.currency",
            "properties.detail",
            "properties.source_files",
        ],
    }
    if artifact_type in ("graph", "diagram", "map"):
        actual=_flattened_keys(rows)
        return _dedupe([*[key for key in preferred["graph" if artifact_type=="diagram" else artifact_type] if key in actual], *actual])
    return _dedupe(_flattened_keys(rows))


def _graph_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for node in _dict_rows(payload.get("nodes")):
        rows.append({"row_type": "node", **node})
    for link in _dict_rows(payload.get("links") or payload.get("edges")):
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


def render_report_pdf(*, title: str, payload: dict[str, Any]) -> AgentArtifactExport:
    from services.agent.export_documents import document_pdf
    return AgentArtifactExport(document_pdf(title,payload),f"{_safe_filename(title)}-report.pdf","application/pdf")


def render_report_docx(*, title: str, payload: dict[str, Any]) -> AgentArtifactExport:
    from services.agent.export_documents import document_docx
    return AgentArtifactExport(document_docx(title,payload),f"{_safe_filename(title)}-report.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")


def _report_html(*, title: str, payload: dict[str, Any]) -> str:
    from services.agent.export_documents import document_html
    return document_html(title,payload)


def _markdownish_to_html(content: str) -> str:
    from services.agent.export_documents import markdown_html
    return markdown_html(content)


def _embed_html(embed: dict[str, Any]) -> str:
    from services.agent.export_documents import embed_html
    return embed_html(embed)
