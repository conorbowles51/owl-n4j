"""Find documents that say the same thing, and stop counting them twice.

Evidence arrives with duplicates.  The same statement is disclosed twice, or
scanned once and re-exported, or supplied by two parties who each got it from
the bank.  The pipeline as it stands does not notice: each copy becomes its own
document, its own statement period and its own transactions, and each of those
periods reconciles perfectly, because each is a faithful reading of the same
page.

That is what makes the defect dangerous rather than merely untidy.  The balance
identity is computed per period, so it stays green.  What goes wrong is
everything that adds periods together — account totals, money flow, cross-period
continuity — all of which see March twice with no way to distinguish that from
March having happened twice.  A fault that inflates every aggregate while every
individual check passes will not announce itself, so it has to be looked for.

The cascade
-----------

The legacy resolver below compares persisted fingerprints within account/period
coverage groups. The HTTP candidate reader in ``duplicate_query`` instead
recomputes fingerprints without saving them. Identical bytes need not imply
identical readings: parser versions and corrections can disagree. That reader
reports the conflict explicitly and makes no exclusion decision.

``identical_bytes`` is the same sha256 over the file.  Cheap, certain, and the
narrowest: it catches a re-upload and nothing else.

``identical_reading`` is the same ``content_fingerprint`` — accounts, period
bounds, currency, balance observations, and all transaction rows.  This is the rung that earns the
module, because it is the one that survives a re-scan.  Two disclosures of the
same statement are two different files; only their content matches.

``same_account_period`` is the same ``duplicate_group_key`` — accounts and
bounds, without the rows.  It is a candidate and never more than that.  An
interim statement and the final one that replaces it match here.  So do a
statement and its corrected reissue, and two halves of a month printed
separately.  Excluding on this rung would destroy real evidence, so it raises a
flag for a person and changes no status.

What is done about it
---------------------

Within a group, one document is nominated primary and the rest are superseded:
status ``superseded``, ``superseded_by_id`` pointing at the primary, and their
transactions moved to ledger status ``superseded`` as well.  The second is
belt and braces — ``reconcile.total_transactions`` already counts only admitted
rows, so even a caller that forgets to filter by document status cannot
double-count.

Superseding hides; it does not delete.  The rows stay, the reasoning stays
visible, and ``restore_document`` puts a document back if the nomination was
wrong.  Purging is a separate, deliberate act with its own function, and it
writes its adjudication row before it deletes anything, because the record of a
decision has to outlive the thing decided.

Nomination is the balance identity's job.  Where two copies conflict they are
usually not equally good readings: a clean scan reconciles and a degraded one
drops a row and comes out unbalanced.  So the identity is a real discriminator
between copies, not a coin toss.  Where copies are equally good the choice is
arbitrary, and the ordering runs on down through independence, completeness,
extraction layer, age and finally the id, so that arbitrary still means
deterministic.  The same corpus nominates the same primary every time; a
duplicate resolution that reshuffled itself between runs would be evidence of
nothing.

Case scope
----------

Neither fingerprint includes the case, so a statement filed in two matters
produces the same key in both.  That is deliberate.  Seeing it is useful.
Acting on it is not permitted, and the split is enforced here rather than left
to a convention: every function that changes a status takes a ``case_id`` and
filters on it, and the one function that looks across matters
(``cross_matter_sightings``) returns rows and writes nothing.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Iterable, Mapping, Optional, Sequence

from sqlalchemy import select, update

from postgres.models.enums import (
    AdjudicationDecision,
    AdjudicationSubject,
    DocumentStatus,
    DuplicateMatchRung,
    LedgerStatus,
    ReconciliationStatus,
)
from postgres.models.financial import (
    FinancialAccount,
    AdjudicationEvent,
    FinancialSourceDocument,
    FinancialStatementPeriod,
    FinancialTransaction,
)
from services.financial.decisions import Actor, record
from services.financial.periods import read_closing, read_opening
from services.financial.reconcile import evaluate_identity, total_transactions

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.orm import Session


_RECORD = "\x1e"


class DuplicateError(Exception):
    """Raised when a duplicate operation is asked for something incoherent."""


class CrossCaseError(DuplicateError):
    """Raised on any attempt to act on a document in another matter.

    This is its own type because it is the one mistake in this module that
    would be a confidentiality breach rather than a bug.
    """


@dataclass(frozen=True)
class DocumentFingerprint:
    """The two fingerprints of one document, coarse and fine."""

    # Accounts, bounds and currency.  Groups candidates.
    group_key: Optional[str]
    # Includes all rows and balance observations. None means no comparison data.
    content_fingerprint: Optional[str]


@dataclass(frozen=True)
class GroupMember:
    document_id: uuid.UUID
    rung: DuplicateMatchRung
    is_primary: bool
    excluded: bool
    review_required: bool


@dataclass(frozen=True)
class DuplicateGroup:
    """One set of documents covering the same accounts over the same dates."""

    group_key: str
    case_id: uuid.UUID
    primary_id: uuid.UUID
    members: tuple[GroupMember, ...]

    @property
    def excluded_ids(self) -> tuple[uuid.UUID, ...]:
        return tuple(m.document_id for m in self.members if m.excluded)

    @property
    def review_required(self) -> bool:
        return any(m.review_required for m in self.members)


@dataclass(frozen=True)
class CrossMatterSighting:
    """The same statement, seen in a different matter.  Observation only."""

    document_id: uuid.UUID
    case_id: uuid.UUID
    group_key: str
    same_reading: bool


# ---------------------------------------------------------------------------
# Fingerprints
# ---------------------------------------------------------------------------


def _digest(parts: Iterable[str]) -> str:
    joined = _RECORD.join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def fingerprint_document(
    session: "Session", document: FinancialSourceDocument
) -> DocumentFingerprint:
    """Compute both fingerprints from what the document was read to say.

    Periods and rows are sorted before hashing, so two readings that differ
    only in the order rows came back from the database are recognised as the
    same reading.  Sorting is on the content itself, not on any surrogate id,
    Account identity keys are used instead of per-case account IDs.
    Empty documents return no keys; absent data is not an identical reading.
    """
    periods = list(
        session.scalars(
            select(FinancialStatementPeriod).where(
                FinancialStatementPeriod.source_document_id == document.id
            )
        ).all()
    )

    rows = list(session.scalars(
        select(FinancialTransaction).where(
            FinancialTransaction.source_document_id == document.id
        )
    ))
    identity_keys = _account_identity_keys(
        session, {p.account_id for p in periods} | {r.account_id for r in rows}
    )
    return _fingerprint_contents(periods, rows, identity_keys)


def fingerprint_documents(session, documents):
    """Load a bounded comparison set once instead of querying each document."""
    ids = [d.id for d in documents]
    periods = list(session.scalars(select(FinancialStatementPeriod).where(
        FinancialStatementPeriod.source_document_id.in_(ids)))) if ids else []
    rows = list(session.scalars(select(FinancialTransaction).where(
        FinancialTransaction.source_document_id.in_(ids)))) if ids else []
    keys = _account_identity_keys(session, {p.account_id for p in periods} | {r.account_id for r in rows})
    period_groups, row_groups = {}, {}
    for period in periods:
        period_groups.setdefault(period.source_document_id, []).append(period)
    for row in rows:
        row_groups.setdefault(row.source_document_id, []).append(row)
    return ({d.id: _fingerprint_contents(period_groups.get(d.id, []), row_groups.get(d.id, []), keys)
             for d in documents}, row_groups)


def _fingerprint_contents(periods, rows, identity_keys):
    if not periods and not rows:
        return DocumentFingerprint(None, None)

    # Versioned, unambiguous encoding. Accounts can contain arbitrary text;
    # delimiter concatenation must not let a field masquerade as two fields.
    def encoded(value) -> str:
        return json.dumps(value, ensure_ascii=True, separators=(",", ":"))

    by_period: dict[uuid.UUID, list[str]] = {}
    unlinked: list[str] = []
    period_ids = {p.id for p in periods}
    for row in rows:
        value = encoded([identity_keys[row.account_id], row.currency, row.content_hash])
        if row.statement_period_id is None:
            unlinked.append(value)
        elif row.statement_period_id not in period_ids:
            raise DuplicateError("a transaction links to another document's period")
        else:
            by_period.setdefault(row.statement_period_id, []).append(value)

    coarse: list[str] = []
    fine: list[str] = []
    for period in periods:
        signature = [
            identity_keys[period.account_id],
            period.period_start.isoformat() if period.period_start else None,
            period.period_end.isoformat() if period.period_end else None,
            period.currency,
        ]
        coarse.append(encoded(["period", signature]))
        fine.append(encoded([
            "period", signature,
            period.period_start_source, period.period_end_source,
            period.opening_balance_minor, period.opening_balance_source,
            period.closing_balance_minor, period.closing_balance_source,
            sorted(by_period.get(period.id, [])),
        ]))

    # Payment files and ambiguous multi-period readings have unlinked rows.
    # These rows must participate even if the document also has periods.
    if unlinked:
        accounts = sorted({
            (identity_keys[r.account_id], r.currency)
            for r in rows if r.statement_period_id is None
        })
        coarse.append(encoded(["unlinked", accounts]))
        fine.append(encoded(["unlinked", sorted(unlinked)]))

    return DocumentFingerprint(
        group_key=_digest(["v2", *sorted(coarse)]),
        content_fingerprint=_digest(["v2", *sorted(fine)]),
    )


def _account_identity_keys(
    session: "Session", account_ids: set[uuid.UUID]
) -> Mapping[uuid.UUID, str]:
    if not account_ids:
        return {}
    rows = session.execute(
        select(FinancialAccount.id, FinancialAccount.identity_key).where(
            FinancialAccount.id.in_(account_ids)
        )
    ).all()
    return {row[0]: row[1] for row in rows}


def store_fingerprint(
    session: "Session", document: FinancialSourceDocument
) -> DocumentFingerprint:
    """Compute and persist a document's fingerprints."""
    fingerprint = fingerprint_document(session, document)
    document.duplicate_group_key = fingerprint.group_key
    document.content_fingerprint = fingerprint.content_fingerprint
    session.flush()
    return fingerprint


# ---------------------------------------------------------------------------
# Nomination
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Score:
    """How good a reading a document is, as a sortable tuple.

    Every component is 'lower is better' so the whole thing sorts ascending
    and the first element is the primary.
    """

    not_balanced: int
    unbalanced_count: int
    not_independent: int
    incomplete: int
    extraction_layer: int
    created_ordinal: float
    tiebreak: str

    def as_tuple(self) -> tuple:
        return (
            self.not_balanced,
            self.unbalanced_count,
            self.not_independent,
            self.incomplete,
            self.extraction_layer,
            self.created_ordinal,
            self.tiebreak,
        )


def score_document(
    session: "Session", document: FinancialSourceDocument
) -> _Score:
    """Rank one document as a reading, letting the arithmetic lead.

    The balance identity comes first because it is the only component that is
    evidence rather than metadata: a copy whose rows close against its printed
    balances has been shown to be complete, and a copy that does not close has
    been shown not to be.  Everything after it is a tiebreak among copies the
    arithmetic could not separate, ending with the id so that 'arbitrary' still
    means 'the same every time'.
    """
    periods = list(
        session.scalars(
            select(FinancialStatementPeriod).where(
                FinancialStatementPeriod.source_document_id == document.id
            )
        ).all()
    )

    balanced = unbalanced = 0
    independent = True
    complete = True
    for period in periods:
        # Nomination is also used by the read-only group preview. Evaluate
        # current rows without recording a reconciliation attempt: merely
        # viewing candidates must not rewrite totals, verdicts or timestamps.
        outcome = evaluate_identity(
            opening=read_opening(period),
            closing=read_closing(period),
            totals=total_transactions(
                session, period_id=period.id, currency=period.currency
            ),
            currency=period.currency,
        )
        if outcome.status == ReconciliationStatus.balanced:
            balanced += 1
        elif outcome.status == ReconciliationStatus.unbalanced:
            unbalanced += 1
        if not outcome.independent:
            independent = False
        if not outcome.totals.is_complete:
            complete = False

    created = document.created_at
    return _Score(
        not_balanced=0 if balanced else 1,
        unbalanced_count=unbalanced,
        not_independent=0 if independent else 1,
        incomplete=0 if complete else 1,
        extraction_layer=document.extraction_layer,
        created_ordinal=created.timestamp() if created else float("inf"),
        tiebreak=str(document.id),
    )


def nominate_primary(
    session: "Session",
    documents: Sequence[FinancialSourceDocument],
    *,
    scorer: Optional[Callable[["Session", FinancialSourceDocument], _Score]] = None,
) -> FinancialSourceDocument:
    """Pick the copy to keep.  Deterministic for a given set of documents."""
    if not documents:
        raise DuplicateError("cannot nominate a primary from an empty group")
    score = scorer or score_document
    return min(documents, key=lambda d: score(session, d).as_tuple())


# ---------------------------------------------------------------------------
# Grouping and resolution
# ---------------------------------------------------------------------------


def _rung_for(
    candidate: FinancialSourceDocument, primary: FinancialSourceDocument
) -> DuplicateMatchRung:
    """The strongest rung at which ``candidate`` matches ``primary``."""
    if (
        candidate.sha256_at_ingestion
        and candidate.sha256_at_ingestion == primary.sha256_at_ingestion
    ):
        return DuplicateMatchRung.identical_bytes
    if (
        candidate.content_fingerprint
        and candidate.content_fingerprint == primary.content_fingerprint
    ):
        return DuplicateMatchRung.identical_reading
    return DuplicateMatchRung.same_account_period


def _excludes(rung: DuplicateMatchRung) -> bool:
    """Whether a rung is strong enough to justify hiding a document.

    Only the two rungs that establish the documents say the same thing.  A
    shared account and period is a coincidence that legitimate evidence
    produces routinely.
    """
    return rung in (
        DuplicateMatchRung.identical_bytes,
        DuplicateMatchRung.identical_reading,
    )


def find_groups(session: "Session", case_id: uuid.UUID) -> tuple[DuplicateGroup, ...]:
    """Group a case's documents by fingerprint without changing anything.

    Scoped to the case, like everything in this module that could lead to an
    action.  Documents not yet fingerprinted are skipped rather than guessed
    at; a null group key means 'not computed', not 'unique'.
    """
    documents = list(
        session.scalars(
            select(FinancialSourceDocument)
            .where(FinancialSourceDocument.case_id == case_id)
            .where(FinancialSourceDocument.duplicate_group_key.is_not(None))
            .where(
                FinancialSourceDocument.status.in_(
                    (DocumentStatus.admitted.value, DocumentStatus.superseded.value)
                )
            )
        ).all()
    )

    by_key: dict[str, list[FinancialSourceDocument]] = {}
    for document in documents:
        by_key.setdefault(document.duplicate_group_key, []).append(document)

    groups: list[DuplicateGroup] = []
    for key, members in sorted(by_key.items()):
        if len(members) < 2:
            continue
        primary = nominate_primary(session, members)
        entries: list[GroupMember] = []
        for member in sorted(members, key=lambda d: str(d.id)):
            if member.id == primary.id:
                entries.append(
                    GroupMember(
                        document_id=member.id,
                        rung=DuplicateMatchRung.identical_bytes,
                        is_primary=True,
                        excluded=False,
                        review_required=False,
                    )
                )
                continue
            rung = _rung_for(member, primary)
            entries.append(
                GroupMember(
                    document_id=member.id,
                    rung=rung,
                    is_primary=False,
                    excluded=_excludes(rung),
                    # Flagged either way.  A strong match is excluded and still
                    # reviewed, because an automatic exclusion nobody looks at
                    # is a quiet deletion.
                    review_required=True,
                )
            )
        groups.append(
            DuplicateGroup(
                group_key=key,
                case_id=case_id,
                primary_id=primary.id,
                members=tuple(entries),
            )
        )
    return tuple(groups)


def resolve_duplicates(
    session: "Session",
    case_id: uuid.UUID,
    *,
    actor: Actor,
    ingestion_run_id: Optional[uuid.UUID] = None,
) -> tuple[DuplicateGroup, ...]:
    """Apply the default policy: auto-exclude the strong matches, flag them all.

    Returns the groups it acted on, so a caller can report what happened
    without recomputing it.

    ``actor`` is required even though the exclusions are automatic, and that is
    the point.  "The system did it" is not an answer to who took a document out
    of every total; some person ran this, under this policy, and that is who
    the log should name.  ``ingestion_run_id`` records which execution, so the
    pair together say who and when without either standing in for the other.
    """
    if not isinstance(actor, Actor):
        raise DuplicateError(
            f"resolve_duplicates needs an Actor, got {type(actor).__name__}; "
            "an automatic exclusion is still somebody's decision"
        )
    groups = find_groups(session, case_id)
    for group in groups:
        for member in group.members:
            document = session.get(FinancialSourceDocument, member.document_id)
            if document is None:  # pragma: no cover - defensive
                continue
            if document.case_id != case_id:  # pragma: no cover - defensive
                raise CrossCaseError(
                    f"document {document.id} belongs to case {document.case_id}, "
                    f"not {case_id}; refusing to change its status"
                )
            document.duplicate_review_required = member.review_required
            if member.is_primary:
                continue
            if member.excluded:
                # The rung is set inside `_supersede`, after the event is
                # written.  Setting it here first would make the `before`
                # snapshot record the new rung as the old one -- a diff that
                # says a field did not change while changing it.
                _supersede(
                    session,
                    document,
                    group.primary_id,
                    case_id=case_id,
                    rung=member.rung,
                    actor=actor,
                    ingestion_run_id=ingestion_run_id,
                )
            else:
                document.duplicate_match_rung = int(member.rung)
    session.flush()
    return groups


def _supersede(
    session: "Session",
    document: FinancialSourceDocument,
    primary_id: uuid.UUID,
    *,
    case_id: uuid.UUID,
    rung: DuplicateMatchRung,
    actor: Actor,
    ingestion_run_id: Optional[uuid.UUID] = None,
    reason: Optional[str] = None,
) -> None:
    """Append the decision, then hide the document and its rows.

    The row-level trace of a supersession survives it — ``superseded_by_id``
    keeps pointing at the primary — so unlike a quarantine this disposition is
    not erased by its own columns.  It is recorded anyway, because the reversal
    is: ``restore_document`` nulls ``superseded_by_id`` and
    ``duplicate_match_rung``, and without an event the restored document is
    indistinguishable from one that was never superseded at all.  Recording
    only one side of a pair gives a log that is worse than none, because the
    absences read as facts.

    ``resolve_duplicates`` is re-runnable, so this function is reached routinely
    for documents that are already superseded by this primary at this rung.
    That is not a decision — nothing changes — and appending an event for it
    would make the log answer "how many times was this excluded" with the
    number of times the resolver happened to be run.  So the event is written
    only when the two snapshots differ.  The row-level update below is not
    skipped with it: a row ingested against this document after the supersession
    would still be admitted, and hiding it is reconciling state rather than
    taking a decision.
    """
    if reason is not None and (not isinstance(reason, str) or not reason.strip()):
        raise ValueError("A supplied replacement reason must be nonempty text.")
    before = {
        "status": document.status,
        "superseded_by_id": str(document.superseded_by_id)
        if document.superseded_by_id
        else None,
        "duplicate_match_rung": document.duplicate_match_rung,
    }
    after = {
        "status": DocumentStatus.superseded.value,
        "superseded_by_id": str(primary_id),
        "duplicate_match_rung": int(rung),
    }

    if before != after:
        record(
            session,
            case_id=case_id,
            subject=document,
            subject_type=AdjudicationSubject.source_document,
            decision=AdjudicationDecision.supersede_duplicate,
            reason=reason if reason is not None else (
                f"duplicate of {primary_id} at rung {int(rung)} "
                f"({rung.name}); excluded from every total in favour of the primary"
            ),
            actor=actor,
            before=before,
            after=after,
            ingestion_run_id=ingestion_run_id,
        )

    document.status = DocumentStatus.superseded.value
    document.superseded_by_id = primary_id
    document.duplicate_match_rung = int(rung)
    session.execute(
        update(FinancialTransaction)
        .where(FinancialTransaction.source_document_id == document.id)
        .where(FinancialTransaction.ledger_status == LedgerStatus.admitted.value)
        .values(ledger_status=LedgerStatus.superseded.value)
    )


def restore_document(
    session: "Session",
    document: FinancialSourceDocument,
    *,
    case_id: uuid.UUID,
    actor: Actor,
    reason: str,
    ingestion_run_id: Optional[uuid.UUID] = None,
) -> None:
    """Undo a supersession, for when the nomination was wrong.

    Only rows this module superseded are readmitted.  A row quarantined or
    rejected for its own reasons keeps that status, because restoring a
    document is a statement about the document and not a licence to overturn
    every other decision made about its contents.

    An actor and a reason are now required, and were not before.  This function
    put a document back into every total and left nothing behind saying who
    decided that or why — it nulls ``superseded_by_id`` and
    ``duplicate_match_rung``, which are the only two columns that recorded the
    exclusion, so afterwards the document read as one that had never been a
    duplicate.  A wrong nomination and a nomination reversed under pressure
    looked the same in the ledger.
    """
    if not isinstance(actor, Actor):
        raise DuplicateError(
            f"restore_document needs an Actor, got {type(actor).__name__}"
        )
    if not reason or not reason.strip():
        raise DuplicateError(
            "a restore without a stated reason is not an adjudication, it is "
            "an unexplained readmission"
        )
    if document.case_id != case_id:
        raise CrossCaseError(
            f"document {document.id} belongs to case {document.case_id}, "
            f"not {case_id}; refusing to restore it"
        )

    record(
        session,
        case_id=case_id,
        subject=document,
        subject_type=AdjudicationSubject.source_document,
        decision=AdjudicationDecision.restore_document,
        reason=reason,
        actor=actor,
        before={
            "status": document.status,
            "superseded_by_id": str(document.superseded_by_id)
            if document.superseded_by_id
            else None,
            "duplicate_match_rung": document.duplicate_match_rung,
            "duplicate_review_required": document.duplicate_review_required,
        },
        after={
            "status": DocumentStatus.admitted.value,
            "superseded_by_id": None,
            "duplicate_match_rung": None,
            "duplicate_review_required": False,
        },
        ingestion_run_id=ingestion_run_id,
    )

    document.status = DocumentStatus.admitted.value
    document.superseded_by_id = None
    document.duplicate_match_rung = None
    document.duplicate_review_required = False
    session.execute(
        update(FinancialTransaction)
        .where(FinancialTransaction.source_document_id == document.id)
        .where(FinancialTransaction.ledger_status == LedgerStatus.superseded.value)
        .values(ledger_status=LedgerStatus.admitted.value)
    )
    session.flush()


# ---------------------------------------------------------------------------
# Cross-matter observation
# ---------------------------------------------------------------------------


def cross_matter_sightings(
    session: "Session", document: FinancialSourceDocument
) -> tuple[CrossMatterSighting, ...]:
    """Where else this statement has been seen.  Reads only; never acts.

    The same statement turning up in two matters is worth knowing and is not
    grounds for touching either one.  This function exists so that the useful
    half of that can be had without the dangerous half being one careless
    query away: it returns rows, it takes no status arguments, and there is no
    code path from it to a write.
    """
    if not document.duplicate_group_key:
        return ()
    rows = session.execute(
        select(
            FinancialSourceDocument.id,
            FinancialSourceDocument.case_id,
            FinancialSourceDocument.duplicate_group_key,
            FinancialSourceDocument.content_fingerprint,
        )
        .where(
            FinancialSourceDocument.duplicate_group_key
            == document.duplicate_group_key
        )
        .where(FinancialSourceDocument.case_id != document.case_id)
    ).all()
    return tuple(
        CrossMatterSighting(
            document_id=row[0],
            case_id=row[1],
            group_key=row[2],
            same_reading=bool(
                row[3] and row[3] == document.content_fingerprint
            ),
        )
        for row in sorted(rows, key=lambda r: str(r[0]))
    )


# ---------------------------------------------------------------------------
# Purge
# ---------------------------------------------------------------------------


def purge_document(
    session: "Session",
    document: FinancialSourceDocument,
    *,
    case_id: uuid.UUID,
    reason: str,
    actor: Actor,
    ingestion_run_id: Optional[uuid.UUID] = None,
) -> AdjudicationEvent:
    """Delete a duplicate for good.  Separate from hiding, and on purpose.

    Hiding is reversible and is what the automatic path does.  Purging is not
    reversible, so it is never automatic, it requires a stated reason, and it
    is refused across matters outright rather than merely filtered.

    The adjudication is written and flushed before the delete.
    ``AdjudicationEvent`` carries no foreign key to its subject precisely
    so that the record of a decision can outlive the row it was about.  Within
    a single transaction the committed end state does not depend on which of
    the two writes is issued first, so the ordering here buys two narrower
    things: the caller is handed a row that already has an identity, and if
    the delete raises, the decision is what is in hand rather than nothing.
    """
    if document.case_id != case_id:
        raise CrossCaseError(
            f"document {document.id} belongs to case {document.case_id}, "
            f"not {case_id}; refusing to purge it"
        )
    if not reason or not reason.strip():
        raise DuplicateError(
            "a purge without a stated reason is not an adjudication, "
            "it is an unexplained deletion"
        )

    # Refuse to purge a document other documents were superseded in favour of.
    # The foreign key is ON DELETE SET NULL, so the delete would succeed and
    # leave those documents hidden with nothing recording what they were hidden
    # for -- superseded by null.  That is a worse state than either outcome the
    # caller was choosing between, and it would be silent.  Restore or
    # re-resolve the group first, then purge.
    dependents = session.scalars(
        select(FinancialSourceDocument.id).where(
            FinancialSourceDocument.superseded_by_id == document.id
        )
    ).all()
    if dependents:
        raise DuplicateError(
            f"document {document.id} is the primary for "
            f"{len(dependents)} superseded document(s); purging it would leave "
            "them hidden with no record of what superseded them -- restore or "
            "re-resolve the group first"
        )

    adjudication = record(
        session,
        case_id=case_id,
        subject=document,
        subject_type=AdjudicationSubject.source_document,
        decision=AdjudicationDecision.purge_duplicate,
        reason=reason,
        actor=actor,
        before={
            "status": document.status,
            "duplicate_group_key": document.duplicate_group_key,
            "content_fingerprint": document.content_fingerprint,
            "duplicate_match_rung": document.duplicate_match_rung,
            "superseded_by_id": str(document.superseded_by_id)
            if document.superseded_by_id
            else None,
            "sha256_at_ingestion": document.sha256_at_ingestion,
        },
        # `after=None` is the honest snapshot here and the only place in this
        # module it is right: the subject will not exist.  It is also why
        # `_check_diff` tolerates a one-sided pair rather than demanding
        # matching keys unconditionally.
        after=None,
        ingestion_run_id=ingestion_run_id,
    )

    session.delete(document)
    session.flush()
    return adjudication
