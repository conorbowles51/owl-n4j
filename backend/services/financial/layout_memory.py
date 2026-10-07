"""Layout memory: an identity fact a person confirmed once, reused for the same printed layout and account.

The general statement engine proves a period's money from the page, but some
layouts do not print an identity fact in a form it can read (the holder, the
bank's name, the currency of a bare '$'). A person confirms that fact once for
one statement. The confirmation is stored as DATA (never code) in the case:

    key   = (field, printed account, balance convention, the field's printed
             identity evidence)                     -> ``memory_key``
    value = what the person confirmed

and every other period of the case whose reading has the same key receives the
confirmed value as its proposal, with the confirmation as its provenance.

Fail closed:
* only engine periods with a printed account take part (no account, no memory);
* a period whose printed evidence differs (another account number, other holder
  text, other legal-name lines, other currency wording) has another key and is
  not covered;
* memory supplies only the confirmed fact: the period's money must still be
  proved by its own reading, and every other check still applies;
* two active confirmations of one key with different values supply nothing;
* a value the page prints is never replaced: memory fills only an empty field.

Reversible: a confirmation is withdrawn (kept in the record, marked withdrawn);
the periods it filled are read again without it and are held again. A
remembered holder or bank is not part of a reading's revision, so saved
corrections are never invalidated by a confirmation or its withdrawal (the same
rule as derived period dates). A remembered currency is: the amounts are read
in it, exactly as when a person chooses the currency of one statement.

Storage: ``EvidenceFile.metadata_['financial_layout_memory']`` of the file on
which the person confirmed (the existing home of review state; no new table).
The layout key (headings + convention) is recorded with each confirmation and
used to group decisions; it is not part of the match, because OCR of headings
varies between periods of one layout while the printed account and identity
evidence do not.
"""
import uuid
from copy import deepcopy
from datetime import datetime, timezone

from sqlalchemy import String, cast, select

from postgres.models.evidence import EvidenceDocumentText, EvidenceFile, EvidenceTableGeometry
from services.financial.pdf_candidates import PdfMappingError, _digest

FIELDS = ('holder', 'institution', 'currency')
METADATA_KEY = 'financial_layout_memory'
VERSION = 'layout-memory-v1'
LABELS = dict(holder='account holder', institution='bank', currency='currency')


def memory_key(statement, field):
    """The key under which a confirmed ``field`` of this statement is remembered; None if it cannot take part."""
    if field not in FIELDS or not statement or statement.get('layout_id') != 'generic':
        return None
    account = (statement.get('account_reference') or '').strip()
    evidence = (statement.get('identity_evidence') or {}).get(field)
    if not account or evidence is None:
        return None
    return _digest(dict(memory=VERSION, field=field, account=account,
                        convention=statement.get('balance_convention') or 'asset_balance', evidence=evidence))


def missing_fields(statement):
    return [field for field in FIELDS if not (statement.get(field) or '').strip()]


def clean_value(field, value):
    value = ' '.join(str(value or '').split())
    if field == 'currency':
        from services.financial.currency_correction import currency_code
        try:
            return currency_code(value)
        except ValueError as exc:
            raise PdfMappingError(str(exc), 422) from exc
    if not value or len(value) > 128 or any(ord(c) < 32 for c in value):
        raise PdfMappingError(f'Enter the {LABELS[field]} shown on the statement (one line, at most 128 characters).', 422)
    return value


# ---------------------------------------------------------------------------
# Reading the case's memory
# ---------------------------------------------------------------------------

def _entries(session, case_id, *, lock=False):
    """[(file, entry)] of every confirmation recorded in the case, withdrawn ones included."""
    query = select(EvidenceFile).where(EvidenceFile.case_id == case_id,
                                       cast(EvidenceFile.metadata_, String).like('%' + METADATA_KEY + '%'))
    if lock:
        query = query.order_by(EvidenceFile.id).with_for_update().execution_options(populate_existing=True)
    found = []
    for file in session.scalars(query):
        for entry in (file.metadata_ or {}).get(METADATA_KEY, []):
            found.append((file, entry))
    return found


def case_memory(session, case_id, cache=None):
    """{key: [active entries]} for the case (cached per request when a cache is given)."""
    cache_key = ('layout_memory', str(case_id))
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    memory = {}
    for file, entry in _entries(session, case_id):
        if not entry.get('withdrawn_at'):
            memory.setdefault(entry['key'], []).append(dict(entry, file_id=str(file.id)))
    if cache is not None:
        cache[cache_key] = memory
    return memory


def remembered(session, case_id, statement, cache=None):
    """{field: entry} the case remembers for this statement's empty identity fields (one agreed value each)."""
    result = {}
    if not statement or statement.get('layout_id') != 'generic':
        return result
    memory = None
    for field in missing_fields(statement):
        key = memory_key(statement, field)
        if key is None:
            continue
        if memory is None:
            memory = case_memory(session, case_id, cache)
        entries = memory.get(key, [])
        if len({e['value'] for e in entries}) == 1:
            result[field] = entries[0]
    return result


def provenance(entry):
    return dict(basis='layout_memory', confirmation_id=entry['id'], value=entry['value'],
                confirmed_at=entry['confirmed_at'], confirmed_by=entry['confirmed_by'],
                source_file_id=entry.get('file_id'), source_statement_id=entry.get('statement_id'))


# ---------------------------------------------------------------------------
# Statements of a batch, by key
# ---------------------------------------------------------------------------

def file_catalog(session, case_id, file_id, cache):
    """The statement catalog of one prepared file (shares read_statement_import's cache keys)."""
    from services.financial.candidate_sources import read_candidate_source
    from services.financial.statement_import_catalog import statement_catalog
    text = session.get(EvidenceDocumentText, file_id)
    if text is None:
        return None
    source_key = (str(case_id), str(file_id), text.content_sha256)
    if source_key not in cache:
        pages = list(session.scalars(select(EvidenceTableGeometry).where(
            EvidenceTableGeometry.evidence_file_id == file_id).order_by(EvidenceTableGeometry.page_number)))
        cache[source_key] = [read_candidate_source(session, case_id=case_id, evidence_file_id=file_id,
                                                   page_number=page.page_number, table_index=index)
                             for page in pages for index in range(len(page.payload or []))]
    catalog_key = ('catalog', source_key)
    if catalog_key not in cache:
        cache[catalog_key] = statement_catalog(cache[source_key])
    return cache[catalog_key]


def _batch_statements(session, case_id, batch_id, cache):
    """[(item, statement)] for the batch's unfinished items read by the general engine."""
    from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
    from services.financial import import_batches
    import_batches.batch_for(session, case_id, batch_id)
    items = list(session.scalars(select(Item).where(Item.batch_id == batch_id, Item.status.in_(('ready', 'attention')))
                                 .order_by(Item.file_id, Item.statement_key)))
    found = []
    for item in items:
        catalog = file_catalog(session, case_id, item.file_id, cache)
        if not catalog:
            continue
        statement = next((s for s in catalog['statements'] if s['id'] == (item.statement_key or '')), None)
        if statement is None and len(catalog['statements']) == 1 and not item.statement_key:
            statement = catalog['statements'][0]
        if statement is not None and statement.get('layout_id') == 'generic':
            found.append((item, statement))
    return found


def _proposal(field, statement, memory):
    """The machine's prefill for a group: never a guess the page does not support."""
    account = statement.get('account_reference')
    # The same account confirmed under another printing of its identity.
    known = {e['value'] for entries in memory.values() for e in entries
             if e['field'] == field and e['account'] == account}
    if len(known) == 1:
        return next(iter(known)), 'confirmed_for_this_account'
    evidence = (statement.get('identity_evidence') or {}).get(field) or []
    if field == 'holder' and len(evidence) == 1:
        return evidence[0], 'printed_addressee'
    if field == 'institution' and len(evidence) == 1:
        return evidence[0].split(',')[0].strip(' .'), 'printed_legal_name'
    if field == 'currency':
        named = sorted({e.split(':', 1)[1] for e in evidence if e.startswith('named:')})
        if len(named) == 1:
            return named[0], 'printed_currency_name'
    return '', ''


def memory_groups(session, *, case_id, batch_id):
    """Held engine periods of a batch grouped by (field, layout memory key): one confirmation per group."""
    cache = {}
    memory = case_memory(session, case_id, cache)
    groups, not_eligible = {}, {}
    for item, statement in _batch_statements(session, case_id, batch_id, cache):
        if item.summary.get('can_import'):
            continue
        for field in missing_fields(statement):
            key = memory_key(statement, field)
            if key is None:
                not_eligible[field] = not_eligible.get(field, 0) + 1
                continue
            active = memory.get(key, [])
            group = groups.get((field, key))
            if group is None:
                value, basis = _proposal(field, statement, memory)
                group = groups[(field, key)] = dict(
                    key=key, field=field, label=LABELS[field], account=statement['account_reference'],
                    layout_key=statement.get('layout_key', ''), institution=statement.get('institution', ''),
                    printed=(statement.get('identity_evidence') or {}).get(field, [])[:6],
                    proposal=value, proposal_basis=basis,
                    confirmations=[dict(id=e['id'], value=e['value'], confirmed_at=e['confirmed_at'],
                                        confirmed_by=e['confirmed_by']) for e in active],
                    conflict=len({e['value'] for e in active}) > 1, statements=[])
            group['statements'].append(dict(item_id=str(item.id), file_id=str(item.file_id),
                                            statement_id=statement['id'], filename=item.summary.get('filename', ''),
                                            period_start=statement.get('period_start', ''),
                                            period_end=statement.get('period_end', ''),
                                            money_proved=bool((statement.get('engine') or {}).get('proved'))))
    ordered = sorted(groups.values(), key=lambda g: (-len(g['statements']), g['field'], g['account'], g['key']))
    for group in ordered:
        group['statement_count'] = len(group['statements'])
        group['money_proved_count'] = sum(s['money_proved'] for s in group['statements'])
    return dict(case_id=str(case_id), batch_id=str(batch_id), groups=ordered, not_eligible=not_eligible,
                revision=_digest(dict(groups=[(g['key'], g['statement_count'], g['confirmations']) for g in ordered])))


def case_confirmations(session, *, case_id):
    """Every confirmation recorded in the case, newest first, withdrawn ones included."""
    rows = []
    for file, entry in _entries(session, case_id):
        rows.append(dict({k: entry.get(k) for k in ('id', 'field', 'value', 'account', 'layout_key', 'statement_id',
                                                      'confirmed_at', 'confirmed_by', 'withdrawn_at', 'withdrawn_by',
                                                      'withdrawal_reason')},
                         file_id=str(file.id), filename=file.original_filename, active=not entry.get('withdrawn_at')))
    return dict(case_id=str(case_id), confirmations=sorted(rows, key=lambda r: r['confirmed_at'], reverse=True))


# ---------------------------------------------------------------------------
# Writing: confirm and withdraw
# ---------------------------------------------------------------------------

def _refresh(session, case_id, keys):
    """Re-read and re-assess every unfinished batch item of the case whose reading has one of these keys.

    Items with saved corrections keep them (their own values win; the remembered value is offered as the
    proposal when the review is opened); every other item is assessed again from a fresh reading, so a
    confirmation makes its periods ready and a withdrawal holds them again.
    """
    from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
    from services.financial import import_batches
    from services.financial.statement_import import read_statement_import
    from services.financial.statement_progress import review_progress
    cache, affected = {}, []
    items = list(session.scalars(select(Item).join(Batch, Batch.id == Item.batch_id).where(
        Batch.case_id == case_id, Batch.status != 'removed', Item.status.in_(('ready', 'attention')))
        .order_by(Item.id)))
    for item in items:
        catalog = file_catalog(session, case_id, item.file_id, cache)
        if not catalog:
            continue
        statement = next((s for s in catalog['statements'] if s['id'] == (item.statement_key or '')), None)
        if statement is None and len(catalog['statements']) == 1 and not item.statement_key:
            statement = catalog['statements'][0]
        if statement is not None and any(memory_key(statement, f) in keys for f in FIELDS):
            affected.append(item)
    result = dict(affected=len(affected), refreshed=0, kept_saved_corrections=0, failed=0)
    if not affected:
        return result
    inputs = import_batches._ProjectionInputs(session, case_id, affected)
    updates = {}
    for item in affected:
        file = inputs.files.get(item.file_id)
        if item.review_request or (file is not None and review_progress(file, item.statement_key)):
            result['kept_saved_corrections'] += 1
            continue
        remembered_currency = (item.summary.get('identity_memory') or {}).get('currency')
        currency = None if remembered_currency else (item.summary.get('currency') or None)
        snapshot = (item.status, deepcopy(item.summary), deepcopy(item.review_request))
        try:
            proposal = read_statement_import(session, case_id=case_id, evidence_file_id=item.file_id, currency=currency,
                                             statement_id=item.statement_key or None, _cache=cache)
            state, assessment = import_batches.assess(proposal, None)
        except PdfMappingError:
            result['failed'] += 1
            continue
        summary = {key: value for key, value in item.summary.items() if key not in ('readiness', 'identity_memory')}
        summary.update(assessment)
        updates[item.id] = (snapshot, import_batches._readiness_change(inputs, item, state, summary, None))
    result['refreshed'] = import_batches._write_items(session, updates, import_batches._apply_readiness)
    return result


def _statement(session, case_id, file_id, statement_id):
    try:
        file_id = file_id if isinstance(file_id, uuid.UUID) else uuid.UUID(str(file_id))
    except ValueError as exc:
        raise PdfMappingError('The selected statement is not in this case.', 404) from exc
    file = session.scalar(select(EvidenceFile).where(EvidenceFile.case_id == case_id, EvidenceFile.id == file_id)
                          .with_for_update().execution_options(populate_existing=True))
    if file is None:
        raise PdfMappingError('The selected statement is not in this case.', 404)
    catalog = file_catalog(session, case_id, file.id, {})
    statement = next((s for s in (catalog or {}).get('statements', []) if s['id'] == statement_id), None)
    if statement is None:
        raise PdfMappingError('This statement period is no longer available. Refresh the list.', 409)
    return file, statement


def confirm(session, *, case_id, file_id, statement_id, field, value, expected_key, actor, request_id=None):
    """Remember ``field`` = ``value`` for every period sharing this statement's layout memory key."""
    try:
        if field not in FIELDS:
            raise PdfMappingError('Choose the account holder, bank or currency.', 422)
        value = clean_value(field, value)
        file, statement = _statement(session, case_id, file_id, statement_id)
        key = memory_key(statement, field)
        if key is None:
            raise PdfMappingError('This statement cannot be remembered by layout: it has no printed account number or '
                                  'was not read by the general statement reader. Review it individually.', 409)
        if key != expected_key:
            raise PdfMappingError('The statement reading changed since the group was listed. Refresh the list; nothing was saved.', 409)
        if (statement.get(field) or '').strip():
            raise PdfMappingError(f'The {LABELS[field]} is printed on this statement and was read from it; nothing was saved.', 409)
        for other_file, entry in _entries(session, case_id, lock=True):
            if entry['key'] != key or entry.get('withdrawn_at'):
                continue
            if entry['value'] == value:
                return dict(case_id=str(case_id), confirmation=dict(entry, file_id=str(other_file.id)),
                            already_confirmed=True, refreshed=_refresh(session, case_id, {key}))
            raise PdfMappingError(f'A different {LABELS[field]} is already confirmed for these statements. '
                                  'Withdraw that confirmation first.', 409)
        entry = dict(id=str(uuid.uuid4()), version=VERSION, key=key, field=field, value=value,
                     account=statement['account_reference'], convention=statement.get('balance_convention') or 'asset_balance',
                     layout_key=statement.get('layout_key', ''), layout_fingerprint=statement.get('layout_fingerprint', ''),
                     evidence=(statement.get('identity_evidence') or {}).get(field, []), statement_id=statement_id,
                     confirmed_at=datetime.now(timezone.utc).isoformat(),
                     confirmed_by=dict(user_id=str(actor.user_id), name=actor.name),
                     request_id=str(request_id) if request_id else None, withdrawn_at=None, withdrawn_by=None)
        metadata = deepcopy(file.metadata_ or {})
        metadata.setdefault(METADATA_KEY, []).append(entry)
        file.metadata_ = metadata
        session.commit()
    except Exception:
        session.rollback()
        raise
    return dict(case_id=str(case_id), confirmation=dict(entry, file_id=str(file.id)), already_confirmed=False,
                refreshed=_refresh(session, case_id, {key}))


def withdraw(session, *, case_id, confirmation_id, reason, actor):
    """Withdraw one confirmation: the periods it filled are read again without it (held again)."""
    try:
        reason = ' '.join(str(reason or '').split())
        if not reason or len(reason) > 500:
            raise PdfMappingError('Record why this confirmation is withdrawn (at most 500 characters).', 422)
        for file, entry in _entries(session, case_id, lock=True):
            if entry['id'] != str(confirmation_id):
                continue
            if entry.get('withdrawn_at'):
                return dict(case_id=str(case_id), confirmation=entry, already_withdrawn=True,
                            refreshed=dict(refreshed=0, skipped=0, remaining=0))
            metadata = deepcopy(file.metadata_ or {})
            for stored in metadata.get(METADATA_KEY, []):
                if stored['id'] == entry['id']:
                    stored.update(withdrawn_at=datetime.now(timezone.utc).isoformat(),
                                  withdrawn_by=dict(user_id=str(actor.user_id), name=actor.name), withdrawal_reason=reason)
                    entry = stored
            file.metadata_ = metadata
            session.commit()
            return dict(case_id=str(case_id), confirmation=entry, already_withdrawn=False,
                        refreshed=_refresh(session, case_id, {entry['key']}))
        raise PdfMappingError('This confirmation is not in this case.', 404)
    except Exception:
        session.rollback()
        raise


