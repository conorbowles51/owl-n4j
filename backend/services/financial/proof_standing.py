"""Where a case's evidence stands by proof class, and what each class licenses.

:mod:`services.financial.proof_class` computes the class and states what it
permits.  Four of its five predicates already have production callers.
:func:`~services.financial.proof_class.requires_adjudication` has none: it is
defined, it is exported, and nothing in the running system asks it.  That is
not a small omission, because it names the only class whose route into the
ledger is a recorded human act, and a rule nothing consults is a rule that is
not in force.  This module is the caller.

What it answers is case-shaped, in the same sense
:mod:`services.financial.decision_log` is: not "what class is this document",
which the row already carries, but how much of this matter's evidence sits in
each class, and what each of those classes is allowed to do.  Both halves are
returned together on purpose.  A count on its own invites the reader to supply
the meaning, and the meanings are not guessable -- p1 admits automatically
while p3 does not, and nothing about the labels says so.

One axis, and it is the class
-----------------------------

A document also carries a ``status`` and a transaction a ``ledger_status``,
and neither is filtered here.  A superseded duplicate is still p3; that is a
true statement about the document's arithmetic and it does not stop being true
because a later copy replaced it.  Mixing the two axes into one number would
make this read disagree with itself whenever the disposition moved and the
class did not, and would put the mixing rule inside a query where no caller
could see it.  A question that spans both axes -- "p3 documents currently
admitted" -- is a real question, and the answer to it is a query that states
both, not a default hidden in this one.

Every class is reported, including the ones with nothing in them
----------------------------------------------------------------

A class carrying zero documents is reported as carrying zero, rather than
omitted.  "This case has no p3 documents" and "nothing here looked at p3" are
different facts and an absent key spells them the same way.  p4 is reported
against transactions too, where its count is structurally zero because
``ck_financial_transactions_no_p4`` refuses the row; showing the zero is the
constraint made visible rather than a wasted line.

The counted set is a value
--------------------------

``included`` is reported back in the result and not merely applied.
:func:`~services.financial.proof_class.counts_toward_totals` exists in the
shape it does for this reason: a total has to state which classes it covers.
A census of the classes that would state its own coverage inaccurately would
be worse than the totals it is meant to explain.

An unrecognised stored class is refused, not skipped.  Both tables constrain
``proof_class`` to the vocabulary, so this is unreachable while the constraint
holds; if it ever stops holding, dropping the row would return a document
count lower than the case's documents with nothing saying why, which is the
one outcome this read exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable, Optional
from uuid import UUID

from sqlalchemy import func, select

from postgres.models.enums import ProofClass
from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
from services.financial.proof_class import (
    DEFAULT_TOTAL_CLASSES,
    admits_automatically,
    counts_toward_totals,
    may_produce_ledger_rows,
    requires_adjudication,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.orm import Session


class ProofStandingError(ValueError):
    """A census of proof classes was asked for something it cannot answer."""


@dataclass(frozen=True, slots=True)
class ClassStanding:
    """One proof class in one case: how much sits in it, and what it permits.

    The four booleans are read from
    :mod:`services.financial.proof_class` rather than restated here.  They are
    carried on the record instead of being left to the caller because the
    alternative is every reader re-deriving them from a two-character string,
    and a reader that gets ``requires_adjudication`` wrong shows unadjudicated
    material as admitted -- which is the failure the taxonomy exists to
    prevent.
    """

    #: The class itself, as the two-character value the column stores.
    proof_class: str
    #: Source documents in this case carrying this class, whatever their status.
    documents: int
    #: Ledger rows in this case carrying this class, whatever their status.
    transactions: int
    #: Enters the verified ledger with no human act.
    admits_automatically: bool
    #: A recorded human verdict is the only route into the ledger.
    requires_adjudication: bool
    #: May yield transaction rows at all.  False only for p4.
    may_produce_ledger_rows: bool
    #: Participates in an aggregate under the ``included`` set this census ran
    #: with.  Not a property of the class alone, which is why the set it was
    #: decided against is reported alongside it.
    counts_toward_totals: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "proof_class": self.proof_class,
            "documents": self.documents,
            "transactions": self.transactions,
            "admits_automatically": self.admits_automatically,
            "requires_adjudication": self.requires_adjudication,
            "may_produce_ledger_rows": self.may_produce_ledger_rows,
            "counts_toward_totals": self.counts_toward_totals,
        }


@dataclass(frozen=True, slots=True)
class ProofStanding:
    """A whole case's evidence, arranged by the class that was computed for it.

    ``documents`` and ``transactions`` are the case's totals across every
    class, so a reader can see that the per-class figures account for all of
    it.  They are summed from the same rows rather than counted again, which
    means the parts cannot fail to add up to the whole.
    """

    case_id: str
    #: Every class, in the enum's own order, present or not.
    classes: tuple[ClassStanding, ...]
    documents: int
    transactions: int
    #: The p3 population, named for what it means rather than for the class,
    #: because the label is what a reader cannot interpret unaided.
    documents_requiring_adjudication: int
    transactions_requiring_adjudication: int
    #: The classes this census counted as included in totals, reported so the
    #: coverage of any figure derived from it can be stated.
    counted_classes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "classes": [standing.as_dict() for standing in self.classes],
            "documents": self.documents,
            "transactions": self.transactions,
            "documents_requiring_adjudication": (
                self.documents_requiring_adjudication
            ),
            "transactions_requiring_adjudication": (
                self.transactions_requiring_adjudication
            ),
            "counted_classes": list(self.counted_classes),
        }


def _member(value: str, *, table: str) -> ProofClass:
    """One stored class string as its enum member, or a refusal naming it."""
    try:
        return ProofClass(value)
    except ValueError:
        raise ProofStandingError(
            f"{table} holds proof_class {value!r}, which is not a ProofClass; "
            "a census cannot say what it licenses and will not omit it "
            "silently"
        ) from None


def _validated_included(included: Any) -> frozenset[ProofClass]:
    """The counted set, refused unless it is made of real classes.

    A set of strings would leave every ``counts_toward_totals`` False and
    ``counted_classes`` reporting a coverage nothing was measured against --
    a wrong answer that looks exactly like a right one.
    """
    if not isinstance(included, (set, frozenset)):
        raise ProofStandingError(
            f"included must be a set of ProofClass members, got "
            f"{type(included).__name__}"
        )
    for member in included:
        if not isinstance(member, ProofClass):
            raise ProofStandingError(
                f"included holds {member!r}, which is not a ProofClass; the "
                "counted set is reported as the coverage of every figure "
                "derived from it and cannot be approximate"
            )
    return frozenset(included)


def _counts_by_class(
    session: "Session", model: Any, case_id: UUID
) -> dict[ProofClass, int]:
    """Rows of one table in one case, grouped by the class they carry.

    Counted in the database rather than by loading rows, because a case's
    ledger has no bound and this read is a census: the answer is the same
    size whether the case holds ten rows or a hundred thousand.
    """
    table = model.__tablename__
    grouped = session.execute(
        select(model.proof_class, func.count())
        .where(model.case_id == case_id)
        .group_by(model.proof_class)
    ).all()
    return {
        _member(value, table=table): int(count or 0) for value, count in grouped
    }


def case_proof_standing(
    session: "Session",
    case_id: UUID,
    *,
    included: Optional[Iterable[ProofClass]] = None,
) -> ProofStanding:
    """How one case's evidence stands by proof class.

    ``case_id`` is a mandatory positional and part of the WHERE clause rather
    than an optional filter, for the reason
    :func:`services.financial.decision_log.list_case_decisions` gives: an
    unscoped read of these tables crosses matters, and the rows would look
    entirely ordinary while doing it.

    ``included`` defaults to
    :data:`~services.financial.proof_class.DEFAULT_TOTAL_CLASSES`.  It is
    ``None`` in the signature rather than that constant directly so that a
    caller passing an empty set gets an empty set -- a census of a total that
    covers nothing is a strange thing to ask for, but it is answerable, and a
    default that swallowed it would answer a different question instead.

    This read never writes and never classifies.  It reports the class each
    row already carries; the only thing that computes a class is
    :func:`~services.financial.proof_class.assign_proof_class`, and the only
    thing that moves a stored one is
    :func:`services.financial.documents.reclassify_after_reconciliation`.
    """
    if case_id is None:
        raise ProofStandingError(
            "a proof class census needs a case; an unscoped read of these "
            "tables crosses matters"
        )

    counted = _validated_included(
        DEFAULT_TOTAL_CLASSES if included is None else included
    )

    documents = _counts_by_class(session, FinancialSourceDocument, case_id)
    transactions = _counts_by_class(session, FinancialTransaction, case_id)

    classes = tuple(
        ClassStanding(
            proof_class=member.value,
            documents=documents.get(member, 0),
            transactions=transactions.get(member, 0),
            admits_automatically=admits_automatically(member),
            requires_adjudication=requires_adjudication(member),
            may_produce_ledger_rows=may_produce_ledger_rows(member),
            counts_toward_totals=counts_toward_totals(member, included=counted),
        )
        for member in ProofClass
    )

    return ProofStanding(
        case_id=str(case_id),
        classes=classes,
        # Summed from the per-class figures rather than counted again, so the
        # parts cannot disagree with the whole.
        documents=sum(standing.documents for standing in classes),
        transactions=sum(standing.transactions for standing in classes),
        documents_requiring_adjudication=sum(
            standing.documents
            for standing in classes
            if standing.requires_adjudication
        ),
        transactions_requiring_adjudication=sum(
            standing.transactions
            for standing in classes
            if standing.requires_adjudication
        ),
        counted_classes=tuple(
            member.value for member in ProofClass if member in counted
        ),
    )
