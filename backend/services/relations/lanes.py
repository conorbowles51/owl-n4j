"""Story lanes (Corroborate W): one lane per person for one instance of a result, the records the grid cites for that
instance as numbered events in time order. Nothing is added to what the result already cites: a lane only lays the
cited records out in order, so the picture never holds a record the grid does not."""
from __future__ import annotations

from typing import Any

KIND_WORDS = {"message": "Message", "call": "Call", "payment": "Payment", "payment_alert": "Payment alert",
              "doc_row": "Document or access row", "position": "Place", "media_position": "Photo place",
              "activity": "Phone activity"}


def cited_refs(corroboration: dict, instance_id: str) -> list[str]:
    seen: dict[str, None] = {}
    for row in corroboration.get("grid", []):
        if row.get("cells", {}).get(instance_id) == "present":
            for ref in row.get("records", {}).get(instance_id, []):
                seen[ref] = None
    return list(seen)


def _text(rec: dict) -> str:
    body = (rec.get("body") or "").strip()
    if body:
        return body[:240]
    if rec.get("place"):
        p = rec["place"]
        return f"At {p['lat']:.4f}, {p['lon']:.4f} (within {int(p.get('radius_m') or 0)} m)"
    return rec.get("source_label") or KIND_WORDS.get(rec.get("kind"), rec.get("kind") or "Record")


def build(store, corroboration: dict, instance_id: str) -> dict[str, Any]:
    """Lanes for one instance. ``store`` reads records (``CaseStore``)."""
    cmp_ = corroboration["comparison"]
    inst = next((i for i in cmp_["incident"] + cmp_["ordinary"] if i["id"] == instance_id), None)
    if inst is None:
        raise LookupError("That instance is not in this result.")
    refs = set(cited_refs(corroboration, instance_id))
    everyone = list(store.people())
    keys = {p["key"] for p in corroboration.get("people", [])}
    group = [p for p in everyone if p["key"] in keys]
    from services.corroborate import model as M
    start, end = M.as_utc(inst["start"]), M.as_utc(inst.get("money_until") or inst["end"])
    recs = [r for r in store.records(group, [(start, end)], everyone) if r["ref"] in refs]
    recs.sort(key=lambda r: (r["at"], r["ref"]))
    label = {p["key"]: p["label"] for p in everyone}
    lanes: dict[str, dict] = {}
    events = []
    for n, r in enumerate(recs, 1):
        who = r.get("owner") or (r.get("parties") or [None])[0] or "unplaced"
        lane = lanes.setdefault(who, {"person": who, "label": label.get(who, "Not placed on a person"), "events": []})
        ev = {"n": n, "ref": r["ref"], "kind": r.get("kind"), "kind_words": KIND_WORDS.get(r.get("kind"), "Record"),
              "at": r["at"].isoformat(), "day_only": bool(r.get("day_only")), "text": _text(r),
              "with": [label.get(x, x) for x in r.get("parties") or [] if x != who]}
        lane["events"].append(ev)
        events.append(ev)
    missing = sorted(refs - {r["ref"] for r in recs})
    return {"instance": {"id": inst["id"], "label": inst["label"]}, "lanes": list(lanes.values()),
            "events": len(events), "cited": len(refs),
            "not_laid_out": [{"ref": m, "why": "The record could not be read again for this instance."} for m in missing]}
