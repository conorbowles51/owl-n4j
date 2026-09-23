from services.financial.account_consolidation import expand_account_ids
"""Incomplete imported statement records and their later, atomic completion."""
from copy import deepcopy
from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import UUID
from sqlalchemy import select, func
from pydantic import BaseModel, ConfigDict, Field
from postgres.models.financial import FinancialSourceDocument, FinancialStatementPeriod, FinancialTransaction
from postgres.models.evidence import EvidenceFile
from services.financial.pdf_candidates import PdfMappingError
from services.financial.statement_import import ImportRow, StatementImportRequest, _reading_dates, _date_roles, _primary_date_role
from services.financial.import_issues import usable_currency, incomplete_fields


class CompleteImportedRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')
    row: ImportRow
    version: int = Field(ge=0)
    currency: str = Field(pattern=r'^[A-Z]{3}$')


def imported_records(session, *, case_id, account_id=None, start_date=None, end_date=None, offset=0, limit=50, account_ids=None, account_holders=None, source_document_id=None):
    # Select only the small retained-record arrays, never each full PDF proposal.
    query = select(FinancialSourceDocument.id, FinancialSourceDocument.evidence_file_id,
        FinancialSourceDocument.metadata_['statement_account_id'].as_string(),
        FinancialSourceDocument.metadata_['statement_incomplete_records'],
        func.coalesce(FinancialSourceDocument.metadata_['statement_details_review']['currency'].as_string(),
            FinancialSourceDocument.metadata_['statement_import_request']['currency'].as_string()),
        EvidenceFile.original_filename).join(EvidenceFile, EvidenceFile.id == FinancialSourceDocument.evidence_file_id).where(
            FinancialSourceDocument.case_id == case_id, EvidenceFile.case_id == case_id,
            FinancialSourceDocument.status == 'admitted').order_by(FinancialSourceDocument.id)
    if source_document_id:
        query = query.where(FinancialSourceDocument.id == source_document_id)
    if account_id:
        query = query.where(FinancialSourceDocument.metadata_['statement_account_id'].as_string().in_([str(id) for id in expand_account_ids(session, case_id, [account_id])]))
    if account_ids:
        account_ids = expand_account_ids(session, case_id, account_ids)
        query = query.where(FinancialSourceDocument.metadata_['statement_account_id'].as_string().in_([str(id) for id in account_ids]))
    if account_holders:
        from services.financial.account_selection import holder_account_ids
        ids = [str(id) for id in holder_account_ids(session, case_id, account_holders)]
        query = query.where(FinancialSourceDocument.metadata_['statement_account_id'].as_string().in_(ids))
    records = []
    for source_id, file_id, account, items, currency, filename in session.execute(query):
        for item in items or []:
            if item.get('resolved_transaction_id'):
                continue
            fields = item['fields']
            from services.financial.import_issues import calendar_date
            day = calendar_date(fields.get('date'))
            # Keep undated records visible and identify them, even with a range.
            if day and ((start_date and day < start_date) or (end_date and day > end_date)):
                continue
            original = item.get('original', {})
            records.append(dict(id=item['id'], source_document_id=str(source_id), evidence_file_id=str(file_id),
                account_id=account, filename=filename, currency=currency or '', fields=fields,
                page_number=original.get('page_number'), locator=(original.get('source_cells') or [{}])[0].get('locator'),
                original_text=' '.join(c.get('expected_text', '') for c in original.get('source_cells', [])),
                missing_fields=item['missing_fields'], version=item.get('version', 0)))
    statements = {}
    for record in records:
        summary = statements.setdefault(record['evidence_file_id'], dict(
            evidence_file_id=record['evidence_file_id'], filename=record['filename'], count=0))
        summary['count'] += 1
    return dict(records=records[offset:offset+limit], total=len(records), offset=offset,
        statements=sorted(statements.values(), key=lambda item: (item['filename'], item['evidence_file_id'])))


def transaction_draft(row, original, *, account_id, period_id, currency, position, actor, balance_sign=1, period_end='', session=None, case_id=None):
    from services.financial.transactions import TransactionDraft
    from services.financial.references import RowReading
    from services.financial.locators import Locator, SourceRectangle
    from postgres.models.enums import LocatorKind, TransactionDirection
    cells = original.get('source_cells', []) + [v['source_cell'] for v in original.get('value_sources', {}).values()]
    rectangles = [Locator.from_json(c['locator']).rectangle for c in cells]
    rectangles = [r for r in rectangles if r is not None]
    page = original.get('page_number') or row.manual_page
    locator = Locator(kind=LocatorKind.page_only, page_number=page)
    if rectangles and all((r.page_number, r.page_width, r.page_height) == (page, rectangles[0].page_width, rectangles[0].page_height) for r in rectangles):
        first = rectangles[0]
        locator = Locator(kind=LocatorKind.page_rectangle, rectangle=SourceRectangle(page_number=page,
            page_width=first.page_width, page_height=first.page_height,
            x0=min(r.x0 for r in rectangles), y0=min(r.y0 for r in rectangles),
            x1=max(r.x1 for r in rectangles), y1=max(r.y1 for r in rectangles)))
    from services.financial.payment_counterparty_link import resolve_link
    from services.financial.account_parties import AccountPartyError
    try:
        link = resolve_link(session, case_id=case_id, link=row.counterparty_link) if row.counterparty_link else None
    except AccountPartyError as exc:
        raise PdfMappingError(str(exc), exc.status_code) from exc
    return TransactionDraft(row_index=position, account_id=account_id, locator=locator, statement_period_id=period_id,
        reading=RowReading(currency=currency, amount_minor=int(row.amount_minor), direction=TransactionDirection(row.direction),
            **({'effective_date': date.fromisoformat(period_end)} if row.date_unprinted else _reading_dates(original.get('fields', {}), row.date, row.date_values)),
            description=row.description, counterparty_raw=row.counterparty or None,
            bank_reference=original.get('fields', {}).get('bank_reference'),
            running_balance_minor=balance_sign * int(row.balance_minor) if row.balance_minor is not None else None),
        provenance=dict(**(dict(reviewed_counterparty=link) if link else {}), statement_import_original=original, statement_import_review=row.model_dump(mode='json'),
            **(dict(date_basis='statement_end_ordering_only', statement_end_date=period_end) if row.date_unprinted else {}),
            confirmed_by=dict(user_id=str(actor.user_id), name=actor.name, email=actor.email)))


def complete_record(*, session_factory, case_id, source_id, request, actor):
    from services.financial.runs import ingestion_run
    from services.financial.transactions import record_transactions
    from services.financial.reconcile import reconcile_period
    currency = usable_currency(request.currency)
    if not currency or request.row.excluded:
        raise PdfMappingError('Enter the missing values before saving this payment.', 422)
    with session_factory() as session:
        exists = session.scalar(select(FinancialSourceDocument.id).where(FinancialSourceDocument.id == source_id,
            FinancialSourceDocument.case_id == case_id, FinancialSourceDocument.status == 'admitted'))
        if exists is None:
            raise PdfMappingError('This imported statement is no longer available.', 404)
    with ingestion_run(case_id=case_id, actor=SimpleNamespace(id=actor.user_id, email=actor.email),
            session_factory=session_factory, config=dict(operation='complete_imported_record', source_document_id=str(source_id))) as run:
        with session_factory() as session:
            from postgres.models.case import Case
            session.execute(select(Case.id).where(Case.id == case_id).with_for_update()).all()
            document = session.scalar(select(FinancialSourceDocument).where(FinancialSourceDocument.id == source_id,
                FinancialSourceDocument.case_id == case_id, FinancialSourceDocument.status == 'admitted').with_for_update())
            if document is None:
                raise PdfMappingError('This imported statement is no longer available.', 404)
            metadata = deepcopy(document.metadata_)
            record = next((r for r in metadata.get('statement_incomplete_records', []) if r['id'] == request.row.id), None)
            if record is None:
                raise PdfMappingError('The imported record was not found.', 404)
            if record.get('resolved_transaction_id'):
                if record.get('correction') == request.row.model_dump(mode='json') and record.get('correction_currency') == currency:
                    return dict(transaction_id=record['resolved_transaction_id'], created=False)
                raise PdfMappingError('This record has already been corrected. Open its transaction.', 409)
            if record.get('version', 0) != request.version:
                raise PdfMappingError('Another investigator changed this record. Reload it before saving.', 409)
            original = record['original']
            fields = original.get('fields', {})
            if request.row.date_unprinted and fields.get('date_basis') != 'statement_end_ordering_only':
                raise PdfMappingError('Only a recognised undated statement charge can have no printed date.', 422)
            if not set(request.row.date_values) <= set(_date_roles(fields)) - {_primary_date_role(fields)}:
                raise PdfMappingError('Only separately identified source dates can be corrected.', 422)
            if request.row.manual_page != record['fields'].get('manual_page'):
                raise PdfMappingError('The source page cannot be reassigned.', 422)
            from services.financial.statement_details import saved_details
            raw = {**metadata['statement_import_request'], **saved_details(document)}
            checked_request = StatementImportRequest.model_validate({**raw, 'currency': currency})
            if incomplete_fields(request.row, checked_request):
                raise PdfMappingError('The record still has incomplete values.', 422)
            account_id = UUID(metadata['statement_account_id'])
            period = session.scalar(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id == source_id,
                FinancialStatementPeriod.case_id == case_id))
            if period and period.currency != currency:
                raise PdfMappingError('Use the currency recorded for this statement.', 422)
            position = next(i for i, r in enumerate(r for r in raw['rows'] if not r['excluded']) if r['id'] == request.row.id)
            sign = -1 if metadata['statement_import_original']['metadata'].get('balance_convention') == 'liability_owed' else 1
            draft = transaction_draft(request.row, original, session=session, case_id=case_id, account_id=account_id, period_id=period.id if period else None,
                currency=currency, position=position, actor=actor, balance_sign=sign, period_end=raw.get('period_end', ''))
            transaction = record_transactions(session, run, document, [draft], retain_prior_versions=True)[0]
            record.update(resolved_transaction_id=str(transaction.id), correction=request.row.model_dump(mode='json'),
                correction_currency=currency, version=request.version + 1, corrected_by=str(actor.user_id),
                corrected_at=datetime.now(timezone.utc).isoformat())
            corrected_rows = {r['id']: r['correction'] for r in metadata['statement_incomplete_records'] if r.get('correction')}
            from services.financial.statement_details import saved_details, saved_currency
            reviewed = {**raw, **saved_details(document), 'currency': saved_currency(document) or raw.get('currency', ''),
                'rows':[corrected_rows.get(r['id'], r) for r in raw['rows']]}
            from services.financial.review_arithmetic import check_proposed_rows
            from services.financial.import_issues import retained_issues
            checks = check_proposed_rows(metadata['statement_import_original'], reviewed['rows'])
            metadata['statement_import_checks'] = checks
            coverage_issues = [i for i in metadata.get('statement_import_issues', []) if i.get('kind') == 'coverage']
            metadata['statement_import_issues'] = retained_issues(metadata['statement_import_original'],
                StatementImportRequest.model_validate(reviewed), arithmetic=checks) + coverage_issues
            # A corrected currency belongs to this record, not automatically to
            # every other record from an unidentified-currency statement.
            if not usable_currency(raw.get('currency')):
                resolved = {r['id'] for r in metadata['statement_incomplete_records'] if r.get('resolved_transaction_id')}
                metadata['statement_import_issues'] = [i for i in metadata['statement_import_issues']
                    if not (i.get('field') == 'currency' and i.get('row_id') in resolved)]
            document.metadata_ = metadata
            if period:
                reconcile_period(session, period)
            session.commit()
            run.transaction_admitted(1)
            return dict(transaction_id=str(transaction.id), created=True)
