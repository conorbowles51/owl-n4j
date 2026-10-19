"""Layer 0 for MT940: a specification-conformant parse, exact by construction.

Extraction divides into layers and this one runs first.  For P0 and P1 formats
there is no extraction problem: camt.053, BAI2, NACHA and MT940 are parsed with
a specification-conformant parser and the output is exact by construction.  This
is the third such parser, after :mod:`~services.financial.camt053` and
:mod:`~services.financial.bai2`.

What MT940 gives and what it withholds are both precise.  The identity
``:60F: + Σ:61: = :62F:`` holds.  But field ``:86:`` — the
information-to-account-owner field where the counterparty description actually
lives — is unstructured and bank-specific, so the balance check is sound while
the narrative parse is not.

The format is not going away.  Statement messages have no hard SWIFT migration
deadline: the November 2025 deadline applied to payment messages.  camt
migration for statements is planned for 2027 or later, so MT940 will remain in
circulation.

One check, and why it is only one
---------------------------------

camt.053 has a mandatory balance identity and optional summaries.  BAI2 has
mandatory control totals at three levels and an optional balance identity.
MT940 has the balance identity and nothing else.

That is the whole arithmetic.  ``:60a:`` and ``:62a:`` are both mandatory, so
the identity is always computable — there is no "the sender omitted the opening
balance" case, because a message omitting it is not an MT940.  In exchange the
format offers no count of anything.  No record count, no entry count, no
declared credit or debit totals.

**This is why MT940 is not a P0 format, and the distinction is worth being
exact about.**  P0 is a structured bank-originated file with mandatory control
totals, and a control total is a count or a sum that establishes that *nothing
was lost in carriage*.  MT940 has none.  Two adjacent ``:61:`` lines merged into
one during transmission, or a single line of net zero dropped entirely, leave a
message whose balance identity still closes perfectly.  A BAI2 ``49`` record
count would catch both.  Nothing in MT940 does.  So MT940 sits alongside the
other three in this layer while falling one class short of them, and that is a
property of the format rather than an oversight.

So the shape is :attr:`~services.financial.proof_class.SourceShape.native_without_control_totals`
and a clean statement earns p1 rather than p0.  Operationally this costs
nothing — p0, p1 and p2 are auto-admitted alike — and it avoids asserting a
format guarantee the format does not make.  A statement whose identity *fails*
still lands at p3, because
:func:`~services.financial.proof_class.assign_proof_class` tests the failure
before it dispatches on shape.  MT940 therefore behaves better than a bare
"format validation only" reading of P1 suggests: it is a structured format
without control totals that nevertheless carries a real arithmetic check, and
the check is run.

Decisions the specification leaves open
---------------------------------------

Each resolves toward refusing rather than guessing, because the error is
asymmetric: a class assigned one step too low costs an adjudication a person
will resolve, and one step too high puts an unchecked row inside a total.

**The amount separator is a comma, and only a comma.**  SWIFT writes ``15d`` as
digits with a mandatory comma for the decimal point and no thousands separator
at all.  ``1000,00`` is one thousand.  A file writing ``1.000,00`` or
``1,000.00`` is not conformant, and the two disagree with each other by three
orders of magnitude on the same digits.  Reading either by guessing which
convention a bank meant is how a ledger acquires an amount nothing downstream
can question, so both are refused by name.  The refusal says what was found and
that it is a non-conformant emission, so that an operator reads it as a fact
about the file rather than a defect in this parser.

**Two-digit years are recorded, not resolved.**  Every date in MT940 is
``YYMMDD``.  ``980115`` is 15 January 1998 or 15 January 2098 and the message
does not say which.  A sliding window would pick one silently, and the pick
would be wrong for exactly the archival material — a decade-old account history
— that an investigation is most likely to be reading.  Dates are therefore kept
as the six digits the file wrote, the same treatment
:class:`~services.financial.bai2.Bai2Group` gives the ``02`` as-of date.
Grounding them against a known statement period is
:mod:`~services.financial.dates`' work, and it is work that needs a period this
message does not carry.

**A debit/credit mark this parser does not know is refused, not guessed
around.**  The mark on a ``:61:`` line is one of ``C``, ``D``, ``RC`` or
``RD``, and that is the entire legal set.  This differs from BAI2, where an
undirected type code makes the balance identity *decline* rather than fail —
and the difference is in the formats, not in the doctrine.  BAI2 type codes
have whole ranges (700–999) the specification leaves without a direction, so a
file using one is conformant and declining is the honest answer.  MT940 has no
such range.  A mark outside the four is a corrupt field, and a corrupt field in
the position that decides which side of the equation an amount lands on is a
reason to stop.

**A reversal is recorded as a reversal.**  ``RC`` reverses a credit and so
subtracts; ``RD`` reverses a debit and so adds.  For the identity they are a
debit and a credit respectively, and they are summed as such.  But a reversal
is a correction to something the bank said earlier, not an ordinary movement,
and a ledger that flattened the two would lose the only signal in the message
that an earlier figure was withdrawn.  :attr:`Mt940StatementLine.is_reversal`
keeps it.

**``:86:`` is captured verbatim and left unparsed.**  This is the single most
tempting field in the format and the one the balance check does not cover.  It is
where the counterparty actually lives, it is unstructured, and its layout is
per-bank and frequently per-product.  A regex that works on one bank's
narrative silently mis-splits another's, and the result is a counterparty
attributed to a transaction on the authority of nothing.  The text is kept
exactly as written, including its line breaks, and structuring it is left to a
later layer that is allowed to be uncertain and required to say so.

**An intermediate balance is recorded, and does not demote.**  ``:60M:`` opens
a statement that continues an earlier message and ``:62M:`` closes one that a
later message continues.  Such a statement is a fragment of a period, but it is
not a defective fragment: opening plus movements equals closing *within* the
fragment, and the identity is as sound there as anywhere.  So it is reported
(:attr:`Mt940Statement.is_fragment`) and not treated as a reservation.  The
BAI2 precedent is deliberately not followed here, and the reason is that it
does not apply: a BAI2 test group draws a reservation because it asserts
nothing about money that moved, while a ``:62M:`` statement asserts exactly
what moved and merely does not finish.  Whether the fragments in hand cover the
period is a coverage question and belongs to
:mod:`~services.financial.periods`, which can see the other messages.

**No convention is retried until one balances.**  As in
:mod:`~services.financial.bai2`: the literal reading is implemented and the
delta reported when it fails.  Nothing is tried a second way to see whether the
second way closes, because a file with a genuine error that gets silently
repaired into a passing class is the failure mode the classes exist to prevent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

from postgres.models.enums import (
    LocatorKind,
    ReconciliationStatus,
    TransactionDirection,
)
from services.financial.locators import Locator
from services.financial.money import Money, MoneyError, get_currency
from services.financial.proof_class import ProofClass, SourceShape, assign_proof_class


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class Mt940Error(Exception):
    """Base for every refusal in this module."""


class NotAnMt940Error(Mt940Error):
    """Readable text that is not an MT940 customer statement message."""


class Mt940MalformedFileError(Mt940Error):
    """Structurally broken: a tag out of sequence, or a field that will not resolve."""


class Mt940MissingFieldError(Mt940Error):
    """A mandatory tag is absent."""


class Mt940AmountError(Mt940Error):
    """A figure is not an MT940 amount, or not exactly representable as money."""


class Mt940CurrencyError(Mt940Error):
    """The currencies stated within one statement do not agree."""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: An MT940 message is a sequence of tagged fields, not a rectangle on a page.
#: Stated once so that no caller has to decide, and so that the absence of a
#: click-through target reads as a property of the format rather than a defect
#: in a reader.
MT940_LOCATOR: Locator = Locator(kind=LocatorKind.not_positional)

#: A ceiling on what will be read into memory.  A statement file covering many
#: accounts over a long period is large but not unbounded; something far past
#: this is a different kind of object and refusing it is cheaper than
#: discovering what it is.
MT940_MAX_FILE_BYTES: int = 64 * 1024 * 1024

#: Tags this parser reads.  ``:20:`` opens a message and is what a statement is
#: split on; ``:25:``, ``:28C:`` and the two balances are mandatory.
MT940_TRANSACTION_REFERENCE = "20"
MT940_RELATED_REFERENCE = "21"
MT940_ACCOUNT_IDENTIFICATION = "25"
MT940_STATEMENT_NUMBER = "28C"
MT940_OPENING_BALANCE = "60"
MT940_STATEMENT_LINE = "61"
MT940_INFORMATION = "86"
MT940_CLOSING_BALANCE = "62"
MT940_CLOSING_AVAILABLE_BALANCE = "64"
MT940_FORWARD_AVAILABLE_BALANCE = "65"

#: The balance tags, by whether they are final or intermediate.  ``F`` is a
#: balance that begins or ends a statement period; ``M`` is one that continues
#: it across messages.
MT940_BALANCE_FINAL = "F"
MT940_BALANCE_INTERMEDIATE = "M"

#: The debit/credit marks on a balance.  A balance is signed by this mark and
#: not by a minus: an overdrawn account writes ``D``.
MT940_BALANCE_CREDIT = "C"
MT940_BALANCE_DEBIT = "D"

#: The four legal marks on a ``:61:`` statement line, and the direction each
#: contributes to the identity.  ``RC`` reverses a credit and therefore behaves
#: as a debit; ``RD`` reverses a debit and therefore behaves as a credit.
MT940_LINE_MARKS: dict[str, TransactionDirection] = {
    "C": TransactionDirection.credit,
    "D": TransactionDirection.debit,
    "RC": TransactionDirection.debit,
    "RD": TransactionDirection.credit,
}

#: The two marks that are corrections rather than movements.
MT940_REVERSAL_MARKS = frozenset({"RC", "RD"})

#: The conventional placeholder a bank writes when it has no reference to give.
#: Recorded as written; named here so that a reader of the parsed output knows
#: it is a convention and not a reference that happens to look like a word.
MT940_NO_REFERENCE = "NONREF"

#: A tag line opens with a colon, two digits, an optional single uppercase
#: letter, and a closing colon.  Anything else on a line continues the tag
#: above it.
_TAG_RE = re.compile(r"^:(?P<tag>\d{2}[A-Z]?):(?P<value>.*)$")

#: A SWIFT amount: digits, a mandatory comma, then optional digits.  Applied
#: before any conversion, and deliberately strict — see the module docstring on
#: why a period is refused rather than accommodated.
_AMOUNT_RE = re.compile(r"^(?P<whole>\d{1,15}),(?P<frac>\d*)$")

#: Six digits, ``YYMMDD``.  The century is not resolved; see the docstring.
_DATE_RE = re.compile(r"^\d{6}$")

#: Four digits, ``MMDD``, the optional entry date on a ``:61:``.
_ENTRY_DATE_RE = re.compile(r"^\d{4}$")

#: A balance field: mark, date, currency, amount.
_BALANCE_RE = re.compile(
    r"^(?P<mark>[A-Z])(?P<date>\d{6})(?P<currency>[A-Z]{3})(?P<amount>[\d,.]+)$"
)

#: A statement line.  The marks are written two-character-first for reading,
#: but the order is not what makes ``RC`` safe: alternation tries every branch
#: at the same position, and ``C`` cannot match an ``R``, so ``RC|RD|C|D`` and
#: ``C|D|RC|RD`` accept exactly the same marks.  What actually keeps ``RC``
#: whole is that ``R`` is not a mark in its own right.  Said plainly here
#: because a comment claiming the order is load-bearing would send a later
#: reader looking for a guarantee this expression does not provide.
_STATEMENT_LINE_RE = re.compile(
    r"^(?P<value_date>\d{6})"
    r"(?P<entry_date>\d{4})?"
    r"(?P<mark>RC|RD|C|D)"
    r"(?P<funds_code>[A-Z])?"
    r"(?P<amount>[\d,.]+?)"
    r"(?P<transaction_type>[A-Z][A-Z0-9]{3})"
    r"(?P<rest>.*)$",
    re.DOTALL,
)

#: The SWIFT application block.  A downloaded statement is often bare block-4
#: content, but a captured FIN message carries the full envelope and the
#: statement is inside ``{4:`` … ``-}``.
_BLOCK_4_RE = re.compile(r"\{4:\r?\n?(?P<body>.*?)\r?\n?-\}", re.DOTALL)


# ---------------------------------------------------------------------------
# Lexical helpers
# ---------------------------------------------------------------------------


def _parse_amount(text: str, currency: str, *, context: str) -> Money:
    """Read a SWIFT ``15d`` amount into :class:`~services.financial.money.Money`.

    The comma is the decimal separator and there is no thousands separator, so
    the digits before the comma are whole units and the digits after are minor
    units of the currency.  Nothing is rounded: a figure with more decimal
    places than the currency has is refused, because rounding evidence is a
    decision this module is not entitled to make.
    """
    if not text:
        raise Mt940AmountError(f"{context}: the amount is empty")
    if "." in text:
        raise Mt940AmountError(
            f"{context}: {text!r} contains a period.  SWIFT writes an amount as "
            "digits with a comma for the decimal point and no thousands "
            "separator, so this is a non-conformant emission rather than a "
            "figure this parser can read.  It is refused instead of guessed at "
            "because '1.000,00' and '1,000.00' are both plausible readings of "
            "such a file and they differ by three orders of magnitude"
        )
    match = _AMOUNT_RE.match(text)
    if match is None:
        raise Mt940AmountError(
            f"{context}: {text!r} is not a SWIFT amount.  The form is digits, "
            "then a mandatory comma, then optional decimal digits"
        )
    whole = match.group("whole")
    frac = match.group("frac")
    exponent = get_currency(currency).exponent
    if len(frac) > exponent:
        raise Mt940AmountError(
            f"{context}: {text!r} carries {len(frac)} decimal digits and "
            f"{currency} has {exponent}; refusing to round evidence"
        )
    minor = int(whole) * (10**exponent) + int(frac.ljust(exponent, "0") or "0")
    try:
        return Money.from_minor_units(minor, currency)
    except MoneyError as exc:  # pragma: no cover - get_currency already validated
        raise Mt940AmountError(f"{context}: {exc}") from exc


def _parse_date(text: str, *, context: str) -> str:
    """Validate a ``YYMMDD`` date and return its six digits unchanged.

    The century is not resolved here and is not resolved anywhere in this
    module.  See the module docstring: a sliding window would silently pick a
    century, and would pick wrong for exactly the archival material an
    investigation most often reads.
    """
    if not _DATE_RE.match(text):
        raise Mt940MalformedFileError(
            f"{context}: {text!r} is not a YYMMDD date"
        )
    month = int(text[2:4])
    day = int(text[4:6])
    if not 1 <= month <= 12:
        raise Mt940MalformedFileError(
            f"{context}: {text!r} states month {month:02d}, which is not a month"
        )
    if not 1 <= day <= 31:
        raise Mt940MalformedFileError(
            f"{context}: {text!r} states day {day:02d}, which is not a day"
        )
    return text


def _weakest(statuses: Iterable[ReconciliationStatus]) -> ReconciliationStatus:
    """The least favourable outcome in a run of them.

    Order: ``unbalanced`` beats everything, then ``unavailable``, then
    ``not_attempted``, and ``balanced`` only when every check balanced.  A
    single failure anywhere therefore governs, which is what stops a file with
    one clean statement and one broken one from presenting as clean.  The same
    rule as :func:`~services.financial.bai2._weakest`, kept separate so that
    neither module reaches into the other's internals.
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
# Tags, and folding continuation lines into them
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Mt940Tag:
    """One tagged field, with any continuation lines folded into its value.

    ``first_line`` is the 1-based line the tag opened on, and it is what every
    refusal in this module points at.  A reader sent to a line number can find
    the fault; a reader sent to a tag name has to search for which of the six
    ``:61:`` tags was meant.
    """

    tag: str
    value: str
    first_line: int
    line_count: int


def _fold_tags(text: str) -> tuple[Mt940Tag, ...]:
    """Split text into tags, folding continuation lines into the tag above.

    A line beginning ``:nn:`` or ``:nnA:`` opens a tag.  Every other line
    continues the tag above it, and is joined with a newline rather than a
    space: ``:86:`` narrative and the supplementary-details line of a ``:61:``
    are both line-structured, and flattening them would destroy the only
    structure those fields have.

    Text before the first tag is refused rather than skipped.  It is the shape
    a truncated file takes — the front of the message lost, the rest intact —
    and skipping it would parse the remainder into a statement missing its
    opening balance without ever saying that anything was dropped.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    tags: list[Mt940Tag] = []
    buffer: list[str] = []
    current: Optional[tuple[str, int]] = None

    def flush() -> None:
        if current is None:
            return
        tag, first_line = current
        # Trailing blank lines are carriage, not content.  The same statement
        # saved with a final newline and saved without one carry the same
        # narrative, and a ``:86:`` that came out of them differing by a
        # trailing ``\n`` would hash differently for a reason that has nothing
        # to do with what the bank wrote — which matters here, because the
        # narrative is carried verbatim and downstream identity is computed
        # over it.  Interior blanks are kept: those sit between two pieces of
        # narrative, and dropping one would alter what the bank wrote.  The
        # first line is never dropped, since a tag whose content begins on its
        # continuation lines legitimately opens empty.
        folded = list(buffer)
        while len(folded) > 1 and not folded[-1].strip():
            folded.pop()
        tags.append(
            Mt940Tag(
                tag=tag,
                value="\n".join(folded),
                first_line=first_line,
                line_count=len(folded),
            )
        )

    for number, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        match = _TAG_RE.match(line)
        if match is not None:
            flush()
            current = (match.group("tag"), number)
            buffer = [match.group("value")]
            continue
        if current is None:
            if not line.strip():
                continue
            # A block-4 terminator standing alone before any tag is the end of
            # a preceding message and not stray content.
            if line.strip() == "-":
                continue
            raise NotAnMt940Error(
                f"line {number}: {line.strip()[:60]!r} appears before any "
                "tagged field.  An MT940 message opens with :20:, so content "
                "ahead of the first tag means the front of the message is "
                "missing or this is not an MT940 at all"
            )
        if line.strip() == "-":
            # The block-4 terminator.  It closes the message; it is not part of
            # the value of whatever tag happened to be last.
            continue
        buffer.append(line)

    flush()
    return tuple(tags)


def _extract_statements(text: str) -> str:
    """Strip a SWIFT FIN envelope down to its application block, if there is one.

    A statement downloaded from a bank portal is usually bare block-4 content
    and passes through untouched.  A message captured off the wire carries
    ``{1:`` basic header, ``{2:`` application header, sometimes ``{3:`` user
    header, then ``{4:`` … ``-}`` and sometimes ``{5:`` trailer.  Only block 4
    holds the statement.

    Several concatenated FIN messages are joined back together, because a file
    of them is a file of statements and the caller asked for the statements.
    """
    if "{4:" not in text:
        return text
    bodies = [match.group("body") for match in _BLOCK_4_RE.finditer(text)]
    if not bodies:
        raise NotAnMt940Error(
            "the content carries a '{4:' application-block marker but no block "
            "that closes with '-}'.  A truncated FIN message is refused rather "
            "than read up to where it stops, because the missing tail is where "
            "the closing balance lives"
        )
    return "\n".join(bodies)


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Mt940Balance:
    """A ``:60a:``, ``:62a:``, ``:64:`` or ``:65:`` balance.

    ``amount`` is signed: a ``D`` mark makes it negative, because an overdrawn
    balance is a negative balance and carrying the sign in a separate field
    would invite a caller to add two balances without it.  ``mark`` keeps what
    the file actually wrote.

    ``is_intermediate`` distinguishes ``:60M:``/``:62M:`` from ``:60F:``/``:62F:``.
    It is a fact about the statement's place in a sequence of messages, not a
    fact about its arithmetic.
    """

    tag: str
    mark: str
    date: str
    amount: Money
    is_intermediate: bool
    first_line: int

    @property
    def currency(self) -> str:
        return self.amount.currency

    @property
    def locator(self) -> Locator:
        return MT940_LOCATOR


@dataclass(frozen=True, slots=True)
class Mt940StatementLine:
    """One ``:61:`` movement, with the ``:86:`` that follows it if there is one.

    ``amount`` is an unsigned magnitude and ``direction`` carries the sign, the
    ledger convention :class:`~services.financial.money.Money` documents.
    ``mark`` keeps the two characters the file wrote, so that a reversal stays
    visibly a reversal after ``direction`` has flattened it to the side of the
    equation it lands on.

    ``information`` is the ``:86:`` narrative, verbatim and including its line
    breaks.  It is not parsed here and this module makes no claim about what is
    in it — the field is bank-specific, and a counterparty
    extracted from it by pattern would be a counterparty asserted on the
    authority of a guess.
    """

    value_date: str
    entry_date: Optional[str]
    mark: str
    funds_code: Optional[str]
    amount: Money
    transaction_type: str
    account_owner_reference: str
    institution_reference: Optional[str]
    supplementary_details: Optional[str]
    information: Optional[str]
    first_line: int

    @property
    def direction(self) -> TransactionDirection:
        """Which side of the identity this line lands on."""
        return MT940_LINE_MARKS[self.mark]

    @property
    def is_reversal(self) -> bool:
        """Whether the line withdraws an earlier figure rather than reporting a new one."""
        return self.mark in MT940_REVERSAL_MARKS

    @property
    def signed_amount(self) -> Money:
        """The magnitude with the direction applied."""
        if self.direction is TransactionDirection.credit:
            return self.amount
        return -self.amount

    @property
    def locator(self) -> Locator:
        return MT940_LOCATOR


@dataclass(frozen=True, slots=True)
class Mt940BalanceIdentity:
    """``:60a: + ΣCredits − ΣDebits = :62a:``, the whole of MT940's arithmetic.

    Unlike its BAI2 and camt.053 counterparts this check never declines.  Both
    balances are mandatory in a conformant message and a message missing either
    is refused before it reaches here, and every ``:61:`` mark this parser
    accepts has a direction.  So the status is ``balanced`` or ``unbalanced``,
    and a caller reading ``unavailable`` from this type has found a bug rather
    than a quiet file.

    ``delta`` is ``computed − printed``, the same orientation
    :class:`~services.financial.bai2.Bai2BalanceIdentity` uses, so that a
    reviewer comparing an MT940 against a BAI2 reads the sign the same way in
    both.  A positive delta means the movements add up to more than the closing
    balance the bank printed.
    """

    status: ReconciliationStatus
    opening: Money
    printed_closing: Money
    computed_closing: Money
    delta: Money
    credits: Money
    debits: Money
    credit_count: int
    debit_count: int
    reversal_count: int

    @property
    def balanced(self) -> bool:
        return self.status is ReconciliationStatus.balanced


@dataclass(frozen=True, slots=True)
class Mt940Statement:
    """One ``:20:`` … ``:62a:`` message: an account over a period, and its movements.

    How strictly a field is validated tracks what depends on it, and the line
    is drawn deliberately rather than by accident of implementation.  A field
    that enters the arithmetic — an amount, a currency, a debit/credit mark —
    is refused the moment it is doubtful, because a wrong value there produces
    a ledger figure nothing downstream can question.  A field that is recorded
    and carried — a reference, a statement number, the ``:86:`` narrative — is
    kept as written even when it is malformed, because refusing a whole
    statement over a cosmetic defect costs a real statement and gains nothing.
    """

    transaction_reference: str
    related_reference: Optional[str]
    account_identification: str
    account_identifier_code: Optional[str]
    statement_number: Optional[str]
    sequence_number: Optional[str]
    opening_balance: Mt940Balance
    closing_balance: Mt940Balance
    closing_available_balance: Optional[Mt940Balance]
    forward_available_balances: tuple[Mt940Balance, ...]
    lines: tuple[Mt940StatementLine, ...]
    information: Optional[str]
    balance_identity: Mt940BalanceIdentity
    first_line: int

    @property
    def currency(self) -> str:
        """The currency of the statement, taken from its balances.

        A ``:61:`` line states no currency of its own — at most a funds code,
        which is the third character of one — so every amount in the statement
        is in this currency by construction, and a statement whose two balances
        disagreed was refused before it reached here.
        """
        return self.opening_balance.currency

    @property
    def is_fragment(self) -> bool:
        """Whether this statement is part of a period split across messages.

        True when either balance is intermediate (``:60M:`` or ``:62M:``).  It
        is reported and does not demote: a fragment's own arithmetic is sound,
        and whether the fragments in hand cover the period is a question for
        :mod:`~services.financial.periods`, which can see the other messages
        and this parser cannot.
        """
        return (
            self.opening_balance.is_intermediate
            or self.closing_balance.is_intermediate
        )

    @property
    def reconciliation_status(self) -> ReconciliationStatus:
        """The balance identity, which is the whole of what MT940 can be checked against.

        There is nothing to weaken it with.  camt.053 has summaries and BAI2
        has control totals at three levels, and in both modules this property
        combines a mandatory check with optional corroboration.  MT940 offers
        no corroboration at all — no count, no declared total — so the identity
        stands alone, and saying so plainly is better than routing one value
        through machinery built for several.
        """
        return self.balance_identity.status

    @property
    def locator(self) -> Locator:
        return MT940_LOCATOR


@dataclass(frozen=True, slots=True)
class Mt940File:
    """One or more MT940 messages read from a single input."""

    statements: tuple[Mt940Statement, ...]

    #: Fixed, and one step below where the other two native parsers sit.  MT940
    #: is structured and bank-originated, but it carries no control total: no
    #: record count, no entry count, no declared credit or debit total.  Two
    #: ``:61:`` lines merged in carriage, or one of net zero dropped, leave a
    #: message whose identity still closes.  See the module docstring for why
    #: this costs nothing operationally and why claiming otherwise would.
    source_shape: SourceShape = field(
        default=SourceShape.native_without_control_totals, init=False
    )

    @property
    def lines(self) -> tuple[Mt940StatementLine, ...]:
        """Every ``:61:`` movement in the input, in file order."""
        return tuple(
            line for statement in self.statements for line in statement.lines
        )

    @property
    def admissibility_reservations(self) -> tuple[str, ...]:
        """Always empty, and present so that callers need no special case.

        :class:`~services.financial.bai2.Bai2File` has reservations because
        BAI2 has a group status that can mark a file as a test or a deletion —
        arithmetically perfect and asserting nothing about money that moved.
        MT940 has no such field.  There is no tag in the format that says "this
        message is a rehearsal", so there is nothing for this parser to notice
        and no reservation it could honestly raise.

        The property exists anyway because the caller that wires Layer 0 into
        extraction reads it from every native parser, and a caller
        that has to remember which parsers have reservations is a caller that
        will eventually forget.
        """
        return ()

    @property
    def reconciliation_status(self) -> ReconciliationStatus:
        """Every statement's identity, with the least favourable governing."""
        return _weakest(
            [statement.reconciliation_status for statement in self.statements]
        )

    @property
    def proof_class(self) -> ProofClass:
        """The class this input earns, computed rather than asserted.

        The shape and the outcome go to
        :func:`~services.financial.proof_class.assign_proof_class`, which owns
        the rule; this module supplies the two inputs and has no vote on what
        they add up to.

        Nothing is withheld here, unlike
        :attr:`~services.financial.bai2.Bai2File.proof_class`, because there is
        nothing to withhold it for: MT940 states no status that would make a
        clean statement inadmissible.
        """
        return assign_proof_class(self.source_shape, self.reconciliation_status)


# ---------------------------------------------------------------------------
# The structural walk
# ---------------------------------------------------------------------------


def _parse_balance(tag: Mt940Tag, *, name: str) -> Mt940Balance:
    """Read a ``:60a:``, ``:62a:``, ``:64:`` or ``:65:`` balance field.

    The subfield letter is required on the opening and closing balances and is
    read from the tag by the caller.  A bare ``:60:`` or ``:62:`` is refused
    there rather than here: SWIFT defines field 60a only as ``60F`` or ``60M``,
    and reading an unmarked one as final would set
    :attr:`Mt940Statement.is_fragment` by assumption on a message that declined
    to say.
    """
    context = f"line {tag.first_line} (:{tag.tag}: {name})"
    value = tag.value.strip()
    match = _BALANCE_RE.match(value)
    if match is None:
        raise Mt940MalformedFileError(
            f"{context}: {value[:60]!r} is not a balance.  The form is a "
            "single C or D mark, a YYMMDD date, a three-letter currency, and "
            "an amount"
        )
    mark = match.group("mark")
    if mark not in (MT940_BALANCE_CREDIT, MT940_BALANCE_DEBIT):
        raise Mt940MalformedFileError(
            f"{context}: the balance is marked {mark!r}; a balance is marked "
            f"{MT940_BALANCE_CREDIT} or {MT940_BALANCE_DEBIT}, and the mark is "
            "what carries the sign, so a mark this parser cannot read is a "
            "balance whose sign is unknown"
        )
    currency = match.group("currency")
    try:
        get_currency(currency)
    except MoneyError as exc:
        raise Mt940CurrencyError(f"{context}: {exc}") from exc
    amount = _parse_amount(match.group("amount"), currency, context=context)
    if mark == MT940_BALANCE_DEBIT:
        amount = -amount
    return Mt940Balance(
        tag=tag.tag,
        mark=mark,
        date=_parse_date(match.group("date"), context=context),
        amount=amount,
        is_intermediate=tag.tag.endswith(MT940_BALANCE_INTERMEDIATE),
        first_line=tag.first_line,
    )


def _parse_statement_line(
    tag: Mt940Tag, currency: str, *, information: Optional[str]
) -> Mt940StatementLine:
    """Read a ``:61:`` statement line and the ``:86:`` that follows it, if any."""
    context = f"line {tag.first_line} (:61: statement line)"
    value = tag.value.rstrip()
    match = _STATEMENT_LINE_RE.match(value)
    if match is None:
        first = value.split("\n", 1)[0]
        raise Mt940MalformedFileError(
            f"{context}: {first[:60]!r} is not a statement line.  The form is a "
            "YYMMDD value date, an optional MMDD entry date, a C, D, RC or RD "
            "mark, an optional funds code, the amount, and a four-character "
            "transaction type.  Note that EC and ED are MT942 interim marks and "
            "have no meaning in an MT940 statement"
        )
    mark = match.group("mark")
    funds_code = match.group("funds_code")
    if funds_code is not None and funds_code != currency[2]:
        # The funds code is the third character of the currency code.  One that
        # disagrees says the amount is in some other currency, and an amount in
        # another currency summed into this statement's identity would move the
        # delta by an arbitrary amount for a reason no reader could recover.
        raise Mt940CurrencyError(
            f"{context}: the funds code is {funds_code!r} but the statement is "
            f"in {currency}, whose third character is {currency[2]!r}.  The "
            "funds code names the currency of the amount, so a disagreement "
            "means this line may not be in the statement's currency"
        )
    amount = _parse_amount(match.group("amount"), currency, context=context)
    entry_date = match.group("entry_date")
    if entry_date is not None and not _ENTRY_DATE_RE.match(entry_date):
        raise Mt940MalformedFileError(  # pragma: no cover - regex guarantees it
            f"{context}: {entry_date!r} is not an MMDD entry date"
        )

    rest = match.group("rest")
    reference_part, _, supplementary = rest.partition("\n")
    owner_reference, separator, institution_reference = reference_part.partition("//")

    return Mt940StatementLine(
        value_date=_parse_date(match.group("value_date"), context=context),
        entry_date=entry_date,
        mark=mark,
        funds_code=funds_code,
        amount=amount,
        transaction_type=match.group("transaction_type"),
        account_owner_reference=owner_reference,
        institution_reference=institution_reference if separator else None,
        supplementary_details=supplementary or None,
        information=information,
        first_line=tag.first_line,
    )


def _check_balance_identity(
    opening: Mt940Balance,
    closing: Mt940Balance,
    lines: tuple[Mt940StatementLine, ...],
    currency: str,
) -> Mt940BalanceIdentity:
    """``:60a: + ΣCredits − ΣDebits = :62a:``.

    Summed in minor units and compared as integers.  Both terms are already in
    the statement's currency — the balances were checked against each other by
    the caller and the lines carry no currency of their own — so the sum needs
    no currency reconciliation and gets none, which keeps a currency mismatch
    from being reported as an arithmetic failure.
    """
    credit_units = sum(
        line.amount.minor_units
        for line in lines
        if line.direction is TransactionDirection.credit
    )
    debit_units = sum(
        line.amount.minor_units
        for line in lines
        if line.direction is TransactionDirection.debit
    )
    computed_units = opening.amount.minor_units + credit_units - debit_units
    delta_units = computed_units - closing.amount.minor_units

    return Mt940BalanceIdentity(
        status=(
            ReconciliationStatus.balanced
            if delta_units == 0
            else ReconciliationStatus.unbalanced
        ),
        opening=opening.amount,
        printed_closing=closing.amount,
        computed_closing=Money.from_minor_units(computed_units, currency),
        delta=Money.from_minor_units(delta_units, currency),
        credits=Money.from_minor_units(credit_units, currency),
        debits=Money.from_minor_units(debit_units, currency),
        credit_count=sum(
            1 for line in lines if line.direction is TransactionDirection.credit
        ),
        debit_count=sum(
            1 for line in lines if line.direction is TransactionDirection.debit
        ),
        reversal_count=sum(1 for line in lines if line.is_reversal),
    )


def _require_subfield(tag: Mt940Tag, base: str, *, name: str) -> None:
    """Refuse a balance tag written without its ``F`` or ``M`` subfield letter.

    SWIFT defines field 60a as ``60F`` or ``60M`` and field 62a the same way;
    there is no bare form.  Reading an unmarked tag as final would be a guess
    that sets :attr:`Mt940Statement.is_fragment` on a message that declined to
    say, and a statement wrongly presented as covering a whole period is the
    kind of error that is discovered by someone else, later, in a total.
    """
    if tag.tag != base:
        return
    raise Mt940MalformedFileError(
        f"line {tag.first_line}: the {name} is written ':{base}:' with no "
        f"subfield letter.  SWIFT writes it ':{base}{MT940_BALANCE_FINAL}:' "
        f"when it opens or closes a period and ':{base}{MT940_BALANCE_INTERMEDIATE}:' "
        "when it continues one across messages, and the difference is whether "
        "this statement is a whole period or a fragment of one.  A bare tag is "
        "refused rather than assumed to be final"
    )


def _parse_statement(
    tags: tuple[Mt940Tag, ...], cursor: int
) -> tuple[Mt940Statement, int]:
    """Read one ``:20:`` … statement, returning it and the index after it."""
    opening_tag = tags[cursor]
    first_line = opening_tag.first_line
    context = f"line {first_line} (:20: statement)"
    transaction_reference = opening_tag.value.strip()
    cursor += 1

    related_reference: Optional[str] = None
    if cursor < len(tags) and tags[cursor].tag == MT940_RELATED_REFERENCE:
        related_reference = tags[cursor].value.strip() or None
        cursor += 1

    if cursor >= len(tags) or tags[cursor].tag not in (
        MT940_ACCOUNT_IDENTIFICATION,
        MT940_ACCOUNT_IDENTIFICATION + "P",
    ):
        found = tags[cursor].tag if cursor < len(tags) else None
        raise Mt940MissingFieldError(
            f"{context}: the statement states no :{MT940_ACCOUNT_IDENTIFICATION}: "
            "account identification, which is mandatory and is the only thing "
            "in the message that says which account these movements belong to"
            + (f"; found :{found}: instead" if found else "")
        )
    account_tag = tags[cursor]
    account_lines = account_tag.value.strip().split("\n")
    account_identification = account_lines[0].strip()
    account_identifier_code = (
        account_lines[1].strip()
        if account_tag.tag.endswith("P") and len(account_lines) > 1
        else None
    )
    cursor += 1

    statement_number: Optional[str] = None
    sequence_number: Optional[str] = None
    if cursor < len(tags) and tags[cursor].tag in (
        MT940_STATEMENT_NUMBER,
        "28",
    ):
        # Recorded, not validated.  The statement number enters no arithmetic,
        # so a bank writing something other than the specified digits costs
        # nothing, and refusing the statement over it would cost the statement.
        number, separator, sequence = tags[cursor].value.strip().partition("/")
        statement_number = number.strip() or None
        sequence_number = sequence.strip() if separator else None
        cursor += 1

    if cursor >= len(tags) or not tags[cursor].tag.startswith(
        MT940_OPENING_BALANCE
    ):
        found = tags[cursor].tag if cursor < len(tags) else None
        raise Mt940MissingFieldError(
            f"{context}: the statement states no :{MT940_OPENING_BALANCE}"
            f"{MT940_BALANCE_FINAL}: or :{MT940_OPENING_BALANCE}"
            f"{MT940_BALANCE_INTERMEDIATE}: opening balance.  It is mandatory, "
            "and it is one of the two ends of the only arithmetic check this "
            "format carries"
            + (f"; found :{found}: instead" if found else "")
        )
    _require_subfield(tags[cursor], MT940_OPENING_BALANCE, name="opening balance")
    opening_balance = _parse_balance(tags[cursor], name="opening balance")
    cursor += 1

    currency = opening_balance.currency
    lines: list[Mt940StatementLine] = []
    while cursor < len(tags) and tags[cursor].tag == MT940_STATEMENT_LINE:
        line_tag = tags[cursor]
        cursor += 1
        information: Optional[str] = None
        if cursor < len(tags) and tags[cursor].tag == MT940_INFORMATION:
            # A :86: directly after a :61: belongs to that line.  One that
            # appears after the closing balance is statement-level and is
            # picked up below.  The placement is the only thing that
            # distinguishes them, so it is followed exactly.
            information = tags[cursor].value
            cursor += 1
        lines.append(
            _parse_statement_line(line_tag, currency, information=information)
        )

    if cursor >= len(tags) or not tags[cursor].tag.startswith(
        MT940_CLOSING_BALANCE
    ):
        found = tags[cursor].tag if cursor < len(tags) else None
        raise Mt940MissingFieldError(
            f"{context}: the statement is never closed by a "
            f":{MT940_CLOSING_BALANCE}{MT940_BALANCE_FINAL}: or "
            f":{MT940_CLOSING_BALANCE}{MT940_BALANCE_INTERMEDIATE}: closing "
            "balance.  A statement that ends without one may have been "
            "truncated in carriage, and the balance that would have detected "
            "it is the one that is missing"
            + (f"; found :{found}: instead" if found else "")
        )
    _require_subfield(tags[cursor], MT940_CLOSING_BALANCE, name="closing balance")
    closing_balance = _parse_balance(tags[cursor], name="closing balance")
    cursor += 1

    if closing_balance.currency != currency:
        raise Mt940CurrencyError(
            f"{context}: the opening balance at line {opening_balance.first_line} "
            f"is in {currency} and the closing balance at line "
            f"{closing_balance.first_line} is in {closing_balance.currency}.  "
            "The identity subtracts one from the other, so two currencies make "
            "it meaningless rather than merely wrong"
        )

    closing_available_balance: Optional[Mt940Balance] = None
    if cursor < len(tags) and tags[cursor].tag == MT940_CLOSING_AVAILABLE_BALANCE:
        closing_available_balance = _parse_balance(
            tags[cursor], name="closing available balance"
        )
        cursor += 1

    forward_available_balances: list[Mt940Balance] = []
    while cursor < len(tags) and tags[cursor].tag == MT940_FORWARD_AVAILABLE_BALANCE:
        forward_available_balances.append(
            _parse_balance(tags[cursor], name="forward available balance")
        )
        cursor += 1

    for extra in (closing_available_balance, *forward_available_balances):
        if extra is not None and extra.currency != currency:
            raise Mt940CurrencyError(
                f"line {extra.first_line}: the :{extra.tag}: balance is in "
                f"{extra.currency} and the statement is in {currency}.  These "
                "are balances of the same account, so two currencies mean one "
                "of them is not this account's"
            )

    information_tail: Optional[str] = None
    if cursor < len(tags) and tags[cursor].tag == MT940_INFORMATION:
        information_tail = tags[cursor].value
        cursor += 1

    if cursor < len(tags) and tags[cursor].tag != MT940_TRANSACTION_REFERENCE:
        stray = tags[cursor]
        raise Mt940MalformedFileError(
            f"line {stray.first_line}: :{stray.tag}: follows the closing "
            f"balance of the statement opened at line {first_line}.  The "
            "closing balance ends the statement, so what comes after it is "
            "outside the balance identity and would enter the ledger unchecked; "
            f"only a :{MT940_TRANSACTION_REFERENCE}: opening the next statement "
            "may appear here"
        )

    return (
        Mt940Statement(
            transaction_reference=transaction_reference,
            related_reference=related_reference,
            account_identification=account_identification,
            account_identifier_code=account_identifier_code,
            statement_number=statement_number,
            sequence_number=sequence_number,
            opening_balance=opening_balance,
            closing_balance=closing_balance,
            closing_available_balance=closing_available_balance,
            forward_available_balances=tuple(forward_available_balances),
            lines=tuple(lines),
            information=information_tail,
            balance_identity=_check_balance_identity(
                opening_balance, closing_balance, tuple(lines), currency
            ),
            first_line=first_line,
        ),
        cursor,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _decode(data: "bytes | bytearray | str") -> str:
    """Turn the input into text, or refuse.

    Bytes are decoded as UTF-8 with no fallback and no error handler.  The
    SWIFT character set is a subset of ASCII, so a conformant message is valid
    UTF-8 and is read exactly, and one that is not has something in it this
    parser has no way to read correctly.  Falling back to latin-1 would make
    every such file decode successfully and silently, turning a counterparty
    name into mojibake that no later stage can distinguish from a name the bank
    actually sent.

    ``str`` is accepted, as :func:`~services.financial.bai2.parse_bai2` accepts
    it and :func:`~services.financial.camt053.parse_camt053` does not.  The
    asymmetry is the same one: an XML document declares its own encoding inside
    itself, so decoding it before parsing means overruling what the file
    states.  An MT940 message declares nothing, so a caller who already holds
    text holds exactly what this function would have produced.
    """
    if isinstance(data, str):
        return data
    if not isinstance(data, (bytes, bytearray)):
        raise Mt940MalformedFileError(
            f"parse_mt940 takes bytes or str, got {type(data).__name__}"
        )
    if len(data) > MT940_MAX_FILE_BYTES:
        raise Mt940MalformedFileError(
            f"the input is {len(data)} bytes, over the {MT940_MAX_FILE_BYTES}-byte "
            "ceiling for a statement file"
        )
    try:
        return bytes(data).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Mt940MalformedFileError(
            f"the input is not valid UTF-8: {exc}.  It is refused rather than "
            "decoded with a fallback, because a fallback succeeds on every "
            "input and turns unreadable bytes into plausible-looking text that "
            "nothing downstream can tell from what the bank sent"
        ) from exc


def parse_mt940(data: "bytes | bytearray | str") -> Mt940File:
    """Parse one or more MT940 customer statement messages.  Pure: no database,
    no network, no clock.

    Unlike :func:`~services.financial.bai2.parse_bai2` this takes no
    ``default_currency``.  It needs none: every MT940 balance states its own
    currency in the field itself, so there is no case where the message is
    silent and something has to be supplied from outside.

    :raises NotAnMt940Error: the content is not an MT940 statement message.
    :raises Mt940MalformedFileError: the tag structure is not conformant.
    :raises Mt940MissingFieldError: a mandatory tag is absent.
    :raises Mt940AmountError: a figure is not a SWIFT amount, or not representable.
    :raises Mt940CurrencyError: the currencies within a statement disagree.
    """
    text = _decode(data)
    if not text.strip():
        raise NotAnMt940Error("the input is empty")

    tags = _fold_tags(_extract_statements(text))
    if not tags:
        raise NotAnMt940Error("the input carries no tagged fields")

    if tags[0].tag != MT940_TRANSACTION_REFERENCE:
        raise NotAnMt940Error(
            f"the input opens with :{tags[0].tag}:; an MT940 statement opens "
            f"with a :{MT940_TRANSACTION_REFERENCE}: transaction reference"
        )

    statements: list[Mt940Statement] = []
    cursor = 0
    while cursor < len(tags):
        statement, cursor = _parse_statement(tags, cursor)
        statements.append(statement)

    return Mt940File(statements=tuple(statements))
