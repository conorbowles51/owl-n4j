"""Agent readers of what the ledger knows beyond its rows (agent-ledger B, C, D; report ranks 6 and 7).

Each reader keeps the ledger-tool contract (``financial_ledger_tools``): the case comes from the run, never the
model; the session is the read-only one the runner opens; a page states ``total``, ``returned``, ``offset`` and
``next_offset``; a ``revision`` pins what was read; every item carries a citation (an in-app link to the record).
A subject that is not in the case is answered "not in this case" in the same words whether or not it exists in
another case. Arithmetic is done here, never by the model.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from uuid import UUID

MAX_PAGE = 100
NOT_IN_CASE = "That record is not in this case."


class LedgerReadingError(ValueError):
    """Invalid input, answered without a partial result."""


def _uuid(value, what="identifier"):
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise LedgerReadingError("Use a valid %s." % what) from exc


def _day(value):
    if value in (None, ""):
        return None
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError as exc:
        raise LedgerReadingError("Use calendar dates in YYYY-MM-DD format.") from exc
    return parsed


def _page(offset, limit):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= MAX_PAGE:
        raise LedgerReadingError("Use a nonnegative offset and a page limit from 1 to %d." % MAX_PAGE)
    return offset, limit


def _revision(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
                          .encode()).hexdigest()


def _paged(schema, case_id, items, offset, limit, revision, **extra):
    page = items[offset:offset + limit]
    nxt = offset + limit if offset + limit < len(items) else None
    return dict(schema=schema, case_id=str(case_id), available=True, reason=None, revision=revision,
                total=len(items), returned=len(page), offset=offset, has_more=nxt is not None, next_offset=nxt,
                items=page, **extra)


def _unavailable(schema, case_id, reason, code="not_in_case"):
    return dict(schema=schema, case_id=str(case_id), available=False, reason=reason, reason_code=code,
                revision=None, total=None, returned=0, offset=0, has_more=False, next_offset=None, items=[])


def payment_href(case_id, payment_id):
    return "/cases/%s/financial?view=transactions&payment=%s" % (case_id, payment_id)


def judgements_href(case_id):
    return "/cases/%s/financial?view=statements&judgements=1" % case_id


def accounts_href(case_id):
    return "/cases/%s/financial?view=statements&accounts=1" % case_id


# ---- open judgement calls behind a figure (E) ------------------------------------------------------------------

def open_calls_behind(index, rows):
    """How many open judgement calls touch these payments (on the payment or on its whole statement), and how many
    of the payments carry one: ``{available, open_calls, payments_with_open_calls, payments, sentence}``. The index
    is ``judgements.row_map``; None (unreadable) says so rather than claiming none."""
    rows = list(rows)
    if index is None:
        return dict(available=False, open_calls=None, payments_with_open_calls=None, payments=len(rows),
                    sentence="Judgement calls could not be read; do not say this figure rests on none.")
    if "_status" not in index:  # built once per index, not once per group
        index["_status"] = {item["id"]: item["status"] for item in index["judgements"]}
    status = index["_status"]
    calls, touched = set(), 0
    for r in rows:
        ids = [*index["transactions"].get(str(r["id"]), []),
               *index["documents"].get(str(r.get("source_document_id") or ""), [])]
        for mirror in r.get("_mirror_rows") or ():
            ids += [*index["transactions"].get(str(mirror["id"]), []),
                    *index["documents"].get(str(mirror.get("source_document_id") or ""), [])]
        open_ids = {i for i in ids if status.get(i) == "open"}
        calls |= open_ids
        touched += bool(open_ids)
    n = len(calls)
    sentence = ("This figure rests on %d open judgement call%s (on %d of its %d payment%s); say so in the answer."
                % (n, "" if n == 1 else "s", touched, len(rows), "" if len(rows) == 1 else "s")) if n else \
        "No open judgement call touches these payments."
    return dict(available=True, open_calls=n, payments_with_open_calls=touched, payments=len(rows), sentence=sentence)


def judgement_index(session, case_id):
    from services.agent.financial_ledger_tools import _judgement_index
    return _judgement_index(session, case_id)


# ---- amounts ------------------------------------------------------------------------------------------------------

def formatted(amount_minor, currency) -> dict:
    """``{"amount": "MXN 21,000.00", "currency_exponent": 2}`` beside a minor-unit figure, so a model never reads
    minor units as whole units (measured live: MXN 2,100,000 centavos was answered as MXN 2,100,000.00)."""
    from services.financial.money import MoneyError, get_currency
    from services.phone.link_edges import format_minor
    try:
        return dict(amount=format_minor(int(amount_minor), currency), currency_exponent=get_currency(currency).exponent)
    except (MoneyError, AttributeError, TypeError, ValueError):
        return dict(amount=None, currency_exponent=None)


def _formatted_totals(totals):
    out = []
    for t in totals:
        p3 = t["p3"]
        out.append(dict(t, paid_ab=formatted(t["paid_ab_minor"], t["currency"])["amount"],
                        paid_ba=formatted(t["paid_ba_minor"], t["currency"])["amount"],
                        currency_exponent=formatted(0, t["currency"])["currency_exponent"],
                        p3=dict(p3, paid_ab=formatted(p3["paid_ab_minor"], t["currency"])["amount"],
                                paid_ba=formatted(p3["paid_ba_minor"], t["currency"])["amount"])))
    return out


# ---- money between two parties (B) ------------------------------------------------------------------------------

MONEY_SCHEMA = "loupe.agent.money_between/1"


def _source_documents(session, case_id, ids):
    from sqlalchemy import select
    from postgres.models.financial import FinancialTransaction
    if not ids:
        return {}
    return {str(i): str(d) for i, d in session.execute(select(FinancialTransaction.id,
            FinancialTransaction.source_document_id).where(FinancialTransaction.case_id == case_id,
                                                           FinancialTransaction.id.in_([UUID(x) for x in ids])))}


def get_money_between(session, *, case_id, party_a, party_b, start_date=None, end_date=None, offset=0, limit=25):
    """Money between two parties through ``services.financial.money_between`` (the function the Graph pair edge
    uses): totals per currency, p3 stated beside, phone readings counted, the payments paged with citations, and
    how many open judgement calls the figure rests on."""
    from services.financial import money_between as MB
    case_id = _uuid(case_id, "case identifier")
    offset, limit = _page(offset, limit)
    start, end = _day(start_date), _day(end_date)
    try:
        a, b = MB.parse_side(_strip(party_a)), MB.parse_side(_strip(party_b))
        out = MB.money_between(session, case_id, a, b, from_date=start, to_date=end)
    except MB.NotInCase as exc:
        return _unavailable(MONEY_SCHEMA, case_id, str(exc))
    except MB.MoneyBetweenError as exc:
        raise LedgerReadingError(str(exc)) from exc
    mirrors = [r["mirrored_by"]["id"] for r in out["rows"] if r.get("mirrored_by")]
    docs = _source_documents(session, case_id, [r["id"] for r in out["rows"]] + mirrors)
    rows = [dict(r, source_document_id=docs.get(r["id"]), financial_href=payment_href(case_id, r["id"]),
                 **formatted(r["amount_minor"], r["currency"])) for r in out["rows"]]
    # a payment seen on both statements is one payment; the calls on its mirror row count too
    behind = open_calls_behind(judgement_index(session, case_id), [
        dict(r, _mirror_rows=[{"id": r["mirrored_by"]["id"], "source_document_id": docs.get(r["mirrored_by"]["id"])}]
             if r.get("mirrored_by") else []) for r in rows])
    return _paged(MONEY_SCHEMA, case_id, rows, offset, limit, out["revision"], a=out["a"], b=out["b"],
                  start_date=out["from_date"], end_date=out["to_date"], totals=_formatted_totals(out["totals"]),
                  amounts="Every *_minor figure is in the currency's minor units (currency_exponent decimals); quote the "
                          "formatted amount beside it, never the minor-unit integer as a whole amount.",
                  payments_by_class=out["payments_by_class"], shared_accounts=out["shared_accounts"],
                  phone_money_mentions=out["p4"], date_basis=out["date_basis"], basis=out["basis"],
                  graph=out["graph"], limits=out["limits"], open_judgement_calls=behind)


def _strip(value):
    """A ledger tool counterparty group key (``identity:party:<id>``) names the same side as ``party:<id>``."""
    if isinstance(value, str) and value.startswith("identity:"):
        return value[len("identity:"):]
    return value


# ---- judgement calls (C) ----------------------------------------------------------------------------------------

JUDGEMENT_SCHEMA = "loupe.agent.judgement_calls/1"
SUBJECT_KINDS = ("payment", "statement", "period", "account")


def _subject(value):
    if value in (None, ""):
        return None, None
    if not isinstance(value, str) or ":" not in value:
        raise LedgerReadingError("Name the subject as payment:<id>, statement:<id>, period:<id> or account:<id>.")
    kind, ident = value.split(":", 1)
    if kind not in SUBJECT_KINDS:
        raise LedgerReadingError("Name the subject as payment:<id>, statement:<id>, period:<id> or account:<id>.")
    return kind, _uuid(ident)


def _in_case(session, case_id, kind, ident) -> bool:
    from postgres.models.financial import (FinancialAccount, FinancialSourceDocument, FinancialStatementPeriod,
                                           FinancialTransaction)
    model = {"payment": FinancialTransaction, "statement": FinancialSourceDocument,
             "period": FinancialStatementPeriod, "account": FinancialAccount}[kind]
    row = session.get(model, ident)
    return row is not None and row.case_id == case_id


MAX_CHAIN = 50


def correction_chain(session, case_id, payment_id) -> list:
    """The payment and every earlier version it corrects (newest first): a correction's decision and its calls are
    recorded against the row it replaced, so a reader of the current row reads the whole chain."""
    from postgres.models.financial import FinancialTransaction
    chain, seen, current = [], set(), session.get(FinancialTransaction, payment_id)
    while current is not None and current.case_id == case_id and current.id not in seen and len(chain) < MAX_CHAIN:
        seen.add(current.id)
        chain.append(current.id)
        previous = ((current.provenance or {}).get("correction") or {}).get("previous_transaction_id")
        current = session.get(FinancialTransaction, _uuid(previous)) if previous else None
    return chain


def get_judgement_calls(session, *, case_id, subject=None, status=None, rule=None, offset=0, limit=25):
    """The case's judgement calls (``judgements.search``, the Judgement calls screen's own read), filtered by
    subject, status and rule; each with its sentence, page, file, who made it and whether a person resolved it."""
    from services.financial import judgements as J
    case_id = _uuid(case_id, "case identifier")
    offset, limit = _page(offset, limit)
    kind, ident = _subject(subject)
    if status not in (None, "", "open", "confirmed", "corrected"):
        raise LedgerReadingError("Status is open, confirmed or corrected.")
    if kind and not _in_case(session, case_id, kind, ident):
        return _unavailable(JUDGEMENT_SCHEMA, case_id, NOT_IN_CASE)
    query = dict(statuses=[status] if status else (), rule_ids=[rule] if rule else (), offset=offset, limit=limit)
    if kind == "payment":
        query["subject_ids"] = correction_chain(session, case_id, ident)
    elif kind == "statement":
        query["source_document_id"] = ident
    elif kind == "period":
        query["statement_period_id"] = ident
    elif kind == "account":
        query["account_ids"] = [str(ident)]
    found = J.search(session, case_id, **query)
    items = []
    for item in found["items"]:
        items.append(dict(id=item["id"], rule_id=item["rule_id"], rule_label=item["rule_label"],
                          category=item["category_label"], priority=item["priority_label"],
                          status=item["status"], strength=item["strength"], made_by=item["origin"],
                          summary=item["summary"], subject_type=item["subject_type"], subject_id=item["subject_id"],
                          account_id=item.get("account_id"), account_label=item.get("account_label"),
                          period_start=item.get("period_start"), period_end=item.get("period_end"),
                          filename=item["filename"], page=item["page"], resolved_by=item["resolved_by"],
                          resolved_at=item["resolved_at"], resolution_reason=item["resolution_reason"],
                          citation=dict(href=(payment_href(case_id, item["subject_id"])
                                              if item["subject_type"] == "transaction" else judgements_href(case_id)),
                                        filename=item["filename"], page=item["page"])))
    total = found["total"]
    nxt = offset + limit if offset + limit < total else None
    return dict(schema=JUDGEMENT_SCHEMA, case_id=str(case_id), available=True, reason=None,
                revision=_revision([found["total"], found["facets"].get("status"), [i["id"] for i in items]]),
                total=total, returned=len(items), offset=offset, has_more=nxt is not None, next_offset=nxt,
                items=items, counts_by_status=found["facets"].get("status", {}),
                note="Open calls are machine judgements no person has confirmed; a figure that rests on them is a "
                     "working figure.")


# ---- decisions (C) ----------------------------------------------------------------------------------------------

DECISION_SCHEMA = "loupe.agent.decisions/1"
DECISION_SUBJECT = {"payment": "transaction", "statement": "source_document", "period": "statement_period",
                    "account": "account"}


def _made_by(origin, actor_name):
    if origin and origin.get("kind") == "model":
        who = (origin.get("for") or {}).get("name") or actor_name
        return dict(kind="model", model=origin.get("model"), for_person=who,
                    label="Drafted by %s for %s; not a person's own decision" % (origin.get("model"), who))
    return dict(kind="person", model=None, for_person=actor_name, label="Decided by %s" % actor_name)


DECISION_SUBJECT_WORDS = {"transaction": "payment", "source_document": "statement", "statement_period": "period",
                          "account": "account"}


def _case_decisions(session, case_id, offset, limit):
    """Every recorded decision of the case, newest first, with counts by decision, by who decided and by whether a
    model drafted it (lx-agentlive: "how many decisions, and by whom" had no answer without naming one record)."""
    from sqlalchemy import func, select
    from postgres.models.financial import AdjudicationEvent
    cond = [AdjudicationEvent.case_id == case_id]
    total = int(session.scalar(select(func.count()).select_from(AdjudicationEvent).where(*cond)) or 0)
    by_decision = {d: int(n) for d, n in session.execute(select(AdjudicationEvent.decision, func.count()).where(
        *cond).group_by(AdjudicationEvent.decision).order_by(func.count().desc()))}
    by_subject = {DECISION_SUBJECT_WORDS.get(t, t): int(n) for t, n in session.execute(select(
        AdjudicationEvent.subject_type, func.count()).where(*cond).group_by(AdjudicationEvent.subject_type))}
    who: dict[str, dict] = {}
    model_drafted = 0
    for actor, origin in session.execute(select(AdjudicationEvent.actor_name, AdjudicationEvent.actor_origin)
                                         .where(*cond)):
        made = _made_by(origin, actor)
        model_drafted += made["kind"] == "model"
        label = made["label"]
        who.setdefault(label, {"made_by": label, "kind": made["kind"], "decisions": 0})["decisions"] += 1
    events = session.scalars(select(AdjudicationEvent).where(*cond).order_by(
        AdjudicationEvent.created_at.desc(), AdjudicationEvent.id).offset(offset).limit(limit)).all()
    items = []
    for e in events:
        kind = DECISION_SUBJECT_WORDS.get(e.subject_type, e.subject_type)
        href = payment_href(case_id, e.subject_id) if kind == "payment" else (
            accounts_href(case_id) if kind == "account" else judgements_href(case_id))
        items.append(dict(id=str(e.id), decision=e.decision, reason=e.reason, reason_kind=e.reason_kind,
                          subject="%s:%s" % (kind, e.subject_id), actor=e.actor_name,
                          made_by=_made_by(e.actor_origin, e.actor_name),
                          recorded_at=e.created_at.isoformat() if e.created_at else None,
                          citation=dict(href=href, subject="%s:%s" % (kind, e.subject_id))))
    nxt = offset + len(items) if offset + len(items) < total else None
    return dict(schema=DECISION_SCHEMA, case_id=str(case_id), available=True, reason=None, scope="whole case",
                revision=_revision([total, by_decision, [i["id"] for i in items]]), total=total,
                returned=len(items), offset=offset, has_more=nxt is not None, next_offset=nxt, items=items,
                counts_by_decision=by_decision, counts_by_subject=by_subject,
                counts_by_who=sorted(who.values(), key=lambda w: -w["decisions"]), model_drafted=model_drafted,
                person_decided=total - model_drafted,
                note="Counts cover every decision of the case; items are the newest, paged. A decision drafted by "
                     "a model (made_by.kind model) is not a person's own decision.")


def get_decisions(session, *, case_id, subject=None, offset=0, limit=25):
    """The recorded decisions (adjudications) on one subject, oldest first, each with who made it and, when a
    model drafted it, the model origin (``actor_origin``)."""
    from sqlalchemy import select
    from postgres.models.financial import AdjudicationEvent
    case_id = _uuid(case_id, "case identifier")
    offset, limit = _page(offset, limit)
    kind, ident = _subject(subject)
    if kind is None:
        return _case_decisions(session, case_id, offset, limit)
    if not _in_case(session, case_id, kind, ident):
        return _unavailable(DECISION_SCHEMA, case_id, NOT_IN_CASE)
    subjects = correction_chain(session, case_id, ident) if kind == "payment" else [ident]
    order = {sid: n for n, sid in enumerate(reversed(subjects))}  # oldest version first
    events = sorted(session.scalars(select(AdjudicationEvent).where(
        AdjudicationEvent.case_id == case_id, AdjudicationEvent.subject_type == DECISION_SUBJECT[kind],
        AdjudicationEvent.subject_id.in_(subjects))),
        key=lambda e: (order.get(e.subject_id, 0), e.subject_sequence))
    href = payment_href(case_id, ident) if kind == "payment" else (
        accounts_href(case_id) if kind == "account" else judgements_href(case_id))
    items = [dict(id=str(e.id), sequence=e.subject_sequence, decision=e.decision, reason=e.reason,
                  reason_kind=e.reason_kind, before=e.before, after=e.after, actor=e.actor_name,
                  actor_origin=e.actor_origin, made_by=_made_by(e.actor_origin, e.actor_name),
                  recorded_at=e.created_at.isoformat() if e.created_at else None,
                  on_row="this version" if e.subject_id == ident else "an earlier version this payment corrects",
                  subject_row_id=str(e.subject_id), citation=dict(href=href, subject=subject)) for e in events]
    return _paged(DECISION_SCHEMA, case_id, items, offset, limit,
                  _revision([[i["id"], i["sequence"]] for i in items]),
                  model_drafted=sum(i["made_by"]["kind"] == "model" for i in items))


# ---- statement continuity and coverage (C) ----------------------------------------------------------------------

CONTINUITY_SCHEMA = "loupe.agent.statement_continuity/1"


def _money(m):
    return None if m is None else dict(amount_minor=str(m.minor_units), currency=m.currency,
                                       **formatted(m.minor_units, m.currency))


def get_statement_continuity(session, *, case_id, account, offset=0, limit=50):
    """One account's statement run (``continuity.read_account_continuity``, the account and its merged aliases) and
    the coverage it supports (``correlation.coverage_from_continuity``): covered from and to, gaps (no statement),
    breaks (balances that do not meet), overlaps and periods whose arithmetic did not close (unverified)."""
    from sqlalchemy import select
    from postgres.models.financial import FinancialAccount, FinancialStatementPeriod
    from services.financial.account_consolidation import expand_account_ids
    from services.financial.continuity import read_account_continuity
    from services.financial.correlation import coverage_from_continuity
    case_id = _uuid(case_id, "case identifier")
    offset, limit = _page(offset, limit)
    account_id = _uuid(_strip_kind(account, "account"), "account identifier")
    row = session.get(FinancialAccount, account_id)
    if row is None or row.case_id != case_id:
        return _unavailable(CONTINUITY_SCHEMA, case_id, "That account is not in this case.")
    run = read_account_continuity(session, case_id=case_id, account_id=account_id)
    members = expand_account_ids(session, case_id, [account_id])
    statuses = list(session.execute(select(FinancialStatementPeriod.id, FinancialStatementPeriod.period_start,
                                           FinancialStatementPeriod.period_end,
                                           FinancialStatementPeriod.reconciliation_status).where(
        FinancialStatementPeriod.case_id == case_id, FinancialStatementPeriod.account_id.in_(members))))
    unverified = sorted((s.period_start, s.period_end) for s in statuses
                        if s.period_start and s.period_end and s.reconciliation_status != "balanced")
    status_of = {str(s.id): s.reconciliation_status for s in statuses}
    coverage = None
    if run.account_id is not None and run.periods:
        cov = coverage_from_continuity(run, holder=row.holder_name, unverified=unverified)
        coverage = dict(covered_from=cov.covered_from.isoformat() if cov.covered_from else None,
                        covered_to=cov.covered_to.isoformat() if cov.covered_to else None,
                        gaps=[[a.isoformat(), b.isoformat()] for a, b in cov.gaps],
                        breaks=[[a.isoformat(), b.isoformat()] for a, b in cov.breaks],
                        overlaps=[[a.isoformat(), b.isoformat()] for a, b in cov.overlaps],
                        unverified=[[a.isoformat(), b.isoformat()] for a, b in cov.unverified])
    items = []
    for p in run.periods:
        items.append(dict(kind="period", period_id=str(p.period_id), source_document_id=str(p.document_id),
                          start=p.start.isoformat(), end=p.end.isoformat(), currency=p.currency,
                          opening=_money(p.opening), closing=_money(p.closing),
                          reconciliation_status=status_of.get(str(p.period_id)),
                          citation=dict(href="/cases/%s/financial?view=statements&account=%s" % (case_id, account_id))))
    seams = [dict(kind=s.kind.value, agreement=s.agreement.value, uncovered_days=s.uncovered_days,
                  earlier_period_id=str(s.earlier.period_id), later_period_id=str(s.later.period_id),
                  earlier_end=s.earlier.end.isoformat(), later_start=s.later.start.isoformat(),
                  discrepancy=_money(s.discrepancy)) for s in run.seams]
    excluded = [dict(period_id=str(e.period_id), source_document_id=str(e.document_id), reason=e.reason.value,
                     detail=e.detail) for e in run.excluded]
    saved = len(run.periods) + len(excluded)
    left_out = ""
    if excluded:
        from collections import Counter
        why = Counter(e["reason"] for e in excluded)
        left_out = " %d saved period%s %s left out of the run (%s); %s cover%s no dates here." % (
            len(excluded), "" if len(excluded) == 1 else "s", "is" if len(excluded) == 1 else "are",
            ", ".join("%d %s" % (n, r.replace("_", " ")) for r, n in sorted(why.items())),
            "it" if len(excluded) == 1 else "they", "s" if len(excluded) == 1 else "")
    sentence = ("No dated statement period is saved for this account, so it covers no dates: an absence of payments "
                "here proves nothing." + left_out if not run.periods else
                "%d of %d saved statement period%s in the run, from %s to %s; %d gap%s, %d break%s, %d overlap%s, "
                "%d period%s whose arithmetic did not close." % (len(run.periods), saved, "" if saved == 1 else "s",
                                               coverage["covered_from"], coverage["covered_to"],
                                               len(coverage["gaps"]), "" if len(coverage["gaps"]) == 1 else "s",
                                               len(coverage["breaks"]), "" if len(coverage["breaks"]) == 1 else "s",
                                               len(coverage["overlaps"]), "" if len(coverage["overlaps"]) == 1 else "s",
                                               len(coverage["unverified"]),
                                               "" if len(coverage["unverified"]) == 1 else "s") + left_out)
    return _paged(CONTINUITY_SCHEMA, case_id, items, offset, limit,
                  _revision([items, seams, excluded, coverage]), account_id=str(account_id),
                  account_label=" · ".join(v for v in (row.holder_name, row.institution_name,
                                                       row.identifier_as_printed) if v) or None,
                  merged_accounts=len(members), periods_saved=saved, periods_in_run=len(run.periods),
                  coverage=coverage, seams=seams, excluded_periods=excluded,
                  sentence=sentence,
                  limitation="Coverage is from the printed statement dates. A gap means no saved statement covers "
                             "those days, not that the account was inactive.")


def _strip_kind(value, kind):
    if isinstance(value, str) and value.startswith(kind + ":"):
        return value[len(kind) + 1:]
    return value


# ---- account mentions (C) ---------------------------------------------------------------------------------------

MENTIONS_SCHEMA = "loupe.agent.account_mentions/1"


def get_account_mentions(session, *, case_id, search="", show="missing", offset=0, limit=25):
    """Account numbers printed in payment descriptions and counterparties (``account_mentions.account_references``),
    each with whether a statement for that account is in the case."""
    from services.financial.account_mentions import account_references
    case_id = _uuid(case_id, "case identifier")
    offset, limit = _page(offset, limit)
    if show not in ("missing", "all"):
        raise LedgerReadingError("Show is missing or all.")
    found = account_references(session, case_id=case_id, offset=offset, limit=limit, search=str(search or "")[:200],
                               show=show)
    items = []
    for g in found["items"]:
        items.append(dict(id=g["id"], reference=g["reference"], kind=g["kind"], partial=g["partial"],
                          status=g["status"], payment_count=g["payment_count"], variants=g["variants"],
                          possible_accounts=g["possible_accounts"],
                          examples=[dict(e, financial_href=payment_href(case_id, e["payment_id"]))
                                    for e in g["examples"]],
                          citation=dict(href=payment_href(case_id, g["examples"][0]["payment_id"])
                                        if g["examples"] else accounts_href(case_id))))
    total = found["total"]
    nxt = offset + limit if offset + limit < total else None
    return dict(schema=MENTIONS_SCHEMA, case_id=str(case_id), available=True, reason=None,
                revision=found["revision"], total=total, returned=len(items), offset=offset,
                has_more=nxt is not None, next_offset=nxt, items=items, scanned_payments=found["scanned_payments"],
                missing_count=found["missing_count"], possible_match_count=found["possible_match_count"],
                limitation="A mention is an account number printed on a payment; 'no_statement_found' means no "
                           "statement for a matching account is in this case, not that the account does not exist.")


# ---- connected payments (lx-linksuggest) ----------------------------------------------------------------------------

CONNECTED_SCHEMA = "loupe.agent.connected_payments.v1"


def _payment_id(session, case_id, payment):
    """A payment of this case by its id or its reference (ref_id); never another case's."""
    from sqlalchemy import select
    from postgres.models.financial import FinancialTransaction as FT
    text = _strip(payment)
    try:
        return UUID(text)
    except (TypeError, ValueError, AttributeError):
        found = session.scalar(select(FT.id).where(FT.case_id == case_id, FT.ref_id == text))
        if found is None:
            raise LedgerReadingError("No payment %s in this case." % text)
        return found


def _printed_not_named(p: dict) -> dict:
    """A payment with no printed counterparty: the screen fills its other side with the description, which is not a
    name (the system prompt's rule: a name comes only from from_name/to_name). For the agent that side is no name, the
    text is printed_text, and the name fit says names were not compared rather than reading as a disagreement."""
    if p.get("counterparty"):
        return p
    other = "to_name" if p.get("direction") == "debit" else "from_name"
    out = dict(p)
    if out.get(other) and out.get(other) != "not printed":
        out["printed_text"] = p.get("description")
    out[other] = None
    out["name_basis"] = ("No counterparty name is printed on this payment; %s is empty and the printed description is "
                         "in printed_text (any name you read in it is your reading)." % other)
    if (out.get("fits") or {}).get("name") == 0 and not out.get("name_similarity"):
        out["name_fit_words"] = ("Names were not compared: no counterparty name is printed on one side or both, so a "
                                 "name fit of 0 is not a disagreement.")
    return out


def find_connected_payments(session, *, case_id, payment, mode="connected", search="", offset=0, limit=25):
    """Ranked candidate payments for one payment (``services.financial.link_suggestions``): its possible other side
    (``connected``), the onward payments out of the account it arrived in (``onward``), or a case-wide search graded
    against it (``search``: amounts like 825.62, 800-900 or 825±10, dates 2024-01-02..2024-01-09, names, references).
    Each with its strength (rule-computed) and reasons; a person links, never the agent."""
    from services.financial import link_suggestions as LS
    case_id = _uuid(case_id, "case identifier")
    offset, limit = _page(offset, limit)
    if mode not in ("connected", "onward", "search"):
        raise LedgerReadingError("Mode is connected, onward or search.")
    ident = _payment_id(session, case_id, payment)
    try:
        if mode == "search":
            if not str(search or "").strip():
                raise LedgerReadingError("Give the search words, amount or dates.")
            out = LS.search_payments(session, case_id=case_id, q=str(search)[:300], transaction_id=ident,
                                     page=1, page_size=LS.MAX_PAGE_SIZE)
        else:
            fn = LS.suggest_onward if mode == "onward" else LS.suggest_connected
            out = fn(session, case_id=case_id, transaction_id=ident, page=1, page_size=LS.MAX_PAGE_SIZE)
    except LS.LinkSuggestionError as exc:
        if exc.status_code == 404:
            return _unavailable(CONNECTED_SCHEMA, case_id, str(exc))
        raise LedgerReadingError(str(exc)) from exc
    items = list(out["candidates"])
    # the service pages at most MAX_PAGE_SIZE; read every page so the agent's offset covers the whole list
    for page in range(2, out["pages"] + 1):
        fn_kw = dict(case_id=case_id, transaction_id=ident, page=page, page_size=LS.MAX_PAGE_SIZE)
        more = (LS.search_payments(session, q=str(search)[:300], **fn_kw) if mode == "search" else
                (LS.suggest_onward if mode == "onward" else LS.suggest_connected)(session, **fn_kw))
        items.extend(more["candidates"])
    items = [_printed_not_named(dict(c, financial_href=payment_href(case_id, c["id"]),
                                     citation=dict(href=payment_href(case_id, c["id"])))) for c in items]
    anchor = _printed_not_named(dict(out["anchor"], financial_href=payment_href(case_id, out["anchor"]["id"])))
    return _paged(CONNECTED_SCHEMA, case_id, items, offset, limit, _revision([c["id"] for c in items]),
                  mode=mode, anchor=anchor, by_level=out["by_level"], rule=out["rule"],
                  understood=out.get("understood"), left_out=out.get("left_out"),
                  limitation="These are possibilities computed by a stated rule, never links. Only a person links "
                             "payments; anything you propose is a model suggestion until a person links it.")


# ---- investigator timeline additions (D) -------------------------------------------------------------------------

TIMELINE_SOURCES = {"transaction": "ledger payment", "money_trail": "money trail", "workspace_entry": "finding",
                    "phone_record": "phone record"}


def timeline_additions(session, *, case_id, start_date=None, end_date=None, event_types=None, left_out=None):
    """Every event an investigator added to the case Timeline (``timeline_entries.list_entries``: ledger payments,
    money trails, findings, phone records), resolved to its current reading, labelled by source, oldest first."""
    from services.timeline_entries import list_entries
    case_id = _uuid(case_id, "case identifier")
    start, end = _day(start_date), _day(end_date)
    events, offset = [], 0
    while True:
        chunk = list_entries(session, case_id=case_id, offset=offset, limit=2000)
        events.extend(chunk)
        if len(chunk) < 2000:
            break
        offset += 2000
    out = []
    types = {str(t).casefold() for t in event_types or ()}
    skipped = {"undated_outside_window": 0, "other_types": 0}
    for e in events:
        d = e.get("date")
        if types and str(e.get("type") or "").casefold() not in types:
            skipped["other_types"] += 1
            continue
        if (start or end) and not d:
            # an undated addition cannot be placed in a window: counted, never shown as inside it
            skipped["undated_outside_window"] += 1
            continue
        if d and ((start and d < start.isoformat()) or (end and d > end.isoformat())):
            continue
        source = e.get("source") or {}
        kind = source.get("kind")
        href = None
        if kind == "transaction" and source.get("id"):
            href = payment_href(case_id, source["id"])
        out.append(dict(key=e.get("key"), date=d, time=e.get("time"), name=e.get("name"), type=e.get("type"),
                        summary=e.get("summary"), amount=e.get("amount"),
                        source="investigator addition: %s" % TIMELINE_SOURCES.get(kind, kind or "unknown"),
                        source_kind=kind, source_state=source.get("state"), source_id=source.get("id"),
                        date_basis=source.get("date_basis"),
                        citation=dict(href=href or "/cases/%s/timeline" % case_id)))
    out.sort(key=lambda x: (x["date"] or "9999", x["time"] or "", x["key"] or ""))
    if left_out is not None:
        left_out.update(skipped)
    return out
