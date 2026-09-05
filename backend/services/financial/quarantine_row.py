"""Setting one stored ledger row aside, and letting it back in.

:mod:`~services.financial.quarantine` holds the two writers and refuses
anything it cannot ground.  What it does not do is find the row.  Both writers
take a ``FinancialTransaction`` already in hand and a ``case_id`` given
separately, and :func:`~services.financial.decisions.record` compares the two
and raises :class:`~services.financial.decisions.CrossCaseError` when they
disagree.  That check is a last line, not a lookup: it can only fire once
somebody has already loaded a row belonging to another matter.  This module is
the caller that supplies the missing half -- resolve the row *within* the case,
build the actor from the person making the request, and turn every way the
writers can refuse into a word.

Why a refusal is not an error
-----------------------------

``quarantine_transaction`` and ``release_transaction`` raise
:class:`~services.financial.quarantine.UngroundedQuarantineError` for four
different things, and every one of them is a true statement about the state of
the ledger rather than a fault: the row is already quarantined on other
grounds, the row is superseded and so already outside every total, the row is
not quarantined and there is nothing to release, the grounds given were empty.
A person looking at a ledger row has no way to know any of that before
clicking, because the row on screen was fetched before somebody else acted on
it.  So these return ``refused`` carrying the writer's own sentence, and the
interface can put it beside the row.  Only a database fault becomes an error
status, because there is nothing the person can do with it.

Why an unchanged row is reported separately
-------------------------------------------

``quarantine_transaction`` is deliberately idempotent for a row already
quarantined on the same grounds: it appends nothing and returns the row, on the
reasoning that an event claiming a change that did not happen dilutes the log.
That is right for the writer and wrong for the response, which would otherwise
say ``quarantined`` and name an adjudication that belongs to somebody else's
earlier decision.  The status is checked before the call so the caller is told
the row was already set aside, and no adjudication id is claimed.

Why the person's name reaches the row twice
-------------------------------------------

``QuarantineBasis.from_adjudication`` folds the actor's name into the detail
string, and ``record`` writes ``actor_name`` and ``actor_email`` as columns.
That is not redundancy.  The columns are what a review joins and filters on;
the detail is the sentence that becomes the adjudication's ``reason`` and is
the only part a reader sees next to the row.  A detail reading "the amount is
illegible" with no name in it would be correct and useless in a list of
decisions taken by four people.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy.exc import SQLAlchemyError

from postgres.models.enums import AdjudicationSubject, LedgerStatus, QuarantineReason
from postgres.models.financial import FinancialTransaction
from services.financial.decisions import Actor, DecisionError, history
from services.financial.quarantine import (
    QuarantineBasis,
    UngroundedQuarantineError,
    quarantine_transaction,
    release_transaction,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class RowAdjudicationOutcome(str, Enum):
    """What the attempt came to, in one word per thing the caller can do next."""

    #: The row is quarantined and a decision was appended naming who and why.
    quarantined = "quarantined"
    #: The row is admitted again and the reversal was appended.
    released = "released"
    #: The row was already in the state asked for, on the same grounds.
    #: Nothing was appended, so no adjudication is named.
    unchanged = "unchanged"
    #: No such row in this case.  Reported identically to a row in another
    #: case, so that asking cannot be used to learn what a case the caller
    #: cannot see contains.
    not_found = "not_found"
    #: The writers would not do it, and said why.  A fact about the ledger's
    #: current state, not a fault.
    refused = "refused"
    #: The write itself failed.  Discarded and logged.
    write_failed = "write_failed"


@dataclass(frozen=True, slots=True)
class RowAdjudication:
    """One attempt to change a row's standing, and what became of it."""

    transaction_id: str
    outcome: RowAdjudicationOutcome
    reason: Optional[str] = None
    #: The row's status after the attempt, absent when the row was not found.
    ledger_status: Optional[str] = None
    quarantine_reason: Optional[str] = None
    #: Set only when a decision was actually appended.
    adjudication_id: Optional[str] = None

    @property
    def applied(self) -> bool:
        """Whether this attempt changed the row."""
        return self.outcome in (
            RowAdjudicationOutcome.quarantined,
            RowAdjudicationOutcome.released,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "outcome": self.outcome.value,
            "applied": self.applied,
            "reason": self.reason,
            "ledger_status": self.ledger_status,
            "quarantine_reason": self.quarantine_reason,
            "adjudication_id": self.adjudication_id,
        }


class ActorError(Exception):
    """Raised when the requesting user cannot be turned into an actor."""


def actor_from_user(user: Any) -> Actor:
    """The logged-in user as an adjudicating actor.

    Read through ``getattr`` rather than typed against
    :class:`~postgres.models.user.User`, which is how
    :mod:`~services.financial.runs` already reads an actor, and which keeps
    this package from importing the auth model to write one string.

    ``user_id`` is carried so a decision can be joined back to the account that
    took it.  ``name`` and ``email`` are copied rather than joined because a
    decision has to stay readable after the account is renamed or removed; that
    is why :class:`~services.financial.decisions.Actor` holds all three.
    """
    name = getattr(user, "name", None)
    email = getattr(user, "email", None)
    if not isinstance(name, str) or not name.strip():
        raise ActorError(
            "the requesting user has no name; a decision with nobody's name on "
            "it cannot be reviewed"
        )
    if not isinstance(email, str) or not email.strip():
        raise ActorError(
            "the requesting user has no email address; a decision nobody can "
            "be asked about cannot be reviewed"
        )
    user_id = getattr(user, "id", None)
    return Actor(
        name=name.strip(),
        email=email.strip(),
        user_id=user_id if isinstance(user_id, uuid.UUID) else None,
    )


def find_case_transaction(
    session: "Session", *, case_id: uuid.UUID, transaction_id: uuid.UUID
) -> Optional[FinancialTransaction]:
    """One ledger row, but only if it belongs to this case.

    The case is part of the filter rather than checked afterwards, so a row in
    another matter is indistinguishable from one that does not exist.
    """
    return (
        session.query(FinancialTransaction)
        .filter(
            FinancialTransaction.id == transaction_id,
            FinancialTransaction.case_id == case_id,
        )
        .first()
    )


def _latest_adjudication_id(
    session: "Session", transaction: FinancialTransaction
) -> Optional[str]:
    """The decision just appended about this row.

    The writers return the row rather than the event, so the event is read back
    through :func:`~services.financial.decisions.history`, which orders by
    ``subject_sequence`` -- the only column here that can carry an order, for
    the reason its own docstring gives.  ``record`` flushes, so the row is
    already there to be read.
    """
    events = history(session, transaction, AdjudicationSubject.transaction)
    return str(events[-1].id) if events else None


def _not_found(transaction_id: uuid.UUID) -> RowAdjudication:
    return RowAdjudication(
        transaction_id=str(transaction_id),
        outcome=RowAdjudicationOutcome.not_found,
        reason="No such transaction in this case.",
    )


def _current(
    transaction: FinancialTransaction,
    outcome: RowAdjudicationOutcome,
    *,
    reason: Optional[str] = None,
    adjudication_id: Optional[str] = None,
) -> RowAdjudication:
    return RowAdjudication(
        transaction_id=str(transaction.id),
        outcome=outcome,
        reason=reason,
        ledger_status=transaction.ledger_status,
        quarantine_reason=transaction.quarantine_reason,
        adjudication_id=adjudication_id,
    )


def quarantine_case_row(
    session: "Session",
    *,
    case_id: uuid.UUID,
    transaction_id: uuid.UUID,
    actor: Any,
    reason: str,
) -> RowAdjudication:
    """Set one row aside on a person's authority, and record who and why.

    The only grounds this function can produce are
    :attr:`~postgres.models.enums.QuarantineReason.adjudicated`.  The computed
    grounds -- a proved break in a statement's own running balance, a currency
    that cannot be summed with its period, a delta the identity cannot explain
    -- are decided against a reconciled period rather than against a request,
    and belong with the code that reconciles.  A person cannot type them, and
    an endpoint that let them be typed would let a class a person raised be
    mistaken for one the arithmetic proved.

    The caller's ``session`` is committed here on success.  Nothing under
    ``services.financial`` commits, so a caller that did not would return a
    response describing a decision that was about to be discarded.
    """
    transaction = find_case_transaction(
        session, case_id=case_id, transaction_id=transaction_id
    )
    if transaction is None:
        return _not_found(transaction_id)

    already_adjudicated = (
        transaction.ledger_status == LedgerStatus.quarantined.value
        and transaction.quarantine_reason == QuarantineReason.adjudicated.value
    )
    if already_adjudicated:
        # quarantine_transaction is idempotent here and would append nothing,
        # so saying "quarantined" would name somebody else's earlier decision.
        return _current(
            transaction,
            RowAdjudicationOutcome.unchanged,
            reason="This row was already set aside by a person.",
        )

    try:
        actor_record = actor_from_user(actor)
    except ActorError as exc:
        return _current(
            transaction, RowAdjudicationOutcome.refused, reason=str(exc)
        )

    try:
        basis = QuarantineBasis.from_adjudication(
            actor=actor_record.name, reason=reason
        )
    except UngroundedQuarantineError as exc:
        return _current(
            transaction, RowAdjudicationOutcome.refused, reason=str(exc)
        )

    try:
        quarantine_transaction(
            session,
            transaction,
            basis,
            case_id=case_id,
            actor=actor_record,
        )
        adjudication_id = _latest_adjudication_id(session, transaction)
        session.commit()
    except (UngroundedQuarantineError, DecisionError) as exc:
        # A statement about the row's current standing, not a fault.  The
        # rollback discards the appended decision along with it, which is the
        # point: the two move together or neither does.
        session.rollback()
        return _current(
            transaction, RowAdjudicationOutcome.refused, reason=str(exc)
        )
    except SQLAlchemyError as exc:
        session.rollback()
        logger.exception(
            "Failed to quarantine transaction %s in case %s",
            transaction_id,
            case_id,
        )
        return RowAdjudication(
            transaction_id=str(transaction_id),
            outcome=RowAdjudicationOutcome.write_failed,
            reason=str(exc),
        )

    return _current(
        transaction,
        RowAdjudicationOutcome.quarantined,
        adjudication_id=adjudication_id,
    )


def release_case_row(
    session: "Session",
    *,
    case_id: uuid.UUID,
    transaction_id: uuid.UUID,
    actor: Any,
    reason: str,
) -> RowAdjudication:
    """Return one quarantined row to the admitted set, recording the reversal.

    Every quarantine is releasable here, including the computed ones.  That is
    deliberate and it is not a way of overruling the arithmetic: the row's
    reason column is nulled by the constraint's requirement, but the decision
    that set it aside stays in the log with its grounds, and this reversal is
    appended after it naming the person who took it.  A break in a printed
    running balance is a fact about the document, and whether the row that
    breaks it is the wrong one is a judgement.

    The caller's ``session`` is committed here on success, for the reason
    :func:`quarantine_case_row` gives.
    """
    transaction = find_case_transaction(
        session, case_id=case_id, transaction_id=transaction_id
    )
    if transaction is None:
        return _not_found(transaction_id)

    try:
        actor_record = actor_from_user(actor)
    except ActorError as exc:
        return _current(
            transaction, RowAdjudicationOutcome.refused, reason=str(exc)
        )

    try:
        release_transaction(
            session,
            transaction,
            case_id=case_id,
            actor=actor_record,
            reason=reason,
        )
        adjudication_id = _latest_adjudication_id(session, transaction)
        session.commit()
    except (UngroundedQuarantineError, DecisionError) as exc:
        session.rollback()
        return _current(
            transaction, RowAdjudicationOutcome.refused, reason=str(exc)
        )
    except SQLAlchemyError as exc:
        session.rollback()
        logger.exception(
            "Failed to release transaction %s in case %s",
            transaction_id,
            case_id,
        )
        return RowAdjudication(
            transaction_id=str(transaction_id),
            outcome=RowAdjudicationOutcome.write_failed,
            reason=str(exc),
        )

    return _current(
        transaction,
        RowAdjudicationOutcome.released,
        adjudication_id=adjudication_id,
    )
