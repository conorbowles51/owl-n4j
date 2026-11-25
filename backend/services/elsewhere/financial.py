"""The Financial part: ledger rows that bear on the subject.

Only admitted rows that are not replaced are read, so a corrected value is the one compared (the correction is the
row in use; the original stays in the row's history and is never matched).

Rules, strongest first:
- the same check number: **agrees**, unless the subject states one amount and the row's is another (**disagrees**);
- the same amount in the window: **agrees** when the account holder or the counterparty is one of the subject's
  people (named in full), otherwise a **possible match**;
- a firm or place the subject names, printed on a payment in the window: **agrees** when the account is one of the
  subject's people's, otherwise a **possible match**;
- a payment in the window that names a subject person as counterparty or in its description: a **possible
  match** (same person, near in time; nothing ties it to the subject). A payment is not listed only because it is
  on that person's own account: that would list every payment they made that week;
- an account ending the subject gives: the account it is, when the ledger has one.
Nothing found says which amounts, numbers and names were searched, over which dates, and which of the people's
accounts the ledger covers for those dates.
"""
from __future__ import annotations

import re

from sqlalchemy import text

from services.elsewhere import words as W
from services.elsewhere.subject import window

RECORD_WINDOW = (3, 14)      # days before and after a record: a payment usually follows the message about it
STATEMENT_WINDOW = (3, 3)
TERM_WINDOW = (30, 30)
PER_RULE = 3

ROW_SQL = ("SELECT t.id::text AS id, t.ordering_date, t.amount_minor, t.currency, t.direction, t.description, "
           "t.counterparty_raw, t.metadata -> 'investigation_labels' AS labels, a.holder_name, "
           "a.identifier_as_printed, a.institution_name, f.original_filename, f.id::text AS file_id, "
           "t.provenance -> 'locator' ->> 'page' AS page "
           "FROM financial_transactions t JOIN financial_accounts a ON a.id = t.account_id "
           "LEFT JOIN financial_source_documents d ON d.id = t.source_document_id "
           "LEFT JOIN evidence_files f ON f.id = d.evidence_file_id "
           "WHERE t.case_id = CAST(:c AS uuid) AND t.ledger_status = 'admitted' AND t.superseded_by_id IS NULL ")


def _rows(conn, case_id, cond, params, lo=None, hi=None, limit=200):
    sql = ROW_SQL + "AND (" + cond + ")"
    p = dict(params, c=str(case_id))
    if lo is not None:
        sql += " AND t.ordering_date >= :lo"
        p["lo"] = lo
    if hi is not None:
        sql += " AND t.ordering_date <= :hi"
        p["hi"] = hi
    sql += " ORDER BY t.ordering_date, t.row_index, t.id LIMIT %d" % limit
    return conn.execute(text(sql), p).fetchall()


def _ending(r):
    d = W.digits(r.identifier_as_printed)
    return d[-4:] if d else None


ABBREVIATIONS = {"pc", "llc", "inc", "ltd", "llp", "pllc", "plc", "na", "lp", "co"}


def holder_words(name):
    """A holder name as people write it: ``CORWEN STREET DENTAL PC`` is ``Corwen Street Dental PC``."""
    return " ".join(w.upper() if w.lower().strip(".,") in ABBREVIATIONS else w.capitalize()
                    for w in (name or "").split())


def _owner(r):
    return holder_words((r.holder_name or "").strip()) or "an account"


def _row_text(r):
    way = "in" if r.direction == "credit" else "out"
    acct = "%s's account" % _owner(r) if r.holder_name else "an account"
    if _ending(r):
        acct += " ending %s" % _ending(r)
    printed = (r.description or r.counterparty_raw or "").strip()
    return "%s %s on %s, %s%s" % (W.money_text(r.amount_minor, r.currency), way, acct, W.day_text(r.ordering_date),
                                  (": “%s”" % printed) if printed else "")


def _cite(r):
    page = int(r.page) if r.page and str(r.page).isdigit() else None
    label = r.original_filename or "Ledger row"
    if page:
        label += " p.%d" % page
    return {"kind": "transaction", "id": r.id, "href": "txn://%s" % r.id, "label": label,
            "evidence_file_id": r.file_id, "page": page}


def _row_names(r, holder=True):
    labels = r.labels if isinstance(r.labels, dict) else {}
    link = labels.get("counterparty_link") if isinstance(labels.get("counterparty_link"), dict) else {}
    return " ".join(str(x) for x in (r.holder_name if holder else None, r.counterparty_raw, r.description, labels.get("from_name"),
                                     labels.get("to_name"), link.get("label")) if x)


def _person_on(subject, r, holder=True):
    """The subject person named in full on the row (holder, counterparty or a name a person saved), else ``None``."""
    names = _row_names(r, holder)
    for n in subject.names(strong_only=True):
        if W.name_in(n, names):
            return n
    return None


def _anchor_amount(subject):
    return subject.amounts[0] if len(subject.amounts) == 1 else None


def _ref_cond(refs):
    conds, params = [], {}
    for i, ref in enumerate(refs):
        if ref.isdigit():
            conds.append("t.description ~* :r%d" % i)
            params["r%d" % i] = r"(^|[^0-9a-z])(chk|check|cheque|ck)\.?\s*(no\.?|#)?\s*0*%s([^0-9]|$)" % re.escape(ref)
        else:
            conds.append("t.description ILIKE :r%d" % i)
            params["r%d" % i] = "%%%s%%" % ref.replace("%", "").replace("_", "")
    return " OR ".join(conds), params


def part(conn, case_id, subject, zone) -> dict:
    items, seen = [], set()
    before, after = RECORD_WINDOW if subject.kind == "record" else STATEMENT_WINDOW
    lo, hi = window(subject, before, after)

    def add(rel, r, reason, matched, rank=0):
        if r.id in seen:
            return
        seen.add(r.id)
        items.append(W.item(rel, _row_text(r) + ".", reason, _cite(r), matched, _rank=rank))

    anchor = _anchor_amount(subject)
    if subject.references:
        cond, params = _ref_cond(subject.references)
        for r in _rows(conn, case_id, cond, params):
            if anchor and (r.amount_minor, r.currency) != anchor:
                add(W.DISAGREES, r, "Same check number, but the ledger shows %s, not %s." % (
                    W.money_text(r.amount_minor, r.currency), W.money_text(*anchor)), ["reference", "amount"])
            elif lo and not (lo <= r.ordering_date <= hi):
                add(W.POSSIBLE, r, "Same check number, outside the dates searched (%s)." % W.span_text(lo, hi),
                    ["reference"])
            else:
                add(W.AGREES, r, "Same check number%s." % (" and the same amount" if anchor else ""),
                    ["reference"] + (["amount"] if anchor else []))
    for minor, cur in subject.amounts:
        rows = _rows(conn, case_id, "t.amount_minor = :m AND t.currency = :cur", {"m": minor, "cur": cur}, lo, hi)
        for r in rows:
            who = _person_on(subject, r)
            if who:
                add(W.AGREES, r, "Same amount and %s is on the payment, %s." % (
                    who, W.when_words(W.days_apart(subject.anchor or lo, r.ordering_date)) if subject.anchor else
                    "inside the dates searched"), ["amount", "name", "date"])
            else:
                add(W.POSSIBLE, r, "Same amount inside the dates searched; nothing on the payment names the people "
                    "in this %s." % subject.kind, ["amount", "date"], rank=1)
    if subject.terms:
        tlo, thi = window(subject, *TERM_WINDOW)
        for term in subject.terms:
            rows = _rows(conn, case_id, "t.description ILIKE :q OR t.counterparty_raw ILIKE :q",
                         {"q": "%%%s%%" % term.replace("%", "").replace("_", "")}, tlo, thi, limit=50)
            rows = [r for r in rows if W.name_in(term, _row_names(r))]
            for r in rows[:PER_RULE]:
                who = _person_on(subject, r)
                if who and lo and lo <= r.ordering_date <= hi:
                    add(W.AGREES, r, "“%s” is printed on a payment on %s's account within the dates searched." % (
                        term, who), ["name", "date"])
                else:
                    add(W.POSSIBLE, r, "“%s” is printed on this payment; nothing else ties it to this %s." % (
                        term, subject.kind), ["name"], rank=2)
            if len(rows) > PER_RULE:
                items.append(W.item(W.POSSIBLE, "%s more payments print “%s” %s." % (
                    "{:,}".format(len(rows) - PER_RULE), term, W.span_text(tlo, thi)),
                    "Listed in Financial; only the first %d are shown here." % PER_RULE, {
                        "kind": "search", "screen": "financial", "query": term}, ["name"], _rank=3))
    strong = subject.names(strong_only=True)
    if strong and lo:
        conds, params = [], {}
        for i, n in enumerate(strong):
            toks = W.name_tokens(n)
            conds.append("(" + " AND ".join(
                "(t.counterparty_raw ILIKE :n%d_%d OR t.description ILIKE :n%d_%d)" % (i, j, i, j)
                for j in range(len(toks))) + ")")
            params.update({"n%d_%d" % (i, j): "%%%s%%" % t for j, t in enumerate(toks)})
        rows = [r for r in _rows(conn, case_id, " OR ".join(conds), params, lo, hi, limit=500)
                if r.id not in seen and _person_on(subject, r, holder=False)]
        if subject.anchor is not None:
            rows.sort(key=lambda r: abs(W.days_apart(subject.anchor, r.ordering_date)))
        for r in rows[:PER_RULE]:
            add(W.POSSIBLE, r, "%s is on this payment, %s; nothing else ties it to this %s." % (
                _person_on(subject, r, holder=False), W.when_words(W.days_apart(subject.anchor, r.ordering_date))
                if subject.anchor else W.span_text(lo, hi), subject.kind), ["name", "date"], rank=4)
        if len(rows) > PER_RULE:
            items.append(W.item(W.POSSIBLE, "%s more payments name %s %s." % (
                "{:,}".format(len(rows) - PER_RULE), W.join_words(strong), W.span_text(lo, hi)),
                "Listed in Financial; only the nearest %d are shown here." % PER_RULE,
                {"kind": "search", "screen": "financial", "query": strong[0], "start": lo.isoformat(),
                 "end": hi.isoformat()}, ["name"], _rank=5))
    for ending in subject.accounts:
        accts = conn.execute(text(
            "SELECT id::text AS id, holder_name, identifier_as_printed, institution_name FROM financial_accounts "
            "WHERE case_id = CAST(:c AS uuid) AND right(regexp_replace(coalesce(identifier_normalised, "
            "identifier_as_printed, ''), '\\D', '', 'g'), :n) = :d"),
            {"c": str(case_id), "n": len(ending), "d": ending}).fetchall()
        for a in accts:
            items.append(W.item(W.AGREES, "Account ending %s is %s's account%s, in the ledger." % (
                ending[-4:], holder_words(a.holder_name) or "an unnamed holder",
                (" at %s" % a.institution_name) if a.institution_name else ""),
                "Same account ending.", {"kind": "account", "id": a.id, "label": "Account ending %s" % ending[-4:]},
                ["account"]))
        if not accts:
            items.append(W.item(W.NOTHING, "No account ending %s is in the ledger." % ending[-4:],
                                "Searched every account in the case's financial records.", None, ["account"]))
    searched = _searched(subject, lo, hi)
    if not [i for i in items if i["relation"] != W.NOTHING]:
        items.append(W.item(W.NOTHING, "No payment in the ledger matches. %s" % searched, _coverage(conn, case_id,
                                                                                                   subject, lo, hi),
                            None))
    return {"searched": searched, "items": items}


def _searched(subject, lo, hi):
    what = []
    if subject.amounts:
        what.append("the amount%s %s" % ("" if len(subject.amounts) == 1 else "s",
                                         W.join_words([W.money_text(m, c) for m, c in subject.amounts])))
    if subject.references:
        what.append("check number%s %s" % ("" if len(subject.references) == 1 else "s",
                                           W.join_words(subject.references)))
    if subject.names(strong_only=True):
        what.append(W.join_words(subject.names(strong_only=True)))
    if subject.terms:
        what.append(W.join_words(["“%s”" % t for t in subject.terms]))
    if subject.accounts:
        what.append("account ending %s" % W.join_words([a[-4:] for a in subject.accounts]))
    if not what:
        return "Nothing to search the ledger for: no amount, check number, full name, firm or account was given."
    return "Searched for %s, %s." % (W.join_words(what), W.span_text(lo, hi))


def _coverage(conn, case_id, subject, lo, hi):
    """Which of the subject's people have accounts in the ledger, and whether statements cover the dates."""
    strong = subject.names(strong_only=True)
    if not strong:
        return "No full name to look up accounts by; single first names are not matched to account holders."
    out = []
    for n in strong:
        rows = conn.execute(text(
            "SELECT a.holder_name, a.identifier_as_printed, min(p.period_start) AS s, max(p.period_end) AS e FROM "
            "financial_accounts a LEFT JOIN financial_statement_periods p ON p.account_id = a.id WHERE a.case_id = "
            "CAST(:c AS uuid) AND a.holder_name ILIKE :q GROUP BY 1, 2"),
            {"c": str(case_id), "q": "%%%s%%" % W.name_tokens(n)[-1]}).fetchall()
        rows = [r for r in rows if W.name_in(n, r.holder_name)]
        if not rows:
            out.append("The ledger holds no account of %s." % n)
            continue
        for r in rows:
            d = W.digits(r.identifier_as_printed)[-4:]
            if r.s is None:
                out.append("%s's account ending %s has no statement period." % (n, d))
            elif lo and (r.s > lo or r.e < hi):
                out.append("%s's account ending %s has statements %s only, not the whole of the dates searched." % (
                    n, d, W.span_text(r.s, r.e)))
            else:
                out.append("%s's account ending %s has statements for the dates searched." % (n, d))
    return " ".join(out)
