"""Printed page numbering that shows pages absent from the file (any bank).

A statement that prints its own page numbering ("PAGINA 2 / 7", "Página 2 de 7", "Page 2 of 7", "HOJA 2 DE 7")
and whose file does not hold every printed page cannot be proved complete: the absent page may carry the opening
balance, the summary or movements. Its reading may still add up (a balance chain that starts on the first page the
file holds), so arithmetic alone never clears it.

Read only and outside the revision: derived from the file's saved page text. The proposal records the gap
(``printed_pages_missing``); ``import_issues.retained_issues`` turns it into a blocker for preparation and
admission alike, so nothing is saved automatically. A person who has checked the original and accepts the gap
saves a coverage note (``coverage_review_reason``), as for other coverage questions.

The gap is proved, never guessed:
- only numbering printed on the statement's own pages, and on the pages next to them that continue the same
  printed sequence (same page total), is used;
- a statement page whose numbering could not be read may be any one missing number, so it is counted against
  the gap (OCR losing a page number never holds a complete file);
- a number above its page total, or several page totals on one page, is not numbering.

Off (LOUPE_FINANCIAL_PRINTED_PAGE_COUNT_GATE=0): no gap is recorded, as before.
"""
import os
import re
import unicodedata

ENABLED = os.environ.get('LOUPE_FINANCIAL_PRINTED_PAGE_COUNT_GATE', '1').strip().lower() not in ('0', 'false', 'no', 'off')

NUMBERING = re.compile(r'\b(?:PAGINA|PAGE|HOJA|PAG\.?)\s*(\d{1,3})\s*(?:/|DE|OF)\s*(\d{1,3})\b')


def _fold(text):
    text = unicodedata.normalize('NFKD', text or '')
    return ''.join(c for c in text if not unicodedata.combining(c)).upper()


def page_numbering(text):
    """(printed number, printed total) of one page, or None when absent or ambiguous."""
    found = {(int(a), int(b)) for a, b in NUMBERING.findall(_fold(text))}
    found = {(n, total) for n, total in found if 1 <= n <= total <= 500}
    return next(iter(found)) if len(found) == 1 else None


def missing_pages(pages, statement_pages):
    """dict(printed_total, missing, held) when the printed numbering proves pages absent, else None.

    ``pages``: {file page number: page text} for the whole file. ``statement_pages``: the statement's file pages.
    """
    if not ENABLED or not pages or not statement_pages:
        return None
    numbering = {page: page_numbering(text) for page, text in pages.items()}
    own = sorted(set(statement_pages) & set(pages))
    totals = {numbering[page][1] for page in own if numbering.get(page)}
    if len(totals) != 1:
        return None  # unnumbered, or several printed sequences on the statement's own pages
    total = next(iter(totals))
    run = set(own)
    for step in (-1, 1):
        page = (min(own) if step < 0 else max(own)) + step
        while page in pages and numbering.get(page) and numbering[page][1] == total:
            run.add(page)
            page += step
    seen = {numbering[page][0] for page in run if numbering.get(page) and numbering[page][1] == total}
    unread = sum(1 for page in own if not numbering.get(page))
    missing = sorted(set(range(1, total + 1)) - seen)
    if len(missing) <= unread:
        return None
    return dict(printed_total=total, missing=missing, held=len(run))


def message(gap):
    numbers = ', '.join(str(n) for n in gap['missing'])
    word = 'Page' if len(gap['missing']) == 1 else 'Pages'
    return (f'{word} {numbers} of {gap["printed_total"]} printed pages are not in this PDF. Find the complete statement '
            f'and add it to the case. If you have checked the original and the missing pages hold nothing for this '
            f'period, save a note saying so.')
