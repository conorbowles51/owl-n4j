"""Subjects of the pattern views (04 sections 1.4, 4.2 and 10): one extraction, or a person as a dossier.

A person counts an extraction only when the extraction's owner identity is linked to the dossier by a reviewed
identity-to-dossier link (``phone_identity_links``, 02 section 8). Every subject is checked against the case the
request is made in; an extraction or dossier of another case is "not found".
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text


class SubjectError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def _uuid(v):
    try:
        return UUID(str(v))
    except (TypeError, ValueError):
        raise SubjectError(400, "The subject's id is not a valid id.")


def extractions(conn, case_id) -> list:
    """Active extractions of the case with their label, zone, owner identity, families and projection status."""
    from services.phone import identities as I
    from services.phone import readings
    labels = readings.phone_labels(conn, case_id)
    out = []
    for r in conn.execute(text(
            "SELECT e.id, e.device_zone, s.status AS interp_status, p.status AS pol_status, p.event_count, p.built_at "
            "FROM phone_extractions e LEFT JOIN phone_interpretation_state s ON s.extraction_id = e.id "
            "LEFT JOIN pol_projection_state p ON p.extraction_id = e.id "
            "WHERE e.case_id = :c AND e.standing = 'active' ORDER BY e.created_at"), {"c": case_id}).mappings():
        fams = [dict(f._mapping) for f in conn.execute(text(
            "SELECT family, count(*) AS events, min(instant_utc) AS first, max(instant_utc) AS last FROM "
            "pol_activity_event WHERE extraction_id = :e GROUP BY family ORDER BY family"), {"e": r["id"]})]
        owner = I.owner(conn, r["id"])
        keys = owner.get("owner_identity_keys") or []
        out.append({"kind": "extraction", "extraction_id": str(r["id"]), "label": labels.get(r["id"]) or
                    labels.get(str(r["id"])) or "Phone", "device_zone": r["device_zone"],
                    "owner_identity_key": keys[0] if keys else None,
                    "families": fams, "first": min((f["first"] for f in fams), default=None),
                    "last": max((f["last"] for f in fams), default=None),
                    "projection_status": r["pol_status"] or ("waiting" if r["interp_status"] == "done" else
                                                             "not_interpreted"),
                    "event_count": r["event_count"] or 0})
    return out


def dossiers(conn, case_id, exts=None) -> list:
    """Persons (dossiers) with the extractions whose owner identity is linked to them."""
    exts = extractions(conn, case_id) if exts is None else exts
    by_key = {}
    for e in exts:
        if e["owner_identity_key"]:
            by_key.setdefault(e["owner_identity_key"], []).append(e["extraction_id"])
    out = {}
    if by_key:
        for key, dossier, name in conn.execute(text(
                "SELECT i.identity_key, l.dossier_id, p.display_name FROM phone_identity_links l JOIN phone_identities i "
                "ON i.id = l.identity_id LEFT JOIN case_profiles p ON p.id = l.dossier_id WHERE l.case_id = :c AND "
                "i.identity_key = ANY(:k)"), {"c": case_id, "k": list(by_key)}):
            d = out.setdefault(str(dossier), {"kind": "dossier", "dossier_id": str(dossier), "name": name,
                                              "extraction_ids": []})
            d["extraction_ids"] += [x for x in by_key[key] if x not in d["extraction_ids"]]
    return sorted(out.values(), key=lambda d: (d["name"] or "", d["dossier_id"]))


def resolve(conn, case_id, subject) -> dict:
    """``{"subject": ..., "extraction_ids": [...]}``; raises ``SubjectError`` 400 or 404."""
    if not isinstance(subject, dict) or subject.get("kind") not in ("extraction", "dossier"):
        raise SubjectError(400, "A subject is a phone (extraction) or a person (dossier).")
    if subject["kind"] == "extraction":
        eid = _uuid(subject.get("extraction_id"))
        ok = conn.execute(text("SELECT 1 FROM phone_extractions WHERE id = :e AND case_id = :c AND standing = 'active'"),
                          {"e": eid, "c": case_id}).scalar()
        if not ok:
            raise SubjectError(404, "That phone is not in this case.")
        return {"subject": {"kind": "extraction", "extraction_id": str(eid)}, "extraction_ids": [str(eid)]}
    did = _uuid(subject.get("dossier_id"))
    exists = conn.execute(text("SELECT 1 FROM case_profiles WHERE id = :d AND case_id = :c"),
                          {"d": did, "c": case_id}).scalar()
    if not exists:
        raise SubjectError(404, "That person is not in this case.")
    for d in dossiers(conn, case_id):
        if d["dossier_id"] == str(did):
            return {"subject": {"kind": "dossier", "dossier_id": str(did)}, "extraction_ids": d["extraction_ids"],
                    "name": d["name"]}
    return {"subject": {"kind": "dossier", "dossier_id": str(did)}, "extraction_ids": [], "name": None}
