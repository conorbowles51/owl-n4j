"""Bounded screening candidates with exact source readings, never findings."""
import hashlib
import json
from datetime import date
from services.financial.ledger_timeline import ledger_timeline
from services.financial.ledger_summary import LedgerSummaryError

MAX_HYPOTHESES = 200


def screen_ledger_patterns(export, *, population='working', window_days=3, threshold_minor=None, threshold_currency=None):
    if type(window_days) is not int or not 0 <= window_days <= 30:
        raise LedgerSummaryError('Choose a screening window from 0 to 30 days.')
    if (threshold_minor is None) != (threshold_currency is None):
        raise LedgerSummaryError('Provide both an amount threshold and its currency.')
    if threshold_minor is not None:
        if type(threshold_minor) is not int or not 1 <= threshold_minor <= 9223372036854775807:
            raise LedgerSummaryError('The threshold must be a positive exact amount within the ledger range.')
        if not isinstance(threshold_currency, str) or len(threshold_currency) != 3 or not threshold_currency.isascii() or not threshold_currency.isalpha() or not threshold_currency.isupper():
            raise LedgerSummaryError('Choose a three-letter currency for the threshold.')
    timeline = ledger_timeline(export, population=population)
    readings = {r['row']['key']: r for r in json.loads(export.snapshot.content)['ledger']['readings']}
    usable = [r for r in timeline['rows'] if r['chronology_basis'] not in ('ordering_date', 'statement_end_ordering_only')]
    excluded_dates = [r['key'] for r in timeline['rows'] if r not in usable]
    hypotheses = []

    def add(kind, left, right, days, explanation, *, group=None):
        if len(hypotheses) >= MAX_HYPOTHESES:
            raise LedgerSummaryError('More than 200 screening candidates match. Narrow the account or dates; no partial result was returned.')
        group = group or [left, right]
        keys = [r['key'] for r in group]
        identity = [kind, keys, window_days]
        if kind == 'split_payment_threshold':
            identity.extend([threshold_minor, threshold_currency])
        digest = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
        sources = []
        for row in group:
            captured = readings[row['key']]
            sources.append(dict(row=row, source=captured['source'], provenance=captured['provenance']))
        hypotheses.append(dict(id=digest, kind=kind, transaction_ids=keys, gap_days=days,
            account_id=left['account_id'], account_label=left['account_label'], currency=left['currency'],
            amount_minor=str(sum(int(r['amount_minor']) for r in group)) if kind == 'split_payment_threshold' else left['amount_minor'], sources=sources, explanation=explanation,
            limitation='Screening candidate only. Amounts and nearby dates do not establish common funds, purpose, identity or misconduct. Same-day order is unknown.'))

    for i, left in enumerate(usable):
        for right in usable[i + 1:]:
            days = (date.fromisoformat(right['chronology_date']) - date.fromisoformat(left['chronology_date'])).days
            if days > window_days:
                break
            if left['account_id'] != right['account_id'] or left['currency'] != right['currency'] or left['amount_minor'] != right['amount_minor']:
                continue
            if left['direction'] == right['direction']:
                add('repeated_equal_amount', left, right, days,
                    'Two same-direction postings have the same recorded amount within the selected window. They may be legitimate separate transactions or repeated source coverage; inspect both originals.')
            elif left['direction'] == 'credit' or days == 0:
                credit, debit = (left, right) if left['direction'] == 'credit' else (right, left)
                add('equal_amount_in_and_out', credit, debit, days,
                    'A credit and debit have the same recorded amount within the selected window. This is a possible pass-through pattern to investigate, not a tracing allocation. Same-day order is not established.' if days == 0 else
                    'A credit is followed by an equal recorded debit within the selected window. This is a possible pass-through pattern to investigate, not evidence that the same funds moved.')
    if threshold_minor is not None:
        groups = {}
        for row in usable:
            if row['currency'] == threshold_currency and 0 < int(row['amount_minor']) < threshold_minor:
                groups.setdefault((row['account_id'], row['direction']), []).append(row)
        for group in groups.values():
            # Distinct maximal forward windows: skip a strict subset of the previous
            # window, retain overlapping windows that introduce later payments.
            previous_end = -1
            for start, left in enumerate(group):
                end = start
                while end + 1 < len(group) and (date.fromisoformat(group[end + 1]['chronology_date']) - date.fromisoformat(left['chronology_date'])).days <= window_days:
                    end += 1
                if end <= previous_end:
                    continue
                previous_end = end
                selected = group[start:end + 1]
                if len(selected) < 2 or sum(int(r['amount_minor']) for r in selected) < threshold_minor:
                    continue
                if len(selected) > 50:
                    raise LedgerSummaryError('A threshold candidate contains more than 50 readings. Narrow the dates or window; no partial result was returned.')
                right = selected[-1]
                days = (date.fromisoformat(right['chronology_date']) - date.fromisoformat(left['chronology_date'])).days
                add('split_payment_threshold', left, right, days,
                    'Several same-direction postings in one account are individually below the investigator-selected amount and together reach or exceed it. This is a configurable split-payment screen, not a statutory threshold or evidence of intent. Different counterparties may be involved. Overlapping candidates must not be added together.', group=selected)
    return dict(schema='loupe.financial.pattern_review/1',case_id=timeline['case_id'],account_id=timeline['account_id'],
        start_date=timeline['start_date'],end_date=timeline['end_date'],population=population,window_days=window_days,
        threshold_minor=None if threshold_minor is None else str(threshold_minor),threshold_currency=threshold_currency,
        snapshot_sha256=export.snapshot.sha256,reviewed_rows=len(timeline['rows']),date_unavailable_ids=excluded_dates,
        hypotheses=hypotheses,limitation='Repeated equal amounts and equal incoming/outgoing pairs are screened within one account and currency. An optional investigator-selected threshold also screens groups of smaller same-direction payments. Dates use the labelled chronology basis. Candidates can overlap and must not be totalled together. No regulatory threshold, intent, typology conclusion or automatic finding is applied.')
