"""Read-only phone tools for the agent (docs/cellebrite/07 section 7.1; 06 item 61a).

Schema ``loupe.agent.phone_<tool>/1``, to the ledger-tool standard: every result states ``total_matching``,
``returned``, ``has_more`` and ``next_offset``, a ``coverage`` sentence saying what was read, a ``limitation``
sentence when anything is left out, the unconfirmed readings by record, and a ``rec://`` link per record. The agent
reads phone records in full (Neil, 2026-11-01: "the agent should have full visibility of the phones"); sensitive values
(saved passwords, card numbers) stay masked as on screen.

Case scope (Neil: "Each case should only see the data within that case"): every tool takes the case id from the run,
never from the model, and every query names it. A phone, person or record that is not in the case is answered "not in
this case", the same words whether or not it exists elsewhere, so nothing leaks across cases.

The counts are the screens' counts: messages and calls come from the Conversations query (``services.phone.streams``,
copies collapsed as on screen), places from the Map's points view, money readings from approach 1's last run.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import text

NOT_IN_CASE = "Not in this case."
MAX_LIMIT = 100
DEFAULT_LIMIT = 40


def _schema(tool):
    return "loupe.agent.phone_%s/1" % tool


def _rec(uid):
    return "rec://%s" % uid


def _base(tool, case_id, **kw):
    return {"schema": _schema(tool), "case_id": str(case_id), "available": True, **kw}


def _not_in_case(tool, case_id, what):
    return {"schema": _schema(tool), "case_id": str(case_id), "available": False, "not_in_case": True,
            "reason": "%s %s" % (NOT_IN_CASE, what), "total_matching": 0, "returned": 0, "has_more": False,
            "items": []}


def _limit(n):
    return max(1, min(int(n or DEFAULT_LIMIT), MAX_LIMIT))


def _instant(value, end=False):
    """A date (whole day, in UTC) or an ISO instant; ``None`` for nothing."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        d = value
    else:
        s = str(value).strip()
        try:
            if len(s) == 10:
                d = date.fromisoformat(s)
            else:
                v = datetime.fromisoformat(s.replace("Z", "+00:00"))
                return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        except ValueError:
            raise ValueError("%r is not a date (YYYY-MM-DD) or a time (ISO 8601)." % value) from None
    return datetime.combine(d + timedelta(days=1) if end else d, time(0), tzinfo=timezone.utc)


# ---- phones and people --------------------------------------------------------------------------------------------

def _phone_ids(conn, case_id, phones):
    """Phone labels (``C5``) or ids to extraction ids in this case; ``(ids, unknown)``."""
    if not phones:
        return [], []
    from services.phone.readings import phone_labels
    labels = phone_labels(conn, case_id)
    by_label = {v.lower(): k for k, v in labels.items() if v}
    ids, unknown = [], []
    for p in phones:
        s = str(p).strip()
        if s.lower() in by_label:
            ids.append(by_label[s.lower()])
        elif s in labels:
            ids.append(s)
        else:
            unknown.append(s)
    return ids, unknown


def _people_hits(conn, case_id, q):
    """Every identity matching ``q`` (no cap), its phone names, and whether the match is exact: a phone's name for it
    or its value equal to ``q`` once folded, or the same number (seven or more digits, compared from the end)."""
    from services.phone import fold as phone_fold
    folded = phone_fold.fold(q)
    digits = "".join(ch for ch in q if ch.isdigit())
    idents = conn.execute(text(
        "SELECT i.identity_id, i.identity_key, i.kind, i.value_display, i.value_normalised FROM pv_identity i "
        "WHERE i.case_id = :c"), {"c": str(case_id)}).fetchall()
    names = {}
    for n in conn.execute(text("SELECT identity_id, extraction_id, name, is_phone_name FROM pv_identity_name WHERE "
                               "case_id = :c ORDER BY extraction_id"), {"c": str(case_id)}):
        names.setdefault(n.identity_id, []).append(n)

    def hit(r):
        hay = [r.value_display, r.identity_key] + [n.name for n in names.get(r.identity_id, [])]
        if folded and any(folded in phone_fold.fold(h) for h in hay if h):
            return True
        return len(digits) >= 3 and digits in "".join(ch for ch in (r.value_normalised or "") if ch.isdigit())

    def exact(r):
        hay = [r.value_display, r.identity_key] + [n.name for n in names.get(r.identity_id, [])]
        if folded and any(folded == phone_fold.fold(h) for h in hay if h):
            return True
        own = "".join(ch for ch in (r.value_normalised or "") if ch.isdigit())
        return len(digits) >= 7 and len(own) >= 7 and (own.endswith(digits) or digits.endswith(own))

    hits = [r for r in idents if hit(r)]
    return hits, names, {r.identity_key for r in hits if exact(r)}


def find_people(conn, case_id, query, limit=20) -> dict:
    """Identities on the case's phones whose number, address or any phone's name for them matches ``query``
    (folded as Search folds; three or more digits match a number's digits)."""
    from services.phone.readings import phone_labels
    q = (query or "").strip()
    if not q:
        raise ValueError("Say whose name, number or address to look for.")
    hits, names, exact = _people_hits(conn, case_id, q)
    if not hits:
        return _not_in_case("find_people", case_id, "No one on the phones in this case matches %r." % q)
    counts = {k: int(n) for k, n in conn.execute(text(
        "SELECT identity_key, count(DISTINCT event_uid) FROM pv_comm_party WHERE case_id = :c AND identity_key = "
        "ANY(CAST(:k AS text[])) GROUP BY identity_key"), {"c": str(case_id), "k": [r.identity_key for r in hits]})}
    hits.sort(key=lambda r: (-counts.get(r.identity_key, 0), r.value_display or "", r.identity_key))
    labels = phone_labels(conn, case_id)
    lim = _limit(limit)
    items = [{"identity_key": r.identity_key, "kind": r.kind, "value": r.value_display,
              "names": [{"phone": labels.get(str(n.extraction_id)), "name": n.name}
                        for n in names.get(r.identity_id, []) if n.is_phone_name],
              "events": counts.get(r.identity_key, 0), "exact": r.identity_key in exact} for r in hits[:lim]]
    return _base("find_people", case_id, total_matching=len(hits), returned=len(items),
                 has_more=len(hits) > len(items), next_offset=None, items=items,
                 coverage="Searched every identity on the %d phone(s) in this case." % len(labels),
                 limitation=None if len(hits) <= len(items) else
                 "Showing the %d people with the most messages and calls of %d that match." % (len(items), len(hits)))


def _resolve_people(conn, case_id, people):
    """Each person named (an identity key, number, address or name) to exactly one identity in this case:
    ``(keys, problem)``. ``problem`` is ``None``, or a result to return as it is: "Not in this case." naming who was
    not found, or, when a name fits several identities and none exactly, the candidates to choose from. Nobody is
    dropped and no identity is added that was not asked for."""
    keys, unknown, unclear = [], [], []
    for p in people or []:
        s = str(p).strip()
        if not s:
            continue
        key = conn.execute(text("SELECT identity_key FROM pv_identity WHERE case_id = :c AND identity_key = :k"),
                           {"c": str(case_id), "k": s}).scalar()
        if key:
            keys.append(key)
            continue
        hits, _, exact = _people_hits(conn, case_id, s)
        pick = sorted(exact) if exact else [r.identity_key for r in hits]
        if not pick:
            unknown.append(s)
        elif len(pick) == 1:
            keys.append(pick[0])
        else:
            unclear.append((s, pick))
    if unknown:
        return keys, "unknown", "No one on the phones in this case matches %s." % ", ".join(repr(u) for u in unknown)
    if unclear:
        return keys, "unclear", unclear
    return list(dict.fromkeys(keys)), None, None


def _people_problem(tool, case_id, kind, detail):
    if kind == "unknown":
        return _not_in_case(tool, case_id, detail)
    return {"schema": _schema(tool), "case_id": str(case_id), "available": False, "not_in_case": False,
            "reason": " ".join("%r fits %d people on the phones; say which one (by identity_key)." % (s, len(ks))
                               for s, ks in detail),
            "candidates": {s: ks[:MAX_LIMIT] for s, ks in detail}, "total_matching": 0, "returned": 0,
            "has_more": False, "items": []}


# ---- messages and calls -------------------------------------------------------------------------------------------

def _row_out(r):
    from services.phone import labels as L
    t = r.get("time") or {}
    return {"rec": _rec(r["record_uid"]), "record_uid": r["record_uid"], "kind": r["kind"],
            "phone": r["phone"].get("label"), "app": r.get("app"), "direction": r.get("direction"),
            "time": t.get("full"), "instant": t.get("instant"), "line": r.get("line"),
            "from": L.label_text(r["from"]) if r.get("from") else None,
            "to": [L.label_text(x) for x in r.get("to") or []], "body": r.get("body"), "subject": r.get("subject"),
            "call": (r.get("call") or {}).get("words"),
            "attachments": [a.get("filename") for a in r.get("attachments") or []],
            "badges": r.get("flags") or [], "copies": (r.get("copies") or {}).get("count", 1),
            "thread": (r.get("thread") or {}).get("title"),
            "unconfirmed": r.get("interpretation_level") == "applied_unconfirmed"}


def messages(conn, case_id, *, people=(), mode="between", start=None, end=None, phones=(), kinds=(), search=None,
             include_groups=False, offset=0, limit=DEFAULT_LIMIT) -> dict:
    """Messages and calls under one Conversations filter: between people (``between``), involving any of them
    (``any``), in a window, on some phones, or containing words (``search``). Every row in full, oldest first."""
    from services.phone import streams
    from services.phone.filters import StreamFilter
    tool = "messages"
    keys, problem, detail = _resolve_people(conn, case_id, people)
    if problem:
        return _people_problem(tool, case_id, problem, detail)
    notes = []
    ext_ids, unknown_phones = _phone_ids(conn, case_id, phones)
    if unknown_phones:
        return _not_in_case(tool, case_id, "There is no phone %s in this case." % ", ".join(unknown_phones))
    if mode == "between" and len(keys) < 2:
        mode = "any"
    a, b = _instant(start), _instant(end, end=True)
    f = StreamFilter.model_validate({
        "case_id": str(case_id), "phones": ext_ids, "participants": keys,
        "participant_mode": mode if keys else "any", "group_scope": "include_groups" if include_groups else "direct",
        "kinds": list(kinds or []), "from_instant": a, "to_instant": b, "include_no_time": a is None and b is None,
        "text": {"query": (search or "").strip()}, "zone": {"mode": "case"}})
    idx = streams.index_comm_events(conn, f)
    counts = idx["counts"]
    total = int(counts.get("events") or 0)
    offset, lim = max(0, int(offset or 0)), _limit(limit)
    days = [(d["day"], d["count"]) for d in idx["items"]] + ([(None, idx["no_time_count"])]
                                                            if idx["no_time_count"] else [])
    rows, seen = [], 0
    for day, n in days:
        if seen + n <= offset:
            seen += n
            continue
        start_in = max(0, offset - seen)
        while start_in < n and len(rows) < lim:
            w = streams.window_comm_events(conn, f, snapshot_token=idx["snapshot"], day=day, offset=start_in,
                                           limit=min(streams.WINDOW_MAX, lim - len(rows)))
            if not w["items"]:
                break
            rows += w["items"]
            start_in += len(w["items"])
        seen += n
        if len(rows) >= lim:
            break
    items = [_row_out(r) for r in rows]
    nxt = offset + len(items) if offset + len(items) < total else None
    phones_n = int(counts.get("phones") or 0)
    window = ("on %s" % a.date().isoformat() if a and b and b - a == timedelta(days=1) and a.time() == time(0)
              else "from %s to %s" % (a.date().isoformat(), (b - timedelta(seconds=1)).date().isoformat())
              if a and b else "from %s" % a.date().isoformat() if a else "until %s" % (
                  b - timedelta(seconds=1)).date().isoformat() if b else "over every date")
    coverage = "Read %d of %d messages and calls on %d phone%s %s%s (times in %s)." % (
        len(items), total, phones_n, "" if phones_n == 1 else "s", window,
        "; repeated copies counted once" if counts.get("collapsed_copies") else "", idx["zone"]["label"])
    limits = [lim_["message"] for lim_ in idx.get("limits") or []]
    limitation = " ".join(([("Only %d of %d are in this result; read on with offset %d." % (len(items), total, nxt))]
                           if nxt is not None else []) + notes + limits) or None
    unconfirmed = [i["rec"] for i in items if i["unconfirmed"]]
    out = _base(tool, case_id, total_matching=total, returned=len(items), has_more=nxt is not None,
                next_offset=nxt, offset=offset, items=items, coverage=coverage, limitation=limitation,
                unconfirmed=unconfirmed, unconfirmed_sentence=(
                    "%d of these rely on readings not yet confirmed by a person: %s." % (
                        len(unconfirmed), ", ".join(unconfirmed))) if unconfirmed else None,
                counts={"messages": int(counts.get("messages") or 0), "calls": int(counts.get("calls") or 0),
                        "no_time": int(counts.get("no_time") or 0)})
    if idx.get("group_totals"):
        out["group_totals"] = idx["group_totals"]
        out["group_sentence"] = ("Group chats they share are not counted here: %d more messages in %d group "
                                 "threads." % (idx["group_totals"]["events"], idx["group_totals"]["threads"]))
    return out


def contact_summary(conn, case_id, person) -> dict:
    """One person's messages and calls on every phone: totals by kind, the first and the last contact."""
    from services.phone import streams
    from services.phone.filters import StreamFilter
    keys, problem, detail = _resolve_people(conn, case_id, [person])
    if problem:
        return _people_problem("contact_summary", case_id, problem, detail)
    notes = []
    f = StreamFilter.model_validate({"case_id": str(case_id), "participants": keys, "participant_mode": "any",
                                     "group_scope": "include_groups", "zone": {"mode": "case"}})
    idx = streams.index_comm_events(conn, f)
    total = int(idx["counts"].get("events") or 0)
    first = last = None
    if idx["items"]:
        d0, d1 = idx["items"][0]["day"], idx["items"][-1]["day"]
        w0 = streams.window_comm_events(conn, f, snapshot_token=idx["snapshot"], day=d0, offset=0, limit=1)
        first = _row_out(w0["items"][0]) if w0["items"] else None
        n1 = idx["items"][-1]["count"]
        w1 = streams.window_comm_events(conn, f, snapshot_token=idx["snapshot"], day=d1, offset=n1 - 1, limit=1)
        last = _row_out(w1["items"][0]) if w1["items"] else None
    c = idx["counts"]
    return _base("contact_summary", case_id, identity_keys=keys, total_matching=total, returned=0,
                 has_more=False, next_offset=None, items=[],
                 counts={"messages": int(c.get("messages") or 0), "calls": int(c.get("calls") or 0),
                         "no_time": int(c.get("no_time") or 0), "phones": int(c.get("phones") or 0)},
                 first_contact=first, last_contact=last,
                 coverage="Counted every message and call with %s on %d phone(s), group chats included, repeated "
                          "copies once (times in %s)." % (person, int(c.get("phones") or 0), idx["zone"]["label"]),
                 limitation=" ".join(notes) or None)


# ---- coverage, places, money ---------------------------------------------------------------------------------------

def totals(conn, case_id) -> dict:
    """The case's phone totals for the other tools' sentences (07 section 7.1): phones, messages and calls as
    Conversations counts them with no filter (copies once), and recorded location points. Zero phones: all zero."""
    from services.phone import records
    phones = records.phones(conn, case_id)
    if not phones:
        return {"phones": 0, "messages_and_calls": 0, "location_points": 0}
    events = messages(conn, case_id, limit=1)
    points = int(conn.execute(text("SELECT count(*) FROM pv_location_point WHERE case_id = :c AND lat IS NOT NULL "
                                   "AND lon IS NOT NULL"), {"c": str(case_id)}).scalar())
    return {"phones": len(phones), "messages_and_calls": int(events.get("total_matching") or 0),
            "location_points": points}


def not_in_result_sentence(t: dict, what: str = "Phone messages and calls") -> str | None:
    """'Phone messages and calls are not in this result; 186,787 are on the phones. Use the phone tools.'"""
    n = t.get("location_points") if what.startswith("Phone location") else t.get("messages_and_calls")
    if not t.get("phones") or not n:
        return None
    return "%s are not in this result; %s %s on the phones. Use the phone tools." % (
        what, "{:,}".format(n), "is" if n == 1 else "are")


def coverage(conn, case_id) -> dict:
    """The case's phones: owner, the period each covers, what each holds, deleted records, and what is incomplete."""
    from services.phone import labels as L
    from services.phone import records
    phones = records.phones(conn, case_id)
    if not phones:
        return _not_in_case("coverage", case_id, "This case has no phones.")
    spans = {str(r.extraction_id): r for r in conn.execute(text(
        "SELECT extraction_id, min(sort_instant) AS first, max(sort_instant) AS last, count(*) FILTER (WHERE "
        "lower(coalesce(deleted_state, '')) = 'deleted') AS deleted FROM pv_comm_event WHERE case_id = :c GROUP BY "
        "extraction_id"), {"c": str(case_id)})}
    from services.phone import time_display as T
    items = []
    for p in phones:
        s = spans.get(p["extraction_id"])
        items.append({"phone": p["label"], "owner": L.label_text(p["owner"]) if p.get("owner") else None,
                      "standing": p["standing"], "state": p["state"], "device_zone": p.get("device_zone"),
                      "first_event": T.iso(s.first) if s and s.first else None,
                      "last_event": T.iso(s.last) if s and s.last else None,
                      "deleted_messages_and_calls": int(s.deleted) if s else 0, "counts": p["counts"]})
    incomplete = [i["phone"] for i in items if i["state"] != "ingested" or i["standing"] != "active"]
    return _base("coverage", case_id, total_matching=len(items), returned=len(items), has_more=False,
                 next_offset=None, items=items,
                 coverage="Every phone in this case (%d)." % len(items),
                 limitation=("Not fully read yet or not active: %s." % ", ".join(incomplete)) if incomplete else None)


def places(conn, case_id, *, start=None, end=None, phones=(), offset=0, limit=DEFAULT_LIMIT) -> dict:
    """Location points recorded on the phones in a window, oldest first, with each one's accuracy as reported."""
    ext_ids, unknown = _phone_ids(conn, case_id, phones)
    if unknown:
        return _not_in_case("places", case_id, "There is no phone %s in this case." % ", ".join(unknown))
    a, b = _instant(start), _instant(end, end=True)
    where = ["p.case_id = :c", "p.lat IS NOT NULL", "p.lon IS NOT NULL"]
    params = {"c": str(case_id)}
    if ext_ids:
        where.append("p.extraction_id = ANY(CAST(:e AS uuid[]))")
        params["e"] = ext_ids
    if a:
        where.append("p.instant >= :a")
        params["a"] = a
    if b:
        where.append("p.instant < :b")
        params["b"] = b
    w = " AND ".join(where)
    total = int(conn.execute(text("SELECT count(*) FROM pv_location_point p WHERE %s" % w), params).scalar())
    offset, lim = max(0, int(offset or 0)), _limit(limit)
    from services.phone import time_display as T
    from services.phone.readings import phone_labels
    labels = phone_labels(conn, case_id)
    items = [{"rec": _rec(r.record_uid), "phone": labels.get(str(r.extraction_id)), "kind": r.model_type,
              "lat": r.lat, "lon": r.lon, "accuracy_m": float(r.accuracy_m) if r.accuracy_m is not None else None,
              "instant": T.iso(r.instant), "source": r.source_kind, "deleted_state": r.deleted_state,
              "unconfirmed": r.interpretation_level == "applied_unconfirmed"}
             for r in conn.execute(text(
                 "SELECT p.record_uid, p.extraction_id, p.model_type, p.lat, p.lon, p.accuracy_m, p.instant, "
                 "p.source_kind, p.deleted_state, p.interpretation_level FROM pv_location_point p WHERE %s ORDER BY "
                 "p.instant NULLS LAST, p.point_uid OFFSET :o LIMIT :l" % w), {**params, "o": offset, "l": lim})]
    nxt = offset + len(items) if offset + len(items) < total else None
    return _base("places", case_id, total_matching=total, returned=len(items), has_more=nxt is not None,
                 next_offset=nxt, items=items,
                 coverage="Read %d of %d location points%s." % (len(items), total, (
                     " from %s" % a.date().isoformat() if a else "") + (
                     " to %s" % (b - timedelta(seconds=1)).date().isoformat() if b else "")),
                 limitation=("Only %d of %d are in this result; read on with offset %d." % (len(items), total, nxt))
                 if nxt is not None else None,
                 unconfirmed=[i["rec"] for i in items if i["unconfirmed"]])


REJECTED_OUTCOME = "rule match rejected by a person"


def money_readings(conn, case_id, *, outcome=None, offset=0, limit=DEFAULT_LIMIT) -> dict:
    """Approach 1's last completed run: money the phones record, each checked against the ledger. Every reading is
    a reading from a phone (p4), never a statement."""
    run = conn.execute(text(
        "SELECT id, finished_at FROM phone_analysis_runs WHERE case_id = :c AND approach = 'money_signals' AND status "
        "= 'completed' ORDER BY finished_at DESC NULLS LAST LIMIT 1"), {"c": str(case_id)}).first()
    if run is None:
        return _base("money_readings", case_id, total_matching=0, returned=0, has_more=False, next_offset=None,
                     items=[], coverage="Money on the phones has not been run in this case.",
                     limitation="Run it from Money on the phones; until then there is nothing to read.")
    from services.phone_analysis import money_pairings
    where = "r.run_id = :r AND r.kind = 'money_reading'"
    params = {"r": run.id}
    rejected = money_pairings.rejected_links(conn, case_id)
    offset, lim = max(0, int(offset or 0)), _limit(limit)
    if rejected:
        # 05 4.3.8: a rule match a person rejected is not corroboration; the reading is relabelled, so the outcome
        # filter and the total are applied after the decisions are read
        everything = conn.execute(text(
            "SELECT r.id, r.measures, r.strength FROM phone_analysis_results r WHERE %s ORDER BY r.period_start NULLS "
            "LAST, r.id" % where), params).fetchall()
        relabel = {}
        for r in everything:
            m = r.measures or {}
            if m.get("outcome") in ("corroborated", "near_amount") and any(
                    (m.get("record_uid"), x.get("transaction_id")) in rejected for x in m.get("matched") or []):
                relabel[r.id] = REJECTED_OUTCOME
        kept = [r for r in everything if not outcome or relabel.get(r.id, (r.measures or {}).get("outcome")) == outcome]
        total, rows = len(kept), kept[offset:offset + lim]
    else:
        relabel = {}
        if outcome:
            where += " AND r.measures ->> 'outcome' = :o"
            params["o"] = outcome
        total = int(conn.execute(text("SELECT count(*) FROM phone_analysis_results r WHERE %s" % where),
                                 params).scalar())
        rows = conn.execute(text(
            "SELECT r.id, r.measures, r.strength FROM phone_analysis_results r WHERE %s ORDER BY r.period_start NULLS "
            "LAST, r.id OFFSET :off LIMIT :lim" % where), {**params, "off": offset, "lim": lim}).fetchall()
    links = {}
    if rows:
        for x in conn.execute(text(
                "SELECT x.result_id, x.record_uid, x.role, t.ref_id, t.id AS tid FROM phone_analysis_result_records x "
                "LEFT JOIN financial_transactions t ON t.id = x.ledger_transaction_id AND t.case_id = :c WHERE "
                "x.result_id = ANY(:ids)"), {"c": str(case_id), "ids": [r.id for r in rows]}):
            links.setdefault(x.result_id, []).append(x)
    items = []
    for r in rows:
        m = r.measures or {}
        xs = links.get(r.id, [])
        items.append({
            "result_id": str(r.id), "rec": next((_rec(x.record_uid) for x in xs if x.record_uid), None),
            "phone": m.get("phone_label"), "source": m.get("source"), "instant": m.get("event_instant"),
            "amount_minor": m.get("amount_minor"), "currency": m.get("currency"), "amount_text": m.get("amount_text"),
            "direction": m.get("direction"), "institution": (m.get("institution") or {}).get("name"),
            "account": m.get("account_ref"), "outcome": relabel.get(r.id, m.get("outcome")), "reason": m.get("reason"),
            "strength": r.strength, "proof_class": "p4",
            "ledger_rows": [{"payment": str(x.tid), "ref": x.ref_id,
                             "role": "ledger_match_rejected_by_person" if (m.get("record_uid"), str(x.tid)) in rejected
                             else x.role} for x in xs if x.tid]})
    nxt = offset + len(items) if offset + len(items) < total else None
    return _base("money_readings", case_id, run_id=str(run.id), total_matching=total, returned=len(items),
                 has_more=nxt is not None, next_offset=nxt, items=items,
                 coverage="Read %d of %d money readings from the last run of Money on the phones." % (len(items),
                                                                                                         total),
                 limitation=("Only %d of %d are in this result; read on with offset %d." % (len(items), total, nxt))
                 if nxt is not None else None,
                 note="A money reading is what a phone shows, not a bank statement; a ledger row it matches only "
                      "gains a link.")


def colocation_results(conn, case_id, *, offset=0, limit=DEFAULT_LIMIT) -> dict:
    """Together and apart runs already made in this case (the pattern-of-life pair rule), newest first."""
    total = int(conn.execute(text("SELECT count(*) FROM pol_colocation_run WHERE case_id = :c"),
                             {"c": str(case_id)}).scalar())
    offset, lim = max(0, int(offset or 0)), _limit(limit)
    items = []
    for r in conn.execute(text(
            "SELECT r.id, r.subjects, r.window_start, r.window_end, r.status, (SELECT count(*) FROM "
            "pol_colocation_item i WHERE i.run_id = r.id) AS items FROM pol_colocation_run r WHERE r.case_id = :c "
            "ORDER BY r.started_at DESC NULLS FIRST, r.id OFFSET :o LIMIT :l"),
            {"c": str(case_id), "o": offset, "l": lim}):
        items.append({"run_id": str(r.id), "subjects": [s.get("label") or s.get("name") or s.get("key")
                                                        for s in (r.subjects or [])],
                      "window_start": r.window_start.isoformat() if r.window_start else None,
                      "window_end": r.window_end.isoformat() if r.window_end else None,
                      "status": r.status, "pairs": int(r.items)})
    nxt = offset + len(items) if offset + len(items) < total else None
    return _base("colocation_results", case_id, total_matching=total, returned=len(items), has_more=nxt is not None,
                 next_offset=nxt, items=items,
                 coverage="Every together-and-apart run made in this case (%d)." % total,
                 limitation=None if total else "No together-and-apart run has been made in this case.")


def record(conn, case_id, record_uid) -> dict:
    """One phone record in full, as the record panel shows it (sensitive values masked)."""
    from services.phone import records
    try:
        uid = str(uuid.UUID(str(record_uid).replace("rec://", "")))
    except ValueError:
        return _not_in_case("record", case_id, "That is not a record id.")
    try:
        d = records.record_detail(conn, case_id, uid)
    except records.NotFound:
        return _not_in_case("record", case_id, "No such phone record.")
    return _base("record", case_id, total_matching=1, returned=1, has_more=False, next_offset=None,
                 items=[{"rec": _rec(uid), "phone": d["extraction"]["label"], "model_type": d["model_type"],
                         "text": records.record_text(d), "parents": d.get("parents") or [],
                         "files": [f.get("path") or f.get("reference") for f in d["files"]],
                         "corrections": d["corrections"]}],
                 coverage="The whole record, every field.", limitation=None)
