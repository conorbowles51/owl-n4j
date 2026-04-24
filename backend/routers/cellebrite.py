"""
Cellebrite Router

Analytics endpoints for the Cellebrite Multi-Phone View:
- List ingested phone reports
- Cross-phone graph (shared contacts across devices)
- Multi-device timeline
- Communication network analysis
"""

from typing import Dict, List, Optional
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
async def get_reports(
    case_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """List all ingested Cellebrite PhoneReport nodes for a case."""
    _require_case_access(case_id, current_user, db)
    reports = neo4j_service.get_cellebrite_reports(case_id)
    return {"reports": reports}


@router.get("/cross-phone-graph")
async def get_cross_phone_graph(
    case_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Get cross-phone graph showing shared contacts across devices."""
    _require_case_access(case_id, current_user, db)
    graph = neo4j_service.get_cellebrite_cross_phone_graph(case_id)
    return graph


@router.get("/timeline")
async def get_timeline(
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
async def get_communication_network(
    case_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Get communication network analysis (contact frequency, shared contacts)."""
    _require_case_access(case_id, current_user, db)
    result = neo4j_service.get_cellebrite_communication_network(case_id)
    return result


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
async def get_comms_entities(
    case_id: str = Query(...),
    report_keys: Optional[str] = Query(None, description="Comma-separated report keys"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """List distinct comms participants with per-entity comm counts and device membership."""
    _require_case_access(case_id, current_user, db)
    keys = _csv_param(report_keys)
    entities = neo4j_service.get_cellebrite_comms_entities(case_id=case_id, report_keys=keys)
    return {"entities": entities}


@router.get("/comms/source-apps")
async def get_comms_source_apps(
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
async def get_comms_threads(
    case_id: str = Query(...),
    report_keys: Optional[str] = Query(None),
    from_keys: Optional[str] = Query(None, description="Comma-separated Person keys in From"),
    to_keys: Optional[str] = Query(None, description="Comma-separated Person keys in To"),
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
async def get_comms_thread_detail(
    thread_id: str,
    case_id: str = Query(...),
    thread_type: str = Query(..., description="chat, calls, or emails"),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
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
    )
    _resolve_attachments(case_id, result.get("items", []))
    return result


@router.get("/comms/between")
async def get_comms_between(
    case_id: str = Query(...),
    from_keys: Optional[str] = Query(None),
    to_keys: Optional[str] = Query(None),
    types: Optional[str] = Query(None, description="Comma-separated: message,call,email"),
    report_keys: Optional[str] = Query(None),
    source_apps: Optional[str] = Query(None, description="Comma-separated source app names"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Chronological cross-type feed between selected entity sets."""
    _require_case_access(case_id, current_user, db)
    result = neo4j_service.get_cellebrite_comms_between(
        case_id=case_id,
        from_keys=_csv_param(from_keys),
        to_keys=_csv_param(to_keys),
        types=_csv_param(types),
        report_keys=_csv_param(report_keys),
        source_apps=_csv_param(source_apps),
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    _resolve_attachments(case_id, result.get("items", []))
    return result


@router.get("/comms/attachment/{file_id}")
async def resolve_comms_attachment(
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
async def get_events(
    case_id: str = Query(...),
    report_keys: Optional[str] = Query(None),
    event_types: Optional[str] = Query(None),
    source_apps: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    only_geolocated: bool = Query(False),
    limit: int = Query(5000, ge=1, le=20000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    """Unified event feed for the Location & Event Center."""
    _require_case_access(case_id, current_user, db)
    return neo4j_service.get_cellebrite_events(
        case_id=case_id,
        report_keys=_csv_param(report_keys),
        event_types=_csv_param(event_types),
        source_apps=_csv_param(source_apps),
        start_date=start_date,
        end_date=end_date,
        only_geolocated=only_geolocated,
        limit=limit,
        offset=offset,
    )


@router.get("/events/types")
async def get_event_types(
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
async def get_event_tracks(
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


@router.get("/events/detail/{node_key}")
async def get_event_detail(
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


class IntersectionRunRequest(BaseModel):
    methods: List[str]
    report_keys: Optional[List[str]] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    params: Optional[Dict[str, Dict[str, object]]] = None


@router.post("/intersections/run")
async def run_intersections(
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
async def get_cellebrite_files(
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
async def get_cellebrite_files_tree(
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
