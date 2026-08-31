"""What uploaded evidence files are, before anyone spends money reading them.

Upload and processing are two calls.  ``POST /api/evidence/upload`` stages a
file, registers it and returns no job; ``POST /api/evidence/process/background``
is what actually enqueues work.  Everything here exists to be called in the gap
between them, so that the interface can say "three of these are bank files, and
they should go to the ledger instead" while that is still a choice rather than
a thing to undo.

This is the road, not the backstop.  ``app.pipeline.financial_route`` in the
evidence engine catches a bank file that reached the document pipeline anyway,
by a folder scan or a re-process or an API caller who never asked; by then the
only honest thing left to do is stop the job and explain.  Asking here costs
four kilobytes a file and happens before a decision is made.

Why the outcome words are written twice
---------------------------------------

The engine's ``FinancialRoute.outcome`` and this module's ``outcome`` share
four strings -- ``native``, ``ambiguous``, ``not_native``, ``unreadable`` --
and are two separate pieces of code.  That is deliberate, and the alternative
was considered and rejected.

Neither side can produce the other's full vocabulary.  The engine's
``detector_unavailable`` exists precisely for the case where this package
cannot be imported at all, so it cannot be defined in this package.  This
module's ``not_found`` describes a file id that is not in the case, which is a
question the engine never asks because it is handed a job that already exists.
A shared enum would therefore be a union that neither side can wholly return,
and each would need its own subset anyway.

The genuine risk is drift -- one side gaining a word the interface does not
handle.  That is answered where both are consumed: the interface owns the union
type, and both sides are asserted against it.  A word added here without being
added there fails to compile.

``undetermined`` is the one word the two sides spell differently for the same
condition: the bytes were read and the detector did not return an answer.  The
engine calls that ``detector_unavailable`` because on that side the usual cause
is a missing import.  Here the detector is a direct import in this same
process, so it is present by definition, and calling it unavailable would be a
plain lie to whoever reads the response.  What both spellings share is the part
that matters -- neither is a green light.  A file nobody could classify must
not be presented as one that was classified and found ordinary.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence

from sqlalchemy.orm import Session

from services.financial import native

logger = logging.getLogger(__name__)

#: Outcomes that mean "do not send this to the document pipeline yet".  Held as
#: a set rather than left implicit at each call site so that adding an outcome
#: forces a decision about which side of this line it falls on.
BLOCKING_OUTCOMES = frozenset({"native", "ambiguous", "unreadable", "undetermined"})


@dataclass(frozen=True)
class FileRouteCheck:
    """One file's answer, in the shape the interface reads it.

    ``claimants`` holds every format that recognised the head of the file, not
    the first, for the reason ``native.sniff`` returns all of them: more than
    one claimant is an answer about the file, and picking one would record a
    confident format for something whose format is in doubt.
    """

    file_id: str
    file_name: Optional[str] = None
    claimants: tuple[str, ...] = ()
    reason: Optional[str] = None
    missing: bool = False
    undetermined: bool = False

    @property
    def is_native(self) -> bool:
        """Exactly one format claims this, so the ledger can read it."""
        return len(self.claimants) == 1

    @property
    def is_ambiguous(self) -> bool:
        """Several formats claim this, so no parser can be chosen for it."""
        return len(self.claimants) > 1

    @property
    def detected_format(self) -> Optional[str]:
        return self.claimants[0] if self.is_native else None

    @property
    def outcome(self) -> str:
        if self.missing:
            return "not_found"
        if self.undetermined:
            return "undetermined"
        if self.reason is not None:
            return "unreadable"
        if self.is_native:
            return "native"
        if self.is_ambiguous:
            return "ambiguous"
        return "not_native"

    @property
    def blocks_document_processing(self) -> bool:
        """Whether sending this file to the document pipeline needs a decision.

        Read by the interface to decide whether to interrupt.  ``not_found`` is
        absent from :data:`BLOCKING_OUTCOMES` on purpose: a file id that is not
        in this case is not a file this call can say anything about, and
        ``process/background`` already refuses the whole request over one.
        """
        return self.outcome in BLOCKING_OUTCOMES

    def as_dict(self) -> dict:
        """The keys the interface reads, present whatever happened.

        Every key is written on every outcome, including the ordinary one.  A
        field that appears only on the interesting branch cannot distinguish a
        file that was checked and found unremarkable from one a build too old
        to check never looked at, and those want different responses.
        """
        return {
            "file_id": self.file_id,
            "file_name": self.file_name,
            "claimants": list(self.claimants),
            "detected_format": self.detected_format,
            "outcome": self.outcome,
            "blocks_document_processing": self.blocks_document_processing,
            "reason": self.reason,
        }


def check_head(head: bytes) -> tuple[tuple[str, ...], Optional[str]]:
    """Which native formats claim these bytes, and why not if none could say.

    Separated from the file handling so the classification can be exercised
    without a filesystem, and so the one place that decides what a raising
    detector means is one place.
    """
    try:
        claimants = native.sniff(head)
    except Exception as exc:  # noqa: BLE001 - a detector that raises is not a verdict
        # Not re-raised.  One unclassifiable file must not fail the check for
        # the others in the same request, and the caller's real question --
        # "may I send this to the document pipeline?" -- has a safe answer
        # here, which is no.
        logger.exception("Native format detection raised while checking a file")
        return (), f"{type(exc).__name__}: {exc}"
    return tuple(fmt.value for fmt in claimants), None


def check_path(path: Optional[Path], *, file_id: str, file_name: Optional[str]) -> FileRouteCheck:
    """Read the head of one file and classify it.

    Only ``native.SNIFF_BYTES`` are read.  ``sniff`` truncates its input to that
    window before looking at it, so this prefix is not an approximation of the
    whole-file answer, it is the same answer -- which is what makes it
    affordable to ask about fifty files at once, some of which may be a year of
    a busy account.
    """
    if path is None:
        return FileRouteCheck(
            file_id=file_id,
            file_name=file_name,
            reason="the file has no stored path",
        )

    try:
        with open(path, "rb") as handle:
            head = handle.read(native.SNIFF_BYTES)
    except OSError as exc:
        return FileRouteCheck(
            file_id=file_id,
            file_name=file_name,
            reason=f"{type(exc).__name__}: {exc}",
        )

    claimants, detector_error = check_head(head)
    if detector_error is not None:
        return FileRouteCheck(
            file_id=file_id,
            file_name=file_name,
            reason=detector_error,
            undetermined=True,
        )
    return FileRouteCheck(file_id=file_id, file_name=file_name, claimants=claimants)


def check_case_files(
    db: Session,
    *,
    case_id: uuid.UUID,
    file_ids: Sequence[uuid.UUID],
    resolve_path: Callable[[Optional[str]], Optional[Path]],
) -> list[FileRouteCheck]:
    """Classify every requested file that belongs to ``case_id``.

    ``resolve_path`` is required rather than defaulted because the stored path
    on an evidence file is not always a path that exists in this process: the
    engine writes one layout and the host reads another, and the router already
    owns the function that reconciles them.  A default of "use it as written"
    would work on a developer's machine and quietly fail in a container, which
    is the worst way for it to be wrong, so there is no default to forget.

    Results come back in the caller's order, once per distinct id.  Files the
    caller asked about that are not in this case come back as ``not_found``
    rather than being dropped -- an interface that asked about five files and
    got three answers would show a clean bill of health for the two it never
    heard about, which is exactly the silence this whole check exists to break.

    A file that exists in another case is reported identically to one that does
    not exist at all, so that asking cannot be used to learn what is in a case
    the caller cannot see.
    """
    from services.evidence_db_storage import EvidenceDBStorage

    ordered: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for file_id in file_ids:
        if file_id in seen:
            continue
        seen.add(file_id)
        ordered.append(file_id)

    records = EvidenceDBStorage.get_files_by_ids(db, ordered)
    # Scoped here rather than in the query so that the filtering is visible at
    # the point the guarantee is made, and so a future change to
    # ``get_files_by_ids`` cannot quietly widen it.
    in_case = {
        record.id: record
        for record in records
        if record.case_id == case_id
    }

    results: list[FileRouteCheck] = []
    for file_id in ordered:
        record = in_case.get(file_id)
        if record is None:
            results.append(
                FileRouteCheck(
                    file_id=str(file_id),
                    missing=True,
                    reason="no such file in this case",
                )
            )
            continue
        results.append(
            check_path(
                resolve_path(record.stored_path),
                file_id=str(record.id),
                file_name=record.original_filename,
            )
        )
    return results


def summarise(checks: Iterable[FileRouteCheck]) -> dict:
    """Counts the interface needs before it has decided how to show the detail.

    ``blocking`` is the number that would make ``process/background`` the wrong
    next call.  It is computed from :attr:`FileRouteCheck.blocks_document_processing`
    rather than by re-testing the outcome strings, so that the two can never
    disagree about what blocks.
    """
    checks = list(checks)
    counts: dict[str, int] = {}
    for check in checks:
        counts[check.outcome] = counts.get(check.outcome, 0) + 1
    return {
        "checked": len(checks),
        "native": sum(check.is_native for check in checks),
        "blocking": sum(check.blocks_document_processing for check in checks),
        "outcomes": counts,
    }
