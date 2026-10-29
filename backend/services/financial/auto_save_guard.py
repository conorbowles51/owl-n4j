"""What the System must prove before it saves a statement on its own (fin-queue3, L1 and 0b).

A statement that balances is not thereby right: balances balance in any
currency, under any holder and any account number. Before the automatic save
(``queue_save``) imports a statement no person has looked at, every fact a
balance cannot prove has to be proven another way; a statement for which one
cannot be is held for a person with one plain sentence saying what to check.
A person's own saves are never held by it: a person looked at the page.

Checks, each from facts already recorded:

* currency: a currency the page prints for this statement's own section
  (Monex prints each section's currency in its 'RESUMEN CUENTA' heading and
  in 'MOVIMIENTOS DE <mes> EN <moneda>') must be the saved one; a currency the
  System filled as the case's usual one (``field_proposals.CASE_CURRENCY``,
  not printed) saves only when the file's name and the pages both name it;
* holder: a holder read from the address lines (a street, colonia, CP) is
  not a holder;
* chain: the saved statements of the same account and currency next to these
  dates (at most ``CHAIN_DAYS`` apart) must close where this one opens and
  open where it closes; the same amount with the opposite sign leaves the
  sign unproven;
* account number: a number one digit off another account of the same bank and
  currency whose statements never share a month with this one, and whose
  balances continue straight into this one, is most likely misread.

Reverse: ``LOUPE_FINANCIAL_AUTO_SAVE_GUARD=0`` (the automatic save checks only
reconciliation, as before).
"""
import os
import re
import unicodedata
from dataclasses import dataclass, replace
from functools import lru_cache
from datetime import date

ENABLED = os.environ.get('LOUPE_FINANCIAL_AUTO_SAVE_GUARD', '1').strip().lower() not in ('0', 'false', 'off', 'no')
LEDGER_SIGN = os.environ.get('LOUPE_FINANCIAL_GUARD_LEDGER_SIGN', '1') != '0'
SAVED_TWICE_BY_TYPE = os.environ.get('LOUPE_FINANCIAL_SAVED_TWICE_BY_TYPE', '1') != '0'
# The chain compares a statement with saved neighbours of its own account type only, when the ledger already
# holds that type under its number: a checking account and a checking line of credit printing the same last
# digits ('3701') are two saved accounts, and the line of credit's periods were held as not continuing the
# checking account's balances (Navy Federal, 11 periods). A type the number has never been saved as compares
# with every type, as before (a savings statement read with its checking account's number stays held).
CHAIN_BY_TYPE = os.environ.get('LOUPE_FINANCIAL_GUARD_CHAIN_BY_TYPE', '1') != '0'
CHAIN_DAYS = 5


def enabled():
    return ENABLED


def _fold(text):
    text = unicodedata.normalize('NFKD', str(text or '').upper())
    return ' '.join(''.join(c for c in text if not unicodedata.combining(c)).split())


# -- currency printed for the statement's own section --------------------------------------------------------------
_SECTION_NAMES = {'EURO': 'EUR', 'EUROS': 'EUR', 'DOLAR AMERICANO': 'USD', 'DOLARES AMERICANOS': 'USD',
                  'PESO MEXICANO': 'MXN', 'PESOS MEXICANOS': 'MXN', 'YEN JAPONES': 'JPY', 'YENES JAPONESES': 'JPY'}
_SECTION_NAME = '(' + '|'.join(sorted(map(re.escape, _SECTION_NAMES), key=len, reverse=True)) + ')'
_SUMMARY_HEADING = re.compile(r'^(?:CUENTA )?RESUMEN (?:DE )?CUENTA$')
# 'RESUMEN DIVISAS | PESO MEXICANO | AL 31 DICIEMBRE 2025': the currency the summary page is in.
_DIVISAS = re.compile(r'^RESUMEN DIVISAS ' + '(' + '|'.join(sorted(map(re.escape, _SECTION_NAMES), key=len, reverse=True)) + r')(?: AL \d{1,2} .*)?$')
# 'EURO | AL 31 MAYO 2025' right under the heading: the section's currency.
_SUMMARY_CURRENCY = re.compile('^' + _SECTION_NAME + r'(?: AL \d{1,2} .*)?$')
_MOVEMENTS = re.compile(r'^MOVIMIENTOS DE [A-Z]+ EN ' + _SECTION_NAME + '$')


def section_currencies(sources):
    """{code: first page} of the currencies this statement's own section headings print.

    Only headings: a glossary or exchange-rate table naming every currency
    (Monex prints one on the same pages) is not read.
    """
    found = {}
    for source in sources or ():
        rows = [[_fold(cell.get('expected_text')) for cell in row.get('cells') or ()] for row in source.get('rows') or ()]
        for index, cells in enumerate(rows):
            joined = ' '.join(c for c in cells if c)
            code = None
            if (match := _MOVEMENTS.match(joined) or _DIVISAS.match(joined)):
                code = _SECTION_NAMES[match[1]]
            elif _SUMMARY_HEADING.match(joined) and index + 1 < len(rows):
                after = ' '.join(c for c in rows[index + 1] if c)
                if (match := _SUMMARY_CURRENCY.match(after)):
                    code = _SECTION_NAMES[match[1]]
            if code and code not in found:
                found[code] = source.get('page_number')
    return found


# -- holder ------------------------------------------------------------------------------------------------------------
_ADDRESS = re.compile(r'(?<![A-Z])(CALLE|COL\.|COLONIA|C\.? ?P\.? ?\d{5}|AV\.|AVENIDA|SECCION|POLANCO|NO\. ?\d|DELEGACION|'
                      r'MUNICIPIO|ALCALDIA|PISO \d|LOMAS DE|BLVD|BOULEVARD|CDMX|MIGUEL HIDALGO|CIUDAD DE MEXICO|'
                      r'CUAUHTEMOC|BENITO JUAREZ)(?![A-Z])')


def holder_is_address(holder):
    """The holder read is an address line (street, colonia, postcode, borough), not a name."""
    return bool(_ADDRESS.search(_fold(holder)))


# -- the saved ledger next to a statement --------------------------------------------------------------------------
@dataclass(frozen=True)
class SavedPeriod:
    account: str
    institution: str
    currency: str
    start: date
    end: date
    opening: int | None
    closing: int | None
    source_document_id: str = ''
    kind: str = ''  # the account type, when known (saved ledger); '' compares with every type


def account_digits(text):
    return re.sub(r'\D', '', str(text or ''))


# Words a bank's printed or typed name carries that do not tell banks apart ('BANCO MONEX' and 'Monex' are one bank).
_BANK_WORDS = frozenset({'BANCO', 'BANK', 'THE', 'GRUPO', 'FINANCIERO', 'CASA', 'DE', 'BOLSA', 'S.A.', 'SA', 'MEXICO'})


def _bank(text):
    # Compared for every pair of saved periods (misread_account, chain_problem): the same few bank names are
    # folded once each, not once per pair (d5b330d1: 22 s of a 67 s queue build).
    return _bank_of(text) if text is None or isinstance(text, str) else _bank_of.__wrapped__(text)


@lru_cache(maxsize=4096)
def _bank_of(text):
    words = [word.strip('.,') for word in _fold(text).split()]
    return next((word for word in words if word and word not in _BANK_WORDS), words[0] if words else '')


def _iso(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _money(minor):
    sign = '-' if minor < 0 else ''
    whole, cents = divmod(abs(minor), 100)
    return f'{sign}{whole:,}.{cents:02d}'


def _month(day):
    return day.strftime('%b %Y')


def load_ledger(session, case_id):
    """Every admitted statement period of the case, as the guard compares them."""
    from sqlalchemy import select
    from postgres.models.financial import (FinancialAccount as Account, FinancialSourceDocument as Source,
                                           FinancialStatementPeriod as Period)
    rows = session.execute(select(Account.identifier_normalised, Account.institution_name, Period.currency,
                                  Period.period_start, Period.period_end, Period.opening_balance_minor,
                                  Period.closing_balance_minor, Period.source_document_id, Account.account_type)
                           .join(Account, Account.id == Period.account_id)
                           .join(Source, Source.id == Period.source_document_id)
                           .where(Period.case_id == case_id, Source.status == 'admitted')).all()
    return [SavedPeriod(account_digits(a), i or '', (c or '').upper(), s, e, o, cl, str(d),
                        (kind or '') if CHAIN_BY_TYPE else '')
            for a, i, c, s, e, o, cl, d, kind in rows if s and e]


def _seam(prior_closing, next_opening):
    if prior_closing is None or next_opening is None or prior_closing == next_opening:
        return 'agrees'
    if prior_closing == -next_opening:
        return 'sign'
    return 'breaks'


def chain_problem(statement, ledger):
    """A sentence when a saved neighbour of the same account and currency does not continue into this statement."""
    near = [p for p in ledger if p.account == statement.account and p.currency == statement.currency
            and _bank(p.institution) == _bank(statement.institution) and p.source_document_id != statement.source_document_id
            and (not p.kind or not statement.kind or p.kind == statement.kind)]
    before = [p for p in near if 0 <= (statement.start - p.end).days <= CHAIN_DAYS]
    after = [p for p in near if 0 <= (p.start - statement.end).days <= CHAIN_DAYS]
    for prior in sorted(before, key=lambda p: p.end, reverse=True)[:1]:
        seam = _seam(prior.closing, statement.opening)
        if seam == 'sign':
            return ('sign', f'The opening balance {_money(statement.opening)} has the opposite sign of the '
                    f'{_month(prior.start)} statement\'s closing {_money(prior.closing)}: check which sign the page prints')
        if seam == 'breaks':
            return ('balance', f'The opening balance {_money(statement.opening)} does not continue the saved '
                    f'{_month(prior.start)} statement of this account, which closes at {_money(prior.closing)}: '
                    'check both pages')
    for following in sorted(after, key=lambda p: p.start)[:1]:
        seam = _seam(statement.closing, following.opening)
        if seam == 'sign':
            return ('sign', f'The closing balance {_money(statement.closing)} has the opposite sign of the '
                    f'{_month(following.start)} statement\'s opening {_money(following.opening)}: check which sign '
                    'the page prints')
        if seam == 'breaks':
            return ('balance', f'The closing balance {_money(statement.closing)} does not carry into the saved '
                    f'{_month(following.start)} statement of this account, which opens at {_money(following.opening)}: '
                    'check both pages')
    return None


def _months(start, end):
    months, (y, m) = set(), (start.year, start.month)
    while (y, m) <= (end.year, end.month):
        months.add((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


def misread_account(statement, ledger):
    """The account number this one is most likely a misreading of, or None.

    One digit off an account of the same bank and currency, never sharing a
    month with any statement saved under this number (or this one), and a
    balance of one continuing exactly into the other within ``CHAIN_DAYS``.
    """
    if len(statement.account) < 6:
        return None
    mine = [p for p in ledger if p.account == statement.account and p.currency == statement.currency
            and p.source_document_id != statement.source_document_id] + [statement]
    my_months = set().union(*(_months(p.start, p.end) for p in mine))
    others = {}
    for p in ledger:
        if (p.currency == statement.currency and _bank(p.institution) == _bank(statement.institution)
                and len(p.account) == len(statement.account) and p.account != statement.account
                and sum(a != b for a, b in zip(p.account, statement.account)) == 1):
            others.setdefault(p.account, []).append(p)
    for number, theirs in sorted(others.items()):
        if len(theirs) < len(mine) - 1:
            continue  # The other number is the odd one out: its statements are the ones to check.
        if my_months & set().union(*(_months(p.start, p.end) for p in theirs)):
            continue  # Both numbers have statements in the same month: two real accounts.
        for a in mine:
            for b in theirs:
                if ((0 <= (a.start - b.end).days <= CHAIN_DAYS and b.closing is not None and b.closing == a.opening)
                        or (0 <= (b.start - a.end).days <= CHAIN_DAYS and a.closing is not None and a.closing == b.opening)):
                    return number
    return None


# -- the decision ------------------------------------------------------------------------------------------------------
CASE_DEFAULT_LABEL = "currency assumed: case's usual (not printed)"


def system_currency_basis(file, statement_key, currency):
    """The basis the System recorded when it filled this statement's currency, or ''."""
    from services.financial.field_proposals import SYSTEM_NAME
    for entry in reversed(((file.metadata_ or {}) if file is not None else {}).get('financial_account_detail_history') or []):
        if (entry.get('statement_id') or '') != (statement_key or '') or 'currency' not in (entry.get('after') or {}):
            continue
        if (entry['after'].get('currency') or '').upper() != (currency or '').upper():
            return ''
        return entry.get('basis') or '' if (entry.get('actor') or {}).get('name') == SYSTEM_NAME else ''
    return ''


_FILE_CODES = (('USD', re.compile(r'(?<![A-Z])(USD|DLLS?|DLS|DOLARES|DOLAR)(?![A-Z])')),
               ('EUR', re.compile(r'(?<![A-Z])(EUR|EUROS?)(?![A-Z])')),
               ('MXN', re.compile(r'(?<![A-Z])(MXN|MXP|PESOS)(?![A-Z])')))


def file_name_currency(filename):
    codes = {code for code, rx in _FILE_CODES if rx.search(_fold(filename))}
    return next(iter(codes)) if len(codes) == 1 else ''


def statement_of(summary, source_document_id=''):
    """The statement as the guard compares it, from its projected summary (None without dates)."""
    start, end = _iso(summary.get('period_start')), _iso(summary.get('period_end'))
    if not start or not end:
        return None
    calculation = (summary.get('admission') or {}).get('calculation') or {}
    closing = calculation.get('printed_closing_minor')
    if closing is None:
        closing = calculation.get('calculated_closing_minor')
    # A card prints the amount owed; the ledger stores it negative (asset arithmetic). Compared as printed, every
    # card statement looked like the opposite sign of its saved neighbours (Credit One 1930, 18 periods held).
    sign = -1 if LEDGER_SIGN and calculation.get('balance_convention') == 'liability_owed' else 1
    opening, closing = _int(calculation.get('opening_minor')), _int(closing)
    return SavedPeriod(account_digits(summary.get('account')), summary.get('institution') or '',
                       (summary.get('currency') or '').upper(), start, end,
                       None if opening is None else sign * opening, None if closing is None else sign * closing,
                       source_document_id, (summary.get('account_type') or '') if CHAIN_BY_TYPE else '')


def _account_history(summary, ledger):
    """The currencies of the saved statements of this statement's account at this bank (its other periods)."""
    number, bank = account_digits(summary.get('account')), _bank(summary.get('institution'))
    if len(number) < 6:
        return set()
    return {p.currency for p in ledger if p.account == number and _bank(p.institution) == bank}


def hold(summary, *, ledger, currency_basis='', filename='', named_currencies=()):
    """(reason, sentence) holding a statement from the automatic save, or None when every check is proven.

    ``summary`` is the statement's projected summary (``import_batches.assess``,
    with ``section_currencies``); ``ledger`` the case's saved periods
    (``load_ledger``); ``currency_basis`` the System's recorded basis when it
    filled the currency; ``named_currencies`` the currencies the pages name.
    """
    currency = (summary.get('currency') or '').upper()
    sections = summary.get('section_currencies') or {}
    # Pages holding several sections (a summary page and each currency's own) settle nothing here.
    if len(sections) == 1 and currency not in sections:
        named = ', '.join(sorted(sections))
        page = min(sections.values(), key=lambda p: p if isinstance(p, int) else 10 ** 6)
        return ('currency', f'The page prints this section\'s currency as {named}'
                + (f' (page {page})' if isinstance(page, int) else '') + f', but it would be saved in {currency}: '
                'check the currency')
    if CASE_DEFAULT_LABEL in (currency_basis or '') and not (
            file_name_currency(filename) == currency and (currency in {str(c).upper() for c in named_currencies}
                                                          or _account_history(summary, ledger) == {currency})):
        # The file name alone is not proof; with the pages naming the currency, or with every saved statement of
        # this account in that currency, two independent signals agree (a scan whose 'MONEDA NACIONAL' line the
        # text reading lost: Santander 65-50462403-4 Dec 2021, BNB2 sample #52).
        return ('currency', f'No currency is printed for this statement; {currency} is only the case\'s usual '
                'currency: check the currency on the page')
    if holder_is_address(summary.get('holder')):
        return ('holder', f'The account holder read, "{summary.get("holder")}", is an address line: '
                'check the holder printed on the page')
    statement = statement_of(summary)
    if statement is None or not statement.account:
        return None
    if statement.kind and not any(p.kind == statement.kind and p.account == statement.account
                                  and p.currency == statement.currency
                                  and _bank(p.institution) == _bank(statement.institution) for p in ledger):
        statement = replace(statement, kind='')
    problem = chain_problem(statement, ledger)
    if problem:
        return problem
    number = misread_account(statement, ledger)
    if number:
        return ('account', f'The account number {summary.get("account")} is one digit off account {number} at the '
                'same bank, whose balances continue straight into this statement and which never has a statement '
                'in the same month: check the number printed on the page')
    return None


# -- saved statements: the same checks on what is already in the ledger (fin-queue3 0b / L28) ----------------------
def saved_checks(session, case_id):
    """{(file sha256, statement key): (reason, sentence)} for saved statements a check finds wrong or unproven.

    The checks that need only the saved ledger: holder read from an address line, a balance that does not carry
    from or into a saved neighbour (or carries with the opposite sign), the same account, currency and dates
    saved twice, and an account number one digit off an account whose balances continue
    into it. A saved statement is never changed by this: it is listed for a person with the sentence.
    """
    from collections import defaultdict
    from sqlalchemy import select
    from postgres.models.financial import (FinancialAccount as Account, FinancialSourceDocument as Source,
                                           FinancialStatementPeriod as Period)
    rows = session.execute(select(Account.account_type, Account.identifier_normalised, Account.institution_name, Account.holder_name,
                                  Period.currency, Period.period_start, Period.period_end, Period.opening_balance_minor,
                                  Period.closing_balance_minor, Period.source_document_id, Source.sha256_at_ingestion,
                                  Source.metadata_['statement_import_statement_id'].as_string())
                           .join(Account, Account.id == Period.account_id)
                           .join(Source, Source.id == Period.source_document_id)
                           .where(Period.case_id == case_id, Source.status == 'admitted',
                                  Source.metadata_['financial_import_removal'].as_string().is_(None))).all()
    return ledger_checks(rows)


def ledger_checks(rows):
    """``saved_checks`` on its rows: (account type, number, bank, holder, currency, start, end, opening, closing,
    document, file sha256, statement key). Saved twice means the same account, of the same type, currency and
    dates: one statement can print two products whose numbers end alike (Navy Federal 'EveryDay Checking 3701'
    and 'Checking Line of Credit 3701'), saved as two accounts, a deposit account and a card; they are not copies.
    Switch: LOUPE_FINANCIAL_SAVED_TWICE_BY_TYPE (default on)."""
    from collections import defaultdict
    ledger, scope, holders, types = [], {}, {}, {}
    for kind, number, institution, holder, currency, start, end, opening, closing, document, sha, key in rows:
        if not (start and end):
            continue
        period = SavedPeriod(account_digits(number), institution or '', (currency or '').upper(), start, end,
                             opening, closing, str(document), (kind or '') if SAVED_TWICE_BY_TYPE else '')
        ledger.append(period)
        scope[period] = (sha, key or '')
        holders[period] = holder or ''
        types[period] = period.kind
    twice = defaultdict(set)
    same = lambda period: (period.account, types[period], _bank(period.institution), period.currency, period.start,
                           period.end)
    for period in ledger:
        twice[same(period)].add(period.source_document_id)
    found = {}
    for period in ledger:
        if holder_is_address(holders[period]):
            result = ('holder', f'The account holder saved, "{holders[period]}", is an address line: check the holder '
                      'printed on the page')
        elif period.account and len(twice[same(period)]) > 1:
            result = ('copy', f'This account, currency and period ({_month(period.start)}) is saved more than once: '
                      'check whether one is a copy of the other or belongs to another currency')
        else:
            result = (period.account and (chain_problem(period, ledger) or (
                lambda number: number and ('account', f'The account number is one digit off account {number} at the '
                                           'same bank, whose balances continue straight into this statement: check the '
                                           'number printed on the page'))(misread_account(period, ledger)))) or None
        if result and scope[period] not in found:
            found[scope[period]] = result
    return found
