"""Investigator categories and names, kept separately from statement readings."""
from datetime import datetime, timezone
from functools import lru_cache
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator
from services.financial.payment_counterparty_link import PaymentCounterpartyLink, resolve_link, effective_link, display_link
from sqlalchemy import select
from postgres.models.financial import FinancialTransaction
from services.financial.model_work import ModelWorkError, describe, explanation, is_model, origin_of, require_person


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
    add_to_library: bool = False
    from_name: str | None = Field(default=None, max_length=512)
    to_name: str | None = Field(default=None, max_length=512)
    counterparty_link: PaymentCounterpartyLink | None = None
    counterparty_name: str | None = Field(default=None, max_length=512)
    # 'statement': the person read the name off the statement page shown beside the table. Recorded in the label
    # history and shown as "Named by <person> from the statement"; it changes nothing else about the save.
    named_from: Literal['statement'] | None = None
    # The payment whose name this one was given, when a person applied it to payments like it after reviewing them.
    same_as: UUID | None = None

    @field_validator('category', 'from_name', 'to_name', 'counterparty_name')
    @classmethod
    def clean(cls, value):
        if value is None:
            return None
        value = value.strip()
        if any(ord(c) < 32 for c in value):
            raise ValueError('Names must be a single line.')
        return value


def update_payment_labels(session, *, case_id, request, actor, commit=True, reason=None):
    """``reason``: why the value was set (where it was read), kept in the label history and shown with the label."""
    changes = request.model_dump(exclude_unset=True, exclude={'transactions', 'add_to_library', 'named_from', 'same_as'})
    if request.named_from == 'statement':
        reason = reason or 'Named from the statement.'
        if request.same_as is not None:
            reason = f'Named from the statement, the same name as payment {request.same_as}.'
    if not changes or any(value is None for key, value in changes.items() if key != 'counterparty_link'):
        raise PaymentLabelsError('Choose a category or enter a name. Use an empty value to clear it.', 422)
    ids = [target.id for target in request.transactions]
    if len(set(ids)) != len(ids):
        raise PaymentLabelsError('A payment was selected twice.', 422)
    model = is_model(actor)
    if model and (set(changes) - {'from_name', 'to_name', 'counterparty_name'} or request.add_to_library
                  or any(not value for value in changes.values())):
        # A model reads names off the page; choosing categories, linking parties and clearing names stay a person's.
        raise PaymentLabelsError(f'{actor.name} can only record a name it read; a person sets categories and links.', 422)
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
        if request.add_to_library:
            if not changes.get('category'):
                raise PaymentLabelsError('Enter a category to add to the library.', 422)
            from services.financial.category_library import ensure_category
            changes['category'] = ensure_category(session, name=changes['category'], actor=actor)['name']
        if 'counterparty_link' in changes:
            changes['counterparty_link'] = resolve_link(session, case_id=case_id, link=request.counterparty_link) if request.counterparty_link else None
        for row in rows:
            metadata = dict(row.metadata_ or {})
            current = dict(metadata.get('investigation_labels', {}))
            row_changes = dict(changes)
            if 'counterparty_name' in row_changes:
                row_changes['from_name' if row.direction == 'credit' else 'to_name'] = row_changes.pop('counterparty_name')
            if all(key in current and current[key] == value for key, value in row_changes.items()):
                continue
            effective = payment_label_view(row, row.account)
            if model:
                # A person's entry or confirmation outranks a model reading: never replace it, or a link, with one.
                for key in row_changes:
                    if effective['label_sources'].get(key, {}).get('source') == 'investigator':
                        raise PaymentLabelsError(f"A person named this payment. A reading by {actor.origin['model']} "
                                                 'does not replace it.')
            if 'counterparty_link' in row_changes:
                # Direction determines the linked side; remove earlier explicit
                # labels on that side so they cannot silently hide the link.
                current.pop('from_name' if row.direction == 'credit' else 'to_name', None)
            elif ('from_name' if row.direction == 'credit' else 'to_name') in row_changes:
                row_changes['counterparty_link'] = None
            before = {key: effective.get(key, '') for key in row_changes}
            current.update(row_changes)
            current['version'] = current.get('version', 0) + 1
            if 'counterparty_link' in row_changes:
                from services.financial.payment_counterparty_link import record_link
                record_link(session, row=row, link=row_changes['counterparty_link'], actor=actor, reason='Counterparty edited from the investigator transaction table.')
            metadata['investigation_labels'] = current
            if 'category' in row_changes:
                from services.financial.payment_categories import record_person_choice
                record_person_choice(session, row, row_changes['category'], actor)
            metadata['investigation_label_history'] = [*metadata.get('investigation_label_history', []), dict(
                at=datetime.now(timezone.utc).isoformat(), actor_name=actor.name,
                actor_email=actor.email, actor_id=str(actor.user_id) if actor.user_id else None,
                before=before, after=row_changes, version=current['version'], **({'reason': reason} if reason else {}),
                **({'via': 'statement'} if request.named_from == 'statement' else {}),
                **({'same_as': str(request.same_as)} if request.same_as is not None else {}),
                **({'origin': dict(actor.origin)} if model else {}),
                previous_label_sources={key: effective['label_sources'].get(key, {}) for key in row_changes})]
            row.metadata_ = metadata
        if commit:
            session.commit()
        else:
            session.flush()
        return dict(case_id=str(case_id), updated=len(rows))
    except Exception:
        session.rollback()
        raise



class RemovePaymentLabelsRequest(BaseModel):
    """Take a person's name off payments so the statement's own reading (or "Not identified") shows again."""
    model_config = ConfigDict(extra='forbid')
    transactions: list[LabelTarget] = Field(min_length=1, max_length=5000)
    fields: list[Literal['from_name', 'to_name', 'counterparty_name']] = Field(min_length=1, max_length=3)


def remove_payment_labels(session, *, case_id, request, actor, commit=True):
    """Remove saved names, recorded in the label history like any edit. Only the named label keys change."""
    require_label_person(actor, 'take a name off')
    ids = [target.id for target in request.transactions]
    if len(set(ids)) != len(ids):
        raise PaymentLabelsError('A payment was selected twice.', 422)
    try:
        rows = []
        ordered_ids = sorted(ids)
        for offset in range(0, len(ordered_ids), 1000):
            rows.extend(session.scalars(select(FinancialTransaction).where(
                FinancialTransaction.case_id == case_id,
                FinancialTransaction.id.in_(ordered_ids[offset:offset + 1000])
            ).order_by(FinancialTransaction.id).with_for_update()))
        if len(rows) != len(ids):
            raise PaymentLabelsError('One or more payments are unavailable in this case.', 404)
        versions = {target.id: target.version for target in request.transactions}
        removed = 0
        for row in rows:
            current = (row.metadata_ or {}).get('investigation_labels', {})
            if row.ledger_status != 'admitted' or row.superseded_by_id is not None:
                raise PaymentLabelsError('A selected payment has been replaced or excluded. Reload the selection.')
            if current.get('version', 0) != versions[row.id]:
                raise PaymentLabelsError('Someone edited a selected payment. Reload the selection before saving.')
        for row in rows:
            metadata = dict(row.metadata_ or {})
            current = dict(metadata.get('investigation_labels', {}))
            fields = {('from_name' if row.direction == 'credit' else 'to_name') if field == 'counterparty_name' else field
                      for field in request.fields}
            fields = sorted(field for field in fields if field in current)
            if not fields:
                continue
            effective = payment_label_view(row, row.account)
            before = {field: effective.get(field, '') for field in fields}
            history = metadata.get('investigation_label_history', [])
            restored, restored_sources = {}, {}
            for field in fields:
                # Undo the save that set this name: a person's earlier name comes back; a statement reading comes
                # back by dropping the label. A save that replaced a link to a known party is not undone here.
                entry = next((e for e in reversed(history) if isinstance(e, dict)
                              and (field in (e.get('after') or {}) or field in (e.get('removed') or []))), None)
                previous = ((entry or {}).get('previous_label_sources') or {}).get(field) or {}
                if entry is not None and field in (entry.get('after') or {}) and previous.get('identity_kind'):
                    raise PaymentLabelsError('This name replaced a link to a known party. Open the payment to link it again.', 422)
                if (entry is not None and field in (entry.get('after') or {})
                        and previous.get('source') in ('investigator', 'model_reading')
                        and isinstance((entry.get('before') or {}).get(field), str)):
                    current[field] = restored[field] = entry['before'][field]
                    restored_sources[field] = previous
                else:
                    current.pop(field)
            current['version'] = current.get('version', 0) + 1
            metadata['investigation_labels'] = current
            metadata['investigation_label_history'] = [*metadata.get('investigation_label_history', []), dict(
                at=datetime.now(timezone.utc).isoformat(), actor_name=actor.name,
                actor_email=actor.email, actor_id=str(actor.user_id) if actor.user_id else None,
                before=before, removed=fields, version=current['version'],
                **({'restored': restored, 'restored_sources': restored_sources} if restored else {}),
                previous_label_sources={key: effective['label_sources'].get(key, {}) for key in fields})]
            row.metadata_ = metadata
            removed += 1
        if commit:
            session.commit()
        else:
            session.flush()
        return dict(case_id=str(case_id), updated=removed)
    except Exception:
        session.rollback()
        raise

def require_label_person(actor, what):
    try:
        require_person(actor, what)
    except ModelWorkError as exc:
        raise PaymentLabelsError(str(exc), exc.status_code) from exc


class ConfirmPaymentLabelsRequest(BaseModel):
    """A person confirms a name a model read, from the statement: the name stays, the person becomes its actor."""
    model_config = ConfigDict(extra='forbid')
    transactions: list[LabelTarget] = Field(min_length=1, max_length=5000)
    fields: list[Literal['from_name', 'to_name', 'counterparty_name']] = Field(default=['counterparty_name'],
                                                                              min_length=1, max_length=2)


def confirm_payment_labels(session, *, case_id, request, actor, commit=True):
    """Confirm model readings: one label-history entry per payment by the person, naming the fields confirmed and
    the model reading they confirm. No value changes; the model's entry stays in the history. A field whose current
    label is not an unconfirmed model reading is left alone and counted as skipped."""
    require_label_person(actor, 'confirm a name a model read')
    ids = [target.id for target in request.transactions]
    if len(set(ids)) != len(ids):
        raise PaymentLabelsError('A payment was selected twice.', 422)
    try:
        rows = []
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
            if row.ledger_status != 'admitted' or row.superseded_by_id is not None:
                raise PaymentLabelsError('A selected payment has been replaced or excluded. Reload the selection.')
            if (row.metadata_ or {}).get('investigation_labels', {}).get('version', 0) != versions[row.id]:
                raise PaymentLabelsError('Someone edited a selected payment. Reload the selection before saving.')
        confirmed = skipped = 0
        for row in rows:
            metadata = dict(row.metadata_ or {})
            current = dict(metadata.get('investigation_labels', {}))
            history = metadata.get('investigation_label_history', [])
            fields = sorted({('from_name' if row.direction == 'credit' else 'to_name') if field == 'counterparty_name'
                             else field for field in request.fields})
            sources = {field: _label_source(row, field) for field in fields if field in current}
            fields = [field for field, source in sources.items() if source.get('source') == 'model_reading']
            if not fields:
                skipped += 1
                continue
            current['version'] = current.get('version', 0) + 1
            metadata['investigation_labels'] = current
            metadata['investigation_label_history'] = [*history, dict(
                at=datetime.now(timezone.utc).isoformat(), actor_name=actor.name,
                actor_email=actor.email, actor_id=str(actor.user_id) if actor.user_id else None,
                confirmed=fields, values={field: current[field] for field in fields}, version=current['version'],
                via='statement', confirmed_origin=sources[fields[0]]['origin'],
                previous_label_sources={field: sources[field] for field in fields})]
            row.metadata_ = metadata
            confirmed += 1
        if commit:
            session.commit()
        else:
            session.flush()
        return dict(case_id=str(case_id), confirmed=confirmed, skipped=skipped)
    except Exception:
        session.rollback()
        raise


_LOOKUP = object()


def payment_label_view(row, account=None, stored=_LOOKUP, matched=None):
    """``stored``: the row's stored category (services.financial.payment_categories), None when it has none, or
    left out to look it up. A stored category replaces the per-read description guess; a person's label wins.
    ``matched``: this row's entry from services.financial.payment_party_matches.case_party_matches, used only when
    neither the statement nor the description names the other side."""
    if account is not None and (account.id != row.account_id or account.case_id != row.case_id):
        account = None
    labels = (row.metadata_ or {}).get('investigation_labels', {})
    if stored is _LOOKUP:
        stored = _stored_category(row)
    inferred = _inferred_labels(row.description, row.direction,
        account.account_type if account is not None else None,
        account.institution_name if account is not None else None)
    if stored is not None and 'category' not in labels:
        from services.financial.payment_categories import label_source
        inferred = {**inferred, 'category': dict(value=stored.category, **label_source(stored))}
    own = (account.holder_name or account.identifier_as_printed) if account is not None else None
    own = own or 'Account ' + str(row.account_id)[:8]
    if matched and not row.counterparty_raw and not inferred.get('counterparty'):
        inferred = {**inferred, 'counterparty': matched}
    other = row.counterparty_raw or inferred.get('counterparty', {}).get('value', '')
    sender, recipient = (other, own) if row.direction == 'credit' else (own, other)
    own_source = dict(source='account', explanation='From the saved statement account details.')
    other_source = (dict(source='statement', explanation='From the recorded counterparty field.')
                    if row.counterparty_raw else inferred.get('counterparty') or _missing(inferred.get('counterparty_reason')))
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
            sources[field] = _label_source(row, field)
    link = display_link(row)
    if link:
        side = 'from_name' if row.direction == 'credit' else 'to_name'
        values[side] = link['label']
        sources[side] = dict(source='investigator', explanation='Linked by an investigator to an existing ' + link['kind'] + '.', identity_kind=link['kind'], identity_id=link['id'])
    return dict(**values, counterparty_link=link, label_sources=sources, label_version=labels.get('version', 0))


def _label_entry(history, field):
    """The latest label-history entry that set, removed, restored or confirmed ``field``."""
    return next((e for e in reversed(history) if isinstance(e, dict) and (
        field in (e.get('after') or {}) or field in (e.get('removed') or []) or field in (e.get('confirmed') or [])
        or field in (e.get('restored') or {}))), None)


def _label_source(row, field):
    """Where a stored label comes from: a person, a person's confirmation of a model reading, or a model reading
    nobody has confirmed yet. Only the presentation differs; the value is the stored label in every case."""
    history = (row.metadata_ or {}).get('investigation_label_history', [])
    entry = _label_entry(history, field)
    if entry is not None and field in (entry.get('confirmed') or []):
        read = entry.get('confirmed_origin') or {}
        when = str(entry.get('at') or '')[:10]
        return dict(source='investigator', confirmed_model_reading=read,
                    explanation=f"Confirmed by {entry.get('actor_name') or 'an investigator'} from the statement"
                                + (f' on {when}' if when else '') + f". Read first by {read.get('model') or 'a model'}.")
    if entry is not None and field in (entry.get('restored') or {}):
        restored = (entry.get('restored_sources') or {}).get(field)
        if restored:
            return dict(restored)
    if entry is not None and field in (entry.get('after') or {}) and origin_of(entry):
        origin = origin_of(entry)
        return dict(source='model_reading', origin=origin, label=describe(origin),
                    explanation=explanation(origin, reason=str(entry.get('reason') or '')))
    return dict(source='investigator', explanation=_saved_by(row, field))


def _saved_by(row, field):
    """Who saved a label, when, and the reason they recorded, from the label history."""
    history = (row.metadata_ or {}).get('investigation_label_history', [])
    entry = next((e for e in reversed(history) if isinstance(e, dict) and field in (e.get('after') or {})), None)
    if not entry or not entry.get('actor_name'):
        return 'Saved by an investigator.'
    when = str(entry.get('at') or '')[:10]
    if entry.get('via') == 'statement':
        same = ' (the same name as a payment like it)' if entry.get('same_as') else ''
        return f"Named by {entry['actor_name']} from the statement" + (f' on {when}' if when else '') + same + '.'
    text = f"Saved by {entry['actor_name']}" + (f' on {when}' if when else '') + '.'
    return text + (' ' + entry['reason'] if entry.get('reason') else '')


def _missing(reason):
    """No name for the other side; with the reason when the statement's layout is known to print none."""
    if not reason:
        return dict(source='missing')
    return dict(source='missing', reason=reason['value'], rule=reason['rule'], version=reason['version'],
                explanation=reason['explanation'])


@lru_cache(maxsize=50_000)
def _inferred_once(description, direction, account_type, institution):
    from services.financial.payment_inference import infer_payment_labels
    return infer_payment_labels(description, direction=direction, account_type=account_type, institution=institution)


def _inferred_labels(description, direction, account_type, institution):
    """infer_payment_labels reads only these four values, so equal values get the same labels. Reading a case asked
    the same descriptions again for every payment on every request; each caller gets its own copy."""
    return {field: dict(label) for field, label in _inferred_once(description, direction, account_type, institution).items()}


def _stored_category(row):
    if '_category_record' in vars(row):
        return row._category_record
    from sqlalchemy.orm import object_session
    from sqlalchemy.orm.exc import UnmappedInstanceError
    try:
        session = object_session(row)
    except UnmappedInstanceError:
        return None
    if session is None or row.id is None:
        return None
    try:
        from postgres.models.financial_payment_category import FinancialPaymentCategory
        from services.financial.payment_categories import table_ready
        with session.no_autoflush:
            if not table_ready(session):
                return None
            return session.get(FinancialPaymentCategory, row.id)
    except Exception:  # noqa: BLE001 - a database without the table yet reads the description guess, as before
        return None
