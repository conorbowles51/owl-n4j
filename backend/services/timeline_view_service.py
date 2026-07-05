"""Service layer for saved timeline views and timeline exports."""

from __future__ import annotations

import csv
import html
import io
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session, selectinload

from postgres.models.notebook import NotebookNote, NotebookNoteLink
from postgres.models.timeline_view import TimelineView, TimelineViewEvent
from postgres.models.user import User
from services.neo4j_service import neo4j_service
from services.system_log_service import LogOrigin, LogType, system_log_service


MAX_VIEW_EVENTS = 10000
MAX_PDF_EVENTS = 5000
MAX_CSV_EVENTS = 20000

EXPORT_FIELD_KEYS = {
    "date",
    "time",
    "type",
    "title",
    "summary",
    "notes",
    "amount",
    "location",
    "linked_entities",
    "source_references",
    "notebook_notes",
}


class TimelineViewNotFound(Exception):
    """Raised when a saved timeline view is not found in the requested case."""


@dataclass(frozen=True)
class TimelineExport:
    content: bytes
    filename: str
    media_type: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _clean_title(value: str | None) -> str:
    title = _clean_text(value)
    if not title:
        raise ValueError("Timeline view title is required")
    if len(title) > 255:
        raise ValueError("Timeline view title must be 255 characters or fewer")
    return title


def _clean_description(value: str | None) -> str | None:
    text = _clean_text(value)
    if text and len(text) > 5000:
        raise ValueError("Timeline view description must be 5000 characters or fewer")
    return text


def _clean_json_object(value: dict[str, Any] | None) -> dict[str, Any]:
    return dict(value or {}) if isinstance(value, dict) else {}


def _clean_event_keys(event_keys: Iterable[str] | None, *, limit: int = MAX_VIEW_EVENTS) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for key in event_keys or []:
        key_text = str(key or "").strip()
        if not key_text or key_text in seen:
            continue
        if len(key_text) > 512:
            raise ValueError("Timeline event keys must be 512 characters or fewer")
        seen.add(key_text)
        cleaned.append(key_text)
        if len(cleaned) > limit:
            raise ValueError(f"Timeline views can contain at most {limit} events")
    return cleaned


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    return [value]


def _string_list(value: Any) -> list[str]:
    result: list[str] = []
    for item in _as_list(value):
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _event_sort_date(event: dict[str, Any]) -> str | None:
    value = str(event.get("date") or "").strip()
    return value[:10] if value else None


def _event_sort_time(event: dict[str, Any]) -> str | None:
    value = str(event.get("time") or "").strip()
    match = re.match(r"^(\d{2}:\d{2})", value)
    return match.group(1) if match else None


def _event_snapshot(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": event.get("key"),
        "name": event.get("name"),
        "type": event.get("type"),
        "date": event.get("date"),
        "time": event.get("time"),
        "amount": event.get("amount"),
        "summary": event.get("summary"),
        "notes": event.get("notes"),
        "connections": event.get("connections") or [],
    }


def _view_event_to_dict(item: TimelineViewEvent) -> dict[str, Any]:
    snapshot = dict(item.event_snapshot or {})
    return {
        "id": str(item.id),
        "view_id": str(item.view_id),
        "case_id": str(item.case_id),
        "event_key": item.event_key,
        "event_snapshot": snapshot,
        "sort_date": item.sort_date,
        "sort_time": item.sort_time,
        "position": item.position,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def timeline_view_to_dict(view: TimelineView, *, include_events: bool = True) -> dict[str, Any]:
    events = list(view.events or [])
    return {
        "id": str(view.id),
        "case_id": str(view.case_id),
        "title": view.title,
        "description": view.description,
        "visibility": view.visibility,
        "owner_user_id": str(view.owner_user_id) if view.owner_user_id else None,
        "owner_email": view.owner_email,
        "owner_name": view.owner_name,
        "filter_snapshot": dict(view.filter_snapshot or {}),
        "export_defaults": dict(view.export_defaults or {}),
        "event_count": len(events),
        "created_at": view.created_at.isoformat() if view.created_at else None,
        "updated_at": view.updated_at.isoformat() if view.updated_at else None,
        "events": [_view_event_to_dict(item) for item in events] if include_events else [],
    }


def _get_view(db: Session, case_id: UUID, view_id: UUID) -> TimelineView:
    view = (
        db.query(TimelineView)
        .options(selectinload(TimelineView.events))
        .filter(
            TimelineView.id == view_id,
            TimelineView.case_id == case_id,
            TimelineView.deleted_at.is_(None),
        )
        .first()
    )
    if not view:
        raise TimelineViewNotFound(f"Timeline view {view_id} not found")
    return view


def _fetch_current_events(case_id: UUID | str, event_keys: list[str], *, require_all: bool = True) -> list[dict[str, Any]]:
    events = neo4j_service.get_timeline_events_by_keys(
        case_id=str(case_id),
        event_keys=event_keys,
        include_export_fields=True,
    )
    found = {str(event.get("key")) for event in events}
    missing = [key for key in event_keys if key not in found]
    if require_all and missing:
        raise ValueError(f"{len(missing)} timeline event(s) were not found in this case")
    return events


def list_timeline_views(
    db: Session,
    *,
    case_id: UUID,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    query = (
        db.query(TimelineView)
        .options(selectinload(TimelineView.events))
        .filter(TimelineView.case_id == case_id, TimelineView.deleted_at.is_(None))
    )
    total = query.count()
    views = (
        query.order_by(desc(TimelineView.updated_at), desc(TimelineView.created_at), desc(TimelineView.id))
        .offset(max(offset, 0))
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return {"views": [timeline_view_to_dict(view, include_events=False) for view in views], "total": total}


def get_timeline_view(db: Session, *, case_id: UUID, view_id: UUID) -> dict[str, Any]:
    return timeline_view_to_dict(_get_view(db, case_id, view_id))


def _replace_view_events(
    db: Session,
    *,
    view: TimelineView,
    current_user: User,
    events: list[dict[str, Any]],
) -> None:
    view.events.clear()
    db.flush()
    for position, event in enumerate(events):
        view.events.append(
            TimelineViewEvent(
                view_id=view.id,
                case_id=view.case_id,
                event_key=str(event.get("key")),
                event_snapshot=_event_snapshot(event),
                sort_date=_event_sort_date(event),
                sort_time=_event_sort_time(event) or "99:99",
                position=position,
                added_by_user_id=current_user.id,
            )
        )


def create_timeline_view(
    db: Session,
    *,
    case_id: UUID,
    current_user: User,
    title: str,
    description: str | None = None,
    event_keys: list[str] | None = None,
    filter_snapshot: dict[str, Any] | None = None,
    export_defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    keys = _clean_event_keys(event_keys)
    events = _fetch_current_events(case_id, keys, require_all=True) if keys else []

    view = TimelineView(
        case_id=case_id,
        owner_user_id=current_user.id,
        owner_email=current_user.email,
        owner_name=current_user.name,
        title=_clean_title(title),
        description=_clean_description(description),
        visibility="case",
        filter_snapshot=_clean_json_object(filter_snapshot),
        export_defaults=_clean_json_object(export_defaults),
    )
    db.add(view)
    db.flush()
    _replace_view_events(db, view=view, current_user=current_user, events=events)

    system_log_service.log(
        log_type=LogType.CASE_OPERATION,
        origin=LogOrigin.FRONTEND,
        action="Create Timeline View",
        details={"case_id": str(case_id), "view_id": str(view.id), "event_count": len(events)},
        user=current_user.email,
        success=True,
        db=db,
    )
    db.commit()
    return timeline_view_to_dict(_get_view(db, case_id, view.id))


def update_timeline_view(
    db: Session,
    *,
    case_id: UUID,
    view_id: UUID,
    current_user: User,
    title: str | None = None,
    description: str | None = None,
    filter_snapshot: dict[str, Any] | None = None,
    export_defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    view = _get_view(db, case_id, view_id)
    if title is not None:
        view.title = _clean_title(title)
    if description is not None:
        view.description = _clean_description(description)
    if filter_snapshot is not None:
        view.filter_snapshot = _clean_json_object(filter_snapshot)
    if export_defaults is not None:
        view.export_defaults = _clean_json_object(export_defaults)

    system_log_service.log(
        log_type=LogType.CASE_OPERATION,
        origin=LogOrigin.FRONTEND,
        action="Update Timeline View",
        details={"case_id": str(case_id), "view_id": str(view.id)},
        user=current_user.email,
        success=True,
        db=db,
    )
    db.commit()
    return timeline_view_to_dict(_get_view(db, case_id, view_id))


def delete_timeline_view(
    db: Session,
    *,
    case_id: UUID,
    view_id: UUID,
    current_user: User,
) -> None:
    view = _get_view(db, case_id, view_id)
    view.deleted_at = _now()
    system_log_service.log(
        log_type=LogType.CASE_OPERATION,
        origin=LogOrigin.FRONTEND,
        action="Delete Timeline View",
        details={"case_id": str(case_id), "view_id": str(view.id)},
        user=current_user.email,
        success=True,
        db=db,
    )
    db.commit()


def batch_update_view_events(
    db: Session,
    *,
    case_id: UUID,
    view_id: UUID,
    current_user: User,
    action: str,
    event_keys: list[str],
) -> dict[str, Any]:
    view = _get_view(db, case_id, view_id)
    keys = _clean_event_keys(event_keys)

    if action not in {"add", "remove", "set"}:
        raise ValueError("Unsupported timeline view event action")

    if action == "remove":
        remove_set = set(keys)
        for item in list(view.events):
            if item.event_key in remove_set:
                view.events.remove(item)
        for position, item in enumerate(view.events):
            item.position = position
        changed_count = len(remove_set)
    else:
        events = _fetch_current_events(case_id, keys, require_all=True) if keys else []
        existing = {item.event_key for item in view.events}
        if action == "set":
            _replace_view_events(db, view=view, current_user=current_user, events=events)
            changed_count = len(events)
        else:
            position = len(view.events)
            changed_count = 0
            for event in events:
                key = str(event.get("key"))
                if key in existing:
                    continue
                view.events.append(
                    TimelineViewEvent(
                        view_id=view.id,
                        case_id=case_id,
                        event_key=key,
                        event_snapshot=_event_snapshot(event),
                        sort_date=_event_sort_date(event),
                        sort_time=_event_sort_time(event) or "99:99",
                        position=position,
                        added_by_user_id=current_user.id,
                    )
                )
                position += 1
                changed_count += 1

    system_log_service.log(
        log_type=LogType.CASE_OPERATION,
        origin=LogOrigin.FRONTEND,
        action="Update Timeline View Events",
        details={
            "case_id": str(case_id),
            "view_id": str(view.id),
            "action": action,
            "event_count": changed_count,
        },
        user=current_user.email,
        success=True,
        db=db,
    )
    db.commit()
    return timeline_view_to_dict(_get_view(db, case_id, view_id))


def _safe_filename(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower())
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-._")
    return (normalized or "timeline")[:80]


def _default_fields(detail_level: str) -> dict[str, bool]:
    fields = {
        "date": True,
        "time": True,
        "type": True,
        "title": True,
        "summary": detail_level != "compact",
        "notes": detail_level == "detailed",
        "amount": True,
        "location": True,
        "linked_entities": detail_level != "compact",
        "source_references": True,
        "notebook_notes": False,
    }
    return fields


def _normalize_fields(fields: dict[str, Any] | None, detail_level: str) -> dict[str, bool]:
    result = _default_fields(detail_level)
    for key, value in (fields or {}).items():
        if key in EXPORT_FIELD_KEYS:
            result[key] = bool(value)
    return result


def _event_location(event: dict[str, Any]) -> str:
    for key in ("location_name", "location_formatted", "location_raw", "location"):
        text = str(event.get(key) or "").strip()
        if text:
            return text
    lat = event.get("latitude")
    lon = event.get("longitude")
    if lat is not None and lon is not None:
        return f"{lat}, {lon}"
    return ""


def _source_refs(event: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ("source_references", "source_files", "source_quotes"):
        for item in _string_list(event.get(key)):
            if item not in refs:
                refs.append(item)
    return refs


def _events_by_key(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(event.get("key")): event for event in events if event.get("key")}


def _resolve_export_events(
    db: Session,
    *,
    case_id: UUID,
    view_id: UUID | None,
    event_keys: list[str] | None,
    require_all: bool,
) -> tuple[list[dict[str, Any]], str | None, dict[str, Any]]:
    view = _get_view(db, case_id, view_id) if view_id else None
    if view:
        keys = [item.event_key for item in view.events]
    else:
        keys = _clean_event_keys(event_keys, limit=MAX_CSV_EVENTS)

    current_events = _fetch_current_events(case_id, keys, require_all=require_all)
    current_by_key = _events_by_key(current_events)
    resolved: list[dict[str, Any]] = []

    if view:
        for item in view.events:
            event = current_by_key.get(item.event_key)
            if event:
                resolved.append(event)
            elif item.event_snapshot:
                snapshot = dict(item.event_snapshot)
                snapshot.setdefault("key", item.event_key)
                snapshot.setdefault("_missing_current_event", True)
                resolved.append(snapshot)
    else:
        resolved = current_events

    return resolved, view.title if view else None, dict(view.export_defaults or {}) if view else {}


def _notes_by_event(db: Session, *, case_id: UUID, event_keys: list[str]) -> dict[str, list[dict[str, str | None]]]:
    if not event_keys:
        return {}
    rows = (
        db.query(NotebookNoteLink, NotebookNote)
        .join(NotebookNote, NotebookNote.id == NotebookNoteLink.note_id)
        .filter(
            NotebookNoteLink.case_id == case_id,
            NotebookNoteLink.target_type == "timeline_event",
            NotebookNoteLink.target_id.in_(event_keys),
            NotebookNote.deleted_at.is_(None),
        )
        .order_by(desc(NotebookNote.updated_at), desc(NotebookNote.created_at))
        .all()
    )
    result: dict[str, list[dict[str, str | None]]] = {}
    for link, note in rows:
        result.setdefault(link.target_id, []).append(
            {
                "title": note.title,
                "body": note.body,
                "author_name": note.author_name,
                "updated_at": note.updated_at.isoformat() if note.updated_at else None,
            }
        )
    return result


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(str(item) for item in value if item is not None)
    return str(value)


def _render_csv(events: list[dict[str, Any]], fields: dict[str, bool], notes_by_event: dict[str, list[dict[str, str | None]]]) -> bytes:
    columns: list[tuple[str, str]] = []
    if fields["date"]:
        columns.append(("date", "Date"))
    if fields["time"]:
        columns.append(("time", "Time"))
    if fields["type"]:
        columns.append(("type", "Type"))
    if fields["title"]:
        columns.append(("name", "Event"))
    if fields["amount"]:
        columns.append(("amount", "Amount"))
    if fields["location"]:
        columns.append(("location", "Location"))
    if fields["linked_entities"]:
        columns.append(("linked_entities", "Linked entities"))
    if fields["summary"]:
        columns.append(("summary", "Summary"))
    if fields["notes"]:
        columns.append(("notes", "Notes"))
    if fields["source_references"]:
        columns.append(("source_references", "Source references"))
    if fields["notebook_notes"]:
        columns.append(("notebook_notes", "Notebook notes"))

    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=[label for _, label in columns], lineterminator="\n")
    writer.writeheader()
    for event in events:
        row: dict[str, str] = {}
        for key, label in columns:
            if key == "location":
                row[label] = _event_location(event)
            elif key == "linked_entities":
                row[label] = "; ".join(
                    str(conn.get("name") or conn.get("key") or "")
                    for conn in event.get("connections") or []
                    if conn.get("name") or conn.get("key")
                )
            elif key == "source_references":
                row[label] = "; ".join(_source_refs(event))
            elif key == "notebook_notes":
                row[label] = " | ".join(
                    note.get("title") or note.get("body") or ""
                    for note in notes_by_event.get(str(event.get("key")), [])
                )
            else:
                row[label] = _csv_value(event.get(key))
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8-sig")


def _format_day(value: str | None) -> str:
    if not value:
        return "Unknown date"
    try:
        parsed = datetime.strptime(value[:10], "%Y-%m-%d")
        return f"{parsed.strftime('%A, %B')} {parsed.day}, {parsed.year}"
    except ValueError:
        return value[:10]


def _group_events(events: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    groups: list[tuple[str, list[dict[str, Any]]]] = []
    current_date = None
    for event in events:
        date = str(event.get("date") or "")[:10]
        if date != current_date:
            current_date = date
            groups.append((date, []))
        groups[-1][1].append(event)
    return groups


def _build_source_index(events: list[dict[str, Any]]) -> tuple[dict[str, int], list[str]]:
    index: dict[str, int] = {}
    refs: list[str] = []
    for event in events:
        for ref in _source_refs(event):
            if ref in index:
                continue
            refs.append(ref)
            index[ref] = len(refs)
    return index, refs


def _render_pdf_html(
    *,
    events: list[dict[str, Any]],
    case_name: str,
    title: str,
    fields: dict[str, bool],
    detail_level: str,
    generated_by: str,
    footer_label: str,
    notes_by_event: dict[str, list[dict[str, str | None]]],
) -> str:
    generated_at = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    dates = [str(event.get("date") or "")[:10] for event in events if event.get("date")]
    date_span = f"{min(dates)} to {max(dates)}" if dates else "No dated events"
    source_index, source_refs = _build_source_index(events)

    def source_marks(event: dict[str, Any]) -> str:
        refs = [source_index[ref] for ref in _source_refs(event) if ref in source_index]
        if not refs:
            return ""
        return (
            '<span class="source-marks">Sources '
            + ", ".join(f"[{ref}]" for ref in refs[:5])
            + ("+" if len(refs) > 5 else "")
            + "</span>"
        )

    day_sections = []
    for date, day_events in _group_events(events):
        event_rows = []
        for event in day_events:
            time = str(event.get("time") or "").strip() or "No time"
            event_type = html.escape(str(event.get("type") or "Event"))
            name = html.escape(str(event.get("name") or event.get("key") or "Untitled event"))
            amount = html.escape(str(event.get("amount") or ""))
            location = html.escape(_event_location(event))
            summary = html.escape(str(event.get("summary") or ""))
            notes = html.escape(str(event.get("notes") or ""))
            connections = [
                html.escape(str(conn.get("name") or conn.get("key") or ""))
                for conn in event.get("connections") or []
                if conn.get("name") or conn.get("key")
            ]
            notebook_notes = notes_by_event.get(str(event.get("key")), [])

            meta = []
            if fields["type"]:
                meta.append(f'<span class="type-pill">{event_type}</span>')
            if fields["amount"] and amount:
                meta.append(f'<span class="meta-pill">{amount}</span>')
            if fields["location"] and location:
                meta.append(f'<span class="meta-pill">{location}</span>')
            if fields["source_references"]:
                marks = source_marks(event)
                if marks:
                    meta.append(marks)

            body_parts = []
            if fields["summary"] and summary:
                body_parts.append(f'<p class="summary">{summary}</p>')
            if fields["notes"] and notes:
                body_parts.append(f'<p class="notes"><strong>Notes:</strong> {notes}</p>')
            if fields["linked_entities"] and connections:
                chips = "".join(f'<span class="entity-chip">{conn}</span>' for conn in connections[:12])
                body_parts.append(f'<div class="entities">{chips}</div>')
            if fields["notebook_notes"] and notebook_notes:
                note_items = "".join(
                    f'<li><strong>{html.escape(note.get("title") or "Notebook note")}</strong>'
                    f'<span>{html.escape(note.get("body") or "")}</span></li>'
                    for note in notebook_notes[:4]
                )
                body_parts.append(f'<ul class="notebook-notes">{note_items}</ul>')

            event_rows.append(
                f"""
                <article class="event">
                    <div class="time">{html.escape(time)}</div>
                    <div class="event-body">
                        <div class="event-title">{name}</div>
                        <div class="event-meta">{''.join(meta)}</div>
                        {''.join(body_parts)}
                    </div>
                </article>
                """
            )

        day_sections.append(
            f"""
            <section class="day">
                <h2>{html.escape(_format_day(date))}</h2>
                {''.join(event_rows)}
            </section>
            """
        )

    appendix = ""
    if fields["source_references"] and source_refs:
        rows = "".join(
            f"<li><span>[{idx}]</span><p>{html.escape(ref)}</p></li>"
            for idx, ref in enumerate(source_refs, start=1)
        )
        appendix = f"""
        <section class="appendix">
            <h2>Source Appendix</h2>
            <ol>{rows}</ol>
        </section>
        """

    return f"""
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            @page {{
                size: A4 portrait;
                margin: 1.35cm 1.25cm 1.45cm;
                @bottom-left {{
                    content: "{html.escape(footer_label)}";
                    font-size: 9px;
                    color: #64748b;
                }}
                @bottom-right {{
                    content: "Page " counter(page) " of " counter(pages);
                    font-size: 9px;
                    color: #64748b;
                }}
            }}
            body {{
                margin: 0;
                color: #172033;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                line-height: 1.42;
            }}
            .cover {{
                border-bottom: 2px solid #1f2937;
                padding-bottom: 18px;
                margin-bottom: 18px;
            }}
            .eyebrow {{
                color: #64748b;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: .08em;
                text-transform: uppercase;
            }}
            h1 {{
                margin: 4px 0 8px;
                font-size: 28px;
                line-height: 1.1;
                color: #0f172a;
            }}
            .case-name {{
                color: #334155;
                font-size: 14px;
                font-weight: 600;
            }}
            .summary-grid {{
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 9px;
                margin-top: 16px;
            }}
            .summary-card {{
                border: 1px solid #d8dee8;
                border-radius: 7px;
                padding: 9px 10px;
                background: #f8fafc;
            }}
            .summary-card span {{
                display: block;
                color: #64748b;
                font-size: 9px;
                font-weight: 700;
                text-transform: uppercase;
            }}
            .summary-card strong {{
                display: block;
                margin-top: 3px;
                color: #0f172a;
                font-size: 13px;
            }}
            .day {{
                margin-top: 18px;
                break-inside: avoid;
            }}
            .day h2 {{
                margin: 0 0 9px;
                padding: 7px 9px;
                border-left: 4px solid #475569;
                background: #eef2f7;
                color: #111827;
                font-size: 13px;
            }}
            .event {{
                display: grid;
                grid-template-columns: 58px minmax(0, 1fr);
                gap: 10px;
                padding: 9px 0;
                border-bottom: 1px solid #e5e7eb;
                break-inside: avoid;
            }}
            .time {{
                color: #334155;
                font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
                font-size: 11px;
                font-weight: 700;
                text-align: right;
            }}
            .event-title {{
                color: #0f172a;
                font-size: 12px;
                font-weight: 700;
            }}
            .event-meta {{
                display: flex;
                flex-wrap: wrap;
                gap: 4px;
                margin-top: 4px;
            }}
            .type-pill, .meta-pill, .source-marks {{
                display: inline-block;
                border: 1px solid #d8dee8;
                border-radius: 999px;
                padding: 2px 6px;
                color: #475569;
                font-size: 9px;
                font-weight: 600;
            }}
            .type-pill {{
                border-color: #cbd5e1;
                background: #f8fafc;
                color: #1f2937;
            }}
            .summary, .notes {{
                margin: 6px 0 0;
                color: #334155;
                font-size: 10.5px;
            }}
            .entities {{
                margin-top: 6px;
            }}
            .entity-chip {{
                display: inline-block;
                margin: 0 4px 4px 0;
                border-radius: 999px;
                background: #ecfdf5;
                color: #0f766e;
                padding: 2px 6px;
                font-size: 9px;
                font-weight: 600;
            }}
            .notebook-notes {{
                margin: 7px 0 0;
                padding-left: 18px;
                color: #334155;
                font-size: 10px;
            }}
            .notebook-notes span {{
                display: block;
            }}
            .appendix {{
                break-before: page;
            }}
            .appendix h2 {{
                margin-top: 0;
                font-size: 18px;
            }}
            .appendix ol {{
                padding-left: 0;
                list-style: none;
            }}
            .appendix li {{
                display: grid;
                grid-template-columns: 36px 1fr;
                gap: 8px;
                border-bottom: 1px solid #e5e7eb;
                padding: 6px 0;
                break-inside: avoid;
            }}
            .appendix li span {{
                color: #475569;
                font-weight: 700;
            }}
            .appendix p {{
                margin: 0;
                color: #334155;
                font-size: 10px;
                overflow-wrap: anywhere;
            }}
        </style>
    </head>
    <body>
        <section class="cover">
            <div class="eyebrow">Timeline Chronology</div>
            <h1>{html.escape(title)}</h1>
            <div class="case-name">{html.escape(case_name)}</div>
            <div class="summary-grid">
                <div class="summary-card"><span>Events</span><strong>{len(events)}</strong></div>
                <div class="summary-card"><span>Date span</span><strong>{html.escape(date_span)}</strong></div>
                <div class="summary-card"><span>Generated by</span><strong>{html.escape(generated_by)}</strong></div>
                <div class="summary-card"><span>Generated</span><strong>{html.escape(generated_at)}</strong></div>
            </div>
        </section>
        {''.join(day_sections)}
        {appendix}
    </body>
    </html>
    """


def _render_pdf(
    *,
    events: list[dict[str, Any]],
    case_name: str,
    title: str,
    fields: dict[str, bool],
    detail_level: str,
    generated_by: str,
    footer_label: str,
    notes_by_event: dict[str, list[dict[str, str | None]]],
) -> bytes:
    from weasyprint import HTML

    html_text = _render_pdf_html(
        events=events,
        case_name=case_name,
        title=title,
        fields=fields,
        detail_level=detail_level,
        generated_by=generated_by,
        footer_label=footer_label,
        notes_by_event=notes_by_event,
    )
    return HTML(string=html_text).write_pdf()


def export_timeline(
    db: Session,
    *,
    case_id: UUID,
    case_name: str,
    current_user: User,
    export_format: str,
    source: str,
    view_id: UUID | None = None,
    event_keys: list[str] | None = None,
    title: str | None = None,
    detail_level: str = "standard",
    fields: dict[str, Any] | None = None,
    footer_label: str = "Confidential",
) -> TimelineExport:
    export_format = (export_format or "pdf").lower()
    if export_format not in {"pdf", "csv"}:
        raise ValueError("Timeline export format must be pdf or csv")
    if source not in {"view", "selection", "filtered"}:
        raise ValueError("Timeline export source must be view, selection, or filtered")
    if source == "view" and not view_id:
        raise ValueError("Timeline view export requires view_id")
    if source != "view" and not event_keys:
        raise ValueError("Timeline export requires at least one event")

    detail_level = detail_level if detail_level in {"compact", "standard", "detailed"} else "standard"
    events, view_title, view_defaults = _resolve_export_events(
        db,
        case_id=case_id,
        view_id=view_id if source == "view" else None,
        event_keys=event_keys,
        require_all=source != "view",
    )
    limit = MAX_PDF_EVENTS if export_format == "pdf" else MAX_CSV_EVENTS
    if len(events) > limit:
        raise ValueError(f"{export_format.upper()} exports can include at most {limit} events")

    view_default_fields = view_defaults.get("fields") if isinstance(view_defaults, dict) else {}
    if not isinstance(view_default_fields, dict):
        view_default_fields = {}
    merged_fields = _normalize_fields({**view_default_fields, **(fields or {})}, detail_level)
    final_title = _clean_text(title) or view_title or "Timeline Export"
    generated_by = current_user.name or current_user.email
    note_map = (
        _notes_by_event(db, case_id=case_id, event_keys=[str(event.get("key")) for event in events if event.get("key")])
        if merged_fields.get("notebook_notes")
        else {}
    )

    if export_format == "csv":
        content = _render_csv(events, merged_fields, note_map)
        media_type = "text/csv; charset=utf-8"
        extension = "csv"
    else:
        content = _render_pdf(
            events=events,
            case_name=case_name,
            title=final_title,
            fields=merged_fields,
            detail_level=detail_level,
            generated_by=generated_by,
            footer_label=_clean_text(footer_label) or "Confidential",
            notes_by_event=note_map,
        )
        media_type = "application/pdf"
        extension = "pdf"

    system_log_service.log(
        log_type=LogType.CASE_OPERATION,
        origin=LogOrigin.FRONTEND,
        action="Export Timeline",
        details={
            "case_id": str(case_id),
            "source": source,
            "view_id": str(view_id) if view_id else None,
            "format": export_format,
            "event_count": len(events),
        },
        user=current_user.email,
        success=True,
        db=db,
    )
    db.flush()
    db.commit()

    filename = f"{_safe_filename(final_title)}-{datetime.now().strftime('%Y%m%d')}.{extension}"
    return TimelineExport(content=content, filename=filename, media_type=media_type)
