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

