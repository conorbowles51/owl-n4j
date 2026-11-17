"""A drawn Map area read as a selection (lx-corroselect C): every phone position, photo and place inside it.

Each point is tested on its own position (the same ray test as the Map's "phones seen in this area"), so points a
cluster draws as one marker are all counted. The result is one member per phone record with a position inside, one
per graph place inside, and the counts by kind, with the phones they come from. Positions are read in full: a result
over the group limit is refused with its number, never trimmed.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from services import case_selections
from services.phone.map import AREA_MAX_VERTICES, _inside

MODEL_WORDS = {"Image": "photos", "Photo": "photos", "Video": "videos"}


def _ring(raw: list[list[float]]) -> list[tuple[float, float]]:
    pts = [(float(x), float(y)) for x, y in raw]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        raise ValueError("An area needs at least three corners.")
    if len(pts) > AREA_MAX_VERTICES:
        raise ValueError(f"An area has at most {AREA_MAX_VERTICES} corners; this one has {len(pts)}.")
    if not all(-180 <= x <= 180 and -90 <= y <= 90 for x, y in pts):
        raise ValueError("The area is not on the map.")
    return pts


def inside_any(lon: float, lat: float, rings: list[list[tuple[float, float]]]) -> bool:
    return any(_inside(lon, lat, r) for r in rings)


def graph_places(case_id: str, bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    from services.neo4j.driver import active_node_predicate, driver
    w, s, e, n = bbox
    with driver.session() as session:
        rows = session.run(
            f"MATCH (n) WHERE {active_node_predicate('n')} AND n.latitude IS NOT NULL AND n.longitude IS NOT NULL "
            "AND n.latitude >= $s AND n.latitude <= $n AND n.longitude >= $w AND n.longitude <= $e "
            "RETURN n.key AS key, n.name AS name, n.latitude AS lat, n.longitude AS lon",
            case_id=str(case_id), s=s, n=n, w=w, e=e)
        return [{"key": r["key"], "name": r["name"], "lat": float(r["lat"]), "lon": float(r["lon"])} for r in rows]


def members_in_areas(conn, case_id, areas: list[list[list[float]]], *, places=graph_places) -> dict[str, Any]:
    """The selection a set of drawn areas makes: ``members``, counts by kind and the phones the positions belong to."""
    if not areas:
        raise ValueError("Draw at least one area.")
    rings = [_ring(a) for a in areas]
    xs = [x for r in rings for x, _ in r]
    ys = [y for r in rings for _, y in r]
    bbox = (min(xs), min(ys), max(xs), max(ys))
    seen: dict[str, str] = {}
    phones: set[str] = set()
    kinds: dict[str, int] = {}
    rows = conn.execute(text(
        "SELECT t.record_uid, t.extraction_id, t.model_type, t.lat, t.lon FROM pv_location_point t WHERE t.case_id = :c "
        "AND t.lat IS NOT NULL AND t.lon IS NOT NULL AND t.lat BETWEEN :s AND :n AND t.lon BETWEEN :w AND :e"),
        {"c": str(case_id), "w": bbox[0], "s": bbox[1], "e": bbox[2], "n": bbox[3]}).execution_options(
        stream_results=True, yield_per=5000)
    for r in rows:
        if r.record_uid is None or not inside_any(r.lon, r.lat, rings):
            continue
        uid = str(r.record_uid)
        if uid not in seen:
            seen[uid] = str(r.model_type or "")
            kinds[MODEL_WORDS.get(seen[uid], "positions")] = kinds.get(MODEL_WORDS.get(seen[uid], "positions"), 0) + 1
        phones.add(str(r.extraction_id))
    members = [{"type": "phone_record", "id": uid, "label": "Position inside the area"} for uid in seen]
    found = [p for p in places(str(case_id), bbox) if inside_any(p["lon"], p["lat"], rings)]
    members += [{"type": "graph_entity", "id": p["key"], "label": p["name"]} for p in found]
    if len(members) > case_selections.MAX_MEMBERS:
        raise ValueError(f"{len(members):,} items are inside the area; a selection holds at most "
                         f"{case_selections.MAX_MEMBERS:,}. Draw a smaller area; nothing was added.")
    return {"members": members, "phones": len(phones), "places": len(found), "by_kind": kinds,
            "total": len(members)}
