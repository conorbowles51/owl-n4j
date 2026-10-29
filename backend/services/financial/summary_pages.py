"""The summary page of a statement period, before its payment pages (coordinator, 2026-10-28).

A card statement prints its account summary (previous and new balance, holder and address) on "Page 1 of N" and its
payments from "Page 2 of N". When page 1 has no table the period is read from (fdaf956c's 52 Capital One periods: page
1 carries only the payment box as a table), the period's pages started at page 2 and its printed balances were never
read with it. The pages before the period's first page are its summary pages when the text of the file shows it: the
first page prints "Page k of N" (k > 1, the only numbering it prints) and, walking back, each page is a page of the
file on no other statement, prints no numbering or one "Page j of N" (j falling), until one prints "Page 1 of N"; at
most two file pages per printed page (a reverse side or a notice beside each). Any layout whose summary comes first.

They are not the period's table pages: no payment is read from them by the text reading, and nothing about its rows
changes. They are pages the period's printed balances may be cited from, and pages read with the period from its page
images (vision_reader). Off: no summary pages, as before.
"""
import os
import re

ENABLED = os.environ.get('LOUPE_FINANCIAL_SUMMARY_PAGES', '1').strip().lower() not in ('0', 'false', 'off', 'no', '')
_PAGE_OF = re.compile(r'\bpage\s+(\d{1,3})\s+of\s+(\d{1,3})\b', re.I)


def page_labels(content, source_locations):
    """{file page: set of (k, N)} for each "Page k of N" the stored text of the file prints on that page."""
    labels = {}
    for location in source_locations or ():
        if not isinstance(location, dict) or location.get('kind') != 'page':
            continue
        page, start, end = location.get('page_number'), location.get('start_char'), location.get('end_char')
        if not (type(page) is int and type(start) is int and type(end) is int):
            continue
        found = {(int(m[1]), int(m[2])) for m in _PAGE_OF.finditer(' '.join((content or '')[start:end].split()))}
        if found:
            labels.setdefault(page, set()).update(found)
    return labels


def summary_pages(pages, file_pages, taken, labels):
    """The file pages before ``pages`` (the period's own) that are its summary pages; [] when the text does not show
    them. ``taken``: pages of the file's other statements; ``labels``: page_labels."""
    if not ENABLED or not pages:
        return []
    first = min(pages)
    own = labels.get(first) or set()
    if len(own) != 1:
        return []
    number, total = next(iter(own))
    if not 1 < number <= total:
        return []
    file_pages, taken = set(file_pages or ()), set(taken or ())
    added, last = [], number
    for page in range(first - 1, first - 2 * (number - 1) - 1, -1):
        if page not in file_pages or page in taken:
            return []
        printed = labels.get(page) or set()
        if len(printed) > 1:
            return []
        added.append(page)
        if printed:
            j, n = next(iter(printed))
            if n != total or not 1 <= j < last:
                return []
            last = j
            if j == 1:
                return sorted(added)
    return []


def statement_summary_pages(proposal):
    """The summary pages the text reading found for this period (statement_import: ``summary_page_numbers``)."""
    return list(proposal.get('summary_page_numbers') or []) if ENABLED else []


def balance_pages(proposal):
    """Pages a printed balance of this period may be cited from: its pages and its summary pages."""
    pages = proposal.get('statement_page_numbers') or sorted({source['page_number'] for source in proposal.get('sources', [])}) \
        or proposal.get('page_numbers', [])
    return sorted(set(pages) | set(statement_summary_pages(proposal)))
