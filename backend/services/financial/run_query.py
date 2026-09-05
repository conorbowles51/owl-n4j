"""Reading the runs: what produced the ledger, and what failed trying.

``services.financial.runs`` has written a row for every execution of the
ingestion pipeline since it was built.  Nothing read one back.  Every fact in
the ledger carries a non-null ``ingestion_run_id``, so the database has always
been able to say which run produced a transaction, but no caller could ask the
opposite and far more useful question: what did that run do, did it finish, and
if it did not, what stopped it.  ``list_runs`` is that read.

The default population is deliberately different from the ledger's.
``list_transactions`` defaults to ``admitted`` because admitted is the
population every total is filtered to, and showing quarantined rows beside real
ones would mislead.  Runs are the opposite case: **the default here is every
status, including ``failed`` and ``aborted``, because the failures are the
reason to look.**  A run list that hid them would answer "what worked" while
appearing to answer "what happened", and a half-finished ingest that nothing
reports is the specific gap this read exists to close.

Ordering is newest first.  ``ix_financial_ingestion_runs_case`` is on
``(case_id, started_at)`` and supports either direction; newest first is chosen
because the question a reader arrives with is almost always about the ingest
that just happened, not the first one ever run on the case.

The counts come off the row and are never recomputed.  This follows the model's
own docstring: counting the ledger now would answer a different question,
because adjudication moves rows after a run ends, and a run's record is meant to
say what was true when it finished.

Nothing here decides whether a run is stale.  A ``running`` row is reported as
``running``, with the time it started, and that is all.  Deciding that a run has
been abandoned is :func:`services.financial.runs.reap_stale_runs`'s job and it
writes that decision down; a reader that made the same judgement independently
would be a second opinion with no record behind it, and the two would disagree
the moment either threshold moved.

Nothing here mutates a run.  This module answers "what happened", not "close
this one out".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from postgres.models.enums import IngestionRunStatus
from postgres.models.financial import FinancialIngestionRun


class RunQueryError(ValueError):
    """A run read was asked for something it cannot honestly answer."""


def list_runs(
    session: Session,
    case_id: UUID,
    *,
    status: Optional[IngestionRunStatus] = None,
    limit: Optional[int] = None,
) -> list[FinancialIngestionRun]:
    """Ingestion runs for one case, newest first, every status by default.

    ``status`` left unset means every status.  That is not the ledger read's
    behaviour and the difference is intentional: a failed run is the thing a
    reader most needs to see, so it cannot be behind an opt-in.

    ``limit`` is honoured when given and refused when it is not a positive
    number.  A limit of zero would return nothing while looking like a request
    for something, which is the kind of silence this subsystem is built to
    avoid.
    """
    if limit is not None and limit < 1:
        raise RunQueryError(
            f"limit must be a positive number of runs, not {limit}"
        )

    stmt = select(FinancialIngestionRun).where(
        FinancialIngestionRun.case_id == case_id
    )
    if status is not None:
        stmt = stmt.where(FinancialIngestionRun.status == status.value)
    stmt = stmt.order_by(
        FinancialIngestionRun.started_at.desc(),
        FinancialIngestionRun.id.asc(),
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt).all())


@dataclass(frozen=True)
class RunView:
    """One run, shaped for a reader rather than for storage.

    Every field is a stored column unwrapped to a JSON-safe type.  Nothing is
    derived, computed or inferred: a caller asking what a run did gets what the
    run recorded about itself and nothing this module made up on its behalf.
    """

    key: str
    case_id: str
    status: str
    code_version: Optional[str]
    ruleset_version: Optional[str]
    config: dict[str, Any]
    started_by_user_id: Optional[str]
    started_by_email: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]
    documents_seen: int
    transactions_admitted: int
    transactions_quarantined: int
    error: Optional[str]
    notes: Optional[str]

    def to_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "case_id": self.case_id,
            "status": self.status,
            "code_version": self.code_version,
            "ruleset_version": self.ruleset_version,
            "config": self.config,
            "started_by_user_id": self.started_by_user_id,
            "started_by_email": self.started_by_email,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "documents_seen": self.documents_seen,
            "transactions_admitted": self.transactions_admitted,
            "transactions_quarantined": self.transactions_quarantined,
            "error": self.error,
            "notes": self.notes,
        }


def _isoformat(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def to_run_view(row: FinancialIngestionRun) -> RunView:
    """Convert one stored run into its read shape.

    ``status`` is read straight off the column as the plain string
    :func:`services.financial.runs.open_ingestion_run` and
    :meth:`~services.financial.runs.IngestionRunHandle.terminate` put there --
    always a ``.value``, never an enum instance -- so there is nothing to
    unwrap.

    ``started_by_email`` is carried beside ``started_by_user_id`` because the
    foreign key nulls when a user is deleted and the email does not.  Who
    started a run has to survive an account being removed, which is the whole
    reason the writer records both.
    """
    return RunView(
        key=str(row.id),
        case_id=str(row.case_id),
        status=row.status,
        code_version=row.code_version,
        ruleset_version=row.ruleset_version,
        config=dict(row.config or {}),
        started_by_user_id=(
            str(row.started_by_user_id)
            if row.started_by_user_id is not None
            else None
        ),
        started_by_email=row.started_by_email,
        started_at=_isoformat(row.started_at),
        completed_at=_isoformat(row.completed_at),
        documents_seen=row.documents_seen,
        transactions_admitted=row.transactions_admitted,
        transactions_quarantined=row.transactions_quarantined,
        error=row.error,
        notes=row.notes,
    )
