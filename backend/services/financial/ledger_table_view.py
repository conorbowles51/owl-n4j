"""Reproducible display filters and row order inside a full ledger capture."""
from typing import Annotated, Literal
from datetime import date
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from services.financial.ledger_summary import LedgerSummaryError

class LedgerTableView(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    search: Annotated[str, Field(max_length=256)] = ''
    category: Annotated[str, Field(max_length=120)] = ''
    account_id: Annotated[str, Field(pattern=r'^$|^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')] = ''
    account_holder: Annotated[str, Field(max_length=512)] = ''
    source_document_id: Annotated[str, Field(pattern=r'^$|^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')] = ''
    import_batch_id: Annotated[str, Field(pattern=r'^$|^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')] = ''
    import_batch_revision: Annotated[str, Field(pattern=r'^$|^[a-f0-9]{64}$')] = ''
    currency: Annotated[str, Field(pattern=r'^$|^[A-Z]{3}$')] = ''
    direction: Literal['', 'credit', 'debit'] = ''
    proof: Literal['', 'p0', 'p1', 'p2', 'p3'] = ''
    minimum_minor: Annotated[str, Field(pattern=r'^$|^(0|[1-9][0-9]{0,18})$')] = ''
    maximum_minor: Annotated[str, Field(pattern=r'^$|^(0|[1-9][0-9]{0,18})$')] = ''
    from_names: list[Annotated[str, Field(max_length=1024)]] = Field(default_factory=list, max_length=5000)
    to_names: list[Annotated[str, Field(max_length=1024)]] = Field(default_factory=list, max_length=5000)
    perspective_names: list[Annotated[str, Field(max_length=1024)]] = Field(default_factory=list, max_length=5000)
    analysis_group: Annotated[str, Field(pattern=r'^$|^[A-Z]{3}:(card|bank)$')] = ''
    analysis_period: Annotated[str, Field(pattern=r'^$|^undated$|^\d{4}-(0[1-9]|1[0-2])$')] = ''
    analysis_categories: list[Annotated[str, Field(max_length=120)]] = Field(default_factory=list, max_length=1000)
    flow_party: Annotated[str, Field(max_length=1024)] = ''
    flow_kind: Literal['', 'incoming', 'outgoing', 'internal'] = ''
    sort: Literal['ledger', 'oldest', 'newest', 'amount-asc', 'amount-desc',
                  'description-asc', 'description-desc', 'from-asc', 'from-desc',
                  'to-asc', 'to-desc', 'category-asc', 'category-desc'] = 'ledger'


    @model_validator(mode='after')
    def amount_range(self):
        if (self.flow_party or self.flow_kind) and not self.perspective_names:
            raise ValueError('Choose a perspective for money flow filters.')
        if bool(self.import_batch_id) != bool(self.import_batch_revision):
            raise ValueError('A batch filter requires the exact imported statement list.')
        if self.minimum_minor or self.maximum_minor:
            if not self.currency:
                raise ValueError('Select a currency for an amount range.')
            if any(int(v)>9223372036854775807 for v in (self.minimum_minor,self.maximum_minor) if v):
                raise ValueError('Amount range exceeds the ledger range.')
            if self.minimum_minor and self.maximum_minor and int(self.minimum_minor)>int(self.maximum_minor):
                raise ValueError('Minimum amount exceeds maximum amount.')
        return self


def _party(row, side):
    own = row['direction'] == ('debit' if side == 'from' else 'credit')
    value = row.get(f'{side}_name')
    if value is None:
        value = (row.get('account_holder') or row.get('account_label') or row.get('account_id')) if own else row.get('counterparty_raw')
    name = ' '.join((value or '').split())
    return f'name:{name}' if name else f'unknown:{side}'


def _period(row):
    if row.get('ordering_date_context') == 'statement_end_ordering_only':
        return 'undated'
    value = (row.get('ordering_date') or '')[:10]
    try:
        parsed = date.fromisoformat(value)
        return parsed.isoformat()[:7] if parsed.isoformat() == value else 'undated'
    except ValueError:
        return 'undated'


def _analysis_match(row, view, selections):
    group = f"{row['currency']}:{'card' if row.get('account_type') == 'credit_card' else 'bank'}"
    if view.analysis_group and group != view.analysis_group:
        return False
    if view.analysis_period and _period(row) != view.analysis_period:
        return False
    if view.analysis_categories and (row.get('category') or 'Uncategorized') not in selections['analysis_categories']:
        return False
    sender, recipient = _party(row, 'from'), _party(row, 'to')
    if view.from_names and sender not in selections['from_names'] or view.to_names and recipient not in selections['to_names']:
        return False
    inside_from, inside_to = sender in selections['perspective_names'], recipient in selections['perspective_names']
    kind = 'internal' if inside_from and inside_to else 'outgoing' if inside_from else 'incoming' if inside_to else ''
    if view.perspective_names and not kind or view.flow_kind and kind != view.flow_kind:
        return False
    if view.flow_party and (kind not in ('incoming', 'outgoing') or (sender if kind == 'incoming' else recipient) != view.flow_party):
        return False
    return True


def capture_table_view(ledger, request, *, batch_scope=None):
    try:
        view = LedgerTableView.model_validate(request)
    except ValidationError as exc:
        raise LedgerSummaryError('Invalid table-view filters.') from exc
    query = view.search.strip().lower()
    selections = {key: set(getattr(view, key)) for key in ('from_names', 'to_names', 'perspective_names', 'analysis_categories')}
    if view.import_batch_id and (not batch_scope or batch_scope['batch_id'] != view.import_batch_id or batch_scope['revision'] != view.import_batch_revision):
        raise LedgerSummaryError('The imported batch changed. Reopen its transactions before downloading.')
    batch_sources = set(batch_scope['source_document_ids']) if view.import_batch_id else None
    rows = []
    for captured in ledger['readings']:
        row = captured['row']
        # Mirrors the ledger table's admitted-row API, including its explicit
        # distinction from eligibility of the parent source for totals.
        if row['ledger_status'] != 'admitted':
            continue
        if view.account_id and row.get('account_id') != view.account_id:
            continue
        if view.account_holder and ' '.join((row.get('account_holder') or '').split()).lower() != ' '.join(view.account_holder.split()).lower():
            continue
        if view.source_document_id and row.get('source_document_id') != view.source_document_id:
            continue
        if batch_sources is not None and row.get('source_document_id') not in batch_sources:
            continue
        if view.category and (row.get('category') or 'Uncategorized') != view.category:
            continue
        if view.currency and row['currency'] != view.currency or view.direction and row['direction'] != view.direction or view.proof and row['proof_class'] != view.proof:
            continue
        if view.minimum_minor and int(row['amount_minor']) < int(view.minimum_minor) or view.maximum_minor and int(row['amount_minor']) > int(view.maximum_minor):
            continue
        if not _analysis_match(row, view, selections):
            continue
        if query and not any(isinstance(row.get(k), str) and query in row[k].lower() for k in (
                'ordering_date','description','from_name','to_name','category','counterparty_raw','bank_reference','ref_id','key','account_id','source_document_id')):
            continue
        rows.append(row)
    rows.sort(key=lambda r: (r['ordering_date'], r['row_index'], r['key']))
    if view.sort == 'newest':
        rows.sort(key=lambda r: r['ordering_date'], reverse=True)
    if view.sort.startswith('amount'):
        if len({r['currency'] for r in rows}) > 1:
            raise LedgerSummaryError('Choose one currency before exporting an amount-sorted table.')
        rows.sort(key=lambda r: int(r['amount_minor']), reverse=view.sort == 'amount-desc')
    if view.sort.split('-')[0] in ('description', 'from', 'to', 'category'):
        field, direction = view.sort.split('-')
        def label(row):
            if field in ('from', 'to'):
                key = _party(row, field)
                return (key[5:] if key.startswith('name:') else 'Not identified').lower()
            return (row.get(field) or ('Uncategorized' if field == 'category' else '')).lower()
        rows.sort(key=lambda row: label(row).encode('utf-16-be', errors='surrogatepass'), reverse=direction == 'desc')
    result = dict(schema='loupe.financial.ledger_table_view/1',filters=view.model_dump(exclude={key for key in ('category', 'account_id', 'account_holder', 'source_document_id', 'import_batch_id', 'import_batch_revision', 'from_names', 'to_names', 'perspective_names', 'analysis_group', 'analysis_period', 'analysis_categories', 'flow_party', 'flow_kind') if not getattr(view, key)}),
        row_ids=[r['key'] for r in rows],matching_rows=len(rows),
        limitation='Admitted ledger rows matching the recorded table filters, in display order, captured at export time. Display order does not establish bank sequence. The enclosing snapshot retains the full applied account/date scope and its history; its totals apply to that full scope. Source eligibility and proof classes are unchanged. All matching rows are included, not just the visible page.')
    if batch_sources is not None:
        result['imported_source_document_ids'] = sorted(batch_sources)
    return result
