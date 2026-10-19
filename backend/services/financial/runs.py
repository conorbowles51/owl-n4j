"""Run identity: what produced each fact in the financial ledger.

Every source document, statement period and transaction carries a non-null
``ingestion_run_id``, so the database already refuses an unattributed fact.
What the database cannot do is guarantee that the run those facts point at
tells the truth about itself.  That is this module's job, and it comes down to
two promises.

*A run always reaches a terminal state.*  A row left saying ``running`` forever
is worse than no row: it invites the reading that ingestion is still in
progress when in fact the process died an hour ago.  So the context manager
below records ``completed``, ``failed`` or ``aborted`` on every exit path
including interpreter shutdown, and :func:`reap_stale_runs` exists for the one
case no in-process handler can cover — the process that is killed outright.

*A failed run still leaves a record.*  This is why the run's own bookkeeping
uses a session of its own rather than the caller's.  If the two shared a
session, the rollback that discards a failed run's partial data would discard
the evidence that the run ever happened, and the ledger would show a silent gap
instead of a recorded failure.  Silent gaps are the specific thing this whole
subsystem exists to make impossible.

The caller's session is never touched.  If work was committed before the
failure, those rows survive and carry the failed run's id, which is correct:
they are exactly the rows a later quarantine pass needs to find.

Concurrency is deliberately not guarded here.  Two runs may ingest one case at
once, and the ``(source_document_id, content_hash)`` uniqueness constraint is
what keeps that from double-counting a transaction.  A service-layer "is a run
already active" check would be a race, not a protection, and claiming it as one
would be worse than the honest absence.  If concurrent runs must be prevented,
that belongs in the database as a partial unique index, not here.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Iterator, Mapping, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from postgres.models.enums import IngestionRunStatus
from postgres.models.financial import FinancialIngestionRun
from postgres.session import get_background_session
from services.financial.version import code_version, ruleset_version

# Recorded failure messages are bounded.  The run row is a record that a failure
# happened and roughly what it was; it is not a log sink, and a megabyte of
# traceback in a Text column helps nobody read the ledger.
MAX_ERROR_CHARS = 2000


class RunError(Exception):
    """Base class for run lifecycle problems."""


class RunAborted(RunError):
    """Raised by pipeline code to stop a run deliberately.

    Deliberate cessation is not failure, and the ledger records them as
    different statuses, because someone later asking why a case's ledger is
    incomplete needs to know whether the pipeline broke or declined.

    :func:`ingestion_run` suppresses this exception: raising it is how a caller
    says "stop here, and record why", so the ``with`` block exits normally and
    the reason is written to the run row.
    """


class RunScopeError(RunError):
    """Raised when a row cannot be attributed to the run stamping it.

    Always a programming error rather than a data condition: either the row has
    nowhere to record a run, or it already belongs to a different run or a
    different case.  Cross-case contamination in particular must fail loudly
    and immediately, because a transaction filed under the wrong case is
    evidence pointed at the wrong person.
    """


class SessionFactory(Protocol):
    def __call__(self) -> Session: ...


@dataclass(frozen=True)
class RunCounts:
    """The outcome of a run as it stood when the run ended.

    Recorded rather than recomputed, per the model's own docstring: counting the
    ledger later answers a different question, because adjudication will have
    moved rows since.
    """

    documents_seen: int = 0
    transactions_admitted: int = 0
    transactions_quarantined: int = 0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _describe(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}".strip()
    if len(text) <= MAX_ERROR_CHARS:
        return text
    return text[: MAX_ERROR_CHARS - 1] + "…"


def _as_utc(value: datetime | None) -> datetime | None:
    """Interpret a stored timestamp as UTC when it comes back without a zone.

    Postgres returns aware datetimes for ``timestamptz``; SQLite, which the test
    suite uses, has no zone concept and returns naive ones.  Treating a naive
    value as UTC is correct for both, because every value this module writes is
    UTC at the point of writing.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


@contextmanager
def _bookkeeping(session_factory: SessionFactory | None) -> Iterator[Session]:
    """A session for run bookkeeping, independent of any caller's transaction."""
    if session_factory is None:
        with get_background_session() as session:
            yield session
        return

    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class IngestionRunHandle:
    """A live run: its identity, its running counts, and how rows join it.

    The handle holds the run's id rather than the ORM row, so that nothing about
    a caller's session state can affect the run record, and vice versa.
    """

    def __init__(
        self,
        *,
        run_id: uuid.UUID,
        case_id: uuid.UUID,
        code_version: str,
        ruleset_version: str | None,
        session_factory: SessionFactory | None = None,
    ) -> None:
        self.run_id = run_id
        self.case_id = case_id
        self.code_version = code_version
        self.ruleset_version = ruleset_version
        self._session_factory = session_factory
        self._counts = RunCounts()
        self._status = IngestionRunStatus.running
        self._closed = False

    # -- attribution --------------------------------------------------------

    def stamp(self, row: Any) -> Any:
        """Attribute a ledger row to this run, and to this run's case.

        Returns the row so it can be used inline::

            db.add(run.stamp(FinancialTransaction(...)))

        A row with no ``ingestion_run_id`` is refused rather than silently
        skipped, because the caller believed it was recording provenance and
        the whole value of this call is that the belief is checked.
        """
        if self._closed:
            raise RunScopeError(
                f"run {self.run_id} is already {self._status.value}; "
                "it cannot take further rows"
            )

        if not hasattr(row, "ingestion_run_id"):
            raise RunScopeError(
                f"{type(row).__name__} has no ingestion_run_id and cannot "
                "carry run provenance"
            )

        existing_run = getattr(row, "ingestion_run_id", None)
        if existing_run is not None and existing_run != self.run_id:
            raise RunScopeError(
                f"{type(row).__name__} already belongs to run {existing_run}; "
                f"run {self.run_id} may not claim it"
            )
        row.ingestion_run_id = self.run_id

        if hasattr(row, "case_id"):
            existing_case = getattr(row, "case_id", None)
            if existing_case is None:
                row.case_id = self.case_id
            elif existing_case != self.case_id:
                raise RunScopeError(
                    f"{type(row).__name__} belongs to case {existing_case}, "
                    f"but this run is ingesting case {self.case_id}"
                )

        return row

    def stamp_all(self, rows: Iterable[Any]) -> list[Any]:
        """Attribute many rows, returning them as a list."""
        return [self.stamp(row) for row in rows]

    # -- counting -----------------------------------------------------------

    @property
    def counts(self) -> RunCounts:
        return self._counts

    @property
    def status(self) -> IngestionRunStatus:
        return self._status

    def document_seen(self, count: int = 1) -> None:
        self._counts = replace(
            self._counts, documents_seen=self._counts.documents_seen + count
        )

    def transaction_admitted(self, count: int = 1) -> None:
        self._counts = replace(
            self._counts,
            transactions_admitted=self._counts.transactions_admitted + count,
        )

    def transaction_quarantined(self, count: int = 1) -> None:
        self._counts = replace(
            self._counts,
            transactions_quarantined=self._counts.transactions_quarantined + count,
        )

    # -- termination --------------------------------------------------------

    def terminate(
        self,
        status: IngestionRunStatus,
        *,
        error: str | None = None,
    ) -> None:
        """Write the run's terminal status, counts and completion time.

        Idempotent by refusal: a run that has already ended cannot be ended
        again, because the first terminal status is the true one and a second
        write would be overwriting the record of what happened.
        """
        if self._closed:
            raise RunScopeError(
                f"run {self.run_id} already ended as {self._status.value}"
            )
        if status is IngestionRunStatus.pending or status is IngestionRunStatus.running:
            raise ValueError(f"{status.value} is not a terminal status")

        with _bookkeeping(self._session_factory) as session:
            run = session.get(FinancialIngestionRun, self.run_id)
            if run is None:
                raise RunScopeError(
                    f"run {self.run_id} no longer exists and cannot be closed"
                )
            run.status = status.value
            run.completed_at = _now()
            run.documents_seen = self._counts.documents_seen
            run.transactions_admitted = self._counts.transactions_admitted
            run.transactions_quarantined = self._counts.transactions_quarantined
            if error is not None:
                run.error = error[:MAX_ERROR_CHARS]

        self._status = status
        self._closed = True


def open_ingestion_run(
    *,
    case_id: uuid.UUID,
    actor: Any | None = None,
    config: Mapping[str, Any] | None = None,
    ruleset: Mapping[str, Any] | None = None,
    notes: str | None = None,
    session_factory: SessionFactory | None = None,
) -> IngestionRunHandle:
    """Record the start of a run and return a handle to it.

    ``actor`` is the user starting the run, or ``None`` for a system-initiated
    one.  Both the id and the email are copied from that one object rather than
    passed separately, so the recorded email cannot end up belonging to a
    different user than the recorded id.  The email is copied at all because the
    foreign key nulls on user deletion and "who started this" must survive an
    account being removed.

    Prefer :func:`ingestion_run`, which cannot leave a run unterminated.  This
    function is for callers whose run genuinely outlives a single block, and
    they take on the duty of calling :meth:`IngestionRunHandle.terminate`.
    """
    run_id = uuid.uuid4()
    resolved_code_version = code_version()
    resolved_ruleset_version = ruleset_version(ruleset)

    with _bookkeeping(session_factory) as session:
        session.add(
            FinancialIngestionRun(
                id=run_id,
                case_id=case_id,
                status=IngestionRunStatus.running.value,
                code_version=resolved_code_version,
                ruleset_version=resolved_ruleset_version,
                config=dict(config or {}),
                started_by_user_id=getattr(actor, "id", None),
                started_by_email=getattr(actor, "email", None),
                started_at=_now(),
                notes=notes,
            )
        )

    return IngestionRunHandle(
        run_id=run_id,
        case_id=case_id,
        code_version=resolved_code_version,
        ruleset_version=resolved_ruleset_version,
        session_factory=session_factory,
    )


@contextmanager
def ingestion_run(
    *,
    case_id: uuid.UUID,
    actor: Any | None = None,
    config: Mapping[str, Any] | None = None,
    ruleset: Mapping[str, Any] | None = None,
    notes: str | None = None,
    session_factory: SessionFactory | None = None,
) -> Iterator[IngestionRunHandle]:
    """Run a block of ingestion under a recorded run.

    On normal exit the run is ``completed``.  On :class:`RunAborted` it is
    ``aborted`` and the exception is suppressed, that being the point of
    raising it.  On any other exception — including ``KeyboardInterrupt``, since
    an interrupted run did not finish — it is ``failed``, the exception is
    described on the row, and it is re-raised unchanged.

    If writing the terminal status itself fails, the original exception is
    still raised and the run is left ``running`` for :func:`reap_stale_runs` to
    close.  Losing the real cause in order to report a bookkeeping error would
    be the wrong trade.
    """
    handle = open_ingestion_run(
        case_id=case_id,
        actor=actor,
        config=config,
        ruleset=ruleset,
        notes=notes,
        session_factory=session_factory,
    )

    try:
        yield handle
    except RunAborted as exc:
        _terminate_quietly(handle, IngestionRunStatus.aborted, error=str(exc) or None)
    except BaseException as exc:
        _terminate_quietly(handle, IngestionRunStatus.failed, error=_describe(exc))
        raise
    else:
        handle.terminate(IngestionRunStatus.completed)


def _terminate_quietly(
    handle: IngestionRunHandle,
    status: IngestionRunStatus,
    *,
    error: str | None,
) -> None:
    """Terminate a run while an exception is in flight, never masking it."""
    try:
        handle.terminate(status, error=error)
    except Exception:
        # Deliberately swallowed.  The alternative is replacing a real failure
        # with a bookkeeping one on its way out of the ``with`` block, and the
        # reaper already covers a run left open.
        pass


def reap_stale_runs(
    *,
    older_than: timedelta,
    session_factory: SessionFactory | None = None,
    now: datetime | None = None,
) -> list[uuid.UUID]:
    """Close runs still marked ``running`` past a threshold, and say why.

    The safety net for a process killed outright, where no in-process handler
    can run.  Such a run is marked ``failed``, not ``aborted``: nobody decided
    to stop it, and recording a crash as a decision would misstate the record.

    Candidates are filtered by status in SQL and by age in Python, so that a
    naive timestamp from a database without time zones is interpreted rather
    than compared as though it carried an offset.  The set of running rows is
    small by definition, so the cost is not a concern.
    """
    moment = now or _now()
    cutoff = moment - older_than
    reaped: list[uuid.UUID] = []

    with _bookkeeping(session_factory) as session:
        candidates = (
            session.execute(
                select(FinancialIngestionRun).where(
                    FinancialIngestionRun.status == IngestionRunStatus.running.value
                )
            )
            .scalars()
            .all()
        )
        for run in candidates:
            started_at = _as_utc(run.started_at)
            if started_at is None or started_at > cutoff:
                continue
            run.status = IngestionRunStatus.failed.value
            run.completed_at = moment
            run.error = (
                "Abandoned: no terminal status was recorded within "
                f"{older_than}. The process was most likely killed before it "
                "could close the run."
            )[:MAX_ERROR_CHARS]
            reaped.append(run.id)

    return reaped
