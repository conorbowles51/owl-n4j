"""The accounts a native file is about, and the coverage it claims for each.

A parsed native file is a document plus a flat run of rows, and each row names
the account it belongs to with a printed string.  Before any of it can be
stored, somebody has to answer two questions the row itself does not: which
account is that string, and what period does this document cover for it.  This
module answers both, and does nothing else -- it touches no session, writes
nothing, and returns drafts for the driver to hand to the writers.

Keeping it separate from the driver is not tidiness.  The four formats disagree
about what an account even *is* in a way that has to be visible somewhere, and
burying it inside a function that is also opening transactions and stamping
runs would leave the disagreement to be rediscovered from behaviour.

Three formats describe a subject, one does not
----------------------------------------------

camt.053, BAI2 and MT940 are statements.  Each names the account it is about,
prints balances for it, and its rows are movements *on* that account.  One
subject, one period, and the period is checkable arithmetic.

NACHA is not a statement.  It is a batch of payment instructions, and the
account on each entry is the **receiver's** -- the party being paid or debited,
a different one on most rows.  A NACHA file therefore describes many accounts
and is about none of them, prints no balance for any, and states no period.
That is not a gap to be filled: a period is a claim that a document covers an
account between two dates and closes over it, and NACHA makes no such claim for
anybody.  So it yields accounts and no periods at all, which
:class:`~services.financial.transactions.TransactionDraft` already allows by
leaving ``statement_period_id`` optional.

The account key is the only join
--------------------------------

Rows carry ``account_key``, a raw printed string, and it is the *only* thing
connecting a row to an account.  Every key produced here is therefore derived
by the same expression the row adapter in
:mod:`~services.financial.native` uses, because a key computed two ways is a
key that will eventually be computed two different ways.

The consequence is a case that has to be refused rather than papered over.
Where a format lets the account identifier be absent -- camt.053's is
``Optional`` -- every row of every unidentified statement in the file carries
``account_key=None``, and there is no information left to tell them apart.  One
such statement is fine and becomes an unidentified account.  Two is not: their
rows are indistinguishable, so attributing them would put one account's
transactions on another inside a single matter, which is the merge the account
module exists to prevent.  It raises instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from services.financial.accounts import AccountDraft, AccountIdentityError
from services.financial.bai2 import Bai2File
from services.financial.camt053 import Camt053Document
from services.financial.money import Money
from services.financial.mt940 import Mt940Balance, Mt940File
from services.financial.nacha import NachaFile
from services.financial.native import (
    CenturyWindow,
    DateResolutionError,
    NativeFormat,
    NativeReading,
)
from services.financial.periods import BalanceObservation, PeriodBounds

from postgres.models.enums import PeriodBoundsSource


class SubjectError(Exception):
    """A native file's accounts could not be described as read."""


# ---------------------------------------------------------------------------
# What the adapter returns
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PeriodFacts:
    """One document's coverage of one account, before either has an id.

    Not a :class:`~services.financial.periods.StatementPeriodDraft` because
    that needs ``account_id`` and ``source_document_id``, and neither exists
    until the driver has written them.  These are the parts that come from the
    file rather than from the database.
    """

    currency: str
    bounds: PeriodBounds
    opening: BalanceObservation
    closing: BalanceObservation


@dataclass(frozen=True, slots=True)
class AccountSubject:
    """One account a native file names, and what it claims about it."""

    #: Matches ``NativeRow.account_key`` exactly, including ``None``.
    account_key: Optional[str]
    draft: AccountDraft
    #: ``None`` where the format states no coverage, which is every NACHA file.
    period: Optional[PeriodFacts] = None


# ---------------------------------------------------------------------------
# Small shared readings
# ---------------------------------------------------------------------------


def _clean(value: Optional[str]) -> Optional[str]:
    """Whitespace-only is absent.  Fixed-width formats pad every field."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _iso_day(value: Optional[str]) -> Optional[date]:
    """An ISO date or date-time as a plain date, or ``None`` if unreadable.

    Unreadable rather than raising, because a bound that could not be read is
    the absent case the bounds type is built to carry, and refusing the whole
    document over a malformed date would discard rows that are fine.
    """
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _yymmdd(
    value: Optional[str], window: CenturyWindow, context: str
) -> Optional[date]:
    """A two-digit-year date through the window, or ``None`` if unresolvable.

    A malformed date is not what reaches here.  Both parsers reject those on
    the face of the file -- MT940 refuses ``249999`` for stating month 99 --
    and :func:`~services.financial.native.read_native` resolves BAI2's group
    as-of date itself while dating the rows, so a BAI2 file whose date this
    could not read was refused before the reading existed.

    What reaches here is the narrower case those two do not cover: a date that
    is well formed but falls outside the century window.  ``read_native``
    resolves MT940's ``:61:`` line dates and never its ``:60a:``/``:62a:``
    balance dates, so a statement whose balances are stamped outside the
    engagement's window and whose lines fall inside it parses, reads, and
    arrives here with two dates the window has no reading for.

    Raising would discard that whole statement -- its rows, its amounts and
    its balances -- over the bounds alone.  Recording the bounds as ``absent``
    keeps all of it and states exactly what is true: the dates were not
    established.  Nothing downstream is misled, because
    :attr:`~services.financial.periods.PeriodBounds.supports_continuity`
    already refuses to argue a gap from a bound that was not printed.
    """
    if not value:
        return None
    try:
        return window.resolve_yymmdd(value, context=context)
    except DateResolutionError:
        return None


def _printed(amount: Optional[Money]) -> BalanceObservation:
    """A printed balance, or the absent one.  Absent is not zero."""
    if amount is None:
        return BalanceObservation.absent()
    return BalanceObservation.printed(amount)


def _bounds(start: Optional[date], end: Optional[date]) -> PeriodBounds:
    """Whichever ends were printed, each recorded on its own.

    Partial bounds are constructed directly rather than through
    :meth:`PeriodBounds.printed`, which takes both: a statement that prints
    only a closing date is the case the type's two source fields exist for.
    """
    if start is not None and end is not None and start > end:
        raise SubjectError(
            f"statement period runs backwards: {start} to {end}; the document "
            "states a start after its own end and the two cannot both be right"
        )
    return PeriodBounds(
        start=start,
        end=end,
        start_source=(
            PeriodBoundsSource.absent if start is None else PeriodBoundsSource.printed
        ),
        end_source=(
            PeriodBoundsSource.absent if end is None else PeriodBoundsSource.printed
        ),
    )


def _account_draft(
    *,
    key: Optional[str],
    distinguisher: str,
    ordinal: int,
    institution_name: Optional[str] = None,
    holder_name: Optional[str] = None,
    currency: Optional[str] = None,
    iban: Optional[str] = None,
    bic: Optional[str] = None,
    routing_number: Optional[str] = None,
) -> AccountDraft:
    """An observed draft where the document identified the account, else not.

    The fall back to :meth:`AccountDraft.unidentified` is deliberate and narrow.
    ``observed`` refuses a draft whose identifying fields are placeholders --
    ``see statement``, a row of asterisks, ``N/A`` -- and the right answer to
    that is not to force it through but to record an account this document
    could not name, which is what the unidentified constructor is for.  The
    printed string is still kept; it just takes no part in the key.

    The distinguisher is the document's content hash with the account's
    position appended.  The hash makes it unique across documents, which is the
    property that stops two files' unnamed accounts merging; the position makes
    it unique within one, and is safe only because the hash is there -- a bare
    position would give every file's first unnamed account the same key.
    """
    printed = _clean(key)
    if printed is not None:
        try:
            return AccountDraft.observed(
                institution_name=institution_name,
                identifier_as_printed=printed,
                holder_name=holder_name,
                currency=currency,
                iban=iban,
                bic=bic,
                routing_number=routing_number,
            )
        except AccountIdentityError:
            # A placeholder identifier, or nothing identifying left once the
            # guard has removed them.  PlaceholderIdentifierError derives from
            # AccountIdentityError, so this catches both, and both are
            # recoverable the same way: the document said what it said.
            #
            # Deliberately not `except Exception`.  The only other refusal
            # `observed` can raise is AccountCurrencyError, which falling back
            # would not fix -- `unidentified` takes the same currency and
            # refuses it identically -- so catching it would turn a real
            # refusal into a silent misfiling under a different constructor.
            pass
    return AccountDraft.unidentified(
        distinguisher=f"{distinguisher}:{ordinal}",
        institution_name=institution_name,
        identifier_as_printed=printed,
        holder_name=holder_name,
        currency=currency,
    )


# ---------------------------------------------------------------------------
# Per-format
# ---------------------------------------------------------------------------


def _subjects_camt053(
    document: Camt053Document, distinguisher: str
) -> list[AccountSubject]:
    """One subject per ``Stmt``, with its printed balances and bounds.

    ``OPBD`` and ``CLBD`` are the opening and closing booked balances, which
    are the two the statement's own identity is drawn against.  Where a
    statement prints neither, the period is still recorded: a document that
    covers an account and shows no balances is a real statement and the absence
    is the finding.
    """
    subjects: list[AccountSubject] = []
    for ordinal, statement in enumerate(document.statements):
        account = statement.account
        key = account.identifier
        opening = statement.balance("OPBD")
        closing = statement.balance("CLBD")
        subjects.append(
            AccountSubject(
                account_key=key,
                draft=_account_draft(
                    key=key,
                    distinguisher=distinguisher,
                    ordinal=ordinal,
                    holder_name=_clean(account.owner_name),
                    currency=account.currency or statement.currency,
                    iban=_clean(account.iban),
                    bic=_clean(account.servicer_bic),
                ),
                period=PeriodFacts(
                    currency=statement.currency,
                    bounds=_bounds(
                        _iso_day(statement.period_from),
                        _iso_day(statement.period_to),
                    ),
                    opening=_printed(None if opening is None else opening.signed),
                    closing=_printed(None if closing is None else closing.signed),
                ),
            )
        )
    return subjects


def _subjects_bai2(
    file: Bai2File, window: CenturyWindow, distinguisher: str
) -> list[AccountSubject]:
    """One subject per ``03`` account, dated by the ``02`` group above it.

    BAI2 states an as-of date on the group, not a span on the account, so only
    the end bound is recorded and it is recorded as printed -- because it was.
    Inventing a start to make the pair look complete would assert coverage the
    file never claimed, and
    :attr:`~services.financial.periods.PeriodBounds.supports_continuity` is
    false either way, so nothing is gained by the fiction.
    """
    subjects: list[AccountSubject] = []
    ordinal = 0
    for group in file.groups:
        as_of = _yymmdd(
            group.as_of_date,
            window,
            f"BAI2 group at line {group.first_line} as-of date",
        )
        for account in group.accounts:
            key = account.customer_account_number
            subjects.append(
                AccountSubject(
                    account_key=key,
                    draft=_account_draft(
                        key=key,
                        distinguisher=distinguisher,
                        ordinal=ordinal,
                        currency=account.currency,
                    ),
                    period=PeriodFacts(
                        currency=account.currency,
                        bounds=_bounds(None, as_of),
                        opening=_printed(account.opening_balance),
                        closing=_printed(account.closing_balance),
                    ),
                )
            )
            ordinal += 1
    return subjects


def _subjects_mt940(
    file: Mt940File, window: CenturyWindow, distinguisher: str
) -> list[AccountSubject]:
    """One subject per ``:20:`` statement, bounded by its own balance dates.

    Both bounds come from the balances rather than from a period field, because
    MT940 has no period field: ``:60a:`` carries the date the statement opens
    at and ``:62a:`` the date it closes at, and those are the span.  They are
    printed dates, so they are recorded as printed.
    """
    subjects: list[AccountSubject] = []
    for ordinal, statement in enumerate(file.statements):
        key = statement.account_identification
        opening = statement.opening_balance
        closing = statement.closing_balance
        subjects.append(
            AccountSubject(
                account_key=key,
                draft=_account_draft(
                    key=key,
                    distinguisher=distinguisher,
                    ordinal=ordinal,
                    currency=statement.currency,
                    bic=_clean(statement.account_identifier_code),
                ),
                period=PeriodFacts(
                    currency=statement.currency,
                    bounds=_bounds(
                        _balance_day(opening, window, "opening"),
                        _balance_day(closing, window, "closing"),
                    ),
                    opening=_printed(None if opening is None else opening.amount),
                    closing=_printed(None if closing is None else closing.amount),
                ),
            )
        )
    return subjects


def _balance_day(
    balance: Optional[Mt940Balance], window: CenturyWindow, label: str
) -> Optional[date]:
    """An MT940 balance's ``YYMMDD`` date resolved through the century window.

    ``balance`` is typed optional although :class:`Mt940Statement` declares
    both of these mandatory, because the guard costs nothing and the caller
    reads the same either way.
    """
    if balance is None:
        return None
    return _yymmdd(balance.date, window, f"MT940 {label} balance date")


def _subjects_nacha(file: NachaFile, distinguisher: str) -> list[AccountSubject]:
    """One subject per distinct receiver, and no period for any of them.

    The originator is not among these.  A NACHA file names the company sending
    the batch in the ``5`` record, but it prints no account for it -- only a
    company identification -- and every ``6`` record's account belongs to the
    party on the other side.  Recording the originator as an account here would
    invent an identifier the file does not contain.

    Its name is kept as the institution on each receiver instead, because that
    *is* what the file asserts: this is who paid or debited this account.
    """
    subjects: list[AccountSubject] = []
    seen: dict[str, None] = {}
    for batch in file.batches:
        originator = _clean(batch.company_name)
        for entry in batch.entries:
            key = f"{entry.routing_number}/{entry.account_number.strip()}"
            if key in seen:
                continue
            seen[key] = None
            subjects.append(
                AccountSubject(
                    account_key=key,
                    draft=_account_draft(
                        key=key,
                        distinguisher=distinguisher,
                        ordinal=len(seen) - 1,
                        institution_name=originator,
                        holder_name=_clean(entry.individual_name),
                        routing_number=entry.routing_number,
                    ),
                    period=None,
                )
            )
    return subjects


# ---------------------------------------------------------------------------
# The entry point
# ---------------------------------------------------------------------------


def describe_subjects(
    reading: NativeReading,
    *,
    window: CenturyWindow,
    distinguisher: str,
) -> tuple[AccountSubject, ...]:
    """The accounts a parsed native file names, in file order.

    ``distinguisher`` must be stable across re-reads of this document and
    unique across documents; the file's content hash is the intended value.  It
    is used only for accounts the document failed to identify.

    ``window`` resolves the two-digit years BAI2 and MT940 print.  It is passed
    in rather than defaulted because the same file read under two windows is
    two different documents, and a default would let that happen silently.

    :raises SubjectError: if the file states a period backwards, or if two of
        its accounts are indistinguishable at the row level.
    """
    if not isinstance(distinguisher, str) or not distinguisher.strip():
        raise SubjectError(
            "describe_subjects needs a non-empty distinguisher; without one "
            "every unidentified account across every document shares a key"
        )

    document = reading.document
    fmt = reading.format
    if fmt is NativeFormat.camt053:
        subjects = _subjects_camt053(document, distinguisher)
    elif fmt is NativeFormat.bai2:
        subjects = _subjects_bai2(document, window, distinguisher)
    elif fmt is NativeFormat.mt940:
        subjects = _subjects_mt940(document, window, distinguisher)
    elif fmt is NativeFormat.nacha:
        subjects = _subjects_nacha(document, distinguisher)
    else:
        raise SubjectError(
            f"no subject adapter for native format {fmt!r}; a format that can "
            "be parsed but not attributed would write rows against no account"
        )

    _refuse_indistinguishable(subjects)
    return tuple(subjects)


def _refuse_indistinguishable(subjects: list[AccountSubject]) -> None:
    """Two unnamed accounts in one file cannot be told apart by their rows.

    Every row of both carries ``account_key=None``, so there is no fact left to
    attribute them by.  Storing them would either merge two accounts or assign
    one account's money to the other, and both are in-matter errors that no
    later stage can detect, let alone undo.

    Repeated *named* keys are not this case and are left alone: a camt.053
    holding two statements for one account is an ordinary combined file, and
    the two periods it produces are both real.
    """
    unnamed = [subject for subject in subjects if _clean(subject.account_key) is None]
    if len(unnamed) > 1:
        raise SubjectError(
            f"{len(unnamed)} accounts in this file print no identifier, and "
            "every row of each of them carries the same empty account key; "
            "there is nothing left to attribute the rows by, and guessing "
            "would put one account's transactions on another"
        )
