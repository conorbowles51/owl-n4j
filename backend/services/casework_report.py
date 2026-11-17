"""Casework report: the case's Findings first, with the evidence linked to each, then the other sections in the order
the investigator chose.

Sections are Findings, Theories and Notes; the order and which are included are the exporter's choice, Findings
first by default. A financial finding saved from the ledger (a note tagged ``financial-entry-finding``) prints under
Findings, so it is in the report by default. Each entry prints its title, state, significance, author (or the model
that drafted it and who accepted it), text and every item linked to it: the link's relationship (supports,
contradicts, context), the person's reason, who added it and when, whether the model chose it, its narrative (a model
reading is marked as one, with the model's name) and the production numbers of a cited page. A theory adds how it
fits together, its accepted counter-arguments (the model's text marked as a model reading) and its timeline: the
dated items it holds, in date order. Every link type prints its plain name (``postgres.link_types.TYPE_WORDS``).
Deleted entries never print. The audit log is not part of this report. The privilege marking is the same three values as the ledger
export, chosen by the exporter, printed on the cover and every page footer, and is not a legal determination.
"""
from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Any, Callable

from postgres.link_types import type_words
from services.snapshot_report import PRIVILEGE_BASIS, privilege_label

SECTIONS = {"findings": "finding", "theories": "theory", "notes": "note"}
SECTION_TITLES = {"findings": "Findings", "theories": "Theories", "notes": "Notes"}
DEFAULT_ORDER = ["findings", "theories", "notes"]
MAX_REPORT_ENTRIES = 2000
_SIGNIFICANCE_RANK = {"high": 0, "medium": 1, "low": 2, None: 3}
_RELATIONSHIP_WORDS = {"supports": "Supports", "contradicts": "Contradicts", "context": "Context",
                       "unclassified": "Not yet classified"}
FINANCIAL_FINDING_TAG = "financial-entry-finding"


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


UNRESOLVED_LABEL = "no name on record"


def fold_financial_findings(entries_by_section: dict[str, list[dict[str, Any]]], notes: list[dict[str, Any]]) -> None:
    """Financial findings saved from the ledger are notes; they print under Findings and not again under Notes."""
    if "findings" not in entries_by_section:
        return
    moved = [n for n in notes if FINANCIAL_FINDING_TAG in (n.get("tags") or [])]
    ids = {id(n) for n in moved}
    for note in moved:
        note["_financial_finding"] = True
    entries_by_section["findings"] = list(entries_by_section["findings"]) + moved
    if "notes" in entries_by_section:
        entries_by_section["notes"] = [n for n in entries_by_section["notes"] if id(n) not in ids]


def fill_missing_link_labels(
    entries_by_section: dict[str, list[dict[str, Any]]],
    lookup: Callable[[str, set[str]], dict[str, str]],
) -> None:
    """Links saved without a label (most graph-entity links, some evidence links) get the current name of what they
    point to: one lookup per target type, scoped to the case by the caller. A target that cannot be named keeps its
    id, marked as unnamed, so a link is never dropped from the report. A label saved on the link is never replaced."""
    wanted: dict[str, set[str]] = {}
    for entries in entries_by_section.values():
        for entry in entries:
            for link in entry.get("links") or []:
                if not link.get("target_label") and link.get("target_id"):
                    wanted.setdefault(str(link.get("target_type") or ""), set()).add(str(link["target_id"]))
    names: dict[str, dict[str, str]] = {}
    for target_type, ids in wanted.items():
        try:
            names[target_type] = lookup(target_type, ids) or {}
        except Exception:  # a store being unreachable must not lose the report; the ids still print
            names[target_type] = {}
    for entries in entries_by_section.values():
        for entry in entries:
            for link in entry.get("links") or []:
                if not link.get("target_label") and link.get("target_id"):
                    target_id = str(link["target_id"])
                    name = names.get(str(link.get("target_type") or ""), {}).get(target_id)
                    link["target_label"] = name or UNRESOLVED_LABEL


def _sort(section: str, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if section == "findings":
        return sorted(entries, key=lambda e: (_SIGNIFICANCE_RANK.get(e.get("significance"), 3), str(e.get("title") or "")))
    return sorted(entries, key=lambda e: str(e.get("updated_at") or ""), reverse=True)


def _link_words(link: dict[str, Any]) -> str:
    """A quote prints whole, with its page and what read it; other links print their label."""
    anchor = link.get("source_anchor") or {}
    if link.get("target_type") == "evidence_passage" and anchor.get("quote"):
        reader = (anchor.get("reader") or {}).get("words")
        place = ", ".join(str(value) for value in (anchor.get("document_name"), anchor.get("page_label")) if value)
        return "“%s”, %s%s" % (anchor["quote"], place, " · %s" % reader if reader else "")
    if link.get("target_type") == "agent_answer" and anchor.get("thread_title"):
        # Named by the question it answers, never by its first lines of markdown.
        words = "Answer in “%s”" % anchor["thread_title"]
        facts = [_day(anchor.get("answered_at")), anchor.get("model")]
        return words + "".join(f", {fact}" for fact in facts if fact)
    words = str(link.get("target_label") or UNRESOLVED_LABEL)
    if link.get("target_type") == "evidence" and anchor.get("page"):
        words += f", page {anchor['page']}"
    return words


# A citation link in an entry's body: [words](doc://...), [words](txn://...), [words](rec://...).
# An older payment link names the Financial page row (``/cases/<case>/financial?...&payment=<id>``): read as txn://.
_BODY_LINK = re.compile(r"\[([^\]]*)\]\(\s*<?((?:doc|txn|rec)://[^)>\s]*|(?:https?://[^)\s>]*?)?/?cases/[^)\s>]*)>?"
                        r"(?:\s+\"[^\"]*\")?\s*\)")
_SCHEME_WORDS = {"doc": "document", "txn": "payment", "rec": "phone record", "entity": "graph entity"}


def _body_html(body: Any, cited: dict[str, str]) -> str:
    """An entry's body verbatim, except that each citation link prints as its words and the place it cites
    (``cited``, read from the case), never as its raw id. Everything else is escaped as written."""
    from services.case_citations import link_bare_citations, parse_citation
    text = link_bare_citations(str(body or ""))
    out, at = [], 0
    for match in _BODY_LINK.finditer(text):
        words, href = match.group(1).strip(), match.group(2)
        citation = parse_citation(href)
        if citation is None:  # a link to another Loupe page, not a citation: left as written
            continue
        out.append(_e(text[at:match.start()]))
        scheme = citation.scheme
        place = cited.get(href)
        if not place and scheme == "doc":
            page = href.rstrip("/").rsplit("/", 1)[-1] if href.count("/") > 2 else ""
            place = f"page {page}" if page.isdigit() else "page not given"
        out.append(_e(words or _SCHEME_WORDS[scheme]) + (f' <span class="cite">({_e(place)})</span>' if place else ""))
        at = match.end()
    out.append(_e(text[at:]))
    return "".join(out)


def _e(value: Any) -> str:
    return html.escape(str(value or ""))


def _day(value: Any) -> str:
    return str(value or "")[:10]


def _narrative_html(narrative: dict[str, Any] | None, lead: str) -> str:
    if not narrative or not narrative.get("text"):
        return ""
    model = narrative.get("origin") == "agent"
    cls = "narrative model" if model else "narrative"
    return (f'<p class="{cls}"><span class="who">{_e(lead)} ({_e(narrative.get("words"))}):</span> '
            f'{_e(narrative["text"])}</p>')


def _link_html(link: dict[str, Any], report: dict[str, Any]) -> str:
    addition = (report.get("additions") or {}).get(str(link.get("id"))) or {}
    head = "<strong>{}</strong> · {}: {}".format(
        _e(_RELATIONSHIP_WORDS.get(link.get("relationship"), "Not yet classified")),
        _e(type_words(link.get("target_type"))),
        _e(_link_words(link)),
    )
    production = (report.get("production") or {}).get(str(link.get("id")))
    if production:
        head += f' · <span class="bates">Production numbers: {_e(production)}</span>'
    lines = []
    meta = link.get("metadata") or {}
    if meta.get("counter_argument"):
        model = ((meta.get("actor_origin") or {}).get("origin") or {}).get("model") or "the case agent"
        lines.append(f"From the counter-argument “{_e(meta.get('title'))}”, proposed by {_e(model)} (the model's choice)")
    elif addition.get("origin") == "agent":
        chosen = f"Chosen by the model ({addition.get('model') or 'the case agent'})"
        if addition.get("accepted_by"):
            chosen += f", accepted by {addition['accepted_by']}"
        lines.append(_e(chosen))
    if link.get("target_type") == "agent_answer":
        lines.append("An agent answer: a model reading, not a person's finding")
    if addition.get("why"):
        lines.append(f"Why: {_e(addition['why'])}")
    who = addition.get("added_by")
    when = _day(addition.get("added_at") or link.get("created_at"))
    if who or when:
        lines.append("Added" + (f" by {_e(who)}" if who else "") + (f" on {_e(when)}" if when else ""))
    sub = "".join(f'<span class="sub">{line}</span>' for line in lines)
    return f"<li>{head}{sub}{_narrative_html(addition.get('narrative'), 'What it shows')}</li>"


def _counter_html(items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    rows = []
    for item in items:
        head = f"<strong>{_e(item.get('title') or 'Counter-argument')}</strong>"
        if item.get("strength"):
            head += f" · Strength: {_e(str(item['strength']).capitalize())}"
        accepted = f"Accepted by {_e(item.get('accepted_by') or 'a person')}" + (
            f" on {_e(_day(item.get('accepted_at')))}" if item.get("accepted_at") else "")
        body = (f'<p class="narrative model"><span class="who">Model reading ({_e(item.get("model"))}):</span> '
                f'{_e(item.get("model_text"))}</p>') if item.get("model_text") else ""
        if item.get("person_text"):
            body += (f'<p class="narrative"><span class="who">Edited by {_e(item.get("accepted_by") or "a person")}:</span> '
                     f'{_e(item["person_text"])}</p>')
        rows.append(f'<li>{head}<span class="sub">{accepted}</span>{body}</li>')
    return f'<div class="links"><p class="links-head">Counter-arguments accepted ({len(items)})</p><ul>{"".join(rows)}</ul></div>'


def _member_label(member: dict[str, Any]) -> str:
    """A member's name; one with no name of its own (its label is only its id) prints as having none."""
    label = str(member.get("label") or "").strip()
    return UNRESOLVED_LABEL if not label or label == str(member.get("id") or "") else label


def _timeline_html(report: dict[str, Any]) -> str:
    if report.get("timeline_missing"):
        return f'<p class="muted">{_e(report["timeline_missing"])}</p>'
    dated = report.get("timeline")
    if not dated:
        return ""
    total = int(report.get("timeline_total") or len(dated))
    rows = "".join(
        f"<li>{_e(m.get('date'))} · {_e(type_words(m.get('type')))}: {_e(_member_label(m))}"
        + (f" ({_e(m['state'])})" if m.get("state") not in (None, "present") else "") + "</li>"
        for m in dated)
    note = ""
    if total > len(dated):
        note = f'<p class="muted">The first {len(dated):,} of {total:,} dated items are printed; Loupe shows all of them on the theory.</p>'
    if report.get("timeline_cut"):
        note += '<p class="muted">The theory holds more items than its timeline reads at once; Loupe shows the count.</p>'
    return f'<div class="links"><p class="links-head">Timeline ({total:,} dated items)</p><ul>{rows}</ul>{note}</div>'


def _entry_html(entry: dict[str, Any]) -> str:
    report = entry.get("_report") or {}
    facts = []
    if entry.get("_financial_finding"):
        facts.append("Financial finding, saved from the ledger")
    if entry.get("lifecycle_state"):
        facts.append(f"State: {_e(str(entry['lifecycle_state']).capitalize())}")
    if entry.get("significance"):
        facts.append(f"Significance: {_e(str(entry['significance']).capitalize())}")
    if entry.get("confidence") is not None:
        facts.append(f"Confidence: {int(entry['confidence'])}%")
    if entry.get("review_state") and entry.get("review_state") != "accepted":
        facts.append(f"Review: {_e(entry['review_state'])}")
    if entry.get("origin_label"):
        facts.append(_e(entry["origin_label"]))
    else:
        author = entry.get("author_name") or entry.get("author_email")
        if author:
            facts.append(f"Author: {_e(author)}")
    if entry.get("updated_at"):
        facts.append(f"Updated: {_e(_day(entry['updated_at']))}")
    links = entry.get("links") or []
    link_rows = "".join(_link_html(link, report) for link in links)
    missing = "".join(f'<p class="muted">{_e(report[key])}</p>'
                      for key in ("missing", "counter_missing", "production_missing") if report.get(key))
    title = entry.get("title") or "Untitled note"
    return f"""
    <article class="entry">
      <h3>{_e(title)}</h3>
      <p class="facts">{' · '.join(facts)}</p>
      <div class="body">{_body_html(entry.get('body'), report.get('body_citations') or {})}</div>
      {_narrative_html(report.get('fit'), 'How it fits together')}
      {f'<div class="links"><p class="links-head">Linked evidence and material ({len(links)})</p><ul>{link_rows}</ul></div>' if links else '<p class="muted">No linked evidence.</p>'}
      {_counter_html(report.get('counter_arguments') or [])}
      {_timeline_html(report)}
      {missing}
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
      .entry {{ border-bottom: 1px solid #e2e8f0; padding-bottom: 6px; }} .muted {{ color: #64748b; }}
      .links li {{ margin-bottom: 3px; break-inside: avoid; }} .sub {{ display: block; color: #475569; font-size: 9px; }}
      .narrative {{ margin: 2px 0 2px 0; }} .narrative.model {{ border-left: 2px solid #a78bfa; padding-left: 5px; }}
      .who {{ font-weight: bold; }} .bates {{ color: #334155; }}
    </style></head><body>
      <div class="eyebrow">Casework report</div>
      <h1>{html.escape(case_name or 'Case')}</h1>
      <p>Generated by {html.escape(generated_by)} on {html.escape(generated_at)} · {html.escape(' · '.join(counts))}</p>
      <div class="marking"><strong>{html.escape(label)}</strong><span>{html.escape(PRIVILEGE_BASIS)}</span></div>
      {''.join(body)}
    </body></html>"""


def render_casework_report_pdf(entries_by_section: dict[str, list[dict[str, Any]]], **kwargs: Any) -> bytes:
    from weasyprint import HTML

    from services.pdf_fetch import deny_all
    deny_resource = deny_all("Casework reports cannot load external or local resources.")

    return HTML(string=render_casework_report_html(entries_by_section, **kwargs), url_fetcher=deny_resource).write_pdf()
