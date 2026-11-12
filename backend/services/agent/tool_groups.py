"""The agent's tools in groups a person can read and switch (Neil, 12 Nov 2026: "show the user the tools being used and
give the user the opportunity to switch one on or off as the agent is processing").

Every tool ``make_agent_tools`` builds belongs to exactly one group (tests/test_agent_tool_steering.py fails on a tool
with no group). The "Always on" group is the agent's own bookkeeping (asking you a question, its notes, reading the
rest of a result it already has); it cannot be switched off, because a run without it cannot finish an answer.

A switch is stored on the run (``extra_metadata['steering']``, written by the web process) and read by the worker
before each model step (``read``/``apply``), so it applies from the next step; the running step finishes first. The
answer's "Not examined" names each group that was off, with the steps (``not_examined_lines``), so a narrowed answer
never reads as complete (rule 1).
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

ALWAYS_ON = "always"

GROUPS: tuple[dict[str, Any], ...] = (
    {"id": "money", "name": "Money and ledger", "about": "Statements, ledger rows, payments between people",
     "words": r"money|pa(y|id)|payments?|transfers?|ledger|statements? of account|bank|accounts?|deposits?|"
              r"withdraw\w*|cash|funds?|wire|cheques?|checks?|trades?|holdings?|usd|eur|gbp|\$|£|€|amounts?|"
              r"totals?|spent|received|sent|owed?|loan|invoice",
     "tools": ("get_money_between", "get_trades", "get_judgement_calls", "get_decisions", "get_statement_continuity",
               "get_account_mentions", "find_connected_payments", "get_financial_transactions",
               "analyze_financial_transactions", "get_financial_coverage", "get_transfer_pairs",
               "get_payment_other_legs", "draft_payment_purpose", "get_reports")},
    {"id": "phones", "name": "Phones", "about": "Messages, calls, payment alerts and apps on the phones",
     "words": r"phones?|devices?|messages?|texts?|sms|whatsapp|signal|telegram|calls?|called|chats?|"
              r"alerts?|apps?|contacts?|pictures?|photos?|extractions?",
     "tools": ("phone_messages", "phone_contact_summary", "phone_coverage", "phone_money_readings", "phone_record",
               "get_money_signal_matches", "get_money_signal_leads", "evaluate_statement", "get_analysis_results",
               "get_monitoring_app_indicators", "get_near_identical_pictures", "draft_control_claim",
               "get_payment_conversation", "get_day_activity")},
    {"id": "documents", "name": "Documents", "about": "Search and read documents, interviews and transcripts",
     "words": r"documents?|files?|proffers?|interviews?|transcripts?|reports?|letters?|emails?|pages?|"
              r"statements?|says?|said|claims?|wrote|written|contract|agreement|testimony|affidavit",
     "tools": ("search_documents", "search_exact_words", "get_document_text", "get_evidence_files", "get_interviews",
               "get_transcript", "search_case", "check_statements")},
    {"id": "people", "name": "People and identities", "about": "Who a name, number or account belongs to",
     "words": r"who|whom|whose|person|people|names?|identit\w*|owners?|belongs?|numbers?|same person|"
              r"dossiers?|between",
     "tools": ("phone_find_people", "get_person_phones", "get_identity_suggestions", "identifier_in_other_cases",
               "get_contact_and_money_between", "list_dossiers", "get_dossier")},
    {"id": "places", "name": "Map and places", "about": "Where phones and people were, and who was together",
     "words": r"where|places?|locations?|located|map|near|together|apart|with whom|nights?|evenings?|home|"
              r"addresses?|apartment|went|visited|travel\w*|routine|movements?",
     "tools": ("phone_places", "phone_colocation_results", "get_together_apart", "get_period_activity",
               "get_phone_company", "get_routine_deviations", "get_phone_map_summary", "get_map_locations")},
    {"id": "graph", "name": "Graph queries", "about": "Links between people, accounts and records in the case graph",
     "words": r"graph|links?|linked|connect\w*|relationships?|network|paths?|timeline|significant",
     "tools": ("get_case_overview", "search_graph_entities", "inspect_graph_schema", "get_entity_details",
               "get_entity_neighborhood", "find_paths_between_entities", "run_readonly_cypher",
               "get_timeline_events", "get_significant_layer")},
    {"id": "casework", "name": "Case notes and theories", "about": "Notes, findings, theories, tasks and the case set-up",
     "words": r"notes?|findings?|theor\w*|tasks?|deadlines?|mandate|glossary|code words?|casework|background",
     "tools": ("get_casework", "get_theory", "get_case_configuration", "get_case_work", "get_glossary",
               "plan_theory_sweep")},
    {"id": "outputs", "name": "Tables, charts and reports", "about": "Build and revise tables, charts, maps and reports",
     "words": r"tables?|charts?|diagrams?|draw|build|make|create|reports?|workbook|spreadsheet|slides?|"
              r"presentation|export|update|revise|summar\w*",
     "tools": ("build_graph_artifact", "build_table_artifact", "build_table_artifact_from_rows",
               "build_chart_artifact", "build_report_artifact", "build_map_artifact", "list_artifacts",
               "read_artifact", "create_artifact", "revise_artifact", "edit_report_sections", "append_artifact_rows",
               "calculate_artifact_data", "inspect_artifact_export", "read_saved_agent_work")},
    {"id": "proposals", "name": "Suggestions for the case", "about": "Drafts a person reviews before anything is saved",
     "words": r"propos\w*|suggest\w*|draft|record|add (it|them|this)|save",
     "tools": ("propose_counter_arguments", "propose_judgement_call", "propose_workspace_entry",
               "propose_dossier_change", "propose_lead_card", "propose_timeline_addition", "propose_link",
               "propose_control_claim", "propose_payment_purpose", "propose_claim", "propose_entity",
               "propose_glossary_term", "propose_assumption")},
    {"id": ALWAYS_ON, "name": "Always on", "about": "Asking you a question, its working notes, reading the rest of a result",
     "words": "",
     "tools": ("request_clarification", "record_working_notes", "read_tool_result_page", "read_conversation_history",
               "read_prior_result")},
)

BY_ID = {group["id"]: group for group in GROUPS}
GROUP_OF = {tool: group["id"] for group in GROUPS for tool in group["tools"]}
SWITCHABLE = tuple(group["id"] for group in GROUPS if group["id"] != ALWAYS_ON)
NOTE_MAX_CHARS = 500


def group_of(tool_name: str | None) -> str | None:
    return GROUP_OF.get(tool_name or "")


def catalogue() -> list[dict[str, Any]]:
    """The groups as the agent page lists them."""
    return [{"id": g["id"], "name": g["name"], "about": g["about"], "tools": list(g["tools"]),
             "switchable": g["id"] != ALWAYS_ON} for g in GROUPS]


def chosen_from_question(question: str) -> list[str]:
    """The groups whose words the question uses. Every group stays offered either way: this is what the card marks
    "Chosen from your question", not a limit on the agent."""
    text = (question or "").lower()
    out = []
    for group in GROUPS:
        if group["words"] and re.search(r"(?<![a-z])(?:" + group["words"] + r")(?![a-z])", text):
            out.append(group["id"])
    return out


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_entry(*, kind: str, user_id: str | None, group: str | None = None, on: bool | None = None,
              note: str | None = None) -> dict[str, Any]:
    """One request from the person: a switch ("switch", group, on) or a note to the agent ("note", note)."""
    if kind == "switch":
        if group not in SWITCHABLE:
            raise ValueError("That tool group cannot be switched: choose one of " + ", ".join(SWITCHABLE) + ".")
        return {"id": uuid.uuid4().hex, "kind": "switch", "group": group, "on": bool(on), "at": now_iso(),
                "by": user_id}
    if kind == "note":
        text = " ".join((note or "").split())
        if not text:
            raise ValueError("Write a note for the agent first.")
        if len(text) > NOTE_MAX_CHARS:
            raise ValueError(f"Keep the note under {NOTE_MAX_CHARS} characters (it has {len(text)}).")
        return {"id": uuid.uuid4().hex, "kind": "note", "note": text, "at": now_iso(), "by": user_id}
    raise ValueError("Unknown request: send a switch or a note.")


def off_groups(applied: Iterable[dict[str, Any]]) -> set[str]:
    """The groups off after the applied entries, in order (a later switch replaces an earlier one)."""
    off: set[str] = set()
    for entry in applied:
        if entry.get("kind") != "switch":
            continue
        (off.discard if entry.get("on") else off.add)(entry.get("group"))
    return off


def hidden_tools(applied: Iterable[dict[str, Any]]) -> frozenset[str]:
    off = off_groups(applied)
    return frozenset(tool for group_id in off for tool in BY_ID[group_id]["tools"])


def apply(requested: Iterable[dict[str, Any]], applied: list[dict[str, Any]], *, step: int) -> list[dict[str, Any]]:
    """Entries the person sent that the run has not taken yet, stamped with the step they arrived at (the last
    finished step) and the step they apply from. Appends them to ``applied`` and returns the new ones."""
    seen = {entry.get("id") for entry in applied}
    fresh = []
    for entry in requested or []:
        if not isinstance(entry, dict) or entry.get("id") in seen:
            continue
        stamped = {**entry, "step": int(step), "applies_from": int(step) + 1}
        applied.append(stamped)
        fresh.append(stamped)
    return fresh


def note_message(entry: dict[str, Any]) -> str:
    """The note as the agent reads it before its next step (the person's words, unchanged)."""
    return ("A note from the investigator, sent while you worked (after step " + str(entry.get("step", 0)) +
            "). Follow it for the rest of this answer where the records allow: " + str(entry.get("note") or ""))


def switch_message(fresh: list[dict[str, Any]]) -> str | None:
    """Tells the agent which groups were switched, so it plans without them (it is no longer offered them)."""
    lines = []
    for entry in fresh:
        if entry.get("kind") != "switch":
            continue
        name = BY_ID[entry["group"]]["name"]
        lines.append(f"{name}: switched {'on again' if entry.get('on') else 'off'} by the investigator after step "
                     f"{entry.get('step', 0)}" + ("" if entry.get("on") else
                     "; do not try to reach these records another way, and say in the answer that they were not "
                     "examined"))
    return ("Tool groups changed by the investigator. " + "; ".join(lines) + ".") if lines else None


def refusal(tool_name: str, applied: Iterable[dict[str, Any]]) -> str | None:
    """Why a call to a switched-off tool is not run (the model asked for it before the switch reached it)."""
    group_id = group_of(tool_name)
    if group_id is None or group_id not in off_groups(applied):
        return None
    step = next((e.get("step") for e in reversed(list(applied))
                 if e.get("kind") == "switch" and e.get("group") == group_id and not e.get("on")), None)
    return (f"Not run: the investigator switched off {BY_ID[group_id]['name']} after step {step}. Answer without "
            "these records and list them under Not examined.")


def trail_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """The trail line for one applied entry."""
    if entry.get("kind") == "note":
        title, result = "You sent a note to the agent", entry.get("note") or ""
    else:
        name = BY_ID.get(entry.get("group") or "", {}).get("name", entry.get("group"))
        title = ("You switched on " if entry.get("on") else "You switched off ") + str(name)
        result = ("The agent is offered these tools again." if entry.get("on")
                  else "The agent will not use these tools for the rest of this answer.")
    return {"id": entry.get("id"), "kind": entry.get("kind"), "group": entry.get("group"), "on": entry.get("on"),
            "note": entry.get("note"), "title": title, "result": result, "step": entry.get("step"),
            "applies_from": entry.get("applies_from"), "at": entry.get("at")}


def off_spans(applied: Iterable[dict[str, Any]], *, last_step: int) -> list[dict[str, Any]]:
    """Each stretch a group was off: from the step it applied from to the step it came back on (or the end)."""
    spans: list[dict[str, Any]] = []
    open_spans: dict[str, dict[str, Any]] = {}
    for entry in applied:
        if entry.get("kind") != "switch":
            continue
        group_id = entry.get("group")
        if not entry.get("on") and group_id not in open_spans:
            open_spans[group_id] = {"group": group_id, "name": BY_ID[group_id]["name"],
                                    "switched_at": entry.get("step"), "from": entry.get("applies_from"), "to": None}
            spans.append(open_spans[group_id])
        elif entry.get("on") and group_id in open_spans:
            open_spans.pop(group_id)["to"] = entry.get("step")
    for span in open_spans.values():
        span["to"] = None
        span["last_step"] = last_step
    return spans


def not_examined_lines(applied: Iterable[dict[str, Any]], *, last_step: int) -> list[str]:
    lines = []
    for span in off_spans(applied, last_step=last_step):
        if span["to"] is None:
            lines.append(f"{span['name']}: switched off by you at step {span['switched_at']}, so not examined "
                         f"from step {span['from']} on.")
        else:
            lines.append(f"{span['name']}: switched off by you at step {span['switched_at']} and on again at step "
                         f"{span['to']}, so not examined in steps {span['from']} to {span['to']}.")
    return lines


_NOT_EXAMINED_HEADING = re.compile(r"^(?:#{1,6}\s*|\*\*)?Not examined\b.*$", re.I | re.M)


def with_not_examined(answer: str, applied: Iterable[dict[str, Any]], *, last_step: int) -> str:
    """The answer with each switched-off group under "Not examined": under the answer's own heading when it has one,
    else in a new section at the end. Unchanged when nothing was switched off."""
    lines = not_examined_lines(list(applied), last_step=last_step)
    if not lines:
        return answer
    bullets = "\n".join(f"- {line}" for line in lines)
    match = _NOT_EXAMINED_HEADING.search(answer or "")
    if match:
        end = match.end()
        return answer[:end] + "\n" + bullets + answer[end:]
    return (answer.rstrip() + "\n\n" if answer and answer.strip() else "") + "**Not examined**\n" + bullets
