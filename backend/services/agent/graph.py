from __future__ import annotations

import json
import operator
import time
import uuid
from typing import Annotated, Any, TypedDict
from collections.abc import Callable

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph, add_messages

from config import OPENAI_API_KEY
from services.agent.json_utils import to_jsonable, truncate_payload
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
        max_tool_calls: int = 12,
        thread_id: str | None = None,
        available_artifacts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        available_artifact_context = _format_available_artifacts(available_artifacts)
        tool_context = AgentToolContext(
            case_id=case_id,
            artifact_preference=artifact_preference,
            artifact_store=_artifact_store_from_available(available_artifacts),
        )
        tools = make_agent_tools(tool_context)
        tools_by_name = {tool.name: tool for tool in tools}
        model_with_tools = self.base_model.bind_tools(tools)

        def build_system_prompt(state: AgentState) -> str:
            return f"""You are the OWL AI Agent, an investigative graph analyst.

You are working inside one case only. Every tool is already scoped to case_id={case_id}.

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
- For graph requests, choose the narrowest graph mode that matches the user's words:
  transaction_only for only Transaction nodes, transactions_plus_accounts for transaction nodes and accounts,
  transaction_flow for money-flow context, shortest_paths for connective tissue between named nodes,
  entity_neighborhood for normal entity expansion.
- If the graph request is ambiguous and the difference changes meaning, ask a clarifying question before building.
- Use request_clarification with 2-4 options when you need the user to choose a scope before continuing.
- If a visual artifact would materially help the answer, build it even when the user did not explicitly ask.
- Create one artifact for a normal request. Create more than one only when the user explicitly asks for multiple views.
- Treat follow-ups like "add emails too", "remove non-transaction nodes", "expand it", or "center this node" as refinements of the previous artifact in the thread.
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
            if isinstance(last_message, AIMessage) and not tool_calls and last_message.content:
                return {"final_answer": message_content_to_text(last_message.content)}

            final_messages = _messages_without_dangling_tool_calls(state["messages"])
            response = self.base_model.invoke(
                [
                    SystemMessage(
                        content=(
                            "Write the final answer from the tool results. "
                            "Be concise, do not call tools, and mention any artifacts created. "
                            "If the previous assistant turn requested more tools than the run budget allowed, "
                            "ignore that unexecuted request and summarize only the completed tool results. "
                            "If CSV export is relevant, refer to the artifact CSV button; do not claim a file is attached."
                        )
                    ),
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
        max_tool_calls: int = 12,
        thread_id: str | None = None,
        available_artifacts: list[dict[str, Any]] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ):
        available_artifact_context = _format_available_artifacts(available_artifacts)
        tool_context = AgentToolContext(
            case_id=case_id,
            artifact_preference=artifact_preference,
            artifact_store=_artifact_store_from_available(available_artifacts),
        )
        tools = make_agent_tools(tool_context)
        tools_by_name = {tool.name: tool for tool in tools}
        model_with_tools = self.base_model.bind_tools(tools)

        def build_system_prompt(state: AgentState) -> str:
            return f"""You are the OWL AI Agent, an investigative graph analyst.

You are working inside one case only. Every tool is already scoped to case_id={case_id}.

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
- For graph requests, choose the narrowest graph mode that matches the user's words:
  transaction_only for only Transaction nodes, transactions_plus_accounts for transaction nodes and accounts,
  transaction_flow for money-flow context, shortest_paths for connective tissue between named nodes,
  entity_neighborhood for normal entity expansion.
- If the graph request is ambiguous and the difference changes meaning, ask a clarifying question before building.
- Use request_clarification with 2-4 options when you need the user to choose a scope before continuing.
- If a visual artifact would materially help the answer, build it even when the user did not explicitly ask.
- Create one artifact for a normal request. Create more than one only when the user explicitly asks for multiple views.
- Treat follow-ups like "add emails too", "remove non-transaction nodes", "expand it", or "center this node" as refinements of the previous artifact in the thread.
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
            if isinstance(last_message, AIMessage) and not tool_calls and last_message.content:
                return {"final_answer": message_content_to_text(last_message.content)}

            final_messages = _messages_without_dangling_tool_calls(state["messages"])
            response = self.base_model.invoke(
                [
                    SystemMessage(
                        content=(
                            "Write the final answer from the tool results. "
                            "Be concise, do not call tools, and mention any artifacts created. "
                            "If the previous assistant turn requested more tools than the run budget allowed, "
                            "ignore that unexecuted request and summarize only the completed tool results. "
                            "If CSV export is relevant, refer to the artifact CSV button; do not claim a file is attached."
                        )
                    ),
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
                        if content:
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
                    yield {"type": "tool_result", "tool": item}
                for artifact in artifacts:
                    yield {"type": "artifact", "artifact": artifact}
                for clarification in clarifications:
                    yield {"type": "clarification", "clarification": clarification}

            finalize_update = update.get("finalize")
            if finalize_update:
                finalize_messages = finalize_update.get("messages") or []
                collected_messages.extend(finalize_messages)
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
