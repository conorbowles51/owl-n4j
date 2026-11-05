"""Saving what a person found on an original PDF page (register E27).

A page the reader did not place in a statement is listed as needing a coverage check. A person who has looked at it
saves what it is, with a reason tied to that page of those exact bytes. The review is shown beside the page, in the
statement's coverage note and in exports. It answers "has someone looked at this page", nothing more: it clears no
check, adds no row, and says nothing about periods or missed payments. ``continuation`` records that the page carries
statement content; a payment on it still has to be added as one.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from postgres.models.evidence import EvidenceFile
from postgres.models.financial_page_review import PAGE_DISPOSITIONS, FinancialPageReview as Review
from services.financial.model_work import origin_field
from services.financial.pdf_candidates import PdfMappingError

MAX_REASON = 2000
LABELS = dict(supporting_correspondence='Supporting correspondence', continuation='Continuation of a statement',
              blank='Blank page', other='Other')


def table_ready(session) -> bool:
    """False on a database without this table (tests that build only some tables); checked once per engine."""
    from services.financial.payment_categories import _table_ready
    return _table_ready(session.connection(), 'financial_page_reviews')


def _view(row: Review, sha256) -> dict:
    return dict(id=str(row.id), evidence_file_id=str(row.evidence_file_id), page_number=row.page_number,
                disposition=row.disposition, label=LABELS[row.disposition], reason=row.reason,
                saved_by=row.saved_by_name or row.saved_by_email, saved_at=row.saved_at.isoformat(),
                file_sha256=row.file_sha256, same_file_bytes=bool(row.file_sha256) and row.file_sha256 == sha256,
                origin=row.origin, undone_at=row.undone_at.isoformat() if row.undone_at else None,
                undone_by=row.undone_by_name)


def _file(session, case_id, evidence_file_id, *, lock=False) -> EvidenceFile:
    query = select(EvidenceFile).where(EvidenceFile.id == evidence_file_id, EvidenceFile.case_id == case_id)
    file = session.scalar(query.with_for_update() if lock else query)
    if file is None:
        raise PdfMappingError('Statement not found in this case.', 404)
    return file


def _rows(session, case_id, evidence_file_id, page=None) -> list[Review]:
    query = select(Review).where(Review.case_id == case_id, Review.evidence_file_id == evidence_file_id)
    if page is not None:
        query = query.where(Review.page_number == page)
    return list(session.scalars(query.order_by(Review.page_number, Review.saved_at, Review.id)))


def _current(rows: list[Review]) -> Review | None:
    return next((row for row in reversed(rows) if row.undone_at is None), None)


def _check_expected(rows, expected_id) -> Review | None:
    current = _current(rows)
    if (str(current.id) if current else None) != expected_id:
        who = (f' {current.saved_by_name or current.saved_by_email} saved "{LABELS[current.disposition]}".'
               if current else '')
        raise PdfMappingError(f'This page\'s review changed while you had it open.{who} Nothing was overwritten. '
                              'Reload the page review before saving.', 409)
    return current


def read_page_reviews(session, *, case_id, evidence_file_id) -> dict:
    file = _file(session, case_id, evidence_file_id)
    if not table_ready(session):
        return dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id), reviews=[], history=[])
    rows = _rows(session, case_id, evidence_file_id)
    pages: dict[int, list[Review]] = {}
    for row in rows:
        pages.setdefault(row.page_number, []).append(row)
    current = [_view(c, file.sha256) for c in (_current(items) for items in pages.values()) if c is not None]
    return dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id), reviews=current,
                history=[_view(row, file.sha256) for row in rows])


def save_page_review(session, *, case_id, evidence_file_id, page_number, disposition, reason, expected_review_id, actor):
    if disposition not in PAGE_DISPOSITIONS:
        raise PdfMappingError('Choose what this page is.', 422)
    reason = ' '.join(str(reason or '').split())
    if not reason:
        raise PdfMappingError('Say why, from what the page shows.', 422)
    if len(reason) > MAX_REASON:
        raise PdfMappingError(f'Keep the reason to {MAX_REASON} characters.', 422)
    # The file row lock serialises two people saving the same page, so neither replaces the other unseen.
    file = _file(session, case_id, evidence_file_id, lock=True)
    _check_expected(_rows(session, case_id, evidence_file_id, page_number), expected_review_id)
    row = Review(case_id=case_id, evidence_file_id=evidence_file_id, page_number=page_number, file_sha256=file.sha256,
                 disposition=disposition, reason=reason, saved_by_user_id=actor.user_id, saved_by_name=actor.name,
                 saved_by_email=getattr(actor, 'email', None), origin=origin_field(actor).get('origin'),
                 saved_at=datetime.now(timezone.utc))
    session.add(row)
    session.commit()
    return read_page_reviews(session, case_id=case_id, evidence_file_id=evidence_file_id)


def undo_page_review(session, *, case_id, evidence_file_id, page_number, expected_review_id, actor):
    _file(session, case_id, evidence_file_id, lock=True)
    current = _check_expected(_rows(session, case_id, evidence_file_id, page_number), expected_review_id)
    if current is None:
        raise PdfMappingError('This page has no saved review to undo.', 409)
    current.undone_at, current.undone_by_user_id = datetime.now(timezone.utc), actor.user_id
    current.undone_by_name = actor.name or getattr(actor, 'email', None)
    session.commit()
    return read_page_reviews(session, case_id=case_id, evidence_file_id=evidence_file_id)


def capture_page_reviews(session, *, case_id, evidence_file_ids) -> list[dict]:
    """Every review of these files for an export, undone ones included and marked, in file and page order."""
    ids = [value if isinstance(value, UUID) else UUID(str(value)) for value in evidence_file_ids]
    if not ids or not table_ready(session):
        return []
    rows = session.execute(select(Review, EvidenceFile.original_filename, EvidenceFile.sha256)
                           .join(EvidenceFile, EvidenceFile.id == Review.evidence_file_id)
                           .where(Review.case_id == case_id, Review.evidence_file_id.in_(ids))
                           .order_by(EvidenceFile.original_filename, Review.page_number, Review.saved_at, Review.id)).all()
    return [dict(_view(row, sha256), filename=name) for row, name, sha256 in rows]
