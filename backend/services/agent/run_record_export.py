"""Two exports of one agent run's record, on demand (report rank 3; AG Guidelines 2024 Annex A paras 47-48).

- **Strategy summary** (DMD-ready): who ran it and when, the model and prompt version, the tools and their result
  schema versions, every search with its parameters and terms, totals against returned, the ledger revision and phone
  generation read, and the exclusions the results stated.
- **What was not examined**: categories of case material the run did not search, items returned but not opened or
  cited, material clipped by paging (tool pages not read, model pages not read) or by the tool budget, material out
  of scope by case decision (the Significant layer, phone material withheld, refused calls), and phone record types
  Loupe does not yet read (the extraction coverage map, 02 section 7.2).

Both are built from the stored record only (``services.agent.run_record``), in CSV and PDF. Every count is computed
by code. Both state that replays on a hosted model are not deterministic.
"""
from __future__ import annotations

import csv
import html
import io
import json
import uuid
from collections import Counter
from typing import Any, Literal

from sqlalchemy import text

from services.agent.exports import AgentArtifactExport, _safe_filename
from services.agent.run_record import CATEGORY_LABELS, NOT_DETERMINISTIC, OTHER_CASES_LABEL, category_of

RecordExportKind = Literal["strategy", "not_examined"]
RecordExportFormat = Literal["csv", "pdf"]
UNREAD_PHONE_LEVELS = ("generic", "suspended")
ITEM_RULE = ("Counted by code from what the run did. Read further: a later tool call named the item. Cited: the "
             "answer names the item's identifier or link (a payment link or txn://, rec://, a doc:// page). Used: an "
             "artifact the run kept names it. An item the answer describes in words without its identifier or link "
             "is not counted as cited, so it is listed here as not examined.")


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _case_material(db, case_id) -> dict[str, dict[str, Any]]:
    """How much of each kind of material the case holds (counted now, at export)."""
    out: dict[str, dict[str, Any]] = {}
    queries = {
        "documents": "SELECT count(*) FROM evidence_files WHERE case_id = :c",
        "ledger": "SELECT count(*) FROM financial_transactions WHERE case_id = :c AND ledger_status = 'admitted'",
        "phones": "SELECT count(*) FROM phone_extractions WHERE case_id = :c",
        "casework": "SELECT count(*) FROM workspace_entries WHERE case_id = :c AND deleted_at IS NULL",
    }
    units = {"documents": "evidence files", "ledger": "admitted imported payments", "phones": "phone extractions",
             "casework": "casework entries"}
    for key, sql in queries.items():
        try:
            with db.begin_nested():
                out[key] = {"count": int(db.execute(text(sql), {"c": str(case_id)}).scalar() or 0), "unit": units[key]}
        except Exception:  # noqa: BLE001 - stated as not counted
            out[key] = {"count": None, "unit": units[key]}
    try:
        from services.neo4j.graph_service import graph_service
        summary = graph_service.get_graph_summary(str(case_id))
    except Exception:  # noqa: BLE001 - stated as not counted
        summary = None
    nodes = summary.get("total_nodes") if isinstance(summary, dict) else None
    out["graph"] = {"count": nodes, "unit": "graph entities"}
    for key in ("timeline", "map"):
        out[key] = {"count": None, "unit": "held in the case graph"}
    return out


def _unread_phone_types(db, case_id) -> list[dict[str, Any]]:
    """Per phone extraction, the record types no reviewed or applied mapping reads (coverage map, 02 7.2)."""
    rows: list[dict[str, Any]] = []
    try:
        extractions = [r[0] for r in db.execute(text("SELECT id FROM phone_extractions WHERE case_id = :c ORDER BY id"),
                                                 {"c": str(case_id)})]
    except Exception:  # noqa: BLE001
        return [{"extraction": None, "type": None, "records": None, "level": "not read",
                 "detail": "The phone coverage map could not be read for this export."}]
    from services.phone import coverage
    for extraction_id in extractions:
        try:
            with db.begin_nested():
                cov = coverage.compute(db.connection(), extraction_id, case_id=case_id)
        except Exception:  # noqa: BLE001
            rows.append({"extraction": str(extraction_id), "type": None, "records": None, "level": "not read",
                         "detail": "The coverage map of this extraction could not be read."})
            continue
        for t in cov.get("types") or []:
            if t.get("level") in UNREAD_PHONE_LEVELS and int(t.get("records") or 0) > 0:
                rows.append({"extraction": str(extraction_id), "type": t.get("type"), "records": int(t["records"]),
                             "level": t.get("level"),
                             "detail": ("suspended: " + json.dumps(t.get("suspension_reasons"), default=str))
                             if t.get("level") == "suspended" else "no mapping reads this type yet"})
    return rows


def _cases_read(db, run, metadata) -> list[dict[str, Any]]:
    """This run's own case, then every other case all-cases mode read (names read now, ids as stored)."""
    from postgres.models.case import Case

    stored = [c for c in metadata.get("cases_read") or [] if isinstance(c, dict) and c.get("case_id")]
    ids = [str(run.case_id)] + [str(c["case_id"]) for c in stored if str(c["case_id"]) != str(run.case_id)]
    out = []
    for cid in dict.fromkeys(ids):
        case = db.get(Case, uuid.UUID(cid))
        out.append({"case_id": cid, "case_name": getattr(case, "title", None), "this_case": cid == str(run.case_id)})
    return out


def load_record(db, run) -> dict[str, Any]:
    """The stored run record as one document (the run-record API and both exports read this)."""
    from postgres.models.agent import AgentPromptVersion, AgentRunItem
    from postgres.models.case import Case

    case = db.get(Case, run.case_id)
    prompt = db.get(AgentPromptVersion, run.prompt_version) if run.prompt_version else None
    items = (db.query(AgentRunItem).filter(AgentRunItem.run_id == run.id)
             .order_by(AgentRunItem.tool_call_sequence, AgentRunItem.position).all())
    calls = []
    for call in run.tool_calls:
        facts = call.record_facts or {}
        calls.append({
            "sequence": call.sequence_number, "name": call.name, "category": category_of(call.name),
            "arguments": call.arguments or {}, "search_terms": call.search_terms or [], "status": call.status,
            "error": call.error, "duration_ms": call.duration_ms, "summary": call.summary,
            "total": call.total, "returned": call.returned, "next_page": call.next_page,
            "ledger_revision": call.ledger_revision, "page_revision": call.page_revision,
            "phone_generation": call.phone_generation, "model_paging": call.model_paging or [],
            "model_not_shown": call.model_not_shown, "tool_not_returned": call.tool_not_returned,
            "continuation_of": call.continuation_of, "schema": facts.get("schema"),
            "available": bool(facts.get("available", True)) and call.status != "error",
            "reason": facts.get("reason") or call.error,
            "reason_code": facts.get("reason_code"), "not_in_case": facts.get("not_in_case"),
            "withheld": facts.get("withheld"), "exclusions": facts.get("exclusions"),
            "items_not_listed": facts.get("items_not_listed") or 0,
            "items_without_id": facts.get("items_without_id") or 0,
            "recorded": call.record_facts is not None,
        })
    metadata = run.extra_metadata or {}
    return {
        "schema": "loupe.agent.run_record/1",
        "run_id": str(run.id), "thread_id": str(run.thread_id), "case_id": str(run.case_id),
        "case_name": getattr(case, "title", None) or getattr(case, "name", None),
        "status": run.status, "question": run.input_message, "answer": run.final_answer, "error": run.error,
        "for_user": {"id": str(run.user_id) if run.user_id else None, "name": run.for_user_name,
                     "email": run.for_user_email},
        "started_at": _iso(run.started_at), "completed_at": _iso(run.completed_at),
        "provider": run.provider, "model_id": run.model_id,
        "prompt_version": run.prompt_version, "prompt_version_label": run.prompt_version_label,
        "prompt_first_used_at": _iso(prompt.first_used_at) if prompt else None,
        "tool_schema_count": prompt.tool_count if prompt else None,
        "tool_budget": run.tool_budget, "tool_calls_used": run.tool_calls_used if run.tool_calls_used is not None
        else len(calls),
        "unrun_tool_calls": run.unrun_tool_calls or [],
        "case_layer": metadata.get("case_layer") or "all",
        # All-cases mode (agent-allcases): off unless the person switched it on for this message; every case read.
        "all_cases": bool(metadata.get("all_cases")),
        "cases_read": _cases_read(db, run, metadata),
        "summary": run.record_summary or {},
        "recorded": run.prompt_version is not None or any(c["recorded"] for c in calls),
        "calls": calls,
        "items": [{"sequence": i.tool_call_sequence, "kind": i.kind, "ref": i.ref, "label": i.label,
                   "list": i.list_path, "position": i.position, "shown_to_model": i.shown_to_model,
                   "opened": i.opened, "opened_by_sequence": i.opened_by_sequence, "cited": i.cited,
                   "in_artifact": i.in_artifact} for i in items],
        "not_deterministic": NOT_DETERMINISTIC,
    }


# --------------------------------------------------------------------------------------------- statements

def _header_rows(record: dict[str, Any]) -> list[tuple[str, str]]:
    person = record["for_user"]
    return [
        ("Case", record.get("case_name") or record["case_id"]),
        ("Run", record["run_id"]),
        ("Run for", " ".join(x for x in (person.get("name"), "<%s>" % person["email"] if person.get("email") else None)
                             if x) or "not recorded"),
        ("Started (UTC)", record.get("started_at") or ""),
        ("Ended (UTC)", record.get("completed_at") or "not ended"),
        ("Status", record["status"]),
        ("Model", "%s / %s" % (record["provider"], record["model_id"])),
        ("Prompt version", ("%s (sha256 %s)" % (record["prompt_version_label"], record["prompt_version"]))
         if record.get("prompt_version") else (record.get("prompt_version_label")
                                               or "not recorded (run made before the run record)")),
        ("Tool calls used", "%s of %s" % (record["tool_calls_used"], record["tool_budget"] or "not recorded")),
        ("Scope", "Significant layer only (case decision for this run)" if record["case_layer"] == "significant"
         else ("All cases the person may open (all-cases mode, switched on for this message)"
               if record.get("all_cases") else "Whole case")),
        ("Cases read", "; ".join("%s%s" % (c.get("case_name") or c["case_id"], " (this case)" if c.get("this_case")
                                                                                else "")
                                 for c in record.get("cases_read") or []) or (record.get("case_name") or "")),
        ("Question", record.get("question") or ""),
        ("Reproducibility", NOT_DETERMINISTIC),
        ("How items are counted", ITEM_RULE),
    ] + ([("Basis of this record", record["summary"]["basis"])] if (record.get("summary") or {}).get("basis") else [])


def strategy_rows(record: dict[str, Any]) -> dict[str, Any]:
    searches = []
    for c in record["calls"]:
        searches.append({
            "#": c["sequence"], "tool": c["name"], "material": {**CATEGORY_LABELS, "other_cases": OTHER_CASES_LABEL}.get(c["category"] or "", "")
            or ("artifact or paging" if c["category"] is None else c["category"]),
            "result schema": c.get("schema") or "", "parameters": json.dumps(c["arguments"], ensure_ascii=False,
                                                                            default=str),
            "search terms": "; ".join(c["search_terms"]), "status": c["status"] if c["available"] else
            "refused: %s" % (c.get("reason") or c.get("error") or ""),
            "total": "" if c["total"] is None else c["total"], "returned": "" if c["returned"] is None else c["returned"],
            "next page": json.dumps(c["next_page"], default=str) if c["next_page"] else "",
            "continues call": c["continuation_of"] or "",
            "ledger revision": c["ledger_revision"] or "", "phone generation": c["phone_generation"] or "",
        })
    tools = Counter(c["name"] for c in record["calls"])
    versions = sorted({c["schema"] for c in record["calls"] if c.get("schema")})
    exclusions = []
    if record["case_layer"] == "significant":
        exclusions.append({"#": "", "exclusion": "Scope", "detail": "Only the Significant layer was searched; the "
                           "rest of the case was out of scope for this run."})
    for c in record["calls"]:
        if c.get("exclusions"):
            exclusions.append({"#": c["sequence"], "exclusion": "Ledger exclusions stated by %s" % c["name"],
                               "detail": json.dumps(c["exclusions"], ensure_ascii=False, default=str)})
        if c.get("withheld"):
            exclusions.append({"#": c["sequence"], "exclusion": "Withheld by case decision",
                               "detail": json.dumps(c["withheld"], ensure_ascii=False, default=str)})
    return {"header": _header_rows(record),
            "tools": [{"tool": name, "calls": n} for name, n in sorted(tools.items())],
            "versions": [{"result schema": v} for v in versions],
            "searches": searches, "exclusions": exclusions}


def not_examined_rows(record: dict[str, Any], *, material: dict[str, dict[str, Any]],
                      phone_types: list[dict[str, Any]]) -> dict[str, Any]:
    searched = {c["category"] for c in record["calls"] if c["category"] and c["available"]}
    categories = []
    for key, label in CATEGORY_LABELS.items():
        if key in searched or key == "case_search":  # case-wide search is a way of searching, not material
            continue
        held = material.get(key) or {}
        count = held.get("count")
        if count == 0:
            continue  # nothing of this kind in the case: nothing was left unsearched
        categories.append({"material": label, "held in case": "" if count is None else count,
                           "unit": held.get("unit") or "", "why": "No tool call of this run read it."})
    unopened = [i for i in record["items"] if not (i["opened"] or i["cited"] or i["in_artifact"])]
    not_shown = [i for i in unopened if not i["shown_to_model"]]
    hits = [{"#": i["sequence"], "kind": i["kind"], "item": i["label"] or i["ref"], "ref": i["ref"],
             "shown to model": "yes" if i["shown_to_model"] else "no (paged out, page not read)"} for i in unopened]
    clipped = []
    for c in record["calls"]:
        if c.get("tool_not_returned"):
            clipped.append({"#": c["sequence"], "tool": c["name"], "clipped by": "tool paging",
                            "items": c["tool_not_returned"],
                            "detail": "%s matching; the run read %s; the next page was not read." % (
                                c["total"], c["total"] - c["tool_not_returned"])})
        if c.get("model_not_shown"):
            clipped.append({"#": c["sequence"], "tool": c["name"], "clipped by": "model page (context budget)",
                            "items": c["model_not_shown"],
                            "detail": "Returned by the tool but not put before the model; no later page read."})
        if c.get("items_not_listed"):
            clipped.append({"#": c["sequence"], "tool": c["name"], "clipped by": "record listing limit",
                            "items": c["items_not_listed"],
                            "detail": "Returned items beyond the record's listing limit; counted, not listed."})
        if c.get("items_without_id"):
            clipped.append({"#": c["sequence"], "tool": c["name"], "clipped by": "not itemised",
                            "items": c["items_without_id"],
                            "detail": "Returned entries with no identifier the record can follow (rows of a "
                                      "custom query, groups, summaries): whether each was used is not known."})
    for call in record.get("unrun_tool_calls") or []:
        clipped.append({"#": "", "tool": call.get("name"), "clipped by": "tool budget",
                        "items": "", "detail": "Asked for but not run (%s of %s tool calls used): %s" % (
                            record["tool_calls_used"], record["tool_budget"],
                            "; ".join(call.get("search_terms") or []) or json.dumps(call.get("arguments"),
                                                                                    default=str))})
    scope = []
    if record["case_layer"] == "significant":
        scope.append({"#": "", "what": "Everything outside the Significant layer",
                      "decision": "The run was asked on the Significant layer only."})
    for c in record["calls"]:
        if c.get("withheld"):
            w = c["withheld"] if isinstance(c["withheld"], dict) else {"what": str(c["withheld"])}
            scope.append({"#": c["sequence"], "what": "%s%s" % (w.get("what") or "Phone material",
                                                               " (%s)" % w["count"] if w.get("count") is not None
                                                               else ""),
                          "decision": " ".join(str(x) for x in (w.get("reason"), w.get("reason_code"),
                                                                 w.get("decision_id")) if x)})
        elif not c["available"] and not c.get("not_in_case"):
            scope.append({"#": c["sequence"], "what": "Result of %s" % c["name"],
                          "decision": "Refused or not available: %s" % (c.get("reason") or c.get("error") or "")})
    return {"header": _header_rows(record), "categories": categories, "hits": hits, "clipped": clipped,
            "scope": scope, "phone_types": phone_types,
            "counts": {"categories_not_searched": len(categories), "hits_not_opened": len(unopened),
                       "hits_not_shown": len(not_shown),
                       "tool_paging_items": sum(c.get("tool_not_returned") or 0 for c in record["calls"]),
                       "model_paging_items": sum(c.get("model_not_shown") or 0 for c in record["calls"]),
                       "budget_unrun_calls": len(record.get("unrun_tool_calls") or []),
                       "items_without_id": sum(c.get("items_without_id") or 0 for c in record["calls"]),
                       "out_of_scope": len(scope), "unread_phone_types": len(phone_types)}}


# --------------------------------------------------------------------------------------------- rendering

SECTIONS = {
    "strategy": [("tools", "Tools used"), ("versions", "Tool result versions"), ("searches", "Searches, in order"),
                 ("exclusions", "Exclusions stated")],
    "not_examined": [("categories", "Categories of case material not searched"),
                     ("hits", "Items returned but not opened, cited or used"),
                     ("clipped", "Material clipped by paging or by the tool budget"),
                     ("scope", "Out of scope by case decision, or refused"),
                     ("phone_types", "Phone record types Loupe does not yet read (coverage map)")],
}
TITLES = {"strategy": "Agent run: search strategy summary", "not_examined": "Agent run: what was not examined"}
EMPTY = {"categories": "Every kind of material the case holds was searched.",
         "hits": "Every returned item was opened, cited or used.",
         "clipped": "Nothing was clipped by paging or by the tool budget.",
         "scope": "Nothing was out of scope by case decision or refused.",
         "phone_types": "No phone record type is left unread (or the case has no phones).",
         "exclusions": "No exclusions were stated by the results.", "tools": "No tools were called.",
         "versions": "No result stated a schema version.", "searches": "No tool calls."}


def build_statement(db, run, kind: RecordExportKind) -> dict[str, Any]:
    record = load_record(db, run)
    if kind == "strategy":
        return strategy_rows(record)
    return not_examined_rows(record, material=_case_material(db, run.case_id),
                             phone_types=_unread_phone_types(db, run.case_id))


def render_csv(kind: RecordExportKind, statement: dict[str, Any]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([TITLES[kind]])
    for label, value in statement["header"]:
        writer.writerow([label, value])
    if statement.get("counts"):
        writer.writerow([])
        writer.writerow(["Counts"])
        for key, value in statement["counts"].items():
            writer.writerow([key.replace("_", " "), value])
    for key, title in SECTIONS[kind]:
        rows = statement.get(key) or []
        writer.writerow([])
        writer.writerow([title, "%d" % len(rows)])
        if not rows:
            writer.writerow([EMPTY.get(key, "None.")])
            continue
        columns = list(rows[0].keys())
        writer.writerow(columns)
        for row in rows:
            writer.writerow([row.get(c, "") for c in columns])
    return buffer.getvalue()


def render_html(kind: RecordExportKind, statement: dict[str, Any]) -> str:
    def table(rows):
        if not rows:
            return ""
        columns = list(rows[0].keys())
        head = "".join("<th>%s</th>" % html.escape(str(c)) for c in columns)
        body = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % html.escape(str(r.get(c, ""))) for c in columns)
                       for r in rows)
        return "<table><thead><tr>%s</tr></thead><tbody>%s</tbody></table>" % (head, body)

    parts = ["<h1>%s</h1>" % html.escape(TITLES[kind]),
             table([{"": label, " ": value} for label, value in statement["header"]])]
    if statement.get("counts"):
        parts.append("<h2>Counts</h2>" + table([{"count": k.replace("_", " "), "value": v}
                                                for k, v in statement["counts"].items()]))
    for key, title in SECTIONS[kind]:
        rows = statement.get(key) or []
        parts.append("<h2>%s (%d)</h2>" % (html.escape(title), len(rows)))
        parts.append(table(rows) if rows else "<p class='muted'>%s</p>" % html.escape(EMPTY.get(key, "None.")))
    style = ("body{font-family:sans-serif;font-size:9pt;color:#111}h1{font-size:15pt}h2{font-size:11pt;margin-top:14pt}"
             "table{border-collapse:collapse;width:100%;table-layout:fixed}td,th{border:1px solid #ccc;padding:3pt;"
             "vertical-align:top;overflow-wrap:anywhere;text-align:left}th{background:#f2f2f2}.muted{color:#555}"
             "@page{size:A4 landscape;margin:12mm}")
    return "<html><head><meta charset='utf-8'><style>%s</style></head><body>%s</body></html>" % (style, "".join(parts))


def render_record_export(db, run, kind: RecordExportKind, export_format: RecordExportFormat) -> AgentArtifactExport:
    if kind not in SECTIONS:
        raise ValueError(f"Unsupported run record export: {kind}")
    statement = build_statement(db, run, kind)
    stem = _safe_filename("agent-run-%s-%s" % (str(run.id)[:8], "strategy" if kind == "strategy" else "not-examined"))
    if export_format == "csv":
        return AgentArtifactExport(content=render_csv(kind, statement).encode("utf-8-sig"), filename=stem + ".csv",
                                   media_type="text/csv; charset=utf-8")
    if export_format == "pdf":
        try:
            from weasyprint import HTML
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"PDF export is unavailable: {exc}") from exc
        return AgentArtifactExport(content=HTML(string=render_html(kind, statement)).write_pdf(),
                                   filename=stem + ".pdf", media_type="application/pdf")
    raise ValueError(f"Unsupported run record export format: {export_format}")
