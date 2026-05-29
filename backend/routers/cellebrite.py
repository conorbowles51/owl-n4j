"""
Cellebrite Router

Analytics endpoints for the Cellebrite Multi-Phone View:
- List ingested phone reports
- Cross-phone graph (shared contacts across devices)
- Multi-device timeline
- Communication network analysis
"""

from typing import Dict, List, Optional, Tuple
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from pydantic import BaseModel

from services.neo4j_service import neo4j_service
from services.evidence_storage import evidence_storage
from services.case_service import get_case_if_allowed, CaseNotFound, CaseAccessDenied
from services import cellebrite_intersection_service
from postgres.session import get_db
from postgres.models.user import User
from routers.users import get_current_db_user

router = APIRouter(prefix="/api/cellebrite", tags=["cellebrite"])


def _require_case_access(case_id: str, user: User, db: Session):
    """Verify user has access to the case."""
    try:
        get_case_if_allowed(db, case_id, user)
    except CaseNotFound:
        raise HTTPException(status_code=404, detail="Case not found")
    except CaseAccessDenied:
        raise HTTPException(status_code=403, detail="Access denied")


@router.get("/reports")
def get_reports(
    case_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """List all ingested Cellebrite PhoneReport nodes for a case."""
    _require_case_access(case_id, current_user, db)
    reports = neo4j_service.get_cellebrite_reports(case_id)
    return {"reports": reports}


@router.get("/report/devices")
def get_device_report(
    case_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Per-device forensic profile for the Report tab: each phone's true
    primary user (by traffic), declared vs actual owner, device numbers,
    recovered contact aliases, in/out comms, and activity window."""
    _require_case_access(case_id, current_user, db)
    return {"devices": neo4j_service.get_cellebrite_device_report(case_id)}


@router.get("/geocoder/status")
def get_geocoder_status(
    current_user: User = Depends(get_current_db_user),
):
    """
    Diagnostic snapshot for ops — which reverse-geocoder backend the
    server picked up at startup, and whether its deps are wired
    correctly. Returns a flat dict; harmless to expose to any
    authenticated user since it carries no case data.
    """
    from services.geocoder import geocoder_status
    return geocoder_status()


def _require_case_evidence_access(case_id: str, user: User, db: Session):
    """Stronger access check for mutating phone-report operations."""
    from services.case_service import check_case_access, CaseNotFound, CaseAccessDenied
    from uuid import UUID
    try:
        check_case_access(
            db,
            UUID(case_id),
            user,
            required_permission=("evidence", "upload"),
        )
    except CaseNotFound:
        raise HTTPException(status_code=404, detail="Case not found")
    except CaseAccessDenied:
        raise HTTPException(status_code=403, detail="Access denied")


@router.delete("/reports/{report_key}")
def delete_phone_report(
    report_key: str,
    case_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """
    Delete a PhoneReport and every node tagged with its
    cellebrite_report_key in this case.

    Cleans up the central PhoneReport node, all entities (Persons,
    PhoneCalls, Communications, Locations, etc.) that were ingested
    against this report, and any registered Cellebrite evidence
    records keyed to it.
    """
    _require_case_evidence_access(case_id, current_user, db)

    # Neo4j-side deletion (PhoneReport + tagged entities + relationships).
    neo_result = neo4j_service.delete_phone_report(case_id, report_key)

    # Drop any evidence_storage records that point at this report so
    # the Files Explorer + main evidence list don't show ghost rows.
    evidence_deleted = 0
    try:
        evidence_records = evidence_storage.list_files(case_id=case_id)
        for rec in evidence_records:
            if (
                rec.get("source_type") == "cellebrite"
                and rec.get("cellebrite_report_key") == report_key
            ):
                rec_id = rec.get("id")
                if rec_id:
                    evidence_storage.delete_record(rec_id)
                    evidence_deleted += 1
    except AttributeError:
        # evidence_storage.delete_record is the canonical name; if a
        # different helper exists, the loop is best-effort.
        pass
    except Exception:
        pass

    if neo_result.get("status") == "not_found" and evidence_deleted == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No phone report '{report_key}' in case",
        )

    return {
        **neo_result,
        "deleted_evidence_records": evidence_deleted,
    }


class PhoneReportUpdateRequest(BaseModel):
    """PATCH body for /reports/{report_key} — only override editing for now."""
    device_name_override: Optional[str] = None


@router.patch("/reports/{report_key}")
def patch_phone_report(
    report_key: str,
    body: PhoneReportUpdateRequest,
    case_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """
    Update mutable fields on a PhoneReport. Currently supports only
    `device_name_override`: pass a non-empty string to override the
    detected device name, or null/empty to clear and revert to the
    parser-detected name.
    """
    _require_case_evidence_access(case_id, current_user, db)
    updated = neo4j_service.update_phone_report_name_override(
        case_id=case_id,
        report_key=report_key,
        device_name_override=body.device_name_override,
    )
    if not updated:
        raise HTTPException(
            status_code=404,
            detail=f"No phone report '{report_key}' in case",
        )
    return updated


@router.get("/persons/search")
def persons_search(
    case_id: str = Query(...),
    q: str = Query(..., min_length=1),
    exclude_key: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Search persons by name / number / key for the merge-identity picker —
    so an investigator selects a real candidate (with its activity + device
    span shown) rather than typing a raw key."""
    _require_case_access(case_id, current_user, db)
    return {"results": neo4j_service.search_persons(
        case_id, q, limit=limit, exclude_key=exclude_key)}


class MergePersonsRequest(BaseModel):
    """POST body for /persons/merge — fold secondary identities into a primary."""
    primary_key: str
    secondary_keys: List[str]


@router.post("/persons/merge")
def merge_persons(
    body: MergePersonsRequest,
    case_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Investigator-asserted identity merge: fold secondary Person identities
    (a contact's other numbers / handles) into a primary one. The system never
    auto-merges different numbers — that would be false attribution — so this is
    a deliberate human action, recorded on the survivor for audit. Requires
    evidence-write access since it mutates the graph.
    """
    _require_case_evidence_access(case_id, current_user, db)
    if not body.secondary_keys:
        raise HTTPException(status_code=400, detail="secondary_keys must be non-empty")
    actor = getattr(current_user, "email", None) or getattr(current_user, "username", None)
    result = neo4j_service.merge_person_identities(
        case_id=case_id,
        primary_key=body.primary_key,
        secondary_keys=body.secondary_keys,
        actor=actor,
    )
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=result.get("detail", "primary identity not found"))
    return result


@router.get("/cross-phone-graph/search")
def search_cross_phone_graph(
    case_id: str = Query(...),
    q: str = Query(..., description="Free-text query — name / phone / key substring match"),
    limit: int = Query(50, ge=1, le=200, description="Max results to return"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Full-case Person search backing the Cross-Phone Graph search bar.

    The graph render is capped at 200 Persons for legibility, so the
    canvas-side filter can only narrow to what's already drawn. This
    endpoint searches every Person in the case so the investigator
    can find anyone regardless of whether they made the cut.

    Each result carries enough to render a row + offer a one-click
    "anchor the graph on this person" action.
    """
    _require_case_access(case_id, current_user, db)
    return neo4j_service.search_cellebrite_persons(case_id, q, limit=limit)


@router.get("/cross-phone-graph")
def get_cross_phone_graph(
    case_id: str = Query(...),
    person_keys: Optional[str] = Query(
        None,
        description=(
            "Comma-separated Person keys to anchor the graph on. "
            "When provided, returns only the anchor set + their "
            "±depth neighbourhood across the active event types."
        ),
    ),
    event_types: Optional[str] = Query(
        None,
        description=(
            "Comma-separated event types to include as edges. "
            "Subset of call, message, email, location, wifi, cell_tower, "
            "meeting, visit, search, bookmark, wifi_ssid, account, "
            "credential, financial, pairing. "
            "Defaults to call+message+email (legacy comms-only)."
        ),
    ),
    depth: int = Query(1, ge=1, le=2, description="Neighbourhood depth (1 or 2). Only used when person_keys is set."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Get cross-phone graph showing shared contacts across devices.

    Backwards-compatible: when neither person_keys nor event_types is
    supplied, the response matches the pre-perspective shape (top 200
    persons by comm volume, comms edges only).
    """
    _require_case_access(case_id, current_user, db)
    pk = [k.strip() for k in person_keys.split(",")] if person_keys else None
    et = [t.strip() for t in event_types.split(",")] if event_types else None
    if pk:
        pk = [k for k in pk if k]
    if et:
        et = [t for t in et if t]
    graph = neo4j_service.get_cellebrite_cross_phone_graph(
        case_id,
        person_keys=pk,
        event_types=et,
        depth=depth,
    )
    return graph


@router.get("/timeline")
def get_timeline(
    case_id: str = Query(...),
    report_keys: Optional[str] = Query(None, description="Comma-separated report keys to filter"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    event_types: Optional[str] = Query(None, description="Comma-separated event types"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Get multi-device event timeline."""
    _require_case_access(case_id, current_user, db)

    keys = [k.strip() for k in report_keys.split(",")] if report_keys else None
    types = [t.strip() for t in event_types.split(",")] if event_types else None

    result = neo4j_service.get_cellebrite_timeline(
        case_id=case_id,
        report_keys=keys,
        start_date=start_date,
        end_date=end_date,
        event_types=types,
        limit=limit,
        offset=offset,
    )
    return result


@router.get("/communication-network")
def get_communication_network(
    case_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Get communication network analysis (contact frequency, shared contacts)."""
    _require_case_access(case_id, current_user, db)
    try:
        return neo4j_service.get_cellebrite_communication_network(case_id)
    except Exception as e:
        # Surface the real driver/Cypher error to the client instead of
        # bubbling a 500 with no detail. The frontend reports the
        # message verbatim, so the investigator gets a clue instead of
        # an opaque "unknown error".
        raise HTTPException(
            status_code=500,
            detail=f"Communication network query failed: {type(e).__name__}: {e}",
        ) from e


# -------------------------------------------------------------------
# Communication Center (Phase 3) endpoints
# -------------------------------------------------------------------

def _csv_param(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    parts = [p.strip() for p in value.split(",") if p.strip()]
    return parts or None


def _resolve_attachments(case_id: str, items: List[dict]) -> None:
    """
    Mutate items in-place: replace `attachment_file_ids` with a richer
    `attachments` list containing evidence_id + category + filename.
    """
    # Collect all file_ids
    all_ids: set = set()
    for it in items:
        for fid in (it.get("attachment_file_ids") or []):
            all_ids.add(fid)
    if not all_ids:
        for it in items:
            it["attachments"] = []
        return

    records = evidence_storage.get_by_cellebrite_file_ids(case_id, list(all_ids))

    for it in items:
        atts = []
        for fid in (it.get("attachment_file_ids") or []):
            rec = records.get(fid)
            if not rec:
                # Missing record — keep minimal placeholder
                atts.append({
                    "file_id": fid,
                    "evidence_id": None,
                    "category": None,
                    "original_filename": None,
                    "missing": True,
                })
                continue
            atts.append({
                "file_id": fid,
                "evidence_id": rec.get("id"),
                "category": rec.get("cellebrite_category"),
                "original_filename": rec.get("original_filename"),
                "size": rec.get("size"),
                "sha256": rec.get("sha256"),
            })
        it["attachments"] = atts


@router.get("/comms/entities")
def get_comms_entities(
    case_id: str = Query(...),
    report_keys: Optional[str] = Query(None, description="Comma-separated report keys"),
    with_counts: bool = Query(
        False,
        description=(
            "When true, includes per-entity call/message/email counts. "
            "Adds 5 OPTIONAL MATCH passes to the Cypher; on busy cases "
            "(OPDMD28: 13K entities) this takes ~12s + ~13MB. Default "
            "false ships only the cheap fields the filter UI needs to "
            "render — counts default to 0; opt in only when sorting by "
            "activity."
        ),
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """List distinct comms participants. Counts opt-in via with_counts."""
    _require_case_access(case_id, current_user, db)
    keys = _csv_param(report_keys)
    entities = neo4j_service.get_cellebrite_comms_entities(
        case_id=case_id, report_keys=keys, with_counts=with_counts,
    )
    return {"entities": entities}


@router.get("/comms/source-apps")
def get_comms_source_apps(
    case_id: str = Query(...),
    report_keys: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """List distinct source_app values (WhatsApp, Facebook Messenger, SMS, Gmail, ...) with counts."""
    _require_case_access(case_id, current_user, db)
    apps = neo4j_service.get_cellebrite_comms_source_apps(
        case_id=case_id,
        report_keys=_csv_param(report_keys),
    )
    return {"apps": apps}


@router.get("/comms/threads")
def get_comms_threads(
    case_id: str = Query(...),
    report_keys: Optional[str] = Query(None),
    from_keys: Optional[str] = Query(None, description="Comma-separated Person keys in From"),
    to_keys: Optional[str] = Query(None, description="Comma-separated Person keys in To"),
    participant_keys: Optional[str] = Query(
        None,
        description=(
            "Comma-separated Person keys for direction-agnostic involvement filter. "
            "A thread passes when at least one of its participants is in this set. "
            "OR-combined with from_keys/to_keys when present."
        ),
    ),
    thread_types: Optional[str] = Query(None, description="Comma-separated: chat,calls,emails"),
    source_apps: Optional[str] = Query(None, description="Comma-separated source app names"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """List threads (chats + synthetic call/email threads per participant pair)."""
    _require_case_access(case_id, current_user, db)
    result = neo4j_service.get_cellebrite_comms_threads(
        case_id=case_id,
        report_keys=_csv_param(report_keys),
        from_keys=_csv_param(from_keys),
        to_keys=_csv_param(to_keys),
        participant_keys=_csv_param(participant_keys),
        thread_types=_csv_param(thread_types),
        source_apps=_csv_param(source_apps),
        start_date=start_date,
        end_date=end_date,
        search=search,
        limit=limit,
        offset=offset,
    )
    return result


@router.get("/comms/threads/{thread_id:path}")
def get_comms_thread_detail(
    thread_id: str,
    case_id: str = Query(...),
    thread_type: str = Query(..., description="chat, calls, or emails"),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    anchor_key: Optional[str] = Query(
        None,
        description="Optional Neo4j key of a message inside the thread; "
                    "when set, the window is centred on it (chat threads only).",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Get chronological items for a thread with attachment metadata resolved."""
    _require_case_access(case_id, current_user, db)
    if thread_type not in ("chat", "calls", "emails"):
        raise HTTPException(status_code=400, detail="Invalid thread_type")
    result = neo4j_service.get_cellebrite_thread_detail(
        case_id=case_id,
        thread_id=thread_id,
        thread_type=thread_type,
        limit=limit,
        offset=offset,
        anchor_key=anchor_key,
    )
    _resolve_attachments(case_id, result.get("items", []))
    return result


@router.get("/comms/between")
def get_comms_between(
    case_id: str = Query(...),
    from_keys: Optional[str] = Query(None),
    to_keys: Optional[str] = Query(None),
    participant_keys: Optional[str] = Query(
        None,
        description=(
            "Comma-separated Person keys for direction-agnostic involvement filter. "
            "An item passes when sender OR recipient is in this set. Used by "
            "Filter Comms intents and the 'Any direction' participants mode."
        ),
    ),
    types: Optional[str] = Query(None, description="Comma-separated: message,call,email"),
    report_keys: Optional[str] = Query(None),
    source_apps: Optional[str] = Query(None, description="Comma-separated source app names"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    sort: str = Query("desc", regex="^(asc|desc)$",
                      description="Order: 'desc' (newest first) or 'asc' (oldest first)"),
    cursor: Optional[str] = Query(
        None,
        description=(
            "Opaque continuation token from a previous response's `next_cursor`. "
            "Takes priority over `offset` when supplied — engages keyset "
            "pagination so deep pages don't re-read earlier rows."
        ),
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Chronological cross-type feed between selected entity sets."""
    _require_case_access(case_id, current_user, db)
    result = neo4j_service.get_cellebrite_comms_between(
        case_id=case_id,
        from_keys=_csv_param(from_keys),
        to_keys=_csv_param(to_keys),
        participant_keys=_csv_param(participant_keys),
        types=_csv_param(types),
        report_keys=_csv_param(report_keys),
        source_apps=_csv_param(source_apps),
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
        sort=sort,
        cursor=cursor,
    )
    _resolve_attachments(case_id, result.get("items", []))
    return result


@router.get("/comms/envelope")
def get_comms_envelope(
    case_id: str = Query(...),
    from_keys: Optional[str] = Query(None),
    to_keys: Optional[str] = Query(None),
    participant_keys: Optional[str] = Query(
        None,
        description="Direction-agnostic involvement filter (see /comms/between).",
    ),
    types: Optional[str] = Query(None, description="Comma-separated: message,call,email"),
    report_keys: Optional[str] = Query(None),
    source_apps: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """
    Cheap aggregation across the comms feed shape.

    Returns total count, per-type counts, min/max date and a per-day
    histogram WITHOUT loading any item rows. Powers the timeline
    scrubber's true min/max + density curve so it can render before
    the body /comms/between request returns.

    Same filter contract as /comms/between so the envelope is always
    consistent with what a body fetch would surface.
    """
    _require_case_access(case_id, current_user, db)
    return neo4j_service.get_cellebrite_comms_envelope(
        case_id=case_id,
        report_keys=_csv_param(report_keys),
        from_keys=_csv_param(from_keys),
        to_keys=_csv_param(to_keys),
        participant_keys=_csv_param(participant_keys),
        types=_csv_param(types),
        source_apps=_csv_param(source_apps),
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/comms/messages/search")
def search_comms_messages(
    case_id: str = Query(...),
    q: str = Query(..., min_length=1, description="Search term (matched against message body, subject, call notes)"),
    report_keys: Optional[str] = Query(None, description="Comma-separated report keys"),
    limit: int = Query(200, ge=1, le=1000, description="Max matches to return"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """
    Full-text search across the bodies of every message / email / call note
    in the case (filtered by selected phones). Returns the matching
    thread_ids plus a ranked list of message snippets so the frontend can
    narrow the thread list and auto-scroll to the first hit inside the
    chosen thread.

    Distinct from `/comms/threads?search=` which only matches thread-level
    metadata (name, source_app). This endpoint searches inside the chats.
    """
    _require_case_access(case_id, current_user, db)
    result = neo4j_service.search_cellebrite_comms_messages(
        case_id=case_id,
        query=q,
        report_keys=_csv_param(report_keys),
        limit=limit,
    )
    return result


@router.get("/comms/attachment/{file_id}")
def resolve_comms_attachment(
    file_id: str,
    case_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Resolve a single Cellebrite file UUID to its evidence record."""
    _require_case_access(case_id, current_user, db)
    records = evidence_storage.get_by_cellebrite_file_ids(case_id, [file_id])
    rec = records.get(file_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return {
        "file_id": file_id,
        "evidence_id": rec.get("id"),
        "category": rec.get("cellebrite_category"),
        "original_filename": rec.get("original_filename"),
        "size": rec.get("size"),
        "sha256": rec.get("sha256"),
    }


# -------------------------------------------------------------------
# Location & Event Center (Phase 4) endpoints
# -------------------------------------------------------------------


@router.get("/events")
def get_events(
    case_id: str = Query(...),
    report_keys: Optional[str] = Query(None),
    event_types: Optional[str] = Query(None),
    source_apps: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    only_geolocated: bool = Query(False),
    limit: int = Query(5000, ge=1, le=500000),
    offset: int = Query(0, ge=0),
    place: Optional[str] = Query(
        None,
        description=(
            "Substring (case-insensitive) matched against the reverse-"
            "geocoded fields stamped at ingestion (address / place_name / "
            "country / country_code / admin1 / admin2). Items without "
            "geocode metadata are excluded — narrowed to geo-known rows."
        ),
    ),
    near: Optional[str] = Query(
        None,
        description=(
            "Geo radius filter as 'lat,lng,radius[unit]'. Unit is km|m, "
            "default km. Example: 51.5074,-0.1278,5km. Items without "
            "coordinates are excluded."
        ),
    ),
    lean: bool = Query(
        False,
        description=(
            "Location type only: project just the columns the map / table / "
            "search use and omit null fields, instead of whole nodes. Keeps "
            "every row; ~halves payload + serialisation. Used by the Locations "
            "tab which loads all geolocated points."
        ),
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Unified event feed for the Location & Event Center."""
    _require_case_access(case_id, current_user, db)
    near_tuple = _parse_near_param(near)
    result = neo4j_service.get_cellebrite_events(
        case_id=case_id,
        report_keys=_csv_param(report_keys),
        event_types=_csv_param(event_types),
        source_apps=_csv_param(source_apps),
        start_date=start_date,
        end_date=end_date,
        only_geolocated=only_geolocated,
        limit=limit,
        offset=offset,
        place=place or None,
        near=near_tuple,
        lean=lean,
    )
    # Resolve message/voicemail/email attachment file-ids into the richer
    # `attachments` list so the Timeline + Event Center rows can render the
    # same inline media (images, voicenotes, video) as the thread view. The
    # `lean` path is locations-only (no attachments), so skip it.
    if not lean:
        _resolve_attachments(case_id, result.get("events", []))
    return result


@router.get("/events/envelope")
def get_events_envelope(
    case_id: str = Query(...),
    report_keys: Optional[str] = Query(None),
    event_types: Optional[str] = Query(None),
    source_apps: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    only_geolocated: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """
    Cheap aggregation for the Timeline scrubber: true total count + per-type
    counts + min/max date + per-day histogram across the active event types,
    WITHOUT loading any event rows.

    The body feed (/events) caps each type at ~5000 rows for responsiveness;
    this lets the scrubber show the honest full date range/density and the tab
    show "showing N of TOTAL" instead of implying the capped slice is all there
    is. `only_geolocated` mirrors the body's geo filter so the count matches
    the Event Center's geo-only mode.
    """
    _require_case_access(case_id, current_user, db)
    return neo4j_service.get_cellebrite_events_envelope(
        case_id=case_id,
        report_keys=_csv_param(report_keys),
        event_types=_csv_param(event_types),
        source_apps=_csv_param(source_apps),
        start_date=start_date,
        end_date=end_date,
        only_geolocated=only_geolocated,
    )


def _parse_near_param(raw: Optional[str]) -> Optional[Tuple[float, float, float]]:
    """
    Parse a `near` query param of the form 'lat,lng,radius[unit]'.
    Returns (lat, lng, radius_meters) or None on any parse failure —
    bad input drops the filter rather than 400ing, mirroring the
    client-side parser's posture so UI typos degrade quietly.
    """
    if not raw:
        return None
    parts = [s.strip() for s in str(raw).split(",")]
    if len(parts) < 3:
        return None
    try:
        lat = float(parts[0])
        lng = float(parts[1])
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    import re as _re
    m = _re.match(r"^([\d.]+)\s*(km|m|meters|metre|meter)?$", parts[2].lower())
    if not m:
        return None
    try:
        value = float(m.group(1))
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    unit = (m.group(2) or "km").lower()
    radius_m = value if unit == "m" or unit.startswith("met") else value * 1000.0
    return (lat, lng, radius_m)


@router.get("/events/types")
def get_event_types(
    case_id: str = Query(...),
    report_keys: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Per-event-type counts (with geolocated subset counts)."""
    _require_case_access(case_id, current_user, db)
    types = neo4j_service.get_cellebrite_event_types(
        case_id=case_id,
        report_keys=_csv_param(report_keys),
    )
    return {"types": types}


@router.get("/events/tracks")
def get_event_tracks(
    case_id: str = Query(...),
    report_keys: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    simplify: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Per-device chronologically-ordered polyline tracks for the map."""
    _require_case_access(case_id, current_user, db)
    return neo4j_service.get_cellebrite_event_tracks(
        case_id=case_id,
        report_keys=_csv_param(report_keys),
        start_date=start_date,
        end_date=end_date,
        simplify=simplify,
    )


@router.get("/locations/tiles")
def get_location_tiles(
    case_id: str = Query(...),
    zoom: int = Query(6, ge=0, le=14),
    report_keys: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    bbox: Optional[str] = Query(
        None,
        description="Optional viewport: 'south,west,north,east' (degrees).",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """
    Tile-aggregated locations for the map at the requested zoom.

    Returns per-cell counts and top source apps so 100K+ raw points
    don't have to ship to the client just to be clustered. Frontend
    should switch to /events?event_types=location for street-level
    zooms (≥ 15) where raw points are smaller than tile boundaries.
    """
    _require_case_access(case_id, current_user, db)
    bbox_tuple = None
    if bbox:
        try:
            parts = [float(x.strip()) for x in bbox.split(",")]
            if len(parts) == 4:
                bbox_tuple = (parts[0], parts[1], parts[2], parts[3])
        except ValueError:
            # Bad bbox = drop the filter rather than 400 — the user
            # gets the unfiltered aggregation, which is still useful.
            bbox_tuple = None
    return neo4j_service.get_cellebrite_location_tiles(
        case_id=case_id,
        zoom=zoom,
        report_keys=_csv_param(report_keys),
        start_date=start_date,
        end_date=end_date,
        bbox=bbox_tuple,
    )


@router.get("/locations/suggestion-values")
def get_location_suggestion_values(
    case_id: str = Query(...),
    report_keys: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """
    Distinct values per searchable Location field for the search
    typeahead. Returns canonical sets covering the whole case so the
    dropdown surfaces values the 500-row sample would miss.
    """
    _require_case_access(case_id, current_user, db)
    return neo4j_service.get_cellebrite_location_suggestion_values(
        case_id=case_id,
        report_keys=_csv_param(report_keys),
    )


@router.get("/locations/visitors")
def get_location_visitors(
    case_id: str = Query(...),
    lat: float = Query(...),
    lon: float = Query(...),
    radius_m: float = Query(150.0, gt=0, le=5000,
                            description="Search radius in metres around (lat, lon)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """
    Devices that have a Location row within `radius_m` of (lat, lon).
    Used by the location rail's "Devices that visited this place"
    section so investigators can see whether a place was visited by
    one phone or several without leaving the rail.
    """
    _require_case_access(case_id, current_user, db)
    return neo4j_service.get_cellebrite_location_visitors(
        case_id=case_id,
        lat=lat,
        lon=lon,
        radius_m=radius_m,
    )


@router.get("/locations/in-tile")
def get_locations_in_tile(
    case_id: str = Query(...),
    cell_x: int = Query(...),
    cell_y: int = Query(...),
    cell_deg: float = Query(..., gt=0),
    report_keys: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """
    Raw location rows inside one aggregated tile — paginated list for
    the rail's tile-contents view (G3). cell_x/cell_y/cell_deg should
    be carried straight back from a tiles-endpoint response.
    """
    _require_case_access(case_id, current_user, db)
    return neo4j_service.get_cellebrite_locations_in_tile(
        case_id=case_id,
        cell_x=cell_x,
        cell_y=cell_y,
        cell_deg=cell_deg,
        report_keys=_csv_param(report_keys),
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


@router.get("/events/detail/{node_key}")
def get_event_detail(
    node_key: str,
    case_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Full event detail (all properties) for the detail drawer."""
    _require_case_access(case_id, current_user, db)
    detail = neo4j_service.get_cellebrite_event_detail(case_id, node_key)
    if not detail:
        raise HTTPException(status_code=404, detail="Event not found")
    # Resolve attachments for comms events
    file_ids = detail.get("attachment_file_ids") or []
    if file_ids:
        rec_map = evidence_storage.get_by_cellebrite_file_ids(case_id, list(file_ids))
        detail["attachments"] = [
            {
                "file_id": fid,
                "evidence_id": rec_map.get(fid, {}).get("id"),
                "category": rec_map.get(fid, {}).get("cellebrite_category"),
                "original_filename": rec_map.get(fid, {}).get("original_filename"),
                "size": rec_map.get(fid, {}).get("size"),
                "missing": rec_map.get(fid) is None,
            }
            for fid in file_ids
        ]
    return detail


@router.get("/events/{node_key}/related")
def get_event_related(
    node_key: str,
    case_id: str = Query(..., description="Case ID the event belongs to"),
    window_h: int = Query(24, ge=1, le=168, description="Hours either side of the anchor for the cross-channel pair window"),
    limit: int = Query(50, ge=1, le=200, description="Max rows per bucket (thread / around)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """
    Surface related comms for a clicked event so the right rail can show
    conversation thread + cross-channel context for the same parties
    without forcing the user to leave the rail.

    Returns:
        {
            "anchor": { node_key, label, timestamp, sender, recipient, thread_key },
            "thread": [event-row, ...],   # surrounding messages in same thread
            "around": [event-row, ...]    # comms with same parties within ±window_h
        }

    Cheap by design — keyset filters on (case_id, time, party_keys), no
    full text fan-out. Returns empty buckets gracefully when the anchor
    is a non-comms node (Location, CellTower, etc.).
    """
    _require_case_access(case_id, current_user, db)
    result = neo4j_service.get_event_related(
        case_id=case_id,
        node_key=node_key,
        window_h=window_h,
        limit=limit,
    )
    # Resolve attachments so the rail's related-message lists (thread +
    # around) can show the same inline media as the thread view.
    _resolve_attachments(case_id, result.get("thread", []))
    _resolve_attachments(case_id, result.get("around", []))
    return result


class IntersectionRunRequest(BaseModel):
    methods: List[str]
    report_keys: Optional[List[str]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    params: Optional[Dict[str, Dict[str, object]]] = None


@router.post("/intersections/run")
def run_intersections(
    req: IntersectionRunRequest,
    case_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Run one or more cross-device intersection detection methods on demand."""
    _require_case_access(case_id, current_user, db)
    return cellebrite_intersection_service.run_methods(
        case_id=case_id,
        methods=req.methods,
        report_keys=req.report_keys,
        start_date=req.start_date,
        end_date=req.end_date,
        params=req.params,
    )


# -------------------------------------------------------------------
# Files Explorer (Phase 5) endpoints
# -------------------------------------------------------------------


def _cellebrite_files_for_case(case_id: str, report_keys: Optional[List[str]]) -> List[dict]:
    """Return all cellebrite evidence records in the case (optionally scoped to reports)."""
    recs = evidence_storage.list_files(case_id=case_id)
    out = []
    for rec in recs:
        if rec.get("source_type") != "cellebrite":
            continue
        if report_keys and rec.get("cellebrite_report_key") not in report_keys:
            continue
        out.append(rec)
    return out


def _guess_device_path_segments(path: str) -> List[str]:
    """Derive nested folder segments from a stored_path or original filename."""
    if not path:
        return []
    p = str(path).replace("\\", "/")
    # Strip any Cellebrite Report folder prefix if present
    marker = "/files/"
    if marker in p.lower():
        p = p[p.lower().index(marker) + len(marker):]
    parts = [seg for seg in p.split("/") if seg and seg not in (".", "..")]
    # Drop the filename
    return parts[:-1] if len(parts) >= 1 else []


@router.get("/files")
def get_cellebrite_files(
    case_id: str = Query(...),
    report_keys: Optional[str] = Query(None),
    category: Optional[str] = Query(None, description="Image | Audio | Video | Text"),
    parent_label: Optional[str] = Query(None, description="Parent entity label filter"),
    source_app: Optional[str] = Query(None),
    device_path: Optional[str] = Query(None, description="Filter by device-path prefix"),
    tag: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="Substring match on filename"),
    only_relevant: bool = Query(False),
    # EXIF / geotag filters. `capture_after` / `capture_before` are
    # YYYY-MM-DD bounds on the file's EXIF capture time (falling back
    # to creation_time if capture_time is absent). `has_geotag=true`
    # keeps only files with a parsed lat/lon. All nullable so old
    # callers keep working.
    capture_after: Optional[str] = Query(None, description="YYYY-MM-DD lower bound on capture/creation time"),
    capture_before: Optional[str] = Query(None, description="YYYY-MM-DD upper bound on capture/creation time"),
    has_geotag: Optional[bool] = Query(None, description="True = only geotagged; False = only non-geotagged"),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Paginated Cellebrite file listing with parent-entity info resolved."""
    _require_case_access(case_id, current_user, db)
    rks = _csv_param(report_keys)
    files = _cellebrite_files_for_case(case_id, rks)

    # Apply filters that don't need graph resolution
    search_l = (search or "").strip().lower()
    if search_l:
        files = [f for f in files if search_l in (f.get("original_filename") or "").lower()]
    if category:
        files = [f for f in files if (f.get("cellebrite_category") or "").lower() == category.lower()]
    if tag:
        files = [f for f in files if tag in (f.get("tags") or [])]
    if entity_id:
        files = [f for f in files if entity_id in (f.get("linked_entity_ids") or [])]
    if only_relevant:
        files = [f for f in files if f.get("is_relevant")]

    # Geotag filter — cheap boolean exists on every record (false when
    # ingestion didn't find one or older records pre-fix). None means
    # "no filter".
    if has_geotag is True:
        files = [f for f in files if f.get("has_geotag")]
    elif has_geotag is False:
        files = [f for f in files if not f.get("has_geotag")]

    # Capture-time window. Falls back to creation_time when capture
    # time is absent (older reports / non-image files). Compares as
    # 10-char prefixes so any ISO 8601 input matches whether or not it
    # has a time / timezone suffix.
    if capture_after or capture_before:
        def _ts_prefix(rec):
            t = rec.get("capture_time") or rec.get("creation_time")
            return t[:10] if t else None
        if capture_after:
            files = [f for f in files if (_ts_prefix(f) or "") >= capture_after]
        if capture_before:
            files = [f for f in files if (_ts_prefix(f) or "9999-12-31") <= capture_before]

    # Resolve parents in one batched call so we can filter by parent_label / source_app
    model_ids = sorted({f.get("cellebrite_model_id") for f in files if f.get("cellebrite_model_id")})
    parents = {}
    if model_ids:
        from services.neo4j_service import resolve_file_parents, neo4j_service as ns
        parents = resolve_file_parents(ns._driver, case_id, model_ids)

    # Attach parent info + apply remaining filters
    enriched = []
    for f in files:
        mid = f.get("cellebrite_model_id")
        parent = parents.get(mid) if mid else None
        plabel = parent.get("label") if parent else None
        papp = parent.get("source_app") if parent else None
        if parent_label and (plabel or "Unlinked") != parent_label:
            continue
        if source_app and (papp or "").lower() != source_app.lower():
            continue
        path_segments = _guess_device_path_segments(
            f.get("stored_path") or f.get("original_filename") or ""
        )
        if device_path:
            prefix = [s for s in device_path.split("/") if s]
            if path_segments[: len(prefix)] != prefix:
                continue
        enriched.append({
            **f,
            "parent": parent,
            "device_path_segments": path_segments,
        })

    total = len(enriched)
    enriched = enriched[offset: offset + limit]
    return {"files": enriched, "total": total}


@router.get("/files/tree")
def get_cellebrite_files_tree(
    case_id: str = Query(...),
    report_keys: Optional[str] = Query(None),
    group_by: str = Query(
        "category",
        description="category | parent | app | path",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Build a nested tree of file counts for the Files Explorer tree pane."""
    _require_case_access(case_id, current_user, db)
    rks = _csv_param(report_keys)
    files = _cellebrite_files_for_case(case_id, rks)

    # Resolve parents once if needed
    parents: Dict[str, dict] = {}
    if group_by in ("parent", "app"):
        model_ids = sorted({f.get("cellebrite_model_id") for f in files if f.get("cellebrite_model_id")})
        if model_ids:
            from services.neo4j_service import resolve_file_parents, neo4j_service as ns
            parents = resolve_file_parents(ns._driver, case_id, model_ids)

    if group_by == "category":
        buckets: Dict[str, int] = {}
        for f in files:
            key = f.get("cellebrite_category") or "Other"
            buckets[key] = buckets.get(key, 0) + 1
        children = [
            {"key": k, "label": k, "count": v, "filter": {"category": k}}
            for k, v in sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
        ]
        return {
            "group_by": "category",
            "root": {"label": "All files", "count": len(files), "children": children},
        }

    if group_by == "parent":
        buckets: Dict[str, int] = {}
        for f in files:
            mid = f.get("cellebrite_model_id")
            p = parents.get(mid) if mid else None
            label = p.get("label") if p else "Unlinked"
            buckets[label] = buckets.get(label, 0) + 1
        children = [
            {"key": k, "label": k, "count": v, "filter": {"parent_label": k}}
            for k, v in sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
        ]
        return {
            "group_by": "parent",
            "root": {"label": "All files", "count": len(files), "children": children},
        }

    if group_by == "app":
        buckets: Dict[str, int] = {}
        for f in files:
            mid = f.get("cellebrite_model_id")
            p = parents.get(mid) if mid else None
            app = (p.get("source_app") if p else None) or "Unknown"
            buckets[app] = buckets.get(app, 0) + 1
        children = [
            {"key": k, "label": k, "count": v, "filter": {"source_app": k}}
            for k, v in sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
        ]
        return {
            "group_by": "app",
            "root": {"label": "All files", "count": len(files), "children": children},
        }

    if group_by == "path":
        # Build a true nested tree from device_path segments
        root = {"label": "All files", "count": len(files), "children": {}}

        def _ensure(children_dict, segment):
            if segment not in children_dict:
                children_dict[segment] = {"label": segment, "count": 0, "children": {}}
            return children_dict[segment]

        for f in files:
            segs = _guess_device_path_segments(
                f.get("stored_path") or f.get("original_filename") or ""
            )
            if not segs:
                # Bucket under top-level "(root)"
                _ensure(root["children"], "(root)")["count"] += 1
                continue
            cur = root
            path_acc = []
            for seg in segs:
                cur = _ensure(cur["children"], seg)
                cur["count"] += 1
                path_acc.append(seg)

        def _finalise(node, prefix=""):
            kids = node.get("children") or {}
            out_children = []
            for name, child in sorted(kids.items()):
                child_path = f"{prefix}/{name}".strip("/")
                finalized = _finalise(child, child_path)
                finalized["key"] = child_path
                finalized["filter"] = {"device_path": child_path}
                out_children.append(finalized)
            return {
                "label": node["label"],
                "count": node["count"],
                "children": out_children,
            }

        return {"group_by": "path", "root": _finalise(root)}

    raise HTTPException(status_code=400, detail=f"Unknown group_by: {group_by}")


# -------------------------------------------------------------------
# Phase 8: Overview drill-down detail endpoints
# Each returns paginated rows for a single (case_id, report_key) pair.
# -------------------------------------------------------------------


@router.get("/overview/contacts")
def overview_contacts(
    case_id: str = Query(...),
    report_key: str = Query(...),
    search: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Contacts on a single device with interaction counts."""
    _require_case_access(case_id, current_user, db)
    return neo4j_service.get_overview_contacts(
        case_id=case_id, report_key=report_key, search=search, limit=limit, offset=offset,
    )


@router.get("/contacts/unified")
def contacts_unified(
    case_id: str = Query(..., description="Case ID"),
    report_keys: Optional[str] = Query(
        None,
        description=(
            "Comma-separated phone-report keys to scope the rollup. "
            "When omitted, uses every cellebrite Person in the case."
        ),
    ),
    search: Optional[str] = Query(
        None,
        description="Substring filter on canonical number, display number, or any alias name.",
    ),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """
    Roll up Person nodes by canonical (E.164) phone number so the same
    human across multiple phones — even with different alias names —
    surfaces as a single row with the alias list attached.

    Returns rows ordered by phone-owner status, then total interaction
    volume desc.
    """
    _require_case_access(case_id, current_user, db)
    rk_list = None
    if report_keys:
        rk_list = [k.strip() for k in report_keys.split(",") if k.strip()]
    try:
        return neo4j_service.get_unified_contacts(
            case_id=case_id,
            report_keys=rk_list,
            search=search,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        # Surface the real Cypher/driver error rather than letting it
        # fall through as a plain 500 — the user otherwise sees
        # "Failed to load unified contacts" with no hint of what
        # went wrong. We also dump the traceback to the server log
        # for triage.
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Unified contacts query failed: {type(e).__name__}: {e}",
        ) from e


@router.get("/overview/calls")
def overview_calls(
    case_id: str = Query(...),
    report_key: str = Query(...),
    search: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Calls on a single device."""
    _require_case_access(case_id, current_user, db)
    return neo4j_service.get_overview_calls(
        case_id=case_id, report_key=report_key, search=search, limit=limit, offset=offset,
    )


@router.get("/overview/messages")
def overview_messages(
    case_id: str = Query(...),
    report_key: str = Query(...),
    search: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Individual messages on a single device."""
    _require_case_access(case_id, current_user, db)
    return neo4j_service.get_overview_messages(
        case_id=case_id, report_key=report_key, search=search, limit=limit, offset=offset,
    )


@router.get("/overview/locations")
def overview_locations(
    case_id: str = Query(...),
    report_key: str = Query(...),
    search: Optional[str] = Query(None),
    # Higher cap than the other overview endpoints because the
    # Locations tab is a map-first surface — investigators want
    # every point at once for trajectory + bounds-fitting, not a
    # paged 500. 10K covers location-heavy phones from real cases
    # (OPDMD28's busiest tile alone holds ~700 points; whole-device
    # totals run a few thousand).
    limit: int = Query(5000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Locations on a single device."""
    _require_case_access(case_id, current_user, db)
    return neo4j_service.get_overview_locations(
        case_id=case_id, report_key=report_key, search=search, limit=limit, offset=offset,
    )


@router.get("/overview/emails")
def overview_emails(
    case_id: str = Query(...),
    report_key: str = Query(...),
    search: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Emails on a single device."""
    _require_case_access(case_id, current_user, db)
    return neo4j_service.get_overview_emails(
        case_id=case_id, report_key=report_key, search=search, limit=limit, offset=offset,
    )


@router.get("/overview/contact/{contact_key}")
def overview_contact_detail(
    contact_key: str,
    case_id: str = Query(...),
    report_key: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Single contact detail + recent comms with that contact on this device."""
    _require_case_access(case_id, current_user, db)
    res = neo4j_service.get_overview_contact_detail(
        case_id=case_id, report_key=report_key, contact_key=contact_key,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Contact not found")
    return res


# -------------------------------------------------------------------
# Phase 9: Communications drill-down — per-contact chronological feed
# -------------------------------------------------------------------


@router.get("/comms/contact-feed/{contact_key}")
def comms_contact_feed(
    contact_key: str,
    case_id: str = Query(...),
    report_keys: Optional[str] = Query(None),
    types: Optional[str] = Query(None, description="Comma-separated: call,message,email"),
    # No artificial contact cap: a key contact's thread can run to tens of
    # thousands of messages (2026-05-25). Default page stays modest; the ceiling
    # is high enough to pull a whole thread, and the response carries the TRUE
    # total + a `truncated` flag so nothing is hidden silently.
    limit: int = Query(2000, ge=1, le=200000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Chronological feed of every call / message / email involving a contact."""
    _require_case_access(case_id, current_user, db)
    result = neo4j_service.get_contact_comms_feed(
        case_id=case_id,
        contact_key=contact_key,
        report_keys=_csv_param(report_keys),
        types=_csv_param(types),
        limit=limit,
        offset=offset,
    )
    # Resolve attachment file_ids → playable/viewable evidence (image/audio/
    # video), same as the thread + between feeds, so media renders in the
    # contact feed (Communications-tab drill + Comms-Center contact drawer)
    # instead of silently dropping (the bubbles read item.attachments).
    _resolve_attachments(case_id, result.get("items", []))
    return result
