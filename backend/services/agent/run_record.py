"""The agent run record is the disclosure record (AG Guidelines 2024 Annex A paras 47-48; FSR Code 28.1.5).

Every run keeps, without further work by anyone:

- who the run was for (name and e-mail as they were at the time), start and end, model provider and id;
- the prompt version: a sha256 of the system prompt templates, the answer prompts and the tool schema set the model
  was given, with a readable label (``v<n> · <date> · <sha8>``) and the full text kept in ``agent_prompt_versions``;
- the tool budget and how much of it the run used, and any call the model asked for that the budget stopped;
- per tool call: its parameters and search terms, the result's ``total`` and ``returned``, the ``next_page`` it
  offered, the ledger revision and the phone generation it read, and what the model was shown of it;
- per item a result returned: whether the agent read it further (a later call named it, or a page holding it was
  read), cited it in the answer, or used it in an artifact.

All of it is computed by this code from what the run did. The model reports nothing about itself here.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from services.agent.json_utils import sanitize_text, to_jsonable

RECORD_SCHEMA = "loupe.agent.run_record/1"
# One call's item list is stored whole up to this; past it the count not listed is stored and stated.
MAX_ITEMS_PER_CALL = 500
# A reference shorter than this is too generic to find inside another call's parameters by text.
MIN_REF_CHARS = 6
NOT_DETERMINISTIC = (
    "Replays on a hosted model are not deterministic: asking the same question again can choose different tools "
    "and search terms and give a different answer. This record states what this run did; it is not a promise "
    "of what a re-run would do.")
PAGE_TOOL = "read_tool_result_page"
# The lists of a result that are its returned items (not its totals, notes or judgement calls).
ITEM_LISTS = ("items", "entities", "rows", "chunks", "events", "paths", "locations", "nodes", "results",
              "transactions", "sample_entities", "matches", "leads", "records")
CONTINUATION_ARGS = ("offset", "expected_revision", "expected_ledger_revision", "limit")
TERM_ARGS = ("query", "search", "text", "terms", "keywords", "people", "person", "names", "entity_key",
             "entity_keys", "node_keys", "source_key", "target_key", "identity_key", "identity_keys", "record_uid",
             "account_ids", "counterparty", "description_contains", "start_date", "end_date", "kinds", "ref")

# Which kind of case material each tool reads (for "categories not searched").
CATEGORY_BY_TOOL = {
    "search_graph_entities": "graph", "inspect_graph_schema": "graph", "get_entity_details": "graph",
    "get_entity_neighborhood": "graph", "find_paths_between_entities": "graph", "run_readonly_cypher": "graph",
    "get_case_overview": "graph", "get_timeline_events": "timeline", "get_map_locations": "map",
    "search_documents": "documents",
    "get_financial_transactions": "ledger", "analyze_financial_transactions": "ledger",
    "get_financial_coverage": "ledger",
    "get_casework": "casework", "get_dossier": "casework",
    # agent-phones cross tools (phone_cross_tools.TOOLS): phones read as the screens read them, joined to money.
    "search_case": "case_search", "get_person_phones": "phones", "get_day_activity": "phones",
    "get_together_apart": "phones", "get_routine_deviations": "phones", "get_phone_map_summary": "phones",
    "get_contact_and_money_between": "phones", "get_money_signal_matches": "phones",
    "get_money_signal_leads": "phones", "evaluate_statement": "phones",
}
CATEGORY_LABELS = {
    "graph": "Case graph (people, organisations, accounts, events)",
    "documents": "Document text (search of the case's documents)",
    "ledger": "Imported bank statements (the ledger)",
    "phones": "Phone extraction reports",
    "timeline": "Timeline events",
    "map": "Map locations",
    "casework": "Casework notes, findings and dossiers",
    "case_search": "Case-wide search (every kind of record)",
}


def category_of(tool_name: str | None) -> str | None:
    name = tool_name or ""
    if name.startswith("phone_"):
        return "phones"
    if name.startswith("build_") or name in (PAGE_TOOL, "request_clarification"):
        return None
    return CATEGORY_BY_TOOL.get(name)


# --------------------------------------------------------------------------------------------- prompt version

def prompt_version_source() -> dict[str, Any]:
    """What the model is given that is the same for every case: the system prompt (both layers, case values
    replaced by placeholders), the answer prompts, and the tool schemas exactly as bound."""
    from langchain_core.utils.function_calling import convert_to_openai_tool

    from services.agent import graph
    from services.agent.tools import AgentToolContext, make_agent_tools

    prompts = {
        layer: graph.render_system_prompt(
            case_id="{case_id}", significant=layer == "significant", mandate_context_block="{mandate}",
            artifact_preference="{artifact_preference}", available_artifact_context="{available_artifacts}")
        for layer in ("all", "significant")
    }
    prompts["final_answer_system"] = graph._FINAL_ANSWER_SYSTEM_PROMPT
    prompts["final_answer_request"] = graph._FINAL_ANSWER_REQUEST
    tools = sorted((convert_to_openai_tool(tool) for tool in make_agent_tools(AgentToolContext(case_id="{case_id}"))),
                   key=lambda item: item.get("function", {}).get("name", ""))
    return {"prompts": prompts, "tools": tools}


def prompt_version_hash(source: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                          .encode()).hexdigest()


_PROMPT_CACHE: dict[str, Any] = {}


def current_prompt_version() -> tuple[str, dict[str, Any]]:
    """(sha256, source) of the running code's prompt and tools; computed once per process."""
    if "sha" not in _PROMPT_CACHE:
        source = prompt_version_source()
        _PROMPT_CACHE["source"] = source
        _PROMPT_CACHE["sha"] = prompt_version_hash(source)
    return _PROMPT_CACHE["sha"], _PROMPT_CACHE["source"]


def register_prompt_version(db, sha: str, source: dict[str, Any]) -> str:
    """The readable label of this prompt version, stored with its full text the first time it is used."""
    from postgres.models.agent import AgentPromptVersion

    row = db.get(AgentPromptVersion, sha)
    if row is None:
        from sqlalchemy import func, select
        from sqlalchemy.exc import IntegrityError
        number = int(db.scalar(select(func.count()).select_from(AgentPromptVersion)) or 0) + 1
        now = datetime.now(timezone.utc)
        # The sha8 in the label keeps two versions apart even if two first uses race for the same number.
        candidate = AgentPromptVersion(
            sha256=sha, label="v%d · %s · %s" % (number, now.date().isoformat(), sha[:8]), first_used_at=now,
            prompt_text=to_jsonable(source.get("prompts")), tool_schemas=to_jsonable(source.get("tools")),
            tool_count=len(source.get("tools") or []))
        try:
            with db.begin_nested():
                db.add(candidate)
            row = candidate
        except IntegrityError:  # another run stored this version first: use its label
            row = db.get(AgentPromptVersion, sha, populate_existing=True)
    return row.label


# --------------------------------------------------------------------------------------------- phone generation

def phone_generation(conn, case_id) -> str | None:
    """Each phone extraction of the case with the interpretation generation read (``<extraction>:<generation>``),
    or None when the case has no phones."""
    from sqlalchemy import text
    try:
        value = conn.execute(text(
            "SELECT string_agg(e.id::text || ':' || coalesce(s.generation::text, 'none'), ',' ORDER BY e.id) "
            "FROM phone_extractions e LEFT JOIN phone_interpretation_state s ON s.extraction_id = e.id "
            "WHERE e.case_id = :c"), {"c": str(case_id)}).scalar()
    except Exception:  # noqa: BLE001 - the record says "not read" rather than failing the tool
        return None
    return value or None


# --------------------------------------------------------------------------------------------- one call's facts

def _int(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _flatten_terms(value) -> list[str]:
    if value is None or value == "" or value == []:
        return []
    if isinstance(value, (list, tuple)):
        return [t for v in value for t in _flatten_terms(v)]
    if isinstance(value, dict):
        return [t for v in value.values() for t in _flatten_terms(v)]
    return [str(value)]


def search_terms(name: str | None, args: dict[str, Any] | None) -> list[str]:
    """The words and identifiers a call searched for, from its parameters (a Cypher query is kept whole)."""
    args = args or {}
    terms: list[str] = []
    for key in TERM_ARGS:
        if key in args:
            terms.extend("%s: %s" % (key, t) for t in _flatten_terms(args.get(key)))
    if name == "run_readonly_cypher" and args.get("query"):
        terms = ["cypher: %s" % args["query"]]
    filters = args.get("filters")
    if isinstance(filters, dict):
        terms.extend("filter %s: %s" % (k, t) for k, v in filters.items() for t in _flatten_terms(v))
    return [sanitize_text(t)[:2000] for t in terms]


def _doc_ref(item: dict[str, Any]):
    """A document hit is one page of one file. It is cited or used only where that page is named (a doc:// link
    to the page, "<file>, p.N", or the chunk id); a mention of the file alone does not credit every page."""
    meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else item
    name = meta.get("file_name") or meta.get("doc_name") or meta.get("filename")
    if not name:
        return None
    page = meta.get("page_start") or meta.get("page") or meta.get("page_number")
    file_id = meta.get("evidence_file_id") or meta.get("doc_id")
    alts = [str(item["id"])] if item.get("id") else []
    if page not in (None, ""):
        ref = "%s#p%s" % (name, page)
        alts += ["%s, p.%s" % (name, page), "doc://%s/%s" % (quote(str(name), safe=""), page)]
        if file_id:
            alts.append("doc://%s/%s" % (file_id, page))
        label = "%s, p.%s" % (name, page)
    else:
        ref = str(name)
        alts += ["doc://%s" % quote(str(name), safe="")] + (["doc://%s" % file_id] if file_id else [])
        label = str(name)
    return "document", ref, alts, label


def item_ref(item: Any, *, data: dict[str, Any], list_key: str):
    """(kind, ref, alternative references, label) of one returned item, or None when it carries no identifier."""
    if not isinstance(item, dict):
        return None
    view = data.get("view") if str(data.get("schema") or "").startswith("loupe.agent.financial_ledger") else None
    label = next((str(item[k]) for k in ("name", "display_name", "title", "group_label", "account_label", "line",
                                         "label", "value") if item.get(k) not in (None, "")), "")
    if item.get("record_uid"):
        uid = str(item["record_uid"])
        return "phone_record", uid, ["rec://" + uid], label or (item.get("kind") or "phone record")
    if item.get("identity_key"):
        return "phone_identity", str(item["identity_key"]), [], label or str(item["identity_key"])
    for key in ("txn", "transaction_id", "payment_id"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            tid = value[len("txn://"):] if value.startswith("txn://") else value
            return "payment", tid, ["txn://" + tid], label
    if list_key == "chunks" or isinstance(item.get("metadata"), dict) and item["metadata"].get("doc_name"):
        return _doc_ref(item)
    if view in ("transactions", "excluded") and item.get("key"):
        alts = [str(item["ref_id"])] if item.get("ref_id") else []
        what = " → ".join(str(item.get(k)) for k in ("from_name", "to_name") if item.get(k))
        amount = item.get("amount") or item.get("amount_minor")
        return "payment", str(item["key"]), alts, " ".join(x for x in (str(item.get("date") or ""), what,
                                                                         str(amount or "")) if x).strip()
    if view == "groups" and item.get("group"):
        return "ledger_group", str(item["group"]), [], label
    if view == "coverage":
        period = item.get("period") if isinstance(item.get("period"), dict) else {}
        ref = period.get("id") or item.get("canonical_account_id") or item.get("account_id")
        return ("statement_period" if period.get("id") else "account", str(ref), [],
                " · ".join(str(item.get(k)) for k in ("holder", "bank") if item.get(k))) if ref else None
    if view == "incomplete" and item.get("id"):
        return "incomplete_record", str(item["id"]), [], label
    if isinstance(item.get("rec"), str) and item["rec"].startswith("rec://"):
        uid = item["rec"][len("rec://"):]
        return "phone_record", uid, [item["rec"]], label or (item.get("kind") or "phone record")
    if item.get("evidence_file_id") and (item.get("title") or item.get("filename")):
        # A document page from the case-wide search: one page of one file, named as the doc links name it.
        name, page, file_id = item.get("title") or item.get("filename"), item.get("page"), item["evidence_file_id"]
        if page not in (None, ""):
            return "document", "%s#p%s" % (name, page), [
                "%s, p.%s" % (name, page), "doc://%s/%s" % (quote(str(name), safe=""), page),
                "doc://%s/%s" % (file_id, page)], "%s, p.%s" % (name, page)
        return "document", str(name), ["doc://%s" % quote(str(name), safe=""), "doc://%s" % file_id], str(name)
    for key in ("key", "entity_key", "node_key"):
        if isinstance(item.get(key), str) and item[key].strip():
            return "entity", item[key], [], label
    if item.get("id") and str(data.get("schema") or "").startswith("loupe.agent.casework"):
        return "casework_entry", str(item["id"]), [], label
    return None


def returned_items(data: Any) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Every identified item in the result's top-level lists (and a single ``entity``), with its list and place,
    and the length of each list."""
    if not isinstance(data, dict):
        return [], {}
    items: list[dict[str, Any]] = []
    lengths: dict[str, int] = {}
    for key, value in data.items():
        if key == "entity" and isinstance(value, dict):
            found = item_ref(value, data=data, list_key=key)
            lengths[key] = 1
            if found:
                kind, ref, alts, label = found
                items.append(dict(kind=kind, ref=ref, alts=alts, label=sanitize_text(label)[:300],
                                  path=["data", key], position=0))
            continue
        if not isinstance(value, list) or not value or not all(isinstance(v, dict) for v in value):
            continue
        lengths[key] = len(value)
        for position, entry in enumerate(value):
            found = item_ref(entry, data=data, list_key=key)
            if found:
                kind, ref, alts, label = found
                items.append(dict(kind=kind, ref=ref, alts=alts, label=sanitize_text(label)[:300],
                                  path=["data", key], position=position))
    return items, lengths


def call_facts(name: str | None, args: dict[str, Any] | None, output: dict[str, Any] | None,
               model_payload: dict[str, Any] | None) -> dict[str, Any]:
    """What one tool call returned, as the run record stores it."""
    output = output if isinstance(output, dict) else {}
    data = output.get("data")
    d = data if isinstance(data, dict) else {}
    page_read = name == PAGE_TOOL
    # A page read returns items of an earlier result: they are that result's items (shown, not new), so they are
    # not listed again here; its own paging note sits in its data.
    items, lengths = ([], {}) if page_read else returned_items(d)
    total = _int(d.get("total_matching"))
    if total is None:
        total = _int(d.get("total"))
    returned = _int(d.get("returned"))
    if returned is None and lengths:
        main = max(lengths, key=lambda k: lengths[k])
        returned = lengths[main]
    if returned is None and isinstance(data, list):
        returned = len(data)
    notes = (model_payload or {}).get("_paging") or (d.get("_paging") if page_read else None) or []
    paging = [to_jsonable(note) for note in notes if isinstance(note, dict)]
    next_page: dict[str, Any] = {}
    if _int(d.get("next_offset")) is not None:
        next_page["tool"] = {"offset": _int(d.get("next_offset")), "revision": d.get("revision")}
    model_next = [note["next_page"] for note in paging if isinstance(note.get("next_page"), dict)]
    if model_next:
        next_page["model"] = model_next
    # A call that raised (status set by the runner) or returned an error searched nothing.
    available = output.get("status") != "error" and d.get("available") is not False and not d.get("error")
    coverage = d.get("coverage") if isinstance(d.get("coverage"), dict) else {}
    exclusions = None
    if coverage.get("exclusions") or coverage.get("excluded_scope_rows") or coverage.get("incomplete_records"):
        exclusions = {k: coverage.get(k) for k in ("excluded_scope_rows", "exclusions", "incomplete_records",
                                                   "registered_accounts_without_statement_periods") if k in coverage}
    listed = items[:MAX_ITEMS_PER_CALL]
    return to_jsonable({
        "schema": d.get("schema"),
        "category": category_of(name),
        "total": total,
        "returned": returned,
        "next_page": next_page or None,
        "ledger_revision": d.get("ledger_revision"),
        "page_revision": d.get("revision"),
        "offset": _int(d.get("offset")),
        "phone_generation": output.get("phone_generation"),
        "search_terms": search_terms(name, args),
        "model_paging": paging,
        "available": available,
        "reason": None if available else (d.get("reason") or output.get("error") or d.get("error")),
        "reason_code": d.get("reason_code"),
        "not_in_case": bool(d.get("not_in_case")),
        "withheld": d.get("withheld"),
        "exclusions": exclusions,
        "list_lengths": lengths,
        "items": listed,
        "items_not_listed": max(0, len(items) - len(listed)),
        # Returned entries the record cannot follow (no identifier): counted and stated, never silently absent.
        "items_without_id": sum(max(0, n - sum(1 for i in items if i["path"] == ["data", key]))
                                for key, n in lengths.items() if key in ITEM_LISTS),
        "result_id": output.get("result_id"),
    })


# --------------------------------------------------------------------------------------------- the whole run

def unrun_tool_calls(messages: list[Any] | None) -> list[dict[str, Any]]:
    """Calls the model asked for that never ran (the tool budget stopped them): an assistant tool call with no
    tool message answering it."""
    answered = {getattr(m, "tool_call_id", None) for m in messages or [] if getattr(m, "type", "") == "tool"}
    unrun = []
    for message in messages or []:
        for call in getattr(message, "tool_calls", None) or []:
            if call.get("id") not in answered:
                unrun.append({"name": call.get("name"), "arguments": to_jsonable(call.get("args") or {}),
                              "search_terms": search_terms(call.get("name"), call.get("args"))})
    return unrun


def _shown_ranges(seq: int, facts: dict[str, Any], trace: list[dict[str, Any]]) -> dict[tuple, list[tuple[int, int]]]:
    """Per list path, the ranges of positions put before the model: the first message, then every page read."""
    ranges: dict[tuple, list[tuple[int, int]]] = {}
    for note in facts.get("model_paging") or []:
        if note.get("path") is not None and _int(note.get("returned")) is not None:
            ranges.setdefault(tuple(note["path"]), []).append((int(note.get("offset") or 0),
                                                               int(note.get("offset") or 0) + int(note["returned"])))
    result_id = facts.get("result_id")
    if not result_id:
        return ranges
    for later in trace[seq:]:
        if later.get("name") != PAGE_TOOL or (later.get("arguments") or {}).get("result_id") != result_id:
            continue
        for note in (later.get("record") or {}).get("model_paging") or []:
            if note.get("path") is not None and _int(note.get("returned")) is not None:
                ranges.setdefault(tuple(note["path"]), []).append(
                    (int(note.get("offset") or 0), int(note.get("offset") or 0) + int(note["returned"])))
    return ranges


def _mentions(text: str, ref: str) -> bool:
    """``ref`` appears in ``text`` as a whole reference: not as the start of a longer one ("doc://f.pdf/1" is not
    named by "doc://f.pdf/12"; "john-smith" is not named by "john-smith-jr")."""
    if not ref or ref not in text:
        return False
    return re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(ref), text) is not None


def _covered(ranges: list[tuple[int, int]]) -> int:
    covered, end = 0, -1
    for start, stop in sorted(ranges):
        start = max(start, end)
        if stop > start:
            covered += stop - start
            end = stop
    return covered


def _continuation_key(call: dict[str, Any]) -> str:
    args = {k: v for k, v in (call.get("arguments") or {}).items() if k not in CONTINUATION_ARGS}
    return json.dumps([call.get("name"), args], sort_keys=True, default=str)


def examine(trace: list[dict[str, Any]], *, answer: str | None, artifacts: list[dict[str, Any]] | None,
            unrun: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Opened, cited and used in an artifact, per returned item; clipped material per call. Pure code."""
    answer_text = answer or ""
    artifact_text = json.dumps(to_jsonable(artifacts or []), ensure_ascii=False)
    later_args = [json.dumps(to_jsonable(call.get("arguments") or {}), ensure_ascii=False) for call in trace]
    rows: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    groups: dict[str, dict[str, Any]] = {}
    for index, call in enumerate(trace):
        seq = index + 1
        facts = call.get("record") or {}
        ranges = _shown_ranges(seq, facts, trace)
        for item in facts.get("items") or []:
            refs = [r for r in [item.get("ref"), *(item.get("alts") or [])] if r and len(str(r)) >= MIN_REF_CHARS]
            path = tuple(item.get("path") or ())
            shown = (not ranges.get(path)) or any(a <= int(item.get("position") or 0) < b for a, b in ranges[path])
            opened_by = None
            for later_index in range(index + 1, len(trace)):
                # A page read shows items (shown_to_model); an artifact builder uses them (in_artifact).
                if trace[later_index].get("name") == PAGE_TOOL or str(trace[later_index].get("name") or "").startswith(
                        "build_"):
                    continue
                if any(_mentions(later_args[later_index], str(r)) for r in refs):
                    opened_by = later_index + 1
                    break
            cited = any(_mentions(answer_text, str(r)) for r in refs)
            rows.append(dict(tool_call_sequence=seq, kind=item.get("kind"), ref=item.get("ref"),
                             label=item.get("label"), list_path=".".join(map(str, path)),
                             position=item.get("position"), shown_to_model=bool(shown),
                             opened=opened_by is not None, opened_by_sequence=opened_by, cited=cited,
                             in_artifact=any(_mentions(artifact_text, str(r)) for r in refs)))
        model_not_shown = 0
        for note in facts.get("model_paging") or []:
            if note.get("path") is None or _int(note.get("total")) is None:
                continue
            seen = _covered(ranges.get(tuple(note["path"]), []))
            model_not_shown += max(0, int(note["total"]) - seen)
        entry = dict(sequence=seq, name=call.get("name"), model_not_shown=model_not_shown, tool_not_returned=0,
                     continuation_of=None)
        total = _int(facts.get("total"))
        if total is not None and _int(facts.get("returned")) is not None and call.get("name") != PAGE_TOOL:
            key = _continuation_key(call)
            offset = int(facts.get("offset") or 0)
            group = groups.get(key)
            if group is None or group["total"] != total:
                group = groups[key] = dict(first=entry, total=total, ranges=[])
            else:
                entry["continuation_of"] = group["first"]["sequence"]
            group["ranges"].append((offset, offset + int(facts["returned"])))
            group["first"]["tool_not_returned"] = max(0, total - _covered(group["ranges"]))
        calls.append(entry)
    return {"items": rows, "calls": calls, "unrun": list(unrun or [])}


def record_summary(items: list[dict[str, Any]], calls: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "items_returned": len(items),
        "items_shown": sum(1 for r in items if r["shown_to_model"]),
        "items_opened": sum(1 for r in items if r["opened"]),
        "items_cited": sum(1 for r in items if r["cited"]),
        "items_in_artifact": sum(1 for r in items if r["in_artifact"]),
        "items_not_examined": sum(1 for r in items if not (r["opened"] or r["cited"] or r["in_artifact"])),
        "items_not_shown": sum(1 for r in items if not r["shown_to_model"]),
        "model_not_shown": sum(c["model_not_shown"] for c in calls),
        "tool_not_returned": sum(c["tool_not_returned"] for c in calls),
    }


# --------------------------------------------------------------------------------------------- persistence

def persist_call_facts(db, *, run, trace: list[dict[str, Any]], answer: str | None,
                       artifacts: list[dict[str, Any]] | None, messages: list[Any] | None = None,
                       budget_exhausted: bool = False) -> dict[str, int]:
    """Store the per-call columns, the per-item rows and the run's budget for one finished (or stopped) run."""
    from postgres.models.agent import AgentRunItem, AgentToolCall

    unrun = unrun_tool_calls(messages) if messages is not None else []
    result = examine(trace, answer=answer, artifacts=artifacts, unrun=unrun)
    by_seq = {c.sequence_number: c for c in db.query(AgentToolCall).filter(AgentToolCall.run_id == run.id)}
    for entry, call in zip(result["calls"], trace):
        record = by_seq.get(entry["sequence"])
        facts = call.get("record") or {}
        if record is None:
            continue
        apply_facts(record, facts)
        record.model_not_shown = entry["model_not_shown"]
        record.tool_not_returned = entry["tool_not_returned"]
        record.continuation_of = entry["continuation_of"]
    db.query(AgentRunItem).filter(AgentRunItem.run_id == run.id).delete(synchronize_session=False)
    for row in result["items"]:
        db.add(AgentRunItem(run_id=run.id, **{k: (sanitize_text(v)[:500] if isinstance(v, str) else v)
                                              for k, v in row.items()}))
    summary = record_summary(result["items"], result["calls"])
    run.tool_calls_used = len(trace)
    run.unrun_tool_calls = to_jsonable(unrun) or None
    run.record_summary = to_jsonable({**summary, "budget_exhausted": bool(budget_exhausted),
                                      "items_not_listed": sum(int((c.get("record") or {}).get("items_not_listed")
                                                                  or 0) for c in trace)})
    db.flush()
    return summary


def apply_facts(record, facts: dict[str, Any]) -> None:
    """The columns of one stored tool call, from its facts."""
    record.total = _int(facts.get("total"))
    record.returned = _int(facts.get("returned"))
    record.next_page = facts.get("next_page")
    record.ledger_revision = (str(facts["ledger_revision"])[:64] if facts.get("ledger_revision") else None)
    record.page_revision = (str(facts["page_revision"])[:64] if facts.get("page_revision") else None)
    record.phone_generation = facts.get("phone_generation")
    record.search_terms = facts.get("search_terms") or None
    record.model_paging = facts.get("model_paging") or None
    record.record_facts = {k: facts.get(k) for k in ("schema", "category", "available", "reason", "reason_code",
                                                     "not_in_case", "withheld", "exclusions", "list_lengths",
                                                     "items_not_listed", "items_without_id", "offset",
                                                     "result_id")}


# --------------------------------------------------------------------------------------------- earlier runs

PREVIEW_BASIS = ("Rebuilt from the stored result previews of a run made before the run record: each list was "
                 "stored cut to its first 25 items, so later items and what the model was shown are not known; "
                 "the prompt version and tool budget were not recorded.")


def backfill_run(db, run) -> dict[str, Any] | None:
    """The record of a run made before the run record, from what it stored, through the same path as a new run.
    Returns None when the run already has a record."""
    from postgres.models.agent import AgentToolCall
    from postgres.models.user import User

    if run.record_summary is not None:
        return None
    calls = db.query(AgentToolCall).filter(AgentToolCall.run_id == run.id).order_by(AgentToolCall.sequence_number).all()
    # Made with the run record: it has a prompt version, or its label says the version could not be read then.
    if run.prompt_version is not None or (run.prompt_version_label or "").startswith("not recorded:"):
        # Made with the run record but never finished (the process ended): its calls were stored whole as they
        # ran and are kept as they are; only the summary is added, saying what is not known.
        run.tool_calls_used = len(calls)
        run.record_summary = {"items_returned": 0, "basis": (
            "The run did not finish (the process ended while it ran). Its tool calls were stored as they ran and "
            "are shown as stored; which returned items it opened or cited was never computed.")}
        db.flush()
        return {"items_returned": 0}
    trace = []
    for call in calls:
        output = {"data": call.result_preview, "status": call.status, "error": call.error, "result_id": call.result_id}
        trace.append({"name": call.name, "arguments": call.arguments or {},
                      "record": call_facts(call.name, call.arguments, output, None)})
    artifacts = [{"data": a.payload, "metadata": a.extra_metadata} for a in run.artifacts]
    if run.user_id and not run.for_user_email:
        user = db.get(User, run.user_id)
        if user is not None:
            run.for_user_name = (getattr(user, "name", None) or "")[:255] or None
            run.for_user_email = (getattr(user, "email", None) or "")[:255] or None
    if not run.prompt_version_label:
        run.prompt_version_label = "not recorded (run made before the run record)"
    summary = persist_call_facts(db, run=run, trace=trace, answer=run.final_answer, artifacts=artifacts,
                                 messages=None)
    basis = PREVIEW_BASIS
    if not calls and run.status in ("running", "failed", "cancelled"):
        basis += (" The run did not finish normally and its tool calls were not stored at the time, so what it "
                  "searched is not known.")
    run.record_summary = {**(run.record_summary or {}), "basis": basis}
    db.flush()
    return summary


def main(argv=None) -> int:
    """``python -m services.agent.run_record --backfill [--apply]``: the record of every earlier run (dry run
    by default: reports and rolls back)."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill", action="store_true", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rebuild", action="store_true",
                        help="recompute the records already rebuilt from previews (after a change to the rules)")
    args = parser.parse_args(argv)
    from postgres.models.agent import AgentRun, AgentRunItem
    from postgres.session import _get_session_local

    done = skipped = items = 0
    with _get_session_local()() as db:
        for run in db.query(AgentRun).order_by(AgentRun.started_at).all():
            basis = (run.record_summary or {}).get("basis") or ""
            if args.rebuild and run.prompt_version is None and basis.startswith(PREVIEW_BASIS[:60]):
                db.query(AgentRunItem).filter(AgentRunItem.run_id == run.id).delete(synchronize_session=False)
                run.record_summary = None
            summary = backfill_run(db, run)
            if summary is None:
                skipped += 1
                continue
            done += 1
            items += summary["items_returned"]
        print(json.dumps({"runs_backfilled": done, "runs_with_record": skipped, "items_recorded": items,
                          "applied": bool(args.apply)}))
        if args.apply:
            db.commit()
        else:
            db.rollback()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
