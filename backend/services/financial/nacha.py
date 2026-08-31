"""Native reading of a NACHA ACH file, the strongest of the four formats.

Four formats are read natively here rather than through a rendered statement,
and three of them reach P0 on the strength of mandatory control totals.  Of
those three this is the one where that phrase
is least of an understatement.  camt.053 states a closing balance.  BAI2 states
a sum of amount fields.  A NACHA file states, at two levels independently:

* the count of entry and addenda records,
* the *entry hash*, a checksum over the receiving institutions,
* the total of debits, and
* the total of credits, **as two separate figures**,

and at file level adds a batch count and a block count on top.  Six declared
quantities at file level, four at batch level, each of which this module
recomputes from the records it read.

The separation of debits from credits is the property that matters most and it
is worth saying why.  Every other format in this package states a *net*: a
closing balance, or a single control total.  A net conceals a compensating
pair.  Read a $4,000 debit as a credit and a BAI2 control total still agrees,
because the total is a sum of unsigned amount fields and nothing moved; a
camt.053 closing balance fails, but fails by $8,000 with no indication that the
cause was a direction rather than an amount.  NACHA states the two sides
apart, so the same error moves $4,000 out of one declared figure and into the
other, and both halves of the check fail in opposite directions by the same
amount.  The failure names itself.

The entry hash is the other property with no analogue in the sibling formats.
It is the sum of the receiving institutions' routing numbers — not of money at
all — truncated to its rightmost ten digits.  It is insensitive to amount and
to direction, and sensitive to exactly the thing the money totals cannot see:
whether the entries in hand are addressed to the institutions the sender
addressed them to.  An entry silently retargeted to a different bank, with the
amount untouched, passes every monetary check in this file and fails the hash.

What this module refuses to guess at
------------------------------------

*A transaction code it does not recognise.*  The direction of an ACH entry is
carried in a two-digit code, and the codes are grouped in decades by account
type — 2x checking, 3x savings, 4x general ledger, 5x loan — with credits and
debits at conventional offsets inside each decade.  The pattern is close enough
to regular to invite extrapolation, and extrapolation is wrong: ``55`` is a
loan account debit and sits where the checking, savings and GL decades all
carry a credit.  A parser that inferred the decade rule would place ``55`` on
the credit side, and the batch control totals *would then disagree*, which is
the good case; in a batch of net-zero loan activity they would agree.  So the
codes are enumerated, and one that is not in the table fixes no direction.

*A record longer than the record length.*  Ninety-four characters is not a
convention here, it is the format.  A longer record means the field boundaries
this module reads by are not where it thinks they are, and every field after
the divergence is a different field's contents.  Shorter records are padded and
the reasoning for that asymmetry is at :func:`_split_records`.

*Which of two ``9`` records is the file control.*  A NACHA file is blocked to a
multiple of ten records and padded with rows of ninety-four ``9`` characters.
A filler is therefore a record whose type code is ``9``, exactly like the file
control record it follows.  They are told apart structurally — the first ``9``
closes the file and anything after it must be all-nines — rather than by
pattern-matching, because a file control record whose every field happened to
be nines is a thing that can be written and a filler that lost a character is a
thing that can happen in carriage.

*The meaning of an IAT batch.*  An international entry carries its foreign
currency and its true parties in addenda records this module does not decode.
The dollar figure in the entry detail is the domestic settlement leg and is
read as such.  The batch is recorded with a reservation rather than dropped,
because the settlement leg is real money and the sender's own totals cover it.

*Whether a prenotification is a payment.*  It is not.  A prenote is a
zero-dollar test that an account exists, and it contributes nothing to either
money total while still counting in the entry count and the entry hash.  A
batch of them passes every check in this module vacuously.  That is not a
defect and the file is not refused, but the promotion to P0 is withheld,
because P0 admits with no human act at all, and admitting an account test
to a ledger of payments is the failure the taxonomy exists to prevent.

Currency
--------

Fixed at USD, with no parameter to change it.  A domestic ACH entry settles in
dollars by definition; the amount field is ten digits with two implied decimal
places and no separator, which is to say it is already a count of cents.  There
is consequently nothing to round and no separator convention to infer, and the
``default_currency`` parameter that :func:`~services.financial.bai2.parse_bai2`
needs has no counterpart here.  An IAT batch is the one place a foreign
currency appears, and it appears in addenda this module does not read; the
entry-detail figure remains the dollar settlement amount even there.

Offsets
-------

Every field position in this module is written as a pair of Python slice
indices in a named constant, and the constants are checked against the record
length at import.  Fixed-width parsing fails silently by construction — an
off-by-one gives a field that is still a string, still parses, and is still
wrong — so the offsets are stated once, in one table, rather than spelled at
each use site where two of them could drift apart.
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
from services.financial.check_digits import aba_check_digit
from services.financial.locators import Locator
from services.financial.money import Money, MoneyError
from services.financial.proof_class import ProofClass, SourceShape, assign_proof_class


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class NachaError(Exception):
    """Base for every refusal in this module."""


class NotANachaError(NachaError):
    """Readable text that is not a NACHA file."""


class NachaMalformedFileError(NachaError):
    """Structurally broken: a record out of sequence, or a field that will not resolve."""


class NachaMissingFieldError(NachaError):
    """A mandatory field is absent or blank."""


class NachaAmountError(NachaError):
    """A figure is not a NACHA amount, or is not representable as money."""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: An ACH file is a feed of fixed-width records, not a rectangle on a page.
#: Stated once so that no caller has to decide, and so that the absence of a
#: click-through target reads as a property of the format rather than as a
#: defect in a reader.
NACHA_LOCATOR: Locator = Locator(kind=LocatorKind.not_positional)

#: A ceiling on what will be read into memory.  A day's origination for a large
#: payroll originator is millions of records and still well inside this;
#: something far past it is a different kind of object, and refusing it is
#: cheaper than discovering what it is.
NACHA_MAX_FILE_BYTES: int = 64 * 1024 * 1024

#: The record length.  Not a convention: the ``1`` file header states it in its
#: own record size field, and this module checks that the file agrees with
#: itself about it.
NACHA_RECORD_LENGTH: int = 94

#: Records per physical block.  Also declared in the file header, also checked.
NACHA_BLOCKING_FACTOR: int = 10

NACHA_FILE_HEADER = "1"
NACHA_BATCH_HEADER = "5"
NACHA_ENTRY_DETAIL = "6"
NACHA_ADDENDA = "7"
NACHA_BATCH_CONTROL = "8"
NACHA_FILE_CONTROL = "9"

#: The record size and format code the ``1`` header must state.  A file
#: declaring anything else is declaring a layout this module does not read, and
#: reading it anyway would produce records that parse.
NACHA_RECORD_SIZE = "094"
NACHA_FORMAT_CODE = "1"

#: The settlement currency of a domestic ACH entry.  See the module docstring:
#: there is no parameter for this because there is no choice in it.
NACHA_CURRENCY = "USD"

#: The entry hash is truncated to its rightmost ten digits, at both levels.
#: Truncation, not modulo of a signed quantity — the hash is a sum of routing
#: numbers and is never negative — but the two coincide here and the constant
#: is named so that the two sites cannot disagree about the width.
NACHA_ENTRY_HASH_DIGITS: int = 10

#: Service class codes, from the ``5`` batch header and repeated in the ``8``
#: batch control.  The three that carry money constrain which totals may be
#: non-zero, which is a fifth check at batch level and is applied as one.
NACHA_SERVICE_CLASS_MIXED = "200"
NACHA_SERVICE_CLASS_CREDITS_ONLY = "220"
NACHA_SERVICE_CLASS_DEBITS_ONLY = "225"
NACHA_SERVICE_CLASS_ADVICES = "280"

NACHA_SERVICE_CLASS_CODES: frozenset[str] = frozenset(
    {
        NACHA_SERVICE_CLASS_MIXED,
        NACHA_SERVICE_CLASS_CREDITS_ONLY,
        NACHA_SERVICE_CLASS_DEBITS_ONLY,
        NACHA_SERVICE_CLASS_ADVICES,
    }
)

#: Addenda type codes this module distinguishes.  ``05`` is ordinary payment
#: related information and carries no structural meaning here.  The other two
#: change what the entry they hang from *is*, which is why they are named.
NACHA_ADDENDA_RETURN = "99"
NACHA_ADDENDA_NOTIFICATION_OF_CHANGE = "98"
NACHA_ADDENDA_PAYMENT_INFORMATION = "05"

#: The direction each entry detail transaction code fixes.
#:
#: Enumerated rather than derived.  The codes fall into decades by account type
#: — 2x checking, 3x savings, 4x general ledger, 5x loan — and inside the first
#: three decades the offsets are regular: ``x1``–``x4`` credit the receiver and
#: ``x6``–``x9`` debit them.  The loan decade breaks it.  ``55`` is an automated
#: loan account debit and sits in the position that carries a credit everywhere
#: else, because a loan account is the originator's asset and the customer's
#: liability, so the sign convention inverts with it.
#:
#: A parser that inferred the offsets would therefore place ``55`` on the credit
#: side.  In a mixed batch the batch control totals would catch it; in a batch
#: of loan activity that nets to zero they would not, and the entry hash — which
#: is blind to amount and direction — would not either.  So the table is
#: written out, and :func:`_direction_for_transaction_code` returns ``None`` for
#: anything absent from it rather than extrapolating.
NACHA_TRANSACTION_CODE_DIRECTIONS: dict[str, TransactionDirection] = {
    # Demand (checking) accounts.
    "21": TransactionDirection.credit,  # return or NOC for a credit entry
    "22": TransactionDirection.credit,  # automated deposit
    "23": TransactionDirection.credit,  # prenotification of a credit
    "24": TransactionDirection.credit,  # zero dollar with remittance, credit
    "26": TransactionDirection.debit,  # return or NOC for a debit entry
    "27": TransactionDirection.debit,  # automated payment
    "28": TransactionDirection.debit,  # prenotification of a debit
    "29": TransactionDirection.debit,  # zero dollar with remittance, debit
    # Savings accounts.
    "31": TransactionDirection.credit,
    "32": TransactionDirection.credit,
    "33": TransactionDirection.credit,
    "34": TransactionDirection.credit,
    "36": TransactionDirection.debit,
    "37": TransactionDirection.debit,
    "38": TransactionDirection.debit,
    "39": TransactionDirection.debit,
    # General ledger accounts.
    "41": TransactionDirection.credit,
    "42": TransactionDirection.credit,
    "43": TransactionDirection.credit,
    "44": TransactionDirection.credit,
    "46": TransactionDirection.debit,
    "47": TransactionDirection.debit,
    "48": TransactionDirection.debit,
    "49": TransactionDirection.debit,
    # Loan accounts.  ``55`` is the exception the table exists for.
    "51": TransactionDirection.credit,
    "52": TransactionDirection.credit,
    "53": TransactionDirection.credit,
    "54": TransactionDirection.credit,
    "55": TransactionDirection.debit,  # automated loan account debit
    "56": TransactionDirection.debit,
}

#: Codes that announce a zero-dollar account test rather than a payment.  Every
#: one of these must carry an amount of zero, and this module checks that:
#: a prenotification with money in it is a contradiction in the file, not a
#: payment that happens to be labelled oddly.
NACHA_PRENOTIFICATION_CODES: frozenset[str] = frozenset(
    {"23", "28", "33", "38", "43", "48", "53", "58"}
)

#: Codes used for an automated return or a notification of change.  Which of
#: the two it is cannot be read from the code — the pair share it — and is
#: settled by the addenda type code hanging from the entry.  A return moves
#: money back; a notification of change is zero dollar and corrects account
#: data.  See :class:`NachaEntry`.
NACHA_RETURN_OR_NOC_CODES: frozenset[str] = frozenset(
    {"21", "26", "31", "36", "41", "46", "51", "56"}
)

#: The standard entry class code for an international transaction.  Its foreign
#: currency and true parties live in addenda this module does not decode.
NACHA_SEC_INTERNATIONAL = "IAT"

#: The standard entry class code for a corporate trade exchange.  A CTX entry
#: detail reuses the individual-identification and name positions for an
#: addenda count and a receiving company name, so the two fields are recorded
#: under their positional names and not under a meaning they do not carry here.
NACHA_SEC_CORPORATE_TRADE_EXCHANGE = "CTX"

#: A NACHA numeric field is digits and nothing else.  Applied before ``int``
#: sees the text, because ``int`` accepts a leading sign, surrounding
#: whitespace and underscores, none of which can appear in a fixed-width field
#: without meaning that the field boundaries are wrong.
_DIGITS_RE = re.compile(r"^\d+$")

#: A filler record: ninety-four ``9`` characters, written to block the file out
#: to a multiple of ten records.
_FILLER_RE = re.compile(r"^9{%d}$" % NACHA_RECORD_LENGTH)


# ---------------------------------------------------------------------------
# Field offsets
# ---------------------------------------------------------------------------
#
# Every position in the format, as a half-open slice, named once.  Fixed-width
# parsing has no redundancy in it: an offset that is wrong by one yields a
# field that is still a string of the right shape and is silently a different
# quantity.  There is nothing in the data to catch that, so the offsets are
# stated in one table and verified against the record length at import time by
# :func:`_verify_offsets`, which is the only check available.

# ``1`` file header.
_FH_PRIORITY = (1, 3)
_FH_IMMEDIATE_DESTINATION = (3, 13)
_FH_IMMEDIATE_ORIGIN = (13, 23)
_FH_CREATION_DATE = (23, 29)
_FH_CREATION_TIME = (29, 33)
_FH_ID_MODIFIER = (33, 34)
_FH_RECORD_SIZE = (34, 37)
_FH_BLOCKING_FACTOR = (37, 39)
_FH_FORMAT_CODE = (39, 40)
_FH_DESTINATION_NAME = (40, 63)
_FH_ORIGIN_NAME = (63, 86)
_FH_REFERENCE_CODE = (86, 94)

# ``5`` batch header.
_BH_SERVICE_CLASS = (1, 4)
_BH_COMPANY_NAME = (4, 20)
_BH_DISCRETIONARY_DATA = (20, 40)
_BH_COMPANY_IDENTIFICATION = (40, 50)
_BH_STANDARD_ENTRY_CLASS = (50, 53)
_BH_ENTRY_DESCRIPTION = (53, 63)
_BH_DESCRIPTIVE_DATE = (63, 69)
_BH_EFFECTIVE_ENTRY_DATE = (69, 75)
_BH_SETTLEMENT_DATE = (75, 78)
_BH_ORIGINATOR_STATUS = (78, 79)
_BH_ORIGINATING_DFI = (79, 87)
_BH_BATCH_NUMBER = (87, 94)

# ``6`` entry detail.
_ED_TRANSACTION_CODE = (1, 3)
_ED_RECEIVING_DFI = (3, 11)
_ED_CHECK_DIGIT = (11, 12)
_ED_ACCOUNT_NUMBER = (12, 29)
_ED_AMOUNT = (29, 39)
_ED_INDIVIDUAL_IDENTIFICATION = (39, 54)
_ED_INDIVIDUAL_NAME = (54, 76)
_ED_DISCRETIONARY_DATA = (76, 78)
_ED_ADDENDA_INDICATOR = (78, 79)
_ED_TRACE_NUMBER = (79, 94)

# ``7`` addenda.
_AD_TYPE_CODE = (1, 3)
_AD_PAYMENT_INFORMATION = (3, 83)
_AD_SEQUENCE_NUMBER = (83, 87)
_AD_ENTRY_DETAIL_SEQUENCE = (87, 94)

# ``8`` batch control.
_BC_SERVICE_CLASS = (1, 4)
_BC_ENTRY_ADDENDA_COUNT = (4, 10)
_BC_ENTRY_HASH = (10, 20)
_BC_TOTAL_DEBITS = (20, 32)
_BC_TOTAL_CREDITS = (32, 44)
_BC_COMPANY_IDENTIFICATION = (44, 54)
_BC_MESSAGE_AUTHENTICATION = (54, 73)
_BC_ORIGINATING_DFI = (79, 87)
_BC_BATCH_NUMBER = (87, 94)

# ``9`` file control.
_FC_BATCH_COUNT = (1, 7)
_FC_BLOCK_COUNT = (7, 13)
_FC_ENTRY_ADDENDA_COUNT = (13, 21)
_FC_ENTRY_HASH = (21, 31)
_FC_TOTAL_DEBITS = (31, 43)
_FC_TOTAL_CREDITS = (43, 55)


def _verify_offsets() -> None:
    """Refuse to import on an offset that cannot be right.

    Not a test.  A test can be skipped, and the failure this guards against —
    a slice edited to the wrong bound — produces a module that imports, parses,
    and misreports.  Checking at import means a file with a broken offset table
    cannot be used at all, which is the correct outcome for a table whose
    errors are otherwise invisible.

    What is checkable here is bounds and ordering, not correctness against the
    specification; no amount of internal consistency proves the amount field is
    where the format says it is.  That is what the control totals establish,
    and they establish it on every file rather than once at import.
    """
    table = {
        name: value
        for name, value in globals().items()
        if re.match(r"^_(FH|BH|ED|AD|BC|FC)_", name)
    }
    for name, (start, stop) in sorted(table.items()):
        if not 0 <= start < stop <= NACHA_RECORD_LENGTH:
            raise AssertionError(
                f"{name} = ({start}, {stop}) is not a slice inside a "
                f"{NACHA_RECORD_LENGTH}-character record"
            )


_verify_offsets()


# ---------------------------------------------------------------------------
# Reading fields out of a fixed-width record
# ---------------------------------------------------------------------------


def _field(record: str, span: tuple[int, int]) -> str:
    """The characters at ``span``, with surrounding blanks removed.

    Alphanumeric NACHA fields are left-justified and blank-filled and numeric
    fields are right-justified and zero-filled, so stripping blanks is lossless
    for both.  Zeros are deliberately *not* stripped: a zero-filled numeric
    field is a number, and an amount field of ten zeros means zero dollars
    rather than an absent amount.
    """
    return record[span[0] : span[1]].strip()


def _required_field(
    record: str, span: tuple[int, int], name: str, *, context: str
) -> str:
    value = _field(record, span)
    if not value:
        raise NachaMissingFieldError(
            f"{context}: {name} is mandatory and is blank "
            f"(positions {span[0] + 1}-{span[1]})"
        )
    return value


def _parse_count(text: str, *, context: str, name: str) -> int:
    """Read a declared count: digits, and nothing that ``int`` would forgive."""
    if not _DIGITS_RE.match(text):
        raise NachaMalformedFileError(
            f"{context}: {name} is {text!r}, which is not a count; a NACHA "
            "count is a right-justified zero-filled run of digits"
        )
    return int(text)


def _parse_amount(text: str, *, context: str, name: str) -> Money:
    """Read a NACHA amount: a count of cents, written as digits.

    There is no decimal point in the field and no separator, and the two
    implied decimal places are exactly the exponent of the settlement currency.
    So the field is already a minor-unit count and nothing is scaled, rounded
    or inferred on the way in.
    """
    if not _DIGITS_RE.match(text):
        raise NachaAmountError(
            f"{context}: {name} is {text!r}, which is not a NACHA amount; "
            "amounts are written as an unsigned run of digits in cents, with "
            "no decimal point, no sign and no separators"
        )
    try:
        return Money.from_minor_units(int(text), NACHA_CURRENCY)
    except MoneyError as exc:
        raise NachaAmountError(
            f"{context}: {name} {text!r} is not usable as {NACHA_CURRENCY}: {exc}"
        ) from exc


def _direction_for_transaction_code(code: str) -> Optional[TransactionDirection]:
    """The direction a transaction code fixes, or ``None`` if it fixes none.

    ``None`` rather than a guess, for the reason set out at
    :data:`NACHA_TRANSACTION_CODE_DIRECTIONS`: the decade offsets look regular
    and are not, and a code invented after this table was written is more
    likely to break the pattern than to follow it.  The caller decides what an
    undirected entry costs, and :class:`NachaControlTotal` treats it as
    something that blocks the money totals rather than as a zero.
    """
    return NACHA_TRANSACTION_CODE_DIRECTIONS.get(code)


#: The check digit the leading eight digits of a routing number imply, and
#: ``None`` where the prefix is not eight digits.
#:
#: This module held the only copy of the ABA algorithm until
#: :mod:`services.financial.check_digits` existed, and the note that stood here
#: asked for the duplication to be removed rather than discovered.  It has
#: been: the weights and the arithmetic now live there alone and this is an
#: alias, kept under the private name because that is what this module and its
#: tests call it and renaming it would be churn for nothing.
_aba_check_digit = aba_check_digit


def _truncate_hash(total: int) -> int:
    """The rightmost :data:`NACHA_ENTRY_HASH_DIGITS` digits of a hash sum.

    The specification says the hash field carries the low-order digits of the
    sum and that any overflow is discarded, which is this.  Stated as a
    function so that the batch level and the file level cannot disagree about
    the width, and so that the discarding is visible rather than implied by a
    field that happens to be ten characters wide.
    """
    return total % (10**NACHA_ENTRY_HASH_DIGITS)


def _weakest(statuses: Iterable[ReconciliationStatus]) -> ReconciliationStatus:
    """The least favourable outcome in a run of them.

    Order: ``unbalanced`` beats everything, then ``unavailable``, then
    ``not_attempted``, and ``balanced`` only when every check balanced.  A
    single failure anywhere governs, which is what stops a file with one clean
    batch and one broken one from presenting as clean.
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
# Physical records
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NachaRecord:
    """One physical record, its type code, and where it came from.

    ``line_number`` is one-based and counts records rather than text lines,
    because a NACHA file written without line breaks — which is common, and
    valid — has no text lines to count.  For a file that does have them the two
    coincide.
    """

    line_number: int
    code: str
    text: str

    @property
    def is_filler(self) -> bool:
        return bool(_FILLER_RE.match(self.text))


def _split_records(text: str) -> tuple[NachaRecord, ...]:
    """Cut the file into ninety-four character records.

    Two carriages are in circulation and both are conformant.  A file may be
    written with a line terminator after each record, or as one unbroken run of
    characters whose length is a multiple of the record length.  Which one is
    in hand is decided by whether the text contains a newline at all, rather
    than by trying both and keeping whichever produced more records: a
    file-shaped run of text can usually be cut both ways, and the reading that
    yields more records is not the reading that is correct.

    *Short records are padded and long ones are refused*, and the asymmetry is
    deliberate.  Trailing blanks carry no information in a fixed-width format,
    so a record shortened by a transport that trimmed them is restored exactly
    by putting them back; there is no other content it could have lost, because
    what was removed was blank by definition.  A record that is *longer* has no
    such reading — the surplus characters are somewhere in the middle as far as
    this module can tell, and every field boundary after the surplus is wrong.

    The padding is safe only because a record genuinely truncated mid-field is
    caught downstream rather than here: the last field of a ``6`` entry detail
    is the trace number, which is mandatory and never blank, so a truncated
    entry is refused by :func:`_parse_entry` when its trace number comes back
    empty.  The same holds for the trailers, whose declared totals sit past the
    midpoint of the record and whose absence is a refusal rather than a zero.
    """
    if not text.strip():
        raise NotANachaError("the file is empty")

    if "\n" in text or "\r" in text:
        raw = [line.rstrip("\r\n") for line in text.splitlines()]
    else:
        if len(text) % NACHA_RECORD_LENGTH != 0:
            raise NachaMalformedFileError(
                f"the file has no line terminators and is {len(text)} "
                f"characters, which is not a multiple of the "
                f"{NACHA_RECORD_LENGTH}-character record length; it cannot be "
                "cut into records without guessing where one ends"
            )
        raw = [
            text[start : start + NACHA_RECORD_LENGTH]
            for start in range(0, len(text), NACHA_RECORD_LENGTH)
        ]

    records: list[NachaRecord] = []
    for index, line in enumerate(raw, start=1):
        if not line.strip():
            # A blank line between records is carriage, not a record.  Kept out
            # of the numbering deliberately: the numbers a reader is given have
            # to match the records, and a blank that consumed a number would
            # make every message after it point one record short.
            continue
        if len(line) > NACHA_RECORD_LENGTH:
            raise NachaMalformedFileError(
                f"record {len(records) + 1} (line {index}) is {len(line)} "
                f"characters, over the {NACHA_RECORD_LENGTH}-character record "
                "length; the surplus cannot be located, so every field "
                "boundary after it is unknown"
            )
        padded = line.ljust(NACHA_RECORD_LENGTH)
        records.append(
            NachaRecord(
                line_number=len(records) + 1, code=padded[0], text=padded
            )
        )

    if not records:
        raise NotANachaError("the file carries no records")
    return tuple(records)


# ---------------------------------------------------------------------------
# What a parsed file is made of
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NachaAddenda:
    """A ``7`` record: information hanging from the entry above it.

    ``payment_information`` is captured verbatim and left unparsed.  Its
    contents are structured for some addenda types — ``05`` on a CTX entry
    carries an EDI or STP 820 remittance segment, ``99`` carries a return
    reason code, ``98`` a change code and the corrected data — and none of that
    is decoded here, for the reason that governs the parsers generally: a field
    read into
    fields is a field a reader can no longer see as it was sent, and the return
    reason in particular is the sort of thing an opposing expert will want to
    read in the original.  What *is* read is the type code, because it changes
    what the entry it hangs from is.
    """

    line_number: int
    type_code: str
    payment_information: str
    sequence_number: Optional[int]
    entry_detail_sequence: Optional[str]
    locator: Locator = NACHA_LOCATOR

    @property
    def is_return(self) -> bool:
        return self.type_code == NACHA_ADDENDA_RETURN

    @property
    def is_notification_of_change(self) -> bool:
        return self.type_code == NACHA_ADDENDA_NOTIFICATION_OF_CHANGE


@dataclass(frozen=True, slots=True)
class NachaEntry:
    """A ``6`` record and the ``7`` records that hang from it.

    ``direction`` is ``None`` where the transaction code fixes none.  That is
    not the same as zero and is not treated as such: an entry with an unknown
    direction and a non-zero amount blocks the money totals for its batch,
    because putting it on either side would make one of the two declared
    figures agree by construction.

    ``individual_identification`` and ``individual_name`` are the positional
    names of two fields the format reuses.  On a CTX batch they carry a count
    of addenda records and a receiving company name instead.  They are recorded
    under the positions they occupy rather than under either meaning, so that a
    reader is not told the number of addenda records is somebody's name.
    """

    line_number: int
    transaction_code: str
    direction: Optional[TransactionDirection]
    receiving_dfi: str
    check_digit: str
    account_number: str
    amount: Money
    individual_identification: str
    individual_name: str
    discretionary_data: str
    addenda_indicator: str
    trace_number: str
    addenda: tuple[NachaAddenda, ...] = ()
    locator: Locator = NACHA_LOCATOR

    @property
    def routing_number(self) -> str:
        """The nine-digit routing number: the eight-digit prefix and its check digit."""
        return f"{self.receiving_dfi}{self.check_digit}"

    @property
    def check_digit_agrees(self) -> Optional[bool]:
        """Whether the stated check digit is the one the prefix implies.

        ``None`` where it cannot be computed.  Reported rather than enforced:
        a single failing check digit is a corrupt record and is worth flagging
        loudly, but refusing the whole file for it would discard the other
        several thousand entries and the control totals that vouch for them.
        The failure surfaces as a file-level reservation instead, which is the
        mechanism that already exists for "a human needs to look at this".
        """
        expected = _aba_check_digit(self.receiving_dfi)
        if expected is None or not self.check_digit.isdigit():
            return None
        return expected == int(self.check_digit)

    @property
    def is_prenotification(self) -> bool:
        """A zero-dollar test that the receiving account exists."""
        return self.transaction_code in NACHA_PRENOTIFICATION_CODES

    @property
    def is_return(self) -> bool:
        """Money coming back.  Settled by the addenda, not by the code alone.

        The transaction codes for a return and for a notification of change are
        the same code, which is why this is not simply a set membership test.
        The two are told apart by the addenda type that hangs from the entry,
        and an entry carrying neither is an ordinary payment whose code happens
        to be in the shared set.
        """
        return any(addendum.is_return for addendum in self.addenda)

    @property
    def is_notification_of_change(self) -> bool:
        """A zero-dollar correction of account data, not a movement of money."""
        return any(
            addendum.is_notification_of_change for addendum in self.addenda
        )

    @property
    def entry_detail_sequence(self) -> str:
        """The last seven digits of the trace number.

        This is what a ``7`` addenda record points back at, so it is the join
        between an addendum and its entry.  Derived from the trace number
        rather than stored, because the format derives it that way and storing
        it separately would allow the two to disagree.
        """
        return self.trace_number[-7:]


@dataclass(frozen=True, slots=True)
class NachaControlTotal:
    """A trailer against what it closes: an ``8`` batch control or a ``9`` file control.

    One type for both levels because it is one question asked twice — does the
    trailer agree with the records it encloses — and a reader comparing the two
    should not have to translate between shapes to do it.  ``level`` names
    which trailer.  ``declared_batch_count`` and ``declared_block_count`` are
    ``None`` at batch level, where those quantities do not exist.

    Four independent comparisons at batch level and six at file level, each
    with its own ``*_agrees`` property so that a reviewer can see *which* one
    failed rather than only that something did.  ``status`` is the conjunction:
    ``balanced`` only where every comparison that could be made agreed.

    The two money totals are compared as :class:`Money` rather than as integers,
    unlike the BAI2 control total, and the difference is not an inconsistency.
    A BAI2 control total is a checksum over digits with no currency of its own,
    so comparing it as money would have required inventing one.  A NACHA total
    is a dollar figure in a file whose settlement currency is fixed, so it has
    one, and the arithmetic that a reviewer will want to do with a delta is
    monetary arithmetic.
    """

    level: str
    status: ReconciliationStatus
    basis: str
    declared_entry_addenda_count: Optional[int]
    computed_entry_addenda_count: int
    declared_entry_hash: Optional[int]
    computed_entry_hash: int
    declared_debit_total: Optional[Money]
    computed_debit_total: Optional[Money]
    debit_delta: Optional[Money]
    declared_credit_total: Optional[Money]
    computed_credit_total: Optional[Money]
    credit_delta: Optional[Money]
    undirected_count: int = 0
    #: Whether the batch's service class code is consistent with the totals it
    #: declares.  ``220`` announces a credits-only batch and ``225`` a
    #: debits-only one, so a non-zero figure on the other side contradicts the
    #: batch's own header.  ``None`` at file level, where no service class is
    #: stated, and on ``200``, which permits both.
    #:
    #: Treated as a control failure rather than as a structural refusal because
    #: it is one: two declared quantities in the file disagree, which is what
    #: every other comparison here reports, and reporting it the same way puts
    #: it in the same list a reviewer is already reading.
    service_class_consistent: Optional[bool] = None
    declared_batch_count: Optional[int] = None
    computed_batch_count: Optional[int] = None
    declared_block_count: Optional[int] = None
    computed_block_count: Optional[int] = None
    unavailable_reason: Optional[str] = None

    @property
    def entry_addenda_count_agrees(self) -> bool:
        return (
            self.declared_entry_addenda_count
            == self.computed_entry_addenda_count
        )

    @property
    def entry_hash_agrees(self) -> bool:
        return self.declared_entry_hash == self.computed_entry_hash

    @property
    def debit_total_agrees(self) -> bool:
        return (
            self.declared_debit_total is not None
            and self.declared_debit_total == self.computed_debit_total
        )

    @property
    def credit_total_agrees(self) -> bool:
        return (
            self.declared_credit_total is not None
            and self.declared_credit_total == self.computed_credit_total
        )

    @property
    def batch_count_agrees(self) -> bool:
        return self.declared_batch_count == self.computed_batch_count

    @property
    def block_count_agrees(self) -> bool:
        return self.declared_block_count == self.computed_block_count

    @property
    def failed_checks(self) -> tuple[str, ...]:
        """Which comparisons disagreed, named.

        Carried on the artefact rather than left to a caller to reconstruct.
        The value of six separate control totals is entirely in knowing which
        of them failed — a hash failure and a credit-total failure mean
        different things and send a reviewer to different places — and a
        boolean status throws exactly that away.
        """
        failures: list[str] = []
        if not self.entry_addenda_count_agrees:
            failures.append("entry and addenda count")
        if not self.entry_hash_agrees:
            failures.append("entry hash")
        if not self.debit_total_agrees:
            failures.append("total debits")
        if not self.credit_total_agrees:
            failures.append("total credits")
        if self.declared_batch_count is not None or self.computed_batch_count is not None:
            if not self.batch_count_agrees:
                failures.append("batch count")
        if self.declared_block_count is not None or self.computed_block_count is not None:
            if not self.block_count_agrees:
                failures.append("block count")
        if self.service_class_consistent is False:
            failures.append("service class against the totals declared")
        return tuple(failures)


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------

#: What each level's declared figures are compared against, in words, for
#: :attr:`NachaControlTotal.basis`.  Named constants rather than literals at the
#: construction sites so that the two cannot drift apart, and so that a test
#: asserting on a basis asserts on the same string the artefact carries.
_BATCH_CONTROL_BASIS = (
    "the 6 entry detail and 7 addenda records between this batch's 5 header "
    "and its 8 trailer"
)
_FILE_CONTROL_BASIS = (
    "the totals declared by the 8 batch control records in this file, together "
    "with the physical record count of the whole file"
)


def _entry_hash(entries: Sequence[NachaEntry]) -> int:
    """The batch entry hash: the receiving institutions, summed and truncated.

    The eight-digit routing prefix is summed, not the nine-digit routing
    number.  Including the check digit would multiply every contribution by ten
    and add the check digit itself, which produces a number that is stable,
    plausible, and disagrees with every sender's.  Addenda contribute nothing;
    the hash is over entries.
    """
    return _truncate_hash(
        sum(int(entry.receiving_dfi) for entry in entries if entry.receiving_dfi.isdigit())
    )


def _partition(entries: Sequence[NachaEntry]) -> tuple[Money, Money, int]:
    """Credits, debits, and the number of entries that block the two totals.

    An entry blocks when its transaction code fixes no direction *and* its
    amount is non-zero.  A zero amount contributes nothing to either side, so
    not knowing which side it belongs on costs nothing — which matters, because
    a prenotification of a code this table does not carry is exactly that case
    and refusing to check a batch over it would be refusing over nothing.
    """
    credits = Money.zero(NACHA_CURRENCY)
    debits = Money.zero(NACHA_CURRENCY)
    blocking = 0
    for entry in entries:
        if entry.direction is TransactionDirection.credit:
            credits = credits + entry.amount
        elif entry.direction is TransactionDirection.debit:
            debits = debits + entry.amount
        elif not entry.amount.is_zero:
            blocking += 1
    return credits, debits, blocking


def _service_class_consistent(
    service_class: str, debits: Money, credits: Money
) -> Optional[bool]:
    """Whether the declared totals are permitted by the declared service class.

    ``None`` where the service class permits both sides, which is the ordinary
    case and is not an absence of evidence — it is a statement that constrains
    nothing, so there is nothing to agree or disagree with.
    """
    if service_class == NACHA_SERVICE_CLASS_CREDITS_ONLY:
        return debits.is_zero
    if service_class == NACHA_SERVICE_CLASS_DEBITS_ONLY:
        return credits.is_zero
    if service_class == NACHA_SERVICE_CLASS_ADVICES:
        return debits.is_zero and credits.is_zero
    return None


def _status_from(checks: Sequence[ReconciliationStatus]) -> ReconciliationStatus:
    """Fold per-comparison outcomes into one.

    Uses :func:`_weakest`, which means a definite contradiction anywhere
    outranks an inability to check anywhere.  That ordering is the one that
    matters: a batch whose entry hash is wrong is a batch with something wrong
    in it, and the fact that its money totals could not be checked because of
    an unrecognised transaction code does not soften that.
    """
    return _weakest(checks)


def _check_batch_control(
    *,
    service_class: str,
    entries: Sequence[NachaEntry],
    addenda_count: int,
    declared_entry_addenda_count: int,
    declared_entry_hash: int,
    declared_debits: Money,
    declared_credits: Money,
) -> NachaControlTotal:
    """Compare an ``8`` batch control against the records it closes.

    Four comparisons, plus the service class consistency check, each recorded
    separately.  The point of a format that states four quantities rather than
    one is that the four fail independently and each failure means something
    different, so folding them into a single boolean before a reviewer sees
    them would throw away most of what the format is for.
    """
    computed_count = len(entries) + addenda_count
    computed_hash = _entry_hash(entries)
    credits, debits, blocking = _partition(entries)

    checks: list[ReconciliationStatus] = [
        ReconciliationStatus.balanced
        if declared_entry_addenda_count == computed_count
        else ReconciliationStatus.unbalanced,
        ReconciliationStatus.balanced
        if declared_entry_hash == computed_hash
        else ReconciliationStatus.unbalanced,
    ]

    reason: Optional[str] = None
    if blocking:
        # Declining rather than assuming, for the reason
        # :func:`~services.financial.bai2._check_balance_identity` gives: an
        # entry placed on a side it may not belong to makes one of the two
        # declared figures agree by construction, and an agreement obtained
        # that way is worse than no agreement at all.
        computed_debits: Optional[Money] = None
        computed_credits: Optional[Money] = None
        debit_delta: Optional[Money] = None
        credit_delta: Optional[Money] = None
        consistent = None
        checks.append(ReconciliationStatus.unavailable)
        reason = (
            f"{blocking} entr{'y' if blocking == 1 else 'ies'} "
            f"{'carries' if blocking == 1 else 'carry'} a transaction code "
            "that fixes no direction and a non-zero amount, so neither money "
            "total can be computed without placing them on a side the file "
            "does not state"
        )
    else:
        computed_debits = debits
        computed_credits = credits
        debit_delta = computed_debits - declared_debits
        credit_delta = computed_credits - declared_credits
        consistent = _service_class_consistent(
            service_class, declared_debits, declared_credits
        )
        checks.append(
            ReconciliationStatus.balanced
            if debit_delta.is_zero
            else ReconciliationStatus.unbalanced
        )
        checks.append(
            ReconciliationStatus.balanced
            if credit_delta.is_zero
            else ReconciliationStatus.unbalanced
        )
        if consistent is False:
            checks.append(ReconciliationStatus.unbalanced)

    return NachaControlTotal(
        level=NACHA_BATCH_CONTROL,
        status=_status_from(checks),
        basis=_BATCH_CONTROL_BASIS,
        declared_entry_addenda_count=declared_entry_addenda_count,
        computed_entry_addenda_count=computed_count,
        declared_entry_hash=declared_entry_hash,
        computed_entry_hash=computed_hash,
        declared_debit_total=declared_debits,
        computed_debit_total=computed_debits,
        debit_delta=debit_delta,
        declared_credit_total=declared_credits,
        computed_credit_total=computed_credits,
        credit_delta=credit_delta,
        undirected_count=blocking,
        service_class_consistent=consistent,
        unavailable_reason=reason,
    )


def _check_file_control(
    *,
    batches: Sequence["NachaBatch"],
    declared_batch_count: int,
    declared_block_count: int,
    declared_entry_addenda_count: int,
    declared_entry_hash: int,
    declared_debits: Money,
    declared_credits: Money,
    physical_record_count: int,
) -> NachaControlTotal:
    """Compare the ``9`` file control against the batch trailers beneath it.

    **Computed from what the batches declared, not from their contents.**  The
    specification defines the file figures as sums of the batch figures, and
    following that literally is also what localises a failure.  A single
    corrupted entry makes its own batch's trailer disagree; the file trailer,
    compared against the sum of what the batches *said*, still agrees, and a
    reviewer is shown one failure at the level where the fault actually is.
    Recomputing from the entries instead would fail both levels for one cause
    and leave the reviewer to work out that it was one cause.

    Nothing is lost by it.  A batch that went missing entirely still fails
    here, on the batch count and on every sum; a batch that lied about its own
    totals still fails at batch level.  The two levels together cover both, and
    they cover them separately, which is the point.

    The block count is the one figure with no batch-level analogue: it is a
    property of the file's physical carriage — how many ten-record blocks it
    occupies, filler included — and it is the only check here that would notice
    records appended after the trailer.
    """
    computed_batch_count = len(batches)
    computed_block_count = -(-physical_record_count // NACHA_BLOCKING_FACTOR)
    computed_count = sum(
        batch.control_total.declared_entry_addenda_count or 0 for batch in batches
    )
    computed_hash = _truncate_hash(
        sum(batch.control_total.declared_entry_hash or 0 for batch in batches)
    )
    computed_debits = Money.zero(NACHA_CURRENCY)
    computed_credits = Money.zero(NACHA_CURRENCY)
    for batch in batches:
        if batch.control_total.declared_debit_total is not None:
            computed_debits = computed_debits + batch.control_total.declared_debit_total
        if batch.control_total.declared_credit_total is not None:
            computed_credits = (
                computed_credits + batch.control_total.declared_credit_total
            )

    debit_delta = computed_debits - declared_debits
    credit_delta = computed_credits - declared_credits

    checks = [
        ReconciliationStatus.balanced
        if declared_batch_count == computed_batch_count
        else ReconciliationStatus.unbalanced,
        ReconciliationStatus.balanced
        if declared_block_count == computed_block_count
        else ReconciliationStatus.unbalanced,
        ReconciliationStatus.balanced
        if declared_entry_addenda_count == computed_count
        else ReconciliationStatus.unbalanced,
        ReconciliationStatus.balanced
        if declared_entry_hash == computed_hash
        else ReconciliationStatus.unbalanced,
        ReconciliationStatus.balanced
        if debit_delta.is_zero
        else ReconciliationStatus.unbalanced,
        ReconciliationStatus.balanced
        if credit_delta.is_zero
        else ReconciliationStatus.unbalanced,
    ]

    return NachaControlTotal(
        level=NACHA_FILE_CONTROL,
        status=_status_from(checks),
        basis=_FILE_CONTROL_BASIS,
        declared_entry_addenda_count=declared_entry_addenda_count,
        computed_entry_addenda_count=computed_count,
        declared_entry_hash=declared_entry_hash,
        computed_entry_hash=computed_hash,
        declared_debit_total=declared_debits,
        computed_debit_total=computed_debits,
        debit_delta=debit_delta,
        declared_credit_total=declared_credits,
        computed_credit_total=computed_credits,
        credit_delta=credit_delta,
        declared_batch_count=declared_batch_count,
        computed_batch_count=computed_batch_count,
        declared_block_count=declared_block_count,
        computed_block_count=computed_block_count,
    )


@dataclass(frozen=True, slots=True)
class NachaBatch:
    """A ``5`` header, the entries between it and its ``8`` trailer, and that trailer.

    A batch is the unit that carries the format's real strength: its trailer
    states debits and credits *separately*, so a direction error inside it
    cannot cancel.  It is also the unit at which a reservation is raised, since
    the things worth reserving over — a prenotification run, a notification of
    change, an international entry whose real currency is somewhere this module
    does not read — are properties of what the batch was for.
    """

    line_number: int
    service_class: str
    company_name: str
    company_identification: str
    standard_entry_class: str
    entry_description: str
    descriptive_date: str
    effective_entry_date: str
    settlement_date: str
    originator_status: str
    originating_dfi: str
    batch_number: str
    entries: tuple[NachaEntry, ...]
    control_total: NachaControlTotal

    @property
    def addenda(self) -> tuple[NachaAddenda, ...]:
        """Every ``7`` record in the batch, in file order."""
        return tuple(
            addendum for entry in self.entries for addendum in entry.addenda
        )

    @property
    def reconciliation_status(self) -> ReconciliationStatus:
        """The ``8`` trailer's verdict.  A batch has no level beneath it."""
        return self.control_total.status

    @property
    def admissibility_reservations(self) -> tuple[str, ...]:
        """Why a human should look at this batch before it enters a ledger.

        Each of these describes a batch whose arithmetic can be perfectly
        sound and whose contents are still not what a total of payments should
        be made of.  None of them is a defect and none is refused; what they
        block is the *automatic* admission that p0 carries.

        A prenotification is a zero-dollar test that an account exists.  A
        batch of them contributes nothing to either money total while still
        counting in the entry count and the hash, so every check passes
        vacuously — the strongest possible arithmetic agreement about no money
        at all.

        A notification of change is a correction to account data travelling on
        a payment's record shape.  It is zero dollar for the same reason and
        additionally means the account number in the entry it corrects is
        known to be wrong, which is a thing a reader of the *other* file needs
        told.

        An international entry settles in a foreign currency whose figure is in
        addenda this module does not decode.  The dollar amount in the ``6``
        record is real and is the settlement leg, so the arithmetic is sound;
        what is not available here is what the parties actually agreed, and a
        total that silently treats the settlement leg as the transaction is
        answering a different question from the one asked.

        A failing routing check digit is one corrupt record.  It does not
        invalidate the file — see :attr:`NachaEntry.check_digit_agrees` for why
        the whole file is not refused for it — but the entry is addressed to
        an institution number that cannot exist, so where the money went is
        not established by this document.
        """
        reservations: list[str] = []

        prenotes = sum(1 for entry in self.entries if entry.is_prenotification)
        if prenotes:
            reservations.append(
                f"batch {self.batch_number} carries {prenotes} prenotification "
                f"entr{'y' if prenotes == 1 else 'ies'}, which are zero-dollar "
                "tests that an account exists rather than movements of money; "
                "they satisfy every control total while contributing nothing "
                "to either side"
            )

        changes = sum(
            1 for entry in self.entries if entry.is_notification_of_change
        )
        if changes:
            reservations.append(
                f"batch {self.batch_number} carries {changes} notification"
                f"{'' if changes == 1 else 's'} of change, which correct "
                "account data rather than move money, and which state that the "
                "account details on the entries they answer are wrong"
            )

        returns = sum(1 for entry in self.entries if entry.is_return)
        if returns:
            reservations.append(
                f"batch {self.batch_number} carries {returns} return"
                f"{'' if returns == 1 else 's'}; the money moves back, so the "
                "entry reverses an earlier one and a total containing both "
                "without netting them counts the same funds twice"
            )

        if self.standard_entry_class == NACHA_SEC_INTERNATIONAL:
            reservations.append(
                f"batch {self.batch_number} is an {NACHA_SEC_INTERNATIONAL} "
                "international batch; its foreign currency amounts and true "
                "parties are in addenda this parser records verbatim and does "
                f"not decode, so the {NACHA_CURRENCY} figures here are the "
                "settlement leg and not necessarily what was agreed"
            )

        bad_digits = sum(
            1 for entry in self.entries if entry.check_digit_agrees is False
        )
        if bad_digits:
            reservations.append(
                f"batch {self.batch_number} carries {bad_digits} entr"
                f"{'y' if bad_digits == 1 else 'ies'} whose routing number "
                "fails its own check digit, so the receiving institution is "
                "not established by the document"
            )

        if self.control_total.undirected_count:
            reservations.append(
                f"batch {self.batch_number} carries "
                f"{self.control_total.undirected_count} entr"
                f"{'y' if self.control_total.undirected_count == 1 else 'ies'} "
                "whose transaction code fixes no direction, so the money "
                "totals were not checked"
            )

        return tuple(reservations)


@dataclass(frozen=True, slots=True)
class NachaFile:
    """A parsed NACHA file: its ``1`` header, its batches and its ``9`` trailer."""

    immediate_destination: str
    immediate_origin: str
    creation_date: str
    creation_time: str
    file_id_modifier: str
    record_size: str
    blocking_factor: str
    format_code: str
    destination_name: str
    origin_name: str
    reference_code: str
    batches: tuple[NachaBatch, ...]
    control_total: NachaControlTotal
    physical_record_count: int

    #: Fixed.  NACHA is a structured file whose format mandates control totals
    #: at two levels, which is the whole of what the shape asserts.
    #: Whether those totals agree is the other half of the class and arrives
    #: from the arithmetic, not from here.
    source_shape: SourceShape = field(
        default=SourceShape.native_with_control_totals, init=False
    )

    @property
    def entries(self) -> tuple[NachaEntry, ...]:
        """Every ``6`` record in the file, in file order."""
        return tuple(entry for batch in self.batches for entry in batch.entries)

    @property
    def addenda(self) -> tuple[NachaAddenda, ...]:
        """Every ``7`` record in the file, in file order."""
        return tuple(
            addendum for batch in self.batches for addendum in batch.addenda
        )

    @property
    def admissibility_reservations(self) -> tuple[str, ...]:
        """Every batch's reservations, gathered so a caller reads one list."""
        return tuple(
            reason
            for batch in self.batches
            for reason in batch.admissibility_reservations
        )

    @property
    def reconciliation_status(self) -> ReconciliationStatus:
        """The ``9`` control total together with every batch beneath it.

        Both levels, because they check different things.  The file trailer is
        computed against what the batches *declared* — see
        :func:`_check_file_control` — so a batch that lied about its own
        contents consistently agrees with itself all the way up, and the only
        place that failure appears is at the batch level.
        """
        return _weakest(
            [
                self.control_total.status,
                *[batch.reconciliation_status for batch in self.batches],
            ]
        )

    @property
    def proof_class(self) -> ProofClass:
        """The class this file earns, computed rather than asserted.

        The shape and the outcome go to
        :func:`~services.financial.proof_class.assign_proof_class`, which owns
        the rule.  This module supplies the two inputs and has no vote on what
        they add up to.

        The one thing decided here is the reservation, and it is decided the
        same way :class:`~services.financial.bai2.Bai2File` decides it.  A
        batch of prenotifications produces a file whose every control total
        agrees, and on the evidence ``assign_proof_class`` is given that is
        rightly p0 — the arithmetic did pass.  But p0 auto-admits with no human
        act, and admitting a run of zero-dollar account tests to a verified
        ledger as though it were a run of payments is a worse error than any
        this module's arithmetic could make.  So the promotion is withheld, the
        file lands at p3, and the reservations say why in words a reviewer can
        read on the artefact.
        """
        earned = assign_proof_class(self.source_shape, self.reconciliation_status)
        if earned is ProofClass.p0 and self.admissibility_reservations:
            return ProofClass.p3
        return earned


# ---------------------------------------------------------------------------
# The structural walk
# ---------------------------------------------------------------------------


def _parse_addenda(record: NachaRecord) -> NachaAddenda:
    """Read a ``7`` addenda record.

    The type code is mandatory: it is what says whether the entry above is a
    payment, a return, or a correction, and an addendum with no type code is
    an addendum whose effect on its entry cannot be determined.  Everything
    else is optional, because the sequence fields are absent on some types and
    the payment information is by definition free-form.
    """
    context = f"record {record.line_number} (7 addenda)"
    type_code = _required_field(
        record.text, _AD_TYPE_CODE, "the addenda type code", context=context
    )

    sequence_text = _field(record.text, _AD_SEQUENCE_NUMBER)
    sequence_number: Optional[int] = None
    if sequence_text:
        sequence_number = _parse_count(
            sequence_text, context=context, name="the addenda sequence number"
        )

    entry_sequence = _field(record.text, _AD_ENTRY_DETAIL_SEQUENCE) or None

    return NachaAddenda(
        line_number=record.line_number,
        type_code=type_code,
        # Not stripped.  Position is meaningful inside an addenda payload for
        # the fixed-layout types, and a reader comparing this against the file
        # needs the characters as sent.
        payment_information=record.text[
            _AD_PAYMENT_INFORMATION[0] : _AD_PAYMENT_INFORMATION[1]
        ],
        sequence_number=sequence_number,
        entry_detail_sequence=entry_sequence,
    )


def _parse_entry(
    records: Sequence[NachaRecord], cursor: int
) -> tuple[NachaEntry, int]:
    """Read a ``6`` entry detail and every ``7`` that hangs from it.

    The addenda indicator is *not* used to decide whether to read addenda.  It
    is a declaration, the records are the fact, and where the two disagree the
    records govern: an indicator of ``0`` on an entry followed by a ``7``
    record would otherwise make that record vanish from the entry count and
    take the batch trailer's count check down with it, reporting an arithmetic
    failure whose cause is this function rather than the file.  What the
    indicator is good for is the reverse direction, and that is checked below.
    """
    record = records[cursor]
    context = f"record {record.line_number} (6 entry detail)"
    text = record.text

    transaction_code = _required_field(
        text, _ED_TRANSACTION_CODE, "the transaction code", context=context
    )
    receiving_dfi = _required_field(
        text, _ED_RECEIVING_DFI, "the receiving DFI identification", context=context
    )
    # The trace number is the last field in the record and is mandatory, which
    # is what makes padding a short record safe: a record truncated mid-way
    # loses its trace number and is refused here rather than read with the
    # missing characters silently supplied as blanks.
    trace_number = _required_field(
        text, _ED_TRACE_NUMBER, "the trace number", context=context
    )
    amount = _parse_amount(
        _field(text, _ED_AMOUNT) or "0", context=context, name="the amount"
    )

    addenda_indicator = _field(text, _ED_ADDENDA_INDICATOR)

    cursor += 1
    addenda: list[NachaAddenda] = []
    while cursor < len(records) and records[cursor].code == NACHA_ADDENDA:
        addenda.append(_parse_addenda(records[cursor]))
        cursor += 1

    if addenda_indicator == "1" and not addenda:
        raise NachaMalformedFileError(
            f"{context}: the addenda record indicator is 1, so the entry "
            "declares that addenda follow, and none do.  The missing records "
            "are counted in the batch trailer, so reading past this would "
            "report an arithmetic failure whose real cause is a truncated file"
        )

    return (
        NachaEntry(
            line_number=record.line_number,
            transaction_code=transaction_code,
            direction=_direction_for_transaction_code(transaction_code),
            receiving_dfi=receiving_dfi,
            check_digit=_field(text, _ED_CHECK_DIGIT),
            account_number=_field(text, _ED_ACCOUNT_NUMBER),
            amount=amount,
            individual_identification=_field(
                text, _ED_INDIVIDUAL_IDENTIFICATION
            ),
            individual_name=_field(text, _ED_INDIVIDUAL_NAME),
            discretionary_data=_field(text, _ED_DISCRETIONARY_DATA),
            addenda_indicator=addenda_indicator,
            trace_number=trace_number,
            addenda=tuple(addenda),
        ),
        cursor,
    )


def _parse_batch(
    records: Sequence[NachaRecord], cursor: int
) -> tuple[NachaBatch, int]:
    """Read a ``5`` header, its entries, and the ``8`` trailer that closes it."""
    header = records[cursor]
    context = f"record {header.line_number} (5 batch header)"
    text = header.text

    service_class = _required_field(
        text, _BH_SERVICE_CLASS, "the service class code", context=context
    )
    if service_class not in NACHA_SERVICE_CLASS_CODES:
        raise NachaMalformedFileError(
            f"{context}: service class code {service_class!r} is not one this "
            f"parser recognises ({', '.join(sorted(NACHA_SERVICE_CLASS_CODES))}). "
            "The service class governs which of the two money totals may be "
            "non-zero, so a code with no known meaning leaves the batch's own "
            "trailer uninterpretable"
        )
    standard_entry_class = _required_field(
        text, _BH_STANDARD_ENTRY_CLASS, "the standard entry class code", context=context
    )

    cursor += 1
    entries: list[NachaEntry] = []
    addenda_count = 0
    while cursor < len(records) and records[cursor].code == NACHA_ENTRY_DETAIL:
        entry, cursor = _parse_entry(records, cursor)
        entries.append(entry)
        addenda_count += len(entry.addenda)

    if cursor >= len(records):
        raise NachaMalformedFileError(
            f"{context}: the batch is never closed by an "
            f"{NACHA_BATCH_CONTROL} batch control record.  A batch that ends "
            "without one may have been truncated in carriage, and the four "
            "totals that would have detected it are the ones that are missing"
        )

    trailer = records[cursor]
    if trailer.code != NACHA_BATCH_CONTROL:
        raise NachaMalformedFileError(
            f"record {trailer.line_number}: expected a "
            f"{NACHA_ENTRY_DETAIL} entry detail or the "
            f"{NACHA_BATCH_CONTROL} batch control that closes the batch opened "
            f"at record {header.line_number}, and found record code "
            f"{trailer.code!r}"
        )

    trailer_context = f"record {trailer.line_number} (8 batch control)"
    trailer_service_class = _required_field(
        trailer.text, _BC_SERVICE_CLASS, "the service class code", context=trailer_context
    )
    if trailer_service_class != service_class:
        # Refused rather than reported, unlike the service-class-against-totals
        # check, and for a different reason.  That check compares a declaration
        # against the arithmetic and can say which one is wrong.  This one has
        # two declarations of the same quantity and nothing to break the tie,
        # so there is no service class to check the totals against at all.
        raise NachaMalformedFileError(
            f"{trailer_context}: the batch control states service class "
            f"{trailer_service_class!r} and the batch header at record "
            f"{header.line_number} states {service_class!r}.  The service "
            "class governs which totals may be non-zero, so a batch whose two "
            "records disagree about it cannot be checked against either"
        )

    control_total = _check_batch_control(
        service_class=service_class,
        entries=entries,
        addenda_count=addenda_count,
        declared_entry_addenda_count=_parse_count(
            _required_field(
                trailer.text,
                _BC_ENTRY_ADDENDA_COUNT,
                "the entry/addenda count",
                context=trailer_context,
            ),
            context=trailer_context,
            name="the entry/addenda count",
        ),
        declared_entry_hash=_parse_count(
            _required_field(
                trailer.text, _BC_ENTRY_HASH, "the entry hash", context=trailer_context
            ),
            context=trailer_context,
            name="the entry hash",
        ),
        declared_debits=_parse_amount(
            _required_field(
                trailer.text,
                _BC_TOTAL_DEBITS,
                "the total debit entry dollar amount",
                context=trailer_context,
            ),
            context=trailer_context,
            name="the total debit entry dollar amount",
        ),
        declared_credits=_parse_amount(
            _required_field(
                trailer.text,
                _BC_TOTAL_CREDITS,
                "the total credit entry dollar amount",
                context=trailer_context,
            ),
            context=trailer_context,
            name="the total credit entry dollar amount",
        ),
    )

    return (
        NachaBatch(
            line_number=header.line_number,
            service_class=service_class,
            company_name=_field(text, _BH_COMPANY_NAME),
            company_identification=_field(text, _BH_COMPANY_IDENTIFICATION),
            standard_entry_class=standard_entry_class,
            entry_description=_field(text, _BH_ENTRY_DESCRIPTION),
            descriptive_date=_field(text, _BH_DESCRIPTIVE_DATE),
            effective_entry_date=_field(text, _BH_EFFECTIVE_ENTRY_DATE),
            settlement_date=_field(text, _BH_SETTLEMENT_DATE),
            originator_status=_field(text, _BH_ORIGINATOR_STATUS),
            originating_dfi=_field(text, _BH_ORIGINATING_DFI),
            batch_number=_field(text, _BH_BATCH_NUMBER),
            entries=tuple(entries),
            control_total=control_total,
        ),
        cursor + 1,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _decode(data: "bytes | bytearray | str") -> str:
    """Turn the input into text, or refuse.

    Bytes are decoded as UTF-8 with no fallback and no error handler, for the
    reason :func:`~services.financial.bai2._decode` gives at greater length: a
    fallback succeeds on every input, and the mojibake it produces is
    indistinguishable downstream from a name the originator actually sent.

    NACHA is stricter about this than its siblings, and the strictness is worth
    naming.  Every field in the format is a fixed number of *characters*, and
    every offset in this module is a character offset.  A file carrying a
    multi-byte sequence has more bytes than characters, so the two agree only
    while the content is ASCII — which conformant content is, the format
    permitting nothing else.  Decoding as UTF-8 keeps the character count
    right; decoding as latin-1 would keep it right too but would silently
    accept a file the format does not allow.
    """
    if isinstance(data, str):
        return data
    if not isinstance(data, (bytes, bytearray)):
        raise NachaMalformedFileError(
            f"parse_nacha takes bytes or str, got {type(data).__name__}"
        )
    if len(data) > NACHA_MAX_FILE_BYTES:
        raise NachaMalformedFileError(
            f"the file is {len(data)} bytes, over the "
            f"{NACHA_MAX_FILE_BYTES}-byte ceiling for an ACH file"
        )
    try:
        return bytes(data).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise NachaMalformedFileError(
            f"the file is not valid UTF-8: {exc}.  It is refused rather than "
            "decoded with a fallback, because a fallback succeeds on every "
            "input and turns unreadable bytes into plausible-looking text that "
            "nothing downstream can tell from what the originator sent"
        ) from exc


def parse_nacha(data: "bytes | bytearray | str") -> NachaFile:
    """Parse a NACHA ACH file.  Pure: no database, no network, no clock.

    There is no ``default_currency`` parameter, and its absence is a statement
    rather than an omission.  A domestic ACH entry settles in
    :data:`NACHA_CURRENCY` by definition; the amount field is ten digits with
    two implied decimals, which is to say it is already a count of cents.  A
    parameter would let a caller reinterpret those cents as some other
    currency's minor unit, which is a way of being wrong that the format itself
    forecloses.

    :raises NotANachaError: the content does not open with a ``1`` file header.
    :raises NachaMalformedFileError: the record structure is not conformant.
    :raises NachaMissingFieldError: a mandatory field is absent.
    :raises NachaAmountError: a figure is not a NACHA amount, or not representable.
    """
    text = _decode(data)
    records = _split_records(text)

    header = records[0]
    if header.code != NACHA_FILE_HEADER:
        raise NotANachaError(
            f"the file opens with record code {header.code!r}; a NACHA file "
            f"opens with a {NACHA_FILE_HEADER} file header"
        )

    context = f"record {header.line_number} (1 file header)"
    text_h = header.text

    record_size = _field(text_h, _FH_RECORD_SIZE)
    if record_size and record_size != NACHA_RECORD_SIZE:
        # Refused rather than obeyed.  A file that states a different record
        # size states that every offset in this module is wrong, and the fields
        # read at those offsets would still be strings and would still parse.
        raise NachaMalformedFileError(
            f"{context}: the file states a record size of {record_size!r}; "
            f"this parser reads {NACHA_RECORD_SIZE}-character records and a "
            "different size means every field offset is somewhere else, which "
            "would parse cleanly and mean something else"
        )

    blocking_factor = _field(text_h, _FH_BLOCKING_FACTOR)
    if blocking_factor and blocking_factor != f"{NACHA_BLOCKING_FACTOR:02d}":
        raise NachaMalformedFileError(
            f"{context}: the file states a blocking factor of "
            f"{blocking_factor!r}; this parser computes the block count at "
            f"{NACHA_BLOCKING_FACTOR} records to the block, and a different "
            "factor would make the file trailer's block count disagree for a "
            "reason that is not a fault in the file"
        )

    format_code = _field(text_h, _FH_FORMAT_CODE)
    if format_code and format_code != NACHA_FORMAT_CODE:
        raise NachaMalformedFileError(
            f"{context}: the file states format code {format_code!r}; this "
            f"parser reads format code {NACHA_FORMAT_CODE}, and a different "
            "format code is a different record layout"
        )

    cursor = 1
    batches: list[NachaBatch] = []
    while cursor < len(records) and records[cursor].code == NACHA_BATCH_HEADER:
        batch, cursor = _parse_batch(records, cursor)
        batches.append(batch)

    if cursor >= len(records):
        raise NachaMalformedFileError(
            f"{context}: the file is never closed by a {NACHA_FILE_CONTROL} "
            "file control record; a file that ends without one may have been "
            "truncated in carriage, and the six totals that would have "
            "detected it are the ones that are missing"
        )

    trailer = records[cursor]
    if trailer.code != NACHA_FILE_CONTROL:
        raise NachaMalformedFileError(
            f"record {trailer.line_number}: expected a {NACHA_BATCH_HEADER} "
            f"batch header or the {NACHA_FILE_CONTROL} file control, and found "
            f"record code {trailer.code!r}"
        )
    if trailer.is_filler:
        # A filler record opens with a ``9`` too, so position alone cannot tell
        # the file control from the padding that follows it — and where the
        # control is missing entirely, the first filler stands exactly where
        # the control should be.  Read as a control it parses: every field is
        # digits, so the batch count reads 999999, the hash 9999999999, and
        # both money totals $9,999,999,999.99.  The file then reports
        # ``unbalanced``, which is the wrong answer to the wrong question — it
        # names an arithmetic failure when the fault is a trailer that is not
        # there, and sends a reviewer to look for a discrepancy rather than for
        # the missing record.
        #
        # The shape settles it.  A conformant file control ends in thirty-nine
        # reserved positions that are blank, so no file control is ever
        # ninety-four ``9`` characters, and a record that is must be padding.
        raise NachaMalformedFileError(
            f"record {trailer.line_number}: the file is never closed by a "
            f"{NACHA_FILE_CONTROL} file control record — the record standing "
            "where one should be is filler.  A file that ends without a "
            "control may have been truncated in carriage, and the six totals "
            "that would have detected it are the ones that are missing"
        )

    # Everything after the file control must be filler.  A NACHA file is
    # blocked out to a multiple of ten records with lines of ninety-four ``9``
    # characters, so records *do* legitimately follow the trailer — which is
    # why this is a shape test rather than the flat refusal its siblings use.
    # What it still catches is a record with content appended after the
    # trailer, which is outside all six file totals and would enter a ledger
    # uncounted.
    for following in records[cursor + 1 :]:
        if not following.is_filler:
            raise NachaMalformedFileError(
                f"record {following.line_number}: record code "
                f"{following.code!r} follows the {NACHA_FILE_CONTROL} file "
                f"control at record {trailer.line_number} and is not a filler "
                "record.  The file control closes the file, so anything after "
                "it that is not padding sits outside every control total and "
                "would enter the ledger uncounted"
            )

    trailer_context = f"record {trailer.line_number} (9 file control)"

    def _count(span: tuple[int, int], name: str) -> int:
        return _parse_count(
            _required_field(trailer.text, span, name, context=trailer_context),
            context=trailer_context,
            name=name,
        )

    def _amount(span: tuple[int, int], name: str) -> Money:
        return _parse_amount(
            _required_field(trailer.text, span, name, context=trailer_context),
            context=trailer_context,
            name=name,
        )

    control_total = _check_file_control(
        batches=batches,
        declared_batch_count=_count(_FC_BATCH_COUNT, "the batch count"),
        declared_block_count=_count(_FC_BLOCK_COUNT, "the block count"),
        declared_entry_addenda_count=_count(
            _FC_ENTRY_ADDENDA_COUNT, "the entry/addenda count"
        ),
        declared_entry_hash=_count(_FC_ENTRY_HASH, "the entry hash"),
        declared_debits=_amount(
            _FC_TOTAL_DEBITS, "the total debit entry dollar amount in file"
        ),
        declared_credits=_amount(
            _FC_TOTAL_CREDITS, "the total credit entry dollar amount in file"
        ),
        # Filler included.  The block count is a property of the file's
        # physical carriage, and the filler is part of that carriage — it is
        # what makes the record count a multiple of the blocking factor in the
        # first place.  Excluding it would make the computed count disagree
        # with every conformant file.
        physical_record_count=len(records),
    )

    return NachaFile(
        immediate_destination=_field(text_h, _FH_IMMEDIATE_DESTINATION),
        immediate_origin=_field(text_h, _FH_IMMEDIATE_ORIGIN),
        creation_date=_field(text_h, _FH_CREATION_DATE),
        creation_time=_field(text_h, _FH_CREATION_TIME),
        file_id_modifier=_field(text_h, _FH_ID_MODIFIER),
        record_size=record_size,
        blocking_factor=blocking_factor,
        format_code=format_code,
        destination_name=_field(text_h, _FH_DESTINATION_NAME),
        origin_name=_field(text_h, _FH_ORIGIN_NAME),
        reference_code=_field(text_h, _FH_REFERENCE_CODE),
        batches=tuple(batches),
        control_total=control_total,
        physical_record_count=len(records),
    )
