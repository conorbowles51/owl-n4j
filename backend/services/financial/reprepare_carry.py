"""Carry an investigator's saved work through held_reprepare: her file is prepared by the current reader, her work kept.

held_reprepare prepares a held statement again from its saved reading when a deploy changes the backend
reader. Until now any statement with investigator work (saved progress or a batch draft) was left as it was,
so it never got the improved reader. With this switch on, such a statement IS prepared again, and:

* every value she saved (statement details, notes, confirmations, rows, balances, hand-added rows) is
  carried onto the matching statement of the current reading and wins over the reader's value;
* where a value of hers differs from what the current reader reads, the statement is held with a question
  showing both values (``carry_conflicts`` / ``carry_row_conflicts`` on the carried record, shown in the queue
  by ``review_carry.conflict_problems``). A payment line the current reader reads that her saved work did not
  have is asked about the same way. Nothing of hers is replaced silently;
* her original records stay on the file untouched: the saved-progress record is kept in
  ``financial_review_history`` and, verbatim with every batch draft, in ``financial_reprepare_carry_log``. Each
  batch draft that changes keeps its earlier value in the item's ``review_upgrade_history``. Nothing saved or
  imported changes;
* the carried record stays hers (``saved_by`` is her saver), so it is never saved by the System
  (queue_save.system_filled_only): she saves it.

The reader in this process is the only reader there is, so her earlier reading cannot be read again. Which of
her values she typed and which she accepted from the earlier reader cannot be told apart: every value of hers
that differs from the current reading counts as hers, carried, and asked about (fail closed; reread_carry's
'unproven' baseline). Records with no person in them (System-filled details) settle as in reread_carry
(Neil's decision, LOUPE_FINANCIAL_RECOVERY_DETAILS_CARRY): they are kept in history and the reading is prepared
like any other.

Fail closed. The whole file is left exactly as it is (investigator_edits, with the reason recorded) when:
work sits on another reading of the original; two different drafts of one statement exist; a statement of hers
has no single counterpart in the current reading (statement key gone and period/account not matching exactly
one statement, or two of hers on one); a row of hers has no single counterpart; a hand-added row's page is gone
or one of her hand-added payments is now read by the reader (it would count twice); the carried review is not a
valid draft; or the reading the worker prepares is not the one the review was carried onto.

Switch ``LOUPE_FINANCIAL_REPREPARE_CARRY_EDITS`` (default on; needs ``LOUPE_FINANCIAL_AUTO_REPREPARE_HELD``).
Off: investigator work protects the file, as before.
"""
from copy import deepcopy
from datetime import datetime, timezone

from sqlalchemy import select

from postgres.models.evidence import EvidenceFile
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item

REASON = 'held_reprepare'
LOG = 'financial_reprepare_carry_log'
OPEN = ('ready', 'attention')
# Row fields a reader prints: a value of hers that differs is asked about. Other row fields (notes, page of a
# hand-added row, links, placement anchors, extra dates) have no reading to differ from: hers are kept.
ASKED_ROW_FIELDS = ('excluded', 'date', 'description', 'counterparty', 'amount_minor', 'direction', 'balance_minor')
ASKED_DETAILS = ('currency', 'account_number', 'institution', 'holder', 'period_start', 'period_end')
FIXED = ('expected_revision', 'statement_id', 'rows')


class NotCarried(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _now():
    return datetime.now(timezone.utc).isoformat()


def _row(row):
    from services.financial.reread_carry import _row as validated
    return validated(row)


def _digits(value):
    return ''.join(ch for ch in str(value or '') if ch.isdigit())


def _empty(value):
    return value in (None, '', False) or (isinstance(value, (list, dict)) and not value)


def _norm(field, value):
    """A row value as compared: no amount is written '0' or left blank."""
    if field == 'amount_minor' and value in (None, '', '0'):
        return ''
    return value


def _same(field, mine, read):
    from services.financial.review_carry import same_value
    if mine == read:
        return True
    if isinstance(mine, str) and isinstance(read, str) and field in ('holder', 'account_number', 'institution'):
        return same_value(field, mine.strip(), read.strip())
    return False


def read_fresh(session, case_id, reading, currency):
    """{statement key: proposal} the current reader reads, as prepare_reviews reads it."""
    from services.financial.statement_import import read_statement_import
    cache = {}
    first = read_statement_import(session, case_id=case_id, evidence_file_id=reading.id, currency=currency,
                                  _cache=cache)
    keys = [choice['id'] for choice in first.get('statement_choices') or [] if not choice.get('document_kind')]
    if not first.get('statement_choices'):
        keys = [None]
    fresh = {}
    for key in keys:
        proposal = read_statement_import(session, case_id=case_id, evidence_file_id=reading.id,
                                         currency=currency or None, statement_id=key, _cache=cache)
        fresh[key or proposal.get('statement_id') or ''] = proposal
    return fresh


def work(session, case_id, reading):
    """{statement key: [(kind, saved, item)]}: saved progress on the reading, and batch drafts of open items."""
    found = {}
    for key, saved in ((reading.metadata_ or {}).get('financial_review_progress') or {}).items():
        found.setdefault(key or '', []).append(('progress', saved, None))
    for item in session.scalars(select(Item).join(Batch, Batch.id == Item.batch_id).where(
            Batch.case_id == case_id, Batch.status != 'removed', Item.file_id == reading.id,
            Item.review_request.is_not(None)).order_by(Item.id)):
        if not item.review_request:
            continue  # a JSON null stored for 'no draft' (IS NOT NULL does not tell them apart)
        if item.status == 'superseded_reading':
            continue  # history: a draft an earlier preparation already retired
        if item.status not in OPEN:
            raise NotCarried('draft_on_settled_item')
        found.setdefault(item.statement_key or '', []).append(('draft', dict(
            request=item.review_request, saved_by=(item.summary or {}).get('review_saved_by')), item))
    return found


def _effective(entries):
    """Her one request for the statement, or NotCarried('two_drafts')."""
    from services.financial.effective_statement_review import resolve_review
    from services.financial.reread_carry import _digest_request
    progress = next((saved for kind, saved, _ in entries if kind == 'progress'), None)
    drafts = [saved['request'] for kind, saved, _ in entries if kind == 'draft']
    if progress:
        for draft in drafts:
            if resolve_review(draft, progress)[1]:
                raise NotCarried('two_drafts')
        return progress['request'], progress
    if len({_digest_request(draft) for draft in drafts}) != 1:
        raise NotCarried('two_drafts')
    saved = next(saved for kind, saved, _ in entries if kind == 'draft')
    return drafts[0], saved


def _period(request, item):
    summary = (item.summary or {}) if item is not None else {}
    return (str(request.get('period_start') or summary.get('period_start') or ''),
            str(request.get('period_end') or summary.get('period_end') or ''),
            _digits(request.get('account_number') or summary.get('account')))


def match_statement(key, request, item, fresh):
    """The current reading's one statement for her statement ``key``: the same key, else the one statement with
    her period (and account, when both print one). NotCarried otherwise."""
    from services.financial.import_batches import initial_request
    if key in fresh:
        return key
    if not key and len(fresh) == 1:
        return next(iter(fresh))
    start, end, account = _period(request, item)
    if not (start and end):
        raise NotCarried('statement_not_found')
    found = []
    for other_key, proposal in fresh.items():
        read = initial_request(proposal)
        other = _digits(read.get('account_number'))
        if (read.get('period_start'), read.get('period_end')) == (start, end) and (
                not account or not other or other[-6:] == account[-6:]):
            found.append(other_key)
    if len(found) != 1:
        raise NotCarried('statement_not_found' if not found else 'statement_ambiguous')
    return found[0]


def _payment_key(row):
    return (row.get('date') or '', str(row.get('amount_minor') or '0'), row.get('direction'),
            None if str(row.get('amount_minor') or '0') not in ('', '0') else row.get('balance_minor'))


def match_rows(mine, read):
    """Her row id -> the current reading's row id. The same id (the same printed line of this reading) first.
    Then lines printing the same date, amount and direction (balance for a line with no amount), her description
    first telling equal lines apart: a group of her lines is paired, in printed order, with the current reading's
    group only when both hold the same number of lines. NotCarried when a row of hers has no counterpart."""
    ids = {row['id'] for row in read}
    mapping = {row['id']: row['id'] for row in mine if row['id'] in ids}
    taken = set(mapping.values())
    for key_of in (lambda row: (_payment_key(row), row.get('description')), lambda row: (_payment_key(row),)):
        hers, theirs = {}, {}
        for row in mine:
            if row['id'] not in mapping:
                hers.setdefault(key_of(row), []).append(row['id'])
        for row in read:
            if row['id'] not in taken:
                theirs.setdefault(key_of(row), []).append(row['id'])
        for key, group in hers.items():
            if len(theirs.get(key) or ()) == len(group):
                for old, new in zip(group, theirs[key]):
                    mapping[old] = new
                    taken.add(new)
    for row in mine:
        if row['id'] not in mapping:
            found = [other for other in read if other['id'] not in taken and _payment_key(other) == _payment_key(row)]
            raise NotCarried('row_ambiguous' if found else 'row_not_found')
    return mapping


def carry_request(request, proposal):
    """(carried request, audit, detail conflicts, row conflicts): her request rebuilt on the current reading."""
    from services.financial.import_batches import initial_request
    from services.financial.statement_import import StatementReviewDraft
    read = initial_request(proposal)
    carried = deepcopy(read)
    fields, conflicts = [], {}
    for field, value in request.items():
        if field in FIXED or _empty(value):
            continue
        if value != read.get(field):
            carried[field] = deepcopy(value)
            fields.append(field)
            if field in ASKED_DETAILS and not _empty(read.get(field)) and not _same(field, value, read.get(field)):
                conflicts[field] = dict(yours=value, reading=read.get(field))
    mine = [_row(row) for row in request.get('rows') or []]
    manual = [row for row in mine if str(row['id']).startswith('manual:')]
    printed = [row for row in mine if not str(row['id']).startswith('manual:')]
    rows = [_row(row) for row in read['rows']]
    mapping = match_rows(printed, rows)
    by_new = {new: old for old, new in mapping.items()}
    theirs = {row['id']: row for row in printed}
    row_conflicts, changed, extra = [], 0, []
    out = []
    for row in rows:
        old = by_new.get(row['id'])
        if old is None:
            extra.append(row)
            out.append(row)
            continue
        hers = theirs[old]
        # A value of hers: 'excluded' always (both ways are a decision); any other field only when she has one.
        diff = {key: hers[key] for key in hers if key != 'id' and _norm(key, hers.get(key)) != _norm(key, row.get(key))
                and (key == 'excluded' or not _empty(_norm(key, hers.get(key))))}
        if diff:
            changed += 1
            for key, value in diff.items():
                if key in ASKED_ROW_FIELDS:
                    row_conflicts.append(dict(row_id=row['id'], field=key, yours=value, reading=row.get(key)))
            row = {**row, **deepcopy(diff)}
        out.append(row)
    pages = set(proposal.get('page_numbers') or [])
    for row in manual:
        if row.get('manual_page') not in pages:
            raise NotCarried('added_row_page_missing')
        if row['id'] in {other['id'] for other in rows}:
            raise NotCarried('added_row_id_taken')
        if not row.get('excluded') and any(_payment_key(other) == _payment_key(row) and not other.get('excluded')
                                           for other in extra):
            raise NotCarried('added_row_now_read')  # the reader now reads the payment she added: it would count twice
    for row in extra:
        if not row.get('excluded'):
            row_conflicts.append(dict(row_id=row['id'], field='new_line', yours=None,
                                      reading=dict(date=row.get('date'), amount_minor=row.get('amount_minor'),
                                                   direction=row.get('direction'), description=row.get('description'))))
    # A hand-added row goes after the current counterpart of the row she placed it after (or first).
    order = [row['id'] for row in mine]
    for row in manual:
        index = order.index(row['id'])
        previous = next((order[i] for i in range(index - 1, -1, -1) if order[i] in mapping or order[i].startswith('manual:')), None)
        anchor = mapping.get(previous, previous)
        position = 0 if anchor is None else next((i + 1 for i, other in enumerate(out) if other['id'] == anchor), None)
        if position is None:
            raise NotCarried('added_row_place_not_found')
        out.insert(position, row)
    carried['rows'] = out
    try:
        StatementReviewDraft.model_validate(carried)
    except ValueError:
        raise NotCarried('invalid_carried_review')
    audit = dict(baseline='unproven', fields=sorted(fields), rows_changed=changed, rows_matched_by_print=sum(
        1 for old, new in mapping.items() if old != new), added=[row['id'] for row in manual],
        new_lines=sum(1 for row in extra if not row.get('excluded')))
    return carried, audit, conflicts, row_conflicts


def plan(session, case_id, reading, source, currency=None):
    """What carrying her work onto the current reading of ``reading`` does. Read only; raises NotCarried.

    Returns dict(statements={her key: dict(kind 'carried'|'settled'|'current', new_key, request, record, ...)},
    fresh=the current proposals)."""
    from services.financial.import_batches import initial_request
    from services.financial.reread_carry import DETAILS_CARRY, statement_history, system_only
    # Work saved on an earlier reading of the original (its ancestors, the original itself) is not this
    # reading's: unless an engine re-read already carried it here, the file is left as it is.
    from services.financial.review_recovery import saved_ancestor_reviews
    records = saved_ancestor_reviews(session, reading)
    carried_here = set((reading.metadata_ or {}).get('financial_review_carried') or ())
    if any(record['id'] not in carried_here for record in records):
        raise NotCarried('work_on_another_reading')
    if source is not None and source.id != reading.id and not any(
            record['evidence_file_id'] == str(source.id) for record in records) and not (
            (source.metadata_ or {}).get('financial_import_removal')):
        # (An original whose imports were removed, a deliberate fresh start, has withdrawn its drafts: the
        # product's own comparison (review_recovery) no longer offers them either.)
        meta = source.metadata_ or {}
        if meta.get('financial_review_progress') or any(item.review_request for item in session.scalars(
                select(Item).join(Batch, Batch.id == Item.batch_id).where(
                    Batch.case_id == case_id, Batch.status != 'removed', Item.file_id == source.id,
                    Item.review_request.is_not(None)))):
            raise NotCarried('work_on_another_reading')
    found = work(session, case_id, reading)
    if not found:
        return dict(statements={}, fresh={})
    fresh = read_fresh(session, case_id, reading, currency)
    # Statements of this reading saved, queued or decided in any batch: her work on them is never moved.
    decided = {item.statement_key or '' for item in session.scalars(select(Item).join(Batch, Batch.id == Item.batch_id).where(
        Batch.case_id == case_id, Batch.status != 'removed', Item.file_id == reading.id,
        Item.status.notin_(OPEN + ('superseded_reading',))))}
    statements, targets = {}, {}
    meta = reading.metadata_ or {}
    for key, entries in sorted(found.items()):
        if key in decided:
            raise NotCarried('statement_saved_or_decided')
        history = statement_history(meta, key)
        pairs = [(kind, saved) for kind, saved, _ in entries]
        if DETAILS_CARRY and system_only(pairs, history):
            statements[key] = dict(kind='settled', entries=entries)
            continue
        request, saved = _effective(entries)
        item = next((item for _, _, item in entries if item is not None), None)
        new_key = match_statement(key, request, item, fresh)
        if new_key in decided:
            raise NotCarried('statement_saved_or_decided')
        if new_key in targets:
            raise NotCarried('statement_ambiguous')
        targets[new_key] = key
        proposal = fresh[new_key]
        if request.get('expected_revision') == proposal['revision'] and new_key == key:
            statements[key] = dict(kind='current', new_key=key, entries=entries)  # already on this reading
            continue
        if not currency and request.get('currency') and request['currency'] != proposal['currency']:
            # prepare_reviews reads the statement with her saved currency: carry onto that reading.
            from services.financial.statement_import import read_statement_import
            proposal = read_statement_import(session, case_id=case_id, evidence_file_id=reading.id,
                                             currency=request['currency'], statement_id=new_key or None, _cache={})
        carried, audit, conflicts, row_conflicts = carry_request(request, proposal)
        statements[key] = dict(kind='carried', new_key=new_key, entries=entries, request=carried, saved=saved,
                               audit=audit, conflicts=conflicts, row_conflicts=row_conflicts, proposal=proposal,
                               initial=initial_request(proposal))
    for key in statements:
        if statements[key]['kind'] == 'settled' and key in targets and targets[key] != key:
            raise NotCarried('statement_ambiguous')  # a settled record on the statement hers moves onto
    return dict(statements=statements, fresh=fresh)


def carried_record(entry, reading, key):
    from services.financial.effective_statement_review import request_signature
    from services.financial.import_batches import initial_request
    from services.financial.pdf_candidates import _digest
    saved, request = entry['saved'], entry['request']
    record = dict(request=request, review_revision=_digest(request), saved_at=_now(),
                  saved_by=deepcopy(saved.get('saved_by')) or dict(user_id=None, name='Investigator'),
                  carried_by=dict(user_id=None, name='System'),
                  carried_from=dict(evidence_file_id=str(reading.id), statement_id=key,
                                    review_revision=saved.get('review_revision'), saved_at=saved.get('saved_at'),
                                    saved_by=saved.get('saved_by'), reason=REASON, **entry['audit']),
                  initial_request_signature=request_signature(initial_request(entry['proposal'])),
                  superseded_request_signatures=[])
    if entry['conflicts']:
        record['carry_conflicts'] = deepcopy(entry['conflicts'])
    if entry['row_conflicts']:
        record['carry_row_conflicts'] = deepcopy(entry['row_conflicts'])
    return record


def progress_digest(file):
    from services.financial.pdf_candidates import _digest
    return _digest((file.metadata_ or {}).get('financial_review_progress') or {})


def apply(session, *, case_id, batch_id, file, fingerprint):
    """Carry her work onto the reading this batch file prepares. Called by the worker before prepare_reviews.

    Returns 'carried' (done now; committed), 'already' (carried by another batch's preparation of the same
    reading; nothing written) or the reason nothing was carried (nothing written: the caller leaves the file's
    statements exactly as they are)."""
    from uuid import UUID
    from services.financial.reread_carry import work_fingerprint
    from services.financial.statement_import import read_statement_import
    reading_id, source_id = UUID(file['file_id']), UUID(file['source_id'])
    reading = session.scalar(select(EvidenceFile).where(EvidenceFile.id == reading_id, EvidenceFile.case_id == case_id)
                             .with_for_update().execution_options(populate_existing=True))
    source = session.scalar(select(EvidenceFile).where(EvidenceFile.id == source_id, EvidenceFile.case_id == case_id))
    if reading is None:
        return 'unavailable'
    ids = [reading.id] + ([source.id] if source is not None and source.id != reading.id else [])
    current = work_fingerprint(session, case_id, ids)
    if current != fingerprint:
        done = [entry for entry in (reading.metadata_ or {}).get(LOG) or [] if entry.get('fingerprint') == fingerprint]
        if done and done[-1].get('progress_after') == progress_digest(reading):
            return 'already'
        return 'work_changed'
    try:
        result = plan(session, case_id, reading, source, file.get('currency'))
    except NotCarried as error:
        return error.reason
    statements = result['statements']
    if not any(entry['kind'] != 'current' for entry in statements.values()):
        return 'nothing_to_carry'
    metadata = deepcopy(reading.metadata_ or {})
    progress = metadata.setdefault('financial_review_progress', {})
    history = metadata.setdefault('financial_review_history', [])
    log_entry = dict(at=_now(), batch_id=str(batch_id), fingerprint=fingerprint, statements={})
    moved = {}
    for key, entry in sorted(statements.items()):
        if entry['kind'] == 'current':
            continue
        original = deepcopy(progress.get(key)) if key in progress else None
        drafts = {str(item.id): deepcopy(item.review_request) for _, _, item in entry['entries'] if item is not None}
        if original is not None:
            history.append(original)
            del progress[key]
        record_log = dict(kind=entry['kind'], original_progress=original, original_drafts=drafts)
        if entry['kind'] == 'carried':
            new_key = entry['new_key']
            progress[new_key] = carried_record(entry, reading, key)
            moved[key] = new_key
            record_log.update(new_statement_id=new_key, conflicts=len(entry['conflicts']) + len(entry['row_conflicts']),
                              **{k: entry['audit'][k] for k in ('fields', 'rows_changed', 'added', 'new_lines')})
        log_entry['statements'][key] = record_log
    reading.metadata_ = metadata
    # Batch drafts follow: a draft of a statement whose key moved stays on its item, retired to history; a draft
    # of the same key becomes the carried review (its earlier value kept on the item).
    carried_requests = {entry['new_key']: entry['request'] for entry in statements.values() if entry['kind'] == 'carried'}
    for item in session.scalars(select(Item).join(Batch, Batch.id == Item.batch_id).where(
            Batch.case_id == case_id, Batch.status != 'removed', Item.file_id == reading.id,
            Item.status.in_(OPEN)).with_for_update(of=Item)):
        key = item.statement_key or ''
        entry = statements.get(key)
        if entry is not None and entry['kind'] == 'settled' and item.review_request:
            item.summary = {**item.summary, 'review_upgrade_history': [*item.summary.get('review_upgrade_history', []),
                dict(request=item.review_request, at=_now(), reason='held_reprepare_settled')]}
            item.review_request = None
        elif key in moved and moved[key] != key:
            item.status = 'superseded_reading'
            item.summary = {**item.summary, 'can_import': False, 'superseded_by_reading': str(reading.id),
                            'carried_to_statement': moved[key], 'recovery_message': MOVED_MESSAGE}
        elif key in carried_requests and item.review_request != carried_requests[key]:
            if item.review_request:
                item.summary = {**item.summary, 'review_upgrade_history': [*item.summary.get('review_upgrade_history', []),
                    dict(request=item.review_request, at=_now(), reason='held_reprepare_carry')]}
            item.review_request = deepcopy(carried_requests[key])
    session.flush()
    # The worker's own reading of each carried statement must be the one the review was carried onto.
    for entry in statements.values():
        if entry['kind'] != 'carried':
            continue
        proposal = read_statement_import(session, case_id=case_id, evidence_file_id=reading.id,
                                         currency=file.get('currency') or None, statement_id=entry['new_key'] or None,
                                         _cache={})
        if proposal['revision'] != entry['request']['expected_revision']:
            session.rollback()
            return 'reading_moved'
    metadata = deepcopy(reading.metadata_)
    log_entry['progress_after'] = progress_digest(reading)
    metadata.setdefault(LOG, []).append(log_entry)
    reading.metadata_ = metadata
    session.commit()
    return 'carried'


MOVED_MESSAGE = ('The current reader names this statement differently. Your saved work was carried onto it; '
                 'this earlier preparation is kept in history.')


def measure(session, case_id, reading, source, currency=None):
    """Read only (dry run): (outcome, [per statement: kind, conflicts, status after carrying])."""
    from services.financial.import_batches import assess
    try:
        result = plan(session, case_id, reading, source, currency)
    except NotCarried as error:
        return error.reason, []
    rows = []
    for key, entry in result['statements'].items():
        if entry['kind'] != 'carried':
            rows.append(dict(kind=entry['kind']))
            continue
        record = carried_record(entry, reading, key)
        proposal = {**entry['proposal'], 'saved_review': record}
        status, summary = assess(proposal, entry['request'])
        rows.append(dict(kind='carried', status=status, can_import=summary.get('can_import'),
                         conflicts=len(entry['conflicts']), row_conflicts=len(entry['row_conflicts']),
                         new_lines=entry['audit']['new_lines'], moved=entry['new_key'] != key,
                         problems=[p.get('kind') or 'check' for p in summary.get('problems') or []]))
    return 'carried' if result['statements'] else 'nothing_to_carry', rows
