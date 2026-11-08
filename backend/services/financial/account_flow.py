"""Account flow for a whole case: the account-perspective view, computed where the rows are.

Below the synchronous transfer limit the screen computes this view in the browser from the one-answer comparison
(``frontend_v2/src/features/financial/lib/flow-perspective.ts``). Above it the rows exist only as a stored run, so
the same classification runs here, inside a whole-case run, and pages its movements and counterparty groups. The
calculation is that file's, kept exactly: a selected transfer pair is one movement (incoming, outgoing or internal
to the selected accounts); every other posting of a selected account is an unpaired movement under its account and
recorded counterparty; internal movements count once and stay out of the counterparty groups; and the view refuses
itself unless each currency's incoming minus outgoing equals the net of the selected accounts' source postings.
"""
import json
from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from services.financial.ledger_summary import LedgerSummaryError
from services.financial.ledger_snapshot import snapshot_matches
from services.financial.ledger_transfers import TransferPairChoice, ledger_transfer_candidates


class AccountFlowInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_snapshot_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    population: str = Field(pattern=r'^(working|verified)$')
    tolerance_days: int = Field(ge=0, le=7, strict=True)
    start_date: date | None = None
    end_date: date | None = None
    account_ids: list[UUID] = Field(min_length=1, max_length=250)
    pairs: list[TransferPairChoice] = Field(default_factory=list, max_length=250)


def _label(row):
    return row.get('account_label') or 'Account ' + row['account_id'][:8]


def account_flow(rows, candidates, selected_accounts, pairs):
    """(totals, movements, groups) exactly as the browser view computes them below the limit.

    ``rows`` is the captured comparison's row list in its stored order; ``candidates`` the proposed pairs as
    (debit_id, credit_id); ``selected_accounts`` and ``pairs`` the investigator's selection."""
    selected = set(selected_accounts)
    by_key = {row['key']: row for row in rows}
    used = set()
    present = {row['account_id'] for row in rows}
    if len(selected) != len(selected_accounts) or selected - present:
        raise LedgerSummaryError('Choose distinct accounts in the captured scope.')
    movements = []
    for pair in pairs:
        debit, credit = str(pair.debit_id), str(pair.credit_id)
        if (debit, credit) not in candidates or debit in used or credit in used:
            raise LedgerSummaryError('Invalid or reused transfer pairing.')
        used.update((debit, credit))
        out_side, in_side = by_key[debit], by_key[credit]
        out, into = out_side['account_id'] in selected, in_side['account_id'] in selected
        if not out and not into:
            continue
        kind = 'internal' if out and into else 'outgoing' if out else 'incoming'
        other = in_side if out else out_side
        movements.append(dict(kind=kind, currency=out_side['currency'], amount_minor=out_side['amount_minor'],
                              transaction_ids=[debit, credit],
                              label='Within selected accounts' if kind == 'internal' else _label(other),
                              group_id='account:' + other['account_id']))
    for row in rows:
        if row['key'] in used or row['account_id'] not in selected:
            continue
        raw = row.get('counterparty_raw')
        label = ('%s · unpaired source label: %s' % (_label(row), raw) if raw
                 else '%s · unpaired posting; other account unknown' % _label(row))
        movements.append(dict(kind='incoming' if row['direction'] == 'credit' else 'outgoing',
                              currency=row['currency'], amount_minor=row['amount_minor'], transaction_ids=[row['key']],
                              label=label, group_id=json.dumps(['unpaired', row['account_id'], raw if raw else None],
                                                               separators=(',', ':'), ensure_ascii=False)))
    totals = []
    for currency in sorted({movement['currency'] for movement in movements}):
        scoped = [movement for movement in movements if movement['currency'] == currency]
        amounts = {kind: sum(int(m['amount_minor']) for m in scoped if m['kind'] == kind)
                   for kind in ('incoming', 'outgoing', 'internal')}
        raw_net = sum((1 if row['direction'] == 'credit' else -1) * int(row['amount_minor'])
                      for row in rows if row['currency'] == currency and row['account_id'] in selected)
        if raw_net != amounts['incoming'] - amounts['outgoing']:
            raise LedgerSummaryError('Account perspective does not reconcile with source postings.')
        totals.append(dict(currency=currency, incoming_minor=str(amounts['incoming']), outgoing_minor=str(amounts['outgoing']),
                           internal_minor=str(amounts['internal']), net_minor=str(amounts['incoming'] - amounts['outgoing']),
                           internal_count=sum(1 for m in scoped if m['kind'] == 'internal'), movement_count=len(scoped)))
    groups = {}
    for movement in movements:
        if movement['kind'] == 'internal':
            continue
        identity = json.dumps([movement['group_id'], movement['currency']], separators=(',', ':'), ensure_ascii=False)
        group = groups.setdefault(identity, dict(id=identity, label=movement['label'], currency=movement['currency'],
                                                 credits_minor=0, debits_minor=0, transaction_ids=[]))
        group['credits_minor' if movement['kind'] == 'incoming' else 'debits_minor'] += int(movement['amount_minor'])
        group['transaction_ids'].extend(movement['transaction_ids'])
    listed = sorted(groups.values(), key=lambda group: (group['currency'],
                                                        group['debits_minor'] - group['credits_minor'], group['id']))
    for group in listed:
        group['net_minor'] = str(group['credits_minor'] - group['debits_minor'])
        group['credits_minor'] = str(group['credits_minor'])
        group['debits_minor'] = str(group['debits_minor'])
    return totals, movements, listed


def whole_case_account_flow(capture, request):
    """(summary, sections) for the stored run: the captured comparison classified from the selected accounts."""
    request = AccountFlowInput.model_validate(request)
    result = ledger_transfer_candidates(capture, population=request.population, tolerance_days=request.tolerance_days, whole_case=True)
    if snapshot_matches(capture, request.expected_snapshot_sha256) is None:
        raise LedgerSummaryError('Captured ledger or date scope changed. Reload the comparison before the flow view.')
    candidates = {(pair['debit_id'], pair['credit_id']) for pair in result['candidates']}
    totals, movements, groups = account_flow(result['rows'], candidates, [str(account) for account in request.account_ids],
                                             request.pairs)
    labels = {row['account_id']: row.get('account_label') for row in result['rows']}
    summary = dict(case_id=result['case_id'], applied=False, population=request.population,
                   tolerance_days=request.tolerance_days, start_date=result['start_date'], end_date=result['end_date'],
                   snapshot_sha256=result['snapshot_sha256'], digest_covers=result['digest_covers'],
                   selected_accounts=[dict(account_id=account, label=labels.get(account))
                                      for account in sorted(str(a) for a in request.account_ids)],
                   pairs=len(request.pairs), totals=totals, movements=len(movements), groups=len(groups),
                   limitation='A perspective over the captured scope: selected transfer pairs count once; every other '
                              'posting of a selected account is an unpaired movement under its recorded counterparty '
                              'label. Labels do not establish identity, and pairings are investigator assumptions, '
                              'not ledger facts. Each currency reconciles exactly with the selected accounts\' postings.')
    def movement_words(movement):
        return (movement['kind'], movement['label'], movement['currency'], movement['amount_minor'])
    return summary, dict(movements=[(movement, movement['kind'], movement_words(movement)) for movement in movements],
                         groups=[(group, None, (group['label'], group['currency'], group['credits_minor'],
                                                group['debits_minor'], group['net_minor'])) for group in groups])
