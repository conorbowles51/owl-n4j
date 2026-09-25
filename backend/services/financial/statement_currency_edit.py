"""Correct a statement's denomination atomically, retaining every prior reading."""
from copy import deepcopy
from dataclasses import fields
from types import SimpleNamespace
from uuid import uuid4
from sqlalchemy import select
from postgres.models.enums import AdjudicationDecision, AdjudicationSubject, TransactionDirection
from postgres.models.financial import FinancialSourceDocument, FinancialStatementPeriod, FinancialTransaction
from services.financial.decisions import record
from services.financial.pdf_candidates import PdfMappingError
from services.financial.references import RowReading, content_hash, ref_id
from services.financial.transaction_query import to_view
from services.financial.currency_correction import rescale_minor


def review_run(document):
    def stamp(row):
        row.case_id = document.case_id
        row.ingestion_run_id = document.ingestion_run_id
    return SimpleNamespace(case_id=document.case_id, run_id=document.ingestion_run_id, stamp=stamp)


def change_currency(session, *, document, period, account, currency, actor, revision, balance_edits=None):
    """Caller owns locks, the details audit overlay, reconciliation and commit.

    This changes the denomination, retaining printed numbers exactly even
    when the destination currency uses a different minor-unit scale.
    """
    rows = list(session.scalars(select(FinancialTransaction).where(
        FinancialTransaction.source_document_id == document.id).order_by(FinancialTransaction.id).with_for_update()))
    current = [row for row in rows if row.ledger_status != 'superseded' and row.superseded_by_id is None]
    if any(row.case_id != document.case_id or row.account_id != account.id for row in rows):
        raise PdfMappingError('The saved payments do not match this statement account.', 409)
    if period is None:
        from services.financial.periods import StatementPeriodDraft, PeriodBounds, record_statement_period
        from services.financial.import_issues import calendar_date
        raw = document.metadata_['statement_import_request']
        start, end = calendar_date(raw.get('period_start')), calendar_date(raw.get('period_end'))
        bounds = PeriodBounds.printed(start, end) if start and end and start <= end else PeriodBounds()
        period = record_statement_period(session, review_run(document),
            StatementPeriodDraft(account_id=account.id, source_document_id=document.id, currency=currency, bounds=bounds))
    else:
        for role in ('opening', 'closing'):
            name = role + '_balance_minor'
            if role not in (balance_edits or set()):
                setattr(period, name, rescale_minor(getattr(period, name), period.currency, currency))
        period.currency = currency
    # Historical row identities are immutable. New readings inherit exclusions,
    # categories, names, source locations and links through the correction chain.
    hashes = {row.content_hash for row in rows}
    references = set(session.scalars(select(FinancialTransaction.ref_id).where(FinancialTransaction.case_id == document.case_id)))
    replacements = {}
    for row in current:
        if row.currency == currency:
            row.statement_period_id = period.id
            continue
        reading = {field.name: getattr(row, field.name) for field in fields(RowReading)}
        amounts = {name: rescale_minor(getattr(row, name), row.currency, currency)
            for name in ('amount_minor', 'running_balance_minor')}
        reading.update(currency=currency, direction=TransactionDirection(row.direction), **amounts)
        occurrence = 0
        while True:
            digest = content_hash(RowReading(**reading), occurrence)
            reference = ref_id(document.sha256_at_ingestion, digest)
            if digest not in hashes and reference not in references:
                break
            occurrence += 1
        hashes.add(digest); references.add(reference)
        values = {prop.key: deepcopy(getattr(row, prop.key)) for prop in FinancialTransaction.__mapper__.column_attrs
            if prop.key not in {'id', 'created_at', 'updated_at'}}
        values.update(id=uuid4(), currency=currency, **amounts, ref_id=reference, content_hash=digest,
            statement_period_id=period.id, superseded_by_id=None)
        values['provenance'] = {**(values['provenance'] or {}), 'correction': dict(
            previous_transaction_id=str(row.id), previous_ref_id=row.ref_id, occurrence=occurrence, version=1)}
        replacement = FinancialTransaction(**values)
        before = to_view(row).to_json()
        before.update(amount_minor=str(row.amount_minor),
            running_balance_minor=str(row.running_balance_minor) if row.running_balance_minor is not None else None)
        record(session, case_id=document.case_id, subject=row, subject_type=AdjudicationSubject.transaction,
            decision=AdjudicationDecision.correct_transaction, actor=actor,
            reason=f'Statement currency corrected from {row.currency} to {currency}; printed numeric amounts unchanged.',
            before=dict(row=before, replacement_id=None, original_status=row.ledger_status,
                original_quarantine_reason=row.quarantine_reason, reviewed_revision=revision),
            after=dict(row={**before, 'key': str(replacement.id), 'ref_id': reference, 'currency': currency,
                **{name: str(value) if value is not None else None for name, value in amounts.items()}},
                replacement_id=str(replacement.id), original_status='superseded', original_quarantine_reason=None,
                reviewed_revision=revision))
        session.add(replacement)
        session.flush()
        row.ledger_status = 'superseded'; row.quarantine_reason = None; row.superseded_by_id = replacement.id
        replacements[str(row.id)] = str(replacement.id)
    session.flush()
    # An account can legitimately have statements in several currencies. Do not
    # relabel its other statements when editing this one.
    other = session.scalar(select(FinancialStatementPeriod.id).join(FinancialSourceDocument,
        FinancialSourceDocument.id == FinancialStatementPeriod.source_document_id).where(
        FinancialStatementPeriod.account_id == account.id, FinancialStatementPeriod.id != period.id,
        FinancialSourceDocument.status == 'admitted',
        FinancialStatementPeriod.currency != currency).limit(1))
    account.currency = None if other else currency
    return period, replacements


def complete_currency_records(session, *, document, period, metadata, currency, actor):
    """Promote records made usable by this currency choice in the same commit."""
    from datetime import datetime, timezone
    from services.financial.import_issues import incomplete_fields
    from services.financial.imported_records import transaction_draft
    from services.financial.statement_import import DraftImportRow, StatementImportRequest
    from services.financial.transactions import record_transactions
    raw = metadata['statement_import_request']
    from services.financial.statement_details import saved_details
    request = StatementImportRequest.model_validate({**raw, **saved_details(document), 'currency': currency})
    positions = {row['id']: index for index, row in enumerate(row for row in raw['rows'] if not row['excluded'])}
    sign = -1 if metadata['statement_import_original']['metadata'].get('balance_convention') == 'liability_owed' else 1
    pending, drafts = [], []
    for item in metadata.get('statement_incomplete_records', []):
        if item.get('resolved_transaction_id'):
            continue
        fields = deepcopy(item.get('correction') or item['fields'])
        previous_currency = item.get('correction_currency') or raw.get('currency')
        if previous_currency and previous_currency != currency:
            for key in ('amount_minor', 'balance_minor'):
                value = fields.get(key)
                if value is None or value == '':
                    # The current draft contract represents a missing amount
                    # as an empty string. Preserve its absence, never zero.
                    fields[key] = '' if key == 'amount_minor' and value is None else value
                    continue
                try:
                    fields[key] = rescale_minor(value, previous_currency, currency)
                except (TypeError, ValueError) as exc:
                    label = 'amount' if key == 'amount_minor' else 'printed balance'
                    raise PdfMappingError(f'A pending payment has an unreadable {label}. '
                        f'Review that payment before changing the statement currency. No changes were saved.', 422) from exc
            item.update(correction=fields, correction_currency=currency)
        row = DraftImportRow.model_validate(fields)
        item['missing_fields'] = incomplete_fields(row, request)
        if item['missing_fields'] or row.excluded:
            continue
        drafts.append(transaction_draft(row, item['original'], session=session, case_id=period.case_id, account_id=period.account_id, period_id=period.id,
            currency=currency, position=positions.get(row.id, len(raw['rows']) + len(drafts)), actor=actor, balance_sign=sign, period_end=request.period_end))
        pending.append((item, row))
    from services.financial.saved_statement_admission import assess_saved_additions
    admission = assess_saved_additions(session, document, period, metadata, currency) if drafts else None
    if admission:
        metadata['statement_import_issues'] = admission['blockers'] + [
            issue for issue in metadata.get('statement_import_issues', []) if issue.get('kind') == 'coverage']
        metadata['statement_admission'] = admission
        if not admission['can_import']:
            return admission
    transactions = record_transactions(session, review_run(document), document, drafts, retain_prior_versions=True) if drafts else []
    for (item, row), transaction in zip(pending, transactions, strict=True):
        item.update(resolved_transaction_id=str(transaction.id), correction=row.model_dump(mode='json'),
            correction_currency=currency, version=item.get('version', 0) + 1,
            corrected_by=str(actor.user_id), corrected_at=datetime.now(timezone.utc).isoformat())
    resolved = {item['id'] for item, _ in pending}
    metadata['statement_import_issues'] = [issue for issue in metadata.get('statement_import_issues', [])
        if not (issue.get('kind') == 'missing_field' and issue.get('row_id') in resolved)]
    if admission: metadata['statement_admission'] = admission
    return admission
