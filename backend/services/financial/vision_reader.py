"""Page-image fallback reader for held bank statements (Neil, 2026-10-24).

A statement the rule readers could not prove stays held. When its file is
prepared again through the normal batch path (a recovery re-read or any new
preparation), this reader looks at the images of that statement's pages with
the AI workload ``financial_vision`` (OpenAI's vision model by default), page
by page, and asks for structured JSON only: the account sections printed on
each page, their header (bank, holder, account, currency, period), opening and
closing balances, printed totals and counts, and every payment row with its
printed running balance.

The reading is accepted only when it proves itself, all of:

* opening balance + every row = closing balance, to the cent;
* every printed running balance agrees with the rows before it;
* printed credit/debit totals and counts agree where printed;
* the period is complete and every row date lies inside it;
* printed page numbering shows no missing page;
* the header agrees with the rule reading wherever that read a value, and the
  account is one the case already has saved statements for, with the same
  holder, bank and currency;
* every payment the rule reading read cleanly appears in the image reading
  with the same amount and direction (the image never drops a payment the text
  shows), and every balance the rule reading read is the same.

It is then recorded as a System review of the statement (``save_review``, the
batch's own save), its rows marked "Read from page image, page N", the rule
reading's rows set aside with that reason (retained, never deleted). The
batch's normal assessment and admission then decide again, and the existing
automatic save saves it only when that finds nothing at all to check. A reading
that does not prove is not applied; the statement stays held exactly as it was,
with the reason recorded beside it.

Never: a statement with any investigator work (draft or saved review), a saved
or set-aside statement, a ready one, a document review, a fund statement.
Fails closed: switch off, no key, a provider without page-image support, an
API error, a timeout, a truncated or refused answer, or the case's cost cap
reached all leave the statement held. Each reading is stored on the evidence
file with its model, per-page tokens and cost, so a statement is read from its
images once per reading and model.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import select

log = logging.getLogger(__name__)


def _switch(name, default='1'):
    return os.environ.get(name, default).strip().lower() not in ('0', 'false', 'off', 'no', '')


def _number(name, default):
    try:
        return float(os.environ.get(name, '') or default)
    except ValueError:
        return float(default)


ENABLED = _switch('LOUPE_FINANCIAL_VISION_FALLBACK')
# Cases whose page images may be sent to the provider (comma-separated case ids). Sending a
# case's images needs its owner's approval, so a case not listed is never read; unset reads none.
APPROVED_CASES = frozenset(c.strip().lower() for c in os.environ.get('LOUPE_FINANCIAL_VISION_CASES', '').split(',') if c.strip())


def approved(case_id):
    return str(case_id).lower() in APPROVED_CASES
# Spend cap per case for one worker run (process lifetime); readings already
# stored are reused and cost nothing again.
CASE_BUDGET_USD = _number('LOUPE_FINANCIAL_VISION_CASE_BUDGET_USD', 30)
MAX_PAGES = int(_number('LOUPE_FINANCIAL_VISION_MAX_PAGES', 30))
PAGE_TIMEOUT_SECONDS = int(_number('LOUPE_FINANCIAL_VISION_TIMEOUT_SECONDS', 180))
IMAGE_WIDTH = int(_number('LOUPE_FINANCIAL_VISION_IMAGE_WIDTH', 1600))
STRIPS = int(_number('LOUPE_FINANCIAL_VISION_STRIPS', 3))
STRIP_OVERLAP = 0.06
SWEEP_SECONDS = _number('LOUPE_FINANCIAL_VISION_SWEEP_SECONDS', 240)
WORKLOAD = 'financial_vision'
VERSION = 'vision-reader-v1'
METADATA_KEY = 'financial_vision_reading'
MARK = 'vision_fallback'
SYSTEM_NAME = 'System'
SYSTEM_EMAIL = 'vision-reader@system.local'
ROW_REASON = 'Read from page image, page {page}.'
REPLACED_REASON = ('Set aside: the reading of the page images of this period reconciles exactly and replaces '
                   'the text reading, which is retained.')
CLAIM_SECONDS = 20 * 60
# A statement whose request fails this many times (for the same reading) is not requested again.
MAX_FAILURES = 3
# Reserved before each request: an answer cut short, refused or timed out is still billed.
RESERVE_TOKENS_PER_IMAGE = 1600
RESERVE_OUTPUT_TOKENS = 16000
GAVE_UP = 'The page images could not be read after several tries; the statement stays held.'
# Outcomes not attempted again for the same reading (failed, budget and unavailable are retried later).
FINAL = ('proved', 'not_proved', 'stale')
# USD per million tokens (input, output). Unknown models use the most expensive line.
# As Loupe's own pricing table (ai_pricing_rates, migration 20260722) for the 5.6 models.
PRICES = {'gpt-4o': (2.50, 10.00), 'gpt-4.1': (2.00, 8.00), 'gpt-5': (1.25, 10.00),
          'gpt-5.6-sol': (5.00, 30.00), 'gpt-5.6-terra': (2.50, 15.00), 'gpt-5.6-luna': (1.00, 6.00)}
FALLBACK_PRICE = (5.00, 30.00)

_spend = {}
_spend_lock = threading.Lock()


def price(model_id):
    override = (os.environ.get('LOUPE_FINANCIAL_VISION_PRICE_IN'), os.environ.get('LOUPE_FINANCIAL_VISION_PRICE_OUT'))
    if all(override):
        try:
            return float(override[0]), float(override[1])
        except ValueError:
            pass
    for prefix in sorted(PRICES, key=len, reverse=True):
        if model_id == prefix or model_id.startswith(prefix + '-'):
            return PRICES[prefix]
    return FALLBACK_PRICE


def cost_usd(model_id, usage):
    rate_in, rate_out = price(model_id)
    usage = usage or {}
    return round((usage.get('prompt_tokens') or 0) * rate_in / 1e6 + (usage.get('completion_tokens') or 0) * rate_out / 1e6, 6)


def spent(case_id):
    with _spend_lock:
        return _spend.get(str(case_id), 0.0)


def _add_spend(case_id, amount):
    with _spend_lock:
        _spend[str(case_id)] = _spend.get(str(case_id), 0.0) + amount


def _reserve(case_id, amount):
    """Count ``amount`` against the case's budget; False (nothing counted) when it would pass the budget."""
    with _spend_lock:
        if _spend.get(str(case_id), 0.0) + amount > CASE_BUDGET_USD:
            return False
        _spend[str(case_id)] = _spend.get(str(case_id), 0.0) + amount
        return True


# ---------------------------------------------------------------------------
# The request: one page image -> its account sections, schema-enforced
# ---------------------------------------------------------------------------

def _nullable(kind):
    return {'type': [kind, 'null']}


_ROW = {'type': 'object', 'additionalProperties': False,
        'required': ['date', 'description', 'amount', 'direction', 'balance_after', 'unreadable'],
        'properties': {
            'date': {'type': 'string', 'description': 'YYYY-MM-DD; the posting (operation) date printed for the row.'},
            'description': {'type': 'string'},
            'amount': {'type': 'string', 'description': 'Positive amount as printed, digits with a dot decimal separator, no thousands separators, e.g. 1234.56'},
            'direction': {'type': 'string', 'enum': ['credit', 'debit']},
            'balance_after': _nullable('string'),
            'unreadable': {'type': 'boolean'}}}
_SECTION = {'type': 'object', 'additionalProperties': False,
            'required': ['section_name', 'institution', 'holder', 'account_number', 'currency', 'currency_as_printed', 'period_start',
                         'period_end', 'opening_balance', 'closing_balance', 'total_credits', 'total_debits',
                         'count_credits', 'count_debits', 'rows', 'no_transactions_printed'],
            'properties': {
                'section_name': {'type': 'string', 'description': 'The printed heading of this account or sub-account section (product, share or sub-account name); empty when none.'},
                'institution': {'type': 'string'}, 'holder': {'type': 'string'},
                'account_number': {'type': 'string'},
                'currency': {'type': 'string', 'description': 'ISO 4217 code only if the page prints the currency; else empty.'},
                'currency_as_printed': {'type': 'string'},
                'period_start': {'type': 'string'}, 'period_end': {'type': 'string'},
                'opening_balance': _nullable('string'), 'closing_balance': _nullable('string'),
                'total_credits': _nullable('string'), 'total_debits': _nullable('string'),
                'count_credits': _nullable('integer'), 'count_debits': _nullable('integer'),
                'rows': {'type': 'array', 'items': _ROW},
                'no_transactions_printed': {'type': 'boolean'}}}
PAGE_SCHEMA = {'type': 'object', 'additionalProperties': False,
               'required': ['printed_page_number', 'printed_page_total', 'is_statement_page', 'sections'],
               'properties': {'printed_page_number': _nullable('integer'), 'printed_page_total': _nullable('integer'),
                              'is_statement_page': {'type': 'boolean'},
                              'sections': {'type': 'array', 'items': _SECTION}}}

# One request per statement: every page image, labelled with its page number; each row cites its page.
_DOC_ROW = dict(_ROW, required=_ROW['required'] + ['page'], properties=dict(_ROW['properties'], page={'type': 'integer'}))
_ACCOUNT = dict(_SECTION, required=_SECTION['required'] + ['opening_balance_page', 'closing_balance_page'],
                properties=dict(_SECTION['properties'], rows={'type': 'array', 'items': _DOC_ROW},
                                opening_balance_page=_nullable('integer'), closing_balance_page=_nullable('integer')))
DOCUMENT_SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['pages', 'accounts'],
                   'properties': {
                       'pages': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
                                 'required': ['page', 'printed_page_number', 'printed_page_total', 'is_statement_page'],
                                 'properties': {'page': {'type': 'integer'},
                                                'printed_page_number': _nullable('integer'),
                                                'printed_page_total': _nullable('integer'),
                                                'is_statement_page': {'type': 'boolean'}}}},
                       'accounts': {'type': 'array', 'items': _ACCOUNT}}}

PROMPT = """You are transcribing a bank account statement for a forensic ledger. The images are its pages; each is preceded by its label "Page N". Transcribe exactly what is printed. Never calculate, correct, complete or adjust any number, and never make figures add up. Return JSON only, in the given schema.

pages: one entry per labelled page: page (N from its label), printed_page_number / printed_page_total (the numbering printed on it, e.g. "PAGINA 2 / 7", "Page 2 of 7", "2 de 7"; null when not printed), is_statement_page (false for a page with no account information: blank, legal notes, advertising).

accounts: one entry per account or sub-account whose statement is printed (a product, currency sub-account or share with its own balances is its own entry), in printed order:
- section_name: the printed product, sub-account or share heading; institution; holder (account holder name); account_number (the account number as printed, including masks; not a CLABE, client or contract number when an account number is printed); currency (ISO code only when the statement prints the currency or its name; never guess from a "$" sign) and currency_as_printed (the literal text).
- period_start, period_end as YYYY-MM-DD: the statement period printed for this account.
- opening_balance (balance at the start of the period, e.g. "Saldo anterior", "Saldo inicial", "Previous balance") and closing_balance (e.g. "Saldo final", "Saldo al corte", "New balance"), with the page each is printed on (opening_balance_page, closing_balance_page). Negative only when printed negative.
- total_credits / total_debits: printed totals of deposits/credits and of withdrawals/charges for the period; count_credits / count_debits: printed numbers of them. null when not printed.
- rows: every movement line of this account in printed order, across all its pages: page (the label N of the page it is printed on); date as YYYY-MM-DD (the operation date; take the year from the statement period); description as printed (one line is enough); amount positive; direction credit (money in, deposit, abono) or debit (money out, charge, cargo, retiro); balance_after = the running balance printed on that line, or null. Never list opening or closing balance lines, totals, subtotals or summary lines as rows. Set unreadable true for a row whose date or amount you cannot read with certainty.
- no_transactions_printed: true only when the statement states there were no movements for this account.
All amounts use a dot as decimal separator, no thousands separators, a leading "-" only when printed negative. Empty string or null for anything not printed."""

STRIPS_NOTE = """

Each page is given as {count} consecutive horizontal strips, top to bottom (labelled "Page N, part k of {count}"); neighbouring strips overlap slightly. Read the strips of a page as one page and transcribe every printed line exactly once (a line visible in two strips is one line)."""


def document_pages(document, sent_pages):
    """The document reading as [(page, page json)] in the per-page form ``combine`` takes.

    Each account becomes one section per page it uses, under a name unique to it,
    so ``combine`` gives back exactly one section per account. A row or balance
    citing a page that was not sent raises NotProved.
    """
    sent = list(sent_pages)
    numbering = {entry.get('page'): entry for entry in document.get('pages') or []}
    if any(page not in numbering for page in sent):
        # Every page sent is described (its printed number), or the page-numbering check could not run.
        raise NotProved('The page-image reading does not describe every page that was read.')
    by_page = {page: [] for page in sent}
    for index, account in enumerate(document.get('accounts') or []):
        rows = account.get('rows') or []
        cited = [row.get('page') for row in rows] + [account.get(k) for k in ('opening_balance_page', 'closing_balance_page')
                                                      if account.get(k) is not None]
        if any(page not in by_page for page in cited):
            raise NotProved('The page-image reading cites a page that was not read.')
        used = sorted(set(cited) or {sent[0]}, key=sent.index)
        first, last = used[0], used[-1]
        for page in used:
            section = {key: '' for key in _SECTION['properties'] if _SECTION['properties'][key].get('type') == 'string'}
            section.update({key: None for key in ('opening_balance', 'closing_balance', 'total_credits', 'total_debits',
                                                  'count_credits', 'count_debits')})
            section.update(section_name='ACCOUNT %d' % (index + 1), account_number=account.get('account_number') or '',
                           rows=[{k: v for k, v in row.items() if k != 'page'} for row in rows if row.get('page') == page],
                           no_transactions_printed=bool(account.get('no_transactions_printed')) and page == first)
            if page == first:
                section.update({key: account.get(key) for key in ('institution', 'holder', 'currency', 'currency_as_printed',
                                'period_start', 'period_end', 'total_credits', 'total_debits', 'count_credits', 'count_debits')})
            if page == (account.get('opening_balance_page') or first):
                section['opening_balance'] = account.get('opening_balance')
            if page == (account.get('closing_balance_page') or last):
                section['closing_balance'] = account.get('closing_balance')
            by_page[page].append(section)
    return [(page, dict(printed_page_number=(numbering.get(page) or {}).get('printed_page_number'),
                        printed_page_total=(numbering.get(page) or {}).get('printed_page_total'),
                        is_statement_page=bool((numbering.get(page) or {}).get('is_statement_page', True)),
                        sections=by_page[page])) for page in sent]


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------

def _iso(value):
    try:
        parsed = date.fromisoformat(str(value or ''))
        return parsed.isoformat() if parsed.isoformat() == value else ''
    except ValueError:
        return ''


_GROUPED = re.compile(r'(-?)\$?\s*(\d{1,3}(?:,\d{3})+)(\.\d+)?')
_CODE = re.compile(r'\s*(?:[A-Z]{3}|M\.N\.|MN|DLLS?)\.?$')


def to_minor(value, exponent, *, signed=False):
    """'1234.56' -> 123456; None for anything not a plain decimal with at most the currency's places.

    Only two unambiguous print forms are normalised: a trailing currency code
    ('0.00 USD') and comma thousands groups of exactly three digits
    ('1,234,567.89'). Anything else (a comma decimal, odd grouping) is refused.
    """
    text = _CODE.sub('', str(value if value is not None else '').strip())
    grouped = _GROUPED.fullmatch(text)
    if grouped:
        text = grouped.group(1) + grouped.group(2).replace(',', '') + (grouped.group(3) or '')
    elif text.startswith('$') or text.startswith('-$'):
        text = text.replace('$', '').strip()
    if not re.fullmatch(r'-?\d{1,16}(\.\d{1,%d})?' % max(exponent, 1), text):
        return None
    if text.startswith('-') and not signed:
        return None
    try:
        amount = Decimal(text) * (Decimal(10) ** exponent)
    except InvalidOperation:
        return None
    return int(amount) if amount == amount.to_integral_value() else None


def _digits(text):
    return re.sub(r'\D', '', str(text or ''))


def _exponent(currency):
    from services.financial.money import get_currency
    try:
        return get_currency(currency).exponent
    except Exception:  # noqa: BLE001 - an unknown code cannot be proved
        return None


class NotProved(Exception):
    """The image reading does not prove; ``str`` is the plain reason recorded for the investigator."""


# ---------------------------------------------------------------------------
# Combining pages into account sections
# ---------------------------------------------------------------------------

_HEADER = ('institution', 'holder', 'account_number', 'currency', 'period_start', 'period_end')


def _continued(merged, account, label, period):
    """The earlier section this one continues, or None for a new section.

    Same account (digits agree) and a compatible period; between sections of one
    account, the same printed section name, or one without a name yet. Without an
    account: the same section name, else the section just before (a continuation).
    """
    def period_ok(m):
        return not all(period) or not all(m['period']) or m['period'] == period
    if account:
        same = [m for m in merged if m['digits'] and (m['digits'].endswith(account) or account.endswith(m['digits']))
                and period_ok(m)]
        if label:
            return next((m for m in reversed(same) if m['label'] == label), None) or \
                next((m for m in reversed(same) if not m['label']), None)
        return same[-1] if same else None
    if label:
        named = next((m for m in reversed(merged) if m['label'] == label), None)
        if named is not None:
            return named
        if merged and merged[-1]['label']:
            return None  # a differently named section starts here
    return merged[-1] if merged else None


def _canonical(value):
    """A printed amount in one comparable form ('65,660.55' == '65660.55'), else its text."""
    minor = to_minor(value, 6, signed=True)
    return str(minor) if minor is not None else ' '.join(str(value).split())


def combine(pages):
    """[(page_number, page_json)] -> merged sections, each with its rows' page numbers.

    A section printing an account number starts (or continues) that account; a
    section without one continues the previous section. Conflicting printed
    values for one account section (two openings, two periods) raise NotProved.
    """
    merged = []
    for page_number, page in pages:
        for section in page.get('sections') or []:
            account = _digits(section.get('account_number'))
            label = ' '.join(str(section.get('section_name') or '').upper().split())
            period = (_iso(section.get('period_start')), _iso(section.get('period_end')))
            target = _continued(merged, account, label, period)
            if target is not None and label and not target['label']:
                target['label'] = label
            if target is None:
                target = dict(digits=account, label=label, period=('', ''), header={k: '' for k in _HEADER}, rows=[], pages=[],
                              values={}, balance_pages={}, no_transactions=False)
                merged.append(target)
            if account and len(account) > len(target['digits']):
                target['digits'] = account
            if all(period):
                if all(target['period']) and target['period'] != period:
                    raise NotProved('The page images print two different periods for one account section.')
                target['period'] = period
            for key in _HEADER:
                value = str(section.get(key) or '').strip()
                if value and not target['header'][key]:
                    target['header'][key] = value
            for key in ('opening_balance', 'closing_balance', 'total_credits', 'total_debits', 'count_credits', 'count_debits'):
                value = section.get(key)
                if value in (None, ''):
                    continue
                value = str(value).strip()
                if key in target['values'] and _canonical(target['values'][key]) != _canonical(value):
                    raise NotProved('The page images print two different values for the %s.' % key.replace('_', ' '))
                target['values'][key] = value
                target['balance_pages'].setdefault(key, page_number)
            target['no_transactions'] = target['no_transactions'] or bool(section.get('no_transactions_printed'))
            for row in section.get('rows') or []:
                target['rows'].append(dict(row, page=page_number))
            if page_number not in target['pages']:
                target['pages'].append(page_number)
    return merged


def check_page_numbering(pages, file_pages=None):
    """NotProved when the printed numbering shows pages absent from the file.

    The numbering may count the whole printed document while this period uses
    only some of its pages; a page is missing when the file has fewer pages
    than printed, or a printed number is beyond the file.
    """
    totals = {page.get('printed_page_total') for _, page in pages if page.get('printed_page_total')}
    numbers = {page.get('printed_page_number') for _, page in pages if page.get('printed_page_number')}
    if len(totals) > 1:
        raise NotProved('The pages print different page counts; the period may combine two printings.')
    if totals:
        total = next(iter(totals))
        if not isinstance(total, int) or total < 1 or total > 500:
            raise NotProved('The printed page count could not be read.')
        count = len(file_pages) if file_pages else len(pages)
        if total > count or any(isinstance(n, int) and n > count for n in numbers):
            missing = sorted(set(range(1, total + 1)) - numbers)
            raise NotProved('The pages print %s pages but the file has %s; pages may be missing (printed pages not read: %s).' % (
                total, count, ', '.join(str(n) for n in missing[:10]) or 'none'))
    _numbering_has_no_gap(pages, file_pages, next(iter(totals)) if totals else None)


def _numbering_has_no_gap(pages, file_pages, total):
    """NotProved when a printed page number between this period's pages is not one of them.

    As the text reader's numbering rule: an unnumbered page of the period (cover,
    notice, reverse side) may stand in for a number only where it sits in the gap.
    Before the first and after the last numbered page the printed pages must at
    least be pages of the file (the numbering may count the whole printed document).
    """
    numbered, loose, previous = [], 0, None
    for physical, page in sorted(pages, key=lambda pair: pair[0]):
        number = page.get('printed_page_number')
        if not isinstance(number, int) or number < 1:
            loose += 1
            continue
        if previous is not None and number == previous:
            raise NotProved('Two pages of this period print the same page number (%s); the pages could not be '
                            'put in order.' % number)
        if previous is not None and (number < previous or number - previous - 1 > loose):
            raise NotProved('The printed page numbers of this period skip from page %s to page %s; '
                            'a page may be missing.' % (previous, number))
        numbered.append((physical, number))
        previous, loose = number, 0
    if not numbered:
        return
    file_pages = sorted(file_pages or [p for p, _ in pages])
    (first_physical, first), (last_physical, last) = numbered[0], numbered[-1]
    before = len([p for p in file_pages if p < first_physical])
    after = len([p for p in file_pages if p > last_physical])
    if first - 1 > before or (total and total - last > after):
        raise NotProved('The printed page numbers show pages of this statement that are not in the file; '
                        'a page may be missing.')


# ---------------------------------------------------------------------------
# Proof
# ---------------------------------------------------------------------------

def _movement(row, liability):
    return row['amount_minor'] * (1 if row['direction'] == 'credit' else -1) * (-1 if liability else 1)


def _rule_metadata(proposal):
    metadata = proposal.get('metadata') or {}
    return dict(currency=proposal.get('currency') or '', holder=metadata.get('holder') or '',
                account_number=metadata.get('account_number') or '', institution=metadata.get('institution') or '',
                period_start=metadata.get('period_start') or '', period_end=metadata.get('period_end') or '')


def same_number(a, b):
    """Two printed account references name the same account: equal, a masked suffix, or one embedded in
    the other (a CLABE or contract number carrying the account number), at least 8 digits."""
    from services.financial import field_proposals as fp
    a, b = _digits(a), _digits(b)
    if not a or not b:
        return False
    if fp.account_match(fp.account_identity(a), fp.account_identity(b)) or a == b:
        return True
    shorter, longer = sorted((a, b), key=len)
    return (len(shorter) >= 8 and shorter in longer) or (len(shorter) == 4 and longer.endswith(shorter))


def _period_end(section):
    return section['period'][1] or _iso(section['header'].get('period_end'))


def choose_section(sections, proposal):
    rule = _rule_metadata(proposal)
    account = _digits(rule['account_number'])
    candidates = [s for s in sections if s['rows'] or s['values']]
    if account and len(account) >= 4:
        numbered = [s for s in candidates if s['digits'] and same_number(s['digits'], account)]
        # Sections printing no number (it is printed in the page header only) remain candidates
        # when no section prints this account's number.
        candidates = numbered or [s for s in candidates if not s['digits']]
    if rule['period_end'] and len(candidates) > 1:
        candidates = [s for s in candidates if _period_end(s) == rule['period_end']]
    if rule['currency'] and len(candidates) > 1:
        candidates = [s for s in candidates if s['header']['currency'] == rule['currency']]
    if not candidates:
        raise NotProved('The page images show no account section matching this statement.')
    if len(candidates) > 1:
        raise NotProved('The page images show %s account sections; the statement could not be matched to one.' % len(candidates))
    return candidates[0]


def prove(proposal, section, knowledge):
    """The proved reading {details, opening, closing, rows, pages} or NotProved with the reason."""
    from services.financial import field_proposals as fp
    rule = _rule_metadata(proposal)
    header = section['header']
    liability = (proposal.get('metadata') or {}).get('balance_convention') == 'liability_owed'
    # Header against the rule reading, wherever that read a value.
    account_text = rule['account_number'] or header['account_number']
    if not _digits(account_text):
        raise NotProved('The account number could not be read from the page images.')
    if rule['account_number'] and header['account_number'] and not same_number(header['account_number'], rule['account_number']):
        raise NotProved('The account number read from the page images differs from the one read from the text.')
    for field, same in (('holder', fp.same_holder), ('institution', fp.same_institution)):
        if rule[field] and header[field] and not same(rule[field], header[field]):
            raise NotProved('The %s read from the page images differs from the one read from the text.' % (
                'account holder' if field == 'holder' else 'bank'))
    start, end = section['period']
    if not end:
        end = _period_end(section)
        start = _iso(section['header'].get('period_start'))
    if not start and end and rule['period_start'] and rule['period_end'] == end:
        # Only the end is printed with this section; the start is the text reading's for the same period.
        start = rule['period_start']
    if not (start and end and start <= end):
        raise NotProved('The statement period could not be read from the page images.')
    if (rule['period_start'] and rule['period_start'] != start) or (rule['period_end'] and rule['period_end'] != end):
        raise NotProved('The period read from the page images differs from the one read from the text.')
    # Header against the account's saved statements: the same printed number at the same bank
    # (fail closed when two different accounts could be meant).
    holder_printed = header['holder'] or rule['holder']
    institution_printed = header['institution'] or rule['institution']
    candidates, matched = fp.matching_accounts(dict(account_number=account_text, institution=institution_printed), knowledge)
    if not candidates or 'ambiguous' in matched or 'account' not in matched:
        raise NotProved('This account has no saved statement in the case to confirm the page-image reading against.')
    partial = 'masked' in matched or not rule['account_number']
    if partial and not holder_printed:
        # Only some digits agree, or only the page images print the number: another account at the
        # bank could end the same way, so the printed holder must also agree (checked below).
        raise NotProved('The account holder is not printed, so the account could not be confirmed from a partial number.')

    def currencies(known):
        return set(known.values('currency')) or ({known.currency} if known.currency else set())
    # One number can hold several currency sub-accounts, each saved as its own account.
    printed = {c for c in (rule['currency'], header['currency']) if c}
    if len(printed) > 1:
        raise NotProved('The currency read from the page images differs from the one read from the text.')
    if printed:
        currency = next(iter(printed))
        candidates = [k for k in candidates if currencies(k) == {currency}]
        if not candidates:
            raise NotProved('The currency differs from the saved statements of this account.')
    else:
        known_currencies = set().union(*(currencies(k) for k in candidates))
        if len(known_currencies) != 1:
            raise NotProved('The currency is not printed and the saved statements of this account have more than one.')
        currency = next(iter(known_currencies))
    saved_holders = [h for k in candidates for h in k.values('holder')]
    saved_institutions = [i for k in candidates for i in k.values('institution')] or [k.institution for k in candidates if k.institution]
    holder = holder_printed or (saved_holders[-1] if saved_holders and len({fp.holder_key(h) for h in saved_holders}) == 1 else '')
    institution = institution_printed or (saved_institutions[-1] if saved_institutions else '')
    if partial and not (saved_holders and saved_institutions and institution_printed):
        # A partial number is confirmed only by a printed holder and bank the saved statements also record.
        raise NotProved('The account could not be confirmed from a partial number: the saved statements of this '
                        'account do not record the holder and bank to compare.')
    if not holder or (saved_holders and not any(fp.same_holder(holder, h) for h in saved_holders)):
        raise NotProved('The account holder could not be confirmed against the saved statements of this account.')
    if not institution or (saved_institutions and not all(fp.same_institution(institution, i) for i in saved_institutions)):
        raise NotProved('The bank could not be confirmed against the saved statements of this account.')
    exponent = _exponent(currency)
    if exponent is None:
        raise NotProved('The currency is not supported.')
    # Balances.
    opening = to_minor(section['values'].get('opening_balance'), exponent, signed=True)
    closing = to_minor(section['values'].get('closing_balance'), exponent, signed=True)
    if opening is None or closing is None:
        raise NotProved('The opening or closing balance could not be read from the page images.')
    # Rows.
    rows = []
    for index, row in enumerate(section['rows']):
        amount = to_minor(row.get('amount'), exponent)
        when = _iso(row.get('date'))
        if row.get('unreadable') or not amount or not when or row.get('direction') not in ('credit', 'debit') \
                or not str(row.get('description') or '').strip():
            raise NotProved('A payment on page %s could not be read with certainty from the page image.' % row['page'])
        if not start <= when <= end:
            raise NotProved('A payment on page %s is dated outside the statement period.' % row['page'])
        balance = None
        if row.get('balance_after') not in (None, ''):
            balance = to_minor(row['balance_after'], exponent, signed=True)
            if balance is None:
                raise NotProved('A running balance on page %s could not be read.' % row['page'])
        rows.append(dict(index=index, date=when, description=' '.join(str(row['description']).split())[:4000],
                         amount_minor=amount, direction=row['direction'], balance_minor=balance, page=row['page']))
    if not rows:
        raise NotProved('No payments were read from the page images; a period without payments needs its printed confirmation.')
    _not_summary_lines(section, rows, exponent)
    expected = opening + sum(_movement(r, liability) for r in rows)
    if expected != closing:
        raise NotProved('The page-image reading did not balance: the payments come to %s, the printed closing balance is %s (difference %s).'
                        % (_show(expected, exponent), _show(closing, exponent), _show(expected - closing, exponent)))
    if not _running_ok(rows, opening, liability):
        raise NotProved('A printed running balance does not agree with the payments read before it.')
    for direction in ('credit', 'debit'):
        printed = section['values'].get('total_%ss' % direction)
        if printed is not None:
            total = to_minor(printed, exponent)
            if total is None or total != sum(r['amount_minor'] for r in rows if r['direction'] == direction):
                raise NotProved('The %s read do not add up to the printed total.' % ('credits' if direction == 'credit' else 'charges'))
        count = section['values'].get('count_%ss' % direction)
        if count is not None:
            if not str(count).isdigit() or int(count) != sum(r['direction'] == direction for r in rows):
                raise NotProved('The number of %s read differs from the printed count.' % ('credits' if direction == 'credit' else 'charges'))
    _agrees_with_rule_reading(proposal, rows, opening, closing)
    return dict(account_keys=[k.key for k in candidates], currency=currency, holder=holder, institution=institution,
                account_number=account_text,
                period_start=start, period_end=end, opening=opening, closing=closing, rows=rows,
                opening_page=section['balance_pages'].get('opening_balance'),
                closing_page=section['balance_pages'].get('closing_balance'))


def _not_summary_lines(section, rows, exponent):
    """A reading whose only rows are the printed period totals has read the summary, not the movements."""
    totals = {direction: to_minor(section['values'].get('total_%ss' % direction), exponent) for direction in ('credit', 'debit')}
    counts = {direction: section['values'].get('count_%ss' % direction) for direction in ('credit', 'debit')}
    by_direction = {direction: [r for r in rows if r['direction'] == direction] for direction in ('credit', 'debit')}
    echoed = [d for d in ('credit', 'debit') if len(by_direction[d]) == 1 and totals[d] is not None
              and by_direction[d][0]['amount_minor'] == totals[d] and str(counts[d]) != '1']
    if echoed and sum(len(v) for v in by_direction.values()) == len(echoed):
        raise NotProved('The page-image reading lists only the printed period totals, not the payments.')


ADJACENT_DAYS = 3


def check_neighbours(db, case_id, reading):
    """The account's saved statements next to this period agree with it; none overlaps it.

    The previous saved period ending at most ADJACENT_DAYS before this start must
    close at this opening; the next one starting at most ADJACENT_DAYS after this end
    must open at this closing (where those balances are recorded). A saved period of
    the same account and currency overlapping this one holds it (a decision).
    """
    from datetime import timedelta
    from postgres.models.financial import (FinancialSourceDocument as Source, FinancialStatementPeriod as Period)
    keys = [UUID(key) for key in reading['account_keys']]
    start, end = date.fromisoformat(reading['period_start']), date.fromisoformat(reading['period_end'])
    rows = db.execute(select(Period.period_start, Period.period_end, Period.opening_balance_minor, Period.closing_balance_minor)
        .join(Source, Source.id == Period.source_document_id)
        .where(Period.case_id == case_id, Period.account_id.in_(keys), Period.currency == reading['currency'],
               Source.status == 'admitted', Source.metadata_['financial_import_removal'].as_string().is_(None))).all()
    for saved_start, saved_end, opening, closing in rows:
        if saved_start and saved_end and saved_start <= end and start <= saved_end:
            raise NotProved('A saved statement of this account already covers part of this period.')
        if saved_end and timedelta(0) < start - saved_end <= timedelta(days=ADJACENT_DAYS) and closing is not None \
                and closing != reading['opening']:
            raise NotProved('The opening balance differs from the closing balance of the previous saved statement.')
        if saved_start and timedelta(0) < saved_start - end <= timedelta(days=ADJACENT_DAYS) and opening is not None \
                and opening != reading['closing']:
            raise NotProved('The closing balance differs from the opening balance of the next saved statement.')


def _show(minor, exponent):
    sign = '-' if minor < 0 else ''
    whole, part = divmod(abs(minor), 10 ** exponent)
    return f'{sign}{whole:,}' + (f'.{part:0{exponent}d}' if exponent else '')


def _running_ok(rows, opening, liability):
    """Every printed running balance agrees in printed order (or, for a reverse-printed list, in reverse)."""
    if not any(r['balance_minor'] is not None for r in rows):
        return True
    for sequence in (rows, list(reversed(rows))):
        balance, ok = opening, True
        for row in sequence:
            balance += _movement(row, liability)
            if row['balance_minor'] is not None and row['balance_minor'] != balance:
                ok = False
                break
        if ok:
            return True
    return False


def _agrees_with_rule_reading(proposal, rows, opening, closing):
    """Every cleanly read text payment is in the image reading; every read text balance is the same."""
    from collections import Counter
    from services.financial.review_arithmetic import integer
    available = Counter((r['amount_minor'], r['direction']) for r in rows)
    missing = 0
    for row in proposal['rows']:
        fields = row.get('fields') or {}
        if row.get('kind') == 'balance':
            value = integer(fields.get('balance'))
            role = (fields.get('description') or '').strip().lower()
            if value is not None and ((role == 'opening balance' and value != opening) or
                                      (role == 'closing balance' and value != closing)):
                raise NotProved('The %s read from the page images differs from the one read from the text.' % role)
            continue
        if row.get('kind') != 'transaction' or row.get('excluded') or row.get('issues'):
            continue
        amount = integer(fields.get('amount_minor'))
        if amount is None or amount <= 0 or fields.get('direction') not in ('credit', 'debit'):
            continue
        key = (amount, fields['direction'])
        if available[key]:
            available[key] -= 1
        else:
            missing += 1
    if missing:
        raise NotProved('%s payment%s read from the text %s not found in the page-image reading.' % (
            missing, '' if missing == 1 else 's', 'was' if missing == 1 else 'were'))


# ---------------------------------------------------------------------------
# The review the proved reading becomes
# ---------------------------------------------------------------------------

def build_request(proposal, reading):
    """The statement review (as the batch save takes it) recording a proved reading."""
    from services.financial.import_batches import initial_request
    from services.financial.manual_row_placement import allowed_source_positions
    request = initial_request(proposal)
    request.update(currency=reading['currency'], holder=reading['holder'], account_number=reading['account_number'],
                   institution=reading['institution'], period_start=reading['period_start'],
                   period_end=reading['period_end'])
    originals = {row['id']: row for row in proposal['rows']}
    roles = {}
    for row in request['rows']:
        original = originals[row['id']]
        if original['kind'] == 'balance':
            role = (original['fields'].get('description') or '').strip().lower()
            if role in ('opening balance', 'closing balance'):
                roles.setdefault(role, []).append(row)
            continue
        if not row['excluded']:
            row.update(excluded=True, reason=REPLACED_REASON)
    pages = proposal.get('statement_page_numbers') or sorted({s['page_number'] for s in proposal.get('sources') or []}) \
        or proposal.get('page_numbers') or []
    for role, value, page in (('opening balance', reading['opening'], reading['opening_page']),
                              ('closing balance', reading['closing'], reading['closing_page'])):
        existing = roles.get(role) or []
        if len(existing) > 1:
            raise NotProved('The text reading has more than one %s for this period.' % role)
        if existing:
            existing[0]['balance_minor'] = str(value)
            continue
        if page not in pages:
            raise NotProved('The %s was read from a page outside this statement.' % role)
        request['rows'].append(dict(id=f'manual:{role.split()[0]}-balance', excluded=True, manual_page=page,
                                    date='', date_unprinted=False, date_values={}, description=role.title(),
                                    counterparty='', amount_minor='0', direction=None, balance_minor=str(value),
                                    reason=ROW_REASON.format(page=page)))
    for row in reading['rows']:
        if row['page'] not in (proposal.get('page_numbers') or []):
            raise NotProved('A payment was read from a page outside this file.')
        entry = dict(id=f'manual:vision-p{row["page"]}-{row["index"]}', excluded=False, manual_page=row['page'],
                     date=row['date'], date_unprinted=False, date_values={}, description=row['description'],
                     counterparty='', amount_minor=str(row['amount_minor']), direction=row['direction'],
                     balance_minor=str(row['balance_minor']) if row['balance_minor'] is not None else None,
                     reason=ROW_REASON.format(page=row['page']))
        allowed = sorted(allowed_source_positions(originals, row['page'], pages))
        anchor = next((a for a in allowed if a[0] == 'after'), None) or (allowed[0] if allowed else None)
        if anchor:
            # After the last text row of its page (all set aside), so the image rows keep printed order.
            on_page = [r for r in proposal['rows'] if r.get('kind') in ('transaction', 'unresolved') and r.get('page_number') == row['page']]
            if on_page:
                anchor = ('after', on_page[-1]['id'])
            entry['source_order_anchor'] = dict(relation=anchor[0], row_id=anchor[1])
        request['rows'].append(entry)
    return request


# ---------------------------------------------------------------------------
# Reading the images
# ---------------------------------------------------------------------------

def render_pages(path, page_numbers, width=IMAGE_WIDTH, strips=None):
    """[(page, [png, ...])]: each page as ``strips`` overlapping horizontal strips, top to bottom.

    One whole portrait page is shrunk by the model to about 768 pixels wide, too
    small for dense statement print; strips keep the rendered width.
    """
    import fitz
    from services.financial.page_render import render_page_png
    strips = STRIPS if strips is None else strips
    pages = []
    with fitz.open(str(path)) as document:
        for number in page_numbers:
            if strips <= 1:
                pages.append((number, [render_page_png(document, page_number=number, width=width)]))
                continue
            render_page_png(document, page_number=number, width=8)  # validates the page number
            page = document.load_page(number - 1)
            rect = page.rect
            zoom = width / rect.width
            height = rect.height / strips
            overlap = height * STRIP_OVERLAP
            images = []
            for index in range(strips):
                top = max(rect.y0, rect.y0 + index * height - overlap)
                bottom = min(rect.y1, rect.y0 + (index + 1) * height + overlap)
                clip = fitz.Rect(rect.x0, top, rect.x1, bottom)
                images.append(page.get_pixmap(matrix=(zoom, 0.0, 0.0, zoom, 0.0, 0.0), clip=clip).tobytes('png'))
            pages.append((number, images))
    return pages


def openai_page_reader(db, case_id):
    """(model_id, read(png) -> (json, usage)) for the workload's model; raises when unavailable (fail closed)."""
    from services.ai_model_policy import get_workload_model
    from services.ai_provider_credentials import get_provider_api_key
    provider, model_id = get_workload_model(db, WORKLOAD)
    if provider != 'openai':
        raise RuntimeError(f'Page-image reading is not available for {provider}')
    api_key = get_provider_api_key(db, provider)
    if not api_key:
        raise RuntimeError('No OpenAI key is configured')

    return model_id, document_request(model_id, api_key)


def document_request(model_id, api_key):
    """read([(page, [png, ...])]) -> (document json, usage): one request for the statement's pages."""
    from services.llm_service import LLMExecutionContext

    def read(pages):
        strips = max(len(images) for _, images in pages)
        labels, images = [], []
        for number, parts in pages:
            for index, image in enumerate(parts):
                labels.append(f'Page {number}' if len(parts) == 1 else f'Page {number}, part {index + 1} of {len(parts)}')
                images.append(image)
        prompt = PROMPT + (STRIPS_NOTE.format(count=strips) if strips > 1 else '')
        context = LLMExecutionContext('openai', model_id, api_key=api_key)
        text = context.call_vision_json(prompt, images, image_labels=labels, schema=DOCUMENT_SCHEMA,
                                        schema_name='statement_document', timeout=PAGE_TIMEOUT_SECONDS,
                                        max_output_tokens=16000)
        return json.loads(text), dict(context.last_usage or {})
    return read


# ---------------------------------------------------------------------------
# One held statement
# ---------------------------------------------------------------------------

def eligible(item, file, proposal):
    """None when the statement may be read from its images, else why not (a code)."""
    from services.financial.statement_progress import review_progress
    if item.status != 'attention':
        return 'not_held'
    if item.review_request or (file is not None and review_progress(file, item.statement_key)):
        return 'investigator_work'
    if proposal.get('saved_review') or proposal.get('previous_saved_review'):
        return 'investigator_work'
    for key, code in (('document_review', 'document'), ('not_payment_statement', 'not_payment'),
                      ('assignment_only', 'assignment'), ('current_import', 'saved'), ('reading_failure', 'reading_failure')):
        if proposal.get(key):
            return code
    if not item.statement_key and len(proposal.get('statement_choices') or []) > 1:
        return 'file_level'
    if (proposal.get('review_recovery') or {}).get('required'):
        return 'recovery_review'
    if (proposal.get('printed_copies') or {}) and not proposal['printed_copies'].get('identical'):
        return 'printed_copies'
    duplicate = proposal.get('duplicate_disposition') or {}
    if duplicate.get('current') and duplicate.get('status') == 'ignored':
        return 'duplicate'
    if ((item.summary or {}).get('duplicate_disposition') or {}).get('status') == 'ignored':
        return 'duplicate'
    return None


def statement_pages(proposal):
    pages = proposal.get('statement_page_numbers') or sorted({s['page_number'] for s in proposal.get('sources') or []
                                                             if type(s.get('page_number')) is int})
    if not pages and len(proposal.get('statement_choices') or []) <= 1:
        # The only statement of its file, with no table read: every page of the file is its page.
        pages = list(proposal.get('page_numbers') or [])
    return [p for p in pages if p in (proposal.get('page_numbers') or pages)]


def _stored(file, key):
    return ((file.metadata_ or {}).get(METADATA_KEY) or {}).get(key or '')


def _being_read(stored):
    if not stored or stored.get('status') != 'reading':
        return False
    started = datetime.fromisoformat(stored['at'])
    return (datetime.now(timezone.utc) - started).total_seconds() < CLAIM_SECONDS


def _store(db, file_id, key, record, claim=None):
    """Store the record under the file's lock. With ``claim=(revision, model)``: False, storing
    nothing, when the statement is being read, was read or was given up (checked under the lock)."""
    from postgres.models.evidence import EvidenceFile
    file = db.scalar(select(EvidenceFile).where(EvidenceFile.id == file_id).with_for_update()
                     .execution_options(populate_existing=True))
    if file is None:
        return False
    metadata = deepcopy(file.metadata_ or {})
    readings = metadata.setdefault(METADATA_KEY, {})
    previous = readings.get(key or '')
    if claim and (_being_read(previous) or _current(previous, *claim) or gave_up(previous, claim[0])):
        return False
    if previous and previous.get('status') not in ('reading',) and previous.get('revision') != record.get('revision'):
        metadata.setdefault(METADATA_KEY + '_history', []).append(previous)
        metadata[METADATA_KEY + '_history'] = metadata[METADATA_KEY + '_history'][-20:]
    readings[key or ''] = record
    file.metadata_ = metadata
    return True


def _note(item, record):
    """The outcome beside the held statement, shown in the queue (summary key survives readiness refreshes)."""
    item.summary = {**(item.summary or {}), 'vision_reading': {k: record.get(k) for k in
                    ('status', 'message', 'pages', 'cost_usd', 'model', 'at')}}


def reserve_usd(model_id, images):
    """The most a request with these images can cost (counted before it is sent)."""
    count = sum(len(strips) for _, strips in images)
    return cost_usd(model_id, dict(prompt_tokens=count * RESERVE_TOKENS_PER_IMAGE + 4000,
                                   completion_tokens=RESERVE_OUTPUT_TOKENS))


def failures(record, revision):
    """Failed requests for this reading; a claim left 'reading' past its time (the worker stopped
    mid-request, after the request was sent) counts as one more."""
    if not record or record.get('version') != VERSION or record.get('revision') != revision:
        return 0
    if record.get('status') == 'failed':
        return record.get('failures') or 0
    if record.get('status') == 'reading' and not _being_read(record):
        return (record.get('failures') or 0) + 1
    return 0


def gave_up(record, revision):
    return failures(record, revision) >= MAX_FAILURES


def _current(record, revision, model_id):
    return (record and record.get('version') == VERSION and record.get('revision') == revision
            and record.get('model') == model_id and record.get('status') in FINAL)


def read_item(factory, item_id, resolve_path, *, page_reader=None, knowledge_for=None, apply=True, force=False):
    """Read one held statement from its page images. Returns the outcome record. Never raises.

    ``page_reader(db, case_id) -> (model_id, read)`` and ``knowledge_for(db, case_id)``
    are injectable for tests and the truth benchmark. ``apply=False`` measures only:
    nothing is stored or saved. ``force`` reads a statement that is not held (truth
    accuracy sampling only, never with ``apply``).
    """
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial_import_batches import (FinancialImportBatch as Batch,
                                                          FinancialImportBatchItem as Item)
    from services.financial.import_batches import assess
    from services.financial.statement_import import read_statement_import
    if force and apply:
        raise ValueError('A forced reading is for measurement only')
    page_reader = page_reader or openai_page_reader
    if knowledge_for is None:
        from services.financial.field_proposals import case_knowledge

        def knowledge_for(db, case_id):
            return case_knowledge(db, case_id)
    record = dict(version=VERSION, status='skipped', message='', at=datetime.now(timezone.utc).isoformat())
    file_id, key = None, ''
    try:
        with factory() as db:
            item = db.get(Item, item_id)
            batch = db.get(Batch, item.batch_id) if item else None
            file = db.get(EvidenceFile, item.file_id) if item else None
            if item is None or batch is None or file is None or batch.status == 'removed':
                return dict(record, reason='gone')
            case_id, file_id, key = batch.case_id, item.file_id, item.statement_key or ''
            if apply and not approved(case_id):
                return dict(record, reason='case_not_approved')
            entry = next((e for e in batch.files or [] if e.get('file_id') == str(file_id)), {})
            proposal = read_statement_import(db, case_id=case_id, evidence_file_id=file_id,
                                             currency=entry.get('currency') or None, statement_id=key or None)
            why = eligible(item, file, proposal)
            if force and why in ('not_held', 'saved', 'investigator_work'):
                why = None  # accuracy sampling of saved statements only (never applied)
            if why:
                return dict(record, reason=why)
            if not force:
                state, _ = assess(proposal, None)
                if state != 'attention':
                    return dict(record, reason='not_held')
            pages = statement_pages(proposal)
            if not pages:
                return dict(record, reason='no_pages')
            if len(pages) > MAX_PAGES:
                record.update(status='not_proved', message=f'This period has {len(pages)} pages; page images are read for periods up to {MAX_PAGES} pages.')
                return _finish(factory, item_id, file_id, key, dict(record, revision=proposal['revision'], pages=pages), apply)
            try:
                model_id, read = page_reader(db, case_id)
            except Exception as error:  # noqa: BLE001 - fail closed
                return dict(record, status='unavailable', reason='unavailable', message=str(error)[:300])
            stored = _stored(file, key)
            if _current(stored, proposal['revision'], model_id) and not force:
                return dict(stored, reason='already_read')
            if _being_read(stored) and not force:
                return dict(record, reason='being_read')
            record.update(revision=proposal['revision'], model=model_id, pages=pages,
                          text_reading=_rule_metadata(proposal), failures=failures(stored, proposal['revision']))
            if record['failures'] >= MAX_FAILURES and not force:
                if stored.get('status') == 'failed':
                    return dict(stored, reason='failed_repeatedly')
                return _finish(factory, item_id, file_id, key, dict(record, status='failed', reason='failed_repeatedly',
                               message=GAVE_UP), apply)
            path = resolve_path(file.stored_path)
            if apply:
                # The claim, checked again under the file's lock (another worker may hold it).
                if not _store(db, file_id, key, dict(record, status='reading'), claim=(proposal['revision'], model_id)):
                    db.rollback()
                    return dict(record, reason='being_read')
                db.commit()
            else:
                db.rollback()
        # Outside any lock or transaction: render and read page by page.
        images = render_pages(path, pages)
        reserved = reserve_usd(record['model'], images)
        # The most it can cost is counted before the request is sent, and settled after.
        if not _reserve(case_id, reserved):
            return _finish(factory, item_id, file_id, key, dict(record, status='budget',
                message='Not read from the page images: the reading budget for this case is used for now.'), apply)
        started = time.monotonic()
        # One request with every page of the period, each image labelled with its page number.
        document, usage = read(images)
        cost = cost_usd(record['model'], usage)
        _add_spend(case_id, cost - reserved)
        page_costs = [dict(page=number, prompt_tokens=round((usage.get('prompt_tokens') or 0) / len(images)),
                           completion_tokens=round((usage.get('completion_tokens') or 0) / len(images)),
                           cost_usd=round(cost / len(images), 6)) for number, _ in images]
        log.info('Page-image reading: case %s file %s, %s pages, cost $%.4f ($%.4f a page; %s tokens in, %s out)',
                 str(case_id)[:8], str(file_id)[:8], len(images), cost, cost / len(images),
                 usage.get('prompt_tokens'), usage.get('completion_tokens'))
        record.update(page_costs=page_costs, cost_usd=round(sum(c['cost_usd'] for c in page_costs), 6),
                      seconds=round(time.monotonic() - started, 1), raw=document)
        with factory() as db:
            item = db.get(Item, item_id)
            proposal = read_statement_import(db, case_id=case_id, evidence_file_id=file_id,
                                             currency=entry.get('currency') or None, statement_id=key or None)
            if proposal['revision'] != record['revision']:
                db.rollback()
                return _finish(factory, item_id, file_id, key, dict(record, status='stale',
                    message='The statement was read again while its page images were read.'), apply)
            try:
                readings = document_pages(document, pages)
                check_page_numbering(readings, proposal.get('page_numbers'))
                section = choose_section(combine(readings), proposal)
                reading = prove(proposal, section, knowledge_for(db, case_id))
                if not force:
                    check_neighbours(db, case_id, reading)
                request = build_request(proposal, reading)
                # Sampling a saved statement: judged as if it were not saved yet.
                state, summary = assess(dict(proposal, current_import=None) if force else proposal, request)
                if state != 'ready' or summary.get('problems') or summary.get('problem_count'):
                    first = next((p.get('message') for p in summary.get('problems') or [] if p.get('message')), '')
                    raise NotProved('The page-image reading reconciles, but the statement still has a check: ' + (first or state))
            except NotProved as reason:
                db.rollback()
                return _finish(factory, item_id, file_id, key, dict(record, status='not_proved', message=str(reason)), apply)
            record.update(status='proved', message='Read from the page images; the period reconciles exactly.',
                          rows=len(reading['rows']), request=request)
            if not apply:
                db.rollback()
                return record
            db.rollback()
        return _save(factory, item_id, case_id, file_id, key, record, request)
    except Exception as error:  # noqa: BLE001 - fail closed: the statement stays held
        log.exception('Page-image reading failed; the statement stays held')
        record.update(status='failed', error=type(error).__name__, failures=(record.get('failures') or 0) + 1)
        record['message'] = GAVE_UP if record['failures'] >= MAX_FAILURES else \
            'The page images could not be read just now; the statement stays held.'
        try:
            if apply and file_id is not None:
                return _finish(factory, item_id, file_id, key, record, apply)
        except Exception:  # noqa: BLE001
            log.exception('Recording a failed page-image reading failed')
        return record


def _finish(factory, item_id, file_id, key, record, apply):
    if not apply:
        return record
    from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
    with factory() as db:
        _store(db, file_id, key, {k: v for k, v in record.items() if k != 'request'})
        item = db.scalar(select(Item).where(Item.id == item_id).with_for_update())
        shown = record.get('status') not in ('failed', 'reading') or (record.get('failures') or 0) >= MAX_FAILURES
        if item is not None and item.status == 'attention' and shown:
            _note(item, record)
        db.commit()
    return record


def _save(factory, item_id, case_id, file_id, key, record, request):
    """The batch's own review save (System), then the automatic save of what now checks out completely."""
    from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
    from services.financial.decisions import Actor
    from services.financial.effective_statement_review import batch_review_revision
    from services.financial.import_batches import save_review
    from services.financial.statement_import import StatementReviewDraft
    from services.financial.pdf_candidates import PdfMappingError
    actor = Actor(name=SYSTEM_NAME, email=SYSTEM_EMAIL)
    with factory() as db:
        item = db.get(Item, item_id)
        if item is None or item.status != 'attention' or item.review_request:
            db.rollback()
            return _finish(factory, item_id, file_id, key, dict(record, status='stale',
                message='The statement changed while its page images were read.'), True)
        batch_id = item.batch_id
        try:
            outcome = save_review(db, case_id=case_id, batch_id=batch_id, item_id=item_id,
                                  request=StatementReviewDraft.model_validate(request),
                                  expected_review_revision=batch_review_revision(None, None), actor=actor)
        except PdfMappingError as error:
            db.rollback()
            return _finish(factory, item_id, file_id, key, dict(record, status='not_proved',
                message='The page-image reading could not be recorded: ' + str(error)), True)
        except Exception:
            db.rollback()
            from postgres.models.evidence import EvidenceFile
            from services.financial.statement_progress import review_progress
            with factory() as check:
                file = check.get(EvidenceFile, file_id)
                progress = review_progress(file, key) if file is not None else None
                by = (progress or {}).get('saved_by') or {}
                ours = any(str(row.get('id', '')).startswith('manual:vision-')
                           for row in ((progress or {}).get('request') or {}).get('rows') or [])
                if not (by.get('name') == SYSTEM_NAME and by.get('user_id') == 'None' and ours):
                    raise  # this review was not saved: a failed reading (read_item)
            # The review was saved; what failed came after its commit (the readiness refresh).
            log.exception('Page-image reading: the review is saved; refreshing the statement after it failed')
            outcome = dict(status='saved')
    stored = {k: v for k, v in record.items() if k != 'request'}
    stored['review_status'] = outcome.get('status')
    try:
        with factory() as db:
            _store(db, file_id, key, stored)
            item = db.get(Item, item_id)
            if item is not None:
                _note(item, stored)
            db.commit()
            from services.financial.queue_save import auto_save_prepared
            auto_save_prepared(db, case_id=case_id, batch_id=batch_id, file_id=file_id)
    except Exception:  # noqa: BLE001 - the review is saved (the statement is ready); only this record or the automatic save failed
        log.exception('Recording a saved page-image reading failed; its review is saved')
    log.info('Page-image reading proved statement %s of file %s (%s rows, $%.4f); saved as System review',
             str(item_id)[:8], str(file_id)[:8], record.get('rows'), record.get('cost_usd') or 0)
    return stored


# ---------------------------------------------------------------------------
# Which statements: held ones of files prepared with the reader on
# ---------------------------------------------------------------------------

def pending(db, limit=50):
    """Held, untouched statements of files whose preparation ran with this reader on (batch entry ``MARK``)."""
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial_import_batches import (FinancialImportBatch as Batch,
                                                          FinancialImportBatchItem as Item)
    marked = {}
    for batch_id, case_id, files in db.execute(select(Batch.id, Batch.case_id, Batch.files).where(
            Batch.status.notin_(('removed', 'pausing', 'paused')))):
        if not approved(case_id):
            continue
        for entry in files or ():
            if entry.get(MARK) and entry.get('file_id'):
                marked.setdefault(batch_id, set()).add(entry['file_id'])
    if not marked:
        return []
    found = []
    for item_id, batch_id, file_id, key, draft, metadata in db.execute(
            select(Item.id, Item.batch_id, Item.file_id, Item.statement_key, Item.review_request, EvidenceFile.metadata_)
            .join(EvidenceFile, EvidenceFile.id == Item.file_id)
            .where(Item.batch_id.in_(list(marked)), Item.status == 'attention')
            .order_by(Item.updated_at, Item.id)):
        # An untouched draft is stored as JSON null, which SQL "IS NULL" does not match: checked here.
        if draft or str(file_id) not in marked.get(batch_id, ()):
            continue
        stored = ((metadata or {}).get(METADATA_KEY) or {}).get(key or '')
        if stored and stored.get('version') == VERSION and (stored.get('status') in FINAL or (
                stored.get('status') == 'failed' and (stored.get('failures') or 0) >= MAX_FAILURES)):
            # Read once per reading of the file (a new reading is a new file, with its own statements).
            continue
        found.append(item_id)
        if len(found) >= limit:
            break
    return found


_skip_until = {}


def sweep(factory, resolve_path, *, budget_seconds=SWEEP_SECONDS):
    """Background round: read held statements from their page images, a few per round. Never raises."""
    report = dict(read=0, proved=0, not_proved=0, failed=0, cost_usd=0.0)
    if not ENABLED:
        return report
    started = time.monotonic()
    try:
        with factory() as db:
            ids = pending(db)
    except Exception:
        log.exception('Finding statements to read from page images failed; the next round retries')
        return report
    now = time.monotonic()
    for item_id in ids:
        if time.monotonic() - started >= budget_seconds:
            break
        if _skip_until.get(item_id, 0) > now:
            continue
        outcome = read_item(factory, item_id, resolve_path)
        reason = outcome.get('reason')
        if reason in ('already_read', 'being_read'):
            continue
        if outcome.get('status') in ('proved', 'not_proved', 'failed', 'unavailable', 'stale', 'budget') or reason:
            # Not looked at again by this process for a while unless its reading changes.
            _skip_until[item_id] = now + (3600 if outcome.get('status') in ('failed', 'unavailable', 'budget') else 6 * 3600)
        if outcome.get('status') in ('proved', 'not_proved', 'failed'):
            report['read'] += 1
            report[outcome['status']] += 1
            report['cost_usd'] = round(report['cost_usd'] + (outcome.get('cost_usd') or 0), 6)
        if outcome.get('status') == 'unavailable':
            break  # no key / provider: nothing else this round can be read either
    if report['read']:
        log.info('Page-image reading round: %s', report)
    return report
