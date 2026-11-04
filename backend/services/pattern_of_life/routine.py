"""Stays, places, routine and deviations (04 section 8.3, unit U8).

Computed on read from the subject's presence observations and returned with every parameter that produced them
(04 decision 16). Places are unnamed: a cluster is a place only in the sense of "where the phone stayed".

- Stay: consecutive presence observations with a stated radius of 250 m or less, all within
  ``max(100 m, r_i + r_j)`` of the running median, spanning at least 10 minutes with at least 2 observations, and
  no two consecutive more than 2 hours apart (04 decision 26).
- Places: DBSCAN over the subject's stays (haversine, eps 150 m, at least 3 stays). A routine place has stays on at
  least 4 distinct days, or on at least 25 percent of the days with any presence data.
- Profile: 7 x 24 dwell minutes by local day of week and hour, divided by the weeks that cell was observed.
- Names (04 7.7, cb-places-rest D): a place is unnamed until a person names it, through the case decision log
  (``label_place``). The name is kept with the place's centre (``pol_place_cluster``); a recomputed place takes the
  name of the nearest named place of the case within ``eps_m`` of its centre, so a name survives new data that
  moves the centre a little. ``place_id`` is that stable identity; an unnamed place has none and is called by its
  number for this computation only.
- Deviation: per day with at least 3 hours carrying stays, the mean surprise ``-log2 p`` of the place in each hour,
  ``p`` estimated from all other weeks (Laplace, alpha 1, over places plus "elsewhere"); a day is flagged above the
  subject's own 95th percentile with at least one hour of 3 bits or more.
"""
from __future__ import annotations

import math
import statistics
import uuid
from collections import Counter, defaultdict
from datetime import timedelta, timezone

from sqlalchemy import text

from services.pattern_of_life.places import ROUTINE_KINDS, haversine_m

# Bumped when what enters places changes (2: photos taken on the phone count as presence, received ones never;
# cb-places-rest E). Echoed with every routine result and part of the projection signature, so phones built under
# an older version are rebuilt through the projection.
PLACES_VERSION = 2

PARAMS = {"stay_max_radius_m": 250.0, "stay_min_distance_m": 100.0, "stay_min_minutes": 10, "stay_min_points": 2,
          "eps_m": 150.0, "min_samples": 3, "routine_min_days": 4, "routine_min_share": 0.25,
          "stay_max_gap_minutes": 120, "deviation_min_hours": 3, "deviation_percentile": 95, "deviation_min_bits": 3.0, "laplace_alpha": 1.0}


def _median_pos(pts):
    return statistics.median(p[1] for p in pts), statistics.median(p[2] for p in pts)


def _p90(vals):
    vals = sorted(vals)
    if not vals:
        return 0.0
    return vals[min(len(vals) - 1, int(math.ceil(0.9 * len(vals))) - 1)]


def presence(conn, extraction_ids):
    """[(start, lat, lon, radius, extraction_id, end)] eligible for stays, in time order."""
    return [tuple(r) for r in conn.execute(text(
        "SELECT start_utc, lat, lon, radius_m, extraction_id, end_utc FROM pol_place_observation WHERE "
        "extraction_id = ANY(CAST(:e AS uuid[])) AND kind = ANY(:k) AND radius_m IS NOT NULL AND radius_m <= :r "
        "ORDER BY start_utc, id"), {"e": [str(x) for x in extraction_ids], "k": list(ROUTINE_KINDS),
                                    "r": PARAMS["stay_max_radius_m"]})]


def stays_of(points, params=PARAMS):
    """Stays from one phone's ordered points. Exact: every point of a candidate is within the limit of the running
    median. A full check runs only when a bound (the last checked maximum distance plus how far the median has moved
    since) could exceed the limit, so a long stationary run costs O(n log n), not O(n^2)."""
    import bisect
    out = []
    i, n = 0, len(points)
    min_dur = timedelta(minutes=params["stay_min_minutes"])
    max_gap = timedelta(minutes=params["stay_max_gap_minutes"])
    while i < n:
        lats, lons = [points[i][1]], [points[i][2]]
        mlat, mlon = points[i][1], points[i][2]
        maxd, moved = 0.0, 0.0
        j = i
        while j + 1 < n:
            q = points[j + 1]
            if q[0] - points[j][0] > max_gap:  # no fix for over 2 hours: whereabouts unknown, the stay ends (8.3)
                break
            bisect.insort(lats, q[1])
            bisect.insort(lons, q[2])
            nlat, nlon = _med(lats), _med(lons)
            moved += haversine_m(mlat, mlon, nlat, nlon)
            d_lim = max(params["stay_min_distance_m"], points[i][3] + q[3])
            dq = haversine_m(nlat, nlon, q[1], q[2])
            ok = dq <= d_lim
            if ok and maxd + moved > d_lim:
                maxd = max(haversine_m(nlat, nlon, p[1], p[2]) for p in points[i:j + 2])
                moved = 0.0
                ok = maxd <= d_lim
            else:
                maxd = max(maxd, dq)
            if not ok:
                lats.remove(q[1])
                lons.remove(q[2])
                break
            mlat, mlon = nlat, nlon
            j += 1
        span = points[i:j + 1]
        if j > i and len(span) >= params["stay_min_points"] and points[j][0] - points[i][0] >= min_dur:
            mlat, mlon = _median_pos(span)
            dists = [haversine_m(mlat, mlon, p[1], p[2]) for p in span]
            out.append({"lat": mlat, "lon": mlon, "radius_m": max(_p90(dists), statistics.median(p[3] for p in span)),
                        "start": points[i][0], "end": max(p[5] or p[0] for p in span), "observations": len(span),
                        "extraction_id": str(points[i][4])})
            i = j + 1
        else:
            i += 1
    return out


def _med(sorted_vals):
    m = len(sorted_vals)
    return sorted_vals[m // 2] if m % 2 else (sorted_vals[m // 2 - 1] + sorted_vals[m // 2]) / 2.0


def dbscan(stays, eps, min_samples):
    """Cluster labels (-1 noise) over stays, haversine distance, with a grid to bound comparisons."""
    n = len(stays)
    cell = eps / 111320.0
    grid = defaultdict(list)
    for k, s in enumerate(stays):
        grid[(int(s["lat"] // cell), int(s["lon"] // (cell / max(0.1, math.cos(math.radians(s["lat"]))))))].append(k)

    def neighbours(k):
        s = stays[k]
        gy = int(s["lat"] // cell)
        gx = int(s["lon"] // (cell / max(0.1, math.cos(math.radians(s["lat"])))))
        out = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for m in grid.get((gy + dy, gx + dx), ()):
                    if haversine_m(s["lat"], s["lon"], stays[m]["lat"], stays[m]["lon"]) <= eps:
                        out.append(m)
        return out
    labels = [None] * n
    c = -1
    for k in range(n):
        if labels[k] is not None:
            continue
        nb = neighbours(k)
        if len(nb) < min_samples:
            labels[k] = -1
            continue
        c += 1
        labels[k] = c
        queue = [m for m in nb if m != k]
        while queue:
            m = queue.pop()
            if labels[m] == -1:
                labels[m] = c
            if labels[m] is not None:
                continue
            labels[m] = c
            nb2 = neighbours(m)
            if len(nb2) >= min_samples:
                queue.extend(x for x in nb2 if labels[x] is None or labels[x] == -1)
    return labels


def _hours_split(start, end, zone):
    """[(local datetime of hour start, minutes)] for an interval."""
    out = []
    t = start
    while t < end:
        loc = t.astimezone(zone)
        h0 = loc.replace(minute=0, second=0, microsecond=0)
        nxt = (h0 + timedelta(hours=1)).astimezone(timezone.utc)
        e = min(end, nxt)
        out.append((h0, (e - t).total_seconds() / 60.0))
        t = e
    return out


class PlaceError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def named_places(conn, case_id) -> list:
    if case_id is None:
        return []
    return [dict(r._mapping) for r in conn.execute(text(
        "SELECT id, lat, lon, radius_m, label, label_decision_id, label_by_name, subject_key FROM pol_place_cluster "
        "WHERE case_id = :c ORDER BY created_at, id"), {"c": str(case_id)})]


def attach_names(places, named, eps_m):
    """Give each computed place the nearest named place within ``eps_m`` of its centre; a named place goes to one
    computed place only (the nearest), so two places never share one name."""
    pairs = sorted((haversine_m(p["lat"], p["lon"], n["lat"], n["lon"]), i, j)
                   for i, p in enumerate(places) for j, n in enumerate(named))
    used_p, used_n = set(), set()
    for d, i, j in pairs:
        if d > eps_m or i in used_p or j in used_n:
            continue
        used_p.add(i)
        used_n.add(j)
        n = named[j]
        places[i].update({"place_id": str(n["id"]), "label": n["label"], "label_decision_id":
                          str(n["label_decision_id"]) if n["label_decision_id"] else None,
                          "label_by": n["label_by_name"]})
    for p in places:
        p.setdefault("place_id", None)
        p.setdefault("label_decision_id", None)
        p.setdefault("label_by", None)
    return places


def place_words(place) -> str:
    """How a place is called in a sentence: its name, else its number in this computation."""
    if place is None:
        return "no usual place"
    return place.get("label") or "place %s" % (place["cluster_id"] + 1)


def compute(conn, extraction_ids, zone, params=PARAMS, case_id=None) -> dict:
    pts = presence(conn, extraction_ids)
    by_phone = defaultdict(list)
    for p in pts:
        by_phone[str(p[4])].append(p)
    stays = []
    for e in sorted(by_phone):
        stays += stays_of(by_phone[e], params)
    stays.sort(key=lambda s: s["start"])
    labels = dbscan(stays, params["eps_m"], params["min_samples"])
    presence_days = {p[0].astimezone(zone).date() for p in pts}
    clusters = {}
    for s, lab in zip(stays, labels):
        s["cluster"] = lab if lab is not None and lab >= 0 else None
        if s["cluster"] is not None:
            clusters.setdefault(lab, []).append(s)
    places = []
    for lab, ss in sorted(clusters.items()):
        clat = statistics.mean(s["lat"] for s in ss)
        clon = statistics.mean(s["lon"] for s in ss)
        days = {s["start"].astimezone(zone).date() for s in ss}
        radius = _p90([haversine_m(clat, clon, s["lat"], s["lon"]) for s in ss]) + \
            statistics.median(s["radius_m"] for s in ss)
        routine = len(days) >= params["routine_min_days"] or (
            presence_days and len(days) / len(presence_days) >= params["routine_min_share"])
        places.append({"cluster_id": lab, "lat": clat, "lon": clon, "radius_m": radius, "stay_count": len(ss),
                       "day_count": len(days), "routine": bool(routine), "label": None,
                       "first_utc": min(s["start"] for s in ss), "last_utc": max(s["end"] for s in ss)})
    attach_names(places, named_places(conn, case_id), params["eps_m"])
    # observed (local date, hour) cells and weeks
    observed = defaultdict(set)  # (dow, hour) -> set of iso weeks
    for p in pts:
        loc = p[0].astimezone(zone)
        observed[(loc.weekday(), loc.hour)].add(loc.isocalendar()[:2])
    for pl in places:
        prof = [[0.0] * 24 for _ in range(7)]
        for s in clusters[pl["cluster_id"]]:
            for h0, mins in _hours_split(s["start"], s["end"], zone):
                prof[h0.weekday()][h0.hour] += mins
        pl["profile"] = [[round(prof[d][h] / len(observed[(d, h)]), 1) if observed[(d, h)] else None
                          for h in range(24)] for d in range(7)]
    return {"parameters": dict(params, places_version=PLACES_VERSION), "zone": str(zone), "stays": stays,
            "places": places,
            "routine_places": [p["cluster_id"] for p in places if p["routine"]],
            "presence_days": len(presence_days), "observations_used": len(pts)}


def deviations(result, zone, start_date=None, end_date=None, params=PARAMS) -> dict:
    """Flag days whose places break the routine (8.3 Deviation)."""
    routine = set(result["routine_places"])
    by_id = {p["cluster_id"]: p for p in result.get("places", [])}
    hour_label = {}  # (local date, hour) -> (label, minutes, stay)
    for s in result["stays"]:
        lab = s["cluster"] if s["cluster"] in routine else "elsewhere"
        for h0, mins in _hours_split(s["start"], s["end"], zone):
            key = (h0.date(), h0.hour)
            if key not in hour_label or mins > hour_label[key][1]:
                hour_label[key] = (lab, mins, s)
    labels_k = len(routine) + 1
    by_slot = defaultdict(Counter)  # (dow, hour) -> Counter of (week, label)
    for (d, h), (lab, _, _) in hour_label.items():
        by_slot[(d.weekday(), h)][(d.isocalendar()[:2], lab)] += 1
    days = defaultdict(list)
    for (d, h), v in hour_label.items():
        days[d].append((h, v))
    scored = []
    for d, hours in sorted(days.items()):
        if len(hours) < params["deviation_min_hours"]:
            continue
        week = d.isocalendar()[:2]
        detail = []
        for h, (lab, mins, s) in sorted(hours):
            others = Counter()
            for (wk, l2), n in by_slot[(d.weekday(), h)].items():
                if wk != week:
                    others[l2] += n
            total = sum(others.values())
            p = (others[lab] + params["laplace_alpha"]) / (total + params["laplace_alpha"] * labels_k)
            expected = others.most_common(1)[0][0] if others else None
            detail.append({"hour": h, "place": lab, "surprise_bits": -math.log2(p), "expected_place": expected,
                           "stay": {k: s[k] for k in ("lat", "lon", "radius_m", "start", "end", "observations",
                                                      "extraction_id")}})
        score = statistics.mean(x["surprise_bits"] for x in detail)
        scored.append((d, score, detail))
    if not scored:
        return {"parameters": dict(params), "threshold": None, "days_scored": 0, "flagged": []}
    all_scores = sorted(s for _, s, _ in scored)
    k = (len(all_scores) - 1) * params["deviation_percentile"] / 100.0
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    thr = all_scores[lo] + (all_scores[hi] - all_scores[lo]) * (k - lo)
    flagged = []
    for d, score, detail in scored:
        if (start_date and d < start_date) or (end_date and d > end_date):
            continue
        hot = [x for x in detail if x["surprise_bits"] >= params["deviation_min_bits"]]
        if score > thr and hot:
            flagged.append({"date": d.isoformat(), "score_bits": round(score, 3), "hours": hot,
                            "expectation": _expectation(d, hot, by_id)})
    return {"parameters": dict(params), "threshold": round(thr, 3), "days_scored": len(scored), "flagged": flagged}


def _expectation(d, hot, by_id=None):
    """The routine the day broke, in words: "Usually at home on Tuesdays 21:00 to 00:00." Consecutive hours are one
    span; a span's place is its usual place in that hour (named, else numbered)."""
    by_id = by_id or {}

    def name(n):
        if n is None:
            return "no usual place"
        if n == "elsewhere":
            return "elsewhere"
        return place_words(by_id.get(n, {"cluster_id": n}))
    spans = []
    for x in sorted(hot, key=lambda x: x["hour"]):
        w = name(x["expected_place"])
        if spans and spans[-1][0] == w and spans[-1][2] == x["hour"]:
            spans[-1][2] = x["hour"] + 1
        else:
            spans.append([w, x["hour"], x["hour"] + 1])
    day = d.strftime("%A")
    parts = ["at %s on %ss %02d:00 to %02d:00" % (w, day, a, b % 24) for w, a, b in spans]
    return "Usually " + "; ".join(parts) + "."


def name_place(session, case_id, *, subject_key, cluster, label, reason, actor) -> dict:
    """A person names a computed place, or renames or clears a named one, as a case decision (04 7.7). ``cluster``
    is the place as computed on the server just now (the route recomputes it; a client's centre is never trusted)."""
    from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
    from postgres.models.pattern_places import PolPlaceCluster
    from services import manual_changes
    from services.financial import decisions
    label = " ".join((label or "").split()) or None
    if label is not None and len(label) > 200:
        raise PlaceError("A place name is at most 200 characters.")
    if not isinstance(reason, str) or not reason.strip():
        raise PlaceError("Say why the place has this name.")
    row = session.get(PolPlaceCluster, uuid.UUID(cluster["place_id"])) if cluster.get("place_id") else None
    if row is None:
        if label is None:
            raise PlaceError("The place has no name to clear.", 409)
        row = PolPlaceCluster(id=uuid.uuid4(), case_id=uuid.UUID(str(case_id)), subject_key=subject_key[:80],
                              lat=cluster["lat"], lon=cluster["lon"], radius_m=cluster["radius_m"],
                              stay_count=cluster["stay_count"], day_count=cluster["day_count"])
        session.add(row)
        session.flush()
        before = None
    else:
        before = row.label
        if before == label:
            raise PlaceError("The place already has that name.", 409)
    ev = decisions.record(session, case_id=row.case_id, subject=row, subject_type=AdjudicationSubject.place_cluster,
                          decision=AdjudicationDecision.label_place, reason=reason.strip(), actor=actor,
                          before={"label": before, "lat": "%.7f" % row.lat, "lon": "%.7f" % row.lon},
                          after={"label": label, "lat": "%.7f" % row.lat, "lon": "%.7f" % row.lon})
    session.execute(text(
        "UPDATE pol_place_cluster SET label = :l, label_decision_id = :d, label_by_name = :n, stay_count = :sc, "
        "day_count = :dc, profile = CAST(:pr AS jsonb), computed_with = CAST(:cw AS jsonb), updated_at = now() "
        "WHERE id = :i"), {"l": label, "d": ev.id, "n": actor.name, "sc": cluster["stay_count"],
                           "dc": cluster["day_count"], "pr": _json(cluster.get("profile")),
                           "cw": _json(cluster.get("computed_with") or {}), "i": row.id})
    manual_changes.record_change(session, "pattern_place_name", case_id, {"type": "place_cluster", "id": str(row.id)},
                                 {"label": before}, {"label": label}, actor, reason.strip(),
                                 link="/cases/%s/phone-patterns?view=places" % case_id,
                                 pattern_key=manual_changes.make_pattern_key("pattern_place_name", "label",
                                                                             "routine", "dbscan"), source="phone")
    return {"place_id": str(row.id), "decision_id": str(ev.id), "label": label, "previous_label": before}


def _json(v):
    import json
    return json.dumps(v, default=str)
