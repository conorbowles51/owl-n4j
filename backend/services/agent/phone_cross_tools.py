"""The agent reads the phones the way the screens do, and joins them to money (agent-phones; report "Four connections
turn phone records into money evidence", tool table rows "Phones" and "Cross").

Every tool wraps the service its screen calls; none computes a second answer:

- ``search_case``: Loupe-wide Search (``services.search.search``), every group with its exact total;
- ``person_phones``: the dossier's phone identities, each phone's names for them and their counts (03 10.4);
- ``day_activity``: the Day view (``pattern_of_life.day.window`` with the money lane);
- ``together_apart``: 04's pair rule (``colocation.compute``, the code a Together run stores), nothing written;
- ``routine_deviations``: ``routine.compute`` and ``routine.deviations``;
- ``phone_map_summary``: the Map's totals line (``phone.map.summary``); places are investigative locations;
- ``contact_and_money_between``: the link-analysis edge (``link_edges.edges``): contact counts and the money between
  two people (p0-p2 summed per currency, p3 stated, p4 counted), the Graph's pair edge;
- ``money_signal_matches`` / ``money_signal_leads``: approach 1's last completed run (05 4.3.5, 4.3.7), with the
  ledger half of a lead (missing account or missing period) from the statement periods;
- ``statement_check``: 04 9's evaluation of a person-confirmed statement, computed and not stored;
- ``analysis_results``: approaches 2 to 13 (``phone_analysis.framework.results``) on their last completed run.

Connections 3 and 4 (``control_claim``, ``payment_conversation``) return proposals only, labelled "model drafted, not
confirmed": a control claim is never "P is the holder", and a purpose reading is the model's until a person confirms.

The ledger-tool contract: the case id is the run's, never the model's; every query names it; read only; pages state
``total_matching``, ``returned``, ``has_more`` and ``next_offset``; every item carries its citation (``rec://`` for a
phone record, ``txn://`` for a ledger row); "Not in this case." in the same words whether or not it exists elsewhere.
Phone text goes to the model in full (Neil 2026-11-03); sensitive values stay masked as on screen.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text

from services.agent.phone_tools import (DEFAULT_LIMIT, MAX_LIMIT, NOT_IN_CASE, _base, _instant, _limit,
                                        _not_in_case, _phone_ids, _rec)

PLACE_LABEL = "investigative location, not cell-site opinion"
MODEL_DRAFT = "model drafted, not confirmed"
CARD_NOT_PERSON = "A card payment places a card, not a person, at a terminal."
# pairs the agent computes in its own request (the Patterns screen runs larger ones in the background and keeps them)
AGENT_PAIRS = 200_000


def _txn(tid):
    return "txn://%s" % tid


def _page(items, offset, limit):
    offset, lim = max(0, int(offset or 0)), _limit(limit)
    page = items[offset:offset + lim]
    nxt = offset + len(page) if offset + len(page) < len(items) else None
    return page, offset, nxt


def _paged(tool, case_id, items, offset, limit, what, **kw):
    page, offset, nxt = _page(items, offset, limit)
    limitation = kw.pop("limitation", None)
    if nxt is not None:
        limitation = " ".join(x for x in ("Only %d of %d %s are in this result; read on with offset %d."
                                          % (len(page), len(items), what, nxt), limitation) if x)
    return _base(tool, case_id, total_matching=len(items), returned=len(page), has_more=nxt is not None,
                 next_offset=nxt, offset=offset, items=page, limitation=limitation, **kw)


def _iso(v):
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return v


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (datetime, date)):
        return _iso(o)
    if isinstance(o, uuid.UUID):
        return str(o)
    return o


# ---- subjects: a person (dossier) or a phone ------------------------------------------------------------------------

class _Missing(LookupError):
    pass


def _dossier(conn, case_id, person):
    """A dossier of this case by id or name (folded, exact first, then a unique part); ``_Missing`` otherwise."""
    s = str(person or "").strip()
    if not s:
        raise ValueError("Say which person (a dossier name or id).")
    rows = conn.execute(text("SELECT id::text AS id, display_name, canonical_entity_key FROM case_profiles WHERE "
                             "case_id = :c AND archived_at IS NULL"), {"c": str(case_id)}).fetchall()
    for r in rows:
        if r.id == s:
            return r
    from services.phone import fold as F
    f = F.fold(s)
    exact = [r for r in rows if F.fold(r.display_name or "") == f]
    if len(exact) == 1:
        return exact[0]
    part = [r for r in rows if f and f in F.fold(r.display_name or "")]
    if len(exact) > 1 or len(part) > 1:
        raise ValueError("%r fits %d people in this case (%s); say which one by id." % (
            s, len(exact or part), ", ".join("%s %s" % (r.display_name, r.id) for r in (exact or part)[:10])))
    if part:
        return part[0]
    raise _Missing("%s No person called %r." % (NOT_IN_CASE, s))


def _subject(conn, case_id, person=None, phone=None, role="subject"):
    """``subjects.resolve`` for a person or a phone, as the pattern screens take it."""
    from services.pattern_of_life import subjects
    if bool(person) == bool(phone):
        raise ValueError("Give the %s as a person or as a phone, one of the two." % role)
    if phone:
        ids, unknown = _phone_ids(conn, case_id, [phone])
        if unknown:
            raise _Missing("%s There is no phone %s." % (NOT_IN_CASE, phone))
        subj = {"kind": "extraction", "extraction_id": ids[0]}
    else:
        subj = {"kind": "dossier", "dossier_id": _dossier(conn, case_id, person).id}
    try:
        r = subjects.resolve(conn, str(case_id), subj)
    except subjects.SubjectError as exc:
        raise _Missing("%s %s" % (NOT_IN_CASE, exc)) from None
    if not r["extraction_ids"]:
        raise ValueError("No phone in this case is linked to %s yet: a phone's owner must be linked to the person "
                         "on People first." % (r.get("name") or "this person"))
    return r


def _labels(conn, case_id):
    from routers.pattern_of_life import _labels as labels
    return labels(conn, str(case_id))


def _zone(conn, case_id, extraction_ids, zone="device"):
    from fastapi import HTTPException

    from routers.pattern_of_life import _zone_for
    try:
        return _zone_for(conn, extraction_ids, zone, str(case_id))
    except HTTPException as exc:
        raise ValueError(str(exc.detail)) from None


def _guard(tool, case_id, fn):
    try:
        return fn()
    except _Missing as exc:
        return _not_in_case(tool, case_id, str(exc).replace(NOT_IN_CASE, "").strip())


# ---- search ---------------------------------------------------------------------------------------------------------

def search_case(conn, case_id, query, *, group=None, exact=False, phones=(), start=None, end=None, offset=0,
                limit=DEFAULT_LIMIT) -> dict:
    """Loupe-wide Search (``/api/search``): without ``group``, every group's exact total and first hits; with a
    group, a page of it (``/api/search/group``)."""
    from services.search import search as S
    tool = "search_case"
    ext_ids, unknown = _phone_ids(conn, case_id, phones)
    if unknown:
        return _not_in_case(tool, case_id, "There is no phone %s in this case." % ", ".join(unknown))
    a, b = _instant(start), _instant(end, end=True)
    a, b = (a.isoformat() if a else None), (b.isoformat() if b else None)
    try:
        if group:
            lim = _limit(limit)
            g = S.group_page(conn, case_id, query, group, cursor=str(max(0, int(offset or 0))), limit=lim, exact=exact,
                             phones=ext_ids or None, start=a, end=b)
            groups = [g]
            complete, limits = g.get("complete"), g.get("limits") or []
            not_searched = []
        else:
            res = S.search(conn, case_id, query, exact=exact, phones=ext_ids or None, start=a, end=b)
            groups, complete, limits = res["groups"], res["complete"], res["limits"]
            not_searched = res.get("not_searched") or []
    except S.SearchError as exc:
        raise ValueError(str(exc)) from None
    out_groups, items = [], []
    for g in groups:
        hits = []
        for it in g["items"]:
            uid = it.get("record_uid")
            hits.append(dict(_clean(it), rec=_rec(uid) if uid else None))
        nxt = g.get("next_cursor")
        out_groups.append({"group": g["group"], "total": g["total"], "returned": len(hits),
                           "next_offset": int(nxt) if nxt else None, "note": g.get("note")})
        items += [dict(h, group=g["group"]) for h in hits]
    total = sum(g["total"] for g in out_groups)
    more = [g for g in out_groups if g["next_offset"] is not None]
    lim_words = [x.get("message") or x.get("words") or str(x) for x in limits]
    return _base(tool, case_id, query=query, total_matching=total, returned=len(items), has_more=bool(more),
                 next_offset=more[0]["next_offset"] if len(more) == 1 else None, groups=out_groups, items=items,
                 coverage="Searched %s: %s." % ("the %s group" % group if group else "every group", ", ".join(
                     "%s %d" % (g["group"], g["total"]) for g in out_groups)),
                 limitation=" ".join(x for x in (
                     ("More hits than shown in %s; page a group with group=<name> and offset." % ", ".join(
                         g["group"] for g in more)) if more else None,
                     "Not complete: %s" % " ".join(lim_words) if not complete else None,
                     " ".join(n.get("reason", "") for n in not_searched) or None) if x) or None)


# ---- people and their phones ----------------------------------------------------------------------------------------

def person_phones(conn, case_id, person) -> dict:
    """The dossier panel (03 10.4): every phone identity linked to the person, each phone's names for it, its
    message and call count, and the phones whose owner it is."""
    from services.phone.readings import phone_labels
    tool = "person_phones"

    def run():
        d = _dossier(conn, case_id, person)
        labels = phone_labels(conn, case_id)
        rows = conn.execute(text(
            "SELECT i.identity_id, i.identity_key, i.kind, i.value_display, a.actor_name AS decided_by_name, "
            "a.created_at AS decided_at, a.actor_origin FROM pv_identity i LEFT JOIN phone_identity_links l ON "
            "l.identity_id = i.identity_id AND l.case_id = :c LEFT JOIN adjudications a ON a.id = l.decision_id AND "
            "a.case_id = :c WHERE i.case_id = :c AND i.person_id::text = :d ORDER BY i.identity_key"),
            {"c": str(case_id), "d": d.id}).fetchall()
        keys = [r.identity_key for r in rows]
        counts = {k: int(n) for k, n in conn.execute(text(
            "SELECT identity_key, count(DISTINCT event_uid) FROM pv_comm_party WHERE case_id = :c AND identity_key = "
            "ANY(CAST(:k AS text[])) GROUP BY identity_key"), {"c": str(case_id), "k": keys})} if keys else {}
        names = {}
        for n in conn.execute(text("SELECT identity_id, extraction_id, name, is_phone_name FROM pv_identity_name WHERE "
                                   "case_id = :c AND identity_id = ANY(:i) ORDER BY extraction_id, name"),
                              {"c": str(case_id), "i": [r.identity_id for r in rows]}) if rows else []:
            names.setdefault(n.identity_id, []).append({"phone": labels.get(str(n.extraction_id)), "name": n.name})
        from services.pattern_of_life import subjects
        owned = next((x["extraction_ids"] for x in subjects.dossiers(conn, str(case_id)) if x["dossier_id"] == d.id),
                     [])
        items = [{"identity_key": r.identity_key, "kind": r.kind, "value": r.value_display,
                  "names": names.get(r.identity_id, []), "messages_and_calls": counts.get(r.identity_key, 0),
                  "linked_by": r.decided_by_name, "linked_at": _iso(r.decided_at),
                  "link_origin": (r.actor_origin or {}).get("kind") if r.actor_origin else "person"} for r in rows]
        return _base(tool, case_id, person={"dossier_id": d.id, "name": d.display_name},
                     owner_of_phones=[labels.get(e) or e for e in owned], total_matching=len(items),
                     returned=len(items), has_more=False, next_offset=None, items=items,
                     coverage="Every phone identity linked to %s (%d), linked by a person on People." % (
                         d.display_name, len(items)),
                     limitation=None if items else "No phone identity is linked to %s yet." % d.display_name)
    return _guard(tool, case_id, run)


# ---- pattern of life ------------------------------------------------------------------------------------------------

DAY_LANES = ("communications", "interaction", "places", "money", "device_state", "others", "passive")


def day_activity(conn, case_id, day, *, person=None, phone=None, lanes=("communications", "interaction", "places",
                                                                         "money"), zone="device", offset=0,
                 limit=DEFAULT_LIMIT) -> dict:
    """The Day view for a person or phone on one local day: every lane's total, the hour-by-hour availability, and
    the items of the lanes asked for (oldest first, paged together)."""
    from sqlalchemy.orm import Session

    from services.pattern_of_life import day as day_view
    from services.pattern_of_life import money
    tool = "day_activity"

    def run():
        r = _subject(conn, case_id, person, phone)
        try:
            d = date.fromisoformat(str(day))
        except ValueError:
            raise ValueError("The day is a date, YYYY-MM-DD.") from None
        z, zname = _zone(conn, case_id, r["extraction_ids"], zone)
        a, b = day_view.day_bounds(d, z)
        with Session(bind=conn) as db:
            m = money.lane(db, case_id, start_date=d, end_date=d, zone=z, limit=5000)
        out = day_view.window(conn, r["extraction_ids"], _labels(conn, case_id), a, b, money_rows=m["items"])
        want = [x for x in (lanes or DAY_LANES) if x in DAY_LANES]
        items = []
        for lane in want:
            for it in out["lanes"].get(lane) or []:
                it = _clean(dict(it, lane=lane))
                if it.get("record_uid"):
                    it["rec"] = _rec(it["record_uid"])
                if lane == "money":
                    tid = it.get("transaction_id") or it.get("id")
                    it["txn"] = _txn(tid) if tid else None
                    it["note"] = "A ledger row has a day, never a time of day. " + CARD_NOT_PERSON
                if lane == "places":
                    it["label"] = PLACE_LABEL
                items.append(it)
        items.sort(key=lambda x: (str(x.get("at") or x.get("day") or ""), x["lane"]))
        totals = dict(out["totals"], money=m["total"])
        hours = {}
        for av in out["availability"]:
            for h in av["hours"]:
                hours.setdefault(av["phone"] or av["extraction_id"], {}).setdefault(h["words"], 0)
                hours[av["phone"] or av["extraction_id"]][h["words"]] += 1
        return _paged(tool, case_id, items, offset, limit, "items", subject=r["subject"], date=d.isoformat(),
                      zone=zname, totals=totals, hours_by_state=hours,
                      coverage="The Day view of %s in %s: %s." % (d.isoformat(), zname, ", ".join(
                          "%s %d" % (day_view.LANE_WORDS[k], totals.get(k, 0)) for k in DAY_LANES)),
                      limitation=out.get("limit_words"))
    return _guard(tool, case_id, run)


def together_apart(conn, case_id, start, end, *, person_a=None, phone_a=None, person_b=None, phone_b=None,
                   window_minutes=5, include_synced=False, offset=0, limit=DEFAULT_LIMIT) -> dict:
    """Together and apart for two subjects by 04's pair rule (the code a Together run stores), computed and not
    stored: the counts, the episodes (together, tight or broad, and apart) and the compared pairs."""
    from services.pattern_of_life import colocation
    tool = "together_apart"
    cap = AGENT_PAIRS

    def run():
        ra = _subject(conn, case_id, person_a, phone_a, "first person")
        rb = _subject(conn, case_id, person_b, phone_b, "second person")
        a, b = _instant(start), _instant(end, end=True)
        if not (a and b) or b <= a:
            raise ValueError("Give a start and an end, the end after the start.")
        if b - a > timedelta(days=3660):
            raise ValueError("The range is longer than ten years; choose a shorter one.")
        est = colocation.estimate_pairs(conn, ra["extraction_ids"], rb["extraction_ids"], a, b)
        if est > cap:
            return _base(tool, case_id, available=False, total_matching=0, returned=0, has_more=False,
                         next_offset=None, items=[], estimated_pairs=est,
                         reason="About %s pairs to compare (estimate from hourly counts): too many to compute here. "
                                "Narrow the window, or run Together on the Patterns screen, which runs it in the "
                                "background and keeps every pair." % format(est, ","))
        params = {"window_s": float(window_minutes) * 60, "include_synced": bool(include_synced)}
        pairs, counts, eps = colocation.compute(conn, str(case_id), ra["extraction_ids"], rb["extraction_ids"], a, b,
                                                params)
        items = []
        for it in pairs:
            items.append({"at": _iso(it["at_utc"]), "verdict": it["verdict"], "basis": it["basis"],
                          "distance_m": round(it["d"], 1) if it["d"] is not None else None,
                          "radii_sum_m": round(it["r"], 1) if it["r"] is not None else None,
                          "seconds_apart": round(it["dt"], 1), "tight": it["tight"], "assumed_radius": it["assumed"],
                          "flags": it["flags"], "a": it["ar"] or it["a"], "b": it["br"] or it["b"]})
        episodes = [{"kind": e["kind"], "start": _iso(e["start"]), "end": _iso(e["end"]), "pairs": e["items"],
                     "breadth": e["breadth"]} for e in eps]
        return _paged(tool, case_id, items, offset, limit, "compared pairs", subjects=[ra["subject"], rb["subject"]],
                      window={"start": a.isoformat(), "end": b.isoformat()}, counts=counts, episodes=episodes,
                      label=PLACE_LABEL,
                      coverage="Compared %d positions of the first with %d of the second: %d pairs (%s)." % (
                          counts["observations_a"], counts["observations_b"], counts["pairs"], ", ".join(
                              "%s %d" % (k, counts.get(k, 0)) for k in ("compatible", "separated", "undetermined"))),
                      note="Compatible means the positions could overlap; only a tight pair (radii within 150 m) "
                           "reads as together. Separated means they could not be in one place. Positions are where "
                           "the phones recorded themselves, not where the people were.")
    return _guard(tool, case_id, run)


def routine_deviations(conn, case_id, *, person=None, phone=None, start_date=None, end_date=None, zone="device",
                       offset=0, limit=DEFAULT_LIMIT) -> dict:
    """The routine places of a person or phone and the days whose places break the routine (04 8.3)."""
    from services.pattern_of_life import routine
    tool = "routine_deviations"

    def run():
        r = _subject(conn, case_id, person, phone)
        z, zname = _zone(conn, case_id, r["extraction_ids"], zone)
        a = date.fromisoformat(start_date) if start_date else None
        b = date.fromisoformat(end_date) if end_date else None
        res = routine.compute(conn, r["extraction_ids"], z)
        dev = routine.deviations(res, z, a, b)
        flagged = _clean(dev["flagged"])
        for f in flagged:
            for h in f.get("hours") or []:
                h["label"] = PLACE_LABEL
        return _paged(tool, case_id, flagged, offset, limit, "flagged days", subject=r["subject"], zone=zname,
                      routine_places=_clean(res.get("routine_places")), days_scored=dev["days_scored"],
                      threshold_bits=dev["threshold"], parameters=dev["parameters"], label=PLACE_LABEL,
                      coverage="Scored %d days with enough positions; %d flagged as breaking the routine." % (
                          dev["days_scored"], len(flagged)),
                      note="A flagged day is unusual for this phone's positions, not evidence of where the person "
                           "was or why.")
    return _guard(tool, case_id, run)


def phone_map_summary(conn, case_id, *, phones=(), start=None, end=None) -> dict:
    """The Map's phone layer totals: positioned records by source, what cannot be placed and why, and the area."""
    from services.phone import map as phone_map
    tool = "phone_map_summary"
    ext_ids, unknown = _phone_ids(conn, case_id, phones)
    if unknown:
        return _not_in_case(tool, case_id, "There is no phone %s in this case." % ", ".join(unknown))
    a, b = _instant(start), _instant(end, end=True)
    f = {"phones": ext_ids, "source_kinds": [], "affiliations": [], "from_instant": a.isoformat() if a else None,
         "to_instant": b.isoformat() if b else None, "include_no_time": a is None and b is None}
    s = phone_map.summary(conn, case_id, f)
    items = [dict(m, label="cannot be placed") for m in s["not_positionable"]]
    return _base(tool, case_id, total_matching=s["total"], returned=len(items), has_more=False, next_offset=None,
                 positioned=s["positioned"], by_source=s["by_source"], bbox=s["bbox"], items=items, label=PLACE_LABEL,
                 coverage="%s of %s location records are placed on the map (%s)." % (
                     format(s["positioned"], ","), format(s["total"], ","), ", ".join(
                         "%s %s" % (k, format(v, ",")) for k, v in s["by_source"].items()) or "none"),
                 limitation=("%s cannot be placed: %s." % (format(sum(m["count"] for m in items), ","), "; ".join(
                     "%s %s (%s)" % (format(m["count"], ","), m["model_type"], m["reason"]) for m in items)))
                 if items else None,
                 note="Places are investigative locations, not cell-site opinion. Read points with phone_places.")


# ---- the joins ------------------------------------------------------------------------------------------------------

def _edge_subject(conn, case_id, person=None, identity=None):
    if bool(person) == bool(identity):
        raise ValueError("Give each side as a person (dossier) or one phone identity_key, one of the two.")
    if identity:
        return {"identity_key": str(identity).strip()}
    return {"dossier_id": _dossier(conn, case_id, person).id}


def contact_and_money_between(conn, case_id, *, person_a=None, identity_a=None, person_b=None, identity_b=None,
                              start=None, end=None, offset=0, limit=DEFAULT_LIMIT) -> dict:
    """One edge between two people (02 11.2): messages, calls and emails between them on every phone, and the money
    between them from the ledger (verified p0-p2 summed per currency, p3 stated beside it, never summed across
    currencies), with the payments behind the money listed and cited."""
    from services.phone import link_edges
    tool = "contact_and_money_between"

    def run():
        sa = _edge_subject(conn, case_id, person_a, identity_a)
        sb = _edge_subject(conn, case_id, person_b, identity_b)
        a, b = _instant(start), _instant(end, end=True)
        try:
            out = link_edges.edges(conn, case_id, [sa, sb], from_instant=a, to_instant=b)
        except link_edges.NotInCase as exc:
            raise _Missing(str(exc)) from None
        edge = out["edges"][0]
        pays = link_edges.edge_records(conn, case_id, sa, sb, "payments", from_instant=a, to_instant=b, offset=0,
                                       limit=100000)
        rows = [dict(r, txn=_txn(r["id"]), amount=link_edges.format_minor(r["amount_minor"], r["currency"]),
                     summed=r["proof_class"] in link_edges.SUMMED) for r in pays["items"]]
        money = [dict(m, paid_ab=link_edges.format_minor(m["paid_ab_minor"], m["currency"]),
                      paid_ba=link_edges.format_minor(m["paid_ba_minor"], m["currency"])) for m in edge["money"]]
        c = edge["communication"]
        limits = [x["message"] for x in out["limits"]]
        return _paged(tool, case_id, rows, offset, limit, "payments", a=edge["a"], b=edge["b"], communication=c,
                      money=money, money_mentioned_on_phones=edge["money_mentioned_on_phones"],
                      money_readings_available=edge["money_readings_available"], label_line=edge["label"],
                      money_absent=out["money_absent"], zone=out["zone"],
                      coverage="%s and %s: %s. Money: %s." % (
                          edge["a"]["label"], edge["b"]["label"], edge["label"],
                          "; ".join("%s A to B %s (%d), B to A %s (%d), p3 stated apart" % (
                              m["currency"], m["paid_ab"], m["payments_ab"], m["paid_ba"], m["payments_ba"])
                              for m in money) or (out["money_absent"] or "no payment between them in the ledger")),
                      limitation=" ".join(limits) or None,
                      note="Totals are the ledger's verified rows (p0-p2) per currency; p3 rows are stated beside "
                           "them, never added. Money the phones mention is counted, never summed. Messages: read "
                           "them with phone_messages between the two.")
    return _guard(tool, case_id, run)


def _last_run(conn, case_id, code):
    return conn.execute(text(
        "SELECT id, finished_at, approach_version FROM phone_analysis_runs WHERE case_id = :c AND approach = :a AND "
        "status = 'completed' ORDER BY finished_at DESC NULLS LAST, id LIMIT 1"), {"c": str(case_id), "a": code}).first()


MATCHED = ("corroborated", "near_amount", "several_candidates")


def money_signal_matches(conn, case_id, *, outcome=None, offset=0, limit=DEFAULT_LIMIT) -> dict:
    """Approach 1's readings that answer a ledger row (corroborated, near amount, or several candidates), each with
    the row it links to (``txn://``) and the alert (``rec://``). Wraps ``phone_money_readings``; a reading stays p4,
    the row's class is unchanged."""
    from services.agent import phone_tools
    tool = "money_signal_matches"
    if outcome and outcome not in MATCHED:
        raise ValueError("outcome is one of %s; other readings are in phone_money_readings." % ", ".join(MATCHED))
    run = _last_run(conn, case_id, "money_signals")
    if run is None:
        return _base(tool, case_id, total_matching=0, returned=0, has_more=False, next_offset=None, items=[],
                     coverage="Money on the phones has not been run in this case.",
                     limitation="Run it from Money on the phones; until then there is nothing to read.")
    wanted = [outcome] if outcome else list(MATCHED)
    all_items = []
    for o in wanted:
        got = phone_tools.money_readings(conn, case_id, outcome=o, offset=0, limit=MAX_LIMIT)
        n, off = got["total_matching"], 0
        all_items += got["items"]
        while len([x for x in all_items if x["outcome"] == o]) < n and got["has_more"]:
            off = got["next_offset"]
            got = phone_tools.money_readings(conn, case_id, outcome=o, offset=off, limit=MAX_LIMIT)
            all_items += got["items"]
    all_items.sort(key=lambda x: (x.get("instant") or "", x["result_id"]))
    by = {}
    for it in all_items:
        by[it["outcome"]] = by.get(it["outcome"], 0) + 1
        for r in it["ledger_rows"]:
            r["txn"] = _txn(r["payment"])
    return _paged(tool, case_id, all_items, offset, limit, "matches", run_id=str(run.id), by_outcome=by,
                  coverage="Approach 1's last run: %d readings answer a ledger row (%s)." % (
                      len(all_items), ", ".join("%s %d" % kv for kv in sorted(by.items())) or "none"),
                  note="A reading is what a phone shows (p4), never summed; a matched row gains a link and keeps its "
                       "class. Several candidates means two or more rows fit, and none is linked.")


def _lead_alert_days(conn, case_id, run_id, record_uids):
    """The days (UTC) of the transactional alerts behind a lead, from the same run's money readings."""
    if not record_uids:
        return []
    return sorted({str(r[0])[:10] for r in conn.execute(text(
        "SELECT r.measures ->> 'event_instant' FROM phone_analysis_results r JOIN phone_analysis_result_records x ON "
        "x.result_id = r.id WHERE r.run_id = :run AND r.case_id = :c AND r.kind = 'money_reading' AND x.record_uid = "
        "ANY(CAST(:u AS uuid[])) AND r.measures ->> 'event_instant' IS NOT NULL"),
        {"run": run_id, "c": str(case_id), "u": list(record_uids)})})


def money_signal_leads(conn, case_id, *, offset=0, limit=DEFAULT_LIMIT) -> dict:
    """Approach 1's leads (05 4.3.7) with the ledger half: a lead whose ending is not among the case's accounts is a
    missing account; a held account whose alerts fall on days no admitted statement period covers is a missing
    period (the uncovered months are listed). Alerts are listed by day and never totalled (p4)."""
    from services.phone_analysis import framework as F
    tool = "money_signal_leads"
    run = _last_run(conn, case_id, "money_signals")
    if run is None:
        return _base(tool, case_id, total_matching=0, returned=0, has_more=False, next_offset=None, items=[],
                     coverage="Money on the phones has not been run in this case.",
                     limitation="Run it from Money on the phones; until then there are no leads.")
    res = F.results(conn, case_id, run.id, kind="account_lead", offset=0, limit=F.MAX_LIMIT)
    rows = list(res["items"])
    while len(rows) < res["total"]:
        res = F.results(conn, case_id, run.id, kind="account_lead", offset=len(rows), limit=F.MAX_LIMIT)
        if not res["items"]:
            break
        rows += res["items"]
    periods = {}
    for p in conn.execute(text(
            "SELECT p.account_id::text AS a, p.period_start, p.period_end FROM financial_statement_periods p JOIN "
            "financial_source_documents s ON s.id = p.source_document_id WHERE p.case_id = :c AND s.status = "
            "'admitted' AND p.period_start IS NOT NULL AND p.period_end IS NOT NULL"), {"c": str(case_id)}):
        periods.setdefault(p.a, []).append((p.period_start, p.period_end))
    items = []
    for r in rows:
        m = r["measures"] or {}
        recs = [x for x in conn.execute(text(
            "SELECT record_uid FROM phone_analysis_result_records WHERE result_id = CAST(:i AS uuid) AND record_uid IS "
            "NOT NULL ORDER BY record_uid"), {"i": r["id"]})]
        uids = [str(x.record_uid) for x in recs]
        days = _lead_alert_days(conn, case_id, run.id, uids) if (m.get("counts") or {}).get("transactional") else []
        accounts = m.get("accounts") or []
        if not accounts:
            ledger = "missing_account"
            ledger_words = "No account in this case's financial records matches; the account is missing."
            uncovered = []
        else:
            spans = [s for a in accounts for s in periods.get(a, [])]
            uncovered = sorted({d[:7] for d in days if not any(s <= date.fromisoformat(d) <= e for s, e in spans)})
            if not days:
                ledger, ledger_words = "account_held", "An account this evidence fits is in the records; the " \
                                                       "phone holds no alert with a day to check against its " \
                                                       "statements."
            elif not spans:
                ledger, ledger_words = "missing_period", "The account is named in the records but no statement " \
                                                         "period of it is held."
            elif uncovered:
                ledger, ledger_words = "missing_period", "Alerts fall in %s, which no statement held covers." % \
                    ", ".join(uncovered)
            else:
                ledger, ledger_words = "covered", "Every alert day falls inside a statement period held."
        items.append({"result_id": r["id"], "institution": (m.get("institution") or {}).get("name"),
                      "account": m.get("account_ref"), "status": m.get("status"), "sentence": m.get("sentence"),
                      "evidence_counts": m.get("counts"), "signals": m.get("signals"),
                      "first_seen": m.get("first_seen"), "last_seen": m.get("last_seen"),
                      "request_period": {"from": (m.get("first_seen") or "")[:10] or None,
                                         "to": (m.get("last_seen") or "")[:10] or None},
                      "alert_days": days, "ledger": ledger, "ledger_words": ledger_words,
                      "uncovered_months": uncovered, "matched_accounts": accounts, "strength": r["strength"],
                      "decision": r.get("decision"), "records": [_rec(u) for u in uids]})
    by = {}
    for it in items:
        by[it["ledger"]] = by.get(it["ledger"], 0) + 1
    return _paged(tool, case_id, items, offset, limit, "leads", run_id=str(run.id), by_ledger=by,
                  coverage="Approach 1's last run: %d leads (%s)." % (len(items), ", ".join(
                      "%s %d" % kv for kv in sorted(by.items())) or "none"),
                  note="A lead is evidence of an account or a period the case does not hold. Alerts are p4: listed, "
                       "never totalled. A lead card the agent writes is a draft a person edits.")


def statement_check(conn, case_id, claim_id) -> dict:
    """04 9's check of a statement a person confirmed, computed now and not stored (Check on the Patterns screen
    stores it). Outcomes: contradicted, contradicted_weakly, consistent, supported, mixed, insufficient_data, or
    no_record with its reason."""
    from services.pattern_of_life import claims, evaluation
    tool = "statement_check"
    try:
        cid = uuid.UUID(str(claim_id))
    except ValueError:
        return _not_in_case(tool, case_id, "That is not a statement id.")
    try:
        claim = claims.get(conn, str(case_id), cid, raw=True)
    except claims.ClaimError:
        return _not_in_case(tool, case_id, "No such statement.")
    if claim["status"] != "confirmed":
        return _base(tool, case_id, available=False, total_matching=0, returned=0, has_more=False, next_offset=None,
                     items=[], reason="Only a statement a person has confirmed is checked; this one is %s."
                     % claim["status"])
    try:
        res = evaluation.compute(conn, claim)
    except evaluation.EvaluationError as exc:
        raise ValueError(str(exc)) from None
    items = []
    for it in res["items"]:
        x = _clean({k: it[k] for k in ("role", "ref_kind", "ref_id", "strength", "reason_code", "explanation",
                                       "at_utc", "end_utc", "display")})
        if it.get("record_uid"):
            x["rec"] = _rec(it["record_uid"]) + ("#%s" % it["field_path"] if it.get("field_path") else "")
        if it["ref_kind"] == "transaction":
            x["txn"] = _txn(it["ref_id"])
        items.append(x)
    order = {"contradicting": 0, "supporting": 1, "gap": 2, "context": 3}
    items.sort(key=lambda x: order[x["role"]])
    return _base(tool, case_id, claim={"id": str(cid), "kind": claim["kind"], "window_start": _iso(claim["window_start"]),
                                       "window_end": _iso(claim["window_end"]), "text": claim.get("window_text")},
                 outcome=res["outcome"], outcome_basis=res["outcome_basis"], words=res["summary"]["words"],
                 no_record_reason=res["summary"].get("no_record_reason"), counts=res["counts"],
                 not_yet_checked=res["summary"]["not_yet_checked"], total_matching=len(items),
                 returned=min(len(items), MAX_LIMIT), has_more=len(items) > MAX_LIMIT,
                 next_offset=MAX_LIMIT if len(items) > MAX_LIMIT else None, items=items[:MAX_LIMIT],
                 coverage="Checked the statement now: %s (%s); %d items." % (res["outcome"], res["outcome_basis"],
                                                                           len(items)),
                 limitation=("Only the first %d of %d items are here (undercutting first); every item is on the "
                             "Patterns screen's check." % (MAX_LIMIT, len(items))) if len(items) > MAX_LIMIT else None,
                 note="Computed by the check's own rule; the outcome is never the model's. Not stored: Check on the "
                      "Patterns screen keeps it.")


ANALYSES = ("deletion_timeline", "relationships", "awareness", "device_users")


def analysis_results(conn, case_id, approach, *, kind=None, phone=None, start=None, end=None, offset=0,
                     limit=DEFAULT_LIMIT) -> dict:
    """The last completed run of a phone analysis (approaches 2 to 13 that are built), its results under a filter
    with the exact total, each with its records cited."""
    from services.phone_analysis import approaches, framework as F
    tool = "analysis_results"
    approaches.install()
    if approach == "money_signals":
        raise ValueError("Approach 1 is read with money_signal_matches, money_signal_leads or phone_money_readings.")
    try:
        module = F.approach(approach)
    except Exception:  # noqa: BLE001
        raise ValueError("No analysis called %r; built: %s." % (approach, ", ".join(
            c for c in approaches.BUILT if c != "money_signals"))) from None
    ext = None
    if phone:
        ids, unknown = _phone_ids(conn, case_id, [phone])
        if unknown:
            return _not_in_case(tool, case_id, "There is no phone %s." % phone)
        ext = ids[0]
    run = _last_run(conn, case_id, approach)
    if run is None:
        return _base(tool, case_id, approach=approach, total_matching=0, returned=0, has_more=False,
                     next_offset=None, items=[], coverage="%s has not been run in this case." % approach,
                     limitation="Run it from the phone analyses screen; until then there is nothing to read.")
    lim = _limit(limit)
    res = F.results(conn, case_id, run.id, kind=kind, start=_iso(_instant(start)), end=_iso(_instant(end, end=True)),
                    phone=ext, offset=max(0, int(offset or 0)), limit=lim)
    items = []
    for r in res["items"]:
        recs = [x for x in conn.execute(text(
            "SELECT record_uid, field_path, ledger_transaction_id, role FROM phone_analysis_result_records WHERE "
            "result_id = CAST(:i AS uuid) ORDER BY role, record_uid LIMIT 50"), {"i": r["id"]})]
        r = dict(r, records=[{"rec": _rec(x.record_uid) + ("#%s" % x.field_path if x.field_path else ""),
                              "role": x.role} if x.record_uid else {"txn": _txn(x.ledger_transaction_id),
                                                                     "role": x.role} for x in recs])
        items.append(r)
    nxt = res["offset"] + len(items) if res["offset"] + len(items) < res["total"] else None
    cov = F.coverage(conn, case_id, approach)
    return _base(tool, case_id, approach=approach, version=run.approach_version, run_id=str(run.id),
                 total_matching=res["total"], returned=len(items), has_more=nxt is not None, next_offset=nxt,
                 items=items, kinds=list(getattr(module, "KINDS", ())),
                 coverage="%s, last completed run: %d results%s. %s" % (approach, res["total"], (
                     " of kind %s" % kind) if kind else "", cov.get("sentence") or ""),
                 limitation=("Only %d of %d are in this result; read on with offset %d." % (len(items), res["total"], nxt))
                 if nxt is not None else None,
                 note="Each result is a lead for enquiry with what supports and what undercuts it; the analysis "
                      "reports numbers, never who did what.")


# ---- connection 3: who had the means to operate an account ----------------------------------------------------------

OTP_SQL = r"(one[- ]?time|passcode|pass code|verification code|security code|confirmation code|\motp\M|\mcode\M)"
OTP_DIGITS = __import__("re").compile(r"(?<!\d)\d{4,8}(?!\d)")
INTERACTION_LEAD = timedelta(minutes=5)


def _account(conn, case_id, account):
    """A financial account of this case by id or by its ending (four or more digits)."""
    import re
    s = str(account or "").strip()
    if not s:
        raise ValueError("Say which account (its id, or its ending).")
    rows = conn.execute(text("SELECT id::text AS id, institution_name, identifier_as_printed, holder_name FROM "
                             "financial_accounts WHERE case_id = :c ORDER BY id"), {"c": str(case_id)}).fetchall()
    for r in rows:
        if r.id == s:
            return r
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 4:
        hits = [r for r in rows if re.sub(r"\D", "", r.identifier_as_printed or "").endswith(digits[-4:])]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise ValueError("%d accounts in this case end %s; say which by id: %s." % (
                len(hits), digits[-4:], ", ".join(h.id for h in hits)))
    raise _Missing("%s No account %r." % (NOT_IN_CASE, s))


def _ending(printed):
    import re
    d = re.sub(r"\D", "", printed or "")
    return d[-4:] if len(d) >= 4 else None


def _mask_codes(s):
    return OTP_DIGITS.sub(lambda m: "•" * len(m.group(0)), s or "")


def _alert_strands(conn, case_id, acct_id, exts, a, b):
    """Approach 1 readings on these phones in [a, b) that bind to the account (bound) or could (ambiguous)."""
    run = _last_run(conn, case_id, "money_signals")
    if run is None:
        return None, []
    out = []
    for r in conn.execute(text(
            "SELECT r.id, r.measures, x.record_uid, x.field_path, x.extraction_id FROM phone_analysis_results r JOIN "
            "phone_analysis_result_records x ON x.result_id = r.id AND x.role = 'evidence' WHERE r.run_id = :run AND "
            "r.case_id = :c AND r.kind = 'money_reading' AND x.extraction_id = ANY(CAST(:e AS uuid[])) AND "
            "r.period_start >= :a AND r.period_start < :b ORDER BY r.period_start, r.id"),
            {"run": run.id, "c": str(case_id), "e": list(exts), "a": a, "b": b}):
        m = r.measures or {}
        bnd = m.get("binding") or {}
        ids = [x.get("id") for x in bnd.get("accounts") or []]
        if acct_id not in ids or bnd.get("outcome") not in ("bound", "ambiguous"):
            continue
        out.append({"kind": "alert", "phone": m.get("phone_label"), "at": m.get("event_instant"),
                    "source": m.get("source"), "amount": m.get("amount_text"), "outcome": m.get("outcome"),
                    "binding": bnd.get("outcome"), "by_ending": bnd.get("by_ending"),
                    "rec": "%s#%s" % (_rec(r.record_uid), r.field_path) if r.field_path else _rec(r.record_uid),
                    "extraction_id": str(r.extraction_id), "result_id": str(r.id),
                    "strength": "supporting" if bnd.get("outcome") == "bound" else "weak",
                    "words": ("The phone was told of a payment on this account" if bnd.get("outcome") == "bound" else
                              "The phone was told of a payment that fits this account and another one")})
    return str(run.id), out


def _code_strands(conn, case_id, institution, exts, a, b):
    """One-time codes from the account's institution on these phones in [a, b): a notification, text or email whose
    sender the institution directory names as the institution and whose words are a code (the code is masked)."""
    from services.financial.field_proposals import same_institution
    from services.phone_analysis import institutions as INST
    from services.phone_analysis import money_signals as MS
    if not institution:
        return []
    rows = conn.execute(text(
        "SELECT DISTINCT r.record_uid, r.extraction_id, r.model_type, r.first_instant FROM pv_record r JOIN pv_text t "
        "ON t.record_uid = r.record_uid AND t.case_id = r.case_id WHERE r.case_id = :c AND r.extraction_id = "
        "ANY(CAST(:e AS uuid[])) AND r.model_type IN ('Notification', 'InstantMessage', 'Email') AND "
        "r.parent_record_uid IS NULL AND r.first_instant >= :a AND r.first_instant < :b AND NOT t.is_sensitive AND "
        "t.value ~* :otp"), {"c": str(case_id), "e": list(exts), "a": a, "b": b, "otp": OTP_SQL}).fetchall()
    if not rows:
        return []
    uids = {str(r.record_uid): r for r in rows}
    sigs = {s["record_uid"]: s for s in MS.read_signals(conn, case_id) if s["record_uid"] in uids}
    directory = INST.for_case(conn, case_id)
    phones = MS._phone_context(conn, case_id)
    out = []
    for uid, sig in sorted(sigs.items(), key=lambda kv: (kv[1]["instant"] or datetime.min.replace(tzinfo=timezone.utc))):
        match = MS._institution_for(sig, directory, (phones.get(sig["extraction_id"]) or {}).get("country"))
        if match is None or not any(same_institution(institution, n) for n in MS._names(match)):
            continue
        body = next((sig["fields"].get(f) for f in ("Body", "Subject", "Snippet") if sig["fields"].get(f)), "")
        if not OTP_DIGITS.search(body or ""):
            continue
        out.append({"kind": "code", "phone": (phones.get(sig["extraction_id"]) or {}).get("label"),
                    "at": _iso(sig["instant"]), "rec": _rec(uid), "extraction_id": sig["extraction_id"],
                    "quote": _mask_codes(body)[:300], "strength": "supporting",
                    "words": "A one-time code from %s arrived on the phone: whoever held it could complete a login "
                             "or payment that needed it" % match.display_name})
    return out


def _app_strands(conn, case_id, institution, exts):
    """Approach 1 leads for the institution on these phones: the app installed, a saved login or a card record."""
    from services.financial.field_proposals import same_institution
    run = _last_run(conn, case_id, "money_signals")
    if run is None or not institution:
        return []
    out = []
    for r in conn.execute(text(
            "SELECT r.id, r.measures, array_agg(DISTINCT x.record_uid::text) AS recs, array_agg(DISTINCT "
            "x.extraction_id::text) AS exts FROM phone_analysis_results r JOIN phone_analysis_result_records x ON "
            "x.result_id = r.id WHERE r.run_id = :run AND r.case_id = :c AND r.kind = 'account_lead' AND "
            "x.extraction_id = ANY(CAST(:e AS uuid[])) GROUP BY r.id, r.measures"),
            {"run": run.id, "c": str(case_id), "e": list(exts)}):
        m = r.measures or {}
        name = (m.get("institution") or {}).get("name")
        counts = m.get("counts") or {}
        if not name or not same_institution(institution, name) or not (counts.get("presence") or counts.get("account")):
            continue
        out.append({"kind": "app", "institution": name, "evidence_counts": counts, "signals": m.get("signals"),
                    "records": [_rec(u) for u in sorted(r.recs)[:20]], "records_total": len(r.recs),
                    "result_id": str(r.id), "strength": "weak",
                    "words": "The phone holds the institution's app, a saved login or a card record (%s)" % ", ".join(
                        "%s %d" % kv for kv in sorted(counts.items()))})
    return out


def _interaction_strands(conn, alerts):
    """For each bound alert: did the phone's user do something on it in the five minutes before (04 class
    interaction, actor owner)?"""
    out = []
    for al in alerts:
        if al["binding"] != "bound" or not al.get("at"):
            continue
        t = datetime.fromisoformat(al["at"])
        n = conn.execute(text(
            "SELECT count(*) FROM pol_activity_event_v WHERE extraction_id = CAST(:e AS uuid) AND activity_class = "
            "'interaction' AND actor = 'owner' AND strength <> 'none' AND instant_utc >= :a AND instant_utc <= :b"),
            {"e": al["extraction_id"], "a": t - INTERACTION_LEAD, "b": t}).scalar() or 0
        if n:
            out.append({"kind": "interaction", "phone": al["phone"], "at": al["at"], "rec": al["rec"],
                        "extraction_id": al["extraction_id"],
                        "events": int(n), "strength": "supporting",
                        "words": "The phone's user did something on it in the five minutes before the alert (%d "
                                 "events)" % n})
    return out


def _device_person(conn, case_id, dossier, ext, labels, a, b):
    """Link 2 for one phone: why it is the person's (the owner identity a person linked), and what stands against."""
    from services.phone import identities as I
    own = I.owner(conn, ext)
    keys = own.get("owner_identity_keys") or []
    for_, against = [], []
    for k in keys:
        link = conn.execute(text(
            "SELECT a.actor_name, a.created_at, a.actor_origin FROM phone_identities i JOIN phone_identity_links l ON "
            "l.identity_id = i.id AND l.case_id = :c LEFT JOIN adjudications a ON a.id = l.decision_id AND a.case_id "
            "= :c WHERE i.case_id = :c AND i.identity_key = :k AND l.dossier_id::text = :d"),
            {"c": str(case_id), "k": k, "d": dossier}).first()
        if link:
            for_.append({"kind": "owner_identity", "identity_key": k, "basis": own.get("owner_basis"),
                         "linked_by": link.actor_name, "linked_at": _iso(link.created_at),
                         "strength": "supporting", "correlated_group": "phone_owner",
                         "words": "The phone's owner identity %s (%s) is linked to the person%s" % (
                             k, own.get("owner_basis"), (" by %s" % link.actor_name) if link.actor_name else "")})
    for code, words in (("more_than_one_user", "Signs of more than one user on this phone"),
                        ("shared_markers", "This phone shares numbers, SIMs, accounts or networks with another phone")):
        run = _last_run(conn, case_id, "device_users")
        if run is None:
            continue
        for r in conn.execute(text(
                "SELECT DISTINCT r.id, r.strength, r.measures FROM phone_analysis_results r JOIN "
                "phone_analysis_result_records x ON x.result_id = r.id WHERE r.run_id = :run AND r.case_id = :c AND "
                "r.kind = :k AND x.extraction_id = CAST(:e AS uuid)"),
                {"run": run.id, "c": str(case_id), "k": code, "e": ext}):
            if code == "shared_markers" and r.strength == "weak":
                continue  # a shared WiFi network: families share networks (19.S8-c)
            against.append({"kind": code, "result_id": str(r.id), "strength": r.strength, "words": words})
    synced = conn.execute(text(
        "SELECT count(*) FROM pol_place_observation WHERE extraction_id = CAST(:e AS uuid) AND start_utc < :b AND "
        "end_utc >= :a AND 'synced_from_account' = ANY(attribution_flags)"), {"e": ext, "a": a, "b": b}).scalar() or 0
    if synced:
        against.append({"kind": "synced_records", "count": int(synced), "strength": "context",
                        "words": "%d positions on the phone came from an account synced from another device" % synced})
    if not for_:
        against.append({"kind": "no_reviewed_owner_link", "strength": "missing",
                        "words": "No person has linked this phone's owner identity to the person"})
    return {"phone": labels.get(ext) or ext, "extraction_id": ext, "for": for_, "against": against}


def control_claim(conn, case_id, person, account, start, end) -> dict:
    """Connection 3: "person P had the means to operate account A from t1 to t2", as a chain of two separately
    evidenced links, every strand cited. Account to device: one-time codes from the institution, alerts for the
    account, the institution's app or login, and use of the phone just before an alert. Device to person: the
    phone's owner identity a person linked to P, with what stands against it. A proposal only, never "P is the
    holder"; it holds only when both links have a strand for them."""
    from services.phone.readings import phone_labels
    tool = "control_claim"

    def run():
        d = _dossier(conn, case_id, person)
        acct = _account(conn, case_id, account)
        a, b = _instant(start), _instant(end, end=True)
        if not (a and b) or b <= a:
            raise ValueError("Give the period as a start and an end, the end after the start.")
        from services.pattern_of_life import subjects
        exts = next((x["extraction_ids"] for x in subjects.dossiers(conn, str(case_id)) if x["dossier_id"] == d.id),
                    [])
        labels = phone_labels(conn, case_id)
        claim = ("%s had the means to operate the %s account ending %s from %s to %s" % (
            d.display_name, acct.institution_name or "unnamed", _ending(acct.identifier_as_printed) or "unknown",
            a.date().isoformat(), (b - timedelta(seconds=1)).date().isoformat()))
        base = dict(person={"dossier_id": d.id, "name": d.display_name},
                    account={"id": acct.id, "institution": acct.institution_name,
                             "ending": _ending(acct.identifier_as_printed),
                             "holder_printed": acct.holder_name},
                    period={"start": a.isoformat(), "end": b.isoformat()}, claim=claim, status=MODEL_DRAFT,
                    not_a_holder_finding="This is never a finding that the person is the account holder: the "
                                         "statement's printed holder is unchanged.")
        if not exts:
            return _base(tool, case_id, **base, established=False, total_matching=0, returned=0, has_more=False,
                         next_offset=None, items=[], chain=[],
                         coverage="No phone in this case is linked to %s, so neither link can be shown." %
                                  d.display_name,
                         limitation="Link a phone's owner to the person on People, then ask again.")
        run_id, alerts = _alert_strands(conn, case_id, acct.id, exts, a, b)
        codes = _code_strands(conn, case_id, acct.institution_name, exts, a, b)
        apps = _app_strands(conn, case_id, acct.institution_name, exts)
        inter = _interaction_strands(conn, alerts)
        device = []
        for e in exts:
            mine = [s for s in alerts + codes + inter if s.get("extraction_id") == e]
            for s in mine:
                s["correlated_group"] = "handset %s" % (labels.get(e) or e)
            device.append({"phone": labels.get(e) or e, "strands": mine})
        for s in apps:
            s["correlated_group"] = "the person's phones"
        if apps:
            device.append({"phone": "any of the person's phones", "strands": apps})
        link1_for = [s for s in alerts + codes + inter + apps if s["strength"] in ("supporting", "weak")]
        people = [_device_person(conn, case_id, d.id, e, labels, a, b) for e in exts]
        link2_for = [s for p in people for s in p["for"]]
        established = bool(link1_for) and bool(link2_for)
        chain = [{"link": "account_to_device", "holds": bool(link1_for), "by_phone": device,
                  "counts": {k: sum(1 for s in link1_for if s["kind"] == k) for k in ("code", "alert", "app",
                                                                                   "interaction")},
                  "not_read": None if run_id else "Money on the phones has not been run: alerts and the app are "
                                                  "not read."},
                 {"link": "device_to_person", "holds": bool(link2_for), "by_phone": people}]
        correlated = ("Strands from one handset are not independent: its alerts, codes, app and use all come from "
                      "the same phone and show the handset was told and used, not who held it. The owner identity "
                      "and the saved names on a phone also come from that phone.")
        items = [dict(s, link="account_to_device") for s in link1_for] + \
                [dict(s, link="device_to_person", phone=p["phone"]) for p in people for s in p["for"] + p["against"]]
        return _base(tool, case_id, **base, established=established, chain=chain, correlated_strands=correlated,
                     money_signals_run=run_id, total_matching=len(items), returned=len(items), has_more=False,
                     next_offset=None, items=items,
                     coverage="Account to device: %d codes, %d alerts, %d app or login records, %d alerts with use "
                              "just before, on %d phone%s. Device to person: %d reviewed owner links, %d strands "
                              "against." % (len(codes), len(alerts), len(apps), len(inter), len(exts),
                                            "" if len(exts) == 1 else "s", len(link2_for),
                                            sum(len(p["against"]) for p in people)),
                     limitation=None if established else "The chain does not hold: %s." % " and ".join(
                         x for x, ok in (("nothing ties the account to the person's phones", link1_for),
                                         ("no reviewed link ties a phone to the person", link2_for)) if not ok),
                     note="A proposal for a person to accept or reject; until then it is a model draft, not "
                          "confirmed. Present it as a claim about means, with every strand for and against.")
    return _guard(tool, case_id, run)


# ---- connection 4: the conversation around a payment ----------------------------------------------------------------

PURPOSE_OUTCOMES = ("consistent", "different", "discussed_purpose_not_stated", "no_conversation_in_window")
MAX_WINDOW_DAYS = 7


def _payment_row(conn, case_id, payment):
    s = str(payment or "").replace("txn://", "").strip()
    try:
        tid = str(uuid.UUID(s))
    except ValueError:
        r = conn.execute(text("SELECT id::text FROM financial_transactions WHERE case_id = :c AND ref_id = :r"),
                         {"c": str(case_id), "r": s}).first()
        if r is None:
            raise _Missing("%s No payment %r." % (NOT_IN_CASE, s))
        tid = r[0]
    t = conn.execute(text(
        "SELECT t.id::text AS id, t.ref_id, t.account_id::text AS account_id, t.amount_minor, t.currency, t.direction, "
        "t.proof_class, t.transaction_date, t.posted_date, t.ordering_date, t.description, t.counterparty_raw, "
        "t.bank_reference, t.ledger_status, t.superseded_by_id FROM financial_transactions t WHERE t.case_id = :c AND "
        "t.id = CAST(:i AS uuid)"), {"c": str(case_id), "i": tid}).first()
    if t is None:
        raise _Missing("%s No such payment." % NOT_IN_CASE)
    return t


def _payment_parties(conn, case_id, t, person_a=None, person_b=None):
    """The two people the payment is between, through reviewed identity (``link_edges.payments``): ``(a, b)``
    dossier rows, or ``None`` with the reason."""
    from sqlalchemy.orm import Session

    from services.phone import link_edges
    day = t.ordering_date
    if person_a and person_b:
        cands = [(_dossier(conn, case_id, person_a), _dossier(conn, case_id, person_b))]
    else:
        ds = conn.execute(text("SELECT id::text AS id, display_name, canonical_entity_key FROM case_profiles WHERE "
                               "case_id = :c AND archived_at IS NULL AND canonical_entity_key IS NOT NULL ORDER BY "
                               "display_name, id"), {"c": str(case_id)}).fetchall()
        cands = [tuple(ds)]  # every person once; pairs are formed from the account's holders below
    with Session(bind=conn) as session:
        sides = link_edges.financial_sides(session, case_id, list({d.canonical_entity_key for p in cands for d in p
                                                                   if d.canonical_entity_key}))
        empty = {"parties": set(), "accounts": set()}
        if not (person_a and person_b):
            # only the people holding the payment's account can be its first side: one comparison per other person
            people = {d.id: d for p in cands for d in p}.values()
            holders = [d for d in people if t.account_id in sides.get(d.canonical_entity_key, empty)["accounts"]]
            cands = [(h, o) for h in holders for o in people if o.id != h.id]
        for x, y in cands:
            if t.account_id not in (sides.get(x.canonical_entity_key, empty)["accounts"] |
                                    sides.get(y.canonical_entity_key, empty)["accounts"]):
                continue
            got = link_edges.payments(session, case_id, sides.get(x.canonical_entity_key, empty),
                                      sides.get(y.canonical_entity_key, empty), from_date=day, to_date=day)
            for r in got["rows"]:
                if r["id"] == t.id or (r.get("mirrored_by") or {}).get("id") == t.id:
                    return (x, y) if r["direction"] == "ab" else (y, x), None
    return None, ("The payment is not between two people in this case: its counterparty is not linked to a person "
                  "through a reviewed identity, or the account's holder is not." if not (person_a and person_b) else
                  "The ledger does not show this payment between those two people.")


def payment_conversation(conn, case_id, payment, *, person_a=None, person_b=None, hours=2, days=None, offset=0,
                         limit=DEFAULT_LIMIT) -> dict:
    """Connection 4: the payment row (``txn://``), the two people it is between, and every message, call and email
    between their phone identities in the window around it, each in full with its ``rec://`` link. The window is the
    phone alert's minute when approach 1 linked one to the row, else the payment's whole day (a ledger row has no
    time of day), widened by ``hours`` (default 2) or by ``days`` (up to 7). When nothing is in the window, the
    outcome is ``no_conversation_in_window`` with its reason; otherwise the model reads the purpose and drafts it
    with ``draft_payment_purpose``."""
    from services.phone import link_edges, records
    from services.phone_analysis import money_signals as MS
    tool = "payment_conversation"

    def run():
        t = _payment_row(conn, case_id, payment)
        row = {"txn": _txn(t.id), "ref_id": t.ref_id, "amount": link_edges.format_minor(int(t.amount_minor), t.currency),
               "direction": t.direction, "proof_class": str(t.proof_class),
               "day": (t.transaction_date or t.posted_date or t.ordering_date).isoformat(),
               "description": t.description, "counterparty_printed": t.counterparty_raw, "reference": t.bank_reference,
               "superseded": bool(t.superseded_by_id), "ledger_status": t.ledger_status}
        pair, why = _payment_parties(conn, case_id, t, person_a, person_b)
        if pair is None:
            return _base(tool, case_id, available=False, payment=row, total_matching=0, returned=0, has_more=False,
                         next_offset=None, items=[], reason=why)
        pa, pb = pair
        links = MS.phone_links(conn, case_id, [t.id]).get(t.id) or []
        zone = link_edges._zone(conn, case_id)
        from zoneinfo import ZoneInfo
        try:
            z = ZoneInfo(zone)
        except Exception:  # noqa: BLE001
            z = timezone.utc
        widen = timedelta(days=min(float(days), MAX_WINDOW_DAYS)) if days else timedelta(hours=float(hours or 2))
        if widen > timedelta(days=MAX_WINDOW_DAYS):
            widen = timedelta(days=MAX_WINDOW_DAYS)
        anchor_alert = next((x for x in links if x.get("instant")), None)
        if anchor_alert:
            at = datetime.fromisoformat(anchor_alert["instant"])
            a, b = at - widen, at + widen
            anchor = {"basis": "phone_alert", "at": anchor_alert["instant"], "rec": anchor_alert["link"]}
        else:
            d0 = t.transaction_date or t.posted_date or t.ordering_date
            a = datetime.combine(d0, datetime.min.time(), tzinfo=z) - widen
            b = datetime.combine(d0 + timedelta(days=1), datetime.min.time(), tzinfo=z) + widen
            anchor = {"basis": "ledger_day", "day": d0.isoformat(), "zone": zone}
        sa, sb = {"dossier_id": pa.id}, {"dossier_id": pb.id}
        found, totals = [], {}
        for kind in ("messages", "calls", "emails"):
            got = link_edges.edge_records(conn, case_id, sa, sb, kind, from_instant=a, to_instant=b, offset=0,
                                          limit=200)
            totals[kind] = got["total"]
            found += got["items"]
            off = len(got["items"])
            while off < got["total"]:
                more = link_edges.edge_records(conn, case_id, sa, sb, kind, from_instant=a, to_instant=b,
                                               offset=off, limit=200)
                if not more["items"]:
                    break
                found += more["items"]
                off += len(more["items"])
        found.sort(key=lambda x: (x["instant"] or "", x["record_uid"]))
        base = dict(payment=row, between={"a": {"dossier_id": pa.id, "name": pa.display_name},
                                          "b": {"dossier_id": pb.id, "name": pb.display_name},
                                          "direction": "a paid b"},
                    window={"start": a.isoformat(), "end": b.isoformat(), "widened_by": str(widen)},
                    anchor=anchor, totals=totals, phone_alerts=links, outcomes=list(PURPOSE_OUTCOMES))
        if not found:
            ever = link_edges.edges(conn, case_id, [sa, sb])["edges"][0]["communication"]
            n_ever = sum(link_edges.comm_total(ever, p) for p in ("messages", "calls", "emails"))
            span = conn.execute(text("SELECT min(sort_instant), max(sort_instant) FROM pv_comm_event WHERE case_id = :c"),
                                {"c": str(case_id)}).first()
            if not n_ever:
                reason = ("no_shared_thread_extracted", "No message, call or email between them is on any phone in "
                          "this case.")
            elif span[0] and (b < span[0] or a > span[1]):
                reason = ("outside_extraction_coverage", "The window is outside the time the phones' messages cover "
                          "(%s to %s)." % (span[0].date().isoformat(), span[1].date().isoformat()))
            else:
                dels = _deletions_in(conn, case_id, a, b)
                reason = (("deleted_per_approach_3", "Approach 3 shows deletion on the phones in this window (%d "
                           "results); the conversation may have been deleted." % dels) if dels else
                          ("no_messages_in_window", "They have %d messages, calls or emails between them, none in "
                           "this window." % n_ever))
            return _base(tool, case_id, **base, outcome="no_conversation_in_window", reason_code=reason[0],
                         reason=reason[1], total_matching=0, returned=0, has_more=False, next_offset=None, items=[],
                         coverage="Nothing between %s and %s from %s to %s." % (pa.display_name, pb.display_name,
                                                                                a.isoformat(), b.isoformat()),
                         note="Decided by the records, not by the model.")
        page, offset_, nxt = _page(found, offset, limit)
        items = []
        for it in page:
            try:
                det = records.record_detail(conn, case_id, it["record_uid"])
                body = records.record_text(det)
            except records.NotFound:
                body = None
            items.append(dict(it, rec=_rec(it["record_uid"]), text=body))
        return _base(tool, case_id, **base, outcome=None, total_matching=len(found), returned=len(items),
                     has_more=nxt is not None, next_offset=nxt, offset=offset_, items=items,
                     coverage="%d messages, %d calls and %d emails between %s and %s in the window." % (
                         totals["messages"], totals["calls"], totals["emails"], pa.display_name, pb.display_name),
                     limitation=("Only %d of %d are here; read on with offset %d before drafting." % (
                         len(items), len(found), nxt)) if nxt is not None else None,
                     note="Read every record in the window, then draft the purpose with draft_payment_purpose: "
                          "consistent, different, or discussed_purpose_not_stated, quoting the message by rec:// "
                          "against the row's description and reference. The reading is the model's until a person "
                          "confirms it; offer the surrounding thread with it.")
    return _guard(tool, case_id, run)


def _deletions_in(conn, case_id, a, b):
    run = _last_run(conn, case_id, "deletion_timeline")
    if run is None:
        return 0
    return int(conn.execute(text(
        "SELECT count(*) FROM phone_analysis_results WHERE run_id = :r AND case_id = :c AND period_start < :b AND "
        "coalesce(period_end, period_start) >= :a"), {"r": run.id, "c": str(case_id), "a": a, "b": b}).scalar() or 0)


def draft_payment_purpose(conn, case_id, payment, outcome, quoted, purpose=None, *, person_a=None, person_b=None,
                          hours=2, days=None) -> dict:
    """The model's reading of the stated purpose around a payment, checked and returned as a proposal labelled
    "model drafted, not confirmed". Every quoted record must be in the window ``payment_conversation`` reads (same
    arguments), so a quote from outside it is refused; ``no_conversation_in_window`` is the tool's, never the
    model's."""
    tool = "draft_payment_purpose"
    if outcome not in PURPOSE_OUTCOMES[:3]:
        raise ValueError("outcome is consistent, different or discussed_purpose_not_stated; no conversation in the "
                         "window is decided by payment_conversation.")
    quoted = [str(q).split("#")[0].replace("rec://", "").strip() for q in (quoted or []) if str(q).strip()]
    if not quoted:
        raise ValueError("Quote at least one message by its rec:// link.")
    if outcome in ("consistent", "different") and not (purpose or "").strip():
        raise ValueError("Say the purpose the messages state, in their words.")
    win = payment_conversation(conn, case_id, payment, person_a=person_a, person_b=person_b, hours=hours, days=days,
                               offset=0, limit=MAX_LIMIT)
    if not win.get("available", True) or win.get("not_in_case"):
        return win
    if win.get("outcome") == "no_conversation_in_window":
        raise ValueError("There is no conversation in the window (%s); nothing to read." % win["reason"])
    in_window = set()
    off = 0
    while True:
        in_window |= {i["record_uid"] for i in win["items"]}
        if not win["has_more"]:
            break
        off = win["next_offset"]
        win = payment_conversation(conn, case_id, payment, person_a=person_a, person_b=person_b, hours=hours,
                                   days=days, offset=off, limit=MAX_LIMIT)
    outside = [q for q in quoted if q not in in_window]
    if outside:
        raise ValueError("Not in the window between them: %s. Quote only records payment_conversation listed."
                         % ", ".join("rec://%s" % q for q in outside))
    return _base(tool, case_id, total_matching=1, returned=1, has_more=False, next_offset=None, status=MODEL_DRAFT,
                 items=[{"payment": win["payment"]["txn"], "between": win["between"], "window": win["window"],
                         "outcome": outcome, "purpose_stated": (purpose or "").strip() or None,
                         "quoted": ["rec://%s" % q for q in quoted],
                         "row_description": win["payment"]["description"],
                         "row_reference": win["payment"]["reference"], "status": MODEL_DRAFT,
                         "label": "Model reading: %s. Not confirmed by a person." % outcome.replace("_", " ")}],
                 coverage="The quotes are in the window between %s and %s." % (win["between"]["a"]["name"],
                                                                               win["between"]["b"]["name"]),
                 note="Present this as the model's reading, quoting each message with its rec:// link and the row "
                      "with its txn:// link; a person confirms it. Offer the surrounding thread with it.")


# ---- the tool list (registered in tools.py) -------------------------------------------------------------------------

from typing import Literal  # noqa: E402

from pydantic import BaseModel, Field  # noqa: E402


class _Page(BaseModel):
    offset: int = Field(0, ge=0)
    limit: int = Field(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)


class SearchCaseArgs(_Page):
    query: str = Field(..., description="Words, a name, a number or an address, typed as a person types it.")
    group: Literal["messages", "calls", "emails", "people", "records", "documents", "machine_text"] | None = Field(
        None, description="Page one group; leave empty for every group's total and first hits.")
    exact: bool = False
    phones: list[str] = Field(default_factory=list)
    start: str | None = None
    end: str | None = None


class PersonArgs(BaseModel):
    person: str = Field(..., description="A person (dossier) name or id.")


class SubjectArgs(_Page):
    person: str | None = Field(None, description="A person (dossier) name or id; or give phone.")
    phone: str | None = Field(None, description="A phone label (e.g. C5) or id; or give person.")


class DayArgs(SubjectArgs):
    day: str = Field(..., description="The local day, YYYY-MM-DD.")
    lanes: list[Literal["communications", "interaction", "places", "money", "device_state", "others",
                        "passive"]] = Field(default_factory=lambda: ["communications", "interaction", "places",
                                                                     "money"])
    zone: Literal["device", "case", "UTC"] = "device"


class TogetherArgs(_Page):
    start: str
    end: str
    person_a: str | None = None
    phone_a: str | None = None
    person_b: str | None = None
    phone_b: str | None = None
    window_minutes: float = Field(5, gt=0, le=1440)
    include_synced: bool = False


class RoutineArgs(SubjectArgs):
    start_date: str | None = None
    end_date: str | None = None
    zone: Literal["device", "case", "UTC"] = "device"


class MapSummaryArgs(BaseModel):
    phones: list[str] = Field(default_factory=list)
    start: str | None = None
    end: str | None = None


class BetweenArgs(_Page):
    person_a: str | None = Field(None, description="A person (dossier) name or id; or give identity_a.")
    identity_a: str | None = Field(None, description="One phone identity_key; or give person_a.")
    person_b: str | None = None
    identity_b: str | None = None
    start: str | None = None
    end: str | None = None


class MatchesArgs(_Page):
    outcome: Literal["corroborated", "near_amount", "several_candidates"] | None = None


class StatementArgs(BaseModel):
    claim_id: str = Field(..., description="The id of a statement a person confirmed on the Patterns screen.")


class AnalysisArgs(_Page):
    approach: Literal["deletion_timeline", "relationships", "awareness", "device_users"]
    kind: str | None = None
    phone: str | None = None
    start: str | None = None
    end: str | None = None


class ControlArgs(BaseModel):
    person: str = Field(..., description="A person (dossier) name or id.")
    account: str = Field(..., description="A financial account id, or its ending (four or more digits).")
    start: str
    end: str


class PaymentArgs(_Page):
    payment: str = Field(..., description="A payment's txn:// link, id or reference.")
    person_a: str | None = None
    person_b: str | None = None
    hours: float = Field(2, gt=0, le=168)
    days: float | None = Field(None, gt=0, le=MAX_WINDOW_DAYS)


class PurposeArgs(BaseModel):
    payment: str
    outcome: Literal["consistent", "different", "discussed_purpose_not_stated"]
    quoted: list[str] = Field(..., min_length=1, description="The rec:// links of the messages the reading rests on.")
    purpose: str | None = Field(None, description="The purpose the messages state, in their words.")
    person_a: str | None = None
    person_b: str | None = None
    hours: float = Field(2, gt=0, le=168)
    days: float | None = Field(None, gt=0, le=MAX_WINDOW_DAYS)


TOOLS = [
    ("search_case", "search_case", SearchCaseArgs,
     "Search everything in this case as Search does: messages, calls, emails, people, other phone records, documents "
     "and machine text. Without group: every group's exact total and first hits; with group: a page of it. Cite "
     "phone hits by rec://."),
    ("get_person_phones", "person_phones", PersonArgs,
     "A person's phone identities (numbers, addresses, app accounts) linked on People, each phone's names for them, "
     "their message and call counts, who linked them, and the phones the person owns."),
    ("get_day_activity", "day_activity", DayArgs,
     "One local day for a person or phone, as the Day view: totals per lane, hour availability, and the items "
     "(messages and calls, use of the phone, places, payments) oldest first. A payment has a day, never a time."),
    ("get_together_apart", "together_apart", TogetherArgs,
     "Whether two people's (or phones') positions were together or apart in a window, by the Patterns pair rule: "
     "counts, episodes and compared pairs. Positions are where phones recorded themselves."),
    ("get_routine_deviations", "routine_deviations", RoutineArgs,
     "A person's or phone's routine places and the days that broke the routine, with the hours and places."),
    ("get_phone_map_summary", "phone_map_summary", MapSummaryArgs,
     "The Map's phone totals: how many location records are placed, by source, and what cannot be placed and why."),
    ("get_contact_and_money_between", "contact_and_money_between", BetweenArgs,
     "Did two people talk, and did money move between them: messages, calls and emails on every phone, and the "
     "ledger money between them (verified rows summed per currency, p3 stated apart) with each payment's txn:// "
     "link. Use it for any 'between A and B' question."),
    ("get_money_signal_matches", "money_signal_matches", MatchesArgs,
     "Phone alerts that answer a ledger row (approach 1): the alert's rec:// and the row's txn://, the hour, handset "
     "and amount. An alert is p4 and never summed; the row keeps its class."),
    ("get_money_signal_leads", "money_signal_leads", _Page,
     "Accounts and periods the phones point to that the ledger does not hold (approach 1 leads), each with "
     "institution, masked ending, alert days, missing account or missing period, and records. Alerts are never "
     "totalled."),
    ("evaluate_statement", "statement_check", StatementArgs,
     "Check a statement a person confirmed against the phones (Patterns statement check): contradicted, "
     "contradicted_weakly, consistent, supported, mixed, insufficient_data, or no_record with its reason. Every "
     "item cited."),
    ("get_analysis_results", "analysis_results", AnalysisArgs,
     "Results of a phone analysis's last run: deletion_timeline, relationships, awareness or device_users, with "
     "exact totals and records cited."),
    ("draft_control_claim", "control_claim", ControlArgs,
     "Draft 'P had the means to operate account A from t1 to t2' as two evidenced links (account to phone: codes, "
     "alerts, app, use; phone to person: the reviewed owner link, with strands against). A proposal, model drafted "
     "and not confirmed; never 'P is the holder'."),
    ("get_payment_conversation", "payment_conversation", PaymentArgs,
     "The conversation between the two people a payment is between, in the window around it (the alert's minute "
     "or the payment's day, plus 2 hours by default, up to 7 days), each record in full, beside the row's "
     "description and reference. Says when there is no conversation in the window and why."),
    ("draft_payment_purpose", "draft_payment_purpose", PurposeArgs,
     "Record your reading of a payment's stated purpose (consistent, different, discussed_purpose_not_stated), "
     "quoting the messages by rec://; refused if a quote is outside the window. Returned as model drafted, not "
     "confirmed."),
]
