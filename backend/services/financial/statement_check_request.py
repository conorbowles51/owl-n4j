"""A read-only check accepts incomplete edits and reports unavailable arithmetic."""
from typing import Annotated, Literal
from pydantic import Field
from services.financial.pdf_candidates import _Contract, _Digest, PdfMappingError
from services.financial.review_arithmetic import check_proposed_rows


class CheckRow(_Contract):
    id: Annotated[str, Field(min_length=1, max_length=80)]
    excluded: bool
    manual_page: Annotated[int | None, Field(ge=1, le=500)] = None
    date: Annotated[str, Field(max_length=32)] = ''
    description: Annotated[str, Field(max_length=4096)] = ''
    amount_minor: Annotated[str, Field(max_length=32)] = ''
    direction: Literal['credit', 'debit'] | None = None
    balance_minor: Annotated[str | None, Field(max_length=32)] = None
    reason: Annotated[str, Field(max_length=4096)] = ''


class StatementCheckRequest(_Contract):
    expected_revision: _Digest
    statement_id: _Digest | None = None
    currency: Annotated[str, Field(pattern=r'^[A-Z]{3}$')]
    rows: Annotated[list[CheckRow], Field(max_length=100000)]


def check_statement_request(proposal, request):
    if request.expected_revision != proposal['revision'] or request.statement_id != proposal.get('statement_id'):
        raise PdfMappingError('The saved statement reading changed. Reopen it before checking your edits.', 409)
    if request.currency != proposal['currency'] or proposal.get('reading_failure') or proposal.get('document_review'):
        raise PdfMappingError('Open a recognised statement and choose its printed currency first.', 422)
    return dict(revision=proposal['revision'], applied=False,
                **check_proposed_rows(proposal, [r.model_dump() for r in request.rows]))
