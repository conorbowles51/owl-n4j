"""Dated "what changed" briefs per case (report: "Proactive briefs about conclusions, not just new alerts";
connection 2's "what changed" brief; rank 9).

A brief compares two **snapshots** of what the case can conclude, each pinned to its ``ledger_revision``:

- totals per currency, verified and working, never mixed (``ledger_summary`` and ``working_totals_from_readings``, the
  totals the screens and agent tools read);
- open leads: statement gaps per account (``continuity.read_account_continuity``), account numbers printed in payment
  descriptions with no statement in the case (``account_mentions.account_references``), and, on a case with phones,
  the phone account leads of the current money-signals run (re-run through ``phone_analysis.framework.request_run``,
  which correlates every reading against the new ledger with ``correlation.correlate``/``correlate_all``);
- what can be tested: days each account's statements cover, and phone readings that were unresolved;
- judgement calls (open, added, resolved);
- conclusions: findings, open hypotheses (theories) and dossier assessments, with the ledger rows they cite.

Everything is deterministic code: no model is asked anything, so a run costs database time only (``cost`` in each
brief). A brief is written when an import lands (``request_brief`` from the statement writer, coalesced until the case
is quiet), when the ledger changes any other way (a periodic revision check) and each night. A run that finds nothing
changed writes no new brief; it stamps the latest one as checked. Each brief carries its run time and coverage, and
``latest`` says when evidence newer than the brief exists ("out of date"), so a stale brief never passes as current.

Briefs are case data: one table, ``case_briefs``, read through the case's view permission.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text

log = logging.getLogger(__name__)

SWEEP_SECONDS = 60            # how often the host sweep looks at requests
QUIET_SECONDS = 120           # an import request waits until the case has been quiet this long
MAX_DEFER_SECONDS = 1800      # ... but never longer than this (a long batch still gets a brief, marked importing)
SCAN_SECONDS = 600            # how often every case's inputs are compared with its latest brief
NIGHTLY_HOUR_UTC = 2          # the nightly re-run happens on the first sweep at or after this hour
LIST_LIMIT = 50               # items shown per section; the count is always the full count
OPEN_THEORY_STATES = ("proposed", "investigating", "substantiated", "weakened")
CONCLUSION_FINDING_STATES = ("draft", "active")
TOTALS_NOTE = ("Verified totals count only payments from statements whose own arithmetic proves them (proof classes "
               "p0-p2). Working totals also count payments a person accepted after review (p3), outside the verified "
               "totals. Both are account postings per currency; transfers are not netted and currencies are never "
               "added together.")
_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
CITED_ROW = re.compile(r"(?:txn://|[?&]payment=)(" + _UUID + ")")
LOCK_KEY = 0x6272_6965_6673  # pg advisory lock: one sweep per database at a time ("briefs")
_last = {"scan": 0.0}


class BriefError(Exception):
    status = 400


def _now():
    return datetime.now(timezone.utc)


def _iso(value):
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def mask(reference: str | None) -> str | None:
    """An account number shown as its last four characters (the lead card rule: masked to four)."""
    if not reference:
        return reference
    tail = re.sub(r"[^0-9A-Za-z]", "", reference)[-4:]
    return "ending " + tail if tail else reference


# ---- snapshot ------------------------------------------------------------------------------------------------------

def _currencies(groups) -> dict:
    return {c["currency"]: {"rows": c["rows"], "credits_minor": str(c["credits_minor"]),
                            "debits_minor": str(c["debits_minor"]),
                            "net_minor": str(c.get("net_minor", int(c["credits_minor"]) - int(c["debits_minor"])))}
            for c in groups}


def _totals(session, case_id) -> dict:
    """Both totals the ledger states, from one read: verified (proof classes p0-p2, ``ledger_summary``) and working
    (also the p3 readings accepted after review, ``working_totals_from_readings``), per currency."""
    from services.financial.ledger_summary import ledger_summary
    from services.financial.working_totals import working_totals_from_readings
    s = ledger_summary(session, case_id=uuid.UUID(str(case_id)), capture_readings=True, totals_only_readings=True)
    if not s.get("available"):
        return {"available": False, "reason": s.get("reason"), "verified": {}, "working": {}}
    w = working_totals_from_readings(s)
    return {"available": True, "considered_rows": s["considered_rows"], "verified_rows": s["included_rows"],
            "working_rows": w["included_rows"], "outside_verified_rows": w.get("outside_verified_rows"),
            "verified": _currencies(s["currencies"]), "working": _currencies(w["currencies"])}


def case_runs(session, case_id) -> dict:
    """{reviewed account id: AccountContinuity} for every account of the case: the same run
    ``continuity.read_account_continuity`` reads for each (periods of the account and every account merged with it,
    in the same order, projected onto the reviewed account, documents' statuses applied by ``build_run``), with the
    periods, statuses and merges read once for the case instead of once per account."""
    from types import SimpleNamespace
    from sqlalchemy import select
    from postgres.models.financial import FinancialSourceDocument, FinancialStatementPeriod
    from services.financial.account_consolidation import canonical_map
    from services.financial.continuity import build_run
    cid = uuid.UUID(str(case_id))
    roots = canonical_map(session, cid)
    periods = session.execute(select(FinancialStatementPeriod).where(FinancialStatementPeriod.case_id == cid).order_by(
        FinancialStatementPeriod.period_start, FinancialStatementPeriod.period_end, FinancialStatementPeriod.id)
    ).scalars().all()
    statuses = dict(session.execute(select(FinancialSourceDocument.id, FinancialSourceDocument.status).where(
        FinancialSourceDocument.case_id == cid)).all())
    keys = [prop.key for prop in FinancialStatementPeriod.__mapper__.column_attrs if prop.key != "account_id"]
    grouped = {}
    for p in periods:
        root = roots.get(p.account_id, p.account_id)
        grouped.setdefault(root, []).append(SimpleNamespace(**{k: getattr(p, k) for k in keys}, account_id=root))
    out = {}
    for root in sorted(set(roots.values()), key=str):
        rows = grouped.get(root)
        if not rows:
            from services.financial.continuity import AccountContinuity
            out[root] = AccountContinuity(account_id=root)
            continue
        out[root] = build_run(rows, document_status={d: statuses.get(d) for d in {r.source_document_id
                                                                                   for r in rows}})
    return out


def _accounts(session, case_id) -> dict:
    """Per reviewed account (merged accounts read as one): statements, span, gaps, breaks."""
    labels = {str(r.id): r for r in session.execute(text(
        "SELECT id, institution_name, identifier_as_printed, holder_name FROM financial_accounts WHERE case_id = :c"),
        {"c": str(case_id)})}
    try:
        runs = case_runs(session, case_id)
    except Exception:  # noqa: BLE001 - unreadable merges: every account reported as unread, never as a gap
        log.warning("briefs: statement runs of case %s not read", case_id, exc_info=True)
        return {aid: {"read": False} for aid in sorted(labels)}
    out = {}
    for root, run in runs.items():
        a = labels.get(str(root))
        out[str(root)] = {
            "read": True,
            "label": " ".join(x for x in ((a.institution_name if a else None),
                                          mask(a.identifier_as_printed if a else None)) if x) or "Account",
            "statements": len(run.periods),
            "from": _iso(run.covered_from), "to": _iso(run.covered_to),
            "covered": [[_iso(p.start), _iso(p.end)] for p in run.periods],
            "gaps": [[_iso(s.earlier.end), _iso(s.later.start), s.uncovered_days] for s in run.gaps],
            "breaks": len(run.breaks),
            "excluded": len(run.excluded),
        }
    return out


def _references(session, case_id) -> dict:
    """Account numbers printed in payment descriptions, by group id: status and how many payments print it."""
    from services.financial.account_mentions import account_references
    r = account_references(session, case_id=uuid.UUID(str(case_id)), offset=0, limit=1, show="all")
    # account_references pages its items; read every group (the page size is ours to choose, never a silent cut)
    total = r["total"]
    if total > 1:
        r = account_references(session, case_id=uuid.UUID(str(case_id)), offset=0, limit=total, show="all")
    return {g["id"]: {"reference": mask(g["reference"]), "kind": g["kind"], "status": g["status"],
                      "payments": g["payment_count"]} for g in r["items"]}


def _phone(conn, case_id) -> dict:
    """The current completed money-signals run of the case (phone leads and readings), or none."""
    has = conn.execute(text("SELECT count(*) FROM phone_extractions WHERE case_id = :c AND standing = 'active'"),
                       {"c": str(case_id)}).scalar() or 0
    if not has:
        return {"phones": 0}
    run = conn.execute(text(
        "SELECT id, finished_at, input_revision, parameters FROM phone_analysis_runs WHERE case_id = :c AND approach = "
        "'money_signals' AND status = 'completed' ORDER BY finished_at DESC NULLS LAST, created_at DESC LIMIT 1"),
        {"c": str(case_id)}).first()
    queued = conn.execute(text(
        "SELECT count(*) FROM phone_analysis_runs WHERE case_id = :c AND approach = 'money_signals' AND status IN "
        "('queued', 'running')"), {"c": str(case_id)}).scalar() or 0
    out = {"phones": int(has), "run_id": str(run.id) if run else None,
           "run_finished_at": _iso(run.finished_at) if run else None, "runs_pending": int(queued),
           "parameters": run.parameters if run else None, "leads": {}, "outcomes": {}}
    if run is None:
        return out
    from services.phone_analysis import money_pairings
    # 05 4.3.8: a rule match a person rejected is not corroboration, and the matches are counted by strength with
    # rejected pairings left out (the matches screen lists every one)
    rejected = money_pairings.rejected_links(conn, case_id)
    readings = [{"kind": "money_reading", "measures": dict(r.measures or {})} for r in conn.execute(text(
        "SELECT measures FROM phone_analysis_results WHERE run_id = :r AND kind = 'money_reading'"), {"r": run.id})]
    matches = {"by_level": {lv: 0 for lv in money_pairings.LEVELS}, "confirmed": 0, "rejected": 0}
    for it in money_pairings.overlay(conn, case_id, readings):
        c = (it["measures"].get("pair_counts") or {})
        for lv, n in (c.get("by_level") or {}).items():
            matches["by_level"][lv] = matches["by_level"].get(lv, 0) + n
        matches["confirmed"] += c.get("confirmed", 0)
        matches["rejected"] += c.get("rejected", 0)
    out["matches"] = matches
    for r in conn.execute(text(
            "SELECT result_key, kind, measures FROM phone_analysis_results WHERE run_id = :r AND kind IN "
            "('account_lead', 'money_reading')"), {"r": run.id}):
        m = r.measures or {}
        if r.kind == "account_lead":
            inst = m.get("institution") or {}
            out["leads"][r.result_key] = {"status": m.get("status"), "account_ref": m.get("account_ref"),
                                          "institution": inst.get("name"), "first_seen": m.get("first_seen"),
                                          "last_seen": m.get("last_seen")}
        else:
            # counted by outcome: a reading's result key changes when it gains its ledger match, so keys do not follow it
            o = m.get("outcome") or "none"
            if o in ("corroborated", "near_amount") and any((m.get("record_uid"), x.get("transaction_id")) in rejected
                                                            for x in m.get("matched") or []):
                o = "rule_match_rejected"
            out["outcomes"][o] = out["outcomes"].get(o, 0) + 1
    return out


def _judgements(conn, case_id) -> dict:
    rows = conn.execute(text(
        "SELECT status, rule_id, count(*) n FROM financial_judgements WHERE case_id = :c GROUP BY 1, 2"),
        {"c": str(case_id)}).all()
    by = {}
    for r in rows:
        by.setdefault(r.status, {})[r.rule_id] = int(r.n)
    all_by_rule = {}
    for st in by.values():
        for rule, n in st.items():
            all_by_rule[rule] = all_by_rule.get(rule, 0) + n
    return {"open": sum(by.get("open", {}).values()), "confirmed": sum(by.get("confirmed", {}).values()),
            "corrected": sum(by.get("corrected", {}).values()), "open_by_rule": by.get("open", {}),
            # a case agent's proposal a person rejected is answered too (agent-proposals)
            "rejected": sum(by.get("rejected", {}).values()),
            "total": sum(all_by_rule.values()), "by_rule": all_by_rule}


def _row_fingerprints(conn, case_id, ids) -> dict:
    if not ids:
        return {}
    out = {}
    for r in conn.execute(text(
            "SELECT id, ledger_status, superseded_by_id, amount_minor, currency, direction, ordering_date, "
            "counterparty_raw, proof_class FROM financial_transactions WHERE case_id = :c AND id = ANY(CAST(:i AS "
            "uuid[]))"), {"c": str(case_id), "i": sorted(ids)}):
        out[str(r.id)] = {"status": r.ledger_status, "replaced_by": str(r.superseded_by_id) if r.superseded_by_id
                          else None, "amount_minor": str(r.amount_minor), "currency": r.currency,
                          "direction": r.direction, "date": _iso(r.ordering_date), "counterparty": r.counterparty_raw,
                          "proof_class": str(r.proof_class)}
    for i in ids:
        out.setdefault(i, {"status": "not_in_case"})
    return out


def _cited(found: set, *texts) -> set:
    for t in texts:
        if t:
            found.update(m.lower() for m in CITED_ROW.findall(t if isinstance(t, str) else canonical(t)))
    return found


def _conclusions(conn, case_id) -> dict:
    """Findings, open hypotheses and dossier assessments, each with the ledger rows it cites (a txn:// or a payment
    link in its text, or a link whose target is a payment)."""
    items = {}
    for r in conn.execute(text(
            "SELECT e.id, e.entry_type, e.title, e.body, e.lifecycle_state, e.updated_at FROM workspace_entries e "
            "WHERE e.case_id = :c AND e.deleted_at IS NULL AND ((e.entry_type = 'theory' AND e.lifecycle_state = "
            "ANY(:t)) OR (e.entry_type = 'finding' AND coalesce(e.lifecycle_state, 'draft') = ANY(:f)))"),
            {"c": str(case_id), "t": list(OPEN_THEORY_STATES), "f": list(CONCLUSION_FINDING_STATES)}):
        items["entry:%s" % r.id] = {"kind": "hypothesis" if r.entry_type == "theory" else "finding",
                                    "id": str(r.id), "title": r.title, "state": r.lifecycle_state,
                                    "rows": _cited(set(), r.title, r.body)}
    for r in conn.execute(text(
            "SELECT entry_id, target_type, target_id, source_anchor, metadata FROM workspace_entry_links WHERE "
            "case_id = :c"), {"c": str(case_id)}):
        it = items.get("entry:%s" % r.entry_id)
        if it is None:
            continue
        if re.search(r"transaction|payment", r.target_type or "") and re.fullmatch(_UUID, r.target_id or ""):
            it["rows"].add(r.target_id.lower())
        _cited(it["rows"], r.target_id, r.source_anchor, r.metadata)
    for r in conn.execute(text(
            "SELECT a.id, a.category, a.content, a.provenance_type FROM dossier_assessments a WHERE a.case_id = :c"),
            {"c": str(case_id)}):
        items["assessment:%s" % r.id] = {"kind": "assessment", "id": str(r.id), "title": r.category,
                                         "state": r.provenance_type, "rows": _cited(set(), r.content)}
    for r in conn.execute(text(
            "SELECT assessment_id, target_type, target_id FROM dossier_assessment_links WHERE case_id = :c"),
            {"c": str(case_id)}):
        it = items.get("assessment:%s" % r.assessment_id)
        if it is not None and re.search(r"transaction|payment", r.target_type or "") and \
                re.fullmatch(_UUID, r.target_id or ""):
            it["rows"].add(r.target_id.lower())
    rows = set().union(*(it["rows"] for it in items.values())) if items else set()
    prints = _row_fingerprints(conn, case_id, rows)
    for it in items.values():
        it["rows"] = sorted(it["rows"])
    return {"items": items, "rows": prints,
            "hypotheses_open": sum(1 for it in items.values() if it["kind"] == "hypothesis")}


def _importing(conn, case_id) -> int:
    return int(conn.execute(text(
        "SELECT count(*) FROM financial_import_batch_items i JOIN financial_import_batches b ON b.id = i.batch_id "
        "WHERE b.case_id = :c AND i.status = 'pending_import'"), {"c": str(case_id)}).scalar() or 0)


def evidence_stamp(conn, case_id) -> dict:
    """When the case's evidence last changed: statements saved, files added, phones loaded, ledger rows, periods and
    accounts written, judgement calls, casework and assessments changed.
    Cheap (indexed max per table); compared with the brief's own stamp to say "out of date"."""
    r = conn.execute(text(
        "SELECT (SELECT max(created_at) FROM financial_source_documents WHERE case_id = :c) st, "
        "(SELECT max(updated_at) FROM financial_source_documents WHERE case_id = :c) stu, "
        "(SELECT max(updated_at) FROM financial_transactions WHERE case_id = :c) lr, "
        "(SELECT max(created_at) FROM evidence_files WHERE case_id = :c) ef, "
        "(SELECT max(created_at) FROM phone_extractions WHERE case_id = :c) ph, "
        "(SELECT max(greatest(created_at, coalesce(resolved_at, created_at))) FROM financial_judgements WHERE "
        "case_id = :c) jc, "
        "(SELECT max(updated_at) FROM financial_statement_periods WHERE case_id = :c) sp, "
        "(SELECT max(updated_at) FROM financial_accounts WHERE case_id = :c) ac, "
        "(SELECT max(updated_at) FROM workspace_entries WHERE case_id = :c) we, "
        "(SELECT max(updated_at) FROM dossier_assessments WHERE case_id = :c) da"), {"c": str(case_id)}).first()
    parts = {"statements": r.st, "statement_changes": r.stu, "ledger_rows": r.lr, "files": r.ef, "phones": r.ph,
             "judgement_calls": r.jc, "statement_periods": r.sp, "accounts": r.ac, "casework": r.we,
             "assessments": r.da}
    newest = max((v for v in parts.values() if v is not None), default=None)
    return {"newest": _iso(newest), "parts": {k: _iso(v) for k, v in parts.items()}}


def input_revision(conn, case_id) -> tuple:
    """(ledger_revision, input_revision): what a brief reads, digested. The ledger part is the one the phone analyses
    pin (money_signals.ledger_revision); the rest are the judgement calls, the current phone run and the conclusions."""
    from services.phone_analysis.money_signals import ledger_revision
    ledger = ledger_revision(conn, case_id)
    j = conn.execute(text(
        "SELECT count(*), max(created_at), max(resolved_at), count(*) FILTER (WHERE status = 'open') FROM "
        "financial_judgements WHERE case_id = :c"), {"c": str(case_id)}).first()
    run = conn.execute(text(
        "SELECT max(finished_at) FROM phone_analysis_runs WHERE case_id = :c AND approach = 'money_signals' AND "
        "status = 'completed'"), {"c": str(case_id)}).scalar()
    w = conn.execute(text(
        "SELECT (SELECT count(*) || ':' || coalesce(max(updated_at)::text, '') FROM workspace_entries WHERE case_id = "
        ":c AND entry_type IN ('theory', 'finding')), (SELECT count(*) || ':' || coalesce(max(updated_at)::text, '') FROM workspace_entry_links WHERE "
        "case_id = :c), (SELECT count(*) || ':' || coalesce(max(updated_at)::text, '') FROM dossier_assessments "
        "WHERE case_id = :c)"), {"c": str(case_id)}).first()
    digest = hashlib.sha256(canonical({"ledger": ledger, "judgements": [str(x) for x in j], "phone_run": _iso(run),
                                       "conclusions": list(w)}).encode()).hexdigest()
    return ledger, digest


def snapshot(session, case_id) -> dict:
    """Everything a brief compares, read in one session (read only)."""
    conn = session.connection()
    ledger, irev = input_revision(conn, case_id)
    return {
        "ledger_revision": ledger,
        "input_revision": irev,
        "totals": _totals(session, case_id),
        "accounts": _accounts(session, case_id),
        "references": _references(session, case_id),
        "phone": _phone(conn, case_id),
        "judgements": _judgements(conn, case_id),
        "conclusions": _conclusions(conn, case_id),
    }


# ---- what changed --------------------------------------------------------------------------------------------------

def _days(a, b) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days + 1


def _uncovered(spans, start, end) -> list:
    """The parts of [start, end] (ISO dates, inclusive) that none of ``spans`` covers."""
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    out, cursor = [], s
    for a, b in sorted((date.fromisoformat(x), date.fromisoformat(y)) for x, y in spans if x and y):
        if b < cursor or a > e:
            continue
        if a > cursor:
            out.append([cursor.isoformat(), (a - timedelta(days=1)).isoformat()])
        cursor = max(cursor, b + timedelta(days=1))
        if cursor > e:
            break
    if cursor <= e:
        out.append([cursor.isoformat(), e.isoformat()])
    return out


def _clip(items: list) -> dict:
    """A section list: the full count, and at most LIST_LIMIT items with the number left out stated."""
    return {"count": len(items), "items": items[:LIST_LIMIT], "not_shown": max(0, len(items) - LIST_LIMIT)}


def _gap_key(account_id, gap):
    return "%s:%s:%s" % (account_id, gap[0], gap[1])


def diff(prev: dict | None, cur: dict) -> dict:
    """The sections of a brief: what changed from ``prev`` to ``cur`` (both from :func:`snapshot`). ``prev`` None is a
    first brief: every section states the starting point and nothing is "closed"."""
    first = prev is None
    prev = prev or {}
    out = {"first": first}

    # Leads closed (and opened)
    closed, opened = [], []
    p_acc, c_acc = prev.get("accounts") or {}, cur.get("accounts") or {}
    for aid, acc in c_acc.items():
        if not acc.get("read"):
            continue
        before = p_acc.get(aid) or {}
        old_gaps = {_gap_key(aid, g): g for g in before.get("gaps") or []} if before.get("read") else {}
        new_gaps = {_gap_key(aid, g): g for g in acc.get("gaps") or []}
        for key, g in old_gaps.items():
            if key in new_gaps:
                continue
            # the days strictly between the two statements that met at the gap
            inner = ((date.fromisoformat(g[0]) + timedelta(days=1)).isoformat(),
                     (date.fromisoformat(g[1]) - timedelta(days=1)).isoformat())
            left = _uncovered(acc.get("covered") or [], *inner) if inner[0] <= inner[1] else []
            # a gap is closed when statements now cover its days (fully or in part); a gap that only moved because the
            # run's ends moved is not closed
            covered = g[2] - sum(_days(a, b) for a, b in left) if g[2] > 0 else 0
            if covered > 0:
                closed.append({"kind": "missing_period", "account_id": aid, "account": acc["label"],
                               "from": g[0], "to": g[1], "days_now_covered": covered,
                               "days_still_missing": sum(_days(a, b) for a, b in left),
                               "sentence": "Statements now cover %d of the %d missing days for %s between %s and %s."
                               % (covered, g[2], acc["label"], g[0], g[1])})
        if not first and not (aid in p_acc and not before.get("read")):
            for key, g in new_gaps.items():
                # a gap inside an earlier gap is what is left of it after a statement landed in it: not a new lead
                if key not in old_gaps and not any(o[0] <= g[0] and g[1] <= o[1] for o in old_gaps.values()):
                    opened.append({"kind": "missing_period", "account_id": aid, "account": acc["label"],
                                   "from": g[0], "to": g[1], "days": g[2],
                                   "sentence": "No statement covers %s between %s and %s (%d days)."
                                   % (acc["label"], g[0], g[1], g[2])})
    p_ref, c_ref = prev.get("references") or {}, cur.get("references") or {}
    for gid, ref in c_ref.items():
        old = p_ref.get(gid)
        if old and old["status"] == "no_statement_found" and ref["status"] != "no_statement_found":
            closed.append({"kind": "missing_account", "reference": ref["reference"], "payments": ref["payments"],
                           "sentence": "A statement now in the case may hold the account %s that %d payment "
                           "description%s name." % (ref["reference"], ref["payments"], "" if ref["payments"] == 1
                                                     else "s")})
        elif not first and ref["status"] == "no_statement_found" and (old is None or
                                                                       old["status"] != "no_statement_found"):
            opened.append({"kind": "missing_account", "reference": ref["reference"], "payments": ref["payments"],
                           "sentence": "Payment descriptions name the account %s; no statement for it is in the case."
                           % ref["reference"]})
    p_ph, c_ph = (prev.get("phone") or {}), (cur.get("phone") or {})
    for key, lead in (p_ph.get("leads") or {}).items():
        if lead.get("status") == "possible_statement":
            continue
        now = (c_ph.get("leads") or {}).get(key)
        if now and now.get("status") == "possible_statement":
            closed.append({"kind": "phone_lead", "reference": lead.get("account_ref"),
                           "institution": lead.get("institution"),
                           "sentence": "Phone alerts for %s%s may now be covered: an account in the case that could be "
                           "theirs now has a statement."
                           % (lead.get("account_ref") or "an account",
                              " at %s" % lead["institution"] if lead.get("institution") else "")})
    out["leads_closed"] = _clip(closed)
    out["leads_opened"] = _clip(opened)
    out["open_leads"] = {
        "accounts_not_read": sum(1 for a in c_acc.values() if not a.get("read")),
        "missing_periods": sum(len(a.get("gaps") or []) for a in c_acc.values() if a.get("read")),
        "missing_days": sum(g[2] for a in c_acc.values() if a.get("read") for g in a.get("gaps") or []),
        "missing_accounts": sum(1 for r in c_ref.values() if r["status"] == "no_statement_found"),
        "phone_leads": sum(1 for l in (c_ph.get("leads") or {}).values() if l.get("status") != "possible_statement"),
    }

    # Contradictions newly testable: days a statement now covers that none did, and phone readings now decided
    testable = []
    for aid, acc in c_acc.items():
        if not acc.get("read"):
            continue
        before = p_acc.get(aid)
        if before is not None and not before.get("read"):
            continue  # the earlier brief could not read this account: nothing to compare against
        old_spans = (before or {}).get("covered") or []
        for a, b in acc.get("covered") or []:
            if not (a and b):
                continue
            for x, y in _uncovered(old_spans, a, b):
                testable.append({"account_id": aid, "account": acc["label"], "from": x, "to": y,
                                 "days": _days(x, y),
                                 "sentence": "%s is now covered by statements from %s to %s: a payment claimed in "
                                 "those days can now be checked against the ledger, and its absence means something."
                                 % (acc["label"], x, y)})
    po, co = (p_ph.get("outcomes") or {}), (c_ph.get("outcomes") or {})
    compare_phone = not first and bool(p_ph.get("run_id")) and bool(c_ph.get("run_id"))
    out["newly_testable"] = {"spans": _clip([] if first else testable),
                             "days": 0 if first else sum(t["days"] for t in testable),
                             "phone_outcomes_before": po if compare_phone else None, "phone_outcomes_after": co,
                             "phone_matches_after": c_ph.get("matches"),
                             "phone_unresolved_change": (co.get("unresolved", 0) - po.get("unresolved", 0))
                             if compare_phone else 0,
                             "phone_contradicted_change": (co.get("contradicted", 0) - po.get("contradicted", 0))
                             if compare_phone else 0,
                             "phone_corroborated_change": (co.get("corroborated", 0) - po.get("corroborated", 0))
                             if compare_phone else 0}

    # Totals per currency, before and after, each with its ledger revision: verified and working, never mixed
    pt, ct = (prev.get("totals") or {}), (cur.get("totals") or {})
    before_unread = not first and not pt.get("available")
    totals = []
    for population in ("verified", "working"):
        before_all, after_all = pt.get(population) or {}, ct.get(population) or {}
        for code in sorted(set(before_all) | set(after_all)):
            b, a = before_all.get(code), after_all.get(code)
            totals.append({"population": population, "currency": code, "before": None if first else b, "after": a,
                           "changed": (first or b != a) and not before_unread,
                           "credits_change_minor": str(int((a or {}).get("credits_minor", 0)) -
                                                       int((b or {}).get("credits_minor", 0))),
                           "debits_change_minor": str(int((a or {}).get("debits_minor", 0)) -
                                                      int((b or {}).get("debits_minor", 0))),
                           "rows_change": int((a or {}).get("rows", 0)) - int((b or {}).get("rows", 0))})
    out["totals"] = {"before_revision": prev.get("ledger_revision"), "after_revision": cur.get("ledger_revision"),
                     "available": bool(ct.get("available")), "reason": ct.get("reason"), "basis": TOTALS_NOTE,
                     "verified_rows": ct.get("verified_rows"), "working_rows": ct.get("working_rows"),
                     "outside_verified_rows": ct.get("outside_verified_rows"),
                     "before_unavailable": before_unread,
                     "currencies": totals, "changed": 0 if first else sum(1 for t in totals if t["changed"])}

    # Judgement calls added and resolved (counts per rule)
    pj, cj = prev.get("judgements") or {}, cur.get("judgements") or {}
    # calls are added, never deleted: added = new rows per rule, whatever their status now
    added = {}
    for rule, n in (cj.get("by_rule") or {}).items():
        d = n - (pj.get("by_rule") or {}).get(rule, 0)
        if d > 0:
            added[rule] = d
    out["judgement_calls"] = {
        "open": cj.get("open", 0), "open_before": pj.get("open") if not first else None,
        "added_open": 0 if first else sum(added.values()), "added_by_rule": {} if first else added,
        "resolved": 0 if first else max(0, (cj.get("confirmed", 0) + cj.get("corrected", 0) + cj.get("rejected", 0))
                                        - (pj.get("confirmed", 0) + pj.get("corrected", 0) + pj.get("rejected", 0))),
    }

    # Conclusions whose cited rows changed
    pc, cc = prev.get("conclusions") or {}, cur.get("conclusions") or {}
    p_rows, c_rows = pc.get("rows") or {}, cc.get("rows") or {}
    changed = []
    for key, it in sorted((cc.get("items") or {}).items()):
        rows = []
        for rid in it["rows"]:
            now = c_rows.get(rid) or {"status": "not_in_case"}
            was = p_rows.get(rid)
            if first:
                if now.get("status") != "admitted" or now.get("replaced_by"):
                    rows.append({"id": rid, "before": None, "after": now})
            elif was is not None and was != now:
                rows.append({"id": rid, "before": was, "after": now})
        if rows:
            changed.append({"kind": it["kind"], "id": it["id"], "title": it["title"], "state": it["state"],
                            "rows": rows, "sentence": "%s “%s” cites %d ledger row%s that %s."
                            % (it["kind"].capitalize(), it["title"], len(rows), "" if len(rows) == 1 else "s",
                               "are no longer current" if first else "changed since the last brief")})
    out["conclusions_changed"] = _clip(changed)
    out["conclusions"] = {"total": len(cc.get("items") or {}), "hypotheses_open": cc.get("hypotheses_open", 0),
                          "citing_rows": sum(1 for it in (cc.get("items") or {}).values() if it["rows"]),
                          "rows_cited": len(c_rows)}
    out["something_changed"] = bool(first or closed or opened or out["totals"]["changed"] or
                                    out["judgement_calls"]["added_open"] or out["judgement_calls"]["resolved"] or
                                    changed or testable or out["newly_testable"]["phone_unresolved_change"] or
                                    # a person confirming or rejecting a phone match, or a run finding other matches
                                    # (05 4.3.8); a brief made before matches were counted has none to compare
                                    (p_ph.get("matches") is not None and p_ph.get("matches") != c_ph.get("matches")) or
                                    (p_ph.get("matches") is None and bool(c_ph.get("matches"))) or
                                    prev.get("ledger_revision") != cur.get("ledger_revision"))
    return out


def coverage(session, case_id, cur: dict) -> dict:
    """What this brief read and what it did not, in counts."""
    conn = session.connection()
    docs = conn.execute(text(
        "SELECT count(*) FILTER (WHERE status = 'admitted'), count(*) FROM financial_source_documents WHERE case_id = "
        ":c"), {"c": str(case_id)}).first()
    acc = cur.get("accounts") or {}
    ph = cur.get("phone") or {}
    not_read = []
    unread = [a for a in acc.values() if not a.get("read")]
    if unread:
        not_read.append("%d account%s whose statement run could not be read" % (len(unread),
                                                                                "" if len(unread) == 1 else "s"))
    if not (cur.get("totals") or {}).get("available"):
        not_read.append("verified totals: %s" % ((cur.get("totals") or {}).get("reason") or "unavailable"))
    if ph.get("phones") and not ph.get("run_id"):
        not_read.append("phone leads: no completed money-signals run yet")
    if ph.get("runs_pending"):
        not_read.append("phone leads: a newer money-signals run is still queued; this brief reads the run of %s"
                        % (ph.get("run_finished_at") or "none"))
    importing = _importing(conn, case_id)
    if importing:
        not_read.append("%d statement%s still importing" % (importing, "" if importing == 1 else "s"))
    return {"statements_admitted": int(docs[0] or 0), "statements_total": int(docs[1] or 0),
            "accounts": len(acc), "accounts_read": len(acc) - len(unread),
            "ledger_rows_considered": (cur.get("totals") or {}).get("considered_rows"),
            "ledger_rows_verified": (cur.get("totals") or {}).get("verified_rows"),
            "ledger_rows_working": (cur.get("totals") or {}).get("working_rows"),
            "account_references": len(cur.get("references") or {}),
            "phones": ph.get("phones", 0), "phone_run": ph.get("run_id"),
            "conclusions": len((cur.get("conclusions") or {}).get("items") or {}),
            "importing": importing, "not_read": not_read,
            "questions": ["leads (statement gaps, accounts named without a statement%s)"
                          % (", phone account leads" if ph.get("phones") else ""),
                          "what can now be tested (statement coverage%s)"
                          % (", phone readings" if ph.get("phones") else ""),
                          "verified and working totals per currency", "judgement calls",
                          "findings, open hypotheses and dossier assessments citing ledger rows"]}


# ---- storage -------------------------------------------------------------------------------------------------------

BRIEF_COLS = ("id, case_id, created_at, checked_at, trigger, ledger_revision, input_revision, previous_id, changes, "
              "coverage, cost, evidence_stamp")


def _out(r, current_stamp=None) -> dict:
    d = {"id": str(r.id), "case_id": str(r.case_id), "created_at": _iso(r.created_at),
         "checked_at": _iso(r.checked_at), "trigger": r.trigger, "ledger_revision": r.ledger_revision,
         "previous_id": str(r.previous_id) if r.previous_id else None, "changes": r.changes, "coverage": r.coverage,
         "cost": r.cost}
    if current_stamp is not None:
        mine = (r.evidence_stamp or {}).get("newest")
        newest = current_stamp.get("newest")
        stale = bool(newest and (mine is None or newest > mine))
        d["out_of_date"] = stale
        d["newest_evidence_at"] = newest
        d["out_of_date_sentence"] = (
            "Out of date: evidence changed at %s, after this brief was made. A new brief follows within minutes once "
            "the case is quiet." % newest if stale else None)
    return d


def _latest_row(conn, case_id):
    return conn.execute(text("SELECT %s, snapshot FROM case_briefs WHERE case_id = :c ORDER BY created_at DESC, id "
                             "DESC LIMIT 1" % BRIEF_COLS), {"c": str(case_id)}).first()


def build(session, case_id, trigger: str, *, force_new: bool = False) -> dict:
    """Read the case, compare with its latest brief and store a new brief when something changed (or none exists);
    otherwise stamp the latest as checked. Commits. Returns ``{"brief": ..., "created": bool}``."""
    started, cpu = time.monotonic(), time.process_time()
    conn = session.connection()
    prev = _latest_row(conn, case_id)
    stamp = evidence_stamp(conn, case_id)
    cur = snapshot(session, case_id)
    changes = diff(prev.snapshot if prev is not None else None, cur)
    cov = coverage(session, case_id, cur)
    cost = {"seconds": round(time.monotonic() - started, 3), "cpu_seconds": round(time.process_time() - cpu, 3),
            "model_calls": 0, "model_tokens": 0}
    now = _now()
    if prev is not None and not changes["something_changed"] and not force_new:
        # nothing a section shows changed: the brief stands, stamped as checked against these inputs (its coverage
        # and changes stay those of the read that made it; the check's own cost is kept beside its build cost)
        session.execute(text("UPDATE case_briefs SET checked_at = :n, input_revision = :r, evidence_stamp = "
                             "CAST(:s AS jsonb), cost = cost || CAST(:cost AS jsonb) WHERE id = :i"),
                        {"n": now, "r": cur["input_revision"], "s": canonical(stamp),
                         "cost": canonical({"last_check": {**cost, "trigger": trigger}}), "i": prev.id})
        session.commit()
        return {"brief": _out(_latest_row(session.connection(), case_id)), "created": False}
    bid = uuid.uuid4()
    session.execute(text(
        "INSERT INTO case_briefs (id, case_id, created_at, checked_at, trigger, ledger_revision, input_revision, "
        "previous_id, snapshot, changes, coverage, cost, evidence_stamp) VALUES (:i, :c, :n, :n, :t, :l, :r, :p, "
        "CAST(:s AS jsonb), CAST(:ch AS jsonb), CAST(:cov AS jsonb), CAST(:cost AS jsonb), CAST(:st AS jsonb))"),
        {"i": bid, "c": str(case_id), "n": now, "t": trigger, "l": cur["ledger_revision"], "r": cur["input_revision"],
         "p": prev.id if prev is not None else None, "s": canonical(cur), "ch": canonical(changes),
         "cov": canonical(cov), "cost": canonical(cost), "st": canonical(stamp)})
    session.commit()
    return {"brief": _out(_latest_row(session.connection(), case_id)), "created": True}


def latest(conn, case_id) -> dict | None:
    r = _latest_row(conn, case_id)
    if r is None:
        return None
    return _out(r, evidence_stamp(conn, case_id))


def history(conn, case_id, *, offset=0, limit=20) -> dict:
    total = conn.execute(text("SELECT count(*) FROM case_briefs WHERE case_id = :c"), {"c": str(case_id)}).scalar()
    rows = conn.execute(text("SELECT %s FROM case_briefs WHERE case_id = :c ORDER BY created_at DESC, id DESC "
                             "OFFSET :o LIMIT :l" % BRIEF_COLS), {"c": str(case_id), "o": offset, "l": limit}).all()
    return {"total": int(total or 0), "returned": len(rows), "offset": offset,
            "next_offset": offset + len(rows) if offset + len(rows) < (total or 0) else None,
            "items": [_out(r) for r in rows]}


# ---- triggers ------------------------------------------------------------------------------------------------------

def request_brief(case_id, reason: str = "import", session_factory=None) -> None:
    """Ask for a brief of this case once it is quiet. Cheap; never raises (called after a ledger commit). It writes
    through ``session_factory`` (the caller's database) when given, else the background sessions."""
    try:
        if session_factory is None:
            from postgres.session import _get_background_session_local
            session_factory = _get_background_session_local()
        with session_factory() as s:
            if s.get_bind().dialect.name != "postgresql":
                return
            s.execute(text(
                "INSERT INTO case_brief_requests (case_id, first_requested_at, last_requested_at, reason) VALUES "
                "(:c, now(), now(), :r) ON CONFLICT (case_id) DO UPDATE SET last_requested_at = now(), reason = :r"),
                {"c": str(case_id), "r": reason[:40]})
            s.commit()
    except Exception:  # pragma: no cover - a brief request must never fail an import
        log.exception("Brief request for case %s could not be recorded", case_id)


def _request_phone_rerun(session, case_id, ledger_changed: bool) -> None:
    """On a case with phones whose ledger changed since the last brief, ask for the money-signals run on the new
    ledger with the settings of the case's current run (a person's chosen settings are kept; the framework returns
    the existing run when nothing it reads changed). Its completion changes the input revision, so the next scan
    writes a brief that reads it."""
    if not ledger_changed:
        return
    conn = session.connection()
    if not conn.execute(text("SELECT 1 FROM phone_extractions WHERE case_id = :c AND standing = 'active' LIMIT 1"),
                        {"c": str(case_id)}).first():
        return
    params = conn.execute(text(
        "SELECT parameters FROM phone_analysis_runs WHERE case_id = :c AND approach = 'money_signals' AND status = "
        "'completed' ORDER BY finished_at DESC NULLS LAST, created_at DESC LIMIT 1"), {"c": str(case_id)}).scalar()
    try:
        from services.phone_analysis import approaches, framework as F
        approaches.install()
        with session.begin_nested():
            F.request_run(conn, case_id, "money_signals", params, "case-briefs")
        session.commit()
    except Exception:  # noqa: BLE001 - the brief still runs on the current phone run, and says which
        log.warning("briefs: money-signals re-run for case %s not requested", case_id, exc_info=True)
        session.rollback()


def due_cases(conn, now=None, *, scan=False, nightly=False) -> list:
    """[(case_id, trigger)]: requests that are quiet (or waited too long), and with ``scan`` every case with financial
    records whose inputs differ from its latest brief, with ``nightly`` every such case not checked today."""
    now = now or _now()
    out = {}
    for r in conn.execute(text("SELECT case_id, first_requested_at, last_requested_at, reason FROM "
                               "case_brief_requests")):
        if (now - r.last_requested_at).total_seconds() >= QUIET_SECONDS or \
                (now - r.first_requested_at).total_seconds() >= MAX_DEFER_SECONDS:
            if not _importing(conn, r.case_id) or (now - r.first_requested_at).total_seconds() >= MAX_DEFER_SECONDS:
                out[str(r.case_id)] = r.reason or "import"
    if scan or nightly:
        for r in conn.execute(text(
                "SELECT c.id, b.input_revision, b.checked_at FROM cases c LEFT JOIN LATERAL (SELECT input_revision, "
                "checked_at FROM case_briefs x WHERE x.case_id = c.id ORDER BY created_at DESC, id DESC LIMIT 1) b ON "
                "true WHERE EXISTS (SELECT 1 FROM financial_accounts a WHERE a.case_id = c.id) ORDER BY c.id")):
            cid = str(r.id)
            if cid in out:
                continue
            if nightly and (r.checked_at is None or r.checked_at.astimezone(timezone.utc).date() <
                            now.astimezone(timezone.utc).date()):
                out[cid] = "nightly"
                continue
            if scan and (r.input_revision is None or input_revision(conn, cid)[1] != r.input_revision):
                out[cid] = "ledger_changed" if r.input_revision else "first"
    return sorted(out.items())


SWEEP_BUDGET_SECONDS = 180    # one round stops starting new cases after this; the rest are due next round
FAILURE_BACKOFF_SECONDS = 3600
_failed = {}                  # case id -> monotonic time of its last failure (in this process)


def sweep_once(factory=None, now=None, *, scan=None, nightly=None) -> list:
    """One round: under a database advisory lock held on a connection of its own (one sweep per database), build each
    due case's brief, within a time budget. A case whose brief failed waits an hour before the next try. Returns
    [(case_id, created, seconds)]."""
    if factory is None:
        from postgres.session import _get_background_session_local
        factory = _get_background_session_local()
    now = now or _now()
    mono = time.monotonic()
    if scan is None:
        scan = mono - _last["scan"] >= SCAN_SECONDS
    if nightly is None:
        nightly = now.astimezone(timezone.utc).hour >= NIGHTLY_HOUR_UTC
    done = []
    with factory() as probe:
        engine = probe.get_bind()
    if engine.dialect.name != "postgresql":
        return done
    # the lock lives on this one connection for the whole round, and is released on it
    with engine.connect() as lock:
        if not lock.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}).scalar():
            lock.rollback()
            return done
        lock.commit()
        try:
            with factory() as s:
                due = due_cases(s.connection(), now, scan=scan, nightly=nightly)
                s.rollback()
            if scan:
                _last["scan"] = mono
            for case_id, trigger in due:
                if time.monotonic() - mono > SWEEP_BUDGET_SECONDS:
                    break
                if time.monotonic() - _failed.get(case_id, -1e12) < FAILURE_BACKOFF_SECONDS:
                    continue
                with factory() as s:
                    try:
                        # one consistent view of the case for the whole read (an import committing meanwhile is
                        # read by the next brief, not half by this one)
                        s.connection(execution_options={"isolation_level": "REPEATABLE READ"})
                        before = s.execute(text("SELECT ledger_revision FROM case_briefs WHERE case_id = :c ORDER BY "
                                                "created_at DESC, id DESC LIMIT 1"), {"c": case_id}).scalar()
                        result = build(s, case_id, trigger)
                        s.execute(text("DELETE FROM case_brief_requests WHERE case_id = :c AND last_requested_at <= "
                                       ":n"), {"c": case_id, "n": now})
                        s.commit()
                        _failed.pop(case_id, None)
                        done.append((case_id, result["created"], result["brief"]["cost"]["seconds"]))
                        _request_phone_rerun(s, case_id, before != result["brief"]["ledger_revision"])
                    except Exception:  # noqa: BLE001 - one case's failure never stops the others
                        s.rollback()
                        _failed[case_id] = time.monotonic()
                        log.exception("Brief for case %s failed; it will be tried again in an hour", case_id)
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})
            lock.commit()
    if done:
        log.info("Case briefs: %s", ", ".join("%s %s %.1fs" % (c[:8], "new" if n else "checked", t)
                                             for c, n, t in done))
    return done
