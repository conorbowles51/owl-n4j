"""Every decision about financial evidence, appended before the row changes.

``financial_adjudications`` was built to be the append-only record of who did
what to which piece of evidence and why.  Until this module there was exactly
one writer — :func:`services.financial.duplicates.purge_document` — and the
consequence was not that the log was thin.  It was that **the log recorded the
dispositions and none of the reversals**, which is the wrong half.

The row-level columns cannot carry a reversal, and this is by design rather
than by oversight.  ``ck_financial_transactions_quarantine_coherent`` requires
``(quarantine_reason IS NOT NULL) = (ledger_status = 'quarantined')``, so a
released row *must* have its reason nulled; the migration that added it says
so in as many words — "a row carrying a reason while admitted describes a
decision that was reversed, and a reader cannot tell that from a decision that
was taken."  That is right.  It also means the schema deliberately pushes the
history of the reversal somewhere else, and the somewhere else is this table.
:func:`release_transaction` was validating an actor and a reason, then
discarding both and nulling the grounds, leaving a readmitted row
byte-identical to one that was never set aside.  The check constraint was
doing its job.  Nothing was doing the other half.

So the rule this module exists to enforce is: **the event is written before
the state changes, or the state does not change.**

Four things are checked here that the database cannot check for itself.

*The subject exists and is what the caller says it is.*  ``subject_id`` carries
no foreign key, because a decision has to outlive the row it was about and a
cascade would delete the audit trail at the moment it mattered.  The model
docstring says the integrity is "checked in the service layer instead", and
:func:`record` is that service layer: it takes the mapped object, not a bare
id, so ``subject_type`` cannot disagree with what was actually acted on.

*The subject is in the matter being written to.*  A decision filed against
another firm's case is a confidentiality breach rather than a bug, which is
why it raises :class:`~services.financial.duplicates.CrossCaseError`.

*``before`` and ``after`` describe the same fields.*  A before/after pair is a
diff, and a diff whose two sides list different keys cannot be read: a missing
key on the right is indistinguishable from a field that was cleared.  Both
sides may be ``None`` — the subject did not exist, or no longer does — but two
dicts must agree on their keys, and must not be equal, because an event
claiming a change where none occurred dilutes the log it is written to.

*No floats reach the payload.*  The whole ledger is integer minor units for
the reason set out in :mod:`services.financial.money`; a before/after snapshot
is the one place where an amount could re-enter as binary floating point,
round on the way in, and be quoted later as the figure of record.

A fifth thing is not checked but assigned: ``subject_sequence``.  A log whose
purpose is sequence has to be able to state one, and ``created_at`` cannot.
See :class:`~postgres.models.financial.FinancialAdjudication` for why; the
consequence here is that :func:`record` reads the subject's current high-water
mark and writes one past it, in the same flush as the row.
"""

from __future__ import annotations

import datetime as _datetime
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Mapping, Optional

from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
from postgres.models.financial import (
    FinancialAccount,
    FinancialAdjudication,
    FinancialSourceDocument,
    FinancialStatementPeriod,
    FinancialTransaction,
)
from services.financial.money import Money

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.orm import Session


class DecisionError(Exception):
    """Raised when a decision cannot be recorded as stated."""


class SubjectMismatchError(DecisionError):
    """Raised when ``subject_type`` does not describe the object handed over.

    Its own type because it is the failure that would put a decision in the
    log against the wrong kind of evidence, where it reads as authoritative
    and is simply about something else.
    """


class MalformedSnapshotError(DecisionError):
    """Raised when ``before``/``after`` cannot be read as a diff."""


# The one place the string in ``subject_type`` is tied to a table.  Kept as a
# mapping rather than inferred from ``__tablename__`` so that renaming a table
# is a decision someone makes here, in view of the vocabulary, rather than a
# silent change to the meaning of every historical row.
_SUBJECT_MODELS: dict[AdjudicationSubject, type] = {
    AdjudicationSubject.transaction: FinancialTransaction,
    AdjudicationSubject.statement_period: FinancialStatementPeriod,
    AdjudicationSubject.source_document: FinancialSourceDocument,
    AdjudicationSubject.account: FinancialAccount,
}


@dataclass(frozen=True)
class Actor:
    """Who decided.  One object so the name and the address cannot drift apart.

    ``user_id`` is optional and the other two are not, which is the same trade
    the ingestion run table makes: the account may be deleted later, and a
    deleted account must not erase who decided what, so the name and address
    are copied in at the time of the decision rather than joined at read time.
    """

    name: str
    email: str
    user_id: Optional[uuid.UUID] = None

    def __post_init__(self) -> None:
        for field_name in ("name", "email"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise DecisionError(
                    f"an actor needs a {field_name}; a decision with nobody's "
                    "name on it cannot be reviewed"
                )


def _jsonable(value: Any, path: str) -> Any:
    """Convert a snapshot value to something JSONB can hold, or refuse it.

    Refusing is the point.  A value that psycopg cannot adapt fails at flush
    time, a long way from the call that built it, with a message about a type
    rather than about a field.
    """
    if value is None or isinstance(value, (bool, int, str)):
        # bool before int is not needed here because both are accepted, but
        # note that `isinstance(True, int)` is true, so any future numeric
        # narrowing has to test bool first.
        return value
    if isinstance(value, float):
        raise MalformedSnapshotError(
            f"{path} is a float ({value!r}); this ledger holds money as "
            "integer minor units, and a snapshot is exactly where a rounded "
            "amount would re-enter and later be quoted as the figure of "
            "record. Pass a Money, or an int if it is not money."
        )
    if isinstance(value, Money):
        return {"minor_units": value.minor_units, "currency": value.currency}
    if isinstance(value, Enum):
        return _jsonable(value.value, path)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (_datetime.datetime, _datetime.date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        out = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise MalformedSnapshotError(
                    f"{path} has a non-string key {key!r}; JSON object keys "
                    "are strings, and letting one be coerced would make two "
                    "different keys collide silently"
                )
            out[key] = _jsonable(item, f"{path}.{key}")
        return out
    if isinstance(value, (list, tuple)):
        return [_jsonable(item, f"{path}[{i}]") for i, item in enumerate(value)]
    raise MalformedSnapshotError(
        f"{path} is a {type(value).__name__}, which has no agreed JSON form. "
        "Convert it at the call site, where it is known what it means."
    )


def _snapshot(value: Optional[Mapping[str, Any]], side: str) -> Optional[dict]:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise MalformedSnapshotError(
            f"{side} must be a mapping of field name to value, or None; "
            f"got {type(value).__name__}"
        )
    return _jsonable(dict(value), side)


def _check_diff(before: Optional[dict], after: Optional[dict]) -> None:
    if before is None or after is None:
        return
    if before.keys() != after.keys():
        only_before = sorted(before.keys() - after.keys())
        only_after = sorted(after.keys() - before.keys())
        raise MalformedSnapshotError(
            "before and after must describe the same fields, or the pair "
            "cannot be read as a diff: a key missing on one side is "
            "indistinguishable from a field that was cleared. "
            f"only in before: {only_before}; only in after: {only_after}"
        )
    if before == after:
        raise MalformedSnapshotError(
            "before and after are identical, so this event claims a change "
            "that did not happen. Record a review with before=None and "
            "after=None, or leave the log alone."
        )


def _next_sequence(
    session: "Session",
    subject_type: AdjudicationSubject,
    subject_id: uuid.UUID,
) -> int:
    """One past the highest sequence recorded about this subject.

    Two transactions deciding about the same subject at the same time will both
    read the same high-water mark and both try to write one past it.  The
    unique constraint refuses the second, which is the outcome to want: the
    alternative is two decisions claiming the same position in a history, and a
    reader with no way to tell which came first.  The caller sees an
    ``IntegrityError`` and retries, having lost nothing — :func:`record` is
    called before the mutation, so nothing has changed yet.
    """
    from sqlalchemy import func, select

    highest = session.scalar(
        select(func.max(FinancialAdjudication.subject_sequence))
        .where(FinancialAdjudication.subject_type == subject_type.value)
        .where(FinancialAdjudication.subject_id == subject_id)
    )
    return 1 if highest is None else int(highest) + 1


def record(
    session: "Session",
    *,
    case_id: uuid.UUID,
    subject: Any,
    subject_type: AdjudicationSubject,
    decision: AdjudicationDecision,
    reason: str,
    actor: Actor,
    before: Optional[Mapping[str, Any]] = None,
    after: Optional[Mapping[str, Any]] = None,
    ingestion_run_id: Optional[uuid.UUID] = None,
) -> FinancialAdjudication:
    """Append one decision.  Call this *before* mutating ``subject``.

    Returns the flushed row, so the caller holds a decision with an identity
    even if the mutation that follows raises.  ``before`` is therefore read
    from the subject as it still stands; ``after`` is what the caller is about
    to write.
    """
    # Deferred so this module can be imported without a cycle: duplicates
    # imports from here for the recorded reversals.
    from services.financial.duplicates import CrossCaseError

    if not isinstance(decision, AdjudicationDecision):
        raise DecisionError(
            f"decision must be an AdjudicationDecision, got "
            f"{type(decision).__name__}; a bare string is how 'release', "
            "'released' and 'release_row' become three answers to one question"
        )
    if not isinstance(subject_type, AdjudicationSubject):
        raise DecisionError(
            f"subject_type must be an AdjudicationSubject, got "
            f"{type(subject_type).__name__}"
        )

    expected = _SUBJECT_MODELS[subject_type]
    if not isinstance(subject, expected):
        raise SubjectMismatchError(
            f"subject_type is {subject_type.value!r}, which is "
            f"{expected.__name__}, but the subject is a "
            f"{type(subject).__name__}. There is no foreign key to catch this "
            "later; the decision would be filed against the wrong evidence."
        )
    if subject.id is None:
        raise DecisionError(
            "the subject has no id yet; flush it first, or the decision will "
            "point at nothing"
        )
    if subject.case_id != case_id:
        raise CrossCaseError(
            f"{subject_type.value} {subject.id} belongs to case "
            f"{subject.case_id}, not {case_id}; refusing to record a decision "
            "about it in another matter"
        )

    if not isinstance(reason, str) or not reason.strip():
        raise DecisionError(
            "a decision without a stated reason is not an adjudication, it is "
            "an unexplained edit"
        )
    if not isinstance(actor, Actor):
        raise DecisionError(
            f"actor must be an Actor, got {type(actor).__name__}"
        )

    before_json = _snapshot(before, "before")
    after_json = _snapshot(after, "after")
    _check_diff(before_json, after_json)

    adjudication = FinancialAdjudication(
        case_id=case_id,
        subject_type=subject_type.value,
        subject_id=subject.id,
        subject_sequence=_next_sequence(session, subject_type, subject.id),
        decision=decision.value,
        reason=reason,
        before=before_json,
        after=after_json,
        actor_user_id=actor.user_id,
        actor_name=actor.name,
        actor_email=actor.email,
        ingestion_run_id=ingestion_run_id,
    )
    session.add(adjudication)
    session.flush()
    return adjudication


def history(
    session: "Session",
    subject: Any,
    subject_type: AdjudicationSubject,
) -> tuple[FinancialAdjudication, ...]:
    """Every decision recorded about one subject, oldest first.

    Ordered by ``subject_sequence``, which is the only column here that can
    carry an order.  An earlier draft of this function ordered by
    ``created_at`` and broke ties on ``id``, with a docstring claiming that
    settled the sequence of a quarantine and the release that undid it.  It did
    not: ``id`` is a random uuid4, so the tiebreak was arbitrary, and the pair
    it claimed to order is exactly the pair most likely to be written in one
    transaction and so to share a timestamp under Postgres ``now()``.  The
    order looked authoritative and was a coin toss.
    """
    from sqlalchemy import select

    rows = session.scalars(
        select(FinancialAdjudication)
        .where(FinancialAdjudication.subject_type == subject_type.value)
        .where(FinancialAdjudication.subject_id == subject.id)
        .order_by(FinancialAdjudication.subject_sequence)
    ).all()
    return tuple(rows)
