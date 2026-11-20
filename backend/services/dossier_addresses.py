"""Positions for the addresses typed on dossiers, through the case's address lookup (Neil 2026-11-20, followups).

Addresses found in evidence were looked up (services.address_lookup); addresses on a dossier never were, so a
statement naming one ("I was at Ruiz Auto & Tire") could not be placed on the map. They now go through the same
lookup under the same case setting:

- ``auto``: the one lookup worker looks each new dossier address up on its own, with the same rules as evidence
  addresses (services.address_auto_rules: text naming no place is not sent; the case's own state is added and the
  answer must lie in it) and the same shared cache (one request per new address).
- ``flag``: nothing is sent until a person clicks Look up on the dossier; that lookup sends the address as typed.

The position is the address service's reading, never the person's: it is kept in the contact's own ``position``
block (who asked, the service, the words sent, when), shown "Read by Loupe, not confirmed", and the person's entry
(value, label, who recorded it) is not touched. An address edited to new words drops its old position and is looked
up again. When a lookup places nothing, ``lookup`` says why, so the worker does not ask again for the same words.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from threading import Event
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from postgres.models.case_profile import CaseProfile
from postgres.session import get_background_session

log = logging.getLogger(__name__)

READING_WORDS = "Read by Loupe, not confirmed"
NO_MATCH = "no_match"
OUTCOME_WORDS = {
    NO_MATCH: "The address service found no match",
    "not_a_place": "Not sent: the words name no place on their own",
    "no_case_region": "Not sent: the case has no state to bound the lookup",
    "outside_case_region": "Not placed: the service's answer lies outside the case's state",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _active(db, case_id) -> list[CaseProfile]:
    return list(db.scalars(select(CaseProfile).where(
        CaseProfile.case_id == uuid.UUID(str(case_id)), CaseProfile.archived_at.is_(None))))


def waiting(contact: dict) -> bool:
    """An address with no position for its present words and no lookup already tried for them."""
    if contact.get("kind") != "address" or not (contact.get("value") or "").strip():
        return False
    value = contact["value"]
    pos, tried = contact.get("position") or {}, contact.get("lookup") or {}
    return pos.get("value") != value and tried.get("value") != value


def keep_reading(previous: dict, value: str) -> dict:
    """The position and lookup blocks a saved contact keeps: only those made for the words it still holds."""
    out = {}
    for k in ("position", "lookup"):
        block = previous.get(k)
        if isinstance(block, dict) and block.get("value") == value:
            out[k] = block
    return out


def _position(value: str, query: str, found: dict, *, mode: str, requested_by: str, requested_by_name: Optional[str],
              service: str, region_added: Optional[str]) -> dict:
    return {"value": value, "lat": float(found["latitude"]), "lon": float(found["longitude"]),
            "formatted_address": found.get("formatted_address"), "confidence": found.get("confidence"),
            "query": query, "service": service, "mode": mode, "requested_by": requested_by,
            "requested_by_name": requested_by_name, "region_added": region_added, "at": _now(),
            "read_by": "Loupe", "confirmed": False, "words": READING_WORDS}


def _region(case_id: str, db) -> Optional[str]:
    from services import address_auto_rules as rules
    texts: list[str] = []
    try:
        from services.neo4j_service import neo4j_service
        texts = list(neo4j_service.case_address_texts(case_id))
    except Exception:  # noqa: BLE001 - the graph not answering: the dossier addresses alone decide the state
        log.warning("Case address texts unavailable for %s", case_id, exc_info=True)
    for p in _active(db, case_id):
        texts += [c["value"] for c in (p.contacts or []) if c.get("kind") == "address" and c.get("value")]
    return rules.case_region(texts)[0]


def look_up_waiting(case_id: str, stop: Event | None = None, *, still_auto=None) -> dict[str, int]:
    """The automatic lookups of one case's dossier addresses (the case's mode re-read before each). Counts per
    outcome, as services.address_lookup.look_up_waiting returns them."""
    from services import address_auto_rules as rules
    from services.address_lookup import AUTO, case_mode
    from services.geo_rescan_service import AUTOMATIC, LOOKUP_SERVICE_NAME, GeocoderUnavailable, geocode_with_cache
    still_auto = still_auto or (lambda: case_mode(case_id)[0] == AUTO)
    counts: dict[str, int] = {}

    def add(k):
        counts[k] = counts.get(k, 0) + 1

    with get_background_session() as db:
        todo = [(p.id, c["id"]) for p in _active(db, case_id) for c in (p.contacts or []) if waiting(c) and c.get("id")]
        region = _region(case_id, db) if todo else None
    for profile_id, contact_id in todo:
        if (stop is not None and stop.is_set()) or not still_auto():
            add("stopped")
            break
        with get_background_session() as db:
            p = db.get(CaseProfile, profile_id)
            c = next((x for x in (p.contacts or []) if x.get("id") == contact_id), None) if p is not None else None
            if c is None or not waiting(c):
                continue
            value = c["value"]
        plan = rules.plan(value, region)
        result: dict[str, Any]
        if plan.action != rules.SEND:
            result = {"lookup": {"value": value, "outcome": plan.action, "requested_by": AUTOMATIC, "at": _now()}}
        else:
            try:
                found = geocode_with_cache(plan.query, requested_by=AUTOMATIC)
            except GeocoderUnavailable:
                add("unavailable")
                break  # tried again on a later pass
            if found and not rules.in_state(found, plan.expect_state):
                result = {"lookup": {"value": value, "outcome": rules.OUTSIDE_REGION, "requested_by": AUTOMATIC,
                                     "at": _now()}}
            elif found:
                result = {"position": _position(value, plan.query, found, mode=AUTO, requested_by=AUTOMATIC,
                                                requested_by_name=None, service=LOOKUP_SERVICE_NAME,
                                                region_added=region if plan.region_added else None)}
            else:
                result = {"lookup": {"value": value, "outcome": NO_MATCH, "requested_by": AUTOMATIC, "at": _now()}}
        if _save(profile_id, contact_id, value, result):
            add("placed" if "position" in result else result["lookup"]["outcome"])
    return counts


def _save(profile_id, contact_id, value, result: dict) -> bool:
    """Write the reading onto the contact when it still holds the same words (a person may have edited it)."""
    with get_background_session() as db:
        p = db.get(CaseProfile, profile_id)
        if p is None:
            return False
        contacts = [dict(x) for x in (p.contacts or [])]
        c = next((x for x in contacts if x.get("id") == contact_id), None)
        if c is None or c.get("value") != value:
            return False
        c.pop("lookup", None)
        if "position" in result:
            c["position"] = result["position"]
        else:
            c["lookup"] = result["lookup"]
        p.contacts = contacts
        flag_modified(p, "contacts")
        db.commit()
    return True


def look_up_one(db, *, dossier: CaseProfile, contact_id: str, user) -> dict:
    """A person clicked Look up on one dossier address: the address is sent as typed (a person's lookup is not bound
    by the automatic rules), and the answer is a reading by Loupe, not confirmed. Returns the contact."""
    from services.address_lookup import case_mode
    from services.geo_rescan_service import LOOKUP_SERVICE_NAME, geocode_with_cache
    contacts = [dict(x) for x in (dossier.contacts or [])]
    c = next((x for x in contacts if str(x.get("id")) == str(contact_id)), None)
    if c is None or c.get("kind") != "address" or not (c.get("value") or "").strip():
        raise LookupError("No address with that id on this dossier")
    value = c["value"]
    found = geocode_with_cache(value, requested_by=str(user.id))  # GeocoderUnavailable: the caller says so
    c.pop("lookup", None)
    c.pop("position", None)
    if found:
        c["position"] = _position(value, value, found, mode=case_mode(dossier.case_id)[0], requested_by=str(user.id),
                                  requested_by_name=getattr(user, "name", None) or getattr(user, "email", None),
                                  service=LOOKUP_SERVICE_NAME, region_added=None)
    else:
        c["lookup"] = {"value": value, "outcome": NO_MATCH, "requested_by": str(user.id), "at": _now()}
    dossier.contacts = contacts
    flag_modified(dossier, "contacts")
    db.commit()
    return c
