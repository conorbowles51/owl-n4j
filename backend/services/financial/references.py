"""The reference a reviewer cites when disputing a single row.

Every figure this system publishes will eventually be argued about one line at
a time, and the argument needs a name for the line.  That name is ``ref_id``.
It appears in the table, in the PDF, in the CSV a reviewer marks up offline,
and in the transcript when someone reads it aloud.  Its whole value is that it
means the same thing in all four places, months apart, on a different machine.

This module computes it, and computes the ``content_hash`` it is built from.
Both columns already exist on ``FinancialTransaction`` and neither had a
producer; only tests populated them.  That mattered more than it looked,
because :func:`services.financial.duplicates.fingerprint_document` hashes the
sorted ``content_hash`` of a period's rows to build ``content_fingerprint`` --
the ``identical_reading`` rung that duplicates.py calls the one that earns the
module.  So the strongest duplicate rung was resting on a column nothing wrote.
The two are one job, and this is it.

Why the reference is derived from content
-----------------------------------------

The obvious alternative is positional: document plus row number, the way a
lawyer cites "Ex. 14, line 37".  It is more legible and it survives a
re-extraction, which is what V1's CSV notes upload needed.  It is also
impossible here, and the schema is what makes it impossible rather than any
opinion about citation.

The ledger is append-only.  A row that is re-read is not overwritten; it gains
``ledger_status = 'superseded'`` and a ``superseded_by_id`` pointing at its
replacement, and both rows stay in the table.  ``ref_id`` carries
``UniqueConstraint("case_id", "ref_id")``.  A positional reference computed
from a stable document identity would hand the old row and its replacement the
same string, and the insert would fail.  Computing it from the document's
surrogate id instead would avoid the collision by making the reference change
on every re-ingestion, which defeats the only reason to want it positional.
Content-derived references are the arrangement the existing constraints admit.

The behaviour that falls out of it is also the behaviour worth having.  A row
that was read the same way twice keeps its reference across a re-extraction,
because nothing it is made of changed.  A row whose figure was corrected gets a
new one.  So an offline note orphans exactly when the reading beneath it moved
-- which is the moment a person should be asked to look again, not the moment
to quietly re-attach their note to a different number.

Why not V1's form
-----------------

V1 generated ``uuid.uuid4().hex[:8].upper()`` and retried on collision against
the ids already stored (``7dbbe46``, ``neo4j_service.ensure_transaction_ref_ids``),
assigned lazily the first time a case's transactions were read.  Three
consequences, none of them survivable here.  It is random, so re-importing the
same evidence into a clean database produces different references and a report
generated last quarter cites rows that no longer exist under those names.  It
is order-dependent, so which row got which reference depended on what order the
database happened to return unlabelled nodes in.  And it is created by a read,
so two readers racing could both assign.  ``FinancialTransaction.ref_id`` is
commented "regenerated identically"; V1's form cannot do that, so restoring the
column does not mean restoring its implementation.

What the document component is
------------------------------

The reference is a digest over the document the row was read from and the row
itself.  The document part is ``sha256_at_ingestion`` -- the bytes of the file
-- and not ``content_fingerprint``, because the fingerprint covers every row in
the document, so correcting one row would change the reference of all of them.
The file's bytes never change, so the document part is fixed for the life of
the exhibit.

Two scans of the same statement are two different files and therefore two sets
of references.  That is right: they are two exhibits, and the duplicate cascade
supersedes one of them.  A citation into the superseded copy still resolves,
because superseding hides and does not delete.

Occurrence, not row number
--------------------------

Two rows in one document can be genuinely identical -- the same fifty dollars
withdrawn from the same machine twice on the same day, described the same way.
Their readings are equal, so their digests would be equal, and
``UniqueConstraint("source_document_id", "content_hash")`` would reject the
second.  Something must distinguish them.

The distinguishing field is an occurrence index: among the rows of this
document whose reading is identical, this is the n-th.  Not ``row_index``,
which would be simpler and is wrong, because a re-extraction that recovers a
row missed earlier shifts the row number of everything below it and would
change the reference of rows that nobody re-read.  Occurrence only moves when
an identical row is added or removed, which is the only case where the rows
were never distinguishable to begin with.

What counts as the reading
--------------------------

The canonical form covers what the document was read to *say*: the currency,
the magnitude, the direction, the four dates as printed, the running balance
beside the row, and the four text fields.  It excludes everything the system
decided *about* the reading -- ``ordering_date`` and its source, which are a
choice among the four dates; ``proof_class`` and ``extraction_layer``, which
grade the reading; ``ledger_status``; and every surrogate id.  A row found by
two different parsers at two different layers is one reading if the fields
agree, and re-grading it later must not rename it.

Text is normalised to NFC and its internal whitespace collapsed, so that a
parser upgrade which only changes spacing does not orphan a reviewer's notes.
Case is *not* folded: "PAYMENT TO SMITH" and "Payment to Smith" are different
things printed on a page, and this module is not entitled to decide otherwise.
An absent text field and an empty one are treated as identical, because that
distinction is an artefact of which parser ran and never of what the document
said.  Fields sit in fixed positions separated by a control character, so an
absent value in one slot can never be confused with an absent value in another.

The alphabet
------------

The reference is Crockford base32, which excludes I, L, O and U, so the
characters a person most often mistakes for one another are not both in play.
:func:`normalise` folds the residual confusions on the way back in -- I and L
read as 1, O reads as 0, case is ignored and hyphens are optional -- so a
reference typed from a printed exhibit into a spreadsheet matches the row it
came from.  Twelve significant characters is sixty bits: for a case of a
million rows the chance that any two references collide is about four in ten
million, and the unique constraint turns even that into a loud failure rather
than a silent one.

Crockford's optional check symbol was considered and dropped.  It would let the
system say "you mistyped this" rather than "no such row", which is a genuinely
better message, but it costs a thirty-seventh symbol drawn from ``*~$=U`` --
characters that cannot be read aloud in a deposition, which is the setting the
whole reference exists for.

    >>> reading = RowReading(
    ...     currency="USD",
    ...     amount_minor=2500_00,
    ...     direction=TransactionDirection.debit,
    ...     transaction_date=date(2026, 3, 14),
    ...     description="  WIRE   TO  MEYER  ",
    ... )
    >>> canonical_form(reading, occurrence=0) == canonical_form(
    ...     replace(reading, description="WIRE TO MEYER"), occurrence=0
    ... )
    True
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, replace  # noqa: F401  (replace: doctest)
from datetime import date
from typing import Iterable, Optional, Sequence

from postgres.models.enums import TransactionDirection


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class RowReferenceError(Exception):
    """Base class for every failure in this module.

    Named for the row rather than for the module, because ``ReferenceError`` is
    a Python builtin: a caller who wrote ``except ReferenceError`` after a
    star-import would be catching whichever of the two the import order left
    bound, and would be none the wiser.
    """


class MalformedReadingError(RowReferenceError):
    """A row reading cannot be canonicalised as given."""


class MalformedReferenceError(RowReferenceError):
    """A string cannot be read as a reference."""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Field separator inside one row's canonical form.  Matches the discipline in
#: :mod:`services.financial.duplicates`, which uses the same control character
#: for the same reason: it cannot occur in text a PDF reader produced.
_SEP = "\x1f"

#: Crockford base32.  I, L, O and U are absent by construction.
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

#: Confusions Crockford defines as decodable rather than invalid.
_FOLD = {"I": "1", "L": "1", "O": "0"}

#: Characters carried for legibility that mean nothing on the way back in.
_ORNAMENT = re.compile(r"[\s\-]+")

_WHITESPACE = re.compile(r"\s+")
_CURRENCY = re.compile(r"^[A-Z]{3}$")

#: Significant characters in a reference, before grouping.  Sixty bits.
REFERENCE_LENGTH = 12

#: Characters per group, for reading aloud and for typing without losing place.
_GROUP = 4

#: What kind of thing the reference names.  Present so that a reference found
#: loose in a document says what table to look in.
REFERENCE_PREFIX = "TX"


# ---------------------------------------------------------------------------
# The reading
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RowReading:
    """One ledger row reduced to what the document was read to say.

    Deliberately not the ORM object, for the reason
    :class:`services.financial.quarantine.RowObservation` is not either: this
    has to be testable without a database, and a narrow record makes the field
    set an explicit decision rather than whatever the model happens to carry.

    ``amount_minor`` is a magnitude and must not be negative; sign lives in
    ``direction``.  That mirrors ``ck_financial_transactions_amount_non_negative``
    so a reading that could never be stored cannot be hashed either.
    """

    currency: str
    amount_minor: int
    direction: TransactionDirection

    transaction_date: Optional[date] = None
    posted_date: Optional[date] = None
    value_date: Optional[date] = None
    effective_date: Optional[date] = None

    running_balance_minor: Optional[int] = None

    description: Optional[str] = None
    counterparty_raw: Optional[str] = None
    transaction_type: Optional[str] = None
    bank_reference: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.direction, TransactionDirection):
            raise MalformedReadingError(
                f"direction {self.direction!r} is neither credit nor debit"
            )
        if isinstance(self.amount_minor, bool) or not isinstance(
            self.amount_minor, int
        ):
            raise MalformedReadingError(
                f"amount_minor is {type(self.amount_minor).__name__}; a reading "
                "is hashed exactly and cannot go through a float"
            )
        if self.amount_minor < 0:
            raise MalformedReadingError(
                "amount_minor is negative; magnitude lives in the amount and "
                "sign lives in the direction"
            )
        if isinstance(self.running_balance_minor, bool) or not isinstance(
            self.running_balance_minor, (int, type(None))
        ):
            raise MalformedReadingError(
                "running_balance_minor is "
                f"{type(self.running_balance_minor).__name__}; a reading is "
                "hashed exactly and cannot go through a float"
            )
        if not isinstance(self.currency, str) or not _CURRENCY.match(self.currency):
            raise MalformedReadingError(
                f"currency {self.currency!r} is not a three-letter code; "
                "normalise it before hashing so that two spellings of one "
                "currency cannot produce two references"
            )


# ---------------------------------------------------------------------------
# Canonicalisation
# ---------------------------------------------------------------------------


def _text(value: Optional[str]) -> str:
    """One text field, reduced to what it says.

    NFC first, so two encodings of one accented character are one reading.
    Then internal whitespace collapses and the ends are stripped, so a parser
    that changes only its spacing does not rename every row it touched.  Case
    survives untouched: it is on the page.
    """
    if value is None:
        return ""
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFC", value)).strip()


def _day(value: Optional[date]) -> str:
    return value.isoformat() if value is not None else ""


def canonical_form(reading: RowReading, occurrence: int) -> str:
    """The exact string a row's digest is taken over.

    Every field occupies a fixed position, so an absent date in one slot can
    never be mistaken for an absent date in another -- the same reasoning
    :func:`services.financial.duplicates._period_signature` applies to period
    bounds, and for the same reason.
    """
    if isinstance(occurrence, bool) or not isinstance(occurrence, int):
        raise MalformedReadingError(
            f"occurrence is {type(occurrence).__name__}; it counts identical "
            "readings and must be an integer"
        )
    if occurrence < 0:
        raise MalformedReadingError("occurrence is negative")

    return _SEP.join(
        (
            reading.currency,
            str(reading.amount_minor),
            reading.direction.value,
            _day(reading.transaction_date),
            _day(reading.posted_date),
            _day(reading.value_date),
            _day(reading.effective_date),
            ""
            if reading.running_balance_minor is None
            else str(reading.running_balance_minor),
            _text(reading.description),
            _text(reading.counterparty_raw),
            _text(reading.transaction_type),
            _text(reading.bank_reference),
            str(occurrence),
        )
    )


def content_hash(reading: RowReading, occurrence: int = 0) -> str:
    """The value for ``FinancialTransaction.content_hash``: 64 hex characters.

    Occurrence defaults to zero because most rows are the only one of their
    kind in their document.  Where that is not true,
    :func:`document_content_hashes` assigns the indices; passing them by hand
    row by row is how two rows end up sharing one.
    """
    return hashlib.sha256(
        canonical_form(reading, occurrence).encode("utf-8")
    ).hexdigest()


def document_content_hashes(readings: Sequence[RowReading]) -> list[str]:
    """Content hashes for a whole document, occurrences assigned.

    Returned in the order given, which is document order, so the caller can zip
    them back onto its rows.  Occurrence is counted over the canonical form
    rather than over the whole hash, so counting costs one digest per row and
    not two.
    """
    seen: dict[str, int] = {}
    hashes: list[str] = []
    for reading in readings:
        form = canonical_form(reading, 0)
        occurrence = seen.get(form, 0)
        seen[form] = occurrence + 1
        hashes.append(
            hashlib.sha256(
                canonical_form(reading, occurrence).encode("utf-8")
            ).hexdigest()
        )
    return hashes


# ---------------------------------------------------------------------------
# The reference
# ---------------------------------------------------------------------------


def _encode(value: int) -> str:
    characters = []
    for _ in range(REFERENCE_LENGTH):
        value, remainder = divmod(value, 32)
        characters.append(_ALPHABET[remainder])
    return "".join(reversed(characters))


def _group(significant: str) -> str:
    groups = [
        significant[start : start + _GROUP]
        for start in range(0, len(significant), _GROUP)
    ]
    return "-".join((REFERENCE_PREFIX, *groups))


def ref_id(document_sha256: str, row_content_hash: str) -> str:
    """The citable reference for one row of one document.

    ``document_sha256`` is the file's bytes as recorded in
    ``FinancialSourceDocument.sha256_at_ingestion``, and never the document's
    surrogate id, so that re-ingesting the same file reproduces the same
    references rather than a fresh set.
    """
    document = _hex64(document_sha256, "document_sha256")
    row = _hex64(row_content_hash, "content_hash")

    digest = hashlib.sha256(_SEP.join((document, row)).encode("ascii")).digest()
    # Sixty bits, most significant first: the top of a sha256 digest is as good
    # as any other part of it, and taking a fixed slice keeps this reproducible
    # across interpreters in a way that hash() never is.
    return _group(_encode(int.from_bytes(digest[:8], "big") >> 4))


def _hex64(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise MalformedReferenceError(
            f"{field} is {type(value).__name__}, not a hex digest"
        )
    lowered = value.strip().lower()
    if len(lowered) != 64 or any(c not in "0123456789abcdef" for c in lowered):
        raise MalformedReferenceError(
            f"{field} is not a 64-character sha256 hex digest: {value!r}"
        )
    return lowered


def document_ref_ids(
    document_sha256: str, readings: Sequence[RowReading]
) -> list[str]:
    """References for a whole document, in document order."""
    return [
        ref_id(document_sha256, row_hash)
        for row_hash in document_content_hashes(readings)
    ]


def normalise(text: str) -> str:
    """Read a reference back in from wherever a person typed it.

    Accepts it with or without the prefix and the hyphens, in any case, and
    folds the confusions Crockford defines as decodable: I and L are 1, O is 0.
    U is not among them -- Crockford omits it from the alphabet entirely, so a
    U in a reference is a character that was never printed and is reported
    rather than guessed at.

    Returns the reference in its canonical printed form, so that a CSV column
    of hand-typed references can be compared against stored ones directly.
    """
    if not isinstance(text, str):
        raise MalformedReferenceError(
            f"a reference is text, not {type(text).__name__}"
        )

    stripped = _ORNAMENT.sub("", text).upper()
    if stripped.startswith(REFERENCE_PREFIX):
        stripped = stripped[len(REFERENCE_PREFIX) :]

    folded = "".join(_FOLD.get(character, character) for character in stripped)

    if len(folded) != REFERENCE_LENGTH:
        raise MalformedReferenceError(
            f"a reference has {REFERENCE_LENGTH} characters after its prefix; "
            f"{text!r} has {len(folded)}"
        )
    unknown = sorted({c for c in folded if c not in _ALPHABET})
    if unknown:
        raise MalformedReferenceError(
            f"{text!r} contains {', '.join(unknown)}, which the reference "
            "alphabet does not use"
        )
    return _group(folded)


def is_reference(text: str) -> bool:
    """Whether ``text`` reads as a reference, without raising if it does not.

    For sorting a column of a reviewer's CSV into rows to look up and rows to
    report back, which is a question about the string and not an error yet.
    """
    try:
        normalise(text)
    except RowReferenceError:
        return False
    return True

