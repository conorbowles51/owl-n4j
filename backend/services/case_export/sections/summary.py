"""Case summary section."""

from __future__ import annotations

from sqlalchemy import select

from postgres.models.case_profile import CaseProfile
from services.case_export.registry import register_section
from services.case_export.sections._html import clean_text, empty_state, html_text, preformatted
from services.case_export.types import ExportSection, SectionContext


def _profile_summaries(context: SectionContext) -> list[CaseProfile]:
    return list(
        context.db.scalars(
            select(CaseProfile)
            .where(
                CaseProfile.case_id == context.case.id,
                CaseProfile.archived_at.is_(None),
                CaseProfile.summary.is_not(None),
            )
            .order_by(CaseProfile.profile_type, CaseProfile.display_name, CaseProfile.id)
        )
    )


def render_summary(context: SectionContext) -> str:
    case_summary = clean_text(context.case.description)
    profiles = [
        profile
        for profile in _profile_summaries(context)
        if clean_text(profile.summary)
    ]

    case_block = (
        f"""
        <h3 class="subsection-title">Case Description</h3>
        {preformatted(case_summary)}
        """
        if case_summary
        else empty_state("No case description recorded.")
    )

    if profiles:
        profile_items = "".join(
            f"""
            <div class="item-card">
                <div class="item-title">{html_text(profile.display_name)}</div>
                <div class="item-meta">{html_text(profile.profile_type)}</div>
                {preformatted(profile.summary)}
            </div>
            """
            for profile in profiles
        )
    else:
        profile_items = empty_state("No entity summaries recorded.")

    return f"""
        <h2>Summary</h2>
        <p class="lead">Case description and investigator-curated entity summaries.</p>
        {case_block}
        <h3 class="subsection-title">Entity Summaries</h3>
        {profile_items}
    """


register_section(
    ExportSection(
        key="summary",
        label="Summary",
        description="Case description and curated entity summary notes.",
        default_enabled=True,
        order=20,
        render=render_summary,
    )
)
