"""AI costs of one case, one line per document (BACKLOG FEAT-007).

The ledger stores one cost record per model call: on live (4 Nov 2026) 105,551 reading records for 1,157 documents,
about 91 per document, which is what made a bill hard to defend. The report folds them into one line per thing a
person would recognise and bill for:

* a document read on its own: its file name (from the evidence row, else from the record's description);
* documents read together in one batch: one line per batch, saying so (the batch's records do not name each file);
* the AI assistant: one line per conversation (or agent run), else one line for questions with neither;
* entity merges: one line;
* anything else: one line per kind of work.

Every line keeps the number of calls it folds, the models used, the first and last time, tokens and cost, so nothing
is hidden: the line totals add up to the case total exactly. The case is named on the report and on every line.
"""
from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

MAX_PDF_LINES = 5000


class CostReportError(ValueError):
    pass


def _day(value: str | None, *, end: bool = False):
    if not value:
        return None
    try:
        day = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise CostReportError("Use dates as YYYY-MM-DD.") from exc
    return day + timedelta(days=1) if end else day


def _line_key(job_type, operation_kind, evidence_file_id, description, metadata, agent_run_id):
    metadata = metadata or {}
    description = description or ""
    if job_type == "ingestion":
        if evidence_file_id:
            return ("document", str(evidence_file_id))
        if description.startswith("Evidence ingestion: "):
            return ("document_name", description[len("Evidence ingestion: "):].strip())
        if metadata.get("batch_id"):
            return ("batch", str(metadata["batch_id"]))
        return ("reading", operation_kind or "other")
    if job_type == "ai_assistant":
        if metadata.get("conversation_id"):
            return ("conversation", str(metadata["conversation_id"]))
        if agent_run_id:
            return ("agent_run", str(agent_run_id))
        return ("assistant", "")
    if job_type == "entity_merge":
        return ("merges", "")
    return ("other", f"{job_type}:{operation_kind or ''}")


def _label(kind, value, names):
    if kind == "document":
        return names.get(value) or f"Document {value[:8]}"
    if kind == "document_name":
        return value or "Document (name not recorded)"
    if kind == "batch":
        return f"Documents read together in one batch ({value[:8]}); the batch's records do not name each file"
    if kind == "reading":
        return f"Document reading not tied to a document ({value.replace('_', ' ')})"
    if kind == "conversation":
        return f"AI assistant conversation {value[:8]}"
    if kind == "agent_run":
        return f"AI agent run {value[:8]}"
    if kind == "assistant":
        return "AI assistant questions (no conversation recorded)"
    if kind == "merges":
        return "Entity merges"
    return f"Other AI work ({value.replace('_', ' ').replace(':', ', ')})"


KIND_TITLES = {"document": "Document reading", "document_name": "Document reading", "batch": "Document reading",
               "reading": "Document reading", "conversation": "AI assistant", "agent_run": "AI assistant",
               "assistant": "AI assistant", "merges": "Entity merges", "other": "Other"}


def case_cost_report(db, case_id: UUID, *, start_date: str | None = None, end_date: str | None = None) -> dict:
    """The case's cost lines, folded per document, conversation or kind; totals equal the sum of the records."""
    from postgres.models.case import Case
    from postgres.models.cost_record import CostRecord as R
    from postgres.models.evidence import EvidenceFile

    case = db.get(Case, case_id)
    if case is None:
        raise CostReportError("Case not found.")
    start, end = _day(start_date), _day(end_date, end=True)
    if start and end and start >= end:
        raise CostReportError("The start date must be on or before the end date.")
    stmt = select(R.job_type, R.operation_kind, R.evidence_file_id, R.description, R.extra_metadata, R.agent_run_id,
                  R.model_id, R.cost_usd, R.total_tokens, R.created_at).where(R.case_id == case_id)
    if start:
        stmt = stmt.where(R.created_at >= start)
    if end:
        stmt = stmt.where(R.created_at < end)
    lines: dict = {}
    total_cost, total_calls, total_tokens = Decimal("0"), 0, 0
    for job_type, operation, file_id, description, metadata, run_id, model, cost, tokens, at in db.execute(stmt):
        key = _line_key(str(getattr(job_type, "value", job_type)), operation, file_id, description, metadata, run_id)
        line = lines.setdefault(key, dict(calls=0, cost=Decimal("0"), tokens=0, models=set(), first=at, last=at))
        cost = Decimal(str(cost or 0))
        line["calls"] += 1
        line["cost"] += cost
        line["tokens"] += int(tokens or 0)
        if model:
            line["models"].add(model)
        if at is not None:
            line["first"] = min(line["first"] or at, at)
            line["last"] = max(line["last"] or at, at)
        total_cost += cost
        total_calls += 1
        total_tokens += int(tokens or 0)
    file_ids = [UUID(value) for kind, value in lines if kind == "document"]
    names = {}
    for offset in range(0, len(file_ids), 1000):
        for file_id, name in db.execute(select(EvidenceFile.id, EvidenceFile.original_filename)
                                        .where(EvidenceFile.id.in_(file_ids[offset:offset + 1000]))):
            names[str(file_id)] = name
    out = []
    for (kind, value), line in lines.items():
        out.append(dict(
            kind=KIND_TITLES[kind], label=_label(kind, value, names),
            evidence_file_id=value if kind == "document" else None,
            calls=line["calls"], tokens=line["tokens"], models=sorted(line["models"]),
            cost_usd=float(line["cost"]), cost_exact=str(line["cost"]),
            first_at=line["first"].isoformat() if line["first"] else None,
            last_at=line["last"].isoformat() if line["last"] else None))
    out.sort(key=lambda line: (line["kind"], line["first_at"] or "", line["label"]))
    return dict(case_id=str(case.id), case_title=case.title, start_date=start_date, end_date=end_date,
                lines=out, line_count=len(out), call_count=total_calls, total_tokens=total_tokens,
                total_cost_usd=float(total_cost), total_cost_exact=str(total_cost),
                generated_at=datetime.now(timezone.utc).isoformat())


def _money(value: str) -> str:
    return f"${Decimal(value).quantize(Decimal('0.01')):,}"


def cost_report_html(report: dict) -> str:
    esc = lambda value: html.escape(str(value if value is not None else ""))  # noqa: E731
    period = ("from " + (report["start_date"] or "the first record") + " to " + (report["end_date"] or "today")
              if report["start_date"] or report["end_date"] else "all dates")
    rows = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in (
            esc(report["case_title"]), esc(line["kind"]), esc(line["label"]), f"{line['calls']:,}",
            esc((line["first_at"] or "")[:10]) + ("" if (line["first_at"] or "")[:10] == (line["last_at"] or "")[:10]
                                                  else " to " + esc((line["last_at"] or "")[:10])),
            esc(", ".join(line["models"])), f"{line['tokens']:,}", _money(line["cost_exact"]))) + "</tr>"
        for line in report["lines"])
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>AI costs · {esc(report['case_title'])}</title>
<style>@page {{ size: A4 landscape; margin: 14mm;
  @bottom-left {{ content: "Loupe · AI costs · {esc(report['case_title'])}"; font: 8pt sans-serif; color: #556; }}
  @bottom-right {{ content: "Page " counter(page) " of " counter(pages); font: 8pt sans-serif; color: #556; }} }}
body {{ font: 9pt sans-serif; color: #1e293b; }} h1 {{ font-size: 18pt; margin: 0 0 4pt; }}
table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }} thead {{ display: table-header-group; }}
th, td {{ border-bottom: 1px solid #e2e8f0; padding: 4pt; text-align: left; vertical-align: top;
  overflow-wrap: anywhere; }} th {{ background: #eef1f5; }} tr {{ break-inside: avoid; }}
td:nth-child(4), td:nth-child(7), td:nth-child(8), th:nth-child(4), th:nth-child(7), th:nth-child(8) {{ text-align: right; }}
tfoot td {{ font-weight: bold; }}</style></head><body>
<h1>AI costs: {esc(report['case_title'])}</h1>
<p>Case {esc(report['case_id'])} · {esc(period)} · generated {esc(report['generated_at'][:16].replace('T', ' '))} UTC.</p>
<p>One line per document, conversation or kind of work. Each line folds the individual model calls recorded for it;
the number of calls is shown. Line totals add up to the case total.</p>
<table><colgroup><col style="width:13%"><col style="width:10%"><col style="width:30%"><col style="width:6%">
<col style="width:12%"><col style="width:12%"><col style="width:8%"><col style="width:9%"></colgroup>
<thead><tr><th>Case</th><th>Work</th><th>Document or item</th><th>Calls</th><th>Dates</th><th>Models</th><th>Tokens</th>
<th>Cost (USD)</th></tr></thead><tbody>{rows}</tbody>
<tfoot><tr><td colspan="3">Total · {report['line_count']:,} lines</td><td>{report['call_count']:,}</td><td></td><td></td>
<td>{report['total_tokens']:,}</td><td>{_money(report['total_cost_exact'])}</td></tr></tfoot></table></body></html>"""


def cost_report_pdf(report: dict) -> bytes:
    if report["line_count"] > MAX_PDF_LINES:
        raise CostReportError(f"The report has {report['line_count']:,} lines; a PDF holds up to {MAX_PDF_LINES:,}. "
                              "Choose a shorter date range; no partial PDF was made.")
    from weasyprint import HTML

    def deny(url, *args, **kwargs):
        raise ValueError("The cost report cannot load outside resources.")
    return HTML(string=cost_report_html(report), url_fetcher=deny).write_pdf()
