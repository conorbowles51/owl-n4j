"""Case overview skeleton section."""

from __future__ import annotations

from html import escape

from services.case_export.registry import register_section
from services.case_export.types import ExportSection, SectionContext


def _text(value: str | None) -> str:
    value = (value or "").strip()
    return value or "No description recorded."


def render_case_overview(context: SectionContext) -> str:
    created_at = context.case.created_at.strftime("%Y-%m-%d") if context.case.created_at else "-"
    updated_at = context.case.updated_at.strftime("%Y-%m-%d") if context.case.updated_at else "-"

    return f"""
        <h2>Case Overview</h2>
        <p class="lead">{escape(_text(context.case.description))}</p>
        <table class="fact-table">
            <tbody>
                <tr>
                    <th>Case ID</th>
                    <td>{escape(str(context.case.id))}</td>
                </tr>
                <tr>
                    <th>Owner User ID</th>
                    <td>{escape(str(context.case.owner_user_id))}</td>
                </tr>
                <tr>
                    <th>Created</th>
                    <td>{escape(created_at)}</td>
                </tr>
                <tr>
                    <th>Last Updated</th>
                    <td>{escape(updated_at)}</td>
                </tr>
            </tbody>
        </table>
    """


register_section(
    ExportSection(
        key="case_overview",
        label="Case Overview",
        description="Skeleton case metadata and description section.",
        default_enabled=True,
        order=10,
        render=render_case_overview,
    )
)
