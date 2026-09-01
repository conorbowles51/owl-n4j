"""Joining a graph transaction back to the rectangle it was read from.

The transaction screen reads from Neo4j, and a transaction node carries four
provenance properties: ``source_document_id``, ``source_filename``,
``source_page`` and ``source_excerpt``.  None of them is a rectangle.  The
rectangles live in ``evidence_table_geometry``, written by the engine one row
per (evidence file, page), each row holding the geometry-bearing ``per_table``
entries whose table landed on that page (see
:mod:`postgres.models.evidence` and the engine's
``app/services/evidence_table_geometry``).  This module is the join: given a
transaction's provenance and the stored geometry for its page, produce one
:class:`~services.financial.locators.Locator` saying where on the page the
transaction's row was read from.

There is no stored key from a transaction to a cell.  The extraction pipeline
built the chunk text a transaction was extracted from by joining a table row's
cells with ``" | "``, and ``source_excerpt`` carries either that declared text
or a grounded quote from it.  So the join is textual and has to be honest
about being textual: a grid row is a *candidate* when at least
:data:`TRANSACTION_MATCH_MINIMUM_CELLS` of its distinct non-empty cell texts
occur inside the whitespace-normalised excerpt, and a candidate wins only by
strictly beating every other candidate on the page.  A tie is two rows the
excerpt describes equally well, and highlighting one of them would be a guess
wearing the interface's authority -- the same refusal
:func:`~services.financial.table_geometry.locate_table` makes when two cells
overlap.  Ties, like everything else that stops short of a rectangle, degrade
to ``page_only``: the reader is taken to the right page and shown no lie
about the row.

The fallback ladder, best to worst: the union rectangle of the winning row's
clickable cells; that table's own rectangle when the row's cells cannot be
unioned (none clickable, or captured against differing page geometry); a
``page_only`` locator when the page is known; ``unlocated`` when it is not.
Every step down is a loss of precision, never a loss of truth.

Malformed stored geometry -- an entry that is not a mapping, a cell whose
locator does not parse -- is skipped rather than raised on.  By the time this
module runs the ingestion is long finished; the only thing failing here could
cost the investigator is the transaction list itself, which is the one thing
this feature must never take down.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Mapping, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from postgres.models.enums import LocatorKind
from postgres.models.evidence import EvidenceTableGeometry
from services.financial.locators import Locator, LocatorError, SourceRectangle
from services.financial.transactions import LOCATOR_PROVENANCE_KEY

logger = logging.getLogger(__name__)

# A single cell text found in the excerpt is one shared word away from being a
# coincidence -- dates repeat down a statement column, amounts recur.  Two
# distinct cell texts from the same grid row is the minimum that reads as the
# excerpt actually describing that row.
TRANSACTION_MATCH_MINIMUM_CELLS = 2


def _normalise(text: Any) -> str:
    """Whitespace-collapsed form used on both sides of the substring test.

    Case is deliberately left alone.  The excerpt was built from these same
    cell texts, so a case difference is a real difference; folding it away
    could only ever convert a safe ``page_only`` fallback into a wrong
    highlight, which is the worse trade in both directions.
    """
    if not isinstance(text, str):
        return ""
    return " ".join(text.split())


def _valid_page(value: Any) -> bool:
    # bool is an int subclass and True would pass ``>= 1``.
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _fallback(source_page: Any) -> Locator:
    if _valid_page(source_page):
        return Locator(kind=LocatorKind.page_only, page_number=source_page)
    return Locator(kind=LocatorKind.unlocated)


def _cell_locator(cell: Any) -> Optional[Locator]:
    """The cell's parsed locator, or ``None`` for anything that will not parse."""
    if not isinstance(cell, Mapping):
        return None
    payload = cell.get("locator")
    if not isinstance(payload, Mapping):
        return None
    try:
        return Locator.from_json(payload)
    except LocatorError:
        return None


def _row_candidates(page_payload: Sequence[Any], excerpt: str) -> list[tuple[int, int, list[Mapping]]]:
    """Grid rows the excerpt could describe: ``(score, order, cells)`` triples.

    ``order`` exists only to keep the result deterministic; scores decide.
    """
    candidates: list[tuple[int, int, list[Mapping]]] = []
    order = 0
    for entry in page_payload:
        if not isinstance(entry, Mapping):
            continue
        located = entry.get("table")
        if not isinstance(located, Mapping):
            continue
        values = located.get("values")
        if not isinstance(values, list):
            continue
        rows: dict[int, list[Mapping]] = {}
        for cell in values:
            if not isinstance(cell, Mapping):
                continue
            row = cell.get("row")
            if not isinstance(row, int) or isinstance(row, bool):
                continue
            rows.setdefault(row, []).append(cell)
        for row in sorted(rows):
            cells = rows[row]
            matched = {
                text
                for text in (_normalise(cell.get("text")) for cell in cells)
                if text and text in excerpt
            }
            if len(matched) >= TRANSACTION_MATCH_MINIMUM_CELLS:
                candidates.append((len(matched), order, cells))
                order += 1
    return candidates


def _union_of_clickable_cells(cells: Sequence[Mapping]) -> Optional[Locator]:
    """One rectangle covering the row's clickable cells, or ``None``.

    Refuses (returns ``None``) when the cells were captured against differing
    page geometry -- a union across two coordinate frames is not a rectangle
    anywhere -- and when no cell carries a rectangle at all.
    """
    rects: list[SourceRectangle] = []
    for cell in cells:
        locator = _cell_locator(cell)
        if locator is None or not locator.is_clickable:
            continue
        assert locator.rectangle is not None  # is_clickable promises it
        rects.append(locator.rectangle)
    if not rects:
        return None
    first = rects[0]
    for rect in rects[1:]:
        if (
            rect.page_number != first.page_number
            or rect.page_width != first.page_width
            or rect.page_height != first.page_height
        ):
            return None
    try:
        union = SourceRectangle(
            page_number=first.page_number,
            x0=min(rect.x0 for rect in rects),
            y0=min(rect.y0 for rect in rects),
            x1=max(rect.x1 for rect in rects),
            y1=max(rect.y1 for rect in rects),
            page_width=first.page_width,
            page_height=first.page_height,
        )
        return Locator(kind=LocatorKind.page_rectangle, rectangle=union)
    except LocatorError:
        return None


def _table_rectangle(cells: Sequence[Mapping], page_payload: Sequence[Any]) -> Optional[Locator]:
    """The own rectangle of the table the winning cells belong to."""
    for entry in page_payload:
        if not isinstance(entry, Mapping):
            continue
        located = entry.get("table")
        if not isinstance(located, Mapping):
            continue
        values = located.get("values")
        if not isinstance(values, list):
            continue
        if not any(cell is candidate for cell in values for candidate in cells):
            continue
        table_payload = located.get("table")
        if not isinstance(table_payload, Mapping):
            return None
        try:
            locator = Locator.from_json(table_payload)
        except LocatorError:
            return None
        return locator if locator.is_clickable else None
    return None


def locate_transaction(
    *,
    source_excerpt: Any,
    source_page: Any,
    page_payload: Optional[Sequence[Any]],
) -> Locator:
    """Where on its source page a transaction's row was read from.

    Pure: takes the transaction's provenance fields and the stored geometry
    payload for that (evidence file, page), returns a locator.  Never raises
    on malformed inputs; every failure mode is a step down the fallback
    ladder described in the module docstring.
    """
    if not page_payload:
        return _fallback(source_page)
    excerpt = _normalise(source_excerpt)
    if not excerpt:
        return _fallback(source_page)

    candidates = _row_candidates(page_payload, excerpt)
    if not candidates:
        return _fallback(source_page)
    best_score = max(score for score, _, _ in candidates)
    winners = [cells for score, _, cells in candidates if score == best_score]
    if len(winners) != 1:
        # Two rows the excerpt describes equally well.  Refuse to pick.
        return _fallback(source_page)
    cells = winners[0]

    union = _union_of_clickable_cells(cells)
    if union is not None:
        return union
    table = _table_rectangle(cells, page_payload)
    if table is not None:
        return table
    return _fallback(source_page)


def attach_transaction_locators(db: Session, transactions: Sequence[Any]) -> None:
    """Attach a locator, under ``LOCATOR_PROVENANCE_KEY``, to every transaction.

    Mutates the dicts in place, which is how the router hands the enriched
    rows straight back to the caller.  A transaction already carrying the key
    is left alone: a locator written at ingestion time knows more than this
    join does.  ``source_document_id`` that is not a UUID (the extraction
    pipeline falls back to the filename when no evidence file id was known)
    means there is nothing to look up, and the transaction gets the honest
    ``page_only``/``unlocated`` fallback rather than nothing.
    """
    wanted: dict[uuid.UUID, set[int]] = {}
    keyed: list[tuple[dict, Optional[uuid.UUID], Any]] = []
    for transaction in transactions:
        if not isinstance(transaction, dict) or LOCATOR_PROVENANCE_KEY in transaction:
            continue
        page = transaction.get("source_page")
        file_id: Optional[uuid.UUID] = None
        raw_id = transaction.get("source_document_id")
        if raw_id is not None:
            try:
                file_id = uuid.UUID(str(raw_id))
            except (ValueError, AttributeError, TypeError):
                file_id = None
        keyed.append((transaction, file_id, page))
        if file_id is not None and _valid_page(page):
            wanted.setdefault(file_id, set()).add(page)

    payloads: dict[tuple[uuid.UUID, int], list] = {}
    for file_id, pages in wanted.items():
        rows = db.execute(
            select(
                EvidenceTableGeometry.page_number,
                EvidenceTableGeometry.payload,
            ).where(
                EvidenceTableGeometry.evidence_file_id == file_id,
                EvidenceTableGeometry.page_number.in_(sorted(pages)),
            )
        ).all()
        for page_number, payload in rows:
            if isinstance(payload, list):
                payloads[(file_id, page_number)] = payload

    for transaction, file_id, page in keyed:
        page_payload = None
        if file_id is not None and _valid_page(page):
            page_payload = payloads.get((file_id, page))
        locator = locate_transaction(
            source_excerpt=transaction.get("source_excerpt"),
            source_page=page,
            page_payload=page_payload,
        )
        transaction[LOCATOR_PROVENANCE_KEY] = locator.to_json()
