"""Suggested connected payments for one payment, a case-wide payment search, and the next step of a money trail.

Opening "Link transfer or follow this payment" on a payment lists, strongest first, the payments in this case that
may be its other side (``suggest_connected``) or, for money that arrived, the payments that took it onward out of the
receiving account (``suggest_onward``). Every candidate carries a strength computed by the stated rule
(:data:`RULE`, :data:`ONWARD_RULE`) on the app's one scale (``services.match_strength``: strong, moderate, weak,
faint) and its reasons in one plain line. Nothing here links anything: a person links a suggestion through the saved
money-trail path, which records which rule suggested it (``TrailRequest.suggested_by``).

Scope and cost. Every query is bounded by ``case_id`` (and the source document and account are held to the same case),
so a case never sees another case's payments. Candidates are found in SQL (by date window, direction and the printed
reference, account number and name signals), never by loading the ledger. Only current readings count: admitted,
not superseded (a corrected payment is matched on its corrected value; the original stays on its own page) and from an
admitted statement. Credit-card activity is not offered, because a money trail refuses it.

No silent cap. Every candidate is listed, paged with its count; the date window is stated with the count of same-amount
payments outside it (``left_out``).
"""
from __future__ import annotations

import re
import time
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import func, or_, select

from postgres.models.financial import FinancialAccount, FinancialSourceDocument, FinancialTransaction
from postgres.models.financial_money_trails import FinancialMoneyTrail
from services.financial.linkage import NAME_SIMILARITY_THRESHOLD, name_similarity
from services.financial.money import get_currency
from services.match_strength import LEVELS, counts, rank

WINDOW_DAYS = 31          # amount-led candidates are compared within this many days either side
SIGNAL_DAYS = 7           # a name match alone (no amount, no reference) is offered only this close
ONWARD_DAYS = 31          # onward payments out of the receiving account, this many days after the receipt
FEE_SHARE = Decimal('0.02')   # amounts within 2 % are a possible fee or charge
FX_SHARE = Decimal('0.03')    # an implied rate within 3 % of a rate already saved in this case for the month
COMMON_REFERENCE = 25    # a code printed on more than this many payments of the case is a common code, not a reference
PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

RULE = (
    "Suggested other sides of a payment: payments in this case going the other way (money in for money out) in "
    "another account. Amount: the same currency and amount (3); within 2%%, a possible fee or charge (2); two "
    "payments in one account that add up to it, a possible split (2); another currency at an implied rate within 3%% "
    "of a rate already saved in this case for that month, or a printed line that shows the other amount (2). Date: "
    "same day (3), within 3 days (2), within 31 days (1), further (0). Name: the other side's name against the other "
    "account's holder, both agree (3), one agrees (2), alike but under %.2f (1). Evidence: a shared reference in the "
    "printed lines, a line that names the other account's number within %d days, being the only same-amount payment. A reference is a run of 6 or more digits with at least 5 significant ones, or the bank reference; a code printed on more than %d payments of the case is common, not a reference, and is named as such. Strong: a "
    "matching amount within 3 days with a name or evidence. Moderate: a matching amount within 3 days, or a matching "
    "amount with a name or evidence, or evidence within 3 days with a name. Weak: a matching amount within %d days, or "
    "evidence, or a name within %d days. Faint: anything else listed. Amount matches are compared within %d days "
    "either side and the same-amount payments further away are counted; a reference or account number is searched "
    "across the whole case. A suggestion is a possibility to check, never a link."
    % (NAME_SIMILARITY_THRESHOLD, WINDOW_DAYS, COMMON_REFERENCE, WINDOW_DAYS, SIGNAL_DAYS, WINDOW_DAYS))

ONWARD_RULE = (
    "Onward payments: money out of the receiving account (including accounts consolidated with it) in the receipt's "
    "currency, from the receipt's date to %d days after it. Amount: the same as the receipt (3); within 2%% (2); two "
    "payments adding up to it (2); part of it (1); more than it (0). Date: same day (3), within 3 days (2), within 31 "
    "days (1). Strong: the same amount within 3 days. Moderate: a matching amount (3 or 2) within 31 days. Weak: part "
    "of the receipt. Faint: more than the receipt. The account's other money in the same days can also fund these "
    "payments; an onward payment is a possibility to check, not proof of where the money went." % ONWARD_DAYS)

_DIGITS = re.compile(r'\d{6,}')
_REF_TOKEN = re.compile(r'[A-Z0-9]{6,}')


class LinkSuggestionError(Exception):
    def __init__(self, message, status_code=422):
        super().__init__(message)
        self.status_code = status_code


T, D, A = FinancialTransaction, FinancialSourceDocument, FinancialAccount
_COLUMNS = (T.id, T.case_id, T.account_id, T.ref_id, T.amount_minor, T.currency, T.direction, T.ordering_date,
            T.description, T.counterparty_raw, T.bank_reference, T.provenance['date_basis'].as_string(),
            A.institution_name, A.identifier_as_printed, A.identifier_normalised, A.holder_name)


def _current(case_id):
    """Current bank-account payments of this case, every table held to the case."""
    return (select(*_COLUMNS).join(D, D.id == T.source_document_id).join(A, A.id == T.account_id)
            .where(T.case_id == case_id, D.case_id == case_id, A.case_id == case_id, T.ledger_status == 'admitted',
                   T.superseded_by_id.is_(None), D.status == 'admitted', T.amount_minor > 0,
                   or_(A.account_type.is_(None), A.account_type != 'credit_card')))


def _row(r):
    (id, case_id, account_id, ref_id, amount, currency, direction, day, description, counterparty, bank_reference,
     date_basis, institution, identifier, identifier_normalised, holder) = r
    return dict(id=str(id), case_id=str(case_id), account_id=str(account_id), ref_id=ref_id, amount_minor=int(amount),
                currency=currency, direction=direction, day=None if date_basis == 'statement_end_ordering_only' else day,
                ordering_date=day, description=description or '', counterparty=counterparty or '',
                bank_reference=bank_reference or '', institution=institution or '', identifier=identifier or '',
                identifier_digits=re.sub(r'\D', '', identifier_normalised or identifier or ''), holder=holder or '')


def _exponent(currency):
    try:
        return get_currency(currency).exponent
    except Exception:
        return 2


def amount_text(minor, currency):
    exp = _exponent(currency)
    value = Decimal(int(minor)).scaleb(-exp)
    return '{:,.{}f} {}'.format(value, exp, currency)


def _plain_amount(minor, currency):
    """The amount as a statement prints it, without grouping or currency (for printed-line matching)."""
    exp = _exponent(currency)
    return '{:.{}f}'.format(Decimal(int(minor)).scaleb(-exp), exp)


def _line(p):
    return ' '.join(x for x in (p['description'], p['counterparty'], p['bank_reference']) if x)


def _account_label(p):
    tail = p['identifier'][-4:] if p['identifier'] else ''
    return ' · '.join(x for x in (p['holder'], p['institution'], ('…' + tail) if tail else '') if x) or (
        'Account ' + p['account_id'][:8])


def _references(p):
    """Reference-like tokens of a payment's printed line: runs of 6+ digits, and the bank reference itself."""
    text = _line(p).upper()
    tokens = {t for t in _DIGITS.findall(text) if len(t.lstrip('0')) >= 5 and len(set(t)) > 2}
    ref = re.sub(r'\s+', '', p['bank_reference'].upper())
    if len(ref) >= 6 and _REF_TOKEN.fullmatch(ref) and len(ref.lstrip('0')) >= 5 and len(set(ref)) > 2:
        tokens.add(ref)
    # a printed amount or a date run together is not a reference
    tokens.discard(re.sub(r'\D', '', _plain_amount(p['amount_minor'], p['currency'])))
    return tokens


def _view(p, linked):
    """One payment in the list format: who to whom, when, how much, which account."""
    holder = p['holder'] or _account_label(p)
    other = p['counterparty'] or (p['description'][:80] if p['description'] else 'not printed')
    sender, receiver = (holder, other) if p['direction'] == 'debit' else (other, holder)
    return dict(id=p['id'], ref_id=p['ref_id'], date=p['ordering_date'].isoformat() if p['ordering_date'] else None,
                dated=p['day'] is not None, direction=p['direction'], amount_minor=str(p['amount_minor']),
                currency=p['currency'], amount=amount_text(p['amount_minor'], p['currency']),
                account_id=p['account_id'], account_label=_account_label(p), from_name=sender, to_name=receiver,
                description=p['description'], counterparty=p['counterparty'], bank_reference=p['bank_reference'],
                already_linked=p['id'] in linked)


def _gap(a, b):
    if a['ordering_date'] is None or b['ordering_date'] is None:
        return None
    return (b['ordering_date'] - a['ordering_date']).days


def _when(gap, *, undated=False):
    if gap is None:
        return 'no date to compare'
    words = 'same day' if gap == 0 else '%d day%s %s' % (abs(gap), '' if abs(gap) == 1 else 's',
                                                         'later' if gap > 0 else 'earlier')
    return words + (' (statement date only)' if undated else '')


def _date_fit(gap):
    if gap is None:
        return 0
    g = abs(gap)
    return 3 if g == 0 else 2 if g <= 3 else 1 if g <= 31 else 0


_SIMILAR = {}


def _similar(x, y):
    key = (x, y)
    if key not in _SIMILAR:
        if len(_SIMILAR) > 50000:
            _SIMILAR.clear()
        _SIMILAR[key] = name_similarity(x or None, y or None)
    return _SIMILAR[key]


def _name_fit(a, b):
    scores = [s for s in (_similar(a['counterparty'], b['holder']), _similar(b['counterparty'], a['holder']))
              if s is not None]
    agree = [s for s in scores if s >= NAME_SIMILARITY_THRESHOLD]
    if len(agree) == 2:
        return 3, scores
    if agree:
        return 2, scores
    if scores and max(scores) >= 0.5:
        return 1, scores
    return 0, scores


def _level(amount, when, name, evidence):
    if amount >= 2 and when >= 2 and (name >= 2 or evidence >= 1):
        return 'strong'
    if (amount >= 2 and when >= 2) or (amount >= 2 and (name >= 2 or evidence >= 1)) or (
            evidence >= 1 and when >= 2 and name >= 2):
        return 'moderate'
    if (amount >= 2 and when >= 1) or evidence >= 1 or name >= 2:
        return 'weak'
    return 'faint'


def _onward_level(amount, when):
    if amount == 3 and when >= 2:
        return 'strong'
    if amount >= 2 and when >= 1:
        return 'moderate'
    if amount >= 1:
        return 'weak'
    return 'faint'


def _canonical(session, case_id):
    from services.financial.account_consolidation import canonical_map
    return {str(k): str(v) for k, v in canonical_map(session, case_id).items()}


def _linked(session, case_id):
    out = set()
    for details in session.scalars(select(FinancialMoneyTrail.details).where(
            FinancialMoneyTrail.case_id == case_id, FinancialMoneyTrail.active.is_(True),
            FinancialMoneyTrail.kind == 'transfer')):
        out.update(p['key'] for p in (details or {}).get('payments') or [])
    return out


def _saved_rates(session, case_id):
    """Rates implied by transfers already saved in this case: {(from, to, 'YYYY-MM'): [rate]}."""
    rates = {}
    for details in session.scalars(select(FinancialMoneyTrail.details).where(
            FinancialMoneyTrail.case_id == case_id, FinancialMoneyTrail.active.is_(True),
            FinancialMoneyTrail.kind == 'transfer')):
        rate = (details or {}).get('implied_exchange_rate')
        pays = {p.get('direction'): p for p in (details or {}).get('payments') or []}
        if not rate or 'debit' not in pays or 'credit' not in pays:
            continue
        month = str(pays['debit'].get('ordering_date') or '')[:7]
        try:
            rates.setdefault((pays['debit']['currency'], pays['credit']['currency'], month), []).append(Decimal(rate))
        except (InvalidOperation, KeyError):
            continue
    return rates


def _anchor(session, case_id, transaction_id):
    try:
        ident = transaction_id if isinstance(transaction_id, UUID) else UUID(str(transaction_id))
    except (TypeError, ValueError) as exc:
        raise LinkSuggestionError('Choose a payment of this case.', 404) from exc
    row = session.execute(_current(case_id).where(T.id == ident)).first()
    if row is None:
        raise LinkSuggestionError('This payment is not a current bank-account payment of this case. Open its current '
                                  'reading and try again.', 404)
    return _row(row)


def _page(items, page, page_size):
    if type(page) is not int or page < 1 or type(page_size) is not int or not 1 <= page_size <= MAX_PAGE_SIZE:
        raise LinkSuggestionError('Use a page from 1 and a page size from 1 to %d.' % MAX_PAGE_SIZE)
    start = (page - 1) * page_size
    return dict(total=len(items), page=page, page_size=page_size, pages=max(1, -(-len(items) // page_size)),
                by_level=counts(items), candidates=items[start:start + page_size])


class _Grader:
    """Grades payments as possible other sides of one anchor payment (the rule in :data:`RULE`)."""

    def __init__(self, session, case_id, anchor):
        self.anchor = anchor
        self.canonical = _canonical(session, case_id)
        self.linked = _linked(session, case_id)
        self.rates = None
        self.session, self.case_id = session, case_id
        self.group = self.canonical.get(anchor['account_id'], anchor['account_id'])
        self.refs = _references(anchor)
        self.common = {}
        self.line = _line(anchor).upper()
        self.same_amount = 0
        self.sums = {}

    def other_account(self, p):
        return self.canonical.get(p['account_id'], p['account_id']) != self.group

    def prepare(self, rows):
        """Counts and split sums over the window rows (the 'only same-amount payment' and 'adds up to it' fits)."""
        a = self.anchor
        same = [p for p in rows if p['currency'] == a['currency'] and p['amount_minor'] == a['amount_minor']]
        self.same_amount = len(same)
        by_account = {}
        for p in rows:
            if p['currency'] == a['currency'] and p['amount_minor'] < a['amount_minor']:
                by_account.setdefault(p['account_id'], []).append(p)
        for acct, ps in by_account.items():
            seen = {}
            for p in sorted(ps, key=lambda x: (x['ordering_date'] or date.min, x['id'])):
                partner = seen.get(a['amount_minor'] - p['amount_minor'])
                if partner and abs(_gap(partner, p) or 0) <= 7:
                    self.sums.setdefault(p['id'], partner)
                    self.sums.setdefault(partner['id'], p)
                seen.setdefault(p['amount_minor'], p)

    def amount(self, p):
        a = self.anchor
        if p['currency'] == a['currency']:
            if p['amount_minor'] == a['amount_minor']:
                return 3, 'same amount'
            diff = abs(p['amount_minor'] - a['amount_minor'])
            if Decimal(diff) <= FEE_SHARE * Decimal(max(p['amount_minor'], a['amount_minor'])):
                return 2, 'amount differs by %s (a possible fee or charge)' % amount_text(diff, a['currency'])
            partner = self.sums.get(p['id'])
            if partner:
                return 2, 'with %s (%s) it adds up to the amount, a possible split' % (
                    partner['ref_id'], amount_text(partner['amount_minor'], partner['currency']))
            return 0, None
        printed_p = _plain_amount(p['amount_minor'], p['currency'])
        printed_a = _plain_amount(a['amount_minor'], a['currency'])
        if printed_a in _line(p) or printed_p in _line(a):
            return 2, 'other currency; a printed line shows the other amount'
        if self.rates is None:
            self.rates = _saved_rates(self.session, self.case_id)
        debit, credit = (a, p) if a['direction'] == 'debit' else (p, a)
        month = (debit['ordering_date'].isoformat() if debit['ordering_date'] else '')[:7]
        implied = (Decimal(credit['amount_minor']).scaleb(-_exponent(credit['currency']))
                   / Decimal(debit['amount_minor']).scaleb(-_exponent(debit['currency'])))
        for saved in self.rates.get((debit['currency'], credit['currency'], month), []):
            if saved and abs(implied - saved) <= FX_SHARE * saved:
                return 2, 'other currency at %s, within 3%% of the rate saved in this case for %s' % (
                    format(implied, '.6g'), month)
        return 0, None

    def grade(self, p):
        """``None`` when no rule connects the payment; else the graded candidate."""
        a = self.anchor
        amount, amount_words = self.amount(p)
        gap = _gap(a, p)
        when = _date_fit(gap)
        name, scores = _name_fit(a, p)
        evidence = []
        near = gap is not None and abs(gap) <= WINDOW_DAYS
        shared = sorted((self.refs - set(self.common)) & _references(p))
        if shared:
            evidence.append('reference %s in both' % shared[0] if len(shared) == 1 else
                            'references %s in both' % ', '.join(shared[:3]))
        tail = p['identifier_digits'][-6:] if len(p['identifier_digits']) >= 6 else (
            p['identifier_digits'] if len(p['identifier_digits']) >= 4 else '')
        if near and tail and tail in re.sub(r'[\s-]', '', self.line):
            evidence.append('this payment\'s line names account …%s' % tail[-4:])
        mine = a['identifier_digits'][-6:] if len(a['identifier_digits']) >= 6 else ''
        if near and mine and mine in re.sub(r'[\s-]', '', _line(p).upper()):
            evidence.append('its line names this account …%s' % mine[-4:])
        if amount == 3 and self.same_amount == 1:
            evidence.append('the only same-amount payment within %d days' % WINDOW_DAYS)
        strong_evidence = [e for e in evidence if not e.startswith('the only')]
        if not (amount >= 2 or strong_evidence or (name >= 2 and gap is not None and abs(gap) <= SIGNAL_DAYS)):
            return None
        names = {3: 'both names agree with the account holders', 2: 'a name agrees with the other account\'s holder',
                 1: 'names alike but not agreeing', 0: None}[name]
        reasons = [x for x in (amount_words, _when(gap, undated=p['day'] is None or a['day'] is None), *evidence,
                               names) if x]
        if p['id'] in self.linked:
            reasons.append('already in a saved transfer')
        level = _level(amount, when, name, len(evidence))
        return dict(_view(p, self.linked), level=level, rule='connected_payment', reasons='; '.join(reasons),
                    fits=dict(amount=amount, date=when, name=name, evidence=len(evidence)),
                    gap_days=gap, name_similarity=[round(s, 3) for s in scores])


def _sort_key(c):
    return (rank(c['level']), -c['fits']['amount'], -(c['fits']['date'] + c['fits'].get('name', 0)),
            -c['fits'].get('evidence', 0), abs(c['gap_days']) if c['gap_days'] is not None else 10 ** 6,
            c['ref_id'] or '', c['id'])


def suggest_connected(session, *, case_id, transaction_id, page=1, page_size=PAGE_SIZE):
    """Ranked possible other sides of one payment, across the whole case (see :data:`RULE`)."""
    started = time.monotonic()
    anchor = _anchor(session, case_id, transaction_id)
    grader = _Grader(session, case_id, anchor)
    other = 'credit' if anchor['direction'] == 'debit' else 'debit'
    rows = {}
    window = []
    base = _current(case_id).where(T.direction == other)
    if anchor['ordering_date'] is not None:
        lo = anchor['ordering_date'] - timedelta(days=WINDOW_DAYS)
        hi = anchor['ordering_date'] + timedelta(days=WINDOW_DAYS)
        window = [p for p in map(_row, session.execute(base.where(T.ordering_date >= lo, T.ordering_date <= hi)))
                  if grader.other_account(p)]
        rows.update((p['id'], p) for p in window)
    # a printed reference or this account's number, anywhere in the case
    probes = sorted(grader.refs)
    if probes:
        conditions = [col.ilike('%' + token + '%') for token in probes
                      for col in (T.description, T.counterparty_raw, T.bank_reference)]
        found = [p for p in map(_row, session.execute(_current(case_id).where(or_(*conditions))))]
        hits = {t: sum(1 for p in found if t in _line(p).upper().replace(' ', '') or t in _line(p).upper())
                for t in probes}
        grader.common = {t: n for t, n in hits.items() if n > COMMON_REFERENCE}
        for p in found:
            if p['direction'] == other and grader.other_account(p) and (_references(p) & (grader.refs - set(grader.common))):
                rows.setdefault(p['id'], p)
    grader.prepare(window)
    candidates = [c for c in (grader.grade(p) for p in rows.values()) if c is not None]
    candidates.sort(key=_sort_key)
    # same amount outside the window: counted and stated, never dropped silently
    beyond = 0
    if anchor['ordering_date'] is not None:
        beyond = session.scalar(select(func.count()).select_from(
            _current(case_id).where(T.direction == other, T.currency == anchor['currency'],
                                    T.amount_minor == anchor['amount_minor'],
                                    or_(T.ordering_date < anchor['ordering_date'] - timedelta(days=WINDOW_DAYS),
                                        T.ordering_date > anchor['ordering_date'] + timedelta(days=WINDOW_DAYS)))
            .subquery())) or 0
    out = _page(candidates, page, page_size)
    return dict(case_id=str(case_id), mode='connected', anchor=_view(anchor, grader.linked), rule=RULE,
                compared=len(rows), window_days=WINDOW_DAYS,
                left_out=dict(same_amount_beyond_window=int(beyond),
                              common_codes=grader.common,
                              common_words=('Not used as a reference, being printed on more than %d payments of this '
                                            'case: %s.' % (COMMON_REFERENCE, ', '.join(
                                                '%s (%d)' % kv for kv in sorted(grader.common.items()))))
                              if grader.common else None,
                              words=('%d more payment%s of the same amount %s more than %d days away; search by '
                                     'amount to see them.' % (beyond, '' if beyond == 1 else 's',
                                                              'is' if beyond == 1 else 'are', WINDOW_DAYS))
                              if beyond else None),
                elapsed_ms=round((time.monotonic() - started) * 1000), **out)


def suggest_onward(session, *, case_id, transaction_id, page=1, page_size=PAGE_SIZE):
    """The next step of a trail: payments out of the account the money arrived in, shortly after (ONWARD_RULE)."""
    started = time.monotonic()
    anchor = _anchor(session, case_id, transaction_id)
    if anchor['direction'] != 'credit':
        raise LinkSuggestionError('Follow the money from where it arrived: choose the receipt in the receiving account '
                                  'first (its suggested other sides are listed).')
    canonical = _canonical(session, case_id)
    linked = _linked(session, case_id)
    group = canonical.get(anchor['account_id'], anchor['account_id'])
    accounts = [UUID(k) for k, v in canonical.items() if v == group] or [UUID(anchor['account_id'])]
    rows = []
    if anchor['ordering_date'] is not None:
        rows = [_row(r) for r in session.execute(_current(case_id).where(
            T.direction == 'debit', T.account_id.in_(accounts), T.currency == anchor['currency'],
            T.ordering_date >= anchor['ordering_date'],
            T.ordering_date <= anchor['ordering_date'] + timedelta(days=ONWARD_DAYS)))]
    sums = {}
    seen = {}
    for p in sorted(rows, key=lambda x: (x['ordering_date'], x['id'])):
        partner = seen.get(anchor['amount_minor'] - p['amount_minor'])
        if partner:
            sums.setdefault(p['id'], partner)
            sums.setdefault(partner['id'], p)
        seen.setdefault(p['amount_minor'], p)
    candidates = []
    for p in rows:
        diff = p['amount_minor'] - anchor['amount_minor']
        if diff == 0:
            amount, words = 3, 'same amount as the receipt'
        elif Decimal(abs(diff)) <= FEE_SHARE * Decimal(anchor['amount_minor']):
            amount, words = 2, 'within 2%% of the receipt (%s %s)' % (
                amount_text(abs(diff), p['currency']), 'more' if diff > 0 else 'less')
        elif p['id'] in sums:
            amount, words = 2, 'with %s (%s) it adds up to the receipt' % (
                sums[p['id']]['ref_id'], amount_text(sums[p['id']]['amount_minor'], p['currency']))
        elif diff < 0:
            amount, words = 1, 'part of the receipt (%s of %s)' % (
                amount_text(p['amount_minor'], p['currency']), amount_text(anchor['amount_minor'], p['currency']))
        else:
            amount, words = 0, 'more than the receipt'
        gap = _gap(anchor, p)
        when = _date_fit(gap)
        reasons = [words, _when(gap, undated=p['day'] is None or anchor['day'] is None)]
        if p['id'] in linked:
            reasons.append('already in a saved transfer')
        candidates.append(dict(_view(p, linked), level=_onward_level(amount, when), rule='onward_payment',
                               reasons='; '.join(reasons), fits=dict(amount=amount, date=when), gap_days=gap,
                               name_similarity=[]))
    candidates.sort(key=_sort_key)
    out = _page(candidates, page, page_size)
    return dict(case_id=str(case_id), mode='onward', anchor=_view(anchor, linked), rule=ONWARD_RULE,
                compared=len(rows), window_days=ONWARD_DAYS, left_out=dict(words=None),
                elapsed_ms=round((time.monotonic() - started) * 1000), **out)


# ---- search --------------------------------------------------------------------------------------------------------

_NUM = r'\d[\d,]*(?:\.\d+)?'
_RANGE = re.compile(r'^(%s)\s*(?:-|\.\.|to)\s*(%s)$' % (_NUM, _NUM))
_PLUSMINUS = re.compile(r'^(%s)\s*(?:±|\+/-|\+-)\s*(%s)$' % (_NUM, _NUM))
_AMOUNT = re.compile(r'^(%s)$' % _NUM)
_DAY = r'\d{4}-\d{2}-\d{2}'
_DAYS = re.compile(r'(%s)\s*(?:\.\.|to)\s*(%s)' % (_DAY, _DAY))
_ONE_DAY = re.compile(r'(%s)' % _DAY)


def _dec(text):
    return Decimal(text.replace(',', ''))


def parse_query(q):
    """One search box: amounts (825.62 exact, 825 whole units, 800-900, 825±10), dates (2024-01-02, or a range with ..
    or 'to') and words (names, references, account numbers). Returns the understood filters and their words."""
    text = ' '.join(str(q or '').split())
    if len(text) > 300:
        raise LinkSuggestionError('Use a search of up to 300 characters.')
    out = dict(amount=None, date_from=None, date_to=None, words=[])
    said = []
    m = _DAYS.search(text)
    if m:
        out['date_from'], out['date_to'] = date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))
        text = (text[:m.start()] + ' ' + text[m.end():]).strip()
    else:
        m = _ONE_DAY.search(text)
        if m:
            out['date_from'] = out['date_to'] = date.fromisoformat(m.group(1))
            text = (text[:m.start()] + ' ' + text[m.end():]).strip()
    if out['date_from']:
        said.append('dated %s' % out['date_from'].isoformat() if out['date_from'] == out['date_to'] else
                    'dated %s to %s' % (out['date_from'].isoformat(), out['date_to'].isoformat()))
    for pattern, kind in ((_PLUSMINUS, 'plusminus'), (_RANGE, 'range')):
        m = pattern.fullmatch(text)
        if m:
            a, b = _dec(m.group(1)), _dec(m.group(2))
            lo, hi = (a - b, a + b) if kind == 'plusminus' else (min(a, b), max(a, b))
            out['amount'] = (max(lo, Decimal(0)), hi)
            said.append('amount %s to %s' % (out['amount'][0], hi))
            text = ''
            break
    tokens = text.split()
    words = []
    for tok in tokens:
        if out['amount'] is None and _AMOUNT.fullmatch(tok) and ('.' in tok or ',' in tok or len(tok.replace(',', '')) <= 7):
            value = _dec(tok)
            if '.' in tok:
                out['amount'] = (value, value)
                said.append('amount exactly %s' % tok)
            else:
                out['amount'] = (value, value + 1 - Decimal('0.000001'))
                said.append('amount %s to %s.99' % (tok, tok))
            # a whole number may also be a reference or account number: search it as a word too
            if '.' not in tok:
                words.append(tok)
            continue
        words.append(tok)
    out['words'] = words
    if words:
        said.append('words: ' + ', '.join('"%s"' % w for w in words))
    if out['amount'] is None and not words and not out['date_from']:
        raise LinkSuggestionError('Type a name, reference, account number, amount or date to search.')
    out['understood'] = '; '.join(said)
    return out


def search_payments(session, *, case_id, q, transaction_id=None, direction=None, account_id=None, page=1,
                    page_size=PAGE_SIZE):
    """Search the whole case's current payments; graded against ``transaction_id`` when one is given."""
    started = time.monotonic()
    parsed = parse_query(q)
    stmt = _current(case_id)
    if direction in ('debit', 'credit'):
        stmt = stmt.where(T.direction == direction)
    if account_id:
        try:
            stmt = stmt.where(T.account_id == UUID(str(account_id)))
        except ValueError as exc:
            raise LinkSuggestionError('Choose an account of this case.') from exc
    if parsed['date_from']:
        stmt = stmt.where(T.ordering_date >= parsed['date_from'], T.ordering_date <= parsed['date_to'])
    amount_only_words = set()
    if parsed['amount'] is not None:
        lo, hi = parsed['amount']
        currencies = [c for c in session.scalars(select(T.currency).where(T.case_id == case_id).distinct())]
        ranges = []
        for currency in currencies:
            exp = _exponent(currency)
            low = int((lo.scaleb(exp)).to_integral_value(rounding='ROUND_CEILING'))
            high = int((hi.scaleb(exp)).to_integral_value(rounding='ROUND_FLOOR'))
            ranges.append((T.currency == currency) & (T.amount_minor >= low) & (T.amount_minor <= high))
        amount_clause = or_(*ranges) if ranges else T.amount_minor < 0
        # a bare whole number may be an amount or a reference: either matches
        numeric = [w for w in parsed['words'] if w.replace(',', '').isdigit()]
        if numeric:
            amount_only_words.update(numeric)
            word = numeric[0].replace(',', '')
            amount_clause = or_(amount_clause, *[col.ilike('%' + word + '%') for col in (
                T.description, T.counterparty_raw, T.bank_reference, T.ref_id, A.identifier_as_printed)])
        stmt = stmt.where(amount_clause)
    for word in parsed['words']:
        if word in amount_only_words:
            continue
        like = '%' + word.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        stmt = stmt.where(or_(*[col.ilike(like, escape='\\') for col in (
            T.description, T.counterparty_raw, T.bank_reference, T.ref_id, A.holder_name, A.institution_name,
            A.identifier_as_printed)]))
    rows = [_row(r) for r in session.execute(stmt)]
    anchor = None
    if transaction_id:
        anchor = _anchor(session, case_id, transaction_id)
        grader = _Grader(session, case_id, anchor)
        rows = [p for p in rows if p['id'] != anchor['id']]
        window = [p for p in rows if p['direction'] != anchor['direction'] and grader.other_account(p)]
        grader.prepare(window)
        in_window = {p['id'] for p in window}
        items = []
        for p in rows:
            graded = grader.grade(p) if p['id'] in in_window else None
            if graded is None:
                gap = _gap(anchor, p)
                why = [_when(gap)]
                if p['direction'] == anchor['direction']:
                    why.append('same direction as this payment')
                elif not grader.other_account(p):
                    why.append('same account as this payment')
                else:
                    why.append('no connecting rule met')
                if p['id'] in grader.linked:
                    why.append('already in a saved transfer')
                graded = dict(_view(p, grader.linked), level='faint', rule='search', reasons='; '.join(why),
                              fits=dict(amount=0, date=_date_fit(gap), name=0, evidence=0), gap_days=gap,
                              name_similarity=[])
            else:
                graded['rule'] = 'search'
            items.append(graded)
        items.sort(key=_sort_key)
        linked = grader.linked
    else:
        linked = _linked(session, case_id)
        items = [dict(_view(p, linked), level=None, rule='search', reasons='matches the search',
                      fits=dict(amount=0, date=0), gap_days=None, name_similarity=[]) for p in rows]
        items.sort(key=lambda c: (c['date'] or '', c['id']), reverse=True)
    out = _page(items, page, page_size)
    if anchor is None:
        out['by_level'] = {}  # nothing to grade against: listed newest first, no strength
    return dict(case_id=str(case_id), mode='search', q=q, understood=parsed['understood'],
                anchor=_view(anchor, linked) if anchor else None, rule=RULE, compared=len(rows),
                elapsed_ms=round((time.monotonic() - started) * 1000), **out)


def grade_payments(session, *, case_id, ids, transaction_id):
    """Named payments (e.g. those a model cited in an answer) in the list format, graded against one payment by the
    same rule. Ids that are not current payments of this case are counted, never shown."""
    started = time.monotonic()
    wanted = []
    for value in ids or []:
        try:
            wanted.append(UUID(str(value)))
        except ValueError:
            continue
    wanted = list(dict.fromkeys(wanted))[:MAX_PAGE_SIZE]
    anchor = _anchor(session, case_id, transaction_id)
    grader = _Grader(session, case_id, anchor)
    rows = [_row(r) for r in session.execute(_current(case_id).where(T.id.in_(wanted)))] if wanted else []
    rows = [p for p in rows if p['id'] != anchor['id']]
    window = [p for p in rows if p['direction'] != anchor['direction'] and grader.other_account(p)]
    grader.prepare(window)
    items = []
    for p in rows:
        graded = grader.grade(p) if p in window else None
        if graded is None:
            gap = _gap(anchor, p)
            graded = dict(_view(p, grader.linked), level='faint', rule='named', reasons='; '.join(
                [_when(gap), 'no connecting rule met' if p in window else
                 ('same direction as this payment' if p['direction'] == anchor['direction'] else
                  'same account as this payment')]), fits=dict(amount=0, date=_date_fit(gap), name=0, evidence=0),
                gap_days=gap, name_similarity=[])
        graded['rule'] = 'named'
        items.append(graded)
    items.sort(key=_sort_key)
    out = _page(items, 1, MAX_PAGE_SIZE)
    return dict(case_id=str(case_id), mode='named', anchor=_view(anchor, grader.linked), rule=RULE,
                not_found=len(wanted) - len(rows) - (1 if UUID(anchor['id']) in wanted else 0),
                compared=len(rows), elapsed_ms=round((time.monotonic() - started) * 1000), **out)


assert LEVELS == ('strong', 'moderate', 'weak', 'faint')
