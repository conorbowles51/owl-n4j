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
from collections import defaultdict
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
        subj = {"kind": "dossier", "dossier_id": str(_dossier(conn, case_id, person).id)}
    try:
        r = subjects.resolve(conn, str(case_id), subj)
    except subjects.SubjectError as exc:
        raise _Missing("%s %s" % (NOT_IN_CASE, exc)) from None
    if not r["extraction_ids"]:
        from services.agent import fit
        name = r.get("name") or getattr(_dossier(conn, case_id, person), "display_name", None) or "this person"
        suggested = suggested_phones(conn, case_id, subj["dossier_id"]) if fit.on("C") else []
        if not suggested:
            raise ValueError("No phone in this case is linked to %s yet, and no identity suggestion ties a phone's "
                             "owner to them: a phone's owner must be linked to the person on People first." % name)
        best = suggested[0]
        link = {"by": "identity suggestion", "strength": best["strength"], "phones": best["phones"],
                "reasons": best["reasons"], "other_suggestions": [dict(phones=x["phones"], strength=x["strength"])
                                                                 for x in suggested[1:5]],
                "words": ("No person has linked a phone to %s. This reads %s, whose owner a %s identity suggestion "
                          "ties to them (%s); say so beside every fact from it, and that a person decides on "
                          "People." % (name, ", ".join(best["phones"]), best["strength"], "; ".join(best["reasons"][:3])))}
        r = dict(r, extraction_ids=best["extraction_ids"], name=name, subject=dict(r["subject"], link=link))
    return r


def suggested_identities(conn, case_id, dossier_id) -> list:
    """Phone identities an open identity suggestion ties to the person, strongest first:
    ``[{identity_key, shown_as, strength, reasons}]`` (the suggestions' own rule; nothing is linked or stored)."""
    from services.match_strength import LEVELS
    from services.phone import identity_decisions as idd
    rows = [r for r in idd.candidate_rows(conn, str(case_id)) if str(r.get("dossier") or "") == str(dossier_id)]
    ids = sorted({str(i) for r in rows for i in r["ids"]})
    shown = {str(i): (k, v) for i, k, v in conn.execute(text(
        "SELECT id::text, identity_key, value_display FROM phone_identities WHERE id = ANY(CAST(:i AS uuid[]))"),
        {"i": ids})} if ids else {}
    best = {}
    for r in rows:
        level, _ = idd.strength(r["score"], r["reasons"])
        for i in r["ids"]:
            key, value = shown.get(str(i), (None, None))
            if key and (key not in best or LEVELS.index(level) < LEVELS.index(best[key]["strength"])):
                best[key] = {"identity_key": key, "shown_as": value, "strength": level,
                             "reasons": [idd.READING.get(str(x.get("reason")), str(x.get("reason")))
                                         for x in r["reasons"] if x.get("reason")]}
    return sorted(best.values(), key=lambda x: (LEVELS.index(x["strength"]), x["identity_key"]))


def suggested_phones(conn, case_id, dossier_id) -> list:
    """Phones whose owner identity an open identity suggestion ties to the person, strongest first (lx-agentfit C):
    ``[{extraction_ids, phones, strength, reasons}]``. The suggestions' own rule grades them
    (``identity_decisions.strength``); nothing is linked or stored."""
    from services.match_strength import LEVELS
    from services.pattern_of_life import subjects
    from services.phone import identity_decisions as idd
    owners = {}
    for e in subjects._owners(conn, str(case_id)):
        if e["owner_identity_key"]:
            owners.setdefault(e["owner_identity_key"], []).append(e["extraction_id"])
    if not owners:
        return []
    keys = {str(i): k for i, k in conn.execute(text(
        "SELECT id, identity_key FROM phone_identities WHERE case_id = :c AND identity_key = ANY(:k)"),
        {"c": str(case_id), "k": list(owners)})}
    labels = _labels(conn, case_id)
    found = {}
    for row in idd.candidate_rows(conn, str(case_id)):
        if str(row.get("dossier") or "") != str(dossier_id):
            continue
        exts = sorted({x for i in row["ids"] if str(i) in keys for x in owners[keys[str(i)]]})
        if not exts:
            continue
        level, _ = idd.strength(row["score"], row["reasons"])
        key = tuple(exts)
        if key not in found or LEVELS.index(level) < LEVELS.index(found[key]["strength"]):
            found[key] = {"extraction_ids": exts, "phones": [labels.get(x) or x for x in exts], "strength": level,
                          "reasons": [idd.READING.get(str(x.get("reason")), str(x.get("reason")))
                                      for x in row["reasons"] if x.get("reason")]}
    return sorted(found.values(), key=lambda x: LEVELS.index(x["strength"]))


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


PERIOD_MAX_DAYS = 62


def period_activity(conn, case_id, start, end, *, person=None, phone=None,
                    lanes=("communications", "places", "money"), zone="device", offset=0, limit=DEFAULT_LIMIT) -> dict:
    """A person or phone over a period, as the Day view reads a day (``day.window`` with the money lane), for every
    day of the period: per day each lane's count, the items of the lanes asked for (oldest first, paged), and, for a
    person, the case's documents and records that name them (Search's own total) (lx-agentfit D)."""
    from sqlalchemy.orm import Session

    from services.pattern_of_life import day as day_view
    from services.pattern_of_life import money
    tool = "period_activity"

    def run():
        r = _subject(conn, case_id, person, phone)
        try:
            d0, d1 = date.fromisoformat(str(start)[:10]), date.fromisoformat(str(end)[:10])
        except ValueError:
            raise ValueError("Give start and end as dates, YYYY-MM-DD.") from None
        if d1 < d0:
            raise ValueError("The end is before the start.")
        if (d1 - d0).days + 1 > PERIOD_MAX_DAYS:
            raise ValueError("Read up to %d days in one call; split a longer period." % PERIOD_MAX_DAYS)
        z, zname = _zone(conn, case_id, r["extraction_ids"], zone)
        a, _ = day_view.day_bounds(d0, z)
        _, b = day_view.day_bounds(d1, z)
        with Session(bind=conn) as db:
            m = money.lane(db, case_id, start_date=d0, end_date=d1, zone=z, limit=5000)
        out = day_view.window(conn, r["extraction_ids"], _labels(conn, case_id), a, b, money_rows=m["items"])
        want = [x for x in (lanes or DAY_LANES) if x in DAY_LANES]
        per_day, items = {}, []
        for lane in DAY_LANES:
            for it in out["lanes"].get(lane) or []:
                when = it.get("at") or it.get("day")
                day = str(when)[:10] if when else "no time"
                if when and len(str(when)) > 10:
                    try:
                        day = datetime.fromisoformat(str(when).replace("Z", "+00:00")).astimezone(z).date().isoformat()
                    except ValueError:
                        pass
                per_day.setdefault(day, {}).setdefault(lane, 0)
                per_day[day][lane] += 1
                if lane not in want:
                    continue
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
        mentions = None
        name = r.get("name") or (person if person else None)
        if person and name:
            found = search_case(conn, case_id, name, group="documents", limit=10)
            mentions = {"query": name, "total": found.get("total_matching"), "items": found.get("items") or [],
                        "note": "Documents and machine text that name them (Search); read more with search_case."}
        totals = {k: sum(v.get(k, 0) for v in per_day.values()) for k in DAY_LANES}
        return _paged(tool, case_id, items, offset, limit, "items", subject=r["subject"],
                      period={"start": d0.isoformat(), "end": d1.isoformat()}, zone=zname, totals=totals,
                      per_day=dict(sorted(per_day.items())), documents_naming_them=mentions,
                      coverage="%s to %s in %s: %s." % (d0.isoformat(), d1.isoformat(), zname, ", ".join(
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
        if not 0 < float(window_minutes) <= 60:
            raise ValueError("The pairing window is up to 60 minutes here; a wider one runs on the Patterns screen.")
        # the hourly estimate pairs observations within an hour; a wider window pairs proportionally more
        est = colocation.estimate_pairs(conn, ra["extraction_ids"], rb["extraction_ids"], a, b) * \
            max(1.0, 2 * float(window_minutes) / 60)
        if est > cap:
            return _base(tool, case_id, available=False, total_matching=0, returned=0, has_more=False,
                         next_offset=None, items=[], estimated_pairs=est,
                         reason="About %s pairs to compare (estimate from hourly counts): too many to compute here. "
                                "Narrow the window, or run Together on the Patterns screen, which runs it in the "
                                "background and keeps every pair." % format(int(est), ","))
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


# Nights run from 18:00 to 06:00 local time and are named by their evening's date (lx-agentfit C: "on 14 of 14
# evenings"). Reverse if a case needs another split; the hours are stated in every result.
NIGHT_FROM, NIGHT_TO = 18, 6
COMPANY_MAX_DAYS = 400


def _night_or_day(instant, z):
    local = instant.astimezone(z)
    if local.hour >= NIGHT_FROM:
        return "night", local.date()
    if local.hour < NIGHT_TO:
        return "night", local.date() - timedelta(days=1)
    return "day", local.date()


def phone_company(conn, case_id, start, end, *, phone=None, person=None, other_phone=None, other_person=None,
                  zone="case", offset=0, limit=DEFAULT_LIMIT) -> dict:
    """Which phones were with one phone (or one person's phones) over a window, or how two compare, by the phone
    analysis's together-and-apart rule (``device_users.bin_verdicts`` and ``place_results``, the code its stored run
    uses), computed for this request and not stored: per companion the graded strength, quarter hours together and
    apart, the nights and days with a together quarter hour, the distances, and records cited."""
    from statistics import median

    from services.phone_analysis import device_users as DU
    from services.phone_analysis import fields as FV
    from services.phone_analysis import framework as F
    tool = "phone_company"

    def run():
        r = _subject(conn, case_id, person, phone)
        a, b = _instant(start), _instant(end, end=True)
        if not (a and b) or b <= a:
            raise ValueError("Give a start and an end, the end after the start.")
        if b - a > timedelta(days=COMPANY_MAX_DAYS):
            raise ValueError("Compare up to %d days in one call; split a longer period." % COMPANY_MAX_DAYS)
        phones = FV.active_phones(conn, str(case_id))
        mine = [e for e in r["extraction_ids"] if e in phones]
        if other_phone or other_person:
            ro = _subject(conn, case_id, other_person, other_phone, "other phone")
            others = [e for e in ro["extraction_ids"] if e in phones and e not in mine]
            other_subject = ro["subject"]
        else:
            others = [e for e in phones if e not in mine]
            other_subject = None
        z, zname = _zone(conn, case_id, mine, zone)
        params = F.validate_parameters(DU, {})
        exts = set(mine) | set(others)
        obs = {e: DU._observations(conn, e, params["include_synced"], a, b) for e in exts}
        inter = {e: DU._interactions(conn, e) for e in exts}
        lo, hi = DU._bin(a), DU._bin(b)
        wifi = {k: {bn: v for bn, v in bins.items() if lo <= bn <= hi}
                for k, bins in DU._wifi_bins(conn, case_id, exts).items()}
        counts = defaultdict(int)
        items = []
        for x in mine:
            for y in others:
                verdicts = DU.bin_verdicts(obs[x], obs[y], params, wifi.get((x, y), {}))
                graded = [g for g in DU.place_results(x, y, phones, verdicts, inter, counts) if g["kind"] == "co_location"]
                together = sorted(bn for bn, v in verdicts.items() if v["verdict"] == "together")
                apart = [bn for bn, v in verdicts.items() if v["verdict"] == "apart"]
                spans = defaultdict(set)
                for bn in together:
                    kind, day = _night_or_day(datetime.fromtimestamp(bn * DU.BIN_S, tz=timezone.utc), z)
                    spans[kind].add(day.isoformat())
                apart_nights = {_night_or_day(datetime.fromtimestamp(bn * DU.BIN_S, tz=timezone.utc), z)[1].isoformat()
                                for bn in apart if _night_or_day(datetime.fromtimestamp(bn * DU.BIN_S, tz=timezone.utc),
                                                                 z)[0] == "night"}
                dist = [verdicts[bn]["distance_m"] for bn in together if verdicts[bn]["distance_m"] is not None]
                cited = []
                for bn in together[:6]:
                    cited += [_rec(u) for u in (verdicts[bn]["x"][:1] + verdicts[bn]["y"][:1])]
                g = graded[0] if graded else None
                m = (g or {}).get("measures") or {}
                items.append({
                    "phone": phones[x], "companion": phones[y],
                    "strength": g["strength"] if g else None,
                    "quarter_hours_both_placed": len(verdicts), "together": m.get("together", len(together)),
                    "together_tight": m.get("together_tight"), "apart": m.get("apart", len(apart)),
                    "undecided": m.get("indeterminate"), "share_together": m.get("C"),
                    "nights_together": len(spans["night"]), "night_dates": sorted(spans["night"])[:60],
                    "days_together": len(spans["day"]), "day_dates": sorted(spans["day"])[:60],
                    "nights_apart_only": len(apart_nights - spans["night"]),
                    "distance_m_when_together": ({"median": round(median(dist), 1), "max": round(max(dist), 1)}
                                                 if dist else None),
                    "first_together": DU._bin_iso(together[0]) if together else None,
                    "last_together": DU._bin_iso(together[-1]) if together else None,
                    "supports": [d.get("detail") for d in ((g or {}).get("directions") or {}).get("supports") or []],
                    "undercuts": [d.get("detail") for d in ((g or {}).get("directions") or {}).get("undercuts") or []],
                    "records": cited})
        items.sort(key=lambda i: (-(i["together"] or 0), i["companion"] or ""))
        placed = {phones[e]: len(obs[e]) for e in sorted(exts, key=lambda e: phones[e])}
        return _paged(tool, case_id, items, offset, limit, "companions", subject=r["subject"],
                      other=other_subject, window={"start": a.isoformat(), "end": b.isoformat()}, zone=zname,
                      nights="%02d:00 to %02d:00 %s, named by the evening's date" % (NIGHT_FROM, NIGHT_TO, zname),
                      place_observations=placed, label=PLACE_LABEL,
                      computed=("Computed for this answer by the phone analysis's together-and-apart rule (quarter "
                                "hours, graded strong, moderate, weak or faint by its stated rule); not stored, and a "
                                "lead, not who carried a phone."),
                      coverage="Compared %s with %d other phone(s) over %s to %s: %d with a quarter hour together." % (
                          ", ".join(phones[e] for e in mine), len(others), a.date().isoformat(), b.date().isoformat(),
                          sum(1 for i in items if i["together"])))
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
        res = routine.compute(conn, r["extraction_ids"], z, case_id=case_id, subject=routine.subject_key(r))
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


BETWEEN_RECORDS = 25


def _side_sightings(conn, case_id, keys, per_side=3):
    """Where each side's identities appear on the phones (contact cards and the records naming them), cited, so an
    answer of no contact can name what was searched (lx-agentfit D)."""
    if not keys:
        return []
    return [{"identity_key": r.identity_key, "shown_as": r.value_display, "name_beside_it": r.name_alongside,
             "rec": _rec(r.card_record_uid or r.record_uid)} for r in conn.execute(text(
                 "SELECT DISTINCT ON (identity_key) identity_key, value_display, name_alongside, card_record_uid, "
                 "record_uid FROM pv_identity_sighting WHERE case_id = :c AND identity_key = ANY(:k) ORDER BY "
                 "identity_key, (card_record_uid IS NULL), instant NULLS LAST"), {"c": str(case_id), "k": list(keys)})
            ][:per_side * max(1, len(keys))]


def _between_records(conn, case_id, link_edges, sa, sb, a, b):
    """The messages, calls and emails behind the edge's counts, oldest first, each with its text and rec:// link."""
    out = {}
    for kind in ("messages", "calls", "emails"):
        got = link_edges.edge_records(conn, case_id, sa, sb, kind, from_instant=a, to_instant=b, offset=0,
                                      limit=BETWEEN_RECORDS)
        texts = {str(r.event_uid): r for r in conn.execute(text(
            "SELECT event_uid, body, subject, app, call_duration_s FROM pv_comm_event WHERE case_id = :c AND "
            "event_uid = ANY(CAST(:e AS uuid[]))"), {"c": str(case_id), "e": [i["event_uid"] for i in got["items"]]})
        } if got["items"] else {}
        items = []
        for i in got["items"]:
            t = texts.get(i["event_uid"])
            items.append({"at": i["instant"], "phone": i["phone"], "direction": i["direction"], "rec": i["link"],
                          "app": t.app if t else None, "text": ((t.body or t.subject or "") if t else "")[:600] or None,
                          "call_seconds": float(t.call_duration_s) if t and t.call_duration_s is not None else None})
        out[kind] = {"total": got["total"], "shown": len(items), "items": items}
    return out


def _between_suggested(conn, case_id, sa, sb, suggested, a, b, with_records):
    """Each pair of identities when a side is read through its suggested identities: every pair's counts, with the
    suggestion and its strength beside it."""
    from services.phone import link_edges

    def options(tag, subject):
        if tag not in suggested:
            return [dict(subject=subject)]
        return [dict(subject={"identity_key": x["identity_key"]}, suggestion=x) for x in suggested[tag]["identities"]]
    pairs = []
    for x in options("a", sa)[:6]:
        for y in options("b", sb)[:6]:
            try:
                out = link_edges.edges(conn, case_id, [x["subject"], y["subject"]], from_instant=a, to_instant=b)
            except link_edges.NotInCase:
                continue
            edge = out["edges"][0]
            item = {"a": edge["a"]["label"], "b": edge["b"]["label"], "communication": edge["communication"],
                    "label_line": edge["label"], "a_suggested": x.get("suggestion"), "b_suggested": y.get("suggestion")}
            if with_records:
                item["records"] = _between_records(conn, case_id, link_edges, x["subject"], y["subject"], a, b)
            pairs.append(item)
    return pairs


def contact_and_money_between(conn, case_id, *, person_a=None, identity_a=None, person_b=None, identity_b=None,
                              start=None, end=None, with_records=False, offset=0, limit=DEFAULT_LIMIT) -> dict:
    """One edge between two people (02 11.2): messages, calls and emails between them on every phone, and the money
    between them from the ledger (verified p0-p2 summed per currency, p3 stated beside it, never summed across
    currencies), with the payments behind the money listed and cited."""
    from services.phone import link_edges
    tool = "contact_and_money_between"

    def run():
        sa = _edge_subject(conn, case_id, person_a, identity_a)
        sb = _edge_subject(conn, case_id, person_b, identity_b)
        a, b = _instant(start), _instant(end, end=True)
        # A person with no phone identity linked is read through the identities an identity suggestion ties to them
        # (each counted as its own side, the link and its strength stated), never counted as no contact
        # (lx-agentfit D: the demo's "did Mateo ever contact Okafor" was answered from a count over no identity).
        from services.agent import fit
        suggested, unlinked = {}, []
        for tag, subject in (("a", sa), ("b", sb)):
            if subject.get("dossier_id"):
                try:
                    side = link_edges.resolve_side(conn, case_id, subject)
                except link_edges.NotInCase as exc:
                    raise _Missing(str(exc)) from None
                if not side["keys"]:
                    # The count over no identity is never given as no contact (always on); counting through the
                    # suggested identities is item D's.
                    found = suggested_identities(conn, case_id, subject["dossier_id"]) if fit.on("D") else []
                    if found:
                        suggested[tag] = dict(person=side["label"], identities=found)
                    else:
                        unlinked.append(side["label"])
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
        # A side with no phone identity linked has no contact to count: said, never a silent zero (lx-agentfit D).
        sides = {}
        for tag, subject in (("a", sa), ("b", sb)):
            side = link_edges.resolve_side(conn, case_id, subject)
            if not fit.on("D"):
                if not side["keys"] and side["label"] in unlinked:
                    limits.append("No phone identity is linked to %s, so no message, call or email of theirs can be "
                                  "counted here; find their numbers with phone_find_people and read phone_messages."
                                  % side["label"])
                continue
            seen_keys = side["keys"] or [x["identity_key"] for x in (suggested.get(tag) or {}).get("identities", [])]
            sides[tag] = {"label": side["label"], "identities": len(side["keys"]),
                          "where_seen": _side_sightings(conn, case_id, seen_keys)}
            if not side["keys"] and side["label"] in unlinked:
                limits.append("No phone identity is linked to %s and no identity suggestion ties one to them, so no "
                              "message, call or email of theirs can be counted here; find their numbers with "
                              "phone_find_people and read phone_messages." % side["label"])
        extra = {"sides": sides} if fit.on("D") else {}
        label = edge["label"]
        if suggested:
            pairs = _between_suggested(conn, case_id, sa, sb, suggested, a, b, with_records)
            people = " or ".join(v["person"] for v in suggested.values())
            extra["suggested_pairs"] = pairs
            label = ("No person has linked a phone identity to %s, so contact is counted through the identities an "
                     "identity suggestion ties to them (say so, with the strength, beside every count): %s" % (
                         people, "; ".join("%s and %s: %s" % (p["a"], p["b"], p["label_line"]) for p in pairs)))
            limits = [x for x in limits if not any(v["person"] in x for v in suggested.values())]
        elif unlinked:
            label = "Contact cannot be counted: no phone identity is linked to %s." % " or ".join(unlinked)
        if with_records and not suggested and fit.on("D"):
            extra["records"] = _between_records(conn, case_id, link_edges, sa, sb, a, b)
        return _paged(tool, case_id, rows, offset, limit, "payments", a=edge["a"], b=edge["b"], communication=c, **extra,
                      money=money, money_mentioned_on_phones=edge["money_mentioned_on_phones"],
                      money_readings_available=edge["money_readings_available"], label_line=edge["label"],
                      money_absent=out["money_absent"], zone=out["zone"],
                      coverage="%s and %s: %s. Money: %s." % (
                          edge["a"]["label"], edge["b"]["label"], label,
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
LEVELS = ("strong", "moderate", "weak", "faint")


def _pair_out(p):
    """One candidate payment of a reading, as the matches screen shows it (05 4.3.8)."""
    from services.phone import link_edges
    status = ("rejected by a person" if p.get("decision") == "rejected" else
              "confirmed by a person" if p.get("decision") == "confirmed" else "found by the rule, not confirmed")
    return {"payment": p["transaction_id"], "txn": _txn(p["transaction_id"]), "ref": p.get("ref_id"),
            "financial_href": "financial?view=transactions&payment=%s" % p["transaction_id"],
            "strength": p.get("level"), "status": status, "decision_words": p.get("decision_words"),
            "found_by_rule": p.get("found_by_rule", True), "rule_match": bool(p.get("rule_match")),
            "amount": link_edges.format_minor(p["amount_minor"], p["currency"])
            if p.get("amount_minor") is not None and p.get("currency") else None,
            "date": p.get("date"), "lag_days": p.get("lag_days"),
            "how_well_matched": (p.get("reasons") or {}).get("match") or [],
            "how_substantiated": (p.get("reasons") or {}).get("substantiation") or [],
            "base_rate": p.get("base_rate")}


def _line(it, p):
    alert = "%s %s on %s, %s" % (it.get("source") or "record", " ".join(x for x in (it.get("amount_text") or "",
                                 {"debit": "out", "credit": "in"}.get(it.get("direction") or "", "")) if x),
                                 it.get("phone") or "a phone", (it.get("instant") or "")[:10])
    return "%s | %s | payment %s, %s, %s | %s | %s%s" % (
        (p.get("strength") or "").capitalize(), alert, p.get("ref") or p["payment"], p.get("amount") or "",
        p.get("date") or "", "; ".join(p.get("how_well_matched") or []) or "no longer found by the rule",
        p.get("decision_words") or p["status"],
        " | %s" % p["base_rate"]["words"] if p.get("base_rate") else "")


def match_lines(items) -> dict:
    """One ready line per pairing on this page, grouped by strength (strongest first) with rejected ones apart: the
    answer copies them, so no pairing is dropped or summarised (05 4.3.8)."""
    out = {lv: [] for lv in LEVELS}
    out["rejected"] = []
    for it in items:
        for p in it.get("pairings") or []:
            out.setdefault(p.get("strength") or "faint", []).append(_line(it, p))
        for p in it.get("rejected_pairings") or []:
            out["rejected"].append(_line(it, p))
    return out


def money_signal_matches(conn, case_id, *, outcome=None, strength=None, offset=0, limit=DEFAULT_LIMIT) -> dict:
    """Every phone money reading of approach 1's last run that pairs with a ledger row at any strength (strong,
    moderate, weak, faint; 05 4.3.8), strongest first, each with its candidate payments (txn://), the strength by rule
    and the plain reasons (how well matched, how substantiated), and whether a person confirmed or rejected the pairing.
    Rejected pairings stay listed and are left out of every count. The correlation outcome (corroborated, near amount,
    several candidates) is unchanged; strength is extra. A reading stays p4; a row keeps its class."""
    from services.agent import phone_tools
    from services.phone_analysis import framework as F
    from services.phone_analysis import money_pairings as MP
    tool = "money_signal_matches"
    if outcome and outcome not in MATCHED:
        raise ValueError("outcome is one of %s; other readings are in phone_money_readings." % ", ".join(MATCHED))
    if strength and strength not in LEVELS:
        raise ValueError("strength is one of %s." % ", ".join(LEVELS))
    run = _last_run(conn, case_id, "money_signals")
    if run is None:
        return _base(tool, case_id, total_matching=0, returned=0, has_more=False, next_offset=None, items=[],
                     coverage="Money on the phones has not been run in this case.",
                     limitation="Run it from Money on the phones; until then there is nothing to read.")
    base = {}
    got = phone_tools.money_readings(conn, case_id, offset=0, limit=MAX_LIMIT)
    while True:
        for it in got["items"]:
            base[it["result_id"]] = it
        if not got["has_more"]:
            break
        got = phone_tools.money_readings(conn, case_id, offset=got["next_offset"], limit=MAX_LIMIT)
    measures = []
    res = F.results(conn, case_id, run.id, kind="money_reading", offset=0, limit=F.MAX_LIMIT, order="strength")
    measures += res["items"]
    while len(measures) < res["total"] and res["items"]:
        res = F.results(conn, case_id, run.id, kind="money_reading", offset=len(measures), limit=F.MAX_LIMIT,
                        order="strength")
        measures += res["items"]
    items, by_outcome, by_level = [], {}, {lv: 0 for lv in LEVELS}
    confirmed = rejected = 0
    all_rejected = []
    left_words = []
    old_run = False
    for r in measures:
        m = r["measures"] or {}
        it = base.get(r["id"])
        if it is None:
            continue
        if "pairings" not in m and m.get("outcome") in MATCHED:
            old_run = True
        pairs = [_pair_out(p) for p in m.get("pairings") or []]
        if not pairs and m.get("outcome") not in MATCHED:
            continue
        rejected_rule = {p["payment"] for p in pairs if p["rule_match"] and p["status"] == "rejected by a person"}
        live = [p for p in pairs if p["status"] != "rejected by a person"]
        best = live[0]["strength"] if live else None
        if not live and not (m.get("outcome") in MATCHED and not rejected_rule):
            # every pairing was rejected by a person: not a reading that pairs, counted apart and listed apart
            all_rejected.append({"result_id": r["id"], "rec": it.get("rec"),
                                 "rejected": [p["payment"] for p in pairs]})
            rejected += len(pairs)
            continue
        if outcome and m.get("outcome") != outcome:
            continue
        if strength and best != strength:
            continue
        o = m.get("outcome")
        if o in ("corroborated", "near_amount") and rejected_rule:
            o = "rule match rejected by a person"
        by_outcome[o] = by_outcome.get(o, 0) + 1
        for p in pairs:
            if p["status"] == "rejected by a person":
                rejected += 1
            else:
                if p["found_by_rule"]:
                    by_level[p["strength"]] = by_level.get(p["strength"], 0) + 1
                if p["status"] == "confirmed by a person":
                    confirmed += 1
        for row in it["ledger_rows"]:
            row["txn"] = _txn(row["payment"])
            if row["payment"] in rejected_rule:
                row["status"] = "rejected by a person"
        if m.get("pairings_left_out_words"):
            left_words.append(m["pairings_left_out_words"])
        # rejected pairings sit in their own list, so no reading of the matches can count one as a match
        items.append(dict(it, best_strength=best, pairings=live,
                          rejected_pairings=[p for p in pairs if p["status"] == "rejected by a person"],
                          pairings_left_out=m.get("pairings_left_out") or {},
                          pairings_left_out_words=m.get("pairings_left_out_words")))
    total_pairs = sum(by_level.values())
    cov = ("Approach 1's last run: %d phone readings pair with ledger rows; %d pairings by strength: %s. %d confirmed "
           "by a person, %d rejected by a person (left out of these counts). Outcomes: %s.%s" % (
               len(items), total_pairs, ", ".join("%s %d" % (lv, by_level[lv]) for lv in LEVELS), confirmed, rejected,
               ", ".join("%s %d" % kv for kv in sorted(by_outcome.items())) or "none",
               (" %d more readings had every pairing rejected by a person and are not counted." % len(all_rejected))
               if all_rejected else ""))
    limitation = None
    if left_words:
        limitation = "Search bound: %s %d readings have payments outside it, counted not listed (see each " \
                     "reading's pairings_left_out_words)." % (MP.search_words(), len(left_words))
    if old_run:
        limitation = " ".join(x for x in (limitation, "The last run predates match strengths; run Money on the phones "
                                          "again to list every candidate payment with its strength.") if x)
    out = _paged(tool, case_id, items, offset, limit, "readings", run_id=str(run.id), by_outcome=by_outcome,
                  by_strength=by_level, confirmed_by_person=confirmed, rejected_by_person=rejected,
                  readings_with_every_pairing_rejected=all_rejected,
                  search=MP.search_words(), coverage=cov, limitation=limitation,
                  note="Mention every pairing with its strength and reasons, one line each, weak and faint ones as weak "
                       "or faint; never replace them with examples or a count, and never say they are only in the tool "
                       "output. Copy every line of match_lines under its strength heading (Strong, Moderate, Weak, Faint) and the rejected lines apart; rejected_pairings are not matches: list them apart, never under a strength. Say which are confirmed by a person and which are found by the rule; never "
                       "call a rule-found pairing confirmed. Rejected pairings are not evidence of a match and are "
                       "not counted. A reading is what a phone shows (p4), never summed; a row keeps its class.")
    out["match_lines"] = match_lines(out.get("items") or [])
    return out


def _lead_alert_days(conn, case_id, run_id, record_uids):
    """The days of the transactional alerts behind a lead, in the phone's own zone as approach 1 dates them (the
    statement's days are the bank's local days), from the same run's money readings."""
    if not record_uids:
        return []
    return sorted({str(r[0])[:10] for r in conn.execute(text(
        "SELECT r.measures ->> 'event_date' FROM phone_analysis_results r JOIN phone_analysis_result_records x ON "
        "x.result_id = r.id WHERE r.run_id = :run AND r.case_id = :c AND r.kind = 'money_reading' AND x.record_uid = "
        "ANY(CAST(:u AS uuid[])) AND r.measures ->> 'event_date' IS NOT NULL"),
        {"run": run_id, "c": str(case_id), "u": list(record_uids)})})


def money_signal_leads(conn, case_id, *, offset=0, limit=DEFAULT_LIMIT) -> dict:
    """Approach 1's leads (05 4.3.7) with the ledger half: a lead whose ending is not among the case's accounts is a
    missing account; a held account whose alerts fall on days no admitted statement period covers is a missing
    period (the uncovered months are listed). Alerts are listed by day and never totalled (p4). Leads come in the
    stated rank order (``money_signals.LEAD_RANK_RULE``), each with its reason; every lead is listed."""
    from services.phone_analysis import framework as F
    from services.phone_analysis.money_signals import LEAD_RANK_RULE
    tool = "money_signal_leads"
    run = _last_run(conn, case_id, "money_signals")
    if run is None:
        return _base(tool, case_id, total_matching=0, returned=0, has_more=False, next_offset=None, items=[],
                     coverage="Money on the phones has not been run in this case.",
                     limitation="Run it from Money on the phones; until then there are no leads.")
    res = F.results(conn, case_id, run.id, kind="account_lead", offset=0, limit=F.MAX_LIMIT, order="lead_rank")
    rows = list(res["items"])
    while len(rows) < res["total"]:
        res = F.results(conn, case_id, run.id, kind="account_lead", offset=len(rows), limit=F.MAX_LIMIT,
                        order="lead_rank")
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
        items.append({"rank": len(items) + 1, "rank_reason": r.get("rank_reason"),
                      "result_id": r["id"], "institution": (m.get("institution") or {}).get("name"),
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
                  rank_rule=LEAD_RANK_RULE, coverage="Approach 1's last run: %d leads (%s)." % (len(items), ", ".join(
                      "%s %d" % kv for kv in sorted(by.items())) or "none"),
                  note="A lead is evidence of an account or a period the case does not hold. Alerts are p4: listed, "
                       "never totalled. Give the leads in rank order with rank_reason and name rank_rule; every "
                       "lead stays listed. A lead card the agent writes is a draft a person edits.")


def statement_check(conn, case_id, claim_id, offset=0, limit=MAX_LIMIT) -> dict:
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
    page, off, nxt = _page(items, offset, limit)
    return _base(tool, case_id, claim={"id": str(cid), "kind": claim["kind"], "window_start": _iso(claim["window_start"]),
                                       "window_end": _iso(claim["window_end"]), "text": claim.get("window_text")},
                 outcome=res["outcome"], outcome_basis=res["outcome_basis"], words=res["summary"]["words"],
                 no_record_reason=res["summary"].get("no_record_reason"), counts=res["counts"],
                 not_yet_checked=res["summary"]["not_yet_checked"], total_matching=len(items),
                 returned=len(page), has_more=nxt is not None, next_offset=nxt, offset=off, items=page,
                 coverage="Checked the statement now: %s (%s); %d items." % (res["outcome"], res["outcome_basis"],
                                                                           len(items)),
                 limitation=("Only %d of %d items are here (undercutting first); read on with offset %d." % (
                     len(page), len(items), nxt)) if nxt is not None else None,
                 note="Computed by the check's own rule; the outcome is never the model's. Not stored: Check on the "
                      "Patterns screen keeps it.")


def monitoring_app_indicators(conn, case_id, *, start=None, end=None, offset=0, limit=DEFAULT_LIMIT) -> dict:
    """Monitoring apps on the phones and bank control notices, one date-ordered lane, each with its basis. An indicator
    a person weighs, never a finding. Dates are hard: what falls outside is counted, nothing is summed."""
    from sqlalchemy.orm import Session

    from services.phone_analysis import monitoring_apps as MA
    tool = "monitoring_app_indicators"
    a, b = _instant(start), _instant(end, end=True)
    with Session(bind=conn) as session:
        got = MA.indicators(conn, session, case_id, start=a, end=b)
    items = got["items"]
    return _paged(tool, case_id, items, offset, limit, "items", by_kind={"monitoring_app": got["monitoring_apps"],
                                                                         "bank_control": got["bank_control_notices"]},
                  set_aside=got["set_aside"], outside_dates=got["outside_dates"], list_source=got["list"],
                  coverage=got["coverage"], not_read=got["not_read"], limitation=got["limits"],
                  note="Report each item with its basis and its rec:// link, labelled as an indicator. Never say who "
                       "installed or used an app, or that someone took control of an account.")


def glossary_terms(conn, case_id, *, offset=0, limit=DEFAULT_LIMIT) -> dict:
    """The code words a person confirmed, each with every mention and the ledger rows it joins to."""
    from sqlalchemy.orm import Session

    from services.agent import glossary as G
    tool = "glossary_terms"
    with Session(bind=conn) as session:
        got = G.read(conn, session, case_id)
    terms = [t for t in got["items"] if t["status"] == "confirmed"]
    return _paged(tool, case_id, terms, offset, limit, "terms", confirmed=got["confirmed"],
                  coverage="%d confirmed terms in this case; %d withdrawn by a person and left out." % (
                      got["confirmed"], got["total"] - got["confirmed"]), limitation=got["limitation"],
                  note="Say each meaning is a person's reading and name who confirmed it (reading_words). A meaning "
                       "waiting on Workspace is a model reading and is not here. Link messages by rec:// and rows by "
                       "txn://; state the join window and each mention's join_reason; never add amounts.")


ANALYSES = ("deletion_timeline", "relationships", "awareness", "device_users")


# lx-agentfit C: an analysis never run in the case is computed for the question, by its own code on the run's read-only
# connection, and nothing is stored. Bounded so one answer never holds the live database long: the module's own
# cancellation check after COMPUTE_SECONDS, and a statement timeout per query; a computation that is stopped says so
# and returns nothing partial. Reverse (raise or lower) if a measured case needs it.
COMPUTE_SECONDS = 90
COMPUTED_LABEL = ("Computed for this answer by the analysis's own code and its stated grading rule; not stored, and "
                  "nobody has reviewed it. A lead for enquiry, never who did what.")


class _ComputeCtx:
    def __init__(self, seconds):
        import time as _t
        self._t, self.until, self.stopped = _t, _t.monotonic() + seconds, False

    def progress(self, *args, **kwargs):
        return None

    def cancelled(self):
        if self._t.monotonic() > self.until:
            self.stopped = True
        return self.stopped


def computed_results(conn, case_id, approach):
    """``(results, None)`` from computing the approach now, or ``(None, reason)`` when it could not finish in the
    bound. Results are the module's own (kind, strength, measures, directions, records)."""
    from services.phone_analysis import approaches, framework as F
    approaches.install()
    module = F.approach(approach)
    ctx = _ComputeCtx(COMPUTE_SECONDS)
    try:
        with conn.begin_nested():
            conn.execute(text("SET LOCAL statement_timeout = '%ds'" % COMPUTE_SECONDS))
            results = module.run(conn, str(case_id), F.validate_parameters(module, {}), ctx)
    except Exception as exc:  # noqa: BLE001 - a computation that fails is reported, never a silent empty result
        if "statement timeout" in str(exc) or "canceling statement" in str(exc):
            return None, ("It is too large to compute within one answer (a query ran past %d s). Run it from the "
                          "phone analyses screen." % COMPUTE_SECONDS)
        raise
    if ctx.stopped:
        return None, ("It is too large to compute within one answer (stopped after %d s, nothing partial is shown). "
                      "Run it from the phone analyses screen." % COMPUTE_SECONDS)
    return results, None


def _not_current_words(approach, run):
    if run is None:
        return "%s has not been run in this case." % approach
    return ("The last run of %s (finished %s) read the phones, identities or ledger as they were then, not as the case "
            "holds them now." % (approach, _iso(run.finished_at)))


def _computed_out(r):
    recs = [{"rec": _rec(x["record_uid"]) + ("#%s" % x["field_path"] if x.get("field_path") else ""), "role": x["role"]}
            if x.get("record_uid") else {"txn": _txn(x.get("ledger_transaction_id")), "role": x["role"]}
            for x in (r.get("records") or [])[:50]]
    return {"kind": r["kind"], "strength": r["strength"], "measures": _clean(r.get("measures") or {}),
            "directions": r.get("directions"), "period_start": _iso(r.get("period_start")),
            "period_end": _iso(r.get("period_end")), "records": recs}


def analysis_results(conn, case_id, approach, *, kind=None, phone=None, start=None, end=None, offset=0,
                     limit=DEFAULT_LIMIT, strength=None) -> dict:
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
    # A stored run on older inputs is read as stored, with that said (measured 11 Nov: 30 of 33 stored runs on the
    # check and reference cases read older inputs; computing each again would cost every such call up to 90 s).
    from services.agent import fit
    stale = run is not None and not F.run_is_current(conn, case_id, approach, run.id)
    if run is None and fit.on("C"):
        results, reason = computed_results(conn, case_id, approach)
        if results is None:
            return _base(tool, case_id, approach=approach, available=False, total_matching=0, returned=0,
                         has_more=False, next_offset=None, items=[], reason="%s %s" % (
                             _not_current_words(approach, run), reason))
        a, b = _instant(start), _instant(end, end=True)
        keep = [r for r in results if (not kind or r["kind"] == kind) and (not strength or r["strength"] == strength)
                and (not ext or any(str(x.get("extraction_id")) == ext for x in r.get("records") or []))
                and (not a or not r.get("period_end") or _instant(_iso(r["period_end"]), end=True) >= a)
                and (not b or not r.get("period_start") or _instant(_iso(r["period_start"])) <= b)]
        by_strength = {}
        for r in keep:
            by_strength[r["strength"]] = by_strength.get(r["strength"], 0) + 1
        return _paged(tool, case_id, [_computed_out(r) for r in keep], offset, limit, "results", approach=approach,
                      computed=COMPUTED_LABEL, kinds=list(getattr(module, "KINDS", ())), by_strength=by_strength,
                      strength_rule=getattr(module, "RULE_OF_THUMB", None),
                      coverage="%s Computed now for this answer: %d result(s)%s." % (
                          _not_current_words(approach, run), len(keep), (" of kind %s" % kind) if kind else ""))
    if run is None:
        return _base(tool, case_id, approach=approach, total_matching=0, returned=0, has_more=False,
                     next_offset=None, items=[], coverage="%s has not been run in this case." % approach,
                     limitation="Run it from the phone analyses screen; until then there is nothing to read.")
    lim = _limit(limit)
    res = F.results(conn, case_id, run.id, kind=kind, strength=strength, start=_iso(_instant(start)),
                    end=_iso(_instant(end, end=True)), phone=ext, offset=max(0, int(offset or 0)), limit=lim)
    # every strength under the same filter, so weak and faint results are counted, never silently left out
    where, fp = F._filters(case_id, run.id, kind, None, _iso(_instant(start)), _iso(_instant(end, end=True)), ext)
    by_strength = {str(r[0]): int(r[1]) for r in conn.execute(text(
        "SELECT r.strength, count(*) FROM phone_analysis_results r WHERE %s GROUP BY 1 ORDER BY 1" % where), fp)}
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
                 items=items, kinds=list(getattr(module, "KINDS", ())), by_strength=by_strength,
                 coverage_notes=list(cov.get("notes") or []),
                 strength_rule=getattr(module, "RULE_OF_THUMB", None),
                 coverage="%s%s, last completed run: %d results%s%s. %s%s" % (
                     (_not_current_words(approach, run) + " ") if stale else "",
                     approach, res["total"], (" of kind %s" % kind) if kind else "",
                     (" of strength %s" % strength) if strength else "", cov.get("sentence") or "",
                     (" " + " ".join(cov.get("notes") or [])) if cov.get("notes") else ""),
                 limitation=("Only %d of %d are in this result; read on with offset %d." % (len(items), res["total"], nxt))
                 if nxt is not None else None,
                 note="Each result is a lead for enquiry with what supports and what undercuts it; the analysis "
                      "reports numbers, never who did what.")


def near_identical_pictures(conn, case_id, *, strength=None, offset=0, limit=DEFAULT_LIMIT) -> dict:
    """Approach 8's perceptual tier (05 11.3 step 3): pictures that look nearly the same on two phones although the
    files differ, every pair graded strong to faint with its reasons, the exact total and the counts by strength.
    A pair cites the messages that carried each picture (rec://) and the files by id."""
    from services.phone import media_spread as S
    tool = "near_identical_pictures"
    lim, off = _limit(limit), max(0, int(offset or 0))
    page = S.perceptual(conn, case_id, strength, off, lim)
    items = []
    for it in page["items"]:
        recs = []
        for side in ("a", "b"):
            for m in it[side]["messages"]:
                recs.append({"rec": _rec(m["message_record_uid"]), "role": "%s on %s" % (m["role"],
                                                                                   it[side]["phone_label"])})
        items.append({"strength": it["level"], "distance_bits": it["distance"], "reasons": it["reasons"],
                      "label": it["label"],
                      "pictures": [{"phone": it[s_]["phone_label"], "file_uid": it[s_]["file_uid"],
                                    "filename": it[s_]["filename"], "roles": it[s_]["roles"],
                                    "copies_on_phone": it[s_]["copies_on_phone"],
                                    "open": "/cases/%s/phones/%s/records/media/spread?file=%s" % (
                                        case_id, it[s_]["extraction_id"], it[s_]["file_uid"])} for s_ in ("a", "b")],
                      "records": recs})
    nxt = off + len(items) if off + len(items) < page["total"] else None
    h = page["hashing"]
    cov = h["not_hashed_words"] or ("%d of %d pictures compared, %d waiting, %d could not be read." % (
        h["hashed"], h["pictures"], h["waiting"], h["failed"]))
    return _base(tool, case_id, total_matching=page["total"], returned=len(items), has_more=nxt is not None,
                 next_offset=nxt, offset=off, items=items, by_strength=page["by_strength"],
                 total_all_strengths=page["total_all"], strength_rule=page["rule_words"],
                 coverage="Near-identical pictures: %d pairs%s. %s" % (
                     page["total"], (" of strength %s" % strength) if strength else "", cov),
                 limitation=" ".join(x for x in (
                     ("Only %d of %d are in this result; read on with offset %d." % (len(items), page["total"], nxt))
                     if nxt is not None else None, page["stopped_words"]) if x) or None,
                 note="A near-identical picture is a lead for enquiry, not proof of the same file; identical files "
                      "are the exact tier (media spread) and are not listed here.")


# ---- connection 3: who had the means to operate an account ----------------------------------------------------------

OTP_SQL = r"(one[- ]?time|passcode|pass code|verification code|security code|confirmation code|\motp\M|\mcode\M)"
# a code of 4 to 8 digits, whole or split in two by a space or a dash ("482913", "482 913", "482-913")
OTP_DIGITS = __import__("re").compile(r"(?<!\d)(?:\d{4,8}|\d{3,4}[ -]\d{3,4})(?!\d)")
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
    """Every digit masked: a code can be split ("482 913", "482-913"), so no run of digits is left readable."""
    return "".join("•" if ch.isdigit() else ch for ch in (s or ""))


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
    sigs = {s["record_uid"]: s for s in MS.read_signals(conn, case_id, record_uids=list(uids))}
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
                    "quote": _mask_codes(body)[:300], "quote_clipped": len(body) > 300,
                    "quote_words": "Digits masked%s; read the record by its rec:// link." % (
                        ", and cut at 300 characters" if len(body) > 300 else ""),
                    "strength": "supporting",
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


def _count_between(conn, case_id, sa, sb) -> int:
    """Messages, calls and emails between two sides at any time, counted as ``edge_records`` counts them; the
    communication half of ``link_edges.edges``, without its money."""
    from services.phone import link_edges
    a, b = (link_edges.resolve_side(conn, case_id, s) for s in (sa, sb))
    c = link_edges.communication(conn, case_id, a["keys"], b["keys"])
    return sum(link_edges.comm_total(c, p) for p in ("messages", "calls", "emails"))


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
        if t.superseded_by_id or t.ledger_status != "admitted":
            return _base(tool, case_id, available=False, payment=row, total_matching=0, returned=0, has_more=False,
                         next_offset=None, items=[],
                         reason=("This row was corrected; its correction is txn://%s. Ask about that row." %
                                 t.superseded_by_id) if t.superseded_by_id else
                         "This row is not admitted to the ledger (%s), so it is not between anyone." % t.ledger_status)
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
            n_ever = _count_between(conn, case_id, sa, sb)
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
        # the window is a stated search bound (lx-matchgrades): what it leaves out is counted, not hidden
        outside = max(0, _count_between(conn, case_id, sa, sb) - len(found))
        return _base(tool, case_id, **base, outcome=None, total_matching=len(found), returned=len(items),
                     has_more=nxt is not None, next_offset=nxt, offset=offset_, items=items,
                     outside_window=outside,
                     coverage="%d messages, %d calls and %d emails between %s and %s in the window%s." % (
                         totals["messages"], totals["calls"], totals["emails"], pa.display_name, pb.display_name,
                         ("; %d more between them are outside it (widen with hours or days, up to %d days, to read "
                          "them)" % (outside, MAX_WINDOW_DAYS)) if outside else ""),
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
    window_minutes: float = Field(5, gt=0, le=60)
    include_synced: bool = False


class PeriodArgs(SubjectArgs):
    start: str = Field(..., description="First local day, YYYY-MM-DD.")
    end: str = Field(..., description="Last local day, YYYY-MM-DD (up to 62 days after the start).")
    lanes: list[Literal["communications", "interaction", "places", "money", "device_state", "others", "passive"]] = \
        Field(default_factory=lambda: ["communications", "places", "money"])
    zone: Literal["device", "case", "UTC"] = "device"


class CompanyArgs(SubjectArgs):
    start: str = Field(..., description="Start of the window, YYYY-MM-DD or an ISO time.")
    end: str = Field(..., description="End of the window, YYYY-MM-DD or an ISO time.")
    other_phone: str | None = Field(None, description="Compare with this phone only; leave out to compare with every "
                                    "other phone in the case.")
    other_person: str | None = Field(None, description="Compare with this person's phone only.")
    zone: Literal["device", "case", "UTC"] = "case"


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
    with_records: bool = Field(False, description="Also return the messages, calls and emails behind the counts "
                               "(up to 25 of each, oldest first, with their text). Leave off for counts and money.")


class MatchesArgs(_Page):
    outcome: Literal["corroborated", "near_amount", "several_candidates"] | None = None
    strength: Literal["strong", "moderate", "weak", "faint"] | None = Field(
        None, description="Only readings whose strongest pairing has this strength.")


class StatementArgs(_Page):
    claim_id: str = Field(..., description="The id of a statement a person confirmed on the Patterns screen.")
    limit: int = Field(MAX_LIMIT, ge=1, le=MAX_LIMIT)


class AnalysisArgs(_Page):
    approach: Literal["message_reconciliation", "deletion_timeline", "relationships", "awareness", "device_users",
                      "other_devices", "plans"]
    kind: str | None = Field(None, description=(
        "awareness: group_roles, read_events, reply_latency, read_without_reply, unread. device_users: "
        "shared_markers, complementary_use, more_than_one_user, co_location, use_while_apart. other_devices: "
        "shared_key lists every key two or more phones share."))
    strength: str | None = Field(None, description=(
        "Only results of this strength. Read, reply, unread, co-location and use-while-apart results are graded "
        "strong, moderate, weak or faint by a stated rule (other_devices and plans too); by_strength gives the "
        "count of each."))
    phone: str | None = None
    start: str | None = None
    end: str | None = None


class MonitoringArgs(_Page):
    start: str | None = Field(None, description="Hard start date (YYYY-MM-DD or ISO instant); earlier items are "
                                                   "counted in outside_dates, not listed.")
    end: str | None = Field(None, description="Hard end date.")


class NearIdenticalArgs(_Page):
    strength: Literal["strong", "moderate", "weak", "faint"] | None = None


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
    ("get_period_activity", "period_activity", PeriodArgs,
     "For: where a person or phone was and what they did over a period (several days or nights, a month): per day "
     "the count in each lane, then the items oldest first (messages and calls, places, payments by default), and for "
     "a person the documents that name them. Not for: one day (get_day_activity) or a search for words "
     "(search_case)."),
    ("get_phone_company", "phone_company", CompanyArgs,
     "For: whose phone a device was with, who was near a phone or a person over a period, and how two phones' "
     "movements compare. One phone (or person) against every other phone, or against one: per companion the graded "
     "strength (strong, moderate, weak, faint by the phone analysis's stated rule), quarter hours together and apart, "
     "the nights and days together with their dates, distances, and records cited. Computed on request, not stored. "
     "Not for: one day's activity (get_day_activity) or one exact pair of moments (get_together_apart)."),
    ("get_routine_deviations", "routine_deviations", RoutineArgs,
     "A person's or phone's routine places and the days that broke the routine, with the hours and places."),
    ("get_phone_map_summary", "phone_map_summary", MapSummaryArgs,
     "The Map's phone totals: how many location records are placed, by source, and what cannot be placed and why."),
    ("get_contact_and_money_between", "contact_and_money_between", BetweenArgs,
     "Did two people talk, and did money move between them: messages, calls and emails on every phone, and the "
     "ledger money between them (verified rows summed per currency, p3 stated apart) with each payment's txn:// "
     "link, and where each side's numbers appear on the phones. Use it for any 'between A and B' question; "
     "with_records adds the messages, calls and emails themselves, so everything between two people is one call."),
    ("get_money_signal_matches", "money_signal_matches", MatchesArgs,
     "Every phone alert or message that pairs with a ledger row at any strength (approach 1), strongest first: the "
     "alert's rec://, each candidate row's txn://, the strength (strong, moderate, weak, faint) with the reasons "
     "(how well matched, how substantiated), and whether a person confirmed or rejected it. An alert is p4 and never "
     "summed; the row keeps its class."),
    ("get_money_signal_leads", "money_signal_leads", _Page,
     "Accounts and periods the phones point to that the ledger does not hold (approach 1 leads), each with "
     "institution, masked ending, alert days, missing account or missing period, and records. Alerts are never "
     "totalled."),
    ("evaluate_statement", "statement_check", StatementArgs,
     "Check a statement a person confirmed against the phones (Patterns statement check): contradicted, "
     "contradicted_weakly, consistent, supported, mixed, insufficient_data, or no_record with its reason. Every "
     "item cited."),
    ("get_analysis_results", "analysis_results", AnalysisArgs,
     "Results of a phone analysis's last run: message_reconciliation (messages across phones: copies matched, "
     "deleted on one side), deletion_timeline, relationships, awareness (read and play times, reply times, read "
     "with no reply, unread, group roles), device_users (shared markers, use in turn, together or apart, used "
     "while apart, signs of more than one user), other_devices (WiFi networks, Bluetooth devices, accounts and web "
     "services each phone shows; kind shared_key lists every one two or more phones share) or plans (calendar "
     "entries, check-ins and notes; a placed one compared with the phone's location: consistent, inconsistent, "
     "mixed, no_data), with exact totals, the count per strength (by_strength) and records cited. List weak and "
     "faint results as such; coverage_notes give the counts they rest on. Medium and weak keys are leads, never "
     "an identity."),
    ("get_monitoring_app_indicators", "monitoring_app_indicators", MonitoringArgs,
     "Monitoring apps on the phones (installed applications checked against an editable, sourced list) beside bank "
     "control notices (new payee, changed sign-in details, new device, stopped card), in one date-ordered lane, each "
     "with its rec:// link and basis. An indicator a person weighs, never a finding of who did what."),
    ("get_glossary", "glossary_terms", _Page,
     "The code words of this case a person confirmed, labelled as a person's reading, each with every mention "
     "(rec://) and the ledger rows it joins to (txn://) within the stated window, or why it joins none."),
    ("get_near_identical_pictures", "near_identical_pictures", NearIdenticalArgs,
     "Pictures that look nearly the same on two phones although the files differ (a re-compressed forward), every "
     "pair graded strong, moderate, weak or faint with its reasons, the exact total and counts by strength, the "
     "messages that carried each copy (rec://) and how many pictures were compared. A lead, not proof of the same "
     "file."),
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


# ---- payment links ---------------------------------------------------------------------------------------------------
# Every item that names a ledger row by txn:// also carries the Financial page path the ledger tools give
# (financial_href), so the answer links a payment the way the live screens open it. Decision (agent-phones,
# 2026-11-03): reversed by agent-citations, whose release opens txn:// on the Financial page; the prompt cites txn://
# and financial_href stays for older readers (the citation check reads both).

def _with_hrefs(case_id, obj):
    if isinstance(obj, dict):
        out = {k: _with_hrefs(case_id, v) for k, v in obj.items()}
        t = out.get("txn")
        if isinstance(t, str) and t.startswith("txn://") and "financial_href" not in out:
            out["financial_href"] = "/cases/%s/financial?view=transactions&payment=%s" % (case_id, t[len("txn://"):])
        return out
    if isinstance(obj, list):
        return [_with_hrefs(case_id, v) for v in obj]
    return obj


def _hrefs(fn):
    import functools

    @functools.wraps(fn)
    def run(conn, case_id, *a, **kw):
        return _with_hrefs(case_id, fn(conn, case_id, *a, **kw))
    return run


for _name in {func for _, func, _, _ in TOOLS}:
    globals()[_name] = _hrefs(globals()[_name])
