"""Edit imported statement details without rereading or replacing its payments."""
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from postgres.models.financial import FinancialAccount, FinancialSourceDocument, FinancialStatementPeriod, FinancialTransaction
from services.financial.pdf_candidates import PdfMappingError, _digest

DETAIL_KEYS = ('holder', 'account_number', 'institution')


class BalanceEdit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    amount_minor: str | None = Field(pattern=r'^-?(0|[1-9][0-9]{0,18})$')
    page: int | None = Field(default=None, ge=1)


class StatementDetailsRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    holder: str = Field(max_length=255)
    account_number: str = Field(max_length=128)
    institution: str = Field(max_length=128)
    opening: BalanceEdit | None = None
    closing: BalanceEdit | None = None


def saved_details(document):
    metadata = document.metadata_ or {}
    raw = metadata.get('statement_import_request', {})
    review = metadata.get('statement_details_review', {})
    return {**{key: raw.get(key, '') for key in (*DETAIL_KEYS, 'period_start', 'period_end')},
            **review.get('details', {})}


def _load(session, case_id, source_id, lock=False):
    query = select(FinancialSourceDocument).where(
        FinancialSourceDocument.id == source_id, FinancialSourceDocument.case_id == case_id)
    document = session.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
    if document is None:
        raise PdfMappingError('Statement not found in this case.', 404)
    if document.document_type != 'statement_review' or document.status != 'admitted':
        raise PdfMappingError('Only a current imported statement can be edited here.', 409)
    metadata = document.metadata_ or {}
    if (_digest(metadata.get('statement_import_original')) != metadata.get('statement_import_original_sha256') or
            _digest(metadata.get('statement_import_request')) != metadata.get('statement_import_request_sha256')):
        raise PdfMappingError('The saved import cannot be verified. Open its source history before changing it.', 409)
    query = select(FinancialStatementPeriod).where(
        FinancialStatementPeriod.source_document_id == source_id, FinancialStatementPeriod.case_id == case_id)
    periods = list(session.scalars(query.order_by(FinancialStatementPeriod.id).with_for_update() if lock else query))
    if len(periods) > 1:
        raise PdfMappingError('Choose an individual statement period before editing.', 409)
    period = periods[0] if periods else None
    account_id = period.account_id if period else UUID(document.metadata_['statement_account_id'])
    query = select(FinancialAccount).where(FinancialAccount.id == account_id, FinancialAccount.case_id == case_id)
    account = session.scalar(query.with_for_update() if lock else query)
    if account is None:
        raise PdfMappingError('The statement account is unavailable.', 409)
    if metadata.get('statement_details_review'):
        if _digest(metadata['statement_details_review']) != metadata.get('statement_details_review_sha256'):
            raise PdfMappingError('The saved corrections cannot be verified. Open the statement history.', 409)
    return document, period, account


def _view(document, period, account):
    metadata = document.metadata_ or {}
    original = metadata['statement_import_original']
    convention = original['metadata'].get('balance_convention') or (
        'liability_owed' if account.account_type == 'credit_card' else 'asset_balance')
    sign = -1 if convention == 'liability_owed' else 1
    pages = sorted({s['page_number'] for s in original.get('sources', [])})
    controls = metadata.get('statement_details_review', {}).get('balances', {})
    result = dict(case_id=str(document.case_id), source_document_id=str(document.id),
        evidence_file_id=str(document.evidence_file_id), account_id=str(account.id),
        period_id=str(period.id) if period else None,
        details=saved_details(document), currency=period.currency if period else account.currency,
        balance_convention=convention, pages=pages, balances={})
    for role in ('opening', 'closing'):
        value = getattr(period, role + '_balance_minor') if period else None
        result['balances'][role] = dict(amount_minor=str(value * sign) if value is not None else None,
            page=controls.get(role, {}).get('page'))
    result['revision'] = _digest(dict(view=result, account=[account.identity_key, account.holder_name,
        account.identifier_as_printed, account.institution_name], history=metadata.get('statement_details_history', [])))
    return result


def read_statement_details(session, *, case_id, source_id):
    return _view(*_load(session, case_id, source_id))


def update_statement_details(session, *, case_id, source_id, request, actor):
    try:
        document, period, account = _load(session, case_id, source_id, lock=True)
        before = _view(document, period, account)
        if before['revision'] != request.expected_revision:
            # Retrying an already saved request is harmless; a different stale
            # edit must never overwrite another reviewer's changes.
            prior = (document.metadata_ or {}).get('statement_details_last_request')
            if prior == request.model_dump(mode='json'):
                return before
            raise PdfMappingError('These details changed since you opened them. Reload before saving; your edits have not overwritten them.', 409)
        details = {key: getattr(request, key).strip() for key in DETAIL_KEYS}
        if any(any(ord(c) < 32 for c in value) for value in details.values()):
            raise PdfMappingError('Account details must be on a single line.', 422)
        balances = deepcopy((document.metadata_ or {}).get('statement_details_review', {}).get('balances', {}))
        for role in ('opening', 'closing'):
            edit = getattr(request, role)
            if edit is None:
                continue
            if period is None:
                raise PdfMappingError('Choose the statement currency before adding balances.', 422)
            amount = int(edit.amount_minor) if edit.amount_minor is not None else None
            if amount is not None and (abs(amount) > 9223372036854775807 or edit.page not in before['pages']):
                raise PdfMappingError('Enter a balance within range and choose its page in this statement.', 422)
            balances[role] = edit.model_dump()
        metadata = deepcopy(document.metadata_ or {})
        old_account_id = account.id
        if any(details[key] != before['details'][key] for key in DETAIL_KEYS):
            from services.financial.accounts import AccountDraft, AccountIdentityError, record_account
            fields = dict(holder_name=details['holder'] or None, identifier_as_printed=details['account_number'] or None,
                institution_name=details['institution'] or None, currency=account.currency,
                account_type=account.account_type, metadata=dict(display_label=' · '.join(filter(None,
                    [details['holder'], details['account_number']])) or 'Account details not recorded'))
            try:
                draft = AccountDraft.observed(**fields)
            except AccountIdentityError:
                draft = AccountDraft.unidentified(distinguisher='statement-details:' + str(document.id), **fields)
            target = record_account(session, SimpleNamespace(case_id=case_id, run_id=document.ingestion_run_id), draft)
            # Keep other statements' identities untouched. Corrections belong
            # to this source; a matching identified account can be reused.
            account = target
            metadata['statement_account_id'] = str(account.id)
            if period:
                period.account_id = account.id
            rows = list(session.scalars(select(FinancialTransaction).where(
                FinancialTransaction.case_id == case_id, FinancialTransaction.source_document_id == source_id)
                .order_by(FinancialTransaction.id).with_for_update()))
            for row in rows:
                if row.account_id != old_account_id:
                    raise PdfMappingError('This import contains multiple accounts. Review its assignment before changing details.', 409)
                row.account_id = account.id
        sign = -1 if before['balance_convention'] == 'liability_owed' else 1
        for role in ('opening', 'closing'):
            edit = getattr(request, role)
            if edit is not None:
                setattr(period, role + '_balance_minor', int(edit.amount_minor) * sign if edit.amount_minor is not None else None)
                setattr(period, role + '_balance_source', 'printed' if edit.amount_minor is not None else 'absent')
                setattr(period, role + '_carried_from_period_id', None)
        review = dict(details=details, balances=balances, account_id=str(account.id),
            period_id=str(period.id) if period else None, source_document_id=str(source_id),
            balance_convention=before['balance_convention'])
        metadata['statement_details_review'] = review
        metadata['statement_details_review_sha256'] = _digest(review)
        metadata.setdefault('statement_details_history', []).append(dict(
            at=datetime.now(timezone.utc).isoformat(), actor_id=str(actor.user_id), actor_name=actor.name,
            before=before, after=review))
        metadata['statement_details_last_request'] = request.model_dump(mode='json')
        document.metadata_ = metadata
        session.flush()
        if period:
            from services.financial.reconcile import reconcile_period
            reconcile_period(session, period)
        result = _view(document, period, account)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise


def reviewed_controls(period, document, original):
    """Overlay later readings while leaving the sealed import controls intact."""
    metadata = document.metadata_ or {}
    review = metadata.get('statement_details_review')
    if not review:
        return original
    if (_digest(review) != metadata.get('statement_details_review_sha256') or
            review['period_id'] != str(period.id) or review['account_id'] != str(period.account_id) or
            review['source_document_id'] != str(document.id)):
        raise ValueError('The later statement review no longer matches its period.')
    result = deepcopy(original) if original else dict(import_source_document_id=str(document.id), finalization_id=None,
        currency=period.currency, balance_convention=review['balance_convention'], controls=[], account_closure=None)
    controls = {item['role']: item for item in result['controls']}
    for role, balance in review['balances'].items():
        if balance['amount_minor'] is None:
            controls.pop(role, None)
        else:
            sign = -1 if review['balance_convention'] == 'liability_owed' else 1
            if getattr(period, role + '_balance_minor') != int(balance['amount_minor']) * sign:
                raise ValueError('The saved balance differs from its review.')
            controls[role] = dict(role=role, original_text='', reviewed_value=balance['amount_minor'],
                locator=dict(kind='page_only', page=balance['page']))
    result.update(controls=list(controls.values()), reason='Account details or balances corrected after import.',
        scope='Manually entered balances cite their PDF page. Earlier values and the original import remain in history.')
    return result
