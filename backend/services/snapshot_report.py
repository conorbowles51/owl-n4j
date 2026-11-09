"""Snapshot report: the snapshot's own graph, its own events and their sources, with a chosen privilege marking.

A snapshot freezes what an investigator had on the graph: the entities and links, where each sat, and the
timeline events among those entities as they read when the snapshot was saved. The report prints only that: the
graph is drawn as vector graphics from the saved positions (sharp at any print resolution, no screen capture),
the chronology lists the snapshot's own events (never the whole case's), and every event cites its source
documents in a numbered appendix. The privilege marking is the same three values as the ledger export, chosen by
the person exporting; it is printed on the cover and in every page footer and is not a legal determination.
"""
from __future__ import annotations

import html
import math
from datetime import datetime
from typing import Any, Iterable

PRIVILEGE_LABELS = {
    "unmarked": "No privilege marking selected",
    "confidential": "Confidential",
    "privileged_confidential": "Privileged and confidential",
}
PRIVILEGE_BASIS = "Selected by the exporting user; not a legal privilege determination."
MAX_REPORT_NODES = 2000
GRAPH_WIDTH = 1000.0
GRAPH_HEIGHT = 640.0
_PAD = 40.0
_LABEL_ROOM = 170.0  # labels run to the right of each dot; keep the rightmost inside the drawing
_DEFAULT_NODE_COLOUR = "#64748b"


class SnapshotReportError(ValueError):
    """The report cannot be produced as asked; the message says why. No partial report is produced."""


def privilege_label(marking: str | None) -> str:
    label = PRIVILEGE_LABELS.get(marking or "unmarked")
    if label is None:
        raise SnapshotReportError("Unrecognized privilege marking; choose unmarked, confidential or privileged_confidential.")
    return label


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _node_key(node: dict[str, Any]) -> str:
    return str(node.get("key") or node.get("id") or "")


def _link_end(value: Any) -> str:
    if isinstance(value, dict):
        return _node_key(value)
    return str(value or "")


def snapshot_links(subgraph: dict[str, Any]) -> list[dict[str, Any]]:
    return list(subgraph.get("links") or subgraph.get("edges") or [])


def layout_positions(nodes: list[dict[str, Any]]) -> tuple[dict[str, tuple[float, float]], bool]:
    """Saved positions scaled into the drawing; nodes without one go on a circle. Returns (positions, all_saved)."""
    keys = [_node_key(n) for n in nodes]
    saved = {k: (_num(n.get("x")), _num(n.get("y"))) for k, n in zip(keys, nodes)}
    placed = {k: xy for k, xy in saved.items() if xy[0] is not None and xy[1] is not None}
    all_saved = len(placed) == len(keys)
    missing = [k for k in keys if k not in placed]
    if missing:
        radius = 400.0
        for i, key in enumerate(missing):
            angle = 2 * math.pi * i / max(1, len(missing))
            placed[key] = (radius * math.cos(angle), radius * math.sin(angle))
    if not placed:
        return {}, all_saved
    xs = [xy[0] for xy in placed.values()]
    ys = [xy[1] for xy in placed.values()]
    span_x = max(xs) - min(xs) or 1.0
    span_y = max(ys) - min(ys) or 1.0
    scale = min((GRAPH_WIDTH - 2 * _PAD - _LABEL_ROOM) / span_x, (GRAPH_HEIGHT - 2 * _PAD) / span_y)
    off_x = (GRAPH_WIDTH - _LABEL_ROOM - span_x * scale) / 2
    off_y = (GRAPH_HEIGHT - span_y * scale) / 2
    return {
        k: (off_x + (x - min(xs)) * scale, off_y + (y - min(ys)) * scale) for k, (x, y) in placed.items()
    }, all_saved


def graph_svg(subgraph: dict[str, Any]) -> str:
    """The snapshot graph as an SVG document (vector: no fixed DPI, sharp at any print size)."""
    nodes = [n for n in (subgraph.get("nodes") or []) if _node_key(n)]
    positions, _ = layout_positions(nodes)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {GRAPH_WIDTH:.0f} {GRAPH_HEIGHT:.0f}" '
        f'width="{GRAPH_WIDTH:.0f}" height="{GRAPH_HEIGHT:.0f}" font-family="sans-serif">',
        f'<rect width="{GRAPH_WIDTH:.0f}" height="{GRAPH_HEIGHT:.0f}" fill="#ffffff"/>',
    ]
    for link in snapshot_links(subgraph):
        a = positions.get(_link_end(link.get("source")))
        b = positions.get(_link_end(link.get("target")))
        if a and b:
            parts.append(
                f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" stroke="#94a3b8" stroke-width="1"/>'
            )
    show_labels = len(nodes) <= 150
    for node in nodes:
        x, y = positions[_node_key(node)]
        colour = str(node.get("color") or _DEFAULT_NODE_COLOUR)
        if not colour.startswith("#") or len(colour) not in (4, 7):
            colour = _DEFAULT_NODE_COLOUR
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{html.escape(colour)}" stroke="#1e293b" stroke-width="0.6"/>')
        if show_labels:
            label = html.escape(str(node.get("label") or node.get("name") or _node_key(node))[:40])
            parts.append(f'<text x="{x + 8:.1f}" y="{y + 3:.1f}" font-size="11" fill="#0f172a">{label}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _node_sources(node: dict[str, Any]) -> list[str]:
    props = node.get("properties") if isinstance(node.get("properties"), dict) else {}
    refs: list[str] = []
    for container in (node, props):
        for key in ("source_references", "source_files", "source_documents", "sources"):
            value = container.get(key)
            items: Iterable[Any] = value if isinstance(value, list) else ([value] if value else [])
            for item in items:
                if isinstance(item, dict):
                    item = item.get("fileName") or item.get("file_name") or item.get("name") or item.get("fileId")
                text = str(item or "").strip()
                if text and text not in refs:
                    refs.append(text)
    return refs


def _sort_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(events, key=lambda e: (str(e.get("date") or "9999"), str(e.get("time") or ""), str(e.get("name") or "")))


def render_snapshot_report_html(
    snapshot: dict[str, Any],
    *,
    case_name: str,
    generated_by: str,
    privilege_marking: str = "unmarked",
) -> str:
    from services import timeline_view_service as tvs

    label = privilege_label(privilege_marking)
    subgraph = snapshot.get("subgraph") or {}
    nodes = [n for n in (subgraph.get("nodes") or []) if _node_key(n)]
    if len(nodes) > MAX_REPORT_NODES:
        raise SnapshotReportError(
            f"Snapshot reports support up to {MAX_REPORT_NODES:,} entities; this snapshot has {len(nodes):,}. "
            "No partial report was generated."
        )
    events = _sort_events([e for e in (snapshot.get("timeline") or []) if isinstance(e, dict)])
    if len(events) > tvs.MAX_PDF_EVENTS:
        raise SnapshotReportError(
            f"Snapshot reports support up to {tvs.MAX_PDF_EVENTS:,} events; this snapshot has {len(events):,}. "
            "No partial report was generated."
        )
    _, all_saved = layout_positions(nodes)
    links = snapshot_links(subgraph)
    entity_rows = []
    for node in nodes:
        refs = _node_sources(node)
        entity_rows.append(
            "<tr><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                html.escape(str(node.get("label") or node.get("name") or _node_key(node))),
                html.escape(str(node.get("type") or "")),
                html.escape("; ".join(refs)) if refs else '<span class="muted">No source recorded on the entity</span>',
            )
        )
    notes = str(snapshot.get("notes") or "").strip()
    saved_at = str(snapshot.get("created_at") or snapshot.get("timestamp") or "")[:19].replace("T", " ")
    layout_note = (
        "Positions are as they were on the graph when the snapshot was saved."
        if all_saved
        else "Some entities had no saved position and are placed on a circle."
    )
    preface = f"""
    <section class="snapshot-marking"><strong>{html.escape(label)}</strong>
      <span>{html.escape(PRIVILEGE_BASIS)}</span></section>
    <section class="snapshot-meta">
      <p><strong>Snapshot saved:</strong> {html.escape(saved_at or "unknown")} &nbsp;·&nbsp;
         <strong>Entities:</strong> {len(nodes)} &nbsp;·&nbsp; <strong>Links:</strong> {len(links)} &nbsp;·&nbsp;
         <strong>Events:</strong> {len(events)}</p>
      {f'<p class="snapshot-notes">{html.escape(notes)}</p>' if notes else ''}
    </section>
    <section class="snapshot-graph">
      <h2>Graph</h2>
      <div class="graph-frame">{graph_svg(subgraph).replace('<svg ', '<svg class="graph-svg" ', 1)}</div>
      <p class="muted">Drawn as vector graphics from the saved graph. {html.escape(layout_note)}</p>
    </section>
    <section class="snapshot-entities">
      <h2>Entities in this snapshot</h2>
      <table><thead><tr><th>Entity</th><th>Type</th><th>Sources</th></tr></thead>
      <tbody>{''.join(entity_rows) or '<tr><td colspan="3">No entities.</td></tr>'}</tbody></table>
    </section>
    <h2 class="chronology-head">Events in this snapshot</h2>
    {'' if events else '<p class="muted">None of the entities in this snapshot is a dated event.</p>'}
    """
    css = """
      .snapshot-marking { border: 1.5px solid #0f172a; padding: 6px 10px; margin: 10px 0; font-size: 11px; }
      .snapshot-marking span { display: block; color: #475569; font-size: 9px; margin-top: 2px; }
      .graph-frame { border: 1px solid #cbd5e1; }
      .graph-svg { width: 100%; height: auto; display: block; }
      .snapshot-entities table { width: 100%; border-collapse: collapse; font-size: 9px; }
      .snapshot-entities td, .snapshot-entities th { border-bottom: 1px solid #e2e8f0; padding: 3px 4px; text-align: left; vertical-align: top; }
      .muted { color: #64748b; }
      .snapshot-notes { white-space: pre-wrap; }
    """
    footer = label if privilege_marking in ("confidential", "privileged_confidential") else "Loupe snapshot report"
    return tvs._render_pdf_html(
        events=events,
        case_name=case_name,
        title=str(snapshot.get("name") or "Snapshot"),
        fields=tvs._normalize_fields({"linked_entities": True, "source_references": True}, "standard"),
        detail_level="standard",
        generated_by=generated_by,
        footer_label=footer,
        notes_by_event={},
        eyebrow="Snapshot report",
        preface_html=preface,
        extra_css=css,
    )


def render_snapshot_report_pdf(snapshot: dict[str, Any], **kwargs: Any) -> bytes:
    from weasyprint import HTML

    from services.pdf_fetch import deny_all
    # The graph is inline SVG in the page, so the report never needs to fetch anything.
    deny_resource = deny_all("Snapshot reports cannot load external or local resources.")

    return HTML(string=render_snapshot_report_html(snapshot, **kwargs), url_fetcher=deny_resource).write_pdf()


def report_filename(snapshot: dict[str, Any]) -> str:
    import re

    name = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(snapshot.get("name") or "snapshot").strip().lower()).strip("-._")
    return f"{(name or 'snapshot')[:60]}-report-{datetime.now().strftime('%Y%m%d')}.pdf"


def frozen_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Events as stored in the snapshot: JSON-safe copies, so later edits to the case do not change the report."""
    import json

    return json.loads(json.dumps(events, ensure_ascii=False, default=str))
