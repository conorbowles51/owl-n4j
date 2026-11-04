"""Phone interpretation API, prefix ``/api/phones`` (02; placement fixed by 03 section 4.1).

Registry review queue (02 section 3.4): admin only, because the registry is global. Coverage map (02 section 7)
and the readings queue (02 sections 6.8, 6.10): anyone who can view the case; deciding needs case edit.
"""
from __future__ import annotations

import os
from datetime import date, datetime
from typing import List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from postgres.models.user import User
from postgres.session import get_db
from routers.case_access import authorize_case
from routers.users import get_current_db_user, require_admin, require_super_admin
from services.financial.quarantine_row import ActorError, actor_from_user
from services.phone import corrections, coverage, external_processing, identities, identity_decisions, readings, registry

router = APIRouter(prefix="/api/phones", tags=["phones"])

FlagState = Literal["open", "acknowledged", "mapping_needed", "mapped", "dismissed"]


class FlagTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to: Literal["open", "acknowledged", "mapping_needed", "dismissed"]
    reason: str = Field(min_length=1, max_length=4000)


class ExportDescribeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    filter: dict
    # "timeline_lens": the filter is the Timeline phone lens filter and the totals are the lens's (03 12.2)
    source: Literal["stream", "timeline_lens"] = "stream"


class ExportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    format: Literal["pdf", "rsmf"] = "pdf"
    source: Literal["stream", "timeline_lens", "collection", "finding", "dossier", "statement_check",
                    "analysis_result", "incident_window", "phone_profile"] = "stream"
    filter: dict
    options: dict = Field(default_factory=dict)


@router.post("/exports/describe")
def describe_export(body: ExportDescribeBody, db: Session = Depends(get_db),
                    user: User = Depends(get_current_db_user)):
    """What an export of this filter holds (03 section 12.2 steps 1 and 2): totals, phones, zone, unconfirmed rows."""
    from services.phone.exports import jobs
    authorize_case(db, body.case_id, user, ("case", "view"))
    try:
        out = jobs.describe_source(db.connection(), body.case_id, body.source, body.filter)
        # machine text on the attachments in scope: the dialog asks to confirm it or keep it marked (07 5 Media)
        out["machine_text"] = jobs.describe_machine_text(db.connection(), body.case_id, body.filter,
                                                         lens=body.source == "timeline_lens")
        return out
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc.errors()[0].get("msg")))


@router.post("/exports", status_code=202)
def create_export(body: ExportBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Queue an export (03 section 12.2); the phone worker draws it."""
    from services.phone.exports import jobs
    authorize_case(db, body.case_id, user, ("case", "view"))
    try:
        out = jobs.create(db.connection(), case_id=body.case_id, user_id=user.id, fmt=body.format,
                          source=body.source, filter_body=body.filter, options=body.options)
    except jobs.ExportError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc.errors()[0].get("msg")))
    db.commit()
    return out


@router.get("/exports")
def export_history(case_id: UUID = Query(...), db: Session = Depends(get_db),
                   user: User = Depends(get_current_db_user)):
    from services.phone.exports import jobs
    authorize_case(db, case_id, user, ("case", "view"))
    return {"case_id": str(case_id), "items": jobs.history(db.connection(), case_id)}


@router.get("/exports/{export_id}")
def export_state(export_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                 user: User = Depends(get_current_db_user)):
    from services.phone.exports import jobs
    authorize_case(db, case_id, user, ("case", "view"))
    out = jobs.get(db.connection(), case_id, export_id)
    if out is None:
        raise HTTPException(status_code=404, detail="That export is not in this case.")
    return out


@router.get("/exports/{export_id}/file")
def export_file(export_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                user: User = Depends(get_current_db_user)):
    from fastapi.responses import FileResponse

    from services.phone.exports import jobs
    authorize_case(db, case_id, user, ("case", "view"))
    r = jobs.file_of(db.connection(), case_id, export_id)
    if r is None or not r.storage_path or not os.path.exists(r.storage_path):
        raise HTTPException(status_code=404, detail="That export has no finished file.")
    # an RSMF file is an RFC 5322 message (Relativity's RSMF specification)
    media = "message/rfc822" if (r.filename or "").endswith(".rsmf") else "application/pdf"
    return FileResponse(r.storage_path, media_type=media, filename=r.filename,
                        headers={"X-Content-SHA256": r.sha256 or ""})


@router.get("/compare")
def compare_phones(case_id: UUID = Query(...), a: UUID = Query(...), b: UUID = Query(...),
                   person: Optional[str] = Query(None, max_length=512), db: Session = Depends(get_db),
                   user: User = Depends(get_current_db_user)):
    """Compare two phones of the case (07 J-16): messages and calls on both, only on one, only on the other."""
    from services.phone import compare as phone_compare
    authorize_case(db, case_id, user, ("case", "view"))
    try:
        return phone_compare.compare(db.connection(), case_id, a, b, person=person or None)
    except phone_compare.NotFound:
        raise HTTPException(status_code=404, detail="Both phones must be in this case.")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


class ReplacedLinksBody(BaseModel):
    case_id: UUID
    record_uids: list[str] = Field(default_factory=list)


@router.post("/records/replacements")
def replaced_links(body: ReplacedLinksBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """For linked phone records: whether each is on a replaced report, and the record with the equal natural key in
    the report that replaced it, or why none is offered (07 CO-9a and CO-9b). A read, so POST carries the list."""
    from services.phone import replaced_links as R
    authorize_case(db, body.case_id, user, ("case", "view"))
    try:
        return {"items": R.replacements(db.connection(), body.case_id, body.record_uids)}
    except R.TooMany as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/financial-presence")
def financial_presence(case_id: UUID = Query(...), db: Session = Depends(get_db),
                       user: User = Depends(get_current_db_user)):
    """Whether the case holds financial evidence, and the sentence every money part shows when it does not (07
    section 8). Case view only: a person with no financial access still sees why the money parts are empty."""
    from services.phone import money_presence
    authorize_case(db, case_id, user, ("case", "view"))
    return money_presence.presence(db.connection(), case_id)


@router.get("/crossings/payment/{transaction_id}")
def crossing_payment(transaction_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                     user: User = Depends(get_current_db_user)):
    """XF-1: phone activity around a payment, its counterparty's linked people, the payment date and a day either
    side, each count equal to the Conversations page it opens."""
    from services.phone import crossings
    authorize_case(db, case_id, user, ("case", "view"))
    try:
        return crossings.payment_activity(db, case_id, transaction_id)
    except crossings.NotInCase as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/crossings/payment/{transaction_id}/payee-dossier", status_code=201)
def crossing_payee_dossier(transaction_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                           user: User = Depends(get_current_db_user)):
    """XF-1: a payee that exists only on payments gets a person dossier, unlinked until a person links it."""
    from services.phone import crossings
    authorize_case(db, case_id, user, ("case", "edit"))
    try:
        out = crossings.create_payee_dossier(db, case_id, transaction_id, user)
        db.commit()
        return out
    except crossings.NotInCase as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/crossings/person")
def crossing_person(case_id: UUID = Query(...), dossier_id: Optional[UUID] = Query(None),
                    entity_key: Optional[str] = Query(None, max_length=512), db: Session = Depends(get_db),
                    user: User = Depends(get_current_db_user)):
    """XF-2: a Graph person (its dossier) to its messages and calls on the phones, the count Conversations shows."""
    from services.phone import crossings
    authorize_case(db, case_id, user, ("case", "view"))
    if not dossier_id and not entity_key:
        raise HTTPException(status_code=422, detail="Name a dossier or a graph entity.")
    try:
        return crossings.person_activity(db.connection(), case_id, dossier_id=dossier_id, entity_key=entity_key)
    except crossings.NotInCase as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/crossings/period")
def crossing_period(case_id: UUID = Query(...), from_day: date = Query(..., alias="from"),
                    to_day: date = Query(..., alias="to"), db: Session = Depends(get_db),
                    user: User = Depends(get_current_db_user)):
    """XF-4: what the phones did in a Timeline period, per phone, equal to the lens lanes and Conversations."""
    from services.phone import crossings
    authorize_case(db, case_id, user, ("case", "view"))
    if (to_day - from_day).days > 3700:
        raise HTTPException(status_code=422, detail="Choose a period of ten years or less.")
    try:
        return crossings.period_activity(db.connection(), case_id, from_day, to_day)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/crossings/counterparty-suggestions")
def crossing_counterparty_suggestions(case_id: UUID = Query(...), identity_key: str = Query(..., max_length=512),
                                      db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """XF-8: a phone contact's number or address used as a reviewed account reference suggests that account's
    payments. Suggested, not reviewed; nothing on the ledger changes."""
    from services.phone import crossings
    authorize_case(db, case_id, user, ("case", "view"))
    try:
        return crossings.counterparty_suggestions(db, case_id, identity_key)
    except crossings.NotInCase as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/findings/{entry_id}/explain")
def explain_finding(entry_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                    user: User = Depends(get_current_db_user)):
    """How this was found (07 J-17): generated from the finding's phone links; nothing in it is typed."""
    from services.phone import explain as phone_explain
    authorize_case(db, case_id, user, ("case", "view"))
    try:
        return phone_explain.explain(db.connection(), case_id, entry_id)
    except phone_explain.NotFound:
        raise HTTPException(status_code=404, detail="This finding is not in this case.")


class MapFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phones: list[UUID] = Field(default_factory=list)
    source_kinds: list[str] = Field(default_factory=list)
    affiliations: list[str] = Field(default_factory=list)
    from_instant: Optional[str] = None
    to_instant: Optional[str] = None
    include_no_time: bool = True


class MapSummaryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    filter: MapFilter = Field(default_factory=MapFilter)


class MapPointsBody(MapSummaryBody):
    bbox: list[float] = Field(min_length=4, max_length=4)
    zoom: float = Field(ge=0, le=24)


@router.post("/map/summary")
def phone_map_summary(body: MapSummaryBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """The Map phone layer's totals line and what cannot be placed (03 section 13.2)."""
    from services.phone import map as phone_map
    authorize_case(db, body.case_id, user, ("case", "view"))
    return phone_map.summary(db.connection(), body.case_id, body.filter.model_dump())


@router.post("/map/points")
def phone_map_points(body: MapPointsBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Phone positions in a viewport: points up to 5,000, else exact clusters with a limit (03 13.2, G-1)."""
    from services.phone import map as phone_map
    authorize_case(db, body.case_id, user, ("case", "view"))
    w, s, e, n = body.bbox
    if not (-180 <= w <= 180 and -180 <= e <= 180 and -90 <= s <= n <= 90):
        raise HTTPException(status_code=422, detail="The map area is not a valid longitude and latitude box.")
    return phone_map.points(db.connection(), body.case_id, body.bbox, body.zoom, body.filter.model_dump())


@router.get("/map/near")
def phone_map_near(case_id: UUID = Query(...), record_uid: UUID = Query(...), db: Session = Depends(get_db),
                   user: User = Depends(get_current_db_user)):
    """Show on Map from a message (03 section 3.6 item 7): positions on the same phone within 1 hour of it, or the
    nearest one and how far it is in time."""
    from services.phone import map as phone_map
    authorize_case(db, case_id, user, ("case", "view"))
    out = phone_map.near_record(db.connection(), case_id, record_uid)
    if out is None:
        raise HTTPException(status_code=404, detail="This record is not a message, call or email in this case.")
    return out


@router.get("/graph/pair")
def phone_graph_pair(case_id: UUID = Query(...), a: str = Query(..., max_length=512), b: str = Query(..., max_length=512),
                     from_instant: Optional[str] = Query(None, alias="from"), to_instant: Optional[str] = Query(None, alias="to"),
                     db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """A pair edge's counts for a time slice (03 R-3): equal to Conversations' Between A and B in that window."""
    from services.phone import graph_projection
    authorize_case(db, case_id, user, ("case", "view"))
    try:
        return graph_projection.pair_counts(db.connection(), case_id, a, b, from_instant, to_instant)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


class EdgeSubject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dossier_id: Optional[UUID] = None
    identity_key: Optional[str] = Field(None, max_length=512)


class LinkEdgesBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    from_instant: Optional[datetime] = None
    to_instant: Optional[datetime] = None
    subjects: list[EdgeSubject] = Field(min_length=2, max_length=20)
    slice: Optional[Literal["day", "week", "month", "year"]] = None
    group_scope: Literal["direct", "include_groups"] = "direct"
    collapse_copies: bool = True


class EdgeRecordsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    a: EdgeSubject
    b: EdgeSubject
    from_instant: Optional[datetime] = None
    to_instant: Optional[datetime] = None
    kind: Literal["messages", "calls", "emails", "payments"]
    cursor: int = Field(0, ge=0)
    limit: int = Field(200, ge=1, le=200)
    group_scope: Literal["direct", "include_groups"] = "direct"
    collapse_copies: bool = True


def _subject(s: EdgeSubject) -> dict:
    if bool(s.dossier_id) == bool(s.identity_key):
        raise HTTPException(status_code=422, detail="Each subject is a person (dossier_id) or one identity (identity_key).")
    return {"dossier_id": str(s.dossier_id)} if s.dossier_id else {"identity_key": s.identity_key}


def _aware(*instants):
    if any(i is not None and i.tzinfo is None for i in instants):
        raise HTTPException(status_code=422, detail="Dates are sent as instants with an offset.")


@router.post("/link-analysis/edges")
def phone_link_edges(body: LinkEdgesBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Combined communication and money edges (02 section 11.2, 05 section 17.8)."""
    from services.phone import link_edges
    authorize_case(db, body.case_id, user, ("case", "view"))
    _aware(body.from_instant, body.to_instant)
    try:
        return link_edges.edges(db.connection(), body.case_id, [_subject(s) for s in body.subjects],
                                from_instant=body.from_instant, to_instant=body.to_instant, slice_by=body.slice,
                                group_scope=body.group_scope, collapse_copies=body.collapse_copies)
    except link_edges.NotInCase as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/link-analysis/edge-records")
def phone_link_edge_records(body: EdgeRecordsBody, db: Session = Depends(get_db),
                            user: User = Depends(get_current_db_user)):
    """The records behind one edge's count; ``total`` equals the edge count (03 R-1, R-3)."""
    from services.phone import link_edges
    authorize_case(db, body.case_id, user, ("case", "view"))
    _aware(body.from_instant, body.to_instant)
    try:
        return link_edges.edge_records(db.connection(), body.case_id, _subject(body.a), _subject(body.b), body.kind,
                                       from_instant=body.from_instant, to_instant=body.to_instant,
                                       offset=body.cursor, limit=body.limit, group_scope=body.group_scope,
                                       collapse_copies=body.collapse_copies)
    except link_edges.NotInCase as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))


class MediaFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    phones: list[UUID] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    verification: list[str] = Field(default_factory=list)
    linked_to_message: Optional[bool] = None
    thread_key: Optional[str] = Field(None, max_length=512)


class MediaWindowBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filter: MediaFilter
    offset: int = Field(0, ge=0)
    limit: int = Field(200, ge=1, le=500)


@router.get("/threads/attachments")
def phone_thread_attachments(case_id: UUID = Query(...), thread_key: str = Query(..., max_length=512),
                             db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """The thread header's attachment counts: "14 attachments referenced, 3 not in the report" (03 section 6.7)."""
    from services.phone import media
    authorize_case(db, case_id, user, ("case", "view"))
    return media.thread_attachments(db.connection(), case_id, thread_key)


@router.post("/media/index")
def phone_media_index(body: MediaFilter, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Media totals (03 section 8.2): the grid total equals the phone summary's file count (M-4)."""
    from services.phone import media
    authorize_case(db, body.case_id, user, ("case", "view"))
    return media.index(db.connection(), body.case_id, body.model_dump(exclude={"case_id"}))


@router.post("/media/window")
def phone_media_window(body: MediaWindowBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    from services.phone import media
    authorize_case(db, body.filter.case_id, user, ("case", "view"))
    return media.window(db.connection(), body.filter.case_id, body.filter.model_dump(exclude={"case_id"}),
                        body.offset, body.limit)


# phone media types Python's table gets wrong or does not know (03 20.5 groups): .ts is MPEG-TS video, not a Qt
# translation file; without these the viewer is sent an attachment and never tries to play the file
PHONE_MEDIA_TYPES = {".ts": "video/mp2t", ".amr": "audio/amr", ".caf": "audio/x-caf", ".3gp": "video/3gpp",
                     ".3g2": "video/3gpp2", ".aif": "audio/aiff", ".aiff": "audio/aiff", ".m4a": "audio/mp4",
                     ".opus": "audio/ogg", ".mov": "video/quicktime", ".m4v": "video/mp4", ".mts": "video/mp2t"}


def media_type_of(name):
    import mimetypes
    import posixpath
    ext = posixpath.splitext((name or "").lower())[1]
    return PHONE_MEDIA_TYPES.get(ext) or mimetypes.guess_type(name)[0] or "application/octet-stream"


@router.get("/media-spread/index")
def phone_media_spread_index(case_id: UUID = Query(...), db: Session = Depends(get_db),
                             user: User = Depends(get_current_db_user)):
    """Media spread across phones, exact tier (05 section 11): true totals, by phone and by pair of phones."""
    from services.phone import media_spread
    authorize_case(db, case_id, user, ("case", "view"))
    return media_spread.index(db.connection(), case_id)


@router.get("/media-spread/window")
def phone_media_spread_window(case_id: UUID = Query(...), phones: list[UUID] = Query(default_factory=list),
                              common: Literal["all", "hide", "only"] = Query("all"), offset: int = Query(0, ge=0),
                              limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db),
                              user: User = Depends(get_current_db_user)):
    """One page of spread groups with their copies; ``phones`` keeps groups every listed phone holds. The page
    states the total under the filter."""
    from services.phone import media_spread
    authorize_case(db, case_id, user, ("case", "view"))
    return media_spread.window(db.connection(), case_id, {"phones": phones, "common": common}, offset, limit)


@router.get("/media/{file_uid}/content")
def phone_media_content(file_uid: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                        user: User = Depends(get_current_db_user), range_header: Optional[str] = Header(
                            None, alias="Range")):
    """One phone file's bytes, read in place from its container (03 8.3 viewer). Nothing is fetched elsewhere.
    A byte range is answered with 206, so audio and video can be seeked and Safari plays them."""
    from services.phone import media
    from services.ranged_stream import ranged_response
    authorize_case(db, case_id, user, ("case", "view"))
    try:
        name, size, opener = media.content(db.connection(), case_id, file_uid)
    except media.ContentRefused as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    from urllib.parse import quote
    kind = media_type_of(name)
    # evidence never runs in the app's origin: only passive types are shown inline, and nothing may script
    inline = (kind.startswith(("image/", "audio/", "video/")) and kind != "image/svg+xml") or kind in (
        "application/pdf", "text/plain")
    if not inline:
        kind = "application/octet-stream"
    return ranged_response(range_header, opener, size, kind, {
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; img-src 'self'; media-src 'self'; sandbox",
        "Content-Disposition": "%s; filename*=UTF-8''%s" % ("inline" if inline else "attachment", quote(name))})


@router.get("/media/{file_uid}/converted")
def phone_media_converted(file_uid: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                          user: User = Depends(get_current_db_user), range_header: Optional[str] = Header(
                              None, alias="Range")):
    """A converted copy of a phone file the browsers cannot play (03 8.3, 03 20.5): H.264/AAC in MP4, or AAC in
    M4A, made on demand and kept beside the case's files. The original is never changed; /content still sends it."""
    from pathlib import Path

    from config import EVIDENCE_DATA_ROOT
    from services.phone import media, media_convert
    authorize_case(db, case_id, user, ("case", "view"))
    try:
        _name, size, opener = media.content(db.connection(), case_id, file_uid)
    except media.ContentRefused as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    try:
        path, kind = media_convert.converted(Path(EVIDENCE_DATA_ROOT) / str(case_id), file_uid, size, opener)
    except media_convert.NotConvertible as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    from services.ranged_stream import ranged_response
    return ranged_response(range_header, lambda: open(path, "rb"), path.stat().st_size, kind, {
        "X-Content-Type-Options": "nosniff", "X-Converted-Copy": "1", "Cache-Control": "private, max-age=300",
        "Content-Security-Policy": "default-src 'none'; media-src 'self'; sandbox",
        "Content-Disposition": "inline"})


@router.get("/media/{file_uid}/thumbnail")
def phone_media_thumbnail(file_uid: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                          user: User = Depends(get_current_db_user)):
    """A small JPEG preview of one phone image for the Media grid, made in memory; the original is unchanged. A
    small file, or one no preview can be made of, is sent whole exactly as /content sends it."""
    from fastapi.responses import Response
    from services.phone import media
    authorize_case(db, case_id, user, ("case", "view"))
    try:
        made = media.thumbnail(db.connection(), case_id, file_uid)
    except media.ContentRefused as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    if made is None:
        return phone_media_content(file_uid, case_id, db, user, None)
    body, kind = made
    return Response(body, media_type=kind, headers={
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=300",
        "Content-Security-Policy": "default-src 'none'; img-src 'self'; sandbox"})


class DeriveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    kind: Literal["ocr", "transcript"]


@router.post("/media/{file_uid}/derive")
def phone_media_derive(file_uid: UUID, body: DeriveBody, db: Session = Depends(get_db),
                       user: User = Depends(get_current_db_user)):
    """Ask for a photo's text to be read or an audio file to be transcribed (03 8.3, M-3), by a model on this
    server. The result is machine-generated text stored beside the original; the original is never changed."""
    from services.phone import derive
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        out = derive.request(db.connection(), body.case_id, file_uid, body.kind, user_id=user.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except derive.DeriveError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    return out


class TranslateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID


class TranslateThreadBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    thread_key: str = Field(min_length=1, max_length=2000)


class TranslationsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    source_type: Literal["message", "derived_text"] = "message"
    keys: list[UUID] = Field(max_length=1000)


def _translate_call(db, fn):
    from services.phone import translate
    try:
        out = fn()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except translate.TranslateError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    return out


@router.post("/messages/{event_uid}/translate")
def phone_message_translate(event_uid: UUID, body: TranslateBody, db: Session = Depends(get_db),
                            user: User = Depends(get_current_db_user)):
    """Ask for one message to be translated to English on this server (05 17.5). The translation is machine-generated
    and stored beside the message, never replacing it; nothing is sent anywhere."""
    from services.phone import translate
    authorize_case(db, body.case_id, user, ("case", "edit"))
    return _translate_call(db, lambda: translate.request(db.connection(), body.case_id, "message", event_uid,
                                                         user_id=user.id))


@router.post("/media/derived/{derived_id}/translate")
def phone_derived_translate(derived_id: UUID, body: TranslateBody, db: Session = Depends(get_db),
                            user: User = Depends(get_current_db_user)):
    """Ask for a finished transcript (or text read from an image) to be translated, segment by segment (05 17.5)."""
    from services.phone import translate
    authorize_case(db, body.case_id, user, ("case", "edit"))
    return _translate_call(db, lambda: translate.request(db.connection(), body.case_id, "derived_text", derived_id,
                                                         user_id=user.id))


@router.post("/threads/translate")
def phone_thread_translate(body: TranslateThreadBody, db: Session = Depends(get_db),
                           user: User = Depends(get_current_db_user)):
    """Translate this conversation: every message with text, one translation each. Returns true counts, queued and
    left out by reason."""
    from services.phone import translate
    authorize_case(db, body.case_id, user, ("case", "edit"))
    return _translate_call(db, lambda: translate.request_thread(db.connection(), body.case_id, body.thread_key,
                                                                user_id=user.id))


@router.post("/translations")
def phone_translations(body: TranslationsBody, db: Session = Depends(get_db),
                       user: User = Depends(get_current_db_user)):
    """The translation to show for each of a set of messages (or machine texts): open, else the latest finished
    (marked stale when the text has been corrected since), else the latest failed."""
    from services.phone import translate
    authorize_case(db, body.case_id, user, ("case", "view"))
    got = translate.latest_for(db.connection(), body.case_id, body.source_type, body.keys)
    return {"case_id": str(body.case_id), "items": got}


@router.get("/media/derived/{derived_id}/translations")
def phone_derived_translations(derived_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                               user: User = Depends(get_current_db_user)):
    from services.phone import translate
    authorize_case(db, case_id, user, ("case", "view"))
    return {"items": translate.list_for(db.connection(), case_id, "derived_text", derived_id)}


class CorrectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    text: str
    reason: str


class ConfirmBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    note: str = ""


def _machine_text_call(db, fn):
    from services.phone import machine_text
    try:
        out = fn()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except machine_text.MachineTextError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    return out


@router.post("/media/derived/{derived_id}/correct")
def phone_media_derived_correct(derived_id: UUID, body: CorrectBody, db: Session = Depends(get_db),
                                user: User = Depends(get_current_db_user)):
    """A person corrects machine-generated text (07 4.6): the machine text stays and stays visible; the corrected
    text is the one searched, quoted and exported. One decision in the case ledger per save."""
    from services.phone import machine_text
    authorize_case(db, body.case_id, user, ("case", "edit"))
    return _machine_text_call(db, lambda: machine_text.correct(db, case_id=body.case_id, derived_id=derived_id,
                                                               text=body.text, reason=body.reason, user=user))


@router.post("/media/derived/{derived_id}/confirm")
def phone_media_derived_confirm(derived_id: UUID, body: ConfirmBody, db: Session = Depends(get_db),
                                user: User = Depends(get_current_db_user)):
    """A person checked machine-generated text against the original and it stands (07 4.6, M-7)."""
    from services.phone import machine_text
    authorize_case(db, body.case_id, user, ("case", "edit"))
    return _machine_text_call(db, lambda: machine_text.confirm(db, case_id=body.case_id, derived_id=derived_id,
                                                               user=user, note=body.note))


class AcceptBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    dossier_id: UUID
    category: str = Field(min_length=1, max_length=128)


@router.post("/media/derived/{derived_id}/accept-into-assessment", status_code=201)
def phone_media_derived_accept(derived_id: UUID, body: AcceptBody, db: Session = Depends(get_db),
                               user: User = Depends(get_current_db_user)):
    """CO-18: accept machine text into a dossier assessment, stored ai_assisted with "Read by <model>, accepted by
    <name>". The text keeps its own mark until a person confirms it."""
    from services.dossier_service import DossierNotFound
    from services.phone import machine_text
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        return _machine_text_call(db, lambda: machine_text.accept_into_assessment(
            db, case_id=body.case_id, derived_id=derived_id, dossier_id=body.dossier_id, category=body.category,
            user=user))
    except DossierNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


class BatchScope(BaseModel):
    """The Media filter without its case (the case is the body's): unknown keys are refused, never ignored."""
    model_config = ConfigDict(extra="forbid")
    phones: list[UUID] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    verification: list[str] = Field(default_factory=list)
    linked_to_message: Optional[bool] = None


class BatchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    kind: Literal["ocr", "transcript"]
    filter: BatchScope = Field(default_factory=BatchScope)
    scope_words: str = Field(default="", max_length=500)


def _batch_scope(case_id, body_filter: BatchScope):
    return body_filter.model_dump(mode="json", exclude_defaults=True)


@router.post("/media/derive-batches/describe")
def phone_media_batch_describe(body: BatchBody, db: Session = Depends(get_db),
                               user: User = Depends(get_current_db_user)):
    """How many files a batch reading of this Media scope would read, and what it leaves out and why (M-5)."""
    from services.phone import derive_batch
    authorize_case(db, body.case_id, user, ("case", "view"))
    try:
        return derive_batch.describe(db.connection(), body.case_id, body.kind, _batch_scope(body.case_id, body.filter))
    except derive_batch.BatchError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/media/derive-batches", status_code=201)
def phone_media_batch_create(body: BatchBody, db: Session = Depends(get_db),
                             user: User = Depends(get_current_db_user)):
    """Queue a reading of every eligible file of one kind in a Media scope, on this server (M-5)."""
    from services.phone import derive_batch
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        out = derive_batch.create(db.connection(), case_id=body.case_id, kind=body.kind,
                                  scope=_batch_scope(body.case_id, body.filter), scope_words=body.scope_words or None,
                                  user_id=user.id)
    except derive_batch.BatchError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    return out


@router.get("/media/derive-batches")
def phone_media_batch_status(case_id: UUID = Query(...), db: Session = Depends(get_db),
                             user: User = Depends(get_current_db_user)):
    """This case's batch readings with true counts by state, newest first (the job tray polls this every second)."""
    from services.phone import derive_batch
    authorize_case(db, case_id, user, ("case", "view"))
    return {"case_id": str(case_id), "items": derive_batch.status(db.connection(), case_id)}


@router.post("/media/derive-batches/{batch_id}/cancel")
def phone_media_batch_cancel(batch_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                             user: User = Depends(get_current_db_user)):
    """Stop a batch: readings not yet started are removed; every finished reading is kept."""
    from services.phone import derive_batch
    authorize_case(db, case_id, user, ("case", "edit"))
    try:
        out = derive_batch.cancel(db.connection(), case_id, batch_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    db.commit()
    return out


class ImageIndexBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID


class ImageSearchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    query: str = Field(min_length=1, max_length=300)
    limit: int = Field(24, ge=1, le=200)


def _image_search_call(fn, db=None):
    from services.phone import image_search
    try:
        out = fn()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except image_search.ImageSearchBusy as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except image_search.ImageSearchError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if db is not None:
        db.commit()
    return out


@router.post("/media/image-index/describe")
def phone_image_index_describe(body: ImageIndexBody, db: Session = Depends(get_db),
                               user: User = Depends(get_current_db_user)):
    """True counts for indexing this case's images for search by description (05 17.6): the images it would index
    and every image it leaves out, by reason; whether the model is installed on this server."""
    from services.phone import image_search
    authorize_case(db, body.case_id, user, ("case", "view"))
    return _image_search_call(lambda: image_search.describe(db.connection(), body.case_id))


@router.post("/media/image-index", status_code=201)
def phone_image_index_create(body: ImageIndexBody, db: Session = Depends(get_db),
                             user: User = Depends(get_current_db_user)):
    """Index this case's images for search, on this server: one row per eligible image, drawn by the media worker."""
    from services.phone import image_search
    authorize_case(db, body.case_id, user, ("case", "edit"))
    return _image_search_call(lambda: image_search.create(db.connection(), case_id=body.case_id, user_id=user.id), db)


@router.get("/media/image-index")
def phone_image_index_status(case_id: UUID = Query(...), db: Session = Depends(get_db),
                             user: User = Depends(get_current_db_user)):
    """This case's indexing jobs with true counts by state and failures by reason, newest first."""
    from services.phone import image_search
    authorize_case(db, case_id, user, ("case", "view"))
    return {"case_id": str(case_id), "items": image_search.status(db.connection(), case_id)}


@router.post("/media/image-index/{job_id}/cancel")
def phone_image_index_cancel(job_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                             user: User = Depends(get_current_db_user)):
    """Stop indexing: images not yet started are removed from the job; every indexed image is kept."""
    from services.phone import image_search
    authorize_case(db, case_id, user, ("case", "edit"))
    return _image_search_call(lambda: image_search.cancel(db.connection(), case_id, job_id), db)


@router.post("/media/image-search")
def phone_image_search(body: ImageSearchBody, db: Session = Depends(get_db),
                       user: User = Depends(get_current_db_user)):
    """Find images by description (05 17.6): the case's indexed images ranked by a model on this server. A result
    points to an image; it does not describe it. The description is not stored and is not sent anywhere."""
    from services.phone import image_search
    authorize_case(db, body.case_id, user, ("case", "view"))
    return _image_search_call(lambda: image_search.search(db.connection(), body.case_id, body.query, body.limit))


@router.get("/media/{file_uid}/derived")
def phone_media_derived(file_uid: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                        user: User = Depends(get_current_db_user)):
    from services.phone import derive
    authorize_case(db, case_id, user, ("case", "view"))
    return {"file_uid": str(file_uid), "items": derive.list_for(db.connection(), case_id, file_uid)}


@router.get("/media/{file_uid}")
def phone_media_detail(file_uid: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                       user: User = Depends(get_current_db_user)):
    """One file: hashes, state, and every message that carried it with the mechanism that found it (M-1, M-2)."""
    from services.phone import media
    authorize_case(db, case_id, user, ("case", "view"))
    out = media.detail(db.connection(), case_id, file_uid)
    if out is None:
        raise HTTPException(status_code=404, detail="This file is not in this case.")
    return out


@router.get("/registry/flags")
def list_registry_flags(state: Optional[FlagState] = None, db: Session = Depends(get_db),
                        _: User = Depends(require_admin)):
    flags = registry.list_flags(db, state)
    return {"total": len(flags), "flags": [dict(f, raised_at=f["raised_at"].isoformat(),
                                                raised_by_extraction_id=(str(f["raised_by_extraction_id"])
                                                                         if f["raised_by_extraction_id"] else None))
                                           for f in flags]}


@router.post("/registry/flags/{flag_id}/transition")
def transition_registry_flag(flag_id: int, body: FlagTransition, db: Session = Depends(get_db),
                             user: User = Depends(require_admin)):
    try:
        out = registry.transition_flag(db, flag_id, body.to, body.reason, actor_name=user.name,
                                       actor_email=user.email, actor_user_id=user.id)
    except registry.TransitionRefused as exc:
        db.rollback()
        raise HTTPException(status_code=409 if "cannot become" in str(exc) else 422, detail=str(exc))
    db.commit()
    return out


@router.get("/{extraction_id}/coverage")
def extraction_coverage(extraction_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                        user: User = Depends(get_current_db_user)):
    """What Loupe reads of one phone, per type and field, beside the production's own selection statement."""
    authorize_case(db, case_id, user, ("case", "view"))
    try:
        return coverage.compute(db.connection(), extraction_id, case_id)
    except coverage.NotFound:
        raise HTTPException(status_code=404, detail="Phone extraction not found in this case")


class ConfirmReading(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    viewed: list[str] = Field(default_factory=list, max_length=200)
    opened: Optional[list[str]] = Field(default=None, max_length=200)
    note: Optional[str] = Field(default=None, max_length=4000)
    expected_status: Literal["open", "confirmed", "corrected"] = "open"


class CorrectReading(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    choice: str = Field(min_length=1, max_length=300)
    reason: str = Field(min_length=1, max_length=4000)
    scope: Literal["this_phone", "same_format"] = "this_phone"
    note: Optional[str] = Field(default=None, max_length=4000)
    expected_status: Literal["open", "confirmed", "corrected"] = "open"


def _actor(user):
    try:
        return actor_from_user(user)
    except ActorError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _reading_error(db, exc):
    db.rollback()
    raise HTTPException(status_code=exc.status, detail=str(exc))


@router.get("/readings")
def list_readings(case_id: UUID = Query(...), db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """The system's readings of the case's phones as plain sentences, most records first (07 J-8)."""
    authorize_case(db, case_id, user, ("case", "view"))
    return readings.queue(db.connection(), case_id)


@router.get("/readings/progress")
def readings_progress(case_id: UUID = Query(...), db: Session = Depends(get_db),
                      user: User = Depends(get_current_db_user)):
    authorize_case(db, case_id, user, ("case", "view"))
    return {"phones": readings.progress(db.connection(), case_id)}


@router.get("/readings/{judgement_id}/examples")
def reading_examples(judgement_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                     user: User = Depends(get_current_db_user)):
    authorize_case(db, case_id, user, ("case", "view"))
    try:
        return readings.examples(db.connection(), case_id, judgement_id)
    except readings.ReadingError as exc:
        _reading_error(db, exc)


@router.post("/readings/{judgement_id}/confirm")
def confirm_reading(judgement_id: UUID, body: ConfirmReading, db: Session = Depends(get_db),
                    user: User = Depends(get_current_db_user)):
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        out = readings.confirm(db, body.case_id, judgement_id, viewed=body.viewed, opened=body.opened,
                               note=body.note, actor=_actor(user), expected_status=body.expected_status)
    except readings.ReadingError as exc:
        _reading_error(db, exc)
    db.commit()
    return out


@router.post("/readings/{judgement_id}/correct")
def correct_reading(judgement_id: UUID, body: CorrectReading, db: Session = Depends(get_db),
                    user: User = Depends(get_current_db_user)):
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        out = readings.correct(db, body.case_id, judgement_id, choice_id=body.choice, reason=body.reason,
                               scope=body.scope, note=body.note, actor=_actor(user),
                               expected_status=body.expected_status)
    except readings.ReadingError as exc:
        _reading_error(db, exc)
    db.commit()
    return out


class IdentityDecision(BaseModel):
    """02 section 8.8 endpoint (spec 03 section 10.4)."""
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    decision: Literal["link_phone_identity", "unlink_phone_identity", "split", "reject_phone_identity_link",
                      "restore_phone_identity_link"]
    identity_keys: list[str] = Field(min_length=1, max_length=500)
    dossier_id: Optional[UUID] = None
    new_person_name: Optional[str] = Field(default=None, max_length=255)
    target_identity_key: Optional[str] = Field(default=None, max_length=600)
    reason: Optional[str] = Field(default=None, max_length=4000)
    note: Optional[str] = Field(default=None, max_length=4000)
    reasons_shown: Optional[list[dict]] = Field(default=None, max_length=20)
    expected_revision: Optional[str] = Field(default=None, max_length=64)


@router.get("/identity-suggestions")
def identity_suggestions(case_id: UUID = Query(...), db: Session = Depends(get_db),
                         user: User = Depends(get_current_db_user)):
    """Suggested links, recomputed from the current sightings, links and dossier contacts (8.7)."""
    authorize_case(db, case_id, user, ("case", "view"))
    conn = db.connection()
    identity_decisions.compute_suggestions(conn, case_id)
    out = identity_decisions.suggestions(conn, case_id)
    decided = identity_decisions.decided_count(conn, case_id)
    db.commit()
    # "12 of 36 decided" (07 J-7): decided suggestions against decided plus open
    return {"case_id": str(case_id), "total": len(out), "decided": decided, "suggestions": out}


@router.get("/identities/{identity_key:path}")
def identity_detail(identity_key: str, case_id: UUID = Query(...), db: Session = Depends(get_db),
                    user: User = Depends(get_current_db_user)):
    """One identity: its value, each phone's names, its link and the revision a decision must name."""
    authorize_case(db, case_id, user, ("case", "view"))
    from sqlalchemy import text as sql
    conn = db.connection()
    row = conn.execute(sql("SELECT id, identity_key, kind, subkind, value_display, sighting_count, phone_count FROM "
                           "phone_identities WHERE case_id = :c AND identity_key = :k"),
                       {"c": case_id, "k": identity_key}).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="This identity is not in this case")
    labels = readings.phone_labels(conn, case_id)
    names = [{"phone": labels.get(str(n.extraction_id)), "name": n.name, "basis": n.basis,
              "occurrences": n.occurrences, "is_phone_name": n.is_phone_name}
             for n in conn.execute(sql("SELECT extraction_id, name, basis, occurrences, is_phone_name FROM "
                                       "pv_identity_name WHERE identity_id = :i ORDER BY is_phone_name DESC, "
                                       "occurrences DESC, name"), {"i": row.id})]
    link = conn.execute(sql("SELECT l.dossier_id, p.display_name FROM phone_identity_links l LEFT JOIN case_profiles p "
                            "ON p.id = l.dossier_id WHERE l.identity_id = :i"), {"i": row.id}).one_or_none()
    return {"id": str(row.id), "identity_key": row.identity_key, "kind": row.kind, "subkind": row.subkind,
            "value_display": row.value_display, "sightings": row.sighting_count, "phones": row.phone_count,
            "names": names, "linked_dossier": {"id": str(link[0]), "name": link[1]} if link else None,
            "can_be_a_person": not (row.kind == "other" and row.subkind == "group"),
            "expected_revision": identity_decisions.links_revision(conn, [row.id])}


@router.post("/identity-decisions")
def identity_decision(body: IdentityDecision, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        out = identity_decisions.decide(
            db, case_id=body.case_id, decision=body.decision, identity_keys=body.identity_keys, actor=_actor(user),
            user=user, dossier_id=body.dossier_id, new_person_name=body.new_person_name, reason=body.reason,
            note=body.note, reasons_shown=body.reasons_shown, expected_revision=body.expected_revision,
            target_identity_key=body.target_identity_key)
    except identity_decisions.IdentityDecisionError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status, detail=str(exc))
    db.commit()
    return out


@router.get("/{extraction_id}/profile")
def phone_profile(extraction_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                  user: User = Depends(get_current_db_user)):
    """Phone summary (03 section 7): every number a count over the read views, each with the list it opens. A phone
    of another case is 404."""
    from services.phone import profile as phone_profile_service
    authorize_case(db, case_id, user, ("case", "view"))
    try:
        return phone_profile_service.profile(db.connection(), case_id, extraction_id)
    except phone_profile_service.NotFound:
        raise HTTPException(status_code=404, detail="This phone is not in this case.")


@router.get("/{extraction_id}/since")
def phone_since(extraction_id: UUID, case_id: UUID = Query(...), since: datetime = Query(...),
                db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Since you last looked (03 section 7.3, 07 J-15): counts per change kind after the viewer's last visit."""
    from services.phone import profile as phone_profile_service
    authorize_case(db, case_id, user, ("case", "view"))
    if since.tzinfo is None:
        raise HTTPException(status_code=422, detail="The time of the last visit needs its offset from UTC.")
    return phone_profile_service.since_last_looked(db.connection(), case_id, extraction_id, since, user.id)


@router.get("/{extraction_id}/owner")
def extraction_owner(extraction_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                     user: User = Depends(get_current_db_user)):
    """The owner of one phone: computed with every candidate, and a person's decision when there is one (8.6)."""
    authorize_case(db, case_id, user, ("case", "view"))
    from sqlalchemy import text as sql
    if not db.connection().execute(sql("SELECT 1 FROM phone_extractions WHERE id = :e AND case_id = :c"),
                                   {"e": extraction_id, "c": case_id}).scalar():
        raise HTTPException(status_code=404, detail="Phone extraction not found in this case")
    out = identities.owner(db.connection(), extraction_id)
    for cnd in out["candidates"]:
        cnd["identity_id"] = str(cnd["identity_id"]) if cnd["identity_id"] else None
    return out


class ExternalProcessingDecision(BaseModel):
    """02 sections 8.8, 9.8: embeddings, transcription, translation, image search and geocoding of one phone."""
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    allow: bool
    reason: str = Field(min_length=1, max_length=4000)


@router.get("/{extraction_id}/external-processing")
def get_external_processing(extraction_id: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                            user: User = Depends(get_current_db_user)):
    authorize_case(db, case_id, user, ("case", "view"))
    return external_processing.state(db.connection(), case_id, extraction_id)


@router.post("/{extraction_id}/external-processing")
def set_external_processing(extraction_id: UUID, body: ExternalProcessingDecision, db: Session = Depends(get_db),
                            user: User = Depends(require_super_admin)):
    """Sending a phone's material to a third-party service is decided by the system owner for a case (9.8)."""
    authorize_case(db, body.case_id, user, ("case", "view"))
    try:
        out = external_processing.decide(db, case_id=body.case_id, extraction_id=extraction_id, allow=body.allow,
                                         reason=body.reason, actor=_actor(user))
    except external_processing.ExternalProcessingError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    db.commit()
    return out


class ProjectionRebuild(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID


@router.post("/projection/rebuild")
def rebuild_projection(body: ProjectionRebuild, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Rebuild the case graph's phone layer from Postgres now (02 section 9.5)."""
    authorize_case(db, body.case_id, user, ("case", "edit"))  # derived data only; anyone who can edit the case
    from postgres.session import _get_engine
    from services.phone import graph_projection
    out = graph_projection.project_case(_get_engine(), body.case_id)
    return {"case_id": str(body.case_id), **{k: v for k, v in out.items()}}


class ValueCorrection(BaseModel):
    """02 section 10.4: one captured value, corrected with the person's own reason; the original stays visible."""
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    field_path: str = Field(min_length=1, max_length=400)
    value_index: int = Field(default=0, ge=0)
    corrected_text: str = Field(max_length=200000)
    reason: str = Field(min_length=1, max_length=4000)
    expected_revision: Optional[str] = Field(default=None, max_length=64)


def _correction_error(db, exc):
    db.rollback()
    raise HTTPException(status_code=exc.status, detail=str(exc))


@router.post("/records/{record_uid}/corrections")
def correct_value(record_uid: UUID, body: ValueCorrection, db: Session = Depends(get_db),
                  user: User = Depends(get_current_db_user)):
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        out = corrections.correct_value(db, case_id=body.case_id, record_uid=record_uid, field_path=body.field_path,
                                        value_index=body.value_index, corrected_text=body.corrected_text,
                                        reason=body.reason, actor=_actor(user),
                                        expected_revision=body.expected_revision)
    except corrections.CorrectionError as exc:
        _correction_error(db, exc)
    db.commit()
    return out


@router.get("/records/{record_uid}/corrections")
def value_corrections(record_uid: UUID, case_id: UUID = Query(...), db: Session = Depends(get_db),
                      user: User = Depends(get_current_db_user)):
    """Every correction of a record's values, oldest first: the machine value, each correction, who and why."""
    authorize_case(db, case_id, user, ("case", "view"))
    rows = [c for c in corrections.chain(db.connection(), record_uid)]
    from sqlalchemy import text as sql
    if rows and not db.connection().execute(sql("SELECT 1 FROM phone_value_corrections WHERE record_uid = :r AND "
                                                "case_id = :c LIMIT 1"), {"r": record_uid, "c": case_id}).scalar():
        raise HTTPException(status_code=404, detail="This record is not in this case")
    return {"record_uid": str(record_uid), "corrections": rows}


class ClockOffset(BaseModel):
    """02 section 10.1: the device clock was off by ``offset_seconds`` (added to the recorded time) in a period."""
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    offset_seconds: int
    start: Optional[str] = Field(default=None, max_length=64)
    end: Optional[str] = Field(default=None, max_length=64)
    reason: str = Field(min_length=1, max_length=4000)


@router.post("/{extraction_id}/clock-offset")
def set_clock_offset(extraction_id: UUID, body: ClockOffset, db: Session = Depends(get_db),
                     user: User = Depends(get_current_db_user)):
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        out = corrections.set_clock_offset(db, case_id=body.case_id, extraction_id=extraction_id,
                                           offset_seconds=body.offset_seconds, start=body.start, end=body.end,
                                           reason=body.reason, actor=_actor(user))
    except corrections.CorrectionError as exc:
        _correction_error(db, exc)
    db.commit()
    return out


class OwnerDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    identity_key: str = Field(min_length=1, max_length=512)
    reason: str = Field(min_length=1, max_length=4000)


@router.post("/{extraction_id}/owner")
def set_owner(extraction_id: UUID, body: OwnerDecision, db: Session = Depends(get_db),
              user: User = Depends(get_current_db_user)):
    """Set whose phone this is (03 section 7.3); written as a ``set_phone_owner`` decision with its reason."""
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        out = corrections.set_owner(db, case_id=body.case_id, extraction_id=extraction_id,
                                    identity_key=body.identity_key, reason=body.reason, actor=_actor(user))
    except corrections.CorrectionError as exc:
        _correction_error(db, exc)
    db.commit()
    return out


class LabelDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    label: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=4000)


@router.post("/{extraction_id}/label")
def set_label(extraction_id: UUID, body: LabelDecision, db: Session = Depends(get_db),
              user: User = Depends(get_current_db_user)):
    """Name a phone (02 section 12.3); written as a ``set_phone_label`` decision with its reason."""
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        out = corrections.set_label(db, case_id=body.case_id, extraction_id=extraction_id, label=body.label,
                                    reason=body.reason, actor=_actor(user))
    except corrections.CorrectionError as exc:
        _correction_error(db, exc)
    db.commit()
    return out


class AcceptDifference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    reason: str = Field(min_length=1, max_length=4000)


RESTART_FAILED = ("The difference is accepted and recorded, but reading could not be restarted: %s Choose Resume on "
                  "this phone's evidence item to continue.")


def _resume_capture(job_id, case_id) -> dict:
    """Resume the phone's capture job through the engine's own Resume (01 section 10.4) after an acceptance."""
    if not job_id:
        return {"state": "not_restarted", "words": RESTART_FAILED % "this phone has no reading job on record."}
    import anyio.from_thread

    from services import evidence_engine_client
    try:
        out = anyio.from_thread.run(evidence_engine_client.control_job, job_id, str(case_id), "resume")
    except Exception as exc:  # the decision stands; the person is told the restart did not happen and why
        detail = getattr(getattr(exc, "response", None), "text", None) or exc.__class__.__name__
        return {"state": "not_restarted", "words": RESTART_FAILED % ("the reading service answered: %s." % detail[:300])}
    return {"state": out.get("state") or "queued",
            "words": "The difference is accepted. Reading continues from the check; the phone summary updates as it goes."}


@router.post("/{extraction_id}/reconciliation/accept")
def accept_reconciliation_difference(extraction_id: UUID, body: AcceptDifference, db: Session = Depends(get_db),
                                     user: User = Depends(get_current_db_user)):
    """Accept the difference (07 J-1, 03 section 7.3): an ``accept_phone_reconciliation_difference`` decision with a
    typed reason, then the held capture resumes and passes exactly the accepted differences (02 decision 37)."""
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        out = corrections.accept_reconciliation_difference(db, case_id=body.case_id, extraction_id=extraction_id,
                                                           reason=body.reason, actor=_actor(user))
    except corrections.CorrectionError as exc:
        _correction_error(db, exc)
    db.commit()
    out["restart"] = _resume_capture(out.pop("engine_job_id"), body.case_id)
    return out


# ---- screens: phone list, settings, streams, threads, record panel (03 sections 4 to 6) ----------------------------

import logging as _logging  # noqa: E402
import uuid as _uuid  # noqa: E402

from pydantic import ValidationError  # noqa: E402

from services.phone import records as phone_records  # noqa: E402
from services.phone import streams  # noqa: E402
from services.phone import time_display  # noqa: E402
from services.phone.filters import StreamFilter  # noqa: E402

_log = _logging.getLogger(__name__)
LIST_FAILED = "The message list could not be loaded."


def _failure(message: str, exc: Exception) -> HTTPException:
    """3.8: an unexpected failure says what failed and gives a reference to quote, never 'unknown error'."""
    ref = _uuid.uuid4().hex[:10]
    _log.exception("phone screen request failed, reference %s", ref, exc_info=exc)
    return HTTPException(status_code=500, detail={"message": message, "reference": ref,
                                                  "text": "%s Reference: %s." % (message, ref)})


def _filter(body: dict, db, user, permission=("case", "view")) -> StreamFilter:
    try:
        f = StreamFilter.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=[{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()])
    authorize_case(db, UUID(f.case_id), user, permission)
    return f


@router.get("")
def list_phones(case_id: UUID = Query(...), db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """``{"phones": [PhoneSummary]}`` (03 section 4.4). An empty list means the case has no phone; the sidebar's
    Phones group shows only when it is not empty (5.2)."""
    authorize_case(db, case_id, user, ("case", "view"))
    out = phone_records.phones(db.connection(), case_id)
    return {"case_id": str(case_id), "phones": out, "total": len(out),
            "case_zone": streams.case_zone(db.connection(), case_id)}


class DisplaySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    time_zone: str = Field(min_length=1, max_length=64)


@router.get("/settings")
def get_settings(case_id: UUID = Query(...), db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """The case time zone for phone data (4.6): the setting if one is saved, else the default and why."""
    authorize_case(db, case_id, user, ("case", "view"))
    from sqlalchemy import text as sql
    row = db.connection().execute(sql(
        "SELECT s.time_zone, s.updated_at, u.name FROM case_display_settings s LEFT JOIN users u ON u.id = s.updated_by "
        "WHERE s.case_id = :c"), {"c": case_id}).first()
    zone = streams.case_zone(db.connection(), case_id)
    return {"case_id": str(case_id), "time_zone": row.time_zone if row else None, "effective": zone,
            "updated_at": time_display.iso(row.updated_at) if row else None, "updated_by": row.name if row else None}


@router.put("/settings")
def put_settings(body: DisplaySettings, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Save the case time zone; the change is written to the audit log with the old and new values (4.6)."""
    authorize_case(db, body.case_id, user, ("case", "edit"))
    if not time_display.valid_zone(body.time_zone):
        raise HTTPException(status_code=422, detail="Not a time zone name Loupe knows (for example America/New_York).")
    from sqlalchemy import text as sql
    from services.system_log_service import LogOrigin, LogType, system_log_service
    conn = db.connection()
    old = conn.execute(sql("SELECT time_zone FROM case_display_settings WHERE case_id = :c"),
                       {"c": body.case_id}).scalar()
    conn.execute(sql(
        "INSERT INTO case_display_settings (case_id, time_zone, updated_by, updated_at) VALUES (:c, :z, :u, now()) "
        "ON CONFLICT (case_id) DO UPDATE SET time_zone = EXCLUDED.time_zone, updated_by = EXCLUDED.updated_by, "
        "updated_at = now()"), {"c": body.case_id, "z": body.time_zone, "u": user.id})
    system_log_service.log(log_type=LogType.CASE_OPERATION, origin=LogOrigin.BACKEND,
                           action="Set phone data time zone",
                           details={"case_id": str(body.case_id), "changes": {"time_zone": {"from": old,
                                                                                            "to": body.time_zone}}},
                           user=user.email, success=True, db=db)
    db.commit()
    return get_settings(case_id=body.case_id, db=db, user=user)


@router.post("/streams/index")
def stream_index(body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """03 section 4.5: exact total, per-day counts in the display zone, the no-time count and a snapshot."""
    f = _filter(body, db, user)
    try:
        out = streams.index_comm_events(db.connection(), f)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - 3.8 error wording with a reference
        raise _failure(LIST_FAILED, exc)
    if (f.text.query or "").strip():  # searches run, for the review coverage summary (07 J-13 step 6)
        from services.phone import review_share
        # the thread list records a Conversations search; here only a search inside open threads (find in
        # thread) and other screens' streams, so one search is not counted twice
        review_share.record_search(db, f.case_id, user, f.text.query, exact=f.text.exact_characters,
                                   surface="thread" if f.threads else "stream",
                                   hits=(out.get("counts") or {}).get("events"))
    return out


class WindowBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filter: dict
    snapshot: str = Field(min_length=1, max_length=64)
    day: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=200, ge=1, le=streams.WINDOW_MAX)


@router.post("/streams/window")
def stream_window(body: WindowBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Rows of one day (or the no-time group, ``day`` null) by offset; 409 ``stale_snapshot`` when the data moved."""
    f = _filter(body.filter, db, user)
    try:
        return streams.window_comm_events(db.connection(), f, snapshot_token=body.snapshot, day=body.day,
                                          offset=body.offset, limit=body.limit)
    except streams.StaleSnapshot:
        raise HTTPException(status_code=409, detail="stale_snapshot")
    except Exception as exc:  # noqa: BLE001
        raise _failure("These messages could not be loaded.", exc)


class LocateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filter: dict
    snapshot: str = Field(min_length=1, max_length=64)
    event_uid: UUID


@router.post("/streams/locate")
def stream_locate(body: LocateBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    f = _filter(body.filter, db, user)
    try:
        return streams.locate_comm_event(db.connection(), f, snapshot_token=body.snapshot,
                                         event_uid=str(body.event_uid))
    except streams.StaleSnapshot:
        raise HTTPException(status_code=409, detail="stale_snapshot")
    except streams.NotInCase:
        raise HTTPException(status_code=404, detail="This message is not in the current list.")


class FindBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filter: dict
    snapshot: str = Field(min_length=1, max_length=64)
    query: str = Field(min_length=1, max_length=2000)
    exact: bool = False


@router.post("/streams/find")
def stream_find(body: FindBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Find in these results (03 section 3.1 rule 4, 07 section 4.8): every match in the whole result, in list order,
    with the true total ("Match 3 of 214"). Too many matches is refused with the count, never cut."""
    f = _filter(body.filter, db, user)
    if not body.query.strip():
        raise HTTPException(status_code=422, detail="Type something to find.")
    try:
        return streams.find_in_results(db.connection(), f, snapshot_token=body.snapshot, query=body.query,
                                       exact=body.exact)
    except streams.StaleSnapshot:
        raise HTTPException(status_code=409, detail="stale_snapshot")
    except streams.FindTooLarge as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def _lens_filter(body: dict, db, user):
    from services.phone.timeline_lens import TimelineLensFilter
    try:
        f = TimelineLensFilter.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=[{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()])
    authorize_case(db, UUID(f.case_id), user, ("case", "view"))
    return f


@router.post("/timeline/index")
def timeline_lens_index(body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """03 section 9.3: the phone lens's exact total, per-day counts by lane, the no-time count, the lanes and the
    hidden device and sensor count (T-7)."""
    from services.phone import timeline_lens
    f = _lens_filter(body, db, user)
    try:
        return timeline_lens.index(db.connection(), f)
    except Exception as exc:  # noqa: BLE001
        raise _failure("The phone entries could not be loaded.", exc)


class LensWindowBody(WindowBody):
    pass


@router.post("/timeline/window")
def timeline_lens_window(body: LensWindowBody, db: Session = Depends(get_db),
                         user: User = Depends(get_current_db_user)):
    from services.phone import timeline_lens
    f = _lens_filter(body.filter, db, user)
    try:
        return timeline_lens.window(db.connection(), f, snapshot_token=body.snapshot, day=body.day,
                                    offset=body.offset, limit=body.limit)
    except streams.StaleSnapshot:
        raise HTTPException(status_code=409, detail="stale_snapshot")
    except Exception as exc:  # noqa: BLE001
        raise _failure("The phone entries could not be loaded.", exc)


class LensLocateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filter: dict
    snapshot: str = Field(min_length=1, max_length=64)
    record_uid: UUID


@router.post("/timeline/locate")
def timeline_lens_locate(body: LensLocateBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Show on Timeline (03 section 3.6): the day and offset of a record's entry in the lens."""
    from services.phone import timeline_lens
    f = _lens_filter(body.filter, db, user)
    try:
        return timeline_lens.locate_record(db.connection(), f, snapshot_token=body.snapshot,
                                           record_uid=str(body.record_uid))
    except streams.StaleSnapshot:
        raise HTTPException(status_code=409, detail="stale_snapshot")
    except streams.NotInCase:
        raise HTTPException(status_code=404, detail="This record has no entry in the phone lens with the kinds shown.")


class LensBucketsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filter: dict
    snapshot: str = Field(min_length=1, max_length=64)
    start: datetime
    end: datetime
    bucket: Literal["hour", "day", "week"] = "day"


@router.post("/timeline/buckets")
def timeline_lens_buckets(body: LensBucketsBody, db: Session = Depends(get_db),
                          user: User = Depends(get_current_db_user)):
    """03 section 9.6: counts per lane per hour or day for the Lanes view; a phone's periods with no data are marked
    (T-6)."""
    from services.phone import timeline_lens
    f = _lens_filter(body.filter, db, user)
    if body.start.tzinfo is None or body.end.tzinfo is None:
        raise HTTPException(status_code=422, detail="The span needs times with a zone.")
    try:
        return timeline_lens.buckets(db.connection(), f, snapshot_token=body.snapshot, start=body.start,
                                     end=body.end, bucket=body.bucket)
    except streams.StaleSnapshot:
        raise HTTPException(status_code=409, detail="stale_snapshot")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise _failure("The lanes could not be loaded.", exc)


@router.post("/conversations/threads")
def conversation_threads(body: dict, sort: str = Query("recent", pattern="^(recent|first|volume|unreviewed|name)$"),
                         db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Every thread with events under the filter, in one response (6.3, C-5), with its review mark."""
    f = _filter(body, db, user)
    try:
        out = streams.thread_list(db.connection(), f, sort=sort)
    except Exception as exc:  # noqa: BLE001
        raise _failure("The conversation list could not be loaded.", exc)
    if (f.text.query or "").strip():  # a Conversations search starts here (07 J-13 step 6, searches run)
        from services.phone import review_share
        review_share.record_search(db, f.case_id, user, f.text.query, exact=f.text.exact_characters,
                                   surface="conversations", hits=sum(int(t.get("event_count") or 0)
                                                                     for t in out.get("items") or []))
    return out


@router.post("/conversations/participants")
def conversation_participants(body: dict, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """People mode (6.3): every participant under the filter with counts, phones and apps, in one response."""
    f = _filter(body, db, user)
    try:
        return streams.participant_list(db.connection(), f)
    except Exception as exc:  # noqa: BLE001
        raise _failure("The list of people could not be loaded.", exc)


@router.get("/people/linked")
def person_linked_identities(case_id: UUID = Query(...), key: str = Query(..., min_length=1, max_length=512),
                             db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """The other numbers and accounts linked to the same person as ``key`` (07 J-3 step 3), for the switch that
    takes them in. A key with no person has none."""
    authorize_case(db, case_id, user, ("case", "view"))
    keys = streams._person_keys(db.connection(), str(case_id), [key])[key]
    others = [k for k in keys if k != key]
    numbers = sum(1 for k in others if k.startswith("phone:"))
    return {"case_id": str(case_id), "identity_key": key, "others": others, "numbers": numbers,
            "accounts": len(others) - numbers}


class SelectionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filter: dict
    words: str = Field(min_length=1, max_length=2000)


class EntryExportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    entry_id: UUID


class SourceExportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    source: Literal["analysis_result", "statement_check", "incident_window", "collection", "dossier"]
    ref: dict = Field(default_factory=dict)


@router.post("/exports/source")
def prepare_source_export(body: SourceExportBody, db: Session = Depends(get_db),
                          user: User = Depends(get_current_db_user)):
    """The records behind an analysis result, a statement check or an incident window, or collected in a collection
    (``ref.selection_id``) or a dossier (``ref.dossier_id``), frozen as one selection for the export dialog (07 J-14b,
    6.4 item 14): the filter, the count frozen (the export's total), and what is not in the export."""
    from services.phone import source_export
    authorize_case(db, body.case_id, user, ("case", "view"))
    try:
        return source_export.freeze_source(db, body.case_id, body.source, body.ref, user)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    except source_export.SourceExportError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/exports/entry")
def prepare_entry_export(body: EntryExportBody, db: Session = Depends(get_db),
                         user: User = Depends(get_current_db_user)):
    """A finding, theory or note's phone records frozen as one selection for the export dialog (07 XF-7, CO-12): the
    filter to draw, the collected count (the export's total) and what of the entry is not in the export. Needs view
    access, as an export does."""
    from services.phone import entry_export
    authorize_case(db, body.case_id, user, ("case", "view"))
    try:
        return entry_export.freeze_entry(db, body.case_id, body.entry_id, user)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    except entry_export.EntryExportError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/selections")
def freeze_selection(body: SelectionBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Freeze every record the filter matches now as one ``phone_selection`` (07 section 6.1), for Add to… on a whole
    result. Needs edit access, because it is made to be added somewhere."""
    from services.phone import selections
    f = _filter(body.filter, db, user, ("case", "edit"))
    try:
        return selections.freeze(db, f, user, body.words)
    except selections.SelectionError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/selections/{selection_id}")
def get_selection(selection_id: str, case_id: UUID = Query(...), db: Session = Depends(get_db),
                  user: User = Depends(get_current_db_user)):
    """A saved selection's sentence and counts, for the screen a saved link opens (07 6.1)."""
    authorize_case(db, case_id, user, ("case", "view"))
    from services.phone import selections
    try:
        out = selections.describe(db, case_id, selection_id)
    except (ValueError, TypeError):
        out = None
    if out is None:
        raise HTTPException(status_code=404, detail="This selection is not in this case.")
    return out


class SaveViewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filter: dict
    location: str = Field(min_length=1, max_length=4000)
    words: str = Field("", max_length=1000)
    title: Optional[str] = Field(None, max_length=300)


@router.post("/views")
def save_view(body: SaveViewBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Save this view (07 section 6): the filter as a ``phone_view`` held by a new Workspace note. Needs edit access."""
    from services.phone import views
    f = _filter(body.filter, db, user, ("case", "edit"))
    try:
        return views.save(db, f, user, location=body.location, words=body.words, title=body.title)
    except views.ViewError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/views/{view_id}")
def get_view(view_id: str, case_id: UUID = Query(...), db: Session = Depends(get_db),
             user: User = Depends(get_current_db_user)):
    """A saved view re-run live: the count when saved and now, and the screen it opens (07 section 6)."""
    authorize_case(db, case_id, user, ("case", "view"))
    from services.phone import views
    out = views.describe(db, case_id, view_id)
    if out is None:
        raise HTTPException(status_code=404, detail="This saved view is not in this case.")
    return out


class ReviewMarkBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    thread_key: str = Field(min_length=1, max_length=512)
    scope: dict = Field(default_factory=dict)
    position: Optional[dict] = None


@router.post("/conversations/review")
def mark_thread_reviewed(body: ReviewMarkBody, db: Session = Depends(get_db),
                         user: User = Depends(get_current_db_user)):
    """Mark a thread reviewed (07 section 6.1, J-13). Needs edit access to the case."""
    from services.phone import review_marks
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        return {"thread_key": body.thread_key,
                "review": review_marks.mark(db, body.case_id, body.thread_key, user, scope=body.scope,
                                            position=body.position)}
    except review_marks.ReviewMarkError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/conversations/review/undo")
def undo_thread_review(body: ReviewMarkBody, db: Session = Depends(get_db),
                       user: User = Depends(get_current_db_user)):
    """Undo the latest review mark on a thread; an earlier mark, if any, is current again."""
    from services.phone import review_marks
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        prev = review_marks.undo(db, body.case_id, body.thread_key, user)
    except review_marks.ReviewMarkError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    return {"thread_key": body.thread_key, "restored": bool(prev)}


class SplitBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filter: dict
    by: str = Field(pattern="^(thread|person)$")
    reviewers: List[UUID] = Field(min_length=1, max_length=50)
    only_not_reviewed: bool = True
    expect_threads: Optional[int] = Field(default=None, ge=0)
    scope_words: Optional[str] = Field(default=None, max_length=1000)


@router.post("/conversations/review/split/preview")
def preview_review_split(body: SplitBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """The counts "Split for review" makes, before anything is made (07 J-13 step 1)."""
    from services.phone import review_share
    f = _filter(body.filter, db, user, ("case", "edit"))
    try:
        plan = review_share.plan_split(db.connection(), f, by=body.by, reviewers=[str(r) for r in body.reviewers],
                                       only_not_reviewed=body.only_not_reviewed)
    except review_share.ReviewShareError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    plan.pop("_threads", None)
    for p in plan["parts"]:
        p.pop("thread_keys", None)
    return plan


@router.post("/conversations/review/split")
def make_review_split(body: SplitBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Make one Workspace task per reviewer, each linking its threads; 409 when the threads changed since the
    counts were shown (nothing is made)."""
    from services.phone import review_share
    f = _filter(body.filter, db, user, ("case", "edit"))
    if body.expect_threads is None:
        raise HTTPException(status_code=422, detail="Show the counts first: the split needs the thread count seen.")
    try:
        return review_share.create_split(db, f, by=body.by, reviewers=[str(r) for r in body.reviewers], user=user,
                                         expect_threads=body.expect_threads, only_not_reviewed=body.only_not_reviewed,
                                         scope_words=body.scope_words)
    except review_share.SplitChanged as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc))
    except review_share.ReviewShareError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


class SecondPassBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    reviewer: UUID
    percent: int = Field(default=10, ge=1, le=100)
    seed: Optional[int] = Field(default=None, ge=0, le=2**31 - 1)


@router.post("/conversations/review/second-pass")
def start_second_pass(body: SecondPassBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Draw a second-pass sample of reviewed threads for a different person (07 J-13 step 5); the seed is kept."""
    from services.phone import review_share
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        return review_share.start_second_pass(db, body.case_id, reviewer_id=str(body.reviewer), user=user,
                                              percent=body.percent, seed=body.seed)
    except review_share.ReviewShareError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


class SecondPassResultBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    task_id: UUID
    thread_key: str = Field(min_length=1, max_length=512)
    agrees: bool
    note: Optional[str] = Field(default=None, max_length=4000)


@router.post("/conversations/review/second-pass/result")
def record_second_pass(body: SecondPassResultBody, db: Session = Depends(get_db),
                       user: User = Depends(get_current_db_user)):
    """The second reviewer's result, recorded beside the first mark; the first mark is never changed."""
    from services.phone import review_share
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        return review_share.record_second_pass(db, body.case_id, task_id=body.task_id, thread_key=body.thread_key,
                                               user=user, agrees=body.agrees, note=body.note)
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    except review_share.ReviewShareError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/conversations/review/thread")
def thread_review_state(case_id: UUID = Query(...), thread_key: str = Query(..., min_length=1, max_length=512),
                        db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """The open thread's review task and second-pass samples, for its header."""
    from services.phone import review_share
    authorize_case(db, case_id, user, ("case", "view"))
    return review_share.thread_review_state(db.connection(), case_id, thread_key, user.id)


class PresenceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    thread_key: str = Field(min_length=1, max_length=512)
    leaving: bool = False


@router.post("/conversations/presence")
def thread_presence(body: PresenceBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """"[name] is also reviewing this thread." One beat per open thread every 45 s; a person is gone after 100 s."""
    from services.phone import review_share
    authorize_case(db, body.case_id, user, ("case", "view"))
    return review_share.heartbeat(db, body.case_id, body.thread_key, user, leaving=body.leaving)


@router.get("/conversations/review/coverage")
def review_coverage(case_id: UUID = Query(...), phones: Optional[str] = None, db: Session = Depends(get_db),
                    user: User = Depends(get_current_db_user)):
    """The review coverage summary (07 J-13 step 6), whole: counts equal to the marks, who reviewed what, every
    thread not yet reviewed, the splits, the second-pass results, the searches run and the terms used."""
    from services.phone import review_share
    authorize_case(db, case_id, user, ("case", "view"))
    out = review_share.coverage(db.connection(), case_id, phones=[p for p in (phones or "").split(",") if p] or None)
    out["cover"] = review_share.cover_lines(out)
    return out


class CopyDecisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    reason: str = Field(min_length=1, max_length=4000)
    restore: bool = False


@router.post("/records/{record_uid}/not-a-copy")
def record_not_a_copy(record_uid: UUID, body: CopyDecisionBody, db: Session = Depends(get_db),
                      user: User = Depends(get_current_db_user)):
    """A person's Not a copy decision (03 section 3.4, C-13); ``restore`` puts the record back in its group."""
    from services.phone import copies
    authorize_case(db, body.case_id, user, ("case", "edit"))
    try:
        return copies.mark_not_a_copy(db, case_id=body.case_id, record_uid=record_uid, reason=body.reason,
                                      actor=_actor(user), restore=body.restore)
    except copies.CopyDecisionError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/records/{record_uid}")
def record_detail(record_uid: UUID, case_id: UUID = Query(...), zone: Optional[str] = Query(None, max_length=64),
                  db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """The record panel (3.6). A record of another case is 404, never 403 (3.11)."""
    authorize_case(db, case_id, user, ("case", "view"))
    z = zone if zone and time_display.valid_zone(zone) else streams.case_zone(db.connection(), case_id)["name"]
    try:
        out = phone_records.record_detail(db.connection(), case_id, record_uid, zone=z)
    except phone_records.NotFound:
        raise HTTPException(status_code=404, detail="This record is not in this case.")
    out["as_text"] = phone_records.record_text(out)
    return out


@router.get("/records/{record_uid}/source-database")
async def record_source_database(record_uid: UUID, case_id: UUID = Query(...), source: int = Query(0, ge=0),
                                 browse: Optional[str] = Query(None, max_length=256), page: int = Query(1, ge=1),
                                 db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """05 section 17.2: the app database the report names as this record's source, opened read-only from a copy.
    ``source`` is the index into the record panel's ``sources``. Only a file tagged Database, present and verified
    is opened; anything else is answered with the reason, never opened."""
    from starlette.concurrency import run_in_threadpool

    from services import evidence_engine_client as engine
    from services.phone import source_db

    def resolve():
        authorize_case(db, case_id, user, ("case", "view"))
        loc = phone_records._locate(db.connection(), case_id, record_uid)
        if loc is None:
            return None, None
        return loc, source_db.record_sources(db.connection(), loc.extraction_id, loc.document_index, loc.ordinal)

    loc, sources = await run_in_threadpool(resolve)
    if loc is None:
        raise HTTPException(status_code=404, detail="This record is not in this case.")
    if source >= len(sources):
        raise HTTPException(status_code=404, detail="This record has no such source.")
    s = sources[source]
    base = {"record_uid": str(record_uid), "source": s,
            "read_by": "Read from the app database file by Loupe's read-only viewer; not the report's record."}
    if not s["file"] or not s["file"]["is_database"] or s["state"] != "verified":
        return dict(base, refused=s["state_words"] if s["file"] else source_db.STATE_WORDS["unresolved"],
                    view=None)
    f = s["file"]
    out = await engine.source_database(str(case_id), str(loc.extraction_id), f["document_index"], f["ordinal"],
                                       {"table": s["table_name"], "offset": s["offset"], "browse": browse,
                                        "page": page})
    if "refused" in out:
        return dict(base, refused=out["refused"], view=None)
    if not s["table_name"]:
        out["named_row"] = {"found": False, "reason": source_db.NO_ROW_NAMED}
    return dict(base, refused=None, view=out)


class ReparseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    extraction_id: UUID


def _os_family(os_text) -> Optional[str]:
    t = (os_text or "").casefold()
    if "android" in t:
        return "Android"
    if t.startswith("ios") or " ios" in t or "iphone" in t:
        return "iOS"
    return None


@router.get("/reparse/runs")
def reparse_runs(case_id: UUID = Query(...), db: Session = Depends(get_db),
                 user: User = Depends(get_current_db_user)):
    """05 section 17.3: each active phone with its operating system and its re-parse runs, newest first."""
    from sqlalchemy import text
    authorize_case(db, case_id, user, ("case", "view"))
    conn = db.connection()
    labels = readings.phone_labels(conn, case_id)
    phones = []
    for (ext,) in conn.execute(text("SELECT id::text FROM phone_extractions WHERE case_id = :c AND standing = 'active' "
                                    "ORDER BY created_at"), {"c": str(case_id)}):
        os_text = phone_records._device(conn, ext).get("os")
        runs = [dict(r._mapping) for r in conn.execute(text(
            "SELECT id::text, tool, tool_version, tool_commit, tool_licence, status, tree, exit_code, stopped, seconds, "
            "peak_rss_mb, artefact_counts, error, requested_by, created_at, started_at, finished_at FROM "
            "phone_reparse_runs WHERE extraction_id = :e ORDER BY created_at DESC LIMIT 20"), {"e": ext})]
        for r in runs:
            for k in ("created_at", "started_at", "finished_at"):
                r[k] = r[k].isoformat() if r[k] else None
        phones.append({"extraction_id": ext, "label": labels.get(ext, "A phone"), "os": os_text,
                       "os_family": _os_family(os_text), "runs": runs})
    return {"phones": phones, "total": len(phones)}


@router.post("/reparse", status_code=202)
async def request_reparse(body: ReparseBody, db: Session = Depends(get_db), user: User = Depends(get_current_db_user)):
    """Queue an independent re-parse of one phone (05 section 17.3). The tool's rows are stored apart from the
    report's records and are compared by the analysis "Read again by an independent tool"."""
    from starlette.concurrency import run_in_threadpool

    from services import evidence_engine_client as engine

    from sqlalchemy import text

    def resolve():
        authorize_case(db, body.case_id, user, ("case", "edit"))
        conn = db.connection()
        ok = conn.execute(text("SELECT 1 FROM phone_extractions WHERE id = :e AND case_id = :c AND standing = 'active'"),
                          {"e": str(body.extraction_id), "c": str(body.case_id)}).first()
        return ok, _os_family(phone_records._device(conn, str(body.extraction_id)).get("os")) if ok else None
    ok, family = await run_in_threadpool(resolve)
    if not ok:
        raise HTTPException(status_code=404, detail="This phone is not in this case.")
    if family is None:
        raise HTTPException(status_code=409, detail="The report does not say which operating system this phone ran, "
                                                    "so no re-parse tool can be chosen.")
    out = await engine.request_reparse(str(body.case_id), str(body.extraction_id), family, _actor(user).email)
    if "refused" in out:
        raise HTTPException(status_code=409, detail=out["refused"])
    return out


class RevealBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: UUID
    field_path: str = Field(min_length=1, max_length=512)
    value_index: int = Field(0, ge=0)


@router.post("/records/{record_uid}/reveal")
def reveal_sensitive(record_uid: UUID, body: RevealBody, db: Session = Depends(get_db),
                     user: User = Depends(get_current_db_user)):
    """Reveal one sensitive value (05 section 3.8); the reveal is logged (actor, time, locator, field) first."""
    from services.phone import sensitive
    authorize_case(db, body.case_id, user, ("case", "view"))
    try:
        out = sensitive.reveal(db, body.case_id, record_uid, body.field_path, body.value_index, _actor(user))
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    except sensitive.RevealError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    return out


@router.get("/identities")
def identity_picker(case_id: UUID = Query(...), q: str = Query("", max_length=200), limit: int = Query(50, ge=1, le=200),
                    cursor: int = Query(0, ge=0), db: Session = Depends(get_db),
                    user: User = Depends(get_current_db_user)):
    """The identity picker (4.4): search as you type over every identity by value or any phone's name, with each
    phone's names and the event count; ``total`` is exact."""
    authorize_case(db, case_id, user, ("case", "view"))
    from sqlalchemy import text as sql
    from services.phone import fold as phone_fold
    conn = db.connection()
    folded = phone_fold.fold(q.strip()) if q.strip() else ""
    digits = "".join(ch for ch in q if ch.isdigit())
    idents = conn.execute(sql(
        "SELECT i.identity_id, i.identity_key, i.kind, i.value_display, i.value_normalised, i.person_id, "
        "p.display_name AS person_name FROM pv_identity i LEFT JOIN case_profiles p ON p.id = i.person_id "
        "WHERE i.case_id = :c"), {"c": case_id}).fetchall()
    names = {}
    for n in conn.execute(sql("SELECT identity_id, extraction_id, name, basis, is_phone_name FROM pv_identity_name "
                              "WHERE case_id = :c ORDER BY extraction_id"), {"c": case_id}):
        names.setdefault(n.identity_id, []).append(n)

    def matches(r):
        # Folded as Search folds (11.3): "jose" finds "José"; three or more digits match the number's digits.
        if not q.strip():
            return True
        if not folded:
            return False  # punctuation only: nothing to match
        hay = [r.value_display, r.identity_key] + [n.name for n in names.get(r.identity_id, [])]
        if any(folded in phone_fold.fold(h) for h in hay if h):
            return True
        return len(digits) >= 3 and digits in "".join(ch for ch in (r.value_normalised or "") if ch.isdigit())

    hits = [r for r in idents if matches(r)]
    counts = {k: int(n) for k, n in conn.execute(sql(
        "SELECT identity_key, count(DISTINCT event_uid) FROM pv_comm_party WHERE case_id = :c AND identity_key = "
        "ANY(CAST(:k AS text[])) GROUP BY identity_key"), {"c": case_id, "k": [r.identity_key for r in hits]})}
    hits.sort(key=lambda r: (-counts.get(r.identity_key, 0), r.value_display or "", r.identity_key))
    total = len(hits)
    labels = readings.phone_labels(conn, case_id)
    items = []
    for r in hits[cursor:cursor + limit]:
        items.append({"identity_key": r.identity_key, "kind": r.kind, "value_display": r.value_display,
                      "names": [{"phone_label": labels.get(str(n.extraction_id)), "name": n.name, "basis": n.basis}
                                for n in names.get(r.identity_id, []) if n.is_phone_name],
                      "person": {"id": str(r.person_id), "display_name": r.person_name} if r.person_id else None,
                      "event_count": counts.get(r.identity_key, 0)})
    nxt = cursor + len(items)
    return {"case_id": str(case_id), "items": items, "total": int(total), "next_cursor": nxt if nxt < total else None}
