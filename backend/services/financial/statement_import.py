"""Case-scoped automatic statement review assembled from stored source tables."""
import re
from sqlalchemy import select
from postgres.models.evidence import EvidenceFile, EvidenceDocumentText, EvidenceTableGeometry
from services.financial.candidate_sources import read_candidate_source
from services.financial.pdf_candidates import PdfMappingError, _digest
from services.financial.statement_import_proposal import propose_table, VERSION

MAX_STATEMENT_TRANSACTIONS = 25000
MAX_STATEMENT_REVIEW_ROWS = 100000


def _imported_account_id(session, source_document_id):
    from postgres.models.financial import FinancialStatementPeriod, FinancialSourceDocument
    accounts = list(session.scalars(select(FinancialStatementPeriod.account_id).where(
        FinancialStatementPeriod.source_document_id == source_document_id).distinct().limit(2)))
    if len(accounts) == 1:
        return str(accounts[0])
    document = session.get(FinancialSourceDocument, source_document_id)
    return (document.metadata_ or {}).get('statement_account_id') if document else None


def _check_review_size(rows):
    # Keep headings and balance controls available without making them consume
    # the payment allowance. Unknown rows still count until they are resolved.
    if len(rows) > MAX_STATEMENT_REVIEW_ROWS:
        raise PdfMappingError('This statement exceeds the 100,000-row review limit, including headings and other page text. No rows were omitted.', 422)
    if sum(not row['excluded'] for row in rows) > MAX_STATEMENT_TRANSACTIONS:
        raise PdfMappingError('This statement has more than 25,000 possible transactions. Review a shorter statement period. No rows were omitted.', 422)


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
    # An edited additional date replaces its unreadable original before parsing.
    values = {**fields, **(date_values or {})}
    result = {names[key]: date.fromisoformat(value) for key, value in values.items() if key in names and value and key != primary}
    result[names[primary]] = date.fromisoformat(reviewed_date)
    for key, value in (date_values or {}).items():
        if value:
            result[names[key]] = date.fromisoformat(value)
        else:
            result.pop(names[key], None)
    return result


def _existing_statement(session, case_id, file, statement_id, addresses=(), row_addresses=None, source_regions=None, *, excluded_duplicates=False):
    from postgres.models.financial import FinancialSourceDocument
    query = select(FinancialSourceDocument).where(
        FinancialSourceDocument.case_id == case_id,
        FinancialSourceDocument.sha256_at_ingestion == file.sha256)
    if excluded_duplicates:
        # A fresh OCR reading of this same source must not bypass its recorded
        # duplicate exclusion. Unrelated copies with the same bytes are not
        # given that file's exclusion, and normal replacement history is skipped.
        from uuid import UUID
        try:
            root_id = UUID((file.metadata_ or {}).get('statement_root_evidence_id', str(file.id)))
        except (ValueError, TypeError, AttributeError):
            raise PdfMappingError('The statement source history is invalid. Review its file history before importing.', 409)
        related_files = select(EvidenceFile.id).where(
            EvidenceFile.case_id == case_id,
            (EvidenceFile.id == root_id) |
            (EvidenceFile.metadata_['statement_root_evidence_id'].as_string() == str(root_id)))
        query = query.where(FinancialSourceDocument.status == 'superseded',
            FinancialSourceDocument.duplicate_match_rung.is_not(None),
            FinancialSourceDocument.evidence_file_id.in_(related_files))
    else:
        query = query.where(FinancialSourceDocument.status != 'superseded')
    candidates = session.scalars(query.order_by(FinancialSourceDocument.id))
    addresses = set(addresses)
    row_addresses = {tuple(value) for value in row_addresses} if row_addresses is not None else None
    matches = []
    for item in candidates:
        if excluded_duplicates:
            retained = session.get(FinancialSourceDocument, item.superseded_by_id)
            replacement_request = (retained.metadata_ or {}).get('statement_import_request', {}) if retained else {}
            if (retained and retained.case_id == case_id and
                    replacement_request.get('replaces_source_document_id') == str(item.id)):
                # A confirmed reread replaces this reading within the same PDF
                # history. That is not an investigator's duplicate exclusion.
                continue
        metadata = item.metadata_ or {}
        if metadata.get('statement_import_statement_id') in (None, statement_id):
            matches.append(item)
            continue
        if (item.evidence_file_id == file.id and statement_id in
                metadata.get('statement_import_original', {}).get('assigned_period_ids', [])):
            # Explicitly assigned periods in this same reading may share a PDF
            # table. A neighbouring period is not a duplicate of this one.
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


def read_statement_import(session, *, case_id, evidence_file_id, currency=None, statement_id=None, _cache=None, _include_period_checks=True, _apply_assignments=True):
    file = session.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_file_id,
                                                    EvidenceFile.case_id == case_id))
    if file is None:
        raise PdfMappingError('Statement not found in this case.', 404)
    from services.financial.file_visibility import require_financial_file
    require_financial_file(file)
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
    cache = _cache if _cache is not None else {}
    source_key = (str(case_id), str(evidence_file_id), text.content_sha256)
    if source_key not in cache:
        cache[source_key] = [read_candidate_source(session, case_id=case_id, evidence_file_id=evidence_file_id,
                        page_number=page.page_number, table_index=index)
                       for page in pages for index in range(len(page.payload or []))]
    all_sources = cache[source_key]
    from services.financial.payment_document_review import payment_document_response
    payment_document = payment_document_response(file, all_sources, case_id=case_id)
    if payment_document is not None:
        return dict(case_id=str(case_id), evidence_file_id=str(file.id), filename=file.original_filename,
            metadata=metadata, currency='', rows=[], sources=[], issues=[], transaction_count=0,
            needs_attention=0, revision=payment_document['revision'], applied=False,
            document_review=payment_document, page_numbers=payment_document['page_numbers'])
    catalog_key = ('catalog', source_key)
    if catalog_key not in cache:
        cache[catalog_key] = statement_catalog(all_sources)
    catalog = cache[catalog_key]
    from services.financial.deposit_receipt_proposal import deposit_receipt_choices
    from services.financial.statement_currency import currencies_by_statement, detect_statement_currency
    currencies_key = ('currencies', source_key)
    if currencies_key not in cache:
        cache[currencies_key] = currencies_by_statement(
            catalog['statements'] + deposit_receipt_choices(all_sources), all_sources)
    choices = cache[currencies_key]
    detected = {choice.get('currency', '') for choice in choices if not choice.get('document_kind')}
    detected_currency = (next(iter(detected)) if len(detected) == 1 else '') if choices else detect_statement_currency(all_sources, header_text=header)
    chosen_currency = currency or detected_currency
    from services.financial.review_recovery import recovery_state
    from services.financial.statement_review_checks import add_period_checks
    checks_key = ('checks', source_key, chosen_currency)
    if _include_period_checks:
        if checks_key not in cache:
            cache[checks_key] = add_period_checks(choices, all_sources, currency)
        choices = cache[checks_key]
        if _apply_assignments:
            from services.financial.statement_row_assignment import assignment_choices
            choices = assignment_choices(session, file, choices, chosen_currency, cache)
    selected = next((item for item in choices if item['id'] == statement_id), None)
    if statement_id and selected is None:
        raise PdfMappingError('This statement period is no longer available. Reload the document.', 409)
    if len(choices) == 1 and selected is None:
        selected = choices[0]
        statement_id = selected['id']
    if len(choices) > 1 and selected is None:
        recovery, _ = recovery_state(session, file, sources=all_sources, choices=choices,
            statement_id=None, revision=None, cache=cache)
        return dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id), filename=file.original_filename,
                    metadata=metadata, currency=chosen_currency, rows=[], sources=[], issues=[],
                    transaction_count=0, needs_attention=0, revision=_digest(dict(catalog=catalog, choices=choices)),
                    statement_choices=choices, statement_id=None, page_numbers=[p.page_number for p in pages], applied=False,
                    review_recovery=recovery)
    if selected and selected.get('document_kind'):
        document = payment_document_response(file, all_sources, case_id=case_id, document_id=selected['id'])
        if document is None:
            raise PdfMappingError('This receipt is no longer available. Reload the PDF.', 409)
        return dict(case_id=str(case_id), evidence_file_id=str(file.id), filename=file.original_filename,
            metadata=metadata, currency='', rows=[], sources=[], issues=[], transaction_count=0,
            needs_attention=0, revision=document['revision'], applied=False, document_review=document,
            statement_choices=choices, statement_id=selected['id'], page_numbers=document['page_numbers'])
    sources = all_sources
    if selected:
        detected_currency = selected.get('currency', '')
        chosen_currency = currency or detected_currency
        addresses = {(item['page_number'], item['table_index']) for item in selected['sources']}
        sources = [source for source in all_sources if (source['page_number'], source['table_index']) in addresses]
        metadata.update(account_type=selected.get('account_type', 'credit_card'), institution=selected['institution'], account_number=selected['account_reference'],
                        period_start=selected['period_start'], period_end=selected['period_end'],
                        period=(selected['period_start'] + ' - ' + selected['period_end']) if selected['period_start'] else selected.get('printed_statement_date') or selected.get('printed_closing_date', ''))
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
            if selected.get('assignment_only'):
                issues.append('These payments have a printed main account and period, but their savings or checking share could not be established. Compare the PDF, then move the selected payments to the correct account and period. A missing preceding page may contain the share heading.')
            elif selected['account_type'] == 'other':
                issues.append('The printed account label is VISA PAYMENT. Its account type is recorded as Other; this label does not establish a credit-card balance.')
            if not selected.get('assignment_only'):
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
        recovery, _ = recovery_state(session, file, sources=all_sources, choices=choices,
            statement_id=statement_id, revision=None, cache=cache)
        return dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id), filename=file.original_filename,
                    metadata=metadata, currency='', detected_currency=detected_currency, rows=[], sources=[], issues=issues + ['The statement currency could not be identified confidently. Choose it once to read the amounts.'],
                    statement_choices=choices, statement_id=statement_id,
                    transaction_count=0, needs_attention=1, revision=_digest(dict(file=str(file.id), text=text.content_sha256, version=VERSION)), applied=False,
                    review_recovery=recovery)
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
        _check_review_size(rows)
    from services.financial.statement_import_proposal import has_transaction_header
    transaction_header_pages = {s['page_number'] for s in sources if has_transaction_header(s)} if not selected else set()
    for source in ([] if selected and selected.get('layout_id') == 'andrews-share-statement' else sources):
        try:
            if selected and selected.get('layout_id') == 'merrick-card':
                from services.financial.statement_import_merrick import propose_merrick_table
                proposal = propose_merrick_table(source, chosen_currency, selected)
            elif selected:
                from services.financial.statement_import_card import propose_card_table
                proposal = propose_card_table(source, chosen_currency, selected)
            else:
                proposal = propose_table(source, chosen_currency,
                    page_has_transaction_table=source['page_number'] in transaction_header_pages)
        except ValueError as exc:
            raise PdfMappingError(str(exc), 422) from exc
        rows.extend(proposal['rows'])
        issues.extend(proposal.get('issues', []))
        _check_review_size(rows)
    if metadata.get('balance_convention') == 'liability_owed':
        for role in ('opening', 'closing'):
            controls = [row for row in rows if row['kind'] == 'balance'
                        and row['fields'].get('description', '').lower() == f'{role} balance']
            if len(controls) > 1:
                issues.append(f'More than one {role} amount owed was read. Check the account-summary rows and clear any repeated balance before importing.')
    reading_failure = None
    if not selected and not choices:
        from services.financial.statement_layout_context import _cycle
        printed_cycles = {cycle for line in text.content.splitlines()
                          if (cycle := _cycle(' '.join(line.split()))) is not None}
        if len(printed_cycles) > 1 and re.search(r'capital\s*one|capitalone\.com', text.content, re.I):
            reading_failure = (
                'This PDF contains several Capital One statements, but its saved reading has not separated '
                'their account and period details. Transaction amounts on later pages may already be readable. '
                'Use Reprocess statement below with Use the PDF text where available to prepare the statements '
                'as separate reviews. Summary and information pages should not be corrected as payments. '
                'The original file, saved reviews and existing imports are kept.'
            )
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
    excluded_copy = _existing_statement(session, case_id, file, statement_id,
        ((source['page_number'], source['table_index']) for source in sources), row_addresses, source_regions,
        excluded_duplicates=True)
    if excluded_copy is not None:
        current = excluded_copy
    current_import = None
    if current is not None:
        current_file = session.get(EvidenceFile, current.evidence_file_id)
        current_import = dict(source_document_id=str(current.id), evidence_file_id=str(current.evidence_file_id),
            account_id=_imported_account_id(session, current.id),
            filename=current_file.original_filename if current_file else None,
            revision=duplicate_revision(session, current), transaction_count=session.scalar(select(func.count()).select_from(FinancialTransaction).where(FinancialTransaction.source_document_id == current.id, FinancialTransaction.ledger_status == 'admitted')))
        recorded_review = (current.metadata_ or {}).get('statement_import_request', {})
        current_import['review_decisions'] = [
            dict(description=row.get('description', ''), date=row.get('date', ''),
                 excluded=bool(row.get('excluded')), reason=row['reason'])
            for row in recorded_review.get('rows', []) if row.get('reason')]
        current_import['details_reason'] = recorded_review.get('details_reason', '')
        current_import['issues'] = (current.metadata_ or {}).get('statement_import_issues', [])
        current_import['incomplete_count'] = sum(not r.get('resolved_transaction_id') for r in (current.metadata_ or {}).get('statement_incomplete_records', []))
        current_import['record_count'] = current_import['transaction_count'] + current_import['incomplete_count']
        current_import['excluded_as_duplicate'] = excluded_copy is not None
        if excluded_copy is not None:
            retained = session.scalar(select(FinancialSourceDocument).where(
                FinancialSourceDocument.id == excluded_copy.superseded_by_id,
                FinancialSourceDocument.case_id == case_id))
            retained_file = session.get(EvidenceFile, retained.evidence_file_id) if retained else None
            current_import['retained_filename'] = retained_file.original_filename if retained_file else None
            current_import['transaction_count'] = 0
    snapshot = dict(version=VERSION, source_sha256=file.sha256, sources=sources,
                    metadata=metadata, currency=chosen_currency, statement_id=statement_id)
    undated_charges = [row['id'] for row in rows if row['fields'].get('date_basis') == 'statement_end_ordering_only']
    if undated_charges:
        snapshot['undated_statement_charges_v1'] = undated_charges
    if reading_failure:
        snapshot['reading_failure'] = 'unseparated-statement-periods-v1'
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
    from services.financial.statement_progress import review_progress
    revision = _digest(snapshot)
    recovery, previous_review = recovery_state(session, file, sources=all_sources, choices=choices,
        statement_id=statement_id, revision=revision, cache=cache)
    result = dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id), filename=file.original_filename,
                metadata=metadata, currency=chosen_currency, detected_currency=detected_currency, rows=[] if reading_failure else rows, sources=sources, issues=issues,
                saved_review=review_progress(file, statement_id),
                previous_saved_review=previous_review, review_recovery=recovery,
                reading_failure=reading_failure,
                assignment_only=bool(selected and selected.get('assignment_only')),
                printed_main_account=selected.get('main_account_reference', '') if selected else '',
                can_record_account_closure=closure_only,
                can_import_balances=balance_only,
                page_numbers=all_page_numbers,
                unassigned_page_numbers=unassigned_pages if selected else [],
                information_pages=[dict(page_number=number, kind=kind) for number, kind in sorted(
                    {(item['page_number'], item['kind']) for item in catalog['information_sources']})],
                statement_page_numbers=(selected['page_numbers'] if selected and selected.get('uses_printed_page_order')
                                        else sorted({source['page_number'] for source in sources})),
                statement_choices=choices, statement_id=statement_id,
                statement_row_addresses=row_addresses,
                statement_source_regions=source_regions,
                transaction_count=0 if reading_failure else sum(not row['excluded'] for row in rows),
                needs_attention=sum(bool(row['issues']) for row in rows) + len(issues),
                revision=revision, current_import=current_import, applied=False)
    if _apply_assignments:
        from services.financial.statement_row_assignment import assigned_proposal
        return assigned_proposal(session, file, result, cache)
    return result

# A single confirmation carries all reviewed rows. The original proposal stays
# separate from edits in the stored source record.
from datetime import date
from typing import Annotated, Literal
from types import SimpleNamespace
from uuid import UUID
from pydantic import Field, model_validator
from services.financial.pdf_candidates import _Contract, _Digest


class DraftImportRow(_Contract):
    id: Annotated[str, Field(min_length=1, max_length=80)]
    excluded: bool = False
    manual_page: Annotated[int | None, Field(ge=1, le=500)] = None
    date: Annotated[str, Field(max_length=32)] = ''
    date_unprinted: bool = False
    date_values: dict[Literal['date', 'booking_date', 'value_date'], Annotated[str, Field(max_length=32)]] = Field(default_factory=dict)
    description: Annotated[str, Field(max_length=4096)] = ''
    counterparty: Annotated[str, Field(max_length=4096)] = ''
    amount_minor: Annotated[str, Field(max_length=32)] = '0'
    direction: Literal['credit', 'debit'] | None = None
    balance_minor: Annotated[str | None, Field(max_length=32)] = None
    reason: Annotated[str, Field(max_length=4096)] = ''


class ImportRow(DraftImportRow):
    amount_minor: Annotated[str, Field(pattern=r'^(0|[1-9][0-9]{0,18})$')] = '0'
    balance_minor: Annotated[str | None, Field(pattern=r'^-?(0|[1-9][0-9]{0,18})$')] = None

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
            if self.date_unprinted:
                if self.date or any(self.date_values.values()):
                    raise ValueError('A transaction with a printed date cannot also be marked date not printed.')
            elif date.fromisoformat(self.date).isoformat() != self.date:
                raise ValueError('A complete transaction date is required.')
            if not self.description.strip():
                raise ValueError('A transaction description is required.')
            if not 0 < int(self.amount_minor) <= 9223372036854775807:
                raise ValueError('A positive transaction amount within the supported range is required.')
        return self


class StatementReviewDraft(_Contract):
    expected_revision: _Digest
    statement_id: _Digest | None = None
    replaces_source_document_id: UUID | None = None
    replacement_revision: _Digest | None = None
    currency: Annotated[str, Field(pattern=r'^[A-Z]{3}$')]
    account_number: Annotated[str, Field(max_length=128)]
    institution: Annotated[str, Field(max_length=128)] = ''
    holder: Annotated[str, Field(max_length=128)]
    period_start: Annotated[str, Field(max_length=32)] = ''
    period_end: Annotated[str, Field(max_length=32)] = ''
    details_reason: Annotated[str, Field(max_length=4096)] = ''
    balance_exception_reason: Annotated[str, Field(max_length=4096)] = ''
    balance_exception_revision: _Digest | None = None
    coverage_review_reason: Annotated[str, Field(max_length=4096)] = ''
    coverage_review_revision: _Digest | None = None
    rows: Annotated[list[DraftImportRow], Field(min_length=1, max_length=MAX_STATEMENT_REVIEW_ROWS)]


class StatementImportRequest(StatementReviewDraft):
    currency: Annotated[str, Field(pattern=r'^(?:[A-Z]{3})?$')]
    rows: Annotated[list[DraftImportRow], Field(min_length=1, max_length=MAX_STATEMENT_REVIEW_ROWS)]

    @model_validator(mode='after')
    def distinct_rows(self):
        if sum(not row.excluded for row in self.rows) > MAX_STATEMENT_TRANSACTIONS:
            raise ValueError('A statement import can contain up to 25,000 transactions.')
        if len({r.id for r in self.rows}) != len(self.rows):
            raise ValueError('A statement row cannot be included twice.')
        if bool(self.replaces_source_document_id) != bool(self.replacement_revision):
            raise ValueError('A replacement must identify the current imported version.')
        if self.replaces_source_document_id and not self.details_reason.strip():
            raise ValueError('Explain why the reprocessed version should replace the current import.')
        return self


def check_import_request(proposal, request):
    saved = proposal.get('saved_review')
    if saved and saved['request'].get('expected_revision') != proposal['revision']:
        raise PdfMappingError('The saved corrections belong to an older reading. Compare them and use Save progress before importing.', 422)
    recovery = proposal.get('review_recovery')
    if recovery and recovery['required'] and not recovery['acknowledged']:
        raise PdfMappingError('Compare the earlier saved reviews for this file before importing. Saved corrections may belong to different statement periods in the new reading.', 422)
    if proposal.get('reading_failure'):
        raise PdfMappingError(proposal['reading_failure'], 422)
    if proposal.get('assignment_only'):
        raise PdfMappingError('Assign these payments to a recognised account and statement period before importing. Use Move to another account or period; this unassigned page cannot be imported directly.', 422)
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
        originally_undated = fields.get('date_basis') == 'statement_end_ordering_only'
        if row.date_unprinted and (not originally_undated or bool(row.date)):
            raise PdfMappingError('Only a recognised undated statement charge can be marked as having no printed date.', 422)
        additional_roles = set(_date_roles(fields)) - {_primary_date_role(fields)}
        if not set(row.date_values) <= additional_roles:
            raise PdfMappingError('Only separately identified source dates can be corrected here. Reload the statement.', 422)
        if original['kind'] in ('balance', 'statement_total') and not row.excluded:
            raise PdfMappingError('A printed balance or statement total is not a transaction. Keep it outside the transaction list.', 422)
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
            or row.amount_minor != (fields.get('amount_minor') or '')
            or row.direction != fields.get('direction'))) or row.balance_minor != fields.get('balance')
        changed = changed or any(value != fields.get(key, '') for key, value in row.date_values.items())
        changed = changed or (not row.excluded and row.date_unprinted != originally_undated)
        if changed and not row.reason.strip():
            raise PdfMappingError(f"Explain the correction or decision for row {row.id}.", 422)
    return originals


def _same_import_request(document, request, request_hash):
    metadata = document.metadata_ or {}
    if metadata.get('statement_import_request_sha256') == request_hash:
        return True
    # Additive fields default to no decision/no unprinted date. A retry of an
    # older successful request must still return its receipt, not import again.
    previous = metadata.get('statement_import_request')
    if not previous or _digest(previous) != metadata.get('statement_import_request_sha256'):
        return False
    try:
        return StatementImportRequest.model_validate(previous).model_dump(mode='json') == request.model_dump(mode='json')
    except ValueError:
        return False


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
                if (proposal.get('current_import') or {}).get('excluded_as_duplicate'):
                    raise PdfMappingError(
                        'This statement was excluded as a duplicate. Review or restore its recorded decision in Import review before importing again.', 409)
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
                    if _same_import_request(existing, request, request_hash):
                        from sqlalchemy import func
                        imported_count = session.scalar(select(func.count()).select_from(FinancialTransaction).where(
                            FinancialTransaction.source_document_id == existing.id, FinancialTransaction.ledger_status == 'admitted'))
                        incomplete_count = sum(not r.get('resolved_transaction_id') for r in existing.metadata_.get('statement_incomplete_records', []))
                        return dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id), source_document_id=str(existing.id),
                            account_id=_imported_account_id(session, existing.id), transaction_count=imported_count,
                            record_count=imported_count + incomplete_count, incomplete_count=incomplete_count,
                            issues=existing.metadata_.get('statement_import_issues', []),
                            account_closed_on=((existing.metadata_.get('statement_import_original', {}).get('metadata', {}).get('account_closure')) or {}).get('date'), created=False, applied=True)
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
                from services.financial.statement_import_overlap import coverage_review, requires_decision
                coverage = coverage_review(session, case_id=case_id, file_id=evidence_file_id,
                                           request=request.model_dump(mode='json'))
                coverage['requires_review'] = requires_decision(coverage, request.model_dump(mode='json'))
                from services.financial.review_arithmetic import check_proposed_rows
                arithmetic = check_proposed_rows(proposal, [r.model_dump() for r in request.rows])
                from services.financial.import_issues import incomplete_records, retained_issues, calendar_date, usable_currency
                incomplete = incomplete_records(proposal, request)
                issues = retained_issues(proposal, request, arithmetic=arithmetic, coverage=coverage)
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
                    currency=request.currency or None, metadata=dict(display_label=' · '.join(filter(None, [request.holder, request.account_number])) or file.original_filename,
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
                        statement_import_original=proposal, statement_import_original_sha256=_digest(proposal), coverage='all_prepared_rows_imported',
                        statement_account_id=str(account.id), statement_import_issues=issues,
                        statement_incomplete_records=incomplete, statement_import_checks=arithmetic,
                        whole_document_extraction_verified=False)))
                from services.financial.periods import StatementPeriodDraft, PeriodBounds, BalanceObservation, record_statement_period
                from services.financial.money import Money
                balance_sign = -1 if proposal['metadata'].get('balance_convention') == 'liability_owed' else 1
                start, end = calendar_date(request.period_start), calendar_date(request.period_end)
                bounds = PeriodBounds.printed(start, end) if start and end and start <= end else PeriodBounds()
                from services.financial.import_issues import usable_balance
                convention = proposal['metadata'].get('balance_convention')
                openings = [row for row in request.rows if row.excluded and originals[row.id]['kind'] == 'balance'
                    and 'opening' in originals[row.id]['fields'].get('description', '').lower() and usable_balance(row.balance_minor, convention)]
                currency = usable_currency(request.currency)
                opening = BalanceObservation.printed(Money(balance_sign * int(openings[0].balance_minor), currency)) if len(openings) == 1 and currency else BalanceObservation.absent()
                closings = [row for row in request.rows if row.excluded and originals[row.id]['kind'] == 'balance'
                    and originals[row.id]['fields'].get('description', '').strip().lower() == 'closing balance'
                    and usable_balance(row.balance_minor, convention)]
                closing = BalanceObservation.printed(Money(balance_sign * int(closings[0].balance_minor), currency)) if len(closings) == 1 and currency else BalanceObservation.absent()
                period = record_statement_period(session, run, StatementPeriodDraft(account_id=account.id,
                    source_document_id=document.id, currency=currency, bounds=bounds, opening=opening, closing=closing)) if currency else None
                if period and proposal['metadata'].get('balance_convention') in ('liability_owed', 'asset_balance'):
                    from services.financial.statement_import_controls import retain_import_controls
                    retain_import_controls(document, period, request, originals, openings, closings,
                                           balance_convention=proposal['metadata']['balance_convention'])
                drafts = []
                incomplete_ids = {r['id'] for r in incomplete}
                for position, row in enumerate(r for r in request.rows if not r.excluded):
                    if row.excluded or row.id in incomplete_ids:
                        continue
                    original = originals[row.id]
                    from services.financial.imported_records import transaction_draft
                    drafts.append(transaction_draft(row, original, account_id=account.id,
                        period_id=period.id if period else None, currency=request.currency, position=position,
                        actor=actor, balance_sign=balance_sign, period_end=request.period_end))
                transactions = record_transactions(session, run, document, drafts, retain_prior_versions=shares_source_references)
                from services.financial.reconcile import reconcile_period
                if period:
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
                    transaction_count=len(transactions), record_count=len(transactions) + len(incomplete),
                    incomplete_count=len(incomplete), issues=issues,
                    account_closed_on=(proposal['metadata'].get('account_closure') or {}).get('date'), created=True, applied=True)
            except Exception:
                session.rollback()
                raise
