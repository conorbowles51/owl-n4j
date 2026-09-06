"""Overruling the router about one file, on a named person's word.

:mod:`services.financial.route_check` answers "may I send this to the document
pipeline?" and, for four of its six outcomes, answers no.
:mod:`services.financial.admission` writes down a person overruling that no.
Between them there was nothing: ``record_admission`` had no caller, so the
override existed as a function and not as anything a person could do.  This
module is the caller.

Why the check is re-run here and not accepted from the request
--------------------------------------------------------------

``record_admission`` takes a :class:`~services.financial.route_check.FileRouteCheck`
and copies its finding into the event verbatim.  That is right -- the finding
has to be the one the decision was taken against, because the detector changes
and a finding re-derived later would describe a different question.  But it
means whoever supplies the check decides what the record says was found.  A
check that arrived over the wire could say anything, and the log would carry it
as the router's judgement.

So the check is read from the file again, here, immediately before the event is
written.  The cost is one prefix read.  What it buys is that the finding in the
log is the finding, and not a claim about it.

There is a window between the interface showing a person the router's answer
and this function reading the file again, and in principle the file could be
replaced inside it.  If that happens the record still describes what was
actually there at the moment of the decision, which is the property that
matters; what it would no longer describe is what the person was looking at.
That is a smaller wrong than a caller-supplied finding, and it is the direction
the error should fall.

Every outcome the router blocks on is overridable
--------------------------------------------------

Including ``native`` -- a file the ledger could read exactly.  Admitting one of
those means its figures will be inferred from text rather than parsed, which is
the failure this whole subsystem exists to prevent, so it is worth saying why
it is nonetheless allowed.

:class:`~postgres.models.enums.AdjudicationDecision` settles it in its own
prose: ``admit_financial_document`` is described there as being for "a bank
statement that arrived on the evidence list ... admitted *out* to that pipeline
anyway, by a named person who was shown what the router found and chose to
proceed."  That is the native case by name.  The detector reads a prefix and
matches a signature; it can be wrong, and a file it wrongly claims would
otherwise have no path at all -- the ledger cannot parse it and the pipeline
will not take it.  The answer to a detector that might be wrong is a person who
can say so on the record, not a refusal nobody can get past.

**Known gap, and it is in the other service.** The engine runs its own
pre-stage, ``evidence-engine/app/pipeline/orchestrator.py``, which fails any job
whose file it detects as native, and it has no channel by which an admission
recorded here could reach it.  So an admitted native file is recorded here,
sent, and then refused there with a message naming the format.  Nothing is lost
and nothing is silent, but the override does not yet take effect for that one
outcome.  Closing it is an engine change and is not this unit.

What this does not do
---------------------

It does not send the file.  ``admission`` states the rule as "the event is
written before the file is sent, or it is not sent", and recording is the first
half of it.  The second half is a gate on the processing route that refuses a
blocked file with no admission behind it, which is what turns "written first"
from a convention into a guarantee.  Until that lands, this records an override
that the processing route does not yet consult.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from sqlalchemy.exc import SQLAlchemyError

from postgres.models.evidence import EvidenceFile
from services.financial.admission import (
    ROUTED_DOCUMENT_PIPELINE,
    ROUTED_HELD,
    AdmissionError,
    record_admission,
)
from services.financial.decisions import DecisionError
from services.financial.quarantine_row import ActorError, actor_from_user
from services.financial.route_check import check_path

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class FileAdmissionOutcome(str, Enum):
    """What the attempt came to, in one word per thing the caller can do next."""

    #: The override is on the record.  It names the person, the grounds, and
    #: what the router had found at the moment they overruled it.
    admitted = "admitted"
    #: No such file in this case.  Reported identically to a file in another
    #: case, so that asking cannot be used to learn what a case the caller
    #: cannot see contains.
    not_found = "not_found"
    #: The router is not holding this file, so there is no no to overrule.
    #: A fact about the file, not a fault: nothing stops it being processed.
    nothing_to_override = "nothing_to_override"
    #: The request could not be turned into a decision -- no actor to name, or
    #: the log refused the event.  Nothing was written.
    refused = "refused"
    #: The write itself failed.  Rolled back and logged.
    write_failed = "write_failed"


@dataclass(frozen=True, slots=True)
class FileAdmission:
    """One attempt to overrule the router about one file, and what became of it."""

    file_id: str
    outcome: FileAdmissionOutcome
    #: Why the attempt came out as it did.  On ``admitted`` this is the
    #: person's own stated grounds, echoed back so the caller can show what
    #: went into the log rather than what it sent.
    reason: Optional[str] = None
    file_name: Optional[str] = None
    #: What the router found, read from the file at the moment of the decision.
    #: Absent only when there was no file to read.
    route_outcome: Optional[str] = None
    detected_format: Optional[str] = None
    claimants: tuple[str, ...] = ()
    #: Set only when a decision was actually appended.
    adjudication_id: Optional[str] = None

    @property
    def admitted(self) -> bool:
        """Whether this attempt put an override on the record."""
        return self.outcome is FileAdmissionOutcome.admitted

    @property
    def routed_to(self) -> str:
        """Where the file stands after the attempt, in the log's own words.

        The same two constants the event carries, so a reader of the response
        and a reader of the log are told the same thing in the same vocabulary
        rather than in two that have to be mapped onto each other.
        """
        return ROUTED_DOCUMENT_PIPELINE if self.admitted else ROUTED_HELD

    def as_dict(self) -> dict[str, Any]:
        return {
            "file_id": self.file_id,
            "outcome": self.outcome.value,
            "admitted": self.admitted,
            "routed_to": self.routed_to,
            "reason": self.reason,
            "file_name": self.file_name,
            "route_outcome": self.route_outcome,
            "detected_format": self.detected_format,
            "claimants": list(self.claimants),
            "adjudication_id": self.adjudication_id,
        }


def find_case_file(
    session: "Session",
    *,
    case_id: uuid.UUID,
    file_id: uuid.UUID,
) -> Optional[EvidenceFile]:
    """One evidence file, or ``None`` if it is not this case's.

    A file belonging to another matter returns ``None`` rather than raising, so
    that the caller reports it the same way it reports a file that does not
    exist.  Two different refusals here would let a caller distinguish the two
    and so enumerate another case's evidence one id at a time.
    """
    record = session.get(EvidenceFile, file_id)
    if record is None or record.case_id != case_id:
        return None
    return record


def admit_case_file(
    session: "Session",
    *,
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    actor: Any,
    reason: str,
    resolve_path: Callable[[Optional[str]], Optional[Path]],
) -> FileAdmission:
    """Record one person's decision to send a held file to the document pipeline.

    ``resolve_path`` is required and not defaulted for the reason
    :func:`~services.financial.route_check.check_case_files` gives: the stored
    path on an evidence file is not always a path this process can open, the
    router owns the function that reconciles the two, and a default of "use it
    as written" would work in development and fail quietly in a container.

    The caller's ``session`` is committed here on success, and rolled back on
    every failure, for the reason
    :func:`~services.financial.quarantine_row.quarantine_case_row` gives: the
    decision and the state it describes move together or neither moves.

    Nothing is deduplicated.  Two calls append two events, because an admission
    authorises one send and two sends are two decisions --
    :class:`~postgres.models.enums.AdjudicationDecision` says so in as many
    words, and it takes no reversal member for the same reason: a send cannot
    be un-sent.
    """
    record = find_case_file(session, case_id=case_id, file_id=file_id)
    if record is None:
        return FileAdmission(
            file_id=str(file_id),
            outcome=FileAdmissionOutcome.not_found,
            reason="no such file in this case",
        )

    check = check_path(
        resolve_path(record.stored_path),
        file_id=str(record.id),
        file_name=record.original_filename,
    )

    if not check.blocks_document_processing:
        return FileAdmission(
            file_id=str(record.id),
            outcome=FileAdmissionOutcome.nothing_to_override,
            reason=(
                "the router is not holding this file, so there is nothing to "
                "overrule; it can be processed without a recorded decision"
            ),
            file_name=check.file_name,
            route_outcome=check.outcome,
            detected_format=check.detected_format,
            claimants=check.claimants,
        )

    try:
        actor_record = actor_from_user(actor)
    except ActorError as exc:
        return _refused(check, str(exc))

    try:
        event = record_admission(
            session,
            case_id=case_id,
            evidence_file=record,
            check=check,
            reason=reason,
            actor=actor_record,
        )
        adjudication_id = str(event.id)
        session.commit()
    except (AdmissionError, DecisionError) as exc:
        # The log declined to carry the event as stated.  Rolled back so the
        # half-written decision does not survive the refusal, and reported as a
        # fact rather than as a fault: there is something the caller can do
        # about every one of these.
        session.rollback()
        return _refused(check, str(exc))
    except SQLAlchemyError as exc:
        session.rollback()
        logger.exception(
            "Failed to record an admission for file %s in case %s",
            file_id,
            case_id,
        )
        return FileAdmission(
            file_id=str(record.id),
            outcome=FileAdmissionOutcome.write_failed,
            reason=str(exc),
            file_name=check.file_name,
            route_outcome=check.outcome,
            detected_format=check.detected_format,
            claimants=check.claimants,
        )

    return FileAdmission(
        file_id=str(record.id),
        outcome=FileAdmissionOutcome.admitted,
        reason=reason,
        file_name=check.file_name,
        route_outcome=check.outcome,
        detected_format=check.detected_format,
        claimants=check.claimants,
        adjudication_id=adjudication_id,
    )


def _refused(check, reason: str) -> FileAdmission:
    """A refusal that still carries what the router found.

    The finding is repeated on the refusal on purpose.  A caller told only
    "refused" has to ask again to find out what it is being refused about, and
    the second answer may not be the first.
    """
    return FileAdmission(
        file_id=check.file_id,
        outcome=FileAdmissionOutcome.refused,
        reason=reason,
        file_name=check.file_name,
        route_outcome=check.outcome,
        detected_format=check.detected_format,
        claimants=check.claimants,
    )
