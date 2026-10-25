"""Proposals for a statement's missing currency, bank, holder and account number.

Read only. A held statement that lacks one of these details is matched with
what the case already holds, and the value is proposed with its source, e.g.
"USD - same account's 12 saved statements". Nothing here writes: a proposal is
saved only through the existing statement-details save, by a person's click or
by the queue's save action (``apply_confirmed_proposals``).

Currency, in order (Neil, 2026-10-13):
  (a) printed on the statement. The statement reader already adopts a printed
      code or unambiguous symbol, so a statement that asks for its currency
      has none; nothing is proposed from the page here.
  (a') printed elsewhere on the same statement: a brokerage cash ledger
      prints no currency, but its holdings table can
      (``statement_currency.printed_holdings_currency``). Proposed with the
      page it is printed on, never confirmed automatically: the currency of
      the cash ledger stays a person's choice (standing decision, wave 12).
  (b) the same account's saved statements, when they all agree. Confirmed
      automatically only when there are at least two of them, the account is
      identified exactly and uniquely on two independent fields (account number
      plus bank or holder), and no saved statement of that account covers the
      same dates (several currency sections share one account number at some
      banks: those sections must never inherit each other's currency).
  (b') a brokerage cash ledger that prints no currency anywhere (not even in
      its holdings) takes the currency of the ledger account it joins (Neil,
      2026-10-24): confirmed automatically when that account's saved
      statements give exactly one currency (one saved statement is enough),
      the account is identified exactly and uniquely on two independent fields
      and no saved statement of it covers the same dates. No saved statement,
      or several currencies, proposes nothing that is confirmed: it stays held.
      Basis ``account_currency``, recorded with the System details save.
      Switch ``ACCOUNT_CURRENCY``. A brokerage statement that prints a
      currency keeps it; one that differs from its account's is held
      (``account_currency_conflict``).
  (c) the case's usual currency (the currency of most of its saved
      statements). A proposal that needs one click, except under
      ``CASE_CURRENCY`` below.

Bank, holder, full account number: taken from the one known account whose
identity matches the statement (full account number, or the visible digits of
a masked number, plus the bank or holder where both sides print them). Every
saved statement of that account must agree on the value. Confirmed
automatically only when the match is unique and exact on at least two
independent fields; otherwise a one-click proposal.

Automatic fills (Neil, 2026-10-24; each behind a default-on switch
``LOUPE_FINANCIAL_AUTOFILL_<NAME>``, recorded as System with its basis):

* ``CURRENCY``: no currency printed takes the account's currency when every
  saved statement of the one matching account agrees on it (one saved
  statement is enough), no saved statement of it covers the same dates and the
  statement prints no other currency (its holdings). The account is the one
  whose number the statement prints (``identity_proven``). Basis
  ``account_currency``.
* ``CASE_CURRENCY`` (Neil, 2026-10-25): no currency printed anywhere on the
  statement (no holdings currency, no currency word, label or symbol; only
  markers such as a bare '$' that allow the case's usual currency among
  others), no account it could be
  having any other currency, and the case's usual currency a clear majority of
  its saved statements: the case's usual currency, basis
  ``case_default_assumed``, labelled "currency assumed: case's usual (not
  printed)". A person changes it in the statement details like any value.
* ``IDENTITY``: a missing bank (and the full number behind a masked one, as
  before) from the one account whose printed number the statement carries,
  when every saved statement of it gives the same value. The holder keeps its
  bracketing rule (a holder can change after the last saved statement: the
  truth set holds one). An account number is never proposed from anything but
  a matching printed number.

The account is proven by its printed number alone when it is printed in full
(at least six digits) or masked with at least six visible digits, and it is
the only account of the case with that identity (the existing ambiguity check:
two accounts sharing the digits, or one number at two banks, prove nothing).

Re-application with no click (``LOUPE_FINANCIAL_AUTOFILL_REAPPLY``, default on;
``autofill_reapply``): a held statement whose reading is current is filled by
itself only with ``automatic_fills``, a stricter subset of the confirmed
proposals: currency only from the account's saved statements when the
statement's printed balances continue that account's ledger, bank and holder
only when saved statements of the account bracket it, never an account number;
the case's usual currency only under ``CASE_CURRENCY`` (checked again).

A field the statement prints is never replaced: only empty fields receive a
proposal. Switches: ``LOUPE_FINANCIAL_CURRENCY_PROPOSALS`` and
``LOUPE_FINANCIAL_DETAIL_PROPOSALS`` (both on unless set to 0).
"""
import os
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select

VERSION = 'field-proposals-v1'
FIELDS = ('currency', 'institution', 'holder', 'account_number')
# Queue review reason of each field.
REASONS = {'currency': 'currency', 'institution': 'institution', 'holder': 'holder', 'account_number': 'account'}
LABELS = {'currency': 'Currency', 'institution': 'Bank', 'holder': 'Account holder', 'account_number': 'Account number'}
MIN_AGREEING_STATEMENTS = 2
# Neil, 2026-10-24: a brokerage cash ledger printing no currency takes its account's one currency (b').
# Reverse: False (such a statement's currency stays a person's choice, as before).
ACCOUNT_CURRENCY = True
ACCOUNT_CURRENCY_BASIS = 'account_currency'
MIN_MASKED_DIGITS = 4
FULL_ACCOUNT_DIGITS = 6


AUTOFILL_NAMES = ('CURRENCY', 'IDENTITY', 'CASE_CURRENCY')
AUTOFILL_CURRENCY_BASIS = 'account_currency'
# Neil, 2026-10-25: a statement printing no currency anywhere takes the case's usual currency with no click
# (LOUPE_FINANCIAL_AUTOFILL_CASE_CURRENCY). "Clear majority": more than CASE_CURRENCY_SHARE of the case's saved
# statements, at least CASE_CURRENCY_MIN_SAVED of them.
CASE_CURRENCY_BASIS = 'case_default_assumed'
CASE_CURRENCY_LABEL = "currency assumed: case's usual (not printed)"
CASE_CURRENCY_SHARE = 0.55
CASE_CURRENCY_MIN_SAVED = 20


def autofill_enabled(name):
    """A default-on automatic fill switch (``LOUPE_FINANCIAL_AUTOFILL_<NAME>``; 0/false/off/no turns it off)."""
    return os.environ.get(f'LOUPE_FINANCIAL_AUTOFILL_{name}', '1').strip().lower() not in ('0', 'false', 'off', 'no')


def identity_proven(values, candidates, matched):
    """The statement's printed account number alone identifies one account of the case.

    Printed in full with at least six digits, or masked with at least six
    visible digits; one candidate identity only (``matching_accounts`` marks
    two accounts sharing the digits, or a number at two banks, ambiguous).
    """
    if not candidates or 'ambiguous' in matched or 'account' not in matched:
        return False
    digits, _ = account_identity(values.get('account_number'))
    # The digits both sides print: a known masked number proves only its visible digits.
    return all(min(len(digits), len(k.digits)) >= FULL_ACCOUNT_DIGITS for k in candidates)


def currency_proposals_enabled():
    return os.environ.get('LOUPE_FINANCIAL_CURRENCY_PROPOSALS', '1') != '0'


def detail_proposals_enabled():
    return os.environ.get('LOUPE_FINANCIAL_DETAIL_PROPOSALS', '1') != '0'


def enabled_fields():
    fields = []
    if currency_proposals_enabled():
        fields.append('currency')
    if detail_proposals_enabled():
        fields.extend(('institution', 'holder', 'account_number'))
    return fields


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

_MASK = re.compile(r'[*xX•#]')
_INSTITUTION_NOISE = frozenset({
    'BANCO', 'BANK', 'BANCA', 'BANCORP', 'SA', 'S', 'A', 'DE', 'DEL', 'CV', 'C', 'V', 'NA', 'N', 'THE', 'OF',
    'MEXICO', 'MULTIPLE', 'INSTITUCION', 'GRUPO', 'FINANCIERO', 'INC', 'CORP', 'CORPORATION', 'CO', 'CARD',
    'USA', 'NATIONAL', 'ASSOCIATION', 'FSB', 'LTD', 'LLC', 'Y'})
_HOLDER_NOISE = frozenset({'SA', 'S', 'A', 'DE', 'CV', 'C', 'V', 'INC', 'LLC', 'LTD', 'CORP', 'THE'})


def _fold(text):
    text = unicodedata.normalize('NFKD', str(text or '').upper())
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return re.findall(r'[A-Z0-9]+', text)


def institution_key(text):
    return frozenset(t for t in _fold(text) if t not in _INSTITUTION_NOISE)


def holder_key(text):
    return ' '.join(t for t in _fold(text) if t not in _HOLDER_NOISE)


def same_institution(a, b):
    """Core names equal or one contained in the other ("BANCO SANTANDER MEXICO" ~ "Santander")."""
    left, right = institution_key(a), institution_key(b)
    return bool(left and right) and (left <= right or right <= left)


def same_holder(a, b):
    """Equal names, or one printed name truncated from the other."""
    left, right = holder_key(a), holder_key(b)
    if not left or not right:
        return False
    return left == right or (min(len(left), len(right)) >= 8 and (left.startswith(right) or right.startswith(left)))


def account_identity(text):
    """(digits, masked): the printed number's digits and whether only part of it is printed."""
    text = str(text or '').strip()
    digits = re.sub(r'\D', '', text)
    masked = bool(_MASK.search(text)) or 0 < len(digits) < FULL_ACCOUNT_DIGITS
    return digits, masked


def account_match(statement, known):
    """'full' (both printed in full and equal), 'masked' (visible digits agree), or ''."""
    (a, a_masked), (b, b_masked) = statement, known
    if not a or not b:
        return ''
    if not a_masked and not b_masked:
        return 'full' if a == b else ''
    shorter, longer = sorted((a, b), key=len)
    if len(shorter) >= MIN_MASKED_DIGITS and longer.endswith(shorter):
        return 'masked'
    return ''


# ---------------------------------------------------------------------------
# What the case knows
# ---------------------------------------------------------------------------

@dataclass
class SavedStatement:
    """The details one saved statement was saved with (after any later details correction)."""
    currency: str
    period_start: str
    period_end: str
    institution: str
    holder: str
    account_number: str
    # The saved period's opening and closing balances (minor units), when saved.
    opening_minor: int = None
    closing_minor: int = None


@dataclass
class KnownAccount:
    """One account of the case with the details of each of its saved statements."""
    key: str
    account: str
    digits: str
    masked: bool
    institution: str
    currency: str
    statements: list = field(default_factory=list)  # [SavedStatement]

    def values(self, name):
        return [getattr(s, name) for s in self.statements if (getattr(s, name) or '').strip()]


@dataclass
class CaseKnowledge:
    accounts: list
    default_currency: str = ''
    default_count: int = 0
    saved_total: int = 0


_CACHE_SIZE = 16
_cache = {}
_cache_lock = __import__('threading').Lock()


def _fingerprint(session, case_id):
    """Cheap aggregate that changes whenever a saved statement, its period or its account changes."""
    from sqlalchemy import func
    from postgres.models.financial import (FinancialAccount as Account, FinancialSourceDocument as Source,
                                           FinancialStatementPeriod as Period)
    documents = session.execute(select(func.count(Source.id), func.max(Source.updated_at)).where(
        Source.case_id == case_id, Source.document_type == 'statement_review')).one()
    periods = session.execute(select(func.count(Period.id), func.max(Period.updated_at)).where(
        Period.case_id == case_id)).one()
    accounts = session.execute(select(func.count(Account.id), func.max(Account.updated_at)).where(
        Account.case_id == case_id)).one()
    return tuple(str(value) for value in (*documents, *periods, *accounts))


def case_knowledge(session, case_id, evidence_file_ids=None, use_cache=True):
    """The case's saved statements by account, reused while nothing saved in the case changes."""
    if evidence_file_ids is not None or not use_cache:
        return _case_knowledge(session, case_id, evidence_file_ids)
    fingerprint = _fingerprint(session, case_id)
    key = str(case_id)
    with _cache_lock:
        hit = _cache.get(key)
        if hit and hit[0] == fingerprint:
            return hit[1]
    knowledge = _case_knowledge(session, case_id, None)
    with _cache_lock:
        _cache[key] = (fingerprint, knowledge)
        while len(_cache) > _CACHE_SIZE:
            _cache.pop(next(iter(_cache)))
    return knowledge


def _case_knowledge(session, case_id, evidence_file_ids=None):
    """Every current saved statement of the case, grouped by its account (one query).

    ``evidence_file_ids`` limits it to statements saved from those files (replays).
    Holder and bank are taken per statement (as saved, then as corrected), never
    from the account record alone: one account can be printed under different
    names over time, and such an account proposes no holder.
    """
    from postgres.models.financial import (FinancialAccount as Account, FinancialSourceDocument as Source,
                                           FinancialStatementPeriod as Period)
    request, review = Source.metadata_['statement_import_request'], Source.metadata_['statement_details_review']
    rows = session.execute(select(Account.id, Account.identifier_as_printed, Account.identifier_normalised,
            Account.institution_name, Account.currency, Period.currency, Period.period_start, Period.period_end,
            Period.opening_balance_minor, Period.closing_balance_minor, request['holder'].as_string(), request['institution'].as_string(), request['account_number'].as_string(),
            review['details']['holder'].as_string(), review['details']['institution'].as_string(),
            review['details']['account_number'].as_string())
        .join(Period, Period.account_id == Account.id).join(Source, Source.id == Period.source_document_id)
        .where(Period.case_id == case_id, Account.case_id == case_id, Source.status == 'admitted',
               Source.document_type == 'statement_review',
               Source.metadata_['financial_import_removal'].as_string().is_(None),
               *([Source.evidence_file_id.in_(list(evidence_file_ids))] if evidence_file_ids is not None else []))).all()
    accounts, currencies = {}, Counter()
    for (account_id, printed, normalised, institution, account_currency, currency, start, end, opening, closing,
         holder, saved_institution, saved_account, reviewed_holder, reviewed_institution, reviewed_account) in rows:
        known = accounts.get(account_id)
        if known is None:
            digits, masked = account_identity(printed or normalised)
            known = accounts[account_id] = KnownAccount(key=str(account_id), account=printed or normalised or '',
                digits=digits, masked=masked, institution=institution or '', currency=account_currency or '')
        known.statements.append(SavedStatement(currency=currency or '',
            period_start=start.isoformat() if start else '', period_end=end.isoformat() if end else '',
            institution=(reviewed_institution if reviewed_institution is not None else saved_institution) or institution or '',
            holder=(reviewed_holder if reviewed_holder is not None else holder) or '',
            account_number=(reviewed_account if reviewed_account is not None else saved_account) or printed or '',
            opening_minor=opening, closing_minor=closing))
        if currency:
            currencies[currency] += 1
    knowledge = CaseKnowledge(accounts=list(accounts.values()), saved_total=sum(currencies.values()))
    if currencies:
        (top, count), *rest = currencies.most_common(2) + [(None, 0)]
        if count > rest[0][1]:
            knowledge.default_currency, knowledge.default_count = top, count
    return knowledge


# ---------------------------------------------------------------------------
# Proposals
# ---------------------------------------------------------------------------

def _plural(n, one, many):
    return f'{n} {one if n == 1 else many}'


def _overlaps(start, end, other_start, other_end):
    if not (start and end and other_start and other_end):
        return False
    return start <= other_end and other_start <= end


def _agrees(value, known_values, same):
    """The statement's value agrees with every value the account's saved statements give."""
    return bool(known_values) and all(same(value, other) for other in known_values)


def matching_accounts(values, knowledge):
    """(candidates, matched field names) for the statement's account identity, fail closed."""
    statement = account_identity(values.get('account_number'))
    if not statement[0]:
        return [], set()
    candidates, kinds = [], set()
    for known in knowledge.accounts:
        kind = account_match(statement, (known.digits, known.masked))
        if not kind:
            continue
        # A detail both sides print must agree with every saved statement; a
        # conflict excludes the account.
        institutions = known.values('institution') or ([known.institution] if known.institution else [])
        if values.get('institution') and institutions and not _agrees(values['institution'], institutions, same_institution):
            continue
        candidates.append(known)
        kinds.add(kind)
    if not candidates:
        return [], set()
    # Exactly one account identity: the same printed number (full, or the same
    # masked digits) at the same bank. Two full numbers ending in the same
    # visible digits, or a masked and a full record, are not one account. A
    # holder never narrows this choice (it can change while the number stays).
    if len({(k.digits, k.masked, institution_key(k.institution)) for k in candidates}) != 1:
        return candidates, {'ambiguous'}
    if values.get('holder') and any(k.values('holder') and not _agrees(values['holder'], k.values('holder'), same_holder)
                                    for k in candidates):
        return [], set()
    matched = {'account'}
    if values.get('institution') and all(_agrees(values['institution'], k.values('institution') or [k.institution],
                                                 same_institution) for k in candidates):
        matched.add('institution')
    if values.get('holder') and all(_agrees(values['holder'], k.values('holder'), same_holder) for k in candidates):
        matched.add('holder')
    if kinds != {'full'}:
        matched.add('masked')
    return candidates, matched


def _agreed(values, fold):
    """The single value every source gives (most common spelling), or ''."""
    present = [v for v in values if (v or '').strip()]
    if not present or len({fold(v) for v in present}) != 1:
        return ''
    return Counter(present).most_common(1)[0][0]


def _statement_count(candidates):
    return sum(len(k.statements) for k in candidates)


def _bracketed(values, candidates):
    """Saved statements of the account exist both before and after this statement's dates.

    A holder can change while the account number stays (a company renamed, an
    account transferred): the value is established for this period only when it
    is printed on both sides of it.
    """
    start, end = values.get('period_start') or '', values.get('period_end') or ''
    if not start or not end:
        return False
    saved = [s for k in candidates for s in k.statements]
    return (any(s.period_end and s.period_end < start for s in saved)
            and any(s.period_start and s.period_start > end for s in saved))


def _account_key(candidates):
    """Opaque key of the matched account (its record ids), for grouping one account's proposals."""
    return ','.join(sorted(k.key for k in candidates))


def _detail_proposal(name, candidates, matched, values):
    fold = {'institution': institution_key, 'holder': holder_key,
            'account_number': lambda v: account_identity(v)}[name]
    if name == 'account_number':
        # Only a number printed in full is proposed; a masked one proposes nothing.
        found = [v for k in candidates for v in k.values('account_number')]
        if any(account_identity(v)[1] for v in found):
            return None
    else:
        found = [v for k in candidates for v in k.values(name)]
    # Every saved statement must give the value: one without it proposes nothing.
    if len(found) != _statement_count(candidates):
        return None
    value = _agreed(found, fold)
    if not value:
        return None
    statements = _statement_count(candidates)
    other = sorted(matched - {'account', 'masked'})
    exact = ('account number' if 'masked' not in matched else 'masked account number') + ''.join(
        f' and {"bank" if f == "institution" else f}' for f in other)
    independent = len(matched - {'masked', 'ambiguous'})
    confirmed = independent >= 2 and (name != 'holder' or _bracketed(values, candidates))
    basis = 'same_account'
    if (not confirmed and name == 'institution' and autofill_enabled('IDENTITY')
            and identity_proven(values, candidates, matched)):
        # IDENTITY: the bank of the one account whose number the statement prints.
        confirmed, basis = True, 'same_account_number'
    return dict(value=value, basis=basis, confirmed=confirmed, account_key=_account_key(candidates),
                label=f"same account's {_plural(statements, 'saved statement', 'saved statements')} ({exact} match)",
                statements=statements, matched=sorted(matched - {'ambiguous'}))


def _currency_proposal(values, candidates, matched, knowledge):
    """The currency proposal: printed elsewhere on the statement first, unless the same account confirms it.

    A currency the same statement prints in its holdings is proposed with its
    page (one click). Where the account's saved statements would confirm the
    same currency automatically, that confirmation stands; where they give
    another currency, the printed one is proposed and nothing is confirmed.
    """
    printed = values.get('printed_currency') or {}
    other = _account_or_case_currency(values, candidates, matched, knowledge)
    if (not printed and (other is None or not other['confirmed'])
            and case_currency_assumable(values, knowledge)
            and (other is None or str(other['value']).upper() == knowledge.default_currency.upper())):
        return _case_currency(knowledge)
    if not printed.get('value') or (other and other['confirmed'] and other['value'] == printed['value']):
        return other
    return dict(value=printed['value'], basis='printed_on_statement', confirmed=False,
                label=f"printed in this statement's holdings on page {printed.get('page_number')}",
                statements=0, matched=[], page_number=printed.get('page_number'),
                cited=dict(page_number=printed.get('page_number'), table_index=printed.get('table_index'),
                           row_index=printed.get('row_index'), expected_text=printed.get('expected_text')))


def _account_or_case_currency(values, candidates, matched, knowledge):
    if candidates and 'ambiguous' not in matched:
        currencies = [s.currency for k in candidates for s in k.statements] + [k.currency for k in candidates if k.currency]
        value = _agreed(currencies, str.upper)
        statements = _statement_count(candidates)
        if value:
            start, end = values.get('period_start') or '', values.get('period_end') or ''
            same_dates = any(_overlaps(start, end, s.period_start, s.period_end) for k in candidates for s in k.statements)
            independent = len(matched - {'masked', 'ambiguous'})
            confirmed = (statements >= MIN_AGREEING_STATEMENTS and independent >= 2 and not same_dates)
            label = f"same account's {_plural(statements, 'saved statement', 'saved statements')}"
            if statements > 1:
                label += ', all ' + value
            basis = 'same_account'
            if ACCOUNT_CURRENCY and values.get('brokerage_cash_ledger') and not values.get('printed_currency'):
                # (b') The account's one established currency: one saved statement establishes it.
                confirmed = statements >= 1 and independent >= 2 and not same_dates
                basis, label = ACCOUNT_CURRENCY_BASIS, 'account currency: ' + label
            if (not confirmed and autofill_enabled('CURRENCY') and not values.get('printed_currency')
                    and statements >= 1 and not same_dates
                    and (independent >= 2 or identity_proven(values, candidates, matched))):
                # CURRENCY: the account's one currency, every saved statement of it agreeing.
                confirmed, basis = True, AUTOFILL_CURRENCY_BASIS
                if not label.startswith('account currency: '):
                    label = 'account currency: ' + label
            return dict(value=value, basis=basis, confirmed=confirmed, label=label, statements=statements,
                        matched=sorted(matched), same_dates_saved=same_dates, account_key=_account_key(candidates))
    if knowledge.default_currency:
        return dict(value=knowledge.default_currency, basis='case_default', confirmed=False,
                    label=f"the case's usual currency ({knowledge.default_count} of "
                          f"{_plural(knowledge.saved_total, 'saved statement', 'saved statements')})",
                    statements=knowledge.default_count, matched=[])
    return None


def case_currency_assumable(values, knowledge):
    """True when the case's usual currency may fill a statement's empty currency with no click.

    Every condition must hold (fail closed): the switch is on; the statement has
    no currency and nothing in its holdings; its reading recorded the currency
    markers it prints (``currency_marks``; an older reading has none and is
    refused) and none names one currency, not even the case's own (a bare '$'
    allows several, including the case's usual one); that currency is a clear
    majority of the case's saved statements; and no account the statement could
    be (matched by identity, ambiguous included, or sharing its printed number's
    digits whatever its bank or holder) has a saved statement or an account
    record in another currency.
    """
    if not autofill_enabled('CASE_CURRENCY') or knowledge is None or not knowledge.default_currency:
        return False
    default = knowledge.default_currency.upper()
    if str(values.get('currency') or '').strip() or values.get('printed_currency'):
        return False
    marks = values.get('currency_marks')
    if not isinstance(marks, list) or not all(
            isinstance(mark, list) and len(mark) > 1 and all(isinstance(c, str) for c in mark)
            and default in {c.upper() for c in mark} for mark in marks):
        return False  # a marker naming one currency (even the case's own) is a printed currency
    if (knowledge.saved_total < CASE_CURRENCY_MIN_SAVED
            or knowledge.default_count <= CASE_CURRENCY_SHARE * knowledge.saved_total):
        return False
    candidates, _ = matching_accounts(dict(values, currency=''), knowledge)
    # Any account sharing the printed number's digits too, whatever its bank or holder reads.
    number = account_identity(values.get('account_number'))
    candidates = list(candidates) + [k for k in knowledge.accounts if account_match(number, (k.digits, k.masked))]
    established = {c.upper() for k in candidates for c in [s.currency for s in k.statements] + [k.currency] if c}
    return established <= {default}


def _case_currency(knowledge):
    return dict(value=knowledge.default_currency, basis=CASE_CURRENCY_BASIS, confirmed=True,
                label=CASE_CURRENCY_LABEL, statements=knowledge.default_count, matched=[])


def propose(values, knowledge, fields=None):
    """{field: proposal} for each empty field of a statement's details (``values`` keys as in FIELDS)."""
    fields = enabled_fields() if fields is None else fields
    wanted = [name for name in fields if not str(values.get(name) or '').strip()]
    if 'account_number' in fields and account_identity(values.get('account_number'))[1]:
        # Only part of the number is printed: the full number of the one
        # matching account is proposed (the masked digits stay the identity).
        wanted.append('account_number')
    if not wanted or knowledge is None:
        return {}
    candidates, matched = matching_accounts(values, knowledge)
    result = {}
    for name in wanted:
        if name == 'currency':
            proposal = _currency_proposal(values, candidates, matched, knowledge)
        elif candidates and 'ambiguous' not in matched:
            proposal = _detail_proposal(name, candidates, matched, values)
        else:
            proposal = None
        if proposal:
            result[name] = dict(proposal, field=name, version=VERSION)
    return result


def summary_values(summary):
    """Statement details of a projected batch summary, under the FIELDS names."""
    balances = next((check for check in summary.get('checks') or []
                     if isinstance(check, dict) and check.get('kind') == 'closing_balance'), None) or {}
    return dict(currency=summary.get('currency') or '', institution=summary.get('institution') or '',
                holder=summary.get('holder') or '', account_number=summary.get('account') or '',
                period_start=summary.get('period_start') or '', period_end=summary.get('period_end') or '',
                printed_currency=summary.get('printed_currency') or None,
                currency_marks=summary.get('currency_marks') if isinstance(summary.get('currency_marks'), list) else None,
                brokerage_cash_ledger=bool(summary.get('brokerage_cash_ledger')),
                opening_minor=_minor(balances.get('opening_minor')), closing_minor=_minor(balances.get('printed_minor')))


def _minor(value):
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Automatic re-application (LOUPE_FINANCIAL_AUTOFILL_REAPPLY)
# ---------------------------------------------------------------------------
#
# The no-click fill of a held statement whose reading is current (autofill_reapply). It applies only the
# answers the account's saved statements establish, under rules stricter than a one-click confirmation
# (each found necessary by leave-one-out on the saved statements and the truth set):
#
# * currency: the same account's saved statements, all in one currency (basis same_account /
#   account_currency; or the case's usual currency under CASE_CURRENCY, which needs no matched account), nothing printed on the statement giving another, no
#   saved statement of the account on the same dates, AND the statement's printed balances continue the
#   account's ledger: its opening equals the closing of the account's saved statement just before it, or its
#   closing equals the opening of the one just after (a non-zero balance). Several currency sections can share
#   one account number (a section of another currency arriving first among an all-one-currency account): the
#   balance chain is what proves this statement is that ledger.
# * bank and holder: confirmed from the account's agreeing saved statements AND bracketed by them (saved
#   statements both before and after its dates): a bank renamed, or a holder changed, after the last saved
#   statement is not carried onto a statement outside the saved span.
# * account number: never. A masked number's visible digits can be shared by another account of the case
#   that has no saved statement yet; the full number would then be invented.

REAPPLY_BASIS = {'currency': 'account_ledger', 'institution': 'same_account_bracketed',
                 'holder': 'same_account_bracketed'}


def reapply_enabled():
    """Default-on switch LOUPE_FINANCIAL_AUTOFILL_REAPPLY (0/false/off/no turns it off)."""
    return autofill_enabled('REAPPLY')


def balance_chained(values, candidates):
    """The statement's printed balances continue the matched account's saved ledger (see above)."""
    start, end = values.get('period_start') or '', values.get('period_end') or ''
    opening, closing = values.get('opening_minor'), values.get('closing_minor')
    if not start or not end:
        return False
    saved = [s for k in candidates for s in k.statements if s.period_start and s.period_end]
    before = [s for s in saved if s.period_end < start]
    after = [s for s in saved if s.period_start > end]
    if opening not in (None, 0) and before:
        last = max(s.period_end for s in before)
        previous = [s for s in before if s.period_end == last]
        if all(s.closing_minor == opening for s in previous):
            return True
    if closing not in (None, 0) and after:
        first = min(s.period_start for s in after)
        following = [s for s in after if s.period_start == first]
        if all(s.opening_minor == closing for s in following):
            return True
    return False


def automatic_fills(values, proposals, knowledge):
    """{field: proposal} of the confirmed proposals the no-click re-application may save. Fail closed."""
    if not reapply_enabled() or not proposals or knowledge is None:
        return {}
    result = {}
    currency = proposals.get('currency') or {}
    if (currency.get('confirmed') and currency.get('basis') == CASE_CURRENCY_BASIS
            and currency.get('value') == knowledge.default_currency and case_currency_assumable(values, knowledge)):
        # The case's usual currency (checked again here): needs no matched account.
        result['currency'] = dict(currency)
    candidates, matched = matching_accounts(values, knowledge)
    if not candidates or 'ambiguous' in matched:
        return result
    for name, proposal in proposals.items():
        if name in result:
            continue
        if not proposal.get('confirmed') or not proposal.get('value') or name not in REAPPLY_BASIS:
            continue
        if str(values.get(name) or '').strip():
            continue  # a printed or entered value is never replaced
        if name == 'currency':
            if (proposal.get('basis') not in ('same_account', ACCOUNT_CURRENCY_BASIS) or values.get('printed_currency')
                    or proposal.get('same_dates_saved') or not balance_chained(values, candidates)):
                continue
            established = {c.upper() for k in candidates for c in [s.currency for s in k.statements] + [k.currency] if c}
            if established != {proposal['value'].upper()}:
                continue
        elif not _bracketed(values, candidates):
            continue
        result[name] = dict(proposal, basis=REAPPLY_BASIS[name],
                            label=proposal.get('label', '') + ('; balances continue its saved statements'
                                                                if name == 'currency' else '; saved before and after it'))
    return result


def account_currency_conflict(values, knowledge):
    """The account's established currency when a brokerage cash ledger's own currency differs from it, else ''.

    The statement's currency is printed (its holdings); its account (same
    number and bank, any currency) has saved statements in another currency.
    The printed currency is never replaced: the statement is held for a person.
    """
    if not ACCOUNT_CURRENCY or not values.get('brokerage_cash_ledger') or not values.get('currency') or knowledge is None:
        return ''
    candidates, matched = matching_accounts(dict(values, currency=''), knowledge)
    if not candidates or 'ambiguous' in matched:
        return ''
    established = {c.upper() for k in candidates for c in [s.currency for s in k.statements] + [k.currency] if c}
    other = sorted(established - {values['currency'].upper()})
    return ', '.join(other)


def resolves_all(reasons, proposals):
    """True when every actionable reason is a detail with an automatically confirmed proposal."""
    confirmed = {REASONS[name] for name, p in proposals.items() if p.get('confirmed')}
    return bool(reasons) and set(reasons) <= confirmed


def sentence(reason, proposals):
    """The queue sentence for a detail with a proposal, or None."""
    name = next((n for n, r in REASONS.items() if r == reason), None)
    proposal = proposals.get(name) if name else None
    if not proposal:
        return None
    label = LABELS[name]
    if proposal.get('confirmed'):
        return f'{label} filled: {proposal["value"]} ({proposal["label"]})'
    return f'{label} not printed: {proposal["value"]} proposed ({proposal["label"]}). Confirm it'


# ---------------------------------------------------------------------------
# Applying confirmed proposals (write side: only through the details save)
# ---------------------------------------------------------------------------

SYSTEM_NAME = 'System'
SYSTEM_EMAIL = 'field-proposals@system.local'


def apply_confirmed_proposals(session, *, case_id, entries, apply=False, actor=None, owned_batch_id=None):
    """Save automatically confirmed proposals of queue entries through the statement-details save.

    ``entries`` are review-queue entries (``case_review_queue``) carrying
    ``proposals``. Only confirmed proposals are applied, only to fields that are
    still empty (mode ``fill_missing``), grouped so each identical change is
    one save. Dry run unless ``apply``: returns what would change. Each save is
    audited in the file's account-detail history with the System actor and the
    proposal's source; an investigator replaces any value in the same dialog.
    """
    import uuid
    from services.financial import bulk_statement_details as bulk
    from services.financial.decisions import Actor
    actor = actor or Actor(name=SYSTEM_NAME, email=SYSTEM_EMAIL)
    groups = {}
    for entry in entries:
        if not entry.get('batch_id') or not entry.get('file_id'):
            continue
        confirmed = {name: p for name, p in (entry.get('proposals') or {}).items() if p.get('confirmed')}
        if not confirmed:
            continue
        changes = tuple(sorted((name, p['value']) for name, p in confirmed.items()))
        basis = '; '.join(f'{LABELS[name]} {p["value"]}: {p["label"]}' for name, p in sorted(confirmed.items()))
        groups.setdefault(changes, dict(basis=basis, entries=[]))['entries'].append(entry)
    report = dict(groups=[], statements=0, saved=0, failed=0, apply=bool(apply))
    for changes, group in groups.items():
        cache = {}
        targets = []
        for entry in group['entries']:
            target = bulk.Target(file_id=entry['file_id'], statement_id=entry.get('statement_id') or None,
                                 revision='0' * 64)
            try:
                row, _ = bulk._load(session, case_id, target, cache, stored=True)
            except Exception as error:  # noqa: BLE001 - reported, the rest continue
                report['failed'] += 1
                report['groups'].append(dict(changes=dict(changes), error=str(error), statements=1))
                continue
            targets.append(bulk.Target(file_id=entry['file_id'], statement_id=entry.get('statement_id') or None,
                                       revision=row['revision']))
        if not targets:
            continue
        request_id = uuid.uuid5(uuid.NAMESPACE_URL, f'{VERSION}:{case_id}:{changes}:'
                                + ','.join(sorted(f'{t.file_id}:{t.statement_id}' for t in targets)))
        # A masked account number is replaced by the full one; every other
        # change fills an empty field only.
        mode = 'replace' if 'account_number' in dict(changes) else 'fill_missing'
        request = bulk.BulkEdit(targets=targets, changes=bulk.Changes(**dict(changes)), mode=mode,
                                request_id=request_id)
        line = dict(changes=dict(changes), basis=group['basis'], statements=len(targets))
        try:
            preview = bulk.preview(session, case_id=case_id, request=request)
            line['would_update'] = preview['updated']
            if apply:
                request = request.model_copy(update=dict(preview_revision=preview['preview_revision'],
                                                         basis=group['basis']))
                saved = bulk.save(session, case_id=case_id, request=request, actor=actor,
                                  owned_batch_id=owned_batch_id)
                line['updated'] = saved['updated']
                report['saved'] += saved['updated']
            else:
                session.rollback()
        except Exception as error:  # noqa: BLE001 - reported, the rest continue
            session.rollback()
            line['error'] = str(error)
            report['failed'] += len(targets)
        report['statements'] += len(targets)
        report['groups'].append(line)
    return report
