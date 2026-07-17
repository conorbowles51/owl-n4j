"""Notebook notes section."""

from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import selectinload

from postgres.models.notebook import NotebookNote
from services.case_export.registry import register_section
from services.case_export.sections._html import (
    badge_list,
    clean_text,
    empty_state,
    format_datetime,
    html_text,
    preformatted,
)
from services.case_export.types import ExportSection, SectionContext


def _notes(context: SectionContext) -> list[NotebookNote]:
    return list(
        context.db.scalars(
            select(NotebookNote)
            .options(selectinload(NotebookNote.links))
            .where(NotebookNote.case_id == context.case.id, NotebookNote.deleted_at.is_(None))
            .order_by(desc(NotebookNote.updated_at), desc(NotebookNote.created_at), desc(NotebookNote.id))
        )
    )


def _author(note: NotebookNote) -> str:
    return clean_text(note.author_name) or clean_text(note.author_email) or "Unknown author"


def _link_items(note: NotebookNote) -> str:
    if not note.links:
        return ""
    items = "".join(
        f"""
        <li>
            {html_text(link.target_label or link.target_id)}
            <span class="muted">({html_text(link.target_type)})</span>
        </li>
        """
        for link in note.links
    )
    return f"<ul>{items}</ul>"


def render_notes(context: SectionContext) -> str:
    notes = _notes(context)
    if not notes:
        content = empty_state("No notebook notes recorded for this case.")
    else:
        content = "".join(
            f"""
            <div class="item-card">
                <div class="item-title">{html_text(note.title) or "Untitled note"}</div>
                <div class="item-meta">
                    Updated {html_text(format_datetime(note.updated_at))}
                    by {html_text(_author(note))}
                </div>
                {badge_list(list(note.tags or []))}
                {preformatted(note.body)}
                {_link_items(note)}
            </div>
            """
            for note in notes
        )

    return f"""
        <h2>Notes</h2>
        <p class="lead">Case notebook notes, tags, and linked investigative objects.</p>
        {content}
    """


register_section(
    ExportSection(
        key="notes",
        label="Notes",
        description="Case notebook notes with tags and object links.",
        default_enabled=True,
        order=40,
        render=render_notes,
    )
)
