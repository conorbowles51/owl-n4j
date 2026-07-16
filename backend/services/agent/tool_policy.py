from __future__ import annotations

import hashlib
import json
from typing import Any, Literal


ToolRiskTier = Literal["read_only", "expensive", "mutation"]

READ_ONLY_TOOL_NAMES = frozenset(
    {
        "request_clarification",
        "get_case_overview",
        "search_graph_entities",
        "inspect_graph_schema",
        "get_entity_details",
        "get_entity_neighborhood",
        "find_paths_between_entities",
        "search_documents",
        "run_readonly_cypher",
        "get_timeline_events",
        "get_financial_transactions",
        "get_map_locations",
        "build_graph_artifact",
        "build_table_artifact",
        "build_table_artifact_from_rows",
        "build_chart_artifact",
        "build_report_artifact",
        "build_map_artifact",
    }
)

EXPENSIVE_TOOL_NAMES = frozenset()


def tier_for_tool(name: str | None) -> ToolRiskTier:
    if name in READ_ONLY_TOOL_NAMES:
        return "read_only"
    if name in EXPENSIVE_TOOL_NAMES:
        return "expensive"
    return "mutation"


def requires_confirmation(name: str | None) -> bool:
    return tier_for_tool(name) != "read_only"


def tool_call_signature(name: str | None, args: dict[str, Any] | None) -> str:
    payload = {
        "name": name or "unknown",
        "args": args or {},
    }
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
