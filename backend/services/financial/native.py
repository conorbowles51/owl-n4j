"""Layer 0: the four native parsers, read as ledger rows that carry their layer.

The four parsers in this package — :mod:`~services.financial.camt053`,
:mod:`~services.financial.bai2`, :mod:`~services.financial.mt940` and
:mod:`~services.financial.nacha` — each read one bank format exactly.  None of
them knows anything about the ledger, and that separation is deliberate: a
parser that also decided what a ledger row looks like would have to be rewritten
whenever either the format or the schema moved.  This module is the seam.  It
takes a file, works out which of the four it is, parses it, and turns the result
into :class:`~services.financial.references.RowReading` values with the
provenance the schema asks for: ``extraction_layer``, ``parser_name`` and
``parser_version`` on the document, an ordering date and its
:class:`~postgres.models.enums.DateSource` on every row.

``extraction_layer`` is :attr:`~postgres.models.enums.ExtractionLayer.native`
for everything this module produces, and that is not a formality.  `13` §2.1
grants ``native_with_control_totals`` the strongest proof class available, and
it does so because the format itself mandates the totals that make the
arithmetic a guarantee rather than a hope.  Recording the layer is what lets a
later reader tell a figure that was *read* from a figure that was *inferred*,
months after both have become numbers in the same table.

Four decisions here are not obvious, so each is argued rather than asserted.

Why the locator is ``not_positional``
-------------------------------------

Every row this module emits carries a locator whose kind is
:attr:`~postgres.models.enums.LocatorKind.not_positional`, taken from the
parser that produced it.  That looks like an admission of failure next to a
page-and-rectangle locator from a PDF, and it is the opposite.  A camt.053
entry has no page, because a camt.053 file has no pages.  There is no
coordinate to record, no rectangle a reviewer could be shown, and no honest way
to manufacture one.  ``not_positional`` says precisely that, and its docstring
names a camt.053 entry as its example.  The alternative —
:attr:`~postgres.models.enums.LocatorKind.unlocated` — means a reader looked
for a position and failed, which would be a false statement about a format
where there was never anything to look for.

Why the century window is required
----------------------------------

BAI2, MT940 and NACHA all write years as two digits, and none of the three
carries a four-digit year anywhere in the file.  ``FinancialTransaction``
requires ``ordering_date``, and there is no way to get from ``89`` to a year
without an assumption from outside the document.

So the assumption is taken from outside the document, explicitly, by the
caller, following the precedent :func:`~services.financial.bai2.parse_bai2`
already set with ``default_currency``: where a format leaves something
genuinely undetermined, the reader refuses to invent it and requires the caller
to say.  :class:`CenturyWindow` is that parameter.  Its invariant — the two
years may differ by at most 99 — is what makes resolution a *derivation*
rather than a guess: within a span that narrow, exactly one century can
produce any given two-digit year, so the answer is computed arithmetically and
there is no rule to argue with.

A wider default window would have been friendlier and would have been wrong.
"Nineteen-seventy through twenty-sixty-nine" is a convention, not a fact, and a
convention buried in a library is exactly the kind of assumption that is
invisible until a 1998 statement in a matter about the 1990s reads as 2098.
Making the caller state the engagement's date range costs one argument and
turns an invisible guess into a recorded one.

Why unmapped rows are counted rather than dropped
-------------------------------------------------

Not every row a parser reads can become a ledger row, and some must not.  A
camt.053 entry that is not ``BOOK`` is pending, not money that moved.  A NACHA
prenotification is a test that money will *never* move under it.  A BAI2
transaction whose type code is not in the direction table has no side to land
on, and ``direction`` is ``NOT NULL``.

The tempting implementation skips these and returns the rows that worked.  It
is unsafe for one reason: it makes "this file had forty entries and produced
thirty-eight rows" indistinguishable from "this file had thirty-eight
entries", and the difference is the whole question when a total is disputed.
So every row the parser produced appears in exactly one of :attr:`rows` or
:attr:`unmapped`, with ``row_index`` running across both, and
:meth:`NativeReading.check_partition` states the invariant so a test can hold
it.  A reviewer asking why a number is smaller than the file gets a list of
reasons instead of silence.

Why the format is sniffed by exclusive claim
--------------------------------------------

The obvious way to detect the format is to try each parser in turn and keep the
first that does not raise.  That makes the answer depend on the order the
parsers happen to be listed in, which is a property of this file rather than of
the evidence.  Instead all four signature predicates are evaluated and exactly
one must claim the input: none is :class:`UnrecognisedFormatError`, more than
one is :class:`AmbiguousFormatError`.  A file that two formats claim is a file
nobody should be quietly assigning to one of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Optional, Sequence

from postgres.models.enums import (
    DateSource,
    ExtractionLayer,
    ReconciliationStatus,
    TransactionDirection,
)
from services.financial.bai2 import (
    BAI2_FILE_HEADER,
    BAI2_LOCATOR,
    Bai2File,
    parse_bai2,
)
from services.financial.camt053 import (
    CAMT053_LOCATOR,
    Camt053Document,
    parse_camt053,
)
from services.financial.locators import Locator
from services.financial.mt940 import MT940_LOCATOR, Mt940File, parse_mt940
from services.financial.nacha import (
    NACHA_LOCATOR,
    NACHA_RECORD_LENGTH,
    NachaFile,
    parse_nacha,
)
from services.financial.proof_class import ProofClass, SourceShape
from services.financial.references import (
    MalformedReadingError,
    RowReading,
    document_content_hashes,
    document_ref_ids,
)
from services.financial.version import UNVERIFIED, code_fingerprint_detail


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: How many bytes of a file are examined to decide what format it is.  Every
#: signature this module recognises is in the first record or the first tag, so
#: a small prefix is enough and a large file is not read twice.
SNIFF_BYTES: int = 4096

#: The widest span a :class:`CenturyWindow` may cover.  Ninety-nine years is
#: not a policy choice, it is the largest span over which a two-digit year
#: still names exactly one calendar year.  At one hundred, ``89`` means both
#: 1989 and 2089 and nothing in the file distinguishes them.
CENTURY_WINDOW_MAX_SPAN_YEARS: int = 99

#: Length of the fingerprint kept in ``parser_version``.  Matches
#: :data:`services.financial.version._FINGERPRINT_CHARS`, and the resulting
#: value — at most ``camt053+`` plus sixteen hex characters — fits the
#: ``String(32)`` the column declares with room to spare.
PARSER_FINGERPRINT_CHARS: int = 16


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


class NativeError(Exception):
    """Base for every refusal in this module."""


class UnrecognisedFormatError(NativeError):
    """No native parser claims this input."""


class AmbiguousFormatError(NativeError):
    """More than one native parser claims this input.

    Raised rather than resolved by precedence.  A file that looks like two
    formats is a file whose format is genuinely in doubt, and picking one by
    the order they happen to be tried records a confident answer to a question
    that was not settled.
    """


class CenturyWindowError(NativeError):
    """A century window was described that cannot resolve a two-digit year."""


class DateResolutionError(NativeError):
    """A two-digit year has no reading inside the window it was given.

    Raised rather than recorded as an unmapped row, and the asymmetry is
    deliberate.  An unmappable row is a property of the document; a date that
    will not resolve is a property of the *window*, which is to say of the
    caller's assumption.  A wrong window is wrong for every row in the file, so
    recording it row by row would turn one fixable mistake into a file that
    parsed successfully and produced nothing.  Widening a window costs one
    argument; a silently empty ledger costs a case.
    """


# ---------------------------------------------------------------------------
# Formats
# ---------------------------------------------------------------------------


class NativeFormat(str, Enum):
    """The four formats read natively.

    The value doubles as the module name inside this package, which is what
    lets :func:`parser_version` fingerprint the right file without a second
    table mapping one to the other.
    """

    camt053 = "camt053"
    bai2 = "bai2"
    mt940 = "mt940"
    nacha = "nacha"


#: The locator every row of a given format carries, taken from the parser that
#: produced it rather than restated, so that changing one changes both.
NATIVE_LOCATORS: dict[NativeFormat, Locator] = {
    NativeFormat.camt053: CAMT053_LOCATOR,
    NativeFormat.bai2: BAI2_LOCATOR,
    NativeFormat.mt940: MT940_LOCATOR,
    NativeFormat.nacha: NACHA_LOCATOR,
}


# ---------------------------------------------------------------------------
# The century window
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CenturyWindow:
    """The span of years a two-digit year in this evidence may fall in.

    Supplied by the caller because the document does not contain it.  The two
    bounds are ordinary dates rather than years so that a caller can pass the
    engagement's date range directly instead of translating it, and so that the
    intent — "this matter concerns this period" — survives into the code.

    The invariant enforced here is the point of the class.  Because the bounds
    may span at most :data:`CENTURY_WINDOW_MAX_SPAN_YEARS` years, at most one
    century can produce any two-digit year, so :meth:`resolve` computes the
    answer instead of searching for it and there is no case where two readings
    both fit and one has to be preferred.

    The window constrains the *year*, not the date.  A window of 2019-06-01 to
    2024-05-31 resolves ``19`` to 2019 and accepts 2019-01-04, which is outside
    the window but inside its first year.  Requiring the resolved date to fall
    within the bounds would make a statement's opening entries unreadable
    whenever an engagement started mid-year, which is most of them.
    """

    earliest: date
    latest: date

    def __post_init__(self) -> None:
        for name, value in (("earliest", self.earliest), ("latest", self.latest)):
            # datetime subclasses date, so an isinstance check against date
            # alone lets a timestamp through.  A timestamp carries a zone or
            # pointedly does not, and neither is a thing this window has an
            # opinion about; taking one silently would hide the question.
            if isinstance(value, datetime) or not isinstance(value, date):
                raise CenturyWindowError(
                    f"{name} is {type(value).__name__}; a century window is "
                    "bounded by calendar dates, and a timestamp raises a "
                    "timezone question this has no way to answer"
                )
        if self.latest < self.earliest:
            raise CenturyWindowError(
                f"latest {self.latest.isoformat()} precedes earliest "
                f"{self.earliest.isoformat()}"
            )
        span = self.latest.year - self.earliest.year
        if span > CENTURY_WINDOW_MAX_SPAN_YEARS:
            raise CenturyWindowError(
                f"window spans {span} years ({self.earliest.year}–"
                f"{self.latest.year}); at more than "
                f"{CENTURY_WINDOW_MAX_SPAN_YEARS} a two-digit year names two "
                "calendar years and nothing in the document says which"
            )

    @property
    def span_years(self) -> int:
        """How many years the window covers, counting both endpoints' years."""
        return self.latest.year - self.earliest.year

    def resolve_year(self, year_of_century: int, *, context: str) -> int:
        """The single four-digit year inside the window ending in these two digits.

        Computed rather than searched.  Take the century of the lower bound,
        graft the two digits on, and step forward one century if that lands
        before the window.  The invariant guarantees a second step would
        overshoot, so the result either sits inside the window or there is no
        answer at all.
        """
        if not 0 <= year_of_century <= 99:
            raise DateResolutionError(
                f"{context}: {year_of_century} is not a two-digit year"
            )
        low = self.earliest.year
        year = low - (low % 100) + year_of_century
        if year < low:
            year += 100
        if year > self.latest.year:
            raise DateResolutionError(
                f"{context}: two-digit year {year_of_century:02d} has no "
                f"reading between {low} and {self.latest.year}; widen the "
                "century window if this evidence really is from outside the "
                "engagement's period"
            )
        return year

    def resolve(self, year_of_century: int, month: int, day: int, *, context: str) -> date:
        """One ``YY``, ``MM``, ``DD`` as a calendar date inside the window."""
        year = self.resolve_year(year_of_century, context=context)
        try:
            return date(year, month, day)
        except ValueError as exc:
            # 000229 is the case that matters: valid in a window resolving to
            # 2000, impossible in one resolving to 1900.  The window is what
            # makes it right or wrong, so the window is named in the message.
            raise DateResolutionError(
                f"{context}: {year:04d}-{month:02d}-{day:02d} is not a date ({exc})"
            ) from exc

    def resolve_yymmdd(self, text: str, *, context: str) -> date:
        """A six-digit ``YYMMDD`` as a calendar date inside the window."""
        cleaned = (text or "").strip()
        if len(cleaned) != 6 or not cleaned.isdigit():
            raise DateResolutionError(
                f"{context}: {text!r} is not a six-digit YYMMDD date"
            )
        return self.resolve(
            int(cleaned[0:2]), int(cleaned[2:4]), int(cleaned[4:6]), context=context
        )


def resolve_mmdd_near(text: str, near: date, *, context: str) -> date:
    """A four-digit ``MMDD`` as the calendar date closest to ``near``.

    MT940's ``:61:`` entry date is a month and a day with no year at all, so
    unlike a two-digit year it cannot be resolved from a window — it has to be
    read against the value date on the same line.

    Deriving it is defensible where deriving a century is not, and the
    difference is the size of the error.  A century guess is wrong by a hundred
    years when it is wrong.  This one chooses among the same month-day in the
    year before, the year of, and the year after the value date, so the worst
    available answer is off by about a day-of-year — and nothing sequences on
    it, because the value date is what orders the ledger.  The entry date is
    carried as ``posted_date`` for the record and for nothing else.

    Ties go to the earlier date.  A tie needs the two candidates to be
    equidistant from the value date, which takes a gap of a full 366 days, so
    the rule exists to make the function total rather than because it will be
    exercised.
    """
    cleaned = (text or "").strip()
    if len(cleaned) != 4 or not cleaned.isdigit():
        raise DateResolutionError(f"{context}: {text!r} is not a four-digit MMDD")
    month, day = int(cleaned[0:2]), int(cleaned[2:4])
    candidates: list[date] = []
    for year in (near.year - 1, near.year, near.year + 1):
        try:
            candidates.append(date(year, month, day))
        except ValueError:
            # 0229 in a common year: absent from that candidate and present in
            # the leap year beside it, which is the correct reading.
            continue
    if not candidates:
        raise DateResolutionError(
            f"{context}: {month:02d}-{day:02d} is not a date in "
            f"{near.year - 1}, {near.year} or {near.year + 1}"
        )
    return min(candidates, key=lambda value: (abs((value - near).days), value))


# ---------------------------------------------------------------------------
# Parser identity
# ---------------------------------------------------------------------------


def parser_version(fmt: NativeFormat) -> str:
    """The recorded version of one parser: its name and its own source digest.

    Deliberately narrower than :func:`services.financial.version.code_version`,
    which fingerprints the whole package.  The package-wide value is right for
    a run, because a run is the whole pipeline.  It is wrong for a parser: it
    would change the recorded version of the camt.053 reader every time the
    NACHA reader was touched, so two documents read by byte-identical code
    would carry different versions and the field would stop being evidence of
    anything.

    Falls back to ``{format}+unverified`` on the same reasoning
    :func:`~services.financial.version.code_version` gives for its own
    fallback: a deployment that cannot read its own source must still be able
    to record a document, and must still say that it could not.
    """
    try:
        digest = code_fingerprint_detail().get(f"{fmt.value}.py")
    except Exception:
        digest = None
    if not digest:
        return f"{fmt.value}+{UNVERIFIED}"
    return f"{fmt.value}+{digest[:PARSER_FINGERPRINT_CHARS]}"


def parser_name(fmt: NativeFormat) -> str:
    """The recorded name of one parser, qualified by the package that holds it."""
    return f"services.financial.{fmt.value}"


# ---------------------------------------------------------------------------
# Sniffing
# ---------------------------------------------------------------------------


def _sniff_text(data: bytes) -> str:
    """A decoded prefix of the input, good enough to recognise a signature.

    Byte-order marks are honoured because a camt.053 file written by a Windows
    tool is very often UTF-16 with one, and its whole signature is invisible if
    the bytes are read as Latin-1.  Everything else is decoded as UTF-8 with
    replacement: the four signatures are pure ASCII, so a mangled non-ASCII
    byte further along cannot change the answer, while raising on it would
    refuse a file over a character in a payee's name.
    """
    prefix = data[:SNIFF_BYTES]
    if prefix.startswith(b"\xef\xbb\xbf"):
        return prefix.decode("utf-8-sig", errors="replace")
    if prefix.startswith(b"\xff\xfe") or prefix.startswith(b"\xfe\xff"):
        # Trim to an even length so the decoder is not handed half a unit.
        even = prefix[: len(prefix) - (len(prefix) % 2)]
        return even.decode("utf-16", errors="replace")
    return prefix.decode("utf-8", errors="replace")


def _first_content_line(text: str) -> str:
    """The first line with anything on it, or the empty string."""
    for line in text.splitlines():
        if line.strip():
            return line
    return ""


def _claims_camt053(text: str, first: str) -> bool:
    """XML that says it is a bank-to-customer statement."""
    if not text.lstrip().startswith("<"):
        return False
    return "BkToCstmrStmt" in text or "camt.053" in text


def _claims_bai2(text: str, first: str) -> bool:
    """A BAI2 file header: record code ``01`` and the format's comma."""
    return first.startswith(f"{BAI2_FILE_HEADER},")


def _claims_nacha(text: str, first: str) -> bool:
    """A NACHA file header: record type ``1``, priority ``01``, full-width record.

    The width test is what separates this from a coincidence.  Every NACHA
    record is exactly ninety-four characters, and the file header is the first
    of them whether the file is written one record per line or as a single
    unbroken run of characters — in the unbroken case the "first line" is the
    whole file, which is longer still.  A line that begins ``101`` and is
    shorter than a record is not a NACHA file.
    """
    return first.startswith("101") and len(first.rstrip("\r\n")) >= NACHA_RECORD_LENGTH


def _claims_mt940(text: str, first: str) -> bool:
    """A SWIFT envelope, or a bare statement starting at its transaction reference."""
    if "{4:" in text or "{1:" in text:
        return True
    return any(line.startswith(":20:") for line in text.splitlines())


_CLAIMS = {
    NativeFormat.camt053: _claims_camt053,
    NativeFormat.bai2: _claims_bai2,
    NativeFormat.mt940: _claims_mt940,
    NativeFormat.nacha: _claims_nacha,
}


def sniff(data: bytes) -> tuple[NativeFormat, ...]:
    """Every native format that claims this input, in a stable order.

    Returns all claimants rather than the first, so that ambiguity is a visible
    result rather than something resolved by the order of a dictionary.
    """
    text = _sniff_text(bytes(data))
    first = _first_content_line(text)
    return tuple(fmt for fmt in NativeFormat if _CLAIMS[fmt](text, first))


def detect_format(data: bytes) -> NativeFormat:
    """The one native format that claims this input.

    Raises :class:`UnrecognisedFormatError` if none does and
    :class:`AmbiguousFormatError` if more than one does.
    """
    claimants = sniff(data)
    if not claimants:
        raise UnrecognisedFormatError(
            "no native parser claims this input; it is not camt.053, BAI2, "
            "MT940 or NACHA, and reading it needs a layer above zero"
        )
    if len(claimants) > 1:
        names = ", ".join(fmt.value for fmt in claimants)
        raise AmbiguousFormatError(
            f"{names} all claim this input; its format is genuinely in doubt "
            "and choosing one here would record a confident answer to an "
            "unsettled question"
        )
    return claimants[0]


# ---------------------------------------------------------------------------
# The result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NativeRow:
    """One parsed row, ready to become a ledger row, with where it came from."""

    row_index: int
    reading: RowReading
    locator: Locator
    account_key: Optional[str]
    ordering_date: date
    ordering_date_source: DateSource
    is_reversal: bool

    def __post_init__(self) -> None:
        if isinstance(self.ordering_date, datetime) or not isinstance(
            self.ordering_date, date
        ):
            raise MalformedReadingError(
                f"ordering_date is {type(self.ordering_date).__name__}; the "
                "column is a DATE and a timestamp would be silently truncated"
            )
        if not isinstance(self.ordering_date_source, DateSource):
            raise MalformedReadingError(
                f"ordering_date_source {self.ordering_date_source!r} is not a "
                "DateSource; the point of the field is that the choice was "
                "recorded rather than inferred"
            )


@dataclass(frozen=True, slots=True)
class UnmappedRow:
    """A row the parser read that did not become a ledger row, and why not.

    Covers both "cannot" and "must not", and does not distinguish them, because
    the consequence is identical: the row is in the file, it is not in the
    total, and a reviewer comparing the two is owed a reason in words.
    """

    row_index: int
    reason: str


@dataclass(frozen=True, slots=True)
class NativeReading:
    """One natively-parsed document: its rows, its provenance, and what it omitted."""

    format: NativeFormat
    parser_name: str
    parser_version: str
    source_shape: SourceShape
    reconciliation_status: ReconciliationStatus
    proof_class: ProofClass
    admissibility_reservations: tuple[str, ...]
    rows: tuple[NativeRow, ...]
    unmapped: tuple[UnmappedRow, ...]
    document: object

    #: Constant for every reading this module produces.  Declared as a field
    #: rather than a property so that it is present in the record itself, which
    #: is what gets written and what gets argued about.
    extraction_layer: ExtractionLayer = ExtractionLayer.native

    @property
    def readings(self) -> tuple[RowReading, ...]:
        """The rows as bare readings, in document order, for hashing."""
        return tuple(row.reading for row in self.rows)

    @property
    def row_count(self) -> int:
        """Rows that became ledger rows."""
        return len(self.rows)

    @property
    def parsed_row_count(self) -> int:
        """Rows the parser read, mapped and unmapped together."""
        return len(self.rows) + len(self.unmapped)

    def content_hashes(self) -> list[str]:
        """The content hash of every mapped row, with repeats numbered."""
        return document_content_hashes(self.readings)

    def ref_ids(self, document_sha256: str) -> list[str]:
        """The citable reference of every mapped row, under one document digest."""
        return document_ref_ids(document_sha256, self.readings)

    def check_partition(self) -> None:
        """Assert that mapped and unmapped rows partition the parsed rows exactly.

        Stated as a method rather than left to the tests because it is the
        invariant the module's third design decision rests on.  If the indices
        ever stop being a contiguous run with no repeats, a row has gone
        missing or been counted twice, and "the file had forty entries" has
        stopped being answerable from this object.
        """
        indices = sorted(
            [row.row_index for row in self.rows]
            + [row.row_index for row in self.unmapped]
        )
        if indices != list(range(len(indices))):
            raise NativeError(
                f"{self.format.value}: row indices {indices!r} are not the "
                f"contiguous run 0..{len(indices) - 1}; a parsed row is either "
                "missing from both lists or present in both"
            )


# ---------------------------------------------------------------------------
# Row construction
# ---------------------------------------------------------------------------


class _RowCollector:
    """Accumulates mapped and unmapped rows against one running index.

    The index is shared and advances once per row the parser produced,
    whichever list the row lands in.  That is what makes
    :meth:`NativeReading.check_partition` mean anything: a collector that
    numbered the two lists separately would satisfy no invariant worth
    checking.
    """

    __slots__ = ("_format", "_locator", "_rows", "_unmapped", "_index")

    def __init__(self, fmt: NativeFormat) -> None:
        self._format = fmt
        self._locator = NATIVE_LOCATORS[fmt]
        self._rows: list[NativeRow] = []
        self._unmapped: list[UnmappedRow] = []
        self._index = 0

    def skip(self, reason: str) -> None:
        self._unmapped.append(UnmappedRow(row_index=self._index, reason=reason))
        self._index += 1

    def add(
        self,
        *,
        account_key: Optional[str],
        ordering_date: date,
        ordering_date_source: DateSource,
        is_reversal: bool,
        **reading_fields: object,
    ) -> None:
        """Build one row, or record why the reading would not hold together.

        ``RowReading`` refuses a negative magnitude, a non-integer amount and a
        currency that is not three letters.  Those refusals are caught here and
        become unmapped rows carrying the real message, rather than being
        pre-empted by an ``abs()`` that would launder a parser defect into a
        plausible-looking figure.
        """
        try:
            reading = RowReading(**reading_fields)  # type: ignore[arg-type]
        except MalformedReadingError as exc:
            self.skip(f"reading rejected: {exc}")
            return
        self._rows.append(
            NativeRow(
                row_index=self._index,
                reading=reading,
                locator=self._locator,
                account_key=account_key,
                ordering_date=ordering_date,
                ordering_date_source=ordering_date_source,
                is_reversal=is_reversal,
            )
        )
        self._index += 1

    @property
    def rows(self) -> tuple[NativeRow, ...]:
        return tuple(self._rows)

    @property
    def unmapped(self) -> tuple[UnmappedRow, ...]:
        return tuple(self._unmapped)


def _iso_day(text: Optional[str]) -> Optional[date]:
    """A camt.053 date choice reduced to the calendar day it names.

    camt keeps its dates lexically for the reason
    :func:`services.financial.camt053._date_text` gives: a ``DtTm`` carries an
    offset, and converting it to a day means choosing a zone.  Taking the date
    portion as written is not that choice.  It keeps the day the bank stated,
    in the zone the bank stated it in, which is the account's jurisdiction by
    construction — and it is converting to UTC that would move an entry across
    the period boundary where a reconciliation is most likely to be contested.
    """
    if not text:
        return None
    head = text.strip()[:10]
    try:
        return date.fromisoformat(head)
    except ValueError:
        return None


def _clean(text: Optional[str]) -> Optional[str]:
    """A text field with surrounding space removed, or ``None`` if it is empty.

    Fixed-width formats pad; an empty string and an absent field mean the same
    thing and should hash the same way.
    """
    if text is None:
        return None
    stripped = text.strip()
    return stripped or None


# ---------------------------------------------------------------------------
# Per-format adapters
# ---------------------------------------------------------------------------


def _rows_camt053(document: Camt053Document) -> _RowCollector:
    """camt.053 entries as ledger rows, ordered by booking date.

    Booking is when the bank posted the entry and value is when it earns; the
    ledger orders by posting because that is what a statement's own totals are
    drawn against.  An entry with no booking date falls back to its value date
    rather than being dropped, and the fallback is recorded in
    ``ordering_date_source`` rather than hidden.

    Only ``BOOK`` entries become rows.  A pending entry is a bank's statement
    of intent, and admitting it as money that moved is the one error a
    statement parser must not make.
    """
    collector = _RowCollector(NativeFormat.camt053)
    for statement in document.statements:
        account_key = statement.account.identifier
        for entry in statement.entries:
            if not entry.is_booked:
                collector.skip(
                    f"entry status {entry.status!r} is not BOOK; the entry is "
                    "pending and does not assert that money moved"
                )
                continue
            posted = _iso_day(entry.booking_date)
            valued = _iso_day(entry.value_date)
            if posted is not None:
                ordering, source = posted, DateSource.posted
            elif valued is not None:
                ordering, source = valued, DateSource.value
            else:
                collector.skip(
                    f"entry states neither a usable booking date "
                    f"({entry.booking_date!r}) nor value date "
                    f"({entry.value_date!r}); the ledger orders by date and "
                    "there is none to order by"
                )
                continue
            collector.add(
                account_key=account_key,
                ordering_date=ordering,
                ordering_date_source=source,
                is_reversal=entry.is_reversal,
                currency=entry.amount.currency,
                amount_minor=entry.amount.minor_units,
                direction=entry.direction,
                posted_date=posted,
                value_date=valued,
                description=_clean(entry.additional_information),
                transaction_type=_clean(entry.bank_transaction_code),
                bank_reference=_clean(
                    entry.account_servicer_reference or entry.entry_reference
                ),
            )
    return collector


def _rows_bai2(file: Bai2File, window: CenturyWindow) -> _RowCollector:
    """BAI2 ``16`` records as ledger rows, ordered by the group's as-of date.

    A ``16`` states no date of its own.  BAI2's date lives on the ``02`` group
    header and covers every account and transaction beneath it, so the group's
    as-of date is the row's date — not an approximation of it, but the only
    date the format asserts for that movement.  It is recorded as
    ``posted_date`` because "as of" is a posting statement: it is the date the
    reporting bank drew the group against.

    A transaction whose type code is not in BAI2's direction table has no side
    to land on.  The parser reports ``None`` rather than guessing, and guessing
    here would be the same mistake one layer later.
    """
    collector = _RowCollector(NativeFormat.bai2)
    for group in file.groups:
        as_of = group.as_of_date
        posted: Optional[date] = None
        if as_of:
            posted = window.resolve_yymmdd(
                as_of, context=f"BAI2 group at line {group.first_line} as-of date"
            )
        for account in group.accounts:
            account_key = account.customer_account_number
            for transaction in account.transactions:
                if posted is None:
                    collector.skip(
                        f"transaction at line {transaction.line_number} sits "
                        f"under a group stating no as-of date; BAI2 puts the "
                        "date on the group and there is no other date for the "
                        "row to take"
                    )
                    continue
                direction = transaction.direction
                if direction is None:
                    collector.skip(
                        f"transaction type code {transaction.type_code!r} at "
                        f"line {transaction.line_number} is not in BAI2's "
                        "direction table; the row has no side to land on and "
                        "choosing one would be a guess recorded as a fact"
                    )
                    continue
                collector.add(
                    account_key=account_key,
                    ordering_date=posted,
                    ordering_date_source=DateSource.posted,
                    is_reversal=False,
                    currency=transaction.amount.currency,
                    amount_minor=transaction.amount.minor_units,
                    direction=direction,
                    posted_date=posted,
                    description=_clean(transaction.text),
                    transaction_type=_clean(transaction.type_code),
                    bank_reference=_clean(transaction.bank_reference),
                )
    return collector


def _rows_mt940(file: Mt940File, window: CenturyWindow) -> _RowCollector:
    """MT940 ``:61:`` lines as ledger rows, ordered by value date.

    Value date orders because it is the only date every ``:61:`` carries.  The
    entry date is optional in the format, and ordering by a field that is
    sometimes absent would sequence part of a statement one way and the rest
    another.

    The entry date is resolved against the value date and kept as
    ``posted_date`` for the record; see :func:`resolve_mmdd_near` for why
    deriving its year is defensible where deriving a century is not.
    """
    collector = _RowCollector(NativeFormat.mt940)
    for statement in file.statements:
        account_key = statement.account_identification
        currency = statement.currency
        for line in statement.lines:
            context = (
                f"MT940 :61: at line {line.first_line} in statement "
                f"{statement.transaction_reference!r}"
            )
            valued = window.resolve_yymmdd(line.value_date, context=f"{context} value date")
            posted: Optional[date] = None
            if line.entry_date:
                posted = resolve_mmdd_near(
                    line.entry_date, valued, context=f"{context} entry date"
                )
            collector.add(
                account_key=account_key,
                ordering_date=valued,
                ordering_date_source=DateSource.value,
                is_reversal=line.is_reversal,
                currency=currency,
                amount_minor=line.amount.minor_units,
                direction=line.direction,
                value_date=valued,
                posted_date=posted,
                description=_clean(line.information),
                transaction_type=_clean(line.transaction_type),
                # The institution's reference, not the account owner's.  The
                # owner's reference is what the customer called the payment;
                # the bank reference is what the bank will answer a query on,
                # and it is the bank a dispute is put to.
                bank_reference=_clean(line.institution_reference),
            )
    return collector


def _rows_nacha(file: NachaFile, window: CenturyWindow) -> _RowCollector:
    """NACHA ``6`` entry details as ledger rows, ordered by effective entry date.

    A ``6`` record states no date.  The batch's effective entry date is the day
    the originator asked for the funds to move, and it is the only date NACHA
    puts on an entry, so it is both the ordering date and the recorded
    ``effective_date``.  The file's creation date is not used: it says when the
    file was written, which for a file transmitted days ahead of settlement is
    not when the money moved.

    Prenotifications are excluded, and this is the format's one genuinely
    counter-intuitive exclusion.  A prenote carries a real routing number, a
    real account number and an amount of zero; it exists to test that an
    account will accept a later debit or credit.  It asserts that money will
    *not* move under this entry, so admitting it would put a row in a ledger
    for a transaction that by definition never happened.

    NACHA is the only one of the four formats with a structured counterparty:
    the ``6`` record carries the receiver's name in its own field rather than
    inside a free-text narrative, so ``counterparty_raw`` is populated here and
    nowhere else.
    """
    collector = _RowCollector(NativeFormat.nacha)
    for batch in file.batches:
        stated = (batch.effective_entry_date or "").strip()
        effective: Optional[date] = None
        if len(stated) == 6 and stated.isdigit():
            effective = window.resolve_yymmdd(
                stated,
                context=(
                    f"NACHA batch {batch.batch_number!r} at line "
                    f"{batch.line_number} effective entry date"
                ),
            )
        for entry in batch.entries:
            if entry.is_prenotification:
                collector.skip(
                    f"transaction code {entry.transaction_code} at line "
                    f"{entry.line_number} is a prenotification; it tests that "
                    "an account will accept a later entry and asserts that no "
                    "money moves under this one"
                )
                continue
            if entry.direction is None:
                collector.skip(
                    f"transaction code {entry.transaction_code!r} at line "
                    f"{entry.line_number} is not in NACHA's direction table; "
                    "the row has no side to land on"
                )
                continue
            if effective is None:
                collector.skip(
                    f"entry at line {entry.line_number} sits under a batch "
                    f"whose effective entry date is {batch.effective_entry_date!r}; "
                    "NACHA puts the date on the batch and there is no other "
                    "date for the row to take"
                )
                continue
            collector.add(
                account_key=f"{entry.routing_number}/{entry.account_number.strip()}",
                ordering_date=effective,
                ordering_date_source=DateSource.effective,
                # A return is money coming back, which is a reversal of the
                # entry that sent it, whatever the originator called it.
                is_reversal=entry.is_return,
                currency=entry.amount.currency,
                amount_minor=entry.amount.minor_units,
                direction=entry.direction,
                effective_date=effective,
                description=_clean(batch.entry_description),
                counterparty_raw=_clean(entry.individual_name),
                transaction_type=_clean(entry.transaction_code),
                bank_reference=_clean(entry.trace_number),
            )
    return collector


# ---------------------------------------------------------------------------
# The entry point
# ---------------------------------------------------------------------------


def read_native(
    data: bytes,
    *,
    window: CenturyWindow,
    default_currency: Optional[str] = None,
    fmt: Optional[NativeFormat] = None,
) -> NativeReading:
    """Read one native bank file as ledger rows that carry their own provenance.

    ``window`` is required: three of the four formats write two-digit years and
    none of them carries the century, so the caller states the span the
    evidence falls in rather than the library assuming one.

    ``default_currency`` reaches :func:`~services.financial.bai2.parse_bai2`
    and is ignored by the other three, which each state their currency —
    camt.053 and MT940 in the document, NACHA by being a United States clearing
    format.  It is accepted unconditionally so that a caller reading a mixed
    batch of evidence does not have to know which format each file is before
    calling.

    ``fmt`` overrides detection, for the case where the format is already known
    from outside the bytes — a client who has said what they sent, or a
    re-read of a document whose format was recorded the first time.  Left
    ``None``, the format is detected by exclusive claim.
    """
    payload = bytes(data)
    chosen = fmt if fmt is not None else detect_format(payload)

    if chosen is NativeFormat.camt053:
        document: object = parse_camt053(payload)
        collector = _rows_camt053(document)  # type: ignore[arg-type]
    elif chosen is NativeFormat.bai2:
        document = parse_bai2(payload, default_currency=default_currency)
        collector = _rows_bai2(document, window)  # type: ignore[arg-type]
    elif chosen is NativeFormat.mt940:
        document = parse_mt940(payload)
        collector = _rows_mt940(document, window)  # type: ignore[arg-type]
    else:
        document = parse_nacha(payload)
        collector = _rows_nacha(document, window)  # type: ignore[arg-type]

    reading = NativeReading(
        format=chosen,
        parser_name=parser_name(chosen),
        parser_version=parser_version(chosen),
        source_shape=document.source_shape,  # type: ignore[attr-defined]
        reconciliation_status=document.reconciliation_status,  # type: ignore[attr-defined]
        proof_class=document.proof_class,  # type: ignore[attr-defined]
        admissibility_reservations=tuple(
            document.admissibility_reservations  # type: ignore[attr-defined]
        ),
        rows=collector.rows,
        unmapped=collector.unmapped,
        document=document,
    )
    # Checked on every read rather than only under test.  The invariant is
    # cheap to verify and the failure it catches — a row counted twice or not
    # at all — is one that would otherwise surface as a total that is quietly
    # wrong.
    reading.check_partition()
    return reading
