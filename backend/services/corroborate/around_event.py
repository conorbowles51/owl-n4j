"""Money around chosen events (lx-overlapviews-b C; design Money.dc.html, screen 6).

The person chooses events (theft nights, dates a theory or finding states, dates typed in). For each event the money
from the event's day to a week after is read the way Corroborate reads it (``CaseStore.records``: the ledger as
admitted, superseded rows left out, and the payment alerts on the phones), and copies of one payment are folded by
the Corroborate rule (``model.dedupe``: same payer, payee, amount and day). A payment found in a bank row and on a
phone is BANK + PHONE; on a phone alone PHONE ONLY; in a bank row alone BANK ONLY.

A payment pattern is the same payer, payee and kind (transfer, cash deposit, check) after two or more events; each
is one column, ordered by its usual day after the event. The last row counts each pattern in every other week of the
period (the same weekday to the next), so "after every night and never otherwise" is stated, not implied.

Where a phone shows a payment and the account's bank rows for that month are not in the ledger, the cell says so
and names the statement in the case that covers the month, its printed page numbering and the pages the file does
not hold: a page to ask for. Nothing is truncated; every payment of a pattern is listed.
"""
from __future__ import annotations

import re
import statistics
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from services.corroborate import model as M

SPAN = timedelta(days=7)
MAX_EVENTS = 60
_CHECK = re.compile(r"\b(?:CHK|CHECK|CHEQUE)\s*#?\s*(\d{2,8})\b", re.I)
_PERIOD = re.compile(r"(\d{4}-\d{2}-\d{2})\s*(?:-|to|–)\s*(\d{4}-\d{2}-\d{2})")
_PAGE = re.compile(r"\bPage\s+(\d{1,3})\s+of\s+(\d{1,3})\b", re.I)


def kind_of(rec: dict) -> str:
    body = rec.get("body") or ""
    if rec.get("cash_deposit"):
        return "cash"
    if rec.get("check_deposit") or _CHECK.search(body):
        return "check"
    return "transfer"


def source_of(copies: list[str]) -> str:
    bank = any(c.startswith("financial_transaction:") for c in copies)
    phone = any(c.startswith("phone_record:") for c in copies)
    return "bank_and_phone" if bank and phone else ("phone_only" if phone else "bank_only")


def _windows(days: list[date], zone) -> list[tuple[datetime, datetime]]:
    return [(datetime.combine(d, time.min, zone).astimezone(timezone.utc),
             datetime.combine(d + SPAN, time.max, zone).astimezone(timezone.utc)) for d in days]


def _payments(store, days: list[date]) -> list[dict]:
    everyone = store.people()
    zone = M.tz(store.zone())
    recs = [r for r in store.records(everyone, _windows(days, zone), everyone) if r["kind"] in M.MONEY_KINDS]
    kept, _ = M.dedupe(recs)
    return kept


def _local_day(rec: dict, zone) -> date:
    return rec["at"].date() if rec.get("day_only") else rec["at"].astimezone(zone).date()


def around_events(store, events: list[dict], *, other_weeks: bool = True) -> dict[str, Any]:
    """``events``: [{date: 'YYYY-MM-DD', label}]. Returns the table: one row per event, one column per pattern."""
    if not events:
        raise ValueError("Choose at least one event.")
    if len(events) > MAX_EVENTS:
        raise ValueError(f"Choose at most {MAX_EVENTS} events; {len(events)} are chosen.")
    zone_name = store.zone()
    zone = M.tz(zone_name)
    evs = sorted(({"date": date.fromisoformat(e["date"]), "label": e.get("label") or ""} for e in events),
                 key=lambda e: e["date"])
    names = {p["key"]: p["label"] for p in store.people()}
    pays = _payments(store, [e["date"] for e in evs])

    def who(k):
        return names.get(k) if k else None

    cells: dict[tuple, dict[int, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in pays:
        day = _local_day(r, zone)
        for i, e in enumerate(evs):
            if e["date"] <= day <= e["date"] + SPAN:
                payee = (r.get("parties") or [None])[0]
                key = (r.get("owner"), payee, kind_of(r))
                cells[key][i].append({**r, "offset": (day - e["date"]).days, "day": day})
                break
    patterns = []
    for key, per in cells.items():
        if len(per) < 2:
            continue
        payer, payee, kind = key
        offs = [x["offset"] for v in per.values() for x in v]
        patterns.append({"key": key, "per": per, "offset": int(statistics.median(offs))})
    patterns.sort(key=lambda p: (p["offset"], -len(p["per"])))
    columns = []
    for n, p in enumerate(patterns):
        payer, payee, kind = p["key"]
        title = {"cash": f"Cash into {who(payer) or 'an account'}",
                 "check": f"{who(payer) or 'Unnamed payer'} → {who(payee) or 'an account'}, by check",
                 "transfer": f"{who(payer) or 'Unnamed payer'} → {who(payee) or 'unnamed payee'}"}[kind]
        if kind == "check" and not payer:
            title = f"Checks paid to {who(payee) or 'an account'}"
        if kind == "cash":
            title = f"Cash into {who(payer) or who(payee) or 'an account'}'s account"
        items = [x for v in p["per"].values() for x in v]
        checks = sorted({c for x in items for c in [_cell(store, x, zone)["check"]] if c is not None}) if kind == "check" else []
        columns.append({"id": f"p{n}", "title": title, "kind": kind, "payer": who(payer), "payee": who(payee),
                        "usual_day": p["offset"], "events": len(p["per"]), "of": len(evs),
                        "total_minor": sum(abs(x["amount_minor"] or 0) for x in items),
                        "checks": [checks[0], checks[-1]] if checks else None, "_key": p["key"]})
    rows = []
    for i, e in enumerate(evs):
        row = {"date": e["date"].isoformat(), "label": e["label"], "cells": {}}
        for c, p in zip(columns, patterns):
            row["cells"][c["id"]] = [_cell(store, x, zone) for x in p["per"].get(i, [])]
        rows.append(row)
    baseline = _other_weeks(store, evs, patterns, columns, zone) if other_weeks and columns else None
    for c in columns:
        c.pop("_key")
        seen = len(baseline["found"].get(c["id"], [])) if baseline and baseline.get("found") else 0
        weeks = baseline["weeks"] if baseline else 0
        # money as common in ordinary weeks as after the events is not around them: folded, with its counts
        c["ordinary"] = bool(weeks) and seen / weeks >= 0.5 * c["events"] / max(c["of"], 1)
        c["other_weeks_found"] = seen
    unmatched = [r for r in pays if not any((r.get("owner"), (r.get("parties") or [None])[0], kind_of(r)) == p["key"]
                                            for p in patterns)]
    return {"zone": zone_name, "span_days": SPAN.days, "events": [{"date": e["date"].isoformat(), "label": e["label"]} for e in evs],
            "columns": columns, "rows": rows, "other_weeks": baseline,
            "one_off": [_cell(store, r, zone) for r in unmatched],
            "rule": ("A pattern is the same payer, payee and kind of payment (transfer, cash, check) within a week "
                     "after two or more of the events. A payment held in a bank row and on a phone is counted once.")}


def _cell(store, r: dict, zone) -> dict:
    src = source_of(r["copies"])
    body = (r.get("body") or "").strip()
    m = _CHECK.search(body)
    out = {"amount_minor": abs(r["amount_minor"] or 0), "amount": M.fmt_money(abs(r["amount_minor"] or 0)),
           "day": _local_day(r, zone).isoformat(), "source": src, "words": body[:160],
           "check": int(m.group(1)) if m else None, "records": r["copies"]}
    out["banks"], words = _banks(store, [c.split(":", 1)[1] for c in r["copies"] if c.startswith("financial_transaction:")])
    if out["check"] is None:
        nums = [int(m.group(1)) for w in words for m in [_CHECK.search(w)] if m]
        out["check"] = nums[0] if nums else None
    if src == "phone_only":
        out["gap"] = statement_gap(store, r, _local_day(r, zone))
    return out


def _banks(store, ids: list[str]) -> tuple[list[str], list[str]]:
    """The accounts a payment's bank rows are on (the holder as printed, or "holder not read", and the bank), and the
    rows' own words (a check number is printed there)."""
    if not ids:
        return [], []
    rows = store.q("SELECT a.holder_name, a.institution_name, COALESCE(t.description, '') FROM financial_transactions t "
                   "JOIN financial_accounts a ON a.id = t.account_id WHERE t.case_id = :c AND t.id = ANY(CAST(:i AS uuid[]))",
                   i=ids).fetchall()
    return sorted({f"{h or 'holder not read'}, {b or 'bank not read'}" for h, b, _ in rows}), [w for _, _, w in rows]


def _other_weeks(store, evs, patterns, columns, zone) -> dict:
    """Each pattern counted in every other week of the period: the events' weekday to the next, weeks that do not
    overlap an event's week."""
    period = None
    try:
        from services.corroborate.area_compare import AreaReader
        period = AreaReader(store).period()
    except Exception:  # noqa: BLE001
        period = None
    if not period:
        return {"weeks": 0, "counts": {c["id"]: 0 for c in columns}, "words": "No period with phone records."}
    lo, hi = period
    wd = evs[0]["date"].weekday()
    start = lo + timedelta(days=(wd - lo.weekday()) % 7)
    taken = [(e["date"], e["date"] + SPAN) for e in evs]
    weeks = []
    d = start
    while d + SPAN <= hi + timedelta(days=1):
        if not any(a < d + SPAN and d < b for a, b in taken):  # a week that only touches an event week is ordinary
            weeks.append(d)
        d += timedelta(days=7)
    pays = _payments(store, weeks) if weeks else []
    counts = {c["id"]: [] for c in columns}
    seen: set[str] = set()
    for r in pays:
        day = _local_day(r, zone)
        if not any(w <= day <= w + SPAN for w in weeks):
            continue
        # a payment inside an event's week is in that event's row; the day a week touches is never counted twice
        if any(a <= day <= b for a, b in taken):
            continue
        ref = ",".join(sorted(r.get("copies") or [])) or str(id(r))
        if ref in seen:
            continue
        seen.add(ref)
        key = (r.get("owner"), (r.get("parties") or [None])[0], kind_of(r))
        for c, p in zip(columns, patterns):
            if p["key"] == key:
                counts[c["id"]].append(_cell(store, r, zone))
    return {"weeks": len(weeks), "from": weeks[0].isoformat() if weeks else None,
            "to": (weeks[-1] + SPAN).isoformat() if weeks else None, "found": counts}


def statement_gap(store, r: dict, day: date) -> dict | None:
    """When a phone shows a payment and the ledger has no row of the payer's (or payee's) account that month: the
    statement in the case covering the day, whether its rows are in the ledger, and the pages it prints but does
    not hold."""
    keys = [k for k in [r.get("owner"), *(r.get("parties") or [])] if k]
    people = {p["key"]: p for p in store.people()}
    for k in keys:
        for acc in people.get(k, {}).get("accounts", []):
            row = store.q("SELECT a.identifier_as_printed, a.holder_name, (SELECT count(*) FROM financial_transactions t "
                          "WHERE t.account_id = a.id AND t.superseded_by_id IS NULL AND date_trunc('month', "
                          "COALESCE(t.transaction_date, t.posted_date)) = date_trunc('month', CAST(:d AS date))) "
                          "FROM financial_accounts a WHERE a.case_id = :c AND a.id = :a", a=acc, d=day).first()
            if not row or row[2]:
                continue
            digits = re.sub(r"\D", "", row[0] or "")
            found = []
            for fid, name, content in store.q(
                    "SELECT f.id, f.original_filename, t.content FROM evidence_document_texts t JOIN evidence_files f ON "
                    "f.id = t.evidence_file_id WHERE f.case_id = :c AND f.deleted_at IS NULL AND "
                    "regexp_replace(t.content, '\\D', '', 'g') LIKE :p", p=f"%{digits}%" if len(digits) >= 6 else "-"):
                per = _PERIOD.search(content or "")
                if not per or not (date.fromisoformat(per.group(1)) <= day <= date.fromisoformat(per.group(2))):
                    continue
                printed = {(int(a), int(b)) for a, b in _PAGE.findall(content or "")}
                totals = {b for _, b in printed}
                held = sorted({a for a, _ in printed})
                missing = sorted(set(range(1, max(totals) + 1)) - set(held)) if len(totals) == 1 else []
                found.append({"file_id": str(fid), "name": name, "period": [per.group(1), per.group(2)],
                              "printed_total": max(totals) if len(totals) == 1 else None, "pages_held": held,
                              "pages_missing": missing})
            words = f"{people[k]['label']}'s bank rows for {day:%B %Y} are not in the ledger."
            if found:
                f = found[0]
                words += f" The statement {f['name']} in the case covers the month"
                if f["pages_missing"]:
                    words += (f"; it prints {len(f['pages_held']) + len(f['pages_missing'])} pages and the file holds "
                              f"page{'s' if len(f['pages_held']) != 1 else ''} {', '.join(map(str, f['pages_held']))}"
                              f" only. Ask for page{'s' if len(f['pages_missing']) != 1 else ''} "
                              f"{', '.join(map(str, f['pages_missing']))}.")
                else:
                    words += ", but its rows have not been added to the ledger."
            else:
                words += " No statement for that month is in the case. Ask for it."
            return {"person": people[k]["label"], "month": f"{day:%Y-%m}", "statements": found, "words": words}
    return None


def event_choices(store) -> list[dict]:
    """Dates a person can pick as events: dates the case's theories and findings state, and the dates documents
    state of themselves (written, signed, received), each with where it comes from."""
    from services.corroborate import incidents
    out = [{"date": i["date"], "label": i["title"], "from": "theory or finding", "words": i["words"]}
           for i in incidents.incident_dates(store.db, store.case)]
    from services import document_date_store as D
    names = {str(i): n for i, n in store.q("SELECT id, original_filename FROM evidence_files WHERE case_id = :c AND "
                                           "deleted_at IS NULL")}
    for v in D.effective(store.db, store.case):
        if v["kind"] == "period" or not v.get("date_from") or str(v["evidence_file_id"]) not in names:
            continue
        who = v.get("label") or (f"confirmed by {v['confirmed_by']}" if v.get("confirmed_by") else None)
        out.append({"date": str(v["date_from"])[:10], "label": f"{names[str(v['evidence_file_id'])]} ({v['kind']})",
                    "from": "document date", "words": v.get("words"), "reading": who})
    return sorted(out, key=lambda x: x["date"])
