"""The answer written when a run reaches its tool limit keeps the sources of what it found (lx-agentfit R3).

Measured 11 Nov 2026 (BNB2 replays, both stopped at the limit): a record lookup's answer fell from 24 cited sources
to 1 and a build request's from 12 to 1, while the results the run had read still held every row's link. Two parts:

- ``found_so_far``: the finalizer's request at the limit lists, per result read, its summary and the records it
  returned with their links (the run record's own per-item citations, ``call_facts``), so each fact can keep its
  source and the answer can say what was not reached.
- ``keep_sources``: after the answer is written, any figure in it (an amount written as the ledger writes it,
  e.g. 1,380,000.00) that a record read in this run carries, while the answer does not link that record, gets the
  record listed under the answer with its link. The list says only that those records carry the figure: it never
  says a record is the source the answer drew on, and it is cut at ``MAX_LISTED`` with the rest counted.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

LINK = re.compile(r"(?:txn|doc|rec)://[^\s\"')\]\\<>]+")
# One result's records in the list the finalizer is given, and the most results listed.
MAX_ITEMS_PER_RESULT = 25
MAX_RESULTS = 60
# The most records listed under an answer; the rest are counted.
MAX_LISTED = 40
# The most records listed for one figure; a figure many records carry says little about any one of them.
MAX_PER_FIGURE = 3
# An amount is a figure only with at least this many digits (2.00 or 15.50 match too much).
MIN_FIGURE_DIGITS = 4


def _links(item: dict) -> list[str]:
    links = [a for a in item.get("alts") or [] if isinstance(a, str) and LINK.fullmatch(a)]
    ref = item.get("ref")
    if isinstance(ref, str) and LINK.fullmatch(ref) and ref not in links:
        links.insert(0, ref)
    return links


def found_so_far(trace: Iterable[dict]) -> str:
    """The block added to the finalizer's request at the limit: per result, its summary and its records' links."""
    lines: list[str] = []
    with_items = []
    for entry in trace:
        record = entry.get("record") or {}
        items = [i for i in record.get("items") or [] if isinstance(i, dict) and _links(i)]
        if items:
            with_items.append((entry, items))
    for entry, items in with_items[:MAX_RESULTS]:
        lines.append("- %s" % (entry.get("summary") or entry.get("name") or "A result").strip()[:300])
        for item in items[:MAX_ITEMS_PER_RESULT]:
            lines.append("  - %s: %s" % ((item.get("label") or item.get("kind") or "record")[:160],
                                         _links(item)[0]))
        if len(items) > MAX_ITEMS_PER_RESULT:
            lines.append("  - and %d more records in this result" % (len(items) - MAX_ITEMS_PER_RESULT))
    if len(with_items) > MAX_RESULTS:
        lines.append("- %d more results with records are not listed here; they are in the conversation above."
                     % (len(with_items) - MAX_RESULTS))
    if not lines:
        return ""
    return ("Records found so far, each with its link. Give every fact in the answer the link of the record it "
            "comes from, copied exactly; a fact with no record here or above is not stated as found.\n"
            + "\n".join(lines))


def _figures(row: dict) -> set[str]:
    """The amounts a ledger-style row carries, written as the ledger writes them (1,380,000.00)."""
    exponent = row.get("currency_exponent")
    exponent = exponent if isinstance(exponent, int) and not isinstance(exponent, bool) and 0 <= exponent <= 4 else 2
    found = set()
    for key, value in row.items():
        if not key.endswith("_minor") and key not in ("amount", "amount_minor"):
            continue
        try:
            number = int(str(value)) if key.endswith("_minor") else None
        except ValueError:
            number = None
        if number is not None:
            text = "{:,.{p}f}".format(abs(number) / (10 ** exponent), p=exponent)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            text = "{:,.2f}".format(abs(value))
        elif isinstance(value, str) and re.fullmatch(r"-?[\d,]+\.\d{2}", value.strip()):
            text = value.strip().lstrip("-")
        else:
            continue
        if sum(c.isdigit() for c in text) >= MIN_FIGURE_DIGITS:
            found.add(text)
    return found


def _rows_with_links(value: Any) -> Iterable[tuple[str, dict]]:
    """Every mapping in a result that carries a record link of its own (cite, txn, ref), with that link."""
    if isinstance(value, list):
        for item in value:
            yield from _rows_with_links(item)
    elif isinstance(value, dict):
        own = next((v for k, v in value.items() if k in ("cite", "txn", "ref", "href")
                    and isinstance(v, str) and LINK.fullmatch(v)), None)
        if own:
            yield own, value
        for item in value.values():
            if isinstance(item, (list, dict)):
                yield from _rows_with_links(item)


def _label(row: dict, figure: str) -> str:
    parts = []
    for key in ("transaction_date", "date", "posted_date"):
        if isinstance(row.get(key), str):
            parts.append(row[key][:10])
            break
    parts.append(" ".join(x for x in (figure, row.get("currency") if isinstance(row.get("currency"), str) else "")
                          if x))
    for key in ("counterparty", "counterparty_name", "description", "label"):
        if isinstance(row.get(key), str) and row[key].strip():
            parts.append(row[key].strip()[:80])
            break
    return ", ".join(p for p in parts if p)


def keep_sources(answer: str, views: dict[str, Any], *, heading: str) -> tuple[str, dict]:
    """``answer`` with the records listed under it that carry a figure it states and that it does not link, and
    the counts (figures matched, records listed, records not listed)."""
    text = answer or ""
    linked = set(LINK.findall(text))
    stated = {f for f in re.findall(r"(?<![\d.,])\d{1,3}(?:,\d{3})+\.\d{2,4}(?!\d)|(?<![\d.,])\d{4,}\.\d{2,4}(?!\d)", text)}
    stated |= {"{:,.2f}".format(float(f.replace(",", ""))) for f in stated if f.count(".") == 1}
    by_figure: dict[str, dict[str, str]] = {}
    seen: set[str] = set()
    for view in (views or {}).values():
        for link, row in _rows_with_links(view):
            if link in linked or link in seen:
                continue
            for figure in sorted(_figures(row)):
                if figure in stated:
                    seen.add(link)
                    by_figure.setdefault(figure, {})[link] = _label(row, figure)
                    break
    lines: list[str] = []
    unlisted = 0
    for figure, rows in by_figure.items():
        for link, label in list(rows.items())[:MAX_PER_FIGURE]:
            if len(lines) < MAX_LISTED:
                lines.append("- [%s](%s)" % (label.replace("[", "(").replace("]", ")"), link))
            else:
                unlisted += 1
        unlisted += max(0, len(rows) - MAX_PER_FIGURE)
    counts = {"figures": len(by_figure), "listed": len(lines), "not_listed": unlisted}
    if not lines:
        return text, counts
    if unlisted:
        lines.append("- %d more records carry these figures and are not listed." % unlisted)
    return text.rstrip() + "\n\n" + heading + "\n" + "\n".join(lines), counts


# An answer that writes a source as a bare target ([txn://<id>, doc://<id>/3]) gives the reader nothing to open and
# the citation check nothing to count (BNB2 replay bf147c8a, 11 Nov 2026: 22 sources written so, 1 counted).
_TARGET = r"(?:txn|doc|rec)://[0-9A-Za-z][0-9A-Za-z_-]*(?:/\d+)?"
_BARE_GROUP = re.compile(r"\[\s*(%s(?:\s*[,;]\s*%s)*)\s*\](?!\()" % (_TARGET, _TARGET))
_BARE = re.compile(r"(?<!\]\()(?<![\w/])(%s)(?![\w/])" % _TARGET)


def _link(target: str) -> str:
    if target.startswith("txn://"):
        label = "payment"
    elif target.startswith("rec://"):
        label = "phone record"
    else:
        page = re.search(r"/(\d+)$", target)
        label = "document, p.%s" % page.group(1) if page else "document"
    return "[%s](%s)" % (label, target)


def link_bare_targets(text: str) -> str:
    """Each source written as a bare target becomes a Markdown link to it; links already written are untouched."""
    if not text or "://" not in text:
        return text
    text = _BARE_GROUP.sub(lambda m: "(" + ", ".join(
        _link(t) for t in re.findall(_TARGET, m.group(1))) + ")", text)
    out, last = [], 0
    for m in _BARE.finditer(text):
        out.append(text[last:m.start()])
        out.append(_link(m.group(1)))
        last = m.end()
    out.append(text[last:])
    return "".join(out)
