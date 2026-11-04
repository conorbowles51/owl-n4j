"""The Trends page's figures, computed on the server over the rows ``/ledger`` answers with.

Trends compares two periods within one currency and account type: money in and out in each, which counterparties
or categories drove the difference, and four kinds of observation (names first seen, recurring payments, payments
larger than the earlier pattern, returned transfers). The browser worked all of it out from every payment, so the
page waited for the whole ledger (d5b330d1: 27,673 payments, 64 MB; 45-67 s before anything showed on this box).

Each figure here is the browser's own calculation over the same rows (frontend: investigation-trends.ts
investigateTrends, trendObservations, changeDrivers, defaultTrendRanges, rangeError; transaction-analysis.ts party;
investigator-workspace.ts paymentDay, paymentGroup, minorAmount; use-payment-categories.ts matchesCategories), and the
payments behind each figure are returned as their keys, so opening one shows exactly the payments it counts.

Ordering that the browser does with its own text order (localeCompare) is left to the browser: groups, drivers and
observations are returned in the order the browser's calculation first meets them, and the page sorts them as it
always has. Statement coverage stays in the browser (coverageFor over ``accounts``), from the statement register the
page already reads. Amounts are minor units as text.
"""
from __future__ import annotations

import calendar
import datetime
import json
import re
from urllib.parse import quote

from services.financial.overview_panels import _MISSING, _get, _nested, _or, _text, _truthy, amount_of, payment_group
from services.financial.overview_totals import _JS_SPACE, category_name

RULES = dict(recurring_minimum=3, weekly_gap_days=(5, 9), monthly_gap_days=(25, 35), large_payment_multiple=3,
             earlier_minimum=5, return_maximum_days=7)
_SPACE = '[' + re.escape(_JS_SPACE) + ']'
_SPACES = re.compile(_SPACE + '+')
# JavaScript /i without the u flag folds ASCII letters only (a non-ASCII letter never matches an ASCII one), and its
# \b and \w are ASCII.
_W = 'A-Za-z0-9_'
_B = '(?:(?<![%s])(?=[%s])|(?<=[%s])(?![%s]))' % (_W, _W, _W, _W)
_REFERENCE = re.compile(_B + '[Rr][Ee][Ff]' + _SPACE + '*[.:]' + _SPACE + '*([A-Za-z0-9_.-]+)')
_RETURNED = re.compile(_B + '(?:[Ss][Pp][Ee][Ii]|[Ss][Pp][Ii][Dd])' + _SPACE + '+[Dd][Ee][Vv][Uu][Ee][Ll][Tt][Oo]')
_DAY = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', re.ASCII)
_MONTH = re.compile(r'[0-9]{4}-[0-9]{2}', re.ASCII)
_SURROGATE = re.compile('[\ud800-\udfff]')
_SUGGESTED = ('description', 'matched_payment', 'printed_account')


class Unavailable(Exception):
    """These rows hold a value the browser's calculation treats in a way this port does not reproduce (a year 0000
    date, a text field that is not text, a key the browser would write differently); the page then reads every row
    and calculates in the browser as before."""


_checked_days: dict = {}


def _valid_day(value) -> str | None:
    """dateValid / validDay: a real calendar day written YYYY-MM-DD."""
    if isinstance(value, str) and value in _checked_days:
        return _checked_days[value]
    day = _check_day(value)
    if len(_checked_days) < 100_000:
        _checked_days[value] = day
    return day


def _check_day(value) -> str | None:
    if not isinstance(value, str) or not _DAY.fullmatch(value):
        return None
    if value.startswith('0000'):
        raise Unavailable('a date in year 0000')
    try:
        return value if datetime.date.fromisoformat(value).isoformat() == value else None
    except ValueError:
        return None


def payment_day(row) -> str | None:
    """paymentDay."""
    if _get(row, 'ordering_date_context') == 'statement_end_ordering_only':
        return None
    value = _get(row, 'ordering_date')
    if _nullish(value):
        return None
    if not isinstance(value, str):
        raise Unavailable('ordering_date is not text')
    date = value[:10]
    return _valid_day(date) if date else None


def _nullish(value) -> bool:
    return value is None or value is _MISSING


def _stamp(day: str) -> int:
    """Days since an epoch; differences equal (Date.parse(a) - Date.parse(b)) / 86400000."""
    return datetime.date.fromisoformat(day).toordinal()


def _js_string(value) -> str:
    """A field the browser calls a string method on: text, or nothing (Unavailable for anything else)."""
    if isinstance(value, str):
        return value
    raise Unavailable('a text field is not text')


def party(row, side: str) -> dict:
    """party(row, side) where ``side`` is the other side of the payment (Trends asks for "from" on money in and
    "to" on money out, never the account's own side)."""
    field = 'from_name' if side == 'from' else 'to_name'
    own = _get(row, 'direction') == ('debit' if side == 'from' else 'credit')
    value = _get(row, field)
    if _nullish(value):
        value = (_or(_get(row, 'account_holder'), _get(row, 'account_label'), _get(row, 'account_id')) if own
                 else _get(row, 'counterparty_raw'))
    name = _SPACES.sub(' ', _js_string(value).strip(_JS_SPACE)) if _truthy(value) else ''
    linked = _get(row, 'counterparty_link') if not own else None
    reason = ''
    if not name:
        stated = _nested(row, 'label_sources', field, 'reason')
        if _truthy(stated):
            reason = _js_string(stated)
    if _truthy(linked):
        key = 'identity:%s:%s:%s' % (_text(_nested(linked, 'kind')), _text(_nested(linked, 'id')), _uri(name))
    elif name:
        key = 'name:' + name
    elif reason:
        key = 'unknown:%s:%s' % (side, _uri(reason))
    else:
        key = 'unknown:' + side
    return dict(key=key, name=name or reason or 'Not identified',
                suggested=_nested(row, 'label_sources', field, 'source') in _SUGGESTED)


def _uri(text: str) -> str:
    """encodeURIComponent."""
    try:
        return quote(text.encode('utf-8'), safe="-_.!~*'()")
    except UnicodeEncodeError as exc:  # a lone surrogate: encodeURIComponent throws
        raise Unavailable('a name the browser cannot encode') from exc


def other_party(row) -> dict:
    return party(row, 'from' if _get(row, 'direction') == 'credit' else 'to')


def _account(row):
    """``canonical_account_id || account_id``"""
    return _or(_get(row, 'canonical_account_id'), _get(row, 'account_id'))


def _key_parts(values) -> tuple:
    """The parts of a key the browser writes with JSON.stringify (text, null and undefined, undefined written null):
    two keys are equal exactly when these tuples are."""
    for value in values:
        if not (_nullish(value) or isinstance(value, str)):
            raise Unavailable('a key part is not text')
    return tuple(None if _nullish(v) else v for v in values)


def _json_key(parts: tuple) -> str:
    """JSON.stringify of the parts."""
    if any(isinstance(v, str) and _SURROGATE.search(v) for v in parts):
        raise Unavailable('a key part the browser writes differently')
    return json.dumps(list(parts), ensure_ascii=False, separators=(',', ':'))


def _reference(row) -> str:
    """ref(row): the bank reference, else "Ref: X" in the description."""
    bank = _get(row, 'bank_reference')
    if not _nullish(bank):
        bank = _js_string(bank).strip(_JS_SPACE)
        if bank:
            return bank
    description = _description(row)
    match = _REFERENCE.search(description)
    return match.group(1) if match else ''


def _description(row) -> str:
    """``row.description || ""``"""
    value = _get(row, 'description')
    return _js_string(value) if _truthy(value) else ''


class _Memo:
    """Each payment's day, amount and other side, worked out once per answer (the browser's calculation asks for
    them again and again; d5b330d1: about 300,000 date checks for 27,673 payments)."""

    def __init__(self):
        self._day, self._amount, self._other, self._reference = {}, {}, {}, {}

    def reference(self, row):
        key = id(row)
        if key not in self._reference:
            self._reference[key] = _reference(row)
        return self._reference[key]

    def day(self, row):
        key = id(row)
        if key not in self._day:
            self._day[key] = payment_day(row)
        return self._day[key]

    def amount(self, row):
        key = id(row)
        if key not in self._amount:
            self._amount[key] = amount_of(row)
        return self._amount[key]

    def other(self, row):
        key = id(row)
        if key not in self._other:
            self._other[key] = other_party(row)
        return self._other[key]


def month_range(month: str) -> dict:
    if not _MONTH.fullmatch(month) or not _valid_day(month + '-01'):
        return dict(start='', end='')
    year, number = int(month[:4]), int(month[5:7])
    return dict(start=month + '-01', end='%s-%02d' % (month, calendar.monthrange(year, number)[1]))


def default_ranges(rows) -> dict:
    days = [day for day in map(payment_day, rows) if day]
    if not days:
        return dict(earlier=dict(start='', end=''), later=dict(start='', end=''))
    last = max(days)
    later = month_range(last[:7])
    year, number = int(later['start'][:4]), int(later['start'][5:7])
    year, number = (year - 1, 12) if number == 1 else (year, number - 1)
    if year < 1:
        raise Unavailable('a month before year 0001')
    return dict(earlier=month_range('%04d-%02d' % (year, number)), later=later)


def _valid_period_day(value) -> bool:
    """dateValid for a period the page asks about. Year 0000 is a real day to the browser (proleptic Gregorian, a
    leap year like 2000); only the text is compared, so it needs no date arithmetic here."""
    if isinstance(value, str) and _DAY.fullmatch(value) and value.startswith('0000'):
        return _check_day('2000' + value[4:]) is not None
    return _valid_day(value) is not None


def range_error(earlier: dict, later: dict) -> str | None:
    if not all(_valid_period_day(day) for day in (earlier['start'], earlier['end'], later['start'], later['end'])):
        return 'Choose valid start and end dates for both periods.'
    if earlier['start'] > earlier['end'] or later['start'] > later['end']:
        return 'Each period must end on or after its start date.'
    if earlier['end'] >= later['start']:
        return ('The earlier period must finish before the later period starts; comparison periods cannot '
                'overlap.')
    return None


def _within(m, row, period) -> bool:
    day = m.day(row)
    return bool(day) and period['start'] <= day <= period['end']


def _key(row):
    key = _get(row, 'key')
    if not isinstance(key, str):
        raise Unavailable('a payment without a text key')
    return key


def _keys(rows) -> list:
    return [_key(row) for row in rows]


def change_drivers(m, earlier, later, direction: str, by: str) -> list:
    """changeDrivers, in the order its groups are first met (the browser sorts them)."""
    groups: dict = {}
    for side, rows in (('earlier', earlier), ('later', later)):
        for row in rows:
            amount = m.amount(row)
            if _get(row, 'direction') != direction or amount is None:
                continue
            p = m.other(row)  # party(row, direction === "credit" ? "from" : "to"): row.direction is direction
            unknown = p['key'].startswith('unknown:')
            if by == 'category':
                name = category_name(row)
                if not isinstance(name, str):
                    raise Unavailable('a category is not text')
                key = name
            else:
                name = 'Counterparty not identified' if unknown else p['name']
                key = p['key']
            group = groups.get(key)
            if group is None:
                group = groups[key] = dict(key=key, name=name, suggested=False, unknown=unknown, earlier=[], later=[],
                                           before=0, after=0)
            group[side].append(_key(row))
            if not group['suggested']:
                group['suggested'] = (_nested(row, 'label_sources', 'category', 'source') == 'description'
                                      if by == 'category' else p['suggested'])
            group['before' if side == 'earlier' else 'after'] += amount
    return [dict(g, before=str(g['before']), after=str(g['after']), delta=str(g['after'] - g['before']))
            for g in groups.values()]


def _js_less(a, b) -> bool:
    """``a < b`` for the row positions a ledger row carries (numbers, null, undefined)."""
    def number(value):
        if value is _MISSING:
            return None
        if value is None:
            return 0
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise Unavailable('a row position is not a number')
        return value
    a, b = number(a), number(b)
    return a is not None and b is not None and a < b


def observations(m, rows, earlier: dict, later: dict) -> tuple[list, dict]:
    """trendObservations, in the order the browser's calculation makes them (the browser sorts them). Each
    observation's payments are keys; a "larger" observation names its earlier payments by baseline (``baselines``)."""
    dated = [r for r in rows if m.day(r) and m.amount(r) is not None]
    current = [r for r in dated if _within(m, r, later)]
    previous = [r for r in dated if _within(m, r, earlier)]
    history = [r for r in dated if m.day(r) < later['start']]
    result = []
    if history:
        seen = {m.other(r)['key'] for r in history}
        first: dict = {}
        for row in current:
            p = m.other(row)
            if p['key'].startswith('unknown:') or p['key'] in seen:
                continue
            first.setdefault('%s:%s' % (_get(row, 'direction'), p['key']), []).append(row)
        for key, payments in first.items():
            start = min(m.day(r) for r in payments)
            result.append(dict(
                id='first:' + key, kind='first-seen', title=m.other(payments[0])['name'],
                explanation=('First appears on %s in the loaded records for this scope; %d later-period payments. '
                             'Earlier loaded records contain no payment with this displayed name. This does not '
                             'establish a new relationship.' % (start, len(payments))),
                amount=str(sum(m.amount(r) for r in payments)), rows=_keys(payments), earlier_rows=None,
                suggested=any(m.other(r)['suggested'] for r in payments), direction=_get(payments[0], 'direction')))
    repeated: dict = {}
    for row in dated:
        if m.day(row) > later['end']:
            continue
        p = m.other(row)
        if p['key'].startswith('unknown:'):
            continue
        key = _key_parts([_account(row), payment_group(row), _get(row, 'direction'), p['key'], str(m.amount(row))])
        repeated.setdefault(key, []).append(row)
    weekly, monthly = RULES['weekly_gap_days'], RULES['monthly_gap_days']
    for key, payments in repeated.items():
        if len(payments) < RULES['recurring_minimum'] or not any(_within(m, r, later) for r in payments):
            continue
        payments.sort(key=payment_day)
        gaps = [_stamp(m.day(b)) - _stamp(m.day(a)) for a, b in zip(payments, payments[1:])]
        cadence = ('Weekly' if all(weekly[0] <= g <= weekly[1] for g in gaps)
                   else 'Monthly' if all(monthly[0] <= g <= monthly[1] for g in gaps) else '')
        if not cadence:
            continue
        head = payments[0]
        result.append(dict(
            id='recurring:' + _json_key(key), kind='recurring', title='%s payments · %s' % (cadence, m.other(head)['name']),
            explanation=('%d payments of the same amount in %s, %s to %s. Gaps are %d–%d days. This is an observed '
                         'schedule, not proof of a contract or purpose.' % (
                             len(payments),
                             _text(_or(_get(head, 'canonical_account_label'), _get(head, 'account_label'),
                                       'one account')),
                             m.day(head), m.day(payments[-1]), min(gaps), max(gaps))),
            amount=str(m.amount(head)), rows=_keys(payments), earlier_rows=None,
            suggested=any(m.other(r)['suggested'] for r in payments), direction=_get(head, 'direction')))
    baselines: dict = {}
    for row in previous:
        baselines.setdefault('%s:%s' % (_text(_account(row)), _text(_get(row, 'direction'))), []).append(row)
    baseline_keys = {}
    for key, baseline in baselines.items():
        if len(baseline) < RULES['earlier_minimum']:
            continue
        ordered = sorted(m.amount(r) for r in baseline)
        middle = len(ordered) // 2
        median_twice = ordered[middle] * 2 if len(ordered) % 2 else ordered[middle - 1] + ordered[middle]
        if not median_twice:
            continue
        for row in current:
            if '%s:%s' % (_text(_account(row)), _text(_get(row, 'direction'))) != key:
                continue
            value = m.amount(row)
            if value * 2 <= median_twice * RULES['large_payment_multiple'] or value <= ordered[-1]:
                continue
            baseline_keys[key] = _keys(baseline)
            result.append(dict(
                id='larger:' + _key(row), kind='larger',
                title=_or(_get(row, 'description'), 'Larger payment'),
                explanation=('Above every one of the %d earlier payments in the same account and direction, and '
                             'more than three times their median. Compare the earlier payments before interpreting '
                             'this increase.' % len(baseline)),
                amount=str(value), rows=[_key(row)], earlier_rows=key, suggested=False,
                direction=_get(row, 'direction'),
                baseline=dict(median_twice=str(median_twice), maximum=str(ordered[-1]), count=len(baseline))))
    outgoing: dict = {}
    returned: dict = {}

    def reference_key(row):
        return _key_parts([_account(row), payment_group(row), str(m.amount(row)), m.reference(row)])

    for row in dated:
        if m.reference(row):
            if _get(row, 'direction') == 'debit':
                outgoing.setdefault(reference_key(row), []).append(row)
            elif _RETURNED.search(_description(row)):
                returned.setdefault(reference_key(row), []).append(row)
    days = RULES['return_maximum_days']
    for row in current:
        if _get(row, 'direction') != 'credit' or not _RETURNED.search(_description(row)):
            continue
        reference = m.reference(row)
        if not reference:
            continue
        day = _stamp(m.day(row))
        matches = []
        for p in outgoing.get(reference_key(row), []):
            gap = day - _stamp(m.day(p))
            if 0 <= gap <= days and (gap > 0 or (
                    _same(p, row, 'source_document_id') and _same(p, row, 'statement_period_id')
                    and _js_less(_get(p, 'row_index'), _get(row, 'row_index')))):
                matches.append(p)
        if len(matches) != 1:
            continue
        sent = _stamp(m.day(matches[0]))
        credits = [p for p in returned.get(reference_key(row), []) if sent <= _stamp(m.day(p)) <= sent + days]
        if len(credits) != 1:
            continue
        result.append(dict(
            id='return:' + _key(row), kind='return', title='Returned transfer · reference ' + reference,
            explanation=('A credit explicitly described as a returned transfer matches one earlier debit by account, '
                         'currency, amount and reference within seven days. Both entries remain in gross totals; '
                         'this credit is not presented as a new payer.'),
            amount=str(m.amount(row)), rows=[_key(matches[0]), _key(row)], earlier_rows=None,
            suggested=False, direction='credit'))
    return result, baseline_keys


def _same(a, b, field) -> bool:
    """``a.field === b.field`` for text, null and undefined."""
    x, y = _get(a, field), _get(b, field)
    if x is _MISSING or y is _MISSING:
        return x is y
    if not (x is None or isinstance(x, str)) or not (y is None or isinstance(y, str)):
        raise Unavailable('a document or period id is not text')
    return x == y


def _period(start, end) -> dict | None:
    if start is None and end is None:
        return None
    return dict(start=start or '', end=end or '')


def trends_view(transactions, case_id: str, categories, group: str | None = None, earlier: dict | None = None,
                later: dict | None = None) -> dict:
    """What the Trends page shows over the rows the page would use: the ledger's rows when the answer is complete
    (this case's, unique keys), kept to the chosen categories (none chosen: all).

    ``groups``: each currency and account type with its payment count (first met order; the browser sorts by count
    then name and picks the first unless ``group`` names one). ``group``: the group computed (``group`` when it is
    one of them, else the one with most payments, the first met on a tie; the page asks again with its own choice
    when the browser's order differs). ``earlier``/``later``: the periods given, each defaulting to the browser's
    "latest month vs previous month". ``result``: null when the periods are not valid (``error``), else the totals,
    drivers (both directions, by counterparty and by category), observations and the accounts for coverage."""
    chosen = list(dict.fromkeys(c for c in categories if isinstance(c, str) and c))
    complete = (len({_text(_get(row, 'key')) for row in transactions}) == len(transactions)
                and all(_get(row, 'case_id') == case_id for row in transactions))
    if not complete:
        return dict(complete=False)
    rows = [row for row in transactions if not chosen or category_name(row) in chosen]
    m = _Memo()
    counts: dict = {}
    for row in rows:
        name = payment_group(row)
        counts[name] = counts.get(name, 0) + 1
    if group not in counts:
        group = max(counts, key=counts.get) if counts else ''
    scoped = [row for row in rows if payment_group(row) == group]
    defaults = default_ranges(scoped)
    earlier = earlier or defaults['earlier']
    later = later or defaults['later']
    view = dict(complete=True, categories=chosen, groups=[dict(group=g, count=c) for g, c in counts.items()],
                group=group, earlier=earlier, later=later, scoped_count=len(scoped),
                scoped_dated=any(m.day(row) for row in scoped), error=None, result=None)
    error = range_error(earlier, later)
    if error or not scoped:
        return dict(view, error=error)
    accounts: dict = {}
    for row in scoped:
        account = _account(row)
        entry = {} if account is _MISSING else dict(id=account)
        aliases = _get(row, 'account_alias_ids')
        if aliases is not _MISSING:
            entry['aliasIds'] = aliases
        label = _or(_get(row, 'canonical_account_label'), _get(row, 'account_label'), _get(row, 'account_holder'),
                    _get(row, 'account_id'))
        if label is not _MISSING:
            entry['label'] = label
        # A JavaScript Map keeps the first position and the last value; undefined, null and text are distinct keys.
        accounts[('undefined',) if account is _MISSING else ('value', json.dumps(account))] = entry
    before = [r for r in scoped if _within(m, r, earlier) and m.amount(r) is not None]
    after = [r for r in scoped if _within(m, r, later) and m.amount(r) is not None]
    found, baselines = observations(m, scoped, earlier, later)
    totals = []
    for direction in ('credit', 'debit'):
        b = [r for r in before if _get(r, 'direction') == direction]
        a = [r for r in after if _get(r, 'direction') == direction]
        totals.append(dict(direction=direction, before=str(sum(m.amount(r) for r in b)),
                           after=str(sum(m.amount(r) for r in a)), beforeCount=len(b), afterCount=len(a)))
    return dict(view, result=dict(
        accounts=list(accounts.values()),
        before_count=len(before), after_count=len(after),
        unknown_dates=_keys(r for r in scoped if not m.day(r)),
        invalid_amounts=sum(1 for r in scoped if m.amount(r) is None),
        history_count=sum(1 for r in scoped if m.day(r) and m.day(r) < later['start']),
        totals=totals,
        drivers={'%s:%s' % (direction, by): change_drivers(m, before, after, direction, by)
                 for direction in ('debit', 'credit') for by in ('name', 'category')},
        observations=found,
        baselines=baselines,
    ))
