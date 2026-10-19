"""Whether a job's file is a bank file the document pipeline must not read.

Four formats -- camt.053, BAI2, MT940 and NACHA -- are read exactly.  A parser
walks their structure, every figure arrives as the file stated it, and the
balances are checked against the movements before anything is admitted.  What
comes out can be cited to a byte range in the source and put in front of a
court.

The document pipeline does something else entirely.  It extracts text, hands it
to a model, and asks what the text says.  That is the right treatment for a
letter, a contract or a transcript, and the wrong treatment for a bank file:
the model would paraphrase figures it should have parsed, and produce numbers
that look exactly like the parsed kind while being an inference about a
statement rather than a reading of one.  Nothing downstream distinguishes them.
A transaction is a transaction once it is in the graph.

So this stage exists to notice, before any text is extracted, that a file
belongs to the other path.

It is a backstop, not the main road.  The routing that matters happens before
upload, where the check endpoint tells the interface what a file is and the
interface sends it to the ledger.  A file only reaches this stage by a route
that skipped that -- a folder scan, a bulk import, a re-process, an API caller
who did not ask.  Those routes exist, and on the day one of them carries a
client's bank statements the difference between exact and inferred evidence is
the difference between a case and an embarrassment.

What this stage does *not* do is ingest.  Detection is a pure function of the
first few kilobytes; ingestion needs the backend's writers, its models and a
synchronous session, none of which belong in an async worker whose failure
modes are already understood.  Reaching across the service boundary to write
would put a second connection pool and a second set of models in this process
for the sake of one branch.  This stage decides; the ledger path ingests.

Why a detected file fails the job rather than passing quietly
------------------------------------------------------------

There is no status for "this belongs elsewhere", and inventing one is not free:
``jobstatus`` is a Postgres enum shared with the backend, and the backend's
``_sync_db_record_from_job`` silently ignores any status it does not recognise
-- a file under an unknown status would sit at "processing" for ever with
nothing to show for it.  ``merging_properties`` is already in that position.

Of the statuses that do exist, ``completed`` would be the worse lie.  It marks
the evidence file processed, and a bank file recorded as processed with no
transactions anywhere is indistinguishable from one that was ingested and found
to contain nothing.  ``failed`` overstates the fault -- the file is fine -- but
it is visible, it carries an error message that says exactly what to do next,
and it stops.  A backstop that reports nothing is not a backstop.

The job is failed *without* raising, unlike every other failure here.  Raising
returns the exception to arq, which retries; a file's format does not change
between attempts, so a retry burns a worker to reach the same answer.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Set once by :func:`_load_detector`, which is idempotent and remembers failure.
_detector: Any = None
_detector_attempted: bool = False
_detector_failure: Optional[str] = None


def _load_detector() -> Any:
    """The backend's native-format detector, imported on first use.

    The same deferred, path-inserting import ``pdf_extraction`` uses for table
    geometry, for the same reason: this service is deployed separately and may
    or may not be able to see the backend's source.  Importing at module scope
    would turn a deployment without it into a worker that cannot start.

    Detection is deliberately not reimplemented here.  A second copy of four
    file signatures is a second thing to change when a bank ships a dialect,
    and the copy that is not changed is the one that decides how a client's
    statements are read.
    """
    global _detector, _detector_attempted, _detector_failure
    if _detector_attempted:
        return _detector
    _detector_attempted = True

    repo_root = Path(__file__).resolve().parents[3]
    candidates = [repo_root / "backend", Path("/backend")]
    for candidate in reversed(candidates):
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))

    try:
        from services.financial import native

        _detector = native
    except Exception as exc:  # noqa: BLE001 - any import failure means no routing
        _detector_failure = f"{type(exc).__name__}: {exc}"
        # Deliberately louder than the table-geometry equivalent.  A missing
        # table reader costs layout; a missing detector means bank files are
        # read by a language model and nobody is told.
        logger.error(
            "Financial route detection unavailable; native bank files reaching "
            "this pipeline will be processed as documents: %s",
            _detector_failure,
        )
    return _detector


@dataclass(frozen=True)
class FinancialRoute:
    """What the first few kilobytes of a file claim about its format.

    ``claimants`` holds every native format that recognised the input, not the
    first one, because more than one claimant is a real answer and not a tie to
    be broken.  Collapsing it early would record a confident format for a file
    whose format is in doubt.
    """

    claimants: tuple[str, ...] = ()
    detector_error: Optional[str] = None
    read_error: Optional[str] = None

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
    def detector_available(self) -> bool:
        return self.detector_error is None

    def as_state(self) -> dict[str, Any]:
        """The decision, in the shape ``pipeline_state`` keeps it.

        Written whatever the outcome, including the ordinary one where nothing
        claimed the file.  A key that appears only on the interesting branch
        cannot distinguish a run that looked and found nothing from a run of a
        build that never looked, and those want different responses.
        """
        return {
            "checked": True,
            "claimants": list(self.claimants),
            "detected_format": self.detected_format,
            "outcome": self.outcome,
            "detector_available": self.detector_available,
            "detector_error": self.detector_error,
            "read_error": self.read_error,
        }

    @property
    def outcome(self) -> str:
        if not self.detector_available:
            return "detector_unavailable"
        if self.read_error is not None:
            return "unreadable"
        if self.is_native:
            return "native"
        if self.is_ambiguous:
            return "ambiguous"
        return "not_native"


def detect_financial_route(file_path: Optional[str]) -> FinancialRoute:
    """Read the head of ``file_path`` and report which native formats claim it.

    Only the detector's own sniff window is read.  ``sniff`` truncates its input
    to that window before looking at it, so a prefix of exactly that length is
    not an approximation of the whole-file answer -- it is the same answer, and
    ``test_a_prefix_read_matches_the_whole_file`` holds the two together.  It
    matters because this runs before the size of the file is anybody's concern,
    and a statement covering a year of a busy account is not small.
    """
    detector = _load_detector()
    if detector is None:
        return FinancialRoute(detector_error=_detector_failure or "detector unavailable")

    if not file_path:
        return FinancialRoute(read_error="job has no file path")

    try:
        with open(file_path, "rb") as handle:
            head = handle.read(detector.SNIFF_BYTES)
    except OSError as exc:
        # Not this stage's failure to report.  A file the pipeline cannot open
        # will fail at extraction with a better message than anything here, so
        # the route is recorded as unreadable and the pipeline proceeds to find
        # that out in the place built to say so.
        return FinancialRoute(read_error=f"{type(exc).__name__}: {exc}")

    try:
        claimants = detector.sniff(head)
    except Exception as exc:  # noqa: BLE001 - a detector that raises is not a router
        logger.exception("Financial route detection raised for %s", file_path)
        return FinancialRoute(detector_error=f"{type(exc).__name__}: {exc}")

    return FinancialRoute(claimants=tuple(fmt.value for fmt in claimants))


def refusal_message(route: FinancialRoute, file_name: Optional[str] = None) -> str:
    """What to tell someone whose bank file arrived at the wrong pipeline.

    Written to be read in a UI error field by somebody who did not choose this
    route and does not know there are two.  It names the format, says plainly
    that nothing was destroyed, and gives the next action.
    """
    name = file_name or "This file"
    return (
        f"{name} is {route.detected_format}, a bank file the financial ledger "
        "reads directly. It was not processed as a document, because doing so "
        "would infer its figures from text instead of parsing them, and the "
        "result would be indistinguishable from an exact reading. Nothing was "
        "changed and nothing was lost: ingest it through the financial route "
        "to get reconciled transactions."
    )
