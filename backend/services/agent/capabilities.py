"""What the case agent can work with: one registry of data types, used by the agent's help ("What can I ask?"),
by ``GET /api/agent/capabilities`` and by the coverage tests and live coverage check
(``scripts/agent_coverage_eval.py``).

Each data type has a plain label and description for the screen (no tool names, no internal words), example
questions an investigator can ask, and the tools that read it. A tool that reads case material belongs to at least
one type; the tools that build views, ask back, read a page of an earlier result, propose work for a person or read
other cases are listed in ``SUPPORT_TOOLS``. ``tests/test_agent_capabilities.py`` fails when a bound tool is in
neither, or a type names a tool that is not bound.

This module imports nothing from the app, so the live coverage script can read it without the backend's
dependencies.
"""
from __future__ import annotations

from typing import Any

SCHEMA = "loupe.agent.capabilities/1"

DATA_TYPES: list[dict[str, Any]] = [
    {
        "id": "financials",
        "label": "Bank statements and payments",
        "description": "The payments read from the case's bank and brokerage statements: totals per currency, "
                       "accounts and the dates their statements cover, money between two parties, connected "
                       "payments, trades and holdings.",
        "examples": [
            "What is the largest payment out of this case's accounts?",
            "Which accounts have statements, and over what dates?",
            "How much money moved between these two companies?",
        ],
        "tools": ["get_financial_transactions", "analyze_financial_transactions", "get_financial_coverage",
                  "get_money_between", "get_statement_continuity", "get_account_mentions", "get_trades",
                  "find_connected_payments", "get_transfer_pairs", "get_payment_other_legs"],
    },
    {
        "id": "phones",
        "label": "Phones",
        "description": "The case's phone extractions: messages and calls, contacts, places the phones recorded, "
                       "money the phones mention, when people were together or apart, and a person's numbers "
                       "and accounts.",
        "examples": [
            "How many messages are there between these two people?",
            "Who does this phone contact most?",
            "Where was the phone on this day?",
        ],
        "tools": ["phone_find_people", "phone_messages", "phone_contact_summary", "phone_coverage", "phone_places",
                  "phone_money_readings", "phone_colocation_results", "phone_record", "get_person_phones",
                  "get_day_activity", "get_together_apart", "get_routine_deviations", "get_phone_map_summary",
                  "get_contact_and_money_between", "get_money_signal_matches", "get_money_signal_leads",
                  "evaluate_statement", "get_analysis_results", "get_monitoring_app_indicators", "get_glossary",
                  "get_near_identical_pictures", "get_payment_conversation", "draft_payment_purpose",
                  "draft_control_claim", "get_identity_suggestions"],
    },
    {
        "id": "graph",
        "label": "People, companies and connections",
        "description": "The case graph: people, companies, accounts and events, how they are connected, and "
                       "the paths between two of them.",
        "examples": [
            "Who are the directors of this company?",
            "How is this person connected to that company?",
            "How many people are in the case?",
        ],
        "tools": ["get_case_overview", "search_graph_entities", "inspect_graph_schema", "get_entity_details",
                  "get_entity_neighborhood", "find_paths_between_entities", "run_readonly_cypher"],
    },
    {
        "id": "timeline",
        "label": "Timeline",
        "description": "Dated events in order, with the investigators' own additions to the timeline.",
        "examples": [
            "What happened on this date?",
            "What is the earliest event in the case?",
            "What happened in the month before this payment?",
        ],
        "tools": ["get_timeline_events"],
    },
    {
        "id": "map",
        "label": "Map",
        "description": "Places on the case map and what happened at each of them.",
        "examples": [
            "Which places are on the map?",
            "What happened in this city?",
            "How many mapped places are in this country?",
        ],
        "tools": ["get_map_locations"],
    },
    {
        "id": "documents",
        "label": "Documents and passages",
        "description": "The text of the case's documents: passages by meaning, exact words, and a search of "
                       "everything in the case at once.",
        "examples": [
            "Which documents mention this company?",
            "Find the exact words of this reference.",
            "What does this statement say the closing balance was?",
        ],
        "tools": ["search_documents", "search_exact_words", "search_case"],
    },
    {
        "id": "interviews",
        "label": "Interviews and transcripts",
        "description": "Interviews recorded on dossiers (who took part, when, the notes and the files attached) "
                       "and transcripts of the case's recordings with their review state.",
        "examples": [
            "Which interviews are recorded, and who was interviewed?",
            "What files are attached to this interview?",
            "Is there a transcript of this recording, and has a person reviewed it?",
        ],
        "tools": ["get_interviews", "get_transcript"],
    },
    {
        "id": "evidence_files",
        "label": "Evidence files and their processing",
        "description": "The files in the case: how many, which are processed, waiting or failed (and why), "
                       "copies of another file, and files held back from reading.",
        "examples": [
            "How many files are still waiting to be processed?",
            "Which files failed, and why?",
            "Has this file been processed?",
        ],
        "tools": ["get_evidence_files"],
    },
    {
        "id": "dossiers",
        "label": "Dossiers",
        "description": "The case's dossiers on people and organisations: what each holds, its links, its "
                       "assessments and how each was made.",
        "examples": [
            "Which dossiers are there?",
            "What does the dossier on this person hold?",
            "Which assessments were written by a model?",
        ],
        "tools": ["list_dossiers", "get_dossier"],
    },
    {
        "id": "theories",
        "label": "Theories and what was added to them",
        "description": "The case's theories, everything added to each (records, selections, answers) with who "
                       "added it and why, and the narratives written on them, by a person or a model.",
        "examples": [
            "What theories are there?",
            "What has been added to this theory, and by whom?",
            "Which evidence contradicts this theory?",
        ],
        "tools": ["get_theory", "get_casework"],
    },
    {
        "id": "significant",
        "label": "Significant layer",
        "description": "The items marked significant in this case: what they are, who added them, how and when. "
                       "Questions can also be asked inside the Significant layer only.",
        "examples": [
            "What is in the Significant layer?",
            "Is this person marked significant?",
            "Which banks are in the Significant layer?",
        ],
        "tools": ["get_significant_layer"],
    },
    {
        "id": "findings",
        "label": "Findings, observations and notes",
        "description": "Findings, observations, open questions and notes in the casework, each with what is "
                       "linked to it.",
        "examples": [
            "What findings are recorded?",
            "Which observations are still open?",
            "What does this finding rest on?",
        ],
        "tools": ["get_casework"],
    },
    {
        "id": "decisions",
        "label": "Decisions and judgement calls",
        "description": "Judgement calls a person confirms or corrects, and the recorded decisions on records: who "
                       "made each, and which were drafted by a model.",
        "examples": [
            "How many judgement calls are still open?",
            "Who made the decisions on this account?",
            "Which decisions were drafted by a model?",
        ],
        "tools": ["get_judgement_calls", "get_decisions"],
    },
    {
        "id": "reports",
        "label": "Reports",
        "description": "Saved financial reports and what the casework report would hold if it were exported now.",
        "examples": [
            "What saved reports are there?",
            "What would the casework report contain?",
            "What does this saved report say?",
        ],
        "tools": ["get_reports"],
    },
]

# Tools that do not read a kind of case material: they build views, ask back, read the rest of an earlier result,
# propose work for a person to accept, or read other cases (only when the person switches that on).
SUPPORT_TOOLS: dict[str, str] = {
    "request_clarification": "asks the person a question",
    "read_tool_result_page": "reads the rest of an earlier result",
    "build_graph_artifact": "builds a view", "build_table_artifact": "builds a view",
    "build_table_artifact_from_rows": "builds a view", "build_chart_artifact": "builds a view",
    "build_report_artifact": "builds a view", "build_map_artifact": "builds a view",
    "plan_theory_sweep": "proposes work", "propose_counter_arguments": "proposes work",
    "propose_judgement_call": "proposes work", "propose_workspace_entry": "proposes work",
    "propose_lead_card": "proposes work", "propose_timeline_addition": "proposes work", "propose_link": "proposes work",
    "propose_control_claim": "proposes work", "propose_payment_purpose": "proposes work",
    "propose_claim": "proposes work", "propose_entity": "proposes work", "propose_glossary_term": "proposes work",
    "propose_assumption": "proposes work",
    "identifier_in_other_cases": "reads other cases", "list_my_cases": "reads other cases",
    "find_identifier_across_cases": "reads other cases", "read_in_case": "reads other cases",
}

BY_ID = {t["id"]: t for t in DATA_TYPES}


def types_for_tool(name: str) -> list[str]:
    return [t["id"] for t in DATA_TYPES if name in t["tools"]]


def tools_for_type(type_id: str) -> list[str]:
    return list(BY_ID[type_id]["tools"])


def capabilities(bound_tools: list[str] | None = None) -> dict[str, Any]:
    """The help as the screen shows it: plain labels, descriptions and examples, never tool names. With the bound
    tool names, a type none of whose tools is bound is left out (it cannot be asked about on this server)."""
    bound = set(bound_tools) if bound_tools is not None else None
    types = []
    for t in DATA_TYPES:
        if bound is not None and not bound.intersection(t["tools"]):
            continue
        types.append({"id": t["id"], "label": t["label"], "description": t["description"],
                      "examples": list(t["examples"])})
    return {"schema": SCHEMA, "types": types, "total": len(types),
            "note": "Ask in your own words. Every answer cites the records it rests on; what the agent could not "
                    "read is said in the answer."}
