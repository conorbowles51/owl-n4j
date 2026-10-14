"""Graph follow-up: draw the committed ledger into Neo4j, after the ledger is done.

:mod:`services.financial.projection` builds the Cypher that makes a case's graph
match its ledger, and deliberately runs none of it.  This module is the caller
it was waiting for.  Three rules shape it.

*After the commit, never inside it.*  Admission commits the ledger first and
only then asks for a follow-up.  Nothing here can roll back, fail or delay a
ledger write: a projection that fails leaves the ledger exactly as committed
and the failure is recorded as a graph follow-up status, retried with backoff.
Ledger completion and graph follow-up are validated separately.

*One code path.*  The import worker, the drift check and the backfill command
all call :func:`project_case_graph`.  It reads the whole case from the ledger
(the projection is whole-case: retraction is by digest, so a partial input
would retract everything it did not mention) and applies the plan in one Neo4j
transaction.  Re-running it is idempotent: every write is a ``MERGE`` on a
content-derived key, and an unchanged ledger produces the same digest.

*Bounded.*  Retries back off exponentially to a cap and never spin.  A running
projection checks a stop flag between statements, so shutdown waits for at most
one statement, and the open Neo4j transaction is rolled back rather than left
half-applied.

Durable state lives on a ``FinancialLedgerProjection`` marker node per case,
written in the same transaction as the projection, so the marker can never
claim a projection the graph does not hold.  It records the digest and the
ledger fingerprint it was built from.  Failures are recorded on it best-effort
(the graph may be the thing that is down) and also held in process memory, so a
status read can always say why a case is behind.

Which cases are followed up automatically: those an import in this process
asked for, and those already carrying a marker whose ledger fingerprint has
since drifted.  A case that has never been projected is not picked up by the
drift check; it is projected by its next import or by the backfill command
(``python -m scripts.financial_graph_backfill``), which is the same code path.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional
from uuid import UUID

from neo4j import Query
from sqlalchemy import func, select

from postgres.models.evidence import EvidenceFile
from postgres.models.financial import (
    FinancialAccount,
    FinancialSourceDocument,
    FinancialStatementPeriod,
    FinancialTransaction,
)
from services.financial import projection

log = logging.getLogger(__name__)

MARKER_LABEL = "FinancialLedgerProjection"
ENABLED_ENV = "LOUPE_FINANCIAL_GRAPH_FOLLOWUP"

GRAPH_CONNECTION_TIMEOUT = 20
# One transaction carries the whole case.  Generous, because a large case is
# tens of thousands of MERGEs; bounded, because an unbounded graph transaction
# is how a shutdown waits forever.
GRAPH_TRANSACTION_TIMEOUT = 900

# Coalescing.  A batch import admits statements every few seconds; projecting
# the whole case after each one would redraw it hundreds of times.  A request
# waits for a quiet interval, but never longer than the maximum deferral, so a
# long import still shows progress in the graph.
QUIET_SECONDS = 20
MAX_DEFER_SECONDS = 300

RETRY_BASE_SECONDS = 30
RETRY_CAP_SECONDS = 1800
# The ledger moved under a projection; try again soon, without counting it
# against the case as a failure.
STALE_RETRY_SECONDS = 5

DRIFT_SCAN_SECONDS = 300

_CONSTRAINT = Query(
    f"CREATE CONSTRAINT financial_ledger_projection_case IF NOT EXISTS "
    f"FOR (m:{MARKER_LABEL}) REQUIRE m.case_id IS UNIQUE",
    timeout=GRAPH_CONNECTION_TIMEOUT,
)

# Without these every MERGE and edge MATCH on a projected label is a label scan,
# which makes a whole-case projection quadratic in its transaction count.
# Indexes, unlike the uniqueness constraints projection.py recommends, cannot
# fail on existing duplicate keys, so ensuring them here is safe and idempotent.
KEY_INDEXES = tuple(
    f"CREATE INDEX projected_{label.lower()}_case_key IF NOT EXISTS "
    f"FOR (n:{label}) ON (n.case_id, n.key)"
    for label in projection.PROJECTED_LABELS
)
GRAPH_INDEXES = KEY_INDEXES + projection.RECOMMENDED_INDEXES
_indexes_ensured: list[bool] = [False]

# Taking the marker first serialises concurrent projections of one case: every
# writer increments the same property, so the second waits on the first's lock.
_LOCK_MARKER = f"""
MERGE (m:{MARKER_LABEL} {{case_id: $case_id}})
SET m.system_node = true, m.projection_lock = coalesce(m.projection_lock, 0) + 1
RETURN m.digest AS digest, m.ledger_fingerprint AS ledger_fingerprint, m.status AS status
"""

_COMPLETE_MARKER = f"""
MATCH (m:{MARKER_LABEL} {{case_id: $case_id}})
SET m.status = 'current', m.digest = $digest, m.ledger_fingerprint = $fingerprint,
    m.transaction_count = $transaction_count, m.node_count = $node_count,
    m.edge_count = $edge_count, m.refusal_count = $refusal_count,
    m.projection_version = $projection_version, m.completed_at = datetime()
REMOVE m.last_error, m.failed_attempts, m.last_failed_at, m.next_attempt_at
"""

_RECORD_FAILURE = f"""
MERGE (m:{MARKER_LABEL} {{case_id: $case_id}})
SET m.system_node = true, m.status = 'retrying', m.last_error = $error,
    m.failed_attempts = $attempts, m.last_failed_at = datetime(),
    m.next_attempt_at = datetime() + duration({{seconds: $delay}})
"""

_READ_MARKER = f"""
MATCH (m:{MARKER_LABEL} {{case_id: $case_id}})
RETURN m.status AS status, m.digest AS digest, m.ledger_fingerprint AS ledger_fingerprint,
       m.transaction_count AS transaction_count, m.refusal_count AS refusal_count,
       toString(m.completed_at) AS completed_at, m.last_error AS last_error,
       m.failed_attempts AS failed_attempts, toString(m.next_attempt_at) AS next_attempt_at
"""

_ALL_MARKERS = f"""
MATCH (m:{MARKER_LABEL})
WHERE m.case_id IS NOT NULL
RETURN m.case_id AS case_id, m.ledger_fingerprint AS ledger_fingerprint
"""


class GraphFollowUpError(Exception):
    """A projection could not be applied; the ledger is unaffected."""


class ProjectionStale(GraphFollowUpError):
    """The ledger changed between reading it and applying the plan."""


class ProjectionStopped(GraphFollowUpError):
    """Shutdown was requested part-way through; the graph transaction was rolled back."""


class UnexpectedEmptyProjection(GraphFollowUpError):
    """The plan would erase the case's projection although the ledger has admitted rows."""


def follow_up_enabled() -> bool:
    return os.getenv(ENABLED_ENV, "1").strip().lower() not in ("0", "false", "off", "no")


# ---------------------------------------------------------------------------
# Reading the ledger
# ---------------------------------------------------------------------------


_FINGERPRINTED = (FinancialAccount, FinancialSourceDocument, FinancialStatementPeriod, FinancialTransaction)


def ledger_fingerprint(db, case_id) -> str:
    """A cheap change detector for everything the projection reads.

    Row count and latest ``updated_at`` per table, plus row counts by status.  Insertions and deletions
    move the count; updates through the ORM or Core move ``updated_at``.  It is
    a trigger for re-projection, not proof of equality: the digest comparison
    inside :func:`apply_snapshot` is what decides whether anything is written.
    """
    parts = []
    for model in _FINGERPRINTED:
        count, latest = db.execute(
            select(func.count(), func.max(model.updated_at)).where(model.case_id == case_id)
        ).one()
        parts.append([model.__tablename__, int(count or 0), latest.isoformat() if hasattr(latest, 'isoformat') else latest])
    # Status moves (admit, quarantine, supersede) decide what is drawn, and must
    # be seen even when a timestamp does not move: PostgreSQL ``now()`` is the
    # transaction start, and SQLite stamps to the second.
    for model, column in ((FinancialTransaction, FinancialTransaction.ledger_status),
                          (FinancialSourceDocument, FinancialSourceDocument.status)):
        parts.append([model.__tablename__ + ".status", sorted(
            [str(value), int(count)] for value, count in db.execute(
                select(column, func.count()).where(model.case_id == case_id).group_by(column)))])
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class CaseSnapshot:
    case_id: str
    fingerprint: str
    admitted_count: int
    plan: projection.ProjectionPlan


def snapshot_case(db, case_id, *, batch_size: int = projection.DEFAULT_BATCH_SIZE) -> CaseSnapshot:
    """Read the whole case and build its plan.

    The fingerprint is read first.  Under READ COMMITTED a commit can land
    between the fingerprint and the rows; the snapshot then carries an older
    fingerprint than its data, which only ever causes one extra re-projection,
    never a missed one.
    """
    case_id = UUID(str(case_id))
    fingerprint = ledger_fingerprint(db, case_id)
    accounts = [projection.account_from_row(row) for row in db.scalars(
        select(FinancialAccount).where(FinancialAccount.case_id == case_id).order_by(FinancialAccount.id))]
    documents = [
        projection.document_from_row(row, original_filename=filename)
        for row, filename in db.execute(
            select(FinancialSourceDocument, EvidenceFile.original_filename)
            .outerjoin(EvidenceFile, EvidenceFile.id == FinancialSourceDocument.evidence_file_id)
            .where(FinancialSourceDocument.case_id == case_id)
            .order_by(FinancialSourceDocument.id))
    ]
    periods = [projection.period_from_row(row) for row in db.scalars(
        select(FinancialStatementPeriod).where(FinancialStatementPeriod.case_id == case_id)
        .order_by(FinancialStatementPeriod.id))]
    transactions = [projection.transaction_from_row(row) for row in db.scalars(
        select(FinancialTransaction).where(FinancialTransaction.case_id == case_id)
        .order_by(FinancialTransaction.id))]
    # Counted by a separate query, so an adapter or join that silently returned
    # nothing cannot also make the guard below agree with it.
    admitted = int(db.scalar(select(func.count()).select_from(FinancialTransaction).where(
        FinancialTransaction.case_id == case_id, FinancialTransaction.ledger_status == "admitted")) or 0)
    plan = projection.project_case(case_id, accounts=accounts, documents=documents, periods=periods,
                                   transactions=transactions, batch_size=batch_size)
    return CaseSnapshot(case_id=str(case_id), fingerprint=fingerprint, admitted_count=admitted, plan=plan)


_IDENTIFIER = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def summarize(snapshot: CaseSnapshot) -> dict:
    plan = snapshot.plan
    nodes: dict[str, int] = {}
    for node in plan.nodes:
        nodes[node.label] = nodes.get(node.label, 0) + 1
    edges: dict[str, int] = {}
    for edge in plan.edges:
        edges[edge.type] = edges.get(edge.type, 0) + 1
    refusals: dict[str, int] = {}
    for refusal in plan.refusals:
        # Grouped by reason with identifiers removed, so a report on a large
        # case reads as a handful of causes rather than thousands of lines.
        reason = refusal.subject + ": " + _IDENTIFIER.sub("<id>", refusal.reason)
        refusals[reason] = refusals.get(reason, 0) + 1
    return dict(case_id=snapshot.case_id, digest=plan.digest, ledger_fingerprint=snapshot.fingerprint,
                admitted_transactions=snapshot.admitted_count, transaction_count=plan.transaction_count,
                nodes=nodes, edges=edges, statement_count=len(plan.statements),
                refusal_count=len(plan.refusals), refusals_by_reason=refusals)


# ---------------------------------------------------------------------------
# Writing the graph
# ---------------------------------------------------------------------------


def read_marker(graph, case_id) -> Optional[dict]:
    record = graph.run(_READ_MARKER, case_id=str(case_id)).single()
    return dict(record) if record else None


def ensure_graph_indexes(graph) -> None:
    """Idempotent schema setup for the projection; once per process."""
    if _indexes_ensured[0]:
        return
    graph.run(_CONSTRAINT).consume()
    for statement in GRAPH_INDEXES:
        graph.run(Query(statement, timeout=GRAPH_CONNECTION_TIMEOUT)).consume()
    _indexes_ensured[0] = True


def missing_graph_indexes(graph) -> list[str]:
    """Which of :data:`GRAPH_INDEXES` the graph does not have yet (read only)."""
    present = {r["name"] for r in graph.run("SHOW INDEXES YIELD name RETURN name").data()}
    return [s.split(" ")[2] for s in GRAPH_INDEXES if s.split(" ")[2] not in present]


def apply_snapshot(graph, snapshot: CaseSnapshot, *, is_current: Optional[Callable[[], bool]] = None,
                   stop: Optional[threading.Event] = None, force: bool = False) -> dict:
    """Apply one case plan in one transaction, with the marker as its lock."""
    plan = snapshot.plan
    if snapshot.admitted_count > 0 and plan.transaction_count == 0:
        raise UnexpectedEmptyProjection(
            f"The ledger has {snapshot.admitted_count} admitted transactions but the plan draws none; "
            "applying it would erase the case's projection. Nothing was written.")
    ensure_graph_indexes(graph)
    with graph.begin_transaction(timeout=GRAPH_TRANSACTION_TIMEOUT) as tx:
        marker = tx.run(_LOCK_MARKER, case_id=snapshot.case_id).single()
        # Revalidated under the marker lock, so an older snapshot that waited
        # behind a newer writer cannot overwrite it.
        if is_current is not None and not is_current():
            tx.rollback()
            raise ProjectionStale("The ledger changed while the projection was being prepared.")
        unchanged = bool(marker) and marker["digest"] == plan.digest
        if not unchanged or force:
            for statement in plan.statements:
                if stop is not None and stop.is_set():
                    tx.rollback()
                    raise ProjectionStopped("Shutdown requested; the projection was rolled back.")
                tx.run(statement.cypher, dict(statement.parameters)).consume()
        tx.run(_COMPLETE_MARKER, case_id=snapshot.case_id, digest=plan.digest,
               fingerprint=snapshot.fingerprint, transaction_count=plan.transaction_count,
               node_count=len(plan.nodes), edge_count=len(plan.edges), refusal_count=len(plan.refusals),
               projection_version=projection.PROJECTION_VERSION).consume()
        tx.commit()
    return dict(outcome="unchanged" if unchanged and not force else "projected",
                statements_run=0 if unchanged and not force else len(plan.statements))


def record_failure(graph, case_id, *, error: str, attempts: int, delay: float) -> None:
    graph.run(_CONSTRAINT).consume()
    graph.run(_RECORD_FAILURE, case_id=str(case_id), error=error[:500], attempts=attempts,
              delay=int(delay)).consume()


def _default_session_factory():
    from postgres.session import _get_session_local
    return _get_session_local()


def _default_graph_session():
    from services.neo4j_service import neo4j_service
    return neo4j_service.session(connection_acquisition_timeout=GRAPH_CONNECTION_TIMEOUT)


def project_case_graph(case_id, *, session_factory=None, graph_session_factory=None, dry_run: bool = False,
                       force: bool = False, stop: Optional[threading.Event] = None,
                       batch_size: int = projection.DEFAULT_BATCH_SIZE, read_graph: bool = True) -> dict:
    """The one code path: read the case ledger, then (unless ``dry_run``) apply it.

    A dry run never writes.  With ``read_graph`` it also reads the case's marker
    and the reader preflight, so it can say whether a real run would change
    anything and whether existing legacy nodes will hide provenance.
    """
    session_factory = session_factory or _default_session_factory()
    graph_session_factory = graph_session_factory or _default_graph_session
    started = time.monotonic()
    # The SQL snapshot is closed before any graph work starts, so no Postgres
    # transaction or row lock is held while Neo4j is slow or unavailable.
    with session_factory() as db:
        snapshot = snapshot_case(db, case_id, batch_size=batch_size)
        db.rollback()
    report = summarize(snapshot)
    report["read_seconds"] = round(time.monotonic() - started, 3)
    if dry_run:
        report["dry_run"] = True
        if read_graph:
            with graph_session_factory() as graph:
                marker = read_marker(graph, snapshot.case_id)
                preflight = graph.run(projection.PREFLIGHT_CYPHER, case_id=snapshot.case_id).single()
                missing = missing_graph_indexes(graph)
            finding = projection.interpret_preflight(
                preflight["total_amount_nodes"] if preflight else 0,
                preflight["tagged_amount_nodes"] if preflight else 0)
            report["marker"] = marker
            report["would_change_graph"] = not marker or marker.get("digest") != snapshot.plan.digest
            report["missing_graph_indexes"] = missing
            report["legacy_untagged_amount_nodes"] = finding.untagged_amount_nodes
            report["provenance_will_survive_read"] = finding.provenance_will_survive_read
        report["would_refuse_empty_plan"] = snapshot.admitted_count > 0 and snapshot.plan.transaction_count == 0
        return report

    def is_current():
        with session_factory() as db:
            current = ledger_fingerprint(db, UUID(snapshot.case_id))
            db.rollback()
        return current == snapshot.fingerprint

    with graph_session_factory() as graph:
        report.update(apply_snapshot(graph, snapshot, is_current=is_current, stop=stop, force=force))
    report["dry_run"] = False
    report["total_seconds"] = round(time.monotonic() - started, 3)
    return report


# ---------------------------------------------------------------------------
# Scheduling: requests, coalescing, backoff
# ---------------------------------------------------------------------------


@dataclass
class _CaseState:
    first_requested: Optional[float] = None
    last_requested: Optional[float] = None
    request_generation: int = 0
    attempts: int = 0
    next_due: float = 0.0
    last_error: Optional[str] = None
    last_outcome: Optional[str] = None
    running: bool = False
    history: list = field(default_factory=list)


_states: dict[str, _CaseState] = {}
_lock = threading.Lock()
_last_drift_scan: list[float] = [float("-inf")]


def request_follow_up(case_id, *, now: Optional[float] = None, immediate: bool = False) -> None:
    """Ask for this case's graph to be redrawn.  Cheap, no I/O, never raises.

    Called after the ledger commit.  The work happens later, in
    :func:`run_due`, so a slow or unavailable graph never touches the caller.
    """
    try:
        moment = time.monotonic() if now is None else now
        with _lock:
            state = _states.setdefault(str(case_id), _CaseState())
            if state.first_requested is None:
                state.first_requested = moment - (MAX_DEFER_SECONDS if immediate else 0)
            state.last_requested = moment - (QUIET_SECONDS if immediate else 0)
            state.request_generation += 1
    except Exception:  # pragma: no cover - a follow-up request must never fail an import
        log.exception("Graph follow-up request for case %s could not be recorded", case_id)


def _is_due(state: _CaseState, now: float) -> bool:
    if state.running or state.first_requested is None or now < state.next_due:
        return False
    return (now - state.last_requested >= QUIET_SECONDS
            or now - state.first_requested >= MAX_DEFER_SECONDS)


def retry_delay(attempts: int) -> float:
    return float(min(RETRY_BASE_SECONDS * (2 ** max(attempts - 1, 0)), RETRY_CAP_SECONDS))


def _drift_scan(session_factory, graph_session_factory, now: float) -> None:
    with graph_session_factory() as graph:
        markers = graph.run(_ALL_MARKERS).data()
    with session_factory() as db:
        for row in markers:
            case_id = row["case_id"]
            with _lock:
                if _states.get(str(case_id), _CaseState()).first_requested is not None:
                    continue
            try:
                current = ledger_fingerprint(db, UUID(str(case_id)))
            except ValueError:
                continue
            if current != row.get("ledger_fingerprint"):
                request_follow_up(case_id, now=now, immediate=True)
        db.rollback()


def run_due(session_factory=None, graph_session_factory=None, *, stop: Optional[threading.Event] = None,
            clock: Callable[[], float] = time.monotonic) -> list[dict]:
    """Project every case whose follow-up is due.  Never raises for one case."""
    if not follow_up_enabled():
        return []
    session_factory = session_factory or _default_session_factory()
    graph_session_factory = graph_session_factory or _default_graph_session
    now = clock()
    if now - _last_drift_scan[0] >= DRIFT_SCAN_SECONDS:
        _last_drift_scan[0] = now
        try:
            _drift_scan(session_factory, graph_session_factory, now)
        except Exception as error:
            log.warning("Ledger graph drift check skipped this round: %s", error)
    with _lock:
        due = sorted(case for case, state in _states.items() if _is_due(state, now))
        for case in due:
            _states[case].running = True
    results = []
    for case in due:
        if stop is not None and stop.is_set():
            with _lock:
                _states[case].running = False
            continue
        with _lock:
            generation = _states[case].request_generation
        try:
            report = project_case_graph(case, session_factory=session_factory,
                                        graph_session_factory=graph_session_factory, stop=stop)
        except ProjectionStale:
            with _lock:
                state = _states[case]
                state.running = False
                state.next_due = clock() + STALE_RETRY_SECONDS
                state.last_outcome = "stale"
            results.append(dict(case_id=case, outcome="stale"))
            continue
        except ProjectionStopped:
            with _lock:
                _states[case].running = False
            results.append(dict(case_id=case, outcome="stopped"))
            continue
        except Exception as error:
            message = str(error) or type(error).__name__
            with _lock:
                state = _states[case]
                state.running = False
                state.attempts += 1
                delay = retry_delay(state.attempts)
                state.next_due = clock() + delay
                state.last_error = message[:500]
                state.last_outcome = "failed"
                attempts = state.attempts
            if attempts == 1:
                log.exception("Ledger graph projection failed for case %s; retrying in %ss", case, int(delay))
            else:
                log.warning("Ledger graph projection failed for case %s (attempt %s); retrying in %ss: %s",
                            case, attempts, int(delay), message)
            try:
                with graph_session_factory() as graph:
                    record_failure(graph, case, error=message, attempts=attempts, delay=delay)
            except Exception:
                pass  # The graph may be what is down; the in-process status still says why.
            results.append(dict(case_id=case, outcome="failed", attempts=attempts, retry_in=delay,
                                error=message[:500]))
            continue
        with _lock:
            state = _states[case]
            state.running = False
            if state.request_generation == generation:
                # Nothing new arrived while this ran; the case is caught up.
                _states.pop(case, None)
            else:
                state.first_requested = state.last_requested
                state.attempts = 0
                state.next_due = 0.0
                state.last_error = None
                state.last_outcome = report.get("outcome")
        _notify_identity_graph(case)
        results.append(dict(case_id=case, **{k: report[k] for k in ("outcome", "transaction_count", "digest")}))
    return results


def _notify_identity_graph(case_id) -> None:
    try:
        from services.financial.identity_graph import payment_nodes_changed
        payment_nodes_changed(case_id)
    except Exception:  # pragma: no cover
        log.exception("Could not wake the reviewed identity sweep for case %s", case_id)


async def follow_up_round(session_factory=None, graph_session_factory=None) -> list[dict]:
    """Run :func:`run_due` off the event loop; on cancellation stop between statements."""
    stop = threading.Event()
    work = asyncio.create_task(asyncio.to_thread(run_due, session_factory, graph_session_factory, stop=stop))
    try:
        return await asyncio.shield(work)
    except asyncio.CancelledError:
        stop.set()
        await work
        raise


def pending_state(case_id) -> Optional[dict]:
    with _lock:
        state = _states.get(str(case_id))
        if state is None:
            return None
        remaining = max(state.next_due - time.monotonic(), 0.0) if state.next_due else 0.0
        return dict(requested=state.first_requested is not None, running=state.running, attempts=state.attempts,
                    last_error=state.last_error, retry_in_seconds=round(remaining, 1), last_outcome=state.last_outcome)


def follow_up_status(db, case_id, *, graph_session_factory=None) -> dict:
    """What the graph holds for this case, against what the ledger now says.

    ``current``: the marker matches the ledger.  ``pending``: a redraw is due or
    running.  ``retrying``: the last attempt failed; ``last_error`` says why and
    ``retry_in_seconds`` when it runs again.  ``not_projected``: the case has
    admitted rows and has never been drawn (run the backfill).  ``not_needed``:
    no admitted rows and nothing drawn.  ``unavailable``: the graph could not be
    read; the ledger is unaffected.
    """
    case_id = UUID(str(case_id))
    fingerprint = ledger_fingerprint(db, case_id)
    admitted = int(db.scalar(select(func.count()).select_from(FinancialTransaction).where(
        FinancialTransaction.case_id == case_id, FinancialTransaction.ledger_status == "admitted")) or 0)
    local = pending_state(case_id)
    result = dict(case_id=str(case_id), admitted_transactions=admitted, projected_transactions=None,
                  completed_at=None, last_error=(local or {}).get("last_error"),
                  attempts=(local or {}).get("attempts", 0),
                  retry_in_seconds=(local or {}).get("retry_in_seconds"))
    graph_session_factory = graph_session_factory or _default_graph_session
    try:
        with graph_session_factory() as graph:
            marker = read_marker(graph, case_id)
    except Exception:
        result["status"] = "unavailable"
        return result
    if marker:
        result.update(projected_transactions=marker.get("transaction_count"),
                      completed_at=marker.get("completed_at"), refusal_count=marker.get("refusal_count"))
        if not result["last_error"] and marker.get("status") == "retrying":
            result.update(last_error=marker.get("last_error"), attempts=marker.get("failed_attempts") or 0,
                          next_attempt_at=marker.get("next_attempt_at"))
    if local and local.get("attempts"):
        result["status"] = "retrying"
    elif marker and marker.get("status") == "retrying":
        result["status"] = "retrying"
    elif marker and marker.get("status") == "current" and marker.get("ledger_fingerprint") == fingerprint:
        result["status"] = "current"
    elif local and local.get("requested"):
        result["status"] = "pending"
    elif marker and marker.get("completed_at"):
        result["status"] = "pending"
    elif admitted:
        result["status"] = "not_projected"
    else:
        result["status"] = "not_needed"
    return result


def _reset_for_tests() -> None:
    with _lock:
        _states.clear()
    _last_drift_scan[0] = float("-inf")
    _indexes_ensured[0] = False
