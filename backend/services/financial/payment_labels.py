"""Investigator categories and names, kept separately from statement readings."""
from datetime import datetime, timezone
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from postgres.models.financial import FinancialTransaction


class PaymentLabelsError(ValueError):
    def __init__(self, message, status_code=409):
        super().__init__(message)
        self.status_code = status_code


class LabelTarget(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    version: int = Field(ge=0)


class PaymentLabelsRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    transactions: list[LabelTarget] = Field(min_length=1)
    category: str | None = Field(default=None, max_length=120)
    from_name: str | None = Field(default=None, max_length=512)
    to_name: str | None = Field(default=None, max_length=512)
    counterparty_name: str | None = Field(default=None, max_length=512)

    @field_validator('category', 'from_name', 'to_name', 'counterparty_name')
    @classmethod
    def clean(cls, value):
        if value is None:
            return None
        value = value.strip()
        if any(ord(c) < 32 for c in value):
            raise ValueError('Names must be a single line.')
        return value


def update_payment_labels(session, *, case_id, request, actor):
    changes = request.model_dump(exclude_unset=True, exclude={'transactions'})
    if not changes or any(value is None for value in changes.values()):
        raise PaymentLabelsError('Choose a category or enter a name. Use an empty value to clear it.', 422)
    ids = [target.id for target in request.transactions]
    if len(set(ids)) != len(ids):
        raise PaymentLabelsError('A payment was selected twice.', 422)
    try:
        rows = []
        # Bound each SQL query, not the user's selection. All chunks share one
        # transaction and acquire locks in the same order before any writes.
        ordered_ids = sorted(ids)
        for offset in range(0, len(ordered_ids), 1000):
            rows.extend(session.scalars(select(FinancialTransaction).where(
                FinancialTransaction.case_id == case_id,
                FinancialTransaction.id.in_(ordered_ids[offset:offset + 1000])
            ).order_by(FinancialTransaction.id).with_for_update()))
        if len(rows) != len(ids):
            raise PaymentLabelsError('One or more payments are unavailable in this case.', 404)
        versions = {target.id: target.version for target in request.transactions}
        for row in rows:
            current = (row.metadata_ or {}).get('investigation_labels', {})
            if row.ledger_status != 'admitted' or row.superseded_by_id is not None:
                raise PaymentLabelsError('A selected payment has been replaced or excluded. Reload the selection.')
            if current.get('version', 0) != versions[row.id]:
                raise PaymentLabelsError('Someone edited a selected payment. Reload the selection before saving.')
        for row in rows:
            metadata = dict(row.metadata_ or {})
            current = dict(metadata.get('investigation_labels', {}))
            row_changes = dict(changes)
            if 'counterparty_name' in row_changes:
                row_changes['from_name' if row.direction == 'credit' else 'to_name'] = row_changes.pop('counterparty_name')
            if all(key in current and current[key] == value for key, value in row_changes.items()):
                continue
            effective = payment_label_view(row, row.account)
            before = {key: effective.get(key, '') for key in row_changes}
            current.update(row_changes)
            current['version'] = current.get('version', 0) + 1
            metadata['investigation_labels'] = current
            metadata['investigation_label_history'] = [*metadata.get('investigation_label_history', []), dict(
                at=datetime.now(timezone.utc).isoformat(), actor_name=actor.name,
                actor_email=actor.email, actor_id=str(actor.user_id) if actor.user_id else None,
                before=before, after=row_changes, version=current['version'],
                previous_label_sources={key: effective['label_sources'][key] for key in row_changes})]
            row.metadata_ = metadata
        session.commit()
        return dict(case_id=str(case_id), updated=len(rows))
    except Exception:
        session.rollback()
        raise


def payment_label_view(row, account=None):
    from services.financial.payment_inference import infer_payment_labels
    if account is not None and (account.id != row.account_id or account.case_id != row.case_id):
        account = None
    labels = (row.metadata_ or {}).get('investigation_labels', {})
    inferred = infer_payment_labels(row.description, direction=row.direction,
        account_type=account.account_type if account is not None else None,
        institution=account.institution_name if account is not None else None)
    own = (account.holder_name or account.identifier_as_printed) if account is not None else None
    own = own or 'Account ' + str(row.account_id)[:8]
    other = row.counterparty_raw or inferred.get('counterparty', {}).get('value', '')
    sender, recipient = (other, own) if row.direction == 'credit' else (own, other)
    own_source = dict(source='account', explanation='From the saved statement account details.')
    other_source = (dict(source='statement', explanation='From the recorded counterparty field.')
                    if row.counterparty_raw else inferred.get('counterparty', dict(source='missing')))
    sources = dict(category=inferred.get('category', dict(source='missing')),
                   from_name=other_source if row.direction == 'credit' else own_source,
                   to_name=own_source if row.direction == 'credit' else other_source)
    values = dict(category=inferred.get('category', {}).get('value', ''),
                  from_name=sender, to_name=recipient)
    for field in values:
        # An explicit clear also takes precedence; do not put a rejected
        # suggestion back into the investigator's view on the next read.
        if field in labels:
            values[field] = labels[field]
            sources[field] = dict(source='investigator', explanation='Saved by an investigator.')
    return dict(**values, label_sources=sources, label_version=labels.get('version', 0))
