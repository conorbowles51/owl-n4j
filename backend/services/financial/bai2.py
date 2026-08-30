"""Layer 0 for BAI2: a specification-conformant parse, exact by construction.

`13` §4 puts this layer first: "For P0 and P1 formats there is no extraction
problem.  camt.053, BAI2, NACHA and MT940 are parsed with a
specification-conformant parser.  The output is exact by construction."  This
is the second such parser, after :mod:`~services.financial.camt053`.

`12` §6.1 says why BAI2 is worth writing next: "Record types 01 file header, 02
group header, 03 account identifier, 16 transaction detail, 88 continuation, 49
account trailer, 98 group trailer, 99 file trailer.  The 49/98/99 trailers give
control totals at three levels of nesting.  Full arithmetic validation is
available."

Four checks, not one
--------------------

A conformant BAI2 file carries more arithmetic than a camt.053 does, and the
four guarantees are kept apart because they fail for different reasons and a
reviewer needs to know which one moved.

1. **The account control total** (``49``).  The sum of every amount in the
   account — the ``03`` summary amounts and every ``16`` detail amount —
   together with a count of the records that make up the account.  Mandatory.
2. **The group control total** (``98``).  The sum of the account control totals
   in the group, with an account count and a record count.  Mandatory.
3. **The file control total** (``99``).  The sum of the group control totals,
   with a group count and a record count.  Mandatory.
4. **The balance identity**, where the file states the balances to build it
   from::

       010 opening ledger + ΣCredits − ΣDebits = 015 closing ledger

   Optional, because ``010`` and ``015`` are status codes a sender may simply
   omit — many real files carry only a closing balance.

And a fifth where the file offers it: the ``03`` record may declare ``100``
total credits and ``400`` total debits with item counts, which is the same
corroboration ``TxsSummry`` gives in camt.053 and is checked the same way.

What governs, and what merely corroborates
------------------------------------------

The rule established in :mod:`~services.financial.camt053` is that the
mandatory check governs unconditionally and an optional one can weaken the
outcome only by *failing* — never by being absent, because nothing was claimed,
and never by declining, because a decline says what this parser could interpret
and not what the file's arithmetic says.

That principle transfers.  Its *assignment* does not, and the difference is
worth stating because it would otherwise look like an inconsistency.  In
camt.053 the balance identity is the mandatory check and it governs.  In BAI2
the balance identity is optional and the control totals are mandatory, so the
control totals govern and the balance identity corroborates.  What carries over
is the principle, not the list.

The two guarantees are also not the same guarantee, which is why both are
reported rather than collapsed.  A control total is a checksum over the amounts
as transmitted: it establishes that nothing was lost or altered in carriage.
The balance identity establishes something else entirely — that the
transactions actually account for the movement from opening to closing.  A file
can pass either and fail the other, and the two failures send a reader to
different places.

Decisions the specification leaves open
---------------------------------------

Each resolves toward *not* claiming p0, on the reasoning `13` §2.2 gives: a
class assigned one step too low costs an adjudication a person will resolve,
and one step too high puts an unchecked row inside a total.

**Amounts are minor units, and are never scaled by guess.**  BAI2 writes
amounts as integers in the currency's smallest unit with no decimal point, so
``1000`` is ten dollars and not one thousand.  Reading it as the latter is
wrong by exactly the currency's exponent, which for USD is a factor of a
hundred and for JPY is a factor of one.  A parser that got this wrong would
produce a ledger that is internally consistent, passes every control total, and
is out by two orders of magnitude — the identity cannot catch it, because
scaling every term by the same factor preserves the equation.  The exponent
therefore comes from :func:`~services.financial.money.get_currency` and the
currency comes from the file.

**A file that states no currency is refused unless the caller supplies one.**
The specification says currency defaults to that of the originating bank's
country, which is not knowable from inside the file.  Defaulting to USD would
be a guess made by the component least equipped to make it, and it would be
invisible.  ``parse_bai2`` therefore takes an optional ``default_currency``,
records on each account whether the currency was stated or supplied, and
refuses a file that states none when none was supplied.

**Direction comes from the type code, never from a sign.**  Type codes 100–399
are credits and 400–699 are debits.  Codes in 700–799 (loan), 800–899
(unassigned) and 900–999 (customer-defined) have no direction the specification
fixes, so this module does not assign one.  A detail record carrying such a
code with a non-zero amount makes the balance identity *decline* rather than
guess — a guess would land the amount on one side of an equation that would
then close, or fail, for a reason having nothing to do with the file.  A
zero-amount record of that kind is recorded and changes nothing, because it
contributes nothing to either side.

**No convention is retried until one balances.**  Amounts in BAI2 are unsigned
and the type code carries direction, so a control total is the sum of the
amounts as written.  Some senders instead sign their debits.  This module
implements the literal reading and reports the delta when it fails; it does not
try the other convention to see whether that one closes.  Trying conventions
until one passes is how a file with a genuine error gets silently repaired into
a P0 — the arithmetic would close, and nothing would record that it only closed
on the second attempt.

**A test or deletion group is refused p0 however clean its arithmetic.**  Group
status ``4`` marks a test file and ``2`` marks a deletion.  Both can be
arithmetically perfect while asserting nothing about money that moved: a test
file states no fact about any account, and a deletion states the withdrawal of
one.  P0 auto-admits to the verified ledger with no human act (`13` §2.2), so a
test file reaching it would be the exact failure the class exists to prevent.
The reservation is recorded on :attr:`Bai2File.admissibility_reservations` and
is visible rather than folded into the arithmetic, which stays a report of what
the numbers did.  Status ``3``, a correction, is recorded without reservation:
it does assert what moved.  That it implies an earlier file is an intake
question (`13` §3) and not a parse question.

**Continuation text is retained, never interpreted.**  The ``16`` record's text
field and its ``88`` continuations are free-form and bank-specific.  `12` §6.1
makes the same point about MT940's ``:86:``: the balance check is sound while
the narrative parse is not.  So the text is preserved verbatim — commas within
it restored, continuation boundaries kept as line breaks — and no meaning is
read out of it here.

**Anything that is not a conformant BAI2 raises.**  A record out of sequence, a
count that is not a count, an amount outside the integer lexical space, a
funds-type sub-field that does not resolve: these are not unbalanced files,
they are files this module cannot claim to have read, and returning a proof
class for them would be the error the taxonomy exists to prevent.

Reading a hostile flat file
---------------------------

BAI2 has no entities, no external references and no schema, so the XML attack
surface is absent.  What it has instead is field misalignment, and the
misalignment is silent.

The ``Funds Type`` field is the hazard.  It is a single character that
sometimes announces further fields: ``S`` is followed by three, ``V`` by two,
and ``D`` by a count and then that many day-and-amount pairs.  A parser that
reads it as one field regardless will take the *next* field — an availability
amount — as the bank reference number, and every field after it shifts by the
same amount.  The record still parses.  The file still balances, because the
amounts that moved were never in the control total.  This module resolves the
sub-fields explicitly and refuses a funds type it does not recognise, because
the alternative failure is invisible.

A size ceiling applies for the same reason it does in camt.053, and the file is
decoded strictly rather than with a fallback: a fallback encoding silently
substitutes characters, and the substitution would land in exactly the payee
descriptions where a forensic reader most needs the bytes to have survived.
Unlike XML, a BAI2 file declares no encoding, so a caller that has already
decoded it has not overruled anything the file said — which is why, and only
why, this entry point accepts ``str`` where :func:`parse_camt053` does not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

from postgres.models.enums import (
    LocatorKind,
    ReconciliationStatus,
    TransactionDirection,
)
from services.financial.locators import Locator
from services.financial.money import Money, MoneyError, get_currency, sum_money
from services.financial.proof_class import ProofClass, SourceShape, assign_proof_class


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class Bai2Error(Exception):
    """Base for every refusal in this module."""


class NotABai2Error(Bai2Error):
    """Readable text that is not a BAI2 file."""


class Bai2MalformedFileError(Bai2Error):
    """Structurally broken: a record out of sequence, or a field that will not resolve."""


class Bai2MissingFieldError(Bai2Error):
    """A mandatory field is absent or empty."""


class Bai2AmountError(Bai2Error):
    """A figure is not exactly representable as money."""


class Bai2CurrencyError(Bai2Error):
    """No currency can be settled for an account, or the one settled is unusable.

    Raised on absence, not on disagreement.  An account stating a currency its
    group does not is ordinary: the ``02`` currency is a default for the
    accounts beneath it, not a constraint on them, and a corporate group
    holding accounts in several currencies is a common shape rather than a
    defect.  Refusing it would reject conformant files.
    """


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: A BAI2 file is a feed of records, not a rectangle on a page.  Stated once so
#: that no caller has to decide, and so that the absence of a click-through
#: target reads as a property of the format rather than a defect in a reader.
BAI2_LOCATOR: Locator = Locator(kind=LocatorKind.not_positional)

#: A ceiling on what will be read into memory.  A cash-management file for a
#: single day across an entire corporate group is large but not unbounded;
#: something far past this is a different kind of object and refusing it is
#: cheaper than discovering what it is.
BAI2_MAX_FILE_BYTES: int = 64 * 1024 * 1024

BAI2_FILE_HEADER = "01"
BAI2_GROUP_HEADER = "02"
BAI2_ACCOUNT_HEADER = "03"
BAI2_TRANSACTION_DETAIL = "16"
BAI2_CONTINUATION = "88"
BAI2_ACCOUNT_TRAILER = "49"
BAI2_GROUP_TRAILER = "98"
BAI2_FILE_TRAILER = "99"

#: Opening and closing *ledger* balances: the two ends of the balance identity.
#: Available balances (``040``/``045``) are deliberately not used for it — they
#: net out float, so the transactions in the file do not explain the movement
#: between them and the identity would fail on a file with nothing wrong.
BAI2_OPENING_LEDGER = "010"
BAI2_CLOSING_LEDGER = "015"

#: The account-level summary codes, the BAI2 analogue of camt.053 ``TxsSummry``.
BAI2_TOTAL_CREDITS = "100"
BAI2_TOTAL_DEBITS = "400"

#: Group status codes from the ``02`` record.
BAI2_GROUP_STATUS_UPDATE = "1"
BAI2_GROUP_STATUS_DELETION = "2"
BAI2_GROUP_STATUS_CORRECTION = "3"
BAI2_GROUP_STATUS_TEST = "4"

#: The only version this parser claims to read.  ``01`` field 9 states it.
BAI2_VERSION = "2"

#: Funds types that announce further fields, and how many.  ``D`` is variable
#: and handled separately.  An unrecognised funds type is refused rather than
#: assumed to announce none, because assuming none is what shifts every
#: subsequent field by an amount nothing will detect.
_FUNDS_TYPE_EXTRA_FIELDS = {
    "": 0,
    "0": 0,
    "1": 0,
    "2": 0,
    "S": 3,
    "V": 2,
    "Z": 0,
}
_FUNDS_TYPE_DISTRIBUTED = "D"

#: An amount is an optionally-signed run of digits and nothing else.  Applied
#: before ``int`` sees the text: ``int`` accepts underscores and surrounding
#: whitespace, and ``"1_000"`` would parse as a thousand from a file that never
#: said one.
_AMOUNT_RE = re.compile(r"^[+-]?\d+$")

#: A type code is exactly three digits.  Anything else is not a code this
#: module can place in a direction range.
_TYPE_CODE_RE = re.compile(r"^\d{3}$")

_RECORD_CODE_RE = re.compile(r"^\d{2}$")


# ---------------------------------------------------------------------------
# Lexical helpers
# ---------------------------------------------------------------------------


def _direction_for_type_code(code: str) -> Optional[TransactionDirection]:
    """The direction a detail type code fixes, or ``None`` if it fixes none.

    The ranges are the specification's: 100–399 credit, 400–699 debit.  Codes
    below 100 are account status rather than movement, and codes at 700 and
    above are loan, unassigned or customer-defined — for those the direction is
    a matter of local convention between two institutions, which is precisely
    what this module has no access to.  ``None`` is returned rather than a
    guess, and the caller decides what to do about it.
    """
    if not _TYPE_CODE_RE.match(code):
        return None
    value = int(code)
    if 100 <= value <= 399:
        return TransactionDirection.credit
    if 400 <= value <= 699:
        return TransactionDirection.debit
    return None


def _parse_amount(text: str, currency: str, *, context: str) -> Money:
    """Read a BAI2 amount: an integer count of the currency's minor units.

    No decimal point appears in a BAI2 amount, so there is nothing to round and
    no separator convention to infer.  The scaling is entirely the currency's,
    which is why the currency has to be settled before any amount is read.
    """
    raw = text.strip()
    if not raw:
        raise Bai2MissingFieldError(f"{context}: the amount is empty")
    if not _AMOUNT_RE.match(raw):
        raise Bai2AmountError(
            f"{context}: {text!r} is not a BAI2 amount; amounts are written as "
            "an optionally signed run of digits in the currency's minor unit, "
            "with no decimal point and no separators"
        )
    try:
        return Money.from_minor_units(int(raw), currency)
    except MoneyError as exc:
        raise Bai2AmountError(f"{context}: {text!r} is not usable as {currency}: {exc}") from exc


def _parse_count(text: str, *, context: str) -> int:
    """Read a record or item count: a non-negative integer, or refuse."""
    raw = text.strip()
    if not raw:
        raise Bai2MissingFieldError(f"{context}: the count is empty")
    if not raw.isdigit():
        raise Bai2MalformedFileError(
            f"{context}: {text!r} is not a count; a count is a run of digits"
        )
    return int(raw)


def _optional(fields: Sequence[str], index: int) -> Optional[str]:
    """Field ``index`` if present and non-empty, else ``None``."""
    if index >= len(fields):
        return None
    value = fields[index].strip()
    return value or None


def _required(fields: Sequence[str], index: int, name: str, *, context: str) -> str:
    value = _optional(fields, index)
    if value is None:
        raise Bai2MissingFieldError(
            f"{context}: {name} is mandatory and is absent (field {index + 1})"
        )
    return value


def _weakest(statuses: Iterable[ReconciliationStatus]) -> ReconciliationStatus:
    """The least favourable outcome in a run of them.

    Order: ``unbalanced`` beats everything, then ``unavailable``, then
    ``not_attempted``, and ``balanced`` only when every check balanced.  A
    single failure anywhere therefore governs, which is what stops a file with
    one clean account and one broken one from presenting as clean.
    """
    seen = list(statuses)
    if not seen:
        return ReconciliationStatus.not_attempted
    for candidate in (
        ReconciliationStatus.unbalanced,
        ReconciliationStatus.unavailable,
        ReconciliationStatus.not_attempted,
    ):
        if candidate in seen:
            return candidate
    return ReconciliationStatus.balanced


# ---------------------------------------------------------------------------
# Physical records, and folding continuations into logical ones
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Bai2LogicalRecord:
    """One record and the continuations folded into it.

    ``segments`` keeps the fields of each physical line separately, because the
    line boundary is the only thing that survives of a narrative's original
    shape and discarding it would run two descriptions together into one
    sentence that neither line said.  ``fields`` is the flat view the
    structured records are read from.
    """

    code: str
    segments: tuple[tuple[str, ...], ...]
    line_numbers: tuple[int, ...]

    @property
    def fields(self) -> tuple[str, ...]:
        """Every field, continuations appended, with the record code at index 0."""
        return tuple(value for segment in self.segments for value in segment)

    @property
    def physical_record_count(self) -> int:
        """How many lines this record occupies, which is what the trailers count."""
        return len(self.segments)

    @property
    def first_line(self) -> int:
        return self.line_numbers[0]

    def tail_text(self, start: int) -> Optional[str]:
        """Fields from ``start`` onward as text, commas and line breaks restored.

        The free-text field of a ``16`` record runs to the end of the record and
        may contain commas, which the field split has already broken apart.
        Rejoining with commas puts them back exactly — exactly, because
        :func:`_split_physical` does not strip, so the space a sender wrote
        after a comma survives the round trip.  Joining the segments with
        newlines keeps the continuation boundaries the sender chose.  Only the
        outer edges are stripped, and only because those are padding to the
        record length rather than anything the sender wrote.

        Nothing here interprets the result — `12` §6.1's point about MT940's
        ``:86:`` applies equally: the balance check is sound while the narrative
        parse is not, so the narrative is carried and not read.
        """
        pieces: list[str] = []
        offset = 0
        for segment in self.segments:
            end = offset + len(segment)
            if end > start:
                take = segment[max(start - offset, 0):]
                pieces.append(",".join(take))
            offset = end
        joined = "\n".join(pieces).strip()
        return joined or None


def _split_physical(line: str) -> tuple[str, ...]:
    """Split one physical record into fields, dropping the record terminator.

    A single trailing ``/`` is the terminator and is removed.  An interior
    ``/`` is left alone: it occurs in real narrative — dates written ``01/15``,
    reference numbers, account fragments — and truncating the record there
    would discard the remainder of a field this module does not interpret,
    silently and for no gain.

    Fields are returned **unstripped**.  Every structured reader below —
    :func:`_optional`, :func:`_required`, :func:`_parse_amount`,
    :func:`_parse_count`, :func:`_parse_minor_units`,
    :func:`_consume_funds_type` — strips what it reads, so padding costs
    nothing there; but :meth:`Bai2LogicalRecord.tail_text` rebuilds free text by
    rejoining fields with the commas that split them, and stripping first would
    return narrative the sender did not write.  ``"PAID, THEN REVERSED"`` comes
    back as ``"PAID,THEN REVERSED"`` — a quiet edit to a string that may end up
    quoted in an exhibit.  The line's own trailing whitespace is removed, since
    that is padding to the record length rather than content.
    """
    stripped = line.rstrip()
    if stripped.endswith("/"):
        stripped = stripped[:-1]
    return tuple(stripped.split(","))


def _fold_records(text: str) -> tuple[Bai2LogicalRecord, ...]:
    """Read physical lines into logical records, folding ``88`` continuations.

    A continuation extends the field list of the record before it.  Treating it
    as a record in its own right would leave the parent short of fields and the
    continuation short of a code, and neither would be readable.
    """
    folded: list[list] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        fields = _split_physical(raw)
        code = fields[0].strip()
        if not _RECORD_CODE_RE.match(code):
            raise Bai2MalformedFileError(
                f"line {number}: the record begins {code!r}; a BAI2 record "
                "begins with a two-digit record code"
            )
        if code == BAI2_CONTINUATION:
            if not folded:
                raise Bai2MalformedFileError(
                    f"line {number}: a {BAI2_CONTINUATION} continuation record "
                    "opens the file; a continuation extends the record before "
                    "it and there is none"
                )
            folded[-1][1].append(tuple(fields[1:]))
            folded[-1][2].append(number)
            continue
        folded.append([code, [fields], [number]])

    return tuple(
        Bai2LogicalRecord(
            code=code,
            segments=tuple(segments),
            line_numbers=tuple(numbers),
        )
        for code, segments, numbers in folded
    )


def _consume_funds_type(
    fields: Sequence[str], index: int, *, context: str
) -> tuple[Optional[str], int]:
    """Read a funds type and skip whatever sub-fields it announces.

    This is the field-misalignment hazard described in the module docstring, and
    it is the reason this is a function rather than an index increment.  ``S``
    announces three availability amounts, ``V`` a value date and time, and ``D``
    a count followed by that many day-and-amount pairs.  Reading any of them as
    a single field shifts every subsequent field by the difference, and the
    record still parses.

    Returns the funds type and the index of the first field after it.
    """
    if index >= len(fields):
        return None, index
    raw = fields[index].strip().upper()
    cursor = index + 1

    if raw == _FUNDS_TYPE_DISTRIBUTED:
        if cursor >= len(fields):
            raise Bai2MalformedFileError(
                f"{context}: funds type 'D' announces a distribution count and "
                "the record ends before it"
            )
        distributions = _parse_count(
            fields[cursor], context=f"{context} funds type D distribution count"
        )
        cursor += 1
        needed = distributions * 2
        if cursor + needed > len(fields):
            raise Bai2MalformedFileError(
                f"{context}: funds type 'D' announces {distributions} "
                f"distributions, which is {needed} further fields, and only "
                f"{len(fields) - cursor} remain"
            )
        return raw, cursor + needed

    if raw not in _FUNDS_TYPE_EXTRA_FIELDS:
        raise Bai2MalformedFileError(
            f"{context}: {fields[index]!r} is not a funds type this parser "
            "recognises.  It is refused rather than assumed to announce no "
            "sub-fields, because that assumption shifts every field after it "
            "and the resulting record parses cleanly while meaning something "
            "else entirely"
        )
    extra = _FUNDS_TYPE_EXTRA_FIELDS[raw]
    if cursor + extra > len(fields):
        raise Bai2MalformedFileError(
            f"{context}: funds type {raw!r} announces {extra} further fields "
            f"and only {len(fields) - cursor} remain"
        )
    return (raw or None), cursor + extra


# ---------------------------------------------------------------------------
# What a parsed file is made of
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Bai2Summary:
    """One ``(type code, amount, item count, funds type)`` quad from an ``03``.

    These are the account's own declarations about itself: its opening and
    closing balances, and where the sender chose to state them, its totals and
    item counts by direction.
    """

    type_code: str
    amount: Optional[Money]
    item_count: Optional[int]
    funds_type: Optional[str]


@dataclass(frozen=True, slots=True)
class Bai2Transaction:
    """One ``16`` detail record, with its ``88`` continuations folded in."""

    index: int
    type_code: str
    amount: Money
    funds_type: Optional[str]
    bank_reference: Optional[str]
    customer_reference: Optional[str]
    text: Optional[str]
    line_number: int

    @property
    def direction(self) -> Optional[TransactionDirection]:
        """Credit or debit, or ``None`` where the type code fixes neither."""
        return _direction_for_type_code(self.type_code)

    @property
    def locator(self) -> Locator:
        return BAI2_LOCATOR


@dataclass(frozen=True, slots=True)
class Bai2BalanceIdentity:
    """``010 + ΣCredits − ΣDebits = 015``, over transactions with a known direction.

    Declines rather than assumes when an endpoint balance is absent or when any
    transaction's direction is undetermined.  The reasoning is the one
    :func:`~services.financial.camt053._check_balances` gives: substituting zero
    for a missing opening manufactures a delta exactly equal to the real
    opening balance, which reads as a large unexplained discrepancy and sends a
    reviewer hunting for fraud in a file whose only defect is a balance the
    sender did not state.
    """

    status: ReconciliationStatus
    opening: Optional[Money]
    printed_closing: Optional[Money]
    computed_closing: Optional[Money]
    delta: Optional[Money]
    credits: Money
    debits: Money
    credit_count: int
    debit_count: int
    undirected_count: int
    unavailable_reason: Optional[str] = None


@dataclass(frozen=True, slots=True)
class Bai2SummaryIdentity:
    """The ``03`` record's declared ``100``/``400`` totals against the ``16`` records.

    The BAI2 analogue of camt.053's ``TxsSummry``, and optional in the same way:
    a sender may state neither, either or both.  Absence is ``not_attempted``,
    because nothing was claimed and nothing is contradicted.
    """

    status: ReconciliationStatus
    declared_credits: Optional[Money]
    declared_debits: Optional[Money]
    declared_credit_count: Optional[int]
    declared_debit_count: Optional[int]
    observed_credits: Money
    observed_debits: Money
    observed_credit_count: int
    observed_debit_count: int
    credit_delta: Optional[Money]
    debit_delta: Optional[Money]
    unavailable_reason: Optional[str] = None


@dataclass(frozen=True, slots=True)
class Bai2ControlTotal:
    """A trailer against what it closes: ``49``, ``98`` or ``99``.

    One type for all three levels because it is one question asked three times —
    does the trailer agree with the records it encloses — and a reader
    comparing the levels should not have to translate between three shapes to
    do it.  ``level`` names which trailer, and ``declared_child_count`` is
    ``None`` at account level, where the ``49`` record counts records only.

    ``basis`` says in words what went into the computed total, because the
    three levels sum three different things and the number on its own does not
    say which.  It is carried on the artefact rather than left in a source
    comment: a reviewer looking at a delta needs to know what was added up
    before the delta means anything, and that reviewer is not reading this
    file.

    **The comparison is integral, not monetary.**  A BAI2 control total is
    defined by the specification as the sum of the amount fields as
    transmitted — a checksum over digits, asserting that nothing was lost in
    carriage.  It is not a financial quantity and the file gives it no currency
    of its own.  So the check that decides ``status`` compares
    ``declared_minor_units`` against ``computed_minor_units``, which is exactly
    what the sender computed and needs no currency to be meaningful.

    ``currency`` and the three ``Money`` fields are populated in addition, and
    only where every contributing amount shares one currency — always at
    account level, since a BAI2 account is single-currency; at group and file
    level only when the accounts or groups beneath agree.  Modelling the
    comparison the other way round, as ``Money`` first, would have made a
    multi-currency file uncheckable at the top two levels and kept it off P0
    for no reason the file is answerable for: the mixed sum is the bank's own
    checksum, and it either matches or it does not.
    """

    level: str
    status: ReconciliationStatus
    basis: str
    declared_minor_units: Optional[int]
    computed_minor_units: Optional[int]
    minor_unit_delta: Optional[int]
    declared_record_count: Optional[int]
    computed_record_count: int
    currency: Optional[str] = None
    declared_total: Optional[Money] = None
    computed_total: Optional[Money] = None
    total_delta: Optional[Money] = None
    declared_child_count: Optional[int] = None
    computed_child_count: Optional[int] = None
    unavailable_reason: Optional[str] = None

    @property
    def record_count_agrees(self) -> bool:
        return self.declared_record_count == self.computed_record_count

    @property
    def child_count_agrees(self) -> bool:
        return self.declared_child_count == self.computed_child_count


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------

#: What each level's control total is a sum of, in words, for
#: :attr:`Bai2ControlTotal.basis`.  Named constants rather than literals at the
#: construction sites so that the three cannot drift apart, and so that a test
#: asserting on a basis is asserting on the same string the artefact carries.
#: The account basis says "every amount" and means the *primary* amount: one
#: per ``03`` summary and one per ``16`` detail.  The availability amounts
#: carried in an ``S``, ``V`` or ``D`` funds type are not added.
#:
#: The specification's wording — the sum of the amount fields — does not settle
#: this, and implementations differ.  A parser that tried the sum both ways and
#: kept whichever balanced would report a passing control total on a file whose
#: totals do not in fact agree with anything, having chosen the reading that
#: made the failure disappear.  So one reading is fixed, the dominant one, and a
#: file written to the other convention reports ``unbalanced`` with a delta a
#: reader can recognise: it equals the availability amounts exactly.
#:
#: Fixed structurally rather than by a flag.  An earlier draft carried a
#: ``_CONTROL_TOTAL_INCLUDES_AVAILABILITY = False`` constant, which was never
#: read by anything: the availability figures are consumed by
#: :func:`_consume_funds_type` and never stored, so there is nothing for a sum
#: to reach even if it wanted to.  A constant that documents a decision without
#: enforcing it is worse than no constant, because the next reader flips it,
#: sees every test still pass, and concludes the convention does not matter.
#: And a working switch would be worse still — it is precisely the knob that
#: could be turned to make a real failure disappear.
_ACCOUNT_CONTROL_BASIS = (
    "every amount in the 03 account identifier record and every amount in the "
    "16 transaction detail records it heads"
)
_GROUP_CONTROL_BASIS = "the account control totals declared by the 49 records in this group"
_FILE_CONTROL_BASIS = "the group control totals declared by the 98 records in this file"


def _partition(
    transactions: Sequence["Bai2Transaction"], currency: str
) -> tuple[Money, Money, int, int, int]:
    """Credits, debits, their counts, and the number of transactions that block.

    A transaction blocks the balance identity when its type code fixes no
    direction *and* its amount is non-zero.  A zero amount contributes nothing
    to either side, so not knowing which side it belongs on costs nothing, and
    counting it would decline an identity that is in fact complete.
    """
    credits: list[Money] = []
    debits: list[Money] = []
    blocking = 0
    for txn in transactions:
        direction = txn.direction
        if direction is TransactionDirection.credit:
            credits.append(txn.amount)
        elif direction is TransactionDirection.debit:
            debits.append(txn.amount)
        elif not txn.amount.is_zero:
            blocking += 1
    return (
        sum_money(credits, currency),
        sum_money(debits, currency),
        len(credits),
        len(debits),
        blocking,
    )


def _summary_amount(
    summaries: Sequence["Bai2Summary"], code: str
) -> Optional["Bai2Summary"]:
    """The first summary carrying a given status or total type code."""
    for item in summaries:
        if item.type_code == code:
            return item
    return None


def _check_balance_identity(
    summaries: Sequence["Bai2Summary"],
    transactions: Sequence["Bai2Transaction"],
    currency: str,
) -> Bai2BalanceIdentity:
    """``010 + ΣCredits − ΣDebits = 015``, or a recorded reason for declining.

    Four things stop the sum, and each is reported as ``unavailable`` with the
    reason rather than as a failure, because in none of them has any arithmetic
    disagreed:

    *No opening, or no closing.*  Substituting zero manufactures a delta equal
    to the real balance, which reads as a large unexplained discrepancy and
    sends a reviewer hunting for fraud in a file whose only defect is a figure
    the sender chose not to state.

    *A transaction whose direction is undetermined.*  The type code is in a
    range whose meaning is a local convention between two institutions, and
    picking a side would put a real amount on a guess.

    *A summary-only account.*  An ``03`` that declares non-zero totals with no
    ``16`` records beneath it is reporting a period it has not itemised.  Its
    credits and debits observed here are both zero, so the identity would hold
    only for a static account and fail loudly for every other — reporting that
    as ``unbalanced`` would accuse a perfectly ordinary summary file of not
    adding up.
    """
    opening_summary = _summary_amount(summaries, BAI2_OPENING_LEDGER)
    closing_summary = _summary_amount(summaries, BAI2_CLOSING_LEDGER)
    opening = opening_summary.amount if opening_summary is not None else None
    printed = closing_summary.amount if closing_summary is not None else None

    credits, debits, credit_count, debit_count, blocking = _partition(
        transactions, currency
    )

    declared_credits = _summary_amount(summaries, BAI2_TOTAL_CREDITS)
    declared_debits = _summary_amount(summaries, BAI2_TOTAL_DEBITS)
    summary_only = not transactions and any(
        entry is not None
        and (
            (entry.amount is not None and not entry.amount.is_zero)
            or bool(entry.item_count)
        )
        for entry in (declared_credits, declared_debits)
    )

    def decline(reason: str) -> Bai2BalanceIdentity:
        return Bai2BalanceIdentity(
            status=ReconciliationStatus.unavailable,
            opening=opening,
            printed_closing=printed,
            computed_closing=None,
            delta=None,
            credits=credits,
            debits=debits,
            credit_count=credit_count,
            debit_count=debit_count,
            undirected_count=blocking,
            unavailable_reason=reason,
        )

    if opening is None:
        return decline(
            "the account states no opening ledger balance (type code "
            f"{BAI2_OPENING_LEDGER}), so there is nothing for the transactions "
            "to move from"
        )
    if printed is None:
        return decline(
            "the account states no closing ledger balance (type code "
            f"{BAI2_CLOSING_LEDGER}), so there is nothing to check the "
            "transactions against"
        )
    if blocking:
        return decline(
            f"{blocking} transaction(s) carry a type code that fixes neither "
            "credit nor debit, and assigning a side by guess would put a real "
            "amount on the wrong one"
        )
    if summary_only:
        return decline(
            "the account declares totals but carries no 16 transaction detail "
            "records, so the movement it reports has not been itemised and "
            "cannot be summed"
        )

    computed = opening + credits - debits
    delta = computed - printed
    return Bai2BalanceIdentity(
        status=(
            ReconciliationStatus.balanced
            if delta.is_zero
            else ReconciliationStatus.unbalanced
        ),
        opening=opening,
        printed_closing=printed,
        computed_closing=computed,
        delta=delta,
        credits=credits,
        debits=debits,
        credit_count=credit_count,
        debit_count=debit_count,
        undirected_count=blocking,
    )


def _check_summary_identity(
    summaries: Sequence["Bai2Summary"],
    transactions: Sequence["Bai2Transaction"],
    currency: str,
) -> Bai2SummaryIdentity:
    """The ``03`` record's ``100``/``400`` totals against the ``16`` records.

    Optional at both ends: a sender may declare neither, either or both, and
    may state an amount without an item count or the reverse.  Each half is
    compared only where it was declared, and absence is never a failure.

    ``not_attempted`` when nothing was declared — nothing was claimed, so
    nothing is contradicted.  ``unavailable`` when totals were declared but no
    detail records exist to compare them against, for the reason
    :func:`_check_balance_identity` gives: a summary-only account has not
    failed a check, it has declined to itemise.
    """
    declared_credit = _summary_amount(summaries, BAI2_TOTAL_CREDITS)
    declared_debit = _summary_amount(summaries, BAI2_TOTAL_DEBITS)
    observed_credits, observed_debits, credit_count, debit_count, _ = _partition(
        transactions, currency
    )

    declared_credits = declared_credit.amount if declared_credit is not None else None
    declared_debits = declared_debit.amount if declared_debit is not None else None
    declared_credit_count = (
        declared_credit.item_count if declared_credit is not None else None
    )
    declared_debit_count = (
        declared_debit.item_count if declared_debit is not None else None
    )

    claimed = [
        value
        for value in (
            declared_credits,
            declared_debits,
            declared_credit_count,
            declared_debit_count,
        )
        if value is not None
    ]

    def outcome(
        status: ReconciliationStatus,
        credit_delta: Optional[Money],
        debit_delta: Optional[Money],
        reason: Optional[str] = None,
    ) -> Bai2SummaryIdentity:
        return Bai2SummaryIdentity(
            status=status,
            declared_credits=declared_credits,
            declared_debits=declared_debits,
            declared_credit_count=declared_credit_count,
            declared_debit_count=declared_debit_count,
            observed_credits=observed_credits,
            observed_debits=observed_debits,
            observed_credit_count=credit_count,
            observed_debit_count=debit_count,
            credit_delta=credit_delta,
            debit_delta=debit_delta,
            unavailable_reason=reason,
        )

    if not claimed:
        return outcome(ReconciliationStatus.not_attempted, None, None)
    if not transactions:
        return outcome(
            ReconciliationStatus.unavailable,
            None,
            None,
            "the account declares totals but carries no 16 transaction detail "
            "records to compare them against",
        )

    credit_delta = (
        observed_credits - declared_credits if declared_credits is not None else None
    )
    debit_delta = (
        observed_debits - declared_debits if declared_debits is not None else None
    )
    agrees = (
        (credit_delta is None or credit_delta.is_zero)
        and (debit_delta is None or debit_delta.is_zero)
        and (declared_credit_count is None or declared_credit_count == credit_count)
        and (declared_debit_count is None or declared_debit_count == debit_count)
    )
    return outcome(
        ReconciliationStatus.balanced if agrees else ReconciliationStatus.unbalanced,
        credit_delta,
        debit_delta,
    )


def _check_control_total(
    *,
    level: str,
    basis: str,
    declared: Optional[int],
    computed: Optional[int],
    currency: Optional[str],
    declared_record_count: Optional[int],
    computed_record_count: int,
    declared_child_count: Optional[int] = None,
    computed_child_count: Optional[int] = None,
    computed_reason: Optional[str] = None,
) -> Bai2ControlTotal:
    """Compare one trailer against what it closes.

    The control total is mandatory at all three levels, so an absent one is a
    defect in the file rather than a silence the sender was entitled to — but
    it is reported as ``unavailable`` and not as ``unbalanced``, because the
    two say different things to a reviewer.  ``unbalanced`` says the file
    contradicts itself and something in it is wrong.  ``unavailable`` says the
    check could not be run.  Neither reaches P0, so nothing is admitted on the
    strength of the distinction; it exists so that the reviewer looks in the
    right place.

    The record count is compared with the same weight as the total.  A file
    whose amounts sum correctly but whose record count is short by one has lost
    a record carrying no amount — a ``16`` for a zero-value entry, or an ``88``
    carrying the payee's name — and the sum will never notice.
    """
    computed_money = (
        Money.from_minor_units(computed, currency)
        if currency is not None and computed is not None
        else None
    )
    declared_money = (
        Money.from_minor_units(declared, currency)
        if currency is not None and declared is not None
        else None
    )

    if computed is None:
        # A group or file total is the sum of the totals its children declared,
        # not of their contents — see :func:`_group_control`.  A child that
        # declared none leaves nothing to sum, and that is a different failure
        # from a trailer that declared none itself, so it says so.
        return Bai2ControlTotal(
            level=level,
            status=ReconciliationStatus.unavailable,
            basis=basis,
            declared_minor_units=declared,
            computed_minor_units=None,
            minor_unit_delta=None,
            declared_record_count=declared_record_count,
            computed_record_count=computed_record_count,
            currency=currency,
            declared_total=declared_money,
            computed_total=None,
            total_delta=None,
            declared_child_count=declared_child_count,
            computed_child_count=computed_child_count,
            unavailable_reason=(
                computed_reason
                or f"the {level} control total could not be computed"
            ),
        )

    if declared is None:
        return Bai2ControlTotal(
            level=level,
            status=ReconciliationStatus.unavailable,
            basis=basis,
            declared_minor_units=None,
            computed_minor_units=computed,
            minor_unit_delta=None,
            declared_record_count=declared_record_count,
            computed_record_count=computed_record_count,
            currency=currency,
            declared_total=None,
            computed_total=computed_money,
            total_delta=None,
            declared_child_count=declared_child_count,
            computed_child_count=computed_child_count,
            unavailable_reason=(
                f"the {level} trailer states no control total; the total is "
                "mandatory in a conformant BAI2 file"
            ),
        )

    delta = computed - declared
    agrees = (
        delta == 0
        and (declared_record_count is None or declared_record_count == computed_record_count)
        and (declared_child_count is None or declared_child_count == computed_child_count)
    )
    status = (
        ReconciliationStatus.balanced if agrees else ReconciliationStatus.unbalanced
    )
    reason: Optional[str] = None
    if delta == 0 and status is ReconciliationStatus.unbalanced:
        # The amounts agree and a count does not.  Said plainly, because a
        # reviewer shown a zero delta and a failure will otherwise assume the
        # failure is the tool's.
        reason = (
            f"the {level} control total agrees but the declared record or "
            "child count does not"
        )
    return Bai2ControlTotal(
        level=level,
        status=status,
        basis=basis,
        declared_minor_units=declared,
        computed_minor_units=computed,
        minor_unit_delta=delta,
        declared_record_count=declared_record_count,
        computed_record_count=computed_record_count,
        currency=currency,
        declared_total=declared_money,
        computed_total=computed_money,
        total_delta=(
            computed_money - declared_money
            if computed_money is not None and declared_money is not None
            else None
        ),
        declared_child_count=declared_child_count,
        computed_child_count=computed_child_count,
        unavailable_reason=reason,
    )


# ---------------------------------------------------------------------------
# Accounts, groups, and the file
# ---------------------------------------------------------------------------

#: Where an account's currency came from.  Recorded on every account because
#: the three are not equally strong evidence: the account said so, the group
#: said so, or the caller supplied it because nothing in the file did.  A
#: reviewer weighing a figure is entitled to know which.
BAI2_CURRENCY_FROM_ACCOUNT = "account"
BAI2_CURRENCY_FROM_GROUP = "group"
BAI2_CURRENCY_FROM_CALLER = "caller"


def _parse_minor_units(text: str, *, context: str) -> int:
    """Read a control total: a signed integer of minor units, no currency.

    Separate from :func:`_parse_amount` because a control total is not money.
    It is a checksum over the amounts as transmitted, it may legitimately be
    negative, and above account level it may sum figures from more than one
    currency — at which point calling it money would be a category error
    dressed up as a type.
    """
    raw = text.strip()
    if not raw:
        raise Bai2MissingFieldError(f"{context}: the control total is empty")
    if not _AMOUNT_RE.match(raw):
        raise Bai2AmountError(
            f"{context}: {text!r} is not a control total; a control total is "
            "an optionally signed run of digits"
        )
    return int(raw)


def _common_currency(codes: Iterable[str]) -> Optional[str]:
    """The single currency shared by a run of them, or ``None`` if they differ.

    ``None`` for an empty run too, and deliberately: there is no currency to
    name, so there is no ``Money`` to build, and the integer comparison that
    decides the control total runs regardless.
    """
    distinct = set(codes)
    return distinct.pop() if len(distinct) == 1 else None


@dataclass(frozen=True, slots=True)
class Bai2Account:
    """One ``03`` … ``49`` block: an account, its declarations and its detail."""

    customer_account_number: str
    currency: str
    currency_source: str
    summaries: tuple[Bai2Summary, ...]
    transactions: tuple[Bai2Transaction, ...]
    balance_identity: Bai2BalanceIdentity
    summary_identity: Bai2SummaryIdentity
    control_total: Bai2ControlTotal
    first_line: int

    def summary(self, code: str) -> Optional[Bai2Summary]:
        """The first summary carrying a given type code."""
        return _summary_amount(self.summaries, code)

    @property
    def opening_balance(self) -> Optional[Money]:
        entry = self.summary(BAI2_OPENING_LEDGER)
        return entry.amount if entry is not None else None

    @property
    def closing_balance(self) -> Optional[Money]:
        entry = self.summary(BAI2_CLOSING_LEDGER)
        return entry.amount if entry is not None else None

    @property
    def locator(self) -> Locator:
        return BAI2_LOCATOR

    @property
    def reconciliation_status(self) -> ReconciliationStatus:
        """The ``49`` control total, weakened by any identity that failed.

        The shape of this rule is the one
        :attr:`~services.financial.camt053.Camt053Statement.reconciliation_status`
        settled — a mandatory check governs unconditionally, and an optional
        one weakens the outcome only by *failing*, never by being absent and
        never by declining.  What differs is which check is which.

        In camt.053 the balance identity is mandatory, because ``CLBD`` is.  In
        BAI2 it is not: ``010`` and ``015`` are optional status codes and a
        conformant file may omit either.  The ``49`` control total is the
        mandatory one, so it governs here and the two identities corroborate.

        The two mandatory checks are also not equivalent, and reporting only
        one would overstate what the file has shown.  A control total is a
        checksum: it establishes that the amounts arrived as sent.  The balance
        identity establishes something the checksum cannot — that those amounts
        account for the movement between the two balances.  Both are kept.
        """
        failures = [
            check.status
            for check in (self.balance_identity, self.summary_identity)
            if check.status is ReconciliationStatus.unbalanced
        ]
        return _weakest([self.control_total.status, *failures])


@dataclass(frozen=True, slots=True)
class Bai2Group:
    """One ``02`` … ``98`` block: a set of accounts as of one date and time."""

    ultimate_receiver: Optional[str]
    originator: Optional[str]
    status: Optional[str]
    as_of_date: Optional[str]
    as_of_time: Optional[str]
    currency: Optional[str]
    as_of_date_modifier: Optional[str]
    accounts: tuple[Bai2Account, ...]
    control_total: Bai2ControlTotal
    first_line: int

    @property
    def admissibility_reservations(self) -> tuple[str, ...]:
        """Reasons this group must not auto-admit, whatever its arithmetic says.

        Kept out of the arithmetic on purpose.  A test group's totals can be
        flawless — they are generated to be — and folding the reservation into
        the reconciliation status would report an arithmetic failure that did
        not happen, sending a reviewer to look for a discrepancy in a file that
        has none.  The file adds up; it is simply not about money that moved.

        Status ``3`` (correction) draws no reservation.  A correction does
        assert what moved.  That it implies an earlier file whose records it
        supersedes is a question for intake and de-duplication (`13` §3), not a
        reason to distrust this one.
        """
        if self.status is None:
            return ()
        if self.status == BAI2_GROUP_STATUS_TEST:
            return (
                f"the group at line {self.first_line} carries status "
                f"{BAI2_GROUP_STATUS_TEST} (test); a test group asserts nothing "
                "about money that moved, however exactly it adds up",
            )
        if self.status == BAI2_GROUP_STATUS_DELETION:
            return (
                f"the group at line {self.first_line} carries status "
                f"{BAI2_GROUP_STATUS_DELETION} (deletion); it withdraws data "
                "sent earlier rather than reporting movement, and the records "
                "it names are the ones to be removed",
            )
        if self.status not in (
            BAI2_GROUP_STATUS_UPDATE,
            BAI2_GROUP_STATUS_CORRECTION,
        ):
            return (
                f"the group at line {self.first_line} carries status "
                f"{self.status!r}, which is not a BAI2 group status this parser "
                "recognises; what the group asserts is therefore unknown",
            )
        return ()

    @property
    def reconciliation_status(self) -> ReconciliationStatus:
        """The ``98`` control total together with every account beneath it.

        Unlike the account roll-up, nothing here is a corroboration to be
        discounted.  The group total and the accounts are both mandatory
        checks, and an account that failed is a failure of the group whether or
        not the ``98`` noticed — which it will not, since the ``98`` sums what
        the ``49`` records *declared* and a wrong declaration that is summed
        consistently agrees with itself all the way up.
        """
        return _weakest(
            [
                self.control_total.status,
                *[account.reconciliation_status for account in self.accounts],
            ]
        )


@dataclass(frozen=True, slots=True)
class Bai2File:
    """A parsed BAI2 file: its ``01`` header, its groups and its ``99`` trailer."""

    sender: Optional[str]
    receiver: Optional[str]
    creation_date: Optional[str]
    creation_time: Optional[str]
    file_identification: Optional[str]
    physical_record_length: Optional[int]
    block_size: Optional[int]
    version: Optional[str]
    groups: tuple[Bai2Group, ...]
    control_total: Bai2ControlTotal

    #: Fixed.  BAI2 is a structured file whose format mandates control totals,
    #: which is the whole of what the shape asserts (`13` §2.1).  It says
    #: nothing about whether those totals agree; that arrives separately, and
    #: the two together decide the class.
    source_shape: SourceShape = field(
        default=SourceShape.native_with_control_totals, init=False
    )

    @property
    def accounts(self) -> tuple[Bai2Account, ...]:
        """Every account in the file, in file order."""
        return tuple(
            account for group in self.groups for account in group.accounts
        )

    @property
    def transactions(self) -> tuple[Bai2Transaction, ...]:
        """Every ``16`` detail record in the file, in file order."""
        return tuple(
            txn
            for group in self.groups
            for account in group.accounts
            for txn in account.transactions
        )

    @property
    def admissibility_reservations(self) -> tuple[str, ...]:
        """Every group's reservations, gathered so a caller reads one list."""
        return tuple(
            reason
            for group in self.groups
            for reason in group.admissibility_reservations
        )

    @property
    def reconciliation_status(self) -> ReconciliationStatus:
        """The ``99`` control total together with every group beneath it."""
        return _weakest(
            [
                self.control_total.status,
                *[group.reconciliation_status for group in self.groups],
            ]
        )

    @property
    def proof_class(self) -> ProofClass:
        """The class this file earns, computed rather than asserted.

        The shape and the outcome go to
        :func:`~services.financial.proof_class.assign_proof_class`, which owns
        the rule; this module supplies the two inputs and has no vote on what
        they add up to.

        The one thing decided here is the reservation.  A test or deletion
        group can produce a file whose every control total agrees, and
        ``assign_proof_class`` would rightly call that p0 on the evidence it is
        given — the arithmetic did pass.  But p0 auto-admits with no human act
        (`13` §2.2), and admitting a test file to a verified ledger is a worse
        error than any this module's arithmetic could make.  So the promotion
        is withheld and the file lands at p3, which is where a human looks at
        it.  The reservations say why, in words, on the artefact.
        """
        earned = assign_proof_class(self.source_shape, self.reconciliation_status)
        if earned is ProofClass.p0 and self.admissibility_reservations:
            return ProofClass.p3
        return earned


# ---------------------------------------------------------------------------
# The structural walk
# ---------------------------------------------------------------------------


def _parse_summaries(
    record: Bai2LogicalRecord, currency: str, *, context: str
) -> tuple[Bai2Summary, ...]:
    """Read the repeating ``type code, amount, item count, funds type`` quads.

    The quad repeats to the end of the ``03`` record, continuations included,
    and any of the last three may be empty.  A quad that is empty throughout is
    padding and is passed over; one that carries a figure with no type code in
    front of it is refused, because there is then nothing to say what the
    figure is and a reader would have to guess from its position.
    """
    fields = record.fields
    out: list[Bai2Summary] = []
    cursor = 3
    while cursor < len(fields):
        type_code = _optional(fields, cursor)
        amount_text = _optional(fields, cursor + 1)
        count_text = _optional(fields, cursor + 2)
        label = type_code or "(no type code)"
        funds_type, cursor = _consume_funds_type(
            fields, cursor + 3, context=f"{context} summary {label}"
        )

        if type_code is None:
            if amount_text is None and count_text is None and funds_type is None:
                continue
            raise Bai2MalformedFileError(
                f"{context}: a summary carries an amount, an item count or a "
                "funds type with no type code in front of it, so nothing says "
                "what the figure is"
            )
        if not _TYPE_CODE_RE.match(type_code):
            raise Bai2MalformedFileError(
                f"{context}: {type_code!r} is not a three-digit BAI2 type code"
            )

        out.append(
            Bai2Summary(
                type_code=type_code,
                amount=(
                    _parse_amount(
                        amount_text, currency, context=f"{context} summary {type_code}"
                    )
                    if amount_text is not None
                    else None
                ),
                item_count=(
                    _parse_count(
                        count_text,
                        context=f"{context} summary {type_code} item count",
                    )
                    if count_text is not None
                    else None
                ),
                funds_type=funds_type,
            )
        )
    return tuple(out)


def _parse_transaction(
    record: Bai2LogicalRecord, currency: str, index: int
) -> Bai2Transaction:
    """Read one ``16`` detail record with its continuations already folded in."""
    context = f"line {record.first_line} (16 transaction detail)"
    fields = record.fields

    type_code = _required(fields, 1, "the type code", context=context)
    if not _TYPE_CODE_RE.match(type_code):
        raise Bai2MalformedFileError(
            f"{context}: {type_code!r} is not a three-digit BAI2 type code"
        )
    amount = _parse_amount(
        _required(fields, 2, "the amount", context=context), currency, context=context
    )
    funds_type, cursor = _consume_funds_type(fields, 3, context=context)

    return Bai2Transaction(
        index=index,
        type_code=type_code,
        amount=amount,
        funds_type=funds_type,
        bank_reference=_optional(fields, cursor),
        customer_reference=_optional(fields, cursor + 1),
        text=record.tail_text(cursor + 2),
        line_number=record.first_line,
    )


def _resolve_currency(
    stated: Optional[str],
    group_currency: Optional[str],
    default_currency: Optional[str],
    *,
    context: str,
) -> tuple[str, str]:
    """Settle the account's currency, and record where it came from.

    Refuses rather than defaulting.  A BAI2 amount is an integer count of the
    currency's minor units, so the currency is what fixes the scale of every
    figure in the account; assuming one would not produce a figure that is
    slightly wrong, it would produce a figure wrong by a factor of a hundred,
    and it would do so uniformly.  The identity would still close, the control
    totals would still agree, and the ledger would be internally consistent and
    off by two orders of magnitude.
    """
    if stated is not None:
        code, source = stated.upper(), BAI2_CURRENCY_FROM_ACCOUNT
    elif group_currency is not None:
        code, source = group_currency, BAI2_CURRENCY_FROM_GROUP
    elif default_currency is not None:
        code, source = default_currency, BAI2_CURRENCY_FROM_CALLER
    else:
        raise Bai2CurrencyError(
            f"{context}: neither the account nor its group states a currency "
            "and no default was supplied.  BAI2 amounts are integer minor "
            "units, so the currency fixes the scale of every figure here and "
            "guessing it would misstate all of them by the same factor"
        )
    try:
        return get_currency(code).code, source
    except MoneyError as exc:
        raise Bai2CurrencyError(f"{context}: {code!r} is not a usable currency: {exc}") from exc


def _sum_minor_units(amounts: Iterable[Optional[Money]]) -> int:
    """Add the minor units of a run of amounts, ignoring the absent ones.

    Deliberately not :func:`~services.financial.money.sum_money`.  This is the
    checksum arithmetic, not the ledger arithmetic: the figures are added as
    the integers the file transmitted, an absent amount contributes nothing
    because nothing was transmitted for it, and no currency is consulted
    because a control total has none.  Every amount reaching this function
    within one account does share a currency, and above account level the
    contributions come pre-summed as integers, so nothing is silently mixed.
    """
    return sum(amount.minor_units for amount in amounts if amount is not None)


def _parse_account(
    records: Sequence[Bai2LogicalRecord],
    index: int,
    *,
    group_currency: Optional[str],
    default_currency: Optional[str],
) -> tuple[Bai2Account, int]:
    """Read one ``03`` … ``49`` block, returning it and the index after it.

    The currency is settled first and everything else follows from it, because
    a BAI2 amount is an integer count of minor units and there is no reading of
    one that does not already assume a currency.

    The account control total is the sum of every amount in the ``03`` record
    and every amount in the ``16`` records it heads — primary amounts only, for
    the reasons given at :data:`_ACCOUNT_CONTROL_BASIS`.  The record count is
    physical: the ``03`` and its continuations, every ``16`` and its
    continuations, and the ``49`` and its continuations.  That is what the
    trailer counts, and counting logical records instead would come up short by
    exactly the number of ``88`` records the sender wrote, on a file with
    nothing wrong with it.
    """
    header = records[index]
    context = f"line {header.first_line} (03 account identifier)"
    fields = header.fields

    account_number = _required(
        fields, 1, "the customer account number", context=context
    )
    currency, currency_source = _resolve_currency(
        _optional(fields, 2), group_currency, default_currency, context=context
    )
    summaries = _parse_summaries(header, currency, context=context)

    transactions: list[Bai2Transaction] = []
    detail_records = 0
    cursor = index + 1
    while cursor < len(records) and records[cursor].code == BAI2_TRANSACTION_DETAIL:
        transactions.append(
            _parse_transaction(records[cursor], currency, len(transactions))
        )
        detail_records += records[cursor].physical_record_count
        cursor += 1

    if cursor >= len(records):
        raise Bai2MalformedFileError(
            f"{context}: the account is never closed by a "
            f"{BAI2_ACCOUNT_TRAILER} trailer; the file ends first, so the "
            "control total that would establish nothing was lost in carriage "
            "was never sent"
        )
    trailer = records[cursor]
    if trailer.code != BAI2_ACCOUNT_TRAILER:
        raise Bai2MalformedFileError(
            f"line {trailer.first_line}: expected a {BAI2_ACCOUNT_TRAILER} "
            f"account trailer to close the account opened at line "
            f"{header.first_line}, and found record code {trailer.code!r}"
        )

    trailer_context = f"line {trailer.first_line} (49 account trailer)"
    declared_total_text = _optional(trailer.fields, 1)
    declared_count_text = _optional(trailer.fields, 2)

    control_total = _check_control_total(
        level=BAI2_ACCOUNT_TRAILER,
        basis=_ACCOUNT_CONTROL_BASIS,
        declared=(
            _parse_minor_units(declared_total_text, context=trailer_context)
            if declared_total_text is not None
            else None
        ),
        computed=(
            _sum_minor_units(entry.amount for entry in summaries)
            + _sum_minor_units(txn.amount for txn in transactions)
        ),
        currency=currency,
        declared_record_count=(
            _parse_count(
                declared_count_text, context=f"{trailer_context} record count"
            )
            if declared_count_text is not None
            else None
        ),
        computed_record_count=(
            header.physical_record_count
            + detail_records
            + trailer.physical_record_count
        ),
    )

    account = Bai2Account(
        customer_account_number=account_number,
        currency=currency,
        currency_source=currency_source,
        summaries=summaries,
        transactions=tuple(transactions),
        balance_identity=_check_balance_identity(summaries, transactions, currency),
        summary_identity=_check_summary_identity(summaries, transactions, currency),
        control_total=control_total,
        first_line=header.first_line,
    )
    return account, cursor + 1


def _declared_child_totals(
    children: Sequence[Bai2ControlTotal], *, level: str, child_name: str
) -> tuple[Optional[int], Optional[str]]:
    """Sum what the children *declared*, or say why the sum cannot be formed.

    A group total is defined against the account totals, not against the
    account contents, and this is the function that keeps it that way.  Summing
    what the accounts *computed* would make the ``98`` agree with the ``49``
    records by construction, so the group check would confirm nothing the
    account check had not already confirmed and the file would look twice as
    verified as it is.  Summed against the declarations, the two are
    independent links: the ``49`` tests itself against records, the ``98``
    tests itself against the ``49`` records.

    A child that declared no total leaves nothing to sum.  That is reported as
    a reason rather than treated as a zero, because a missing declaration read
    as zero would shift the parent's total by exactly the amount the child was
    carrying and blame the parent's trailer for it.
    """
    total = 0
    for position, child in enumerate(children, start=1):
        if child.declared_minor_units is None:
            return None, (
                f"the {level} control total is the sum of the totals its "
                f"{child_name}s declared, and {child_name} {position} declared "
                "none, so there is nothing to sum against"
            )
        total += child.declared_minor_units
    return total, None


def _parse_group(
    records: Sequence[Bai2LogicalRecord],
    index: int,
    *,
    default_currency: Optional[str],
) -> tuple[Bai2Group, int]:
    """Read one ``02`` … ``98`` block, returning it and the index after it."""
    header = records[index]
    context = f"line {header.first_line} (02 group header)"
    fields = header.fields

    stated_currency = _optional(fields, 6)
    group_currency: Optional[str] = None
    if stated_currency is not None:
        try:
            group_currency = get_currency(stated_currency.upper()).code
        except MoneyError as exc:
            raise Bai2CurrencyError(
                f"{context}: the group states currency {stated_currency!r}, "
                f"which is not usable: {exc}"
            ) from exc

    accounts: list[Bai2Account] = []
    account_records = 0
    cursor = index + 1
    while cursor < len(records) and records[cursor].code == BAI2_ACCOUNT_HEADER:
        account, cursor = _parse_account(
            records,
            cursor,
            group_currency=group_currency,
            default_currency=default_currency,
        )
        accounts.append(account)
        account_records += account.control_total.computed_record_count

    if cursor >= len(records):
        raise Bai2MalformedFileError(
            f"{context}: the group is never closed by a {BAI2_GROUP_TRAILER} "
            "trailer; the file ends first"
        )
    trailer = records[cursor]
    if trailer.code != BAI2_GROUP_TRAILER:
        raise Bai2MalformedFileError(
            f"line {trailer.first_line}: expected a {BAI2_GROUP_TRAILER} group "
            f"trailer to close the group opened at line {header.first_line}, "
            f"and found record code {trailer.code!r}"
        )

    trailer_context = f"line {trailer.first_line} (98 group trailer)"
    declared_total_text = _optional(trailer.fields, 1)
    declared_accounts_text = _optional(trailer.fields, 2)
    declared_count_text = _optional(trailer.fields, 3)
    computed, computed_reason = _declared_child_totals(
        [account.control_total for account in accounts],
        level=BAI2_GROUP_TRAILER,
        child_name="account",
    )

    control_total = _check_control_total(
        level=BAI2_GROUP_TRAILER,
        basis=_GROUP_CONTROL_BASIS,
        declared=(
            _parse_minor_units(declared_total_text, context=trailer_context)
            if declared_total_text is not None
            else None
        ),
        computed=computed,
        # Only where every account beneath agrees.  A group holding accounts in
        # two currencies has a perfectly good control total and no ``Money``
        # that could carry it, and the integer comparison is unaffected.
        currency=_common_currency(account.currency for account in accounts),
        declared_record_count=(
            _parse_count(
                declared_count_text, context=f"{trailer_context} record count"
            )
            if declared_count_text is not None
            else None
        ),
        computed_record_count=(
            header.physical_record_count
            + account_records
            + trailer.physical_record_count
        ),
        declared_child_count=(
            _parse_count(
                declared_accounts_text, context=f"{trailer_context} account count"
            )
            if declared_accounts_text is not None
            else None
        ),
        computed_child_count=len(accounts),
        computed_reason=computed_reason,
    )

    group = Bai2Group(
        ultimate_receiver=_optional(fields, 1),
        originator=_optional(fields, 2),
        status=_optional(fields, 3),
        as_of_date=_optional(fields, 4),
        as_of_time=_optional(fields, 5),
        currency=group_currency,
        as_of_date_modifier=_optional(fields, 7),
        accounts=tuple(accounts),
        control_total=control_total,
        first_line=header.first_line,
    )
    return group, cursor + 1


def _decode(data: "bytes | bytearray | str") -> str:
    """Turn the input into text, or refuse.

    Bytes are decoded as UTF-8 with no fallback and no error handler.  BAI2 is
    an ASCII format in practice, so a file that is valid UTF-8 is read exactly
    and one that is not has something in it this parser has no way to read
    correctly.  Falling back to latin-1 would make every such file decode
    successfully and silently, turning a payee name into mojibake that no later
    stage can distinguish from a name the bank actually sent.

    ``str`` is accepted, unlike :func:`~services.financial.camt053.parse_camt053`,
    and the asymmetry is deliberate rather than an inconsistency.  An XML
    document declares its own encoding inside itself, so decoding it before
    parsing means guessing what the file already states.  A BAI2 file declares
    nothing, so a caller who already holds text holds exactly what this
    function would have produced.
    """
    if isinstance(data, str):
        return data
    if not isinstance(data, (bytes, bytearray)):
        raise Bai2MalformedFileError(
            f"parse_bai2 takes bytes or str, got {type(data).__name__}"
        )
    if len(data) > BAI2_MAX_FILE_BYTES:
        raise Bai2MalformedFileError(
            f"the file is {len(data)} bytes, over the {BAI2_MAX_FILE_BYTES}-byte "
            "ceiling for a cash-management file"
        )
    try:
        return bytes(data).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Bai2MalformedFileError(
            f"the file is not valid UTF-8: {exc}.  It is refused rather than "
            "decoded with a fallback, because a fallback succeeds on every "
            "input and turns unreadable bytes into plausible-looking text that "
            "nothing downstream can tell from what the bank sent"
        ) from exc


def parse_bai2(
    data: "bytes | bytearray | str",
    *,
    default_currency: Optional[str] = None,
) -> Bai2File:
    """Parse a BAI2 cash-management file.  Pure: no database, no network, no clock.

    ``default_currency`` is consulted only where neither the ``03`` account
    record nor its ``02`` group states one.  It is a parameter rather than a
    constant because the right answer is a property of the engagement — the
    bank and the account tell you, and this module does not have either — and
    supplying none means an account with no stated currency is refused rather
    than guessed.  See :func:`_resolve_currency` for why guessing is the worse
    of the two.

    :raises NotABai2Error: the content does not open with an ``01`` file header.
    :raises Bai2MalformedFileError: the record structure is not conformant.
    :raises Bai2MissingFieldError: a mandatory field is absent.
    :raises Bai2AmountError: a figure is not a BAI2 amount, or not representable.
    :raises Bai2CurrencyError: no currency can be settled for an account.
    """
    text = _decode(data)
    if not text.strip():
        raise NotABai2Error("the file is empty")

    records = _fold_records(text)
    if not records:
        raise NotABai2Error("the file carries no records")

    header = records[0]
    if header.code != BAI2_FILE_HEADER:
        raise NotABai2Error(
            f"the file opens with record code {header.code!r}; a BAI2 file "
            f"opens with a {BAI2_FILE_HEADER} file header"
        )

    context = f"line {header.first_line} (01 file header)"
    fields = header.fields

    version = _optional(fields, 8)
    if version is not None and version != BAI2_VERSION:
        # Asymmetric on purpose.  An absent version says nothing, and the
        # layout this parser assumes is verified three times over by the
        # control totals, so an absent version costs nothing and is recorded as
        # ``None``.  A version that says ``1`` says the layout is different,
        # and reading it as version 2 would produce records that parse.
        raise Bai2MalformedFileError(
            f"{context}: the file states version {version!r}; this parser reads "
            f"version {BAI2_VERSION} and a different version is a different "
            "record layout, which would parse cleanly and mean something else"
        )

    length_text = _optional(fields, 6)
    block_text = _optional(fields, 7)

    groups: list[Bai2Group] = []
    group_records = 0
    cursor = 1
    while cursor < len(records) and records[cursor].code == BAI2_GROUP_HEADER:
        group, cursor = _parse_group(
            records, cursor, default_currency=default_currency
        )
        groups.append(group)
        group_records += group.control_total.computed_record_count

    if cursor >= len(records):
        raise Bai2MalformedFileError(
            f"{context}: the file is never closed by a {BAI2_FILE_TRAILER} "
            "trailer; a file that ends without one may have been truncated in "
            "carriage, and the total that would have detected it is the one "
            "that is missing"
        )
    trailer = records[cursor]
    if trailer.code != BAI2_FILE_TRAILER:
        raise Bai2MalformedFileError(
            f"line {trailer.first_line}: expected a {BAI2_GROUP_HEADER} group "
            f"header or the {BAI2_FILE_TRAILER} file trailer, and found record "
            f"code {trailer.code!r}"
        )
    if cursor + 1 != len(records):
        following = records[cursor + 1]
        raise Bai2MalformedFileError(
            f"line {following.first_line}: record code {following.code!r} "
            f"follows the {BAI2_FILE_TRAILER} file trailer at line "
            f"{trailer.first_line}.  The trailer closes the file, so what "
            "follows it is outside every control total and would enter the "
            "ledger uncounted"
        )

    trailer_context = f"line {trailer.first_line} (99 file trailer)"
    declared_total_text = _optional(trailer.fields, 1)
    declared_groups_text = _optional(trailer.fields, 2)
    declared_count_text = _optional(trailer.fields, 3)
    computed, computed_reason = _declared_child_totals(
        [group.control_total for group in groups],
        level=BAI2_FILE_TRAILER,
        child_name="group",
    )

    control_total = _check_control_total(
        level=BAI2_FILE_TRAILER,
        basis=_FILE_CONTROL_BASIS,
        declared=(
            _parse_minor_units(declared_total_text, context=trailer_context)
            if declared_total_text is not None
            else None
        ),
        computed=computed,
        currency=_common_currency(
            account.currency for group in groups for account in group.accounts
        ),
        declared_record_count=(
            _parse_count(
                declared_count_text, context=f"{trailer_context} record count"
            )
            if declared_count_text is not None
            else None
        ),
        computed_record_count=(
            header.physical_record_count
            + group_records
            + trailer.physical_record_count
        ),
        declared_child_count=(
            _parse_count(
                declared_groups_text, context=f"{trailer_context} group count"
            )
            if declared_groups_text is not None
            else None
        ),
        computed_child_count=len(groups),
        computed_reason=computed_reason,
    )

    return Bai2File(
        sender=_optional(fields, 1),
        receiver=_optional(fields, 2),
        creation_date=_optional(fields, 3),
        creation_time=_optional(fields, 4),
        file_identification=_optional(fields, 5),
        physical_record_length=(
            _parse_count(length_text, context=f"{context} physical record length")
            if length_text is not None
            else None
        ),
        block_size=(
            _parse_count(block_text, context=f"{context} block size")
            if block_text is not None
            else None
        ),
        version=version,
        groups=tuple(groups),
        control_total=control_total,
    )
