"""Check money figures in AI-written entity summaries against the ledger.

Entity summaries are written by a model from text read off the page. A
statement whose figure is printed in pieces (``9`` and ``800.00``) can be read
as ``800.00`` while the ledger, which reads the table, holds ``9,800.00``. The
summary then repeats the misreading under a citation to the statement page.

This check reads each summary passage that cites a statement file the ledger
was built from and names a money figure and a day. It looks up the current
ledger rows (admitted, not superseded) from that file on that day:

* a row with that amount: the figure agrees and is left alone;
* no row on that day: the ledger cannot judge, the figure is left alone;
* rows on that day, none with that amount: the figure disagrees. When exactly
  one row is the plain source of the misreading (its amount ends with the
  summary's digits, or it is the only row that day), the figure is replaced
  with the ledger amount and the model's reading stays visible beside it.
  Otherwise the figure is flagged as missing from the ledger.

Passages about balances or totals are not checked: they are not single rows.
A summary a person wrote or edited (``summary`` in ``manual_fields``) is never
changed; its disagreements are only counted. The model's text before the first
change is kept on the node (``summary_model_text``), so the check can be rerun
from it after a ledger correction, and a later model summary replaces it.

The switch ``SUMMARY_LEDGER_CHECK=0`` stops the automatic runs (after a file finishes and after the ledger is
redrawn into the graph); the command below still runs. Run for one case or all: ``python -m services.summary_ledger_check [--case <id>] [--apply]``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Iterable
from urllib.parse import unquote

logger = logging.getLogger(__name__)

REPLACED_NOTE = " (the ledger amount; the AI reading was {model})"
FLAG_NOTE = " (the ledger shows no payment of this amount on this date)"
_FLAG_RE = re.compile(re.escape(FLAG_NOTE))

_MONTHS = {
    name: index
    for index, names in enumerate(
        [
            ("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"),
            ("may",), ("june", "jun"), ("july", "jul"), ("august", "aug"),
            ("september", "sep", "sept"), ("october", "oct"), ("november", "nov"), ("december", "dec"),
        ],
        start=1,
    )
    for name in names
}
_MONTH = r"(?P<month>" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?"
_DAY_MONTH = re.compile(r"\b(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+" + _MONTH + r"(?:,?\s+(?P<year>\d{4}))?\b", re.I)
_MONTH_DAY = re.compile(r"\b" + _MONTH + r"\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(?P<year>\d{4}))?\b", re.I)
_ISO = re.compile(r"\b(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})\b")
_YEAR = re.compile(r"\b(19|20)\d{2}\b")
_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?"
_CODES = r"USD|EUR|GBP|CAD|AUD"
# A figure with a symbol or code before it ("$800.00", "USD 800.00"), or with a code after it ("800.00 USD").
_MONEY = re.compile(
    r"(?:(?P<sym>[$€£])|\b(?P<code>" + _CODES + r")\s?)(?P<num>" + _NUM + r")"
    r"|\b(?P<postnum>" + _NUM + r")\s?(?P<postcode>" + _CODES + r")\b"
)
# A file name may hold one level of parentheses ("Chart (200217).pdf"), so the link target allows them.
_TARGET = r"(?:[^()\s]|\s(?!\[)|\([^()]*\))*"
_CITATION = re.compile(r"\[[^\]]*\]\((?P<scheme>doc|evidence)://(?P<target>" + _TARGET + r")\)")
_CITATION_RUN = re.compile(r"(?:\[[^\]]*\]\((?:doc|evidence)://" + _TARGET + r"\)(?:\s*[;,]\s*)?)+")
_REPLACED_FIGURE_RE = re.compile(r"(?:" + _MONEY.pattern + r") \(the ledger amount; the AI reading was (?P<model>[^)]*)\)")
_NOT_A_ROW = re.compile(r"\b(balance|balances|total|totals|totalling|totaling|sum|combined|altogether|aggregate|net|overall)\b", re.I)


@dataclass(frozen=True)
class LedgerRow:
    source_file: str
    day: date
    amount_minor: int
    balance_minor: int | None = None
    description: str = ""


@dataclass
class Finding:
    figure: str
    day: str
    source_files: list[str]
    ledger_amounts: list[str]
    action: str  # "replaced" | "flagged"
    ledger_figure: str | None = None

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class CheckResult:
    text: str
    findings: list[Finding] = field(default_factory=list)
    checked: int = 0


def strip_notes(text: str) -> str:
    """Remove this check's own notes so a rerun judges the model's figures again."""
    text = _FLAG_RE.sub("", text)
    # A replaced figure reads "<ledger figure> (the ledger amount; the AI reading was <model figure>)".
    return _REPLACED_FIGURE_RE.sub(lambda m: m.group("model"), text)


def _minor(number: str) -> int | None:
    try:
        return int((Decimal(number.replace(",", "")) * 100).to_integral_value())
    except (InvalidOperation, ValueError):
        return None


def _number(money: re.Match) -> str:
    return money.group("num") or money.group("postnum")


def format_minor(amount_minor: int, like: str) -> str:
    """Write a ledger amount in the style of the summary's figure (its symbol or code, before or after)."""
    figure = f"{Decimal(amount_minor) / 100:,.2f}"
    match = _MONEY.match(like)
    if match and match.group("postnum"):
        return figure + like[match.end("postnum"):]
    prefix = like[: match.start("num")] if match else ""
    return f"{prefix}{figure}"


def _days(passage: str) -> list[date]:
    found: list[tuple[int, date | None, int, int]] = []
    for regex in (_DAY_MONTH, _MONTH_DAY):
        for m in regex.finditer(passage):
            month = _MONTHS[m.group("month").lower()]
            day = int(m.group("day"))
            year = m.group("year")
            if year is None:
                later = _YEAR.search(passage, m.end())
                year = later.group(0) if later else None
            if year is None:
                continue
            try:
                found.append((m.start(), date(int(year), month, day), month, day))
            except ValueError:
                continue
    for m in _ISO.finditer(passage):
        try:
            found.append((m.start(), date(int(m.group("year")), int(m.group("month")), int(m.group("day"))), 0, 0))
        except ValueError:
            continue
    return list(dict.fromkeys(d for _, d, _, _ in sorted(found, key=lambda item: item[0])))


def _cited_files(run: str, names: dict[str, str] | None = None) -> list[str]:
    """File names a citation run cites. A doc:// link may name the file or give its evidence file id (``names``)."""
    files = []
    for m in _CITATION.finditer(run):
        target = m.group("target")
        if m.group("scheme") == "doc" and "/" in target:
            target = target.rsplit("/", 1)[0]
        target = unquote(target).strip()
        files.append((names or {}).get(target.lower(), target))
    return list(dict.fromkeys(f for f in files if f))


def _passages(text: str, names: dict[str, str] | None = None) -> Iterable[tuple[int, int, list[str]]]:
    """Yield (start, end, cited files) for the text each citation run supports.

    A passage runs from the previous citation run (or the start of its sentence or
    line, whichever is later) to the citation run that closes it.
    """
    previous_end = 0
    for run in _CITATION_RUN.finditer(text):
        start = previous_end
        head = text[start : run.start()]
        breaks = [m.end() for m in re.finditer(r"(?<=[.!?])\s+(?=[A-Z\"(])|\n", head)]
        if breaks:
            start += breaks[-1]
        yield start, run.start(), _cited_files(run.group(0), names)
        previous_end = run.end()


def check_text(text: str, rows: dict[tuple[str, date], list[LedgerRow]], names: dict[str, str] | None = None) -> CheckResult:
    """Return the summary with disagreeing figures replaced or flagged, and what was found.

    ``rows`` maps (source file name, day) to the current ledger rows from that file on that day; ``names`` maps an
    evidence file id (lower case) to its file name, for citations that give the id.
    """
    base = strip_notes(text)
    edits: list[tuple[int, int, str]] = []
    result = CheckResult(text=base)
    for start, end, files in _passages(base, names):
        passage = base[start:end]
        if not files or _NOT_A_ROW.search(passage):
            continue
        days = _days(passage)
        if not days:
            continue
        for money in _MONEY.finditer(passage):
            figure_minor = _minor(_number(money))
            if figure_minor is None:
                continue
            judged = [(day, [r for f in files for r in rows.get((f, day), [])]) for day in days]
            judged = [(day, day_rows) for day, day_rows in judged if day_rows]
            if not judged:
                continue
            result.checked += 1
            if any(r.amount_minor == figure_minor or r.balance_minor == figure_minor
                   for _, day_rows in judged for r in day_rows):
                continue
            day, day_rows = judged[0]
            if len(judged) == 1:
                digits = str(figure_minor)
                source = [r for r in day_rows if str(r.amount_minor).endswith(digits)]
                if not source and len(day_rows) == 1:
                    source = day_rows
            else:
                source = []
            figure = money.group(0)
            finding = Finding(
                figure=figure,
                day=day.isoformat(),
                source_files=files,
                ledger_amounts=sorted({format_minor(r.amount_minor, figure) for _, rs in judged for r in rs}),
                action="flagged",
            )
            absolute = (start + money.start(), start + money.end())
            if len(source) == 1:
                ledger_figure = format_minor(source[0].amount_minor, figure)
                finding.action = "replaced"
                finding.ledger_figure = ledger_figure
                edits.append((*absolute, ledger_figure + REPLACED_NOTE.format(model=figure)))
            else:
                edits.append((*absolute, figure + FLAG_NOTE))
            result.findings.append(finding)
    out = base
    for s, e, replacement in sorted(edits, reverse=True):
        out = out[:s] + replacement + out[e:]
    result.text = out
    return result


# --- ledger and graph ---------------------------------------------------------------------------------

def file_names(session, case_id) -> dict[str, str]:
    """Evidence file id (lower case) -> file name for a case: summaries cite statements as doc://<file id>/<page>."""
    from sqlalchemy import select

    from postgres.models.evidence import EvidenceFile
    return {str(fid).lower(): name for fid, name in session.execute(
        select(EvidenceFile.id, EvidenceFile.original_filename).where(EvidenceFile.case_id == case_id)) if name}


# --- graph figures: the amount on a payment node and on its connections -------------------------------

AMOUNT_NOTE = "the ledger amount; read from the page as {model}"


@dataclass
class FigureCheck:
    amount: float | None  # the ledger amount to write, or None when the figure agrees or cannot be judged
    finding: Finding | None = None


def _as_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except ValueError:
            try:
                parsed = json.loads(value.replace("'", '"'))
            except ValueError:
                return []
        return parsed if isinstance(parsed, list) else []
    return []


def record_files(files, locations) -> list[str]:
    """The statement files a node or connection was read from (its source_files and source_locations)."""
    names = [str(f) for f in _as_list(files) if f]
    names += [str(loc.get("source_file")) for loc in _as_list(locations) if isinstance(loc, dict) and loc.get("source_file")]
    return list(dict.fromkeys(names))


def check_figure(amount, day, files: list[str], name: str, rows: dict[tuple[str, date], list[LedgerRow]]) -> FigureCheck:
    """Judge one graph amount (as read from the page) against the ledger rows of its files on its day.

    The same rules as a summary figure: agreeing or unjudgeable figures are left alone, balances and totals are not
    rows, and a disagreeing figure is replaced only when exactly one row is its plain source.
    """
    try:
        figure_minor = abs(int((Decimal(str(amount).replace(",", "")) * 100).to_integral_value()))
        when = date.fromisoformat(str(day)[:10])
    except (InvalidOperation, ValueError, TypeError):
        return FigureCheck(None)
    if _NOT_A_ROW.search(name or ""):
        return FigureCheck(None)
    day_rows = [r for f in files for r in rows.get((f, when), [])]
    if not day_rows or any(r.amount_minor == figure_minor for r in day_rows):
        return FigureCheck(None)
    source = [r for r in day_rows if str(r.amount_minor).endswith(str(figure_minor))]
    if not source and len(day_rows) == 1:
        source = day_rows
    model = f"{Decimal(figure_minor) / 100:,.2f}"
    finding = Finding(figure=model, day=when.isoformat(), source_files=files,
                      ledger_amounts=sorted({format_minor(r.amount_minor, model) for r in day_rows}), action="flagged")
    if len(source) != 1:
        return FigureCheck(None, finding)
    finding.action = "replaced"
    finding.ledger_figure = format_minor(source[0].amount_minor, model)
    return FigureCheck(source[0].amount_minor / 100, finding)


_READ_FIGURES = """
MATCH (n {case_id: $case_id}) WHERE n.amount IS NOT NULL AND n.date IS NOT NULL
RETURN 'node' AS what, n.key AS key, n.name AS name, n.amount AS amount, n.amount_as_read AS as_read,
       n.amount_ledger_checked AS checked, n.date AS date, n.source_files AS files, n.source_locations AS locations,
       coalesce(n.manual_fields, []) AS manual_fields
UNION ALL
MATCH (a)-[r]->(b) WHERE r.case_id = $case_id AND r.amount IS NOT NULL AND r.date IS NOT NULL
RETURN 'connection' AS what, elementId(r) AS key, coalesce(b.name, '') + ' ' + coalesce(a.name, '') AS name,
       r.amount AS amount, r.amount_as_read AS as_read, r.amount_ledger_checked AS checked, r.date AS date,
       r.source_files AS files, r.source_locations AS locations, [] AS manual_fields
"""

_WRITE_NODE_FIGURE = """
MATCH (n {case_id: $case_id, key: $key}) WHERE toString(n.amount) = $expected
SET n.amount = $amount, n.amount_as_read = $as_read, n.amount_ledger_checked = $checked
RETURN n.key AS key
"""

_WRITE_CONNECTION_FIGURE = """
MATCH ()-[r]->() WHERE elementId(r) = $key AND r.case_id = $case_id AND toString(r.amount) = $expected
SET r.amount = $amount, r.amount_as_read = $as_read, r.amount_ledger_checked = $checked
RETURN elementId(r) AS key
"""


def check_figures(session, case_id: str, rows, *, apply: bool, report: dict) -> list[str]:
    """Check the amount on every dated node and connection read from a ledger statement; returns changed node keys.

    A replaced amount keeps the page reading in ``amount_as_read`` and the written value in ``amount_ledger_checked``,
    so a rerun judges the reading again and a later ledger correction back to it restores it.
    """
    sources = {f for f, _ in rows}
    changed = []
    for rec in list(session.run(_READ_FIGURES, case_id=case_id)):
        files = [f for f in record_files(rec["files"], rec["locations"]) if f in sources]
        if not files:
            continue
        ours = rec["as_read"] is not None and rec["checked"] is not None and str(rec["checked"]) == str(rec["amount"])
        base = rec["as_read"] if ours else rec["amount"]
        report["checked_amounts"] += 1
        result = check_figure(base, rec["date"], files, rec["name"] or "", rows)
        if result.finding is not None:
            report["amounts_replaced" if result.amount is not None else "amounts_flagged"] += 1
            report["entities"].append({"key": rec["key"], "name": rec["name"], "what": rec["what"],
                                       "findings": [result.finding.as_dict()]})
        person = "amount" in rec["manual_fields"]
        if person or not apply:
            continue
        if result.amount is not None:
            amount, as_read, checked = result.amount, base, result.amount
        elif ours:
            amount, as_read, checked = base, None, None  # the ledger now agrees with the reading: restore it
        else:
            continue
        if str(amount) == str(rec["amount"]) and as_read == rec["as_read"]:
            continue
        query = _WRITE_NODE_FIGURE if rec["what"] == "node" else _WRITE_CONNECTION_FIGURE
        written = session.run(query, case_id=case_id, key=rec["key"], expected=str(rec["amount"]),
                              amount=amount, as_read=as_read, checked=checked).single()
        if written:
            report["amounts_written"] += 1
            if rec["what"] == "node":
                changed.append(rec["key"])
    return changed


def ledger_rows(session, case_id) -> dict[tuple[str, date], list[LedgerRow]]:
    """Current ledger rows of a case keyed by (source file name, transaction day)."""
    from sqlalchemy import select

    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial import FinancialSourceDocument as Source
    from postgres.models.financial import FinancialTransaction as Payment

    query = (
        select(EvidenceFile.original_filename, Payment.transaction_date, Payment.posted_date,
               Payment.amount_minor, Payment.running_balance_minor, Payment.description)
        .join(Source, Source.id == Payment.source_document_id)
        .join(EvidenceFile, EvidenceFile.id == Source.evidence_file_id)
        .where(Payment.case_id == case_id, Source.case_id == case_id,
               Payment.ledger_status == "admitted", Payment.superseded_by_id.is_(None))
    )
    rows: dict[tuple[str, date], list[LedgerRow]] = {}
    for filename, txn_day, posted_day, amount, balance, description in session.execute(query):
        for day in dict.fromkeys(d for d in (txn_day, posted_day) if d):
            rows.setdefault((filename, day), []).append(
                LedgerRow(filename, day, abs(int(amount)), abs(int(balance)) if balance is not None else None,
                          description or ""))
    return rows


_READ_SUMMARIES = """
MATCH (n {case_id: $case_id})
WHERE n.summary IS NOT NULL AND (n.summary CONTAINS 'doc://' OR n.summary CONTAINS 'evidence://')
RETURN n.key AS key, n.name AS name, n.summary AS summary, n.summary_model_text AS model_text,
       n.summary_ledger_checked AS checked_text, coalesce(n.manual_fields, []) AS manual_fields
"""

_WRITE_SUMMARY = """
MATCH (n {case_id: $case_id, key: $key})
WHERE n.summary = $expected
SET n.summary = $summary,
    n.summary_model_text = $model_text,
    n.summary_ledger_checked = $summary,
    n.summary_ledger_findings = $findings
RETURN n.key AS key
"""


def check_case(case_id: str, *, apply: bool = False, db_session=None, graph_session=None) -> dict:
    """Check every summary of one case; with ``apply`` write the corrected text through the graph."""
    from services.neo4j.driver import driver

    if db_session is None:
        from postgres.session import get_background_session
        with get_background_session() as own:
            rows, names = ledger_rows(own, case_id), file_names(own, case_id)
    else:
        rows, names = ledger_rows(db_session, case_id), file_names(db_session, case_id)
    report = {"case_id": case_id, "summaries": 0, "checked_figures": 0, "disagreeing_summaries": 0,
              "replaced": 0, "flagged": 0, "person_written_disagreeing": 0, "written": 0,
              "checked_amounts": 0, "amounts_replaced": 0, "amounts_flagged": 0, "amounts_written": 0, "entities": []}
    if not rows:
        return report
    sources = {f for f, _ in rows}
    own_graph = graph_session is None
    session = graph_session or driver.session()
    try:
        nodes = list(session.run(_READ_SUMMARIES, case_id=case_id))
        changed_keys = []
        for node in nodes:
            summary = node["summary"]
            # The last checked text is this check's own output: judge the model's text again.
            base = node["model_text"] if node["checked_text"] == summary and node["model_text"] else summary
            if not any(set(files) & sources for _, _, files in _passages(strip_notes(base), names)):
                continue
            report["summaries"] += 1
            result = check_text(base, rows, names)
            report["checked_figures"] += result.checked
            # No findings and base == summary: nothing to do. No findings but base differs: the ledger now
            # agrees with the model's own text (a correction was undone), so the model's text is restored.
            if not result.findings and base == summary:
                continue
            person = "summary" in node["manual_fields"]
            if result.findings:
                report["disagreeing_summaries"] += 1
                if person:
                    report["person_written_disagreeing"] += 1
                report["replaced"] += sum(f.action == "replaced" for f in result.findings)
                report["flagged"] += sum(f.action == "flagged" for f in result.findings)
                report["entities"].append({"key": node["key"], "name": node["name"], "person_written": person,
                                           "findings": [f.as_dict() for f in result.findings]})
            if person or not apply or result.text == summary:
                continue
            written = session.run(_WRITE_SUMMARY, case_id=case_id, key=node["key"], expected=summary,
                                  summary=result.text, model_text=base,
                                  findings=json.dumps([f.as_dict() for f in result.findings])).single()
            if written:
                report["written"] += 1
                changed_keys.append(node["key"])
        if os.environ.get("GRAPH_AMOUNT_LEDGER_CHECK", "1") != "0":
            changed_keys += [k for k in check_figures(session, case_id, rows, apply=apply, report=report)
                             if k not in changed_keys]
    finally:
        if own_graph:
            session.close()
    if changed_keys:
        try:
            from services import entity_vectors
            entity_vectors.refresh_entities(case_id, changed_keys, stop_on_failure=False)
        except Exception:
            logger.exception("Summary ledger check: re-embedding %d entities failed", len(changed_keys))
    return report


_pending: set[str] = set()
_lock = threading.Lock()


def schedule_case_check(case_id) -> None:
    """Run the check for a case in the background once ingestion or a ledger change settles."""
    if os.environ.get("SUMMARY_LEDGER_CHECK", "1") == "0":
        return
    case_id = str(case_id)
    with _lock:
        if case_id in _pending:
            return
        _pending.add(case_id)

    def run():
        import time
        time.sleep(30)
        with _lock:
            _pending.discard(case_id)
        try:
            report = check_case(case_id, apply=True)
            if report["written"] or report["disagreeing_summaries"]:
                logger.info("Summary ledger check %s: %s", case_id,
                            {k: v for k, v in report.items() if k != "entities"})
        except Exception:
            logger.exception("Summary ledger check failed for case %s", case_id)

    threading.Thread(target=run, name=f"summary-ledger-check-{case_id[:8]}", daemon=True).start()


def _all_case_ids(session) -> list[str]:
    from sqlalchemy import distinct, select

    from postgres.models.financial import FinancialTransaction as Payment
    return [str(c) for c in session.execute(select(distinct(Payment.case_id))).scalars()]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", action="append", help="case id (repeatable); default every case with a ledger")
    parser.add_argument("--apply", action="store_true", help="write corrected summaries (default: dry run)")
    parser.add_argument("--details", action="store_true", help="print each disagreeing figure")
    args = parser.parse_args(argv)
    from postgres.session import get_background_session
    if args.case:
        cases = args.case
    else:
        with get_background_session() as session:
            cases = _all_case_ids(session)
    totals: dict[str, int] = {}
    for case_id in cases:
        report = check_case(case_id, apply=args.apply)
        for key, value in report.items():
            if isinstance(value, int):
                totals[key] = totals.get(key, 0) + value
        line = {k: v for k, v in report.items() if k != "entities"}
        print(json.dumps(line))
        if args.details:
            for entity in report["entities"]:
                print("   ", json.dumps(entity, ensure_ascii=False))
    print("TOTAL", json.dumps({"cases": len(cases), **totals}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
