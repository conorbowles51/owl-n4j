"""A statement that repeats earlier activity under a new card or account number (register E26).

When a card is replaced or an account migrated, the new statement can print the old one's payments again, with the
same printed references, dates, amounts and descriptions, and a line carrying the old balance across. Duplicate
checks do not see this: the identifiers differ, so the two are different accounts and different sections, and each
statement reconciles on its own. Counting both counts the activity twice.

This module only suggests. It names the earlier statement and what matches, and the coverage review holds the new
statement for a person (``statement_import_overlap.coverage_review``). It changes no row: both sources stay in
Evidence, an import the person allows keeps both statements, and repeated payments that are real stay real. Rows
already admitted are listed by ``case_report`` and never touched.

A pair is a candidate when the two accounts share a bank and holder, have different numbers, and the statements share
payments with the same date, amount, direction and currency plus the same printed reference or description, and:

* at least ``MIN_REFERENCED`` of those carry the same printed reference, or
* at least ``MIN_REPEATED`` match and they are at least ``MIN_SHARE`` of the smaller statement, or
* at least one matches with a printed reference and the new statement carries a balance across.

Recurring bank charges are why a share is needed and why one holder and one bank are required: measured across the
six financial cases, identical fee lines appear in 35 pairs of accounts of different holders in one case.
Reverse: LOUPE_FINANCIAL_REPEATED_ACTIVITY_HOLD=0 removes the hold; the listing stays.
"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select

from postgres.models.evidence import EvidenceFile
from postgres.models.financial import (
    FinancialAccount, FinancialSourceDocument, FinancialStatementPeriod, FinancialTransaction,
)

HOLD = os.environ.get('LOUPE_FINANCIAL_REPEATED_ACTIVITY_HOLD', '1').strip().lower() not in ('0', 'false', 'off', 'no')
MIN_REFERENCED = 2
MIN_REPEATED = 3
MIN_SHARE = 0.3
MAX_EXAMPLES = 5
HOLD_MESSAGE = ('This statement repeats payments from an earlier statement under another card or account number. '
                'Compare the two, then leave it unimported or record why both are needed. Neither file is changed.')
_CARRIED = re.compile(
    r'balance\s+transfer|transfer(?:red)?\s+(?:of\s+)?balance|balance\s+(?:brought\s+)?(?:forward|transferred)|'
    r'(?:previous|prior|old|former)\s+(?:card|account)|transfer(?:red)?\s+from\s+(?:card|account|acct)|'
    r'account\s+(?:migration|conversion|number\s+change)|card\s+replacement', re.I)
_TOKEN = re.compile(r'[A-Za-z0-9]{10,}')
_WORDS = re.compile(r'[^a-z0-9]+')
_NOT_NAME = {'mr', 'mrs', 'ms', 'dr', 'jr', 'sr', 'ii', 'iii', 'sa', 'de', 'cv', 'llc', 'inc', 'ltd', 'the', 'and'}


def _words(text) -> str:
    return _WORDS.sub(' ', str(text or '').lower()).strip()


def printed_references(description, bank_reference=None) -> frozenset:
    """Reference-like tokens: the bank's reference column and long codes printed in the description."""
    found = {token.upper() for token in _TOKEN.findall(str(description or ''))
             if any(c.isdigit() for c in token)}
    if bank_reference and str(bank_reference).strip():
        found.add(re.sub(r'\s+', '', str(bank_reference)).upper())
    return frozenset(found)


@dataclass(frozen=True)
class Line:
    date: str
    amount: int
    direction: str
    currency: str
    description: str
    references: frozenset = frozenset()
    ident: str = ''

    @property
    def key(self):
        return (self.date, self.amount, self.direction, self.currency)


@dataclass
class Statement:
    account_id: str | None
    institution: str
    holder: str
    number: str
    currency: str
    period_start: str
    period_end: str
    lines: list = field(default_factory=list)
    other_lines: list = field(default_factory=list)  # rows set aside in review, read for a carried-balance line
    opening: int | None = None
    closing: int | None = None
    source: dict = field(default_factory=dict)


def same_holder(left, right) -> bool:
    a, b = (set(_words(name).split()) - _NOT_NAME for name in (left, right))
    if not a or not b:
        return False
    return a == b or (len(a & b) >= 2 and (a <= b or b <= a))


def same_bank(left, right) -> bool:
    a, b = _words(left).split(), _words(right).split()
    return bool(a and b and a[0] == b[0])


def different_number(left, right) -> bool:
    a, b = re.sub(r'\D', '', str(left or '')), re.sub(r'\D', '', str(right or ''))
    if not a or not b:
        return False
    return a != b and not (a.endswith(b) or b.endswith(a))


def repeated_lines(own: list[Line], other: list[Line]) -> list[tuple[Line, Line, bool]]:
    """Each line of ``own`` paired once with a line of ``other``; True where a printed reference matches."""
    by_key = defaultdict(list)
    for line in other:
        by_key[line.key].append(line)
    matched = []
    for line in own:
        options = by_key.get(line.key) or []
        words = _words(line.description)
        choice = next((o for o in options if line.references & o.references), None)
        referenced = choice is not None
        choice = choice or next((o for o in options if words and _words(o.description) == words), None)
        if choice is not None:
            options.remove(choice)
            matched.append((line, choice, referenced))
    return matched


def carried_balance(own: Statement, other: Statement) -> str | None:
    """Why the newer statement carries the older one's balance across, or None."""
    if other.closing is not None:
        if own.opening is not None and abs(own.opening) == abs(other.closing) and other.closing != 0:
            return 'Opening balance equals the earlier closing balance'
        if other.closing != 0 and any(line.amount == abs(other.closing) for line in own.lines + own.other_lines):
            return 'A line carries the earlier closing balance'
    for line in own.lines + own.other_lines:
        if _CARRIED.search(line.description):
            return f'A line reads “{line.description[:80]}”'
    return None


def assess_pair(own: Statement, other: Statement) -> dict | None:
    """The comparison of two statements of one holder and bank under different numbers, or None."""
    if own.currency != other.currency or not same_bank(own.institution, other.institution):
        return None
    if not same_holder(own.holder, other.holder) or not different_number(own.number, other.number):
        return None
    matched = repeated_lines(own.lines, other.lines)
    if not matched:
        return None
    referenced = sum(1 for _, _, flag in matched if flag)
    smaller = min(len(own.lines), len(other.lines)) or 1
    carried = carried_balance(own, other)
    if not (referenced >= MIN_REFERENCED or (len(matched) >= MIN_REPEATED and len(matched) / smaller >= MIN_SHARE)
            or (referenced >= 1 and carried)):
        return None
    return dict(repeated=len(matched), with_printed_reference=referenced, own_rows=len(own.lines),
                other_rows=len(other.lines), carried_balance=carried,
                examples=[dict(date=a.date, amount_minor=str(a.amount), direction=a.direction, currency=a.currency,
                               description=a.description[:120], printed_reference_matches=flag)
                          for a, _, flag in matched[:MAX_EXAMPLES]])


def _review_lines(rows, currency) -> tuple[list[Line], list[Line]]:
    kept, others = [], []
    for row in rows or ():
        amount = str(row.get('amount_minor') or '')
        if not amount.lstrip('-').isdigit():
            continue
        text = ' '.join(str(row.get(key) or '') for key in ('description', 'counterparty')).strip()
        line = Line(date=str(row.get('date') or ''), amount=abs(int(amount)), direction=str(row.get('direction') or ''),
                    currency=currency, description=text, references=printed_references(text), ident=str(row.get('id') or ''))
        if row.get('excluded') or not row.get('date') or not row.get('direction'):
            others.append(line)
        else:
            kept.append(line)
    return kept, others


def review_statement(request) -> Statement:
    """A statement under review, from the values a person sees."""
    kept, others = _review_lines(request.get('rows'), request.get('currency') or '')
    return Statement(account_id=None, institution=request.get('institution') or '', holder=request.get('holder') or '',
                     number=request.get('account_number') or '', currency=request.get('currency') or '',
                     period_start=request.get('period_start') or '', period_end=request.get('period_end') or '',
                     lines=kept, other_lines=others)


def _admitted(session, case_id, accounts=None) -> list[Statement]:
    """The case's admitted statements, one per statement period, with their source file."""
    query = (select(FinancialTransaction.statement_period_id, FinancialTransaction.account_id,
                    FinancialTransaction.ordering_date, FinancialTransaction.amount_minor, FinancialTransaction.direction,
                    FinancialTransaction.currency, FinancialTransaction.description, FinancialTransaction.counterparty_raw,
                    FinancialTransaction.bank_reference, FinancialTransaction.id)
             .where(FinancialTransaction.case_id == case_id, FinancialTransaction.ledger_status == 'admitted',
                    FinancialTransaction.superseded_by_id.is_(None), FinancialTransaction.statement_period_id.is_not(None)))
    if accounts is not None:
        query = query.where(FinancialTransaction.account_id.in_(accounts))
    rows = session.execute(query).all()
    period_ids = {row[0] for row in rows}
    if not period_ids:
        return []
    periods = {p.id: p for p in session.scalars(select(FinancialStatementPeriod).where(
        FinancialStatementPeriod.id.in_(period_ids)))}
    account_ids = {row[1] for row in rows}
    accounts_by_id = {a.id: a for a in session.scalars(select(FinancialAccount).where(FinancialAccount.id.in_(account_ids)))}
    sources = dict(session.execute(select(FinancialSourceDocument.id, FinancialSourceDocument.evidence_file_id).where(
        FinancialSourceDocument.id.in_({p.source_document_id for p in periods.values()}))).all())
    names = dict(session.execute(select(EvidenceFile.id, EvidenceFile.original_filename).where(
        EvidenceFile.id.in_(set(sources.values())))).all())
    statements: dict = {}
    for period_id, account_id, day, amount, direction, currency, description, counterparty, reference, row_id in rows:
        period, account = periods.get(period_id), accounts_by_id.get(account_id)
        if period is None or account is None or day is None:
            continue
        statement = statements.get(period_id)
        if statement is None:
            file_id = sources.get(period.source_document_id)
            statement = statements[period_id] = Statement(
                account_id=str(account_id), institution=account.institution_name or '', holder=account.holder_name or '',
                number=account.identifier_as_printed or '', currency=currency,
                period_start=period.period_start.isoformat() if period.period_start else '',
                period_end=period.period_end.isoformat() if period.period_end else '',
                opening=period.opening_balance_minor, closing=period.closing_balance_minor,
                source=dict(file_id=str(file_id) if file_id else '', source_document_id=str(period.source_document_id),
                            statement_period_id=str(period_id), filename=names.get(file_id) or 'Statement'))
        text = ' '.join(v for v in (description, counterparty) if v)
        statement.lines.append(Line(date=day.isoformat(), amount=abs(amount), direction=direction, currency=currency,
                                    description=text, references=printed_references(text, reference), ident=str(row_id)))
    return list(statements.values())


def repeated_candidates(session, *, case_id, file_id, request) -> list[dict]:
    """Admitted statements a statement under review repeats, shaped as coverage review candidates."""
    own = review_statement(request)
    if not HOLD or not own.lines or not own.holder or not own.institution or request.get('replaces_source_document_id'):
        return []
    accounts = [a.id for a in session.scalars(select(FinancialAccount).where(FinancialAccount.case_id == case_id))
                if same_bank(a.institution_name, own.institution) and same_holder(a.holder_name, own.holder)
                and different_number(a.identifier_as_printed, own.number)]
    if not accounts:
        return []
    candidates = []
    for other in _admitted(session, case_id, accounts):
        if other.source.get('file_id') == str(file_id):
            continue
        found = assess_pair(own, other)
        if found:
            candidates.append(dict(
                file_id=other.source['file_id'], statement_id=None, source_document_id=other.source['source_document_id'],
                filename=other.source['filename'], status='imported', period_start=other.period_start,
                period_end=other.period_end, matching_statement=True, same_file_statement=False,
                repeated_activity=dict(found, other_number=other.number, other_holder=other.holder)))
    return sorted(candidates, key=lambda item: (-item['repeated_activity']['repeated'], item['period_start'], item['filename']))


def case_report(session, *, case_id, pending=()) -> list[dict]:
    """Every candidate pair among the case's admitted statements and ``pending`` statements. Reads only."""
    everything = [*pending, *_admitted(session, case_id)]
    # Only statements sharing a line can match, so most pairs are never compared.
    sharing = defaultdict(set)
    for index, statement in enumerate(everything):
        for line in statement.lines:
            sharing[line.key].add(index)
    pairs = {(a, b) for members in sharing.values() if len(members) > 1
             for a in members for b in members if a < b}
    found = []
    for first, second in sorted(pairs):
        own, other = everything[first], everything[second]
        if own.account_id and own.account_id == other.account_id:
            continue
        newer, older = (own, other) if own.period_end >= other.period_end else (other, own)
        result = assess_pair(newer, older)
        if result:
            found.append(dict(result, newer=dict(newer.source, number=newer.number, holder=newer.holder,
                                                 period_end=newer.period_end, pending=newer.account_id is None),
                              older=dict(older.source, number=older.number, holder=older.holder,
                                         period_end=older.period_end, pending=older.account_id is None)))
    return found


def record_admitted(session, *, case_id) -> dict:
    """Put admitted pairs in front of a person as judgement calls, in the Copies group. Adds those rows only.

    A judgement holds nothing and changes no payment; the rows of both statements stay as they are. The same pair
    records once. Run on an existing case with ``python -m services.financial.repeated_activity <case id> --apply``.
    """
    from uuid import UUID
    from services.financial.judgements import record_judgement
    found = case_report(session, case_id=case_id)
    recorded = 0
    for pair in found:
        newer, older = pair['newer'], pair['older']
        summary = (f"{newer['filename']} (number {newer['number']}) repeats {pair['repeated']} payments of "
                   f"{older['filename']} (number {older['number']}), {pair['with_printed_reference']} with the same "
                   'printed reference. Both are in the ledger. Check whether this is the same activity.')
        if record_judgement(session, case_id=case_id, subject_type='source_document',
                            subject_id=UUID(newer['source_document_id']), rule_id='copies.repeated_activity',
                            summary=summary, evidence=pair, target_key='repeats', reading=older['source_document_id'],
                            source_document_id=UUID(newer['source_document_id']),
                            statement_period_id=UUID(newer['statement_period_id'])):
            recorded += 1
    return dict(candidates=len(found), recorded=recorded)


def main(argv=None) -> int:
    import argparse
    import json
    from uuid import UUID
    from postgres.session import _get_session_local
    parser = argparse.ArgumentParser(description='List payments repeated under another number; --apply records them.')
    parser.add_argument('case_id', type=UUID)
    parser.add_argument('--apply', action='store_true', help='add judgement calls for admitted pairs (default: dry run)')
    args = parser.parse_args(argv)
    with _get_session_local()() as session:
        if args.apply:
            print(json.dumps(record_admitted(session, case_id=args.case_id)))
            session.commit()
        else:
            print(json.dumps(case_report(session, case_id=args.case_id), default=str, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
