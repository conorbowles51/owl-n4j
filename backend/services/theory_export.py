"""Theory-scoped investigation exports."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from postgres.models.case import Case
from postgres.models.user import User
from services.system_log_service import LogOrigin, LogType, system_log_service
from services.workspace_service import workspace_service


@dataclass(frozen=True)
class TheoryExport:
    content: bytes
    filename: str
    media_type: str


class TheoryAccessDenied(Exception):
    """Raised when a user may view the case but not the theory."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _user_role(user: User) -> str:
    role = getattr(user, "global_role", None)
    return getattr(role, "value", role) or "investigator"


def _generated_by(user: User) -> str:
    return getattr(user, "name", None) or getattr(user, "email", None) or "Unknown"


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_filename(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return (normalized or "theory-export")[:80]


def _format_generated_at(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _css_string(value: str) -> str:
    return json.dumps(value)


def _format_date(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return "Undated"
    return html.escape(text[:19].replace("T", " "))


def _list_items(items: Any, empty_label: str) -> str:
    values = [_clean_text(item) for item in items or [] if _clean_text(item)]
    if not values:
        return f'<p class="empty-state">{html.escape(empty_label)}</p>'
    return "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in values) + "</ul>"


def _field(label: str, value: Any, empty: str = "Not recorded") -> str:
    text = _clean_text(value) or empty
    return f"<span>{html.escape(label)}</span><strong>{html.escape(text)}</strong>"


def _render_event_items(events: list[dict[str, Any]]) -> str:
    if not events:
        return '<p class="empty-state">No scoped events recorded.</p>'

    items: list[str] = []
    for event in events:
        items.append(
            """
            <li>
                <div class="event-date">{date}</div>
                <div>
                    <div class="event-title">{title}</div>
                    <div class="event-meta">{thread} &middot; {type}</div>
                    <p>{description}</p>
                </div>
            </li>
            """.format(
                date=_format_date(event.get("date")),
                title=html.escape(_clean_text(event.get("title")) or "Untitled event"),
                thread=html.escape(_clean_text(event.get("thread")) or "Theory"),
                type=html.escape(_clean_text(event.get("type")) or "event"),
                description=html.escape(_clean_text(event.get("description")) or "No description recorded."),
            )
        )
    return '<ol class="event-list">' + "".join(items) + "</ol>"


def _render_witnesses(witnesses: list[dict[str, Any]]) -> str:
    if not witnesses:
        return '<p class="empty-state">No witnesses attached.</p>'
    rows: list[str] = []
    for witness in witnesses:
        rows.append(
            """
            <article class="record">
                <h3>{name}</h3>
                <div class="record-grid">
                    <div>{category}</div>
                    <div>{credibility}</div>
                </div>
                <p>{summary}</p>
            </article>
            """.format(
                name=html.escape(_clean_text(witness.get("name")) or "Unnamed witness"),
                category=_field("Category", witness.get("category")),
                credibility=_field("Credibility", witness.get("credibility_rating")),
                summary=html.escape(_clean_text(witness.get("statement_summary")) or "No statement summary recorded."),
            )
        )
    return "".join(rows)


def _render_notes(notes: list[dict[str, Any]]) -> str:
    if not notes:
        return '<p class="empty-state">No notes attached.</p>'
    rows: list[str] = []
    for note in notes:
        tags = ", ".join(_clean_text(tag) for tag in note.get("tags") or [] if _clean_text(tag))
        rows.append(
            """
            <article class="record">
                <h3>{title}</h3>
                <p>{content}</p>
                <div class="tags">{tags}</div>
            </article>
            """.format(
                title=html.escape(_clean_text(note.get("title")) or "Untitled note"),
                content=html.escape(_clean_text(note.get("content")) or "No note content recorded."),
                tags=html.escape(tags or "No tags"),
            )
        )
    return "".join(rows)


def _render_file_records(records: list[dict[str, Any]], empty_label: str) -> str:
    if not records:
        return f'<p class="empty-state">{html.escape(empty_label)}</p>'
    rows: list[str] = []
    for record in records:
        rows.append(
            """
            <li>
                <strong>{filename}</strong>
                <span>{created_at}</span>
                <code>{record_id}</code>
            </li>
            """.format(
                filename=html.escape(_clean_text(record.get("original_filename")) or "Unnamed file"),
                created_at=_format_date(record.get("created_at")),
                record_id=html.escape(_clean_text(record.get("id"))),
            )
        )
    return '<ul class="file-list">' + "".join(rows) + "</ul>"


def _render_theory_pdf_html(
    *,
    theory: dict[str, Any],
    case_name: str,
    scoped_events: list[dict[str, Any]],
    scoped_evidence: dict[str, list[dict[str, Any]]],
    generated_by: str,
    generated_at: datetime,
    footer_label: str,
) -> str:
    title = _clean_text(theory.get("title")) or "Theory Export"
    hypothesis = _clean_text(theory.get("hypothesis")) or "No hypothesis recorded."
    type_label = _clean_text(theory.get("type")) or "Unspecified"
    confidence = theory.get("confidence_score")
    confidence_label = f"{confidence}%" if confidence is not None else "Not recorded"
    privilege = _clean_text(theory.get("privilege_level")) or "PUBLIC"
    generated_at_label = _format_generated_at(generated_at)

    return f"""
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            @page {{
                margin: 18mm 14mm;
                @bottom-left {{
                    content: {_css_string(footer_label)};
                    color: #64748b;
                    font-size: 9px;
                }}
                @bottom-right {{
                    content: "Page " counter(page) " of " counter(pages);
                    color: #64748b;
                    font-size: 9px;
                }}
            }}
            body {{
                color: #0f172a;
                font-family: Inter, Arial, sans-serif;
                font-size: 11px;
                line-height: 1.45;
            }}
            h1, h2, h3, p {{
                margin: 0;
            }}
            .cover {{
                border-bottom: 2px solid #0f172a;
                margin-bottom: 18px;
                padding-bottom: 18px;
            }}
            .eyebrow {{
                color: #475569;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.08em;
                text-transform: uppercase;
            }}
            h1 {{
                font-size: 30px;
                line-height: 1.1;
                margin-top: 8px;
            }}
            .case-name {{
                color: #334155;
                font-size: 14px;
                margin-top: 8px;
            }}
            .summary-grid {{
                display: grid;
                gap: 8px;
                grid-template-columns: repeat(3, 1fr);
                margin-top: 18px;
            }}
            .summary-card {{
                border: 1px solid #cbd5e1;
                padding: 9px;
            }}
            .summary-card span,
            .record-grid span {{
                color: #64748b;
                display: block;
                font-size: 9px;
                font-weight: 700;
                text-transform: uppercase;
            }}
            .summary-card strong,
            .record-grid strong {{
                display: block;
                font-size: 12px;
                margin-top: 3px;
            }}
            section {{
                break-inside: avoid;
                margin-top: 18px;
            }}
            h2 {{
                border-bottom: 1px solid #cbd5e1;
                font-size: 16px;
                margin-bottom: 10px;
                padding-bottom: 5px;
            }}
            .section-block {{
                margin-bottom: 12px;
            }}
            .section-block h3,
            .record h3 {{
                font-size: 12px;
                margin-bottom: 5px;
            }}
            ul {{
                margin: 0;
                padding-left: 18px;
            }}
            li {{
                margin-bottom: 5px;
            }}
            .empty-state {{
                color: #64748b;
                font-style: italic;
            }}
            .event-list {{
                list-style: none;
                padding: 0;
            }}
            .event-list li {{
                border-bottom: 1px solid #e2e8f0;
                display: grid;
                gap: 10px;
                grid-template-columns: 95px 1fr;
                padding: 8px 0;
            }}
            .event-date {{
                color: #334155;
                font-weight: 700;
            }}
            .event-title {{
                font-weight: 700;
            }}
            .event-meta {{
                color: #64748b;
                font-size: 9px;
                margin-top: 2px;
                text-transform: uppercase;
            }}
            .record {{
                border-bottom: 1px solid #e2e8f0;
                margin-bottom: 10px;
                padding-bottom: 10px;
            }}
            .record-grid {{
                display: grid;
                gap: 8px;
                grid-template-columns: repeat(2, 1fr);
                margin-bottom: 6px;
            }}
            .tags {{
                color: #64748b;
                font-size: 9px;
                margin-top: 5px;
            }}
            .file-list {{
                list-style: none;
                padding: 0;
            }}
            .file-list li {{
                border-bottom: 1px solid #e2e8f0;
                display: grid;
                gap: 6px;
                grid-template-columns: 1fr 105px 190px;
                padding: 6px 0;
            }}
            code {{
                color: #475569;
                font-family: "Courier New", monospace;
                font-size: 9px;
            }}
        </style>
    </head>
    <body>
        <section class="cover">
            <div class="eyebrow">Theory Export</div>
            <h1>{html.escape(title)}</h1>
            <div class="case-name">{html.escape(case_name)}</div>
            <div class="summary-grid">
                <div class="summary-card">{_field("Type", type_label)}</div>
                <div class="summary-card">{_field("Confidence", confidence_label)}</div>
                <div class="summary-card">{_field("Privilege", privilege)}</div>
                <div class="summary-card">{_field("Events", len(scoped_events))}</div>
                <div class="summary-card">{_field("Generated by", generated_by)}</div>
                <div class="summary-card">{_field("Generated", generated_at_label)}</div>
            </div>
        </section>

        <section>
            <h2>Narrative</h2>
            <div class="section-block">
                <h3>Hypothesis</h3>
                <p>{html.escape(hypothesis)}</p>
            </div>
            <div class="section-block">
                <h3>Supporting Evidence</h3>
                {_list_items(theory.get("supporting_evidence"), "No supporting evidence recorded.")}
            </div>
            <div class="section-block">
                <h3>Counter Arguments</h3>
                {_list_items(theory.get("counter_arguments"), "No counter arguments recorded.")}
            </div>
            <div class="section-block">
                <h3>Next Steps</h3>
                {_list_items(theory.get("next_steps"), "No next steps recorded.")}
            </div>
        </section>

        <section>
            <h2>Scoped Events</h2>
            {_render_event_items(scoped_events)}
        </section>

        <section>
            <h2>Scoped Evidence</h2>
            <div class="section-block">
                <h3>Witnesses</h3>
                {_render_witnesses(scoped_evidence.get("witnesses") or [])}
            </div>
            <div class="section-block">
                <h3>Notes</h3>
                {_render_notes(scoped_evidence.get("notes") or [])}
            </div>
            <div class="section-block">
                <h3>Evidence</h3>
                {_render_file_records(scoped_evidence.get("evidence") or [], "No evidence files attached.")}
            </div>
            <div class="section-block">
                <h3>Documents</h3>
                {_render_file_records(scoped_evidence.get("documents") or [], "No documents attached.")}
            </div>
        </section>
    </body>
    </html>
    """


def _render_pdf(
    *,
    theory: dict[str, Any],
    case_name: str,
    scoped_events: list[dict[str, Any]],
    scoped_evidence: dict[str, list[dict[str, Any]]],
    generated_by: str,
    generated_at: datetime,
    footer_label: str,
) -> bytes:
    from weasyprint import HTML

    html_text = _render_theory_pdf_html(
        theory=theory,
        case_name=case_name,
        scoped_events=scoped_events,
        scoped_evidence=scoped_evidence,
        generated_by=generated_by,
        generated_at=generated_at,
        footer_label=footer_label,
    )
    return HTML(string=html_text).write_pdf()


def render_theory_pdf(
    db: Session,
    *,
    case: Case,
    theory_id: str,
    current_user: User,
    footer_label: str = "Confidential",
) -> TheoryExport:
    theory = workspace_service.get_theory(str(case.id), theory_id)
    if not theory:
        raise ValueError("Theory not found")

    if theory.get("privilege_level") == "ATTORNEY_ONLY" and _user_role(current_user) != "attorney":
        raise TheoryAccessDenied("Theory export is attorney-only")

    generated_at = _now()
    generated_by = _generated_by(current_user)
    scoped_events = workspace_service.get_theory_timeline(str(case.id), theory_id)
    scoped_evidence = workspace_service.get_theory_scoped_evidence(str(case.id), theory_id)
    content = _render_pdf(
        theory=theory,
        case_name=case.title,
        scoped_events=scoped_events,
        scoped_evidence=scoped_evidence,
        generated_by=generated_by,
        generated_at=generated_at,
        footer_label=_clean_text(footer_label) or "Confidential",
    )

    system_log_service.log(
        log_type=LogType.CASE_OPERATION,
        origin=LogOrigin.FRONTEND,
        action="Export Theory",
        details={
            "case_id": str(case.id),
            "theory_id": theory_id,
            "event_count": len(scoped_events),
            "evidence_count": len(scoped_evidence.get("evidence") or []),
            "document_count": len(scoped_evidence.get("documents") or []),
            "witness_count": len(scoped_evidence.get("witnesses") or []),
            "note_count": len(scoped_evidence.get("notes") or []),
        },
        user=current_user.email,
        success=True,
        db=db,
    )
    db.flush()
    db.commit()

    filename = f"{_safe_filename(theory.get('title') or 'theory-export')}-{generated_at.strftime('%Y%m%d')}.pdf"
    return TheoryExport(content=content, filename=filename, media_type="application/pdf")
