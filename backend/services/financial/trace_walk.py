"""A cross-account trace bounded by steps from its start point, not by the size of the case.

A step is one selected transfer followed out of an account the trace has already reached. An account's calculation
reads only its own postings and the claim shares carried into it by selected transfers, so an account no selected
transfer reaches cannot change the answer: it is left out, and the work follows the trace, not the case. The start
points are the payments carrying the root claims.

A trace that reaches its step limit stops there and says exactly where: which transfers were not followed, from which
account, how much of each claim was in them, and that one more step continues it. Every run is calculated from the
start point, so a continued trace is the same calculation with a larger limit (same inputs, same result).
"""
import hashlib
import json
from datetime import date
from typing import ClassVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.financial.ledger_summary import LedgerSummaryError
from services.financial.ledger_tracing import TraceAttributionInput, _exact_json
from services.financial.ledger_transfers import TransferPairChoice, ledger_transfer_candidates
from services.financial.network_tracing import NetworkOpening, network_results
from services.financial.ledger_snapshot import view_capture, snapshot_matches
from services.financial.tracing import Doctrine

MAX_STEPS = 25
DEFAULT_STEPS = 3


class TraceWalkInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_snapshot_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    population: str = Field(pattern=r'^(working|verified)$')
    tolerance_days: int = Field(ge=0, le=7, strict=True)
    start_date: date | None = None
    end_date: date | None = None
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    steps: int = Field(default=DEFAULT_STEPS, ge=0, le=MAX_STEPS, strict=True)
    attributions: list[TraceAttributionInput] = Field(min_length=1, max_length=50)
    pairs: list[TransferPairChoice] = Field(default_factory=list, max_length=250)
    openings: list[NetworkOpening] = Field(default_factory=list, max_length=250)
    basis: str = Field(default='', max_length=4096)
    order_basis: str = Field(min_length=1, max_length=4096)
    ordered_transaction_ids: list[UUID] | None = None
    doctrines: list[Doctrine] = Field(min_length=1, max_length=5)

    # What the shared calculation reads of a cross-account request and this trace does not offer.
    asset_uses: ClassVar[tuple] = ()
    backward_basis: ClassVar[str] = ''

    @field_validator('order_basis')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Record the basis for the movement order.')
        return value


def reached_accounts(*, roots, links, rows, steps):
    """(depth per account, the links not followed): breadth first from the start accounts over the selected transfers."""
    depth = {account: 0 for account in roots}
    frontier = sorted(depth)
    outgoing = {}
    for debit, credit in links.items():
        outgoing.setdefault(rows[debit]['account_id'], []).append((debit, credit))
    while frontier:
        following = []
        for account in frontier:
            if depth[account] >= steps:
                continue
            for _, credit in sorted(outgoing.get(account, ())):
                target = rows[credit]['account_id']
                if target not in depth:
                    depth[target] = depth[account] + 1
                    following.append(target)
        frontier = sorted(set(following))
    # A selected transfer between two reached accounts is part of the calculation; one out of a reached account into
    # an account past the limit is where the trace stops; one from an account never reached plays no part.
    followed, stopped = {}, []
    for debit, credit in sorted(links.items()):
        source, target = rows[debit]['account_id'], rows[credit]['account_id']
        if source in depth and target in depth:
            followed[debit] = credit
        elif source in depth:
            stopped.append((debit, credit))
    return depth, followed, stopped


def movement_order(request, scoped, followed):
    """(order, moved): the investigator's explicit order if given, else the recorded one: date, then the row's place on
    its statement. Same-day order is an assumption either way, so a receiving credit recorded before its selected debit
    on the same day is placed straight after it, and each such move is named in the report."""
    moved = []
    if request.ordered_transaction_ids is not None:
        ordered = [str(key) for key in request.ordered_transaction_ids]
        if len(ordered) != len(set(ordered)) or set(ordered) != set(scoped):
            raise LedgerSummaryError('The explicit order must contain every reading of the reached accounts exactly once.')
        dates = [scoped[key]['ordering_date'] for key in ordered]
        if dates != sorted(dates):
            raise LedgerSummaryError('Movement order cannot reverse recorded ordering dates.')
    else:
        ordered = sorted(scoped, key=lambda key: (scoped[key]['ordering_date'], scoped[key].get('row_index') or 0, key))
    for _ in range(len(followed) + 1):
        positions = {key: i for i, key in enumerate(ordered)}
        late = [(debit, credit) for debit, credit in sorted(followed.items()) if positions[credit] <= positions[debit]]
        if not late:
            return ordered, moved
        debit, credit = late[0]
        if scoped[credit]['ordering_date'] < scoped[debit]['ordering_date']:
            raise LedgerSummaryError('Forward tracing requires each selected receiving credit on or after its debit. The credit on %s comes before '
                                     'its debit on %s; backward tracing is not assumed.' % (scoped[credit]['ordering_date'], scoped[debit]['ordering_date']))
        ordered.remove(credit)
        ordered.insert(ordered.index(debit) + 1, credit)
        moved.append(dict(credit_id=credit, placed_after=debit, date=scoped[debit]['ordering_date']))
    raise LedgerSummaryError('The selected transfers cannot be placed in one forward order on their dates.')


def trace_walk(capture, request):
    """(summary, report): the bounded trace. ``report`` is the complete record of inputs and results."""
    request = TraceWalkInput.model_validate(request)
    result = ledger_transfer_candidates(capture, population=request.population, tolerance_days=request.tolerance_days, whole_case=True)
    if snapshot_matches(capture, request.expected_snapshot_sha256) is None:
        raise LedgerSummaryError('Captured ledger or date scope changed. Reload the comparison before tracing.')
    document, stamp = view_capture(capture)
    rows = {row['key']: row for row in result['rows'] if row['currency'] == request.currency}
    candidates = {(pair['debit_id'], pair['credit_id']): pair for pair in result['candidates']}
    links, receiving, used = {}, set(), set()
    if request.pairs and not request.basis.strip():
        raise LedgerSummaryError('Record the basis for transfer pairings and movement order.')
    for pair in request.pairs:
        debit, credit = str(pair.debit_id), str(pair.credit_id)
        if (debit, credit) not in candidates or debit not in rows or credit not in rows or debit in used or credit in used:
            raise LedgerSummaryError('Choose proposed transfer pairs in the selected currency without reusing postings.')
        used.update((debit, credit))
        receiving.add(credit)
        links[debit] = credit
    roots, root_totals = {}, {}
    for attribution in request.attributions:
        key = str(attribution.transaction_id)
        if key not in rows or rows[key]['direction'] != 'credit' or key in receiving:
            raise LedgerSummaryError('Root attributions must name selected-currency credits that are not receiving sides of selected transfers.')
        roots.setdefault(key, []).append(attribution)
        root_totals[attribution.claim_id] = root_totals.get(attribution.claim_id, 0) + int(attribution.amount_minor)
    depth, followed, stopped = reached_accounts(roots={rows[key]['account_id'] for key in roots}, links=links, rows=rows, steps=request.steps)
    accounts = set(depth)
    declared = {str(opening.account_id): opening for opening in request.openings}
    if len(declared) != len(request.openings):
        raise LedgerSummaryError('Supply one opening balance for each account, without duplicates.')
    missing = sorted(accounts - set(declared))
    if missing:
        names = {row['account_id']: row.get('account_label') for row in rows.values()}
        raise LedgerSummaryError('Declare an opening balance for every account this trace reaches: ' + ', '.join(names.get(a) or a for a in missing) + '.')
    openings = {account: declared[account] for account in accounts}
    scoped = {key: row for key, row in rows.items() if row['account_id'] in accounts}
    ordered, moved = movement_order(request, scoped, followed)
    positions = {key: i for i, key in enumerate(ordered)}
    results = network_results(request, rows=scoped, accounts=accounts, openings=openings, ordered=ordered, positions=positions, links=followed,
                              backward_pairs=[], account_order=[], roots=roots, root_totals=root_totals)
    labels = {row['account_id']: row.get('account_label') for row in scoped.values()}
    stops = {}
    for method, outcome in results.items():
        draws = {str(draw['transaction_id']): draw for account in outcome['accounts'].values() for draw in account['draws']}
        stops[method] = [dict(account_id=rows[debit]['account_id'], account_label=labels.get(rows[debit]['account_id']), debit_id=debit, credit_id=credit,
                              to_account_label=rows[credit].get('account_label'), date=rows[debit]['ordering_date'], amount_minor=rows[debit]['amount_minor'],
                              claim_shares_minor={claim: share['minor_units'] for claim, share in draws[debit]['by_claim'].items()} if debit in draws else {})
                         for debit, credit in stopped]
    payload = dict(schema='loupe.financial.trace_walk/1', case_id=result['case_id'], applied=False, assumptions_verified=False,
                   inputs=request.model_dump(mode='json'), snapshot_sha256=stamp['snapshot_sha256'], digest_covers=stamp['digest_covers'],
                   accounts=[dict(account_id=account, label=labels.get(account), steps_from_start=depth[account]) for account in sorted(accounts)],
                   readings=[scoped[key] for key in ordered], order=ordered, same_day_moves=moved, results=results, stopped=stops,
                   limitations=['Conditional trace. Opening balances, root claims, transfer pairings and same-day order are investigator assumptions, not ledger facts.',
                                'Only accounts reached from the start points by selected transfers are read: no other account can change these figures. Their postings are all included.',
                                'Movement order is recorded date, then position on the statement; same-day order remains an assumption with the basis recorded.',
                                'A transfer carries only the claim share allocated to its debit under that method. Selected methods are calculation rules, not a recommendation of which rule legally applies.'])
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    summary = dict(case_id=result['case_id'], applied=False, currency=request.currency, steps=request.steps, snapshot_sha256=stamp['snapshot_sha256'], digest_covers=stamp['digest_covers'],
                   accounts=payload['accounts'], readings=len(ordered), same_day_moves=len(moved), candidates_in_scope=len(result['candidates']), not_followed=len(stopped),
                   stopped=bool(stopped), continue_with_steps=(request.steps + 1) if stopped and request.steps < MAX_STEPS else None,
                   stop_words=stop_words(stopped, rows, request.steps), scenario_sha256=hashlib.sha256(encoded).hexdigest(), scenario_byte_count=len(encoded),
                   methods={method: dict(claims=outcome['claims'], hops=len(outcome['hops']), unidentified_withdrawals_minor=outcome['unidentified_withdrawals_minor'],
                                         stops=stops[method]) for method, outcome in results.items()})
    return summary, encoded


def stop_words(stopped, rows, steps):
    if not stopped:
        return None
    places = sorted({rows[debit].get('account_label') or rows[debit]['account_id'] for debit, _ in stopped})
    first = min(rows[debit]['ordering_date'] for debit, _ in stopped)
    return ('Stopped after %d step%s: %d selected transfer%s out of %s, the first on %s, %s not followed. Add one step to continue.'
            % (steps, '' if steps == 1 else 's', len(stopped), '' if len(stopped) == 1 else 's', ', '.join(places), first, 'was' if len(stopped) == 1 else 'were'))
