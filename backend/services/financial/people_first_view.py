"""The People & businesses page's list of names and accounts, computed on the server over the rows ``/ledger``
answers with and the account directory ``/account-parties`` answers with.

The page grouped every payment in the browser (paymentProfiles) to draw this list, so it waited for the whole ledger
(d5b330d1: 27,673 payments, 64 MB) before showing a single card. Each figure here is the browser's own calculation
over the same rows and directory (frontend: investigator-workspace.ts paymentProfiles, ownsPayment, paymentGroup,
profileAccountGroup, paymentDay; InvestigatorPeople.tsx total, UnidentifiedBreakdown; PaymentTotals;
ProfileStatementSummary; unidentified-payments.ts unidentifiedGroups). Each profile carries what its card shows and
what the page filters and sorts on, not its payments: opening a profile reads every payment and works it out in the
browser as before.

Ordering that the browser does with its own text order (sort(), localeCompare) is left to the browser: profiles are
returned in the order the browser's calculation first meets them, and the page sorts them as it always has.
"""
from __future__ import annotations

from services.financial.overview_panels import (
    _MISSING, _coalesce, _get, _js_trim, _nested, _nullish, _or, _text, _truthy, minor_amount, payment_group,
    payment_totals, unidentified_payment)
from services.financial.overview_totals import category_name
from services.financial.trends_first_view import Unavailable, payment_day


def _account_id(row):
    """``row.canonical_account_id || row.account_id``"""
    return _or(_get(row, 'canonical_account_id'), _get(row, 'account_id'))


def _key(value) -> str:
    """A value used as a JavaScript Map key. Keys here are ids and texts; anything else the port refuses."""
    if isinstance(value, str):
        return value
    raise Unavailable('a key is not text')


def _string(value) -> str:
    if not isinstance(value, str):
        raise Unavailable('a text field is not text')
    return value


def _merge_periods(prior, detail):
    """``[...new Map([...(prior || []), ...(detail || [])].map((p) => [p.id, p])).values()]`` or undefined."""
    if _truthy(detail) or _truthy(prior):
        periods: dict = {}
        for period in [*(prior if _truthy(prior) else []), *(detail if _truthy(detail) else [])]:
            periods[_key(period['id'])] = period
        return list(periods.values())
    return _MISSING


def _merge_links(prior, detail):
    """``[...(prior || []), ...detail].filter((link, i, all) => all.findIndex((o) => o.id === link.id) === i)``"""
    seen = set()
    links = []
    for link in [*(prior if _truthy(prior) else []), *detail]:
        key = _key(link['id'])
        if key not in seen:
            seen.add(key)
            links.append(link)
    return links


def owns_payment(row, party_id) -> bool:
    """ownsPayment: a reviewed holder relationship applies only within its recorded dates."""
    relationships = _get(row, 'account_relationships')
    relationships = [] if _nullish(relationships) else relationships
    links = [link for link in relationships
             if link.get('role') == 'holder' and _nested(link, 'party', 'id') == party_id]
    if not links:
        holders = _get(row, 'account_holder_parties')
        return (not (len(relationships) if isinstance(relationships, list) else 0)
                and not _nullish(holders) and any(party.get('id') == party_id for party in holders))
    day = payment_day(row)
    for link in links:
        start, end = link.get('effective_from'), link.get('effective_to')
        if not _truthy(start) and not _truthy(end):
            return True
        if day and (not _truthy(start) or day >= _string(start)) and (not _truthy(end) or day <= _string(end)):
            return True
    return False


def payment_profiles(rows, directory) -> list:
    """paymentProfiles(rows, directory) with each group's payments kept in full (the summaries below read them)."""
    groups: dict = {}
    canonical_ids = {}
    registered = {}
    for account in directory:
        canonical_ids[_key(account['id'])] = _or(account.get('canonical_id', _MISSING), account['id'])
        registered[_key(account['id'])] = account

    def ensure(key, name, kind):
        group = groups.get(key)
        if group is None:
            group = groups[key] = dict(name=name, kind=kind, rows={}, counterparty_rows={}, accounts={},
                                       nested=False)
        return group

    for account in directory:
        account_id = _key(_or(account.get('canonical_id', _MISSING), account['id']))
        recorded = registered.get(account_id) or account
        label = ' · '.join(_text(v) for v in (recorded.get('institution'), recorded.get('identifier_as_printed'),
                                               recorded.get('holder_as_recorded')) if _truthy(v)) \
            or 'Account reference %s · details not recorded' % account_id[:8]
        detail = dict(id=account_id, label=label, currency=recorded.get('currency'),
                      institution=recorded.get('institution'), number=recorded.get('identifier_as_printed'),
                      accountType=_or(recorded.get('account_type', _MISSING), None), registered=True,
                      statementPeriods=account.get('statement_periods', _MISSING),
                      relationships=account.get('relationships', []))
        account_group = ensure('account:%s' % account_id, label, 'account')
        if account['id'] == account_id:
            account_group['name'] = label
        existing = account_group['accounts'].get(account_id)
        account_group['accounts'][account_id] = dict(
            detail,
            statementPeriods=_merge_periods(existing['statementPeriods'] if existing else _MISSING,
                                            detail['statementPeriods']),
            relationships=_merge_links(existing['relationships'] if existing else _MISSING,
                                       detail['relationships']))
        for party in account.get('holder_parties', []):
            owner = ensure('owner:%s' % _key(party['id']), party['name'], 'owner')
            prior = owner['accounts'].get(account_id)
            owner['accounts'][account_id] = dict(
                detail,
                statementPeriods=_merge_periods(prior['statementPeriods'] if prior else _MISSING,
                                                detail['statementPeriods']),
                relationships=_merge_links(prior['relationships'] if prior else _MISSING, detail['relationships']))
            account_group['nested'] = True

    for row in rows:
        account_id = _account_id(row)
        id_text = _text(account_id)
        row_key = _key(_get(row, 'key'))
        own = ensure('account:%s' % id_text,
                     _or(_get(row, 'canonical_account_label'), _get(row, 'account_label'), 'Account name not recorded'),
                     'account')
        own['rows'][row_key] = row
        if id_text not in own['accounts']:
            relationships = _get(row, 'account_relationships')
            own['accounts'][id_text] = dict(
                id=account_id, label=own['name'], currency=_get(row, 'currency'),
                institution=_or(_get(row, 'account_institution'), None), number=None,
                accountType=_or(_get(row, 'account_type'), None), registered=False, statementPeriods=_MISSING,
                relationships=relationships if _truthy(relationships) else [])
        side = _get(row, 'from_name') if _get(row, 'direction') == 'credit' else _get(row, 'to_name')
        name = _coalesce(side, _get(row, 'counterparty_raw'))
        link = _get(row, 'counterparty_link')
        if _truthy(link):
            kind = link.get('kind')
            linked = (_or(canonical_ids.get(_key(link['id'])), link['id']) if kind == 'account' else link.get('id'))
            other = ensure('%s:%s' % ('owner' if kind == 'party' else 'account', _text(linked)),
                           _or(link.get('label', _MISSING), name, 'Name not recorded'),
                           'owner' if kind == 'party' else 'account')
            other['counterparty_rows'][row_key] = row
            if kind == 'account' and _text(linked) not in other['accounts']:
                other['accounts'][_text(linked)] = dict(
                    id=linked, label=other['name'], currency=None, institution=None, number=None, accountType=None,
                    registered=False, statementPeriods=_MISSING, relationships=[])
        else:
            if not _nullish(name):
                _string(name)
            ensure('name:%s' % _text(_coalesce(name, '')),
                   name if not _nullish(name) and _js_trim(name) else 'Name not recorded', 'name')['rows'][row_key] = row
        holders = _get(row, 'account_holder_parties')
        for party in ([] if _nullish(holders) else holders):
            owner = ensure('owner:%s' % _key(party['id']), party['name'], 'owner')
            own['nested'] = True
            if id_text not in owner['accounts']:
                owner['accounts'][id_text] = own['accounts'][id_text]
            if owns_payment(row, party['id']):
                owner['rows'][row_key] = row
    return [(key, group) for key, group in groups.items()]


def _unidentified_breakdown(rows) -> list:
    """UnidentifiedBreakdown's list before its sort by count: unidentifiedGroups (by direction and kind, first met)
    merged by kind, each kind at its first position with the label and reason of the last group merged into it."""
    by_direction: dict = {}
    for row in rows:
        context = unidentified_payment(row)
        if context is None:
            continue
        key = '%s:%s' % (_text(_get(row, 'direction')), context['kind'])
        group = by_direction.get(key)
        if group is None:
            group = by_direction[key] = dict(context, count=0)
        group['count'] += 1
    kinds: dict = {}
    for group in by_direction.values():
        previous = kinds.get(group['kind'])
        kinds[group['kind']] = dict(label=group['label'], reason=group['reason'],
                                    count=(previous['count'] if previous else 0) + group['count'])
    return list(kinds.values())


def _summary(key: str, group: dict) -> dict:
    rows = list(group['rows'].values())
    dates = sorted(day for day in (payment_day(row) for row in rows) if day)
    periods: dict = {}
    for account in group['accounts'].values():
        statement_periods = account['statementPeriods']
        for period in (statement_periods if _truthy(statement_periods) else []):
            periods[_key(period['id'])] = period
    periods_list = list(periods.values())
    starts = sorted(_string(p['start']) for p in periods_list if _truthy(p.get('start')))
    ends = sorted(_string(p['end']) for p in periods_list if _truthy(p.get('end')))
    if group['kind'] == 'name':
        accounts = list(dict.fromkeys(_text(_account_id(row)) for row in rows))
    else:
        accounts = list(group['accounts'])
    sources = list(dict.fromkeys([_text(_get(row, 'source_document_id')) for row in rows]
                                 + [_text(p.get('source_document_id', _MISSING)) for p in periods_list]))
    unidentified = group['kind'] == 'name' and not _js_trim(key[5:])
    amount = 0
    for row in rows:
        value = minor_amount(_get(row, 'amount_minor'))
        amount += value if value is not None else 0
    return dict(
        id=key,
        name=group['name'],
        kind=group['kind'],
        nested_under_owner=group['nested'],
        unidentified=unidentified,
        payments=len(rows),
        counterparty_payments=len(group['counterparty_rows']),
        accounts=len(accounts),
        account_details=[dict(currency=a['currency'], institution=a['institution'], number=a['number'],
                              accountType=a['accountType'], registered=a['registered'],
                              coverage=a['statementPeriods'] is not _MISSING)
                         for a in group['accounts'].values()],
        sources=len(sources),
        first=dates[0] if dates else None,
        last=dates[-1] if dates else None,
        statement_periods=len(periods_list),
        statement_periods_missing_dates=sum(1 for p in periods_list
                                            if not _truthy(p.get('start')) or not _truthy(p.get('end'))),
        statement_first=starts[0] if starts else None,
        statement_last=ends[-1] if ends else None,
        totals=payment_totals(rows) if rows else None,
        amount=str(amount),
        unidentified_groups=_unidentified_breakdown(rows) if unidentified else None,
    )


def _directory_group(account):
    """profileAccountGroup({currency: account.currency, accountType: account.account_type || null})"""
    currency, account_type = account.get('currency'), _or(account.get('account_type', _MISSING), None)
    if not _truthy(currency) or not _truthy(account_type):
        return None
    return '%s:%s' % (_text(currency), 'card' if account_type == 'credit_card' else 'bank')


def people_view(transactions, case_id: str, directory, categories, group: str | None = None) -> dict:
    """What the People & businesses list shows over the rows the page would use: the ledger's rows when the answer
    is complete (this case's, unique keys), kept to the chosen categories (none chosen: all), then to ``group`` (a
    currency and account type, ``paymentGroup``; none: all).

    ``row_count``: payments in the chosen categories. ``row_groups``: their currency and account type groups;
    ``directory_groups``: the directory accounts' (profileAccountGroup; the page joins both and sorts). ``profiles``: each profile in the order first met, with its card's figures
    (``totals``: PaymentTotals; null when it has no payments)."""
    chosen = list(dict.fromkeys(c for c in categories if isinstance(c, str) and c))
    complete = (len({_text(_get(row, 'key')) for row in transactions}) == len(transactions)
                and all(_get(row, 'case_id') == case_id for row in transactions))
    if not complete:
        return dict(complete=False)
    rows = [row for row in transactions if not chosen or category_name(row) in chosen]
    scoped = [row for row in rows if not group or payment_group(row) == group]
    return dict(
        complete=True,
        categories=chosen,
        group=group or '',
        row_count=len(rows),
        row_groups=list(dict.fromkeys(payment_group(row) for row in rows)),
        directory_groups=list(dict.fromkeys(_directory_group(account) for account in directory
                                            if _directory_group(account) is not None)),
        profiles=[_summary(key, g) for key, g in payment_profiles(scoped, directory)],
    )
