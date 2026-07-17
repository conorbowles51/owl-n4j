"""Server-side visualization rendering for case exports."""

from __future__ import annotations

import base64
import hashlib
import io
import math
from datetime import datetime
from typing import Any
from urllib.parse import quote


GRAPH_COLORS = {
    "Person": "#2563eb",
    "Organization": "#7c3aed",
    "Company": "#7c3aed",
    "Location": "#059669",
    "Event": "#d97706",
    "Transaction": "#dc2626",
    "Document": "#64748b",
}
DEFAULT_COLOR = "#475569"


def svg_data_uri(svg: str | bytes) -> str:
    text = svg.decode("utf-8") if isinstance(svg, bytes) else svg
    return "data:image/svg+xml;charset=utf-8," + quote(text)


def png_data_uri(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def render_graph_svg(graph_data: dict[str, Any], *, title: str = "Case Graph") -> str:
    """Render a case graph as SVG bytes encoded as text."""
    plt, nx = _load_graph_libs()

    nodes = _dicts(graph_data.get("nodes"))
    links = _dicts(graph_data.get("links"))
    fig, ax = plt.subplots(figsize=(11, 7), dpi=144)
    ax.set_axis_off()
    fig.patch.set_facecolor("#ffffff")

    graph = nx.Graph()
    for node in nodes:
        key = _node_key(node)
        if not key:
            continue
        graph.add_node(
            key,
            label=_label(node, key),
            type=str(node.get("type") or "Entity"),
        )

    for link in links:
        source = _endpoint_key(link.get("source"))
        target = _endpoint_key(link.get("target"))
        if source and target and source in graph and target in graph:
            graph.add_edge(
                source,
                target,
                type=str(link.get("type") or link.get("relationship") or "related"),
            )

    if not graph.nodes:
        _empty_svg_axes(ax, title, "No graph entities are available for this case.")
        return _figure_svg(fig, plt)

    seed = int(
        hashlib.blake2b(
            "|".join(sorted(str(node) for node in graph.nodes)).encode("utf-8"),
            digest_size=4,
        ).hexdigest(),
        16,
    )
    if len(graph.nodes) == 1:
        pos = {next(iter(graph.nodes)): (0.0, 0.0)}
    else:
        pos = nx.spring_layout(
            graph,
            seed=seed,
            k=min(1.8, 4 / math.sqrt(len(graph.nodes))),
        )

    node_sizes = [
        max(260, min(1200, 280 + 90 * graph.degree(node)))
        for node in graph.nodes
    ]
    node_colors = [
        GRAPH_COLORS.get(str(graph.nodes[node].get("type") or ""), DEFAULT_COLOR)
        for node in graph.nodes
    ]
    edge_widths = [
        0.8 + min(2.2, (graph.degree(u) + graph.degree(v)) / 12)
        for u, v in graph.edges
    ]

    nx.draw_networkx_edges(
        graph,
        pos,
        ax=ax,
        edge_color="#cbd5e1",
        width=edge_widths,
        alpha=0.75,
    )
    nx.draw_networkx_nodes(
        graph,
        pos,
        ax=ax,
        node_color=node_colors,
        node_size=node_sizes,
        linewidths=1.2,
        edgecolors="#ffffff",
    )
    if len(graph.nodes) <= 60:
        font_size = 8 if len(graph.nodes) <= 28 else 6
        labels = {
            node: str(graph.nodes[node].get("label") or node)[:28]
            for node in graph.nodes
        }
        nx.draw_networkx_labels(
            graph,
            pos,
            labels=labels,
            ax=ax,
            font_size=font_size,
            font_color="#111827",
        )

    _title(ax, title, f"{len(graph.nodes)} entities | {len(graph.edges)} relationships")
    fig.tight_layout(pad=0.35)
    return _figure_svg(fig, plt)


def render_timeline_svg(events: list[dict[str, Any]], *, title: str = "Case Timeline") -> str:
    """Render timeline events as a compact SVG strip chart."""
    plt = _load_matplotlib()

    dated_events = []
    for event in _dicts(events):
        parsed = _parse_event_date(event)
        if parsed:
            dated_events.append((parsed, event))
    dated_events.sort(
        key=lambda item: (
            item[0],
            str(item[1].get("time") or ""),
            str(item[1].get("key") or ""),
        )
    )

    type_count = len({str(event.get("type") or "Event") for _, event in dated_events})
    height = max(3.6, min(8.5, 2.3 + type_count * 0.45))
    fig, ax = plt.subplots(figsize=(11, height), dpi=144)
    fig.patch.set_facecolor("#ffffff")

    if not dated_events:
        ax.set_axis_off()
        _empty_svg_axes(ax, title, "No dated timeline events are available for this case.")
        return _figure_svg(fig, plt)

    types = sorted({str(event.get("type") or "Event") for _, event in dated_events})
    y_for_type = {event_type: index for index, event_type in enumerate(types)}
    colors = [
        GRAPH_COLORS.get(str(event.get("type") or ""), DEFAULT_COLOR)
        for _, event in dated_events
    ]
    xs = [date for date, _ in dated_events]
    ys = [y_for_type[str(event.get("type") or "Event")] for _, event in dated_events]

    ax.scatter(
        xs,
        ys,
        s=62,
        c=colors,
        alpha=0.9,
        edgecolors="#ffffff",
        linewidths=0.8,
        zorder=3,
    )
    ax.set_yticks(range(len(types)), labels=types)
    ax.grid(axis="x", color="#e2e8f0", linewidth=0.8)
    ax.grid(axis="y", color="#f1f5f9", linewidth=0.8)
    ax.tick_params(axis="x", labelrotation=30, labelsize=8)
    ax.tick_params(axis="y", labelsize=8)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color("#cbd5e1")

    if len(dated_events) <= 28:
        for index, (date, event) in enumerate(dated_events):
            label = str(event.get("name") or event.get("key") or "Event")[:32]
            ax.annotate(
                label,
                (date, y_for_type[str(event.get("type") or "Event")]),
                xytext=(4, 5 + (index % 2) * 7),
                textcoords="offset points",
                fontsize=6.5,
                color="#334155",
            )

    _title(ax, title, f"{len(dated_events)} dated events")
    fig.tight_layout(pad=0.45)
    return _figure_svg(fig, plt)


def render_map_png(locations: list[dict[str, Any]], *, title: str = "Case Map") -> bytes:
    """Render case locations as PNG, using map tiles with an offline scatter fallback."""
    points = [
        {**location, "latitude": lat, "longitude": lon}
        for location in _dicts(locations)
        for lat, lon in [_lat_lon(location)]
        if lat is not None and lon is not None
    ]
    if not points:
        return _render_map_scatter_png(
            points,
            title=title,
            message="No geocoded locations are available for this case.",
        )

    try:
        return _render_staticmap_png(points)
    except Exception:
        return _render_map_scatter_png(points, title=title)


def _render_staticmap_png(points: list[dict[str, Any]]) -> bytes:
    from staticmap import CircleMarker, StaticMap

    tile_url = "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png"
    static_map = StaticMap(1100, 680, url_template=tile_url)
    for point in points[:500]:
        static_map.add_marker(CircleMarker((point["longitude"], point["latitude"]), "#dc2626", 12))

    image = static_map.render()
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _render_map_scatter_png(
    points: list[dict[str, Any]],
    *,
    title: str,
    message: str | None = None,
) -> bytes:
    plt = _load_matplotlib()
    fig, ax = plt.subplots(figsize=(11, 6.8), dpi=144)
    fig.patch.set_facecolor("#ffffff")

    if not points:
        ax.set_axis_off()
        ax.text(
            0.5,
            0.58,
            title,
            ha="center",
            va="center",
            fontsize=18,
            fontweight="bold",
            color="#111827",
        )
        ax.text(
            0.5,
            0.46,
            message or "No locations to render.",
            ha="center",
            va="center",
            fontsize=10,
            color="#64748b",
        )
        return _figure_png(fig, plt)

    xs = [point["longitude"] for point in points]
    ys = [point["latitude"] for point in points]
    ax.scatter(xs, ys, s=80, c="#dc2626", edgecolors="#ffffff", linewidths=0.9, alpha=0.9, zorder=3)
    if len(points) <= 40:
        for point in points:
            label = str(point.get("name") or point.get("key") or "Location")[:28]
            ax.annotate(
                label,
                (point["longitude"], point["latitude"]),
                xytext=(5, 5),
                textcoords="offset points",
                fontsize=7,
            )
    ax.set_xlabel("Longitude", fontsize=8, color="#475569")
    ax.set_ylabel("Latitude", fontsize=8, color="#475569")
    ax.grid(color="#e2e8f0", linewidth=0.8)
    for spine in ax.spines.values():
        spine.set_color("#cbd5e1")
    _title(ax, title, f"{len(points)} geocoded locations | offline map fallback")
    fig.tight_layout(pad=0.45)
    return _figure_png(fig, plt)


def _load_matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _load_graph_libs():
    plt = _load_matplotlib()
    import networkx as nx

    return plt, nx


def _figure_svg(fig: Any, plt: Any) -> str:
    buffer = io.StringIO()
    fig.savefig(
        buffer,
        format="svg",
        bbox_inches="tight",
        facecolor=fig.get_facecolor(),
        metadata={"Date": None},
    )
    plt.close(fig)
    return buffer.getvalue()


def _figure_png(fig: Any, plt: Any) -> bytes:
    buffer = io.BytesIO()
    fig.savefig(
        buffer,
        format="png",
        bbox_inches="tight",
        facecolor=fig.get_facecolor(),
        metadata={"Software": "Owl"},
    )
    plt.close(fig)
    return buffer.getvalue()


def _title(ax: Any, title: str, subtitle: str) -> None:
    ax.set_title(title, loc="left", fontsize=15, fontweight="bold", color="#111827", pad=18)
    ax.text(0, 1.015, subtitle, transform=ax.transAxes, fontsize=8.5, color="#64748b", va="bottom")


def _empty_svg_axes(ax: Any, title: str, message: str) -> None:
    ax.text(0.5, 0.58, title, ha="center", va="center", fontsize=18, fontweight="bold", color="#111827")
    ax.text(0.5, 0.46, message, ha="center", va="center", fontsize=10, color="#64748b")


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in value or [] if isinstance(item, dict)]


def _node_key(node: dict[str, Any]) -> str:
    return str(node.get("key") or node.get("id") or "").strip()


def _endpoint_key(value: Any) -> str:
    if isinstance(value, dict):
        return _node_key(value)
    return str(value or "").strip()


def _label(node: dict[str, Any], fallback: str) -> str:
    return str(node.get("name") or node.get("label") or fallback).strip()


def _parse_event_date(event: dict[str, Any]) -> datetime | None:
    raw = str(event.get("date") or "").strip()
    if not raw:
        return None
    raw = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw[:10])
    except ValueError:
        return None


def _lat_lon(location: dict[str, Any]) -> tuple[float | None, float | None]:
    try:
        lat = float(location.get("latitude"))
        lon = float(location.get("longitude"))
    except (TypeError, ValueError):
        return None, None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, None
    return lat, lon
