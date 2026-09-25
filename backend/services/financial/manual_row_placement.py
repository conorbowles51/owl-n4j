"""Investigator-declared placement of missed payments in their source period."""
from typing import Annotated, Literal
from pydantic import Field
from services.financial.pdf_candidates import _Contract, PdfMappingError


class SourceOrderAnchor(_Contract):
    relation: Literal['before', 'after']
    row_id: Annotated[str, Field(min_length=1, max_length=80)]


def allowed_source_positions(originals, page, statement_pages):
    """Original neighbours, or explicit page boundaries for an unread page.

    Page order comes from this period's retained source scope, not transaction
    dates. An empty page cannot use an arbitrary row elsewhere in the PDF.
    """
    payments = [row for row in originals.values()
                if row.get('kind') in ('transaction', 'unresolved')]
    on_page = [row for row in payments if row.get('page_number') == page]
    if on_page:
        return {(relation, row['id']) for row in on_page for relation in ('before', 'after')}
    pages = list(dict.fromkeys(statement_pages))
    if page not in pages:
        return set()
    position = pages.index(page)
    preceding = [number for number in pages[:position]
                 if any(row.get('page_number') == number for row in payments)]
    following = [number for number in pages[position + 1:]
                 if any(row.get('page_number') == number for row in payments)]
    candidates = set()
    if preceding:
        prior = [row for row in payments if row.get('page_number') == preceding[-1]][-1]
        candidates.add(('after', prior['id']))
    if following:
        next_row = next(row for row in payments if row.get('page_number') == following[0])
        candidates.add(('before', next_row['id']))
    return candidates


def place_manual_rows(rows, originals, *, statement_pages=None):
    """Return source order without deriving positions from transaction dates.

    Only original payment rows can anchor additions. An otherwise unread page
    can explicitly cite the nearest source-page boundary in its own period.
    Multiple additions on one page at the same anchor keep submitted order;
    additions across empty pages retain the declared source-page order.
    """
    before, after, unplaced = {}, {}, []
    pages = list(dict.fromkeys(statement_pages if statement_pages is not None else
        [row.get('page_number') for row in originals.values()]))
    page_positions = {page: index for index, page in enumerate(pages)}
    allowed_by_page = {}
    source = []
    for row in rows:
        anchor = row.get('fields', {}).get('source_order_anchor')
        if row.get('kind') != 'manual_entry':
            source.append(row)
            continue
        if not anchor:
            unplaced.append(row)
            continue
        target = originals.get(anchor.get('row_id'))
        page = row.get('page_number')
        if page not in allowed_by_page:
            allowed_by_page[page] = allowed_source_positions(originals, page, pages)
        allowed = allowed_by_page[page]
        if (anchor.get('relation'), anchor.get('row_id')) not in allowed:
            raise PdfMappingError('Choose a printed payment on this page, or the nearest page boundary offered for an unread page in this statement. The previous position is no longer available.', 409)
        placement = before if anchor['relation'] == 'before' else after
        placement.setdefault(target['id'], []).append(row)
    for placement in (before, after):
        for entries in placement.values():
            entries.sort(key=lambda row: page_positions.get(row.get('page_number'), len(pages)))
    ordered = []
    for row in source:
        ordered.extend(before.get(row['id'], []))
        ordered.append(row)
        ordered.extend(after.get(row['id'], []))
    ordered.extend(unplaced)
    return ordered
