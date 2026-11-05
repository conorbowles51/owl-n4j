"""Approach 11: relationships over time (docs/cellebrite/05 section 14; unit 05-S9).

For each person (02 identity, or the person a reviewed merge put it under) and each phone: when the phone saved the
contact and last changed it, what each phone calls them, the first and last call and message, monthly counts by
channel and direction, and the weeks where the volume of contact changed (PELT, Poisson cost, BIC penalty). Counts
open Conversations filtered to the person and phone; around a key date the screen opens the same list for the
window, so key dates never need a rerun (05 19.S6-e).

Decisions (05 section 19, 19.S9-a to 19.S9-d):

- 19.S9-a A relationship result rests on the phone's contact cards for the person and on its first and last
  communication, not on every message: storing every communication as a result record would write one row per
  message (186,787 on P08) for a pointer Conversations already gives by filter. Reverse if a result must be exported
  with every record behind it in one step.
- 19.S9-b Weekly counts start at the person's first communication on the phone and end at the phone's last
  communication of any kind, so contact that stops before the phone's data stops shows as weeks of zero; a
  changepoint needs at least 2 weeks either side. Reverse if a corpus run shows changepoints that only mark the
  phone's own data starting or stopping.
- 19.S9-c Penalty: BIC, 2 x ln(weeks) per changepoint (a location and a new rate).
- 19.S9-d "No contact after D" (14.3 step 2) is 04's statement check, which already gathers supporting and
  contradicting records and the data gaps; this approach does not duplicate it, and the screen links to it.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import text

from services.phone_analysis import fields as FV

CODE = "relationships"
VERSION = "11.2"
PARAMETERS = {
    "min_communications": {"default": 1, "min": 1, "max": 1000},
    "min_segment_weeks": {"default": 2, "min": 1, "max": 26},
}
KINDS = ("relationship", "volume_change")
SUPPORTS = ("contact_card", "communications", "named_on_phone", "rate_changed", "reviewed_merge")
UNDERCUTS = ("identity_unreviewed", "no_rename_history", "created_time_absent", "apps_not_extracted",
             "shared_number", "deleted_or_carved", "selective_extraction")
DIRECTION_CODES = SUPPORTS + UNDERCUTS
SIGNALS = [
    {"code": "contacts", "label": "Contacts"},
    {"code": "created", "label": "Contact saved times"},
    {"code": "comms", "label": "Calls and messages"},
]
_last = {"counts": {}}


def _d(code, detail, locators=()):
    return {"code": code, "detail": detail, "locators": [str(x) for x in locators]}


# ---- change detection --------------------------------------------------------------------------------------------

def _poisson_cost(s, n):
    """-2 x maximised Poisson log-likelihood of a segment with sum s over n weeks, without the log(x!) terms (equal
    for every segmentation)."""
    if s <= 0 or n <= 0:
        return 0.0
    return -2.0 * (s * math.log(s / n) - s)


def pelt(counts: list, min_size: int = 2, penalty: float | None = None) -> list:
    """Changepoints (indexes where a new segment starts) of a count series, PELT (Killick et al. 2012)."""
    n = len(counts)
    if n < 2 * min_size:
        return []
    beta = 2.0 * math.log(n) if penalty is None else penalty
    cum = [0]
    for x in counts:
        cum.append(cum[-1] + x)

    def cost(a, b):
        return _poisson_cost(cum[b] - cum[a], b - a)
    f = [-beta] + [math.inf] * n
    last = [0] * (n + 1)
    cands = [0]
    for t in range(min_size, n + 1):
        best, arg = math.inf, 0
        for s in cands:
            if t - s < min_size:
                continue
            v = f[s] + cost(s, t) + beta
            if v < best:
                best, arg = v, s
        f[t], last[t] = best, arg
        cands = [s for s in cands if t - s < min_size or f[s] + cost(s, t) <= f[t]] + [t - min_size + 1]
        cands = sorted(set(c for c in cands if c >= 0))
    out, t = [], n
    while t > 0:
        s = last[t]
        if s > 0:
            out.append(s)
        t = s
    return sorted(out)


# ---- reading -----------------------------------------------------------------------------------------------------

def coverage(conn, case_id) -> dict:
    phones = {}
    for ext, label in FV.active_phones(conn, case_id).items():
        contacts = int(conn.execute(text("SELECT count(*) FROM pv_record WHERE extraction_id = :e AND model_type = "
                                         "'Contact' AND is_top_level"), {"e": ext}).scalar() or 0)
        created = int(conn.execute(text(
            "SELECT count(DISTINCT t.record_uid) FROM pv_time t JOIN pv_record r ON r.record_uid = t.record_uid WHERE "
            "t.extraction_id = :e AND r.model_type = 'Contact' AND t.field_path = 'TimeCreated' AND t.instant IS NOT "
            "NULL"), {"e": ext}).scalar() or 0)
        comms = int(conn.execute(text("SELECT count(*) FROM pv_comm_event WHERE extraction_id = :e AND kind IN "
                                      "('message', 'call', 'email')"), {"e": ext}).scalar() or 0)
        phones[ext] = {"label": label, "signals": {
            "contacts": {"carries_signal": contacts > 0, "records": contacts},
            "created": {"carries_signal": created > 0, "records": created,
                        "reason_absent": None if created else ("field_absent" if contacts else "type_absent")},
            "comms": {"carries_signal": comms > 0, "records": comms}}}
    return {"phones": phones, "signals": SIGNALS}


def _people(conn, case_id) -> dict:
    """identity_key -> (group key, display, person_id): a reviewed person groups its identities."""
    out = {}
    for r in conn.execute(text("SELECT identity_key, value_display, person_id FROM pv_identity WHERE case_id = :c"),
                          {"c": str(case_id)}):
        g = ("person:%s" % r.person_id) if r.person_id else r.identity_key
        out[r.identity_key] = (g, r.value_display, str(r.person_id) if r.person_id else None)
    return out


def _week(dt):
    d = dt.date()
    return d - timedelta(days=d.weekday())


def analyse_phone(conn, case_id, ext, label, people, names_by_group, params, counts) -> list:
    comms = defaultdict(list)  # group -> [(instant, kind, direction, record_uid)]
    keys_of = defaultdict(set)
    phone_last = None
    for r in conn.execute(text(
            "SELECT e.record_uid::text AS uid, e.kind, e.direction, e.sort_instant, e.deleted_state, p.identity_key "
            "FROM pv_comm_event e JOIN pv_comm_party p ON p.event_uid = e.event_uid WHERE e.extraction_id = :e AND "
            "e.kind IN ('message', 'call', 'email') AND p.identity_key IS NOT NULL AND NOT coalesce(p.is_phone_owner, "
            "false) ORDER BY e.sort_instant NULLS LAST, e.record_uid"), {"e": ext}).mappings():
        g = people.get(r["identity_key"], (r["identity_key"], None, None))[0]
        comms[g].append((r["sort_instant"], r["kind"], r["direction"] or "unknown", r["uid"], r["deleted_state"]))
        keys_of[g].add(r["identity_key"])
        if r["sort_instant"] and (phone_last is None or r["sort_instant"] > phone_last):
            phone_last = r["sort_instant"]
    cards = defaultdict(set)
    for r in conn.execute(text(
            "SELECT DISTINCT identity_key, card_record_uid::text FROM pv_identity_sighting WHERE extraction_id = :e AND "
            "card_type = 'Contact' AND card_record_uid IS NOT NULL"), {"e": ext}):
        g = people.get(r[0], (r[0], None, None))[0]
        cards[g].add(r[1])
        keys_of[g].add(r[0])
    card_times = FV.times_for(conn, ext, sorted({c for cs in cards.values() for c in cs}), ("TimeCreated",
                                                                                          "TimeModified"))
    out = []
    for g in sorted(set(comms) | set(cards)):
        evs = comms.get(g, [])
        if len(evs) < params["min_communications"] and not cards.get(g):
            continue
        timed = [e for e in evs if e[0] is not None]
        by_month = defaultdict(lambda: defaultdict(int))
        for t, kind, direction, _, _ in timed:
            by_month[t.strftime("%Y-%m")]["%s_%s" % (kind, direction)] += 1
        first = {k: next((e for e in timed if e[1] == k), None) for k in ("message", "call", "email")}
        last = {k: next((e for e in reversed(timed) if e[1] == k), None) for k in ("message", "call", "email")}
        cs = sorted(cards.get(g, ()))
        created = sorted(card_times.get(c, {}).get("TimeCreated") for c in cs if card_times.get(c, {}).get(
            "TimeCreated"))
        modified = sorted(card_times.get(c, {}).get("TimeModified") for c in cs if card_times.get(c, {}).get(
            "TimeModified"))
        person = people.get(next(iter(sorted(keys_of[g]))), (g, None, None))
        names = names_by_group.get(g, {})
        here = sorted(names.get(ext, ()))
        elsewhere = {counts["labels"].get(x, x[:8]): sorted(v) for x, v in names.items() if x != ext and v}
        supports, undercuts = [], []
        if cs:
            supports.append(_d("contact_card", "Saved as a contact on %s." % label, cs[:1]))
        if evs:
            supports.append(_d("communications", "%d calls, messages or emails with this person on %s." %
                               (len(evs), label)))
        if here:
            supports.append(_d("named_on_phone", "Named on %s as shown." % label))
        if person[2]:
            supports.append(_d("reviewed_merge", "Several numbers or accounts are joined under one person by a "
                               "reviewed decision."))
        elif len(keys_of[g]) > 1:
            undercuts.append(_d("identity_unreviewed", "Joined only because the numbers or accounts are equal."))
        undercuts.append(_d("no_rename_history", "The phone keeps only the current name and the last change time."))
        if cs and not created:
            undercuts.append(_d("created_time_absent", "The phone recorded no saved time for this contact."))
        undercuts.append(_d("apps_not_extracted", "Contact through apps the extraction does not hold is not counted."))
        if any(e[4] in ("Deleted", "Trash") for e in evs):
            undercuts.append(_d("deleted_or_carved", "Some of these records are deleted ones the phone still held."))
        recs = [{"extraction_id": ext, "record_uid": c, "field_path": None, "role": "contact_card"} for c in cs]
        anchor_path = "identity:%s" % g
        for which, e in (("first", min(timed, key=lambda x: x[0]) if timed else None),
                         ("last", max(timed, key=lambda x: x[0]) if timed else None)):
            if e is not None:
                recs.append({"extraction_id": ext, "record_uid": e[3], "field_path": anchor_path,
                             "role": "%s_communication" % which})
        if not timed:
            # one card can list several identities (19.S9-f): the group's own locator keeps its key unique
            recs.append({"extraction_id": ext, "record_uid": cs[0] if cs else evs[0][3], "field_path": anchor_path,
                         "role": "person" if cs else "untimed_communication"})
        counts["relationships"] += 1
        period = (min(t for t, *_ in timed), max(t for t, *_ in timed)) if timed else (
            (created[0], created[0]) if created else (None, None))
        out.append({
            "kind": "relationship", "strength": "reviewed_person" if person[2] else "identity",
            "measures": {"phone_label": label, "extraction_id": ext, "group": g, "display": person[1], "person_id": person[2],
                         "identity_keys": sorted(keys_of[g]), "names_here": here, "names_elsewhere": elsewhere,
                         "saved": created[0] if created else None, "modified": modified[-1] if modified else None,
                         "contact_cards": len(cs), "communications": len(evs), "untimed": len(evs) - len(timed),
                         "first": {k: (v[0] if v else None) for k, v in first.items()},
                         "last": {k: (v[0] if v else None) for k, v in last.items()},
                         "monthly": {m: dict(v) for m, v in sorted(by_month.items())}},
            "directions": {"supports": supports, "undercuts": undercuts},
            "period_start": period[0], "period_end": period[1], "records": recs})
        # weekly volume and its changepoints (19.S9-b)
        if len(timed) >= 2 and phone_last is not None:
            w0, w1 = _week(timed[0][0]), _week(phone_last)
            weeks = (w1 - w0).days // 7 + 1
            series = [0] * weeks
            for t, *_ in timed:
                series[(_week(t) - w0).days // 7] += 1
            cps = pelt(series, params["min_segment_weeks"])
            bounds = [0] + cps + [weeks]
            for j, cp in enumerate(cps):
                seg_before, seg_after = series[bounds[j]:cp], series[cp:bounds[j + 2]]
                at = w0 + timedelta(weeks=cp)
                near = min(timed, key=lambda x: abs((x[0].date() - at).days))
                counts["volume_changes"] += 1
                rb, ra = sum(seg_before) / len(seg_before), sum(seg_after) / len(seg_after)
                out.append({
                    "kind": "volume_change", "strength": "rise" if ra > rb else "fall",
                    "measures": {"phone_label": label, "extraction_id": ext, "group": g, "display": person[1], "week_start": at.isoformat(),
                                 "rate_before": round(rb, 3), "rate_after": round(ra, 3),
                                 "weeks_before": len(seg_before), "weeks_after": len(seg_after),
                                 "series_weeks": weeks},
                    "directions": {"supports": [_d("rate_changed", "About %.1f a week for %d weeks, then about %.1f a "
                                                   "week for %d weeks." % (rb, len(seg_before), ra, len(seg_after)))],
                                   "undercuts": [_d("apps_not_extracted", "Contact through other apps or in person "
                                                    "is not counted.")]},
                    "period_start": at, "period_end": at,
                    "records": [{"extraction_id": ext, "record_uid": near[3], "field_path": "%s#week:%s" %
                                 (anchor_path, at.isoformat()), "role": "nearest_communication"}]})
    return out


def volume(conn, case_id, result_id) -> dict:
    """The weekly volume behind a relationship or volume-change result, for the chart of 05 14.4. The weeks are read
    from the phone's records with the rule of 19.S9-b, on request, because storing every week on every result would
    write about 500 numbers per person into each row of the results list; the changepoints are the run's own stored
    results. ``changed_words`` says so when the records no longer give the run's count."""
    r = conn.execute(text("SELECT run_id, kind, measures FROM phone_analysis_results WHERE id = CAST(:i AS uuid) AND "
                          "case_id = :c"), {"i": str(result_id), "c": str(case_id)}).first()
    if r is None or r.kind not in KINDS:
        raise LookupError("That result is not in this case.")
    group, ext = r.measures.get("group"), r.measures.get("extraction_id")
    rows = conn.execute(text(
        "SELECT id, kind, strength, measures FROM phone_analysis_results WHERE run_id = :r AND measures->>'group' = :g "
        "AND measures->>'extraction_id' = :e"), {"r": r.run_id, "g": group, "e": ext}).fetchall()
    rel = next((x for x in rows if x.kind == "relationship"), None)
    if rel is None:
        raise LookupError("That result is not in this case.")
    keys = rel.measures.get("identity_keys") or []
    timed = [x[0] for x in conn.execute(text(
        "SELECT e.sort_instant FROM pv_comm_event e JOIN pv_comm_party p ON p.event_uid = e.event_uid WHERE "
        "e.extraction_id = :e AND e.kind IN ('message', 'call', 'email') AND p.identity_key = ANY(:k) AND NOT "
        "coalesce(p.is_phone_owner, false) AND e.sort_instant IS NOT NULL ORDER BY e.sort_instant"),
        {"e": ext, "k": keys})]
    phone_last = conn.execute(text(
        "SELECT max(e.sort_instant) FROM pv_comm_event e JOIN pv_comm_party p ON p.event_uid = e.event_uid WHERE "
        "e.extraction_id = :e AND e.kind IN ('message', 'call', 'email') AND p.identity_key IS NOT NULL AND NOT "
        "coalesce(p.is_phone_owner, false)"), {"e": ext}).scalar()
    weeks = []
    if timed:
        w0, w1 = _week(timed[0]), _week(phone_last)
        series = [0] * ((w1 - w0).days // 7 + 1)
        for t in timed:
            series[(_week(t) - w0).days // 7] += 1
        weeks = [{"week_start": (w0 + timedelta(weeks=i)).isoformat(), "count": n} for i, n in enumerate(series)]
    stored = int(rel.measures.get("communications") or 0) - int(rel.measures.get("untimed") or 0)
    changes = sorted(({"result_id": str(x.id), "week_start": x.measures.get("week_start"), "direction": x.strength,
                       "rate_before": x.measures.get("rate_before"), "rate_after": x.measures.get("rate_after"),
                       "weeks_before": x.measures.get("weeks_before"), "weeks_after": x.measures.get("weeks_after")}
                      for x in rows if x.kind == "volume_change"), key=lambda c: c["week_start"] or "")
    return {"result_id": str(rel.id), "phone_label": rel.measures.get("phone_label"), "extraction_id": ext,
            "identity_keys": keys, "weeks": weeks, "total": len(timed), "untimed": int(rel.measures.get("untimed") or 0),
            "changepoints": changes,
            "changed_words": None if stored == len(timed) else (
                "The phone's records now give %d with a time; this run counted %d. Run the analysis again to bring "
                "the changepoints up to date." % (len(timed), stored))}


def analyse(conn, case_id, params, ctx=None) -> tuple:
    counts = defaultdict(int)
    phones = FV.active_phones(conn, case_id)
    counts["labels"] = dict(phones)
    people = _people(conn, case_id)
    names_by_group = defaultdict(lambda: defaultdict(set))
    for r in conn.execute(text("SELECT extraction_id::text, identity_key, name FROM pv_identity_name WHERE case_id = :c "
                               "AND is_phone_name AND name IS NOT NULL"), {"c": str(case_id)}):
        g = people.get(r[1], (r[1], None, None))[0]
        names_by_group[g][r[0]].add(r[2])
    results = []
    for i, (ext, label) in enumerate(phones.items()):
        if ctx is not None:
            ctx.progress(i, len(phones), label)
            if ctx.cancelled():
                break
        results.extend(analyse_phone(conn, case_id, ext, label, people, names_by_group, params, counts))
    if ctx is not None:
        ctx.progress(len(phones), len(phones))
    # M-11c: groups named differently on two phones
    counts["named_differently"] = sum(1 for g, by in names_by_group.items() if len(by) > 1 and
                                      len({frozenset(v) for v in by.values()}) > 1)
    counts.pop("labels", None)
    return results, dict(counts)


def run(conn, case_id, params, ctx) -> list:
    results, counts = analyse(conn, case_id, params, ctx)
    _last["counts"] = counts
    return results


def last_counts() -> dict:
    return _last["counts"]
