"""Evidence transcriptions section."""

from __future__ import annotations

from sqlalchemy import select

from postgres.models.evidence import EvidenceFile
from services.case_export.registry import register_section
from services.case_export.sections._html import badge, clean_text, empty_state, format_datetime, html_text, preformatted
from services.case_export.types import ExportSection, SectionContext


def _files(context: SectionContext) -> list[EvidenceFile]:
    records = context.db.scalars(
        select(EvidenceFile)
        .where(EvidenceFile.case_id == context.case.id, EvidenceFile.transcription.is_not(None))
        .order_by(EvidenceFile.original_filename, EvidenceFile.id)
    ).all()
    return [record for record in records if clean_text(record.transcription)]


def render_transcriptions(context: SectionContext) -> str:
    files = _files(context)
    if not files:
        content = empty_state("No evidence transcriptions recorded for this case.")
    else:
        content = "".join(
            f"""
            <div class="item-card">
                <div class="item-title">{html_text(file.original_filename)}</div>
                <div class="item-meta">
                    {html_text(file.source_type) or "Evidence"}
                    {badge(file.status)}
                    Processed {html_text(format_datetime(file.processed_at))}
                </div>
                {preformatted(file.transcription)}
            </div>
            """
            for file in files
        )

    return f"""
        <h2>Evidence Transcriptions</h2>
        <p class="lead">Stored transcriptions generated from case evidence files.</p>
        {content}
    """


register_section(
    ExportSection(
        key="transcriptions",
        label="Evidence Transcriptions",
        description="Evidence audio or wiretap transcriptions stored for this case.",
        default_enabled=True,
        order=50,
        render=render_transcriptions,
    )
)
