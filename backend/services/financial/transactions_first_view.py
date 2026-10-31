"""The Transactions page's first view, computed on the server over the rows ``/ledger`` answers with.

With no filter, search, chosen category, account choice, judgement filter, selection or extra section, the page shows:
the money in, out and net per currency with each currency's payment count (TransactionsOverview, totals only), how
many payments are listed, how many of them a judgement call touches, how many have the other side not identified
(needsName) and how many carry a name read by a model that no person confirmed (needsConfirm), and one page of the
rows in the ledger's own order. This module works out exactly those figures, each with the browser's own rule over
the same rows (frontend: LedgerRowBrowser, TransactionsOverview, groupMoney, activityAmount, payment-naming,
judgementLookup), so the page can show them without downloading every payment (d5b330d1: 27,673 rows, 64 MB).

Anything else the page offers (filters, search, sorting, sections, CSV, selecting every row) still works from every
row, which the page loads when a person asks for it. Ordering that depends on the browser's language-aware text
order (currencies with equal counts) is left to the browser: currencies are returned in first-met order.
"""
from __future__ import annotations

import math
import re

from services.financial.overview_totals import _JS_SPACE

PAGE_SIZES = (25, 50, 100, 250)  # the table's "Rows per page" choices


class Unavailable(Exception):
    """The browser's own calculation would fail on these rows (BigInt refuses an amount): the page then reads every
    row as before, so whatever it does with such a row is unchanged."""


def js_bigint(value) -> int:
    """BigInt(value) for the values a ledger row's ``amount_minor`` can hold; raises Unavailable where BigInt throws."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        raise Unavailable('amount_minor is not an integer')
    if not isinstance(value, str):
        raise Unavailable('amount_minor is missing')
    text = value.strip(_JS_SPACE)
    if text == '':
        return 0
    if re.fullmatch(r'[+-]?[0-9]+', text, re.ASCII):
        # BigInt("+5") and BigInt("-5") parse; a sign before 0x/0o/0b does not.
        return int(text)
    for prefix, digits, base in (('0x', '0-9a-f', 16), ('0o', '0-7', 8), ('0b', '01', 2)):
        if re.fullmatch('%s[%s]+' % (prefix, digits), text, re.ASCII | re.IGNORECASE):
            return int(text[2:], base)
    raise Unavailable('amount_minor is not an integer')


def _js_text(value) -> str:
    """``(value ?? "").trim()`` for a name field (strings; anything else counts as text by its JSON form)."""
    if value is None:
        return ''
    if isinstance(value, str):
        return value.strip(_JS_SPACE)
    raise Unavailable('a name field is not text')


def _truthy(value) -> bool:
    """JavaScript truthiness of a JSON value."""
    if isinstance(value, dict) or isinstance(value, list):
        return True
    if isinstance(value, float) and math.isnan(value):
        return False
    return bool(value)


def _source(row, field):
    sources = row.get('label_sources')
    if not isinstance(sources, dict):
        return None
    entry = sources.get(field)
    return entry.get('source') if isinstance(entry, dict) else None


def other_side(row) -> str:
    """otherSide: who paid in for money in, else who was paid."""
    return 'from_name' if row.get('direction') == 'credit' else 'to_name'


def needs_name(row) -> bool:
    """needsName: nobody is named for the other side (no printed or suggested name and no person's label)."""
    field = other_side(row)
    if _truthy(row.get('counterparty_link')):
        return False
    if _source(row, field) == 'investigator':
        return False
    return not _js_text(row.get(field)) and not _js_text(row.get('counterparty_raw'))


def needs_confirm(row) -> bool:
    """needsConfirm: a name on the payment (either side) was read by a model and no person has confirmed it."""
    other = other_side(row)
    own = 'to_name' if other == 'from_name' else 'from_name'
    return any(_source(row, field) == 'model_reading' for field in (other, own))


def touched(row, judgement_map) -> bool:
    """judgementLookup(map)(row).length > 0: a current call on the payment, or on its whole statement."""
    known = {str(item.get('id')) for item in judgement_map.get('judgements') or []}
    return _touched(row, judgement_map, known)


def _touched(row, judgement_map, known) -> bool:
    if any(i in known for i in (judgement_map.get('transactions') or {}).get(row.get('key')) or ()):
        return True
    document = row.get('source_document_id')
    return bool(document) and any(i in known for i in (judgement_map.get('documents') or {}).get(document) or ())


def page_index(page: int, page_size: int, total: int) -> int:
    """The page the table shows: Math.min(page, Math.max(0, Math.ceil(total / pageSize) - 1))."""
    return min(page, max(0, math.ceil(total / page_size) - 1))


def first_view(transactions, judgement_map, page: int = 0, page_size: int = 50) -> dict:
    """The figures and the page of rows the default Transactions view shows, over ``transactions`` (the ledger's rows
    for the page's scope, in the ledger's order).

    ``currencies``: per currency (first-met order) its payments and money in (direction ``credit``) and out (anything
    else) as BigInt(amount_minor) sums in minor units, as text. ``touched``: payments with a current judgement call.
    ``rows``: the page ``page`` of ``page_size`` rows after clamping as the table clamps. Raises Unavailable where the
    browser's calculation would fail, so the page then reads every row."""
    known = {str(item.get('id')) for item in judgement_map.get('judgements') or []}
    currencies: dict = {}
    order = []
    unnamed = unconfirmed = hit = 0
    for row in transactions:
        amount = js_bigint(row.get('amount_minor'))
        code = row.get('currency')
        entry = currencies.get(code)
        if entry is None:
            entry = currencies[code] = dict(currency=code, count=0, credit=0, debit=0)
            order.append(code)
        entry['count'] += 1
        if row.get('direction') == 'credit':
            entry['credit'] += amount
        else:
            entry['debit'] += amount
        unnamed += needs_name(row)
        unconfirmed += needs_confirm(row)
        hit += _touched(row, judgement_map, known)
    total = len(transactions)
    index = page_index(page, page_size, total)
    return dict(
        total=total,
        page=index,
        page_size=page_size,
        rows=transactions[index * page_size:(index + 1) * page_size],
        currencies=[dict(currencies[code], credit=str(currencies[code]['credit']),
                         debit=str(currencies[code]['debit'])) for code in order],
        unnamed=unnamed,
        unconfirmed=unconfirmed,
        touched=hit,
    )
