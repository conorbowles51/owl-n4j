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
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.financial.ledger_summary import LedgerSummaryError
from services.financial.ledger_tracing import TraceAttributionInput, _exact_json
from services.financial.ledger_transfers import TransferPairChoice, ledger_transfer_candidates
from services.financial.network_tracing import NetworkOpening, network_results
from services.financial.ledger_snapshot import view_capture, snapshot_matches
from services.financial.trace_assets import TraceAssetUseInput, validate_asset_uses
from services.financial.tracing import Doctrine, TracingError

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
    asset_uses: list[TraceAssetUseInput] = Field(default_factory=list, max_length=50)
    allow_backward: bool = Field(default=False, strict=True)
    backward_basis: str = Field(default='', max_length=4096)

    @field_validator('order_basis')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Record the basis for the movement order.')
        return value


class TraceSourcesInput(BaseModel):
    """Where money came into the selected accounts: a backward walk over the selected transfers, bounded by steps."""
    model_config = ConfigDict(extra='forbid')
    expected_snapshot_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    population: str = Field(pattern=r'^(working|verified)$')
    tolerance_days: int = Field(ge=0, le=7, strict=True)
    start_date: date | None = None
    end_date: date | None = None
    currency: str = Field(pattern=r'^[A-Z]{3}$')
    steps: int = Field(default=DEFAULT_STEPS, ge=0, le=MAX_STEPS, strict=True)
    account_ids: list[UUID] = Field(min_length=1, max_length=50)
    pairs: list[TransferPairChoice] = Field(default_factory=list, max_length=250)
    basis: str = Field(default='', max_length=4096)


def trace_sources(capture, request):
    """(summary, sections): the backward walk. Every credit of a reached account is either a selected transfer
    (followed, or counted and stated as not followed past the step limit) or listed as an outside source; nothing is
    dropped. Debits are outside this question and the limitation says so."""
    request = TraceSourcesInput.model_validate(request)
    result = ledger_transfer_candidates(capture, population=request.population, tolerance_days=request.tolerance_days, whole_case=True)
    if snapshot_matches(capture, request.expected_snapshot_sha256) is None:
        raise LedgerSummaryError('Captured ledger or date scope changed. Reload the comparison before tracing.')
    document, stamp = view_capture(capture)
    rows = {row['key']: row for row in result['rows'] if row['currency'] == request.currency}
    candidates = {(pair['debit_id'], pair['credit_id']) for pair in result['candidates']}
    if request.pairs and not request.basis.strip():
        raise LedgerSummaryError('Record the basis for transfer pairings.')
    links, used = {}, set()
    for pair in request.pairs:
        debit, credit = str(pair.debit_id), str(pair.credit_id)
        if (debit, credit) not in candidates or debit not in rows or credit not in rows or debit in used or credit in used:
            raise LedgerSummaryError('Choose proposed transfer pairs in the selected currency without reusing postings.')
        used.update((debit, credit))
        links[debit] = credit
    known = {row['account_id'] for row in rows.values()}
    selected = []
    for account in request.account_ids:
        if str(account) not in known:
            raise LedgerSummaryError('Choose accounts with current readings in the selected currency.')
        selected.append(str(account))
    if len(set(selected)) != len(selected):
        raise LedgerSummaryError('Choose each account once.')
    incoming = {}
    for debit, credit in sorted(links.items()):
        incoming.setdefault(rows[credit]['account_id'], []).append((debit, credit))
    depth = {account: 0 for account in selected}
    frontier = sorted(depth)
    while frontier:
        following = []
        for account in frontier:
            if depth[account] >= request.steps:
                continue
            for debit, _ in incoming.get(account, ()):
                source = rows[debit]['account_id']
                if source not in depth:
                    depth[source] = depth[account] + 1
                    following.append(source)
        frontier = sorted(set(following))
    followed, stopped = [], []
    for debit, credit in sorted(links.items()):
        source, target = rows[debit]['account_id'], rows[credit]['account_id']
        if target in depth and source in depth:
            followed.append((debit, credit))
        elif target in depth:
            stopped.append((debit, credit))
    paired = {key for pair in followed + stopped for key in pair}
    labels = {row['account_id']: row.get('account_label') for row in rows.values()}
    accounts = {}
    for account in sorted(depth):
        accounts[account] = dict(account_id=account, label=labels.get(account), steps_back=depth[account],
                                 outside_credits=0, outside_credits_minor=0, transfers_in=0, transfers_in_minor=0,
                                 not_followed=0, not_followed_minor=0)
    outside = []
    for key in sorted(rows):
        row = rows[key]
        if row['direction'] != 'credit' or row['account_id'] not in depth or key in paired:
            continue
        outside.append(row)
        entry = accounts[row['account_id']]
        entry['outside_credits'] += 1
        entry['outside_credits_minor'] += int(row['amount_minor'])
    transfers = []
    for debit, credit in followed:
        entry = accounts[rows[credit]['account_id']]
        entry['transfers_in'] += 1
        entry['transfers_in_minor'] += int(rows[debit]['amount_minor'])
        transfers.append(dict(debit_id=debit, credit_id=credit, amount_minor=rows[debit]['amount_minor'], currency=request.currency,
                              from_account_id=rows[debit]['account_id'], from_account_label=labels.get(rows[debit]['account_id']),
                              to_account_id=rows[credit]['account_id'], to_account_label=labels.get(rows[credit]['account_id']),
                              debit_date=rows[debit]['ordering_date'], credit_date=rows[credit]['ordering_date'],
                              steps_back=depth[rows[debit]['account_id']]))
    stops = []
    for debit, credit in stopped:
        entry = accounts[rows[credit]['account_id']]
        entry['not_followed'] += 1
        entry['not_followed_minor'] += int(rows[debit]['amount_minor'])
        stops.append(dict(debit_id=debit, credit_id=credit, amount_minor=rows[debit]['amount_minor'], currency=request.currency,
                          from_account_id=rows[debit]['account_id'], from_account_label=labels.get(rows[debit]['account_id']),
                          to_account_id=rows[credit]['account_id'], to_account_label=labels.get(rows[credit]['account_id']),
                          date=rows[credit]['ordering_date']))
    for entry in accounts.values():
        for name in ('outside_credits_minor', 'transfers_in_minor', 'not_followed_minor'):
            entry[name] = str(entry[name])
    words = None
    if stops:
        places = sorted({stop['to_account_label'] or stop['to_account_id'] for stop in stops})
        first = min(stop['date'] for stop in stops)
        words = ('Stopped after %d step%s back: %d selected transfer%s into %s, the first received on %s, %s not followed to '
                 'the paying account. Add one step to continue.'
                 % (request.steps, '' if request.steps == 1 else 's', len(stops), '' if len(stops) == 1 else 's',
                    ', '.join(places), first, 'was' if len(stops) == 1 else 'were'))
    summary = dict(case_id=result['case_id'], applied=False, currency=request.currency, steps=request.steps,
                   snapshot_sha256=stamp['snapshot_sha256'], digest_covers=stamp['digest_covers'],
                   accounts=[accounts[account] for account in sorted(accounts)], selected_accounts=selected,
                   outside_credits=len(outside), transfers_in=len(transfers), not_followed=len(stops), stops=stops,
                   stopped=bool(stops), continue_with_steps=(request.steps + 1) if stops and request.steps < MAX_STEPS else None,
                   stop_words=words, candidates_in_scope=len(result['candidates']),
                   limitations=['A backward walk over the selected transfers only: it reports where money is recorded arriving, not '
                                'whose money it was. Transfer pairings are investigator assumptions, not ledger facts.',
                                'Every credit of a reached account in the selected currency is counted here exactly once: as a selected '
                                'transfer followed, a selected transfer counted as not followed past the step limit, or an outside source.',
                                'Debits of the reached accounts are outside this question; the step trace follows money onward.'])
    return summary, dict(sources=outside, transfers=transfers)
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
    on the same day is placed straight after it, and each such move is named in the report. With explicit backward
    timing the order is kept as recorded or given: an earlier receiving credit stays where it is and its pair is
    calculated as a backward assumption instead of being moved."""
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
    if request.allow_backward:
        return ordered, moved
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


def walk_payload(request, rows, *, case_id, snapshot_sha256, digest_covers, candidates=None):
    """(payload, stopped): the complete trace document from the rows the request is bound to.

    ``candidates`` checks that each selected pair is a proposed transfer of the captured comparison; a replay has no
    capture, so it passes None and recomputes the calculation from the report's own rows (its limitation says so)."""
    links, receiving, used = {}, set(), set()
    if request.pairs and not request.basis.strip():
        raise LedgerSummaryError('Record the basis for transfer pairings and movement order.')
    for pair in request.pairs:
        debit, credit = str(pair.debit_id), str(pair.credit_id)
        if ((candidates is not None and (debit, credit) not in candidates)
                or debit not in rows or credit not in rows or debit in used or credit in used):
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
    if request.allow_backward and not request.backward_basis.strip():
        raise LedgerSummaryError('Explain the basis for allowing backward transfer timing.')
    ordered, moved = movement_order(request, scoped, followed)
    positions = {key: i for i, key in enumerate(ordered)}
    backward_pairs = ([(debit, credit) for debit, credit in sorted(followed.items()) if positions[credit] <= positions[debit]]
                      if request.allow_backward else [])
    account_order = []
    if backward_pairs:
        # Account dependencies, not global dates, set the calculation order (as the cross-account trace does);
        # acyclic dependencies ensure every incoming allocation is known before its account is calculated.
        dependencies = {account: set() for account in accounts}
        for debit, credit in followed.items():
            dependencies[rows[credit]['account_id']].add(rows[debit]['account_id'])
        while dependencies:
            ready = sorted(account for account, parents in dependencies.items() if not parents)
            if not ready:
                raise LedgerSummaryError('Backward timing with a circular account dependency cannot be resolved by this calculation. No trace was returned.')
            account_order.extend(ready)
            dependencies = {account: parents - set(ready) for account, parents in dependencies.items() if account not in ready}
    validate_asset_uses(request.asset_uses, scoped, {str(pair.debit_id) for pair in request.pairs},
                        ordered_transaction_ids=ordered, transfer_credits={str(pair.credit_id) for pair in request.pairs})
    try:
        results = network_results(request, rows=scoped, accounts=accounts, openings=openings, ordered=ordered, positions=positions, links=followed,
                                  backward_pairs=backward_pairs, account_order=account_order, roots=roots, root_totals=root_totals)
    except TracingError as error:
        raise LedgerSummaryError(str(error)) from error
    labels = {row['account_id']: row.get('account_label') for row in scoped.values()}
    stops = {}
    for method, outcome in results.items():
        draws = {str(draw['transaction_id']): draw for account in outcome['accounts'].values() for draw in account['draws']}
        stops[method] = [dict(account_id=rows[debit]['account_id'], account_label=labels.get(rows[debit]['account_id']), debit_id=debit, credit_id=credit,
                              to_account_label=rows[credit].get('account_label'), date=rows[debit]['ordering_date'], amount_minor=rows[debit]['amount_minor'],
                              claim_shares_minor={claim: share['minor_units'] for claim, share in draws[debit]['by_claim'].items()} if debit in draws else {})
                         for debit, credit in stopped]
    # The rows the request names beyond the reached accounts (a stopped pair's receiving side, a pair out of an
    # account the trace never reaches): carried in the report so the reach and the stops recompute from the file.
    referenced = {str(pair.debit_id) for pair in request.pairs} | {str(pair.credit_id) for pair in request.pairs}
    from services.financial.version import code_version
    payload = dict(schema='loupe.financial.trace_walk/1', case_id=case_id, applied=False, assumptions_verified=False,
                   inputs=request.model_dump(mode='json'), snapshot_sha256=snapshot_sha256, digest_covers=digest_covers,
                   accounts=[dict(account_id=account, label=labels.get(account), steps_from_start=depth[account]) for account in sorted(accounts)],
                   readings=[scoped[key] for key in ordered], order=ordered, same_day_moves=moved, results=results, stopped=stops,
                   backward_timing_used=bool(backward_pairs), calculation_account_order=account_order,
                   pair_rows=[rows[key] for key in sorted(referenced - set(scoped))], code_version=code_version(),
                   limitations=['Conditional trace. Opening balances, root claims, transfer pairings and same-day order are investigator assumptions, not ledger facts.',
                                'Only accounts reached from the start points by selected transfers are read: no other account can change these figures. Their postings are all included.',
                                'Movement order is recorded date, then position on the statement; same-day order remains an assumption with the basis recorded.',
                                'A transfer carries only the claim share allocated to its debit under that method. Selected methods are calculation rules, not a recommendation of which rule legally applies.']
                               + (['Conditional backward timing enabled: selected earlier receiving credits are attributed from later debit allocations. This is an investigator assumption, not a legal conclusion or a finding about payment causation.']
                                  if backward_pairs else [])
                               + (['Explicit asset-use hypotheses are separate annotations on complete withdrawals; they do not change cash results or establish asset ownership, present value or legal entitlement.']
                                  if request.asset_uses else []))
    return payload, stopped


def replay_walk(document):
    """The same calculation from a captured step-trace report's own rows: (recalculated payload, encoded bytes).

    The report carries every posting of the reached accounts and the rows its pairs name beyond them, so the reach,
    the stops, the movement order and every method's figures recompute from the file alone. What needs the case is
    not recomputed: membership of each pair in the captured comparison, and the snapshot digest binding, which stay
    with the stored run and a ledger export."""
    if 'pair_rows' not in document:
        raise LedgerSummaryError('This step-trace report was saved before replay support and carries no pair rows. '
                                 'Run the trace again to produce a replayable report.')
    request = TraceWalkInput.model_validate(document['inputs'])
    rows = {row['key']: row for row in list(document['pair_rows']) + list(document['readings'])}
    payload, _ = walk_payload(request, rows, case_id=document['case_id'],
                              snapshot_sha256=document['snapshot_sha256'], digest_covers=document['digest_covers'])
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    return payload, encoded


def trace_walk(capture, request):
    """(summary, report): the bounded trace. ``report`` is the complete record of inputs and results."""
    request = TraceWalkInput.model_validate(request)
    result = ledger_transfer_candidates(capture, population=request.population, tolerance_days=request.tolerance_days, whole_case=True)
    if snapshot_matches(capture, request.expected_snapshot_sha256) is None:
        raise LedgerSummaryError('Captured ledger or date scope changed. Reload the comparison before tracing.')
    document, stamp = view_capture(capture)
    rows = {row['key']: row for row in result['rows'] if row['currency'] == request.currency}
    candidates = {(pair['debit_id'], pair['credit_id']) for pair in result['candidates']}
    payload, stopped = walk_payload(request, rows, case_id=result['case_id'], snapshot_sha256=stamp['snapshot_sha256'],
                                    digest_covers=stamp['digest_covers'], candidates=candidates)
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    summary = dict(case_id=result['case_id'], applied=False, currency=request.currency, steps=request.steps, snapshot_sha256=stamp['snapshot_sha256'], digest_covers=stamp['digest_covers'],
                   backward_timing_used=payload['backward_timing_used'], asset_uses=len(request.asset_uses),
                   accounts=payload['accounts'], readings=len(payload['order']), same_day_moves=len(payload['same_day_moves']), candidates_in_scope=len(result['candidates']), not_followed=len(stopped),
                   stopped=bool(stopped), continue_with_steps=(request.steps + 1) if stopped and request.steps < MAX_STEPS else None,
                   stop_words=stop_words(stopped, rows, request.steps), scenario_sha256=hashlib.sha256(encoded).hexdigest(), scenario_byte_count=len(encoded),
                   methods={method: dict(claims=outcome['claims'], hops=len(outcome['hops']), unidentified_withdrawals_minor=outcome['unidentified_withdrawals_minor'],
                                         asset_uses=outcome['asset_uses'], stops=payload['stopped'][method]) for method, outcome in payload['results'].items()})
    return summary, encoded


def stop_words(stopped, rows, steps):
    if not stopped:
        return None
    places = sorted({rows[debit].get('account_label') or rows[debit]['account_id'] for debit, _ in stopped})
    first = min(rows[debit]['ordering_date'] for debit, _ in stopped)
    return ('Stopped after %d step%s: %d selected transfer%s out of %s, the first on %s, %s not followed. Add one step to continue.'
            % (steps, '' if steps == 1 else 's', len(stopped), '' if len(stopped) == 1 else 's', ', '.join(places), first, 'was' if len(stopped) == 1 else 'were'))
