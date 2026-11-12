"""Inspect actual in-memory export bytes, tied to the exact saved revision."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from html.parser import HTMLParser
from types import SimpleNamespace

from services.agent.claim_validation import fingerprint

CHECK_VERSION = 3


def _normalized(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value)).replace("\u00ad", ""))


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


class _ContentBlocks(_Text):
    """Keep authored paragraphs and table rows intact, allowing page furniture between them."""
    boundaries = {'p', 'li', 'tr', 'pre', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}

    def __init__(self):
        super().__init__()
        self.blocks = []

    def flush(self):
        value = _normalized(' '.join(self.parts))
        if value:
            self.blocks.append(value)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self.boundaries:
            self.flush()

    def handle_endtag(self, tag):
        if tag in self.boundaries:
            self.flush()


def inspect_export(artifact, *, export_format="pdf", min_pages=None, max_pages=None):
    """Presence checks identify omissions, but never certify layout or source truth."""
    import pymupdf
    from services.agent.exports import render_artifact_export, as_document, _rows_for_artifact, _columns_for_artifact, _flatten_dict, _cell_value
    from services.agent.export_documents import sections, markdown_html

    if export_format != "pdf":
        raise ValueError("Rendered page inspection currently supports PDF. Request a PDF companion to inspect a document.")
    if min_pages is not None and max_pages is not None and min_pages > max_pages:
        raise ValueError("min_pages cannot exceed max_pages.")
    record = SimpleNamespace(type=artifact["type"], title=artifact["title"], payload=artifact["data"], extra_metadata=artifact.get("metadata", {}))
    output = render_artifact_export(record, "pdf")
    with pymupdf.open(stream=output.content, filetype="pdf") as document:
        text = "\n".join(page.get_text() for page in document)
        # The renderer reserves 18/19 mm for page furniture. Excluding it lets a
        # paragraph split over pages match without page numbers interrupting it.
        body_text = "\n".join(page.get_text(clip=pymupdf.Rect(0, 42, page.rect.width, page.rect.height - 45)) for page in document)
        page_count = len(document)
        out_of_bounds = [{"page": index + 1, "text": block[4][:100]} for index, page in enumerate(document)
                         for block in page.get_text("blocks") if block[4].strip() and not page.rect.contains(block[:4])]
    normalized = _normalized(body_text)
    source_rows = source_cells = missing_cells = content_checks = 0
    missing_examples, missing_content, missing_content_examples = [], [], []

    def table(kind, payload, location):
        nonlocal source_rows, source_cells, missing_cells
        rows = _rows_for_artifact(kind, payload)
        columns = _columns_for_artifact(kind, payload, rows)
        source_rows += len(rows)
        for index, row in enumerate(rows):
            flat = _flatten_dict(row)
            for key in columns:
                value = _cell_value(flat.get(key))
                token = _normalized(value)
                if not token:
                    continue
                source_cells += 1
                if token not in normalized:
                    missing_cells += 1
                    if len(missing_examples) < 25:
                        missing_examples.append({"location": location, "row": index, "column": key, "value": value[:160]})

    def embed(item, location):
        kind, payload = item.get("type", "table"), item.get("data", {})
        if kind == 'interactive':
            from services.agent.deliverables import static_content_text
            from services.agent.export_office import scenario_values
            content(static_content_text(payload.get('static_content')), location + '.static_content', markdown=True)
            inputs = (payload.get('interactions') or {}).get('inputs', [])
            if inputs:
                table('table', {'rows': [{'label': row.get('label') or row.get('key'), 'value': row.get('value', 0)} for row in inputs]}, location + '.inputs')
            results = scenario_values(payload)
            if results:
                table('table', {'rows': results}, location + '.calculations')
        if kind == "workbook":
            for i, sheet in enumerate(payload.get("sheets", [])):
                table("table", sheet, f"{location}.sheets.{i}")
                if sheet.get("formulas"):
                    table("table", {"rows": sheet["formulas"]}, f"{location}.sheets.{i}.formulas")
        else:
            table(kind, payload, location)

    def content(value, location, markdown=False):
        nonlocal content_checks
        if not value:
            return
        if markdown:
            parser = _ContentBlocks()
            parser.feed(markdown_html(value))
            parser.flush()
            tokens = parser.blocks
        else:
            tokens = [_normalized(value)]
        if any(tokens):
            content_checks += 1
            cursor = 0
            for token in tokens:
                if not token:
                    continue
                position = normalized.find(token, cursor)
                if position < 0:
                    missing_content.append(location)
                    if len(missing_content_examples) < 25:
                        missing_content_examples.append({'location': location, 'text': token[:160]})
                    break
                cursor = position + len(token)

    payload = as_document(record.type, record.title, record.payload)
    content(payload.get("purpose"), "purpose", markdown=True)
    content(payload.get("scope"), "scope", markdown=True)
    for index, section in enumerate(sections(payload)):
        location = f"sections.{index}"
        content(section.get("heading"), location + ".heading")
        content(section.get("content"), location + ".content", markdown=True)
        for i, item in enumerate(section.get("embeds", [])):
            embed(item, f"{location}.embeds.{i}")
    issues = []
    if min_pages is not None and page_count < min_pages:
        issues.append(f"The rendered PDF has {page_count} pages; the requested minimum is {min_pages}.")
    if max_pages is not None and page_count > max_pages:
        issues.append(f"The rendered PDF has {page_count} pages; the requested maximum is {max_pages}.")
    if out_of_bounds:
        issues.append(f"{len(out_of_bounds)} text blocks extend beyond a page boundary.")
    if missing_cells:
        issues.append(f"{missing_cells} source-cell values were not located in the rendered PDF text.")
    if missing_content:
        issues.append(f"{len(missing_content)} authored content blocks were not located intact in the rendered PDF text.")
    return {"artifact_id": artifact["id"], "revision": artifact.get("metadata", {}).get("revision", 1),
            "check_version": CHECK_VERSION,
            "payload_sha256": fingerprint(artifact["data"]), "format": "pdf", "export_sha256": hashlib.sha256(output.content).hexdigest(),
            "byte_count": len(output.content), "page_count": page_count, "text_character_count": len(text),
            "requested_min_pages": min_pages, "requested_max_pages": max_pages,
            "status": "needs_revision" if issues else "render_checks_passed", "issues": issues,
            "data_coverage": {"source_rows": source_rows, "source_cells": source_cells, "missing_cells": missing_cells,
                              "missing_examples": missing_examples, "status": "missing_values" if missing_cells else "all_source_cell_values_located",
                              "scope": "Every source cell is checked for text presence; repeated identical values do not establish distinct row identity."},
            "content_checks": content_checks, "missing_content_locations": missing_content,
            "missing_content_examples": missing_content_examples,
            "out_of_bounds_count": len(out_of_bounds), "out_of_bounds_examples": out_of_bounds[:25],
            "visual_review": "not_established", "source_truth": "not_established"}
