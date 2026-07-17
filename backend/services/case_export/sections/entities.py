"""Curated entities section."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from postgres.models.case_profile import CaseProfile
from services.case_export.registry import register_section
from services.case_export.sections._html import badge, clean_text, empty_state, html_text
from services.case_export.types import ExportSection, SectionContext


def _profiles(context: SectionContext) -> list[CaseProfile]:
    return list(
        context.db.scalars(
            select(CaseProfile)
            .options(selectinload(CaseProfile.attributes))
            .where(CaseProfile.case_id == context.case.id, CaseProfile.archived_at.is_(None))
            .order_by(CaseProfile.profile_type, CaseProfile.display_name, CaseProfile.id)
        )
    )


def _type_label(value: str | None) -> str:
    text = clean_text(value).replace("_", " ")
    return text.title() if text else "-"


def _attribute_summary(profile: CaseProfile) -> str:
    grouped: dict[str, list[str]] = defaultdict(list)
    for attribute in profile.attributes:
        value = clean_text(attribute.value)
        if not value:
            continue
        label = clean_text(attribute.name) or _type_label(attribute.kind)
        grouped[label].append(value)

    parts: list[str] = []
    for label, values in grouped.items():
        unique_values = list(dict.fromkeys(values))
        parts.append(f"{label}: {', '.join(unique_values)}")
    return "; ".join(parts)


def render_entities(context: SectionContext) -> str:
    profiles = _profiles(context)
    if not profiles:
        content = empty_state("No curated entities recorded for this case.")
    else:
        rows = "".join(
            f"""
            <tr>
                <td>
                    <strong>{html_text(profile.display_name)}</strong>
                    {badge(profile.importance)}
                </td>
                <td>{html_text(_type_label(profile.profile_type))}</td>
                <td>{html_text(profile.summary) or '<span class="muted">-</span>'}</td>
                <td>{html_text(_attribute_summary(profile)) or '<span class="muted">-</span>'}</td>
            </tr>
            """
            for profile in profiles
        )
        content = f"""
        <table class="data-table">
            <thead>
                <tr>
                    <th>Entity</th>
                    <th>Type</th>
                    <th>Summary</th>
                    <th>Attributes</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
        """

    return f"""
        <h2>Entities</h2>
        <p class="lead">Investigator-curated entities linked to this case.</p>
        {content}
    """


register_section(
    ExportSection(
        key="entities",
        label="Entities",
        description="Curated people, places, events, devices, organisations, vehicles, and other entities.",
        default_enabled=True,
        order=30,
        render=render_entities,
    )
)
