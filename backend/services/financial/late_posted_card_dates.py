"""Late-posted card charges on already saved statements (Neil, 2026-10-09).

A card statement can list a charge whose printed date falls shortly before
the billing cycle start (a late-posted charge). The current card reader
(``statement_layout_context.card_row_dates``) already resolves such a date to
the one calendar date it can name in the 31 days before the cycle. Statements
saved with an older reading kept that row as an incomplete record whose only
missing value is its date ("Check the transaction date against this billing
period.").

This module proposes that date for such a saved record, from the record's own
printed date cell and the same reader rule, never from anything else:

* only a printed card row whose reading flagged exactly that date check, whose
  only missing value is the date, and which nobody has corrected or withdrawn;
* the printed text must name exactly one date, at most 31 days (one cycle)
  before the saved period's start; the printed text is kept with the row;
* the proposal is a candidate only: it enters Transactions through the
  held-record rule, i.e. only if the statement then reconciles exactly. If it
  does not, the record stays untouched (still missing its date).

``LATE_POSTED_CARD_DATES = False`` turns the proposal off in one place.
"""
from datetime import date

LATE_POSTED_CARD_DATES = True
DATE_ISSUE = 'Check the transaction date against this billing period.'
RULE = 'late_posted_card_charge'
REASON = ('Printed date {text!r} is just before the billing cycle (a late-posted charge). '
          'The statement reconciles with it.')


def proposed_date(record, period_start, period_end):
    """``(iso_date, basis, printed_text)`` for a saved late-posted card row, else None."""
    if not LATE_POSTED_CARD_DATES or not period_start or not period_end:
        return None
    if (record.get('correction') or record.get('withdrawn') or record.get('resolved_transaction_id')
            or record.get('missing_fields') != ['date']):
        return None
    original = record.get('original') or {}
    if original.get('kind') == 'manual_entry' or DATE_ISSUE not in (original.get('issues') or []):
        return None
    context = original.get('layout_context') or {}
    text = (context.get('date_source') or {}).get('expected_text')
    if not text or not str(text).strip():
        return None
    posting = context.get('posting_date_source')
    posting_text = posting.get('expected_text') if posting else None
    start = period_start if isinstance(period_start, date) else date.fromisoformat(str(period_start)[:10])
    end = period_end if isinstance(period_end, date) else date.fromisoformat(str(period_end)[:10])
    from services.financial.statement_layout_context import card_row_dates
    _reading, possible, _postings, basis = card_row_dates(text, posting_text, start, end)
    if len(possible) != 1 or basis not in ('printed_before_cycle', 'printed_posting_date', 'printed_posting_before_cycle'):
        return None
    value = date.fromisoformat(possible[0])
    if not (0 < (start - value).days <= 31):
        return None
    return value.isoformat(), basis, str(text).strip()


def candidate_fields(record, proposal):
    """The record's own fields with the proposed date and an explaining note."""
    iso, _basis, text = proposal
    return {**record['fields'], 'date': iso, 'reason': REASON.format(text=text)}


def propose(items, period):
    """Put each proposal on its record as a candidate correction (in memory).

    Returns ``{record_id: proposal}``; ``withdraw_proposals`` undoes it.
    """
    proposals = {}
    for item in items:
        proposal = proposed_date(item, getattr(period, 'period_start', None), getattr(period, 'period_end', None))
        if proposal:
            item['correction'] = candidate_fields(item, proposal)
            item['missing_fields'] = []
            proposals[item['id']] = proposal
    return proposals


def withdraw_proposals(items, proposals):
    """Return proposed records to their saved state: still missing the date."""
    for item in items:
        if item['id'] in proposals:
            item.pop('correction', None)
            item['missing_fields'] = ['date']
            for key in ('hold_reason', 'hold_blockers', 'hold_repeat_of'):
                item.pop(key, None)


def provenance(proposal):
    iso, basis, text = proposal
    return dict(rule=RULE, date=iso, basis=basis, printed_text=text)
