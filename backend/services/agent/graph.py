from __future__ import annotations

import json
import operator
import re
import time
import uuid
from typing import Annotated, Any, TypedDict
from collections.abc import Callable

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph, add_messages

from config import OPENAI_API_KEY
from services.agent.json_utils import to_jsonable, truncate_payload, truncate_text
from services.agent.tools import AgentToolContext, make_agent_tools


class AgentRunCancelled(Exception):
    """Raised when an in-flight agent run is cancelled by the caller."""


def message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(part for part in parts if part).strip()
    return str(content or "")


def _merge_dict(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(left or {})
    merged.update(right or {})
    return merged


def _artifact_store_from_available(available_artifacts: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    store: dict[str, dict[str, Any]] = {}
    for artifact in available_artifacts or []:
        if not isinstance(artifact, dict):
            continue
        artifact_id = str(artifact.get("id") or "")
        if artifact_id:
            store[artifact_id] = to_jsonable(artifact)
    return store


def _format_available_artifacts(available_artifacts: list[dict[str, Any]] | None) -> str:
    rows: list[str] = []
    for artifact in (available_artifacts or [])[-8:]:
        if not isinstance(artifact, dict):
            continue
        artifact_id = str(artifact.get("id") or "")
        artifact_type = str(artifact.get("type") or "artifact")
        title = str(artifact.get("title") or "Untitled artifact")
        if artifact_id:
            rows.append(f"- {artifact_id} ({artifact_type}): {title}")
    if not rows:
        return "No previous artifacts are available in this thread yet."
    return "\n".join(rows)


def _messages_without_dangling_tool_calls(messages: list[AnyMessage]) -> list[AnyMessage]:
    if not messages:
        return messages
    last_message = messages[-1]
    if isinstance(last_message, AIMessage) and (getattr(last_message, "tool_calls", []) or []):
        return messages[:-1]
    return messages


_TOOL_PLANNING_RE = re.compile(
    r"\b(i['’]?ll|i will|i am going to|i’m going to|i'm going to|let me)\s+"
    r"(run|query|search|use|call|execute|build|inspect)\b",
    re.IGNORECASE,
)

_INTERNAL_TOOL_MARKERS = (
    "to=functions.",
    "functions.",
    "run_readonly_cypher",
    "search_graph_entities",
    "inspect_graph_schema",
    "get_entity_details",
    "get_entity_neighborhood",
    "find_paths_between_entities",
    "search_documents",
    "build_graph_artifact",
    "build_table_artifact",
    "build_table_artifact_from_rows",
    "build_chart_artifact",
    "build_report_artifact",
    "build_map_artifact",
    "request_clarification",
)

_FINAL_ANSWER_SYSTEM_PROMPT = (
    "Write the final answer from the completed tool results. "
    "Be concise, do not call tools, and mention any artifacts created. "
    "Do not expose internal tool names, tool-call syntax, Cypher implementation details, or messages like "
    "'I will run a query'. "
    "If the previous assistant turn requested more tools than the run budget allowed, ignore that unexecuted "
    "request and summarize only the completed tool results. "
    "If CSV export is relevant, refer to the artifact CSV button; do not claim a file is attached."
)


def _looks_like_tool_planning_text(text: str) -> bool:
    normalized = " ".join((text or "").strip().split())
    if not normalized:
        return False
    lowered = normalized.lower()
    if any(marker in lowered for marker in _INTERNAL_TOOL_MARKERS):
        return True
    if "running cypher" in lowered or "running query" in lowered:
        return True
    return bool(_TOOL_PLANNING_RE.search(normalized))


def _arg_text(args: dict[str, Any], key: str, *, max_chars: int = 90) -> str | None:
    value = args.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return truncate_text(stripped, max_chars) if stripped else None
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def _arg_list_text(args: dict[str, Any], key: str, *, max_items: int = 3) -> str | None:
    value = args.get(key)
    if not isinstance(value, list):
        return None
    items = [str(item).strip() for item in value if str(item).strip()]
    if not items:
        return None
    visible = items[:max_items]
    suffix = f" and {len(items) - len(visible)} more" if len(items) > len(visible) else ""
    return ", ".join(visible) + suffix


def _quoted(value: str | None) -> str:
    if not value:
        return ""
    return f'"{value}"'


def activity_for_tool_call(name: str | None, args: dict[str, Any] | None, call_id: str | None) -> dict[str, Any]:
    """Create a safe, user-visible activity note from a selected tool call."""
    safe_name = name or "unknown"
    safe_args = args or {}
    activity_id = call_id or f"activity_{uuid.uuid4().hex[:12]}"
    title = "Used agent tool"
    detail = "I'm gathering case context before answering."

    if safe_name == "get_case_overview":
        title = "Checked the case overview"
        detail = "I need the case size and available entity types before narrowing the search."
    elif safe_name == "search_graph_entities":
        query = _arg_text(safe_args, "query")
        title = f"Searched the graph for {_quoted(query)}" if query else "Searched the graph"
        detail = "I'm finding matching entities before expanding their relationships."
    elif safe_name == "inspect_graph_schema":
        labels = _arg_list_text(safe_args, "labels")
        rels = _arg_list_text(safe_args, "relationship_types")
        title = "Inspected available graph fields"
        if labels and rels:
            detail = f"I need fields for {labels} and relationships like {rels} before writing Cypher."
        elif labels:
            detail = f"I need available fields for {labels} before writing Cypher."
        elif rels:
            detail = f"I need relationship fields for {rels} before writing Cypher."
        else:
            detail = "I need to inspect available fields before writing Cypher."
    elif safe_name == "get_entity_details":
        key = _arg_text(safe_args, "entity_key")
        title = f"Loaded entity details for {_quoted(key)}" if key else "Loaded entity details"
        detail = "I'm checking the entity's verified fields and direct context."
    elif safe_name == "get_entity_neighborhood":
        key = _arg_text(safe_args, "entity_key")
        title = f"Loaded graph neighborhood for {_quoted(key)}" if key else "Loaded a graph neighborhood"
        detail = "I'm expanding nearby nodes and relationships to see the local context."
    elif safe_name == "find_paths_between_entities":
        source = _arg_text(safe_args, "source_key")
        target = _arg_text(safe_args, "target_key")
        title = (
            f"Looked for paths between {_quoted(source)} and {_quoted(target)}"
            if source or target
            else "Looked for relationship paths"
        )
        detail = "I'm checking how these entities connect inside the case graph."
    elif safe_name == "search_documents":
        query = _arg_text(safe_args, "query")
        title = f"Searched documents for {_quoted(query)}" if query else "Searched documents"
        detail = "I'm looking for source text and citations that support the answer."
    elif safe_name == "run_readonly_cypher":
        title = "Queried graph data"
        detail = "I'm running a safe read-only Cypher query scoped to this case."
    elif safe_name == "get_timeline_events":
        title = "Loaded chronological case events"
        detail = "I'm gathering dated events so the answer can be ordered in time."
    elif safe_name == "get_financial_records":
        title = "Loaded financial records"
        detail = "I'm checking transactions and financial intelligence linked to the request."
    elif safe_name == "get_map_locations":
        title = "Loaded map locations"
        detail = "I'm checking geocoded entities that can support a map view."
    elif safe_name == "build_graph_artifact":
        title_arg = _arg_text(safe_args, "title")
        mode = _arg_text(safe_args, "mode")
        title = f"Built graph view {_quoted(title_arg)}" if title_arg else "Built a graph view"
        detail = f"I'm assembling the focused graph artifact using {mode or 'the selected'} scope."
    elif safe_name == "build_table_artifact":
        title_arg = _arg_text(safe_args, "title")
        title = f"Built table {_quoted(title_arg)}" if title_arg else "Built a table from graph data"
        detail = "I'm turning the Cypher results into a table artifact."
    elif safe_name == "build_table_artifact_from_rows":
        title_arg = _arg_text(safe_args, "title")
        title = f"Built table {_quoted(title_arg)}" if title_arg else "Built a table from analyzed findings"
        detail = "I'm structuring the findings into rows the workspace can export."
    elif safe_name == "build_chart_artifact":
        title_arg = _arg_text(safe_args, "title")
        chart_type = _arg_text(safe_args, "chart_type")
        chart_label = f"{chart_type} chart" if chart_type else "chart"
        title = f"Built {chart_label} {_quoted(title_arg)}" if title_arg else f"Built a {chart_label}"
        detail = "I'm turning the numeric summary into a chart artifact."
    elif safe_name == "build_report_artifact":
        title_arg = _arg_text(safe_args, "title")
        title = f"Built report {_quoted(title_arg)}" if title_arg else "Built a report artifact"
        detail = "I'm composing the selected findings and embedded views into a report."
    elif safe_name == "build_map_artifact":
        title_arg = _arg_text(safe_args, "title")
        title = f"Built map {_quoted(title_arg)}" if title_arg else "Built a map view"
        detail = "I'm assembling the relevant locations into a focused map artifact."
    elif safe_name == "request_clarification":
        question = _arg_text(safe_args, "question", max_chars=140)
        title = "Asked for clarification"
        detail = question or "I need the user to choose a scope before continuing."

    return {
        "id": activity_id,
        "tool_name": safe_name,
        "phase": "plan",
        "status": "running",
        "title": title,
        "detail": detail,
    }


def activity_for_tool_result(item: dict[str, Any]) -> dict[str, Any]:
    activity = dict(item.get("activity") or {})
    if not activity:
        activity = activity_for_tool_call(item.get("name"), item.get("arguments") or {}, item.get("id"))
    activity["id"] = item.get("id") or activity.get("id") or f"activity_{uuid.uuid4().hex[:12]}"
    activity["phase"] = "result"
    activity["status"] = item.get("status") or "error"
    activity["duration_ms"] = int(item.get("duration_ms") or 0)
    if item.get("error"):
        activity["result_detail"] = str(item.get("error"))
    elif item.get("summary"):
        activity["result_detail"] = str(item.get("summary"))
    else:
        activity["result_detail"] = "Completed."
    return activity


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    case_id: str
    artifact_preference: str
    case_context: dict[str, Any]
    max_tool_calls: int
    tool_iterations: int
    tool_trace: Annotated[list[dict[str, Any]], operator.add]
    tool_results: Annotated[dict[str, Any], _merge_dict]
    artifacts: Annotated[list[dict[str, Any]], operator.add]
    clarifications: Annotated[list[dict[str, Any]], operator.add]
    final_answer: str


def _used_tools(state: AgentState) -> bool:
    return int(state.get("tool_iterations") or 0) > 0 or bool(state.get("tool_trace"))


def _last_message_wants_more_tools(state: AgentState) -> bool:
    messages = state.get("messages") or []
    if not messages:
        return False
    last_message = messages[-1]
    tool_calls = getattr(last_message, "tool_calls", []) or []
    if tool_calls:
        return True
    if isinstance(last_message, AIMessage):
        return _looks_like_tool_planning_text(message_content_to_text(last_message.content))
    return False


def _tool_budget_exhausted(state: AgentState) -> bool:
    max_tool_calls = int(state.get("max_tool_calls") or 0)
    if max_tool_calls <= 0:
        return False
    return int(state.get("tool_iterations") or 0) >= max_tool_calls and _last_message_wants_more_tools(state)


def _messages_for_finalizer(state: AgentState) -> list[AnyMessage]:
    messages = _messages_without_dangling_tool_calls(state.get("messages") or [])
    if not messages:
        return messages
    last_message = messages[-1]
    if (
        _tool_budget_exhausted(state)
        and isinstance(last_message, AIMessage)
        and _looks_like_tool_planning_text(message_content_to_text(last_message.content))
    ):
        return messages[:-1]
    return messages


def _budget_continuation_clarification(max_tool_calls: int) -> dict[str, Any]:
    return {
        "question": "I reached the investigation step limit before I could finish cleanly. Would you like me to continue?",
        "options": [
            {
                "id": "continue",
                "label": "Continue",
                "description": "Continues the same investigation with a fresh tool-step budget.",
            },
            {
                "id": "stop",
                "label": "Stop here",
                "description": "Leave the current artifacts and findings as they are.",
            },
        ],
        "allow_free_text": True,
        "context": {
            "reason": "tool_budget_exhausted",
            "max_tool_calls": max_tool_calls,
        },
    }


class AgentGraphRunner:
    def __init__(self, *, provider: str, model_id: str):
        if provider != "openai":
            raise ValueError("Agent mode currently requires the OpenAI provider for reliable tool calling")
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required for Agent mode")

        self.provider = provider
        self.model_id = model_id
        self.base_model = ChatOpenAI(
            model=model_id,
            api_key=OPENAI_API_KEY,
            timeout=180,
            max_retries=2,
            use_responses_api=True,
        )

    def invoke(
        self,
        *,
        case_id: str,
        messages: list[HumanMessage | AIMessage],
        artifact_preference: str = "auto",
        max_tool_calls: int = 28,
        thread_id: str | None = None,
        available_artifacts: list[dict[str, Any]] | None = None,
        allowed_entity_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        available_artifact_context = _format_available_artifacts(available_artifacts)
        tool_context = AgentToolContext(
            case_id=case_id,
            artifact_preference=artifact_preference,
            allowed_entity_keys=(set(allowed_entity_keys) if allowed_entity_keys is not None else None),
            artifact_store=_artifact_store_from_available(available_artifacts),
        )
        tools = make_agent_tools(tool_context)
        tools_by_name = {tool.name: tool for tool in tools}
        model_with_tools = self.base_model.bind_tools(tools)

        def build_system_prompt(state: AgentState) -> str:
            return f"""You are the OWL AI Agent, an investigative graph analyst.

You are working inside one case only. Every tool is already scoped to case_id={case_id}.
{"You are additionally restricted to the Significant layer. Use only its entities and relationships between those entities; do not infer from or request case-wide data." if allowed_entity_keys is not None else "You may use the full case dataset."}

Your job:
- Answer investigation questions using tools instead of guessing.
- Search the graph when the user asks about people, companies, events, relationships, timelines, locations, or transactions.
- Search documents when the answer needs source text, document excerpts, or semantic context.
- Use run_readonly_cypher for precise graph questions that need counts, filters, paths, or custom tables.
- Use inspect_graph_schema before writing custom Cypher for labels or properties you have not already inspected in this run.
- For human-readable entity names in Cypher, prefer coalesce(n.name, n.display_name, n.full_name, n.title, n.key); do not assume display_name exists.
- If the user asks for a graph, map, table, chart, or report view, build the matching artifact.
- Use build_table_artifact for query-backed tables where rows come directly from Neo4j.
- Use build_table_artifact_from_rows for synthesized analytical tables you have already reasoned out from tool evidence, such as ranked contradictions, witness matrices, issue lists, or source comparison tables.
- Use build_chart_artifact for numeric summaries, distributions, rankings, comparisons, trends, and proportions. Pick bar/stacked_bar, line/area, pie/donut, or scatter according to the user's wording and the data shape.
- Do not encode hand-built analytical rows as Cypher UNWIND just to create a table artifact.
- For report requests, do not build the report until the user has clearly specified the purpose, scope, and what should be included. If any of those are unclear, use request_clarification.
- When useful for a report, offer to embed graph, table, or chart artifacts, or create and embed them yourself when they materially support the report.
- Build reports with build_report_artifact. Treat follow-ups as revisions of the previous report artifact and explain what changed.
- If the user asks for a timeline, chronology, transaction list, or financial table, build a table artifact with useful date, amount, entity, and reasoning columns.
- For graph requests, first use search_graph_entities, inspect_graph_schema, or run_readonly_cypher to identify the exact node keys and relationship context that belong in the graph.
- Prefer build_graph_artifact in selected_subgraph mode with node_keys, source_result_ids, or a graph query. The graph builder can materialize nodes/relationships from prior Cypher results, key columns, or graph-shaped rows.
- Use specialized graph modes only as convenience fallbacks: transaction_only for only Transaction nodes, shortest_paths for connective tissue between named nodes, and entity_neighborhood for broad expansion.
- If build_graph_artifact returns zero nodes, do not immediately ask the user. Search or query for the right node keys, inspect available fields if needed, then retry with selected_subgraph.
- If the graph request is ambiguous and the difference changes meaning, ask a clarifying question before building.
- Use request_clarification with 2-4 options when you need the user to choose a scope before continuing.
- If a visual artifact would materially help the answer, build it even when the user did not explicitly ask.
- Create one artifact for a normal request. Create more than one only when the user explicitly asks for multiple views.
- Treat follow-ups like "add emails too", "remove non-transaction nodes", "expand it", or "center this node" as refinements of the previous artifact in the thread.
- If the user says to continue after a tool-budget clarification, continue the previous unfinished request with this fresh run's tool budget.
- If the user asks for CSV export, build the relevant artifact and say it can be downloaded with the artifact CSV button. Do not claim you attached a file or wrote a local file.
- Do not claim evidence exists unless a tool result supports it.
- Keep final answers professional, concise, and specific. Mention artifact titles when you create them.
- When using document search results, cite filename/page metadata when available.

Artifact preference from the UI: {state.get("artifact_preference", "auto")}.

Recent artifacts available in this thread:
{available_artifact_context}

Use these artifact ids when revising a previous report or embedding an existing graph, table, or chart in a report.

Cypher safety rules:
- Only write read-only MATCH/OPTIONAL MATCH/WITH/UNWIND queries that RETURN data.
- Scope actual nodes or relationships with .case_id = $case_id in every Cypher query.
- Do not use fake scoping like WHERE $case_id IS NOT NULL.
- Use Neo4j syntax: RETURN ... ORDER BY ... LIMIT 50. Do not use NULLS FIRST/LAST.
- Use literal numeric LIMIT values, not LIMIT $limit.
- Never use CREATE, MERGE, SET, DELETE, REMOVE, DROP, CALL, LOAD, or admin commands.

Common labels: Person, Organization, Account, Transaction, Communication, Event, Location, LegalAction, Other.
Common relationship types include SENT_PAYMENT, RECEIVED_PAYMENT, VIA_ACCOUNT, HELD_BY, HELD_AT_BANK,
COMMUNICATED_WITH, PARTICIPATED_IN, WORKS_FOR, ASSOCIATED_WITH, BENEFICIAL_OWNER_OF, TRANSFERRED_TO.
Actual labels and fields vary by case, so inspect the schema when field choice matters.
"""

        def agent_node(state: AgentState) -> dict[str, Any]:
            response = model_with_tools.invoke(
                [SystemMessage(content=build_system_prompt(state)), *state["messages"]]
            )
            return {"messages": [response]}

        def tool_node(state: AgentState) -> dict[str, Any]:
            last_message = state["messages"][-1]
            tool_calls = getattr(last_message, "tool_calls", []) or []
            tool_messages: list[ToolMessage] = []
            trace: list[dict[str, Any]] = []
            artifacts: list[dict[str, Any]] = []
            clarifications: list[dict[str, Any]] = []
            tool_results: dict[str, Any] = {}

            for tool_call in tool_calls:
                name = tool_call.get("name")
                args = tool_call.get("args") or {}
                call_id = tool_call.get("id") or f"call_{uuid.uuid4().hex[:12]}"
                activity = activity_for_tool_call(name, args, call_id)
                started = time.perf_counter()
                status = "success"
                error = None
                output: dict[str, Any]

                try:
                    if name not in tools_by_name:
                        raise ValueError(f"Unknown tool: {name}")
                    raw = tools_by_name[name].invoke(args)
                    output = raw if isinstance(raw, dict) else {"summary": str(raw), "data": raw}
                    status = str(output.get("status") or "success")
                    error = output.get("error")
                except Exception as exc:
                    status = "error"
                    error = str(exc)
                    output = {"summary": f"{name} failed: {error}", "data": {"error": error}}

                duration_ms = int((time.perf_counter() - started) * 1000)
                result_id = output.get("result_id")
                if result_id:
                    tool_results[result_id] = output.get("data")

                artifact = output.get("artifact")
                if isinstance(artifact, dict):
                    artifacts.append(to_jsonable(artifact))
                clarification = output.get("clarification")
                if isinstance(clarification, dict):
                    clarifications.append(to_jsonable(clarification))

                summary = str(output.get("summary") or "")
                trace.append(
                    {
                        "id": call_id,
                        "name": name or "unknown",
                        "arguments": to_jsonable(args),
                        "status": "error" if status == "error" else "success",
                        "duration_ms": duration_ms,
                        "summary": summary,
                        "result_id": result_id,
                        "error": error,
                        "result_preview": truncate_payload(output.get("data")),
                        "activity": activity,
                    }
                )
                tool_messages.append(
                    ToolMessage(
                        tool_call_id=call_id,
                        name=name,
                        content=json.dumps(
                            {
                                "result_id": result_id,
                                "summary": summary,
                                "data": truncate_payload(output.get("data"), max_items=20, max_text_chars=1500),
                                "artifact": truncate_payload(artifact, max_items=20, max_text_chars=1500)
                                if artifact
                                else None,
                            },
                            ensure_ascii=False,
                        ),
                    )
                )

            return {
                "messages": tool_messages,
                "tool_trace": trace,
                "artifacts": artifacts,
                "clarifications": clarifications,
                "tool_results": tool_results,
                "tool_iterations": int(state.get("tool_iterations") or 0) + len(tool_calls),
            }

        def route_after_agent(state: AgentState) -> str:
            last_message = state["messages"][-1]
            tool_calls = getattr(last_message, "tool_calls", []) or []
            if tool_calls and int(state.get("tool_iterations") or 0) < int(state.get("max_tool_calls") or max_tool_calls):
                return "tools"
            return "finalize"

        def finalize_node(state: AgentState) -> dict[str, Any]:
            last_message = state["messages"][-1]
            tool_calls = getattr(last_message, "tool_calls", []) or []
            if state.get("clarifications"):
                return {"final_answer": ""}
            if _tool_budget_exhausted(state):
                return {
                    "clarifications": [_budget_continuation_clarification(int(state.get("max_tool_calls") or max_tool_calls))],
                    "final_answer": "",
                }
            if not _used_tools(state) and isinstance(last_message, AIMessage) and not tool_calls and last_message.content:
                return {"final_answer": message_content_to_text(last_message.content)}

            final_messages = _messages_for_finalizer(state)
            response = self.base_model.invoke(
                [
                    SystemMessage(content=_FINAL_ANSWER_SYSTEM_PROMPT),
                    *final_messages,
                ]
            )
            return {"messages": [response], "final_answer": message_content_to_text(response.content)}

        workflow = StateGraph(AgentState)
        workflow.add_node("agent", agent_node)
        workflow.add_node("tools", tool_node)
        workflow.add_node("finalize", finalize_node)
        workflow.add_edge(START, "agent")
        workflow.add_conditional_edges("agent", route_after_agent, {"tools": "tools", "finalize": "finalize"})
        workflow.add_edge("tools", "agent")
        workflow.add_edge("finalize", END)
        graph = workflow.compile(checkpointer=MemorySaver())

        result = graph.invoke(
            {
                "messages": messages,
                "case_id": case_id,
                "artifact_preference": artifact_preference,
                "max_tool_calls": max_tool_calls,
                "tool_iterations": 0,
                "tool_trace": [],
                "tool_results": {},
                "artifacts": [],
                "clarifications": [],
            },
            config={"configurable": {"thread_id": thread_id or f"agent_{uuid.uuid4().hex}"}},
        )

        return {
            "answer": result.get("final_answer") or "",
            "artifacts": result.get("artifacts") or [],
            "clarification": (result.get("clarifications") or [None])[-1],
            "tool_trace": result.get("tool_trace") or [],
            "messages": result.get("messages") or [],
            "usage": self._extract_usage(result.get("messages") or []),
        }

    def stream(
        self,
        *,
        case_id: str,
        messages: list[HumanMessage | AIMessage],
        artifact_preference: str = "auto",
        max_tool_calls: int = 28,
        thread_id: str | None = None,
        available_artifacts: list[dict[str, Any]] | None = None,
        should_cancel: Callable[[], bool] | None = None,
        allowed_entity_keys: list[str] | None = None,
    ):
        available_artifact_context = _format_available_artifacts(available_artifacts)
        tool_context = AgentToolContext(
            case_id=case_id,
            artifact_preference=artifact_preference,
            allowed_entity_keys=(set(allowed_entity_keys) if allowed_entity_keys is not None else None),
            artifact_store=_artifact_store_from_available(available_artifacts),
        )
        tools = make_agent_tools(tool_context)
        tools_by_name = {tool.name: tool for tool in tools}
        model_with_tools = self.base_model.bind_tools(tools)

        def build_system_prompt(state: AgentState) -> str:
            return f"""You are the OWL AI Agent, an investigative graph analyst.

You are working inside one case only. Every tool is already scoped to case_id={case_id}.
{"You are additionally restricted to the Significant layer. Use only its entities and relationships between those entities; do not infer from or request case-wide data." if allowed_entity_keys is not None else "You may use the full case dataset."}

Your job:
- Answer investigation questions using tools instead of guessing.
- Search the graph when the user asks about people, companies, events, relationships, timelines, locations, or transactions.
- Search documents when the answer needs source text, document excerpts, or semantic context.
- Use run_readonly_cypher for precise graph questions that need counts, filters, paths, or custom tables.
- Use inspect_graph_schema before writing custom Cypher for labels or properties you have not already inspected in this run.
- For human-readable entity names in Cypher, prefer coalesce(n.name, n.display_name, n.full_name, n.title, n.key); do not assume display_name exists.
- If the user asks for a graph, map, table, chart, or report view, build the matching artifact.
- Use build_table_artifact for query-backed tables where rows come directly from Neo4j.
- Use build_table_artifact_from_rows for synthesized analytical tables you have already reasoned out from tool evidence, such as ranked contradictions, witness matrices, issue lists, or source comparison tables.
- Use build_chart_artifact for numeric summaries, distributions, rankings, comparisons, trends, and proportions. Pick bar/stacked_bar, line/area, pie/donut, or scatter according to the user's wording and the data shape.
- Do not encode hand-built analytical rows as Cypher UNWIND just to create a table artifact.
- For report requests, do not build the report until the user has clearly specified the purpose, scope, and what should be included. If any of those are unclear, use request_clarification.
- When useful for a report, offer to embed graph, table, or chart artifacts, or create and embed them yourself when they materially support the report.
- Build reports with build_report_artifact. Treat follow-ups as revisions of the previous report artifact and explain what changed.
- If the user asks for a timeline, chronology, transaction list, or financial table, build a table artifact with useful date, amount, entity, and reasoning columns.
- For graph requests, first use search_graph_entities, inspect_graph_schema, or run_readonly_cypher to identify the exact node keys and relationship context that belong in the graph.
- Prefer build_graph_artifact in selected_subgraph mode with node_keys, source_result_ids, or a graph query. The graph builder can materialize nodes/relationships from prior Cypher results, key columns, or graph-shaped rows.
- Use specialized graph modes only as convenience fallbacks: transaction_only for only Transaction nodes, shortest_paths for connective tissue between named nodes, and entity_neighborhood for broad expansion.
- If build_graph_artifact returns zero nodes, do not immediately ask the user. Search or query for the right node keys, inspect available fields if needed, then retry with selected_subgraph.
- If the graph request is ambiguous and the difference changes meaning, ask a clarifying question before building.
- Use request_clarification with 2-4 options when you need the user to choose a scope before continuing.
- If a visual artifact would materially help the answer, build it even when the user did not explicitly ask.
- Create one artifact for a normal request. Create more than one only when the user explicitly asks for multiple views.
- Treat follow-ups like "add emails too", "remove non-transaction nodes", "expand it", or "center this node" as refinements of the previous artifact in the thread.
- If the user says to continue after a tool-budget clarification, continue the previous unfinished request with this fresh run's tool budget.
- If the user asks for CSV export, build the relevant artifact and say it can be downloaded with the artifact CSV button. Do not claim you attached a file or wrote a local file.
- Do not claim evidence exists unless a tool result supports it.
- Keep final answers professional, concise, and specific. Mention artifact titles when you create them.
- When using document search results, cite filename/page metadata when available.

Artifact preference from the UI: {state.get("artifact_preference", "auto")}.

Recent artifacts available in this thread:
{available_artifact_context}

Use these artifact ids when revising a previous report or embedding an existing graph, table, or chart in a report.

Cypher safety rules:
- Only write read-only MATCH/OPTIONAL MATCH/WITH/UNWIND queries that RETURN data.
- Scope actual nodes or relationships with .case_id = $case_id in every Cypher query.
- Do not use fake scoping like WHERE $case_id IS NOT NULL.
- Use Neo4j syntax: RETURN ... ORDER BY ... LIMIT 50. Do not use NULLS FIRST/LAST.
- Use literal numeric LIMIT values, not LIMIT $limit.
- Never use CREATE, MERGE, SET, DELETE, REMOVE, DROP, CALL, LOAD, or admin commands.

Common labels: Person, Organization, Account, Transaction, Communication, Event, Location, LegalAction, Other.
Common relationship types include SENT_PAYMENT, RECEIVED_PAYMENT, VIA_ACCOUNT, HELD_BY, HELD_AT_BANK,
COMMUNICATED_WITH, PARTICIPATED_IN, WORKS_FOR, ASSOCIATED_WITH, BENEFICIAL_OWNER_OF, TRANSFERRED_TO.
Actual labels and fields vary by case, so inspect the schema when field choice matters.
"""

        def agent_node(state: AgentState) -> dict[str, Any]:
            if should_cancel and should_cancel():
                raise AgentRunCancelled("Agent run cancelled")
            response = model_with_tools.invoke(
                [SystemMessage(content=build_system_prompt(state)), *state["messages"]]
            )
            return {"messages": [response]}

        def tool_node(state: AgentState) -> dict[str, Any]:
            last_message = state["messages"][-1]
            tool_calls = getattr(last_message, "tool_calls", []) or []
            tool_messages: list[ToolMessage] = []
            trace: list[dict[str, Any]] = []
            artifacts: list[dict[str, Any]] = []
            clarifications: list[dict[str, Any]] = []
            tool_results: dict[str, Any] = {}

            for tool_call in tool_calls:
                if should_cancel and should_cancel():
                    raise AgentRunCancelled("Agent run cancelled")
                name = tool_call.get("name")
                args = tool_call.get("args") or {}
                call_id = tool_call.get("id") or f"call_{uuid.uuid4().hex[:12]}"
                activity = activity_for_tool_call(name, args, call_id)
                started = time.perf_counter()
                status = "success"
                error = None
                output: dict[str, Any]

                try:
                    if name not in tools_by_name:
                        raise ValueError(f"Unknown tool: {name}")
                    raw = tools_by_name[name].invoke(args)
                    output = raw if isinstance(raw, dict) else {"summary": str(raw), "data": raw}
                    status = str(output.get("status") or "success")
                    error = output.get("error")
                except Exception as exc:
                    status = "error"
                    error = str(exc)
                    output = {"summary": f"{name} failed: {error}", "data": {"error": error}}

                duration_ms = int((time.perf_counter() - started) * 1000)
                result_id = output.get("result_id")
                if result_id:
                    tool_results[result_id] = output.get("data")

                artifact = output.get("artifact")
                if isinstance(artifact, dict):
                    artifacts.append(to_jsonable(artifact))
                clarification = output.get("clarification")
                if isinstance(clarification, dict):
                    clarifications.append(to_jsonable(clarification))

                summary = str(output.get("summary") or "")
                trace.append(
                    {
                        "id": call_id,
                        "name": name or "unknown",
                        "arguments": to_jsonable(args),
                        "status": "error" if status == "error" else "success",
                        "duration_ms": duration_ms,
                        "summary": summary,
                        "result_id": result_id,
                        "error": error,
                        "result_preview": truncate_payload(output.get("data")),
                        "activity": activity,
                    }
                )
                tool_messages.append(
                    ToolMessage(
                        tool_call_id=call_id,
                        name=name,
                        content=json.dumps(
                            {
                                "result_id": result_id,
                                "summary": summary,
                                "data": truncate_payload(output.get("data"), max_items=20, max_text_chars=1500),
                                "artifact": truncate_payload(artifact, max_items=20, max_text_chars=1500)
                                if artifact
                                else None,
                            },
                            ensure_ascii=False,
                        ),
                    )
                )

            return {
                "messages": tool_messages,
                "tool_trace": trace,
                "artifacts": artifacts,
                "clarifications": clarifications,
                "tool_results": tool_results,
                "tool_iterations": int(state.get("tool_iterations") or 0) + len(tool_calls),
            }

        def route_after_agent(state: AgentState) -> str:
            if should_cancel and should_cancel():
                raise AgentRunCancelled("Agent run cancelled")
            last_message = state["messages"][-1]
            tool_calls = getattr(last_message, "tool_calls", []) or []
            if tool_calls and int(state.get("tool_iterations") or 0) < int(state.get("max_tool_calls") or max_tool_calls):
                return "tools"
            return "finalize"

        def finalize_node(state: AgentState) -> dict[str, Any]:
            if should_cancel and should_cancel():
                raise AgentRunCancelled("Agent run cancelled")
            last_message = state["messages"][-1]
            tool_calls = getattr(last_message, "tool_calls", []) or []
            if state.get("clarifications"):
                return {"final_answer": ""}
            if _tool_budget_exhausted(state):
                return {
                    "clarifications": [_budget_continuation_clarification(int(state.get("max_tool_calls") or max_tool_calls))],
                    "final_answer": "",
                }
            if not _used_tools(state) and isinstance(last_message, AIMessage) and not tool_calls and last_message.content:
                return {"final_answer": message_content_to_text(last_message.content)}

            final_messages = _messages_for_finalizer(state)
            response = self.base_model.invoke(
                [
                    SystemMessage(content=_FINAL_ANSWER_SYSTEM_PROMPT),
                    *final_messages,
                ]
            )
            return {"messages": [response], "final_answer": message_content_to_text(response.content)}

        workflow = StateGraph(AgentState)
        workflow.add_node("agent", agent_node)
        workflow.add_node("tools", tool_node)
        workflow.add_node("finalize", finalize_node)
        workflow.add_edge(START, "agent")
        workflow.add_conditional_edges("agent", route_after_agent, {"tools": "tools", "finalize": "finalize"})
        workflow.add_edge("tools", "agent")
        workflow.add_edge("finalize", END)
        graph = workflow.compile(checkpointer=MemorySaver())

        initial_state = {
            "messages": messages,
            "case_id": case_id,
            "artifact_preference": artifact_preference,
            "max_tool_calls": max_tool_calls,
            "tool_iterations": 0,
            "tool_trace": [],
            "tool_results": {},
            "artifacts": [],
            "clarifications": [],
        }
        config = {"configurable": {"thread_id": thread_id or f"agent_{uuid.uuid4().hex}"}}
        collected_messages: list[AnyMessage] = []
        collected_trace: list[dict[str, Any]] = []
        collected_artifacts: list[dict[str, Any]] = []
        collected_clarifications: list[dict[str, Any]] = []
        final_answer = ""

        yield {"type": "status", "stage": "reasoning", "message": "Thinking through the request"}
        for update in graph.stream(initial_state, config=config, stream_mode="updates"):
            agent_update = update.get("agent")
            if agent_update:
                agent_messages = agent_update.get("messages") or []
                collected_messages.extend(agent_messages)
                if agent_messages:
                    last = agent_messages[-1]
                    tool_calls = getattr(last, "tool_calls", []) or []
                    if tool_calls:
                        for call in tool_calls:
                            yield {
                                "type": "activity",
                                "activity": activity_for_tool_call(
                                    call.get("name"),
                                    call.get("args") or {},
                                    call.get("id"),
                                ),
                            }
                        yield {
                            "type": "tool_plan",
                            "tools": [
                                {
                                    "id": call.get("id"),
                                    "name": call.get("name"),
                                    "arguments": to_jsonable(call.get("args") or {}),
                                }
                                for call in tool_calls
                            ],
                        }
                    else:
                        content = message_content_to_text(getattr(last, "content", ""))
                        if content and not collected_trace:
                            yield {"type": "assistant_draft", "answer": content}

            tools_update = update.get("tools")
            if tools_update:
                tool_messages = tools_update.get("messages") or []
                collected_messages.extend(tool_messages)
                trace = tools_update.get("tool_trace") or []
                artifacts = tools_update.get("artifacts") or []
                clarifications = tools_update.get("clarifications") or []
                collected_trace.extend(trace)
                collected_artifacts.extend(artifacts)
                collected_clarifications.extend(clarifications)
                for item in trace:
                    yield {"type": "activity", "activity": activity_for_tool_result(item)}
                    yield {"type": "tool_result", "tool": item}
                for artifact in artifacts:
                    yield {"type": "artifact", "artifact": artifact}
                for clarification in clarifications:
                    yield {"type": "clarification", "clarification": clarification}

            finalize_update = update.get("finalize")
            if finalize_update:
                finalize_messages = finalize_update.get("messages") or []
                clarifications = finalize_update.get("clarifications") or []
                collected_messages.extend(finalize_messages)
                collected_clarifications.extend(clarifications)
                for clarification in clarifications:
                    yield {"type": "clarification", "clarification": clarification}
                final_answer = finalize_update.get("final_answer") or final_answer
                if final_answer:
                    yield {"type": "answer", "answer": final_answer}

        result = {
            "answer": final_answer,
            "artifacts": collected_artifacts,
            "clarification": (collected_clarifications or [None])[-1],
            "tool_trace": collected_trace,
            "messages": collected_messages,
            "usage": self._extract_usage(collected_messages),
        }
        yield {"type": "final", "result": result}

    @staticmethod
    def _extract_usage(messages: list[AnyMessage]) -> dict[str, int] | None:
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        seen = False

        for message in messages:
            if not isinstance(message, AIMessage):
                continue
            usage = getattr(message, "usage_metadata", None) or {}
            if not usage:
                response_metadata = getattr(message, "response_metadata", None) or {}
                token_usage = response_metadata.get("token_usage") or {}
                usage = {
                    "input_tokens": token_usage.get("prompt_tokens"),
                    "output_tokens": token_usage.get("completion_tokens"),
                    "total_tokens": token_usage.get("total_tokens"),
                }
            input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
            output_tokens = usage.get("output_tokens") or usage.get("completion_tokens") or 0
            message_total = usage.get("total_tokens") or (input_tokens + output_tokens)
            if input_tokens or output_tokens or message_total:
                seen = True
                prompt_tokens += int(input_tokens or 0)
                completion_tokens += int(output_tokens or 0)
                total_tokens += int(message_total or 0)

        if not seen:
            return None
        return {
            "prompt_tokens": prompt_tokens or None,
            "completion_tokens": completion_tokens or None,
            "total_tokens": total_tokens or None,
        }
