"""Case-scoped automatic statement review assembled from stored source tables."""
import re
from sqlalchemy import select
from postgres.models.evidence import EvidenceFile, EvidenceDocumentText, EvidenceTableGeometry
from services.financial.candidate_sources import read_candidate_source
from services.financial.pdf_candidates import PdfMappingError, _digest
from services.financial.statement_import_proposal import propose_table, VERSION


def _label(content, labels):
    pattern = r'(?im)^\s*(?:' + '|'.join(re.escape(x) for x in labels) + r')\s*:\s*([^\n]+)'
    values = sorted(set(m.group(1).strip() for m in re.finditer(pattern, content)))
    return values[0] if len(values) == 1 else ''


def _period(value):
    from datetime import datetime
    parts = re.split(r'\s+(?:-|to)\s+', value, flags=re.I)
    if len(parts) != 2:
        return '', ''
    dates = []
    for part in parts:
        parsed = None
        for fmt in ('%Y-%m-%d', '%B %d, %Y', '%b %d, %Y'):
            try:
                parsed = datetime.strptime(part.strip(), fmt).date().isoformat()
                break
            except ValueError:
                pass
        if parsed is None:
            return '', ''
        dates.append(parsed)
    return tuple(dates) if dates[0] <= dates[1] else ('', '')


def _date_roles(fields):
    return [key for key in ('date', 'booking_date', 'value_date') if fields.get(key) or key + '_column' in fields] or ['date']


def _primary_date_role(fields):
    return next((key for key in ('date', 'booking_date', 'value_date') if fields.get(key)), _date_roles(fields)[0])


def _reading_dates(fields, reviewed_date, date_values=None):
    # The editable date keeps the meaning of the first populated source date.
    primary = _primary_date_role(fields)
    names = {'date': 'transaction_date', 'booking_date': 'posted_date', 'value_date': 'value_date'}
    result = {names[key]: date.fromisoformat(value) for key, value in fields.items() if key in names and value}
    result[names[primary]] = date.fromisoformat(reviewed_date)
    for key, value in (date_values or {}).items():
        if value:
            result[names[key]] = date.fromisoformat(value)
        else:
            result.pop(names[key], None)
    return result


def _existing_statement(session, case_id, file, statement_id, addresses=(), row_addresses=None, source_regions=None):
    from postgres.models.financial import FinancialSourceDocument
    candidates = session.scalars(select(FinancialSourceDocument).where(
        FinancialSourceDocument.case_id == case_id,
        FinancialSourceDocument.sha256_at_ingestion == file.sha256,
        FinancialSourceDocument.status != 'superseded').order_by(FinancialSourceDocument.id))
    addresses = set(addresses)
    row_addresses = {tuple(value) for value in row_addresses} if row_addresses is not None else None
    matches = []
    for item in candidates:
        metadata = item.metadata_ or {}
        if metadata.get('statement_import_statement_id') in (None, statement_id):
            matches.append(item)
            continue
        previous = metadata.get('statement_import_original', {}).get('sources', [])
        previous_addresses = {(source['page_number'], source['table_index']) for source in previous}
        previous_rows = metadata.get('statement_import_original', {}).get('statement_row_addresses')
        if row_addresses is not None and previous_rows is not None:
            from services.financial.statement_import_andrews import source_regions_overlap
            overlap = source_regions_overlap(source_regions,
                metadata.get('statement_import_original', {}).get('statement_source_regions'))
            if overlap is not None:
                if overlap:
                    matches.append(item)
                continue
            # If position comparison is unavailable, do not equate row numbers
            # from different OCR readings. A shared page requires source review.
            if {p for p, _ in addresses} & {p for p, _ in previous_addresses}:
                matches.append(item)
            continue
        # A reread may change the printed account or period. Overlapping source
        # tables still require replacement rather than being counted again.
        if addresses & previous_addresses:
            matches.append(item)
    if len(matches) > 1:
        raise PdfMappingError(
            'This reading overlaps more than one imported statement. No imports were changed. '
            'Review the statement periods and existing imports before replacing them.', 409)
    return matches[0] if matches else None


def read_statement_import(session, *, case_id, evidence_file_id, currency=None, statement_id=None):
    file = session.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_file_id,
                                                    EvidenceFile.case_id == case_id))
    if file is None:
        raise PdfMappingError('Statement not found in this case.', 404)
    text = session.get(EvidenceDocumentText, evidence_file_id)
    if text is None:
        raise PdfMappingError('Prepare this PDF before opening its statement review.', 409)
    sections = list(re.finditer(r'(?im)^\s*TRANSACTION HISTORY\s*$', text.content))
    # A labelled beneficiary block below a single transaction history is not
    # the statement account. Multiple statement sections remain unresolved.
    header = text.content[:sections[0].start()] if len(sections) == 1 else text.content
    metadata = dict(holder=_label(header, ('Account Name', 'Account Holder')),
                    account_number=_label(header, ('Account Number', 'Account No', 'IBAN')),
                    period=_label(header, ('Statement Period', 'Period')),
                    currency=_label(header, ('Currency',)).upper())
    banks = [line.strip() for line in header.splitlines() if re.search(r'\b(?:bank|credit union)\b', line, re.I) and not re.search(r'statement|account|:', line, re.I)]
    metadata['institution'] = _label(header, ('Bank', 'Institution')) or (banks[0] if len(set(banks)) == 1 else '')
    metadata['period_start'], metadata['period_end'] = _period(metadata['period'])
    chosen_currency = currency or metadata['currency']
    issues = []
    if not metadata['holder']:
        issues.append('Check the account holder. It could not be identified automatically.')
    if not metadata['account_number']:
        issues.append('Check the account number. It could not be identified automatically.')
    pages = list(session.scalars(select(EvidenceTableGeometry).where(
        EvidenceTableGeometry.evidence_file_id == evidence_file_id).order_by(EvidenceTableGeometry.page_number)))
    if not pages:
        raise PdfMappingError('No readable tables were prepared. Reprocess this PDF or inspect its extraction errors.', 409)
    if len(pages) > 500:
        raise PdfMappingError('This statement exceeds the 500-page review limit. No pages were omitted.', 422)
    from services.financial.statement_import_catalog import statement_catalog
    all_sources = [read_candidate_source(session, case_id=case_id, evidence_file_id=evidence_file_id,
                    page_number=page.page_number, table_index=index)
                   for page in pages for index in range(len(page.payload or []))]
    from services.financial.payment_document_review import payment_document_response
    payment_document = payment_document_response(file, all_sources, case_id=case_id)
    if payment_document is not None:
        return dict(case_id=str(case_id), evidence_file_id=str(file.id), filename=file.original_filename,
            metadata=metadata, currency='', rows=[], sources=[], issues=[], transaction_count=0,
            needs_attention=0, revision=payment_document['revision'], applied=False,
            document_review=payment_document, page_numbers=payment_document['page_numbers'])
    catalog = statement_catalog(all_sources)
    choices = catalog['statements']
    selected = next((item for item in choices if item['id'] == statement_id), None)
    if statement_id and selected is None:
        raise PdfMappingError('This statement period is no longer available. Reload the document.', 409)
    if len(choices) == 1 and selected is None:
        selected = choices[0]
        statement_id = selected['id']
    if len(choices) > 1 and selected is None:
        return dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id), filename=file.original_filename,
                    metadata=metadata, currency=chosen_currency, rows=[], sources=[], issues=[],
                    transaction_count=0, needs_attention=0, revision=_digest(catalog),
                    statement_choices=choices, statement_id=None, page_numbers=[p.page_number for p in pages], applied=False)
    sources = all_sources
    if selected:
        addresses = {(item['page_number'], item['table_index']) for item in selected['sources']}
        sources = [source for source in all_sources if (source['page_number'], source['table_index']) in addresses]
        metadata.update(account_type=selected.get('account_type', 'credit_card'), institution=selected['institution'], account_number=selected['account_reference'],
                        period_start=selected['period_start'], period_end=selected['period_end'],
                        period=(selected['period_start'] + ' - ' + selected['period_end']) if selected['period_start'] else selected.get('printed_statement_date', ''))
        if selected.get('layout_id') in ('capital-one-card', 'merrick-card'):
            metadata['balance_convention'] = 'liability_owed'
        # A selected account must not inherit a name from a different section
        # elsewhere in the same PDF.
        metadata['holder'] = selected.get('holder', '')
        holders = set()
        for source in sources:
            if selected.get('layout_id') == 'capital-one-card' and source.get('layout_context'):
                # Empty purchase/payment sections still name the printed cardholder
                # on statements containing only fees or interest.
                heading = re.compile(r'(.+) #' + re.escape(selected['account_reference'][-4:]) + r': (?:Payments, Credits and Adjustments|Transactions)')
                holders.update(match[1] for row in source['rows'] for cell in row['cells']
                               if (match := heading.fullmatch(cell['expected_text'].strip())))
            for item in (source.get('layout_context') or {}).get('rows', []):
                if item['card_ending'] == selected['account_reference'][-4:]:
                    holders.add(item['section_source']['expected_text'].split(' #', 1)[0])
        if len(holders) == 1:
            metadata['holder'] = next(iter(holders))
        issues = [issue for issue in issues if not ('account number' in issue and metadata['account_number']) and not ('account holder' in issue and metadata['holder'])]
        if not metadata['holder'] and not any('account holder' in issue for issue in issues):
            issues.append('Check the account holder. It could not be identified for this account section.')
        if selected.get('date_conflict'):
            issues.append('The statement date and billing-cycle closing date were read differently. Compare both dates with the PDF and correct the transaction dates before importing.')
        elif selected.get('layout_id') == 'merrick-card' and not selected.get('statement_date'):
            issues.append('The printed statement date could not be read. Check it against the PDF. Transaction years are proposed only where the printed month and year-to-date heading agree.')
        if metadata.get('balance_convention') == 'liability_owed':
            issues.append('This is a credit-card statement. Debits increase the amount owed; credits reduce it. A card ending is a partial account reference.')
        if selected.get('layout_id') == 'andrews-share-statement':
            metadata['balance_convention'] = 'asset_balance'
            if selected.get('account_closure'):
                metadata['account_closure'] = selected['account_closure']
            if selected['account_type'] == 'other':
                issues.append('The printed account label is VISA PAYMENT. Its account type is recorded as Other; this label does not establish a credit-card balance.')
            issues.append('Reviewing ' + selected['account_label'] + ', share ' + selected['share_reference'] + '. Other account sections in this PDF are reviewed separately.')
            if selected.get('uses_printed_page_order'):
                issues.append('These statement pages are out of order in the PDF. Payments follow the printed page numbers. The source viewer keeps the original PDF page numbers.')
        if catalog['unclassified_sources']:
            issues.append('Some pages could not be assigned to a printed statement period. They remain available in the original PDF.')
    all_page_numbers = sorted({p.page_number for p in pages} | {loc['page_number'] for loc in (text.source_locations or []) if type(loc.get('page_number')) is int and loc['page_number'] > 0})
    if all_page_numbers and max(all_page_numbers) > 500:
        raise PdfMappingError('This PDF exceeds the 500-page review limit.', 422)
    recognised_pages = {s['page_number'] for s in all_sources}
    unassigned_pages = sorted({s['page_number'] for s in catalog['unclassified_sources']} | (set(all_page_numbers) - recognised_pages))
    rows = []
    if not chosen_currency:
        return dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id), filename=file.original_filename,
                    metadata=metadata, currency='', rows=[], sources=[], issues=issues + ['Choose the statement currency to read its amounts.'],
                    statement_choices=choices, statement_id=statement_id,
                    transaction_count=0, needs_attention=1, revision=_digest(dict(file=str(file.id), text=text.content_sha256, version=VERSION)), applied=False)
    from services.financial.money import get_currency, MoneyError
    try:
        get_currency(chosen_currency)
    except MoneyError as exc:
        raise PdfMappingError(str(exc), 422) from exc
    if selected and selected.get('layout_id') == 'andrews-share-statement':
        from services.financial.statement_import_andrews import propose_andrews_statement
        proposal = propose_andrews_statement(sources, chosen_currency, selected)
        rows.extend(proposal['rows'])
        issues.extend(proposal.get('issues', []))
        if len(rows) > 1000:
            raise PdfMappingError('This statement exceeds the 1,000-row review limit. No rows were omitted.', 422)
    for source in ([] if selected and selected.get('layout_id') == 'andrews-share-statement' else sources):
        try:
            if selected and selected.get('layout_id') == 'merrick-card':
                from services.financial.statement_import_merrick import propose_merrick_table
                proposal = propose_merrick_table(source, chosen_currency, selected)
            elif selected:
                from services.financial.statement_import_card import propose_card_table
                proposal = propose_card_table(source, chosen_currency, selected)
            else:
                proposal = propose_table(source, chosen_currency)
        except ValueError as exc:
            raise PdfMappingError(str(exc), 422) from exc
        rows.extend(proposal['rows'])
        issues.extend(proposal.get('issues', []))
        if len(rows) > 1000:
            raise PdfMappingError('This statement exceeds the 1,000-row review limit. No rows were omitted.', 422)
    if metadata.get('balance_convention') == 'liability_owed':
        for role in ('opening', 'closing'):
            controls = [row for row in rows if row['kind'] == 'balance'
                        and row['fields'].get('description', '').lower() == f'{role} balance']
            if len(controls) > 1:
                issues.append(f'More than one {role} amount owed was read. Check the account-summary rows and clear any repeated balance before importing.')
    from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
    from services.financial.duplicate_decisions import duplicate_revision
    from sqlalchemy import func
    row_addresses = ([[s['page_number'], s['table_index'], index]
                      for s in selected['sources'] for index in s['row_indices']]
                     if selected and selected.get('layout_id') == 'andrews-share-statement' else None)
    source_regions = None
    if row_addresses is not None:
        from services.financial.statement_import_andrews import andrews_source_regions
        source_regions = andrews_source_regions(sources, selected)
    current = _existing_statement(session, case_id, file, statement_id,
        ((source['page_number'], source['table_index']) for source in sources), row_addresses, source_regions)
    current_import = None
    if current is not None:
        current_import = dict(source_document_id=str(current.id), evidence_file_id=str(current.evidence_file_id),
            revision=duplicate_revision(session, current), transaction_count=session.scalar(select(func.count()).select_from(FinancialTransaction).where(FinancialTransaction.source_document_id == current.id, FinancialTransaction.ledger_status == 'admitted')))
        recorded_review = (current.metadata_ or {}).get('statement_import_request', {})
        current_import['review_decisions'] = [
            dict(description=row.get('description', ''), date=row.get('date', ''),
                 excluded=bool(row.get('excluded')), reason=row['reason'])
            for row in recorded_review.get('rows', []) if row.get('reason')]
        current_import['details_reason'] = recorded_review.get('details_reason', '')
    snapshot = dict(version=VERSION, source_sha256=file.sha256, sources=sources,
                    metadata=metadata, currency=chosen_currency, statement_id=statement_id)
    if row_addresses is not None:
        snapshot['statement_row_addresses'] = row_addresses
    balance_only = (metadata.get('account_type') in ('savings', 'checking', 'other')
                    and not any(not row['excluded'] for row in rows)
                    and all(sum(row['kind'] == 'balance' and row['fields'].get('description', '').lower() == role + ' balance'
                                for row in rows) == 1 for role in ('opening', 'closing')))
    closure_only = bool(metadata.get('account_closure') and selected and selected.get('layout_id') == 'andrews-share-statement'
                        and not any(not row['excluded'] for row in rows)
                        and any(row['kind'] == 'balance' and row['fields'].get('description') == 'Opening Balance'
                                and 'balance' in row['fields'] for row in rows))
    return dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id), filename=file.original_filename,
                metadata=metadata, currency=chosen_currency, rows=rows, sources=sources, issues=issues,
                can_record_account_closure=closure_only,
                can_import_balances=balance_only,
                page_numbers=all_page_numbers,
                unassigned_page_numbers=unassigned_pages if selected else [],
                statement_page_numbers=(selected['page_numbers'] if selected and selected.get('uses_printed_page_order')
                                        else sorted({source['page_number'] for source in sources})),
                statement_choices=choices, statement_id=statement_id,
                statement_row_addresses=row_addresses,
                statement_source_regions=source_regions,
                transaction_count=sum(not row['excluded'] for row in rows),
                needs_attention=sum(bool(row['issues']) for row in rows) + len(issues),
                revision=_digest(snapshot), current_import=current_import, applied=False)

# A single confirmation carries all reviewed rows. The original proposal stays
# separate from edits in the stored source record.
from datetime import date
from typing import Annotated, Literal
from types import SimpleNamespace
from uuid import UUID
from pydantic import Field, model_validator
from services.financial.pdf_candidates import _Contract, _Digest


class ImportRow(_Contract):
    id: Annotated[str, Field(min_length=1, max_length=80)]
    excluded: bool = False
    manual_page: Annotated[int | None, Field(ge=1, le=500)] = None
    date: str = ''
    date_values: dict[Literal['date', 'booking_date', 'value_date'], str] = Field(default_factory=dict)
    description: Annotated[str, Field(max_length=4096)] = ''
    counterparty: Annotated[str, Field(max_length=4096)] = ''
    amount_minor: Annotated[str, Field(pattern=r'^(0|[1-9][0-9]{0,18})$')] = '0'
    direction: Literal['credit', 'debit'] | None = None
    balance_minor: Annotated[str | None, Field(pattern=r'^-?(0|[1-9][0-9]{0,18})$')] = None
    reason: Annotated[str, Field(max_length=4096)] = ''

    @model_validator(mode='after')
    def valid_transaction(self):
        for value in self.date_values.values():
            if value and date.fromisoformat(value).isoformat() != value:
                raise ValueError('Each additional date must be a complete calendar date or left blank.')
        if self.balance_minor is not None and not -9223372036854775808 <= int(self.balance_minor) <= 9223372036854775807:
            raise ValueError('The running balance exceeds the supported range.')
        if not self.excluded:
            if self.direction is None:
                raise ValueError('Choose Credit or Debit for this transaction.')
            if date.fromisoformat(self.date).isoformat() != self.date:
                raise ValueError('A complete transaction date is required.')
            if not self.description.strip():
                raise ValueError('A transaction description is required.')
            if not 0 < int(self.amount_minor) <= 9223372036854775807:
                raise ValueError('A positive transaction amount within the supported range is required.')
        return self


class StatementImportRequest(_Contract):
    expected_revision: _Digest
    statement_id: _Digest | None = None
    replaces_source_document_id: UUID | None = None
    replacement_revision: _Digest | None = None
    currency: Annotated[str, Field(pattern=r'^[A-Z]{3}$')]
    account_number: Annotated[str, Field(min_length=1, max_length=128)]
    institution: Annotated[str, Field(max_length=128)] = ''
    holder: Annotated[str, Field(min_length=1, max_length=128)]
    period_start: str = ''
    period_end: str = ''
    details_reason: Annotated[str, Field(max_length=4096)] = ''
    rows: Annotated[list[ImportRow], Field(min_length=1, max_length=1000)]

    @model_validator(mode='after')
    def distinct_rows(self):
        if len({r.id for r in self.rows}) != len(self.rows):
            raise ValueError('A statement row cannot be included twice.')
        if bool(self.replaces_source_document_id) != bool(self.replacement_revision):
            raise ValueError('A replacement must identify the current imported version.')
        if self.replaces_source_document_id and not self.details_reason.strip():
            raise ValueError('Explain why the reprocessed version should replace the current import.')
        if bool(self.period_start) != bool(self.period_end):
            raise ValueError('Both statement period dates are required together.')
        if self.period_start:
            for value in (self.period_start, self.period_end):
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError('Statement period dates must be full dates.')
            if self.period_start > self.period_end:
                raise ValueError('Statement period runs backwards.')
        if not self.holder.strip() or not self.account_number.strip():
            raise ValueError('Check the account details.')
        return self


def check_import_request(proposal, request):
    if proposal.get("statement_id") != request.statement_id:
        raise PdfMappingError("Reload the selected statement period before confirming.", 409)
    if request.expected_revision != proposal['revision']:
        raise PdfMappingError('The prepared statement changed. Reload its review before importing.', 409)
    if any(getattr(request, field) != proposal['metadata'].get(field, '') for field in ('holder', 'account_number', 'institution', 'period_start', 'period_end')) and not request.details_reason.strip():
        raise PdfMappingError('Explain the corrected account or statement details.', 422)
    originals = {row['id']: row for row in proposal['rows']}
    if not any(not row.excluded for row in request.rows):
        controls = [row for row in request.rows if row.id in originals and originals[row.id]['kind'] == 'balance'
                    and originals[row.id]['fields'].get('description', '').lower() in ('opening balance', 'closing balance')]
        if not proposal.get('can_record_account_closure') and (not proposal.get('can_import_balances') or len(controls) != 2
                or any(row.balance_minor is None for row in controls)
                or controls[0].balance_minor != controls[1].balance_minor):
            raise PdfMappingError('A statement without transactions must have matching opening and closing balances. Check both against the PDF.', 422)
    submitted = {row.id for row in request.rows}
    if not set(originals) <= submitted:
        raise PdfMappingError('The review must account for every prepared row. Reload the statement.', 409)
    for row in request.rows:
        if row.id not in originals:
            if not row.id.startswith('manual:') or row.manual_page not in proposal.get('page_numbers', []):
                raise PdfMappingError('A manually added transaction must identify an existing source page.', 422)
            originals[row.id] = dict(id=row.id, page_number=row.manual_page, table_index=None,
                row_index=None, source_revision=proposal['revision'], source_cells=[], fields={},
                issues=['Manually added transaction'], excluded=False, kind='manual_entry')
        elif row.manual_page is not None:
            raise PdfMappingError('The page of an extracted row cannot be reassigned.', 422)
    for row in request.rows:
        original = originals[row.id]
        fields = original['fields']
        additional_roles = set(_date_roles(fields)) - {_primary_date_role(fields)}
        if not set(row.date_values) <= additional_roles:
            raise PdfMappingError('Only separately identified source dates can be corrected here. Reload the statement.', 422)
        if fields.get('account_closed_on') and not row.excluded:
            raise PdfMappingError('An account closure notice is not a payment. Keep it outside the transaction list.', 422)
        if fields.get('balance_convention') == 'liability_owed':
            if not row.excluded:
                raise PdfMappingError('An account-summary balance is not a transaction. Keep it outside the transaction list.', 422)
        if proposal['metadata'].get('balance_convention') == 'liability_owed' and row.balance_minor == '-9223372036854775808':
            raise PdfMappingError('This amount owed exceeds the supported balance range.', 422)
        changed = row.excluded != original['excluded'] or (not row.excluded and (
            row.date != (fields.get('date') or fields.get('booking_date') or fields.get('value_date') or '')
            or row.description != fields.get('description', '')
            or row.counterparty != fields.get('counterparty', '')
            or row.amount_minor != fields.get('amount_minor')
            or row.direction != fields.get('direction'))) or row.balance_minor != fields.get('balance')
        changed = changed or any(value != fields.get(key, '') for key, value in row.date_values.items())
        if (changed or original['issues']) and not row.reason.strip():
            raise PdfMappingError(f"Explain the correction or decision for row {row.id}.", 422)
    return originals


def confirm_statement_import(*, session_factory, case_id, evidence_file_id, request, actor, resolve_path):
    """One transaction writes the account, source and all money rows, or none."""
    import hashlib
    from postgres.models.case import Case
    from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
    from services.financial.accounts import AccountDraft, record_account
    from services.financial.documents import SourceDocumentDraft, record_source_document
    from services.financial.proof_class import SourceShape
    from services.financial.runs import ingestion_run
    from services.financial.transactions import TransactionDraft, record_transactions
    from services.financial.references import RowReading
    from services.financial.locators import Locator, SourceRectangle
    from postgres.models.enums import ExtractionLayer, LocatorKind, TransactionDirection

    request = StatementImportRequest.model_validate(request)
    request_hash = _digest(request.model_dump(mode='json'))
    with ingestion_run(case_id=case_id, actor=SimpleNamespace(id=actor.user_id, email=actor.email),
            session_factory=session_factory, config=dict(operation='statement_import', version=VERSION,
                evidence_file_id=str(evidence_file_id), request_sha256=request_hash)) as run:
        with session_factory() as session:
            try:
                if session.scalar(select(Case.id).where(Case.id == case_id).with_for_update()) is None:
                    raise PdfMappingError('Case not found.', 404)
                file = session.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_file_id,
                    EvidenceFile.case_id == case_id).with_for_update())
                if file is None:
                    raise PdfMappingError('Statement not found in this case.', 404)
                session.execute(select(EvidenceDocumentText).where(EvidenceDocumentText.evidence_file_id == evidence_file_id).with_for_update()).all()
                session.execute(select(EvidenceTableGeometry).where(EvidenceTableGeometry.evidence_file_id == evidence_file_id).order_by(EvidenceTableGeometry.page_number).with_for_update()).all()
                proposal = read_statement_import(session, case_id=case_id, evidence_file_id=evidence_file_id,
                                                 currency=request.currency, statement_id=request.statement_id)
                if proposal.get('document_review') is not None:
                    raise PdfMappingError('Save this wire report from its document review. It cannot be imported as an account statement.', 422)
                existing = _existing_statement(session, case_id, file, request.statement_id,
                    ((source['page_number'], source['table_index']) for source in proposal['sources']),
                    proposal.get('statement_row_addresses'), proposal.get('statement_source_regions'))
                if existing is not None:
                    existing = session.scalar(select(FinancialSourceDocument).where(
                        FinancialSourceDocument.id == existing.id, FinancialSourceDocument.status != 'superseded'
                    ).with_for_update().execution_options(populate_existing=True))
                    if existing is None:
                        raise PdfMappingError('The current statement changed. Reload the review.', 409)
                replacing = None
                if existing is not None:
                    if (existing.metadata_ or {}).get('statement_import_request_sha256') == request_hash:
                        imported_count = sum(not row['excluded'] for row in existing.metadata_['statement_import_request']['rows'])
                        return dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id), source_document_id=str(existing.id), transaction_count=imported_count, account_closed_on=((existing.metadata_.get('statement_import_original', {}).get('metadata', {}).get('account_closure')) or {}).get('date'), created=False, applied=True)
                    from services.financial.duplicate_decisions import duplicate_revision
                    parent = (file.metadata_ or {}).get('statement_parent_evidence_id')
                    root = (file.metadata_ or {}).get('statement_root_evidence_id')
                    current_file = session.get(EvidenceFile, existing.evidence_file_id)
                    if current_file is None:
                        raise PdfMappingError('The existing import has no available evidence file to compare. Open its source history before replacing it.', 409)
                    current_root = (current_file.metadata_ or {}).get('statement_root_evidence_id', str(current_file.id))
                    if not parent or root != current_root or request.replaces_source_document_id != existing.id:
                        raise PdfMappingError('This statement already has imported transactions. Open them to correct values, or reprocess a new version.', 409)
                    from postgres.models.financial import FinancialStatementPeriod
                    session.execute(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id == existing.id).with_for_update()).all()
                    session.execute(select(FinancialTransaction).where(FinancialTransaction.source_document_id == existing.id).with_for_update()).all()
                    if request.replacement_revision != duplicate_revision(session, existing):
                        raise PdfMappingError('The current import was edited. Reload the comparison before replacing it.', 409)
                    replacing = existing
                elif request.replaces_source_document_id is not None:
                    raise PdfMappingError('The import selected for replacement is no longer current.', 409)
                originals = check_import_request(proposal, request)
                path = resolve_path(file.stored_path)
                if path is None or not path.is_file() or path.stat().st_size > 256 * 1024 * 1024:
                    raise PdfMappingError('The original statement is unavailable for verification.', 409)
                digest = hashlib.sha256()
                bytes_read = 0
                with path.open('rb') as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                        bytes_read += len(chunk)
                        if bytes_read > 256 * 1024 * 1024:
                            raise PdfMappingError('The source exceeds the supported file size.', 409)
                        digest.update(chunk)
                if digest.hexdigest() != file.sha256:
                    raise PdfMappingError('The source file changed. Reprocess it before importing.', 409)
                from services.financial.accounts import AccountIdentityError
                account_fields = dict(institution_name=request.institution or None,
                    identifier_as_printed=request.account_number, holder_name=request.holder,
                    account_type=proposal['metadata'].get('account_type'),
                    currency=request.currency, metadata=dict(display_label=request.holder + ' · ' + request.account_number,
                        statement_source_file_id=str(evidence_file_id)))
                try:
                    account_draft = AccountDraft.observed(**account_fields)
                except AccountIdentityError:
                    account_draft = AccountDraft.unidentified(distinguisher='statement:' + str(evidence_file_id) + ':' + request.currency
                        + (':' + request.statement_id if request.statement_id else ''), **account_fields)
                account = record_account(session, run, account_draft)
                shares_source_references = session.scalar(select(FinancialSourceDocument.id).where(
                    FinancialSourceDocument.case_id == case_id, FinancialSourceDocument.sha256_at_ingestion == file.sha256).limit(1)) is not None
                document = record_source_document(session, run, SourceDocumentDraft(
                    evidence_file_id=evidence_file_id, sha256_at_ingestion=file.sha256,
                    document_type='statement_review', shape=SourceShape.selected_document_rows,
                    extraction_layer=ExtractionLayer.investigator_review,
                    parser_name=VERSION, parser_version='1', metadata=dict(
                        statement_import_statement_id=request.statement_id,
                        statement_import_request_sha256=request_hash, statement_import_request=request.model_dump(mode='json'),
                        statement_import_original=proposal, statement_import_original_sha256=_digest(proposal), coverage='all_prepared_rows_reviewed',
                        whole_document_extraction_verified=False)))
                from services.financial.periods import StatementPeriodDraft, PeriodBounds, BalanceObservation, record_statement_period
                from services.financial.money import Money
                balance_sign = -1 if proposal['metadata'].get('balance_convention') == 'liability_owed' else 1
                bounds = PeriodBounds.printed(date.fromisoformat(request.period_start), date.fromisoformat(request.period_end)) if request.period_start else PeriodBounds()
                openings = [row for row in request.rows if row.excluded and originals[row.id]['kind'] == 'balance'
                    and 'opening' in originals[row.id]['fields'].get('description', '').lower() and row.balance_minor is not None]
                opening = BalanceObservation.printed(Money(balance_sign * int(openings[0].balance_minor), request.currency)) if len(openings) == 1 else BalanceObservation.absent()
                closings = [row for row in request.rows if row.excluded and originals[row.id]['kind'] == 'balance'
                    and originals[row.id]['fields'].get('description', '').strip().lower() == 'closing balance'
                    and row.balance_minor is not None]
                closing = BalanceObservation.printed(Money(balance_sign * int(closings[0].balance_minor), request.currency)) if len(closings) == 1 else BalanceObservation.absent()
                period = record_statement_period(session, run, StatementPeriodDraft(account_id=account.id,
                    source_document_id=document.id, currency=request.currency, bounds=bounds, opening=opening, closing=closing))
                if proposal['metadata'].get('balance_convention') in ('liability_owed', 'asset_balance'):
                    from services.financial.statement_import_controls import retain_import_controls
                    retain_import_controls(document, period, request, originals, openings, closings,
                                           balance_convention=proposal['metadata']['balance_convention'])
                drafts = []
                for row in request.rows:
                    if row.excluded:
                        continue
                    original = originals[row.id]
                    rectangles = [Locator.from_json(c['locator']).rectangle for c in original['source_cells']]
                    rectangles = [r for r in rectangles if r is not None]
                    locator = Locator(kind=LocatorKind.page_only, page_number=original['page_number'])
                    if rectangles:
                        first = rectangles[0]
                        locator = Locator(kind=LocatorKind.page_rectangle, rectangle=SourceRectangle(
                            page_number=first.page_number, page_width=first.page_width, page_height=first.page_height,
                            x0=min(r.x0 for r in rectangles), y0=min(r.y0 for r in rectangles),
                            x1=max(r.x1 for r in rectangles), y1=max(r.y1 for r in rectangles)))
                    drafts.append(TransactionDraft(row_index=len(drafts), account_id=account.id, locator=locator, statement_period_id=period.id,
                        reading=RowReading(currency=request.currency, amount_minor=int(row.amount_minor),
                            direction=TransactionDirection(row.direction), **_reading_dates(original['fields'], row.date, row.date_values),
                            description=row.description, counterparty_raw=row.counterparty or None,
                            bank_reference=original['fields'].get('bank_reference'),
                            running_balance_minor=balance_sign * int(row.balance_minor) if row.balance_minor is not None else None), provenance=dict(statement_import_original=original,
                                statement_import_review=row.model_dump(mode='json'),
                                confirmed_by=dict(user_id=str(actor.user_id), name=actor.name, email=actor.email))))
                transactions = record_transactions(session, run, document, drafts, retain_prior_versions=shares_source_references)
                from services.financial.reconcile import reconcile_period
                reconcile_period(session, period)
                if replacing is not None:
                    from services.financial.duplicates import _supersede, store_fingerprint
                    from postgres.models.enums import DuplicateMatchRung
                    store_fingerprint(session, replacing)
                    store_fingerprint(session, document)
                    _supersede(session, replacing, document.id, case_id=case_id, rung=DuplicateMatchRung.identical_bytes, actor=actor, ingestion_run_id=run.run_id,
                        reason="Statement reread replaces the prior import: " + request.details_reason)
                session.commit()
                run.document_seen()
                run.transaction_admitted(len(transactions))
                return dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id),
                    source_document_id=str(document.id), account_id=str(account.id),
                    transaction_count=len(transactions), account_closed_on=(proposal['metadata'].get('account_closure') or {}).get('date'), created=True, applied=True)
            except Exception:
                session.rollback()
                raise
