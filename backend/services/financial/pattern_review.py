"""Bounded screening candidates with exact source readings, never findings."""
import hashlib
import json
from datetime import date
from services.financial.ledger_timeline import ledger_timeline
from services.financial.ledger_summary import LedgerSummaryError

MAX_HYPOTHESES = 200


def screen_ledger_patterns(export, *, population='working', window_days=3, threshold_minor=None, threshold_currency=None, cross_account=False):
    if type(cross_account) is not bool:raise LedgerSummaryError('Cross-account screening must be selected explicitly.')
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
    if cross_account and timeline['account_id'] is not None:
        raise LedgerSummaryError('Clear the account filter to screen paths between accounts.')
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
            amount_minor=str(sum(int(r['amount_minor']) for r in group)) if kind in ('split_payment_threshold', 'repeated_counterparty') else left['amount_minor'], sources=sources, explanation=explanation,
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
    # Repeated relationships often involve changing amounts and month-long gaps.
    # Match the recorded name exactly; never claim that a label establishes identity.
    relationships = {}
    for row in usable:
        label = readings[row['key']]['row'].get('counterparty_raw')
        if isinstance(label, str) and label.strip():
            relationships.setdefault((row['account_id'], row['currency'], row['direction'], label), []).append(row)
    for (*_, label), group in relationships.items():
        distinct_dates = sorted({r['chronology_date'] for r in group})
        if len(group) < 3 or len(distinct_dates) < 3:
            continue
        if len(group) > 50:
            raise LedgerSummaryError('More than 50 payments share one recorded name. Narrow the dates to inspect that relationship; no partial result was returned.')
        gaps = [(date.fromisoformat(b)-date.fromisoformat(a)).days for a,b in zip(distinct_dates, distinct_dates[1:])]
        elapsed = (date.fromisoformat(distinct_dates[-1])-date.fromisoformat(distinct_dates[0])).days
        add('repeated_counterparty',group[0],group[-1],elapsed,
            f'{len(group)} payments use the recorded name {label!r} on {len(distinct_dates)} dates. Amounts may differ. Gaps between payment dates range from {min(gaps)} to {max(gaps)} days. This check uses the full selected date range, not the short payment window.',group=group)
        hypotheses[-1].update(counterparty_label=label, minimum_gap_days=min(gaps), maximum_gap_days=max(gaps),
            limitation='The same printed name does not establish that the recipient or sender is the same person or business. Review the originals and record your explanation. The total is for these payments only; do not add overlapping pattern totals together.')
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
    if cross_account:
        from services.financial.ledger_transfers import ledger_transfer_candidates
        by_id = {r['key']:r for r in usable}
        transfers = ledger_transfer_candidates(export,population=population,tolerance_days=min(window_days,7))
        outgoing = {}
        for pair in transfers['candidates']:
            debit,credit=by_id.get(pair['debit_id']),by_id.get(pair['credit_id'])
            if not debit or not credit or int(pair['amount_minor']) == 0 or debit['chronology_date'] > credit['chronology_date']:
                continue
            outgoing.setdefault((debit['account_id'],pair['currency'],pair['amount_minor']),[]).append((debit,credit,pair))
        examined = 0
        def extend(path, used):
            nonlocal examined
            first,last = path[0][0],path[-1][1]
            if len(path)>=2:
                kind='possible_return_flow' if first['account_id']==last['account_id'] else 'possible_transfer_chain'
                group=[r for debit,credit,_ in path for r in (debit,credit)]
                gap=(date.fromisoformat(last['chronology_date'])-date.fromisoformat(first['chronology_date'])).days
                add(kind,first,last,gap,
                    'Equal-value candidate transfers return to the starting account within the selected window. Ordinary transfers, repeated source coverage and unrelated payments can create this pattern; it is not proof of round-tripping.' if kind=='possible_return_flow' else
                    'Equal-value candidate transfers may connect several accounts within the selected window. This is a possible chain for review, not a funds allocation or evidence of layering.',group=group)
                hypotheses[-1]['transfer_pairs']=[pair for _,_,pair in path]
                if kind=='possible_return_flow' or len(path)==3:return
            for edge in outgoing.get((last['account_id'],last['currency'],last['amount_minor']),[]):
                examined+=1
                if examined>10000:raise LedgerSummaryError('More than10,000candidate path extensions. Narrow the dates; no partial screen was returned.')
                debit,credit,_=edge
                if debit['key'] in used or credit['key'] in used or debit['chronology_date']<last['chronology_date']:
                    continue
                if (date.fromisoformat(credit['chronology_date'])-date.fromisoformat(first['chronology_date'])).days>window_days:
                    continue
                extend(path+[edge],used|{debit['key'],credit['key']})
        for edges in outgoing.values():
            for edge in edges:
                if (date.fromisoformat(edge[1]['chronology_date'])-date.fromisoformat(edge[0]['chronology_date'])).days<=window_days:
                    extend([edge],{edge[0]['key'],edge[1]['key']})
    return dict(schema='loupe.financial.pattern_review/1',case_id=timeline['case_id'],account_id=timeline['account_id'],
        start_date=timeline['start_date'],end_date=timeline['end_date'],population=population,window_days=window_days,cross_account=cross_account,
        threshold_minor=None if threshold_minor is None else str(threshold_minor),threshold_currency=threshold_currency,
        snapshot_sha256=export.snapshot.sha256,reviewed_rows=len(timeline['rows']),date_unavailable_ids=excluded_dates,
        hypotheses=hypotheses,limitation='Optional cross-account screening follows two or three equal-value candidate transfers, with no repeated posting, a maximum seven-day per-pair date tolerance and the selected overall window. All alternatives remain proposals; same-day order is unknown. Repeated equal amounts and equal incoming/outgoing pairs are screened within one account and currency. An optional investigator-selected threshold also screens groups of smaller same-direction payments. Dates use the labelled chronology basis. Candidates can overlap and must not be totalled together. No regulatory threshold, intent, typology conclusion or automatic finding is applied.')
