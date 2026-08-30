"""The statement's own printed control totals, read without assuming a dialect.

This module sits at the boundary, before anything reaches the ledger.  It is
concerned with one thing: the block of summary figures an institution prints on
its own statement — opening balance, deposits, withdrawals, checks, fees,
closing balance — and whether those figures are internally consistent.

That block is the most valuable evidence a document carries, because the
institution computed it and we did not.  Checking our extracted rows against it
is the check that catches a dropped transaction.  But the block cannot be read
naively, and two facts measured across the 326-document ET-Fraud corpus say why.

**The field names are not stable.**  The deposits/withdrawals pair appears as
``deposits_credits``/``withdrawals_debits`` on 139 documents, ``deposits``/
``withdrawals`` on 39, ``credits``/``debits`` on 18, and on one Chase business
statement as ``deposits_additions`` against three separate withdrawal buckets
that must be summed.  Opening and closing appear as ``beginning_balance``/
``ending_balance`` on 187 and as ``opening``/``closing`` on 10.  Reading a
fixed field name finds nothing on a quarter of the corpus, and finding nothing
is indistinguishable, downstream, from a figure of zero.

**The sign convention is not stable either.**  See
:class:`~postgres.models.enums.TotalsConvention`.  Two documents in the corpus
print their outflows already negative.  Under the subtracting formula they miss
by $279,555.74 and $280,288.96; under the adding formula they are exact to the
cent.  They are not errors.  A check hard-coded to one dialect would have
reported the two most accurate documents in the corpus as its two worst.

The response to both is the same and is the design of this module: **normalise
explicitly, and never guess silently.**

The alias table below is data, not logic, so that adding an institution is a
reviewable diff rather than a change to a parser.  Roles are disjoint — no
field name belongs to two roles — and verified so across all 326 documents,
which is what makes summing the outflow roles safe from double-counting.  Each
role takes the first alias present, and no document in the corpus carries two
aliases of one role, so that rule discards nothing.

Convention is *inferred* by :func:`infer_convention`, which reports which
dialects close and whether the answer is unambiguous, and it is *applied* only
by an explicit argument to :func:`read_header_totals`.  The separation is the
point.  A routine that tried each dialect until one balanced would report every
document as balanced, including the ones with genuinely missing rows, because
there is nearly always some combination of signs that closes.  Inference
produces a proposal and its evidence; a caller records the proposal as a
finding, and a document whose proposal disagrees with its institution's
prevailing dialect is a document to look at rather than to accept.

What this module does not do: it does not read transaction rows, and it does
not compare rows to totals.  Its output is the normalised block plus a verdict
on the block's internal arithmetic.  Comparing that block against extracted
rows is :mod:`services.financial.reconcile`, which works in the ledger's own
convention where direction is an enum and magnitudes are unsigned — a
representation that has no dialect problem, precisely because this module
resolved it at the door.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Iterable, Mapping, Optional, Sequence

from postgres.models.enums import ReconciliationStatus, TotalsConvention
from services.financial.money import Money, MoneyError, get_currency, parse_money


class StatementTotalsError(Exception):
    """The printed block could not be read as money at all."""


class UnreadableFigureError(StatementTotalsError):
    """A field held something that is not a finite monetary quantity."""


class ConventionError(StatementTotalsError):
    """A convention was required and the one supplied cannot be applied."""


# ---------------------------------------------------------------------------
# Roles and the alias table
# ---------------------------------------------------------------------------


class TotalsRole(str, Enum):
    """What a printed figure means, independent of what it is called.

    ``opening`` and ``closing`` are balances.  ``credits`` is the single
    inflow role.  Everything else is an outflow, and there are several because
    institutions itemise withdrawals differently: most print one combined
    figure, Chase business statements split it three ways.  Separate roles let
    all present outflows be summed without any risk of counting one twice,
    since the alias sets are disjoint.
    """

    opening = "opening"
    closing = "closing"
    credits = "credits"
    debits = "debits"
    checks = "checks"
    fees = "fees"
    atm_withdrawals = "atm_withdrawals"
    electronic_withdrawals = "electronic_withdrawals"
    other_withdrawals = "other_withdrawals"


#: Roles whose figures increase the balance across the period.
INFLOW_ROLES: tuple[TotalsRole, ...] = (TotalsRole.credits,)

#: Roles whose figures decrease it.  Summed, never first-match, because a
#: statement may itemise withdrawals across several of them at once.
OUTFLOW_ROLES: tuple[TotalsRole, ...] = (
    TotalsRole.debits,
    TotalsRole.checks,
    TotalsRole.fees,
    TotalsRole.atm_withdrawals,
    TotalsRole.electronic_withdrawals,
    TotalsRole.other_withdrawals,
)

#: Field names seen in the wild, mapped to the role they play, most common
#: first.  Every name here was observed in the ET-Fraud corpus; the counts in
#: the module docstring come from the same survey.  Extending this table is how
#: a new institution is supported, and it is deliberately the only thing that
#: needs to change.
#:
#: Two invariants hold and are enforced by :func:`_validate_alias_table` at
#: import: no name appears under two roles, and no name is repeated.  The first
#: is what makes summing the outflow roles safe.
FIELD_ALIASES: Mapping[TotalsRole, tuple[str, ...]] = {
    TotalsRole.opening: ("beginning_balance", "opening"),
    TotalsRole.closing: ("ending_balance", "closing"),
    TotalsRole.credits: (
        "deposits_credits",
        "deposits",
        "credits",
        "deposits_additions",
        "deposits_total",
        "total_additions",
    ),
    TotalsRole.debits: (
        "withdrawals_debits",
        "withdrawals",
        "debits",
        "total_subtractions",
    ),
    TotalsRole.checks: ("checks",),
    TotalsRole.fees: ("service_fees", "service_charges", "total_fees"),
    TotalsRole.atm_withdrawals: ("atm_debit_withdrawals",),
    TotalsRole.electronic_withdrawals: ("electronic_withdrawals",),
    TotalsRole.other_withdrawals: ("other_withdrawals",),
}


def _validate_alias_table(
    table: Mapping[TotalsRole, Sequence[str]]
) -> None:
    """Refuse to import with an alias table that could double-count.

    Checked at import rather than at call time because a collision is a
    permanent property of the table, and the failure it would otherwise cause
    is a wrong number rather than an exception.
    """
    seen: dict[str, TotalsRole] = {}
    for role, names in table.items():
        for name in names:
            if name in seen:
                raise ConventionError(
                    f"field {name!r} is listed under both {seen[name].value} "
                    f"and {role.value}; roles must be disjoint or summing the "
                    "outflow roles would count it twice"
                )
            seen[name] = role
    missing = set(TotalsRole) - set(table)
    if missing:
        raise ConventionError(
            "alias table has no entry for "
            + ", ".join(sorted(r.value for r in missing))
        )


_validate_alias_table(FIELD_ALIASES)


# ---------------------------------------------------------------------------
# Reading figures
# ---------------------------------------------------------------------------


def figure_to_money(value: object, currency: str, *, field: str) -> Money:
    """Convert one printed figure to exact money, refusing anything doubtful.

    Source documents arrive with these figures as JSON floats — all 30,570
    transaction amounts in the corpus are floats, and so is every header
    figure.  A float is converted by way of its shortest round-trip string,
    which recovers the decimal the extractor intended: ``str(279555.74)`` is
    ``'279555.74'`` exactly, not the binary approximation.

    What this cannot do is recover precision the float already lost, and it
    does not pretend to.  A figure carrying more decimal places than the
    currency has minor units raises rather than rounds, because a rounded cent
    in a control total is a delta of one cent in the identity, which is
    indistinguishable from a real one-cent error and far more misleading.

    Booleans are refused explicitly.  ``True`` is an ``int`` in Python and
    would otherwise read as one cent.

    Strings are delegated to :func:`~services.financial.money.parse_money`
    rather than handed to ``Decimal``.  A figure that reached this module as
    text has usually been through a layout, so it arrives formatted —
    ``'1,234.50'``, ``'$244.68'``, ``'(213.91)'``, ``'1.234,50'`` — and
    ``Decimal`` rejects every one of those as malformed.  Reporting a
    well-formed figure as unreadable is the same failure as reading it
    wrongly: in both cases the block loses a term and the identity stops being
    a check.

    The parse is ``strict``, which is the setting that matters here.  In its
    default mode ``parse_money`` resolves a single separator with three digits
    behind it — ``'1.234'``, ``'10.005'`` — by inferring that the separator
    groups, because the decimal reading is not representable in a two-digit
    currency.  That inference is right far more often than not and is recorded
    on the parse, which is enough for free text.  It is not enough for a
    control total, where the two readings differ by three orders of magnitude
    and the wrong one is a $10,005 figure standing in for $10.005 in the one
    block whose whole purpose is to be arithmetically checkable.  Under
    ``strict`` that case raises instead, which is the correct outcome for a
    module that resolves ambiguity by declaration rather than by inference:
    the document's separator convention is a fact about the document, and
    where it is needed it should be read from the document and passed in, as
    :class:`~postgres.models.enums.TotalsConvention` is.

    The underlying diagnosis is preserved in the message and in ``__cause__``,
    so a refusal still distinguishes an ambiguous separator from a figure that
    was never a number.
    """
    code = get_currency(currency).code

    if isinstance(value, bool):
        raise UnreadableFigureError(
            f"{field} holds a boolean; a flag is not a monetary figure"
        )
    if isinstance(value, Money):
        if value.currency != code:
            raise UnreadableFigureError(
                f"{field} is {value.currency} but the block is {code}"
            )
        return value
    if isinstance(value, Decimal):
        candidate = value
    elif isinstance(value, int):
        candidate = Decimal(value)
    elif isinstance(value, float):
        candidate = Decimal(repr(value))
    elif isinstance(value, str):
        try:
            return parse_money(value, code, strict=True)
        except MoneyError as exc:
            raise UnreadableFigureError(f"{field} holds {value!r}: {exc}") from exc
    else:
        raise UnreadableFigureError(
            f"{field} holds {type(value).__name__}, which is not a figure"
        )

    if not candidate.is_finite():
        raise UnreadableFigureError(
            f"{field} holds {candidate}, which is not a finite amount; a NaN "
            "in a control total silently zeroes every summary computed from it"
        )
    try:
        return Money.from_decimal(candidate, code)
    except MoneyError as exc:
        raise UnreadableFigureError(f"{field}: {exc}") from exc


def is_figure(value: object) -> bool:
    """Whether a raw value is a candidate figure, without converting it.

    Used to choose among aliases before any conversion is attempted, so that a
    role falls through to its next alias when the first is present but null,
    rather than raising on a field the document did not really carry.
    """
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float, Decimal, Money)) or (
        isinstance(value, str) and value.strip() not in ("", "-", "--")
    )


@dataclass(frozen=True, slots=True)
class FigureReading:
    """One printed figure, with the name it was printed under.

    The source field travels with the value because it is the audit trail for
    the normalisation: a reviewer asking why a document's withdrawals are
    $10,381.61 needs to know that the figure came from ``withdrawals_debits``
    and not from one of the five other names that could have supplied it.
    """

    role: TotalsRole
    source_field: str
    amount: Money


# ---------------------------------------------------------------------------
# The normalised block
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HeaderTotals:
    """A statement's printed control totals, normalised under one convention.

    ``unmapped`` carries the field names present in the source block that no
    role claimed.  It is kept rather than discarded because it is how a new
    naming variant announces itself: a document whose withdrawals arrive under
    an unrecognised name presents as having no outflows at all, which is a
    number that looks plausible and is wrong.  A harness that watches
    ``unmapped`` sees the drift; one that ignores it silently mis-reads.
    """

    currency: str
    convention: TotalsConvention
    opening: Optional[Money]
    closing: Optional[Money]
    inflows: tuple[FigureReading, ...]
    outflows: tuple[FigureReading, ...]
    unmapped: tuple[str, ...]

    @property
    def has_balances(self) -> bool:
        """Both endpoint balances were printed, so the identity can run."""
        return self.opening is not None and self.closing is not None

    @property
    def has_flows(self) -> bool:
        return bool(self.inflows or self.outflows)

    @property
    def is_testable(self) -> bool:
        """Enough was printed for the identity to mean something."""
        return self.has_balances and self.has_flows

    def figure(self, role: TotalsRole) -> Optional[Money]:
        """The amount read for one role, as printed, or None if absent."""
        for reading in self.inflows + self.outflows:
            if reading.role is role:
                return reading.amount
        if role is TotalsRole.opening:
            return self.opening
        if role is TotalsRole.closing:
            return self.closing
        return None

    @property
    def total_inflow(self) -> Money:
        return _sum(( r.amount for r in self.inflows), self.currency)

    @property
    def total_outflow(self) -> Money:
        """Outflow as a positive magnitude, whatever dialect it was printed in.

        Under ``signed`` the printed figures are already negative, so the sum
        is negated.  Doing that here rather than at each call site means the
        rest of the system sees one representation and never has to ask.

        The sum is negated; the terms are not individually made positive.  The
        difference is not cosmetic.  Taking each figure's absolute value would
        turn a reversed fee — a credit printed positive inside an otherwise
        negative block — into an additional charge, inflating the outflow by
        twice the reversal and breaking an identity that was correct.
        Negating the sum preserves the offset, which is what the statement
        meant.

        It is also what makes the two dialects distinguishable at all.  Under
        absolute values, ``signed`` and ``magnitude`` agree on every block
        whose figures are positive, so ``signed`` would close wherever
        ``magnitude`` did and the declaration would carry no information.
        Here they agree only when every outflow is zero, which is exactly the
        case :class:`TotalsConvention` calls ``undetermined``.
        """
        printed = _sum((r.amount for r in self.outflows), self.currency)
        if self.convention is TotalsConvention.signed:
            return -printed
        return printed

    @property
    def outflow_signs_coherent(self) -> bool:
        """Whether every printed outflow agrees with the declared convention.

        Under ``signed`` all non-zero outflows should be negative; under
        ``magnitude`` all should be positive.  A block that mixes them is not
        necessarily wrong — a reversed fee legitimately offsets a charge — but
        it is the shape a mis-declared convention takes, and it is worth
        surfacing rather than averaging away.
        """
        nonzero = [r.amount for r in self.outflows if not r.amount.is_zero]
        if not nonzero:
            return True
        if self.convention is TotalsConvention.signed:
            return all(a.is_negative for a in nonzero)
        if self.convention is TotalsConvention.magnitude:
            return all(a.is_positive for a in nonzero)
        return False


def _sum(amounts: Iterable[Money], currency: str) -> Money:
    total = Money.zero(currency)
    for amount in amounts:
        total = total + amount
    return total


def read_header_totals(
    raw: Mapping[str, object],
    *,
    currency: str,
    convention: TotalsConvention,
    aliases: Mapping[TotalsRole, Sequence[str]] = FIELD_ALIASES,
) -> HeaderTotals:
    """Normalise a raw printed block under an explicitly supplied convention.

    The convention is a required argument with no default, which is the whole
    discipline of this module expressed as a signature.  A caller that does not
    know the dialect must go and find out — from
    :func:`infer_convention`, from the institution's prevailing setting, or
    from a person — and the answer it used is then recorded on the result.
    """
    code = get_currency(currency).code
    if not isinstance(convention, TotalsConvention):
        raise ConventionError(
            f"convention must be a TotalsConvention, got "
            f"{type(convention).__name__}"
        )
    if convention is TotalsConvention.undetermined:
        raise ConventionError(
            "cannot normalise a block under 'undetermined'; that value records "
            "that the dialect is not yet known, and reading figures under it "
            "would be picking one while appearing not to"
        )
    if not isinstance(raw, Mapping):
        raise StatementTotalsError(
            f"header totals must be a mapping, got {type(raw).__name__}"
        )

    claimed: set[str] = set()
    readings: dict[TotalsRole, FigureReading] = {}

    for role, names in aliases.items():
        for name in names:
            if name in raw and is_figure(raw[name]):
                readings[role] = FigureReading(
                    role=role,
                    source_field=name,
                    amount=figure_to_money(raw[name], code, field=name),
                )
                claimed.add(name)
                break
            if name in raw:
                # Present but not a figure: the document mentioned the field
                # and left it empty.  Claim the name so it is not reported as
                # unmapped drift, and fall through to the next alias.
                claimed.add(name)

    opening = readings.pop(TotalsRole.opening, None)
    closing = readings.pop(TotalsRole.closing, None)

    return HeaderTotals(
        currency=code,
        convention=convention,
        opening=opening.amount if opening else None,
        closing=closing.amount if closing else None,
        inflows=tuple(
            readings[r] for r in INFLOW_ROLES if r in readings
        ),
        outflows=tuple(
            readings[r] for r in OUTFLOW_ROLES if r in readings
        ),
        unmapped=tuple(sorted(k for k in raw if k not in claimed)),
    )


# ---------------------------------------------------------------------------
# The identity over the printed block
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HeaderIdentityOutcome:
    """Whether a statement's own printed figures agree with each other.

    This is a weaker claim than :class:`~services.financial.reconcile.IdentityOutcome`
    and a necessary precondition for it.  A block that does not close against
    itself has been mis-read, and comparing extracted rows against a mis-read
    control total produces a delta that describes our reading of the header
    rather than anything about the rows.

    ``delta`` is ``computed_closing - printed_closing``, matching the sign
    convention used everywhere else in the package: positive means the figures
    produce more money than the statement says it ended with.
    """

    status: ReconciliationStatus
    convention: TotalsConvention
    opening: Optional[Money]
    printed_closing: Optional[Money]
    computed_closing: Optional[Money]
    delta: Optional[Money]
    signs_coherent: bool
    unavailable_reason: Optional[str]

    @property
    def is_balanced(self) -> bool:
        return self.status is ReconciliationStatus.balanced


def check_header_identity(totals: HeaderTotals) -> HeaderIdentityOutcome:
    """Apply the identity to a normalised block.  Pure: no database, no I/O.

    Declines rather than assumes, on the same grounds as the ledger-side check:
    a missing opening balance treated as zero yields a delta exactly equal to
    the real opening, which reads as a large unexplained discrepancy and sends
    a reviewer hunting for fraud in a document whose only defect is an
    unreadable top-of-page.
    """
    missing = [
        name
        for name, value in (("opening", totals.opening), ("closing", totals.closing))
        if value is None
    ]
    if missing or not totals.has_flows:
        if missing:
            reason = (
                f"the {' and '.join(missing)} balance"
                f"{'s were' if len(missing) > 1 else ' was'} not printed in the "
                "control block, and substituting zero would manufacture a delta "
                "equal to the real figure"
            )
        else:
            reason = (
                "the block printed both balances but no deposit or withdrawal "
                "figure, so there is nothing to check them against"
            )
        return HeaderIdentityOutcome(
            status=ReconciliationStatus.unavailable,
            convention=totals.convention,
            opening=totals.opening,
            printed_closing=totals.closing,
            computed_closing=None,
            delta=None,
            signs_coherent=totals.outflow_signs_coherent,
            unavailable_reason=reason,
        )

    opening = totals.opening
    printed_closing = totals.closing
    assert opening is not None and printed_closing is not None

    computed = opening + totals.total_inflow - totals.total_outflow
    delta = computed - printed_closing

    return HeaderIdentityOutcome(
        status=(
            ReconciliationStatus.balanced
            if delta.is_zero
            else ReconciliationStatus.unbalanced
        ),
        convention=totals.convention,
        opening=opening,
        printed_closing=printed_closing,
        computed_closing=computed,
        delta=delta,
        signs_coherent=totals.outflow_signs_coherent,
        unavailable_reason=None,
    )


# ---------------------------------------------------------------------------
# Inferring the convention, without applying it
# ---------------------------------------------------------------------------

#: The dialects a block may actually be written in.  ``undetermined`` is a
#: recorded state, not a way of reading figures, so it is not a candidate.
CANDIDATE_CONVENTIONS: tuple[TotalsConvention, ...] = (
    TotalsConvention.magnitude,
    TotalsConvention.signed,
)


@dataclass(frozen=True, slots=True)
class ConventionInference:
    """What the block's own arithmetic says about which dialect it is in.

    ``proposed`` is a suggestion and never an answer.  It is
    :attr:`TotalsConvention.undetermined` unless exactly one dialect closes the
    identity, because a block where both close — every outflow zero, most
    commonly — carries no evidence of its own dialect, and a block where
    neither closes is telling us something is wrong rather than which formula
    to prefer.

    ``balancing`` is the full set that closed, so a caller can tell those two
    cases apart, and ``deltas`` records what each dialect actually produced so
    that a near miss can be distinguished from a wild one without recomputing.
    """

    proposed: TotalsConvention
    balancing: frozenset[TotalsConvention]
    deltas: Mapping[TotalsConvention, Optional[Money]]
    testable: bool
    reason: str

    @property
    def is_evidenced(self) -> bool:
        """Exactly one dialect closes, so the block evidences its own."""
        return len(self.balancing) == 1

    @property
    def is_ambiguous(self) -> bool:
        """More than one dialect closes; the block cannot distinguish them."""
        return len(self.balancing) > 1

    @property
    def is_unexplained(self) -> bool:
        """The block was testable and no dialect closed it."""
        return self.testable and not self.balancing


def infer_convention(
    raw: Mapping[str, object],
    *,
    currency: str,
    aliases: Mapping[TotalsRole, Sequence[str]] = FIELD_ALIASES,
) -> ConventionInference:
    """Report which dialects close this block, and whether that is decisive.

    Deliberately returns evidence rather than performing a normalisation, so
    that no code path exists in which a document is read under whichever
    formula happened to work.  The caller must take the proposal, record it,
    and pass it back to :func:`read_header_totals` as an explicit argument.

    A document whose proposal contradicts the prevailing convention of its
    institution is the interesting case: it is either a genuine format change,
    which the institution's setting should follow, or an extraction that has
    gone wrong in a way that a sign flip happens to mask.  Both want a person.
    """
    code = get_currency(currency).code
    balancing: set[TotalsConvention] = set()
    deltas: dict[TotalsConvention, Optional[Money]] = {}
    testable = False

    for candidate in CANDIDATE_CONVENTIONS:
        totals = read_header_totals(
            raw, currency=code, convention=candidate, aliases=aliases
        )
        testable = testable or totals.is_testable
        outcome = check_header_identity(totals)
        deltas[candidate] = outcome.delta
        if outcome.is_balanced:
            balancing.add(candidate)

    if not testable:
        reason = (
            "the block does not carry both balances and at least one flow "
            "figure, so no dialect can be tested"
        )
        proposed = TotalsConvention.undetermined
    elif len(balancing) == 1:
        only = next(iter(balancing))
        other = next(c for c in CANDIDATE_CONVENTIONS if c is not only)
        miss = deltas[other]
        reason = (
            f"the identity closes under {only.value} and misses by "
            f"{miss.format() if miss is not None else 'an uncomputable amount'} "
            f"under {other.value}, so the block evidences its own dialect"
        )
        proposed = only
    elif balancing:
        reason = (
            "the identity closes under both dialects, which happens when every "
            "outflow figure is zero; the block carries no evidence of its own "
            "dialect and the institution's prevailing convention should decide"
        )
        proposed = TotalsConvention.undetermined
    else:
        magnitude_delta = deltas[TotalsConvention.magnitude]
        reason = (
            "no dialect closes the identity; the nearest miss is "
            f"{magnitude_delta.format() if magnitude_delta is not None else 'uncomputable'} "
            "under magnitude, so this is a reading to investigate rather than a "
            "dialect to choose"
        )
        proposed = TotalsConvention.undetermined

    return ConventionInference(
        proposed=proposed,
        balancing=frozenset(balancing),
        deltas=deltas,
        testable=testable,
        reason=reason,
    )
