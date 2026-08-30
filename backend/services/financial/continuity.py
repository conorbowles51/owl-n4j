"""Cross-period continuity: whether an account's statements form an unbroken run.

Reconciliation asks whether one statement is internally consistent.  This module
asks the question reconciliation cannot: whether the statements held for an
account actually abut, and whether each one's closing balance is the next one's
opening balance.  A perfectly reconciling statement proves nothing about the
month before it, so an account can consist entirely of periods that each balance
and still be missing half its history.  A gap between two printed period bounds
is the only evidence that a whole statement was never produced.

The design of this module was set by measuring the corpus rather than by
reasoning about what statements ought to look like, and the first measurement
was wrong in an instructive way.  Sorting every period by start date and
comparing neighbours reported 87 overlapping pairs against 48 gaps, which no
account of a statement series predicts.  All but four of those overlaps were
artefacts of the measurement:

  * documents already superseded as duplicates, counted as separate periods,
    so the run appeared to double back on itself once per duplicate group;
  * multi-year exports — one covering 2017-10-24 to 2021-05-17 — interleaved
    with the monthly statements they enclose, overlapping every one of them.

Both are handled here, and both are handled by exclusion with a recorded
reason rather than by silently reordering, because a period set aside without
explanation is indistinguishable from a period nobody looked at.

The same measurement decided the rest of the vocabulary.  Of 102 adjacent pairs
where both balances were present, 96 agreed outright and the remaining 6 were
each the same magnitude with an inverted sign — a closing of -1,049.57 meeting
an opening of +1,049.57.  Not one was a genuine break.  That is why
:class:`SeamAgreement` distinguishes ``sign_inverted`` from ``disagrees``
instead of normalising the sign away: on a liability account the sign is a
convention rather than a fact, so a seam that agrees only under an assumed
convention is a different finding from one that agrees outright, and squashing
them together would also hide a real sign error on the one occasion it mattered.

None of the 48 gaps agreed across the missing statement, which is what makes a
gap evidence of an absent document rather than a discrepancy to be explained.
A gap whose balances *do* agree is therefore the surprising case, and
:attr:`Seam.balance_survived_the_gap` marks it for a human rather than treating
it as a quiet success.

Nothing here mutates the ledger.  Continuity is a reading of periods already
recorded, and the periods are the evidence.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING, Iterable, Optional, Sequence

from postgres.models.enums import DocumentStatus, PeriodBoundsSource
from postgres.models.financial import (
    FinancialSourceDocument,
    FinancialStatementPeriod,
)
from services.financial.money import Money

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.orm import Session


class ContinuityError(Exception):
    """A continuity reading was asked for something it cannot answer."""


class ContinuityScopeError(ContinuityError):
    """Periods from more than one account were offered as a single run."""


class SeamKind(str, Enum):
    """How two adjacent periods meet in time.

    ``contiguous`` is the only one of the three that carries no complaint.  The
    other two are recorded rather than repaired: an overlap that survives the
    exclusions below usually means duplicate resolution has not been run, and a
    gap means a statement is missing, which is the single most valuable thing
    this module can say.
    """

    contiguous = "contiguous"
    gap = "gap"
    overlap = "overlap"


class SeamAgreement(str, Enum):
    """Whether the earlier closing balance meets the later opening balance.

    ``circular`` is not a weaker form of agreement, it is the absence of a
    test.  Where the later period's opening balance was carried forward from
    the earlier period, the two numbers are the same number, and comparing them
    asks only whether a copy succeeded.  Reporting that as ``agrees`` would
    manufacture corroboration out of an assignment, and would do it precisely
    on the periods whose balances were never printed — the ones least entitled
    to it.

    ``unavailable`` is likewise not a failure.  A balance that was never
    printed is not a balance of zero, and 39 of the corpus's adjacent pairs are
    missing one.  Declining to answer is the honest result.
    """

    agrees = "agrees"
    sign_inverted = "sign_inverted"
    disagrees = "disagrees"
    unavailable = "unavailable"
    circular = "circular"
    currency_mismatch = "currency_mismatch"


class ExclusionReason(str, Enum):
    """Why a period was left out of the run, kept so the omission is visible.

    ``enclosing`` is the multi-year export case.  A period that strictly
    contains another period for the same account is not that account's
    neighbour in a series; it is the same history at a coarser grain.  Its
    closing balance belongs to the end of a span, not to the start of the next
    month, so comparing the two is a category error that reports an overlap in
    place of the contiguous seam it obscures.
    """

    undated = "undated"
    derived_bounds = "derived_bounds"
    not_admitted = "not_admitted"
    enclosing = "enclosing"


@dataclass(frozen=True)
class PeriodLink:
    """One period, reduced to what a continuity reading is entitled to use.

    The balances arrive as :class:`Money` or as ``None``, never as a bare
    integer, so a seam cannot be computed across two currencies by accident.
    """

    period_id: uuid.UUID
    document_id: uuid.UUID
    account_id: uuid.UUID
    currency: str
    start: date
    end: date
    opening: Optional[Money] = None
    closing: Optional[Money] = None
    opening_carried_from_period_id: Optional[uuid.UUID] = None
    closing_carried_from_period_id: Optional[uuid.UUID] = None

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ContinuityError(
                f"period {self.period_id} ends {self.end} before it starts "
                f"{self.start}"
            )
        for label, value in (("opening", self.opening), ("closing", self.closing)):
            if value is not None and not isinstance(value, Money):
                raise ContinuityError(
                    f"{label} must be a Money or None, got "
                    f"{type(value).__name__}; a bare number would not carry the "
                    "currency the comparison depends on"
                )

    @property
    def span_days(self) -> int:
        """Days covered, counting both endpoints."""
        return (self.end - self.start).days + 1

    def encloses(self, other: "PeriodLink") -> bool:
        """Whether this period strictly contains another and is longer.

        Equal spans are deliberately not enclosure.  Two periods covering
        exactly the same dates are duplicates or a contradiction, and both are
        someone else's question; neither is answered by discarding one of them
        here.
        """
        return (
            self.start <= other.start
            and self.end >= other.end
            and self.span_days > other.span_days
        )


@dataclass(frozen=True)
class ExcludedPeriod:
    """A period left out of the run, and the reason it was left out."""

    period_id: uuid.UUID
    document_id: uuid.UUID
    reason: ExclusionReason
    detail: Optional[str] = None


@dataclass(frozen=True)
class Seam:
    """The join between two consecutive periods of one account.

    ``uncovered_days`` is the number of calendar days no statement covers:
    zero when the periods abut, positive across a gap, negative where they
    overlap.  It is derived from the printed bounds only, which is why
    :func:`build_run` refuses periods whose bounds were derived from their own
    transaction rows — such a bound shrinks to fit whatever was extracted, so
    it invents a gap after a quiet month and closes a real one whenever the
    final rows were dropped.
    """

    account_id: uuid.UUID
    earlier: PeriodLink
    later: PeriodLink
    kind: SeamKind
    agreement: SeamAgreement
    uncovered_days: int
    discrepancy: Optional[Money] = None

    @property
    def proves_continuous(self) -> bool:
        """Whether this seam is evidence that nothing is missing between them.

        Deliberately strict, and strict in the same way as
        ``IdentityOutcome.proves_completeness``: the periods must abut, the
        balances must agree outright, and the agreement must be independent.
        An inverted sign does not qualify, because the claim then rests on a
        convention this module did not verify.
        """
        return (
            self.kind is SeamKind.contiguous
            and self.agreement is SeamAgreement.agrees
        )

    @property
    def agrees_under_a_sign_convention(self) -> bool:
        """Whether the two balances match once one of them is negated.

        True for a seam that would prove continuity if the account's sign
        convention were settled.  Settling it is
        ``services.financial.statement_totals``' work, not this module's.
        """
        return self.agreement is SeamAgreement.sign_inverted

    @property
    def balance_survived_the_gap(self) -> bool:
        """A gap the balances did not notice, which wants a human.

        Not one of the corpus's 48 gaps agreed across the missing statement,
        because a month with no activity is rare and a missing statement almost
        always moved the balance.  So agreement here means something specific
        and worth surfacing: either the absent statement was empty, or the two
        periods are not the neighbours they appear to be.
        """
        return self.kind is SeamKind.gap and self.agreement in (
            SeamAgreement.agrees,
            SeamAgreement.sign_inverted,
        )


@dataclass(frozen=True)
class AccountContinuity:
    """Every seam in one account's run, with what was set aside to build it."""

    account_id: Optional[uuid.UUID]
    periods: Sequence[PeriodLink] = field(default_factory=tuple)
    seams: Sequence[Seam] = field(default_factory=tuple)
    excluded: Sequence[ExcludedPeriod] = field(default_factory=tuple)

    @property
    def gaps(self) -> tuple[Seam, ...]:
        """Seams where no statement covers the intervening days."""
        return tuple(s for s in self.seams if s.kind is SeamKind.gap)

    @property
    def overlaps(self) -> tuple[Seam, ...]:
        """Seams where two statements claim the same days.

        A non-empty result after duplicate resolution has run is a finding in
        itself: two admitted documents assert coverage of one span.
        """
        return tuple(s for s in self.seams if s.kind is SeamKind.overlap)

    @property
    def breaks(self) -> tuple[Seam, ...]:
        """Abutting seams whose balances genuinely disagree.

        Sign inversions are excluded, being a convention rather than a break.
        In the measured corpus this was empty for every account.
        """
        return tuple(
            s
            for s in self.seams
            if s.kind is SeamKind.contiguous
            and s.agreement is SeamAgreement.disagrees
        )

    @property
    def uncovered_days(self) -> int:
        """Total days between the first and last period that nothing covers."""
        return sum(s.uncovered_days for s in self.gaps)

    @property
    def covered_from(self) -> Optional[date]:
        return self.periods[0].start if self.periods else None

    @property
    def covered_to(self) -> Optional[date]:
        return self.periods[-1].end if self.periods else None

    @property
    def is_unbroken(self) -> bool:
        """Whether every seam in the run proves continuity.

        False for a single period, which has no seam and therefore no evidence
        either way.  An account represented by one statement is not a
        continuous history; it is one statement.
        """
        return bool(self.seams) and all(s.proves_continuous for s in self.seams)


def _link_from_period(
    period: FinancialStatementPeriod,
) -> PeriodLink:
    """Read a stored period into the reduced view a seam is computed from."""

    def money(minor: Optional[int]) -> Optional[Money]:
        if minor is None:
            return None
        return Money(minor_units=minor, currency=period.currency)

    return PeriodLink(
        period_id=period.id,
        document_id=period.source_document_id,
        account_id=period.account_id,
        currency=period.currency,
        start=period.period_start,
        end=period.period_end,
        opening=money(period.opening_balance_minor),
        closing=money(period.closing_balance_minor),
        opening_carried_from_period_id=period.opening_carried_from_period_id,
        closing_carried_from_period_id=period.closing_carried_from_period_id,
    )


def _bounds_are_printed(period: FinancialStatementPeriod) -> bool:
    """Whether both bounds were printed on the statement rather than derived."""
    return (
        period.period_start_source == PeriodBoundsSource.printed.value
        and period.period_end_source == PeriodBoundsSource.printed.value
    )


def assess_seam(earlier: PeriodLink, later: PeriodLink) -> Seam:
    """Classify one join between two periods in time and in money.

    The two classifications are independent on purpose.  A gap whose balances
    agree and an abutting pair whose balances disagree are both real and mean
    quite different things, and a single verdict would have to lose one of
    them.
    """
    if earlier.account_id != later.account_id:
        raise ContinuityScopeError(
            "a seam joins two periods of one account; got "
            f"{earlier.account_id} and {later.account_id}"
        )

    # -- in time -----------------------------------------------------------
    uncovered = (later.start - earlier.end).days - 1
    if uncovered == 0:
        kind = SeamKind.contiguous
    elif uncovered > 0:
        kind = SeamKind.gap
    else:
        kind = SeamKind.overlap

    # -- in money ----------------------------------------------------------
    closing, opening = earlier.closing, later.opening
    discrepancy: Optional[Money] = None

    carried_from_here = (
        later.opening_carried_from_period_id == earlier.period_id
        or earlier.closing_carried_from_period_id == later.period_id
    )

    if carried_from_here:
        # One of these numbers was copied from the other.  There is no test
        # here to pass, and calling the copy a corroboration would invent
        # evidence for exactly the periods that printed no balance.
        agreement = SeamAgreement.circular
    elif closing is None or opening is None:
        agreement = SeamAgreement.unavailable
    elif closing.currency != opening.currency:
        agreement = SeamAgreement.currency_mismatch
    elif closing == opening:
        agreement = SeamAgreement.agrees
    elif closing.minor_units == -opening.minor_units:
        # Equal magnitudes, opposite signs.  Six of the corpus's six abutting
        # disagreements were this, and none was a genuine break.
        agreement = SeamAgreement.sign_inverted
        discrepancy = opening - closing
    else:
        agreement = SeamAgreement.disagrees
        discrepancy = opening - closing

    return Seam(
        account_id=earlier.account_id,
        earlier=earlier,
        later=later,
        kind=kind,
        agreement=agreement,
        uncovered_days=uncovered,
        discrepancy=discrepancy,
    )


def order_links(
    links: Iterable[PeriodLink],
) -> tuple[list[PeriodLink], list[ExcludedPeriod]]:
    """Put periods in order, setting aside the ones that enclose others.

    Separated from :func:`build_run` so the rule can be exercised against
    period data that never came from the ledger — which is how it was checked
    against the corpus that motivated it.

    The sort is by start, then end, then id.  The id is there so that two
    periods with identical bounds order deterministically rather than by
    whatever order the database returned them in; a run that changes shape
    between reads cannot be evidence of anything.
    """
    links = list(links)
    kept: list[PeriodLink] = []
    excluded: list[ExcludedPeriod] = []

    for link in links:
        # A period containing another period of the same account is a summary
        # or a multi-year export: the same history at a coarser grain, which
        # overlaps every statement it covers.
        enclosed = [o for o in links if o is not link and link.encloses(o)]
        if enclosed:
            excluded.append(
                ExcludedPeriod(
                    period_id=link.period_id,
                    document_id=link.document_id,
                    reason=ExclusionReason.enclosing,
                    detail=f"spans {link.span_days} days, containing "
                    f"{len(enclosed)} shorter period(s)",
                )
            )
            continue
        kept.append(link)

    kept.sort(key=lambda link: (link.start, link.end, str(link.period_id)))
    return kept, excluded


def build_run(
    periods: Iterable[FinancialStatementPeriod],
    *,
    document_status: Optional[dict[uuid.UUID, str]] = None,
) -> AccountContinuity:
    """Order one account's periods into a run and read every seam in it.

    ``document_status`` maps a document id to its status where the caller has
    already loaded it; anything not admitted is excluded.  Continuity is a
    reading of the documents currently relied upon, and a superseded duplicate
    is not one of them — leaving them in was what produced 83 of the first
    measurement's 87 phantom overlaps.

    Exclusions are returned, not discarded.  A caller looking at a run with
    four seams is entitled to know that eleven periods were set aside and why.
    """
    links: list[PeriodLink] = []
    excluded: list[ExcludedPeriod] = []
    account_ids: set[uuid.UUID] = set()

    for period in periods:
        account_ids.add(period.account_id)
        status = (document_status or {}).get(period.source_document_id)
        if status is not None and status != DocumentStatus.admitted.value:
            excluded.append(
                ExcludedPeriod(
                    period_id=period.id,
                    document_id=period.source_document_id,
                    reason=ExclusionReason.not_admitted,
                    detail=status,
                )
            )
            continue
        if period.period_start is None or period.period_end is None:
            excluded.append(
                ExcludedPeriod(
                    period_id=period.id,
                    document_id=period.source_document_id,
                    reason=ExclusionReason.undated,
                )
            )
            continue
        if not _bounds_are_printed(period):
            excluded.append(
                ExcludedPeriod(
                    period_id=period.id,
                    document_id=period.source_document_id,
                    reason=ExclusionReason.derived_bounds,
                    detail=(
                        f"start={period.period_start_source} "
                        f"end={period.period_end_source}"
                    ),
                )
            )
            continue
        links.append(_link_from_period(period))

    if len(account_ids) > 1:
        raise ContinuityScopeError(
            f"a run covers one account; got {len(account_ids)}"
        )

    kept, enclosing = order_links(links)
    excluded.extend(enclosing)

    seams = tuple(
        assess_seam(earlier, later) for earlier, later in zip(kept, kept[1:])
    )

    return AccountContinuity(
        account_id=next(iter(account_ids)) if account_ids else None,
        periods=tuple(kept),
        seams=seams,
        excluded=tuple(excluded),
    )


def read_account_continuity(
    db: "Session",
    *,
    case_id: uuid.UUID,
    account_id: uuid.UUID,
) -> AccountContinuity:
    """Load one account's periods from the ledger and read its run.

    Scoped by case as well as account so that a mistaken account id cannot
    reach across matters; the account id alone is unique, but a query that
    depends on that is one schema change away from being a cross-case leak.
    """
    from sqlalchemy import select

    rows = (
        db.execute(
            select(FinancialStatementPeriod)
            .where(
                FinancialStatementPeriod.case_id == case_id,
                FinancialStatementPeriod.account_id == account_id,
            )
            .order_by(
                FinancialStatementPeriod.period_start,
                FinancialStatementPeriod.period_end,
                FinancialStatementPeriod.id,
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return AccountContinuity(account_id=account_id)

    statuses = dict(
        db.execute(
            select(
                FinancialSourceDocument.id,
                FinancialSourceDocument.status,
            ).where(
                FinancialSourceDocument.id.in_(
                    {r.source_document_id for r in rows}
                )
            )
        ).all()
    )
    return build_run(rows, document_status=statuses)
