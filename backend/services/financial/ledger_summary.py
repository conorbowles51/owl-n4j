from services.financial.account_consolidation import expand_account_ids
"""Exact, bounded summaries of the relational ledger, with explicit exclusions.

The bound is checked before reporting any count or money. One SELECT observes
rows, source disposition/class and account ownership together. Credits/debits
are account postings, not deduplicated transfers or an opening/closing balance.
"""
from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import load_only
from postgres.models.enums import ProofClass, LedgerStatus, DocumentStatus
from postgres.models.financial import FinancialTransaction, FinancialSourceDocument, FinancialAccount
from services.financial.proof_class import DEFAULT_TOTAL_CLASSES, counts_toward_totals
from services.financial.money import get_currency

MAX_SUMMARY_ROWS = 100000


class LedgerSummaryError(ValueError):
    pass


def _json_copy(value):
    """copy.deepcopy for stored JSON (dicts, lists, scalars); deepcopy's generic memo cost was a fifth of a large read."""
    if type(value) is dict:
        return {key: _json_copy(item) for key, item in value.items()}
    if type(value) is list:
        return [_json_copy(item) for item in value]
    if value is None or type(value) in (str, int, float, bool):
        return value
    from copy import deepcopy
    return deepcopy(value)


def _totals_row(row):
    """The fields of to_view(row).to_json() that totals, groups and contributions read, with identical values."""
    return dict(key=str(row.id), ref_id=row.ref_id, currency=row.currency, amount_minor=str(row.amount_minor),
        direction=row.direction, ordering_date=row.ordering_date.isoformat() if row.ordering_date is not None else None,
        proof_class=row.proof_class, counterparty_raw=row.counterparty_raw, ledger_status=row.ledger_status,
        superseded_by_id=str(row.superseded_by_id) if row.superseded_by_id is not None else None)


def ledger_summary(session, *, case_id, account_id=None, start_date=None, end_date=None, grouping=None, capture_readings=False, account_ids=None, account_holders=None, totals_only_readings=False):
    """``totals_only_readings``: each captured reading's row carries only the stored fields that totals, groups and
    contributions read (see _totals_row), with no payment view, provenance or label history. Callers that never
    return the readings use it; the same rows are included and excluded either way."""
    if type(capture_readings) is not bool or type(totals_only_readings) is not bool or (totals_only_readings and not capture_readings):
        raise LedgerSummaryError("Reading capture must be explicit.")
    if grouping not in (None, "daily", "monthly"):
        raise LedgerSummaryError("Choose daily or monthly ledger grouping.")
    for value in (start_date, end_date):
        if value is not None and type(value) is not date:
            raise LedgerSummaryError("Summary date bounds must be calendar dates.")
    if start_date and end_date and start_date > end_date:
        raise LedgerSummaryError("Summary start date must be on or before end date.")
    # A source can retain megabytes of original table readings. Selecting that
    # JSON for every joined payment multiplied the same PDF data hundreds of
    # times. Totals/citations need only the source identity and disposition.
    query = select(FinancialTransaction, FinancialSourceDocument).options(load_only(
        FinancialSourceDocument.id, FinancialSourceDocument.case_id, FinancialSourceDocument.status,
        FinancialSourceDocument.proof_class, FinancialSourceDocument.evidence_file_id,
        FinancialSourceDocument.sha256_at_ingestion, FinancialSourceDocument.parser_name,
        FinancialSourceDocument.parser_version, raiseload=True,
    )).outerjoin(
        FinancialSourceDocument, FinancialSourceDocument.id == FinancialTransaction.source_document_id
    ).where(FinancialTransaction.case_id == case_id)
    if not capture_readings or totals_only_readings:
        # Totals read only these plain columns. The provenance and metadata JSON of every payment were fetched and
        # decoded for nothing; any other column raises rather than lazily loading once per payment.
        T = FinancialTransaction
        query = query.options(load_only(T.id, T.case_id, T.account_id, T.source_document_id, T.ref_id, T.amount_minor,
            T.currency, T.direction, T.ordering_date, T.proof_class, T.counterparty_raw, T.ledger_status,
            T.superseded_by_id, raiseload=True))
    if account_id is not None:
        query = query.where(FinancialTransaction.account_id.in_(expand_account_ids(session, case_id, [account_id])))
    from services.financial.account_selection import apply_account_selection
    query = apply_account_selection(query, session, case_id, account_ids, account_holders)
    if start_date is not None:
        query = query.where(FinancialTransaction.ordering_date >= start_date)
    if end_date is not None:
        query = query.where(FinancialTransaction.ordering_date <= end_date)
    pairs = list(session.execute(query.order_by(FinancialTransaction.id).limit(MAX_SUMMARY_ROWS + 1).execution_options(populate_existing=True)))
    # Accounts are read once each. Joined to every payment, each account's metadata JSON was decoded again for every
    # one of its payments. A payment whose account is missing pairs with None, as the outer join gave.
    account_keys = sorted({row.account_id for row, _ in pairs if row.account_id is not None}, key=str)
    accounts = {}
    for offset in range(0, len(account_keys), 5000):
        accounts.update((account.id, account) for account in session.scalars(select(FinancialAccount).where(
            FinancialAccount.id.in_(account_keys[offset:offset + 5000])).execution_options(populate_existing=True)))
    pairs = [(row, document, accounts.get(row.account_id)) for row, document in pairs]
    result = dict(case_id=str(case_id), account_id=str(account_id) if account_id else None,
        start_date=start_date.isoformat() if start_date else None, end_date=end_date.isoformat() if end_date else None,
        included_classes=sorted(p.value for p in DEFAULT_TOTAL_CLASSES), max_rows=MAX_SUMMARY_ROWS,
        available=False, reason=None, considered_rows=None, included_rows=None, excluded_rows=None, has_credit_card_readings=False,
        exclusions=None, currencies=[], applied=False,
        limitation="Current ledger account postings only, with admitted source documents and included row/source proof classes. Currency totals are separate. Internal transfers are not matched or netted; net postings are not an account balance. Missing evidence and incomplete extraction are not measured by these totals.")
    if account_ids or account_holders:
        result.update(account_ids=[str(id) for id in (account_ids or [])], account_holders=account_holders or [])
    if capture_readings:
        result['readings'] = []
        result['history_captured'] = False
    if grouping is not None:
        result.update(grouping=grouping, date_basis="ordering_date", points=[])
    if len(pairs) > MAX_SUMMARY_ROWS:
        result['reason'] = f'More than {MAX_SUMMARY_ROWS:,} rows match this scope. Narrow the account or dates; no partial total was calculated.'
        return result
    exclusions = {status.value: 0 for status in LedgerStatus if status.value != 'admitted'}
    exclusions.update(source_not_admitted=0, proof_class_not_included=0)
    groups = {}
    points = {}
    parties = {}
    if capture_readings and not totals_only_readings:
        from services.financial.account_parties import _account_party_state
        from services.financial.transaction_query import account_label_index
        parties = {a['id']: a for a in _account_party_state(session, case_id=case_id)['accounts']}
        account_labels = account_label_index(parties)
        from services.financial.payment_party_matches import case_party_matches
        party_matches = case_party_matches(session, case_id)
        # Stored categories in bounded queries, not one query per payment in to_view.
        from services.financial.payment_categories import attach_stored
        attach_stored(session, [row for row, _, _ in pairs])
    for row, document, account in pairs:
        if document is None or account is None or document.case_id != case_id or account.case_id != case_id:
            raise LedgerSummaryError("Ledger source or account ownership is inconsistent; summary unavailable.")
        try:
            status = LedgerStatus(row.ledger_status)
            source_status = DocumentStatus(document.status)
            row_class, source_class = ProofClass(row.proof_class), ProofClass(document.proof_class)
        except ValueError as exc:
            raise LedgerSummaryError("Stored classification or disposition is unrecognized.") from exc
        if capture_readings:
            from services.financial.transaction_query import to_view
            reason = (status.value if status.value != 'admitted' else
                'source_not_admitted' if source_status.value != 'admitted' else
                'proof_class_not_included' if not counts_toward_totals(row_class) or not counts_toward_totals(source_class) else None)
            result['readings'].append(dict(row=_totals_row(row), included=reason is None, exclusion_reason=reason,
                account=dict(id=str(account.id), account_type=account.account_type),
                source=dict(id=str(document.id), proof_class=source_class.value, status=source_status.value))
                if totals_only_readings else dict(row=to_view(row, account=row.account, account_parties=parties,
                canonical_account_labels=account_labels, party_matches=party_matches).to_json(), included=reason is None,
                exclusion_reason=reason, provenance=_json_copy(row.provenance),
                investigation_label_history=_json_copy((row.metadata_ or {}).get("investigation_label_history", [])),
                account=dict(id=str(account.id), account_type=account.account_type, label=(account.metadata_ or {}).get('display_label') or account.identifier_as_printed or account.holder_name),
                source=dict(id=str(document.id), evidence_file_id=str(document.evidence_file_id) if document.evidence_file_id else None,
                    sha256_at_ingestion=document.sha256_at_ingestion, proof_class=source_class.value,
                    status=source_status.value, parser_name=document.parser_name, parser_version=document.parser_version)))
        if status.value == 'admitted' and row.superseded_by_id is not None:
            raise LedgerSummaryError("An admitted row references a replacement; summary unavailable.")
        if status.value != 'admitted':
            exclusions[status.value] += 1
            continue
        if source_status.value != 'admitted':
            exclusions['source_not_admitted'] += 1
            continue
        if not counts_toward_totals(row_class) or not counts_toward_totals(source_class):
            exclusions['proof_class_not_included'] += 1
            continue
        if account.account_type == 'credit_card':
            result['has_credit_card_readings'] = True
        if type(row.amount_minor) is not int or row.amount_minor < 0 or row.direction not in ('credit', 'debit'):
            raise LedgerSummaryError("An included ledger amount or direction is invalid.")
        try:
            currency = get_currency(row.currency)
        except Exception as exc:
            raise LedgerSummaryError("An included ledger currency is unsupported.") from exc
        group = groups.setdefault(currency.code, dict(currency=currency.code, rows=0, credits_minor=0, debits_minor=0))
        group['rows'] += 1
        group[row.direction + 's_minor'] += row.amount_minor
        if grouping is not None:
            if type(row.ordering_date) is not date:
                raise LedgerSummaryError("An included ledger ordering date is invalid.")
            bucket = row.ordering_date if grouping == "daily" else row.ordering_date.replace(day=1)
            point = points.setdefault((bucket.isoformat(),currency.code),
                dict(date=bucket.isoformat(),currency=currency.code,rows=0,credits_minor=0,debits_minor=0,
                     transaction_ids=[],source_document_ids=set()))
            point['rows'] += 1
            point[row.direction + 's_minor'] += row.amount_minor
            point['transaction_ids'].append(str(row.id))
            point['source_document_ids'].add(str(document.id))
    for group in list(groups.values()) + list(points.values()):
        group['net_minor'] = str(group['credits_minor'] - group['debits_minor'])
        group['credits_minor'] = str(group['credits_minor'])
        group['debits_minor'] = str(group['debits_minor'])
    excluded = sum(exclusions.values())
    result.update(available=True, considered_rows=len(pairs), included_rows=len(pairs)-excluded,
        excluded_rows=excluded, exclusions=exclusions, currencies=[groups[c] for c in sorted(groups)])
    if grouping is not None:
        for point in points.values():
            point['source_document_ids'] = sorted(point['source_document_ids'])
        result['points'] = [points[key] for key in sorted(points)]
    return result



def ledger_counterparties(session, *, case_id, account_id=None, start_date=None, end_date=None, account_ids=None, account_holders=None):
    """Group exact source labels, not inferred people or matched transfers."""
    result = ledger_summary(session, case_id=case_id, account_id=account_id, account_ids=account_ids, account_holders=account_holders,
        start_date=start_date, end_date=end_date, capture_readings=True, totals_only_readings=True)
    readings = result.pop('readings')
    result.pop('history_captured')
    result.update(counterparties=[], label_basis='counterparty_raw_exact',
        counterparty_limitation='Equal source labels are grouped verbatim within each currency, without identity resolution or transfer matching. Missing and blank labels remain separate. Credits and debits are account postings, not inferred sender or beneficiary roles.')
    if not result['available']:
        return result
    groups = {}
    for reading in readings:
        if not reading['included']:
            continue
        row = reading['row']
        label = row['counterparty_raw']
        if label is not None and not isinstance(label, str):
            raise LedgerSummaryError('An included counterparty label is invalid.')
        currency = get_currency(row['currency']).code
        group = groups.setdefault((label, currency), dict(label=label, currency=currency,
            rows=0, credits_minor=0, debits_minor=0, transaction_ids=[], source_document_ids=set()))
        group['rows'] += 1
        group[row['direction'] + 's_minor'] += int(row['amount_minor'])
        group['transaction_ids'].append(row['key'])
        group['source_document_ids'].add(reading['source']['id'])
    for key in sorted(groups, key=lambda key: (key[0] is not None, key[0] or '', key[1])):
        group = groups[key]
        group['net_minor'] = str(group['credits_minor'] - group['debits_minor'])
        group['credits_minor'] = str(group['credits_minor'])
        group['debits_minor'] = str(group['debits_minor'])
        group['source_document_ids'] = sorted(group['source_document_ids'])
        result['counterparties'].append(group)
    return result
