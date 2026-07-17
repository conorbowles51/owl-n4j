from __future__ import annotations

import csv
import html
import io
import json
import re
from dataclasses import dataclass
from typing import Any, Literal


AgentExportFormat = Literal["csv", "pdf", "docx"]


@dataclass(frozen=True)
class AgentArtifactExport:
    content: bytes
    filename: str
    media_type: str


def render_artifact_export(
    artifact: Any | None = None,
    export_format: AgentExportFormat = "csv",
    *,
    artifact_type: str | None = None,
    title: str | None = None,
    payload: dict[str, Any] | None = None,
) -> AgentArtifactExport:
    if artifact is not None:
        artifact_type = artifact_type or str(getattr(artifact, "type", ""))
        title = title or str(getattr(artifact, "title", ""))
        payload = payload if payload is not None else (getattr(artifact, "payload", None) or {})
    if not artifact_type:
        raise ValueError("Artifact type is required for export")
    title = title or "Agent artifact"
    payload = payload or {}

    if export_format == "pdf":
        if artifact_type != "report":
            raise ValueError("PDF export is only supported for report artifacts")
        return render_report_pdf(title=title, payload=payload)
    if export_format == "docx":
        if artifact_type != "report":
            raise ValueError("Word export is only supported for report artifacts")
        return render_report_docx(title=title, payload=payload)
    if export_format != "csv":
        raise ValueError(f"Unsupported artifact export format: {export_format}")
    return render_artifact_csv(
        artifact_type=artifact_type,
        title=title,
        payload=payload,
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
    if artifact_type == "chart":
        return _dict_rows(payload.get("rows"))
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
    if artifact_type in preferred:
        return _dedupe([*preferred[artifact_type], *[key for key in _flattened_keys(rows) if key in preferred[artifact_type]]])
    return _dedupe(_flattened_keys(rows))


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


def render_report_pdf(*, title: str, payload: dict[str, Any]) -> AgentArtifactExport:
    try:
        from weasyprint import HTML
    except Exception as exc:
        raise ValueError(f"PDF export is unavailable: {exc}") from exc

    html_text = _report_html(title=title, payload=payload)
    return AgentArtifactExport(
        content=HTML(string=html_text).write_pdf(),
        filename=f"{_safe_filename(title or 'agent-report')}-report.pdf",
        media_type="application/pdf",
    )


def render_report_docx(*, title: str, payload: dict[str, Any]) -> AgentArtifactExport:
    try:
        from docx import Document
    except Exception as exc:
        raise ValueError(f"Word export is unavailable: {exc}") from exc

    document = Document()
    document.add_heading(str(payload.get("title") or title or "Agent report"), level=0)
    purpose = str(payload.get("purpose") or "").strip()
    if purpose:
        document.add_paragraph(purpose)
    scope = str(payload.get("scope") or "").strip()
    if scope:
        document.add_heading("Scope", level=1)
        document.add_paragraph(scope)
    included = [str(item) for item in payload.get("included_items") or [] if str(item).strip()]
    if included:
        document.add_heading("Included", level=1)
        for item in included:
            document.add_paragraph(item, style="List Bullet")

    for section in _dict_rows(payload.get("sections")):
        heading = str(section.get("heading") or "Section")
        level = max(1, min(int(section.get("level") or 2), 3))
        document.add_heading(heading, level=level)
        _add_markdownish_docx(document, str(section.get("content") or ""))
        for embed in _dict_rows(section.get("embeds")):
            _add_embed_docx(document, embed)

    open_questions = [str(item) for item in payload.get("open_questions") or [] if str(item).strip()]
    if open_questions:
        document.add_heading("Open Questions", level=1)
        for item in open_questions:
            document.add_paragraph(item, style="List Bullet")

    buffer = io.BytesIO()
    document.save(buffer)
    return AgentArtifactExport(
        content=buffer.getvalue(),
        filename=f"{_safe_filename(title or 'agent-report')}-report.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def _report_html(*, title: str, payload: dict[str, Any]) -> str:
    report_title = str(payload.get("title") or title or "Agent report")
    sections = _dict_rows(payload.get("sections"))
    included = [str(item) for item in payload.get("included_items") or [] if str(item).strip()]
    open_questions = [str(item) for item in payload.get("open_questions") or [] if str(item).strip()]
    purpose = str(payload.get("purpose") or "").strip()
    scope = str(payload.get("scope") or "").strip()
    audience = str(payload.get("audience") or "").strip()

    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        "<style>",
        "body{font-family:Arial,sans-serif;color:#111827;margin:36px;line-height:1.45}",
        "h1{font-size:28px;margin:0 0 8px}h2{font-size:18px;margin:24px 0 8px}h3{font-size:15px;margin:18px 0 6px}",
        ".meta{color:#4b5563;font-size:12px;margin-bottom:18px}.scope{border-left:3px solid #d97706;padding-left:12px;color:#374151}",
        "ul{margin-top:6px}.section{break-inside:avoid}.embed{border:1px solid #d1d5db;border-radius:6px;padding:10px;margin:10px 0 14px}",
        ".embed-title{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:#6b7280;margin-bottom:6px}",
        "table{border-collapse:collapse;width:100%;font-size:11px;margin-top:6px}th,td{border:1px solid #d1d5db;padding:5px;text-align:left;vertical-align:top}th{background:#f3f4f6}",
        ".graph-list{font-size:12px;color:#374151}.muted{color:#6b7280}",
        "</style></head><body>",
        f"<h1>{html.escape(report_title)}</h1>",
    ]
    if audience:
        parts.append(f"<div class='meta'>Audience: {html.escape(audience)}</div>")
    if purpose:
        parts.append(f"<p>{html.escape(purpose)}</p>")
    if scope:
        parts.append(f"<h2>Scope</h2><p class='scope'>{html.escape(scope)}</p>")
    if included:
        parts.append("<h2>Included</h2><ul>")
        parts.extend(f"<li>{html.escape(item)}</li>" for item in included)
        parts.append("</ul>")

    for section in sections:
        level = max(2, min(int(section.get("level") or 2), 3))
        heading_tag = f"h{level}"
        parts.append("<div class='section'>")
        parts.append(f"<{heading_tag}>{html.escape(str(section.get('heading') or 'Section'))}</{heading_tag}>")
        parts.append(_markdownish_to_html(str(section.get("content") or "")))
        for embed in _dict_rows(section.get("embeds")):
            parts.append(_embed_html(embed))
        parts.append("</div>")

    if open_questions:
        parts.append("<h2>Open Questions</h2><ul>")
        parts.extend(f"<li>{html.escape(item)}</li>" for item in open_questions)
        parts.append("</ul>")

    parts.append("</body></html>")
    return "".join(parts)


def _markdownish_to_html(content: str) -> str:
    lines = [line.rstrip() for line in content.splitlines()]
    parts: list[str] = []
    list_open = False
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            parts.append(f"<p>{html.escape(' '.join(paragraph))}</p>")
            paragraph = []

    def close_list() -> None:
        nonlocal list_open
        if list_open:
            parts.append("</ul>")
            list_open = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            close_list()
            continue
        if stripped.startswith(("- ", "* ")):
            flush_paragraph()
            if not list_open:
                parts.append("<ul>")
                list_open = True
            parts.append(f"<li>{html.escape(stripped[2:].strip())}</li>")
            continue
        close_list()
        paragraph.append(stripped)

    flush_paragraph()
    close_list()
    return "".join(parts)


def _embed_html(embed: dict[str, Any]) -> str:
    title = html.escape(str(embed.get("title") or "Embedded artifact"))
    caption = html.escape(str(embed.get("caption") or ""))
    artifact_type = str(embed.get("type") or "unknown")
    data = embed.get("data") if isinstance(embed.get("data"), dict) else {}
    if not embed.get("available", True):
        return f"<div class='embed'><div class='embed-title'>{title}</div><p class='muted'>Referenced artifact is not available in this report export.</p></div>"
    if artifact_type == "table":
        rows = _dict_rows(data.get("rows"))[:20]
        columns = _columns_for_artifact("table", data, rows)[:8]
        return (
            f"<div class='embed'><div class='embed-title'>Table: {title}</div>"
            + (f"<p class='muted'>{caption}</p>" if caption else "")
            + _html_table(columns, rows)
            + "</div>"
        )
    if artifact_type == "graph":
        nodes = _dict_rows(data.get("nodes"))[:20]
        links = _dict_rows(data.get("links"))[:20]
        node_names = ", ".join(str(node.get("name") or node.get("key") or "") for node in nodes[:10])
        return (
            f"<div class='embed'><div class='embed-title'>Graph: {title}</div>"
            + (f"<p class='muted'>{caption}</p>" if caption else "")
            + f"<p class='graph-list'>{len(nodes)} shown node(s), {len(links)} shown relationship(s).</p>"
            + (f"<p class='graph-list'>Key nodes: {html.escape(node_names)}</p>" if node_names else "")
            + "</div>"
        )
    if artifact_type == "chart":
        rows = _dict_rows(data.get("rows"))[:20]
        columns = _columns_for_artifact("chart", data, rows)[:8]
        chart_type = html.escape(str(data.get("chart_type") or "chart").replace("_", " "))
        series = ", ".join(str(item.get("label") or item.get("key") or "") for item in _dict_rows(data.get("series"))[:6])
        return (
            f"<div class='embed'><div class='embed-title'>Chart: {title}</div>"
            + (f"<p class='muted'>{caption}</p>" if caption else "")
            + f"<p class='graph-list'>Type: {chart_type}. Rows: {len(rows)}."
            + (f" Series: {html.escape(series)}." if series else "")
            + "</p>"
            + _html_table(columns, rows)
            + "</div>"
        )
    return f"<div class='embed'><div class='embed-title'>{title}</div><p class='muted'>Unsupported embedded artifact type: {html.escape(artifact_type)}</p></div>"


def _html_table(columns: list[str], rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "<p class='muted'>No rows.</p>"
    header = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
    body = []
    for row in rows:
        flattened = _flatten_dict(row)
        body.append("<tr>" + "".join(f"<td>{html.escape(_cell_value(flattened.get(column)))}</td>" for column in columns) + "</tr>")
    return f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _add_markdownish_docx(document: Any, content: str) -> None:
    for block in re.split(r"\n\s*\n", content.strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if all(line.startswith(("- ", "* ")) for line in lines):
            for line in lines:
                document.add_paragraph(line[2:].strip(), style="List Bullet")
        else:
            document.add_paragraph(" ".join(lines))


def _add_embed_docx(document: Any, embed: dict[str, Any]) -> None:
    title = str(embed.get("title") or "Embedded artifact")
    artifact_type = str(embed.get("type") or "unknown")
    document.add_paragraph(f"Embedded {artifact_type}: {title}")
    caption = str(embed.get("caption") or "").strip()
    if caption:
        document.add_paragraph(caption)
    data = embed.get("data") if isinstance(embed.get("data"), dict) else {}
    if artifact_type == "table":
        rows = _dict_rows(data.get("rows"))[:20]
        columns = _columns_for_artifact("table", data, rows)[:8]
        if rows and columns:
            table = document.add_table(rows=1, cols=len(columns))
            header_cells = table.rows[0].cells
            for index, column in enumerate(columns):
                header_cells[index].text = column
            for row in rows:
                cells = table.add_row().cells
                flattened = _flatten_dict(row)
                for index, column in enumerate(columns):
                    cells[index].text = _cell_value(flattened.get(column))
    elif artifact_type == "graph":
        nodes = _dict_rows(data.get("nodes"))
        links = _dict_rows(data.get("links"))
        document.add_paragraph(f"{len(nodes)} node(s), {len(links)} relationship(s)")
    elif artifact_type == "chart":
        chart_type = str(data.get("chart_type") or "chart").replace("_", " ")
        rows = _dict_rows(data.get("rows"))[:20]
        columns = _columns_for_artifact("chart", data, rows)[:8]
        document.add_paragraph(f"Chart type: {chart_type}; {len(rows)} source row(s)")
        if rows and columns:
            table = document.add_table(rows=1, cols=len(columns))
            header_cells = table.rows[0].cells
            for index, column in enumerate(columns):
                header_cells[index].text = column
            for row in rows:
                cells = table.add_row().cells
                flattened = _flatten_dict(row)
                for index, column in enumerate(columns):
                    cells[index].text = _cell_value(flattened.get(column))
