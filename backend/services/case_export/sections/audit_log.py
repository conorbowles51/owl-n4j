"""Case audit log section."""

from __future__ import annotations

from services.case_export.registry import register_section
from services.case_export.sections._html import details_json, empty_state, html_text, preformatted
from services.case_export.types import ExportSection, SectionContext
from services.system_log_service import system_log_service


def render_audit_log(context: SectionContext) -> str:
    result = system_log_service.get_case_logs(
        str(context.case.id),
        limit=10_000,
        db=context.db,
    )
    logs = result["logs"]

    if not logs:
        content = empty_state("No case-scoped audit log entries recorded.")
    else:
        rows = "".join(
            f"""
            <tr>
                <td>{html_text(log.get("timestamp"))}</td>
                <td>
                    <strong>{html_text(log.get("action"))}</strong>
                    <div class="muted">{html_text(log.get("type"))} / {html_text(log.get("origin"))}</div>
                </td>
                <td>{html_text(log.get("user")) or '<span class="muted">-</span>'}</td>
                <td>{'Success' if log.get("success") else 'Failed'}</td>
                <td>
                    {html_text(log.get("error")) if log.get("error") else ""}
                    {preformatted(details_json(log.get("details")))}
                </td>
            </tr>
            """
            for log in logs
        )
        content = f"""
        <table class="data-table">
            <thead>
                <tr>
                    <th>Timestamp</th>
                    <th>Action</th>
                    <th>User</th>
                    <th>Result</th>
                    <th>Details</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
        """

    return f"""
        <h2>Audit Log</h2>
        <p class="lead">Case-scoped system log entries in reverse chronological order.</p>
        {content}
    """


register_section(
    ExportSection(
        key="audit_log",
        label="Audit Log",
        description="Actual system audit trail entries associated with this case.",
        default_enabled=True,
        order=90,
        render=render_audit_log,
    )
)
