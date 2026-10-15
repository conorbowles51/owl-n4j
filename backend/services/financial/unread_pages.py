"""Pages the evidence engine kept unread (OCR ran out of time) and the statements they hold.

The engine no longer fails a whole file when one page's OCR times out: the
page is stored without text and marked ``ocr_status='timeout'``. A statement
whose pages could include such a page might be missing payments or a
balance, so it is held with a plain reason until the file is read again.
Fail closed: when it is not clear which statement a page belongs to, every
statement it could belong to is held.
"""

TIMEOUT_STATUS = 'timeout'


def unread_pages(source_locations):
    """Page numbers stored without text because their OCR timed out."""
    return sorted({loc['page_number'] for loc in source_locations or []
                   if loc.get('kind') == 'page' and loc.get('ocr_status') == TIMEOUT_STATUS
                   and type(loc.get('page_number')) is int})


def _span(choice):
    pages = [p for p in (choice or {}).get('page_numbers') or [] if type(p) is int]
    return (min(pages), max(pages)) if pages else None


def unread_pages_of_statement(source_locations, selected, choices):
    """Unread pages that could belong to the selected statement (all of them without a known layout)."""
    pages = unread_pages(source_locations)
    if not pages:
        return []
    own = _span(selected)
    spans = sorted(span for span in (_span(choice) for choice in choices or []) if span)
    if own is None or not spans:
        return pages
    result = []
    for page in pages:
        if own[0] <= page <= own[1]:
            result.append(page)
            continue
        if any(start <= page <= end for start, end in spans):
            continue  # inside another statement's pages
        # A page between statements (or before the first / after the last)
        # may continue the one before it or open the one after it.
        before = max((end for start, end in spans if end < page), default=None)
        after = min((start for start, end in spans if start > page), default=None)
        if own[1] == before or own[0] == after:
            result.append(page)
    return result


def unread_pages_message(pages):
    if len(pages) == 1:
        where = f'Page {pages[0]} of this PDF'
    else:
        where = 'Pages ' + ', '.join(map(str, pages[:-1])) + f' and {pages[-1]} of this PDF'
    return (f'{where} could not be read in time, so this statement may be missing payments or a balance. '
            'The other pages were kept. Read the file again to read the missing page.')
