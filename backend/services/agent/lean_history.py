"""What one model request carries of the run so far: each tool result in full once, then a digest.

Every agent turn re-sent the whole conversation, so a tool result shown on turn 2 was sent again on every later turn
and to the finalizer (live run 8df85211 on BNB2: 2.0 million characters, 654,388 prompt tokens, for 17 tool calls).

The rule here: a tool message is sent whole on the turn after its call (the model reads it then). On later turns it
is replaced by a digest: the tool's summary, the result's own short facts (counts, revisions, totals, paging notes),
ledger figures when the result is a grouped ledger read, and how to read it again. The whole result stays in the run
(``AgentToolContext.model_views``) and ``read_tool_result_page`` with only the result id returns it again, so nothing
the model was shown becomes unreachable. Small messages are never digested. The digest of one message is the same
text on every turn, so the request's prefix is the same from turn to turn (provider prefix caching).

A tool call that returns exactly what an earlier call in the run returned is sent as a pointer to that result.
The finalizer gets every result whole (see finalizer_messages for the switch that gives it the agent's selection).
The tool definitions are sent with optional fields written once, without the repeated null alternative.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from langchain_core.messages import AIMessage, AnyMessage, ToolMessage

from services.agent.model_payloads import PAGE_TOOL

DIGEST_MARK = "digest_of"
# A message at or below this size is sent whole every time: its digest would not be much smaller.
MIN_DIGEST_CHARS = 2_000
# A short text field or a small mapping (totals, coverage counts, exclusions) of the result is kept in the digest.
MAX_FACT_TEXT = 300
MAX_FACT_MAPPING = 3_000
DIGEST_NOTE = ("Digest of a result shown in full earlier in this run; the full result is unchanged. Before relying "
               "on a detail not in this digest, call %s with this result_id (no path) to read it again." % PAGE_TOOL)
# The fields of one grouped ledger figure (services.agent.financial_ledger_tools, view groups) kept in a digest.
GROUP_FIELDS = ("group", "currency", "account_type", "currency_exponent", "transaction_count", "credits_minor",
                "debits_minor", "net_minor", "account_count")
LEDGER_SCHEMA = "loupe.agent.financial_ledger/1"


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _facts(data: dict) -> tuple[dict, dict]:
    facts, sizes = {}, {}
    for key, value in data.items():
        if value is None or isinstance(value, (bool, int, float)):
            facts[key] = value
        elif isinstance(value, str):
            if len(value) <= MAX_FACT_TEXT:
                facts[key] = value
            else:
                sizes[key] = "text of %d characters" % len(value)
        elif isinstance(value, dict) and len(_dumps(value)) <= MAX_FACT_MAPPING:
            facts[key] = value
        elif isinstance(value, (list, dict)):
            sizes[key] = "%d %s" % (len(value), "items" if isinstance(value, list) else "entries")
    return facts, sizes


def _group_figures(data: dict) -> list[dict] | None:
    if data.get("schema") != LEDGER_SCHEMA or data.get("view") != "groups" or not isinstance(data.get("items"), list):
        return None
    figures = []
    for item in data["items"]:
        if not isinstance(item, dict):
            return None
        figure = {key: item[key] for key in GROUP_FIELDS if key in item}
        calls = item.get("open_judgement_calls")
        if isinstance(calls, dict) and "open_calls" in calls:
            figure["open_judgement_calls"] = calls.get("open_calls")
        figures.append(figure)
    return figures


def digest_payload(payload: dict) -> dict | None:
    """The digest of one tool message's payload, or None when it is kept whole (small, not re-openable, a digest)."""
    if not isinstance(payload, dict) or DIGEST_MARK in payload or not payload.get("result_id"):
        return None
    digest: dict[str, Any] = {DIGEST_MARK: payload["result_id"], "summary": payload.get("summary")}
    for key in ("status", "error", "same_as"):
        if payload.get(key):
            digest[key] = payload[key]
    data = payload.get("data")
    if isinstance(data, dict):
        facts, sizes = _facts(data)
        figures = _group_figures(data)
        if figures is not None:
            facts["group_figures"] = figures
            sizes.pop("items", None)
        digest["facts"] = facts
        if sizes:
            digest["not_in_digest"] = sizes
    elif data is not None:
        digest["not_in_digest"] = {"data": "a %s" % type(data).__name__}
    artifact = payload.get("artifact")
    if isinstance(artifact, dict):
        digest["artifact"] = {key: artifact.get(key) for key in ("id", "type", "title") if artifact.get(key)}
    if payload.get("_paging"):
        digest["_paging"] = payload["_paging"]
    digest["note"] = DIGEST_NOTE
    return digest


def digest_content(content: Any) -> str | None:
    """The digest text of a tool message's content, or None when the message is sent whole."""
    if not isinstance(content, str) or len(content) <= MIN_DIGEST_CHARS:
        return None
    try:
        payload = json.loads(content)
    except ValueError:
        return None
    digest = digest_payload(payload)
    if digest is None:
        return None
    text = _dumps(digest)
    return text if len(text) < len(content) else None


def _last_tool_request(messages: list[AnyMessage]) -> int:
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if isinstance(message, AIMessage) and (getattr(message, "tool_calls", None) or []):
            return index
    return -1


# DeepSeek reads a prompt from its cache (about a thirtieth of the price) only up to the end of an earlier request
# (measured 10 Nov 2026: a 12,789-token request whose first result had become a digest read 4,736 from the cache,
# the first request only; the same request with the result left whole read 8,704). Digesting a result the model was
# already sent therefore makes every later turn pay for the whole history again. With this switch on, nothing already
# sent is rewritten: each turn's request starts with the previous one, byte for byte.
CACHE_STABLE_SETTING = "LOUPE_AGENT_CACHE_STABLE_HISTORY"


def cache_stable_history() -> bool:
    import os
    return os.getenv(CACHE_STABLE_SETTING, "").strip() == "1"


def lean_messages(messages: list[AnyMessage]) -> list[AnyMessage]:
    """The conversation for the next model request: the latest tool batch whole, earlier tool results as digests
    (every message as sent before when the cache-stable switch is on)."""
    if cache_stable_history():
        return list(messages)
    boundary = _last_tool_request(messages)
    lean: list[AnyMessage] = []
    for index, message in enumerate(messages):
        if isinstance(message, ToolMessage) and index < boundary:
            text = digest_content(message.content)
            if text is not None:
                message = ToolMessage(content=text, tool_call_id=message.tool_call_id, name=message.name,
                                      id=message.id)
        lean.append(message)
    return lean


def has_draft(messages: list[AnyMessage]) -> bool:
    """True when the conversation ends on the agent's own answer text (not a tool request)."""
    if not messages or not isinstance(messages[-1], AIMessage) or (getattr(messages[-1], "tool_calls", None) or []):
        return False
    content = messages[-1].content
    text = content if isinstance(content, str) else _dumps(content)
    return bool(text.strip())


# The finalizer may check and add to the draft from every result, so by default it gets every result whole (every
# bounded row reaches it: tests/test_agent_financial_journey). LOUPE_AGENT_LEAN_FINALIZER=1 gives it the agent's own
# selection instead when a draft exists (replay of 8df85211: 252,408 -> 42,990 characters of tool messages). Off
# until a live comparison shows its answers keep every fact, figure and citation.
LEAN_FINALIZER_SETTING = "LOUPE_AGENT_LEAN_FINALIZER"


def lean_finalizer() -> bool:
    import os
    return os.getenv(LEAN_FINALIZER_SETTING, "").strip() == "1"


# The finalizer's request starts as the agent's own does (its system prompt, its tools, the conversation as the agent
# last sent it), so DeepSeek reads all of that from its cache; the final-answer rules follow as the last message and
# tools are offered with tool_choice "none". Off until a side-by-side shows the same facts, figures and citations.
FINALIZER_ON_AGENT_PREFIX_SETTING = "LOUPE_AGENT_FINALIZER_ON_AGENT_PREFIX"


def finalizer_on_agent_prefix() -> bool:
    import os
    return os.getenv(FINALIZER_ON_AGENT_PREFIX_SETTING, "").strip() == "1"


def finalizer_messages(messages: list[AnyMessage]) -> list[AnyMessage]:
    """The finalizer's conversation: every result whole, unless the lean finalizer is switched on and the agent's
    draft answer is last (then the selection the draft was written from). Without a draft, always whole."""
    return lean_messages(messages) if lean_finalizer() and has_draft(messages) else messages


class RepeatedResults:
    """Within one run: a tool message identical to an earlier one (apart from its result id) is sent as a pointer."""

    def __init__(self) -> None:
        self._seen: dict[str, str] = {}

    def content(self, payload: dict) -> str:
        text = _dumps(payload)
        result_id = payload.get("result_id")
        if not result_id or len(text) <= MIN_DIGEST_CHARS:
            return text
        key = hashlib.sha256(_dumps({k: v for k, v in payload.items() if k != "result_id"}).encode()).hexdigest()
        earlier = self._seen.get(key)
        if earlier is None:
            self._seen[key] = result_id
            return text
        return _dumps({"result_id": result_id, "same_as": earlier, "summary": payload.get("summary"),
                       "note": ("This call returned exactly the result %s returned earlier in this run (the same data "
                                "and the same summary); read that one, or call %s with result_id %s."
                                % (earlier, PAGE_TOOL, result_id))})


def _compact_schema(value: Any) -> Any:
    """An optional field's ``anyOf: [X, null]`` with ``default: null`` says the same as X left out of ``required``."""
    if isinstance(value, list):
        return [_compact_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    value = {key: _compact_schema(item) for key, item in value.items()}
    options = value.get("anyOf")
    if isinstance(options, list) and len(options) == 2 and {"type": "null"} in options and "default" in value \
            and value["default"] is None:
        other = options[0] if options[1] == {"type": "null"} else options[1]
        if isinstance(other, dict) and not set(other) & (set(value) - {"anyOf", "default"}):
            value = {**other, **{key: item for key, item in value.items() if key not in ("anyOf", "default")}}
    return value


def tool_definitions(tools: list) -> list[dict]:
    """The tools as the model is sent them (OpenAI function format), with optional fields written without the
    repeated null alternative. Required fields, types, bounds, enums and every description are unchanged; a call
    with an explicit null is still accepted, since each tool validates its arguments with its own schema."""
    from langchain_core.utils.function_calling import convert_to_openai_tool
    definitions = []
    for tool in tools:
        definition = convert_to_openai_tool(tool)
        function = definition.get("function") or {}
        parameters = function.get("parameters")
        if isinstance(parameters, dict):
            required = set(parameters.get("required") or [])
            properties = parameters.get("properties") or {}
            parameters = {**parameters, "properties": {
                name: (spec if name in required else _compact_schema(spec)) for name, spec in properties.items()}}
            definition = {**definition, "function": {**function, "parameters": parameters}}
        definitions.append(definition)
    return definitions


def tools_for_binding(model: Any, tools: list) -> list:
    """What a chat model's ``bind_tools`` is given: the lean definitions for a LangChain chat model (which sends them
    as they are), the tool objects themselves for anything else (a scripted test model reads their names)."""
    from langchain_core.language_models import BaseChatModel
    return tool_definitions(tools) if isinstance(model, BaseChatModel) else tools
