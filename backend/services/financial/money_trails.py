"""Case-wide reviewed transfers and separately reasoned onward allocations.

The case lock serialises movement decisions, including manual pairs outside any
candidate window. Sources and prior revisions remain inspectable after correction.
"""
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from postgres.models.case import Case
from postgres.models.financial import FinancialTransaction, FinancialSourceDocument, FinancialStatementPeriod
from postgres.models.financial_money_trails import FinancialMoneyTrail
from services.financial.account_parties import _account_party_state, AccountPartyError
from services.financial.account_relationships import owners_on
from services.financial.transaction_query import to_view
from services.financial.money import get_currency


class TrailError(AccountPartyError):
    pass


class Allocation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    transaction_id: UUID
    amount_minor: str = Field(pattern=r'^[1-9][0-9]{0,24}$')


class TransferPart(BaseModel):
    model_config = ConfigDict(extra='forbid')
    transaction_id: UUID
    principal_minor: str = Field(pattern=r'^(0|[1-9][0-9]{0,24})$')
    fee_minor: str = Field(default='0', pattern=r'^(0|[1-9][0-9]{0,24})$')

    @model_validator(mode='after')
    def nonempty(self):
        if not int(self.principal_minor) + int(self.fee_minor):
            raise ValueError('Enter a transfer principal or fee for each selected entry.')
        return self


class ReferencedAccount(BaseModel):
    model_config = ConfigDict(extra='forbid')
    identifier_kind: Literal['account_number', 'clabe', 'iban'] = 'account_number'
    institution: str = Field(min_length=1, max_length=255)
    identifier: str = Field(min_length=1, max_length=255)
    holder: str | None = Field(default=None, max_length=255)


class TrailRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    expected_revision: int = Field(default=0, ge=0, strict=True)
    expected_source_revision: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    kind: Literal['transfer', 'allocation']
    debit_id: UUID | None = None
    credit_id: UUID | None = None
    referenced_account: ReferencedAccount | None = None
    transfer_parts: list[TransferPart] = Field(default_factory=list, max_length=100)
    payments: list[Allocation] = Field(default_factory=list, max_length=100)
    allow_fx: bool = Field(default=False, strict=True)
    reason: str = Field(min_length=1, max_length=4000)

    @model_validator(mode='after')
    def valid_shape(self):
        if not self.reason.strip(): raise ValueError('Explain the relationship being recorded.')
        if self.transfer_parts:
            if self.kind != 'transfer' or self.payments or self.debit_id or self.credit_id or self.referenced_account:
                raise ValueError('Use either a simple transfer or explicit split/fee entries, not both.')
        elif self.kind == 'transfer':
            if self.payments or not (self.debit_id or self.credit_id):
                raise ValueError('Choose the sending and receiving transfer entries, or one entry and a referenced account.')
            if bool(self.debit_id and self.credit_id) == bool(self.referenced_account):
                raise ValueError('Use a referenced account only when the other statement entry is missing.')
        elif not self.credit_id or not self.payments or self.debit_id or self.referenced_account or self.allow_fx:
            raise ValueError('Choose a receipt and its onward payment allocations.')
        ids = [str(i) for i in (self.debit_id, self.credit_id) if i] + [str(p.transaction_id) for p in [*self.payments, *self.transfer_parts]]
        if len(ids) != len(set(ids)): raise ValueError('Choose each payment once.')
        return self


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def _rows(session, case_id, ids):
    rows = list(session.scalars(select(FinancialTransaction).where(
        FinancialTransaction.case_id == case_id, FinancialTransaction.id.in_(ids))))
    by_id = {str(r.id): r for r in rows}
    if len(by_id) != len(ids): raise TrailError('A selected payment is not available in this case.', 404)
    for row in rows:
        document = session.get(FinancialSourceDocument, row.source_document_id)
        if (row.ledger_status != 'admitted' or row.superseded_by_id or not document
                or document.case_id != case_id or document.status != 'admitted'):
            raise TrailError('A selected payment changed or is excluded. Open its current reading before saving a trail.', 409)
        if row.amount_minor <= 0 or row.account.account_type == 'credit_card':
            raise TrailError('Money trails require positive bank-account payments. Review credit-card activity separately.')
    return by_id


def _day(row):
    return None if (row.provenance or {}).get('date_basis') == 'statement_end_ordering_only' else row.ordering_date.isoformat()


def _ancestors(session, case_id, ids):
    """Protect a corrected posting from being reused as a second movement."""
    found = set(ids)
    frontier = set(ids)
    while frontier:
        parents = {str(i) for i in session.scalars(select(FinancialTransaction.id).where(
            FinancialTransaction.case_id == case_id,
            FinancialTransaction.superseded_by_id.in_([UUID(i) for i in frontier])))}
        if parents & found: raise TrailError('Payment correction history is circular.', 409)
        found.update(parents); frontier = parents
    return found


def preview_trail(session, *, case_id, request):
    ids = [str(i) for i in (request.debit_id, request.credit_id) if i] + [str(p.transaction_id) for p in [*request.payments, *request.transfer_parts]]
    rows = _rows(session, case_id, [UUID(i) for i in ids])
    directory = _account_party_state(session, case_id=case_id)
    accounts = {a['id']: a for a in directory['accounts']}
    credit = rows.get(str(request.credit_id))
    debit = rows.get(str(request.debit_id))
    if credit and credit.direction != 'credit' or debit and debit.direction != 'debit':
        raise TrailError('Choose an incoming receipt and an outgoing debit in their correct roles.')
    warnings, common, rate, residual = [], [], None, None
    parts = None
    if request.transfer_parts:
        from services.financial.transfer_parts import assess_transfer_parts
        parts, common, rate, part_warnings = assess_transfer_parts(request, rows, accounts, _day, TrailError)
        warnings.extend(part_warnings)
    elif request.kind == 'transfer':
        if credit and debit:
            if credit.account_id == debit.account_id:
                raise TrailError('A transfer between accounts requires two different accounts.')
            if credit.currency == debit.currency:
                if credit.amount_minor != debit.amount_minor:
                    raise TrailError('The amounts differ. Keep fee or split postings separate; this pair is not an equal-value transfer.')
            elif not request.allow_fx:
                raise TrailError('Different currencies require an explicit exchange hypothesis. Both original amounts are retained.')
            else:
                with localcontext() as ctx:
                    ctx.prec = 36
                    source = Decimal(debit.amount_minor).scaleb(-get_currency(debit.currency).exponent)
                    destination = Decimal(credit.amount_minor).scaleb(-get_currency(credit.currency).exponent)
                    rate = format(destination / source, '.12g')
                warnings.append('The rate is implied by these entries. Fees, FX execution and payment identity still require evidence.')
            source_owners = {p['id']:p for p in owners_on(accounts[str(debit.account_id)], _day(debit))}
            target_owners = {p['id']:p for p in owners_on(accounts[str(credit.account_id)], _day(credit))}
            common = [source_owners[id] for id in sorted(source_owners.keys() & target_owners.keys())]
            if not common: warnings.append('Common ownership is not established for these payment dates.')
        else:
            warnings.append('Only one statement entry is available. The other account is a reference, with no imported balance or payment.')
    else:
        allocated = 0
        if not _day(credit): warnings.append('The receipt has no printed payment date; order must be supported in your explanation.')
        for item in request.payments:
            payment = rows[str(item.transaction_id)]
            amount = int(item.amount_minor)
            if payment.direction != 'debit' or payment.account_id != credit.account_id or payment.currency != credit.currency:
                raise TrailError('Onward allocations must use outgoing payments from the receiving account and currency. Link an exchange or account transfer separately.')
            if amount > payment.amount_minor: raise TrailError('An allocation exceeds its outgoing payment.')
            if _day(credit) and _day(payment) and _day(payment) < _day(credit):
                raise TrailError('An outgoing payment predates this receipt.')
            if not _day(payment) or _day(payment) == _day(credit): warnings.append('Same-day or undated entries do not establish exact payment order.')
            allocated += amount
        if allocated > credit.amount_minor: raise TrailError('The allocations exceed the receipt.')
        residual = str(credit.amount_minor - allocated)
        warnings.append('This is an investigator allocation, not proof of funding. Opening funds, intervening payments and missing statements may change the interpretation.')
    consumed = {}
    transfer_consumed = {}
    for saved in session.scalars(select(FinancialMoneyTrail).where(
            FinancialMoneyTrail.case_id == case_id, FinancialMoneyTrail.active.is_(True), FinancialMoneyTrail.id != request.id)):
        other = saved.details['input']
        if request.kind == 'transfer' and saved.kind == 'transfer':
            if other.get('transfer_parts'):
                quantities = {p['transaction_id']: int(p['principal_minor']) + int(p.get('fee_minor', '0')) for p in other['transfer_parts']}
            else:
                quantities = {p['key']: int(p['amount_minor']) for p in saved.details['payments']}
            for key, amount in quantities.items():
                transfer_consumed[key] = transfer_consumed.get(key, 0) + amount
        if request.kind == 'allocation' and saved.kind == 'allocation':
            allocated = sum(int(p['amount_minor']) for p in other['payments'])
            consumed[other['credit_id']] = consumed.get(other['credit_id'], 0) + allocated
            for p in other['payments']:
                consumed[p['transaction_id']] = consumed.get(p['transaction_id'], 0) + int(p['amount_minor'])
    if request.kind == 'transfer':
        quantities = {str(p.transaction_id): int(p.principal_minor) + int(p.fee_minor) for p in request.transfer_parts} if request.transfer_parts else {key: row.amount_minor for key, row in rows.items()}
        for key, amount in quantities.items():
            used = sum(transfer_consumed.get(ancestor, 0) for ancestor in _ancestors(session, case_id, [key]))
            if used + amount > rows[key].amount_minor:
                raise TrailError('A selected entry is already linked to a saved transfer. The combined principal and fees would exceed its amount. Review its existing links first.', 409)
            if parts:
                part = next(p for p in parts['entries'] if p['transaction_id'] == key)
                part['remaining_after_other_links_minor'] = str(rows[key].amount_minor - used - amount)
    if request.kind == 'allocation':
        requested = {str(request.credit_id): sum(int(p.amount_minor) for p in request.payments),
            **{str(p.transaction_id):int(p.amount_minor) for p in request.payments}}
        for id, amount in requested.items():
            used = sum(consumed.get(a, 0) for a in _ancestors(session, case_id, [id]))
            if used + amount > rows[id].amount_minor:
                raise TrailError('A payment is already allocated in another saved trail. The combined allocations would exceed its amount.', 409)
        residual = str(credit.amount_minor - requested[str(request.credit_id)] - sum(
            consumed.get(a, 0) for a in _ancestors(session, case_id, [str(request.credit_id)])))
    snapshots = [to_view(rows[id], account=rows[id].account, account_parties=accounts).to_json() for id in ids]
    ownership = {str(r.account_id): accounts[str(r.account_id)] for r in rows.values()}
    context = None
    if request.kind == 'allocation':
        period = session.get(FinancialStatementPeriod,credit.statement_period_id) if credit.statement_period_id else None
        upper = max(rows[str(p.transaction_id)].ordering_date for p in request.payments)
        sequence = list(session.scalars(select(FinancialTransaction).join(FinancialSourceDocument,
            FinancialTransaction.source_document_id == FinancialSourceDocument.id).where(
                FinancialTransaction.case_id == case_id, FinancialTransaction.account_id == credit.account_id,
                FinancialTransaction.currency == credit.currency, FinancialTransaction.ledger_status == 'admitted',
                FinancialTransaction.superseded_by_id.is_(None), FinancialSourceDocument.status == 'admitted',
                FinancialTransaction.ordering_date >= credit.ordering_date, FinancialTransaction.ordering_date <= upper)
            .order_by(FinancialTransaction.ordering_date,FinancialTransaction.id)))
        sequence_views = [to_view(r,account=r.account,account_parties=accounts).to_json() for r in sequence]
        context = dict(currency=credit.currency,
            opening_balance_minor=str(period.opening_balance_minor) if period and period.opening_balance_minor is not None else None,
            opening_balance_source=period.opening_balance_source if period else 'absent',
            period_start=period.period_start.isoformat() if period and period.period_start else None,
            payments=sequence_views[:100],payment_count=len(sequence_views),sequence_revision=digest(sequence_views),
            limitation='The opening balance is for the statement period, not necessarily immediately before the receipt. Entries on the same day have no established order. Imported entries do not establish that coverage is complete.')
    source_revision = digest({'payments': snapshots, 'ownership': ownership, 'account_context':context})
    return dict(case_id=str(case_id), kind=request.kind, input=request.model_dump(mode='json', exclude={'expected_revision', 'expected_source_revision'}),
        payments=snapshots, ownership=ownership, common_holders=common,
        internal_transfer=bool(common) and bool(parts or (credit and debit)) and request.kind == 'transfer',
        transfer_breakdown=parts,
        implied_exchange_rate=rate, receipt_unallocated_minor=residual,
        warnings=list(dict.fromkeys(warnings)), source_revision=source_revision, account_context=context)


def _current_status(session, record):
    try:
        request = TrailRequest.model_validate(record.details['input'])
        current = preview_trail(session, case_id=record.case_id, request=request)
        return 'current' if current['source_revision'] == record.details['source_revision'] else 'source_changed'
    except (TrailError, AccountPartyError):
        return 'source_changed'


def trail_view(session, record):
    candidates = []
    if record.active and record.kind == 'transfer' and record.details['input'].get('referenced_account'):
        from postgres.models.financial import FinancialAccount
        from services.financial.account_identity import matches_identifier
        reference = record.details['input']['referenced_account']
        available = record.details['payments'][0]
        matching_accounts = [a.id for a in session.scalars(select(FinancialAccount).where(FinancialAccount.case_id == record.case_id))
            if str(a.id) != available['account_id'] and not (a.metadata_ or {}).get('referenced_only')
            and matches_identifier(a, reference.get('identifier_kind', 'account_number'), reference['identifier'])]
        if matching_accounts:
            candidates = list(session.scalars(select(FinancialTransaction).join(FinancialSourceDocument,
                FinancialSourceDocument.id == FinancialTransaction.source_document_id).where(
                    FinancialTransaction.case_id == record.case_id, FinancialSourceDocument.case_id == record.case_id,
                    FinancialTransaction.account_id.in_(matching_accounts), FinancialTransaction.ledger_status == 'admitted',
                    FinancialTransaction.superseded_by_id.is_(None), FinancialSourceDocument.status == 'admitted',
                    FinancialTransaction.amount_minor > 0,
                    FinancialTransaction.direction == ('credit' if available['direction'] == 'debit' else 'debit'))
                .order_by(FinancialTransaction.ordering_date.desc(), FinancialTransaction.id).limit(51)))
            candidates = [to_view(p, account=p.account).to_json() for p in candidates if p.account.account_type != 'credit_card']
    return dict(id=str(record.id), case_id=str(record.case_id), kind=record.kind, revision=record.revision,
        active=record.active, status=_current_status(session, record) if record.active else 'removed',
        details=record.details, history=record.history, matching_entries=candidates[:50], matching_entries_truncated=len(candidates) > 50)


def list_trails(session, *, case_id):
    rows = list(session.scalars(select(FinancialMoneyTrail).where(FinancialMoneyTrail.case_id == case_id)
        .order_by(FinancialMoneyTrail.created_at, FinancialMoneyTrail.id)))
    return dict(case_id=str(case_id), trails=[trail_view(session, row) for row in rows])


def save_trail(session, *, case_id, request, actor):
    try:
        if session.scalar(select(Case.id).where(Case.id == case_id).with_for_update()) is None:
            raise TrailError('Case not found.', 404)
        record = session.get(FinancialMoneyTrail, request.id)
        if record and record.case_id != case_id: raise TrailError('Trail not found in this case.', 404)
        payload = request.model_dump(mode='json', exclude={'expected_revision', 'expected_source_revision'})
        if record and record.active and request.expected_revision == record.revision - 1 and TrailRequest.model_validate(record.details['input']).model_dump(mode='json', exclude={'expected_revision', 'expected_source_revision'}) == payload:
            # A lost acknowledgement returns the same durable receipt.
            result = trail_view(session, record); session.commit(); return result
        if request.expected_revision != (record.revision if record else 0):
            raise TrailError('The saved trail changed. Reopen it before editing.', 409)
        ids = [i for i in (request.debit_id, request.credit_id) if i] + [p.transaction_id for p in [*request.payments, *request.transfer_parts]]
        # Follow the correction writers' document → period → payment lock order.
        # Another investigator cannot alter a selected reading between the
        # preview revision check and the durable saved interpretation.
        document_ids = select(FinancialTransaction.source_document_id).where(
            FinancialTransaction.case_id == case_id, FinancialTransaction.id.in_(ids))
        list(session.scalars(select(FinancialSourceDocument).where(
            FinancialSourceDocument.case_id == case_id, FinancialSourceDocument.id.in_(document_ids))
            .order_by(FinancialSourceDocument.id).with_for_update().execution_options(populate_existing=True)))
        list(session.scalars(select(FinancialStatementPeriod).where(
            FinancialStatementPeriod.case_id == case_id, FinancialStatementPeriod.source_document_id.in_(document_ids))
            .order_by(FinancialStatementPeriod.id).with_for_update().execution_options(populate_existing=True)))
        list(session.scalars(select(FinancialTransaction).where(
            FinancialTransaction.case_id == case_id, FinancialTransaction.id.in_(ids))
            .order_by(FinancialTransaction.id).with_for_update().execution_options(populate_existing=True)))
        details = preview_trail(session, case_id=case_id, request=request)
        if request.expected_source_revision != details['source_revision']:
            raise TrailError('Payment readings or ownership changed. Review the new preview before saving.', 409)
        if record and record.kind != request.kind: raise TrailError('A transfer and an onward allocation are separate records.')
        if not record:
            record = FinancialMoneyTrail(id=request.id, case_id=case_id, kind=request.kind,
                revision=0, details={}, history=[], active=True)
            session.add(record)
        event = dict(revision=record.revision+1, actor=actor.email, recorded_at=datetime.now(timezone.utc).isoformat(),
            reason=request.reason.strip(), before=record.details or None, after=details, action='save')
        record.details, record.revision, record.active = details, record.revision+1, True
        record.history = [*record.history, event]
        session.flush()
        result = trail_view(session, record)
        session.commit()
        return result
    except Exception:
        session.rollback(); raise


def remove_trail(session, *, case_id, id, expected_revision, reason, actor):
    try:
        session.scalar(select(Case.id).where(Case.id == case_id).with_for_update())
        record = session.get(FinancialMoneyTrail, id)
        if not record or record.case_id != case_id: raise TrailError('Trail not found in this case.', 404)
        if not reason.strip(): raise TrailError('Explain why the link is being removed.')
        if not record.active:
            result = trail_view(session, record); session.commit(); return result
        if record.revision != expected_revision: raise TrailError('The saved trail changed. Reopen it before removing.', 409)
        record.history = [*record.history, dict(revision=record.revision+1, actor=actor.email,
            recorded_at=datetime.now(timezone.utc).isoformat(), reason=reason.strip(), action='remove', before=record.details, after=None)]
        record.active, record.revision = False, record.revision+1
        session.flush(); result = trail_view(session, record); session.commit(); return result
    except Exception:
        session.rollback(); raise
