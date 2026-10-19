"""Whether a row's date can be believed, and what a date disagreement proves.

Dates decide ordering, period membership, and every "what happened between X
and Y" answer the system will ever give.  They are also the field most often
read wrongly, because a year is four glyphs at the end of a string that OCR
treats as unremarkable.  This module is the check that stands between a date
as extracted and a date the ledger will act on.

It is shaped by a measurement of the ET-Fraud corpus rather than by intuition,
and the measurement is worth stating because almost every design decision here
follows from it.  Across 30,570 rows in 325 documents:

* Every date parses.  There is no format chaos to defend against at this
  stage; the readers already emit ISO dates or fail earlier.
* **Exactly one row is provably wrong.**  It is dated ``2321-10-08``, in a row
  whose description is visibly mangled OCR, sitting between neighbours dated
  2020-06-06 and 2021-10-12.  The true reading is almost certainly 2021.
* **343 rows fall outside their document's stated period**, and they are
  concentrated in four documents.  332 of them are in one 180-page file whose
  rows span 47 months while its stated period spans 18.

Those two facts point in opposite directions, and keeping them apart is the
whole job.

**One row was provably wrong, and the proof needs no invented constant.**  The
2321 row postdates the moment its own document was read.  A statement cannot
print a transaction that has not happened yet, so the contradiction is
absolute and needs no opinion about which years are reasonable.  This module
therefore has no minimum year, no maximum age, and no configurable window.
Those would all be guesses, and a guess that quarantines evidence is worse
than no check at all.  The corpus contains no implausibly *old* row, so no
rule is invented to catch one.

**Being outside the stated period proves nothing about the row.**  In the
worst document, 332 rows fall outside a period that spans a third of the time
its own rows cover.  The rows are almost certainly right and the period is
almost certainly a misread aggregate over a multi-statement PDF.  Quarantining
those rows would discard 332 pieces of good evidence to preserve one bad
field, and it would do so most aggressively exactly where the document was
hardest to read.  So ``outside_printed_period`` is a finding about a *pair*,
never grounds against the row, and :meth:`DateFinding.grounds` refuses to
produce a quarantine basis from one.

**What can be proved about the pair is a contradiction, not a culprit.**  If
the rows themselves span more calendar time than the stated period provides,
then no assignment of blame to individual dates can reconcile them: the set of
rows requires more days than the period has, whoever is wrong.  That is a
proof rather than a threshold, it needs no tuning, and it catches all four of
the corpus documents — including the one that exceeds its period by a single
day.  It says the period does not cover these rows.  It does not say which to
believe, because nothing here can know that.

**A derived bound cannot be used to check the rows it was derived from.**  The
2321 row demonstrates this better than any argument: its document's stated
period ends ``2321-10-08``, because the bound was taken from the maximum row
date and inherited the defect.  Checking rows against that bound would have
found everything in order.  So comparison is refused unless both bounds were
printed, for the same reason ``PeriodBounds.supports_continuity`` requires it
— and the refusal is recorded as its own outcome rather than silently passing,
because "not checked" and "checked and fine" are different states and only one
of them is reassuring.

There is no default for ``observed_at``.  Reading a clock inside this module
would make the same document produce different findings on different days and
would make the result impossible to reproduce from the record, so the anchor
is always supplied by the caller, which knows when the document was actually
in hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING, Optional, Sequence

from postgres.models.enums import DateSource, PeriodBoundsSource
from services.financial.periods import PeriodBounds
from services.financial.quarantine import QuarantineBasis

if TYPE_CHECKING:  # pragma: no cover - typing only
    from postgres.models.financial import FinancialTransaction


class DateError(Exception):
    """A date could not be recorded or checked as described."""


class DateCoherenceError(DateError):
    """A date and its stated origin contradict each other."""


class UngroundedDateQuarantineError(DateError):
    """Grounds for quarantine were asked for where none exist."""


class DatePlausibility(str, Enum):
    """What was established about one row's date.

    Five outcomes, and the distinction that matters most is between the two
    that mean "checked and fine" and the two that mean "not checked".
    Collapsing those would let an unreadable period silently certify every row
    beneath it.
    """

    # Inside a period whose bounds were both printed on the statement.
    within_printed_period = "within_printed_period"
    # Outside such a period.  A finding about the row and the period together;
    # it is not evidence against the row, and never grounds for quarantine.
    outside_printed_period = "outside_printed_period"
    # Postdates the moment the document was read.  A statement cannot print a
    # transaction that has not happened.  Proof-grade and row-level.
    impossible_future = "impossible_future"
    # The period exists but at least one bound was inferred from the rows, so
    # comparing the rows against it asks whether the extraction agrees with
    # itself.  Refused rather than answered.
    unchecked_derived_bounds = "unchecked_derived_bounds"
    # No period bounds at all.  Nothing to check against.
    unchecked_absent_bounds = "unchecked_absent_bounds"


class CoverageFinding(str, Enum):
    """What the rows of one document say about that document's stated period.

    ``span_contradiction`` is the only one of these that is a proof.  The
    others report what was seen without asserting a cause.
    """

    # Every checked row lies inside the printed period.
    covered = "covered"
    # Some rows lie outside, but the rows as a set would still fit inside a
    # window of the stated length.  Consistent with an offset period or with
    # individual misread dates; this module does not choose between them.
    rows_outside = "rows_outside"
    # The rows span more calendar time than the stated period provides, so no
    # assignment of error to individual rows can reconcile the two.  The
    # period does not cover these rows, whoever is at fault.
    span_contradiction = "span_contradiction"
    # Bounds absent or derived, so coverage was never tested.
    not_checkable = "not_checkable"


@dataclass(frozen=True)
class RowDate:
    """One row's ordering date, with its position and which date it is.

    ``source`` is which of a statement's several dates was chosen to order by,
    recorded so the choice can be reviewed rather than inferred.  It has no
    effect on plausibility: a transaction date and a posted date are checked
    identically, because the arithmetic of "before the period started" does not
    care which column the value came from.
    """

    row_index: int
    value: date
    source: DateSource

    def __post_init__(self) -> None:
        if not isinstance(self.row_index, int) or isinstance(self.row_index, bool):
            raise DateCoherenceError(
                f"row_index must be an int, got {type(self.row_index).__name__}"
            )
        if self.row_index < 0:
            raise DateCoherenceError(
                f"row_index must not be negative, got {self.row_index}"
            )
        # datetime subclasses date and would carry a time component into a Date
        # column and into every comparison below, so it is refused by name.
        if type(self.value) is not date:
            raise DateCoherenceError(
                f"row date must be a date, got {type(self.value).__name__}"
            )
        if not isinstance(self.source, DateSource):
            raise DateCoherenceError(
                f"source must be a DateSource, got {type(self.source).__name__}"
            )


@dataclass(frozen=True)
class DateFinding:
    """What was established about one row's date, and what it licenses.

    ``days_outside`` is zero for every outcome except
    ``outside_printed_period``, where it is the distance to the nearer bound.
    It is reported because the size of the excursion is what tells a reader
    whether they are looking at a boundary effect or at a different statement
    entirely, and that reading is a person's to make.
    """

    row: RowDate
    plausibility: DatePlausibility
    observed_at: date
    days_outside: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.plausibility, DatePlausibility):
            raise DateCoherenceError(
                f"plausibility must be a DatePlausibility, got "
                f"{type(self.plausibility).__name__}"
            )
        if type(self.observed_at) is not date:
            raise DateCoherenceError(
                f"observed_at must be a date, got {type(self.observed_at).__name__}"
            )
        if self.days_outside < 0:
            raise DateCoherenceError(
                f"days_outside must not be negative, got {self.days_outside}"
            )
        outside = self.plausibility is DatePlausibility.outside_printed_period
        if outside and self.days_outside == 0:
            raise DateCoherenceError(
                "a row recorded as outside the printed period must say by how "
                "far; zero days outside is inside"
            )
        if not outside and self.days_outside:
            raise DateCoherenceError(
                f"a {self.plausibility.value} finding may not carry a distance "
                "outside a period it was not compared against"
            )

    @property
    def is_provably_wrong(self) -> bool:
        """Whether the date contradicts something that cannot be argued with."""
        return self.plausibility is DatePlausibility.impossible_future

    @property
    def was_checked(self) -> bool:
        """Whether the row was actually compared against a usable period."""
        return self.plausibility in {
            DatePlausibility.within_printed_period,
            DatePlausibility.outside_printed_period,
        }

    def grounds(self) -> QuarantineBasis:
        """Grounds for setting this row aside, where they exist.

        Only a proved impossibility qualifies.  A row outside its stated
        period is refused here deliberately and loudly: in the corpus that
        motivated this module, acting on that signal would have quarantined
        343 rows, of which the overwhelming majority are good rows sitting
        under a misread period.
        """
        if self.plausibility is DatePlausibility.impossible_future:
            return QuarantineBasis.unreadable_row(
                f"row {self.row.row_index} is dated {self.row.value}, after "
                f"{self.observed_at} when the document was read; a statement "
                "cannot print a transaction that has not happened"
            )
        if self.plausibility is DatePlausibility.outside_printed_period:
            raise UngroundedDateQuarantineError(
                f"row {self.row.row_index} is dated {self.row.value}, "
                f"{self.days_outside} days outside the printed period, which "
                "is not grounds against the row; the period may be the misread "
                "value, and setting the row aside would discard evidence to "
                "protect a field with no better claim to be right"
            )
        raise UngroundedDateQuarantineError(
            f"a {self.plausibility.value} date finding is not grounds for "
            "quarantine; nothing about this row's date has been disproved"
        )


def check_row_date(
    row: RowDate,
    *,
    bounds: PeriodBounds,
    observed_at: date,
) -> DateFinding:
    """Establish what can be said about one row's date.

    The impossibility test runs first and independently of the period, because
    it is the only conclusion here that does not depend on another extracted
    field being right.  A row dated in the 24th century is wrong whether or not
    the statement said anything about its own coverage.
    """
    if not isinstance(row, RowDate):
        raise DateCoherenceError(f"row must be a RowDate, got {type(row).__name__}")
    if not isinstance(bounds, PeriodBounds):
        raise DateCoherenceError(
            f"bounds must be a PeriodBounds, got {type(bounds).__name__}"
        )
    if type(observed_at) is not date:
        raise DateCoherenceError(
            f"observed_at must be a date, got {type(observed_at).__name__}; "
            "this module never reads a clock, because a finding that changes "
            "with the day it was computed cannot be reproduced from the record"
        )

    if row.value > observed_at:
        return DateFinding(
            row=row,
            plausibility=DatePlausibility.impossible_future,
            observed_at=observed_at,
        )

    if not bounds.supports_continuity:
        # Same rule as continuity, for the same reason, and the corpus supplies
        # the demonstration: one document's period end is 2321-10-08 because
        # the bound was derived from a row misread as the 24th century. Checking
        # that document's rows against that bound would have found no fault.
        derived = PeriodBoundsSource.derived in (
            bounds.start_source,
            bounds.end_source,
        )
        return DateFinding(
            row=row,
            plausibility=(
                DatePlausibility.unchecked_derived_bounds
                if derived
                else DatePlausibility.unchecked_absent_bounds
            ),
            observed_at=observed_at,
        )

    # supports_continuity guarantees both bounds are printed, so both are set.
    assert bounds.start is not None and bounds.end is not None
    if row.value < bounds.start:
        return DateFinding(
            row=row,
            plausibility=DatePlausibility.outside_printed_period,
            observed_at=observed_at,
            days_outside=(bounds.start - row.value).days,
        )
    if row.value > bounds.end:
        return DateFinding(
            row=row,
            plausibility=DatePlausibility.outside_printed_period,
            observed_at=observed_at,
            days_outside=(row.value - bounds.end).days,
        )
    return DateFinding(
        row=row,
        plausibility=DatePlausibility.within_printed_period,
        observed_at=observed_at,
    )


@dataclass(frozen=True)
class DateSurvey:
    """Every row date of one document, checked, with the coverage conclusion.

    The survey exists because the interesting question is not "is this row
    odd" but "do these rows and this period describe the same statement", and
    that can only be asked of the set.
    """

    findings: tuple[DateFinding, ...]
    bounds: PeriodBounds
    observed_at: date

    @property
    def impossible(self) -> tuple[DateFinding, ...]:
        """Rows whose dates are disproved.  These, and only these, license
        quarantine."""
        return tuple(f for f in self.findings if f.is_provably_wrong)

    @property
    def outside(self) -> tuple[DateFinding, ...]:
        return tuple(
            f
            for f in self.findings
            if f.plausibility is DatePlausibility.outside_printed_period
        )

    @property
    def checked_count(self) -> int:
        return sum(1 for f in self.findings if f.was_checked)

    @property
    def observed_span_days(self) -> Optional[int]:
        """Calendar days between the earliest and latest believable row date.

        Rows already disproved are excluded, so a single 24th-century misread
        cannot manufacture a span contradiction on a document that is
        otherwise coherent.
        """
        usable = [f.row.value for f in self.findings if not f.is_provably_wrong]
        if not usable:
            return None
        return (max(usable) - min(usable)).days

    @property
    def stated_span_days(self) -> Optional[int]:
        if self.bounds.start is None or self.bounds.end is None:
            return None
        return (self.bounds.end - self.bounds.start).days

    @property
    def coverage(self) -> CoverageFinding:
        """Whether the stated period can cover the rows found beneath it."""
        if not self.bounds.supports_continuity:
            return CoverageFinding.not_checkable
        stated = self.stated_span_days
        observed = self.observed_span_days
        if stated is not None and observed is not None and observed > stated:
            return CoverageFinding.span_contradiction
        if self.outside:
            return CoverageFinding.rows_outside
        return CoverageFinding.covered

    @property
    def period_cannot_cover_the_rows(self) -> bool:
        """Whether the rows and the period are proved inconsistent as a set.

        True only for ``span_contradiction``, which is a proof: the rows
        require more calendar time than the period offers, so at least one of
        the two is misdescribed no matter how the individual dates are read.
        It does not say which, and this module never guesses.
        """
        return self.coverage is CoverageFinding.span_contradiction


def survey_row_dates(
    rows: Sequence[RowDate],
    *,
    bounds: PeriodBounds,
    observed_at: date,
) -> DateSurvey:
    """Check every row of a document and report the coverage conclusion."""
    return DateSurvey(
        findings=tuple(
            check_row_date(row, bounds=bounds, observed_at=observed_at)
            for row in rows
        ),
        bounds=bounds,
        observed_at=observed_at,
    )


def read_row_date(transaction: "FinancialTransaction") -> RowDate:
    """Recover the row-date value object from a stored ledger row."""
    return RowDate(
        row_index=transaction.row_index,
        value=transaction.ordering_date,
        source=DateSource(transaction.ordering_date_source),
    )
