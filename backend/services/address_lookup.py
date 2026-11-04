"""Address lookup mode per case, and the automatic lookups (Neil 2026-11-04).

Two modes, set per case on its settings page by its owner (or an admin), with a system-wide default:

- ``auto``: addresses found in evidence are sent to the outside address service on their own. Ingestion marks them
  ``not_run`` (it never sends); one worker per host (``run_auto_lookups_forever``) picks them up within a minute and
  looks each one up, one a second, re-reading the case's mode before every address, so switching a case to ``flag``
  stops at once and switching it to ``auto`` looks up what is waiting.
- ``flag``: they wait in the map's Needs review panel until a person clicks Look up (routers.graph).

Whatever either mode places is a machine placement (services.neo4j.graph_edit_service.apply_looked_up_location):
the service, the mode, who asked ("automatic" here), and when, shown "not confirmed" until a person confirms it or
moves the pin. An address the service answered before is not asked again automatically (one request per new
address); a person can still click Look up for a fresh answer.
"""

from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import tempfile
from threading import Event
from typing import Optional
from uuid import UUID

from postgres.models.case import Case
from postgres.session import get_background_session

log = logging.getLogger(__name__)

AUTO = "auto"
FLAG = "flag"
MODES = (AUTO, FLAG)
MODE_WORDS = {
    AUTO: "Automatic: addresses found in evidence are looked up on their own",
    FLAG: "Only when a person clicks Look up",
}
PASS_SECONDS = 30
UNAVAILABLE_PAUSE_SECONDS = 300
BATCH = 50
_LOCK_PATH = os.path.join(tempfile.gettempdir(), "loupe-address-lookup.lock")


def default_mode() -> str:
    """The system-wide default (ADDRESS_LOOKUP_DEFAULT); 'auto' unless set to 'flag' (Neil asked for auto-lookup)."""
    value = os.environ.get("ADDRESS_LOOKUP_DEFAULT", "").strip().lower()
    return value if value in MODES else AUTO


def case_mode(case_id: str | UUID) -> tuple[str, Optional[str]]:
    """(the mode in force for the case, the mode set on the case or None for the default)."""
    with get_background_session() as db:
        case = db.get(Case, UUID(str(case_id)))
        chosen = case.address_lookup_mode if case is not None else None
    return (chosen or default_mode()), chosen


def auto_case_ids() -> list[str]:
    """Cases not archived whose lookup is automatic, set on the case or by the default."""
    with get_background_session() as db:
        # archived cases are not worked: their addresses are not sent on their own
        rows = db.query(Case.id, Case.address_lookup_mode).filter(Case.archived.is_(False)).all()
    fallback = default_mode()
    return [str(case_id) for case_id, chosen in rows if (chosen or fallback) == AUTO]


def look_up_waiting(case_id: str, stop: Event | None = None) -> dict[str, int]:
    """Look up the case's waiting addresses while its mode stays automatic. Returns counts per outcome
    ('placed', 'no_match', 'unavailable', 'stopped')."""
    from services.geo_rescan_service import AUTOMATIC, LOOKUP_SERVICE_NAME, GeocoderUnavailable, geocode_with_cache
    from services.neo4j_service import neo4j_service

    counts: dict[str, int] = {}
    _, waiting = neo4j_service.addresses_waiting(case_id, limit=BATCH)
    for row in waiting:
        if (stop is not None and stop.is_set()) or case_mode(case_id)[0] != AUTO:
            counts["stopped"] = counts.get("stopped", 0) + 1
            break
        try:
            found = geocode_with_cache(row["address"], requested_by=AUTOMATIC)
        except GeocoderUnavailable:
            counts["unavailable"] = counts.get("unavailable", 0) + 1
            break  # the service is not answering: the address stays waiting and is tried on a later pass
        if found:
            try:
                neo4j_service.apply_looked_up_location(
                    row["key"], case_id=case_id, query=row["address"], result=found, requested_by=AUTOMATIC,
                    requested_by_name=None, service=LOOKUP_SERVICE_NAME, mode=AUTO,
                )
                counts["placed"] = counts.get("placed", 0) + 1
            except LookupError:
                pass  # a person placed it meanwhile
        else:
            # Answered with no match: listed in Needs review as "Looked up: no match found" (a person can retry).
            neo4j_service.record_lookup_outcome(
                row["key"], case_id=case_id, outcome="no_match", requested_by=AUTOMATIC, requested_by_name=None,
                status="failed",
            )
            counts["no_match"] = counts.get("no_match", 0) + 1
    return counts


def _take_host_lock():
    try:
        handle = open(_LOCK_PATH, "a")
    except OSError:
        return None
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def run_pass(stop: Event) -> dict[str, int]:
    """One pass over every automatic case, by the one worker on this host holding the lock."""
    totals: dict[str, int] = {}
    for case_id in auto_case_ids():
        if stop.is_set():
            break
        try:
            counts = look_up_waiting(case_id, stop)
        except Exception:
            # one case's failure never starves the cases after it; this case is tried again next pass
            log.exception("Automatic address lookups failed for case %s", case_id)
            totals["case_failed"] = totals.get("case_failed", 0) + 1
            continue
        for outcome, n in counts.items():
            totals[outcome] = totals.get(outcome, 0) + n
        if counts.get("unavailable"):
            break
    return totals


async def run_auto_lookups_forever():
    """Started by main.py in every backend worker; only the one holding the host lock does the lookups."""
    lock = None
    while True:
        stop = Event()
        try:
            if lock is None:
                lock = await asyncio.to_thread(_take_host_lock)
            pause = PASS_SECONDS
            if lock is not None:
                work = asyncio.create_task(asyncio.to_thread(run_pass, stop))
                try:
                    totals = await asyncio.shield(work)
                except asyncio.CancelledError:
                    stop.set()
                    await work
                    raise
                if any(totals.get(k) for k in ("placed", "no_match", "unavailable")):
                    log.info("Automatic address lookups: %s", totals)
                if totals.get("unavailable"):
                    pause = UNAVAILABLE_PAUSE_SECONDS
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Automatic address lookups will retry")
        await asyncio.sleep(pause if lock is not None else PASS_SECONDS)
