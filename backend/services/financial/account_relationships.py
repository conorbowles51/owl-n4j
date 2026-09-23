"""Reviewed account relationships, distinct from printed names and grouping."""
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from postgres.models.financial import FinancialSourceDocument


class RelationshipSource(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_document_id: UUID
    page_number: int = Field(ge=1, strict=True)


class AccountRelationshipInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID | None = None
    role: Literal['holder', 'controller', 'signatory', 'analysis_group'] = 'holder'
    basis: Literal['source', 'investigator_knowledge'] = 'investigator_knowledge'
    sources: list[RelationshipSource] = Field(default_factory=list, max_length=100)
    effective_from: date | None = None
    effective_to: date | None = None

    @model_validator(mode='after')
    def valid_basis(self):
        if self.effective_from and self.effective_to and self.effective_from > self.effective_to:
            raise ValueError('The relationship end date must follow its start date.')
        if self.basis == 'source' and not self.sources:
            raise ValueError('Choose a supporting statement page or investigator knowledge.')
        if self.basis == 'investigator_knowledge' and self.sources:
            raise ValueError('Choose source evidence when citing statement pages.')
        if len({(s.source_document_id, s.page_number) for s in self.sources}) != len(self.sources):
            raise ValueError('Choose each supporting page once.')
        return self


def validate_relationship_sources(session, case_id, relationship):
    """A user may only cite documents in the authorised case."""
    from services.financial.account_parties import AccountPartyError
    for citation in relationship.sources:
        document = session.scalar(select(FinancialSourceDocument).where(
            FinancialSourceDocument.case_id == case_id,
            FinancialSourceDocument.id == citation.source_document_id))
        if document is None:
            raise AccountPartyError('Supporting statement not found in this case.', 404)
        original = (document.metadata_ or {}).get('statement_import_original') or {}
        pages = {s.get('page_number') for s in original.get('sources', [])}
        if pages and citation.page_number not in pages:
            raise AccountPartyError('The selected page is not part of that saved statement.')


def owners_on(account, on_date=None):
    """Unknown dates do not establish a dated ownership assertion."""
    result = {}
    for link in account.get('relationships', []):
        if link['role'] != 'holder':
            continue
        start, end = link.get('effective_from'), link.get('effective_to')
        if on_date is None and (start or end):
            continue
        if on_date is not None and ((start and on_date < start) or (end and on_date > end)):
            continue
        result[link['party']['id']] = link['party']
    return list(result.values())
