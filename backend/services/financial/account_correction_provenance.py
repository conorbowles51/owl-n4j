"""Account-correction provenance for the ledger export.

The account panel shows each correction of an account's holder, bank or number with who made it and whether a
person confirmed it (services.financial.account_details_correction). The export carries the same record, so a reader
of the exported file sees which account details were corrected, from what, by whom and on what basis:

- the original value is kept beside the corrected one;
- a correction a model made is shown as the model's reading, not confirmed, until a person confirms it;
- a confirmation someone else entered on the person's instruction says so: "Confirmed by X, entered by Y on X's
  instruction" (a relay stored without its note says that no note was recorded, never assumes one);
- an undone correction is listed as undone, and its original value is the account's current value.

Read only, from the accounts' stored history, inside the export's single consistent read.
"""
from __future__ import annotations

from services.financial.model_work import origin_of

SCHEMA = 'loupe.financial.account_corrections/1'
FIELD_NAMES = (('holder', 'Holder'), ('institution', 'Bank'), ('account_number', 'Account number'))


def _day(value):
    return str(value or '')[:10] or 'date not recorded'


def relay_line(confirmed, relay):
    """'Confirmed by X, entered by Y on X's instruction, <day>'; a relay without a note says so."""
    who = confirmed.get('by') or 'a person'
    how = f"on {who}'s instruction" if relay.get('note') else '(no relay note recorded)'
    return f"Confirmed by {who}, entered by {relay.get('by') or 'someone not recorded'} {how}, {_day(relay.get('at') or confirmed.get('at'))}"


def confirmation_line(confirmed):
    if not confirmed:
        return None
    relay = confirmed.get('relayed')
    head = relay_line(confirmed, relay) if relay else f"Confirmed by {confirmed.get('by') or 'a person'} on {_day(confirmed.get('at'))}"
    return f"{head}: {confirmed.get('basis') or 'basis not recorded'}"


def _relays(confirmed):
    """Every entry of a relayed confirmation, the first and any later instruction, each with its own text."""
    if not confirmed:
        return []
    items = ([dict(confirmed['relayed'])] if confirmed.get('relayed') else []) + [dict(item) for item in confirmed.get('later_relays') or []]
    return [dict(item, text=relay_line(confirmed, item)) for item in items]


def made_by(entry):
    origin = origin_of(entry)
    if origin:
        return f"{origin.get('model') or 'A model'} for {(origin.get('for') or {}).get('name') or 'a person'}"
    return entry.get('actor_name') or entry.get('actor_email') or 'Not recorded'


def status_of(entry, undo=None):
    """(status, text). A model's correction no person confirmed is the model's reading. An undone one names who
    undid it and why, from the undo entry."""
    if entry.get('undone_at'):
        who = f" by {(undo or {}).get('actor_name') or (undo or {}).get('actor_email')}" if (undo or {}).get('actor_name') or (undo or {}).get('actor_email') else ''
        why = f" ({undo['reason']})" if (undo or {}).get('reason') else ''
        return 'undone', f"Undone{who} on {_day(entry['undone_at'])}{why}; this correction no longer applies"
    origin = origin_of(entry)
    if origin and entry.get('confirmed'):
        return 'confirmed', confirmation_line(entry['confirmed'])
    if origin:
        return 'model_reading_not_confirmed', f"Corrected by {origin.get('model') or 'a model'} · not confirmed (the model's reading)"
    return 'person', f"Corrected by {made_by(entry)}"


def account_corrections(accounts):
    """One record per changed field of each correction in the accounts' history, oldest first."""
    records = []
    for account in sorted(accounts, key=lambda value: str(value.id)):
        meta = account.metadata_ or {}
        label = meta.get('display_label') or account.identifier_as_printed or account.holder_name
        history = meta.get('account_details_history') or []
        undos = {item.get('undo_of'): item for item in history if item.get('kind') == 'undo'}
        # The account's value now, per field: a later correction can supersede an earlier one.
        now = dict(holder=account.holder_name or '', institution=account.institution_name or '',
                   account_number=account.identifier_as_printed or '')
        for entry in history:
            if entry.get('kind') != 'correction':
                continue
            before, after = entry.get('before') or {}, entry.get('after') or {}
            undo = undos.get(entry.get('id'))
            status, status_text = status_of(entry, undo)
            origin = origin_of(entry)
            for field, name in FIELD_NAMES:
                if field not in after or after.get(field) == before.get(field):
                    continue
                records.append(dict(
                    account_id=str(account.id), account_label=label, correction_id=entry.get('id'), at=entry.get('at'),
                    field=field, field_label=name, original_value=before.get(field), corrected_value=after.get(field),
                    account_value_now=now[field],
                    made_by=made_by(entry), made_by_kind='model' if origin else 'person',
                    model_origin=origin, citation=(origin or {}).get('citation'), reason=entry.get('reason'),
                    status=status, status_text=status_text, confirmation=entry.get('confirmed'),
                    confirmation_text=confirmation_line(entry.get('confirmed')), relays=_relays(entry.get('confirmed')),
                    undone_at=entry.get('undone_at'),
                    undone_by=(undo or {}).get('actor_name') or (undo or {}).get('actor_email'),
                    undo_reason=(undo or {}).get('reason')))
    records.sort(key=lambda item: (item['account_id'], str(item['at'] or ''), item['correction_id'] or '', item['field']))
    return records


def capture_account_corrections(session, *, case_id, account_ids):
    """The corrections of the captured accounts (the readings' accounts, canonical accounts and aliases)."""
    from uuid import UUID
    from sqlalchemy import select
    from postgres.models.financial import FinancialAccount
    ids = sorted({UUID(str(value)) for value in account_ids}, key=str)
    accounts = []
    for offset in range(0, len(ids), 5000):
        accounts.extend(session.scalars(select(FinancialAccount).where(
            FinancialAccount.case_id == case_id, FinancialAccount.id.in_(ids[offset:offset + 5000]))))
    records = account_corrections(accounts)
    unconfirmed = sum(1 for item in records if item['status'] == 'model_reading_not_confirmed')
    return dict(schema=SCHEMA, scope='Corrections of the holder, bank or account number of the captured accounts, from '
                'each account\'s history. The original value is kept beside the corrected one.',
                corrections=records, unconfirmed_model_corrections=unconfirmed)


def unconfirmed_limitation(section):
    count = section['unconfirmed_model_corrections']
    if not count:
        return None
    return (f'{count} account-detail correction{"s" if count != 1 else ""} a model made {"are" if count != 1 else "is"} '
            'not confirmed by a person. The corrected holder, bank or number is shown as the model\'s reading, with '
            'the original value beside it, under Account corrections.')


def row_markers(section):
    """{account id: short note} for payment rows whose account details were corrected: which details, and whether a
    model's correction is still unconfirmed. Undone corrections mark nothing (the original value is current)."""
    by_account = {}
    for item in (section or {}).get('corrections', []):
        if item['status'] != 'undone':
            by_account.setdefault(item['account_id'], []).append(item)
    markers = {}
    for account_id, items in by_account.items():
        fields = sorted({item['field_label'].lower() for item in items})
        unconfirmed = any(item['status'] == 'model_reading_not_confirmed' for item in items)
        markers[account_id] = (f" ({', '.join(fields)} corrected{'; model reading, not confirmed' if unconfirmed else ''}; "
                               'see Account corrections)')
    return markers
