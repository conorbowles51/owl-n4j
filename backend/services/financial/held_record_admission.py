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
  or several additions that could each be the missing line, stay held.

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
    amount, direction, day, text = _signature(candidate)
    for label, other in existing:
        o_amount, o_direction, o_day, o_text = _signature(other)
        if not amount or (amount, direction) != (o_amount, o_direction):
            continue
        if day and day == o_day:
            return label
        if text and text == o_text and day and o_day and abs(day - o_day) <= timedelta(days=REPEAT_DAYS):
            return label
    return None


def _transaction_fields(row):
    day = row.transaction_date or row.posted_date or row.value_date or row.effective_date
    return dict(amount_minor=str(row.amount_minor), direction=row.direction,
                date=day.isoformat() if day else '', description=row.description)


def plan(session, document, period, metadata, currency, ready, *, transactions=None):
    """Return ``(admit_ids, held_reasons, admission, held_blockers)`` for ``ready``.

    ``ready`` maps record id -> its completed fields (values all present).
    ``admission`` is the assessment of the admitted set, or of the base when
    nothing can be admitted; ``held_blockers`` maps a held record to the
    checks that failed with it. Nothing is written.
    """
    from sqlalchemy import select
    from postgres.models.financial import FinancialTransaction
    from services.financial.saved_statement_admission import assess_saved_additions
    if not ready:
        return set(), {}, None, {}

    def assess(ids):
        return assess_saved_additions(session, document, period, metadata, currency,
                                      transactions=transactions, include=set(ids))

    if not INDIVIDUAL_ADMISSION:
        admission = assess_saved_additions(session, document, period, metadata, currency, transactions=transactions)
        if admission['can_import']:
            return set(ready), {}, admission, {}
        return set(), {key: NO_FIT_REASON for key in ready}, admission, {key: admission['blockers'] for key in ready}
    records = {item['id']: item for item in metadata.get('statement_incomplete_records', [])}
    manual = [key for key in ready if records[key]['original'].get('kind') == 'manual_entry']
    base = [key for key in ready if key not in manual]
    rows = list(transactions) if transactions is not None else list(session.scalars(select(FinancialTransaction).where(
        FinancialTransaction.case_id == document.case_id, FinancialTransaction.source_document_id == document.id,
        FinancialTransaction.superseded_by_id.is_(None))))
    existing = [(f"saved {row.description or 'payment'}", _transaction_fields(row))
                for row in rows if row.ledger_status == 'admitted']
    existing += [(f"corrected {ready[key].get('description') or 'row'}", ready[key]) for key in base]
    held, candidates = {}, []
    for key in manual:
        match = _repeat(ready[key], existing)
        if match:
            held[key] = REPEAT_REASON.format(match)
            continue
        candidates.append(key)
        existing.append((f"added {ready[key].get('description') or 'row'}", ready[key]))
    base_result = assess(base)
    single = {key: assess(base + [key]) for key in candidates}
    passing = [key for key in candidates if single[key]['can_import']]
    if base_result['can_import']:
        # The statement already adds up; an addition must keep it that way.
        admit = list(base)
        if passing:
            together = assess(base + passing)
            if together['can_import']:
                admit += passing
            else:
                held.update({key: AMBIGUOUS_REASON for key in passing})
        admission = assess(admit)
    elif len(passing) == 1:
        admit = base + passing
        admission = single[passing[0]]
    else:
        admit = []
        admission = base_result
        held.update({key: BASE_REASON for key in base})
        held.update({key: AMBIGUOUS_REASON for key in passing})
    failing = [key for key in candidates if key not in admit and key not in held]
    pair = len(failing) > 1 and assess((admit or base) + failing)['can_import']
    held.update({key: PAIR_REASON if pair else NO_FIT_REASON for key in failing})
    blockers = {key: single[key]['blockers'] for key in failing}
    blockers.update({key: base_result['blockers'] for key in base if key in held})
    return set(admit), held, admission, blockers


def held_blockers(record):
    """The record's own hold reason, as a blocker for replayed save receipts."""
    reason = record.get('hold_reason')
    return ([dict(kind='held_record', row_id=record.get('id'), message=reason)] if reason else []) + record.get('hold_blockers', [])
