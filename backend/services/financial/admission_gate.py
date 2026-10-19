"""Refusing to send a held file that no one has decided to send.

:mod:`services.financial.admission` states the rule this module completes:
**the event is written before the file is sent, or it is not sent.**
:func:`~services.financial.admission.record_admission` and
:func:`~services.financial.admit_file.admit_case_file` are the first half --
they write the event.  Nothing was the second half.  A file the router holds
back could still be handed to the document pipeline by the ordinary processing
route, because that route never asked whether a decision existed.  So the rule
was a convention observed by the one path that happened to record, and not a
property of the system.

:func:`gate_document_processing` is the second half.  It is called by
``services.evidence_processing_service.process_db_files`` immediately before
the files are marked as processing and handed to the engine, and it refuses the
request if any of them is a file the router holds and no one has admitted.

Presence, not consumption -- and this is a real limit
-----------------------------------------------------

:func:`~services.financial.admit_file.admit_case_file` says an admission
"authorises one send", and appends a second event for a second send rather than
deduplicating.  This gate does not honour that.  It asks whether *an* admission
exists for the file, not whether an unused one does, so one recorded decision
will let the same file through the pipeline any number of times afterwards.

That is not a shortcut taken for convenience; nothing in the schema can express
consumption.  There is no link from an adjudication to a processing job, and no
per-file record of a send that a decision could be matched against.  A
``consumed`` flag on the event would be the obvious fix and is the wrong one: it
would make an append-only log mutable, which is the single property the whole
table exists to have.

What the gate does deliver in full is the property it was built for: **no file
the router holds reaches the document pipeline without a named person having
said on the record that it should.**  What it does not deliver is the stricter
*every send is separately authorised*.  Closing that needs a record of sends
that a decision can be spent against, and that is a schema change rather than a
change here.

Why the whole request is refused rather than the offending files skipped
-----------------------------------------------------------------------

A caller who asked for five files and received four processed jobs, with
nothing in the response naming the fifth or saying why, would reasonably read
the result as success.  The handler above already refuses a whole batch over a
single unknown file id, so refusing over a single unadmitted one is the
behaviour that is already there rather than a new one.  And the direction a
mistake should fall here is that nothing happens: an unwanted refusal costs a
round trip, while an unnoticed partial send puts a statement's figures into the
text index with no decision behind them, which is the exact failure the router
exists to prevent.

Why the check is re-run from the file
-------------------------------------

For the reason :mod:`services.financial.admit_file` gives about its own
re-read: the finding has to be the file's own and not a claim about it.  Here
the concern is narrower but the same in kind -- a caller that could tell the
gate "nothing here blocks" would be a gate that anyone could walk past.  The
cost is one prefix read per file, on a path that already stats every one of
them.

``resolve_path`` is required and never defaulted, for the reason
:func:`~services.financial.route_check.check_case_files` gives.  It matters
more here than anywhere else in the package: the gate must classify the same
bytes the send will actually carry.  A gate that resolved a path differently
from its caller would clear one file and send another.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable, Optional, Sequence

from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
from postgres.models.financial import AdjudicationEvent
from services.financial.route_check import FileRouteCheck, check_path

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class HeldFile:
    """One file the router holds and no one has admitted.

    Carries the router's finding, not just the refusal.  A caller told only
    that a file was refused has to ask what about it, and route-check is a
    separate request whose answer may by then differ from the one the refusal
    was based on.  Everything an interface needs to offer the admission is
    here: the file, what was found, and who claims the format.
    """

    file_id: str
    file_name: Optional[str]
    #: ``native``, ``ambiguous``, ``unreadable`` or ``undetermined`` -- the
    #: members of :data:`~services.financial.route_check.BLOCKING_OUTCOMES`.
    route_outcome: str
    detected_format: Optional[str]
    claimants: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "file_id": self.file_id,
            "file_name": self.file_name,
            "route_outcome": self.route_outcome,
            "detected_format": self.detected_format,
            "claimants": list(self.claimants),
        }


class UnadmittedFileError(Exception):
    """Raised when a request would send a held file with no decision behind it.

    Carries every offending file rather than the first, so that one refusal
    tells the caller everything they must decide about.  Refusing one at a time
    would make a five-file batch take five round trips to learn its own shape.
    """

    def __init__(self, held: Sequence[HeldFile]):
        self.held: tuple[HeldFile, ...] = tuple(held)
        names = ", ".join(f.file_name or f.file_id for f in self.held)
        super().__init__(
            f"{len(self.held)} file(s) are held back from the document "
            f"pipeline and have no recorded decision to send them: {names}. "
            "Record an admission for each, or process the request without "
            "them."
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "error": "unadmitted_files",
            "message": str(self),
            "held": [f.as_dict() for f in self.held],
        }


def _to_held(check: FileRouteCheck) -> HeldFile:
    return HeldFile(
        file_id=str(check.file_id),
        file_name=check.file_name,
        route_outcome=check.outcome,
        detected_format=check.detected_format,
        claimants=tuple(check.claimants),
    )


def admitted_file_ids(
    session: "Session",
    *,
    case_id: uuid.UUID,
    file_ids: Iterable[uuid.UUID],
) -> set[str]:
    """Which of these files have an admission on the record, as strings.

    Scoped to ``case_id`` as well as to the ids.  The ids alone would be
    enough to find the rows, since they are uuid4 and a file belongs to one
    case; the case is in the filter so that a decision filed against another
    matter could never clear a file here, whatever went wrong upstream to
    make that possible.

    Returns an empty set for an empty input **without querying**, so that a
    caller which has already established that nothing blocks does not touch
    the database at all.
    """
    wanted = [fid for fid in file_ids]
    if not wanted:
        return set()

    from sqlalchemy import select

    rows = session.scalars(
        select(AdjudicationEvent.subject_id)
        .where(AdjudicationEvent.case_id == case_id)
        .where(
            AdjudicationEvent.subject_type == AdjudicationSubject.evidence_file.value
        )
        .where(
            AdjudicationEvent.decision
            == AdjudicationDecision.admit_financial_document.value
        )
        .where(AdjudicationEvent.subject_id.in_(wanted))
    ).all()
    return {str(subject_id) for subject_id in rows}


def held_without_admission(
    session: "Session",
    *,
    case_id: uuid.UUID,
    files: Sequence[Any],
    resolve_path: Callable[[Optional[str]], Optional[Path]],
) -> tuple[HeldFile, ...]:
    """The files here that the router holds and that no one has admitted.

    ``files`` are :class:`~postgres.models.evidence.EvidenceFile` rows.  They
    are typed loosely because the caller is the evidence processing service,
    which is not part of this package and must not have to import from it to
    describe its own arguments.

    Empty result means the request may proceed.  The database is read only
    when at least one file blocks, which is both the right shape -- there is
    no question to ask about a batch the router does not object to -- and what
    keeps this callable from a caller holding a session that cannot answer
    one.
    """
    blocking: list[FileRouteCheck] = []
    for record in files:
        check = check_path(
            resolve_path(record.stored_path),
            file_id=str(record.id),
            file_name=record.original_filename,
        )
        if check.blocks_document_processing:
            blocking.append(check)

    if not blocking:
        return ()

    admitted = admitted_file_ids(
        session,
        case_id=case_id,
        file_ids=[uuid.UUID(check.file_id) for check in blocking],
    )
    return tuple(
        _to_held(check) for check in blocking if check.file_id not in admitted
    )


def gate_document_processing(
    session: "Session",
    *,
    case_id: uuid.UUID,
    files: Sequence[Any],
    resolve_path: Callable[[Optional[str]], Optional[Path]],
) -> None:
    """Let the send proceed, or raise :class:`UnadmittedFileError`.

    Returns ``None`` on success and raises on refusal, rather than returning
    something the caller could ignore.  A gate whose answer can be dropped is
    not a gate, and the value of this one is entirely in the case where the
    caller would rather carry on.

    Reads and writes nothing.  It does not mark an admission as used -- see
    this module's docstring on why nothing can, and on what that costs.
    """
    held = held_without_admission(
        session, case_id=case_id, files=files, resolve_path=resolve_path
    )
    if held:
        raise UnadmittedFileError(held)
