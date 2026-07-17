"""Visualization export sections."""

from __future__ import annotations

import html

from services.case_export.registry import ExportContext, ExportSection, register_section
from services.case_export.visualizations import (
    png_data_uri,
    render_graph_svg,
    render_map_png,
    render_timeline_svg,
    svg_data_uri,
)


def render_graph_section(context: ExportContext) -> str:
    neo4j_service = _get_neo4j_service()
    graph_data = neo4j_service.get_full_graph(case_id=str(context.case_id))
    svg = render_graph_svg(graph_data, title="Graph Visualization")
    nodes = len(graph_data.get("nodes") or [])
    links = len(graph_data.get("links") or [])
    return _figure_section(
        title="Graph Visualization",
        meta=f"{nodes} entities | {links} relationships",
        image_src=svg_data_uri(svg),
        image_type="svg",
    )


def render_timeline_section(context: ExportContext) -> str:
    neo4j_service = _get_neo4j_service()
    events = neo4j_service.get_timeline_events(case_id=str(context.case_id))
    svg = render_timeline_svg(events, title="Timeline Visualization")
    return _figure_section(
        title="Timeline Visualization",
        meta=f"{len(events)} events at export time",
        image_src=svg_data_uri(svg),
        image_type="svg",
    )


def render_map_section(context: ExportContext) -> str:
    neo4j_service = _get_neo4j_service()
    locations = neo4j_service.get_entities_with_locations(case_id=str(context.case_id))
    png = render_map_png(locations, title="Map Visualization")
    return _figure_section(
        title="Map Visualization",
        meta=f"{len(locations)} geocoded entities at export time",
        image_src=png_data_uri(png),
        image_type="png",
    )


def _figure_section(*, title: str, meta: str, image_src: str, image_type: str) -> str:
    return f"""
    <section class="export-section visualization-section" id="{html.escape(title.lower().replace(' ', '-'))}">
        <h2>{html.escape(title)}</h2>
        <p class="section-meta">{html.escape(meta)}</p>
        <img class="visualization-image visualization-{html.escape(image_type)}"
             src="{image_src}"
             alt="{html.escape(title)}" />
    </section>
    """


def _get_neo4j_service():
    from services.neo4j_service import neo4j_service

    return neo4j_service


register_section(
    ExportSection(
        key="graph",
        title="Graph Visualization",
        order=110,
        render=render_graph_section,
    )
)
register_section(
    ExportSection(
        key="timeline",
        title="Timeline Visualization",
        order=120,
        render=render_timeline_section,
    )
)
register_section(
    ExportSection(
        key="map",
        title="Map Visualization",
        order=130,
        render=render_map_section,
    )
)
