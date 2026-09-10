"""Investigator-reviewed statement controls bound to original stored PDF cells.

Controls provide context for selected rows. They never assert complete extraction
or change the selected-document proof class.
"""
from datetime import date
from typing import Annotated, Literal
from uuid import UUID
from pydantic import Field, model_validator, model_serializer
from services.financial.pdf_candidates import _Contract, _Digest, PdfMappingError
from services.financial.candidate_store import CandidateStoreError
from services.financial.candidate_sources import read_candidate_source
from services.financial.money import get_currency, Money, MoneyError
from services.financial.periods import BalanceObservation, PeriodBounds, StatementPeriodDraft, record_statement_period


class ControlCell(_Contract):
    page_number: Annotated[int, Field(strict=True, ge=1)]
    table_index: Annotated[int, Field(strict=True, ge=0)]
    row_index: Annotated[int, Field(strict=True, ge=0)]
    column_index: Annotated[int, Field(strict=True, ge=0)]
    source_revision: _Digest
    expected_text: Annotated[str, Field(strict=True, min_length=1, max_length=4096)]


class ReviewedDateControl(_Contract):
    value: Annotated[str, Field(strict=True, pattern=r'^\d{4}-\d{2}-\d{2}$')]
    source: ControlCell

    @model_validator(mode='after')
    def valid_date(self):
        date.fromisoformat(self.value)
        return self


class ReviewedBalanceControl(_Contract):
    amount_minor: Annotated[str, Field(strict=True, pattern=r'^-?(0|[1-9][0-9]{0,18})$')]
    source: ControlCell

    @model_validator(mode='after')
    def within_ledger(self):
        if not -9223372036854775808 <= int(self.amount_minor) <= 9223372036854775807:
            raise ValueError('Balance is outside the ledger range.')
        return self


class ReviewedTotalControl(ReviewedBalanceControl):
    @model_validator(mode='after')
    def nonnegative(self):
        if int(self.amount_minor) < 0:
            raise ValueError('A direction total must be a nonnegative magnitude.')
        return self


class ReviewedStatementScope(_Contract):
    account_id: UUID
    currency: Annotated[str, Field(strict=True, min_length=3, max_length=3)]
    candidate_ids: Annotated[list[UUID], Field(min_length=1, max_length=1000)]
    start: ReviewedDateControl
    end: ReviewedDateControl
    opening: ReviewedBalanceControl | None = None
    closing: ReviewedBalanceControl | None = None
    credits_total: ReviewedTotalControl | None = None
    debits_total: ReviewedTotalControl | None = None
    balance_convention: Literal['asset_balance', 'liability_owed']
    reason: Annotated[str, Field(strict=True, min_length=1, max_length=4096)]

    @model_serializer(mode='wrap')
    def preserve_existing_receipts(self, handler):
        value = handler(self)
        for role in ('credits_total', 'debits_total'):
            if value.get(role) is None:
                value.pop(role, None)
        return value

    @model_validator(mode='after')
    def coherent(self):
        if self.start.value > self.end.value:
            raise ValueError('Statement end must not precede its start.')
        if len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ValueError('A statement cannot repeat a candidate reading.')
        if not self.reason.strip():
            raise ValueError('A statement review reason is required.')
        try:
            if get_currency(self.currency).code != self.currency:
                raise ValueError('Use the recorded uppercase currency code.')
            for control in (self.opening, self.closing):
                if control is not None:
                    ledger_balance = int(control.amount_minor) * (-1 if self.balance_convention == 'liability_owed' else 1)
                    if not -9223372036854775808 <= ledger_balance <= 9223372036854775807:
                        raise ValueError('Converted balance is outside the ledger range.')
        except MoneyError as exc:
            raise ValueError(str(exc)) from exc
        return self


class StatementScopesRequest(_Contract):
    statement_scopes: Annotated[list[ReviewedStatementScope], Field(max_length=100)] = Field(default_factory=list)


def attach_statement_scopes(session, manifest, prepared, scopes, *, case_id, evidence_file_id, require_statement_dates=False):
    """Rebind every control and row assignment before hashing the preview or writing."""
    dated_by_statement = {UUID(item["row"]["id"]) for item in prepared if item["reading"].statement_end_date}
    assigned_scope_ids = {cid for scope in scopes for cid in scope.candidate_ids}
    if require_statement_dates and not dated_by_statement <= assigned_scope_ids:
        raise CandidateStoreError("Assign every statement-dated reading to its printed statement end control before finalizing.", 422)
    if not scopes:
        return manifest
    by_id = {UUID(item['row']['id']): item['reading'] for item in prepared}
    assigned = set()
    periods = set()
    tables = {}
    bound_scopes = []
    for scope in scopes:
        key = (scope.account_id, scope.currency, scope.start.value, scope.end.value)
        if key in periods:
            raise CandidateStoreError('Statement account and date bounds are repeated.', 422)
        periods.add(key)
        for candidate_id in scope.candidate_ids:
            reading = by_id.get(candidate_id)
            if reading is None or candidate_id in assigned:
                raise CandidateStoreError('Statement rows must be distinct resolved readings from this PDF.', 422)
            if reading.account_id != scope.account_id or reading.currency != scope.currency:
                raise CandidateStoreError('Statement account or currency differs from its reviewed rows.', 422)
            # A booking date is preferred; transaction/value dates can lie outside
            # printed bounds on real statements and are not silently substituted.
            if reading.booking_date and not scope.start.value <= reading.booking_date <= scope.end.value:
                raise CandidateStoreError('A reviewed booking date lies outside its assigned statement.', 422)
            if reading.statement_end_date and reading.statement_end_date != scope.end.value:
                raise CandidateStoreError("Statement-end ordering date differs from the assigned printed end date.", 422)
            assigned.add(candidate_id)
        controls = {}
        for role in ('start', 'end', 'opening', 'closing', 'credits_total', 'debits_total'):
            control = getattr(scope, role)
            if control is None:
                if role in ('credits_total', 'debits_total'):
                    continue
                controls[role] = None
                continue
            cell = control.source
            table_key = (cell.page_number, cell.table_index)
            if table_key not in tables:
                try:
                    tables[table_key] = read_candidate_source(session, case_id=case_id, evidence_file_id=evidence_file_id,
                        page_number=cell.page_number, table_index=cell.table_index)
                except PdfMappingError as exc:
                    raise CandidateStoreError(str(exc), exc.status_code) from exc
            table = tables[table_key]
            stored = [value for row in table['rows'] if row['row_index'] == cell.row_index
                      for value in row['cells'] if value['column_index'] == cell.column_index]
            if table['source_revision'] != cell.source_revision or len(stored) != 1 or stored[0]['expected_text'] != cell.expected_text:
                raise CandidateStoreError('A statement control source changed or does not match. Reload its source cell.')
            controls[role] = dict(**control.model_dump(mode='json'), locator=stored[0]['locator'])
        bound_scopes.append(dict(**scope.model_dump(mode='json'), bound_controls=controls))
    return {**manifest, 'statement_scopes': bound_scopes}


def record_reviewed_statement_scopes(session, run, document, scopes):
    """Store printed observations and return explicit candidate-to-period links."""
    links, records = {}, []
    for scope in scopes:
        def observation(control):
            if control is None:
                return BalanceObservation.absent()
            value = int(control.amount_minor) * (-1 if scope.balance_convention == 'liability_owed' else 1)
            return BalanceObservation.printed(Money(value, scope.currency))
        period = record_statement_period(session, run, StatementPeriodDraft(
            account_id=scope.account_id, source_document_id=document.id, currency=scope.currency,
            bounds=PeriodBounds.printed(date.fromisoformat(scope.start.value), date.fromisoformat(scope.end.value)),
            opening=observation(scope.opening), closing=observation(scope.closing)))
        for candidate_id in scope.candidate_ids:
            links[str(candidate_id)] = period.id
        records.append(dict(period_id=str(period.id), account_id=str(scope.account_id), currency=scope.currency,
            candidate_ids=[str(value) for value in scope.candidate_ids]))
    return links, records
