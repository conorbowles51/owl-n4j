"""Group a selection by person, day, place, amount or app (lx-corrorest C), so a group can be asked about alone or each
group against the others. Every item lands in a group or in a stated "left out" count with the reason: nothing is dropped
silently. An item with several people is in each person's group, and the count says so. Places are cells of about a
kilometre; amounts are bands (the currency is whatever the ledger holds); both are named in the group's label."""
from __future__ import annotations

from collections import defaultdict
from zoneinfo import ZoneInfo

from services.relations import rules

BY = ("person", "day", "place", "amount", "app")
BANDS = [(0, 10_000, "under 100"), (10_000, 100_000, "100 to 999"), (100_000, 1_000_000, "1,000 to 9,999"), (1_000_000, None, "10,000 and over")]
MAX_GROUPS = 200


class GroupError(ValueError):
    pass


def _band(minor: int) -> str:
    n = abs(int(minor))
    return next(label for lo, hi, label in BANDS if n >= lo and (hi is None or n < hi))


def _keys(point: dict, by: str, zone: ZoneInfo, names: dict[str, str]) -> tuple[list[tuple[str, str]], str]:
    """The (key, label) groups an item belongs to, or [] with the reason it has none."""
    if by == "person":
        keys = [(k, names.get(k, k)) for k in point.get("people") or []]
        return keys, "names no person Loupe can join to the records"
    if by == "day":
        when = rules.parse_when(point.get("at"))
        if when is None:
            return [], "has no date"
        d = when.astimezone(zone).date().isoformat()
        return [(d, d)], ""
    if by == "place":
        pl = point.get("place")
        if not pl:
            return [], "has no place"
        lat, lon = round(float(pl["lat"]), 2), round(float(pl["lon"]), 2)
        return [(f"{lat:.2f},{lon:.2f}", f"near {lat:.2f}, {lon:.2f} (within about 1 km)")], ""
    if by == "amount":
        if point.get("amount_minor") is None:
            return [], "has no amount"
        b = _band(point["amount_minor"])
        return [(b, f"payments of {b}")], ""
    if by == "app":
        app = (point.get("app") or "").strip()
        return ([(app.lower(), app)] if app else []), "names no app"
    raise GroupError(f"Group by one of: {', '.join(BY)}.")


def group_points(points: list[dict], by: str, zone_name: str, names: dict[str, str]) -> dict:
    if by not in BY:
        raise GroupError(f"Group by one of: {', '.join(BY)}.")
    zone = ZoneInfo(zone_name or "UTC")
    groups: dict[str, dict] = {}
    left: dict[str, int] = defaultdict(int)
    multi = 0
    for p in points:
        keys, why = _keys(p, by, zone, names)
        if not keys:
            left[why] += 1
            continue
        multi += 1 if len(keys) > 1 else 0
        for key, label in keys:
            g = groups.setdefault(key, {"key": key, "label": label, "members": [], "people": []})
            g["members"].append({"type": p["type"], "id": p["ref"].split(":", 1)[1], "label": p.get("label")})
            for person in p.get("people") or []:
                if person not in g["people"]:
                    g["people"].append(person)
    ordered = sorted(groups.values(), key=lambda g: (-len(g["members"]), g["label"]))
    shown = ordered[:MAX_GROUPS]
    for g in shown:
        g["count"] = len(g["members"])
    return {"by": by, "groups": shown, "group_count": len(ordered), "clipped": len(ordered) - len(shown),
            "in_several_groups": multi, "left_out": [{"count": n, "why": w} for w, n in left.items()],
            "left_out_total": sum(left.values())}
