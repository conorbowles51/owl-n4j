"""Decide which completed retained statement records may enter Transactions.

A corrected printed row or an investigator-added row enters Transactions as
soon as the statement is proven to reconcile with it, without waiting for
every other retained record. The proof is the ordinary saved-statement
admission check (``assess_saved_additions``) run on a candidate set:

* corrected printed rows are the statement's own printed lines and are tested
  together as the base (each alone would leave the printed lines incomplete);
* each investigator addition is tested on its own on top of that base;
* an addition that matches an existing row (same amount and direction, and
  the same date, or the same description within a few days) is held as a
  likely repeat and never tested;
* anything ambiguous fails closed: additions that only reconcile together,
  or several additions that could each be the missing line, stay held;
* when the corrected printed rows do not prove together, each one that
  proves on its own (and together with the others that do) still enters,
  so one wrong correction does not hold back a right one;
* a statement "proves" when it reconciles, or when the only open checks are
  other printed rows still missing a date, description or name whose amount
  and direction are known (the arithmetic is then complete and exact);
* withdrawn records (``withdrawn`` on the retained record) take no part.

``INDIVIDUAL_ADMISSION = False`` restores the earlier rule (every completed
record together, only once the whole statement reconciles).
"""
from datetime import date, timedelta

INDIVIDUAL_ADMISSION = True

REPEAT_REASON = 'Looks like a repeat of an existing row ({}). Compare it with the PDF; it stays outside totals.'
NO_FIT_REASON = "The statement doesn't add up with this row. It stays outside totals until the statement reconciles."
PAIR_REASON = ('This row only adds up together with another added row. Check both against the PDF; '
               'they stay outside totals.')
AMBIGUOUS_REASON = ('More than one added row could be the missing line. Check which belongs to this statement; '
                    'they stay outside totals.')
BASE_REASON = "The statement doesn't add up with the corrected printed rows. They stay outside totals until it reconciles."
REPEAT_DAYS = 3


def _day(value):
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def _text(value):
    return ' '.join(str(value or '').lower().split())


def _signature(fields):
    direction = fields.get('direction')
    direction = getattr(direction, 'value', direction)
    return (str(fields.get('amount_minor') or ''), str(direction or ''), _day(fields.get('date')),
            _text(fields.get('description')))


def _repeat(candidate, existing):
    """The first existing row this candidate repeats, as ``(label, detail)``."""
    amount, direction, day, text = _signature(candidate)
    for label, other, detail in existing:
        o_amount, o_direction, o_day, o_text = _signature(other)
        if not amount or (amount, direction) != (o_amount, o_direction):
            continue
        if day and day == o_day:
            return label, detail
        if text and text == o_text and day and o_day and abs(day - o_day) <= timedelta(days=REPEAT_DAYS):
            return label, detail
    return None


def _transaction_fields(row):
    day = row.transaction_date or row.posted_date or row.value_date or row.effective_date
    return dict(amount_minor=str(row.amount_minor), direction=row.direction,
                date=day.isoformat() if day else '', description=row.description)


def _detail(kind, fields, **ids):
    """What the investigator is shown about the row a repeat matches."""
    direction = fields.get('direction')
    return dict(kind=kind, date=str(fields.get('date') or '')[:10] or None,
                amount_minor=str(fields.get('amount_minor') or ''), direction=getattr(direction, 'value', direction),
                description=fields.get('description') or '', **ids)


# Missing values on other printed rows that do not enter the arithmetic.
SOFT_FIELDS = {'date', 'description', 'counterparty'}


def proves(result, records, candidate):
    """Whether ``result`` proves the candidate rows (see module docstring)."""
    if result['can_import']:
        return True
    for blocker in result['blockers']:
        row_id = blocker.get('row_id')
        record = records.get(row_id)
        if (blocker.get('kind') != 'missing_field' or blocker.get('field') not in SOFT_FIELDS or record is None
                or row_id in candidate or record.get('resolved_transaction_id')
                or record['original'].get('kind') == 'manual_entry'):
            return False
        # Outside the candidate the row keeps its own reading, which must
        # carry a known amount and direction.
        fields = record['fields']
        if not str(fields.get('amount_minor') or '').isdigit() or fields.get('direction') not in ('credit', 'debit'):
            return False
    return True


def plan(session, document, period, metadata, currency, ready, *, transactions=None, details=None):
    """Return ``(admit_ids, held_reasons, admission, held_blockers)`` for ``ready``.

    ``ready`` maps record id -> its completed fields (values all present).
    ``admission`` is the assessment of the admitted set, or of the base when
    nothing can be admitted; ``held_blockers`` maps a held record to the
    checks that failed with it. ``details`` (a dict, optional) receives
    ``repeats`` (held record id -> the row it repeats) and ``rows_proven``
    (the admitted set proves although the statement still has open checks).
    Nothing is written.
    """
    details = {} if details is None else details
    details.update(repeats={}, rows_proven=False)
    from sqlalchemy import select
    from postgres.models.financial import FinancialTransaction
    from services.financial.saved_statement_admission import assess_saved_additions
    if not ready:
        return set(), {}, None, {}

    def assess(ids):
        return assess_saved_additions(session, document, period, metadata, currency,
                                      transactions=transactions, include=set(ids))

    records = {item['id']: item for item in metadata.get('statement_incomplete_records', [])}
    ready = {key: value for key, value in ready.items() if not records.get(key, {}).get('withdrawn')}
    if not ready:
        return set(), {}, None, {}
    if not INDIVIDUAL_ADMISSION:
        admission = assess_saved_additions(session, document, period, metadata, currency, transactions=transactions)
        if admission['can_import']:
            return set(ready), {}, admission, {}
        return set(), {key: NO_FIT_REASON for key in ready}, admission, {key: admission['blockers'] for key in ready}
    ok = lambda result, ids: proves(result, records, set(ids))
    manual = [key for key in ready if records[key]['original'].get('kind') == 'manual_entry']
    base = [key for key in ready if key not in manual]
    rows = list(transactions) if transactions is not None else list(session.scalars(select(FinancialTransaction).where(
        FinancialTransaction.case_id == document.case_id, FinancialTransaction.source_document_id == document.id,
        FinancialTransaction.superseded_by_id.is_(None))))
    existing = [(f"saved {row.description or 'payment'}", _transaction_fields(row),
                 _detail('saved', _transaction_fields(row), transaction_id=str(row.id)))
                for row in rows if row.ledger_status == 'admitted']
    existing += [(f"corrected {ready[key].get('description') or 'row'}", ready[key],
                  _detail('corrected', ready[key], record_id=key, page=records[key]['original'].get('page_number')))
                 for key in base]
    held, candidates = {}, []
    for key in manual:
        match = _repeat(ready[key], existing)
        if match:
            held[key] = REPEAT_REASON.format(match[0])
            details['repeats'][key] = match[1]
            continue
        candidates.append(key)
        existing.append((f"added {ready[key].get('description') or 'row'}", ready[key],
                         _detail('added', ready[key], record_id=key, page=ready[key].get('manual_page'))))
    base_result = assess(base)
    single = {key: assess(base + [key]) for key in candidates}
    passing = [key for key in candidates if ok(single[key], base + [key])]
    own = {}
    if ok(base_result, base):
        # The statement already adds up; an addition must keep it that way.
        admit = list(base)
        if passing:
            together = assess(base + passing)
            if ok(together, base + passing):
                admit += passing
            else:
                held.update({key: AMBIGUOUS_REASON for key in passing})
        admission = assess(admit)
    elif len(passing) == 1:
        admit = base + passing
        admission = single[passing[0]]
    else:
        # Corrected printed rows that prove on their own still enter, as long
        # as they also prove together (fail closed otherwise).
        own = {key: assess([key]) for key in base} if len(base) > 1 else {}
        alone = [key for key in base if key in own and ok(own[key], [key])]
        together = assess(alone) if len(alone) > 1 else own.get(alone[0]) if alone else None
        admit = alone if together is not None and ok(together, alone) else []
        admission = together if admit else base_result
        held.update({key: BASE_REASON for key in base if key not in admit})
        held.update({key: AMBIGUOUS_REASON for key in passing})
    failing = [key for key in candidates if key not in admit and key not in held]
    pair = len(failing) > 1 and ok(assess((admit or base) + failing), (admit or base) + failing)
    held.update({key: PAIR_REASON if pair else NO_FIT_REASON for key in failing})
    blockers = {key: single[key]['blockers'] for key in failing}
    blockers.update({key: (own.get(key) or base_result)['blockers'] for key in base if key in held})
    details['rows_proven'] = bool(admit) and admission is not None and not admission['can_import'] and ok(admission, admit)
    return set(admit), held, admission, blockers


def held_blockers(record):
    """The record's own hold reason, as a blocker for replayed save receipts."""
    reason = record.get('hold_reason')
    return ([dict(kind='held_record', row_id=record.get('id'), message=reason)] if reason else []) + record.get('hold_blockers', [])


def _balance(result):
    calculation = result.get('calculation') or {}
    return dict(reconciles=bool(result['can_import']),
                calculated_closing_minor=calculation.get('calculated_closing_minor'),
                printed_closing_minor=calculation.get('printed_closing_minor'),
                difference_minor=calculation.get('difference_minor'))


def addition_effects(session, document, period, metadata, currency, ready, *, transactions=None):
    """What the statement's closing balance would be with and without each of
    the investigator's added rows. Read only; ``None`` when there are none.

    ``held_only_by_additions`` is true when the statement does not prove with
    everything entered but proves once every added row is left out: the added
    rows are then the only reason it is held.
    """
    from services.financial.saved_statement_admission import assess_saved_additions
    records = {item['id']: item for item in metadata.get('statement_incomplete_records', [])}
    ready = [key for key in ready if key in records and not records[key].get('withdrawn')]
    manual = [key for key in ready if records[key]['original'].get('kind') == 'manual_entry']
    if not manual:
        return None
    base = [key for key in ready if key not in manual]

    def assess(ids):
        return assess_saved_additions(session, document, period, metadata, currency,
                                      transactions=transactions, include=set(ids))
    everything, without = assess(ready), assess(base)
    return dict(
        with_all=_balance(everything), without_additions=_balance(without),
        held_only_by_additions=not proves(everything, records, set(ready)) and proves(without, records, set(base)),
        without_each={key: _balance(assess([other for other in ready if other != key])) for key in manual})
