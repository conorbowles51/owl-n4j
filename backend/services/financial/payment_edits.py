"""Atomic single/selection edits using the existing source correction history."""
import hashlib
import json
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from postgres.models.financial import FinancialSourceDocument, FinancialStatementPeriod, FinancialTransaction
from services.financial.payment_labels import LabelTarget, PaymentLabelsRequest, update_payment_labels, PaymentLabelsError
from services.financial.correction_fields import correction_fields, json_fields, DATE_FIELDS, TEXT_FIELDS
from services.financial.correction_preview import preview_amount_correction, CorrectionPreviewError
from services.financial.corrections import correct_transaction
from services.financial.duplicate_decisions import duplicate_revision
from services.financial.transaction_query import to_view
from services.financial.money import get_currency

LABELS = {'from_name', 'to_name', 'category', 'counterparty_link'}
FIELDS = LABELS | DATE_FIELDS | TEXT_FIELDS | {'amount', 'direction', 'running_balance'}

class PaymentEditRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    transactions: list[LabelTarget] = Field(min_length=1)
    changes: dict[str, str | None]
    expected_revision: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')


def _money(value, currency, signed=False):
    import re
    if not isinstance(value, str) or not re.fullmatch(r'-?\d+(?:\.\d+)?' if signed else r'\d+(?:\.\d+)?', value.strip()):
        raise PaymentLabelsError('Enter a decimal amount without commas or a currency symbol.', 422)
    text = value.strip()
    negative = text.startswith('-')
    whole, _, fraction = text.lstrip('-').partition('.')
    scale = get_currency(currency).exponent
    if len(fraction) > scale:
        raise PaymentLabelsError(f'{currency} supports {scale} decimal places.', 422)
    value = int(whole + fraction.ljust(scale, '0')) * (-1 if negative else 1)
    if not (-9223372036854775808 if signed else 0) <= value <= 9223372036854775807:
        raise PaymentLabelsError('The amount is outside the supported range.', 422)
    return value


def _prepare(session, case_id, request):
    changes = request.changes
    if not changes or set(changes) - FIELDS:
        raise PaymentLabelsError('Choose transaction fields to edit.', 422)
    ids = [target.id for target in request.transactions]
    if len(set(ids)) != len(ids):
        raise PaymentLabelsError('A transaction was selected twice.', 422)
    document_ids = set(session.scalars(select(FinancialTransaction.source_document_id).where(
        FinancialTransaction.case_id == case_id, FinancialTransaction.id.in_(ids))))
    documents = list(session.scalars(select(FinancialSourceDocument).where(
        FinancialSourceDocument.case_id == case_id, FinancialSourceDocument.id.in_(document_ids)
    ).order_by(FinancialSourceDocument.id).with_for_update().execution_options(populate_existing=True)))
    list(session.scalars(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id.in_(document_ids))
        .order_by(FinancialStatementPeriod.id).with_for_update().execution_options(populate_existing=True)))
    rows = list(session.scalars(select(FinancialTransaction).where(FinancialTransaction.case_id == case_id,
        FinancialTransaction.id.in_(ids)).order_by(FinancialTransaction.id).with_for_update().execution_options(populate_existing=True)))
    if len(rows) != len(ids):
        raise PaymentLabelsError('One or more selected transactions are unavailable in this case.', 404)
    versions = {target.id: target.version for target in request.transactions}
    for row in rows:
        if row.ledger_status != 'admitted' or row.superseded_by_id:
            raise PaymentLabelsError('A selected transaction was replaced or removed. Reload the selection.')
        if (row.metadata_ or {}).get('investigation_labels', {}).get('version', 0) != versions[row.id]:
            raise PaymentLabelsError('Someone edited a selected transaction. Reload the selection.')
    if any(key in changes for key in ('amount', 'running_balance')) and len({row.currency for row in rows}) != 1:
        raise PaymentLabelsError('Select transactions in one currency before applying the same amount or balance.', 422)
    labels = {key: value for key, value in changes.items() if key in LABELS}
    if labels:
        if 'counterparty_link' in labels:
            raw = labels['counterparty_link']
            try:
                labels['counterparty_link'] = json.loads(raw) if raw else None
            except (ValueError, TypeError) as exc:
                raise PaymentLabelsError('Choose a person, business or bank account from this case.', 422) from exc
        validated = PaymentLabelsRequest(transactions=request.transactions, **labels)
        labels = validated.model_dump(include=LABELS, exclude_unset=True)
        if any(value is None for key, value in labels.items() if key != 'counterparty_link'):
            raise PaymentLabelsError('Use an empty name to clear it.', 422)
        if validated.counterparty_link:
            from services.financial.payment_counterparty_link import resolve_link
            from services.financial.account_parties import AccountPartyError
            try:
                resolved_link = resolve_link(session, case_id=case_id, link=validated.counterparty_link)
            except AccountPartyError as exc:
                raise PaymentLabelsError(str(exc), exc.status_code) from exc
        else:
            resolved_link = None
    fields = {key: (value or None) for key, value in changes.items() if key in DATE_FIELDS | TEXT_FIELDS}
    correction_fields(fields)
    plans, examples = [], []
    for row in rows:
        row_fields = dict(fields)
        if 'running_balance' in changes:
            row_fields['running_balance_minor'] = str(_money(changes['running_balance'], row.currency, True)) if changes['running_balance'] else None
        amount = _money(changes['amount'], row.currency) if 'amount' in changes else row.amount_minor
        direction = changes.get('direction', row.direction)
        if direction not in ('credit', 'debit'):
            raise PaymentLabelsError('Choose money in / credit or money out / debit.', 422)
        effective = to_view(row, account=row.account).to_json()
        parsed = correction_fields(row_fields)
        needs_correction = amount != row.amount_minor or direction != row.direction or any(getattr(row, key) != value for key, value in parsed.items())
        if needs_correction:
            preview = preview_amount_correction(session, case_id=case_id, transaction_id=row.id, amount_minor=amount, direction=direction, fields=row_fields)
            if not preview['verification']['can_record']:
                raise PaymentLabelsError(preview['verification']['reason'])
        plans.append((row, amount, direction, row_fields, needs_correction))
        if len(examples) < 50:
            after = {**{key: effective.get(key) for key in changes}, **labels, **json_fields(parsed)}
            if 'amount' in changes: after['amount_minor'] = str(amount)
            if 'direction' in changes: after['direction'] = direction
            if 'counterparty_link' in changes:
                after['counterparty_link'] = resolved_link['label'] if resolved_link else None
                effective['counterparty_link'] = (effective.get('counterparty_link') or {}).get('label')
                side = 'from_name' if direction == 'credit' else 'to_name'
                after[side] = resolved_link['label'] if resolved_link else row.counterparty_raw
            keys = (set(changes) - {'amount', 'running_balance'}) | ({'amount_minor'} if 'amount' in changes else set()) | ({'running_balance_minor'} if 'running_balance' in changes else set())
            if 'counterparty_link' in changes:
                keys.add(side)
            examples.append(dict(id=str(row.id), description=row.description, currency=row.currency,
                before={key: effective.get(key) for key in keys}, after={key: after[key] for key in keys}))
    state = dict(reviewed_identity=resolved_link if 'counterparty_link' in labels else None, case_id=str(case_id), request=request.model_dump(mode='json', exclude={'expected_revision'}),
        documents={str(doc.id): duplicate_revision(session, doc) for doc in documents})
    revision = hashlib.sha256(json.dumps(state, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return dict(case_id=str(case_id), revision=revision, count=len(rows), fields=sorted(changes), examples=examples), plans, labels


def preview_payment_edits(session, *, case_id, request):
    try:
        return _prepare(session, case_id, request)[0]
    finally:
        session.rollback()


def save_payment_edits(session, *, case_id, request, actor):
    try:
        preview, plans, labels = _prepare(session, case_id, request)
        if request.expected_revision != preview['revision']:
            raise PaymentLabelsError('The selection changed. Review these edits again before saving.')
        replacements = []
        targets = []
        for original, amount, direction, fields, needs_correction in plans:
            id = original.id
            if needs_correction:
                document = session.get(FinancialSourceDocument, original.source_document_id)
                result = correct_transaction(session, case_id=case_id, transaction_id=original.id,
                    amount_minor=amount, direction=direction, fields=fields,
                    expected_revision=duplicate_revision(session, document), actor=actor,
                    reason='Transaction fields edited from the investigator transaction table.', commit=False)
                id = UUID(result['replacement_id'])
            row = session.get(FinancialTransaction, id)
            targets.append(dict(id=id, version=(row.metadata_ or {}).get('investigation_labels', {}).get('version', 0)))
            replacements.append(dict(previous_id=str(original.id), id=str(id)))
        if labels:
            update_payment_labels(session, case_id=case_id, request=PaymentLabelsRequest(transactions=targets,
                **labels, add_to_library=bool(labels.get('category'))), actor=actor, commit=False)
        session.commit()
        return dict(case_id=str(case_id), updated=len(plans), replacements=replacements)
    except Exception:
        session.rollback()
        raise
