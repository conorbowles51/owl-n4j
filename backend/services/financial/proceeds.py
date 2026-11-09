"""Proceeds calculator (scenario 8; agent-proposals E): deterministic, every assumption its own judgement call.

A calculation multiplies a volume by assumptions:

    turnover = messages x share of messages that are deals x deals per message x price per deal

Each assumption is a judgement call on subject ``calculation`` (rule ``assumption.proceeds``, target the assumption)
that a named person sets with a stated source and a low and high value. The case agent may propose one (origin
``agent``, open); it is used only once a person confirms it. Changing an assumption records a new call and marks the
one it replaces ``corrected`` with the replacement named: the earlier value stays visible, only the current one is
used.

The result is a range (every low, every high, and the middle of each), labelled **estimate, not measured**, with how
it moves when each assumption alone goes from its low to its high. Arithmetic is exact (fractions), rounded once to
minor units at the end. Nothing is stored: the result is computed on every read from the current calls.

Beside the turnover, the cash deposits of the period in the categories the person chose are summed from the verified
ledger only (proof classes p0 to p2); deposits in p3 rows are counted and said to be left out, never summed in.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from fractions import Fraction
from typing import Any, Iterable, Optional

from sqlalchemy import select

RULE = 'assumption.proceeds'
LABEL = 'estimate, not measured'
VERIFIED_CLASSES = ('p0', 'p1', 'p2')
# key -> (what a person reads, unit, kind of value)
ASSUMPTIONS = {
    'messages': ('Messages on the deal line in the period', 'messages', 'count'),
    'share_deals': ('Share of those messages that are deals', '%', 'percent'),
    'deals_per_message': ('Deals per deal message', 'deals', 'ratio'),
    'price_per_deal': ('Price per deal', 'money', 'money'),
}
ORDER = tuple(ASSUMPTIONS)


class ProceedsError(ValueError):
    def __init__(self, message, status_code=422):
        super().__init__(message)
        self.status_code = status_code


def _uuid(value):
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _value(key, raw) -> Fraction:
    kind = ASSUMPTIONS[key][2]
    try:
        value = Fraction(str(raw).strip().replace(',', ''))
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise ProceedsError(f'{ASSUMPTIONS[key][0]}: give a number.') from exc
    if value < 0:
        raise ProceedsError(f'{ASSUMPTIONS[key][0]}: cannot be negative.')
    if kind == 'percent' and value > 100:
        raise ProceedsError(f'{ASSUMPTIONS[key][0]}: a share is at most 100%.')
    if kind == 'count' and value.denominator != 1:
        raise ProceedsError(f'{ASSUMPTIONS[key][0]}: a count is a whole number.')
    return value


def _calc(session, case_id, calculation_id):
    from postgres.models.agent_proposals import ProceedsCalculation
    calc = session.get(ProceedsCalculation, _uuid(calculation_id)) if _uuid(calculation_id) else None
    if calc is None or calc.case_id != _uuid(case_id) or calc.archived_at is not None:
        raise ProceedsError('Not in this case.', 404)
    return calc


def create(session, *, case_id, title, currency, actor, period_start=None, period_end=None,
           deposit_categories=()):
    from postgres.models.agent_proposals import ProceedsCalculation
    from services.financial.model_work import ModelWorkError, require_person
    try:
        require_person(actor, 'start a proceeds calculation')
    except ModelWorkError as exc:
        raise ProceedsError(str(exc), exc.status_code) from exc
    title = ' '.join(str(title or '').split())[:255]
    currency = str(currency or '').strip().upper()
    if not title:
        raise ProceedsError('Name the calculation.')
    if len(currency) != 3 or not currency.isalpha():
        raise ProceedsError('Give the currency as three letters.')
    if period_start and period_end and period_start > period_end:
        raise ProceedsError('The period ends before it starts.')
    calc = ProceedsCalculation(id=uuid.uuid4(), case_id=_uuid(case_id), title=title, currency=currency,
                               period_start=period_start, period_end=period_end,
                               deposit_categories=sorted({str(c).strip() for c in deposit_categories or () if
                                                          str(c).strip()}),
                               created_by=actor.name, created_by_email=actor.email)
    session.add(calc)
    session.commit()
    return view(session, case_id=case_id, calculation_id=calc.id)


def _calls(session, calc):
    from postgres.models.financial_judgements import FinancialJudgement as J
    return list(session.scalars(select(J).where(J.subject_type == 'calculation', J.subject_id == calc.id,
                                                J.rule_id == RULE).order_by(J.created_at, J.id)))


def _summary(key, low, high, currency, source):
    label, unit, kind = ASSUMPTIONS[key]
    show = (lambda v: _money(v, currency)) if kind == 'money' else (lambda v: f'{_num(v)}%' if kind == 'percent'
                                                                       else _num(v))
    span = show(low) if low == high else f'{show(low)} to {show(high)}'
    return f'{label}: {span}. Source: {source}'


def _num(value: Fraction) -> str:
    if value.denominator == 1:
        return f'{value.numerator:,}'
    return f'{float(value):,.4f}'.rstrip('0').rstrip('.')


def _money(minor: Fraction, currency: str) -> str:
    from services.financial.judgements import money
    return f"{money(int(round(minor)), currency)} {currency}"


def _record(session, calc, key, low, high, source, reason, *, origin, actor=None, proposal=None):
    from services.financial.judgements import record_judgement
    if key not in ASSUMPTIONS:
        raise ProceedsError('Unknown assumption.')
    low, high = _value(key, low), _value(key, high)
    if ASSUMPTIONS[key][2] == 'money':  # given in the currency's units (25.50); kept in minor units
        from services.financial.judgements import _EXPONENTS
        scale = 10 ** _EXPONENTS.get(calc.currency, 2)
        low, high = low * scale, high * scale
    if low > high:
        raise ProceedsError(f'{ASSUMPTIONS[key][0]}: the low value is above the high value.')
    source = ' '.join(str(source or '').split())[:600]
    if not source:
        raise ProceedsError(f'{ASSUMPTIONS[key][0]}: say where the value comes from (a source in the case or a '
                            'named reference).')
    previous = [c for c in _calls(session, calc) if c.target_key == key]
    reading = f'v{len(previous) + 1}'
    evidence = dict(key=key, low=str(low), high=str(high), source=source, reason=(reason or '').strip() or None,
                    unit=ASSUMPTIONS[key][1], currency=calc.currency if ASSUMPTIONS[key][2] == 'money' else None)
    if proposal:
        evidence['proposal'] = proposal
    row = record_judgement(session, case_id=calc.case_id, subject_type='calculation', subject_id=calc.id,
                           rule_id=RULE, target_key=key, reading=reading, strength='inferred', origin=origin,
                           summary=_summary(key, low, high, calc.currency, source), evidence=evidence)
    if row is None:
        raise ProceedsError('The assumption could not be recorded.', 500)
    return row, previous


def _settle_previous(previous, row, actor, now):
    for old in previous:
        if old.status in ('open', 'confirmed'):
            old.status = 'corrected'
            old.resolved_by, old.resolved_by_email, old.resolved_at = actor.name, actor.email, now
            old.resolution_reason = f'Replaced by {row.id}'
            old.evidence = dict(old.evidence or {}, replaced_by=str(row.id))


def set_assumption(session, *, case_id, calculation_id, key, low, high, source, actor, reason=''):
    """A named person sets an assumption with its source: a confirmed call under their name."""
    from services.financial.model_work import ModelWorkError, require_person
    try:
        require_person(actor, 'set an assumption')
    except ModelWorkError as exc:
        raise ProceedsError(str(exc), exc.status_code) from exc
    calc = _calc(session, case_id, calculation_id)
    row, previous = _record(session, calc, key, low, high, source, reason, origin='person')
    now = datetime.now(timezone.utc)
    row.status, row.resolved_by, row.resolved_by_email, row.resolved_at = 'confirmed', actor.name, actor.email, now
    row.resolution_reason = (reason or '').strip() or 'Set by a person with its source.'
    _settle_previous(previous, row, actor, now)
    session.commit()
    return view(session, case_id=case_id, calculation_id=calc.id)


def propose_assumption(session, *, case_id, calculation_id, key, low, high, source, why, origin):
    """The case agent proposes an assumption: an open call, never used until a person confirms it."""
    from services.financial.model_work import is_model
    if not is_model(origin):
        raise ProceedsError('A proposal names the model that made it.')
    calc = _calc(session, case_id, calculation_id)
    row, _ = _record(session, calc, key, low, high, source, why, origin='agent',
                     proposal=dict(kind='assumption', why=why, origin=dict(origin)))
    session.commit()
    return view(session, case_id=case_id, calculation_id=calc.id)


def confirm_assumption(session, *, case_id, calculation_id, judgement_id, actor):
    from services.financial.model_work import ModelWorkError, require_person
    try:
        require_person(actor, 'confirm an assumption')
    except ModelWorkError as exc:
        raise ProceedsError(str(exc), exc.status_code) from exc
    calc = _calc(session, case_id, calculation_id)
    calls = _calls(session, calc)
    row = next((c for c in calls if str(c.id) == str(judgement_id)), None)
    if row is None:
        raise ProceedsError('Not in this calculation.', 404)
    if row.status != 'open':
        raise ProceedsError(f'This assumption is already {row.status}.', 409)
    now = datetime.now(timezone.utc)
    row.status, row.resolved_by, row.resolved_by_email, row.resolved_at = 'confirmed', actor.name, actor.email, now
    row.resolution_reason = 'Confirmed by a person.'
    _settle_previous([c for c in calls if c.target_key == row.target_key and c.id != row.id], row, actor, now)
    session.commit()
    return view(session, case_id=case_id, calculation_id=calc.id)


# ---------------------------------------------------------------------------
# The arithmetic: pure, exact
# ---------------------------------------------------------------------------

def _factor(key, value: Fraction) -> Fraction:
    return value / 100 if ASSUMPTIONS[key][2] == 'percent' else value


def turnover(values: dict) -> Fraction:
    """values: {key: Fraction} for every assumption; the price in minor units."""
    total = Fraction(1)
    for key in ORDER:
        total *= _factor(key, values[key])
    return total


def compute(current: dict) -> Optional[dict]:
    """current: {key: (low, high)}. None until every assumption is set. Minor units, rounded once at the end."""
    if any(key not in current for key in ORDER):
        return None
    lows = {k: current[k][0] for k in ORDER}
    highs = {k: current[k][1] for k in ORDER}
    mids = {k: (current[k][0] + current[k][1]) / 2 for k in ORDER}
    result = dict(low_minor=round(turnover(lows)), mid_minor=round(turnover(mids)), high_minor=round(turnover(highs)))
    moves = []
    for key in ORDER:
        at_low, at_high = dict(mids, **{key: lows[key]}), dict(mids, **{key: highs[key]})
        moves.append(dict(key=key, label=ASSUMPTIONS[key][0], at_low_minor=round(turnover(at_low)),
                          at_high_minor=round(turnover(at_high)),
                          swing_minor=round(turnover(at_high)) - round(turnover(at_low))))
    result['moves'] = sorted(moves, key=lambda m: -m['swing_minor'])
    return result


# ---------------------------------------------------------------------------
# Deposits beside it: verified ledger only
# ---------------------------------------------------------------------------

def deposits(session, calc) -> dict:
    """Deposits in the chosen categories, summed from verified rows. Dated by the ledger's ordering date (the
    transaction date, else the posted, value or effective date), so a row printed with only a posted date stays in
    a dated period; only rows of an admitted statement count, as in the money trails (followups m1104002352354)."""
    from postgres.models.financial import FinancialSourceDocument as D
    from postgres.models.financial import FinancialTransaction as T
    from postgres.models.financial_payment_category import FinancialPaymentCategory as C
    if not calc.deposit_categories:
        return dict(categories=[], verified_minor=0, verified_rows=0, left_out_rows=0, left_out_classes={},
                    note='No deposit category chosen.')
    query = (select(T.amount_minor, T.proof_class, T.currency).join(C, C.transaction_id == T.id)
             .join(D, D.id == T.source_document_id)
             .where(T.case_id == calc.case_id, T.ledger_status == 'admitted', T.superseded_by_id.is_(None),
                    D.status == 'admitted', T.direction == 'credit', C.category.in_(list(calc.deposit_categories))))
    if calc.period_start:
        query = query.where(T.ordering_date >= calc.period_start)
    if calc.period_end:
        query = query.where(T.ordering_date <= calc.period_end)
    verified, rows, left, classes, other_currency = 0, 0, 0, {}, 0
    for amount, proof, currency in session.execute(query):
        if (currency or '').upper() != calc.currency:
            other_currency += 1
            continue
        if proof in VERIFIED_CLASSES:
            verified += abs(int(amount))
            rows += 1
        else:
            left += 1
            classes[proof] = classes.get(proof, 0) + 1
    note = ('Verified deposits only (checked against the statement\'s totals or printed balances).'
            + (f' {left:,} deposit rows not checked against printed balances are left out, not summed.' if left else '')
            + (f' {other_currency} rows in another currency are left out.' if other_currency else ''))
    return dict(categories=list(calc.deposit_categories), verified_minor=verified, verified_rows=rows,
                left_out_rows=left, left_out_classes=classes, other_currency_rows=other_currency, note=note)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def view(session, *, case_id, calculation_id) -> dict:
    from services.financial.judgements import as_dict
    calc = _calc(session, case_id, calculation_id)
    calls = _calls(session, calc)
    current, rows = {}, []
    for key in ORDER:
        mine = [c for c in calls if c.target_key == key]
        confirmed = [c for c in mine if c.status == 'confirmed']
        chosen = confirmed[-1] if confirmed else None
        if chosen is not None:
            ev = chosen.evidence or {}
            current[key] = (Fraction(ev['low']), Fraction(ev['high']))
        rows.append(dict(key=key, label=ASSUMPTIONS[key][0], unit=ASSUMPTIONS[key][1], kind=ASSUMPTIONS[key][2],
                         current=as_dict(chosen) if chosen is not None else None,
                         set_by=chosen.resolved_by if chosen is not None else None,
                         low=(chosen.evidence or {}).get('low') if chosen is not None else None,
                         high=(chosen.evidence or {}).get('high') if chosen is not None else None,
                         source=(chosen.evidence or {}).get('source') if chosen is not None else None,
                         proposed=[as_dict(c) for c in mine if c.status == 'open'],
                         history=[as_dict(c) for c in mine if c.status == 'corrected']))
    result = compute(current)
    missing = [ASSUMPTIONS[k][0] for k in ORDER if k not in current]
    return dict(id=str(calc.id), case_id=str(calc.case_id), title=calc.title, currency=calc.currency,
                period_start=calc.period_start.isoformat() if calc.period_start else None,
                period_end=calc.period_end.isoformat() if calc.period_end else None,
                created_by=calc.created_by, label=LABEL, assumptions=rows, result=result,
                missing=missing, formula='messages × share that are deals × deals per message × price per deal',
                deposits=deposits(session, calc))


def list_calculations(session, *, case_id) -> dict:
    from postgres.models.agent_proposals import ProceedsCalculation
    rows = list(session.scalars(select(ProceedsCalculation).where(
        ProceedsCalculation.case_id == _uuid(case_id), ProceedsCalculation.archived_at.is_(None))
        .order_by(ProceedsCalculation.created_at.desc())))
    return dict(items=[dict(id=str(r.id), title=r.title, currency=r.currency, created_by=r.created_by) for r in rows],
                total=len(rows))
