"""One person across every phone (phones redesign screen 3).

A person is the identity keys the scope names (the keys Conversations takes), widened to every key linked to the same
reviewed person. Their messages and calls are read through Conversations' own filter (``streams._query``, Involving any
of the keys, copies on one phone counted once), so the per-phone counts equal the counts Conversations shows.

The same message held by two phones is found by Compare phones' rule (``compare.match``: app family, folded text,
times within 120 seconds, calls within 2 seconds), applied to every pair of phones in scope; copies paired across
pairs join into one contact. A contact is *expected* on a phone when that phone's owner is one of its parties; a
contact expected on a phone that does not hold it is *missing* there. A missing contact is *explained by the phone
not recording* when its hour is an hour the Timeline marks "No data" for that phone (``timeline_lens._no_data_hours``)
or it lies outside the first and last message or call that phone holds.

What differs between the phones (each a lead, never a finding), all computed by these rules, never by a model:
- ``missing``: contacts missing from a phone, with how many are explained by the phone not recording;
- ``deleted``: contacts deleted (Deleted or Trash) on one phone and intact on another;
- ``names``: the person saved under different names on different phones;
- ``clocks``: contacts whose copies on two phones are more than ``CLOCK_SECONDS`` apart.

Decisions (reverse by editing the named constant): ``CLOCK_SECONDS`` = 1 (the design's "times match to the second");
``PAGE_MAX`` = 500 records per page, the total is always stated and the next page is asked for by ``offset``.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta
from itertools import combinations
from types import SimpleNamespace

from sqlalchemy import text

from services.phone import compare as C
from services.phone import crossings, streams
from services.phone import labels as L
from services.phone import time_display as T
from services.phone.filters import StreamFilter

CLOCK_SECONDS = 1.0
PAGE_MAX = 500
DELETED = ("Deleted", "Trash")
KINDS = ("message", "call")


ONLY = {
    "missing": lambda it: bool(it["missing"]),
    "missing_unexplained": lambda it: any(not m["not_recording"] for m in it["missing"]),
    "missing_not_recording": lambda it: any(m["not_recording"] for m in it["missing"]),
    "deleted": lambda it: bool(it["deleted_on"]) and len(it["deleted_on"]) < len(it["on"]),
    "clocks": lambda it: it["spread_s"] > CLOCK_SECONDS,
}


class NotInCase(LookupError):
    pass


def _iso(v):
    return v.isoformat() if v is not None else None


def active_phones(conn, case_id, phones=None) -> list[str]:
    """The case's active phones in capture order, or the named ones (each must be an active phone of the case)."""
    rows = [str(r[0]) for r in conn.execute(text(
        "SELECT id FROM phone_extractions WHERE case_id = :c AND standing = 'active' ORDER BY created_at, id"),
        {"c": str(case_id)})]
    if not phones:
        return rows
    want = [str(p) for p in phones]
    missing = [p for p in want if p not in rows]
    if missing:
        raise NotInCase("A phone named is not an active phone of this case.")
    return [p for p in rows if p in want]


def person_keys(conn, case_id, keys) -> list[str]:
    """``keys`` and every identity key linked to the same reviewed person."""
    exp = streams._person_keys(conn, str(case_id), list(keys))
    return sorted({k for ks in exp.values() for k in ks})


def _events(conn, case_id, keys, phones):
    f = StreamFilter.model_validate(dict(crossings.conversations_scope(case_id, keys, phones=phones)[0],
                                         kinds=list(KINDS)))
    q, ctx = streams._query(conn, f)
    rows = conn.execute(text("WITH m AS (%s) SELECT * FROM m WHERE %s ORDER BY sort_instant NULLS LAST, event_uid"
                             % (q.matched_sql(), streams._shown(f))), q.params).fetchall()
    return rows, ctx, f


def _parties(conn, event_uids) -> dict:
    out = defaultdict(set)
    if not event_uids:
        return out
    for r in conn.execute(text("SELECT event_uid, identity_key FROM pv_comm_party WHERE event_uid = ANY(CAST(:u AS "
                               "uuid[])) AND identity_key IS NOT NULL"), {"u": [str(u) for u in event_uids]}):
        out[str(r.event_uid)].add(r.identity_key)
    return out


def contacts(rows, phones) -> list[list[int]]:
    """Indexes of ``rows`` grouped into contacts: one group per message or call, its copies on every phone in scope
    (Compare phones' pairing rule, every pair of phones). Undated rows are never paired."""
    parent = list(range(len(rows)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    by_phone = defaultdict(list)
    for i, r in enumerate(rows):
        if r.sort_instant is not None:
            by_phone[str(r.extraction_id)].append(i)
    for a, b in combinations(sorted(by_phone), 2):
        idx = by_phone[a] + by_phone[b]
        evs = [SimpleNamespace(extraction_id=str(rows[i].extraction_id), kind=rows[i].kind, app=rows[i].app,
                               at=rows[i].sort_instant, body=rows[i].body, d=rows[i].call_duration_s,
                               direction=rows[i].direction) for i in idx]
        for x, y in C.match_pairs(evs, a, b):
            ra, rb = find(idx[x]), find(idx[y])
            if ra != rb:
                parent[rb] = ra
    groups = defaultdict(list)
    for i in range(len(rows)):
        groups[find(i)].append(i)
    return sorted(groups.values(), key=lambda g: (min((rows[i].sort_instant for i in g if rows[i].sort_instant),
                                                      default=None) is None,
                                                  min((rows[i].sort_instant for i in g if rows[i].sort_instant),
                                                      default=rows[g[0]].sort_instant) or 0, str(rows[g[0]].event_uid)))


def _no_data(conn, ext, times) -> set:
    """Hours (UTC, truncated) among ``times`` that the Timeline marks "No data" for phone ``ext``."""
    from services.phone import timeline_lens
    if not times:
        return set()
    lo = min(times).replace(minute=0, second=0, microsecond=0)
    hi = max(times).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return timeline_lens._no_data_hours(conn, ext, lo, hi)


def _spans(conn, case_id, phones) -> dict:
    """``{ext: (first, last)}``: each phone's first and last dated message or call, whoever it is with."""
    return {str(r.e): (r.f, r.l) for r in conn.execute(text(
        "SELECT extraction_id AS e, min(sort_instant) AS f, max(sort_instant) AS l FROM pv_comm_event WHERE case_id = "
        ":c AND extraction_id = ANY(CAST(:p AS uuid[])) AND kind IN ('message', 'call') GROUP BY 1"),
        {"c": str(case_id), "p": phones})}


def _names(conn, case_id, keys) -> dict:
    """``{ext: [names that phone saved the person under]}``, most used first."""
    out = defaultdict(list)
    for r in conn.execute(text(
            "SELECT extraction_id::text AS e, name FROM pv_identity_name WHERE case_id = :c AND identity_key = ANY(:k) "
            "AND is_phone_name ORDER BY occurrences DESC, name"), {"c": str(case_id), "k": list(keys)}):
        if r.name not in out[r.e]:
            out[r.e].append(r.name)
    return out


def _person_label(conn, case_id, keys, names) -> dict:
    ids = conn.execute(text("SELECT i.identity_key, i.value_display, p.display_name FROM pv_identity i LEFT JOIN "
                            "case_profiles p ON p.id = i.person_id WHERE i.case_id = :c AND i.identity_key = ANY(:k) "
                            "ORDER BY i.identity_key"), {"c": str(case_id), "k": list(keys)}).fetchall()
    person = next((r.display_name for r in ids if r.display_name), None)
    counted = Counter(n for ns in names.values() for n in ns)
    name = person or (counted.most_common(1)[0][0] if counted else None)
    values = [r.value_display for r in ids if r.value_display]
    return {"name": name or (values[0] if values else "This person"), "identifiers": values,
            "name_basis": "case_person" if person else ("contact_on_a_phone" if counted else "identifier")}


def _bucket(at, monthly):
    return at.strftime("%Y-%m") if monthly else (at - timedelta(days=at.weekday())).strftime("%Y-%m-%d")


def person_across(conn, case_id, keys, phones=None, with_keys=None, offset=0, limit=200, only=None) -> dict:
    """Screen 3's data for the person ``keys`` across ``phones`` (default: every active phone of the case); with
    ``with_keys``, only contacts that also involve that other person."""
    case_id = str(case_id)
    if not keys:
        raise ValueError("Name a person.")
    scope = active_phones(conn, case_id, phones)
    keys = person_keys(conn, case_id, keys)
    others = person_keys(conn, case_id, with_keys) if with_keys else []
    rows, ctx, f = _events(conn, case_id, keys, scope)
    parties = _parties(conn, [r.event_uid for r in rows])
    if others:
        keep = set(others)
        rows = [r for r in rows if parties.get(str(r.event_uid), set()) & keep]
    owner_keys = {e: set(ctx.owner_keys(e)) for e in scope}
    own = [e for e in scope if owner_keys[e] & set(keys)]
    names = _names(conn, case_id, keys)
    person = _person_label(conn, case_id, keys, names)
    spans = _spans(conn, case_id, scope)
    groups = contacts(rows, scope)

    items = []
    for g in groups:
        on = sorted({str(rows[i].extraction_id) for i in g}, key=scope.index)
        ps = set().union(*(parties.get(str(rows[i].event_uid), set()) for i in g))
        expected = [e for e in scope if owner_keys[e] & ps]
        times = [rows[i].sort_instant for i in g if rows[i].sort_instant is not None]
        deleted = sorted({str(rows[i].extraction_id) for i in g if rows[i].deleted_state in DELETED}, key=scope.index)
        items.append({"idx": g, "on": on, "expected": expected, "missing": [e for e in expected if e not in on],
                      "deleted_on": deleted, "at": min(times) if times else None,
                      "spread_s": (max(times) - min(times)).total_seconds() if len(times) > 1 else 0.0,
                      "kind": rows[g[0]].kind})

    # not recording: per phone, the hours of the contacts missing there
    miss_times = defaultdict(list)
    for it in items:
        for e in it["missing"]:
            if it["at"] is not None:
                miss_times[e].append(it["at"])
    gaps = {e: _no_data(conn, e, ts) for e, ts in miss_times.items()}

    def explained(e, at):
        if at is None:
            return False
        first, last = spans.get(e, (None, None))
        if first is None or at < first or at > last:
            return True
        return at.replace(minute=0, second=0, microsecond=0) in gaps.get(e, set())
    for it in items:
        it["missing"] = [{"extraction_id": e, "not_recording": explained(e, it["at"])} for e in it["missing"]]

    labels = ctx.phone_labels
    lab = (lambda e: labels.get(e, "A phone"))
    # per-phone cards
    per = {e: {"messages": 0, "calls": 0, "first": None, "last": None} for e in scope}
    for r in rows:
        e = str(r.extraction_id)
        per[e]["messages" if r.kind == "message" else "calls"] += 1
        if r.sort_instant is not None:
            per[e]["first"] = min(x for x in (per[e]["first"], r.sort_instant) if x)
            per[e]["last"] = max(x for x in (per[e]["last"], r.sort_instant) if x)
    zone = streams.case_zone(conn, case_id)["name"]
    cards = []
    for e in scope:
        p = per[e]
        cards.append({"extraction_id": e, "label": lab(e), "owner": _owner_name(ctx, e), "is_own": e in own,
                      "saved_as": names.get(e, []), "messages": p["messages"], "calls": p["calls"],
                      "first": _iso(p["first"]), "last": _iso(p["last"]),
                      "conversations_href": crossings.conversations_scope(case_id, keys, zone=zone, phones=[e])[1]})

    # compare: how many contacts each set of phones holds
    held = Counter((tuple(it["on"]), it["kind"]) for it in items)
    sets = defaultdict(lambda: {"messages": 0, "calls": 0})
    for (on, kind), n in held.items():
        sets[on]["messages" if kind == "message" else "calls"] += n
    compare = [{"on": list(on), **v} for on, v in sorted(sets.items(), key=lambda kv: (-len(kv[0]), kv[0]))]

    # volume: per month (per week when the span is under 92 days), per phone, one count per copy as on the cards
    dated = [r.sort_instant for r in rows if r.sort_instant is not None]
    monthly = not dated or (max(dated) - min(dated)).days >= 92
    vol = defaultdict(Counter)
    for r in rows:
        if r.sort_instant is not None:
            vol[_bucket(r.sort_instant, monthly)][str(r.extraction_id)] += 1
    volume = {"bucket": "month" if monthly else "week",
              "rows": [{"start": b, "by_phone": {e: vol[b].get(e, 0) for e in scope}} for b in sorted(vol)]}

    differs = _differs(items, rows, scope, lab, names, person)
    apps = sorted({(r.app or ("Phone" if r.kind == "call" else "SMS")) for r in rows})
    total_m = sum(1 for it in items if it["kind"] == "message")
    total_c = len(items) - total_m
    no_time = sum(1 for it in items if it["at"] is None)
    limit = max(1, min(int(limit), PAGE_MAX))
    offset = max(0, int(offset))
    if only and only not in ONLY:
        raise ValueError("Unknown list: choose one of %s." % ", ".join(ONLY))
    listed = [it for it in items if ONLY[only](it)] if only else items
    page = listed[offset:offset + limit]
    built = streams.build_rows(conn, ctx, [rows[it["idx"][0]] for it in page], zone, f) if page else []
    records = []
    for it, row in zip(page, built):
        copies = [{"extraction_id": str(rows[i].extraction_id), "record_uid": str(rows[i].record_uid),
                   "event_uid": str(rows[i].event_uid), "at": _iso(rows[i].sort_instant),
                   "deleted": rows[i].deleted_state in DELETED} for i in it["idx"]]
        records.append({"row": row, "on": it["on"], "missing": it["missing"], "deleted_on": it["deleted_on"],
                        "copies": copies, "spread_s": it["spread_s"], "diff": _diff_codes(it)})
    out = {"case_id": case_id, "person": dict(person, keys=keys, own_phones=own),
           "with": ({"keys": others, **_person_label(conn, case_id, others, _names(conn, case_id, others))}
                    if others else None),
           "phones": cards, "zone": zone,
           "summary": {"messages": total_m, "calls": total_c, "apps": apps,
                       "phones_holding": len({e for it in items for e in it["on"]}), "phones_in_scope": len(scope),
                       "first": _iso(min(dated)) if dated else None, "last": _iso(max(dated)) if dated else None,
                       "no_time": no_time, "copies": len(rows)},
           "records": records, "records_total": len(listed), "contacts_total": len(items), "only": only,
           "offset": offset, "limit": limit,
           "compare": compare, "volume": volume, "differs": differs,
           "places": places(conn, case_id, own),
           "rule_words": ("Messages that appear on more than one phone are shown once, marked with each phone that "
                          "holds them. " + C.KEY_WORDS)}
    out["next_steps"] = next_steps(out, lab)
    return out


def _owner_name(ctx, e):
    o = ctx.owners.get(e, {})
    if o.get("keys"):
        lb = ctx.label(e, identity_key=o["keys"][0], is_phone_owner=True)
        return lb.get("name") or L.identifier_text(lb.get("identifier"))
    return None


def _diff_codes(it) -> list[str]:
    out = []
    if it["missing"]:
        out.append("missing")
    if it["deleted_on"] and len(it["deleted_on"]) < len(it["on"]):
        out.append("deleted")
    if it["spread_s"] > CLOCK_SECONDS:
        out.append("clocks")
    return out


def _differs(items, rows, scope, lab, names, person) -> list[dict]:
    miss = [it for it in items if it["missing"]]
    by_phone = Counter(m["extraction_id"] for it in miss for m in it["missing"])
    rec = sum(1 for it in miss for m in it["missing"] if m["not_recording"])
    total = sum(by_phone.values())
    if total:
        where = ", ".join("%d from %s" % (n, lab(e)) for e, n in sorted(by_phone.items(), key=lambda x: scope.index(x[0])))
        body = ("Contacts the other side's phone holds and this phone does not (%s). %d of them fall where that phone "
                "was not recording." % (where, rec))
    else:
        body = "Every contact expected on a phone in scope is on it."
    out = [{"code": "missing", "title": "On one phone, missing from another", "n": total, "explained": rec,
            "by_phone": dict(by_phone), "body": body}]
    dele = [it for it in items if "deleted" in _diff_codes(it)]
    pairs = Counter((tuple(it["deleted_on"]), tuple(e for e in it["on"] if e not in it["deleted_on"])) for it in dele)
    out.append({"code": "deleted", "title": "Deleted on one phone, kept on another", "n": len(dele),
                "body": ("; ".join("%d deleted on %s and still on %s" % (n, " and ".join(map(lab, d)),
                                                                          " and ".join(map(lab, k)))
                                   for (d, k), n in pairs.most_common()) + ".") if dele else
                "No contact is deleted on one phone and kept on another."})
    saved = {e: ns for e, ns in names.items() if e in scope and ns}
    distinct = sorted({n for ns in saved.values() for n in ns})
    out.append({"code": "names", "title": "Saved under different names", "n": len(distinct) if len(distinct) > 1 else 0,
                "names": [{"extraction_id": e, "names": ns} for e, ns in saved.items()],
                "body": (", ".join("%s on %s" % (" / ".join("“%s”" % n for n in ns), lab(e)) for e, ns in
                                   sorted(saved.items(), key=lambda x: scope.index(x[0]))) + ".") if len(distinct) > 1
                else ("Saved as “%s” on every phone that holds a contact card." % distinct[0] if distinct else
                      "No phone in scope holds a contact card for this person.")})
    clk = [it for it in items if it["spread_s"] > CLOCK_SECONDS]
    both = [it for it in items if len(it["on"]) > 1]
    if clk:
        biggest = max(it["spread_s"] for it in clk)
        body = ("%d of %d contacts held by two phones differ by more than %d second; the largest gap is %s."
                % (len(clk), len(both), int(CLOCK_SECONDS), _dur(biggest)))
    elif both:
        body = "Where the same contact is on two phones, the times match to the second (%d contacts)." % len(both)
    else:
        body = "No contact is on two phones, so the clocks cannot be compared."
    out.append({"code": "clocks", "title": "Clocks disagree", "n": len(clk), "body": body})
    return out


def _dur(s):
    s = int(round(s))
    if s < 120:
        return "%d seconds" % s
    if s < 7200:
        return "%d minutes" % (s // 60)
    return "%.1f hours" % (s / 3600)


def places(conn, case_id, own) -> dict:
    """Where the person's own phones in scope were: located points grouped into squares of about 550 m (the Together
    rule's square), with counts and first and last time. Every square is returned."""
    from services.relations.together import SQUARE_DEG
    if not own:
        return {"own_phones": [], "squares": [], "observations": 0,
                "words": "This person has no phone in scope, so their phone's places are not known."}
    rows = conn.execute(text(
        "SELECT extraction_id::text AS e, floor(lat / :d) AS y, floor(lon / :d) AS x, count(*) AS n, avg(lat) AS lat, "
        "avg(lon) AS lon, min(start_utc) AS f, max(coalesce(end_utc, start_utc)) AS l FROM pol_place_observation WHERE "
        "case_id = :c AND extraction_id = ANY(CAST(:p AS uuid[])) AND lat IS NOT NULL AND lon IS NOT NULL GROUP BY 1, "
        "2, 3 ORDER BY count(*) DESC, 2, 3"), {"c": str(case_id), "p": own, "d": SQUARE_DEG}).fetchall()
    sq = [{"extraction_id": r.e, "lat": float(r.lat), "lon": float(r.lon), "observations": int(r.n),
           "first": _iso(r.f), "last": _iso(r.l)} for r in rows]
    n = sum(s["observations"] for s in sq)
    return {"own_phones": own, "squares": sq, "observations": n,
            "words": ("%d located points in %d places (squares of about 550 m)." % (n, len(sq))) if sq else
            "Their phone holds no located points."}


def next_steps(out, lab) -> list[dict]:
    """Ranked steps built from this result's own differences (COMMON rule 4). Each names its action and the scope it
    opens with; the screen turns ``action`` into a button."""
    steps = []
    d = {x["code"]: x for x in out["differs"]}
    m = d["missing"]
    unexplained = m["n"] - m["explained"]
    if unexplained:
        steps.append({"code": "open_unexplained", "title": "Look at the %d %s missing from a phone for no clear reason"
                      % (unexplained, "contact" if unexplained == 1 else "contacts"),
                      "why": "%d of the %d missing contacts fall where the phone was not recording. The other %d do "
                             "not, which can point to a deletion." % (m["explained"], m["n"], unexplained),
                      "action": "Open %s" % ("it" if unexplained == 1 else "them"), "filter": "missing_unexplained"})
    if d["deleted"]["n"]:
        n = d["deleted"]["n"]
        steps.append({"code": "open_deleted", "title": "Read the %d %s deleted on one phone that another kept"
                      % (n, "contact" if n == 1 else "contacts"),
                      "why": d["deleted"]["body"], "action": "Open the %d" % n, "filter": "deleted"})
    if m["n"] and m["explained"]:
        steps.append({"code": "open_not_recording", "title": "Find what the other sources hold for the %d contacts "
                      "missed while a phone was not recording" % m["explained"],
                      "why": "A gap in recording is no data, not no activity: the other phones and the rest of the "
                             "case may cover it.", "action": "Open them", "filter": "missing_not_recording"})
    if d["clocks"]["n"]:
        steps.append({"code": "open_clocks", "title": "Check the clocks on the %d contacts whose times disagree"
                      % d["clocks"]["n"], "why": d["clocks"]["body"], "action": "Open them", "filter": "clocks"})
    holding = [p for p in out["phones"] if p["messages"] + p["calls"]]
    own = set(out["person"]["own_phones"])
    partner = max((p for p in holding if p["extraction_id"] not in own), key=lambda p: p["messages"] + p["calls"],
                  default=None)
    if own and partner:
        o = next(iter(sorted(own)))
        steps.append({"code": "compare", "title": "Compare their phone with %s side by side"
                      % (partner["owner"] and "%s’s" % partner["owner"] or lab(partner["extraction_id"])),
                      "why": "%s holds %d of their messages and calls, the most of any other phone."
                      % (lab(partner["extraction_id"]), partner["messages"] + partner["calls"]),
                      "action": "Compare %s and %s" % (lab(o), lab(partner["extraction_id"])),
                      "phones": [o, partner["extraction_id"]]})
    if d["names"]["n"]:
        steps.append({"code": "names", "title": "Confirm the names each phone saved are one person",
                      "why": d["names"]["body"], "action": "Review the names", "href": "phone-review"})
    if out["records_total"]:
        s = out["summary"]
        steps.append({"code": "export", "title": "Export their contact as a PDF",
                      "why": "%d messages and %d calls on %d %s, in time order, with the source of each line."
                      % (s["messages"], s["calls"], s["phones_holding"], "phone" if s["phones_holding"] == 1 else "phones"),
                      "action": "Export as PDF"})
    for i, s in enumerate(steps):
        s["rank"] = i + 1
    return steps
