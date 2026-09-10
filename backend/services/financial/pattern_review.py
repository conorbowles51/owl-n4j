"""Bounded screening candidates with exact source readings, never findings."""
import hashlib
import json
from datetime import date
from services.financial.ledger_timeline import ledger_timeline
from services.financial.ledger_summary import LedgerSummaryError

MAX_HYPOTHESES = 200


def screen_ledger_patterns(export, *, population='working', window_days=3):
    if type(window_days) is not int or not 0 <= window_days <= 30:
        raise LedgerSummaryError('Choose a screening window from 0 to 30 days.')
    timeline = ledger_timeline(export, population=population)
    readings = {r['row']['key']: r for r in json.loads(export.snapshot.content)['ledger']['readings']}
    usable = [r for r in timeline['rows'] if r['chronology_basis'] not in ('ordering_date', 'statement_end_ordering_only')]
    excluded_dates = [r['key'] for r in timeline['rows'] if r not in usable]
    hypotheses = []

    def add(kind, left, right, days, explanation):
        if len(hypotheses) >= MAX_HYPOTHESES:
            raise LedgerSummaryError('More than 200 screening candidates match. Narrow the account or dates; no partial result was returned.')
        keys = [left['key'], right['key']]
        digest = hashlib.sha256(json.dumps([kind, keys, window_days]).encode()).hexdigest()
        sources = []
        for row in (left, right):
            captured = readings[row['key']]
            sources.append(dict(row=row, source=captured['source'], provenance=captured['provenance']))
        hypotheses.append(dict(id=digest, kind=kind, transaction_ids=keys, gap_days=days,
            account_id=left['account_id'], account_label=left['account_label'], currency=left['currency'],
            amount_minor=left['amount_minor'], sources=sources, explanation=explanation,
            limitation='Screening candidate only. Equal amounts and nearby dates do not establish common funds, purpose, identity or misconduct. Same-day order is unknown.'))

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
    return dict(schema='loupe.financial.pattern_review/1',case_id=timeline['case_id'],account_id=timeline['account_id'],
        start_date=timeline['start_date'],end_date=timeline['end_date'],population=population,window_days=window_days,
        snapshot_sha256=export.snapshot.sha256,reviewed_rows=len(timeline['rows']),date_unavailable_ids=excluded_dates,
        hypotheses=hypotheses,limitation='Two explicit equal-amount screens only: repeated same-direction postings, and incoming/outgoing pairs. Currency and account must match. Dates use the labelled chronology basis. No regulatory threshold, typology conclusion or automatic finding is applied.')
