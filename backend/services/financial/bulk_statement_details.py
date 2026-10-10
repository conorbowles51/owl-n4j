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
from services.financial.effective_statement_review import resolve_review, request_signature
from services.financial.statement_progress import review_progress

FIELDS = ('holder', 'account_number', 'institution', 'currency', 'period_start', 'period_end')


class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    file_ids: list[UUID] = Field(default_factory=list, max_length=1000)
    batch_id: UUID | None = None
    review_group: str | None = None

    @model_validator(mode='after')
    def one_scope(self):
        if bool(self.file_ids) == bool(self.batch_id):
            raise ValueError('Choose files or one processing batch.')
        if self.review_group and not self.batch_id:
            raise ValueError('Choose a batch for grouped review decisions.')
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
    period_start_unprinted: Literal[True] | None = None
    no_activity_confirmed: Literal[True] | None = None

    @model_validator(mode='after')
    def valid_fields(self):
        if self.no_activity_confirmed and (self.period_start_unprinted or any(getattr(self, key) is not None for key in FIELDS)):
            raise ValueError('Confirm no activity separately; each statement keeps its own details, dates and balances.')
        if not self.period_start_unprinted and not self.no_activity_confirmed and not any(getattr(self, key) is not None for key in FIELDS):
            raise ValueError('Choose at least one field to change.')
        if self.period_start_unprinted and any(getattr(self, key) is not None for key in FIELDS):
            raise ValueError('Confirm unprinted start dates separately; each statement keeps its own details and closing date.')
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
    file = session.get(EvidenceFile, file_id)
    if file is None or str(file.case_id) != str(case_id):
        raise PdfMappingError('A selected file is not in this case.', 404)
    from services.financial.file_visibility import require_financial_file
    require_financial_file(file)
    return file


def _items(session, case_id, file_id, statement_id):
    return list(session.scalars(select(Item).join(Batch, Batch.id == Item.batch_id).where(
        Batch.case_id == case_id, Batch.status != 'removed', Item.file_id == file_id,
        Item.statement_key == (statement_id or ''), Item.status.notin_(('removed', 'superseded_reading'))).order_by(Item.id)))


# Listing and previewing use the saved statement records and the readings a
# batch check stored; neither re-reads a PDF. A statement's PDF is read again
# only for a change that depends on the reading (currency, unprinted start,
# no activity) and when a draft is saved. Revisions from these paths are
# opaque tokens: _plan recomputes them the same way before any change.
STORED = 'bulk_stored_readings'
_STORED_FIELDS = (('holder', 'holder'), ('account_number', 'account'), ('institution', 'institution'),
                  ('currency', 'currency'), ('period_start', 'period_start'), ('period_end', 'period_end'))
_INDIVIDUAL = 'Open this statement individually to review its import or account assignment.'
# Problems assess() records for a receipt reading and an unseparated reading.
_DOCUMENT_REVIEW = 'This is a receipt or payment document. Open its document review.'
_READING_FAILURE = 'This PDF contains several Capital One statements'
# Item statuses that _load refuses before it reads anything.
_REFUSED = ('pending_import', 'imported', 'skipped', 'assigned', 'duplicate_ignored')


def _saved_records(session, case_id, source_ids, cache):
    """Saved statements' details from their records, loaded together, without
    decoding their stored readings (the same values read_statement_details shows)."""
    from postgres.models.financial import FinancialAccount, FinancialStatementPeriod
    from services.financial.statement_details import DETAIL_KEYS
    wanted = [sid for sid in {UUID(str(sid)) for sid in source_ids} if ('saved_record', sid) not in cache]
    if not wanted:
        return
    meta = Source.metadata_
    request = meta['statement_import_request']
    keys = (*DETAIL_KEYS, 'period_start', 'period_end')
    rows = session.execute(select(Source.id, Source.evidence_file_id, Source.document_type, Source.status,
        meta['statement_details_review'], meta['statement_details_history'], meta['statement_account_id'].as_string(),
        meta['statement_import_original_sha256'].as_string(), meta['statement_import_request_sha256'].as_string(),
        meta['statement_details_review_sha256'].as_string(), request['currency'].as_string(),
        *[request[key].as_string() for key in keys])
        .where(Source.case_id == case_id, Source.id.in_(wanted))).all()
    periods = {}
    for period in session.scalars(select(FinancialStatementPeriod).where(FinancialStatementPeriod.case_id == case_id,
            FinancialStatementPeriod.source_document_id.in_(wanted)).order_by(FinancialStatementPeriod.id)):
        periods.setdefault(period.source_document_id, []).append(period)
    found = {row[0]: row for row in rows}
    account_ids = set()
    for sid in wanted:
        row = found.get(sid)
        if row is None:
            cache[('saved_record', sid)] = PdfMappingError('Statement not found in this case.', 404)
            continue
        _, file_id, kind, status, review, history, account_ref, *_rest = row
        if kind != 'statement_review' or status != 'admitted':
            cache[('saved_record', sid)] = PdfMappingError('Only a current imported statement can be edited here.', 409)
            continue
        found_periods = periods.get(sid, [])
        if len(found_periods) > 1:
            cache[('saved_record', sid)] = PdfMappingError('Choose an individual statement period before editing.', 409)
            continue
        try:
            account_id = found_periods[0].account_id if found_periods else UUID(account_ref)
        except (TypeError, ValueError):
            cache[('saved_record', sid)] = PdfMappingError('The statement account is unavailable.', 409)
            continue
        account_ids.add(account_id)
        cache[('saved_record', sid)] = (row, found_periods[0] if found_periods else None, account_id)
    accounts = {account.id: account for account in session.scalars(select(FinancialAccount).where(
        FinancialAccount.case_id == case_id, FinancialAccount.id.in_(account_ids)))} if account_ids else {}
    for sid in wanted:
        entry = cache[('saved_record', sid)]
        if isinstance(entry, PdfMappingError):
            continue
        row, period, account_id = entry
        account = accounts.get(account_id)
        if account is None:
            cache[('saved_record', sid)] = PdfMappingError('The statement account is unavailable.', 409)
            continue
        _, file_id, _kind, _status, review, history, _ref, original_sha, request_sha, review_sha, request_currency, *values = row
        review = review or {}
        details = {**{key: value or '' for key, value in zip(keys, values)}, **review.get('details', {})}
        if period:
            for key in ('period_start', 'period_end'):
                value = getattr(period, key)
                details[key] = value.isoformat() if value else ''
        currency = period.currency if period else (review.get('currency') or request_currency or None)
        revision = _digest(dict(saved_record=str(sid), details=details, currency=currency, account=str(account.id),
            period=[str(period.id), str(period.period_start), str(period.period_end), period.currency,
                    period.opening_balance_minor, period.closing_balance_minor] if period else None,
            identity=[account.identity_key, account.holder_name, account.identifier_as_printed, account.institution_name],
            seals=[original_sha, request_sha, review_sha], review=review, history=history or []))
        cache[('saved_record', sid)] = dict(evidence_file_id=str(file_id), account_id=str(account.id),
            values={**details, 'currency': currency or ''}, revision=revision)


def _summary_values(summary):
    return {field: summary.get(name, '') for field, name in _STORED_FIELDS}


def _individual(summary):
    messages = [problem.get('message') or '' for problem in summary.get('problems', [])]
    return bool(summary.get('assignment_only') or _DOCUMENT_REVIEW in messages
                or any(message.startswith(_READING_FAILURE) for message in messages))


def _stored_draft(file, statement_id, items):
    """Values and a revision for an unimported period from the readings its
    batch checks stored, or None when only a fresh reading can answer: a
    batch correction, a saved review of another reading, or batches that
    disagree on whether it needs its individual review."""
    from services.financial.statement_progress import review_progress
    if not items:
        return None
    if any(item.status not in ('ready', 'attention') or 'revision' not in item.summary for item in items):
        return None
    individual = [_individual(item.summary) for item in items]
    if all(individual):
        # The batch read a receipt, payments still to assign or unseparated
        # periods: as _load does for that reading, send the investigator to
        # the individual review.
        raise PdfMappingError(_INDIVIDUAL, 409)
    if any(individual):
        return None
    # Successive batch checks of one PDF can record readings from different
    # reader versions; the most recently written one is the current reading.
    newest = max(items, key=lambda item: (item.updated_at, item.created_at, str(item.id)))
    values = _summary_values(newest.summary)
    # The saved draft _load resolves to: the shared review, which every batch
    # draft must follow, or the batches' one draft. A draft of another reading
    # or competing drafts need the PDF (and usually an individual review).
    shared = review_progress(file, statement_id)
    requests = [item.review_request for item in items if item.review_request is not None]
    effective = None
    if shared is not None:
        effective = shared.get('request') or {}
        compatible = {request_signature(effective), *shared.get('superseded_request_signatures', []),
                      shared.get('initial_request_signature')}
        if any(request_signature(request) not in compatible for request in requests):
            return None
    elif requests:
        if len({request_signature(request) for request in requests}) != 1:
            return None
        effective = requests[0]
    if effective is not None:
        if effective.get('expected_revision') not in {item.summary['revision'] for item in items}:
            return None
        values = {key: effective.get(key, '') for key in FIELDS}
    revision = _digest(dict(stored_reading=values, file=str(file.id), statement=statement_id,
        items=[(str(item.id), item.status, item.summary['revision'], item.review_request) for item in items],
        shared=shared.get('review_revision') if shared else None))
    return values, revision


def _batch_items(session, case_id, file_ids, cache):
    """The current batch items of each file by period, loaded together: what
    _items returns for each period, without one query per period."""
    wanted = {UUID(str(fid)) for fid in file_ids} - {UUID(key[1]) for key in cache if isinstance(key, tuple) and key[0] == STORED}
    if not wanted:
        return
    keyed = {fid: {} for fid in wanted}
    for item in session.scalars(select(Item).join(Batch, Batch.id == Item.batch_id).where(
            Batch.case_id == case_id, Batch.status != 'removed', Item.file_id.in_(wanted),
            Item.status.notin_(('removed', 'superseded_reading'))).order_by(Item.id)):
        keyed[item.file_id].setdefault(item.statement_key or '', []).append(item)
    for fid, found in keyed.items():
        cache[(STORED, str(fid))] = found


def _stored_statements(session, case_id, files, cache):
    """Each file's unimported periods from its stored batch readings, or None
    for a file that must be read: no current batch reading, a file-level
    reading, or saved records the readings do not settle (an import whose
    period the batch did not record, or an excluded copy)."""
    if not files:
        return {}
    _batch_items(session, case_id, [file.id for file in files], cache)
    copies = {}
    for source_id, sha, status, statement, removal, rung in session.execute(select(Source.id, Source.sha256_at_ingestion,
            Source.status, Source.metadata_['statement_import_statement_id'].as_string(),
            Source.metadata_['financial_import_removal'], Source.duplicate_match_rung).where(
            Source.case_id == case_id, Source.sha256_at_ingestion.in_({file.sha256 for file in files}))):
        copies.setdefault(sha, []).append((str(source_id), status, statement, removal, rung))
    result = {}
    for file in files:
        result[file.id] = None
        keyed = cache[(STORED, str(file.id))]
        if not keyed or ('' in keyed and len(keyed) > 1):
            # A file-level reading beside printed periods: the PDF was read
            # both ways, so only a fresh reading says which is current.
            continue
        found = copies.get(file.sha256, [])
        if any(status == 'superseded' and rung is not None for _, status, _, _, rung in found):
            continue
        current = [(source_id, statement or '') for source_id, status, statement, removal, _ in found
                   if status != 'superseded' and not removal]
        statements = [statement for _, statement in current]
        if any(statement not in keyed for statement in statements) or len(statements) != len(set(statements)):
            continue
        current_ids = {source_id for source_id, _ in current}
        # A period whose batch recorded its import into a current saved
        # statement is that statement, whichever period id the import kept.
        saved = set(statements) | {key for key, found_items in keyed.items() if any(item.status == 'imported'
            and str(item.summary.get('source_document_id')) in current_ids for item in found_items)}
        drafts = [key or None for key in sorted(set(keyed) - saved)]
        if current and any(not any(item.status in _REFUSED for item in keyed[key or '']) for key in drafts):
            # Beside a saved period, only a period its batch already refuses is
            # listed without reading: whether another period overlaps a saved
            # one is a question for the reading.
            continue
        result[file.id] = drafts
    return result


def _load(session, case_id, target, cache, *, stored=False):
    """One statement's row. With `stored`, a saved statement comes from its
    records and an unimported period from its batch's stored reading where one
    settles it (state['stored'] is then true); otherwise the PDF is read."""
    file = _file(session, case_id, target.file_id)
    if target.source_id:
        _saved_records(session, case_id, [target.source_id], cache)
        record = cache[('saved_record', UUID(str(target.source_id)))]
        if isinstance(record, PdfMappingError):
            raise record
        if record['evidence_file_id'] != str(file.id):
            raise PdfMappingError('The selected statement does not belong to this PDF.', 409)
        values, revision = dict(record['values']), record['revision']
        state = dict(account_id=record['account_id'])
    else:
        keyed = cache.get((STORED, str(file.id)))
        items = list(keyed.get(target.statement_id or '', [])) if keyed is not None else _items(
            session, case_id, file.id, target.statement_id)
        if any(item.status in ('pending_import', 'imported', 'skipped', 'assigned') for item in items):
            raise PdfMappingError('This statement is importing, imported or left unimported. Refresh the list or restore it to review first.', 409)
        if any(item.status == 'duplicate_ignored' for item in items):
            raise PdfMappingError('This copy was left unimported as a duplicate. Restore it explicitly before changing its details.', 409)
        reading = _stored_draft(file, target.statement_id, items) if stored else None
        if reading is not None:
            values, revision = reading
            state = dict(stored=True, items=items)
            return _row(file, target, values, revision, None), state
        shared = review_progress(file, target.statement_id)
        # A predecessor is not a competing investigator edit. Resolve it before
        # choosing currency, otherwise a corrected currency falsely splits the
        # same saved review into two conflicting drafts.
        drafts = [resolve_review(item.review_request, shared)[0] for item in items]
        drafts = [raw for raw in drafts if raw]
        if shared:
            drafts.append(shared['request'])
        currencies = {raw.get('currency') for raw in drafts}
        if len(currencies) > 1:
            raise PdfMappingError('This statement has conflicting saved reviews. Open it to compare them first.', 409)
        # Identity values only: the duplicate verdict re-reads the retained
        # statement of every earlier decision and is attached at save time,
        # where it decides the saved review's status (see _with_duplicate).
        chosen = next(iter(currencies), None)
        listed = cache.get(('bulk_listed_reading', str(file.id), target.statement_id)) if chosen is None else None
        proposal = listed or read_statement_import(session, case_id=case_id, evidence_file_id=file.id,
            statement_id=target.statement_id, currency=chosen, _cache=cache,
            _include_period_checks=False, _include_duplicate_disposition=False)
        if proposal.get('current_import') or proposal.get('document_review') or proposal.get('assignment_only') or proposal.get('reading_failure'):
            raise PdfMappingError(_INDIVIDUAL, 409)
        saved = proposal.get('saved_review')
        if saved:
            drafts.append(saved['request'])
        from services.financial.review_upgrade import upgrade_request
        drafts = [upgrade_request(raw, proposal) or raw for raw in drafts]
        resolved = [resolve_review(raw, saved, baseline=import_batches.initial_request(proposal)) for raw in drafts]
        if any(conflict for _, conflict in resolved):
            raise PdfMappingError('This statement has different corrections saved in its batch and PDF review. Compare them individually first.', 409)
        drafts = [raw for raw, _ in resolved]
        if len({request_signature(raw) for raw in drafts}) > 1:
            raise PdfMappingError('This statement has different corrections saved in its batch and PDF review. Compare them individually first.', 409)
        raw = deepcopy(drafts[0] if drafts else import_batches.initial_request(proposal))
        if raw['expected_revision'] != proposal['revision']:
            raise PdfMappingError('The reading changed since its corrections were saved. Review this statement individually first.', 409)
        values = {key: raw.get(key, '') for key in FIELDS}
        revision = _digest(dict(proposal=proposal['revision'], raw=raw, saved=saved,
            items=[(str(item.id), item.status, item.review_request) for item in items]))
        state = dict(proposal=proposal, raw=raw, items=items)
    return _row(file, target, values, revision, state.get('account_id')), state


def _row(file, target, values, revision, account_id):
    return dict(key=_key(target), file_id=str(file.id), source_id=str(target.source_id) if target.source_id else None,
        account_id=account_id if target.source_id else None,
        statement_id=target.statement_id, revision=revision, filename=file.original_filename,
        status='Imported' if target.source_id else 'Not imported', values=values)


def _read_draft(session, case_id, target, row, filename, cache):
    """The full reading of a period listed from its stored batch reading, for a
    change that depends on it. Its details must still be the listed ones."""
    full, state = _load(session, case_id, target, cache)
    if full['values'] != row['values']:
        raise PdfMappingError(f'{filename}: this statement was read again since its batch check, so the listed details are out of date. '
            'Open it individually or check its batch again; no details were changed.', 409)
    return state


def list_statements(session, *, case_id, selection):
    """Files show each printed period, including imported and saved draft scopes."""
    if selection.batch_id:
        import_batches.batch_for(session, case_id, selection.batch_id)
        batch_items = list(session.scalars(select(Item).where(Item.batch_id == selection.batch_id, Item.status != 'removed')))
        if selection.review_group:
            from services.financial.batch_review_summary import validate_group, matches_group, is_blocked
            validate_group(selection.review_group)
            batch_items = [item for item in import_batches.checked_batch_items(session, case_id, batch_items)
                if is_blocked(item) and matches_group(item, selection.review_group)]
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
    # Identifiers only: a saved statement's stored reading is never decoded to list it.
    sources = session.execute(select(Source.id, Source.evidence_file_id, Source.metadata_['statement_import_statement_id'].as_string())
        .where(Source.case_id == case_id, Source.evidence_file_id.in_(file_ids), Source.status == 'admitted',
               Source.document_type == 'statement_review').order_by(Source.id)).all()
    from services.financial.statement_import import READ_ONLY_LISTING
    targets, notices, cache = {}, [], {READ_ONLY_LISTING: True}
    stored = _stored_statements(session, case_id, files, cache)
    for source_id, evidence_file_id, statement_id in sources:
        if scopes is not None and (evidence_file_id, statement_id) not in scopes:
            continue
        target = Target(file_id=evidence_file_id, source_id=source_id, revision='0'*64)
        targets[_key(target)] = target
    for file in files:
        if stored.get(file.id) is not None:
            for key in stored[file.id]:
                if scopes is not None and (file.id, key) not in scopes:
                    continue
                target = Target(file_id=file.id, statement_id=key, revision='0'*64)
                targets[_key(target)] = target
            continue
        try:
            first = read_statement_import(session, case_id=case_id, evidence_file_id=file.id, _cache=cache,
                _include_period_checks=False, _include_duplicate_disposition=False)
            identifiers = [c['id'] for c in first.get('statement_choices', [])] or [first.get('statement_id')]
            for sid in identifiers:
                if scopes is not None and (file.id, sid) not in scopes:
                    continue
                proposal = read_statement_import(session, case_id=case_id, evidence_file_id=file.id,
                    statement_id=sid, _cache=cache, _include_period_checks=False, _include_duplicate_disposition=False)
                if proposal.get('current_import'):
                    continue
                # The same call _load makes when no saved review names a
                # currency; reuse it instead of reading the statement twice.
                cache[('bulk_listed_reading', str(file.id), sid)] = proposal
                target = Target(file_id=file.id, statement_id=sid, revision='0'*64)
                targets[_key(target)] = target
        except PdfMappingError as exc:
            notices.append(dict(filename=file.original_filename, message=str(exc)))
    if len(targets) > 1000:
        raise PdfMappingError('Select fewer files: this selection contains more than 1,000 statement periods.', 422)
    _saved_records(session, case_id, [t.source_id for t in targets.values() if t.source_id], cache)
    rows = []
    for target in targets.values():
        try:
            row, _ = _load(session, case_id, target, cache, stored=True)
            rows.append(row)
        except PdfMappingError as exc:
            notices.append(dict(filename=_file(session, case_id, target.file_id).original_filename, message=str(exc)))
    rows.sort(key=lambda row: (row['filename'], row['values'].get('account_number', ''), row['values'].get('period_start', ''), row['key']))
    return dict(case_id=str(case_id), items=rows, notices=notices)


def _no_activity_plan(target, state, after):
    """One investigator confirmation of no activity for each eligible period.

    It applies only to an unimported period with no selected payments whose
    remaining question is activity, bound to that period's own details and
    revision. A period whose source already establishes it needs nothing; one
    whose printed balances differ cannot be quiet and is excluded.
    """
    from pydantic import ValidationError
    from services.financial.statement_import import StatementImportRequest
    from services.financial.statement_admission import assess_admission
    if target.source_id:
        return 'Already imported; saved records are unchanged.', None, None
    proposal, raw = state['proposal'], {**state['raw'], **after}
    if any(not row.get('excluded') for row in raw['rows']):
        return 'Payments are selected in this statement; it is not a period without activity.', None, None
    evidence = proposal.get('no_activity_evidence') or {}
    source_check = evidence.get('message') if evidence.get('verified') is False else None
    if evidence.get('reason') == 'endpoints_differ':
        return 'Its printed opening and ending balances differ, so money moved in this period.', None, source_check
    try:
        admission = assess_admission(proposal, StatementImportRequest.model_validate(raw))
    except (ValidationError, PdfMappingError):
        return 'Open this statement individually: its review is incomplete.', None, source_check
    if not any(blocker['kind'] == 'no_activity' for blocker in admission['blockers']):
        return 'No confirmation is needed for this statement.', None, source_check
    return None, admission['revision'], source_check


def _plan(session, case_id, request, *, saving=False):
    if len({_key(t) for t in request.targets}) != len(request.targets):
        raise PdfMappingError('Select each statement once.', 422)
    changes = request.changes.model_dump(exclude_none=True)
    unprinted = changes.pop('period_start_unprinted', False)
    quiet = changes.pop('no_activity_confirmed', False)
    plan, states, cache = [], [], {}
    targets = sorted(request.targets, key=lambda target: (str(target.file_id), _key(target)))
    _saved_records(session, case_id, [t.source_id for t in targets if t.source_id], cache)
    _batch_items(session, case_id, [t.file_id for t in targets if not t.source_id], cache)
    for target in targets:
        row, state = _load(session, case_id, target, cache, stored=True)
        if row['revision'] != target.revision:
            raise PdfMappingError(f'{row["filename"]} changed since selection. Refresh the statements and preview again; no details were changed.', 409)
        after = {**row['values'], **{key: value for key, value in changes.items()
            if request.mode == 'replace' or not row['values'].get(key, '').strip()}}
        if after.get('period_start') and after.get('period_end') and after['period_start'] > after['period_end']:
            raise PdfMappingError(f'{row["filename"]}: statement start must be on or before statement end.', 422)
        changed = {key: dict(before=row['values'].get(key, ''), after=after[key]) for key in changes if after[key] != row['values'].get(key, '')}
        if state.get('stored') and (unprinted or quiet or 'currency' in changed or (saving and changed)):
            # Only this change depends on the reading: read this period now.
            state = _read_draft(session, case_id, target, row, row['filename'], cache)
        excluded_reason = None
        if unprinted:
            from services.financial.import_issues import calendar_date
            metadata = state.get('proposal', {}).get('metadata', {})
            closing = after.get('period_end') or state.get('proposal', {}).get('printed_closing_date_iso', '')
            if target.source_id:
                excluded_reason = 'Already imported; saved records are unchanged.'
            elif after.get('period_start') or calendar_date(metadata.get('period_start', '')):
                excluded_reason = 'A start date is present; it is preserved.'
            elif not calendar_date(closing):
                excluded_reason = 'No valid closing date is available; this statement still needs a date decision.'
            else:
                if not state['raw'].get('period_start_unprinted'):
                    changed['period_start_unprinted'] = dict(before='Not confirmed', after='Confirmed not printed; start remains unknown')
                if closing != after.get('period_end'):
                    changed['period_end'] = dict(before=after.get('period_end', ''), after=closing)
                    after['period_end'] = closing
        no_activity_revision = None
        source_check = None
        if quiet:
            excluded_reason, no_activity_revision, source_check = _no_activity_plan(target, state, after)
            if no_activity_revision:
                changed['no_activity_confirmed'] = dict(before='Not confirmed',
                    after='Confirmed: every page checked; no transactions in this period')
        if not target.source_id and 'currency' in changed:
            new = read_statement_import(session, case_id=case_id, evidence_file_id=target.file_id,
                statement_id=target.statement_id, currency=after['currency'], _cache=cache,
                _include_period_checks=False, _include_duplicate_disposition=False)
            state['raw'] = import_batches.rebase_review_currency(state['proposal'], new, state['raw'], after['currency'])
            state['proposal'] = new
        plan.append({**row, 'after': after, 'changes': changed, 'excluded_reason': excluded_reason,
                     **(dict(no_activity_revision=no_activity_revision, source_check=source_check) if quiet else {})})
        states.append((target, state))
    revision = _digest(dict(case_id=str(case_id), rows=plan, mode=request.mode, changes=changes, unprinted=unprinted,
                            **(dict(no_activity=True) if quiet else {})))
    return dict(case_id=str(case_id), preview_revision=revision, items=plan,
        updated=sum(bool(row['changes']) for row in plan)), states


def _with_duplicate(session, file, proposal, cache):
    """The proposal as read_statement_import returns it by default: with the
    current duplicate decision attached (an ignored copy saves as ignored)."""
    if 'duplicate_disposition' in proposal:
        return proposal
    from services.financial.pending_statement_duplicates import read_duplicate_disposition
    return {**proposal, 'duplicate_disposition': read_duplicate_disposition(session, file, proposal, cache=cache)}


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
        plan, states = _plan(session, case_id, request, saving=True)
        if request.preview_revision != plan['preview_revision']:
            raise PdfMappingError('Review the current preview before saving these account details.', 409)
        account_changes, duplicate_cache = [], {}
        for row, (target, state) in zip(plan['items'], states):
            if not row['changes']:
                continue
            after = row['after']
            if target.source_id:
                fields = {key: after[key] for key in ('holder', 'account_number', 'institution', 'period_start', 'period_end')}
                if 'currency' in row['changes']:
                    fields['currency'] = after['currency']
                view = read_statement_details(session, case_id=case_id, source_id=target.source_id)
                result = update_statement_details(session, case_id=case_id, source_id=target.source_id,
                    request=StatementDetailsRequest(expected_revision=view['revision'], **fields), actor=actor, commit=False)
                account_changes.append(dict(before=view['account_id'], after=result['account_id']))
            else:
                raw = {**state['raw'], **after}
                if request.changes.period_start_unprinted:
                    raw['period_start_unprinted'] = True
                if request.changes.no_activity_confirmed:
                    raw.update(no_activity_confirmed=True, no_activity_revision=row['no_activity_revision'])
                import_batches.check_proposed_rows(state['proposal'], raw['rows'])
                file = next(f for f in files if f.id == target.file_id)
                metadata = deepcopy(file.metadata_ or {})
                previous = metadata.get('financial_review_progress', {}).get(target.statement_id or '')
                if previous:
                    metadata.setdefault('financial_review_history', []).append(previous)
                record = dict(request=raw, review_revision=_digest(raw), saved_at=datetime.now(timezone.utc).isoformat(),
                    saved_by=dict(user_id=str(actor.user_id), name=actor.name))
                status, summary = import_batches.assess(_with_duplicate(session, file, state['proposal'], duplicate_cache), raw)
                record.update(assessment=summary, assessment_status=status,
                    initial_request_signature=request_signature(import_batches.initial_request(state['proposal'])),
                    superseded_request_signatures=sorted(set([
                        *(previous or {}).get('superseded_request_signatures', []),
                        *([request_signature(previous['request'])] if previous else []),
                    ])))
                metadata.setdefault('financial_review_progress', {})[target.statement_id or ''] = record
                metadata.setdefault('financial_account_detail_history', []).append(dict(
                    request_id=str(request.request_id), before=row['values'], after=after,
                    period_start_unprinted=bool(raw.get('period_start_unprinted')),
                    **(dict(no_activity_confirmed=True) if request.changes.no_activity_confirmed else {}),
                    statement_id=target.statement_id, at=record['saved_at'], actor=record['saved_by']))
                file.metadata_ = metadata
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
