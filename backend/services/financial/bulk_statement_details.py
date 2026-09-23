"""Review and atomically correct selected saved or unimported statement details."""
from copy import deepcopy
from datetime import date, datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialSourceDocument as Source
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from services.financial.pdf_candidates import PdfMappingError, _digest
from services.financial import import_batches
from services.financial.currency_correction import CurrencyCode
from services.financial.statement_details import StatementDetailsRequest, read_statement_details, update_statement_details
from services.financial.statement_import import read_statement_import

FIELDS = ('holder', 'account_number', 'institution', 'currency', 'period_start', 'period_end')


class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    file_ids: list[UUID] = Field(default_factory=list, max_length=1000)
    batch_id: UUID | None = None

    @model_validator(mode='after')
    def one_scope(self):
        if bool(self.file_ids) == bool(self.batch_id):
            raise ValueError('Choose files or one processing batch.')
        return self


class Target(BaseModel):
    model_config = ConfigDict(extra='forbid')
    file_id: UUID
    source_id: UUID | None = None
    statement_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    revision: str = Field(pattern=r'^[a-f0-9]{64}$')


class Changes(BaseModel):
    model_config = ConfigDict(extra='forbid')
    holder: str | None = Field(default=None, max_length=128)
    account_number: str | None = Field(default=None, max_length=128)
    institution: str | None = Field(default=None, max_length=128)
    currency: CurrencyCode | None = None
    period_start: str | None = None
    period_end: str | None = None

    @model_validator(mode='after')
    def valid_fields(self):
        if not any(getattr(self, key) is not None for key in FIELDS):
            raise ValueError('Choose at least one field to change.')
        for key in FIELDS:
            value = getattr(self, key)
            if value is not None:
                value = value.strip()
                if any(ord(c) < 32 for c in value):
                    raise ValueError('Account details must be on a single line.')
                if key.startswith('period_') and value:
                    if date.fromisoformat(value).isoformat() != value:
                        raise ValueError('Enter complete statement dates.')
                setattr(self, key, value)
        return self


class BulkEdit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    targets: list[Target] = Field(min_length=1, max_length=1000)
    changes: Changes
    mode: Literal['fill_missing', 'replace'] = 'fill_missing'
    request_id: UUID
    preview_revision: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')


def _key(target):
    return f'saved:{target.source_id}' if target.source_id else f'draft:{target.file_id}:{target.statement_id or ""}'


def _file(session, case_id, file_id):
    file = session.scalar(select(EvidenceFile).where(EvidenceFile.case_id == case_id, EvidenceFile.id == file_id))
    if file is None:
        raise PdfMappingError('A selected file is not in this case.', 404)
    from services.financial.file_visibility import require_financial_file
    require_financial_file(file)
    return file


def _items(session, case_id, file_id, statement_id):
    return list(session.scalars(select(Item).join(Batch, Batch.id == Item.batch_id).where(
        Batch.case_id == case_id, Batch.status != 'removed', Item.file_id == file_id,
        Item.statement_key == (statement_id or ''), Item.status != 'removed').order_by(Item.id)))


def _load(session, case_id, target, cache):
    file = _file(session, case_id, target.file_id)
    if target.source_id:
        view = read_statement_details(session, case_id=case_id, source_id=target.source_id)
        if view['evidence_file_id'] != str(file.id):
            raise PdfMappingError('The selected statement does not belong to this PDF.', 409)
        values = {**view['details'], 'currency': view['currency'] or ''}
        revision = view['revision']
        state = dict(view=view)
    else:
        items = _items(session, case_id, file.id, target.statement_id)
        if any(item.status in ('pending_import', 'imported', 'skipped', 'assigned') for item in items):
            raise PdfMappingError('This statement is importing, imported or left unimported. Refresh the list or restore it to review first.', 409)
        drafts = [item.review_request for item in items if item.review_request]
        currencies = {raw.get('currency') for raw in drafts}
        if len(currencies) > 1:
            raise PdfMappingError('This statement has conflicting saved reviews. Open it to compare them first.', 409)
        proposal = read_statement_import(session, case_id=case_id, evidence_file_id=file.id,
            statement_id=target.statement_id, currency=next(iter(currencies), None), _cache=cache, _include_period_checks=False)
        if proposal.get('current_import') or proposal.get('document_review') or proposal.get('assignment_only') or proposal.get('reading_failure'):
            raise PdfMappingError('Open this statement individually to review its import or account assignment.', 409)
        saved = proposal.get('saved_review')
        if saved:
            drafts.append(saved['request'])
        from services.financial.review_upgrade import upgrade_request
        drafts = [upgrade_request(raw, proposal) or raw for raw in drafts]
        if len({_digest(raw) for raw in drafts}) > 1:
            raise PdfMappingError('This statement has different corrections saved in its batch and PDF review. Compare them individually first.', 409)
        raw = deepcopy(drafts[0] if drafts else import_batches.initial_request(proposal))
        if raw['expected_revision'] != proposal['revision']:
            raise PdfMappingError('The reading changed since its corrections were saved. Review this statement individually first.', 409)
        values = {key: raw.get(key, '') for key in FIELDS}
        revision = _digest(dict(proposal=proposal['revision'], raw=raw, saved=saved,
            items=[(str(item.id), item.status, item.review_request) for item in items]))
        state = dict(proposal=proposal, raw=raw, items=items)
    row = dict(key=_key(target), file_id=str(file.id), source_id=str(target.source_id) if target.source_id else None,
        statement_id=target.statement_id, revision=revision, filename=file.original_filename,
        status='Imported' if target.source_id else 'Not imported', values=values)
    return row, state


def list_statements(session, *, case_id, selection):
    """Files show each printed period, including imported and saved draft scopes."""
    if selection.batch_id:
        import_batches.batch_for(session, case_id, selection.batch_id)
        batch_items = list(session.scalars(select(Item).where(Item.batch_id == selection.batch_id, Item.status != 'removed')))
        file_ids = {item.file_id for item in batch_items}
        scopes = {(item.file_id, item.statement_key or None) for item in batch_items}
    else:
        file_ids = set(selection.file_ids)
        scopes = None
    files = [_file(session, case_id, fid) for fid in sorted(file_ids, key=str)]
    if scopes is None:
        from services.financial.source_lineage import case_lineage, current_version
        groups = [versions for versions in case_lineage(session, case_id).values() if any(f.id in file_ids for f in versions)]
        files = [current_version(versions) for versions in groups]
        file_ids = {f.id for versions in groups for f in versions}
    sources = list(session.scalars(select(Source).where(Source.case_id == case_id,
        Source.evidence_file_id.in_(file_ids), Source.status == 'admitted', Source.document_type == 'statement_review').order_by(Source.id)))
    targets, notices, cache = {}, [], {}
    for source in sources:
        statement_id = (source.metadata_ or {}).get('statement_import_statement_id')
        if scopes is not None and (source.evidence_file_id, statement_id) not in scopes:
            continue
        target = Target(file_id=source.evidence_file_id, source_id=source.id, revision='0'*64)
        targets[_key(target)] = target
    for file in files:
        try:
            first = read_statement_import(session, case_id=case_id, evidence_file_id=file.id, _cache=cache, _include_period_checks=False)
            identifiers = [c['id'] for c in first.get('statement_choices', [])] or [first.get('statement_id')]
            for sid in identifiers:
                if scopes is not None and (file.id, sid) not in scopes:
                    continue
                proposal = read_statement_import(session, case_id=case_id, evidence_file_id=file.id,
                    statement_id=sid, _cache=cache, _include_period_checks=False)
                if proposal.get('current_import'):
                    continue
                target = Target(file_id=file.id, statement_id=sid, revision='0'*64)
                targets[_key(target)] = target
        except PdfMappingError as exc:
            notices.append(dict(filename=file.original_filename, message=str(exc)))
    if len(targets) > 1000:
        raise PdfMappingError('Select fewer files: this selection contains more than 1,000 statement periods.', 422)
    rows = []
    for target in targets.values():
        try:
            row, _ = _load(session, case_id, target, cache)
            rows.append(row)
        except PdfMappingError as exc:
            notices.append(dict(filename=_file(session, case_id, target.file_id).original_filename, message=str(exc)))
    rows.sort(key=lambda row: (row['filename'], row['values'].get('account_number', ''), row['values'].get('period_start', ''), row['key']))
    return dict(case_id=str(case_id), items=rows, notices=notices)


def _plan(session, case_id, request):
    if len({_key(t) for t in request.targets}) != len(request.targets):
        raise PdfMappingError('Select each statement once.', 422)
    changes = request.changes.model_dump(exclude_none=True)
    plan, states, cache = [], [], {}
    for target in sorted(request.targets, key=lambda target: (str(target.file_id), _key(target))):
        row, state = _load(session, case_id, target, cache)
        if row['revision'] != target.revision:
            raise PdfMappingError(f'{row["filename"]} changed since selection. Refresh the statements and preview again; no details were changed.', 409)
        after = {**row['values'], **{key: value for key, value in changes.items()
            if request.mode == 'replace' or not row['values'].get(key, '').strip()}}
        if after.get('period_start') and after.get('period_end') and after['period_start'] > after['period_end']:
            raise PdfMappingError(f'{row["filename"]}: statement start must be on or before statement end.', 422)
        changed = {key: dict(before=row['values'].get(key, ''), after=after[key]) for key in changes if after[key] != row['values'].get(key, '')}
        if not target.source_id and 'currency' in changed:
            new = read_statement_import(session, case_id=case_id, evidence_file_id=target.file_id,
                statement_id=target.statement_id, currency=after['currency'], _cache=cache, _include_period_checks=False)
            state['raw'] = import_batches.rebase_review_currency(state['proposal'], new, state['raw'], after['currency'])
            state['proposal'] = new
        plan.append({**row, 'after': after, 'changes': changed})
        states.append((target, state))
    revision = _digest(dict(case_id=str(case_id), rows=plan, mode=request.mode, changes=changes))
    return dict(case_id=str(case_id), preview_revision=revision, items=plan,
        updated=sum(bool(row['changes']) for row in plan)), states


def preview(session, *, case_id, request):
    return _plan(session, case_id, request)[0]


def save(session, *, case_id, request, actor):
    try:
        # Same lock order as batch review/import: batches, evidence, saved sources.
        file_ids = sorted({target.file_id for target in request.targets}, key=str)
        batches = list(session.scalars(select(Batch).join(Item, Item.batch_id == Batch.id).where(
            Batch.case_id == case_id, Item.file_id.in_(file_ids), Batch.status != 'removed').distinct().order_by(Batch.id)))
        for batch in batches:
            locked = session.scalar(select(Batch).where(Batch.id == batch.id, Batch.case_id == case_id)
                .with_for_update().execution_options(populate_existing=True))
            if locked.worker_token and locked.lease_until and locked.lease_until.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc):
                raise PdfMappingError('A selected file is still being processed. Pause its batch or wait for it to finish, then retry. Your selection is kept.', 409)
        files = list(session.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id,
            EvidenceFile.id.in_(file_ids)).order_by(EvidenceFile.id).with_for_update().execution_options(populate_existing=True)))
        if len(files) != len(file_ids):
            raise PdfMappingError('A selected file is not in this case.', 404)
        payload = request.model_dump(mode='json')
        signature = _digest(dict(request=payload, actor=str(actor.user_id)))
        anchor = files[0]
        prior = (anchor.metadata_ or {}).get('bulk_account_detail_receipts', {}).get(str(request.request_id))
        if prior:
            if prior['signature'] != signature:
                raise PdfMappingError('This save request was already used for different changes. Preview again.', 409)
            return prior['result']
        source_ids = [t.source_id for t in request.targets if t.source_id]
        if source_ids:
            session.execute(select(Source).where(Source.case_id == case_id, Source.id.in_(source_ids))
                .order_by(Source.id).with_for_update().execution_options(populate_existing=True)).all()
        plan, states = _plan(session, case_id, request)
        if request.preview_revision != plan['preview_revision']:
            raise PdfMappingError('Review the current preview before saving these account details.', 409)
        account_changes = []
        for row, (target, state) in zip(plan['items'], states):
            if not row['changes']:
                continue
            after = row['after']
            if target.source_id:
                fields = {key: after[key] for key in ('holder', 'account_number', 'institution', 'period_start', 'period_end')}
                if 'currency' in row['changes']:
                    fields['currency'] = after['currency']
                result = update_statement_details(session, case_id=case_id, source_id=target.source_id,
                    request=StatementDetailsRequest(expected_revision=state['view']['revision'], **fields), actor=actor, commit=False)
                account_changes.append(dict(before=state['view']['account_id'], after=result['account_id']))
            else:
                raw = {**state['raw'], **after}
                import_batches.check_proposed_rows(state['proposal'], raw['rows'])
                file = next(f for f in files if f.id == target.file_id)
                metadata = deepcopy(file.metadata_ or {})
                previous = metadata.get('financial_review_progress', {}).get(target.statement_id or '')
                if previous:
                    metadata.setdefault('financial_review_history', []).append(previous)
                record = dict(request=raw, review_revision=_digest(raw), saved_at=datetime.now(timezone.utc).isoformat(),
                    saved_by=dict(user_id=str(actor.user_id), name=actor.name))
                metadata.setdefault('financial_review_progress', {})[target.statement_id or ''] = record
                metadata.setdefault('financial_account_detail_history', []).append(dict(
                    request_id=str(request.request_id), before=row['values'], after=after,
                    statement_id=target.statement_id, at=record['saved_at'], actor=record['saved_by']))
                file.metadata_ = metadata
                status, summary = import_batches.assess(state['proposal'], raw)
                for item in state['items']:
                    item.review_request = deepcopy(raw)
                    item.status = status
                    item.summary = {**item.summary, **summary}
            session.flush()
        result = dict(case_id=str(case_id), updated=plan['updated'], unchanged=len(plan['items'])-plan['updated'],
            imported=sum(bool(row['changes']) and row['status']=='Imported' for row in plan['items']),
            drafts=sum(bool(row['changes']) and row['status']=='Not imported' for row in plan['items']),
            items=[dict(key=row['key'], filename=row['filename'], changes=row['changes'], status=row['status']) for row in plan['items']],
            account_changes=account_changes)
        metadata = deepcopy(anchor.metadata_ or {})
        metadata.setdefault('bulk_account_detail_receipts', {})[str(request.request_id)] = dict(signature=signature, result=result)
        anchor.metadata_ = metadata
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
