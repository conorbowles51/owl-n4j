"""Set or correct an account's type after import, without re-reading any PDF.

The type decides how a statement's printed balances read. A credit card prints
the amount owed, which the ledger holds as a negative balance; a bank account
prints the money held. When the first reading missed that an account is a card
(or took a bank account for one), the investigator changes the type here:

- every saved statement of the account switches convention through one
  reviewed record (``statement_convention_review``), with the sealed reading
  and import request left untouched and the previous convention kept in
  its history, and the period and running balances are re-signed;
- each statement is reconciled again from the saved values;
- rows the investigator entered or corrected while the old convention applied
  are flagged. When a statement does not add up after the change but adds up
  exactly with all of its flagged rows flipped, those rows are flipped as part
  of the change (``AUTO_FLIP_REASON``); otherwise they stay flagged for the
  confirmed action ``flip_flagged_rows``. Both go through the ordinary
  transaction correction chain, so the entered values stay in history.

Read-only helpers suggest a type from printed card wording and find accounts
that are the same printed card, for the existing reversible account merge.
"""
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from postgres.models.evidence import EvidenceDocumentText
from postgres.models.financial import (
    FinancialAccount, FinancialSourceDocument, FinancialStatementPeriod, FinancialTransaction,
)
from services.financial.pdf_candidates import PdfMappingError, _digest
from services.financial.statement_details import CONVENTION_REVIEW, effective_convention

ACCOUNT_TYPES = {'credit_card': 'liability_owed', 'checking': 'asset_balance', 'savings': 'asset_balance'}
TYPE_LABELS = {'credit_card': 'credit card', 'checking': 'bank account (checking)',
               'savings': 'bank account (savings)', 'bank': 'bank account', 'other': 'other account'}
# Types a reader assigns when it takes an account for a bank account or does
# not know. A card-wording suggestion is offered only for these.
NOT_CARD_TYPES = (None, '', 'bank', 'other', 'checking', 'savings')
CARD_SIGNALS = (
    ('new balance', re.compile(r'\bnew\s+balance\b', re.I)),
    ('minimum payment due', re.compile(r'\bminimum\s+(?:payment|amount)\s+due\b', re.I)),
    ('credit limit', re.compile(r'\bcredit\s+(?:limit|line)\b', re.I)),
    ('payment due date', re.compile(r'\bpayment\s+due\s+date\b', re.I)),
)
FLIP_REASON = ('Entered while this account was treated as a {before}; direction reversed for a {after} '
               'after the account type was corrected (confirmed by the investigator).')
AUTO_FLIP_REASON = ('Entered while this account was treated as a {before}; direction reversed for a {after} '
                    'after the account type was corrected, because the statement adds up exactly with it reversed '
                    'and not without.')


class AccountTypeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    account_type: Literal['credit_card', 'checking', 'savings']
    expected_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    reason: str = Field(default='', max_length=2000)


class FlipRowsRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_document_id: UUID
    transaction_ids: list[UUID] = Field(min_length=1, max_length=500)
    expected_revision: str = Field(pattern=r'^[a-f0-9]{64}$')


def _account(session, case_id, account_id, lock=False):
    query = select(FinancialAccount).where(FinancialAccount.id == account_id, FinancialAccount.case_id == case_id)
    account = session.scalar(query.with_for_update() if lock else query)
    if account is None:
        raise PdfMappingError('Account not found in this case.', 404)
    return account


def _statements(session, case_id, account, lock=False):
    """The account's current saved statement reviews with their single period."""
    query = (select(FinancialStatementPeriod, FinancialSourceDocument)
        .join(FinancialSourceDocument, FinancialSourceDocument.id == FinancialStatementPeriod.source_document_id)
        .where(FinancialStatementPeriod.case_id == case_id, FinancialSourceDocument.case_id == case_id,
               FinancialStatementPeriod.account_id == account.id, FinancialSourceDocument.status == 'admitted',
               FinancialSourceDocument.document_type == 'statement_review')
        .order_by(FinancialStatementPeriod.period_start, FinancialStatementPeriod.id))
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return [(document, period) for period, document in session.execute(query).all()
            if not (document.metadata_ or {}).get('financial_import_removal')]


def _rows(session, document, period):
    return list(session.scalars(select(FinancialTransaction).where(
        FinancialTransaction.case_id == document.case_id, FinancialTransaction.source_document_id == document.id,
        FinancialTransaction.statement_period_id == period.id, FinancialTransaction.superseded_by_id.is_(None),
        FinancialTransaction.ledger_status == 'admitted').order_by(FinancialTransaction.row_index, FinancialTransaction.id)))


def _entered_by_investigator(row, resolved_ids):
    """A row whose direction a person chose: added in review, completed from an
    incomplete record, corrected after import, or re-directed in review."""
    provenance = row.provenance or {}
    review = provenance.get('statement_import_review') or {}
    original = (provenance.get('statement_import_original') or {}).get('fields') or {}
    return bool(str(review.get('id', '')).startswith('manual:') or str(row.id) in resolved_ids
                or provenance.get('correction')
                or (review.get('direction') and original.get('direction') and review['direction'] != original['direction']))


def _aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _identity(opening, closing, rows, flipped=()):
    if opening is None or closing is None:
        return None
    total = opening
    for row in rows:
        credit = (row.direction == 'credit') != (row.id in flipped)
        total += row.amount_minor if credit else -row.amount_minor
    return total == closing


def _statement_state(session, document, period, account, convention_after=None):
    """Current convention, reconciliation and investigator rows of one statement.

    With ``convention_after`` the state is projected as if the type changed:
    stored balances re-signed, nothing written."""
    metadata = document.metadata_ or {}
    before = effective_convention(metadata, account.account_type) or 'asset_balance'
    after = convention_after or before
    sign = 1 if after == before else -1
    opening = period.opening_balance_minor * sign if period.opening_balance_minor is not None else None
    closing = period.closing_balance_minor * sign if period.closing_balance_minor is not None else None
    rows = _rows(session, document, period)
    review = metadata.get(CONVENTION_REVIEW) or {}
    resolved = {str(item.get('resolved_transaction_id')) for item in metadata.get('statement_incomplete_records', [])
                if item.get('resolved_transaction_id')}
    changing = after != before
    # Rows entered before the latest convention change were entered under the
    # previous convention. Rows entered (or flipped) afterwards are not
    # flagged again, so a confirmed flip can never be applied twice.
    changed_at = (datetime.fromisoformat(review['at']) if not changing and review.get('at')
                  and review.get('previous_convention') not in (None, review.get('balance_convention')) else None)
    flipped = set(review.get('flipped_transaction_ids', []))
    flagged = [row for row in rows if _entered_by_investigator(row, resolved) and (
        changing or (changed_at is not None and row.created_at is not None and _aware(row.created_at) <= changed_at
                     and str(row.id) not in flipped))]
    flagged_ids = {row.id for row in flagged}
    return dict(
        source_document_id=str(document.id), evidence_file_id=str(document.evidence_file_id),
        period_id=str(period.id), period_start=period.period_start.isoformat() if period.period_start else None,
        period_end=period.period_end.isoformat() if period.period_end else None, currency=period.currency,
        convention_before=before, convention_after=after,
        reconciles=_identity(opening, closing, rows),
        reconciles_with_flagged_flipped=_identity(opening, closing, rows, flagged_ids) if flagged else None,
        # Flipped with the type change: it adds up exactly with every flagged
        # row reversed and does not add up as entered.
        auto_flip=bool(flagged) and _identity(opening, closing, rows) is False
        and _identity(opening, closing, rows, flagged_ids) is True,
        flagged_rows=[dict(transaction_id=str(row.id), date=(row.transaction_date or row.posted_date or row.effective_date).isoformat()
                           if (row.transaction_date or row.posted_date or row.effective_date) else None,
                           description=row.description or '', amount_minor=str(row.amount_minor), direction=row.direction,
                           proposed_direction='debit' if row.direction == 'credit' else 'credit') for row in flagged])


def card_signals(session, documents):
    """Printed card wording on the statements' own pages."""
    found = set()
    texts = {}
    for document in documents:
        if document.evidence_file_id not in texts:
            texts[document.evidence_file_id] = session.get(EvidenceDocumentText, document.evidence_file_id)
        text = texts[document.evidence_file_id]
        if text is None:
            continue
        original = (document.metadata_ or {}).get('statement_import_original') or {}
        pages = set(original.get('statement_page_numbers') or original.get('page_numbers') or [])
        spans = [(loc.get('start_char'), loc.get('end_char')) for loc in text.source_locations or []
                 if loc.get('kind', 'page') == 'page' and (not pages or loc.get('page_number') in pages)
                 and isinstance(loc.get('start_char'), int) and isinstance(loc.get('end_char'), int)]
        content = ' '.join(text.content[start:end] for start, end in spans) if spans else ('' if pages else text.content)
        found.update(label for label, pattern in CARD_SIGNALS if pattern.search(content))
    return sorted(found)


def _revision(account, statements):
    return _digest(dict(account=str(account.id), account_type=account.account_type, statements=statements))


def preview_account_type(session, *, case_id, account_id, account_type):
    if account_type not in ACCOUNT_TYPES:
        raise PdfMappingError('Choose credit card or bank account (checking or savings).', 422)
    account = _account(session, case_id, account_id)
    statements = [_statement_state(session, document, period, account, ACCOUNT_TYPES[account_type])
                  for document, period in _statements(session, case_id, account)]
    current = [_statement_state(session, document, period, account) for document, period in _statements(session, case_id, account)]
    return dict(case_id=str(case_id), account_id=str(account.id), account_type_before=account.account_type or '',
        account_type_after=account_type, statements=statements,
        changed_statements=sum(s['convention_before'] != s['convention_after'] for s in statements),
        flagged_rows=sum(len(s['flagged_rows']) for s in statements),
        auto_flip_rows=sum(len(s['flagged_rows']) for s in statements if s['auto_flip']),
        revision=_revision(account, current))


def account_type_state(session, *, case_id, account_id):
    """The account's type, its statements' conventions and any rows still flagged."""
    account = _account(session, case_id, account_id)
    pairs = _statements(session, case_id, account)
    statements = [_statement_state(session, document, period, account) for document, period in pairs]
    signals = card_signals(session, [document for document, _ in pairs])
    return dict(case_id=str(case_id), account_id=str(account.id), account_type=account.account_type or '',
        label=(account.metadata_ or {}).get('display_label') or account.identifier_as_printed or account.holder_name or 'Account not identified',
        institution=account.institution_name or '', statements=statements, card_signals=signals,
        suggested_type='credit_card' if account.account_type in NOT_CARD_TYPES and len(signals) >= 2 else None,
        history=(account.metadata_ or {}).get('account_type_history', []),
        flagged_rows=sum(len(s['flagged_rows']) for s in statements),
        revision=_revision(account, statements))


def save_account_type(session, *, case_id, account_id, request, actor):
    from services.financial.reconcile import reconcile_period
    from services.financial.saved_statement_admission import refresh_saved_assessment
    try:
        account = _account(session, case_id, account_id, lock=True)
        pairs = _statements(session, case_id, account, lock=True)
        current = [_statement_state(session, document, period, account) for document, period in pairs]
        if _revision(account, current) != request.expected_revision:
            raise PdfMappingError('This account changed since you opened it. Reload before changing its type; nothing was changed.', 409)
        before_type = account.account_type
        after = ACCOUNT_TYPES[request.account_type]
        now = datetime.now(timezone.utc).isoformat()
        who = dict(actor_id=str(actor.user_id) if actor.user_id else None, actor_name=actor.name, actor_email=actor.email)
        for document, period in pairs:
            metadata = deepcopy(document.metadata_ or {})
            previous = effective_convention(metadata, before_type) or 'asset_balance'
            if previous == after:
                continue
            old = metadata.get(CONVENTION_REVIEW)
            review = dict(account_type=request.account_type, balance_convention=after, previous_convention=previous,
                previous_account_type=before_type or '', at=now, reason=request.reason.strip(), **who,
                flipped_transaction_ids=[],
                history=[*((old or {}).get('history', [])), *([{k: v for k, v in old.items() if k != 'history'}] if old else [])])
            metadata[CONVENTION_REVIEW] = review
            metadata[CONVENTION_REVIEW + '_sha256'] = _digest(review)
            details = metadata.get('statement_details_review')
            if details:
                # The later details review signs its page-cited balances with
                # its own convention; keep it consistent and record why.
                details = {**details, 'balance_convention': after}
                metadata['statement_details_review'] = details
                metadata['statement_details_review_sha256'] = _digest(details)
            # Ledger balances are the printed balances with the convention's
            # sign; the printed values themselves do not change.
            for role in ('opening', 'closing'):
                value = getattr(period, role + '_balance_minor')
                if value is not None:
                    setattr(period, role + '_balance_minor', -value)
            for row in session.scalars(select(FinancialTransaction).where(
                    FinancialTransaction.case_id == case_id, FinancialTransaction.source_document_id == document.id)
                    .with_for_update()):
                if row.running_balance_minor is not None:
                    row.running_balance_minor = -row.running_balance_minor
            document.metadata_ = metadata
            session.flush()
            reconcile_period(session, period)
            refresh_saved_assessment(session, document, period)
        account_metadata = deepcopy(account.metadata_ or {})
        account_metadata.setdefault('account_type_history', []).append(dict(
            before=before_type or '', after=request.account_type, at=now, reason=request.reason.strip(), **who))
        account.metadata_ = account_metadata
        account.account_type = request.account_type
        session.flush()
        state = account_type_state(session, case_id=case_id, account_id=account_id)
        auto = [s for s in state['statements'] if s['auto_flip']]
        for statement in auto:
            _flip(session, case_id=case_id, account=account, source_document_id=UUID(statement['source_document_id']),
                  rows=statement['flagged_rows'], actor=actor, template=AUTO_FLIP_REASON)
        result = account_type_state(session, case_id=case_id, account_id=account_id) if auto else state
        result['auto_flipped_rows'] = sum(len(s['flagged_rows']) for s in auto)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise


def _flip(session, *, case_id, account, source_document_id, rows, actor, template):
    """Reverse the direction of the given flagged rows through the correction chain."""
    from services.financial.correction_preview import preview_amount_correction
    from services.financial.corrections import correct_transaction
    review = (session.get(FinancialSourceDocument, source_document_id).metadata_ or {}).get(CONVENTION_REVIEW) or {}
    reason = template.format(before=TYPE_LABELS.get(review.get('previous_account_type') or '', 'bank account')
                             if review.get('previous_convention') == 'asset_balance' else 'credit card',
                             after=TYPE_LABELS.get(account.account_type or '', 'account'))
    replacements = []
    for row in rows:
        identifier = row['transaction_id']
        preview = preview_amount_correction(session, case_id=case_id, transaction_id=UUID(identifier),
            amount_minor=int(row['amount_minor']), direction=row['proposed_direction'])
        result = correct_transaction(session, case_id=case_id, transaction_id=UUID(identifier),
            amount_minor=int(row['amount_minor']), direction=row['proposed_direction'],
            expected_revision=preview['document_revision'], actor=actor, reason=reason, commit=False)
        replacements.append(result['replacement_id'])
    document = session.get(FinancialSourceDocument, source_document_id)
    metadata = deepcopy(document.metadata_ or {})
    review = dict(metadata[CONVENTION_REVIEW])
    review['flipped_transaction_ids'] = [*review.get('flipped_transaction_ids', []),
                                         *(row['transaction_id'] for row in rows), *replacements]
    metadata[CONVENTION_REVIEW] = review
    metadata[CONVENTION_REVIEW + '_sha256'] = _digest(review)
    document.metadata_ = metadata
    session.flush()


def flip_flagged_rows(session, *, case_id, account_id, request, actor):
    """Reverse the direction of rows flagged after a type change, once confirmed.

    Only the rows currently flagged on that statement can be flipped, all
    through the correction chain (original kept, adjudication recorded)."""
    try:
        account = _account(session, case_id, account_id, lock=True)
        state = account_type_state(session, case_id=case_id, account_id=account_id)
        if state['revision'] != request.expected_revision:
            raise PdfMappingError('This account changed since you opened it. Reload before flipping rows; nothing was changed.', 409)
        statement = next((s for s in state['statements'] if s['source_document_id'] == str(request.source_document_id)), None)
        flagged = {row['transaction_id']: row for row in (statement or {}).get('flagged_rows', [])}
        chosen = [str(identifier) for identifier in request.transaction_ids]
        if not statement or not chosen or len(set(chosen)) != len(chosen) or any(identifier not in flagged for identifier in chosen):
            raise PdfMappingError('Only rows flagged on this statement after its account type changed can be flipped here.', 409)
        _flip(session, case_id=case_id, account=account, source_document_id=request.source_document_id,
              rows=[flagged[identifier] for identifier in chosen], actor=actor, template=FLIP_REASON)
        result = account_type_state(session, case_id=case_id, account_id=account_id)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise


def _luhn(digits):
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char) * (2 if index % 2 else 1)
        total += value - 9 if value > 9 else value
    return total % 10 == 0


def full_card_number(value):
    """The digits of a complete printed card number, or None (masked or not a card)."""
    if not value or re.search(r'[xX*•]', value):
        return None
    digits = re.sub(r'\D', '', value)
    return digits if 13 <= len(digits) <= 19 and _luhn(digits) else None


def bank_root(value):
    """A bank name without product words, so "<bank> card" and "<bank>" compare equal."""
    from services.financial.account_consolidation import bank_key
    words = [word for word in bank_key(value).split() if word not in ('card', 'cards', 'credit')]
    return ' '.join(words)


def account_type_review(session, *, case_id):
    """Suggestions for Review accounts: card wording on non-card accounts, and
    accounts that are the same printed card (offered for the reversible merge)."""
    from services.financial.account_consolidation import canonical_map
    accounts = list(session.scalars(select(FinancialAccount).where(FinancialAccount.case_id == case_id)
        .order_by(FinancialAccount.created_at, FinancialAccount.id)))
    mapping = canonical_map(session, case_id)
    rows = []
    groups = {}
    for account in accounts:
        pairs = _statements(session, case_id, account)
        signals = card_signals(session, [document for document, _ in pairs]) if account.account_type in NOT_CARD_TYPES and pairs else []
        flagged = sum(len(_statement_state(session, document, period, account)['flagged_rows']) for document, period in pairs
                      if (document.metadata_ or {}).get(CONVENTION_REVIEW))
        rows.append(dict(account_id=str(account.id),
            label=(account.metadata_ or {}).get('display_label') or account.identifier_as_printed or account.holder_name or 'Account not identified',
            institution=account.institution_name or '', account_type=account.account_type or '',
            statement_count=len(pairs), card_signals=signals,
            suggested_type='credit_card' if len(signals) >= 2 else None, flagged_rows=flagged))
        number = full_card_number(account.identifier_as_printed) if not (account.metadata_ or {}).get('identity_provisional') else None
        if number:
            groups.setdefault((bank_root(account.institution_name), number, account.currency), []).append(account)
    same_card = []
    for (_, _, _), members in groups.items():
        if len(members) > 1 and len({mapping.get(member.id, member.id) for member in members}) > 1:
            same_card.append(dict(account_ids=[str(member.id) for member in members],
                reason='The same full card number is printed for these accounts by the same bank.'))
    return dict(case_id=str(case_id), accounts=rows, same_card=same_card)
