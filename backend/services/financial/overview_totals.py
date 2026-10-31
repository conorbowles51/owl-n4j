"""The Financial Overview's headline figures, computed on the server over the rows ``/ledger`` answers with.

Each figure is the browser's own calculation over the same rows, so the page shows the same numbers whether it adds
them up itself or reads them from here (frontend: InvestigatorOverview, useInvestigatorPayments, groupMoney,
paymentDay, categoryName, matchesCategories, isCompleteLedger). Ordering that depends on the browser's
language-aware text order (currencies with equal counts) is left to the browser: the currencies are returned
unordered and the page orders them as it always has.
"""
from __future__ import annotations

import datetime
import re

STATEMENT_END_ONLY = 'statement_end_ordering_only'
_DAY = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}')
# JavaScript's String.prototype.trim (what BigInt(text) strips): ASCII whitespace, NBSP, the Unicode space
# separators, line/paragraph separators and the byte-order mark.
_JS_SPACE = '\t\n\x0b\x0c\r \xa0            ' \
    '    　﻿'


def category_name(row) -> str:
    """categoryName: the row's category, or "Uncategorized" when it has none."""
    return row.get('category') or 'Uncategorized'


def payment_day(row) -> str | None:
    """paymentDay: the ordering date's day when it is a real calendar day and the row's date is not only its
    statement's end date."""
    if row.get('ordering_date_context') == STATEMENT_END_ONLY:
        return None
    value = row.get('ordering_date')
    date = value[:10] if isinstance(value, str) else None
    if not date or not _DAY.fullmatch(date):
        return None
    try:
        parsed = datetime.date.fromisoformat(date)
    except ValueError:
        return None
    # new Date(...).toISOString() covers years 0000-9999 for this pattern; fromisoformat refuses year 0000.
    return date if parsed.isoformat() == date else None


def account_key(row, missing=None):
    """The account a payment counts under: the account its records were joined into by a saved account
    consolidation (``canonical_account_id``; account_consolidation.save_consolidation is its only writer, and
    undo restores the previous value), else the payment's own account. JavaScript ``canonical_account_id ||
    account_id``; ``missing`` stands for an absent ``account_id``. Every account count on the Overview uses it, so
    two account records joined into one are one account everywhere on the page."""
    return row.get('canonical_account_id') or row.get('account_id', missing)


def amount(row) -> int:
    """groupMoney's amount: BigInt(amount_minor), or 0 when BigInt refuses it (the ledger sends the integer as
    text; the other branches follow BigInt for any other value)."""
    value = row.get('amount_minor')
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else 0
    if not isinstance(value, str):
        return 0  # BigInt(null) and BigInt(undefined) throw
    text = value.strip(_JS_SPACE)
    if text == '':
        return 0  # BigInt("") is 0n
    if re.fullmatch(r'[+-]?[0-9]+', text, re.ASCII):
        return int(text)
    for prefix, digits, base in (('0x', '0-9a-f', 16), ('0o', '0-7', 8), ('0b', '01', 2)):
        if re.fullmatch('%s[%s]+' % (prefix, digits), text, re.ASCII | re.IGNORECASE):
            return int(text[2:], base)
    return 0


def overview_totals(transactions, case_id: str, categories) -> dict:
    """The figures the Overview's top card shows, over the rows the page would use.

    The page uses the ledger's rows only when the answer is complete (isCompleteLedger: this case's, unique keys,
    total equal to its row count) and then keeps the rows in the chosen categories (matchesCategories; none chosen:
    all). ``currencies``: per currency its payments and money in (direction credit) and out (anything else), in
    minor units as text, unordered."""
    chosen = list(dict.fromkeys(c for c in categories if isinstance(c, str) and c))
    complete = (len({row.get('key') for row in transactions}) == len(transactions)
                and all(row.get('case_id') == case_id for row in transactions))
    rows = [row for row in transactions if not chosen or category_name(row) in chosen] if complete else []
    currencies: dict = {}
    accounts = set()
    first = last = None
    unknown_dates = uncategorised = 0
    for row in rows:
        if row.get('ordering_date_context') == STATEMENT_END_ONLY:
            unknown_dates += 1
        if category_name(row) == 'Uncategorized':
            uncategorised += 1
        accounts.add(account_key(row))
        entry = currencies.setdefault(row.get('currency'), [0, 0, 0])
        entry[0] += 1
        entry[1 if row.get('direction') == 'credit' else 2] += amount(row)
        day = payment_day(row)
        if day is not None:
            first = day if first is None or day < first else first
            last = day if last is None or day > last else last
    return {
        'complete': complete,
        'categories': chosen,
        'payments': len(rows),
        'accounts': len(accounts),
        'unknown_dates': unknown_dates,
        'uncategorised': uncategorised,
        'first_day': first,
        'last_day': last,
        'currencies': [{'currency': code, 'payments': count, 'credit': str(credit), 'debit': str(debit)}
                       for code, (count, credit, debit) in currencies.items()],
    }
