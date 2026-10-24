"""Carry an investigator's saved work onto a fresh engine reading of the same original.

The engine-release re-read (recovery_readers) reads a held statement again with the current engine. When an
investigator has saved work on the earlier reading (saved progress or a batch review draft), that work is
carried onto the new reading, unchanged:

* every statement detail she changed keeps her value (her value wins over the new reading);
* every payment row she changed is found in the new reading by what the earlier reading printed for it
  (page, date, amount, direction; the description only to tell equal rows apart). Each field she changed
  keeps her value; fields she did not touch take the new reading's value;
* every row she added by hand is kept, after the row she placed it after;
* confirmations bound to the earlier reading (balance exception, no activity, coverage) are carried
  unchanged: they name the earlier reading's revision, so they apply to the new one only if a person
  confirms again (fail closed).

Rows she did not touch, and rows the new reading finds that the earlier one did not, come from the new
reading. When her draft was saved on an earlier parse that today's reader no longer reproduces, every value of hers
that differs from today's parse counts as hers (baseline 'unproven', recorded): none of her work is lost.
Nothing is carried, and the statement stays held with the reason recorded, when her rows are not today's
rows of the earlier reading (rows_not_aligned), a statement or an edited row has
no single counterpart in the new reading, a hand-added row's page does not exist in it, or two different
drafts of the same statement exist. Her original work stays on the earlier reading (history); the carried
record names it (carried_from), so the audit trail shows both.

Neil's decision (2026-10-24), switch LOUPE_FINANCIAL_RECOVERY_DETAILS_CARRY:

* a statement whose every saved record is System's (details System filled, no person in its history) has no
  edits to keep: it is settled, not held, and the new reading is prepared like any other (basis 'no edits to
  keep');
* a statement whose person work is statement details only (no hand-added row, no row or statement note, no
  confirmation, rows not changed between her saves) and whose rows cannot be lined up row by row is carried
  as details: her detail values are set exactly on the new reading, its rows are the new reading's, and only
  when every payment of hers (date, amount, direction; excluded ones as excluded) has its own counterpart in
  the new reading. Extra payments of the new reading are counted on the item and still pass every normal
  readiness check. Basis 'details carried, payments matched'; it may then be saved automatically;
* file-level work of that kind on a file the new reading splits into periods is carried per period: a period
  is released when her payments dated in it match one to one, the account and currency it prints agree with
  hers, and nothing was imported from her reading for an overlapping period. Other periods stay held.

Her original records are never changed; the carry log names them (carried_from).

Pure functions here; the batch hook is ``carry_reread_work``.
"""
from collections import Counter
import os
from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID

DETAIL_FIELDS = ('currency', 'account_number', 'institution', 'holder', 'period_start', 'period_start_unprinted',
                 'period_end', 'details_reason', 'balance_exception_reason', 'balance_exception_revision',
                 'no_activity_confirmed', 'no_activity_revision', 'coverage_review_reason', 'coverage_review_revision',
                 'replaces_source_document_id', 'replacement_revision')
ROW_FIELDS = ('excluded', 'manual_page', 'date', 'date_unprinted', 'date_values', 'description', 'counterparty',
              'counterparty_link', 'source_order_anchor', 'amount_minor', 'direction', 'balance_minor', 'reason')
CARRIED_BY = dict(user_id=None, name='System')

# Neil's decision (2026-10-24): statements carrying investigator edits are re-read, keeping the edits.
# Off: recovery leaves them unchanged, as before.
CARRY_EDITS = os.environ.get('LOUPE_FINANCIAL_RECOVERY_CARRY_EDITS', '1').strip().lower() not in (
    '0', 'false', 'no', 'off')
# Neil's decision (2026-10-24): System-only records settle; details-only work is carried with a payment match.
# Off: such statements stay held, as before.
DETAILS_CARRY = os.environ.get('LOUPE_FINANCIAL_RECOVERY_DETAILS_CARRY', '1').strip().lower() not in (
    '0', 'false', 'no', 'off')
DETAILS_MATCHED = 'details carried, payments matched'
NO_EDITS = 'no edits to keep'
# Details she can set on a statement that carry as they are. Period dates only for a named statement.
CARRIED_DETAILS = ('currency', 'account_number', 'institution', 'holder')
PERIOD_DETAILS = ('period_start', 'period_start_unprinted', 'period_end')
NOTES = ('details_reason', 'balance_exception_reason', 'coverage_review_reason')
CONFIRMATIONS = ('balance_exception_revision', 'no_activity_confirmed', 'no_activity_revision',
                 'coverage_review_revision', 'replaces_source_document_id', 'replacement_revision')
# Row by row carrying failed only because her rows do not line up with the earlier reading as read today.
ROWS_UNALIGNED = ('rows_not_aligned', 'rows_missing', 'row_not_found', 'row_ambiguous', 'no_saved_rows')


class NotCarried(Exception):
    """The saved work cannot be carried; ``reason`` is recorded on the held statement."""

    def __init__(self, reason, periods=None):
        super().__init__(reason)
        self.reason = reason
        self.periods = periods


def _row(row):
    from services.financial.statement_import import DraftImportRow
    return DraftImportRow.model_validate(row).model_dump(mode='json')


def _digits(value):
    return ''.join(ch for ch in str(value or '') if ch.isdigit())


def baseline(old_proposal, request):
    """(her request on the earlier reading's current row ids, the earlier reading as read). Raises NotCarried."""
    from services.financial.import_batches import initial_request
    from services.financial.review_upgrade import upgrade_request
    if not request or not request.get('rows'):
        raise NotCarried('no_saved_rows')
    initial = initial_request(old_proposal)
    if request.get('expected_revision') == old_proposal['revision']:
        return request, initial, 'exact'
    upgraded = upgrade_request(request, old_proposal)
    if upgraded:
        return upgraded, initial, 'exact'
    # Saved on an earlier parse of this reading that today's reader no longer reproduces: which values she
    # typed and which that reader printed cannot be told apart. Every value of hers that differs from today's
    # parse is treated as hers, so none of her work is lost (it may also carry a value she only accepted).
    # Only when her rows are today's rows; otherwise nothing lines up.
    read = {row['id'] for row in initial['rows']}
    mine = {row['id'] for row in request['rows'] if not str(row['id']).startswith('manual:')}
    if read != mine:
        raise NotCarried('rows_not_aligned')
    return request, initial, 'unproven'


def edits(old_proposal, request):
    """What she changed: (detail fields, {row id: changed fields}, hand-added rows with predecessor, baseline)."""
    request, initial, basis = baseline(old_proposal, request)
    fields = {field: request.get(field) for field in DETAIL_FIELDS
              if request.get(field) not in (None, '', False) and request.get(field) != initial.get(field)}
    read = {row['id']: _row(row) for row in initial['rows']}
    changed, added, previous = {}, [], None
    mine = [_row(row) for row in request['rows']]
    if not set(read) <= {row['id'] for row in mine}:
        raise NotCarried('rows_missing')
    for row in mine:
        if row['id'] not in read:
            added.append((previous, row))
        else:
            diff = {key: row[key] for key in ROW_FIELDS if key in row and row.get(key) != read[row['id']].get(key)}
            if diff:
                changed[row['id']] = diff
        previous = row['id']
    return fields, changed, added, basis


def _printed(proposal):
    """Row id -> (page, date, amount, direction) and description, as the reader printed them."""
    from services.financial.import_batches import initial_request
    pages = {row['id']: row.get('page_number') for row in proposal['rows']}
    out = {}
    for row in initial_request(proposal)['rows']:
        out[row['id']] = ((pages.get(row['id']), row['date'], row['amount_minor'], row['direction']),
                          row['description'])
    return out


def match_rows(old_proposal, new_proposal, wanted):
    """Old row id -> new row id for each wanted id: one counterpart each, or NotCarried."""
    old, new = _printed(old_proposal), _printed(new_proposal)
    taken, result = set(), {}
    for old_id in wanted:
        if old_id not in old:
            raise NotCarried('row_not_found')
        key, description = old[old_id]
        found = [new_id for new_id, (other, _) in new.items() if other == key and new_id not in taken]
        if len(found) > 1:
            found = [new_id for new_id in found if new[new_id][1] == description]
        if len(found) != 1:
            raise NotCarried('row_not_found' if not found else 'row_ambiguous')
        result[old_id] = found[0]
        taken.add(found[0])
    return result


def _period(proposal, request=None):
    metadata = proposal.get('metadata') or {}
    dates = proposal.get('period_dates') or {}
    request = request or {}
    return ((metadata.get('period_start') or dates.get('period_start') or request.get('period_start') or ''),
            (metadata.get('period_end') or dates.get('period_end') or request.get('period_end') or ''),
            _digits(metadata.get('account_number') or request.get('account_number')))


def match_statement(old_proposal, request, new_proposals):
    """The new reading's one statement (by id) for the earlier one's account and period, or NotCarried."""
    start, end, account = _period(old_proposal, request)
    found = []
    for statement_id, proposal in new_proposals.items():
        other_start, other_end, other = _period(proposal)
        if (other_start, other_end) == (start, end) and (not account or not other or other[-6:] == account[-6:]):
            found.append(statement_id)
    if len(found) != 1:
        raise NotCarried('statement_not_found' if not found else 'statement_ambiguous')
    return found[0]


def carry(old_proposal, request, new_proposal):
    """Her request rebuilt on the new reading, and the audit of what was carried. Raises NotCarried."""
    from services.financial.import_batches import initial_request
    fields, changed, added, basis = edits(old_proposal, request)
    mapping = match_rows(old_proposal, new_proposal, list(changed))
    pages = set(new_proposal.get('page_numbers') or [])
    if any(row.get('manual_page') not in pages for _, row in added):
        raise NotCarried('added_row_page_missing')
    carried = initial_request(new_proposal)
    new_ids = {row['id'] for row in carried['rows']}
    if any(row['id'] in new_ids for _, row in added):
        raise NotCarried('added_row_id_taken')
    carried.update(fields)
    rows = []
    for row in carried['rows']:
        row = _row(row)
        old_id = next((old for old, new in mapping.items() if new == row['id']), None)
        if old_id is not None:
            row.update(changed[old_id])
        rows.append(row)
    # A hand-added row goes after the new counterpart of the row she placed it after (or first).
    if added:
        added_ids = {row['id'] for _, row in added}
        anchors = {previous for previous, _ in added if previous is not None and previous not in added_ids}
        unmapped = [anchor for anchor in anchors if anchor not in mapping]
        located = {**mapping, **(match_rows(old_proposal, new_proposal, unmapped) if unmapped else {})}
        if len(set(located.values())) != len(located):
            raise NotCarried('added_row_place_not_found')
        after = {}
        for previous, row in added:
            after.setdefault(previous if previous is None or previous in added_ids else located[previous], []).append(row)

        def emit(anchor, out):
            for extra in after.pop(anchor, []):
                out.append(extra)
                emit(extra['id'], out)
        ordered = []
        emit(None, ordered)
        for row in rows:
            ordered.append(row)
            emit(row['id'], ordered)
        if after:
            raise NotCarried('added_row_place_not_found')
        rows = ordered
    carried['rows'] = rows
    audit = dict(baseline=basis, fields=sorted(fields), rows=[dict(earlier=old, new=new, fields=sorted(changed[old]))
                                               for old, new in mapping.items()],
                 added=[row['id'] for _, row in added])
    return carried, audit


def carried_record(carried, saved, audit, earlier_file_id, earlier_key, new_proposal):
    """The saved-progress record of the new reading: her work, carried by System, naming its origin."""
    from services.financial.effective_statement_review import request_signature
    from services.financial.import_batches import initial_request
    from services.financial.pdf_candidates import _digest
    return dict(request=carried, review_revision=_digest(carried), saved_at=datetime.now(timezone.utc).isoformat(),
        # Her work: never System's, so it is never saved without a person (queue_save.system_filled_only).
        saved_by=deepcopy(saved.get('saved_by')) or dict(user_id=None, name='Investigator'),
        carried_by=CARRIED_BY,
        carried_from=dict(evidence_file_id=str(earlier_file_id), statement_id=earlier_key,
                          review_revision=saved.get('review_revision'), saved_at=saved.get('saved_at'),
                          saved_by=saved.get('saved_by'), reason='engine_reread', **audit),
        initial_request_signature=request_signature(initial_request(new_proposal)), superseded_request_signatures=[])


def system_only(entries, history):
    """True when every saved record of the statement is System's and no person appears in its history.

    ``entries`` are (kind, saved) pairs; ``history`` the saved_by/actor names of every earlier save and every
    audited detail change of this statement on the file. A System fill builds on whatever was stored, so any
    person in the history means the record may hold her work."""
    from services.financial.field_proposals import SYSTEM_NAME
    system = {_digest_request(saved.get('request')) for _, saved in entries
              if (saved.get('saved_by') or {}).get('name') == SYSTEM_NAME}
    # A batch draft records no saver when a details save copied its request there: it is that save's.
    names = [SYSTEM_NAME if kind == 'draft' and not saved.get('saved_by') and _digest_request(saved.get('request')) in system
             else (saved.get('saved_by') or {}).get('name') for kind, saved in entries] + list(history)
    if not entries or any(name != SYSTEM_NAME for name in names):
        return False
    for _, saved in entries:
        request = saved.get('request') or {}
        if any(str(row.get('id', '')).startswith('manual:') or str(row.get('reason') or '').strip()
               for row in request.get('rows') or []):
            return False
        if any(str(request.get(field) or '').strip() for field in NOTES):
            return False
    return True


def details_only(request, earlier_saves=()):
    """Raise NotCarried unless her saved work on this statement is statement details only.

    ``earlier_saves`` are her earlier requests on the same statement and reading revision: rows that differ
    between her own saves are row work."""
    rows = [_row(row) for row in request.get('rows') or []]
    if any(str(row['id']).startswith('manual:') for row in rows):
        raise NotCarried('hand_added_rows')
    if any((row.get('reason') or '').strip() for row in rows):
        raise NotCarried('row_notes')
    if any(str(request.get(field) or '').strip() for field in NOTES):
        raise NotCarried('statement_notes')
    if any(request.get(field) not in (None, '', False) for field in CONFIRMATIONS):
        raise NotCarried('confirmations')
    mine = {row['id']: {key: row.get(key) for key in ROW_FIELDS} for row in rows}
    for earlier in earlier_saves:
        if earlier.get('expected_revision') != request.get('expected_revision'):
            continue
        theirs = {row['id']: {key: row.get(key) for key in ROW_FIELDS} for row in map(_row, earlier.get('rows') or [])}
        if theirs != mine:
            raise NotCarried('rows_changed_between_saves')


def _row_day(row):
    values = row.get('date_values') or {}
    return str(row.get('date') or values.get('date') or values.get('booking_date') or values.get('value_date') or '')[:10]


def _amount(row):
    try:
        return int(str(row.get('amount_minor') or '0'))
    except ValueError:
        return None


def payments(rows):
    """(included, excluded) multisets of (date, amount, direction) of rows that carry an amount. NotCarried
    when a row with an amount has no date or an unreadable amount: it cannot be matched."""
    included, excluded = Counter(), Counter()
    for row in map(_row, rows):
        amount = _amount(row)
        if amount is None:
            raise NotCarried('unreadable_amount')
        if amount == 0:
            continue  # A header or balance line: no payment.
        day = _row_day(row)
        if not day:
            raise NotCarried('undated_payment')
        (excluded if row.get('excluded') else included)[(day, amount, row.get('direction'))] += 1
    return included, excluded


def match_payments(mine, new_rows):
    """Extra payments of the new reading when every payment of hers has its own counterpart there (an
    excluded one an excluded counterpart), else NotCarried('payments_differ')."""
    her_in, her_out = mine
    new_in, new_out = payments(new_rows)
    if her_in - new_in or her_out - new_out:
        raise NotCarried('payments_differ')
    return sum((new_in - her_in).values())


def _in(day, start, end):
    return bool(start and end and start <= day <= end)


def carry_details(request, new_proposal, *, rows=None, with_period=True):
    """Her detail values set exactly on the new reading, its own rows, after the payment match. Returns
    (request, audit). ``rows`` are her rows to match (default: all of hers)."""
    from services.financial.import_batches import initial_request
    carried = initial_request(new_proposal)
    extra = match_payments(payments(request.get('rows') or [] if rows is None else rows), carried['rows'])
    fields = CARRIED_DETAILS + (PERIOD_DETAILS if with_period else ())
    values = {field: request.get(field) for field in fields if request.get(field) not in (None, '', False)}
    carried.update(values)
    matched = sum(payments(request.get('rows') or [] if rows is None else rows)[0].values())
    return carried, dict(baseline='details', basis=DETAILS_MATCHED, fields=sorted(values), rows=[], added=[],
                         payments_matched=matched, extra_rows=extra)


def plan_statement(key, entries, old_proposal, new_proposals, *, other_batch=False, history=(), earlier_saves=(),
                   imported_spans=(), taken=()):
    """What to do with one earlier statement's saved work. Pure. Returns a dict:

    kind 'settled' (no edits to keep), 'carried' (row by row, as before), 'details' (one statement, details
    carried), 'periods' (file-level details carried onto several periods; ``held_periods`` the others), or
    'held' with ``reason``. ``carried`` maps a new statement id to (request, audit)."""
    if DETAILS_CARRY and system_only(entries, history):
        return dict(kind='settled', basis=NO_EDITS, carried={})
    try:
        if other_batch:
            raise NotCarried('work_in_another_batch')
        if len({_digest_request(saved['request']) for _, saved in entries}) != 1:
            raise NotCarried('two_drafts')
        saved = next((s for k, s in entries if k == 'progress'), entries[0][1])
        request = saved['request']
        try:
            new_key = match_statement(old_proposal, request, new_proposals)
            if new_key in taken:
                raise NotCarried('new_reading_has_review')
            carried, audit = carry(old_proposal, request, new_proposals[new_key])
            return dict(kind='carried', carried={new_key: (carried, audit)}, saved=saved)
        except NotCarried as error:
            reason = error.reason
            if not DETAILS_CARRY or reason not in ROWS_UNALIGNED + ('statement_not_found', 'statement_ambiguous'):
                raise
            details_only(request, earlier_saves)
            if reason not in ('statement_not_found', 'statement_ambiguous'):
                if new_key in taken:
                    raise NotCarried('new_reading_has_review')
                _no_overlap(new_proposals[new_key], imported_spans)
                return dict(kind='details', carried={new_key: carry_details(request, new_proposals[new_key])}, saved=saved)
            if key:
                raise  # A named statement with no single counterpart stays held.
            return dict(kind='periods', saved=saved, **_periods(request, old_proposal, new_proposals, imported_spans, taken))
    except NotCarried as error:
        return dict(kind='held', reason=error.reason, carried={}, **({'held_periods': error.periods}
                                                                    if error.periods else {}))


def _no_overlap(proposal, spans):
    start, end, _ = _period(proposal)
    if not (start and end):
        raise NotCarried('period_unknown')
    if any(str(a) <= end and start <= str(b) for a, b in spans):
        raise NotCarried('overlaps_imported_period')


def _periods(request, old_proposal, new_proposals, spans, taken):
    """File-level details work carried onto each period of the new reading it can be proven for."""
    from services.financial.import_batches import initial_request
    initial = initial_request(old_proposal)
    if any(request.get(field) not in (None, '', False) and request.get(field) != initial.get(field)
           for field in PERIOD_DETAILS):
        raise NotCarried('period_set_on_file')
    rows = [_row(row) for row in request.get('rows') or []]
    payments(rows)  # every payment of hers must be dated
    account = _digits(request.get('account_number'))
    currency = request.get('currency') or ''
    carried, held, placed = {}, {}, set()
    for new_key, proposal in sorted(new_proposals.items()):
        start, end, printed = _period(proposal)
        mine = [row for row in rows if _in(_row_day(row), start, end)]
        placed |= {id(row) for row in mine}
        try:
            if new_key in taken:
                raise NotCarried('new_reading_has_review')
            if account and printed and printed[-6:] != account[-6:]:
                raise NotCarried('account_differs')
            other = (proposal.get('metadata') or {}).get('currency') or initial_request(proposal).get('currency')
            if currency and other and other != currency:
                raise NotCarried('currency_differs')
            _no_overlap(proposal, spans)
            carried[new_key] = carry_details(request, proposal, rows=mine, with_period=False)
        except NotCarried as error:
            held[new_key] = error.reason
    unplaced = sum(1 for row in rows if id(row) not in placed and (_amount(row) or 0) != 0)
    if not carried:
        raise NotCarried('no_period_proven' if held else 'statement_not_found', periods=held)
    return dict(carried=carried, held_periods=held, unplaced_payments=unplaced,
                complete=not held and not unplaced)


def work_fingerprint(session, case_id, file_ids):
    """Digest of every saved review and batch draft on these files: recorded when a re-read is scheduled, so a
    review saved after that is never carried unseen (the batch's own guard refuses then, as before)."""
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial_import_batches import FinancialImportBatch, FinancialImportBatchItem
    from services.financial.pdf_candidates import _digest
    ids = sorted({str(value) for value in file_ids})
    progress = {str(file.id): (file.metadata_ or {}).get('financial_review_progress') or {}
                for file in session.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id,
                                                                        EvidenceFile.id.in_([UUID(i) for i in ids])))}
    drafts = sorted((str(item.id), _digest(item.review_request)) for item in session.scalars(
        select(FinancialImportBatchItem).join(FinancialImportBatch,
            FinancialImportBatch.id == FinancialImportBatchItem.batch_id).where(
            FinancialImportBatch.case_id == case_id, FinancialImportBatch.status != 'removed',
            FinancialImportBatchItem.file_id.in_([UUID(i) for i in ids]),
            FinancialImportBatchItem.review_request.is_not(None))))
    return _digest(dict(progress=progress, drafts=drafts))


def carry_reread_work(session, *, case_id, batch_id, prior_id, new_id):
    """Carry the saved work of the earlier reading ``prior_id`` onto the fresh reading ``new_id``. Commits nothing.

    Returns {earlier statement key: dict(carried=bool, new_statement_id, reason)}. Each statement is carried or
    left on its own: one that cannot be carried keeps its earlier item and work as they are, and its new
    period stays held by the existing comparison step (review_recovery), with the reason recorded.
    """
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial_import_batches import FinancialImportBatch, FinancialImportBatchItem as Item
    from services.financial.review_recovery import saved_ancestor_reviews
    from services.financial.statement_import import read_statement_import
    prior = session.scalar(select(EvidenceFile).where(EvidenceFile.id == prior_id, EvidenceFile.case_id == case_id))
    new = session.scalar(select(EvidenceFile).where(EvidenceFile.id == new_id, EvidenceFile.case_id == case_id)
                         .with_for_update())
    if prior is None or new is None:
        return {}
    items = list(session.scalars(select(Item).join(FinancialImportBatch, FinancialImportBatch.id == Item.batch_id).where(
        FinancialImportBatch.case_id == case_id, FinancialImportBatch.status != 'removed', Item.file_id == prior.id)))
    work = {}
    for key, saved in ((prior.metadata_ or {}).get('financial_review_progress') or {}).items():
        work.setdefault(key or '', []).append(('progress', saved, None))
    for item in items:
        if item.review_request:
            work.setdefault(item.statement_key or '', []).append(('draft', dict(request=item.review_request,
                saved_at=item.updated_at.isoformat() if item.updated_at else None,
                saved_by=(item.summary or {}).get('review_saved_by')), item))
    if not work:
        return {}
    cache, new_proposals = {}, {}
    first = read_statement_import(session, case_id=case_id, evidence_file_id=new.id, _cache=cache)
    for choice in first.get('statement_choices') or []:
        if choice.get('document_kind'):
            continue  # Not a statement: nothing of hers is carried onto it.
        new_proposals[choice['id']] = read_statement_import(session, case_id=case_id, evidence_file_id=new.id,
            statement_id=choice['id'], _cache=cache)
    if not new_proposals and first.get('rows') is not None:
        new_proposals[first.get('statement_id') or ''] = first  # one unnamed statement
    metadata = deepcopy(new.metadata_ or {})
    progress = metadata.setdefault('financial_review_progress', {})
    records = saved_ancestor_reviews(session, new)
    prior_meta = prior.metadata_ or {}
    spans = imported_spans(session, case_id, prior.id)
    released = deepcopy(metadata.get('financial_review_details_release') or {})
    outcome, carried_records, taken = {}, list(metadata.get('financial_review_carried') or []), set(progress)
    for key, entries in sorted(work.items()):
        own = [record['id'] for record in records
               if record['evidence_file_id'] == str(prior.id) and (record['statement_id'] or '') == key]
        history = statement_history(prior_meta, key)
        earlier = [saved.get('request') or {} for saved in prior_meta.get('financial_review_history') or []
                   if ((saved.get('request') or {}).get('statement_id') or '') == key]
        item = next((item for _, _, item in entries if item is not None), None)
        currency = (item.summary or {}).get('currency') if item is not None else None
        old_proposal = None
        try:
            old_proposal = read_statement_import(session, case_id=case_id, evidence_file_id=prior.id,
                statement_id=key or None, currency=currency or None, _cache={})
        except Exception:
            old_proposal = None
        plan = (plan_statement(key, [(kind, saved) for kind, saved, _ in entries], old_proposal, new_proposals,
                    other_batch=any(item is not None and item.batch_id != batch_id for _, _, item in entries),
                    history=history, earlier_saves=earlier, imported_spans=spans, taken=taken)
                if old_proposal is not None else
                (dict(kind='settled', basis=NO_EDITS, carried={})
                 if DETAILS_CARRY and system_only([(k, s) for k, s, _ in entries], history)
                 else dict(kind='held', reason='earlier_reading_unavailable', carried={})))
        if plan['kind'] == 'held':
            outcome[key] = dict(carried=False, new_statement_id=None, reason=plan['reason'],
                                **({'held_periods': plan['held_periods']} if plan.get('held_periods') else {}))
            continue
        if plan['kind'] == 'settled':
            carried_records += own
            outcome[key] = dict(carried=True, new_statement_id=None, reason=None, baseline=None, basis=NO_EDITS)
            continue
        saved = plan['saved']
        for new_key, (request, audit) in plan['carried'].items():
            progress[new_key] = carried_record(request, saved, audit, prior.id, key, new_proposals[new_key])
            taken.add(new_key)
        periods = {new_key: dict(basis=audit.get('basis'), extra_rows=audit.get('extra_rows'),
                                 payments_matched=audit.get('payments_matched'))
                   for new_key, (_, audit) in plan['carried'].items()}
        if plan['kind'] == 'periods' and not plan['complete']:
            # Some periods stay held: her records stay unresolved, the released periods are named.
            for record_id in own:
                released[record_id] = sorted(set(released.get(record_id) or ()) | set(plan['carried']))
            outcome[key] = dict(carried=False, new_statement_id=None, reason='periods_held', basis=DETAILS_MATCHED,
                                released=periods, held_periods=plan['held_periods'],
                                unplaced_payments=plan['unplaced_payments'])
            continue
        carried_records += own
        first = next(iter(plan['carried']))
        audit = plan['carried'][first][1]
        outcome[key] = dict(carried=True, new_statement_id=first if len(plan['carried']) == 1 else None, reason=None,
                            baseline=audit['baseline'], **({'basis': audit['basis'], 'released': periods}
                                                           if audit.get('basis') else {}))
    now = datetime.now(timezone.utc).isoformat()
    metadata['financial_review_carried'] = sorted(set(carried_records))
    if released:
        metadata['financial_review_details_release'] = released
    metadata.setdefault('financial_reread_carry_log', []).append(dict(at=now, earlier_file_id=str(prior.id),
        batch_id=str(batch_id), statements=outcome))
    new.metadata_ = metadata
    return outcome


def statement_history(metadata, key):
    """Names of everyone who saved or changed details of this statement on the file: earlier saves (history)
    and audited detail changes."""
    names = [((saved.get('saved_by') or {}).get('name')) for saved in metadata.get('financial_review_history') or []
             if ((saved.get('request') or {}).get('statement_id') or '') == key]
    names += [((entry.get('actor') or {}).get('name')) for entry in metadata.get('financial_account_detail_history') or []
              if (entry.get('statement_id') or '') == key]
    return names


def imported_spans(session, case_id, file_id):
    """(start, end) of every period imported from this reading: a released period must not overlap one."""
    from sqlalchemy import select
    from postgres.models.financial import FinancialSourceDocument, FinancialStatementPeriod
    spans = []
    for source in session.scalars(select(FinancialSourceDocument).where(
            FinancialSourceDocument.case_id == case_id, FinancialSourceDocument.evidence_file_id == file_id)):
        for period in session.scalars(select(FinancialStatementPeriod).where(
                FinancialStatementPeriod.source_document_id == source.id)):
            spans.append((str(period.period_start or '0000-00-00'), str(period.period_end or '9999-12-31')))
    return spans


def _digest_request(request):
    from services.financial.pdf_candidates import _digest
    return _digest(request)
