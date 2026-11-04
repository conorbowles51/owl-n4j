"""The Case Map phone layer (03 section 13): phone positions from ``pv_location_point``, never through
``/api/graph/locations`` (phone points are not graph locations, G-4).

- ``summary``: how many location records are in scope, how many can be drawn, and what cannot be placed and why
  (``not_positionable``). Cell tower and WiFi records without a position are counted here and never sent to a
  lookup service (G-3): nothing in this module makes a network request.
- ``points``: the positions in a viewport. At most ``MAP_POINTS_MAX`` points are returned one by one; above that
  they are returned as clusters on a grid whose counts are exact and sum to the viewport's total, with a
  ``limits`` entry saying so (G-1).
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import text

from services.phone import time_display as T

MAP_POINTS_MAX = 5_000
# record types that describe a place but may carry no coordinates, and the words for them (03 13.2)
NOT_POSITIONABLE = {
    "CellTower": "Cell tower records without a position: the production gives tower identifiers only",
    "WirelessNetwork": "WiFi networks without a position: the production gives network names only",
    "Location": "Location records with no coordinates",
}
SOURCE_WORDS = {"device_location": "Location services", "wifi": "WiFi network", "cell": "Cell tower",
                "media": "Photo or video", "app": "App record"}


def _where(f: dict, p: dict) -> str:
    w = ["t.case_id = :c", "t.lat IS NOT NULL", "t.lon IS NOT NULL"]
    if f.get("phones"):
        w.append("t.extraction_id::text = ANY(:phones)")
        p["phones"] = [str(x) for x in f["phones"]]
    if f.get("source_kinds"):
        w.append("t.source_kind = ANY(:kinds)")
        p["kinds"] = list(f["source_kinds"])
    if f.get("affiliations"):
        w.append("coalesce(t.affiliation, '') = ANY(:aff)")
        p["aff"] = list(f["affiliations"])
    time = []
    if f.get("from_instant"):
        time.append("t.instant >= CAST(:fi AS timestamptz)")
        p["fi"] = f["from_instant"]
    if f.get("to_instant"):
        time.append("t.instant <= CAST(:ti AS timestamptz)")
        p["ti"] = f["to_instant"]
    if time:
        cond = " AND ".join(time)
        w.append("(%s%s)" % (cond, " OR t.instant IS NULL" if f.get("include_no_time", True) else ""))
    elif not f.get("include_no_time", True):
        w.append("t.instant IS NOT NULL")
    return " AND ".join(w)


def summary(conn, case_id, f: dict | None = None) -> dict:
    f, p = dict(f or {}), {"c": str(case_id)}
    where = _where(f, p)
    row = conn.execute(text(
        "SELECT count(*) AS n, min(t.lon) AS w, min(t.lat) AS s, max(t.lon) AS e, max(t.lat) AS nn "
        "FROM pv_location_point t WHERE " + where), p).first()
    by_source = {r.k or "unknown": int(r.n) for r in conn.execute(text(
        "SELECT t.source_kind AS k, count(*) AS n FROM pv_location_point t WHERE %s GROUP BY 1 ORDER BY 1" % where), p)}
    pp = {"c": str(case_id), "models": list(NOT_POSITIONABLE)}
    phone_cond = ""
    if f.get("phones"):
        phone_cond, pp["phones"] = " AND r.extraction_id::text = ANY(:phones)", [str(x) for x in f["phones"]]
    rows = conn.execute(text(
        "SELECT r.model_type, count(*) AS n, count(DISTINCT r.extraction_id) AS phones FROM phone_record_summaries r "
        "JOIN phone_interpretation_state st ON st.extraction_id = r.extraction_id AND st.generation = r.generation "
        "JOIN phone_extractions e ON e.id = r.extraction_id AND e.standing = 'active' WHERE "
        "r.case_id = :c AND r.model_type = ANY(:models) AND NOT r.has_point" + phone_cond +
        " GROUP BY 1 ORDER BY 1"), pp).fetchall()
    missing = [{"reason": NOT_POSITIONABLE[r.model_type], "model_type": r.model_type, "count": int(r.n),
                "phones": int(r.phones)} for r in rows]
    positioned = int(row.n or 0)
    return {"case_id": str(case_id), "positioned": positioned,
            "total": positioned + sum(m["count"] for m in missing), "not_positionable": missing,
            "by_source": by_source,
            "bbox": [row.w, row.s, row.e, row.nn] if positioned else None}


def _grid(zoom: float) -> float:
    """Cell size in degrees for a zoom level: about 60 screen pixels per cell."""
    return 360.0 / (2 ** max(0.0, min(22.0, float(zoom)))) / 256.0 * 60.0


def points(conn, case_id, bbox, zoom, f: dict | None = None, zone: str | None = None) -> dict:
    w_, s_, e_, n_ = (float(v) for v in bbox)
    f, p = dict(f or {}), {"c": str(case_id), "w": w_, "s": s_, "e": e_, "n": n_}
    where = _where(f, p) + " AND t.lat BETWEEN :s AND :n AND " + (
        "t.lon BETWEEN :w AND :e" if w_ <= e_ else "(t.lon >= :w OR t.lon <= :e)")
    total = int(conn.execute(text("SELECT count(*) FROM pv_location_point t WHERE " + where), p).scalar() or 0)
    if total <= MAP_POINTS_MAX:
        from services.phone.readings import phone_labels
        labels = phone_labels(conn, case_id)
        zones = {str(r[0]): r[1] for r in conn.execute(text(
            "SELECT extraction_id, device_zone FROM pv_extraction WHERE case_id = :c"), {"c": str(case_id)})}
        items = []
        for r in conn.execute(text(
                "SELECT t.point_uid, t.record_uid, t.extraction_id, t.lat, t.lon, t.accuracy_m, t.accuracy_basis, "
                "t.source_kind, t.affiliation, t.instant, t.model_type, t.flags, t.deleted_state FROM "
                "pv_location_point t WHERE " + where + " ORDER BY t.instant NULLS LAST, t.point_uid"), p):
            ext = str(r.extraction_id)
            z = zone or zones.get(ext) or "UTC"
            items.append({
                "type": "point", "point_uid": str(r.point_uid), "record_uid": str(r.record_uid),
                "extraction_id": ext, "phone_label": labels.get(ext, "A phone"), "lat": r.lat, "lon": r.lon,
                "accuracy_m": float(r.accuracy_m) if r.accuracy_m is not None else None,
                "accuracy_basis": r.accuracy_basis,
                "accuracy_words": ("Within %s m" % "{:,}".format(round(float(r.accuracy_m))))
                if r.accuracy_m is not None else "Accuracy not recorded",
                "source_kind": r.source_kind, "source_words": SOURCE_WORDS.get(r.source_kind or "", r.source_kind or
                                                                               "Unknown source"),
                "affiliation": r.affiliation, "instant": T.iso(r.instant),
                "time": T.time_block(r.instant, z) if r.instant is not None else None,
                "model_type": r.model_type, "flags": list(r.flags or []), "deleted_state": r.deleted_state})
        return {"case_id": str(case_id), "total": total, "clustered": False, "items": items, "limits": []}
    size = _grid(zoom)
    p["g"] = size
    items = [{"type": "cluster", "lat": float(r.lat), "lon": float(r.lon), "count": int(r.n),
              "bbox": [float(r.w), float(r.s), float(r.e), float(r.nn)]}
             for r in conn.execute(text(
                 "SELECT avg(t.lat) AS lat, avg(t.lon) AS lon, count(*) AS n, min(t.lon) AS w, min(t.lat) AS s, "
                 "max(t.lon) AS e, max(t.lat) AS nn FROM pv_location_point t WHERE " + where +
                 " GROUP BY floor(t.lat / :g), floor(t.lon / :g) ORDER BY 3 DESC"), p)]
    return {"case_id": str(case_id), "total": total, "clustered": True, "items": items,
            "limits": [{"kind": "clustered", "shown": len(items), "total": total,
                        "message": "%s positions in this view are grouped into %s clusters; zoom in to see each one."
                        % ("{:,}".format(total), "{:,}".format(len(items)))}]}



NEAR_WINDOW_S = 3600


def gap_words(seconds: float) -> str:
    """A time gap in words: "3 h 12 min", "45 min", "less than a minute", "2 days 4 h"."""
    s = int(abs(seconds))
    if s < 60:
        return "less than a minute"
    d, rem = divmod(s, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    parts = []
    if d:
        parts.append("%s %s" % ("{:,}".format(d), "day" if d == 1 else "days"))
    if h:
        parts.append("%d h" % h)
    if m and not d:
        parts.append("%d min" % m)
    return " ".join(parts) or "%d h" % h


def near_record(conn, case_id, record_uid, window_s: int = NEAR_WINDOW_S) -> dict | None:
    """Show on Map from a message (03 section 3.6 item 7): the positioned records on the same phone within
    ``window_s`` of the message's time, all of them (the map layer draws them under the same 5,000-point rule).
    When there are none, the nearest positioned record on that phone and how far it is in time. None when the
    record is not a message, call or other dated communication in this case."""
    ev = conn.execute(text(
        "SELECT extraction_id, sort_instant FROM pv_comm_event WHERE case_id = :c AND record_uid = CAST(:u AS uuid) "
        "ORDER BY sort_instant NULLS LAST, event_uid LIMIT 1"), {"c": str(case_id), "u": str(record_uid)}).first()
    if ev is None:
        return None
    ext = str(ev.extraction_id)
    out = {"record_uid": str(record_uid), "extraction_id": ext, "instant": T.iso(ev.sort_instant),
           "window_minutes": window_s // 60, "within": 0, "from_instant": None, "to_instant": None, "bbox": None,
           "nearest": None}
    if ev.sort_instant is None:
        out["words"] = "This message has no time, so no positions can be matched to it by time."
        return out
    p = {"c": str(case_id), "e": ext, "t": ev.sort_instant, "w": window_s}
    row = conn.execute(text(
        "SELECT count(*) AS n, min(lon) AS w, min(lat) AS s, max(lon) AS e, max(lat) AS nn, "
        "min(instant) AS lo, max(instant) AS hi FROM pv_location_point WHERE case_id = :c AND extraction_id = "
        "CAST(:e AS uuid) AND lat IS NOT NULL AND lon IS NOT NULL AND instant BETWEEN "
        "CAST(:t AS timestamptz) - make_interval(secs => :w) AND CAST(:t AS timestamptz) + make_interval(secs => :w)"),
        p).first()
    n = int(row.n or 0)
    out["from_instant"] = T.iso(ev.sort_instant - timedelta(seconds=window_s))
    out["to_instant"] = T.iso(ev.sort_instant + timedelta(seconds=window_s))
    if n:
        out.update(within=n, bbox=[row.w, row.s, row.e, row.nn])
        out["words"] = "%s positioned %s on the same phone within 1 hour of this message." % (
            "{:,}".format(n), "record" if n == 1 else "records")
        return out
    near = conn.execute(text(
        "SELECT point_uid, lat, lon, instant, extract(epoch FROM instant - CAST(:t AS timestamptz)) AS gap FROM "
        "pv_location_point WHERE case_id = :c AND extraction_id = CAST(:e AS uuid) AND lat IS NOT NULL AND lon IS "
        "NOT NULL AND instant IS NOT NULL ORDER BY abs(extract(epoch FROM instant - CAST(:t AS timestamptz))), "
        "point_uid LIMIT 1"), p).first()
    if near is None:
        out["words"] = "No positioned records within 1 hour of this message. This phone has no positioned records with a time."
        return out
    gap = float(near.gap)
    when = "%s %s" % (gap_words(gap), "earlier" if gap < 0 else "later")
    out["nearest"] = {"point_uid": str(near.point_uid), "lat": float(near.lat), "lon": float(near.lon),
                      "instant": T.iso(near.instant), "gap_seconds": gap, "gap_words": when}
    out["words"] = "No positioned records within 1 hour of this message. The nearest is %s." % when
    return out


# ---- area selection (03 13.3, 07 J-10 and XF-6) ---------------------------------------------------------------------

AREA_MAX_VERTICES = 500


def _inside(lon, lat, ring) -> bool:
    """Ray casting: is (lon, lat) inside the closed ring [[lon, lat], ...]? A point on an edge counts as inside."""
    hit = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > lat) != (y2 > lat):
            x = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if x == lon:
                return True
            if x > lon:
                hit = not hit
        elif y1 == y2 == lat and min(x1, x2) <= lon <= max(x1, x2):
            return True
    return hit


def area(conn, case_id, ring, f: dict | None = None) -> dict:
    """The phones with at least one position inside a drawn area (and the map's filters and window), each with its
    exact count of positions there and their first and last time. Every phone and every position is counted: no
    cap. ``ring`` is [[lon, lat], ...] (closed or not)."""
    pts = [(float(x), float(y)) for x, y in ring]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        raise ValueError("An area needs at least three corners.")
    if len(pts) > AREA_MAX_VERTICES:
        raise ValueError("An area has at most %d corners; this one has %d." % (AREA_MAX_VERTICES, len(pts)))
    if not all(-180 <= x <= 180 and -90 <= y <= 90 for x, y in pts):
        raise ValueError("The area is not on the map.")
    f, p = dict(f or {}), {"c": str(case_id)}
    p.update({"w": min(x for x, _ in pts), "e": max(x for x, _ in pts), "s": min(y for _, y in pts),
              "n": max(y for _, y in pts)})
    where = _where(f, p) + " AND t.lat BETWEEN :s AND :n AND t.lon BETWEEN :w AND :e"
    from services.pattern_of_life.places import PLACE_LABEL_WORDS
    from services.phone.readings import phone_labels
    labels = phone_labels(conn, case_id)
    per = {}
    no_time = 0
    for r in conn.execute(text("SELECT t.extraction_id, t.lat, t.lon, t.instant FROM pv_location_point t WHERE " +
                               where).execution_options(stream_results=True, yield_per=5000), p):
        if not _inside(r.lon, r.lat, pts):
            continue
        ext = str(r.extraction_id)
        d = per.setdefault(ext, {"extraction_id": ext, "phone_label": labels.get(ext, "A phone"), "points": 0,
                                 "points_without_time": 0, "first": None, "last": None})
        d["points"] += 1
        if r.instant is None:
            d["points_without_time"] += 1
            no_time += 1
            continue
        d["first"] = r.instant if d["first"] is None or r.instant < d["first"] else d["first"]
        d["last"] = r.instant if d["last"] is None or r.instant > d["last"] else d["last"]
    phones = sorted(per.values(), key=lambda d: (-d["points"], d["phone_label"]))
    for d in phones:
        d["first"], d["last"] = T.iso(d["first"]), T.iso(d["last"])
    return {"case_id": str(case_id), "phones": phones, "phones_total": len(phones),
            "points_total": sum(d["points"] for d in phones), "points_without_time": no_time,
            "window": {"from_instant": f.get("from_instant"), "to_instant": f.get("to_instant")},
            "label": PLACE_LABEL_WORDS}
