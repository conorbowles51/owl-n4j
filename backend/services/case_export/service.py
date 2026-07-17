"""PDF composition for case exports."""

from __future__ import annotations

import html
import importlib
import re
from dataclasses import dataclass
from typing import Iterable

from services.case_export.registry import (
    ExportContext,
    get_registered_sections,
    section_metadata,
)

# Importing the package registers built-in sections.
importlib.import_module("services.case_export.sections")


@dataclass(frozen=True)
class CaseExport:
    content: bytes
    filename: str
    media_type: str


def list_export_sections() -> list[dict]:
    return section_metadata()


def render_case_export_html(
    context: ExportContext,
    *,
    section_keys: Iterable[str] | None = None,
) -> str:
    selected = set(section_keys or [])
    sections = [
        section
        for section in get_registered_sections()
        if not selected or section.key in selected
    ]
    rendered_sections = []
    for section in sections:
        try:
            rendered_sections.append(section.render(context))
        except Exception as exc:
            rendered_sections.append(_error_section(section.title, str(exc)))

    generated_by = context.current_user.name or context.current_user.email
    generated_at = context.generated_at.strftime("%Y-%m-%d %H:%M UTC")
    return f"""
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            @page {{
                size: A4;
                margin: 18mm 14mm;
                @bottom-right {{
                    content: "Confidential | " counter(page) " of " counter(pages);
                    color: #64748b;
                    font-size: 8px;
                }}
            }}
            body {{
                color: #111827;
                font-family: Arial, sans-serif;
                line-height: 1.42;
                margin: 0;
            }}
            .cover {{
                border-bottom: 2px solid #111827;
                margin-bottom: 18px;
                padding-bottom: 12px;
            }}
            .eyebrow {{
                color: #64748b;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: .08em;
                text-transform: uppercase;
            }}
            h1 {{
                font-size: 26px;
                margin: 4px 0 8px;
            }}
            h2 {{
                font-size: 18px;
                margin: 0 0 4px;
            }}
            .meta, .section-meta {{
                color: #64748b;
                font-size: 10px;
                margin: 0 0 10px;
            }}
            .export-section {{
                break-inside: avoid;
                margin: 0 0 20px;
                page-break-inside: avoid;
            }}
            .visualization-section {{
                break-before: page;
            }}
            .visualization-section:first-of-type {{
                break-before: auto;
            }}
            .visualization-image {{
                border: 1px solid #d1d5db;
                display: block;
                max-height: 210mm;
                max-width: 100%;
                object-fit: contain;
                width: 100%;
            }}
            .error {{
                background: #fef2f2;
                border: 1px solid #fecaca;
                color: #991b1b;
                padding: 10px;
            }}
        </style>
    </head>
    <body>
        <section class="cover">
            <div class="eyebrow">Case Export</div>
            <h1>{html.escape(context.case_name)}</h1>
            <p class="meta">Generated {html.escape(generated_at)} by {html.escape(generated_by)}</p>
        </section>
        {''.join(rendered_sections)}
    </body>
    </html>
    """


def render_case_export_pdf(
    context: ExportContext,
    *,
    section_keys: Iterable[str] | None = None,
) -> CaseExport:
    try:
        from weasyprint import HTML
    except Exception as exc:
        raise ValueError(f"PDF export is unavailable: {exc}") from exc

    html_text = render_case_export_html(context, section_keys=section_keys)
    return CaseExport(
        content=HTML(string=html_text).write_pdf(),
        filename=f"{_safe_filename(context.case_name or 'case-export')}-case-export.pdf",
        media_type="application/pdf",
    )


def _error_section(title: str, error: str) -> str:
    return f"""
    <section class="export-section error">
        <h2>{html.escape(title)}</h2>
        <p>Section could not be rendered: {html.escape(error)}</p>
    </section>
    """


def _safe_filename(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower())
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-._")
    return (normalized or "case-export")[:80]
