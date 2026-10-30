"""Correct an account's holder or bank for every statement it holds.

A per-statement details edit corrects one statement. When the account record
itself is wrong (for example a holder read from the address block), editing one
statement cannot fix it: the statement no longer agrees with the account, so
the edit moves that statement onto an account of its own (``statement-details:``)
and the rest keep the wrong value.

This correction rewrites the account record once, then:

- records the corrected value on each of the account's saved statements
  through the ordinary statement details edit, so each statement's history
  keeps its earlier value and who changed it, and a later edit of one statement
  agrees with its account;
- re-joins statements an earlier per-statement edit split off whose only
  difference from this account was the corrected field (bank, number, currency
  and type equal; holder and bank compared folded);
- keeps every earlier value in the account history, so the correction can be
  undone, which restores the previous values (and splits re-joined statements
  back onto their own account);
- sets aside, by the duplicates rule, a saved copy of a printed statement the
  account already holds once the correction brings both onto the account
  (``copies_set_aside``), and undoing the correction restores those copies.

Only a person can make it, with a reason, against the revision they reviewed.
The ledger holder filter reads the account record, so it follows at once.
"""
import logging
from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from postgres.models.financial import FinancialAccount, FinancialStatementPeriod
from services.financial.pdf_candidates import PdfMappingError, _digest
from services.financial.model_work import origin_field, origin_of

HISTORY = 'account_details_history'
SPLIT_PREFIX = 'statement-details:'
FIELDS = (('holder', 'holder_name'), ('institution', 'institution_name'))
NUMBER = 'account_number'


class AccountDetailsRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    holder: str | None = Field(default=None, max_length=255)
    institution: str | None = Field(default=None, max_length=128)
    # The account number as the statements print it. A CLABE the account was saved with is kept as its alias.
    account_number: str | None = Field(default=None, max_length=128)
    reason: str = Field(max_length=2000)


class UndoAccountDetailsRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    correction_id: str = Field(max_length=64)
    reason: str = Field(max_length=2000)


class ConfirmAccountDetailsRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    correction_id: str = Field(max_length=64)
    basis: str = Field(max_length=2000)


def _person(actor):
    if actor is None or actor.user_id is None or (actor.email or '').strip().lower().endswith('@system.local'):
        raise PdfMappingError('Only a person can correct an account for all of its statements.', 403)


def _reason(value):
    reason = (value or '').strip()
    if not reason:
        raise PdfMappingError('Give the reason for this correction (for example the page that prints the holder).', 422)
    return reason


def _account(session, case_id, account_id, lock=False):
    from services.financial.account_type_change import _account as load
    return load(session, case_id, account_id, lock=lock)


def _statements(session, case_id, account, lock=False):
    from services.financial.account_type_change import _statements as load
    return load(session, case_id, account, lock=lock)


def _period_counts(session, case_id, pairs):
    """Periods per source document: a statement edit needs exactly one."""
    ids = list({document.id for document, _ in pairs})
    counts = {}
    if ids:
        for source_id in session.scalars(select(FinancialStatementPeriod.source_document_id).where(
                FinancialStatementPeriod.case_id == case_id, FinancialStatementPeriod.source_document_id.in_(ids))):
            counts[source_id] = counts.get(source_id, 0) + 1
    return counts


def _split_off(session, case_id, account, values):
    """Accounts a per-statement edit split off this one, differing only in the
    corrected field: same number (digits), currency and type; holder and bank
    equal to the corrected values when folded."""
    from services.financial.accounts import CLABE_ALIAS, _fold, digits_only
    digits = {digits_only(account.identifier_as_printed), digits_only(values.get(NUMBER))} - {''}
    if not digits:
        return []
    # The CLABE the account keeps after the correction (a preview's account does not record it yet).
    alias = (account.metadata_ or {}).get(CLABE_ALIAS) or (_alias_after(account, values) if NUMBER in values else None)
    found = []
    for other in session.scalars(select(FinancialAccount).where(FinancialAccount.case_id == case_id,
            FinancialAccount.id != account.id, FinancialAccount.identifier_normalised.in_(digits))
            .order_by(FinancialAccount.created_at, FinancialAccount.id)):
        meta = other.metadata_ or {}
        # An identified account of the printed number (saved without the CLABE) is the same account when its
        # bank, holder, currency and type agree and it records no other CLABE.
        printed = (alias and other.identifier_normalised == digits_only(values.get(NUMBER))
                   and not meta.get('identity_distinguisher') and meta.get(CLABE_ALIAS) in (None, alias))
        if not printed and not str(meta.get('identity_distinguisher') or '').startswith(SPLIT_PREFIX):
            continue
        if (other.currency != account.currency or other.account_type != account.account_type
                or meta.get('account_reference_kind') != (account.metadata_ or {}).get('account_reference_kind')):
            continue
        if all(_fold(getattr(other, column)) == _fold(values[key]) for key, column in FIELDS):
            found.append(other)
    return found


def _statement_rows(session, case_id, pairs):
    counts = _period_counts(session, case_id, pairs)
    from services.financial.statement_details import saved_details
    return [dict(source_document_id=str(document.id), evidence_file_id=str(document.evidence_file_id),
                 period_id=str(period.id), period_start=period.period_start.isoformat() if period.period_start else None,
                 period_end=period.period_end.isoformat() if period.period_end else None, currency=period.currency,
                 holder=saved_details(document).get('holder', ''), institution=saved_details(document).get('institution', ''),
                 editable=counts.get(document.id) == 1)
            for document, period in pairs]


def _values(account):
    return dict(holder=account.holder_name or '', institution=account.institution_name or '')


def _with_number(account):
    return dict(_values(account), **{NUMBER: account.identifier_as_printed or ''})


def _revision(account, statements):
    return _digest(dict(account=str(account.id), identity=account.identity_key, values=_values(account),
        number=account.identifier_as_printed, currency=account.currency, account_type=account.account_type,
        history=(account.metadata_ or {}).get(HISTORY, []), statements=statements))


def account_details_state(session, *, case_id, account_id):
    account = _account(session, case_id, account_id)
    statements = _statement_rows(session, case_id, _statements(session, case_id, account))
    return dict(case_id=str(case_id), account_id=str(account.id), **_values(account),
        account_number=account.identifier_as_printed or '', account_clabe=(account.metadata_ or {}).get('account_clabe') or '',
        currency=account.currency or '',
        statements=statements, history=(account.metadata_ or {}).get(HISTORY, []),
        revision=_revision(account, statements))


def _requested(account, request):
    current = _with_number(account) if request.account_number is not None else _values(account)
    after = dict(current)
    for key, _ in FIELDS:
        value = getattr(request, key)
        if value is None:
            continue
        value = value.strip()
        if not value:
            raise PdfMappingError('Enter the holder and bank as printed; a correction cannot leave them blank.', 422)
        if any(ord(c) < 32 for c in value):
            raise PdfMappingError('Account details must be on a single line.', 422)
        after[key] = value
    if request.account_number is not None:
        from services.financial.accounts import clabe_alias
        value = request.account_number.strip()
        if not value or any(ord(c) < 32 for c in value):
            raise PdfMappingError('Enter the account number as printed, on a single line.', 422)
        if clabe_alias(value) and value != current[NUMBER]:
            raise PdfMappingError('A CLABE is not the account number. Enter the account number the statements print; '
                                  'the CLABE stays recorded with the account.', 422)
        after[NUMBER] = value
    if after == current:
        raise PdfMappingError('These are already the account\'s details. Nothing to change.', 422)
    return current, after


def _alias_after(account, after):
    """The CLABE the account keeps once its number is ``after``: the one it records, or its number as saved
    when that is a CLABE and the corrected number is not."""
    from services.financial.accounts import CLABE_ALIAS, clabe_alias
    recorded = (account.metadata_ or {}).get(CLABE_ALIAS)
    if recorded or NUMBER not in after:
        return recorded
    return clabe_alias(account.identifier_as_printed) if after[NUMBER] != account.identifier_as_printed else None


def preview_account_details(session, *, case_id, account_id, request):
    account = _account(session, case_id, account_id)
    current, after = _requested(account, request)
    statements = _statement_rows(session, case_id, _statements(session, case_id, account))
    rejoin = [dict(account_id=str(other.id), statements=_statement_rows(session, case_id, _statements(session, case_id, other)))
              for other in _split_off(session, case_id, account, after)]
    return dict(case_id=str(case_id), account_id=str(account.id), before=current, after=after,
        statements=statements, rejoin=[item for item in rejoin if item['statements']],
        revision=_revision(account, statements))


def _new_identity(session, case_id, account, after, alias=None):
    """The identity key with the corrected bank (the holder takes no part in it).
    An account given its own key (unidentified) keeps that key."""
    meta = account.metadata_ or {}
    if meta.get('identity_distinguisher'):
        return account.identity_key
    from services.financial.accounts import AccountDraft, AccountIdentityError
    try:
        draft = AccountDraft.observed(institution_name=after['institution'] or None,
            identifier_as_printed=after.get(NUMBER, account.identifier_as_printed), account_type=account.account_type,
            holder_name=after['holder'] or None, currency=account.currency, iban=account.iban, bic=account.bic,
            routing_number=account.routing_number, metadata=dict(account_reference_kind=meta.get('account_reference_kind'),
                                                                 **({'account_clabe': alias} if alias else {})))
        key = draft.identity().key
    except AccountIdentityError as exc:
        raise PdfMappingError('The corrected bank does not identify this account. Nothing was changed.', 422) from exc
    if key != account.identity_key and session.scalar(select(FinancialAccount.id).where(
            FinancialAccount.case_id == case_id, FinancialAccount.identity_key == key, FinancialAccount.id != account.id)):
        raise PdfMappingError('Another account already has this bank and number. Merge the two accounts instead; nothing was changed.', 409)
    return key


def _edit_statement(session, case_id, document, overrides, actor, resolve_account=False, onto_account=None):
    """One statement through the ordinary details edit (history, checks,
    reconcile). ``overrides`` are the corrected fields; the statement keeps its
    own spelling of the others."""
    from services.financial.statement_details import StatementDetailsRequest, read_statement_details, update_statement_details
    view = read_statement_details(session, case_id=case_id, source_id=document.id)
    details = view['details']
    keys = [key for key, _ in FIELDS] + [NUMBER, 'account_clabe']
    values = {key: overrides.get(key, details.get(key, '')) for key in keys}
    if not resolve_account and all(details.get(key, '') == values[key] for key in keys):
        return None
    request = StatementDetailsRequest(expected_revision=view['revision'], holder=values['holder'],
        account_number=values[NUMBER], institution=values['institution'], account_clabe=values['account_clabe'])
    result = update_statement_details(session, case_id=case_id, source_id=document.id, request=request,
        actor=actor, commit=False, resolve_account=resolve_account, onto_account=onto_account)
    changed = [key for key, _ in FIELDS] + [key for key in (NUMBER, 'account_clabe') if key in overrides]
    return dict(source_document_id=str(document.id), before={key: details.get(key, '') for key in changed},
                from_account_id=view['account_id'], to_account_id=result['account_id'])


def _apply(session, *, case_id, account, before, after, reason, actor, now, entry, rejoin_details=None):
    """Write the account record, then every statement; then re-join splits."""
    from services.financial.accounts import CLABE_ALIAS, digits_only
    alias = _alias_after(account, after)
    account.identity_key = _new_identity(session, case_id, account, after, alias)
    account.holder_name, account.institution_name = after['holder'] or None, after['institution'] or None
    meta = deepcopy(account.metadata_ or {})
    label = meta.get('display_label')
    if label and before['holder'] and label.startswith(before['holder']):
        meta['display_label'] = label = after['holder'] + label[len(before['holder']):]
    if NUMBER in after and after[NUMBER] != before[NUMBER]:
        account.identifier_as_printed, account.identifier_normalised = after[NUMBER], digits_only(after[NUMBER]) or None
        if label and before[NUMBER] and before[NUMBER] in label:
            meta['display_label'] = label.replace(before[NUMBER], after[NUMBER])
        if alias and not meta.get(CLABE_ALIAS):
            meta[CLABE_ALIAS] = alias
            entry['clabe_alias_added'] = alias
    account.metadata_ = meta
    session.flush()
    overrides = {key: after[key] for key, _ in FIELDS if after[key] != before[key]}
    if NUMBER in after and after[NUMBER] != before[NUMBER]:
        overrides.update({NUMBER: after[NUMBER], 'account_clabe': alias or ''})
    for document, period in _statements(session, case_id, account, lock=True):
        if _period_counts(session, case_id, [(document, period)]).get(document.id) != 1:
            entry['not_edited'].append(dict(source_document_id=str(document.id),
                reason='The PDF holds several statement periods; its account record is corrected, its own details are not.'))
            continue
        changed = _edit_statement(session, case_id, document, overrides, actor, onto_account=account)
        if changed:
            entry['statements'].append(changed)
    for other in _split_off(session, case_id, account, after):
        for document, period in _statements(session, case_id, other, lock=True):
            if _period_counts(session, case_id, [(document, period)]).get(document.id) != 1:
                continue
            # A statement of an account found to be this one joins it, keeping its own spelling of the holder and
            # bank; one that would resolve anywhere else stays where it is (never moved to a third account).
            savepoint = session.begin_nested()
            moved = _edit_statement(session, case_id, document, {'account_clabe': alias} if alias else {}, actor,
                                    resolve_account=True, onto_account=account)
            if moved and moved['to_account_id'] != str(account.id):
                savepoint.rollback()
                entry.setdefault('not_rejoined', []).append(dict(source_document_id=str(document.id),
                    account_id=str(other.id), reason="Its own details name another account; it stays where it is."))
                continue
            savepoint.commit()
            if moved and moved['to_account_id'] == str(account.id):
                entry['rejoined'].append(moved)
                other_meta = deepcopy(other.metadata_ or {})
                other_meta.setdefault('rejoined_into', []).append(dict(account_id=str(account.id),
                    source_document_id=str(document.id), at=now, correction_id=entry['id']))
                other.metadata_ = other_meta
    session.flush()


def save_account_details(session, *, case_id, account_id, request, actor):
    try:
        _person(actor)
        reason = _reason(request.reason)
        account = _account(session, case_id, account_id, lock=True)
        statements = _statement_rows(session, case_id, _statements(session, case_id, account, lock=True))
        if _revision(account, statements) != request.expected_revision:
            raise PdfMappingError('This account changed since you opened it. Reload before correcting it; nothing was changed.', 409)
        before, after = _requested(account, request)
        now = datetime.now(timezone.utc).isoformat()
        entry = dict(id=uuid4().hex, kind='correction', at=now, reason=reason, before=before, after=after,
            identity_key_before=account.identity_key, actor_id=str(actor.user_id), actor_name=actor.name,
            actor_email=actor.email, statements=[], rejoined=[], not_edited=[], **origin_field(actor))
        _apply(session, case_id=case_id, account=account, before=before, after=after, reason=reason, actor=actor,
               now=now, entry=entry)
        entry['identity_key_after'] = account.identity_key
        meta = deepcopy(account.metadata_ or {})
        meta.setdefault(HISTORY, []).append(entry)
        account.metadata_ = meta
        session.flush()
        result = account_details_state(session, case_id=case_id, account_id=account.id)
        result['correction'] = entry
        session.commit()
    except Exception:
        session.rollback()
        raise
    copies = copies_set_aside(session, case_id=case_id, account_id=account_id, correction_id=entry['id'])
    if copies:
        result = account_details_state(session, case_id=case_id, account_id=account_id)
        result['correction'] = {**entry, 'copies_set_aside': copies}
    return result


def copies_set_aside(session, *, case_id, account_id, correction_id):
    """Set aside the saved copies of one printed statement that this account now holds twice
    (``admitted_statement_duplicates.set_aside_on_accounts``) and record them on the correction, so undoing it
    restores them. Runs after the correction committed: a failure leaves the correction as saved, is logged, and the
    copies stay for the duplicates script, which finds the same ones."""
    from services.financial import admitted_statement_duplicates as admitted
    if not admitted.AFTER_ACCOUNT_CHANGE:
        return []
    try:
        outcome = admitted.set_aside_on_accounts(session, case_id, [account_id])
        copies = [dict(source_document_id=item['document_id'], retained_source_document_id=item['retained_document_id'],
                       adjudication_id=item.get('adjudication_id')) for item in outcome['applied']]
        if copies:
            account = _account(session, case_id, account_id, lock=True)
            meta = deepcopy(account.metadata_ or {})
            for item in meta.get(HISTORY, []):
                if item.get('id') == correction_id:
                    item['copies_set_aside'] = item.get('copies_set_aside', []) + copies
            account.metadata_ = meta
            session.commit()
        for item in outcome['refused']:
            logging.getLogger(__name__).warning('Account correction %s: copy %s not set aside: %s', correction_id,
                                                item.get('document_id'), item.get('refusal') or 'already set aside')
        return copies
    except Exception:
        logging.getLogger(__name__).exception('Account correction %s: copies on the account were not set aside',
                                              correction_id)
        session.rollback()
        return []


def _restore_copies(session, case_id, target, actor, reason):
    """Copies the correction set aside count again (each restore is the set-aside's exact reversal)."""
    from postgres.models.financial import FinancialSourceDocument
    from services.financial import admitted_statement_duplicates as admitted
    restored, touched = [], []
    for item in target.get('copies_set_aside', []):
        document = session.get(FinancialSourceDocument, UUID(item['source_document_id']))
        if document is None or document.status != 'superseded' or str(document.superseded_by_id) != item['retained_source_document_id']:
            continue  # Restored or decided again since: left as it stands.
        admitted._restore(session, case_id, document, actor, reason, touched)
        restored.append(item['source_document_id'])
    session.flush()
    return restored, touched


def undo_account_details(session, *, case_id, account_id, request, actor):
    """Restore the values before a correction: the account record, each
    statement's earlier details, and re-joined statements back on their own."""
    try:
        _person(actor)
        reason = _reason(request.reason)
        if any(item.get('copies_set_aside') for item in (_account(session, case_id, account_id).metadata_ or {}).get(HISTORY, [])):
            # Restoring a copy takes the case lock; taken first, in the order the duplicate decisions take it.
            from services.financial.admitted_statement_duplicates import _lock_case
            _lock_case(session, case_id)
        account = _account(session, case_id, account_id, lock=True)
        statements = _statement_rows(session, case_id, _statements(session, case_id, account, lock=True))
        if _revision(account, statements) != request.expected_revision:
            raise PdfMappingError('This account changed since you opened it. Reload before undoing; nothing was changed.', 409)
        history = (account.metadata_ or {}).get(HISTORY, [])
        active = [item for item in history if item.get('kind') == 'correction' and not item.get('undone_at')]
        target = next((item for item in active if item['id'] == request.correction_id), None)
        if target is None:
            raise PdfMappingError('This correction is not in the account history or was already undone.', 409)
        if target is not active[-1]:
            raise PdfMappingError('Undo the later account correction first; nothing was changed.', 409)
        if any(_with_number(account).get(key) != value for key, value in target['after'].items()):
            raise PdfMappingError('The account was changed after this correction. Reload; nothing was changed.', 409)
        now = datetime.now(timezone.utc).isoformat()
        restored = target['before']
        key = target['identity_key_before']
        if key != account.identity_key and session.scalar(select(FinancialAccount.id).where(
                FinancialAccount.case_id == case_id, FinancialAccount.identity_key == key, FinancialAccount.id != account.id)):
            raise PdfMappingError('Another account now has the earlier bank and number. Nothing was changed.', 409)
        account.identity_key = key
        account.holder_name, account.institution_name = restored['holder'] or None, restored['institution'] or None
        meta = deepcopy(account.metadata_ or {})
        if NUMBER in restored:
            from services.financial.accounts import CLABE_ALIAS, digits_only
            account.identifier_as_printed = restored[NUMBER] or None
            account.identifier_normalised = digits_only(restored[NUMBER]) or None
            if target.get('clabe_alias_added'):
                meta.pop(CLABE_ALIAS, None)
            if meta.get('display_label') and target['after'][NUMBER] in meta['display_label']:
                meta['display_label'] = meta['display_label'].replace(target['after'][NUMBER], restored[NUMBER])
        label = meta.get('display_label')
        if label and target['after']['holder'] and label.startswith(target['after']['holder']):
            meta['display_label'] = restored['holder'] + label[len(target['after']['holder']):]
        account.metadata_ = meta
        session.flush()
        entry = dict(id=uuid4().hex, kind='undo', undo_of=target['id'], at=now, reason=reason,
            before=target['after'], after=restored, actor_id=str(actor.user_id), actor_name=actor.name,
            actor_email=actor.email, statements=[], rejoined=[], split_again=[], **origin_field(actor))
        from postgres.models.financial import FinancialSourceDocument
        entry['copies_restored'], touched = _restore_copies(session, case_id, target, actor, reason)
        rejoined = {item['source_document_id']: item for item in target.get('rejoined', [])}
        for item in target.get('statements', []):
            document = session.get(FinancialSourceDocument, UUID(item['source_document_id']))
            if document is None or document.status != 'admitted':
                continue
            changed = _edit_statement(session, case_id, document, item['before'], actor, onto_account=account)
            if changed:
                entry['statements'].append(changed)
        for source_id, item in rejoined.items():
            document = session.get(FinancialSourceDocument, UUID(source_id))
            if document is None or document.status != 'admitted':
                continue
            # A statement re-joined by the CLABE it was given takes its earlier details back.
            earlier = {key: value for key, value in item.get('before', {}).items() if key == 'account_clabe'}
            moved = _edit_statement(session, case_id, document, earlier, actor, resolve_account=True)
            if moved:
                entry['split_again'].append(moved)
        meta = deepcopy(account.metadata_ or {})
        for item in meta.get(HISTORY, []):
            if item.get('id') == target['id']:
                item['undone_at'], item['undone_by'] = now, entry['id']
        meta.setdefault(HISTORY, []).append(entry)
        account.metadata_ = meta
        session.flush()
        result = account_details_state(session, case_id=case_id, account_id=account.id)
        result['correction'] = entry
        session.commit()
    except Exception:
        session.rollback()
        raise
    if touched:
        # Batch lists reuse stored readiness; best effort, as after any duplicate decision.
        from services.financial.import_batches import refresh_file_readiness
        for file_id, statement_key in dict.fromkeys(touched):
            refresh_file_readiness(session, case_id=case_id, file_id=file_id, statement_key=statement_key)
    return result


def _relay(relayed, now):
    """A relayed confirmation's record: who entered it (``by``), the note saying on whose instruction (``note``),
    when it was entered, and anything else given (for example the message it came by)."""
    if relayed is None:
        return None
    if isinstance(relayed, str):
        relayed = dict(note=relayed)
    record = {key: value for key, value in dict(relayed).items() if value not in (None, '')}
    record['note'] = str(record.get('note') or '').strip()
    record['by'] = str(record.get('by') or '').strip()
    if not record['note'] or not record['by']:
        raise PdfMappingError('A confirmation entered for someone else says who entered it and on whose instruction '
                              '(the relay note). Nothing was changed.', 422)
    record.setdefault('at', now)
    return record


def confirm_account_details(session, *, case_id, account_id, request, actor, at=None, relayed=None, commit=True):
    """A person confirms a correction a model made (services.financial.model_work): the correction keeps its model
    origin and values; the confirmation (who, when, on what basis) is stored on it. Nothing else changes.

    ``relayed`` records that someone else entered a confirmation the person gave elsewhere (for example by
    message): ``{'by': who entered it, 'note': on whose instruction}``; the person stays the one who confirmed.
    It is reached only from ``services.financial.relayed_confirmation`` (no HTTP route passes it). A correction
    the same person already confirmed through a relay takes a later relayed instruction beside the first, which
    stays as it was. ``commit=False`` leaves the transaction to the caller (a dry run rolls it back)."""
    from services.financial.model_work import is_model
    try:
        _person(actor)
        if is_model(actor):
            raise PdfMappingError(f'Only a person can confirm a correction; {actor.name} made it.', 403)
        basis = (request.basis or '').strip()
        if not basis:
            raise PdfMappingError('Say what you checked (for example the page that prints the holder).', 422)
        now = datetime.now(timezone.utc).isoformat()
        relay = _relay(relayed, now)
        account = _account(session, case_id, account_id, lock=True)
        statements = _statement_rows(session, case_id, _statements(session, case_id, account, lock=True))
        if _revision(account, statements) != request.expected_revision:
            raise PdfMappingError('This account changed since you opened it. Reload; nothing was changed.', 409)
        meta = deepcopy(account.metadata_ or {})
        target = next((item for item in meta.get(HISTORY, []) if item.get('id') == request.correction_id), None)
        if target is None or target.get('kind') != 'correction' or target.get('undone_at'):
            raise PdfMappingError('This correction is not in the account history or was undone.', 409)
        if not origin_of(target):
            raise PdfMappingError('A person made this correction; there is nothing to confirm.', 409)
        confirmed = target.get('confirmed')
        if confirmed:
            if not (relay and confirmed.get('relayed') and confirmed.get('user_id') == str(actor.user_id)):
                raise PdfMappingError('This correction is already confirmed.', 409)
            confirmed.setdefault('later_relays', []).append(dict(relay, basis=basis))
        else:
            target['confirmed'] = dict(by=actor.name, by_email=actor.email, user_id=str(actor.user_id),
                                       at=at or now, basis=basis, **({'relayed': relay} if relay else {}))
        account.metadata_ = meta
        session.flush()
        result = account_details_state(session, case_id=case_id, account_id=account.id)
        result['confirmed'] = target['confirmed']
        if commit:
            session.commit()
        return result
    except Exception:
        session.rollback()
        raise
