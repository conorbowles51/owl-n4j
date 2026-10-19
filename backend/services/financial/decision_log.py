"""Reading the adjudication log back out, one case at a time.

:mod:`services.financial.decisions` is the writer, and it has been the writer
since the log stopped recording only dispositions.  Nothing has ever been the
reader.  ``decisions.history`` exists and is used, but it answers a different
question: it takes a *loaded subject object* and returns every decision about
that one subject.  That is the right shape for the caller it was built for --
:func:`services.financial.quarantine_row._latest_adjudication_id` needs the
event it just appended -- and it is the wrong shape for every other question
anyone asks of an audit trail, which are all case-shaped: what has been done
to the evidence in this matter, by whom, and when.

It is also unsafe as the basis for an endpoint, and not by a little.
``history`` filters on ``subject_type`` and ``subject_id`` and **not** on
``case_id``.  Subject ids are uuid4 and so unguessable, which is a reason it
has never mattered, not a reason it is sound: a route built on it would be
one caller-supplied id away from returning another firm's decisions, and the
failure would be silent because the rows would look entirely normal.  So the
case is a mandatory positional argument here rather than an optional filter,
and it is part of the WHERE clause rather than checked afterwards -- the same
construction :func:`services.financial.quarantine_row.find_case_transaction`
uses, and for the same reason.

Why this read is bounded when the ledger read is not
----------------------------------------------------

``transaction_query.list_transactions`` returns every matching row with no
limit.  That is defensible there: a case's ledger is bounded by the documents
someone chose to ingest.  This table is not.  ``reclassify_document`` is
written by the reconciliation stage, once per document whose class moves, on
every run -- see :class:`~postgres.models.enums.AdjudicationDecision` on why
that move must be logged.  So a case's decision log grows without anybody
deciding anything, and an unbounded read of it would be a request whose cost
is set by how many times the pipeline has been run.  ``total`` is reported
alongside the page so a reader is told what it is not being shown, which is
the whole point of an audit trail: a truncated history that does not say it
was truncated is worse than no history.

What the order here does and does not claim
-------------------------------------------

``decisions.history`` orders by ``subject_sequence`` and its docstring sets
out why: ``created_at`` is Postgres ``now()``, which is transaction-start
time, so two decisions written in one transaction share it exactly, and
``id`` is a random uuid4 and cannot break the tie.  An earlier draft of that
function ordered by ``created_at`` with an ``id`` tiebreak and claimed to have
settled the sequence of a quarantine and the release that undid it.  It had
not.  That lesson applies here and must not be quietly dropped just because
this read spans subjects.

Across subjects there is no ``subject_sequence`` to use -- the sequences are
per-subject and comparing one subject's 3 with another's 1 means nothing.  So
this read orders by ``created_at`` descending, then by subject, then by
``subject_sequence`` descending.  What that gives is: newest first at the
resolution the timestamp actually has; a correct and authoritative order
*within* any one subject, including for events sharing a timestamp; and a
total, deterministic order, so that paging does not show or skip a row as a
side effect of the database's choice.

What it does not give is a claim that two events about *different* subjects
carrying the same timestamp happened in the order shown.  They were written
in one transaction and nothing recorded which came first.  Every record
carries its ``subject_sequence`` so a reader can see the order that is real,
and the interface is not to present cross-subject adjacency as sequence.

Who decided, and the one derived field here
-------------------------------------------

``by_machine`` is the only value on a record that is not a column.  It is
derived by comparing ``actor_email`` against
:data:`services.financial.documents.RECONCILIATION_ACTOR_EMAIL`, which is the
separation :class:`~postgres.models.enums.AdjudicationDecision` already relies
on: "how many documents did your analysts reclassify" and "how many did your
software reclassify" are both exactly answerable because the automatic writer
carries an address at ``.invalid``, a reserved TLD no person's account can
hold.

It is derived rather than stored because storing it would be a second place
for the same fact to live and the two would drift.  It is surfaced rather than
left to the caller because the alternative is every reader re-implementing the
comparison against a constant, and a reader that gets it wrong shows a
machine's reclassification as a person's judgement -- which is the single most
misleading thing this log could be made to say.
"""

from __future__ import annotations

import datetime as _datetime
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select

from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
from postgres.models.financial import AdjudicationEvent

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.orm import Session


#: How many decisions one read returns when the caller does not say.  A
#: hundred is a screenful several times over and small enough that the count
#: query beside it is not the expensive half.
#:
#: Named for what it limits rather than ``DEFAULT_LIMIT``, because
#: ``services.financial.__init__`` is a flat surface shared by fifty modules
#: and a bare ``DEFAULT_LIMIT`` on it would read as the package's limit for
#: anything paged.
DEFAULT_DECISION_LIMIT = 100

#: The most one read will return however large a limit is asked for.  A cap
#: rather than an error, because the honest response to "give me everything"
#: is a page plus a truthful ``total``, not a refusal.
MAX_DECISION_LIMIT = 500


class DecisionLogError(ValueError):
    """A read of the decision log was asked for something it cannot answer."""


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    """One appended decision, as a reader sees it.

    Every field but :attr:`by_machine` is a column read straight off the row.
    ``before`` and ``after`` are passed through as stored: they were written
    through :func:`services.financial.decisions._jsonable`, which already
    refused anything JSON cannot hold and converted money to its integer minor
    units, so there is nothing to convert here and nothing to round.
    """

    id: str
    case_id: str
    subject_type: str
    subject_id: str
    #: 1 for the first decision about this subject, one more for each after.
    #: The only order in this table that is authoritative; see the module
    #: docstring on what that means for a list spanning subjects.
    subject_sequence: int
    decision: str
    reason: str
    before: Optional[dict]
    after: Optional[dict]
    actor_name: str
    actor_email: str
    actor_user_id: Optional[str]
    ingestion_run_id: Optional[str]
    recorded_at: Optional[str]
    #: Whether the reconciliation stage wrote this, rather than a person.
    #: Derived from the actor's address; see the module docstring.
    by_machine: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "case_id": self.case_id,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "subject_sequence": self.subject_sequence,
            "decision": self.decision,
            "reason": self.reason,
            "before": self.before,
            "after": self.after,
            "actor_name": self.actor_name,
            "actor_email": self.actor_email,
            "actor_user_id": self.actor_user_id,
            "ingestion_run_id": self.ingestion_run_id,
            "recorded_at": self.recorded_at,
            "by_machine": self.by_machine,
        }


@dataclass(frozen=True, slots=True)
class DecisionPage:
    """One page of a case's decision log, and how much of it was not shown.

    ``total`` counts every row matching the same filters, not every row in the
    case.  A reader filtered to one subject needs to know how many decisions
    that subject has, not how many the matter has; reporting the unfiltered
    count beside a filtered page would state a number that answers no question
    the caller asked.
    """

    case_id: str
    decisions: tuple[DecisionRecord, ...]
    total: int
    limit: int
    offset: int

    @property
    def truncated(self) -> bool:
        """Whether decisions matching this read were left off the page."""
        return self.offset + len(self.decisions) < self.total

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "decisions": [record.as_dict() for record in self.decisions],
            "total": self.total,
            "limit": self.limit,
            "offset": self.offset,
            "truncated": self.truncated,
        }


def _machine_actor_email() -> str:
    """The address the reconciliation stage decides under.

    Imported inside the function rather than at module level.
    ``services.financial.documents`` is one of the heavier modules in this
    package and imports a good deal of the rest of it; a reader of the log has
    no other reason to pull that chain in, and this package already defers
    imports for exactly this reason -- see the ``duplicates`` import inside
    :func:`services.financial.decisions.record`.
    """
    from services.financial.documents import RECONCILIATION_ACTOR_EMAIL

    return RECONCILIATION_ACTOR_EMAIL


def _isoformat(value: Any) -> Optional[str]:
    if isinstance(value, (_datetime.datetime, _datetime.date)):
        return value.isoformat()
    return None


def to_record(event: AdjudicationEvent, *, machine_email: str) -> DecisionRecord:
    """One stored event as a reader's record.

    ``machine_email`` is passed in rather than looked up per row so that a
    page of five hundred does not repeat the deferred import five hundred
    times, and so that a test can state which address it means.
    """
    actor_email = event.actor_email or ""
    return DecisionRecord(
        id=str(event.id),
        case_id=str(event.case_id),
        subject_type=event.subject_type,
        subject_id=str(event.subject_id),
        subject_sequence=event.subject_sequence,
        decision=event.decision,
        reason=event.reason,
        before=event.before,
        after=event.after,
        actor_name=event.actor_name,
        actor_email=actor_email,
        actor_user_id=(
            str(event.actor_user_id) if event.actor_user_id is not None else None
        ),
        ingestion_run_id=(
            str(event.ingestion_run_id)
            if event.ingestion_run_id is not None
            else None
        ),
        recorded_at=_isoformat(event.created_at),
        # Compared case-insensitively because an address is not case-sensitive
        # in its domain and the comparison decides whether a reader is told a
        # machine acted or a person did.
        by_machine=actor_email.strip().lower() == machine_email.strip().lower(),
    )


def _validated_limit(limit: int) -> int:
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise DecisionLogError(
            f"limit must be an int, got {type(limit).__name__}"
        )
    if limit < 1:
        raise DecisionLogError(
            f"limit must be at least 1, got {limit}; a page of nothing beside "
            "a total is a count dressed as a history"
        )
    return min(limit, MAX_DECISION_LIMIT)


def _validated_offset(offset: int) -> int:
    if not isinstance(offset, int) or isinstance(offset, bool):
        raise DecisionLogError(
            f"offset must be an int, got {type(offset).__name__}"
        )
    if offset < 0:
        raise DecisionLogError(f"offset cannot be negative, got {offset}")
    return offset


def list_case_decisions(
    session: "Session",
    case_id: UUID,
    *,
    subject_type: Optional[AdjudicationSubject] = None,
    subject_id: Optional[UUID] = None,
    decision: Optional[AdjudicationDecision] = None,
    limit: int = DEFAULT_DECISION_LIMIT,
    offset: int = 0,
) -> DecisionPage:
    """Decisions recorded in one case, newest first.

    ``subject_type`` and ``decision`` are the enum members, not strings, for
    the reason :func:`services.financial.decisions.record` refuses bare
    strings: 'release', 'released' and 'release_row' are three answers to one
    question, and a filter that accepted any of them would silently return
    nothing rather than say the word was not in the vocabulary.

    ``subject_id`` may be given without ``subject_type``.  The pair is not
    unique on its own -- ``subject_id`` carries no foreign key and the unique
    constraint is over the triple -- but two tables producing the same uuid4 is
    not a case worth refusing a filter over, and the records returned each name
    their own subject type.
    """
    if case_id is None:
        raise DecisionLogError(
            "a decision log read needs a case; an unscoped read of this table "
            "crosses matters"
        )
    if subject_type is not None and not isinstance(
        subject_type, AdjudicationSubject
    ):
        raise DecisionLogError(
            f"subject_type must be an AdjudicationSubject, got "
            f"{type(subject_type).__name__}"
        )
    if decision is not None and not isinstance(decision, AdjudicationDecision):
        raise DecisionLogError(
            f"decision must be an AdjudicationDecision, got "
            f"{type(decision).__name__}"
        )

    limit = _validated_limit(limit)
    offset = _validated_offset(offset)

    filters = [AdjudicationEvent.case_id == case_id]
    if subject_type is not None:
        filters.append(AdjudicationEvent.subject_type == subject_type.value)
    if subject_id is not None:
        filters.append(AdjudicationEvent.subject_id == subject_id)
    if decision is not None:
        filters.append(AdjudicationEvent.decision == decision.value)

    total = session.scalar(
        select(func.count()).select_from(AdjudicationEvent).where(*filters)
    )

    rows = session.scalars(
        select(AdjudicationEvent)
        .where(*filters)
        # See the module docstring.  created_at leads because it is the only
        # column comparable across subjects; the three that follow make the
        # order total, so paging is stable, and make it correct within any one
        # subject, which is the part that is actually authoritative.
        .order_by(
            AdjudicationEvent.created_at.desc(),
            AdjudicationEvent.subject_type,
            AdjudicationEvent.subject_id,
            AdjudicationEvent.subject_sequence.desc(),
        )
        .limit(limit)
        .offset(offset)
    ).all()

    machine_email = _machine_actor_email()
    return DecisionPage(
        case_id=str(case_id),
        decisions=tuple(
            to_record(row, machine_email=machine_email) for row in rows
        ),
        total=int(total or 0),
        limit=limit,
        offset=offset,
    )
