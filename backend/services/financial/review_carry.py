"""Carry an investigator's file-level review onto the one period a newer reading names.

An earlier reader read some files as one unnamed statement; a newer one names
its period. The saved review is keyed by the old (empty) period id, so nothing
finds it and the statement waits on "earlier corrections to compare" with no
way forward. When the new reading names exactly one period, each saved detail
is carried onto it unless the reading now prints something else for that
field; only such a field is asked about, with both values. Saved payment-row
edits belong to the old reading's rows and are never remapped here.
"""
import re
import unicodedata
from copy import deepcopy
from datetime import datetime, timezone

from services.financial.pdf_candidates import _digest

DETAILS = ('holder', 'account_number', 'institution', 'currency', 'period_start', 'period_end')
LABELS = dict(holder='Account holder', account_number='Account number', institution='Bank', currency='Currency',
              period_start='Statement start', period_end='Statement end')
CARRIED_BY = dict(user_id=None, name='System')
_COMPANY = {'sa', 'de', 'cv', 'sapi', 'sab', 'srl', 'rl', 'inc', 'llc', 'ltd'}
_BANK = {'banco', 'bank', 'mexico', 'sa', 'de', 'cv', 'institucion', 'banca', 'multiple', 'grupo', 'financiero'}


def _words(value):
    plain = unicodedata.normalize('NFKD', value or '').encode('ascii', 'ignore').decode().lower()
    return [word for word in re.split(r'[^0-9a-z]+', plain.replace('.', '')) if word]


def same_value(field, saved, read):
    """The two values name the same thing, written differently."""
    if saved == read:
        return True
    if field == 'account_number':
        digits = re.sub(r'\D', '', saved)
        return bool(digits) and digits == re.sub(r'\D', '', read)
    if field == 'holder':
        mine, theirs = [[w for w in _words(v) if w not in _COMPANY] for v in (saved, read)]
        return bool(mine) and mine == theirs
    if field == 'institution':
        mine, theirs = [' '.join(w for w in _words(v) if w not in _BANK) for v in (saved, read)]
        return bool(mine and theirs) and (mine in theirs or theirs in mine)
    return False


def _row_edits(request):
    return any((row.get('reason') or '').strip() or row.get('manual_page') for row in request.get('rows') or []) \
        or bool(request.get('_saved_balance_corrections'))


def carry_file_level_review(file, proposal, identifiers):
    """Persist the carried review on `file` for the reading's one named period.

    Returns the new saved-review record, or None when nothing is carried: the
    period already has its own review, the reading names no or several
    periods, or the saved review changed payment rows (those need the old rows).
    """
    from services.financial.import_batches import initial_request
    from services.financial.effective_statement_review import request_signature
    statement_id = proposal.get('statement_id')
    metadata = file.metadata_ or {}
    progress = metadata.get('financial_review_progress') or {}
    saved = progress.get('')
    if not statement_id or len(identifiers) != 1 or identifiers[0] != statement_id or statement_id in progress:
        return None
    if not saved or _row_edits(saved.get('request') or {}):
        return None
    mine = saved['request']
    reading = initial_request(proposal)
    carried, kept, conflicts = deepcopy(reading), [], {}
    for field in DETAILS:
        value, read = (mine.get(field) or '').strip(), (reading.get(field) or '').strip()
        if not value or value == read:
            continue
        if not read or same_value(field, value, read):
            carried[field] = value
            kept.append(field)
        else:
            conflicts[field] = dict(yours=value, reading=read)
    now = datetime.now(timezone.utc).isoformat()
    record = dict(request=carried, review_revision=_digest(carried), saved_at=now, saved_by=CARRIED_BY,
        carried_from=dict(statement_id='', review_revision=saved.get('review_revision'), saved_at=saved.get('saved_at'),
                          saved_by=saved.get('saved_by'), fields=kept),
        initial_request_signature=request_signature(initial_request(proposal)), superseded_request_signatures=[])
    if conflicts:
        record['carry_conflicts'] = conflicts
    updated = deepcopy(metadata)
    updated.setdefault('financial_review_history', []).append(saved)
    del updated['financial_review_progress']['']
    updated['financial_review_progress'][statement_id] = record
    file.metadata_ = updated
    return record


def conflict_problems(proposal, request):
    """One question per field the newer reading prints differently, while the
    carried review is the one being assessed (any later save answers it)."""
    saved = proposal.get('saved_review') or {}
    conflicts = saved.get('carry_conflicts')
    if not conflicts or (request is not None and request != saved.get('request')):
        return []
    return [dict(kind='carry_conflict', field=field, row_id=None, yours=value['yours'], reading=value['reading'],
                 message=f"{LABELS[field]}: you entered {value['yours']}, the statement now reads {value['reading']}. "
                         f"Choose which is right.")
            for field, value in conflicts.items()]
