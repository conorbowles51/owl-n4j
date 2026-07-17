"""Case file export rendering service."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import datetime, timezone
from html import escape

from sqlalchemy.orm import Session

from postgres.models.case import Case
from postgres.models.user import User
from services.case_export import sections  # noqa: F401
from services.case_export.registry import get_sections, list_sections
from services.case_export.types import CaseExportResult, ExportSection, SectionContext


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower()).strip("-")
    return cleaned or "case-export"


def _css_string(value: str) -> str:
    return json.dumps(value)


def available_sections() -> list[dict[str, object]]:
    return [
        {
            "key": section.key,
            "label": section.label,
            "description": section.description,
            "default_enabled": section.default_enabled,
            "order": section.order,
        }
        for section in list_sections()
    ]


def _section_class(section: ExportSection) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", section.key.lower()).strip("-") or "section"


def _render_html(
    *,
    case: Case,
    generated_at: datetime,
    rendered_sections: list[tuple[ExportSection, str]],
    footer_label: str,
) -> str:
    generated_label = generated_at.strftime("%Y-%m-%d %H:%M UTC")
    body_sections = "\n".join(
        f"""
        <section class="case-export-section section-{_section_class(section)}">
            {fragment}
        </section>
        """
        for section, fragment in rendered_sections
    )

    return f"""
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{escape(case.title)} Case Export</title>
        <style>
            @page {{
                size: A4;
                margin: 24mm 18mm 20mm;
                @top-left {{
                    content: {_css_string(case.title)};
                    color: #475569;
                    font-size: 9px;
                }}
                @top-right {{
                    content: {_css_string(generated_label)};
                    color: #475569;
                    font-size: 9px;
                }}
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
            * {{
                box-sizing: border-box;
            }}
            body {{
                color: #111827;
                font-family: Arial, sans-serif;
                font-size: 11px;
                line-height: 1.5;
                margin: 0;
            }}
            h1, h2, h3, p {{
                margin-top: 0;
            }}
            h1 {{
                font-size: 30px;
                line-height: 1.12;
                margin-bottom: 16px;
            }}
            h2 {{
                border-bottom: 1px solid #cbd5e1;
                color: #0f172a;
                font-size: 20px;
                margin-bottom: 14px;
                padding-bottom: 8px;
            }}
            .case-export-section + .case-export-section {{
                break-before: page;
            }}
            .case-export-section {{
                break-after: auto;
            }}
            .cover-page {{
                min-height: 210mm;
                padding-top: 24mm;
            }}
            .document-label {{
                color: #0f766e;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.08em;
                margin-bottom: 12px;
                text-transform: uppercase;
            }}
            .cover-meta {{
                border-bottom: 1px solid #e2e8f0;
                border-top: 1px solid #e2e8f0;
                display: grid;
                grid-template-columns: 1fr;
                margin: 26px 0;
                padding: 10px 0;
            }}
            .cover-meta div {{
                display: grid;
                grid-template-columns: 34mm 1fr;
                padding: 5px 0;
            }}
            .cover-meta dt {{
                color: #64748b;
                font-weight: 700;
            }}
            .cover-meta dd {{
                margin: 0;
                overflow-wrap: anywhere;
            }}
            .included-sections {{
                margin-top: 22mm;
            }}
            .included-sections h2 {{
                font-size: 15px;
            }}
            .included-sections ol {{
                margin: 0;
                padding-left: 18px;
            }}
            .included-sections li {{
                padding: 3px 0;
            }}
            .lead {{
                color: #334155;
                font-size: 12px;
                margin-bottom: 18px;
            }}
            .fact-table {{
                border-collapse: collapse;
                width: 100%;
            }}
            .fact-table th,
            .fact-table td {{
                border-bottom: 1px solid #e5e7eb;
                padding: 8px 6px;
                text-align: left;
                vertical-align: top;
            }}
            .fact-table th {{
                color: #475569;
                font-size: 10px;
                width: 36mm;
            }}
            .fact-table td {{
                overflow-wrap: anywhere;
            }}
            .data-table {{
                border-collapse: collapse;
                margin-top: 12px;
                width: 100%;
            }}
            .data-table th,
            .data-table td {{
                border-bottom: 1px solid #e5e7eb;
                padding: 7px 6px;
                text-align: left;
                vertical-align: top;
            }}
            .data-table th {{
                color: #475569;
                font-size: 9px;
                letter-spacing: 0.04em;
                text-transform: uppercase;
            }}
            .data-table td {{
                overflow-wrap: anywhere;
            }}
            .item-card {{
                border: 1px solid #e5e7eb;
                border-radius: 4px;
                break-inside: avoid;
                margin: 0 0 12px;
                padding: 12px;
            }}
            .item-title {{
                color: #0f172a;
                font-size: 13px;
                font-weight: 700;
                margin-bottom: 4px;
            }}
            .item-meta {{
                color: #64748b;
                font-size: 9px;
                margin-bottom: 8px;
            }}
            .subsection-title {{
                color: #0f172a;
                font-size: 14px;
                margin: 16px 0 8px;
            }}
            .badge-list {{
                margin: 5px 0 0;
            }}
            .badge {{
                background: #f1f5f9;
                border: 1px solid #cbd5e1;
                border-radius: 999px;
                color: #334155;
                display: inline-block;
                font-size: 9px;
                margin: 0 4px 4px 0;
                padding: 1px 6px;
            }}
            .preformatted {{
                overflow-wrap: anywhere;
                white-space: pre-wrap;
            }}
            .empty-state {{
                border: 1px dashed #cbd5e1;
                border-radius: 4px;
                color: #64748b;
                padding: 12px;
            }}
            .muted {{
                color: #64748b;
            }}
        </style>
    </head>
    <body>
        {body_sections}
    </body>
    </html>
    """


def build_case_export_html(
    db: Session,
    *,
    case: Case,
    current_user: User,
    section_keys: Iterable[str] | None = None,
    footer_label: str = "Confidential",
    generated_at: datetime | None = None,
) -> str:
    generated_at = generated_at or _now()
    selected_sections = get_sections(section_keys)
    context = SectionContext(
        db=db,
        case=case,
        current_user=current_user,
        generated_at=generated_at,
        included_sections=tuple(selected_sections),
    )
    rendered_sections: list[tuple[ExportSection, str]] = []
    for section in selected_sections:
        fragment = section.render(context).strip()
        if fragment:
            rendered_sections.append((section, fragment))

    if not rendered_sections:
        raise ValueError("No export sections selected")

    return _render_html(
        case=case,
        generated_at=generated_at,
        rendered_sections=rendered_sections,
        footer_label=(footer_label or "Confidential").strip() or "Confidential",
    )


def render_case_export(
    db: Session,
    *,
    case: Case,
    current_user: User,
    section_keys: Iterable[str] | None = None,
    footer_label: str = "Confidential",
) -> CaseExportResult:
    from weasyprint import HTML

    generated_at = _now()
    html_text = build_case_export_html(
        db,
        case=case,
        current_user=current_user,
        section_keys=section_keys,
        footer_label=footer_label,
        generated_at=generated_at,
    )
    content = HTML(string=html_text).write_pdf()
    filename = f"{_safe_filename(case.title)}-case-export-{generated_at.strftime('%Y%m%d')}.pdf"
    return CaseExportResult(content=content, filename=filename, media_type="application/pdf")
