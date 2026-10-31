"""The Financial Overview's lower panels, computed on the server over the rows ``/ledger`` answers with.

The panels (payment totals per currency and account type, who paid in and where payments went, money in then
out within a week) were worked out in the browser from every ledger row, so the Overview downloaded the whole
ledger (d5b330d1: 27,926 payments) to draw them. Each figure here is the browser's own calculation over the same
rows (frontend: InvestigatorOverview, PaymentTotals, paymentInventory, MoneyConnections, paymentProfiles,
unidentifiedPayment, unidentifiedGroups, nearbyPayments, amountOf, minorAmount, paymentGroup, bankKey). The
payments behind every figure are returned as their keys, so opening one shows exactly the payments it counts.

Ordering that the browser does with its own text order (sort(), localeCompare) is left to the browser: lists the
page sorts are returned in the order the browser's calculation first meets them, and the page sorts them as it
always has. Amounts are minor units as text; a total is null where the browser says "Amount needs checking".
"""
from __future__ import annotations

import datetime
import functools
import re
import unicodedata

from services.financial.overview_totals import _JS_SPACE, account_key, category_name, payment_day

_SPACE = '[' + re.escape(_JS_SPACE) + ']'
# JavaScript's \b without the u flag: a boundary between an ASCII word character and anything else.
_W = 'A-Za-z0-9_'
_B = '(?:(?<![%s])(?=[%s])|(?<=[%s])(?![%s]))' % (_W, _W, _W, _W)
_RETURNED = re.compile(_B + '(?:SPID|SPEI)' + _SPACE + '+DEVUELTO')
_TAX = re.compile(_B + r'(?:I\.?S\.?R\.?' + _SPACE + '+RETENIDO|IVA)' + _B)
_FOREIGN = re.compile(_B + 'ORDEN DE PAGO EXTRANJERO' + _B)
_THIRD_PARTY = re.compile(_B + 'TRASPASO A TERCEROS' + _B)
_SENT = re.compile(_B + '(?:SPID|SPEI)' + _SPACE + '+ENVIADO' + _B)
_CARD_PAYMENT = re.compile('(?:MOBILE|ONLINE|AUTOMATIC|AUTOPAY|ELECTRONIC)' + _SPACE + '*(?:PYMT|PMT|PAYMENT)')
_COMBINING = re.compile('[̀-ͯ]')
_INTEGER = re.compile(r'-?[0-9]+', re.ASCII)
_BANK_ALIASES = {
    'bbva mexico': 'bbva',
    'bbva méxico': 'bbva',
    'bbva bancomer': 'bbva',
    'banco santander mexico': 'santander',
    'banco santander méxico': 'santander',
}
_MISSING = object()


def _get(row, field):
    """``row.field``: _MISSING when the field is absent (JavaScript's undefined)."""
    return row.get(field, _MISSING) if isinstance(row, dict) else _MISSING


def _nullish(value) -> bool:
    return value is None or value is _MISSING


def _truthy(value) -> bool:
    """JavaScript truthiness for JSON values: objects and arrays are true even when empty."""
    if _nullish(value) or value is False:
        return False
    if isinstance(value, (dict, list)):
        return True
    if isinstance(value, (int, float)):
        return value != 0 and value == value
    return value != ''


def _or(*values):
    """``a || b || c``"""
    for value in values[:-1]:
        if _truthy(value):
            return value
    return values[-1]


def _coalesce(first, second):
    """``a ?? b``"""
    return second if _nullish(first) else first


def _text(value) -> str:
    """A value placed in a JavaScript template literal."""
    if value is _MISSING:
        return 'undefined'
    if value is None:
        return 'null'
    if value is True:
        return 'true'
    if value is False:
        return 'false'
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _js_trim(value: str) -> str:
    return value.strip(_JS_SPACE)


def _nested(row, *fields):
    """``row.a?.b?.c``"""
    value = row
    for field in fields:
        if not isinstance(value, dict):
            return _MISSING
        value = value.get(field, _MISSING)
    return value


def payment_group(row) -> str:
    """paymentGroup: currency and account type ("card" for credit cards, else "bank")."""
    return '%s:%s' % (_text(_get(row, 'currency')), 'card' if _get(row, 'account_type') == 'credit_card' else 'bank')


def minor_amount(value) -> int | None:
    """minorAmount: the amount in minor units when it is an integer written as digits, else None."""
    if value is None or value is _MISSING:
        return None
    if isinstance(value, bool):
        text = 'true' if value else 'false'
    elif isinstance(value, float):
        if not value.is_integer() or abs(value) > 2 ** 53 - 1:
            return None
        return int(value)
    elif isinstance(value, int):
        if abs(value) > 2 ** 53 - 1:
            return None
        return value
    else:
        text = _text(value)
    return int(text) if _INTEGER.fullmatch(text) else None


def amount_of(row) -> int | None:
    """amountOf: a non-negative amount on a credit or debit, else None (the payment cannot be totalled)."""
    amount = minor_amount(_get(row, 'amount_minor'))
    return amount if amount is not None and amount >= 0 and _get(row, 'direction') in ('credit', 'debit') else None


def _account_id(row):
    return account_key(row, _MISSING) if isinstance(row, dict) else _MISSING


def _counterparty_name(row):
    """``(direction === "credit" ? from_name : to_name) ?? counterparty_raw``"""
    side = _get(row, 'from_name') if _get(row, 'direction') == 'credit' else _get(row, 'to_name')
    return _coalesce(side, _get(row, 'counterparty_raw'))


def _holder_key(name) -> str:
    return re.sub(_SPACE + '+', ' ', _js_trim(name if _truthy(name) else '')).lower()


def bank_key(value) -> str:
    token = _holder_key(value if _truthy(value) else '')
    return _or(_BANK_ALIASES.get(token), token)


def payment_inventory(rows) -> dict:
    """paymentInventory (no known accounts): accounts, banks and currencies in the order first met (the browser
    sorts them), the first and last dated day, undated payments, accounts with no bank named and payments with no
    counterparty name."""
    accounts: dict = {}
    banks: dict = {}
    unknown_banks = set()
    currencies: dict = {}
    first = last = None
    undated = unidentified = 0
    for row in rows:
        account_id = _account_id(row)
        key = _text(account_id)
        account = accounts.get(key)
        if account is None:
            account = accounts[key] = {
                'id': account_id,
                'label': _or(_get(row, 'canonical_account_label'), _get(row, 'account_label'),
                             'Account details not recorded'),
                'currencies': {},
            }
        account['currencies'].setdefault(_text(_get(row, 'currency')), _get(row, 'currency'))
        institution = _get(row, 'account_institution')
        bank = _js_trim(institution) if isinstance(institution, str) else None
        if bank:
            banks[bank_key(bank)] = bank
        else:
            unknown_banks.add(key)
        currencies.setdefault(_text(_get(row, 'currency')), _get(row, 'currency'))
        day = payment_day(row)
        if day:
            first = day if first is None or day < first else first
            last = day if last is None or day > last else last
        else:
            undated += 1
        name = _counterparty_name(row)
        if not (isinstance(name, str) and _js_trim(name)):
            unidentified += 1
    return {
        'accounts': [{'id': a['id'], 'label': a['label'], 'currencies': list(a['currencies'].values())}
                     for a in accounts.values()],
        'banks': list(banks.values()),
        'currencies': list(currencies.values()),
        'first': first,
        'last': last,
        'undated': undated,
        'unknown_banks': len(unknown_banks),
        'unidentified_counterparties': unidentified,
    }


def payment_totals(rows) -> dict:
    """PaymentTotals (no known accounts): per currency and account type, in the order first met, money in and
    out, payments and accounts; payments that cannot be totalled; the inventory line above them."""
    groups: dict = {}
    unreadable = 0
    for row in rows:
        amount = amount_of(row)
        if amount is None:
            unreadable += 1
            continue
        group = payment_group(row)
        total = groups.setdefault(group, {'credit': 0, 'debit': 0, 'count': 0, 'accounts': set()})
        total[_get(row, 'direction')] += amount
        total['count'] += 1
        total['accounts'].add(_text(_account_id(row)))
    return {
        'payments': len(rows),
        'inventory': payment_inventory(rows),
        'groups': [{'group': group, 'credit': str(t['credit']), 'debit': str(t['debit']), 'count': t['count'],
                    'accounts': len(t['accounts'])} for group, t in groups.items()],
        'unreadable': unreadable,
    }


def _total(rows) -> str | None:
    """MoneyConnections' totalLabel: the sum in minor units, or None ("Amount needs checking") when any amount is
    not a whole number of minor units."""
    total = 0
    for row in rows:
        amount = minor_amount(_get(row, 'amount_minor'))
        if amount is None:
            return None
        total += amount
    return str(total)


def unidentified_payment(row) -> dict | None:
    """unidentifiedPayment: why a payment has no counterparty name, or None when it has one."""
    side_field = 'from_name' if _get(row, 'direction') == 'credit' else 'to_name'
    # party(row, side) for the counterparty side is never the account's own side, so its key is "unknown:..."
    # exactly when the payment has no counterparty link and no name after trimming and folding spaces.
    value = _coalesce(_get(row, side_field), _get(row, 'counterparty_raw'))
    name = re.sub(_SPACE + '+', ' ', _js_trim(value if _truthy(value) else ''))
    if _truthy(_get(row, 'counterparty_link')) or name:
        return None
    if _nested(row, 'label_sources', side_field, 'source') == 'investigator':
        return {'kind': 'cleared', 'label': 'Name cleared during review',
                'reason': 'An investigator left this name blank. Open the payment to review or add a name.'}
    known = _nested(row, 'label_sources', side_field)
    known = known if isinstance(known, dict) else None
    if known is not None and known.get('source') == 'missing' and _truthy(known.get('reason', _MISSING)):
        return {'kind': 'reason:%s' % _text(known['reason']), 'label': known['reason'],
                'reason': _or(known.get('explanation', _MISSING), known['reason'])}
    description = _or(_get(row, 'description'), '')
    description = _COMBINING.sub('', unicodedata.normalize('NFKD', _text(description))).upper()
    if _get(row, 'direction') == 'credit' and _RETURNED.search(description):
        return {'kind': 'returned', 'label': 'Returned transfers',
                'reason': 'The description records a returned transfer. It does not name the original beneficiary; '
                          'compare its reference with the outgoing payment.'}
    if _TAX.search(description):
        return {'kind': 'tax', 'label': 'Tax entries',
                'reason': 'The description identifies tax withheld or tax on a commission, without a named '
                          'recipient.'}
    if _FOREIGN.search(description):
        return {'kind': 'foreign', 'label': 'Foreign payment orders',
                'reason': 'The description records a foreign payment order. Open its reference and original '
                          'statement to identify the counterparty.'}
    if _THIRD_PARTY.search(description):
        return {'kind': 'third-party', 'label': 'Transfers to third parties',
                'reason': 'The description records a transfer to a third party, without naming the recipient. Its '
                          'payment wording and reference remain available.'}
    if _SENT.search(description):
        return {'kind': 'sent', 'label': 'Bank transfers with no named recipient',
                'reason': 'The description identifies the transfer route or bank, but no beneficiary name. A bank '
                          'name alone is not treated as the recipient.'}
    if (_get(row, 'account_type') == 'credit_card' and _get(row, 'direction') == 'credit'
            and _CARD_PAYMENT.search(description)):
        return {'kind': 'card-payment', 'label': 'Card payments with no named funding account',
                'reason': 'The payment reduces card debt. The description does not identify the person or account '
                          'that funded it.'}
    return {'kind': 'unidentified', 'label': 'Other payments with no identified name',
            'reason': 'No counterparty name is currently recorded. Open the payment to check its description and '
                      'statement, or add a name.'}


def _profiles(rows) -> dict:
    """paymentProfiles (no account directory), as the names and payments of each "name" and "account" profile in
    the order first met. Each profile keeps its payments by key, first occurrence position, last value."""
    groups: dict = {}

    def ensure(key, name, kind):
        group = groups.get(key)
        if group is None:
            group = groups[key] = {'name': name, 'kind': kind, 'rows': {}}
        return group

    for row in rows:
        account_id = _account_id(row)
        own = ensure('account:%s' % _text(account_id),
                     _or(_get(row, 'canonical_account_label'), _get(row, 'account_label'), 'Account name not recorded'),
                     'account')
        own['rows'][_text(_get(row, 'key'))] = row
        name = _counterparty_name(row)
        link = _get(row, 'counterparty_link')
        if _truthy(link):
            kind = _nested(link, 'kind')
            linked = _nested(link, 'id')
            ensure('%s:%s' % ('owner' if kind == 'party' else 'account', _text(linked)),
                   _or(_nested(link, 'label'), name, 'Name not recorded'), 'owner' if kind == 'party' else 'account')
        else:
            ensure('name:%s' % _text(_coalesce(name, '')),
                   name if isinstance(name, str) and _js_trim(name) else 'Name not recorded', 'name'
                   )['rows'][_text(_get(row, 'key'))] = row
    return groups


def money_connections(rows) -> dict:
    """MoneyConnections, for every currency and account type the payments have (the browser sorts the groups and
    chooses one): the money in and out, the names that paid in or were paid (in the order first met; the page shows
    six at a time), the accounts in the case and the payments without an identified counterparty, each with the keys
    of its payments."""
    names = [(key, p) for key, p in _profiles([row for row in rows if unidentified_payment(row) is None]).items()
             if p['kind'] == 'name']
    accounts = [(key, p) for key, p in _profiles(rows).items() if p['kind'] == 'account']
    by_group: dict = {}
    for row in rows:
        by_group.setdefault(payment_group(row), []).append(row)
    groups = []
    for group, members in by_group.items():
        def side(payments, field):
            return {'keys': [row.get('key') for row in payments], 'total': _total(payments),
                    'suggested': any(_nested(row, 'label_sources', field, 'source') == 'description'
                                     for row in payments)}
        visible = []
        for key, profile in names:
            mine = [row for row in profile['rows'].values() if payment_group(row) == group]
            if not mine:
                continue
            visible.append({
                'id': key, 'name': profile['name'],
                'credit': side([row for row in mine if _get(row, 'direction') == 'credit'], 'from_name'),
                'debit': side([row for row in mine if _get(row, 'direction') == 'debit'], 'to_name'),
            })
        unnamed: dict = {}
        for row in members:
            context = unidentified_payment(row)
            if context is None:
                continue
            item = unnamed.setdefault('%s:%s' % (_text(_get(row, 'direction')), context['kind']),
                                      {**context, 'direction': _get(row, 'direction'), 'rows': []})
            item['rows'].append(row)
        groups.append({
            'group': group,
            'credit_total': _total([row for row in members if _get(row, 'direction') == 'credit']),
            'debit_total': _total([row for row in members if _get(row, 'direction') == 'debit']),
            'names': visible,
            'accounts': [{'id': key, 'name': profile['name'],
                          'keys': [row.get('key') for row in profile['rows'].values() if payment_group(row) == group]}
                         for key, profile in accounts
                         if any(payment_group(row) == group for row in profile['rows'].values())],
            'unnamed': [{'direction': item['direction'], 'kind': item['kind'], 'label': item['label'],
                         'reason': item['reason'], 'keys': [row.get('key') for row in item['rows']],
                         'total': _total(item['rows'])} for item in unnamed.values()],
        })
    return {'payments': len(rows), 'groups': groups}


def _js_compare(a: str, b: str) -> int:
    """String comparison for the payment keys and days nearbyPayments orders by (localeCompare). Keys and days are
    ASCII letters, digits and hyphens, where localeCompare and code order agree."""
    return (a > b) - (a < b)


def _js_number(value):
    """The number JavaScript's subtraction uses for a row position: null is 0; None for NaN (missing, text)."""
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    return value if isinstance(value, (int, float)) and value == value else None


def nearby_payments(rows, maximum_days: int = 7) -> dict:
    """nearbyPayments: per account and currency (credit cards and undated payments left out), each payment in
    followed by the account's next payment out within ``maximum_days``, ordered by the day money came in. Returns
    how many pairs and the keys of their payments in the order the page lists them (each once)."""
    accounts: dict = {}
    for row in rows:
        if _get(row, 'account_type') == 'credit_card' or not payment_day(row):
            continue
        accounts.setdefault('%s:%s' % (_text(_account_id(row)), _text(_get(row, 'currency'))), []).append(row)

    def order(a, b):
        by_day = _js_compare(payment_day(a), payment_day(b))
        if by_day:
            return by_day
        # a.row_index - b.row_index: null counts as 0; anything else not a number gives NaN, which falls through.
        left, right = (_js_number(_get(row, 'row_index')) for row in (a, b))
        if left is not None and right is not None and left != right:
            return -1 if left < right else 1
        return _js_compare(_text(_get(a, 'key')), _text(_get(b, 'key')))

    pairs = []
    for group in accounts.values():
        ordered = sorted(group, key=functools.cmp_to_key(order))
        for index in range(1, len(ordered)):
            incoming, outgoing = ordered[index - 1], ordered[index]
            if _get(incoming, 'direction') != 'credit' or _get(outgoing, 'direction') != 'debit':
                continue
            days = (datetime.date.fromisoformat(payment_day(outgoing))
                    - datetime.date.fromisoformat(payment_day(incoming))).days
            credit = minor_amount(_get(incoming, 'amount_minor'))
            debit = minor_amount(_get(outgoing, 'amount_minor'))
            if days <= maximum_days and credit is not None and debit is not None and credit >= 0 and debit >= 0:
                pairs.append((incoming, outgoing))
    # The pairs in the order of the day money came in (a stable sort, as the page's).
    pairs.sort(key=functools.cmp_to_key(lambda a, b: _js_compare(payment_day(a[0]), payment_day(b[0]))))
    keys: dict = {}
    for incoming, outgoing in pairs:
        keys.setdefault(_text(_get(incoming, 'key')), incoming.get('key'))
        keys.setdefault(_text(_get(outgoing, 'key')), outgoing.get('key'))
    return {'pairs': len(pairs), 'keys': list(keys.values())}


def overview_panels(transactions, case_id: str, categories) -> dict:
    """The Overview's lower panels over the rows the page would use: the ledger's rows when the answer is complete
    (this case's, unique keys), kept to the chosen categories (none chosen: all), as overview_totals does."""
    chosen = list(dict.fromkeys(c for c in categories if isinstance(c, str) and c))
    complete = (len({row.get('key') for row in transactions}) == len(transactions)
                and all(row.get('case_id') == case_id for row in transactions))
    rows = [row for row in transactions if not chosen or category_name(row) in chosen] if complete else []
    return {
        'complete': complete,
        'categories': chosen,
        'totals': payment_totals(rows),
        'connections': money_connections(rows),
        'comparisons': nearby_payments(rows),
    }
