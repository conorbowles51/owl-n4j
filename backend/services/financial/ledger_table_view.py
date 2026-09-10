"""Reproducible display filters and row order inside a full ledger capture."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from services.financial.ledger_summary import LedgerSummaryError

class LedgerTableView(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    search: Annotated[str, Field(max_length=256)] = ''
    currency: Annotated[str, Field(pattern=r'^$|^[A-Z]{3}$')] = ''
    direction: Literal['', 'credit', 'debit'] = ''
    proof: Literal['', 'p0', 'p1', 'p2', 'p3'] = ''
    minimum_minor: Annotated[str, Field(pattern=r'^$|^(0|[1-9][0-9]{0,18})$')] = ''
    maximum_minor: Annotated[str, Field(pattern=r'^$|^(0|[1-9][0-9]{0,18})$')] = ''
    sort: Literal['ledger', 'oldest', 'newest', 'amount-asc', 'amount-desc'] = 'ledger'

    @model_validator(mode='after')
    def amount_range(self):
        if self.minimum_minor or self.maximum_minor:
            if not self.currency:
                raise ValueError('Select a currency for an amount range.')
            if any(int(v)>9223372036854775807 for v in (self.minimum_minor,self.maximum_minor) if v):
                raise ValueError('Amount range exceeds the ledger range.')
            if self.minimum_minor and self.maximum_minor and int(self.minimum_minor)>int(self.maximum_minor):
                raise ValueError('Minimum amount exceeds maximum amount.')
        return self


def capture_table_view(ledger, request):
    try:
        view = LedgerTableView.model_validate(request)
    except ValidationError as exc:
        raise LedgerSummaryError('Invalid table-view filters.') from exc
    query = view.search.strip().lower()
    rows = []
    for captured in ledger['readings']:
        row = captured['row']
        # Mirrors the ledger table's admitted-row API, including its explicit
        # distinction from eligibility of the parent source for totals.
        if row['ledger_status'] != 'admitted':
            continue
        if view.currency and row['currency'] != view.currency or view.direction and row['direction'] != view.direction or view.proof and row['proof_class'] != view.proof:
            continue
        if view.minimum_minor and int(row['amount_minor']) < int(view.minimum_minor) or view.maximum_minor and int(row['amount_minor']) > int(view.maximum_minor):
            continue
        if query and not any(isinstance(row.get(k), str) and query in row[k].lower() for k in (
                'description','counterparty_raw','bank_reference','ref_id','key','account_id','source_document_id')):
            continue
        rows.append(row)
    rows.sort(key=lambda r: (r['ordering_date'], r['row_index'], r['key']))
    if view.sort == 'newest':
        rows.sort(key=lambda r: r['ordering_date'], reverse=True)
    if view.sort.startswith('amount'):
        if len({r['currency'] for r in rows}) > 1:
            raise LedgerSummaryError('Choose one currency before exporting an amount-sorted table.')
        rows.sort(key=lambda r: int(r['amount_minor']), reverse=view.sort == 'amount-desc')
    return dict(schema='loupe.financial.ledger_table_view/1',filters=view.model_dump(),
        row_ids=[r['key'] for r in rows],matching_rows=len(rows),
        limitation='Admitted ledger rows matching the recorded table filters, in display order, captured at export time. Display order does not establish bank sequence. The enclosing snapshot retains the full applied account/date scope and its history; its totals apply to that full scope. Source eligibility and proof classes are unchanged. All matching rows are included, not just the visible page.')
