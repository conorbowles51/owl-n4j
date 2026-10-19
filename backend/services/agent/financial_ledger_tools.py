"""Read-only, bounded investigator access to the relational Financial ledger.

The caller supplies an authorized case and a dedicated read session. This module
does not use the graph, import records, infer missing months, or convert money.
Pagination re-captures the complete bounded population and rejects changed
revisions, rather than presenting a page as a complete analysis.
"""
from collections import Counter
from datetime import date
from hashlib import sha256
import json
from uuid import UUID

from sqlalchemy import select

from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialAccount, FinancialSourceDocument, FinancialStatementPeriod
from services.financial.account_consolidation import expand_account_ids, bank_key
from services.financial.account_selection import holder_account_ids
from services.financial.candidate_store import _account_statement_periods, CandidateStoreError
from services.financial.ledger_summary import LedgerSummaryError, ledger_summary
from services.financial.ledger_table_view import LedgerTableView, capture_table_view, _period
from services.financial.working_totals import working_totals_from_readings
from services.financial.money import get_currency, MoneyError

MAX_CONTEXT_ROWS = 10000
MAX_INCOMPLETE_RECORDS = 100000
MAX_PAGE_SIZE = 100
LIMITATION = (
    'Current imported ledger only. Working totals include admitted P3 readings; '
    'verified totals use the existing included proof classes. Currency and account '
    'type totals are separate exact minor units, with no FX conversion. Credits '
    'and debits are account postings: card postings are not bank cash flow. Net '
    'postings are not balances; transfers are not matched or netted. Registered '
    'periods and zero-payment accounts do not establish complete extraction or '
    'confirmed inactivity. Source links identify registered same-case Evidence; '
    'original accessibility and file digests are not checked by this metadata read. '
    'Unprocessed Evidence is outside this ledger read.'
)


class FinancialLedgerToolError(LedgerSummaryError):
    """Invalid input or inconsistent saved scope, without a partial result."""


def _uuid(value):
    try:
        return value if isinstance(value, UUID) else UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise FinancialLedgerToolError('Use a valid case or account identifier.') from exc


def _day(value):
    if value is None or value == '':
        return None
    if type(value) is date:
        return value
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError()
        return parsed
    except (ValueError, TypeError) as exc:
        raise FinancialLedgerToolError('Use calendar dates in YYYY-MM-DD format.') from exc


def _unavailable(case_id, reason, *, code='unavailable'):
    return dict(schema='loupe.agent.financial_ledger/1', case_id=str(case_id), available=False,
        reason=reason, reason_code=code, revision=None, ledger_revision=None, total_matching=None, returned=0,
        has_more=False, next_offset=None, items=[], totals=[], coverage=None,
        applied=False, limitation=LIMITATION)


def _account_type(value):
    return value or 'unknown'


def _currency_exponent(value):
    try:
        return get_currency(value).exponent
    except (MoneyError, AttributeError, TypeError):
        # Unreadable incomplete/excluded context remains explicitly unknown.
        return None


def _totals(readings, group_by=None):
    groups = {}
    for reading in readings:
        row = reading['row']
        group = None
        if group_by == 'account':
            group = row.get('canonical_account_id') or row['account_id']
        elif group_by == 'month':
            group = _period(row)
        elif group_by == 'category':
            group = row.get('category') or 'Uncategorized'
        elif group_by == 'counterparty':
            link = row.get('counterparty_link')
            label = row.get('to_name' if row['direction'] == 'debit' else 'from_name')
            if label is None:
                label = row.get('counterparty_raw')
            group = (f"identity:{link['kind']}:{link['id']}" if link else
                'label:' + json.dumps(label, ensure_ascii=False))
        key = (row['currency'], _account_type(row.get('account_type')), group)
        entry = groups.setdefault(key, dict(currency=key[0], account_type=key[1], group=group,
            currency_exponent=_currency_exponent(key[0]),
            transaction_count=0, credits_minor=0, debits_minor=0, account_ids=set(),
            source_document_ids=set(), statement_period_ids=set(), banks=set()))
        if group_by == 'account':
            entry['group_label'] = row.get('canonical_account_label') or row.get('account_label') or group
        if group_by == 'counterparty':
            entry['group_label'] = label
            entry['group_basis'] = 'reviewed_identity' if link else 'exact_displayed_label'
        entry['transaction_count'] += 1
        entry[row['direction'] + 's_minor'] += int(row['amount_minor'])
        entry['account_ids'].add(row.get('canonical_account_id') or row['account_id'])
        if row.get('account_institution'):
            entry['banks'].add(bank_key(row['account_institution']))
        entry['source_document_ids'].add(row['source_document_id'])
        if row.get('statement_period_id'):
            entry['statement_period_ids'].add(row['statement_period_id'])
    result = []
    for key in sorted(groups, key=lambda item: (item[0], item[1], item[2] is not None, item[2] or '')):
        entry = groups[key]
        entry['net_minor'] = str(entry['credits_minor'] - entry['debits_minor'])
        entry['credits_minor'], entry['debits_minor'] = str(entry['credits_minor']), str(entry['debits_minor'])
        for field in ('account_ids', 'source_document_ids', 'statement_period_ids'):
            # Counts cover the entire group. Its members can be retrieved with
            # the ordinary account/date/category filters; no giant ID list.
            entry[field.replace('_ids', '_count')] = len(entry.pop(field))
        entry['bank_count'] = len(entry.pop('banks'))
        result.append(entry)
    return result


def _context(session, case_id, account_ids, account_holders, start, end, filters):
    accounts = list(session.scalars(select(FinancialAccount).where(
        FinancialAccount.case_id == case_id).order_by(FinancialAccount.id).limit(MAX_CONTEXT_ROWS + 1)))
    if len(accounts) > MAX_CONTEXT_ROWS:
        raise FinancialLedgerToolError('Account coverage exceeds the bounded capture; no partial result was calculated.')
    by_id = {str(account.id): account for account in accounts}
    selected = set(by_id)
    for identifiers in (account_ids, [_uuid(filters.account_id)] if filters.account_id else None):
        if identifiers:
            selected &= {str(value) for value in expand_account_ids(session, case_id, identifiers)}
    for holders in (account_holders, [filters.account_holder] if filters.account_holder else None):
        if holders:
            selected &= {str(value) for value in holder_account_ids(session, case_id, holders)}
    for account in accounts:
        canonical = (account.metadata_ or {}).get('canonical_account_id')
        if canonical and canonical not in by_id:
            raise FinancialLedgerToolError('A saved canonical account is outside this case; coverage is unavailable.')
    periods = _account_statement_periods(session, case_id=case_id,
        account_ids=[_uuid(value) for value in sorted(selected)])
    # A filtered, removed or superseded period is not an account with no
    # period metadata. Check existence separately from the admitted directory
    # projection, including aliases in each selected canonical family.
    period_accounts = set(session.scalars(select(FinancialStatementPeriod.account_id)
        .where(FinancialStatementPeriod.case_id == case_id,
            FinancialStatementPeriod.account_id.in_([_uuid(value) for value in selected]))
        .distinct())) if selected else set()
    families_with_periods = {(by_id[str(identifier)].metadata_ or {}).get('canonical_account_id')
        or str(identifier) for identifier in period_accounts}
    sources = list(session.execute(select(FinancialSourceDocument.id,
        FinancialSourceDocument.evidence_file_id, FinancialSourceDocument.status,
        FinancialSourceDocument.proof_class,
        FinancialSourceDocument.superseded_by_id,
        FinancialSourceDocument.metadata_['financial_import_removal'].label('removal'),
        FinancialSourceDocument.metadata_['statement_account_id'].as_string().label('account_id'),
        FinancialSourceDocument.metadata_['statement_incomplete_records'].label('incomplete'),
        FinancialSourceDocument.metadata_['statement_import_request']['currency'].as_string().label('currency'),
        FinancialSourceDocument.metadata_['statement_details_review']['currency'].as_string().label('review_currency'),
        EvidenceFile.case_id.label('file_case_id'), EvidenceFile.original_filename.label('filename'))
        .outerjoin(EvidenceFile, EvidenceFile.id == FinancialSourceDocument.evidence_file_id)
        .where(FinancialSourceDocument.case_id == case_id)
        .order_by(FinancialSourceDocument.id).limit(MAX_CONTEXT_ROWS + 1)))
    if len(sources) > MAX_CONTEXT_ROWS:
        raise FinancialLedgerToolError('Source coverage exceeds the bounded capture; no partial result was calculated.')
    source_index = {}
    for source in sources:
        # Never expose names/links through a dangling or foreign Evidence ID.
        valid_file = source.evidence_file_id is not None and source.file_case_id == case_id
        source_index[str(source.id)] = dict(source_document_id=str(source.id),
            evidence_file_id=str(source.evidence_file_id) if valid_file else None,
            filename=source.filename if valid_file else None,
            status=source.status, proof_class=source.proof_class,
            source_available=valid_file, source_registered=valid_file, source_access_checked=False,
            financial_review_href=f'/cases/{case_id}/financial?view=statements&files=1&reviewFile={source.evidence_file_id}' if valid_file else None,
            evidence_href=f'/cases/{case_id}/evidence?file={source.evidence_file_id}' if valid_file else None)
    context = []
    for identifier in sorted(selected):
        account = by_id[identifier]
        canonical = (account.metadata_ or {}).get('canonical_account_id') or identifier
        saved = [period for period in periods[account.id]
            if (not filters.source_document_id or period['source_document_id'] == filters.source_document_id)
            and (not filters.currency or period['currency'] == filters.currency)
            and (not start or not period['end'] or period['end'] >= start.isoformat())
            and (not end or not period['start'] or period['start'] <= end.isoformat())]
        without_period = canonical not in families_with_periods
        if not saved and (not without_period or start or end or filters.source_document_id
                or (filters.currency and account.currency != filters.currency)):
            continue
        context.append(dict(account_id=identifier,
            canonical_account_id=canonical,
            account_number=account.identifier_as_printed, holder=account.holder_name,
            bank=account.institution_name, account_type=_account_type(account.account_type),
            recorded_account_currency=account.currency,
            periods=[{**period, 'currency_exponent': _currency_exponent(period['currency']),
                'source': source_index[period['source_document_id']]} for period in saved]))
    incomplete = []
    examined = 0
    from services.financial.import_issues import calendar_date
    for source in sources:
        if (source.status != 'admitted' or source.superseded_by_id or source.removal
                or source.account_id not in selected or source.file_case_id != case_id
                or (filters.source_document_id and str(source.id) != filters.source_document_id)):
            continue
        for record in source.incomplete or []:
            examined += 1
            if examined > MAX_INCOMPLETE_RECORDS:
                raise FinancialLedgerToolError('Incomplete-record coverage exceeds the bounded capture; no partial result was calculated.')
            if record.get('resolved_transaction_id'):
                continue
            fields = record.get('correction') or record['fields']
            day = calendar_date(fields.get('date'))
            currency = record.get('correction_currency') or source.review_currency or source.currency or ''
            if filters.currency and currency != filters.currency:
                continue
            if day and ((start and day < start) or (end and day > end)):
                continue
            original = record.get('original') or {}
            record_status = ('excluded_from_statement' if fields.get('excluded') else
                'saved_fields_pending_admission' if not record['missing_fields'] else 'incomplete')
            incomplete.append(dict(id=record['id'], account_id=source.account_id,
                currency=currency, fields=fields, missing_fields=record['missing_fields'],
                currency_exponent=_currency_exponent(currency),
                version=record.get('version', 0), page_number=original.get('page_number'),
                source=source_index[str(source.id)], included_in_totals=False,
                record_status=record_status, exclusion_reason=record_status))
    return context, incomplete, source_index, selected


def _validate_period_ownership(session, case_id, readings):
    """A malformed historical FK must not expose another case's period ID."""
    wanted = {r['row']['statement_period_id'] for r in readings if r['row'].get('statement_period_id')}
    if not wanted:
        return
    period = FinancialStatementPeriod
    saved = list(session.execute(select(period.id, period.account_id, period.source_document_id)
        .where(period.case_id == case_id).limit(MAX_CONTEXT_ROWS + 1)))
    if len(saved) > MAX_CONTEXT_ROWS:
        raise FinancialLedgerToolError('Statement-period coverage exceeds the bounded capture; no partial result was calculated.')
    index = {str(row.id): row for row in saved}
    for reading in readings:
        row = reading['row']
        identifier = row.get('statement_period_id')
        if not identifier:
            continue
        linked = index.get(identifier)
        if (linked is None or str(linked.account_id) != row['account_id']
                or str(linked.source_document_id) != row['source_document_id']):
            raise FinancialLedgerToolError('A ledger statement-period reference is inconsistent in this case.')


def read_financial_ledger(session, *, case_id, account_ids=None, account_holders=None,
        start_date=None, end_date=None, filters=None, population='working', view='transactions',
        group_by='account', offset=0, limit=50, expected_revision=None, expected_ledger_revision=None):
    """Complete filtered totals and a revision-bound page, using Financial rules.

    Coverage/incomplete/excluded views accept only account, date, source and
    currency scope. Payment-specific filters are rejected, never silently lost.
    Exclusion counts describe the captured account/date scope, separately from
    the matching included payments. Missing dates remain explicit.
    """
    case_id = _uuid(case_id)
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= MAX_PAGE_SIZE:
        raise FinancialLedgerToolError(f'Use a nonnegative offset and a page limit from 1 to {MAX_PAGE_SIZE}.')
    if offset and not expected_revision:
        raise FinancialLedgerToolError('Continuation pages require the revision from the first page.')
    if population not in ('working', 'verified') or view not in ('transactions', 'groups', 'coverage', 'excluded', 'incomplete'):
        raise FinancialLedgerToolError('Choose a supported ledger population and view.')
    if group_by not in ('account', 'month', 'counterparty', 'category'):
        raise FinancialLedgerToolError('Choose account, month, counterparty or category grouping.')
    try:
        table = LedgerTableView.model_validate(filters or {})
    except ValueError as exc:
        raise FinancialLedgerToolError('Invalid transaction filters.') from exc
    if view in ('coverage', 'incomplete', 'excluded'):
        changed = table.model_dump(exclude_defaults=True)
        if set(changed) - {'currency', 'account_id', 'account_holder', 'source_document_id'}:
            raise FinancialLedgerToolError('This view supports account/date/currency/source scope, not payment-specific filters.')
    start, end = _day(start_date), _day(end_date)
    account_ids = [_uuid(value) for value in account_ids] if account_ids else None
    if account_holders and (not isinstance(account_holders, list) or
            any(not isinstance(value, str) or len(value) > 512 for value in account_holders)):
        raise FinancialLedgerToolError('Use a list of account-holder selections.')
    with session.no_autoflush:
        ledger = ledger_summary(session, case_id=case_id, account_ids=account_ids,
            account_holders=account_holders, start_date=start, end_date=end, capture_readings=True)
        if not ledger['available']:
            return _unavailable(case_id, ledger['reason'])
        working = working_totals_from_readings(ledger)
        try:
            base_context, base_incomplete, source_index, selected_account_ids = _context(session, case_id, account_ids,
                account_holders, start, end, LedgerTableView())
            _validate_period_ownership(session, case_id, ledger['readings'])
        except CandidateStoreError as exc:
            return _unavailable(case_id, str(exc))
        except FinancialLedgerToolError as exc:
            if 'bounded capture' in str(exc):
                return _unavailable(case_id, str(exc))
            raise
        batch_scope = None
        if table.import_batch_id:
            from services.financial.batch_transaction_scope import imported_batch_scope
            batch_scope = imported_batch_scope(session, case_id=case_id, batch_id=_uuid(table.import_batch_id))
        captured_view = capture_table_view(ledger, table.model_dump(), batch_scope=batch_scope)
        # Cross-analysis pin: account/date capture before payment filters,
        # population choice, grouping or page/view. No timestamps or originals.
        capture = dict(case_id=str(case_id),
            account_ids=sorted(str(value) for value in account_ids or []), account_holders=account_holders or [],
            start_date=start.isoformat() if start else None, end_date=end.isoformat() if end else None,
            readings=[dict(row=r['row'], source=r['source'], included=r['included'],
                exclusion_reason=r['exclusion_reason']) for r in ledger['readings']],
            context=base_context, incomplete=base_incomplete, sources=source_index)
        ledger_revision = sha256(json.dumps(capture, sort_keys=True,
            separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
        if expected_ledger_revision is not None and expected_ledger_revision != ledger_revision:
            return _unavailable(case_id, 'The underlying ledger or base account/date scope changed. Restart the related analyses before comparing them.',
                code='stale_ledger_revision')
        if table.account_id:
            selected_account_ids &= {str(value) for value in expand_account_ids(session, case_id, [_uuid(table.account_id)])}
        if table.account_holder:
            selected_account_ids &= {str(value) for value in holder_account_ids(session, case_id, [table.account_holder])}
    context = []
    for account in base_context:
        if account['account_id'] not in selected_account_ids:
            continue
        periods = [p for p in account['periods']
            if (not table.currency or p['currency'] == table.currency)
            and (not table.source_document_id or p['source_document_id'] == table.source_document_id)]
        if periods or (not account['periods'] and not table.source_document_id
                and (not table.currency or account['recorded_account_currency'] == table.currency)):
            context.append({**account, 'periods': periods})
    incomplete = [record for record in base_incomplete if record['account_id'] in selected_account_ids
        and (not table.currency or record['currency'] == table.currency)
        and (not table.source_document_id or record['source']['source_document_id'] == table.source_document_id)]
    by_id = {reading['row']['key']: reading for reading in ledger['readings']}
    eligible = lambda reading: (reading['exclusion_reason'] in (None, 'proof_class_not_included')
        if population == 'working' else reading['included'])
    matching = [by_id[key] for key in captured_view['row_ids'] if eligible(by_id[key])]
    totals = _totals(matching)
    scoped = working if population == 'working' else ledger
    matched_accounts = {r['row'].get('canonical_account_id') or r['row']['account_id'] for r in matching}
    matched_banks = {bank_key(r['row']['account_institution']) for r in matching if r['row'].get('account_institution')}
    scope_coverage = dict(considered_ledger_rows=ledger['considered_rows'],
        included_scope_rows=scoped['included_rows'], excluded_scope_rows=scoped['excluded_rows'],
        exclusions=scoped['exclusions'], matching_transactions=len(matching),
        matching_accounts=len(matched_accounts), matching_banks=len(matched_banks),
        matching_sources=len({r['row']['source_document_id'] for r in matching}),
        matching_statement_periods=len({r['row']['statement_period_id'] for r in matching if r['row'].get('statement_period_id')}),
        registered_accounts=len({a['canonical_account_id'] for a in context}),
        registered_banks=len({bank_key(a['bank']) for a in context if a['bank']}),
        registered_account_entries=len(context), registered_statement_periods=sum(len(a['periods']) for a in context),
        registered_accounts_with_statement_periods=len({a['canonical_account_id'] for a in context if a['periods']}),
        registered_accounts_without_statement_periods=len({a['canonical_account_id'] for a in context if not a['periods']}),
        registered_sources=len({p['source_document_id'] for a in context for p in a['periods']}),
        incomplete_records=len(incomplete),
        pending_records_without_missing_fields=sum(not r['missing_fields'] for r in incomplete),
        limitation='Exclusions cover the captured account/date scope before payment filters. Registered periods and incomplete records use account/date/currency/source scope only; their unknown dates remain explicit. Directory accounts without any saved period appear only without date/source filters and are not evidence of imported statements, payments or inactivity. These are not missing-transaction counts.')
    counts = Counter(r['row'].get('canonical_account_id') or r['row']['account_id'] for r in matching)
    for account in context:
        account['matching_payments_for_canonical_account'] = counts[account['canonical_account_id']]
    scope_coverage['registered_accounts_without_matching_payments'] = len({
        a['canonical_account_id'] for a in context if not counts[a['canonical_account_id']]})
    def row_item(reading):
        row = reading['row']
        source = source_index.get(row['source_document_id'])
        if source is None:
            raise FinancialLedgerToolError('A ledger source is unavailable in this case.')
        return dict(**row, transaction_id=row['key'], source=source,
            currency_exponent=_currency_exponent(row['currency']),
            included_in_totals=eligible(reading), exclusion_reason=None if eligible(reading) else reading['exclusion_reason'],
            financial_href=f'/cases/{case_id}/financial')
    if view == 'groups':
        items = _totals(matching, group_by)
    elif view == 'coverage':
        # One period per page item also bounds a single account with thousands
        # of periods; no hidden nested directory bypasses the page limit.
        items = [{**{key: value for key, value in account.items() if key != 'periods'},
            'period': period, 'coverage_unit': 'registered_statement_period' if period else 'registered_account_without_period',
            **({'periods': []} if period is None else {})}
            for account in context for period in account['periods'] or [None]]
    elif view == 'incomplete':
        items = incomplete
    elif view == 'excluded':
        # This diagnostic page never contributes money. Apply only the
        # supported scope; disposition stays intact in the returned rows.
        excluded = [r for r in ledger['readings'] if not eligible(r)
            and r['row']['account_id'] in selected_account_ids
            and (not table.currency or r['row']['currency'] == table.currency)
            and (not table.source_document_id or r['row']['source_document_id'] == table.source_document_id)]
        items = [row_item(r) for r in excluded]
    else:
        items = [row_item(r) for r in matching]
    revision = sha256(json.dumps(dict(ledger_revision=ledger_revision, population=population, view=view,
        grouping=group_by if view == 'groups' else None, filters=captured_view['filters'],
        imported_source_document_ids=captured_view.get('imported_source_document_ids')), sort_keys=True,
        separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    if expected_revision is not None and expected_revision != revision:
        return _unavailable(case_id, 'The ledger or scope changed. Restart at offset 0 before continuing; no mixed-revision page was returned.', code='stale_revision')
    total = len(items)
    return dict(schema='loupe.agent.financial_ledger/1', case_id=str(case_id), available=True,
        reason=None, revision=revision, ledger_revision=ledger_revision, population=population, view=view,
        group_by=group_by if view == 'groups' else None, filters=captured_view['filters'],
        start_date=start.isoformat() if start else None, end_date=end.isoformat() if end else None,
        total_matching=total, returned=len(items[offset:offset+limit]), offset=offset,
        has_more=offset+limit < total, next_offset=offset+limit if offset+limit < total else None,
        items=items[offset:offset+limit], totals=totals, coverage=scope_coverage,
        applied=False, limitation=LIMITATION)
