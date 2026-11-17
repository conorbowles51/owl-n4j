"""One result shape for every agent read tool (lx-agenttools D19, plan R4).

A read tool's result says, beside its data, how complete it is: the ``total`` the tool counted, how many it
``shown``, where the ``next`` page is, what was ``searched``, what was ``not_searched``, and, when nothing came
back, ``why_empty`` with what to try. The model cannot tell a real absence from a bad search without these.

``AgentToolContext.result`` applies it to every tool, so no tool can skip it. Search tools (``SEARCH_OWNED``) are
shaped by the case-search service and keep their own; tools that act (build, propose, record) are in ``ACTIONS``.
A tool in neither list needs an entry in ``READS``: ``tests/test_agent_result_shape.py`` fails for a new tool without
one, and for an entry whose tool no longer exists.
"""
from typing import Any

SHAPE_KEY = "result_shape"

# Searched by the case-search service (lx-casesearch) or the agent-quick tools: they state their own shape.
SEARCH_OWNED = frozenset({
    "search_graph_entities", "search_documents", "search_exact_words", "search_case", "search_by_meaning",
    "phone_messages", "phone_find_people", "get_financial_transactions",
})

# Tools that build, propose, record or navigate rather than read the case: no completeness to state.
ACTIONS = frozenset({
    "request_clarification", "build_graph_artifact", "build_table_artifact", "build_table_artifact_from_rows",
    "build_chart_artifact", "build_report_artifact", "build_map_artifact", "create_artifact", "revise_artifact",
    "edit_report_sections", "append_artifact_rows", "calculate_artifact_data", "inspect_artifact_export",
    "propose_relation_hypotheses", "plan_theory_sweep", "propose_counter_arguments", "propose_judgement_call",
    "propose_workspace_entry", "propose_dossier_change", "propose_lead_card", "propose_timeline_addition",
    "propose_link", "propose_control_claim", "propose_payment_purpose", "propose_claim", "propose_entity",
    "propose_glossary_term", "propose_assumption", "draft_control_claim", "draft_payment_purpose", "deep_mark",
    "deep_notebook_add", "record_working_notes", "read_tool_result_page",
})


def _r(searched: str, not_searched: str, empty: str) -> dict[str, str]:
    return {"searched": searched, "not_searched": not_searched, "empty": empty}


_PHONES_GAP = "The phones in the case may not cover that time or person (phone_coverage)."

READS: dict[str, dict[str, str]] = {
    "get_case_overview": _r("The case graph: entity and relationship counts, types, sample entities.",
                            "Documents, the ledger, phones and casework.",
                            "The graph holds no entities yet; documents may still hold material (search_documents)."),
    "inspect_graph_schema": _r("Labels, relationship types and properties in this case's graph.",
                               "Values beyond the samples.",
                               "No such label or relationship type in this case; call without filters to list them."),
    "get_entity_details": _r("One graph entity by exact key, with its immediate connections.",
                             "Other entities; the ledger and phones.",
                             "No entity has that exact key in this case; find the key with search_graph_entities."),
    "get_entity_neighborhood": _r("Graph connections around one exact key, to the depth asked.",
                                  "Entities beyond that depth; links held only in the ledger or phones.",
                                  "That key has no connections within the depth, or is not in this case."),
    "find_paths_between_entities": _r("Shortest graph paths between two exact keys, up to max_depth.",
                                      "Links held only in the ledger, phones or documents.",
                                      "No graph path within max_depth. That does not mean the two are unlinked: "
                                      "try get_contact_and_money_between."),
    "run_readonly_cypher": _r("Your query, run on this case's graph.", "Anything outside the graph.",
                              "The query matched no rows: check label and property names with inspect_graph_schema."),
    "get_timeline_events": _r("Graph events and the investigator's Timeline additions, within the type, date, people "
                              "and word filters given.",
                              "Phone messages, ledger payments and documents nobody added to the Timeline.",
                              "No event matches the filters given; loosen the dates, people or words."),
    "get_money_between": _r("Ledger payments between the two parties, by reviewed identity.",
                            "Money seen only in phone alerts (stated, never summed); names not linked to an identity.",
                            "No payment between them under the reviewed identities in that window; check "
                            "get_identity_suggestions or widen the dates."),
    "get_trades": _r("Trades and holdings read from the case's brokerage statements.",
                     "Bank ledger payments.",
                     "No trade matches; the case may hold no brokerage statement (get_financial_coverage)."),
    "get_judgement_calls": _r("Judgement calls recorded in the case, by subject, status and rule.",
                              "Judgements nobody has raised.", "None match that subject, status or rule; call without filters."),
    "get_decisions": _r("Decisions recorded on payments, statements, periods and accounts.",
                        "Changes made before decisions were recorded.",
                        "No decision is recorded for that subject; none may have been made."),
    "get_statement_continuity": _r("One account's saved statement periods.", "The payments on them.",
                                   "That account has no saved statement period, or no account has that id."),
    "get_account_mentions": _r("Description and counterparty text of admitted ledger payments.",
                               "Statement text, phone messages, documents; numbers printed without a label.",
                               "No labelled account number matches; see why_empty."),
    "find_connected_payments": _r("This case's ledger, for the one payment given.", "Other cases; phone records.",
                                  "No possible other side in this case's ledger; it may sit in a statement not yet loaded."),
    "analyze_financial_transactions": _r("Every ledger payment matching the filters, grouped.",
                                         "Payments outside the filters; phone alerts.",
                                         "No payment matches the filters; check get_financial_coverage."),
    "get_financial_coverage": _r("Registered accounts and statement periods.", "The content of payments.",
                                 "No account or period matches, or no financial material is loaded."),
    "phone_contact_summary": _r("One person's messages and calls on every phone of the case.",
                                "Identities not linked to that person.",
                                "No messages or calls found. The person may be on the phones under an identity not "
                                "linked to them: try get_person_phones or phone_find_people."),
    "phone_coverage": _r("The phones of the case.", "Their contents.", "No phone extraction is loaded in this case."),
    "phone_places": _r("Location points recorded on the phones, within the window.",
                       "Places from documents or the ledger.", "No phone recorded a location in that window. " + _PHONES_GAP),
    "phone_money_readings": _r("The last Money-on-the-phones run's readings of bank alerts, texts and emails.",
                               "Messages that run did not read.",
                               "No reading matches, or Money on the phones has not been run."),
    "phone_colocation_results": _r("Together-and-apart runs saved in this case.", "Pairs nobody ran.",
                                   "No run is saved; get_together_apart makes one."),
    "phone_record": _r("One phone record by id or rec:// link.", "Other records.", "No record has that id in this case."),
    "get_person_phones": _r("The phone identities linked to the person on People.",
                            "Identities nobody has linked to them.",
                            "No identity is linked to this person yet; try phone_find_people."),
    "get_day_activity": _r("One local day of a person's or phone's messages, calls, places and payments.",
                           "Other days; lanes switched off.", "Nothing recorded that day. " + _PHONES_GAP),
    "get_together_apart": _r("Two people's or phones' recorded positions in the window.",
                             "Positions the phones did not record.", "No positions to compare in that window. " + _PHONES_GAP),
    "get_period_activity": _r("Per-day counts and items for a person or phone over the period.",
                              "Days outside the period; lanes switched off.", "Nothing recorded in that period. " + _PHONES_GAP),
    "get_phone_company": _r("One phone or person against every other phone, or one, over the period.",
                            "Phones not in the case.", "No companion found in that period. " + _PHONES_GAP),
    "get_routine_deviations": _r("A person's or phone's routine places and the days that broke them.",
                                 "Days with no location record.", "Too few location records to set a routine. " + _PHONES_GAP),
    "get_phone_map_summary": _r("Location records on the phones, placed and not placed.", "The ledger and documents.",
                                "No location records on the phones in that window."),
    "get_contact_and_money_between": _r("Messages, calls and emails on every phone, and ledger money, between two people.",
                                        "Contact through identities not linked to either person.",
                                        "No contact or money found between them under their linked identities; link "
                                        "identities on People or check phone_find_people."),
    "get_money_signal_matches": _r("Phone alerts paired with ledger rows at any strength.", "Alerts the run did not read.",
                                   "No pairing matches the filters, or the Money run has not been made."),
    "get_money_signal_leads": _r("Accounts and periods the phones point to that the ledger lacks.", "Alerts without an account.",
                                 "No lead: the ledger holds every account and period the phones point to, or the run has not been made."),
    "evaluate_statement": _r("Confirmed statements checked against the phones.", "Statements nobody confirmed.",
                             "No confirmed statement to check; propose_claim drafts one for a person to confirm."),
    "get_analysis_results": _r("The last run of each phone analysis.", "Analyses never run.",
                               "That analysis has no saved result: it may not have been run on these phones."),
    "get_monitoring_app_indicators": _r("Installed apps checked against the monitoring-app list, and bank control notices.",
                                        "Apps not on the list.", "No indicator in that window. " + _PHONES_GAP),
    "get_glossary": _r("Code words a person confirmed.", "Words only a model proposed.",
                       "No confirmed code word; a person confirms them on the Glossary."),
    "get_near_identical_pictures": _r("Pictures on two phones that look nearly the same.", "Pictures on one phone only.",
                                      "No pair at that strength."),
    "get_payment_conversation": _r("Messages between the two people a payment is between, in the window around it.",
                                   "Messages outside the window; other channels.",
                                   "No messages between them in that window; widen hours or days."),
    "get_map_locations": _r("Geocoded graph entities.", "Entities with no place; phone points (get_phone_map_summary).",
                            "No mapped entity matches the types, keys or place given."),
    "get_casework": _r("Notes, findings and theories of the case.", "Dossiers and the graph.",
                       "No note, finding or theory matches the kinds, tag or words given."),
    "get_dossier": _r("One dossier by id or name.", "Other dossiers.",
                      "No dossier has that id or name; list_dossiers shows them."),
    "list_dossiers": _r("The case's dossiers.", "Archived ones unless asked.", "No dossier matches; none may exist."),
    "get_evidence_files": _r("The case's evidence files and their processing state.", "File contents.",
                             "No file matches that state or name."),
    "get_interviews": _r("Interviews recorded on dossiers, and recordings with a transcript.", "Interviews nobody recorded.",
                         "No interview recorded for that dossier."),
    "get_transcript": _r("One recording's transcript.", "Other recordings.", "That recording has no transcript."),
    "get_theory": _r("One theory by id or title words.", "Other theories.", "No theory matches; get_casework lists them."),
    "get_significant_layer": _r("Items in the Significant layer.", "Entities nobody marked significant.",
                                "Nothing is marked significant yet."),
    "get_reports": _r("Saved financial reports and the casework report's sections.", "Agent artifacts (list_artifacts).",
                      "No financial report is saved."),
    "get_transfer_pairs": _r("Possible transfers between the case's own accounts.", "Transfers to accounts outside the case.",
                             "No possible transfer between the case's accounts at that strength."),
    "get_payment_other_legs": _r("Other accounts of the case, for one payment.", "Accounts outside the case.",
                                 "No possible other leg in this case's accounts."),
    "get_identity_suggestions": _r("Phone identity suggestions.", "Identities with no suggestion.",
                                   "No suggestion at that strength."),
    "list_artifacts": _r("Artifacts saved in this conversation.", "Other conversations (read_saved_agent_work).",
                         "No artifact matches."),
    "read_artifact": _r("One saved artifact.", "Other artifacts.", "No artifact has that id in this conversation."),
    "get_case_configuration": _r("Title, description, status, background and mandate.", "Credentials and server settings.",
                                 "The case holds no description or mandate."),
    "get_document_text": _r("One evidence file's stored text, in pages.", "Other files; the image of the page.",
                            "That file has no stored text: it may not have been read yet."),
    "read_scope_with_model": _r("Every record of one phone window or one document, read by a model in chunks.",
                                "Other scopes; records beyond the stated limit.",
                                "No record in the scope bears on the question."),
    "read_conversation_history": _r("Earlier turns of this conversation.", "Other conversations.",
                                    "No earlier turn at that offset."),
    "read_prior_result": _r("One stored result of an earlier turn.", "Results never stored.", "No stored result has that id."),
    "get_case_work": _r("Case tasks, deadlines and pinned evidence.", "Items outside the kind asked.",
                        "No item of that kind."),
    "read_saved_agent_work": _r("Saved agent reports and artifacts across conversations.", "Other cases.",
                                "No saved work matches."),
    "get_relation_results": _r("The link analysis of one marked group.", "Groups nobody marked.",
                               "That group has no saved analysis."),
    "deep_checklist": _r("The run's coverage checklist.", "Work outside the checklist.", "No checklist item."),
    "deep_notebook_read": _r("The run's notebook.", "Notes the run did not keep.", "The notebook holds no note."),
    "identifier_in_other_cases": _r("Cases the person may open, for one identifier.", "Cases the person cannot open.",
                                    "No other case the person may open holds it."),
    "check_statements": _r("Each statement, searched against the case's records.", "Records not in this case.",
                           "No record supports or contradicts the statement."),
    "list_my_cases": _r("Cases the person may open.", "Other cases.", "The person has no case."),
    "find_identifier_across_cases": _r("Every case the person may open, for one identifier.", "Cases the person cannot open.",
                                       "No case the person may open holds it."),
    "read_in_case": _r("One record in one other case the person may open.", "Cases the person cannot open.",
                       "No such record in that case."),
}


def covered(name: str) -> bool:
    return name in SEARCH_OWNED or name in ACTIONS or name in READS


# Tools whose result is one record, not a list: total and shown are 1 unless the result counts something itself.
SINGLE = frozenset({
    "get_case_overview", "inspect_graph_schema", "get_entity_details", "get_entity_neighborhood",
    "get_case_configuration", "get_document_text", "read_scope_with_model", "identifier_in_other_cases", "read_prior_result", "read_artifact",
    "get_transcript", "get_theory", "get_dossier", "phone_record", "deep_checklist",
})
TOTAL_KEYS = ("total", "total_matching", "total_count")
LIST_KEYS = ("items", "events", "rows", "locations", "artifacts", "cases", "matches", "results", "periods")


def _first(data: dict, *keys: str) -> Any:
    for key in keys:
        if data.get(key) is not None:
            return data[key]
    return None


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _main_list(data: dict) -> list | None:
    for key in LIST_KEYS:
        if isinstance(data.get(key), list):
            return data[key]
    return None


def _next(data: dict) -> Any:
    found = _first(data, "next_page", "next_offset", "next_cursor", "next", "next_read")
    if found is not None:
        return found
    inner = data.get("investigator_additions")
    if isinstance(inner, dict) and inner.get("next_offset") is not None:
        return {"investigator_additions": inner["next_offset"]}
    return None


def shape_for(name: str, data: Any) -> dict[str, Any] | None:
    """The shape for a read tool's result data, or None for an action, a search tool or non-record data."""
    if name in SEARCH_OWNED or name in ACTIONS or not isinstance(data, dict):
        return None
    entry = READS.get(name)
    if entry is None:
        return None
    main = _main_list(data)
    shown = _count(_first(data, "returned", "count"))
    if shown is None:
        shown = len(main) if main is not None and name not in SINGLE else 1
    total = _count(_first(data, *TOTAL_KEYS))
    if total is None:
        total = shown
    shape = {
        "total": total,
        "shown": shown,
        "next": _next(data),
        "searched": data.get("searched") or entry["searched"],
        "not_searched": data.get("not_searched") or entry["not_searched"],
        "why_empty": None,
    }
    if total == 0 or (shown == 0 and name not in SINGLE):
        shape["why_empty"] = data.get("why_empty") or data.get("reason") or entry["empty"]
    return shape


def with_shape(name: str, data: Any, summary: str) -> tuple[Any, str]:
    """``data`` with its ``result_shape`` and, for an empty result, the reason in the summary the model reads first."""
    shape = shape_for(name, data)
    if shape is None:
        return data, summary
    if shape["why_empty"] and str(shape["why_empty"]) not in summary:
        summary = f"{summary} Nothing found: {shape['why_empty']}".strip()
    return {**data, SHAPE_KEY: shape}, summary
