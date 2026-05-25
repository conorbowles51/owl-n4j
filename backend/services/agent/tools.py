from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, Literal

from neo4j import READ_ACCESS
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from services.agent.cypher_safety import UnsafeCypherError, repair_common_cypher, run_readonly_cypher
from services.agent.json_utils import to_jsonable, truncate_payload, truncate_text
from services.neo4j.driver import driver
from services.neo4j.financial_service import financial_service
from services.neo4j.geo_service import geo_service
from services.neo4j.graph_service import graph_service
from services.neo4j.timeline_service import timeline_service
from services.vector_db_service import get_vector_db_service


MAX_DIRECT_TABLE_ROWS = 100
MAX_DIRECT_TABLE_COLUMNS = 20
MAX_DIRECT_TABLE_CELL_CHARS = 1200
MAX_DIRECT_TABLE_KEY_CHARS = 80
MAX_CHART_ROWS = 250
MAX_CHART_SERIES = 8
MAX_CHART_CELL_CHARS = 600
ChartType = Literal["bar", "stacked_bar", "line", "area", "pie", "donut", "scatter"]


@dataclass
class AgentToolContext:
    case_id: str
    artifact_preference: str = "auto"
    result_store: dict[str, Any] = field(default_factory=dict)
    artifact_store: dict[str, dict[str, Any]] = field(default_factory=dict)

    def result(
        self,
        tool_name: str,
        data: Any,
        *,
        summary: str,
        artifact: dict[str, Any] | None = None,
        status: Literal["success", "error"] = "success",
        error: str | None = None,
    ) -> dict[str, Any]:
        result_id = f"res_{uuid.uuid4().hex[:12]}"
        safe_data = to_jsonable(data)
        self.result_store[result_id] = safe_data
        payload = {
            "result_id": result_id,
            "status": status,
            "summary": summary,
            "data": safe_data,
        }
        if error:
            payload["error"] = error
        if artifact:
            artifact_id = artifact.get("id")
            if artifact_id:
                self.artifact_store[str(artifact_id)] = to_jsonable(artifact)
            payload["artifact"] = artifact
        return payload


class EmptyArgs(BaseModel):
    pass


class ClarificationOptionArgs(BaseModel):
    id: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    description: str | None = None


class ClarificationArgs(BaseModel):
    question: str = Field(..., min_length=1)
    options: list[ClarificationOptionArgs] = Field(..., min_length=2, max_length=4)
    allow_free_text: bool = True
    reason: str | None = None


class SearchGraphEntitiesArgs(BaseModel):
    query: str = Field(..., min_length=1, description="Name, alias, key, or phrase to search for.")
    limit: int = Field(10, ge=1, le=25)


class InspectGraphSchemaArgs(BaseModel):
    labels: list[str] | None = Field(
        default=None,
        description="Optional node labels to inspect, for example ['Person', 'Transaction'].",
    )
    relationship_types: list[str] | None = Field(
        default=None,
        description="Optional relationship types to inspect, for example ['SENT_PAYMENT'].",
    )
    sample_limit: int = Field(3, ge=1, le=8)


class EntityKeyArgs(BaseModel):
    entity_key: str = Field(..., min_length=1, description="Exact graph node key.")


class EntityNeighborhoodArgs(EntityKeyArgs):
    depth: int = Field(1, ge=1, le=3)


class PathArgs(BaseModel):
    source_key: str = Field(..., min_length=1)
    target_key: str = Field(..., min_length=1)
    max_depth: int = Field(4, ge=1, le=6)


class SearchDocumentsArgs(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(8, ge=1, le=20)


class ReadonlyCypherArgs(BaseModel):
    query: str = Field(..., min_length=1, description="Read-only Cypher. Must include $case_id.")
    params: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(50, ge=1, le=200)


class TimelineArgs(BaseModel):
    event_types: list[str] | None = None
    start_date: str | None = None
    end_date: str | None = None
    limit: int = Field(25, ge=1, le=100)


class FinancialArgs(BaseModel):
    entity_keys: list[str] | None = None
    start_date: str | None = None
    end_date: str | None = None
    categories: list[str] | None = None
    mode: Literal["transactions", "intelligence"] = "transactions"
    limit: int = Field(25, ge=1, le=100)


class MapArgs(BaseModel):
    entity_types: list[str] | None = None
    entity_keys: list[str] | None = None
    limit: int = Field(50, ge=1, le=200)


class GraphArtifactArgs(BaseModel):
    node_keys: list[str] = Field(default_factory=list)
    title: str | None = None
    depth: int = Field(1, ge=0, le=3)
    mode: Literal[
        "entity_neighborhood",
        "transaction_only",
        "transactions_plus_accounts",
        "transaction_flow",
        "shortest_paths",
    ] = "entity_neighborhood"
    node_types: list[str] | None = None
    relationship_types: list[str] | None = None
    max_nodes: int = Field(75, ge=1, le=250)
    max_relationships: int = Field(200, ge=0, le=500)
    include_bridge_nodes: bool = True


class TableArtifactArgs(BaseModel):
    title: str | None = None
    query: str = Field(..., min_length=1, description="Read-only Cypher that returns table rows and includes $case_id.")
    params: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(50, ge=1, le=200)


class TableColumnArgs(BaseModel):
    key: str = Field(..., min_length=1, max_length=MAX_DIRECT_TABLE_KEY_CHARS)
    label: str | None = Field(default=None, max_length=120)


class DirectTableArtifactArgs(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    columns: list[TableColumnArgs] = Field(
        default_factory=list,
        max_length=MAX_DIRECT_TABLE_COLUMNS,
        description="Optional display columns. Missing row keys are appended after these columns.",
    )
    rows: list[dict[str, Any]] = Field(
        ...,
        min_length=1,
        max_length=MAX_DIRECT_TABLE_ROWS,
        description="Rows synthesized from prior tool evidence. Values must be strings, numbers, booleans, or null.",
    )
    source_result_ids: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Optional result_id values for tool results that support this table.",
    )
    notes: str | None = Field(default=None, max_length=1000)


class ChartSeriesArgs(BaseModel):
    key: str = Field(..., min_length=1, max_length=MAX_DIRECT_TABLE_KEY_CHARS)
    label: str | None = Field(default=None, max_length=120)
    color: str | None = Field(
        default=None,
        max_length=32,
        description="Optional CSS color for this series, for example #6366F1.",
    )
    stack: str | None = Field(default=None, max_length=80)


class ChartArtifactArgs(BaseModel):
    title: str = Field(..., min_length=1, max_length=140)
    chart_type: ChartType = Field(
        ...,
        description="Chart shape: bar, stacked_bar, line, area, pie, donut, or scatter.",
    )
    rows: list[dict[str, Any]] = Field(
        ...,
        min_length=1,
        max_length=MAX_CHART_ROWS,
        description="Chart source rows synthesized from prior tool evidence. Values must be scalar.",
    )
    x_key: str | None = Field(
        default=None,
        max_length=MAX_DIRECT_TABLE_KEY_CHARS,
        description="X-axis/category key for bar, stacked_bar, line, area, and scatter charts.",
    )
    y_keys: list[str] = Field(
        default_factory=list,
        max_length=MAX_CHART_SERIES,
        description="Numeric value keys for bar, stacked_bar, line, area, and scatter charts.",
    )
    category_key: str | None = Field(
        default=None,
        max_length=MAX_DIRECT_TABLE_KEY_CHARS,
        description="Category label key for pie or donut charts.",
    )
    value_key: str | None = Field(
        default=None,
        max_length=MAX_DIRECT_TABLE_KEY_CHARS,
        description="Numeric value key for pie or donut charts.",
    )
    series: list[ChartSeriesArgs] = Field(
        default_factory=list,
        max_length=MAX_CHART_SERIES,
        description="Optional display labels/colors for numeric series.",
    )
    x_label: str | None = Field(default=None, max_length=120)
    y_label: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=1000)
    source_result_ids: list[str] = Field(default_factory=list, max_length=20)


class ReportEmbedArgs(BaseModel):
    artifact_id: str = Field(..., min_length=1)
    caption: str | None = Field(default=None, max_length=300)


class ReportSectionArgs(BaseModel):
    heading: str = Field(..., min_length=1, max_length=160)
    content: str = Field(..., min_length=1, max_length=12000)
    level: int = Field(2, ge=1, le=3)
    embeds: list[ReportEmbedArgs] = Field(default_factory=list, max_length=6)


class ReportArtifactArgs(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    purpose: str = Field(..., min_length=1, max_length=1000)
    report_scope: str = Field(
        ...,
        min_length=1,
        max_length=1500,
        description="Clear statement of what the user asked to include and the report boundary.",
    )
    included_items: list[str] = Field(
        ...,
        min_length=1,
        max_length=30,
        description="Specific topics, evidence groups, questions, or headings included in the report.",
    )
    audience: str | None = Field(default=None, max_length=300)
    sections: list[ReportSectionArgs] = Field(..., min_length=1, max_length=24)
    source_result_ids: list[str] = Field(default_factory=list, max_length=30)
    open_questions: list[str] = Field(default_factory=list, max_length=20)
    revision_note: str | None = Field(default=None, max_length=1000)


class MapArtifactArgs(BaseModel):
    title: str | None = None
    entity_keys: list[str] = Field(default_factory=list)
    entity_types: list[str] | None = None
    limit: int = Field(100, ge=1, le=200)


def _artifact(artifact_type: str, title: str, data: dict[str, Any], metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "type": artifact_type,
        "title": title,
        "data": to_jsonable(data),
        "metadata": to_jsonable(metadata or {}),
    }


def _graph_counts(graph: dict[str, Any]) -> str:
    return f"{len(graph.get('nodes') or [])} nodes and {len(graph.get('links') or [])} relationships"


def _compact_node(node: dict[str, Any]) -> dict[str, Any]:
    props = node.get("properties") if isinstance(node.get("properties"), dict) else {}
    key = node.get("key") or props.get("key") or node.get("id")
    return {
        "id": node.get("id") or key,
        "key": key,
        "name": node.get("name") or props.get("name") or key,
        "type": node.get("type") or props.get("type"),
        "summary": truncate_text(node.get("summary") or props.get("summary"), 500),
        "date": node.get("date") or props.get("date"),
        "amount": node.get("amount") or props.get("amount"),
    }


def _compact_link(link: dict[str, Any]) -> dict[str, Any]:
    props = link.get("properties") if isinstance(link.get("properties"), dict) else {}
    compact_props = {
        key: truncate_text(props.get(key), 300)
        for key in ("detail", "date", "amount", "currency", "confidence")
        if props.get(key) is not None
    }
    source_files = props.get("source_files")
    if isinstance(source_files, list):
        compact_props["source_files"] = source_files[:5]
    return {
        "source": link.get("source"),
        "target": link.get("target"),
        "type": link.get("type"),
        "properties": compact_props,
    }


def _compact_graph(graph: dict[str, Any]) -> dict[str, Any]:
    return {
        "nodes": [_compact_node(node) for node in as_dict_list(graph.get("nodes"))],
        "links": [_compact_link(link) for link in as_dict_list(graph.get("links"))],
    }


def as_dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _filter_transactions(
    transactions: list[dict[str, Any]],
    *,
    entity_keys: list[str] | None,
    limit: int,
) -> list[dict[str, Any]]:
    keys = set(entity_keys or [])
    filtered: list[dict[str, Any]] = []
    for tx in transactions:
        if keys:
            from_entity = tx.get("from_entity") or {}
            to_entity = tx.get("to_entity") or {}
            if tx.get("key") not in keys and from_entity.get("key") not in keys and to_entity.get("key") not in keys:
                continue
        filtered.append(tx)
        if len(filtered) >= limit:
            break
    return filtered


def _columns_from_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    keys: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in keys:
                keys.append(key)
    return [{"key": key, "label": key.replace("_", " ").title()} for key in keys]


def _is_table_scalar(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    return isinstance(value, float) and value == value and value not in (float("inf"), float("-inf"))


def _normalize_direct_table(
    *,
    rows: list[dict[str, Any]],
    columns: list[TableColumnArgs],
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    if not rows:
        raise ValueError("At least one table row is required.")
    if len(rows) > MAX_DIRECT_TABLE_ROWS:
        raise ValueError(f"Direct table artifacts are limited to {MAX_DIRECT_TABLE_ROWS} rows.")

    ordered_keys: list[str] = []
    column_labels: dict[str, str] = {}
    for column in columns:
        raw_key = column.key if isinstance(column, TableColumnArgs) else column.get("key")
        raw_label = column.label if isinstance(column, TableColumnArgs) else column.get("label")
        key = truncate_text(str(raw_key).strip(), MAX_DIRECT_TABLE_KEY_CHARS)
        if not key:
            raise ValueError("Table column keys cannot be blank.")
        if key not in ordered_keys:
            ordered_keys.append(key)
        column_labels[key] = truncate_text(raw_label or key.replace("_", " ").title(), 120)

    normalized_rows: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"Table row {row_index} must be an object.")
        normalized: dict[str, Any] = {}
        for raw_key, raw_value in row.items():
            key = truncate_text(str(raw_key).strip(), MAX_DIRECT_TABLE_KEY_CHARS)
            if not key:
                raise ValueError(f"Table row {row_index} contains a blank column key.")
            if not _is_table_scalar(raw_value):
                raise ValueError(
                    f"Table row {row_index}, column '{key}' has a non-scalar value. "
                    "Use strings, numbers, booleans, or null only."
                )
            if key not in ordered_keys:
                ordered_keys.append(key)
            if isinstance(raw_value, str):
                normalized[key] = truncate_text(raw_value, MAX_DIRECT_TABLE_CELL_CHARS)
            else:
                normalized[key] = raw_value
        normalized_rows.append(normalized)

    if len(ordered_keys) > MAX_DIRECT_TABLE_COLUMNS:
        raise ValueError(f"Direct table artifacts are limited to {MAX_DIRECT_TABLE_COLUMNS} columns.")

    normalized_columns = [
        {
            "key": key,
            "label": column_labels.get(key) or key.replace("_", " ").title(),
        }
        for key in ordered_keys
    ]
    return normalized_columns, normalized_rows


def _normalize_chart_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    if not rows:
        raise ValueError("At least one chart row is required.")
    if len(rows) > MAX_CHART_ROWS:
        raise ValueError(f"Chart artifacts are limited to {MAX_CHART_ROWS} rows.")

    ordered_keys: list[str] = []
    normalized_rows: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"Chart row {row_index} must be an object.")
        normalized: dict[str, Any] = {}
        for raw_key, raw_value in row.items():
            key = truncate_text(str(raw_key).strip(), MAX_DIRECT_TABLE_KEY_CHARS)
            if not key:
                raise ValueError(f"Chart row {row_index} contains a blank column key.")
            if not _is_table_scalar(raw_value):
                raise ValueError(
                    f"Chart row {row_index}, column '{key}' has a non-scalar value. "
                    "Use strings, numbers, booleans, or null only."
                )
            if key not in ordered_keys:
                ordered_keys.append(key)
            normalized[key] = truncate_text(raw_value, MAX_CHART_CELL_CHARS) if isinstance(raw_value, str) else raw_value
        normalized_rows.append(normalized)

    if len(ordered_keys) > MAX_DIRECT_TABLE_COLUMNS:
        raise ValueError(f"Chart artifacts are limited to {MAX_DIRECT_TABLE_COLUMNS} columns.")

    return [{"key": key, "label": key.replace("_", " ").title()} for key in ordered_keys], normalized_rows


def _as_finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.replace(",", "").strip())
        except ValueError:
            return None
    else:
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _chart_numeric_keys(rows: list[dict[str, Any]]) -> list[str]:
    keys: list[str] = []
    for row in rows:
        for key, value in row.items():
            if _as_finite_number(value) is not None and key not in keys:
                keys.append(key)
    return keys


def _chart_category_keys(rows: list[dict[str, Any]], numeric_keys: list[str]) -> list[str]:
    numeric = set(numeric_keys)
    keys: list[str] = []
    for row in rows:
        for key, value in row.items():
            if key in numeric:
                continue
            if value is not None and str(value).strip() and key not in keys:
                keys.append(key)
    return keys


def _normalize_chart_artifact(
    *,
    chart_type: ChartType,
    rows: list[dict[str, Any]],
    x_key: str | None,
    y_keys: list[str] | None,
    category_key: str | None,
    value_key: str | None,
    series: list[ChartSeriesArgs] | None,
) -> dict[str, Any]:
    columns, normalized_rows = _normalize_chart_rows(rows)
    numeric_keys = _chart_numeric_keys(normalized_rows)
    category_keys = _chart_category_keys(normalized_rows, numeric_keys)
    available_keys = {column["key"] for column in columns}
    clean_series = [
        {
            "key": truncate_text(item.key, MAX_DIRECT_TABLE_KEY_CHARS),
            "label": truncate_text(item.label or item.key.replace("_", " ").title(), 120),
            "color": truncate_text(item.color, 32) if item.color else None,
            "stack": truncate_text(item.stack, 80) if item.stack else None,
        }
        for item in (series or [])
    ]
    series_by_key = {item["key"]: item for item in clean_series}

    if chart_type in {"pie", "donut"}:
        selected_category = truncate_text(category_key, MAX_DIRECT_TABLE_KEY_CHARS) if category_key else (category_keys[0] if category_keys else None)
        selected_value = truncate_text(value_key, MAX_DIRECT_TABLE_KEY_CHARS) if value_key else (numeric_keys[0] if numeric_keys else None)
        if not selected_category or selected_category not in available_keys:
            raise ValueError("Pie and donut charts need a valid category_key.")
        if not selected_value or selected_value not in available_keys:
            raise ValueError("Pie and donut charts need a valid numeric value_key.")
        if selected_value not in numeric_keys:
            raise ValueError(f"Chart value_key '{selected_value}' must contain numeric values.")
        return {
            "rows": normalized_rows,
            "columns": columns,
            "category_key": selected_category,
            "value_key": selected_value,
            "x_key": "",
            "y_keys": [selected_value],
            "series": [
                series_by_key.get(selected_value)
                or {"key": selected_value, "label": selected_value.replace("_", " ").title(), "color": None, "stack": None}
            ],
        }

    selected_x = truncate_text(x_key, MAX_DIRECT_TABLE_KEY_CHARS) if x_key else (category_keys[0] if category_keys else (columns[0]["key"] if columns else None))
    if not selected_x or selected_x not in available_keys:
        raise ValueError("Chart needs a valid x_key.")
    if chart_type == "scatter" and selected_x not in numeric_keys:
        raise ValueError("Scatter charts need a numeric x_key.")

    requested_y = [
        truncate_text(key, MAX_DIRECT_TABLE_KEY_CHARS)
        for key in (y_keys or [])
        if str(key).strip()
    ]
    selected_y = [key for key in requested_y if key in available_keys]
    if not selected_y:
        selected_y = [key for key in numeric_keys if key != selected_x][:MAX_CHART_SERIES]
    if not selected_y:
        raise ValueError("Chart needs at least one numeric y_key.")

    non_numeric = [key for key in selected_y if key not in numeric_keys]
    if non_numeric:
        raise ValueError(f"Chart y_keys must contain numeric values: {', '.join(non_numeric)}")

    return {
        "rows": normalized_rows,
        "columns": columns,
        "x_key": selected_x,
        "y_keys": selected_y[:MAX_CHART_SERIES],
        "category_key": "",
        "value_key": "",
        "series": [
            series_by_key.get(key)
            or {"key": key, "label": key.replace("_", " ").title(), "color": None, "stack": "total" if chart_type == "stacked_bar" else None}
            for key in selected_y[:MAX_CHART_SERIES]
        ],
    }


def _snapshot_report_embed(context: AgentToolContext, embed: ReportEmbedArgs) -> dict[str, Any]:
    artifact = context.artifact_store.get(str(embed.artifact_id))
    if not artifact:
        return {
            "artifact_id": embed.artifact_id,
            "caption": embed.caption,
            "available": False,
            "type": "unknown",
            "title": "Referenced artifact",
            "data": {},
        }

    artifact_type = str(artifact.get("type") or "unknown")
    if artifact_type not in {"graph", "table", "chart"}:
        return {
            "artifact_id": embed.artifact_id,
            "caption": embed.caption,
            "available": False,
            "type": artifact_type,
            "title": str(artifact.get("title") or "Referenced artifact"),
            "data": {},
            "reason": "Only graph, table, and chart artifacts can be embedded in reports.",
        }

    return {
        "artifact_id": str(artifact.get("id") or embed.artifact_id),
        "caption": embed.caption,
        "available": True,
        "type": artifact_type,
        "title": str(artifact.get("title") or "Embedded artifact"),
        "data": truncate_payload(artifact.get("data") or {}, max_items=120, max_text_chars=2000),
        "metadata": truncate_payload(artifact.get("metadata") or {}, max_items=30, max_text_chars=1000),
    }


def _normalize_report_sections(
    context: AgentToolContext,
    sections: list[ReportSectionArgs],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    normalized_sections: list[dict[str, Any]] = []
    embedded_artifacts: list[dict[str, Any]] = []
    seen_embed_ids: set[str] = set()

    for index, section in enumerate(sections, start=1):
        section_id = f"section-{index}"
        section_embeds: list[dict[str, Any]] = []
        for embed in section.embeds:
            snapshot = _snapshot_report_embed(context, embed)
            snapshot["section_id"] = section_id
            section_embeds.append(snapshot)
            artifact_id = str(snapshot.get("artifact_id") or "")
            if artifact_id and artifact_id not in seen_embed_ids:
                seen_embed_ids.add(artifact_id)
                embedded_artifacts.append(snapshot)

        normalized_sections.append(
            {
                "id": section_id,
                "heading": truncate_text(section.heading, 160),
                "content": truncate_text(section.content, 12000),
                "level": max(1, min(int(section.level or 2), 3)),
                "embeds": section_embeds,
            }
        )

    return normalized_sections, embedded_artifacts


def _is_blank_display_value(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return text == "" or text.lower() in {
        "null",
        "none",
        "n/a",
        "unknown",
        "(no name)",
        "(no display_name)",
    }


def _preview_schema_value(value: Any) -> Any:
    safe = to_jsonable(value)
    if isinstance(safe, str):
        return truncate_text(safe, 120)
    if isinstance(safe, int | float | bool) or safe is None:
        return safe
    if isinstance(safe, list):
        return [_preview_schema_value(item) for item in safe[:3]]
    if isinstance(safe, dict):
        return {
            str(key): _preview_schema_value(item)
            for key, item in list(safe.items())[:5]
        }
    return truncate_text(str(safe), 120)


def _append_sample(samples: list[Any], value: Any, limit: int) -> None:
    if value is None or len(samples) >= limit:
        return
    preview = _preview_schema_value(value)
    if all(existing != preview for existing in samples):
        samples.append(preview)


def _schema_properties(
    counts: list[dict[str, Any]],
    samples: list[dict[str, Any]],
    *,
    group_key: str,
    sample_limit: int,
) -> dict[str, dict[str, dict[str, Any]]]:
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for row in counts:
        group = str(row.get(group_key) or "")
        if not group:
            continue
        props: dict[str, dict[str, Any]] = {}
        for prop in as_dict_list(row.get("properties")):
            name = str(prop.get("key") or "")
            if not name:
                continue
            props[name] = {
                "present_count": int(prop.get("present_count") or 0),
                "sample_values": [],
            }
        grouped[group] = props

    for row in samples:
        group = str(row.get(group_key) or "")
        props = grouped.setdefault(group, {})
        for sample in as_dict_list(row.get("samples")):
            for key, value in sample.items():
                if value is None:
                    continue
                prop = props.setdefault(key, {"present_count": 0, "sample_values": []})
                _append_sample(prop["sample_values"], value, sample_limit)

    return grouped


def _inspect_graph_schema(
    case_id: str,
    *,
    labels: list[str] | None = None,
    relationship_types: list[str] | None = None,
    sample_limit: int = 3,
) -> dict[str, Any]:
    clean_labels = [label for label in dict.fromkeys(labels or []) if label]
    clean_relationships = [rel for rel in dict.fromkeys(relationship_types or []) if rel]
    safe_sample_limit = max(1, min(int(sample_limit or 3), 8))

    with driver.session(default_access_mode=READ_ACCESS) as session:
        label_counts = [
            dict(row)
            for row in session.run(
                """
                MATCH (n)
                WHERE n.case_id = $case_id
                UNWIND labels(n) AS label
                WITH label, n
                WHERE size($labels) = 0 OR label IN $labels
                WITH label, count(n) AS node_count
                RETURN label, node_count
                ORDER BY node_count DESC, label ASC
                """,
                case_id=case_id,
                labels=clean_labels,
            )
        ]
        label_property_counts = [
            dict(row)
            for row in session.run(
                """
                MATCH (n)
                WHERE n.case_id = $case_id
                UNWIND labels(n) AS label
                WITH label, n
                WHERE size($labels) = 0 OR label IN $labels
                UNWIND keys(n) AS property
                WITH label, property, count(n) AS present_count
                RETURN label, collect({key: property, present_count: present_count}) AS properties
                ORDER BY label ASC
                """,
                case_id=case_id,
                labels=clean_labels,
            )
        ]
        label_samples = [
            dict(row)
            for row in session.run(
                """
                MATCH (n)
                WHERE n.case_id = $case_id
                UNWIND labels(n) AS label
                WITH DISTINCT label
                WHERE size($labels) = 0 OR label IN $labels
                CALL (label) {
                  MATCH (n)
                  WHERE n.case_id = $case_id AND label IN labels(n)
                  WITH n
                  ORDER BY coalesce(n.name, properties(n)['display_name'], properties(n)['full_name'], properties(n)['title'], n.key, '')
                  RETURN properties(n) AS sample
                  LIMIT $sample_limit
                }
                RETURN label, collect(sample) AS samples
                ORDER BY label ASC
                """,
                case_id=case_id,
                labels=clean_labels,
                sample_limit=safe_sample_limit,
            )
        ]
        relationship_counts = [
            dict(row)
            for row in session.run(
                """
                MATCH ()-[r]->()
                WHERE r.case_id = $case_id
                WITH type(r) AS relationship_type, r
                WHERE size($relationship_types) = 0 OR relationship_type IN $relationship_types
                WITH relationship_type, count(r) AS relationship_count
                RETURN relationship_type, relationship_count
                ORDER BY relationship_count DESC, relationship_type ASC
                """,
                case_id=case_id,
                relationship_types=clean_relationships,
            )
        ]
        relationship_property_counts = [
            dict(row)
            for row in session.run(
                """
                MATCH ()-[r]->()
                WHERE r.case_id = $case_id
                WITH type(r) AS relationship_type, r
                WHERE size($relationship_types) = 0 OR relationship_type IN $relationship_types
                UNWIND keys(r) AS property
                WITH relationship_type, property, count(r) AS present_count
                RETURN relationship_type, collect({key: property, present_count: present_count}) AS properties
                ORDER BY relationship_type ASC
                """,
                case_id=case_id,
                relationship_types=clean_relationships,
            )
        ]
        relationship_samples = [
            dict(row)
            for row in session.run(
                """
                MATCH ()-[r]->()
                WHERE r.case_id = $case_id
                WITH DISTINCT type(r) AS relationship_type
                WHERE size($relationship_types) = 0 OR relationship_type IN $relationship_types
                CALL (relationship_type) {
                  MATCH ()-[r]->()
                  WHERE r.case_id = $case_id AND type(r) = relationship_type
                  RETURN properties(r) AS sample
                  LIMIT $sample_limit
                }
                RETURN relationship_type, collect(sample) AS samples
                ORDER BY relationship_type ASC
                """,
                case_id=case_id,
                relationship_types=clean_relationships,
                sample_limit=safe_sample_limit,
            )
        ]

    label_props = _schema_properties(
        label_property_counts,
        label_samples,
        group_key="label",
        sample_limit=safe_sample_limit,
    )
    relationship_props = _schema_properties(
        relationship_property_counts,
        relationship_samples,
        group_key="relationship_type",
        sample_limit=safe_sample_limit,
    )

    return {
        "labels": {
            str(row["label"]): {
                "count": int(row.get("node_count") or 0),
                "properties": label_props.get(str(row["label"]), {}),
            }
            for row in label_counts
        },
        "relationships": {
            str(row["relationship_type"]): {
                "count": int(row.get("relationship_count") or 0),
                "properties": relationship_props.get(str(row["relationship_type"]), {}),
            }
            for row in relationship_counts
        },
        "display_name_expression": "coalesce(n.name, n.display_name, n.full_name, n.title, n.key)",
    }


def _entity_key_from_table_row(row: dict[str, Any]) -> str | None:
    for key in ("entity_key", "person_key", "node_key", "key"):
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _lookup_entity_display_names(case_id: str, keys: list[str]) -> dict[str, str]:
    clean_keys = [key for key in dict.fromkeys(keys) if key]
    if not clean_keys:
        return {}
    with driver.session(default_access_mode=READ_ACCESS) as session:
        rows = session.run(
            """
            MATCH (n)
            WHERE n.case_id = $case_id AND n.key IN $keys
            RETURN n.key AS key,
                   coalesce(n.name, properties(n)['display_name'], properties(n)['full_name'], properties(n)['title'], properties(n)['label'], n.key) AS display_name
            """,
            case_id=case_id,
            keys=clean_keys,
        )
        return {
            str(row["key"]): str(row["display_name"])
            for row in rows
            if row.get("key") and row.get("display_name")
        }


def _enrich_table_rows_with_entity_names(case_id: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys_to_resolve = [
        key
        for row in rows
        if _is_blank_display_value(row.get("name")) or _is_blank_display_value(row.get("display_name"))
        for key in [_entity_key_from_table_row(row)]
        if key
    ]
    lookup = _lookup_entity_display_names(case_id, keys_to_resolve)
    if not lookup:
        return rows

    enriched: list[dict[str, Any]] = []
    for row in rows:
        updated = dict(row)
        display_name = lookup.get(_entity_key_from_table_row(row) or "")
        if display_name:
            if "name" in updated and _is_blank_display_value(updated.get("name")):
                updated["name"] = display_name
            if "display_name" in updated and _is_blank_display_value(updated.get("display_name")):
                updated["display_name"] = display_name
            if "name" not in updated and "display_name" not in updated:
                updated["name"] = display_name
        enriched.append(updated)
    return enriched


def _find_paths(case_id: str, source_key: str, target_key: str, max_depth: int) -> list[dict[str, Any]]:
    depth = max(1, min(max_depth, 6))
    query = f"""
        MATCH (source {{key: $source_key, case_id: $case_id}})
        MATCH (target {{key: $target_key, case_id: $case_id}})
        MATCH path = allShortestPaths((source)-[*..{depth}]-(target))
        WHERE all(node IN nodes(path) WHERE node.case_id = $case_id)
          AND all(rel IN relationships(path) WHERE rel.case_id = $case_id)
        RETURN
          [node IN nodes(path) | {{
            key: node.key,
            name: node.name,
            type: labels(node)[0],
            summary: left(coalesce(node.summary, ''), 500)
          }}] AS nodes,
          [rel IN relationships(path) | {{
            source: startNode(rel).key,
            target: endNode(rel).key,
            type: type(rel),
            properties: properties(rel)
          }}] AS relationships
        LIMIT 5
    """
    with driver.session(default_access_mode=READ_ACCESS) as session:
        rows = session.run(
            query,
            case_id=case_id,
            source_key=source_key,
            target_key=target_key,
        )
        return [to_jsonable(dict(row)) for row in rows]


def _graph_node_map(node: Any) -> dict[str, Any]:
    if not isinstance(node, dict):
        return {}
    props = node.get("properties") if isinstance(node.get("properties"), dict) else node
    key = node.get("key") or props.get("key") or node.get("id")
    return {
        "id": node.get("id") or key,
        "key": key,
        "name": node.get("name") or props.get("name") or key,
        "type": node.get("type") or props.get("type"),
        "summary": node.get("summary") or props.get("summary"),
        "date": node.get("date") or props.get("date"),
        "amount": node.get("amount") or props.get("amount"),
        "properties": props if props is not node else {},
    }


def _relationship_map(rel: Any) -> dict[str, Any]:
    if not isinstance(rel, dict):
        return {}
    return {
        "source": rel.get("source"),
        "target": rel.get("target"),
        "type": rel.get("type"),
        "properties": rel.get("properties") if isinstance(rel.get("properties"), dict) else {},
    }


def _dedupe_graph(graph: dict[str, Any]) -> dict[str, Any]:
    nodes_by_key: dict[str, dict[str, Any]] = {}
    for raw in as_dict_list(graph.get("nodes")):
        node = _graph_node_map(raw)
        key = node.get("key")
        if key and key not in nodes_by_key:
            nodes_by_key[key] = node

    seen_links: set[tuple[str, str, str]] = set()
    links: list[dict[str, Any]] = []
    for raw in as_dict_list(graph.get("links")):
        link = _relationship_map(raw)
        source = link.get("source")
        target = link.get("target")
        rel_type = link.get("type") or "RELATED_TO"
        if not source or not target:
            continue
        marker = (str(source), str(target), str(rel_type))
        if marker in seen_links:
            continue
        seen_links.add(marker)
        links.append(link)

    return {"nodes": list(nodes_by_key.values()), "links": links}


def _limit_graph(
    graph: dict[str, Any],
    *,
    max_nodes: int,
    max_relationships: int,
    focus_keys: list[str] | None = None,
) -> dict[str, Any]:
    focus = set(focus_keys or [])
    nodes = as_dict_list(graph.get("nodes"))
    links = as_dict_list(graph.get("links"))
    degree: dict[str, int] = {}
    for link in links:
        source = str(link.get("source") or "")
        target = str(link.get("target") or "")
        if source:
            degree[source] = degree.get(source, 0) + 1
        if target:
            degree[target] = degree.get(target, 0) + 1

    ordered_nodes = sorted(
        nodes,
        key=lambda node: (
            0 if node.get("key") in focus else 1,
            -degree.get(str(node.get("key") or ""), 0),
            str(node.get("name") or node.get("key") or ""),
        ),
    )[:max_nodes]
    kept = {node.get("key") for node in ordered_nodes if node.get("key")}
    kept_links = [
        link
        for link in links
        if link.get("source") in kept and link.get("target") in kept
    ][:max_relationships]
    return {"nodes": ordered_nodes, "links": kept_links}


def _filter_graph(
    graph: dict[str, Any],
    *,
    node_types: list[str] | None = None,
    relationship_types: list[str] | None = None,
    include_bridge_nodes: bool = True,
    focus_keys: list[str] | None = None,
    max_nodes: int = 75,
    max_relationships: int = 200,
) -> dict[str, Any]:
    deduped = _dedupe_graph(graph)
    allowed_nodes = {item.lower() for item in (node_types or []) if item}
    allowed_rels = {item.upper() for item in (relationship_types or []) if item}
    focus = set(focus_keys or [])

    all_nodes = as_dict_list(deduped.get("nodes"))
    all_links = as_dict_list(deduped.get("links"))
    initial_keys = {
        node.get("key")
        for node in all_nodes
        if node.get("key")
        and (not allowed_nodes or str(node.get("type") or "").lower() in allowed_nodes or node.get("key") in focus)
    }
    links = [
        link
        for link in all_links
        if not allowed_rels or str(link.get("type") or "").upper() in allowed_rels
    ]

    if include_bridge_nodes and allowed_nodes:
        kept_keys = set(initial_keys)
        for link in links:
            source = link.get("source")
            target = link.get("target")
            if source in initial_keys or target in initial_keys:
                if source:
                    kept_keys.add(source)
                if target:
                    kept_keys.add(target)
    else:
        kept_keys = set(initial_keys)

    filtered = {
        "nodes": [node for node in all_nodes if node.get("key") in kept_keys],
        "links": [
            link
            for link in links
            if link.get("source") in kept_keys and link.get("target") in kept_keys
        ],
    }
    return _limit_graph(
        filtered,
        max_nodes=max_nodes,
        max_relationships=max_relationships,
        focus_keys=focus_keys,
    )


def _query_nodes_graph(case_id: str, node_keys: list[str] | None, node_types: list[str] | None, limit: int) -> dict[str, Any]:
    with driver.session(default_access_mode=READ_ACCESS) as session:
        rows = session.run(
            """
            MATCH (n)
            WHERE n.case_id = $case_id
              AND (size($node_keys) = 0 OR n.key IN $node_keys)
              AND (size($node_types) = 0 OR labels(n)[0] IN $node_types)
            RETURN n.id AS id, n.key AS key, n.name AS name, labels(n)[0] AS type,
                   n.summary AS summary, n.date AS date, n.amount AS amount,
                   properties(n) AS properties
            ORDER BY coalesce(n.date, ''), coalesce(n.name, n.key)
            LIMIT $limit
            """,
            case_id=case_id,
            node_keys=node_keys or [],
            node_types=node_types or [],
            limit=max(1, min(limit, 250)),
        )
        nodes = [_graph_node_map(dict(row)) for row in rows]
    return {"nodes": nodes, "links": []}


def _transaction_flow_graph(
    case_id: str,
    *,
    node_keys: list[str] | None,
    neighbor_types: list[str],
    relationship_types: list[str] | None,
    limit: int,
) -> dict[str, Any]:
    with driver.session(default_access_mode=READ_ACCESS) as session:
        rows = session.run(
            """
            MATCH (t:Transaction)
            WHERE t.case_id = $case_id
              AND (size($node_keys) = 0 OR t.key IN $node_keys)
            WITH t
            ORDER BY coalesce(t.date, ''), coalesce(t.name, t.key)
            LIMIT $limit
            OPTIONAL MATCH (t)-[r]-(n)
            WHERE r.case_id = $case_id
              AND n.case_id = $case_id
              AND (size($neighbor_types) = 0 OR labels(n)[0] IN $neighbor_types)
              AND (size($relationship_types) = 0 OR type(r) IN $relationship_types)
            RETURN collect(DISTINCT {
                id: t.id, key: t.key, name: t.name, type: labels(t)[0],
                summary: t.summary, date: t.date, amount: t.amount, properties: properties(t)
            }) AS transaction_nodes,
            collect(DISTINCT CASE WHEN n IS NULL THEN NULL ELSE {
                id: n.id, key: n.key, name: n.name, type: labels(n)[0],
                summary: n.summary, date: n.date, amount: n.amount, properties: properties(n)
            } END) AS neighbor_nodes,
            collect(DISTINCT CASE WHEN r IS NULL THEN NULL ELSE {
                source: startNode(r).key, target: endNode(r).key,
                type: type(r), properties: properties(r)
            } END) AS links
            """,
            case_id=case_id,
            node_keys=node_keys or [],
            neighbor_types=neighbor_types,
            relationship_types=relationship_types or [],
            limit=max(1, min(limit, 250)),
        )
        record = rows.single()
    if not record:
        return {"nodes": [], "links": []}
    return {
        "nodes": [item for item in [*(record["transaction_nodes"] or []), *(record["neighbor_nodes"] or [])] if item],
        "links": [item for item in (record["links"] or []) if item],
    }


def _shortest_path_graph(case_id: str, node_keys: list[str], max_depth: int) -> dict[str, Any]:
    if len(node_keys) < 2:
        return {"nodes": [], "links": []}
    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    for source_key, target_key in combinations(list(dict.fromkeys(node_keys))[:8], 2):
        for row in _find_paths(case_id, source_key, target_key, max_depth):
            nodes.extend(row.get("nodes") or [])
            links.extend(row.get("relationships") or [])
    return _dedupe_graph({"nodes": nodes, "links": links})


def make_agent_tools(context: AgentToolContext) -> list[StructuredTool]:
    def request_clarification(
        question: str,
        options: list[dict[str, Any]],
        allow_free_text: bool = True,
        reason: str | None = None,
    ) -> dict[str, Any]:
        raw_options = [
            option.model_dump() if isinstance(option, BaseModel) else option
            for option in options
            if isinstance(option, (dict, BaseModel))
        ]
        clarification = {
            "question": question,
            "options": [
                {
                    "id": str(option.get("id") or f"option_{index}"),
                    "label": str(option.get("label") or option.get("id") or f"Option {index}"),
                    "description": option.get("description"),
                }
                for index, option in enumerate(raw_options[:4], start=1)
            ],
            "allow_free_text": allow_free_text,
            "context": {"reason": reason or "agent_requested_clarification"},
        }
        return context.result(
            "request_clarification",
            {"clarification": clarification},
            summary=f"Requested clarification: {question}",
            artifact=None,
        ) | {"clarification": clarification}

    def get_case_overview() -> dict[str, Any]:
        summary = graph_service.get_graph_summary(context.case_id)
        compact = {
            "total_nodes": summary.get("total_nodes", 0),
            "total_relationships": summary.get("total_relationships", 0),
            "entity_types": summary.get("entity_types", {}),
            "relationship_types": summary.get("relationship_types", {}),
            "sample_entities": (summary.get("entities") or [])[:25],
        }
        return context.result(
            "get_case_overview",
            compact,
            summary=(
                f"Case has {compact['total_nodes']} nodes and "
                f"{compact['total_relationships']} relationships."
            ),
        )

    def search_graph_entities(query: str, limit: int = 10) -> dict[str, Any]:
        rows = graph_service.search_nodes(query=query, limit=limit, case_id=context.case_id)
        return context.result(
            "search_graph_entities",
            {"entities": rows, "count": len(rows)},
            summary=f"Found {len(rows)} graph entities matching '{query}'.",
        )

    def inspect_graph_schema(
        labels: list[str] | None = None,
        relationship_types: list[str] | None = None,
        sample_limit: int = 3,
    ) -> dict[str, Any]:
        schema = _inspect_graph_schema(
            context.case_id,
            labels=labels,
            relationship_types=relationship_types,
            sample_limit=sample_limit,
        )
        return context.result(
            "inspect_graph_schema",
            schema,
            summary=(
                f"Inspected {len(schema.get('labels') or {})} node label(s) and "
                f"{len(schema.get('relationships') or {})} relationship type(s)."
            ),
        )

    def get_entity_details(entity_key: str) -> dict[str, Any]:
        details = graph_service.get_node_details(entity_key, case_id=context.case_id)
        return context.result(
            "get_entity_details",
            {"entity": details},
            summary=(f"Loaded details for {entity_key}." if details else f"No entity found for key {entity_key}."),
        )

    def get_entity_neighborhood(entity_key: str, depth: int = 1) -> dict[str, Any]:
        graph = graph_service.get_node_with_neighbours(entity_key, depth=depth, case_id=context.case_id)
        return context.result(
            "get_entity_neighborhood",
            graph,
            summary=f"Loaded {_graph_counts(graph)} around {entity_key}.",
        )

    def find_paths_between_entities(source_key: str, target_key: str, max_depth: int = 4) -> dict[str, Any]:
        paths = _find_paths(context.case_id, source_key, target_key, max_depth)
        return context.result(
            "find_paths_between_entities",
            {"paths": paths, "count": len(paths)},
            summary=f"Found {len(paths)} shortest path(s) between {source_key} and {target_key}.",
        )

    def search_documents(query: str, limit: int = 8) -> dict[str, Any]:
        from services.vector_db_service import get_vector_db_health

        health = get_vector_db_health()
        vector_db = get_vector_db_service()
        if vector_db is None:
            reason = health.get("reason") or "Vector document search is not configured."
            return context.result(
                "search_documents",
                {"available": False, "health": health, "chunks": []},
                summary=f"Vector document search is unavailable: {reason}",
                status="error",
                error=str(reason),
            )
        from services.embedding_service import embedding_service
        if embedding_service is None:
            return context.result(
                "search_documents",
                {"available": False, "health": health, "chunks": []},
                summary="Vector document search is unavailable: embedding service is not configured.",
                status="error",
                error="Embedding service is not configured.",
            )

        embedding = embedding_service.generate_embedding(query)
        chunks = vector_db.search_chunks(
            embedding,
            top_k=limit,
            filter_metadata={"case_id": context.case_id},
        )
        compact = [
            {
                "id": chunk.get("id"),
                "text": truncate_text(chunk.get("text"), 1200),
                "metadata": chunk.get("metadata") or {},
                "distance": chunk.get("distance"),
            }
            for chunk in chunks
        ]
        return context.result(
            "search_documents",
            {"available": True, "health": health, "chunks": compact, "count": len(compact)},
            summary=f"Found {len(compact)} semantically similar document chunk(s).",
        )

    def run_cypher(query: str, params: dict[str, Any] | None = None, limit: int = 50) -> dict[str, Any]:
        repaired = repair_common_cypher(query)
        used_repair = repaired != query.strip()
        rows = run_readonly_cypher(repaired, case_id=context.case_id, params=params, limit=limit)
        return context.result(
            "run_readonly_cypher",
            {"rows": rows, "count": len(rows), "query": repaired, "repaired": used_repair},
            summary=(
                f"Read-only Cypher returned {len(rows)} row(s)"
                + (" after applying a safe syntax repair." if used_repair else ".")
            ),
        )

    def get_timeline_events(
        event_types: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 25,
    ) -> dict[str, Any]:
        page = timeline_service.get_timeline_page(
            event_types=event_types,
            start_date=start_date,
            end_date=end_date,
            case_id=context.case_id,
            limit=limit,
        )
        return context.result(
            "get_timeline_events",
            page,
            summary=f"Loaded {page.get('count', 0)} timeline event(s).",
        )

    def get_financial_transactions(
        entity_keys: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        categories: list[str] | None = None,
        mode: Literal["transactions", "intelligence"] = "transactions",
        limit: int = 25,
    ) -> dict[str, Any]:
        data = financial_service.get_financial_transactions(
            case_id=context.case_id,
            start_date=start_date,
            end_date=end_date,
            categories=categories,
            mode=mode,
        )
        transactions = _filter_transactions(
            data.get("transactions") or [],
            entity_keys=entity_keys,
            limit=limit,
        )
        result = {**data, "transactions": transactions, "returned": len(transactions)}
        return context.result(
            "get_financial_transactions",
            result,
            summary=f"Loaded {len(transactions)} financial record(s).",
        )

    def get_map_locations(
        entity_types: list[str] | None = None,
        entity_keys: list[str] | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        locations = geo_service.get_entities_with_locations(entity_types=entity_types, case_id=context.case_id)
        keys = set(entity_keys or [])
        if keys:
            locations = [location for location in locations if location.get("key") in keys]
        locations = locations[:limit]
        return context.result(
            "get_map_locations",
            {"locations": locations, "count": len(locations)},
            summary=f"Loaded {len(locations)} mapped location(s).",
        )

    def build_graph_artifact(
        node_keys: list[str] | None = None,
        title: str | None = None,
        depth: int = 1,
        mode: Literal[
            "entity_neighborhood",
            "transaction_only",
            "transactions_plus_accounts",
            "transaction_flow",
            "shortest_paths",
        ] = "entity_neighborhood",
        node_types: list[str] | None = None,
        relationship_types: list[str] | None = None,
        max_nodes: int = 75,
        max_relationships: int = 200,
        include_bridge_nodes: bool = True,
    ) -> dict[str, Any]:
        keys = list(dict.fromkeys(node_keys or []))
        if mode == "transaction_only":
            graph = _query_nodes_graph(
                context.case_id,
                keys,
                ["Transaction"],
                max_nodes,
            )
        elif mode == "transactions_plus_accounts":
            graph = _transaction_flow_graph(
                context.case_id,
                node_keys=keys,
                neighbor_types=["Account"],
                relationship_types=relationship_types,
                limit=max_nodes,
            )
        elif mode == "transaction_flow":
            graph = _transaction_flow_graph(
                context.case_id,
                node_keys=keys,
                neighbor_types=node_types or ["Account", "Organization", "Person"],
                relationship_types=relationship_types,
                limit=max_nodes,
            )
        elif mode == "shortest_paths":
            graph = _shortest_path_graph(context.case_id, keys, max(1, depth or 1))
        elif keys and depth > 0:
            graph = graph_service.expand_nodes(keys, depth=depth, case_id=context.case_id)
        elif keys:
            context_rows = graph_service.get_context_for_nodes(keys, context.case_id).get("selected_entities") or []
            graph = {"nodes": context_rows, "links": []}
        else:
            graph = graph_service.get_graph_structure(context.case_id, limit=max_nodes, sort_by="degree")
        if mode != "transaction_only":
            graph = _filter_graph(
                graph,
                node_types=node_types,
                relationship_types=relationship_types,
                include_bridge_nodes=include_bridge_nodes,
                focus_keys=keys,
                max_nodes=max_nodes,
                max_relationships=max_relationships,
            )
        graph = _compact_graph(graph)
        artifact = _artifact(
            "graph",
            title or "Agent graph",
            graph,
            {
                "mode": mode,
                "depth": depth,
                "node_count": len(graph.get("nodes") or []),
                "relationship_count": len(graph.get("links") or []),
                "node_types": node_types or [],
                "relationship_types": relationship_types or [],
                "max_nodes": max_nodes,
                "max_relationships": max_relationships,
                "include_bridge_nodes": include_bridge_nodes,
            },
        )
        return context.result(
            "build_graph_artifact",
            {"artifact_id": artifact["id"], "summary": artifact["metadata"]},
            summary=f"Built graph artifact with {_graph_counts(graph)}.",
            artifact=artifact,
        )

    def build_table_artifact(query: str, title: str | None = None, params: dict[str, Any] | None = None, limit: int = 50) -> dict[str, Any]:
        repaired = repair_common_cypher(query)
        rows = run_readonly_cypher(repaired, case_id=context.case_id, params=params, limit=limit)
        rows = _enrich_table_rows_with_entity_names(context.case_id, rows)
        artifact = _artifact(
            "table",
            title or "Agent table",
            {"columns": _columns_from_rows(rows), "rows": rows},
            {"row_count": len(rows), "query": repaired, "repaired": repaired != query.strip()},
        )
        return context.result(
            "build_table_artifact",
            {"artifact_id": artifact["id"], "row_count": len(rows)},
            summary=f"Built table artifact with {len(rows)} row(s).",
            artifact=artifact,
        )

    def build_table_artifact_from_rows(
        rows: list[dict[str, Any]],
        title: str | None = None,
        columns: list[TableColumnArgs] | None = None,
        source_result_ids: list[str] | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        try:
            normalized_columns, normalized_rows = _normalize_direct_table(
                rows=rows,
                columns=columns or [],
            )
        except ValueError as exc:
            return context.result(
                "build_table_artifact_from_rows",
                {"error": str(exc), "row_count": len(rows or [])},
                summary=f"Direct table artifact rejected: {exc}",
                status="error",
                error=str(exc),
            )

        metadata = {
            "row_count": len(normalized_rows),
            "direct_rows": True,
            "source_result_ids": list(source_result_ids or [])[:20],
        }
        if notes:
            metadata["notes"] = truncate_text(notes, 1000)

        artifact = _artifact(
            "table",
            title or "Agent table",
            {"columns": normalized_columns, "rows": normalized_rows},
            metadata,
        )
        return context.result(
            "build_table_artifact_from_rows",
            {"artifact_id": artifact["id"], "row_count": len(normalized_rows)},
            summary=f"Built table artifact from {len(normalized_rows)} provided row(s).",
            artifact=artifact,
        )

    def build_chart_artifact(
        title: str,
        chart_type: ChartType,
        rows: list[dict[str, Any]],
        x_key: str | None = None,
        y_keys: list[str] | None = None,
        category_key: str | None = None,
        value_key: str | None = None,
        series: list[ChartSeriesArgs] | None = None,
        x_label: str | None = None,
        y_label: str | None = None,
        notes: str | None = None,
        source_result_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        try:
            normalized = _normalize_chart_artifact(
                chart_type=chart_type,
                rows=rows,
                x_key=x_key,
                y_keys=y_keys,
                category_key=category_key,
                value_key=value_key,
                series=series,
            )
        except ValueError as exc:
            return context.result(
                "build_chart_artifact",
                {"error": str(exc), "row_count": len(rows or [])},
                summary=f"Chart artifact rejected: {exc}",
                status="error",
                error=str(exc),
            )

        row_count = len(normalized["rows"])
        artifact = _artifact(
            "chart",
            title,
            {
                "chart_type": chart_type,
                "rows": normalized["rows"],
                "columns": normalized["columns"],
                "x_key": normalized["x_key"],
                "y_keys": normalized["y_keys"],
                "category_key": normalized["category_key"],
                "value_key": normalized["value_key"],
                "series": normalized["series"],
                "x_label": truncate_text(x_label, 120) if x_label else "",
                "y_label": truncate_text(y_label, 120) if y_label else "",
                "notes": truncate_text(notes, 1000) if notes else "",
            },
            {
                "row_count": row_count,
                "chart_type": chart_type,
                "source_result_ids": list(source_result_ids or [])[:20],
                "direct_rows": True,
            },
        )
        return context.result(
            "build_chart_artifact",
            {
                "artifact_id": artifact["id"],
                "chart_type": chart_type,
                "row_count": row_count,
                "series_count": len(normalized["series"]),
            },
            summary=f"Built {chart_type.replace('_', ' ')} chart artifact with {row_count} row(s).",
            artifact=artifact,
        )

    def build_report_artifact(
        title: str,
        purpose: str,
        report_scope: str,
        included_items: list[str],
        sections: list[ReportSectionArgs],
        audience: str | None = None,
        source_result_ids: list[str] | None = None,
        open_questions: list[str] | None = None,
        revision_note: str | None = None,
    ) -> dict[str, Any]:
        normalized_sections, embedded_artifacts = _normalize_report_sections(context, sections)
        clean_included = [truncate_text(item, 300) for item in included_items if str(item).strip()]
        if not clean_included:
            return context.result(
                "build_report_artifact",
                {"error": "Report must include at least one clearly specified included item."},
                summary="Report artifact rejected: included_items is required.",
                status="error",
                error="Report must include at least one clearly specified included item.",
            )

        artifact = _artifact(
            "report",
            title,
            {
                "title": truncate_text(title, 160),
                "purpose": truncate_text(purpose, 1000),
                "audience": truncate_text(audience, 300) if audience else "",
                "scope": truncate_text(report_scope, 1500),
                "included_items": clean_included,
                "sections": normalized_sections,
                "embedded_artifacts": embedded_artifacts,
                "open_questions": [truncate_text(item, 300) for item in (open_questions or []) if str(item).strip()],
            },
            {
                "section_count": len(normalized_sections),
                "embedded_artifact_count": len(embedded_artifacts),
                "source_result_ids": list(source_result_ids or [])[:30],
                "revision_note": truncate_text(revision_note, 1000) if revision_note else "",
                "status": "draft",
            },
        )
        return context.result(
            "build_report_artifact",
            {
                "artifact_id": artifact["id"],
                "section_count": len(normalized_sections),
                "embedded_artifact_count": len(embedded_artifacts),
            },
            summary=(
                f"Built report artifact with {len(normalized_sections)} section(s) "
                f"and {len(embedded_artifacts)} embedded artifact(s)."
            ),
            artifact=artifact,
        )

    def build_map_artifact(
        title: str | None = None,
        entity_keys: list[str] | None = None,
        entity_types: list[str] | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        locations = geo_service.get_entities_with_locations(entity_types=entity_types, case_id=context.case_id)
        keys = set(entity_keys or [])
        if keys:
            locations = [location for location in locations if location.get("key") in keys]
        locations = locations[:limit]
        artifact = _artifact(
            "map",
            title or "Agent map",
            {"locations": locations},
            {"location_count": len(locations)},
        )
        return context.result(
            "build_map_artifact",
            {"artifact_id": artifact["id"], "location_count": len(locations)},
            summary=f"Built map artifact with {len(locations)} location(s).",
            artifact=artifact,
        )

    def wrap(func, *, name: str, description: str, args_schema: type[BaseModel]):
        def guarded(**kwargs):
            try:
                return func(**kwargs)
            except UnsafeCypherError as exc:
                return context.result(
                    name,
                    {"error": str(exc)},
                    summary=f"{name} rejected an unsafe Cypher query.",
                    status="error",
                    error=str(exc),
                )

        return StructuredTool.from_function(
            func=guarded,
            name=name,
            description=description,
            args_schema=args_schema,
        )

    return [
        StructuredTool.from_function(
            func=request_clarification,
            name="request_clarification",
            description=(
                "Pause and ask the user a clarification question with 2-4 answer options when a request is ambiguous. "
                "Use before building an artifact if two plausible interpretations would produce meaningfully different outputs."
            ),
            args_schema=ClarificationArgs,
        ),
        StructuredTool.from_function(
            func=get_case_overview,
            name="get_case_overview",
            description="Get case-level graph counts, available entity types, relationship types, and sample entities.",
            args_schema=EmptyArgs,
        ),
        wrap(
            search_graph_entities,
            name="search_graph_entities",
            description="Search graph entities by display name, key, summary, notes, or alias-like text.",
            args_schema=SearchGraphEntitiesArgs,
        ),
        wrap(
            inspect_graph_schema,
            name="inspect_graph_schema",
            description=(
                "Inspect the actual case-scoped Neo4j labels, relationship types, available properties, "
                "property presence counts, and sample values. Use before writing custom Cypher for a label "
                "or property shape you have not already inspected in this run."
            ),
            args_schema=InspectGraphSchemaArgs,
        ),
        wrap(
            get_entity_details,
            name="get_entity_details",
            description="Load detailed information and immediate connections for one exact graph entity key.",
            args_schema=EntityKeyArgs,
        ),
        wrap(
            get_entity_neighborhood,
            name="get_entity_neighborhood",
            description="Load a graph neighborhood around one exact entity key.",
            args_schema=EntityNeighborhoodArgs,
        ),
        wrap(
            find_paths_between_entities,
            name="find_paths_between_entities",
            description="Find shortest case-scoped relationship paths between two exact entity keys.",
            args_schema=PathArgs,
        ),
        wrap(
            search_documents,
            name="search_documents",
            description="Semantic search over ingested document chunks for the current case.",
            args_schema=SearchDocumentsArgs,
        ),
        wrap(
            run_cypher,
            name="run_readonly_cypher",
            description=(
                "Run a strictly read-only, case-scoped Neo4j Cypher query. Scope real nodes or relationships "
                "with .case_id = $case_id, put ORDER BY after RETURN, avoid NULLS FIRST/LAST, and use numeric LIMITs."
            ),
            args_schema=ReadonlyCypherArgs,
        ),
        wrap(
            get_timeline_events,
            name="get_timeline_events",
            description="Retrieve chronological events from the current case.",
            args_schema=TimelineArgs,
        ),
        wrap(
            get_financial_transactions,
            name="get_financial_transactions",
            description="Retrieve financial transaction or intelligence records, optionally focused on entity keys.",
            args_schema=FinancialArgs,
        ),
        wrap(
            get_map_locations,
            name="get_map_locations",
            description="Retrieve geocoded case entities for map reasoning.",
            args_schema=MapArgs,
        ),
        wrap(
            build_graph_artifact,
            name="build_graph_artifact",
            description=(
                "Create a focused graph artifact. Supports modes: entity_neighborhood, transaction_only, "
                "transactions_plus_accounts, transaction_flow, and shortest_paths. Use node/relationship filters "
                "and size caps to match the user's requested scope exactly."
            ),
            args_schema=GraphArtifactArgs,
        ),
        wrap(
            build_table_artifact,
            name="build_table_artifact",
            description=(
                "Create a mini table artifact from a safe read-only Cypher query. Use this for database-backed "
                "tables where rows should come directly from Neo4j."
            ),
            args_schema=TableArtifactArgs,
        ),
        wrap(
            build_table_artifact_from_rows,
            name="build_table_artifact_from_rows",
            description=(
                "Create a table artifact directly from rows you have synthesized from prior tool evidence. "
                "Use for analytical tables such as ranked contradictions, witness matrices, issue lists, "
                "or other findings that are not a single database query. Values must be scalar."
            ),
            args_schema=DirectTableArtifactArgs,
        ),
        wrap(
            build_chart_artifact,
            name="build_chart_artifact",
            description=(
                "Create a chart artifact directly from rows you have synthesized from prior tool evidence. "
                "Supports bar, stacked_bar, line, area, pie, donut, and scatter charts. Use for comparisons, "
                "distributions, trends over time, transaction volumes, severity counts, and other numeric summaries."
            ),
            args_schema=ChartArtifactArgs,
        ),
        wrap(
            build_report_artifact,
            name="build_report_artifact",
            description=(
                "Create a report artifact from clearly agreed report scope, purpose, included items, and sections. "
                "Use only after the user has specified what should be included or after you have asked clarifying "
                "questions until the report scope is clear. Sections may embed graph, table, or chart artifacts by artifact_id."
            ),
            args_schema=ReportArtifactArgs,
        ),
        wrap(
            build_map_artifact,
            name="build_map_artifact",
            description="Create a mini map artifact for display in the Agent workspace.",
            args_schema=MapArtifactArgs,
        ),
    ]
