"""Why a particular balance identity fails, recorded so the answer can be wrong.

A statement whose printed control block does not close is a fact about the
extraction, not yet a finding.  :mod:`services.financial.statement_totals`
reports the failure and stops there, which is correct: it can see that the
figures disagree but not why.  This module is what a person adds afterwards —
the explanation — and its whole design problem is that an explanation is the
one thing in this pipeline that a human supplies, and therefore the one thing
that can be self-serving.

The failure mode to guard against is not a wrong explanation.  It is an
unfalsifiable one.  "Extraction error" explains every failing document
equally well, costs nothing to assert, and cannot be checked by anybody.
Written into a report it reads as diligence and carries no information at all.
So the rule here is that **a verdict must owe an arithmetic debt that the
document either pays or does not**, and the debt is specific to the mechanism
being alleged:

* :attr:`BalanceFailure.opening_sign_dropped` alleges the reader lost a minus
  sign on the opening balance.  If that is what happened, the identity misses
  by *exactly twice* the printed opening — once for the balance being on the
  wrong side, once for it not being on the right one.  Any other residual
  refutes the claim outright.
* :attr:`BalanceFailure.rows_lost_in_extraction` alleges specific transactions
  were never recorded.  Then the named amounts must sum to the residual to the
  cent.  Naming approximately-right amounts fails.

Neither obligation is satisfiable by hand-waving, and both are enforced in
:meth:`Adjudication.__post_init__`, so a record that does not pay its debt
cannot be constructed at all.  That is deliberate: an unverifiable verdict
should not reach the database and then need catching in review.

**What this does not do is change the proof class.**  See
:class:`~postgres.models.enums.ProofClass`, which is assigned mechanically and
is never user-settable, "a class that a person could raise would be an opinion,
and the whole point of the taxonomy is that it is not one."  A document whose
arithmetic does not close is p3.  A well-corroborated adjudication explains why
it is p3; it does not make it p2.  Only fixing the reader and re-ingesting the
document can do that, because only then does the arithmetic actually close.
The distinction matters under cross-examination: the honest sentence is "we
know why this one fails and here is the corroboration", not "we decided this
one is fine."

Corroboration is graded because the corroborations genuinely differ in
strength, and a report that flattened them would overstate the weakest.  The
strongest evidence for a dropped opening balance is the *previous* statement on
the same account printing the same figure as a negative closing balance — an
independent document, produced by the institution, that we did not touch.  The
weakest is arithmetic alone, where the only thing supporting the verdict is
that the numbers work out.  Both are recorded; they are not recorded as the
same thing.  :attr:`Corroboration.chained_statement` exists because in this
corpus one corroborating predecessor is itself an adjudicated document, and
that dependency has to be visible rather than laundered into independence.

The vocabulary of failures is deliberately short.  Each member was earned by
documents that could not be explained any other way, and adding one should
require the same: a mechanism, a residual it predicts, and a document that
pays the debt.  A general-purpose "other" member would defeat the module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from services.financial.money import Money, sum_money


class AdjudicationError(Exception):
    """A proposed verdict is not admissible as recorded."""


class UnpaidObligationError(AdjudicationError):
    """The arithmetic the verdict predicts is not the arithmetic observed.

    Raised when a record claims a mechanism whose residual does not match the
    one the document actually shows.  This is the check that makes a verdict a
    claim rather than a label.
    """


class MalformedVerdictError(AdjudicationError):
    """The record is internally inconsistent or missing what its class needs.

    A dropped sign with no printed opening balance, a lost-rows verdict naming
    no rows, or a corroboration that cites a document under a grade that has
    no document to cite.
    """


class BalanceFailure(str, Enum):
    """The mechanism alleged to have broken a statement's balance identity.

    Which mechanism is even possible depends on whether the printed flow
    totals are independent evidence.  If the deposits and withdrawals figures
    in the header differ from the sum of the extracted rows, they were printed
    by the institution, and a failing identity implicates one of the three
    *balances* — because the flows are corroborated by the rows disagreeing
    with them in the ordinary way.  If the header figures equal the row sums
    to the cent, the header was computed from the rows and carries no
    independent information; then the identity can only fail because the rows
    themselves are wrong.

    That test is mechanical and should be run before choosing a member here.
    It is the difference between a verdict and a guess about which of two
    equally plausible stories to tell.
    """

    opening_sign_dropped = "opening_sign_dropped"
    """The account was overdrawn and the reader recorded the opening balance
    as a positive number.

    Predicts a residual of exactly twice the printed opening balance, with the
    printed figure positive and the true one its negation.  Distinguishable
    from a dropped sign on the *closing* balance, or on the checks or fees
    totals, because those predict different residuals; a verdict of this class
    should not be recorded until the alternatives have been tried and failed.
    """

    rows_lost_in_extraction = "rows_lost_in_extraction"
    """One or more transactions on the page were never recorded as rows.

    Predicts a residual equal to the net of the missing amounts.  Note that
    the residual alone cannot distinguish a *lost* debit from an *invented*
    credit of the same size: both leave the identity short by the same
    amount.  Only the document text separates them, so this verdict requires
    reading the page, not just the arithmetic.
    """


class Corroboration(str, Enum):
    """How strongly the verdict is supported by evidence other than its own
    arithmetic, weakest first."""

    arithmetic_only = "arithmetic_only"
    """Nothing supports the verdict but the fact that the numbers close.

    Admissible, and weak.  The obligation is real — most wrong explanations
    fail it — but a residual that matches a prediction is consistent with the
    mechanism rather than proof of it.  Typically this grade means the
    corroborating document simply is not in the corpus.
    """

    same_document = "same_document"
    """Evidence inside the same document supports the verdict.

    A fragment of a lost transaction stranded in an adjacent row's text, or a
    running balance sequence that is internally consistent only if the alleged
    rows existed.  Stronger than arithmetic because it is textual: it names
    the missing item rather than inferring its size.
    """

    adjacent_statement = "adjacent_statement"
    """The neighbouring statement on the same account, whose own identity
    closes, prints the disputed figure.

    The strongest grade available here.  The corroborating document is
    separate, produced by the institution, covers the contiguous period, and
    was not itself in question.
    """

    chained_statement = "chained_statement"
    """The neighbouring statement prints the disputed figure, but that
    statement is itself adjudicated rather than closing on its own arithmetic.

    Recorded separately from :attr:`adjacent_statement` so that a chain of
    dependent verdicts cannot be presented as a set of independent ones.  If
    the earlier verdict is overturned, this one loses its support.
    """


#: Grades that name another document and therefore require one.
_CITING_GRADES = frozenset(
    {Corroboration.adjacent_statement, Corroboration.chained_statement}
)


@dataclass(frozen=True, slots=True)
class Adjudication:
    """One recorded verdict on one document's failing balance identity.

    Construction is validated.  A record that does not pay the arithmetic debt
    its :attr:`failure` implies raises :class:`UnpaidObligationError` rather
    than being stored and reviewed later.
    """

    document: str
    """Identifier of the document whose identity fails."""

    failure: BalanceFailure
    """The mechanism alleged."""

    residual: Money
    """By how much the identity misses, computed as printed.

    This is ``opening + inflows - outflows - closing`` under the document's
    declared convention: the quantity that would be zero if the block were
    consistent.  It is the observation the verdict must account for, so it is
    recorded here rather than recomputed, and it is signed.
    """

    corroboration: Corroboration
    """How strongly the verdict is supported beyond its own arithmetic."""

    reason: str
    """What a reader needs in order to check the verdict themselves.

    Prose, and required.  The arithmetic is enforced by this class; the reason
    is where the evidence that arithmetic cannot capture goes — which row
    stranded the fragment, which page boundary, which neighbouring statement.
    """

    printed_opening: Optional[Money] = None
    """The opening balance as the reader recorded it.

    Required by :attr:`BalanceFailure.opening_sign_dropped` and forbidden
    otherwise.  Positive, since the allegation is that a negative figure was
    recorded without its sign; see :attr:`restated_opening` for the correction.
    """

    missing_outflows: tuple[Money, ...] = field(default_factory=tuple)
    """Net amounts of the transactions alleged to be missing, as outflows.

    Required by :attr:`BalanceFailure.rows_lost_in_extraction` and forbidden
    otherwise.  Amounts are individually positive and must sum to
    :attr:`residual`.  Where a single unextracted block contained offsetting
    movements, its *net* outflow is recorded as one entry, because the net is
    what the identity can see; the components belong in :attr:`reason`.
    """

    corroborating_document: Optional[str] = None
    """The document cited by :attr:`corroboration`.

    Required for :attr:`Corroboration.adjacent_statement` and
    :attr:`Corroboration.chained_statement`, forbidden for the other grades,
    so that a citing grade can never be recorded without the citation.
    """

    def __post_init__(self) -> None:
        if not self.document:
            raise MalformedVerdictError("an adjudication must name its document")
        if not self.reason or not self.reason.strip():
            raise MalformedVerdictError(
                f"{self.document}: a verdict without a reason cannot be checked "
                "by anyone, which is the failure mode this module exists to prevent"
            )
        if self.residual.is_zero:
            raise MalformedVerdictError(
                f"{self.document}: an identity that closes needs no adjudication"
            )

        if self.corroboration in _CITING_GRADES:
            if not self.corroborating_document:
                raise MalformedVerdictError(
                    f"{self.document}: corroboration {self.corroboration.value} "
                    "cites another statement and must name it"
                )
            if self.corroborating_document == self.document:
                raise MalformedVerdictError(
                    f"{self.document}: a document cannot corroborate itself under "
                    f"{self.corroboration.value}"
                )
        elif self.corroborating_document is not None:
            raise MalformedVerdictError(
                f"{self.document}: corroboration {self.corroboration.value} does not "
                "rest on another document, so naming one overstates the evidence"
            )

        if self.failure is BalanceFailure.opening_sign_dropped:
            self._check_opening_sign_dropped()
        elif self.failure is BalanceFailure.rows_lost_in_extraction:
            self._check_rows_lost()
        else:  # pragma: no cover - unreachable while the enum has two members
            raise MalformedVerdictError(
                f"{self.document}: no obligation is defined for {self.failure!r}, "
                "so the verdict could not be checked"
            )

    def _check_opening_sign_dropped(self) -> None:
        if self.missing_outflows:
            raise MalformedVerdictError(
                f"{self.document}: a dropped sign does not lose rows; the verdict "
                "names both and is two claims, not one"
            )
        opening = self.printed_opening
        if opening is None:
            raise MalformedVerdictError(
                f"{self.document}: opening_sign_dropped must record the opening "
                "balance as printed, since the obligation is stated in terms of it"
            )
        if not opening.is_positive:
            raise MalformedVerdictError(
                f"{self.document}: the printed opening is {opening.format()}, which "
                "already carries a sign; there is no dropped sign to allege"
            )
        expected = opening * 2
        if self.residual != expected:
            raise UnpaidObligationError(
                f"{self.document}: a dropped sign on an opening balance of "
                f"{opening.format()} predicts a residual of {expected.format()}, but "
                f"the identity misses by {self.residual.format()}. Some other "
                "mechanism is at work."
            )

    def _check_rows_lost(self) -> None:
        if self.printed_opening is not None:
            raise MalformedVerdictError(
                f"{self.document}: rows_lost_in_extraction makes no claim about the "
                "opening balance, so recording one is misleading"
            )
        if not self.missing_outflows:
            raise MalformedVerdictError(
                f"{self.document}: rows_lost_in_extraction must name the amounts it "
                "alleges were lost; 'some rows are missing' is not falsifiable"
            )
        for amount in self.missing_outflows:
            if not amount.is_positive:
                raise MalformedVerdictError(
                    f"{self.document}: missing outflow {amount.format()} is not a "
                    "positive magnitude; direction is carried by the field, not the sign"
                )
        total = sum_money(self.missing_outflows, self.residual.currency)
        if total != self.residual:
            raise UnpaidObligationError(
                f"{self.document}: the named rows total {total.format()} but the "
                f"identity misses by {self.residual.format()}. Rows that do not "
                "account for the residual do not explain it."
            )

    @property
    def restated_opening(self) -> Optional[Money]:
        """The opening balance the verdict says the statement actually printed.

        ``None`` for failure classes that make no claim about it.  This is the
        correction, not a stored figure: it is what re-extraction should
        produce, and comparing the two after a reader fix is how the verdict
        gets confirmed or refuted mechanically.
        """
        if self.failure is not BalanceFailure.opening_sign_dropped:
            return None
        assert self.printed_opening is not None  # guaranteed by __post_init__
        return -self.printed_opening

    @property
    def is_independently_corroborated(self) -> bool:
        """Whether some evidence outside this verdict's own arithmetic supports it.

        True for every grade except :attr:`Corroboration.arithmetic_only`.
        Note that :attr:`Corroboration.chained_statement` counts here while
        still depending on another verdict; the dependency is visible in
        :attr:`corroboration` and callers that care must look at it.
        """
        return self.corroboration is not Corroboration.arithmetic_only


def restatement_delta(adjudication: Adjudication) -> Money:
    """How much the restated document differs from the one on file.

    For a dropped opening sign this is twice the printed opening, which is the
    residual — the correction closes the identity exactly, by construction.
    For lost rows it is the total of the missing amounts, which is also the
    residual.  The function exists so that a report can state the size of the
    correction without knowing which mechanism produced it, and its agreement
    with :attr:`Adjudication.residual` in both cases is the point rather than
    a coincidence: a verdict that closes the identity is one whose correction
    is exactly the amount by which it missed.
    """
    return adjudication.residual
