"""Combined communication and money edges (docs/cellebrite/02 section 11, 05 section 17.8; 02-U16).

The one implementation (C11): spec 05's approach screens, spec 03's graph pair edges and ``POST
/api/phones/link-analysis/edges`` all read it.

A side is a person (a dossier: every phone identity linked to it, the ``reviewed`` level) or one identity (its exact
identity key). Communication is counted by the Conversations query itself (``streams.Query``) with the two sides
as ``between`` participants, so an edge's message, call and email counts equal Conversations' Between A and B under
the same ``group_scope`` and copy setting (03 R-1, R-3). Each event is counted in one direction only, by the
side that sent that copy (a forwarded message's original sender does not count it back the other way). Events with no
time are counted in ``no_time_count``; with a window set they are left out and the count is ``None`` (not
applicable).

Money comes from the ledger the way the reviewed identity graph reads it: admitted, current rows (``ledger_status
= 'admitted'``, ``superseded_by_id IS NULL``, so a corrected amount is the one used) whose reviewed payment
identity (``payment_counterparty_link.resolved_link``) is a party or account of one side, on an account held
(reviewed ``holder`` relationship) by a party of the other side. A party belongs to a dossier's side when an
account's reviewed entity link names it with the dossier's canonical entity (02 section 8.9). A debit on side A's
account to side B is paid A to B. Sums are integer minor units per currency, never across currencies; p0 to p2
(``DEFAULT_TOTAL_CLASSES``) are summed, p3 is stated separately, and p4 (phone money readings, approach 1) is only
counted as ``money_mentioned_on_phones``. Payments are sliced by the ledger's ordering date, stated as the basis.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timezone

from sqlalchemy import text

from services.phone import labels as L
from services.phone import streams
from services.phone import time_display as T
from services.phone.filters import StreamFilter

KIND_PREFIX = {"message": "messages", "call": "calls", "email": "emails"}
SLICES = ("day", "week", "month", "year")
SUMMED = ("p0", "p1", "p2")
STATED = ("p3",)
CLASSES_LABEL = "p0-p2"


class NotInCase(LookupError):
    """A subject that is not in the case (answered 404, never 403, so ids do not leak across cases)."""


# ---- sides -----------------------------------------------------------------------------------------------------

def resolve_side(conn, case_id, subject: dict) -> dict:
    """``{"subject", "label", "keys", "dossier_id", "entity_key"}``; ``NotInCase`` when the subject is in another
    case or nowhere."""
    case_id = str(case_id)
    if subject.get("dossier_id"):
        row = conn.execute(text(
            "SELECT id::text AS id, display_name, canonical_entity_key FROM case_profiles WHERE case_id = :c AND "
            "id::text = :d AND archived_at IS NULL"), {"c": case_id, "d": str(subject["dossier_id"])}).first()
        if row is None:
            raise NotInCase("That person is not in this case.")
        keys = sorted(r[0] for r in conn.execute(text(
            "SELECT identity_key FROM pv_identity WHERE case_id = :c AND person_id::text = :d"), {"c": case_id, "d": row.id}))
        return {"subject": {"dossier_id": row.id}, "label": row.display_name, "keys": keys, "dossier_id": row.id,
                "entity_key": row.canonical_entity_key}
    key = subject.get("identity_key")
    row = conn.execute(text(
        "SELECT identity_key, value_display FROM phone_identities WHERE case_id = :c AND identity_key = :k"),
        {"c": case_id, "k": key}).first() if key else None
    if row is None:
        raise NotInCase("That phone identity is not in this case.")
    return {"subject": {"identity_key": row.identity_key}, "label": row.value_display or row.identity_key,
            "keys": [row.identity_key], "dossier_id": None, "entity_key": None}


# ---- communication ----------------------------------------------------------------------------------------------

class _SidesQuery(streams.Query):
    """``streams.Query`` with the two ``between`` sides given as key sets (a dossier's linked identities, or one
    identity), so the WHERE clause is the one Conversations builds for Between A and B."""

    def __init__(self, conn, f, owner_keys, a_keys, b_keys):
        self._sides = (list(a_keys), list(b_keys))
        super().__init__(conn, f, owner_keys)

    def _participants(self):
        a, b = self._sides
        w, f = self.where, self.f
        direct = "((%s AND %s) OR (%s AND %s))" % (self.party(a, "s"), self.party(b, "r"), self.party(b, "s"),
                                                   self.party(a, "r"))
        group = "((%s AND %s) OR (%s AND %s))" % (self.party(a, "s"), self.member(b), self.party(b, "s"),
                                                  self.member(a))
        self.between_groups = None
        if f.group_scope == "direct":
            w.append("(%s AND NOT %s)" % (direct, self.is_group()))
        else:
            w.append("((%s AND NOT %s) OR (%s AND %s))" % (direct, self.is_group(), group, self.is_group()))


def _filter(case_id, from_instant, to_instant, group_scope, collapse_copies, kinds):
    return StreamFilter.model_validate({
        "case_id": str(case_id), "kinds": list(kinds), "group_scope": group_scope, "collapse_copies": collapse_copies,
        "from_instant": from_instant, "to_instant": to_instant,
        # a window leaves out events with no time, as Conversations does when a span is chosen
        "include_no_time": from_instant is None and to_instant is None})


def _zone(conn, case_id):
    z = streams.case_zone(conn, case_id)["name"]
    return "UTC" if T.is_utc(z) else z


def communication(conn, case_id, a_keys, b_keys, *, from_instant=None, to_instant=None, group_scope="direct",
                  collapse_copies=True, slice_by=None, ctx=None) -> dict:
    """Counts by kind and direction (A to B is sent by a key of A), first and last instant, phones, no-time count,
    and per-slice totals in the case display zone."""
    ctx = ctx or L.LabelContext(conn, case_id, "phone")
    owners = {e: o["keys"] for e, o in ctx.owners.items()}
    f = _filter(case_id, from_instant, to_instant, group_scope, collapse_copies, KIND_PREFIX)
    shown = "copy_rank = 1" if collapse_copies else "true"
    zone = _zone(conn, case_id)
    out = {"%s_%s" % (p, d): 0 for p in KIND_PREFIX.values() for d in ("ab", "ba")}
    # a window leaves out events with no time, so their count is not applicable then (None), not 0
    windowed = from_instant is not None or to_instant is not None
    out.update({"first_instant": None, "last_instant": None, "phones": [], "no_time_count": None if windowed else 0})
    phones, firsts, lasts, slices = set(), [], [], defaultdict(lambda: {"messages": 0, "calls": 0, "emails": 0})
    q = _SidesQuery(conn, f, owners, a_keys, b_keys)
    # each event goes one way only: to the side of its actual sender, or, when neither side sent this copy, to the
    # side of its original sender (a forwarded message is not also counted back to its author). The direction is a
    # column of the matched set, so both directions are counted over the one set of shown copies Conversations shows.
    a_sent = "(%s OR (NOT %s AND %s))" % (q.party(q._sides[0], "a"), q.party(q._sides[1], "a"), q.party(q._sides[0], "s"))
    q.params["zone"] = zone
    bucket = ("date_trunc('%s', sort_instant AT TIME ZONE :zone)::date" % slice_by) if slice_by else "NULL::date"
    for r in conn.execute(text(
            "WITH m AS (%s) SELECT kind, %s AS slice, count(*) FILTER (WHERE a_sent) AS n_ab, count(*) FILTER (WHERE "
            "NOT a_sent) AS n_ba, min(sort_instant) AS first, max(sort_instant) AS last, count(*) FILTER (WHERE "
            "sort_instant IS NULL) AS no_time, array_agg(DISTINCT extraction_id::text) AS phones FROM m WHERE %s "
            "GROUP BY 1, 2" % (q.matched_sql(columns=["%s AS a_sent" % a_sent]), bucket, shown)), q.params):
        out["%s_ab" % KIND_PREFIX[r.kind]] += int(r.n_ab)
        out["%s_ba" % KIND_PREFIX[r.kind]] += int(r.n_ba)
        if not windowed:
            out["no_time_count"] += int(r.no_time)
        phones.update(r.phones)
        if r.first:
            firsts.append(r.first)
            lasts.append(r.last)
        if slice_by and r.slice is not None:
            slices[r.slice][KIND_PREFIX[r.kind]] += int(r.n_ab) + int(r.n_ba)
    labels = ctx.phone_labels
    out["first_instant"] = min(firsts).isoformat() if firsts else None
    out["last_instant"] = max(lasts).isoformat() if lasts else None
    out["phones"] = sorted(labels.get(p, p) for p in phones)
    out["_slices"] = dict(slices)
    return out


def comm_total(c: dict, prefix: str) -> int:
    return c[prefix + "_ab"] + c[prefix + "_ba"]


# ---- money ------------------------------------------------------------------------------------------------------

def financial_sides(session, case_id, entity_keys) -> dict:
    """``{entity_key: {"parties": set, "accounts": set}}``: the reviewed financial parties an account's entity links
    name with that entity, and the accounts those parties hold (``holder`` relationship)."""
    from services.financial.account_identity import identity_state
    out = {k: {"parties": set(), "accounts": set()} for k in entity_keys if k}
    if not out:
        return out
    state = identity_state(session, case_id)
    for account in state["accounts"]:
        for link in (account.get("identity_review") or {}).get("entity_links") or []:
            if link.get("entity_key") in out:
                out[link["entity_key"]]["parties"].add(link["party_id"])
    for account in state["accounts"]:
        holders = {r["party"]["id"] for r in account.get("relationships") or [] if r.get("role") == "holder"}
        for side in out.values():
            if holders & side["parties"]:
                side["accounts"].add(account["id"])
    return out


def _within(d, from_date, to_date):
    """Inclusive at both ends, as the communication window is (``sort_instant <= to_instant``): the dates are the
    calendar days, in the case zone, of the window's first and last instants."""
    return (from_date is None or d >= from_date) and (to_date is None or d <= to_date)


def payments(session, case_id, side_a: dict, side_b: dict, *, from_date=None, to_date=None) -> dict:
    """The ledger rows between two financial sides: ``{"rows": [...], "both_sides_accounts": n}``. Each row:
    ``{id, ref_id, account_id, direction ("ab"|"ba"), amount_minor, currency, proof_class, ordering_date,
    ordering_date_source}``."""
    from sqlalchemy import or_, select
    from postgres.models.financial import FinancialTransaction
    from services.financial.payment_counterparty_link import resolved_link, stored_link
    from services.financial.proof_class import LEDGER_CLASSES
    accounts = side_a["accounts"] | side_b["accounts"]
    shared = side_a["accounts"] & side_b["accounts"]
    if not accounts:
        return {"rows": [], "shared_accounts": 0}
    rows = []
    # The window is in the query (inclusive at both ends, as _within is), so a one-day lookup reads that day's rows,
    # not every row of the holders' accounts.
    window = ([FinancialTransaction.ordering_date >= from_date] if from_date is not None else []) + (
        [FinancialTransaction.ordering_date <= to_date] if to_date is not None else [])
    for r in session.execute(select(
            FinancialTransaction.id, FinancialTransaction.ref_id, FinancialTransaction.account_id,
            FinancialTransaction.direction, FinancialTransaction.amount_minor, FinancialTransaction.currency,
            FinancialTransaction.proof_class, FinancialTransaction.ordering_date,
            FinancialTransaction.ordering_date_source,
            FinancialTransaction.metadata_['investigation_labels'],
            FinancialTransaction.provenance['reviewed_counterparty']).where(
            FinancialTransaction.case_id == case_id, FinancialTransaction.superseded_by_id.is_(None),
            FinancialTransaction.ledger_status == 'admitted',
            FinancialTransaction.proof_class.in_(sorted(c.value for c in LEDGER_CLASSES)),
            FinancialTransaction.account_id.in_([uuid.UUID(a) for a in accounts]),
            or_(FinancialTransaction.metadata_['investigation_labels']['counterparty_link'].isnot(None),
                FinancialTransaction.provenance['reviewed_counterparty'].isnot(None)), *window)
            .order_by(FinancialTransaction.ordering_date, FinancialTransaction.id)):
        account = str(r.account_id)
        if account in shared or not _within(r.ordering_date, from_date, to_date):
            continue
        identity = resolved_link(session, case_id, stored_link(r[9], r[10]))
        if not identity:
            continue
        kind = "parties" if identity["kind"] == "party" else "accounts"
        if account in side_a["accounts"] and identity["id"] in side_b[kind]:
            towards = "ab" if r.direction == "debit" else "ba"
        elif account in side_b["accounts"] and identity["id"] in side_a[kind]:
            towards = "ba" if r.direction == "debit" else "ab"
        else:
            continue
        rows.append({"id": str(r.id), "ref_id": r.ref_id, "account_id": account, "direction": towards,
                     "amount_minor": int(r.amount_minor), "currency": r.currency, "proof_class": str(r.proof_class),
                     "ordering_date": r.ordering_date.isoformat(), "ordering_date_source": r.ordering_date_source,
                     "_debit": r.direction == "debit", "_side": "a" if account in side_a["accounts"] else "b"})
    return {"rows": collapse_mirrored(rows), "shared_accounts": len(shared)}


def collapse_mirrored(rows) -> list:
    """One payment seen on both sides' statements (a debit in the payer's account, the credit in the payee's) is
    one payment: the ledger's own mirror rule (``flow.collapse_mirrors``: same parties, amount and currency, different
    accounts, dates within its settlement window). The kept row names its mirror; its class is the stronger of the
    two."""
    from services.financial.flow import FlowRow, Party, collapse_mirrors
    from services.financial.money import Money
    from postgres.models.enums import ProofClass, TransactionDirection
    sides = {"a": Party(key="side:a"), "b": Party(key="side:b")}
    flow_rows = [FlowRow(transaction_id=uuid.UUID(r["id"]), account_id=uuid.UUID(r["account_id"]),
                         ordering_date=date.fromisoformat(r["ordering_date"]),
                         amount=Money(minor_units=r["amount_minor"], currency=r["currency"]),
                         direction=TransactionDirection.debit if r["_debit"] else TransactionDirection.credit,
                         proof_class=ProofClass(r["proof_class"]), holder=sides[r["_side"]],
                         counterparty=sides["b" if r["_side"] == "a" else "a"]) for r in rows]
    _, pairs = collapse_mirrors(flow_rows)
    by_id = {r["id"]: r for r in rows}
    dropped = set()
    for p in pairs:
        kept, mirror = by_id[str(p.debit_id)], by_id[str(p.credit_id)]
        kept["mirrored_by"] = {"id": mirror["id"], "ref_id": mirror["ref_id"], "account_id": mirror["account_id"],
                               "ordering_date": mirror["ordering_date"]}
        kept["proof_class"] = p.proof_class.value
        dropped.add(mirror["id"])
    out = []
    for r in rows:
        if r["id"] in dropped:
            continue
        out.append({k: v for k, v in r.items() if not k.startswith("_")})
    return out


def money_totals(rows) -> list:
    """Per currency: p0 to p2 summed by direction, p3 stated separately; never across currencies."""
    by = {}
    for r in rows:
        if r["proof_class"] not in SUMMED + STATED:
            continue
        m = by.setdefault(r["currency"], {"currency": r["currency"], "classes": CLASSES_LABEL, "paid_ab_minor": 0,
                                         "payments_ab": 0, "paid_ba_minor": 0, "payments_ba": 0,
                                         "p3": {"paid_ab_minor": 0, "payments_ab": 0, "paid_ba_minor": 0,
                                                "payments_ba": 0}})
        target = m if r["proof_class"] in SUMMED else m["p3"]
        target["paid_%s_minor" % r["direction"]] += r["amount_minor"]
        target["payments_%s" % r["direction"]] += 1
    return [by[c] for c in sorted(by)]


def format_minor(amount_minor: int, currency: str) -> str:
    from services.financial.money import get_currency
    exp = get_currency(currency).exponent
    sign = "-" if amount_minor < 0 else ""
    digits = str(abs(amount_minor)).rjust(exp + 1, "0")
    whole, frac = (digits[:-exp], digits[-exp:]) if exp else (digits, "")
    whole = "{:,}".format(int(whole))
    return "%s %s%s%s" % (currency, sign, whole, ("." + frac) if exp else "")


def _plural(n, one, many=None):
    return "%s %s" % ("{:,}".format(n), one if n == 1 else (many or one + "s"))


def edge_label(comm: dict, money: list, financial: bool = True) -> str:
    """02 11.2 ``label``, computed, never stored. UI copy: no em dash. In a case with no financial evidence the label
    carries no money words at all (07 section 8, SA-4): the absence is said once, in ``money_absent``."""
    parts = []
    for prefix, word in (("calls", "call"), ("messages", "message"), ("emails", "email")):
        n = comm_total(comm, prefix)
        if n:
            parts.append(_plural(n, word))
    text_ = ", ".join(parts)
    money_parts, stated = [], []
    for m in money:
        n = m["payments_ab"] + m["payments_ba"]
        if n:
            money_parts.append("%s totalling %s (p0 to p2)" % (_plural(n, "payment"),
                                                                 format_minor(m["paid_ab_minor"] + m["paid_ba_minor"], m["currency"])))
        n3 = m["p3"]["payments_ab"] + m["p3"]["payments_ba"]
        if n3:
            stated.append("%s %s (p3)" % (_plural(n3, "more payment"),
                                         format_minor(m["p3"]["paid_ab_minor"] + m["p3"]["paid_ba_minor"], m["currency"])))
    if money_parts:
        text_ = ", ".join(x for x in (text_, "; ".join(money_parts)) if x)
    if stated:
        text_ = "; ".join(x for x in (text_, "; ".join(stated)) if x)
    if not financial:
        return text_ or "No calls, messages or emails in this period"
    return text_ or "No calls, messages, emails or payments in this period"


# ---- phone money readings (p4) ----------------------------------------------------------------------------------

def money_mentioned(conn, case_id, a_keys, b_keys, *, from_instant=None, to_instant=None) -> int | None:
    """Approach 1's money readings on messages between the two sides (p4: counted, never summed). None when no
    approach 1 run exists for the case."""
    exists = conn.execute(text("SELECT to_regclass('phone_analysis_runs') IS NOT NULL")).scalar()
    if not exists:
        return None
    run = conn.execute(text(
        "SELECT id FROM phone_analysis_runs WHERE case_id = :c AND approach = 'money_signals' AND status = 'completed' "
        "ORDER BY finished_at DESC NULLS LAST LIMIT 1"), {"c": str(case_id)}).scalar()
    if run is None:
        return None
    return int(conn.execute(text(
        "SELECT count(DISTINCT r.id) FROM phone_analysis_results r JOIN phone_analysis_result_records x ON "
        "x.result_id = r.id AND x.record_uid IS NOT NULL JOIN phone_comm_events ev ON ev.record_uid = x.record_uid "
        "JOIN phone_interpretation_state st ON st.extraction_id = ev.extraction_id AND st.generation = ev.generation "
        "JOIN phone_extractions e ON e.id = ev.extraction_id AND e.standing = 'active' AND e.case_id = :c "
        "WHERE r.run_id = :run AND r.case_id = :c AND ev.case_id = :c AND r.kind = 'money_reading' AND (CAST(:f AS timestamptz) IS NULL OR "
        "ev.sort_instant >= CAST(:f AS timestamptz)) AND (CAST(:t AS timestamptz) IS NULL OR ev.sort_instant < "
        "CAST(:t AS timestamptz)) AND EXISTS (SELECT 1 FROM phone_participations p WHERE p.record_uid = ev.record_uid "
        "AND p.generation = ev.generation AND p.identity_key = ANY(:a)) AND EXISTS (SELECT 1 FROM "
        "phone_participations p WHERE p.record_uid = ev.record_uid AND p.generation = ev.generation AND "
        "p.identity_key = ANY(:b))"), {"run": run, "c": str(case_id), "f": from_instant, "t": to_instant, "a": list(a_keys),
                                       "b": list(b_keys)}).scalar() or 0)


# ---- edges ------------------------------------------------------------------------------------------------------

def _date_in_zone(instant, zone, end=False):
    """The calendar day of ``instant`` in the case zone. For the end of a window, an instant at local midnight
    closes the day before (a window to 1 July 00:00 holds no payment dated 1 July)."""
    if instant is None:
        return None
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    if isinstance(instant, str):
        instant = datetime.fromisoformat(instant.replace("Z", "+00:00"))
    local = instant.astimezone(ZoneInfo(zone))
    if end and (local.hour, local.minute, local.second, local.microsecond) == (0, 0, 0, 0):
        return local.date() - timedelta(days=1)
    return local.date()


def _slice_start(d: date, slice_by: str) -> date:
    if slice_by == "day":
        return d
    if slice_by == "week":
        from datetime import timedelta
        return d - timedelta(days=d.weekday())
    if slice_by == "month":
        return d.replace(day=1)
    return d.replace(month=1, day=1)


def _slice_end(d: date, slice_by: str) -> date:
    from datetime import timedelta
    if slice_by == "day":
        return d + timedelta(days=1)
    if slice_by == "week":
        return d + timedelta(days=7)
    if slice_by == "month":
        return (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return d.replace(year=d.year + 1)


def edges(conn, case_id, subjects: list, *, from_instant=None, to_instant=None, slice_by=None,
          group_scope="direct", collapse_copies=True) -> dict:
    """02 11.2: one edge per pair of subjects, in the order given."""
    from sqlalchemy.orm import Session
    if slice_by is not None and slice_by not in SLICES:
        raise ValueError("slice is one of day, week, month, year")
    sides = [resolve_side(conn, case_id, s) for s in subjects]
    ctx = L.LabelContext(conn, case_id, "phone")
    zone = _zone(conn, case_id)
    session = Session(bind=conn)
    limits = []
    from services.phone import money_presence
    financial = money_presence.has_financial_evidence(conn, case_id)
    try:
        fin = financial_sides(session, case_id, [s["entity_key"] for s in sides])
        empty = {"parties": set(), "accounts": set()}
        out = []
        for i in range(len(sides)):
            for j in range(i + 1, len(sides)):
                a, b = sides[i], sides[j]
                comm = communication(conn, case_id, a["keys"], b["keys"], from_instant=from_instant,
                                     to_instant=to_instant, group_scope=group_scope, collapse_copies=collapse_copies,
                                     slice_by=slice_by, ctx=ctx)
                pay = payments(session, case_id, fin.get(a["entity_key"], empty), fin.get(b["entity_key"], empty),
                               from_date=_date_in_zone(from_instant, zone), to_date=_date_in_zone(to_instant, zone, end=True))
                if pay["shared_accounts"]:
                    limits.append({"code": "shared_account", "pair": [a["subject"], b["subject"]],
                                   "count": pay["shared_accounts"],
                                   "message": "%s held by both sides are left out of the money between them."
                                              % _plural(pay["shared_accounts"], "account")})
                money = money_totals(pay["rows"])
                slices = []
                if slice_by:
                    cs = comm["_slices"]
                    ms = defaultdict(list)
                    for r in pay["rows"]:
                        ms[_slice_start(date.fromisoformat(r["ordering_date"]), slice_by)].append(r)
                    for start in sorted(set(cs) | set(ms)):
                        c = cs.get(start, {"messages": 0, "calls": 0, "emails": 0})
                        slices.append({"from": start.isoformat(), "to": _slice_end(start, slice_by).isoformat(),
                                       **c, "money": [{"currency": m["currency"],
                                                       "paid_ab_minor": m["paid_ab_minor"], "payments_ab": m["payments_ab"],
                                                       "paid_ba_minor": m["paid_ba_minor"], "payments_ba": m["payments_ba"],
                                                       "p3": m["p3"]} for m in money_totals(ms.get(start, []))]})
                comm.pop("_slices")
                mentioned = money_mentioned(conn, case_id, a["keys"], b["keys"], from_instant=from_instant,
                                            to_instant=to_instant)
                out.append({"a": {**a["subject"], "label": a["label"]}, "b": {**b["subject"], "label": b["label"]},
                            "communication": comm, "money": money,
                            "money_mentioned_on_phones": mentioned or 0,
                            "money_readings_available": mentioned is not None,
                            "money_date_basis": "ledger ordering date",
                            "slices": slices, "label": edge_label(comm, money, financial)})
    finally:
        session.close()
    return {"edges": out, "limits": limits, "zone": zone, "group_scope": group_scope,
            "collapse_copies": collapse_copies, "financial_records": financial,
            "money_absent": None if financial else money_presence.NO_FINANCIAL_RECORDS}


def edge_records(conn, case_id, a: dict, b: dict, kind: str, *, from_instant=None, to_instant=None, offset=0,
                 limit=200, group_scope="direct", collapse_copies=True) -> dict:
    """The records behind one edge's counts: ``{total, offset, limit, items}``; ``total`` equals the edge count."""
    from sqlalchemy.orm import Session
    sa, sb = resolve_side(conn, case_id, a), resolve_side(conn, case_id, b)
    if kind == "payments":
        session = Session(bind=conn)
        try:
            zone = _zone(conn, case_id)
            fin = financial_sides(session, case_id, [sa["entity_key"], sb["entity_key"]])
            empty = {"parties": set(), "accounts": set()}
            rows = payments(session, case_id, fin.get(sa["entity_key"], empty), fin.get(sb["entity_key"], empty),
                            from_date=_date_in_zone(from_instant, zone), to_date=_date_in_zone(to_instant, zone, end=True))["rows"]
        finally:
            session.close()
        rows = [r for r in rows if r["proof_class"] in SUMMED + STATED]
        return {"total": len(rows), "offset": offset, "limit": limit, "items": rows[offset:offset + limit]}
    want = {"messages": "message", "calls": "call", "emails": "email"}[kind]
    ctx = L.LabelContext(conn, case_id, "phone")
    owners = {e: o["keys"] for e, o in ctx.owners.items()}
    f = _filter(case_id, from_instant, to_instant, group_scope, collapse_copies, [want])
    q = _SidesQuery(conn, f, owners, sa["keys"], sb["keys"])
    shown = "copy_rank = 1" if collapse_copies else "true"
    total = int(conn.execute(text("WITH m AS (%s) SELECT count(*) FROM m WHERE %s" % (q.matched_sql(), shown)),
                             q.params).scalar() or 0)
    q.params.update({"off": offset, "lim": limit})
    items = [{"event_uid": str(r.event_uid), "record_uid": str(r.record_uid), "extraction_id": str(r.extraction_id),
              "phone": ctx.phone_labels.get(str(r.extraction_id)), "kind": r.kind, "direction": r.direction,
              "instant": r.sort_instant.isoformat() if r.sort_instant else None,
              "link": "rec://%s" % r.record_uid}
             for r in conn.execute(text(
                 "WITH m AS (%s) SELECT event_uid, record_uid, extraction_id, kind, direction, sort_instant FROM m "
                 "WHERE %s ORDER BY sort_instant NULLS LAST, event_uid OFFSET :off LIMIT :lim" % (q.matched_sql(), shown)),
                 q.params)]
    return {"total": total, "offset": offset, "limit": limit, "items": items}
