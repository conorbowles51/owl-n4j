"""Ingesting one evidence file into the ledger, run and all.

:mod:`~services.financial.native_ingest` writes a reading.  It takes an open run
as an argument and imports :mod:`~services.financial.runs` only under
``TYPE_CHECKING``, which is the module saying that it does not own run
lifecycle: one run is meant to be able to cover many documents, and a driver
that opened its own could never be used that way.  This module is the caller
that supplies the missing half for the one-file case -- find the file, read it,
open a run around the write, and turn every way it can fail into a word.

Why the run opens late
----------------------

A file that will not parse never reaches a run.  The bytes were not a bank
file, no document was seen, and a run whose counts are all zero because someone
uploaded a photograph is a record of nothing.  The caller is told why in the
same response, so nothing is lost by not having written it down.

The failures that happen *inside* the write are the opposite case, and they are
why the run exists.  A period that contradicts one already stored is decided
against the database, not against the file, so it can only be found after the
run is open; the run then terminates ``failed`` on its own session while the
caller's session rolls the half-written document away.  That the two use
separate sessions is :mod:`~services.financial.runs`'s design, and it is what
makes the record that the attempt happened survive the discarding of what it
attempted.

Why a file the case already holds is refused
--------------------------------------------

``record_source_document`` writes one row per file *per run*, and says that
re-ingesting the same file under a new run is a new row on purpose: a second
reading may have used a different parser, and overwriting the first would
destroy the record that it ever said something else.  ``record_transactions``
deduplicates on ``(source_document_id, content_hash)``, and the second document
is a different document, so nothing in the writers stops the second set of rows
being drafted.

The database stops it.  ``FinancialTransaction.ref_id`` is
``build_ref_id(document.sha256_at_ingestion, content)``
(``transactions.py:666``), a pure function of the file's bytes and the row's --
``references.py`` says it takes the digest and not the document's surrogate id
"so that re-ingesting the same file reproduces the same references rather than
a fresh set".  ``uq_financial_transactions_case_ref`` on ``(case_id, ref_id)``
then refuses the second set outright.  The case's money cannot silently double;
that is a property of the schema, not of this module.

What the schema gives instead is the wrong error.  Without a check here, a
second click opens a run, writes a source document, its accounts and its
periods, hits the constraint on the first transaction, and returns
``write_failed`` carrying a constraint name -- everything discarded, a failed
run on the record, and nothing on the screen saying the plain thing, which is
that this file is already in the ledger.  So the check is made before any of
that, against the documents the case already holds, and the answer names the
document holding it.

There is deliberately no override.  A re-read that would clear the constraint
is one whose rows hash differently -- a different window, a different assumed
currency, a genuinely different parse -- and storing it would leave one case
holding two contradictory readings of one file with nothing able to say which
governs.  Resolving that is :mod:`~services.financial.duplicates`, which is not
yet reachable from anywhere.  An override belongs with it and not before it.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from sqlalchemy.exc import SQLAlchemyError

from postgres.models.financial import FinancialSourceDocument
from services.financial.accounts import AccountError
from services.financial.documents import SourceDocumentError
from services.financial.native import CenturyWindow
from services.financial.native_ingest import (
    ContradictoryPeriodError,
    IngestionError,
    NativeIngestion,
    UnattributableRowError,
    ingest_native_reading,
)
from services.financial.native_precheck import (
    NativeParse,
    PrecheckOutcome,
    read_case_file,
)
from services.financial.native_subjects import SubjectError
from services.financial.periods import PeriodError
from services.financial.runs import RunScopeError, ingestion_run
from services.financial.transactions import TransactionWriteError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class IngestOutcome(str, Enum):
    """What the attempt came to, in one word per thing the caller can do next.

    The five reading words are :class:`~services.financial.native_precheck.
    PrecheckOutcome`'s own, spelled identically on purpose: the precheck dialog
    and the ingest that follows it describe the same file, and a file that
    precheck called ``unrecognised`` must not come back from ingest under
    another name.  :data:`READING_OUTCOMES` holds the mapping and a test holds
    it to being total.

    Where ingestion knows more than precheck could, it says more.  Precheck
    reports one ``unattributable`` because it cannot tell a document whose
    accounts will not describe from one whose rows will not attribute without
    running the writers.  By the time a write fails, which of the two happened
    is known, and the two call for different things: a document that cannot be
    described at all is a file to look at again, and a row naming an account
    the document never introduced is a file that is missing part of itself.
    """

    #: Written.  The document, its accounts, its periods and its rows are in
    #: the ledger and the run is ``completed``.
    stored = "stored"
    #: This case already holds a document for this file.  Nothing was written.
    already_ingested = "already_ingested"
    #: No such file in this case.  Reported identically to a file in another
    #: case, for the reason ``precheck_case_file`` gives.
    not_found = "not_found"
    #: No native parser claims these bytes.
    unrecognised = "unrecognised"
    #: More than one does, so the format is in doubt.
    ambiguous = "ambiguous"
    #: A two-digit year on a row has no reading inside the stated window.
    out_of_window = "out_of_window"
    #: The file could not be opened, or a parser fell over on it.
    unreadable = "unreadable"
    #: The file parsed, but its accounts could not be described as read.
    undescribable = "undescribable"
    #: A row names an account the document does not describe.  Storing it would
    #: either invent an account or put the movement on somebody else's.
    unattributable = "unattributable"
    #: The document covers one account's one span twice and disagrees with
    #: itself about it.  Only one claim could be stored and neither is the
    #: document's claim.
    contradictory_period = "contradictory_period"
    #: The writer refused for a reason of its own.  Present so that a refusal
    #: added to ``native_ingest`` later arrives here as an outcome rather than
    #: escaping as a failed request.
    refused = "refused"
    #: The write itself failed: a field too long for its column, a row scoped
    #: to another case, a constraint. Distinct from ``refused`` because a
    #: refusal is a judgement about the evidence and this is a fault.
    write_failed = "write_failed"


#: The reading outcomes ingestion inherits from precheck, by the name each has
#: there.  ``readable`` is absent deliberately: it is precheck's word for "this
#: would ingest", and once it has, the word is ``stored``.
READING_OUTCOMES: dict[PrecheckOutcome, IngestOutcome] = {
    PrecheckOutcome.not_found: IngestOutcome.not_found,
    PrecheckOutcome.unrecognised: IngestOutcome.unrecognised,
    PrecheckOutcome.ambiguous: IngestOutcome.ambiguous,
    PrecheckOutcome.out_of_window: IngestOutcome.out_of_window,
    PrecheckOutcome.unreadable: IngestOutcome.unreadable,
    PrecheckOutcome.unattributable: IngestOutcome.unattributable,
}


@dataclass(frozen=True, slots=True)
class FileIngestion:
    """What one attempt at one file came to.

    Everything the caller needs to say what happened without asking again, and
    identifiers rather than rows, because the session that produced them is
    closed by the time a response is serialised.
    """

    file_id: str
    outcome: IngestOutcome
    file_name: Optional[str] = None
    reason: Optional[str] = None
    #: Set whenever a run was opened, including when it failed.  A failed run
    #: is the record that the attempt happened and is worth reporting.
    run_id: Optional[str] = None
    document_id: Optional[str] = None
    detected_format: Optional[str] = None
    account_ids: tuple[str, ...] = ()
    period_ids: tuple[str, ...] = ()
    transactions_stored: int = 0
    #: Rows stored without a period link because their account has more than
    #: one span in this document and nothing on the row says which.
    unlinked_rows: int = 0
    adjudication_id: Optional[str] = None

    @property
    def stored(self) -> bool:
        return self.outcome is IngestOutcome.stored

    def as_dict(self) -> dict[str, Any]:
        return {
            "file_id": self.file_id,
            "file_name": self.file_name,
            "outcome": self.outcome.value,
            "stored": self.stored,
            "reason": self.reason,
            "run_id": self.run_id,
            "document_id": self.document_id,
            "detected_format": self.detected_format,
            "account_ids": list(self.account_ids),
            "period_ids": list(self.period_ids),
            "transactions_stored": self.transactions_stored,
            "unlinked_rows": self.unlinked_rows,
            "adjudication_id": self.adjudication_id,
        }


def existing_document_for(
    db: "Session", *, case_id: uuid.UUID, file_id: uuid.UUID
) -> Optional[FinancialSourceDocument]:
    """The earliest document this case already holds for this evidence file.

    Earliest rather than latest so that the identifier reported back is the one
    the ledger was first built on, which is the row a person looking for "where
    did this file go" will find.
    """
    return (
        db.query(FinancialSourceDocument)
        .filter(
            FinancialSourceDocument.case_id == case_id,
            FinancialSourceDocument.evidence_file_id == file_id,
        )
        .order_by(FinancialSourceDocument.created_at.asc())
        .first()
    )


def _unread(parse: NativeParse) -> FileIngestion:
    """A parse that never happened, as an outcome.  No run was opened."""
    outcome = READING_OUTCOMES.get(
        parse.outcome or PrecheckOutcome.unreadable, IngestOutcome.unreadable
    )
    return FileIngestion(
        file_id=parse.file_id,
        file_name=parse.file_name,
        outcome=outcome,
        reason=parse.reason,
    )


def ingest_case_file(
    db: "Session",
    *,
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    resolve_path: Callable[[Optional[str]], Optional[Path]],
    window: CenturyWindow,
    default_currency: Optional[str] = None,
    document_type: Optional[str] = None,
    institution_name: Optional[str] = None,
    actor: Any = None,
    session_factory: Any = None,
) -> FileIngestion:
    """Read one evidence file and store what it holds, under a recorded run.

    ``window`` is required for the reason the precheck endpoint gives: three of
    the four native formats print two-digit years and none of them carries the
    century, so a default here would decide which decade a statement belongs to
    silently, in the one place the document itself offers no help.

    The caller's ``db`` is committed here on success.  Nothing under
    ``services.financial`` commits -- the writers flush so that a constraint
    violation surfaces where the draft that caused it is still in hand, and
    leave the transaction open -- so a caller that did not commit would return
    a response describing rows that were about to be discarded.

    Failure returns rather than raises, in every case the evidence can cause.
    A fault that is not about the evidence propagates, because inventing an
    outcome for something unanticipated would file a bug as a finding.
    """
    parse = read_case_file(
        db,
        case_id=case_id,
        file_id=file_id,
        resolve_path=resolve_path,
        window=window,
        default_currency=default_currency,
    )
    if parse.reading is None or not parse.sha256:
        return _unread(parse)

    already = existing_document_for(db, case_id=case_id, file_id=file_id)
    if already is not None:
        return FileIngestion(
            file_id=parse.file_id,
            file_name=parse.file_name,
            outcome=IngestOutcome.already_ingested,
            document_id=str(already.id),
            run_id=str(already.ingestion_run_id),
            detected_format=parse.reading.format.value,
            reason=(
                "this case already holds a reading of this file, stored under "
                "the document named here"
            ),
        )

    detected = parse.reading.format.value
    run_id: Optional[str] = None
    ingestion: Optional[NativeIngestion] = None

    def refusal(outcome: IngestOutcome, reason: str) -> FileIngestion:
        db.rollback()
        return FileIngestion(
            file_id=parse.file_id,
            file_name=parse.file_name,
            outcome=outcome,
            reason=reason,
            run_id=run_id,
            detected_format=detected,
        )

    try:
        with ingestion_run(
            case_id=case_id,
            actor=actor,
            session_factory=session_factory,
            notes=f"native ingest of evidence file {parse.file_id}",
        ) as run:
            run_id = str(run.run_id)
            try:
                ingestion = ingest_native_reading(
                    db,
                    run,
                    parse.reading,
                    evidence_file_id=file_id,
                    sha256=parse.sha256,
                    window=window,
                    document_type=document_type,
                    institution_name=institution_name,
                )
                # Inside the block on purpose: a commit that fails has failed
                # the run, and terminating it ``completed`` first would put a
                # run on the record as having stored what was rolled back.
                db.commit()
            except BaseException:
                # Roll back here rather than leaving it to ``refusal`` below.
                # On the way out of this block ``ingestion_run`` terminates the
                # run ``failed``, and it does that on a session of its own so
                # the record survives the discarding of what it attempted.  A
                # write transaction still open on this session while that
                # ``UPDATE`` runs makes the two sessions contend, and
                # ``runs._terminate_quietly`` swallows the failure by design
                # rather than mask the real exception -- so the run would be
                # left ``running`` and only the reaper would ever close it.
                # Postgres happens not to contend here; SQLite locks the whole
                # file and does.  The rollback costs nothing and removes the
                # question.
                db.rollback()
                raise
    except SubjectError as exc:
        return refusal(IngestOutcome.undescribable, str(exc))
    except UnattributableRowError as exc:
        return refusal(IngestOutcome.unattributable, str(exc))
    except ContradictoryPeriodError as exc:
        return refusal(IngestOutcome.contradictory_period, str(exc))
    except IngestionError as exc:
        return refusal(IngestOutcome.refused, str(exc))
    except (
        AccountError,
        PeriodError,
        SourceDocumentError,
        TransactionWriteError,
        RunScopeError,
        SQLAlchemyError,
    ) as exc:
        logger.exception(
            "Writing evidence file %s into case %s failed", file_id, case_id
        )
        return refusal(IngestOutcome.write_failed, str(exc))
    except Exception:
        db.rollback()
        raise

    if ingestion is None:
        # ``ingestion_run`` suppresses ``RunAborted`` and leaves the block by
        # its normal exit, so an abort arrives here as a missing result rather
        # than as an exception.  Nothing in the write path raises it today;
        # without this the day something does would produce a ``NameError``
        # from a line that looks like it cannot fail.
        return refusal(IngestOutcome.refused, "the ingestion run was aborted")

    return FileIngestion(
        file_id=parse.file_id,
        file_name=parse.file_name,
        outcome=IngestOutcome.stored,
        run_id=run_id,
        document_id=str(ingestion.document.id),
        detected_format=detected,
        account_ids=tuple(str(account.id) for account in ingestion.accounts),
        period_ids=tuple(str(period.id) for period in ingestion.periods),
        transactions_stored=ingestion.row_count,
        unlinked_rows=ingestion.unlinked_rows,
        adjudication_id=(
            str(ingestion.adjudication.id)
            if ingestion.adjudication is not None
            else None
        ),
    )
