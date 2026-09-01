"""Recording that someone chose to send a bank file to the document pipeline.

:mod:`services.financial.route_check` holds back files it recognises as bank
data, because indexing a statement as prose turns its figures into searchable
text that no total can ever be traced to.  An investigator who is shown that
finding may disagree, and should be able to proceed.  This module is what
happens when they do.

Why it is written down
----------------------

An override that left no trace would make one person's judgement look like the
system's behaviour.  Someone reading the case months later, finding a
statement's figures in the text index and in no total anywhere, would have no
way to distinguish a deliberate call made with reasons behind it from a routing
failure nobody noticed.  Those two situations call for opposite responses, and
after the fact only this record can tell them apart.

So the rule is the one :mod:`services.financial.decisions` already enforces
everywhere else: **the event is written before the file is sent, or it is not
sent.**  :func:`record_admission` flushes the adjudication and returns it, so
the caller holds a decision with an identity before it enqueues anything, and a
failure to enqueue leaves a record of an intention rather than an unexplained
gap.

Why the finding is copied into the event
----------------------------------------

``before`` and ``after`` here do not diff a column, and that is deliberate.
Nothing in ``evidence_files`` changes: the decision moves the file from held to
sent, and "held" was never a stored state, it was the absence of a job.  What a
reader needs instead is what was being overridden -- a record saying only that
someone admitted a file is unreadable without the router's finding beside it.

Re-deriving that finding later will not do.  Detection is a function of the
detector, the detector changes, and a check run next year against a file that
was admitted this year answers a different question than the one the person was
actually looking at.  So the outcome, the claimants and the detected format are
copied into the event at the moment of the decision, where they stay true.

They appear on both sides of the diff because they did not change -- the
router's finding is still the router's finding, and the person did not dispute
it, they overrode it.  The one key that differs is ``routed_to``, because that
is the only thing the decision actually did.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
from postgres.models.evidence import EvidenceFile
from postgres.models.financial import AdjudicationEvent
from services.financial import decisions
from services.financial.route_check import FileRouteCheck

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.orm import Session


#: Where the file was going before the decision, and where it goes after.
#: ``held`` is not a stored status; it is the absence of a job, which is
#: exactly why the transition has to be recorded somewhere that is not the
#: evidence file.
ROUTED_HELD = "held"
ROUTED_DOCUMENT_PIPELINE = "document_pipeline"


class AdmissionError(Exception):
    """Raised when an admission cannot be recorded as stated."""


class NothingToOverrideError(AdmissionError):
    """Raised when the check being overridden does not block anything.

    Its own type because the failure is not a malformed request.  Recording an
    override where the router raised no objection would put a decision in the
    log that nobody had to take, and every later count of "how often did the
    team overrule the router" would be wrong by however many of these got in.
    """


class WrongFileError(AdmissionError):
    """Raised when the check describes a different file from the subject.

    The event would then carry one file's identity and another file's finding,
    and would read as authoritative about both.  This is the same failure
    :class:`services.financial.decisions.SubjectMismatchError` exists for, one
    level up: there is no foreign key from an adjudication to anything, so if
    the pairing is not checked here it is not checked at all.
    """


def _finding(check: FileRouteCheck) -> dict:
    """The router's answer, as it stood when the decision was taken."""
    return {
        "route_outcome": check.outcome,
        "claimants": list(check.claimants),
        "detected_format": check.detected_format,
    }


def record_admission(
    session: "Session",
    *,
    case_id: uuid.UUID,
    evidence_file: EvidenceFile,
    check: FileRouteCheck,
    reason: str,
    actor: decisions.Actor,
) -> AdjudicationEvent:
    """Append the decision to send one held file to the document pipeline.

    Call this *before* enqueueing the job.  Returns the flushed adjudication.

    ``reason`` is mandatory and is enforced twice over -- here by
    :func:`services.financial.decisions.record`, and at the database by
    ``ck_adjudications_reason_not_blank``, which is written to survive a reason
    made only of tabs and newlines.  An admission without stated grounds is not
    a decision anyone can review; it is the unexplained edit the whole table
    exists to prevent.
    """
    if not isinstance(check, FileRouteCheck):
        raise AdmissionError(
            f"check must be a FileRouteCheck, got {type(check).__name__}; the "
            "router's finding is copied into the event and cannot be taken on "
            "trust from a caller-built dict"
        )
    if not check.blocks_document_processing:
        raise NothingToOverrideError(
            f"the route check for {check.file_id} reports {check.outcome!r}, "
            "which does not hold the file back. There is nothing to admit it "
            "past, and recording one would overstate how often the router is "
            "overruled."
        )
    if str(check.file_id) != str(evidence_file.id):
        raise WrongFileError(
            f"the check describes file {check.file_id} but the subject is "
            f"{evidence_file.id}; the event would carry one file's identity "
            "and another file's finding"
        )

    finding = _finding(check)
    return decisions.record(
        session,
        case_id=case_id,
        subject=evidence_file,
        subject_type=AdjudicationSubject.evidence_file,
        decision=AdjudicationDecision.admit_financial_document,
        reason=reason,
        actor=actor,
        before={**finding, "routed_to": ROUTED_HELD},
        after={**finding, "routed_to": ROUTED_DOCUMENT_PIPELINE},
    )
