"""Casework report: the case's Findings first, with the evidence linked to each, then the other sections in the order
the investigator chose.

Sections are Findings, Theories and Notes; the order and which are included are the exporter's choice, Findings
first by default. Each entry prints its title, state, significance, author, text and every item linked to it (with
the link's relationship: supports, contradicts, context). Deleted entries never print. The audit log and the
investigation timeline are not part of this report. The privilege marking is the same three values as the ledger
export, chosen by the exporter, printed on the cover and every page footer, and is not a legal determination.
"""
from __future__ import annotations

import html
from datetime import datetime
from typing import Any, Callable

from services.snapshot_report import PRIVILEGE_BASIS, privilege_label

SECTIONS = {"findings": "finding", "theories": "theory", "notes": "note"}
SECTION_TITLES = {"findings": "Findings", "theories": "Theories", "notes": "Notes"}
DEFAULT_ORDER = ["findings", "theories", "notes"]
MAX_REPORT_ENTRIES = 2000
_SIGNIFICANCE_RANK = {"high": 0, "medium": 1, "low": 2, None: 3}
_RELATIONSHIP_WORDS = {"supports": "Supports", "contradicts": "Contradicts", "context": "Context", "unclassified": "Linked"}
_TARGET_WORDS = {
    "evidence": "Evidence file", "graph_entity": "Entity", "dossier": "Dossier", "entry": "Casework",
    "task": "Task", "deadline": "Deadline", "timeline_event": "Timeline event", "agent_artifact": "Agent output",
}


class CaseworkReportError(ValueError):
    """The report cannot be produced as asked; nothing partial is produced."""


def normalise_sections(sections: list[str] | None) -> list[str]:
    chosen = list(DEFAULT_ORDER if sections is None else sections)
    unknown = [s for s in chosen if s not in SECTIONS]
    if unknown:
        raise CaseworkReportError(f"Unknown report section: {', '.join(unknown)}. Use findings, theories or notes.")
    out: list[str] = []
    for s in chosen:
        if s not in out:
            out.append(s)
    if not out:
        raise CaseworkReportError("Choose at least one section.")
    return out


def collect_entries(list_page: Callable[[str, int, int], dict[str, Any]], entry_type: str) -> list[dict[str, Any]]:
    """Every live entry of one type, page by page (the list endpoint caps a page at 200)."""
    entries: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = list_page(entry_type, 200, offset)
        batch = page.get("entries") or []
        entries.extend(batch)
        offset += len(batch)
        if not batch or offset >= int(page.get("total") or 0):
            break
        if len(entries) > MAX_REPORT_ENTRIES:
            raise CaseworkReportError(
                f"Casework reports support up to {MAX_REPORT_ENTRIES:,} entries per section; no partial report was generated."
            )
    return entries


def _sort(section: str, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if section == "findings":
        return sorted(entries, key=lambda e: (_SIGNIFICANCE_RANK.get(e.get("significance"), 3), str(e.get("title") or "")))
    return sorted(entries, key=lambda e: str(e.get("updated_at") or ""), reverse=True)


def _entry_html(entry: dict[str, Any]) -> str:
    facts = []
    if entry.get("lifecycle_state"):
        facts.append(f"State: {html.escape(str(entry['lifecycle_state']).capitalize())}")
    if entry.get("significance"):
        facts.append(f"Significance: {html.escape(str(entry['significance']).capitalize())}")
    if entry.get("confidence") is not None:
        facts.append(f"Confidence: {int(entry['confidence'])}%")
    if entry.get("review_state") and entry.get("review_state") != "accepted":
        facts.append(f"Review: {html.escape(str(entry['review_state']))}")
    author = entry.get("author_name") or entry.get("author_email")
    if author:
        facts.append(f"Author: {html.escape(str(author))}")
    if entry.get("updated_at"):
        facts.append(f"Updated: {html.escape(str(entry['updated_at'])[:10])}")
    links = entry.get("links") or []
    link_rows = "".join(
        "<li><strong>{}</strong> · {}: {}</li>".format(
            html.escape(_RELATIONSHIP_WORDS.get(link.get("relationship"), "Linked")),
            html.escape(_TARGET_WORDS.get(link.get("target_type"), str(link.get("target_type") or "Item"))),
            html.escape(str(link.get("target_label") or link.get("target_id") or "")),
        )
        for link in links
    )
    title = entry.get("title") or "Untitled note"
    return f"""
    <article class="entry">
      <h3>{html.escape(str(title))}</h3>
      <p class="facts">{' · '.join(facts)}</p>
      <div class="body">{html.escape(str(entry.get('body') or ''))}</div>
      {f'<div class="links"><p class="links-head">Linked evidence and material ({len(links)})</p><ul>{link_rows}</ul></div>' if links else '<p class="muted">No linked evidence.</p>'}
    </article>
    """


def render_casework_report_html(
    entries_by_section: dict[str, list[dict[str, Any]]],
    *,
    sections: list[str],
    case_name: str,
    generated_by: str,
    privilege_marking: str = "unmarked",
) -> str:
    label = privilege_label(privilege_marking)
    order = normalise_sections(sections)
    body = []
    counts = []
    for section in order:
        entries = _sort(section, [e for e in entries_by_section.get(section, []) if not e.get("deleted_at")])
        counts.append(f"{SECTION_TITLES[section]}: {len(entries)}")
        body.append(
            f'<section class="section"><h2>{SECTION_TITLES[section]} ({len(entries)})</h2>'
            + ("".join(_entry_html(e) for e in entries) or f'<p class="muted">No {SECTION_TITLES[section].lower()} in this case.</p>')
            + "</section>"
        )
    footer = label if privilege_marking in ("confidential", "privileged_confidential") else "Loupe casework report"
    generated_at = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
      @page {{ size: A4 portrait; margin: 1.5cm 1.4cm 1.6cm;
        @bottom-left {{ content: "{html.escape(footer)}"; font-size: 9px; color: #475569; }}
        @bottom-right {{ content: "Page " counter(page) " of " counter(pages); font-size: 9px; color: #475569; }} }}
      body {{ font-family: sans-serif; font-size: 10px; color: #1e293b; }}
      h1 {{ font-size: 22px; margin: 4px 0; }} h2 {{ font-size: 15px; margin-top: 18px; border-bottom: 1px solid #cbd5e1; }}
      h3 {{ font-size: 12px; margin: 10px 0 2px; }} .eyebrow {{ font-size: 9px; letter-spacing: 1px; text-transform: uppercase; color: #64748b; }}
      .marking {{ border: 1.5px solid #0f172a; padding: 6px 10px; margin: 10px 0; font-size: 11px; }}
      .marking span {{ display: block; color: #475569; font-size: 9px; }}
      .facts {{ color: #475569; font-size: 9px; margin: 0 0 4px; }} .body {{ white-space: pre-wrap; }}
      .links {{ margin-top: 4px; }} .links-head {{ font-weight: bold; margin: 2px 0; }} .links ul {{ margin: 0; padding-left: 16px; }}
      .entry {{ break-inside: avoid; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px; }} .muted {{ color: #64748b; }}
    </style></head><body>
      <div class="eyebrow">Casework report</div>
      <h1>{html.escape(case_name or 'Case')}</h1>
      <p>Generated by {html.escape(generated_by)} on {html.escape(generated_at)} · {html.escape(' · '.join(counts))}</p>
      <div class="marking"><strong>{html.escape(label)}</strong><span>{html.escape(PRIVILEGE_BASIS)}</span></div>
      {''.join(body)}
    </body></html>"""


def render_casework_report_pdf(entries_by_section: dict[str, list[dict[str, Any]]], **kwargs: Any) -> bytes:
    from weasyprint import HTML

    def deny_resource(url: str, *args: Any, **kw: Any):
        raise ValueError("Casework reports cannot load external or local resources.")

    return HTML(string=render_casework_report_html(entries_by_section, **kwargs), url_fetcher=deny_resource).write_pdf()
