"""What a native bank file says it holds, read without storing any of it.

:mod:`~services.financial.native_ingest` explains why the seam between reading
a file and writing it sits where it does: "a file can be read, described and
shown to a reviewer before a single row is stored, which is what the precheck
dialog is for."  This module is the reading half of that sentence.  It opens no
transaction, touches no writer, and returns a description.

What it is not
--------------

It is not :mod:`~services.financial.route_check`.  That module reads the first
few hundred bytes of many files and answers one question -- may this go to the
document pipeline -- cheaply enough to ask about fifty files at once.  This one
opens a single file in full, parses every row, and answers a different
question: if this were ingested, what would land, and would it land at all.

It is not a dry run of ingestion either, because it does not simulate the
writers.  Two of the four documented ingestion failures are decided before any
writer is called -- a file whose accounts cannot be described, and a row naming
an account no subject covers -- and those two are reported here exactly, from
the same functions ingestion uses.  The other two, a contradictory period and a
malformed draft, are decided inside the writers against rows already in the
database and cannot be known from the file alone.  So ``readable`` means the
file parses and its rows attribute; it does not promise the write succeeds.
Saying otherwise would turn a description into a guarantee it cannot keep.

Why it re-derives instead of guessing
-------------------------------------

Every fact reported here comes from calling the function ingestion calls, with
the arguments ingestion passes.  ``distinguisher`` is the file's recorded
sha256, which is what
:func:`~services.financial.native_ingest.ingest_native_reading` uses for the
same purpose; the window comes from the caller for the same reason it does
there.  A precheck that computed an account key a second way would eventually
compute it a second, different way, and the screen would then describe a file
that ingestion would store differently.

The size guard
--------------

Route-check labels a file native from a prefix.  A prefix is enough to be
wrong: a large binary can open with bytes a detector claims, and this module
would otherwise read all of it into memory inside a request.  Files over
:data:`MAX_PRECHECK_BYTES` are refused by name and size rather than opened.
The limit is far above any real statement -- these are text formats, and a year
of a busy account is measured in megabytes -- so a refusal here is a signal
that the file is not what it looked like.
"""

from __future__ import annotations

import dataclasses
import logging
import uuid
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from services.financial.accounts import AccountDraft
from services.financial.money import Money
from services.financial.native import (
    AmbiguousFormatError,
    CenturyWindow,
    DateResolutionError,
    NativeReading,
    UnrecognisedFormatError,
    read_native,
)
from services.financial.native_subjects import (
    AccountSubject,
    SubjectError,
    describe_subjects,
)
from services.financial.periods import BalanceObservation, PeriodBounds

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


#: The largest evidence file this will open, in bytes.  See the module
#: docstring: the ceiling exists because the caller's belief that a file is
#: native came from its first few hundred bytes.
MAX_PRECHECK_BYTES = 64 * 1024 * 1024


class PrecheckOutcome(str, Enum):
    """What reading the file established, in the words the interface shows.

    One word per way the answer can come out, because the caller's next move
    differs for each: a window that resolves no year is fixed by widening the
    window, an unrecognised file is fixed by reading it at a layer above zero,
    and an unattributable one is not fixed by the person holding it at all.
    """

    #: Parsed, described, and every row attributes to an account.
    readable = "readable"
    #: No native parser claims these bytes.
    unrecognised = "unrecognised"
    #: More than one native parser claims them, so the format is in doubt.
    ambiguous = "ambiguous"
    #: A two-digit year on a *row* has no reading inside the stated window.
    #: Raised by the parse, never by describing the accounts: an unresolvable
    #: date on a printed balance is recorded as an absent bound instead, so a
    #: statement is not discarded over its bounds.
    out_of_window = "out_of_window"
    #: Parsed, but its accounts cannot be described or its rows cannot be
    #: attributed to them.
    unattributable = "unattributable"
    #: Could not be opened, was too large to open, or failed to parse.
    unreadable = "unreadable"
    #: No such file in this case.
    not_found = "not_found"


@dataclass(frozen=True, slots=True)
class PrecheckBalance:
    """One opening or closing balance as the document stated it, or did not.

    ``amount_minor`` is ``None`` where the source is ``absent``, and that is
    not zero: :class:`~services.financial.periods.BalanceObservation` keeps the
    two apart because the difference decides whether the reconciliation
    arithmetic can run at all, and flattening it here would throw that away on
    the way to the screen.
    """

    source: str
    amount_minor: Optional[int] = None
    currency: Optional[str] = None

    @classmethod
    def of(cls, observation: BalanceObservation) -> "PrecheckBalance":
        amount: Optional[Money] = observation.amount
        return cls(
            source=observation.source.value,
            amount_minor=None if amount is None else amount.minor_units,
            currency=None if amount is None else amount.currency,
        )

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
        }


@dataclass(frozen=True, slots=True)
class PrecheckPeriod:
    """The span one document claims to cover for one account.

    Each bound carries its own source, for the reason
    :class:`~services.financial.periods.PeriodBounds` gives: a date printed on
    the statement and one derived from the rows support different arguments
    later, and only the printed pair can evidence a missing statement.
    """

    currency: str
    start: Optional[date]
    end: Optional[date]
    start_source: str
    end_source: str
    opening: PrecheckBalance
    closing: PrecheckBalance

    def as_dict(self) -> dict:
        return {
            "currency": self.currency,
            "start": None if self.start is None else self.start.isoformat(),
            "end": None if self.end is None else self.end.isoformat(),
            "start_source": self.start_source,
            "end_source": self.end_source,
            "opening": self.opening.as_dict(),
            "closing": self.closing.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class PrecheckAccount:
    """One account the file names, what it printed about it, and its rows.

    ``identified`` is read from the draft rather than guessed at: a
    distinguisher is set by :meth:`AccountDraft.unidentified` and by nothing
    else, so its presence means this document's account could not be given an
    identity that would match the same account seen elsewhere.

    ``identified`` being false does **not** mean the file printed no account
    number, and ``identifier_as_printed`` is reported beside it precisely so
    the two are not confused.  A number with no institution named alongside it
    does not identify an account -- the same digits belong to a different
    account at every other bank -- so a BAI2 or MT940 statement that prints an
    account number and no bank lands here with the number visible and
    ``identified`` false.  What that costs is joining: this account cannot be
    recognised as the same account in another document, so its movements stand
    alone until the institution is established.

    ``period`` is ``None`` for every NACHA account, and that is not a gap.  A
    NACHA file is a batch of payment instructions, not a statement: it makes no
    claim to cover anybody between two dates, and inventing one here would put
    a coverage claim on the record that no document made.
    """

    account_key: Optional[str]
    identified: bool
    row_count: int
    institution_name: Optional[str] = None
    identifier_as_printed: Optional[str] = None
    account_type: Optional[str] = None
    holder_name: Optional[str] = None
    currency: Optional[str] = None
    iban: Optional[str] = None
    bic: Optional[str] = None
    routing_number: Optional[str] = None
    period: Optional[PrecheckPeriod] = None

    def as_dict(self) -> dict:
        return {
            "account_key": self.account_key,
            "identified": self.identified,
            "row_count": self.row_count,
            "institution_name": self.institution_name,
            "identifier_as_printed": self.identifier_as_printed,
            "account_type": self.account_type,
            "holder_name": self.holder_name,
            "currency": self.currency,
            "iban": self.iban,
            "bic": self.bic,
            "routing_number": self.routing_number,
            "period": None if self.period is None else self.period.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class SkippedRow:
    """A row the parser read that would not become a ledger row, and why not."""

    row_index: int
    reason: str

    def as_dict(self) -> dict:
        return {"row_index": self.row_index, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class FilePrecheck:
    """Everything one file said about itself, stored nowhere.

    Facts about the reading survive an unattributable outcome.  A file that
    parsed forty rows and then failed to describe its accounts still parsed
    forty rows, and a screen that showed only the failure would leave the
    person unable to tell a file that is nearly right from one that is not a
    bank file at all.
    """

    file_id: str
    outcome: PrecheckOutcome
    file_name: Optional[str] = None
    #: Present on every outcome except ``readable``.  Always the words of the
    #: thing that refused, never a restatement of them.
    reason: Optional[str] = None

    detected_format: Optional[str] = None
    parser_name: Optional[str] = None
    parser_version: Optional[str] = None
    extraction_layer: Optional[int] = None
    source_shape: Optional[str] = None
    reconciliation_status: Optional[str] = None
    proof_class: Optional[str] = None
    admissibility_reservations: tuple[str, ...] = ()

    #: Rows that would be stored.
    row_count: Optional[int] = None
    #: Rows the parser read, stored and skipped together.  The pair is the only
    #: honest answer to "how many entries are in this file", and reporting one
    #: without the other is how a total comes to cover a subset silently.
    parsed_row_count: Optional[int] = None
    skipped: tuple[SkippedRow, ...] = ()

    earliest_ordering_date: Optional[date] = None
    latest_ordering_date: Optional[date] = None

    accounts: tuple[PrecheckAccount, ...] = ()
    #: Account keys carried by rows that no subject of this document covers.
    #: Non-empty means ingestion would raise ``UnattributableRowError``.
    unattributed_keys: tuple[Optional[str], ...] = ()
    unattributed_row_count: int = 0

    @property
    def would_ingest(self) -> bool:
        """Whether the two failures decidable from the file alone are absent.

        Not a promise that the write succeeds.  See the module docstring: a
        contradictory period is decided against rows already in the database.
        """
        return self.outcome is PrecheckOutcome.readable

    def as_dict(self) -> dict:
        return {
            "file_id": self.file_id,
            "file_name": self.file_name,
            "outcome": self.outcome.value,
            "would_ingest": self.would_ingest,
            "reason": self.reason,
            "detected_format": self.detected_format,
            "parser_name": self.parser_name,
            "parser_version": self.parser_version,
            "extraction_layer": self.extraction_layer,
            "source_shape": self.source_shape,
            "reconciliation_status": self.reconciliation_status,
            "proof_class": self.proof_class,
            "admissibility_reservations": list(self.admissibility_reservations),
            "row_count": self.row_count,
            "parsed_row_count": self.parsed_row_count,
            "skipped": [row.as_dict() for row in self.skipped],
            "earliest_ordering_date": (
                None
                if self.earliest_ordering_date is None
                else self.earliest_ordering_date.isoformat()
            ),
            "latest_ordering_date": (
                None
                if self.latest_ordering_date is None
                else self.latest_ordering_date.isoformat()
            ),
            "accounts": [account.as_dict() for account in self.accounts],
            "unattributed_keys": list(self.unattributed_keys),
            "unattributed_row_count": self.unattributed_row_count,
        }


# ---------------------------------------------------------------------------
# Describing a reading
# ---------------------------------------------------------------------------


def _reading_facts(reading: NativeReading) -> dict:
    """The parts of a precheck that come from the parse alone.

    Split out because they are reported whether or not the accounts could be
    described, and a second copy of them in the failure branch would be a
    second place for them to drift.
    """
    dates = sorted(row.ordering_date for row in reading.rows)
    return {
        "detected_format": reading.format.value,
        "parser_name": reading.parser_name,
        "parser_version": reading.parser_version,
        "extraction_layer": int(reading.extraction_layer.value),
        "source_shape": reading.source_shape.value,
        "reconciliation_status": reading.reconciliation_status.value,
        "proof_class": reading.proof_class.value,
        "admissibility_reservations": tuple(reading.admissibility_reservations),
        "row_count": reading.row_count,
        "parsed_row_count": reading.parsed_row_count,
        "skipped": tuple(
            SkippedRow(row_index=row.row_index, reason=row.reason)
            for row in reading.unmapped
        ),
        "earliest_ordering_date": dates[0] if dates else None,
        "latest_ordering_date": dates[-1] if dates else None,
    }


def _account_of(
    subject: AccountSubject, row_counts: dict[Optional[str], int]
) -> PrecheckAccount:
    draft: AccountDraft = subject.draft
    period: Optional[PrecheckPeriod] = None
    if subject.period is not None:
        bounds: PeriodBounds = subject.period.bounds
        period = PrecheckPeriod(
            currency=subject.period.currency,
            start=bounds.start,
            end=bounds.end,
            start_source=bounds.start_source.value,
            end_source=bounds.end_source.value,
            opening=PrecheckBalance.of(subject.period.opening),
            closing=PrecheckBalance.of(subject.period.closing),
        )
    return PrecheckAccount(
        account_key=subject.account_key,
        identified=draft.distinguisher is None,
        row_count=row_counts.get(subject.account_key, 0),
        institution_name=draft.institution_name,
        identifier_as_printed=draft.identifier_as_printed,
        account_type=draft.account_type,
        holder_name=draft.holder_name,
        currency=draft.currency,
        iban=draft.iban,
        bic=draft.bic,
        routing_number=draft.routing_number,
        period=period,
    )


def precheck_reading(
    reading: NativeReading,
    *,
    window: CenturyWindow,
    distinguisher: str,
    file_id: str,
    file_name: Optional[str] = None,
) -> FilePrecheck:
    """Describe an already-parsed reading, without storing any of it.

    Separated from the file handling so the description can be exercised
    against a reading built in a test, and so that the one place deciding what
    an undescribable file means is one place.
    """
    facts = _reading_facts(reading)

    try:
        subjects = describe_subjects(
            reading, window=window, distinguisher=distinguisher
        )
    except SubjectError as exc:
        # Reported, not raised.  The parse facts above are true regardless, and
        # a caller shown only "could not describe" cannot tell a file that is
        # nearly a statement from one that is not a statement.
        return FilePrecheck(
            file_id=file_id,
            file_name=file_name,
            outcome=PrecheckOutcome.unattributable,
            reason=str(exc),
            **facts,
        )
    # ``DateResolutionError`` is deliberately not caught here.  It cannot reach
    # this frame: ``native_subjects._yymmdd`` swallows it and returns ``None``,
    # so an unresolvable *balance* date is recorded as ``absent`` bounds rather
    # than discarding the statement, its rows and its amounts over the bounds
    # alone.  Only a row date can raise, and that happens inside ``read_native``
    # one level up.

    row_counts: dict[Optional[str], int] = {}
    for row in reading.rows:
        row_counts[row.account_key] = row_counts.get(row.account_key, 0) + 1

    covered = {subject.account_key for subject in subjects}
    # Ordered by first appearance rather than sorted, because the interface
    # shows them against the rows they came from and ``None`` does not sort
    # against a string.
    unattributed: list[Optional[str]] = []
    unattributed_rows = 0
    for row in reading.rows:
        if row.account_key in covered:
            continue
        unattributed_rows += 1
        if row.account_key not in unattributed:
            unattributed.append(row.account_key)

    accounts = tuple(_account_of(subject, row_counts) for subject in subjects)

    if unattributed:
        return FilePrecheck(
            file_id=file_id,
            file_name=file_name,
            outcome=PrecheckOutcome.unattributable,
            reason=(
                f"{unattributed_rows} row"
                f"{'' if unattributed_rows == 1 else 's'} name an account this "
                "document does not describe, so storing them would either "
                "invent an account or put these movements on another"
            ),
            accounts=accounts,
            unattributed_keys=tuple(unattributed),
            unattributed_row_count=unattributed_rows,
            **facts,
        )

    return FilePrecheck(
        file_id=file_id,
        file_name=file_name,
        outcome=PrecheckOutcome.readable,
        accounts=accounts,
        **facts,
    )


# ---------------------------------------------------------------------------
# Reading a file
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NativeParse:
    """One file located, opened and parsed -- or the reason it was not.

    The step before description, named and returned on its own because
    ingestion needs the same step and a different second half.  Precheck goes
    on to describe the accounts and report what it finds.  Ingestion hands the
    reading to a writer, which describes them itself and refuses on what it
    finds.  What both need first is identical: the file located, size-checked,
    opened, parsed, and a parser that raises turned into one of the same four
    words.

    A second copy of that in the ingest path would drift from this one, and the
    two endpoints would then answer differently about the same file -- which is
    the one thing the precheck dialog exists to rule out.

    ``reading`` is set when the parse succeeded and ``outcome`` when it did
    not.  Exactly one of the two is ever populated.
    """

    file_id: str
    file_name: Optional[str] = None
    #: The evidence row's recorded content hash, set only by
    #: :func:`read_case_file`, which is the only layer with a row to read it
    #: from.  It serves as both the distinguisher and the hash the document
    #: records, for the reason ``ingest_native_reading`` gives.
    sha256: Optional[str] = None
    reading: Optional[NativeReading] = None
    outcome: Optional[PrecheckOutcome] = None
    reason: Optional[str] = None

    @property
    def parsed(self) -> bool:
        return self.reading is not None


def _unparsed(
    file_id: str,
    file_name: Optional[str],
    outcome: PrecheckOutcome,
    reason: str,
) -> NativeParse:
    return NativeParse(
        file_id=file_id, file_name=file_name, outcome=outcome, reason=reason
    )


def _described(
    parse: NativeParse, *, window: CenturyWindow, distinguisher: str
) -> FilePrecheck:
    """A parse that failed as a description of the failure; one that did not,
    described in full."""
    if parse.reading is None:
        return FilePrecheck(
            file_id=parse.file_id,
            file_name=parse.file_name,
            outcome=parse.outcome or PrecheckOutcome.unreadable,
            reason=parse.reason,
        )
    return precheck_reading(
        parse.reading,
        window=window,
        distinguisher=distinguisher,
        file_id=parse.file_id,
        file_name=parse.file_name,
    )


def parse_bytes(
    data: bytes,
    *,
    window: CenturyWindow,
    file_id: str,
    file_name: Optional[str] = None,
    default_currency: Optional[str] = None,
) -> NativeParse:
    """Parse one native file's bytes, or say in one word why it did not parse.

    Every failure comes back as an outcome rather than an exception, because
    the caller's question -- what does this file hold -- has an answer in each
    case, and the answer is what the screen shows.
    """
    try:
        reading = read_native(
            data, window=window, default_currency=default_currency
        )
    except UnrecognisedFormatError as exc:
        return _unparsed(
            file_id, file_name, PrecheckOutcome.unrecognised, str(exc)
        )
    except AmbiguousFormatError as exc:
        return _unparsed(file_id, file_name, PrecheckOutcome.ambiguous, str(exc))
    except DateResolutionError as exc:
        return _unparsed(
            file_id, file_name, PrecheckOutcome.out_of_window, str(exc)
        )
    except Exception as exc:  # noqa: BLE001 - a parser that raises is not a verdict
        # Deliberately broad.  A malformed file reaches the parsers as bytes
        # and they raise their own errors; none of them is a reason to fail the
        # request, and all of them mean the same thing to the person asking.
        logger.exception("Native parse raised while prechecking a file")
        return _unparsed(
            file_id,
            file_name,
            PrecheckOutcome.unreadable,
            f"{type(exc).__name__}: {exc}",
        )

    return NativeParse(file_id=file_id, file_name=file_name, reading=reading)


def parse_path(
    path: Optional[Path],
    *,
    window: CenturyWindow,
    file_id: str,
    file_name: Optional[str] = None,
    default_currency: Optional[str] = None,
) -> NativeParse:
    """Open one file in full and parse it.

    Unlike :func:`~services.financial.route_check.check_path` this reads the
    whole file, because the question is what the file holds and a prefix cannot
    answer it.  Hence the size guard.
    """
    if path is None:
        return _unparsed(
            file_id,
            file_name,
            PrecheckOutcome.unreadable,
            "the file has no stored path",
        )

    try:
        size = path.stat().st_size
    except OSError as exc:
        return _unparsed(
            file_id,
            file_name,
            PrecheckOutcome.unreadable,
            f"{type(exc).__name__}: {exc}",
        )

    if size > MAX_PRECHECK_BYTES:
        return _unparsed(
            file_id,
            file_name,
            PrecheckOutcome.unreadable,
            (
                f"the file is {size} bytes, above the {MAX_PRECHECK_BYTES}-byte "
                "limit for reading a bank file in full; a native statement this "
                "large is not a native statement"
            ),
        )

    try:
        data = path.read_bytes()
    except OSError as exc:
        return _unparsed(
            file_id,
            file_name,
            PrecheckOutcome.unreadable,
            f"{type(exc).__name__}: {exc}",
        )

    return parse_bytes(
        data,
        window=window,
        file_id=file_id,
        file_name=file_name,
        default_currency=default_currency,
    )


def precheck_bytes(
    data: bytes,
    *,
    window: CenturyWindow,
    distinguisher: str,
    file_id: str,
    file_name: Optional[str] = None,
    default_currency: Optional[str] = None,
) -> FilePrecheck:
    """Parse and describe one native file's bytes."""
    return _described(
        parse_bytes(
            data,
            window=window,
            file_id=file_id,
            file_name=file_name,
            default_currency=default_currency,
        ),
        window=window,
        distinguisher=distinguisher,
    )


def precheck_path(
    path: Optional[Path],
    *,
    window: CenturyWindow,
    distinguisher: str,
    file_id: str,
    file_name: Optional[str] = None,
    default_currency: Optional[str] = None,
) -> FilePrecheck:
    """Open one file in full and describe it."""
    return _described(
        parse_path(
            path,
            window=window,
            file_id=file_id,
            file_name=file_name,
            default_currency=default_currency,
        ),
        window=window,
        distinguisher=distinguisher,
    )


@dataclass(frozen=True, slots=True)
class _CaseFile:
    """An evidence row resolved far enough to be worth opening."""

    file_id: str
    file_name: Optional[str]
    sha256: str
    stored_path: Optional[str]


def _locate_case_file(
    db: "Session", *, case_id: uuid.UUID, file_id: uuid.UUID
) -> "_CaseFile | NativeParse":
    """Find the evidence row, or return the parse that will never happen.

    Shared by :func:`precheck_case_file` and :func:`read_case_file` so that the
    two cannot come to disagree about which files belong to a case or which
    rows are usable.
    """
    from services.evidence_db_storage import EvidenceDBStorage

    record = EvidenceDBStorage.get(db, file_id)
    if record is None or record.case_id != case_id:
        return _unparsed(
            str(file_id),
            None,
            PrecheckOutcome.not_found,
            "no such file in this case",
        )

    sha256 = (record.sha256 or "").strip()
    if not sha256:
        # The column is NOT NULL, so this is a row that predates the constraint
        # or was written around it.  Falling back to the file id would produce
        # account keys that ingestion would not reproduce, which is worse than
        # saying so.
        return _unparsed(
            str(record.id),
            record.original_filename,
            PrecheckOutcome.unreadable,
            (
                "this file has no recorded content hash, and the hash is what "
                "tells an unidentified account in one document from an "
                "unidentified account in another"
            ),
        )

    return _CaseFile(
        file_id=str(record.id),
        file_name=record.original_filename,
        sha256=sha256,
        stored_path=record.stored_path,
    )


def precheck_case_file(
    db: "Session",
    *,
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    resolve_path: Callable[[Optional[str]], Optional[Path]],
    window: CenturyWindow,
    default_currency: Optional[str] = None,
) -> FilePrecheck:
    """Describe one evidence file, if it belongs to this case.

    ``resolve_path`` is required rather than defaulted for the reason
    :func:`~services.financial.route_check.check_case_files` gives: the stored
    path on an evidence file is not always a path that exists in this process,
    and the router owns the function that reconciles the two layouts.  A
    default of "use it as written" would work on a developer's machine and
    quietly fail in a container.

    A file in another case is reported identically to one that does not exist,
    so that asking cannot be used to learn what is in a case the caller cannot
    see.

    The distinguisher is the file's recorded ``sha256``, which is the value
    :func:`~services.financial.native_ingest.ingest_native_reading` will be
    given for the same file.  Taking it from the same column is what makes the
    account keys shown here the keys that would actually be written.
    """
    located = _locate_case_file(db, case_id=case_id, file_id=file_id)
    if isinstance(located, NativeParse):
        return _described(located, window=window, distinguisher="")

    return precheck_path(
        resolve_path(located.stored_path),
        window=window,
        distinguisher=located.sha256,
        file_id=located.file_id,
        file_name=located.file_name,
        default_currency=default_currency,
    )


def read_case_file(
    db: "Session",
    *,
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    resolve_path: Callable[[Optional[str]], Optional[Path]],
    window: CenturyWindow,
    default_currency: Optional[str] = None,
) -> NativeParse:
    """Locate and parse one evidence file, without describing what is in it.

    What :func:`precheck_case_file` does up to the point where the two paths
    part.  Ingestion stops here because the writer describes the subjects
    itself, from the same reading, and refuses on what it finds; describing
    them twice would put the same judgement in two places.

    The returned :attr:`NativeParse.sha256` is the row's own recorded hash, and
    it is what the caller must pass on as the document's hash and its
    distinguisher.  Reading it here rather than at the call site is what keeps
    the account keys ingestion writes identical to the ones precheck showed.
    """
    located = _locate_case_file(db, case_id=case_id, file_id=file_id)
    if isinstance(located, NativeParse):
        return located

    parse = parse_path(
        resolve_path(located.stored_path),
        window=window,
        file_id=located.file_id,
        file_name=located.file_name,
        default_currency=default_currency,
    )
    return dataclasses.replace(parse, sha256=located.sha256)
