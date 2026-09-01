"""Source documents: admitting a file to the ledger, and grading it afterwards.

A source document row is the join between an evidence file and the financial
reading of it.  Writing one is the moment a file becomes part of a case's
financial record, and the field that decides what the rest of the subsystem may
do with it is ``proof_class``.

This module holds two functions because the proof class cannot be settled in
one.

Why admission and grading are two steps
---------------------------------------

:func:`~services.financial.proof_class.assign_proof_class` is a function of two
inputs: the shape of the source, and the outcome of the arithmetic.  Only the
first exists at admission.  The arithmetic runs over statement periods and
transactions; those reference the document; so the document has to be on disk
before anything can grade it.  There is no ordering that avoids this — it is
not an accident of the code, it is the shape of the problem.

So :func:`record_source_document` writes the class the document deserves *while
unchecked*, which for anything with arithmetic to run is p3, and
:func:`reclassify_after_reconciliation` moves it when the check reports.  A
camt.053 is admitted at p3 even though its format guarantees control totals,
because at admission the guarantee has not been collected.  That reads as
pessimism and is not: p3 means "arithmetic unsatisfied, human adjudication
required", and an unrun check is unsatisfied arithmetic.

The caller does not choose the class
------------------------------------

Neither function accepts a proof class.  :class:`SourceDocumentDraft` carries a
:class:`~services.financial.proof_class.SourceShape` instead, which is a
property of the file format and knowable by whoever opened the file.  The class
is derived from it here.  This is the whole reason ``proof_class.py`` exists:
before it, every caller supplied a class by hand, and a class a caller chooses
is an opinion.

The one guard worth naming
--------------------------

A native shape must have been read natively.  ``native_without_control_totals``
grades to p1, which is auto-admitted with no arithmetic anywhere in its
history — the format validating the fields is the entire check.  That is
defensible for an OFX parse, where the format really did define the field, and
indefensible for a model reading a screenshot of one.  Without the guard, a
caller who names the wrong shape gets model output into the verified ledger
with nothing downstream that would ever look at it again.  So the two native
shapes require :attr:`ExtractionLayer.native`, and the mismatch is an error
rather than a downgrade: a caller who has said two contradictory things about
one file should find out, not be quietly given the safer of the two.

The other direction is deliberately not constrained.  A statement document read
at any layer still has to pass the arithmetic to leave p3, so the check catches
what a layer rule would have caught, and a rule refusing (say) a natively
parsed statement export would refuse real files for no gain.

Where the shape is kept
-----------------------

``financial_source_documents`` has no shape column, so the shape is recorded in
``metadata`` under ``source_shape`` and read back by :func:`read_source_shape`.
The reclassifier needs it — a class is a function of shape *and* outcome, and
it cannot recover the shape from the class, since p3 is reached from three of
the four shapes.  A document written without it can be graded by nobody, which
is why the writer always writes it and never takes it from caller metadata.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Mapping, Optional, Sequence

from postgres.models.enums import (
    AdjudicationDecision,
    AdjudicationSubject,
    ExtractionLayer,
    ProofClass,
    ReconciliationStatus,
)
from postgres.models.evidence import EvidenceFile
from postgres.models.financial import (
    AdjudicationEvent,
    FinancialSourceDocument,
    FinancialStatementPeriod,
    FinancialTransaction,
)
from services.financial import decisions
from services.financial.money import get_currency
from services.financial.proof_class import (
    SourceShape,
    admits_automatically,
    assign_proof_class,
)
from services.financial.runs import RunScopeError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.orm import Session

    from services.financial.runs import IngestionRunHandle


class SourceDocumentError(Exception):
    """A source document could not be recorded or regraded as described."""


class DocumentFieldError(SourceDocumentError):
    """A field of the draft is missing, malformed, or too long to store."""


class ExtractionLayerMismatchError(SourceDocumentError):
    """The claimed source shape and the layer it was read at contradict."""


class UnknownSourceShapeError(SourceDocumentError):
    """A stored document does not record the shape it was read as."""


#: Shapes whose grading assumes the file format defined the fields.  Both are
#: auto-admitted with no arithmetic, so both require a native parse.
_NATIVE_SHAPES = frozenset(
    {
        SourceShape.native_with_control_totals,
        SourceShape.native_without_control_totals,
    }
)

#: Where the shape is kept, since the table has no column for it.
SHAPE_METADATA_KEY = "source_shape"

#: Who the reclassification log names.  The address is under ``.invalid``,
#: which RFC 2606 reserves and guarantees will never resolve, so it cannot
#: collide with a real person's address now or after any future acquisition of
#: a domain.  That is the property the audit trail depends on: "how many
#: documents did your analysts reclassify" is answered by excluding this
#: address, and the answer is only sound if nobody can hold it.
RECONCILIATION_ACTOR_NAME = "Loupe reconciliation stage"
RECONCILIATION_ACTOR_EMAIL = "reconciliation@loupe.invalid"


def reconciliation_actor() -> decisions.Actor:
    """The pseudo-actor that automatic reclassifications are filed under.

    A function rather than a module-level constant so that a caller cannot
    mutate the shared object, and so that ``user_id`` is unmistakably absent:
    there is no user row behind this and there must never be one, or the
    machine events would join to a person.
    """
    return decisions.Actor(
        name=RECONCILIATION_ACTOR_NAME, email=RECONCILIATION_ACTOR_EMAIL
    )


def _required_text(value: Any, label: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DocumentFieldError(
            f"{label} is required and must be a non-empty string; a document "
            "that cannot say how it was read cannot be reread the same way"
        )
    stripped = value.strip()
    if len(stripped) > limit:
        # Refused rather than truncated.  A truncated parser version is a
        # version that never existed, and the point of storing it is to be able
        # to reproduce the reading.
        raise DocumentFieldError(
            f"{label} is {len(stripped)} characters and the column holds "
            f"{limit}; storing it would silently truncate it"
        )
    return stripped


def _optional_text(value: Any, label: str, limit: int) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise DocumentFieldError(
            f"{label} must be a string or None, got {type(value).__name__}"
        )
    stripped = value.strip()
    if not stripped:
        # An empty string and an absent value would otherwise be two spellings
        # of the same fact, and a reader counting documents with no recorded
        # institution would get two different answers depending on which.
        return None
    if len(stripped) > limit:
        raise DocumentFieldError(
            f"{label} is {len(stripped)} characters and the column holds "
            f"{limit}; storing it would silently truncate it"
        )
    return stripped


def _hex_sha256(value: Any) -> str:
    if not isinstance(value, str):
        raise DocumentFieldError(
            f"sha256_at_ingestion must be a string, got {type(value).__name__}"
        )
    candidate = value.strip().lower()
    if len(candidate) != 64 or any(c not in "0123456789abcdef" for c in candidate):
        raise DocumentFieldError(
            f"sha256_at_ingestion {value!r} is not 64 hex characters. This "
            "column exists to be compared against the evidence file's own "
            "hash, and a value in another form would differ from a matching "
            "hash and read as tampering"
        )
    return candidate


@dataclass(frozen=True)
class SourceDocumentDraft:
    """A file and the financial reading of it, before it is stored.

    There is no ``proof_class`` field, and that absence is the design.  The
    class is derived from ``shape`` in :func:`record_source_document`.
    """

    evidence_file_id: uuid.UUID
    sha256_at_ingestion: str
    document_type: str
    shape: SourceShape
    extraction_layer: ExtractionLayer
    parser_name: str
    parser_version: str
    institution_name: Optional[str] = None
    page_count: Optional[int] = None
    currency: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.shape, SourceShape):
            raise DocumentFieldError(
                f"shape must be a SourceShape, got {type(self.shape).__name__}; "
                "a string would let a typo grade as the safest matching member "
                "or as nothing at all"
            )
        if not isinstance(self.extraction_layer, ExtractionLayer):
            # A bare int is how a layer-3 model reading gets stored as layer 0.
            # Both are valid values of the column, so nothing downstream would
            # catch it.
            raise ExtractionLayerMismatchError(
                "extraction_layer must be an ExtractionLayer, got "
                f"{type(self.extraction_layer).__name__}; the column takes an "
                "integer, so a wrong integer is indistinguishable from a right "
                "one once stored"
            )

        if (
            self.shape in _NATIVE_SHAPES
            and self.extraction_layer is not ExtractionLayer.native
        ):
            raise ExtractionLayerMismatchError(
                f"shape {self.shape.value!r} grades on the format having "
                "defined the fields, but this was read at layer "
                f"{self.extraction_layer.value} "
                f"({self.extraction_layer.name}). A native shape read any "
                "other way would be auto-admitted on a guarantee the reading "
                "did not have. Name the shape the reading actually supports."
            )

        object.__setattr__(
            self, "sha256_at_ingestion", _hex_sha256(self.sha256_at_ingestion)
        )
        object.__setattr__(
            self,
            "document_type",
            _required_text(self.document_type, "document_type", 32),
        )
        object.__setattr__(
            self, "parser_name", _required_text(self.parser_name, "parser_name", 64)
        )
        object.__setattr__(
            self,
            "parser_version",
            _required_text(self.parser_version, "parser_version", 32),
        )
        object.__setattr__(
            self,
            "institution_name",
            _optional_text(self.institution_name, "institution_name", 255),
        )

        if self.page_count is not None:
            if not isinstance(self.page_count, int) or isinstance(
                self.page_count, bool
            ):
                raise DocumentFieldError(
                    "page_count must be an int or None, got "
                    f"{type(self.page_count).__name__}"
                )
            if self.page_count < 1:
                # Zero and absent are different claims: absent says nobody
                # counted, zero says someone counted none, and a document with
                # no pages was not read.
                raise DocumentFieldError(
                    f"page_count is {self.page_count}; a document with no "
                    "pages was not read. Leave it None if it was not counted"
                )

        if self.currency is not None:
            # Normalised here rather than at the column, which would accept any
            # three characters. An unrecognised code has no exponent, and a
            # guessed exponent puts the decimal point in the wrong place.
            object.__setattr__(self, "currency", get_currency(self.currency).code)

        if not isinstance(self.metadata, Mapping):
            raise DocumentFieldError(
                f"metadata must be a mapping, got {type(self.metadata).__name__}"
            )
        if SHAPE_METADATA_KEY in self.metadata:
            # The writer sets this from `shape`. Letting a caller pass it too
            # would create a second, unvalidated way to say what the document
            # is, and the two would eventually disagree.
            raise DocumentFieldError(
                f"metadata may not carry {SHAPE_METADATA_KEY!r}; the shape is "
                "recorded from the `shape` field, which is the one the proof "
                "class is derived from"
            )
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def proof_class(self) -> ProofClass:
        """The class this draft grades to before any arithmetic has run.

        Exposed so a caller can see what admitting the draft would claim,
        without having to write it first.
        """
        return assign_proof_class(self.shape)


def record_source_document(
    session: "Session",
    run: "IngestionRunHandle",
    draft: SourceDocumentDraft,
) -> FinancialSourceDocument:
    """Admit a file to the case's financial record, attributed to ``run``.

    The referenced evidence file is checked to belong to the run's case before
    anything is written.  The foreign key cannot do this: it guarantees the row
    exists, not that it concerns this investigation, and a document joining one
    case's run to another case's file would put a stranger's statements in this
    case's totals.

    One row per file per run.  ``uq_financial_source_documents_run_file`` is
    what enforces it, and re-ingesting the same file under a new run is a new
    row on purpose — the second reading may have used a different parser, and
    overwriting the first would destroy the record that it ever said something
    else.  Duplicate detection across runs is
    :mod:`services.financial.duplicates`, which is a separate question with a
    separate answer.

    The document is admitted, never quarantined.  Quarantine is a decision
    about a document that has been read, so it needs the document to exist
    first; :mod:`services.financial.quarantine` is where it is taken, and it
    records who took it.

    :raises RunScopeError: if the evidence file is missing or in another case.
    """
    evidence_file = session.get(EvidenceFile, draft.evidence_file_id)
    if evidence_file is None:
        raise RunScopeError(
            f"evidence file {draft.evidence_file_id} does not exist; a source "
            "document cannot be recorded against a file that was never uploaded"
        )
    if evidence_file.case_id != run.case_id:
        raise RunScopeError(
            f"evidence file {draft.evidence_file_id} belongs to case "
            f"{evidence_file.case_id}, but this run is ingesting case "
            f"{run.case_id}"
        )

    metadata = dict(draft.metadata)
    metadata[SHAPE_METADATA_KEY] = draft.shape.value

    document = FinancialSourceDocument(
        evidence_file_id=draft.evidence_file_id,
        sha256_at_ingestion=draft.sha256_at_ingestion,
        document_type=draft.document_type,
        # Derived, never accepted. See the module docstring.
        proof_class=assign_proof_class(draft.shape).value,
        extraction_layer=draft.extraction_layer.value,
        parser_name=draft.parser_name,
        parser_version=draft.parser_version,
        institution_name=draft.institution_name,
        page_count=draft.page_count,
        currency=draft.currency,
        status="admitted",
        quarantine_reason=None,
        metadata_=metadata,
    )

    run.stamp(document)
    session.add(document)
    # Flushed so that a constraint violation is raised here, where the draft
    # that caused it is still in hand, rather than at some later commit.
    session.flush()
    return document


def read_source_shape(document: FinancialSourceDocument) -> SourceShape:
    """Recover the shape a stored document was read as.

    :raises UnknownSourceShapeError: if the document does not record one, or
        records a value that is not a member.  Both are refusals rather than
        defaults: every shape maps to a class, so any default chosen here would
        regrade the document on no evidence, and the two shapes that auto-admit
        are exactly the ones a wrong guess would be worst about.
    """
    stored = (document.metadata_ or {}).get(SHAPE_METADATA_KEY)
    if stored is None:
        raise UnknownSourceShapeError(
            f"source document {document.id} does not record a source shape, so "
            "its proof class cannot be recomputed. A class is a function of "
            "shape and outcome, and p3 is reached from three of the four "
            "shapes, so the shape cannot be inferred from the class"
        )
    try:
        return SourceShape(stored)
    except ValueError:
        raise UnknownSourceShapeError(
            f"source document {document.id} records source shape {stored!r}, "
            "which is not a SourceShape member"
        ) from None


def combine_period_outcomes(
    statuses: Sequence[ReconciliationStatus],
) -> ReconciliationStatus:
    """Fold a document's periods into the one outcome that grades the document.

    A document may cover several statement periods, each reconciled on its own.
    The document's class is one value, so the periods have to be resolved into
    one, and the fold is the worst case rather than the majority or the mean:

    * any period unbalanced makes the document unbalanced, because a document
      containing one broken identity is a document with a broken identity;
    * every period balanced makes the document balanced, and nothing less does;
    * otherwise the result is the strongest absence present — ``unavailable``
      if some period could not be checked, ``not_attempted`` if none was tried.

    An empty sequence is ``not_attempted``.  A document with no periods has had
    nothing checked, which is not the same as having passed, and is exactly the
    input a promotion must not be built on.
    """
    seen = set()
    for status in statuses:
        if not isinstance(status, ReconciliationStatus):
            raise SourceDocumentError(
                "period outcomes must be ReconciliationStatus members, got "
                f"{type(status).__name__}"
            )
        seen.add(status)

    if ReconciliationStatus.unbalanced in seen:
        return ReconciliationStatus.unbalanced
    if seen == {ReconciliationStatus.balanced}:
        return ReconciliationStatus.balanced
    if ReconciliationStatus.unavailable in seen:
        return ReconciliationStatus.unavailable
    return ReconciliationStatus.not_attempted


def document_reconciliation(
    session: "Session",
    document: FinancialSourceDocument,
) -> ReconciliationStatus:
    """Read this document's periods and fold them into one outcome.

    Provided so that the fold is not the caller's to get right.  Reading the
    periods and combining them by hand is two chances to be wrong in the
    direction that promotes an unchecked document, and a caller who writes
    ``all(p.reconciliation_status == 'balanced' ...)`` over an empty list gets
    ``True``.
    """
    from sqlalchemy import select

    rows = session.scalars(
        select(FinancialStatementPeriod.reconciliation_status).where(
            FinancialStatementPeriod.source_document_id == document.id
        )
    ).all()
    return combine_period_outcomes(
        [ReconciliationStatus(value) for value in rows]
    )


def reclassify_after_reconciliation(
    session: "Session",
    document: FinancialSourceDocument,
    reconciliation: ReconciliationStatus,
    *,
    run: Optional["IngestionRunHandle"] = None,
    reservations: Sequence[str] = (),
) -> Optional[AdjudicationEvent]:
    """Move a document's proof class to the one the arithmetic now supports.

    Returns the logged decision, or ``None`` if the class is already what the
    outcome implies — which is the common case for a totals-free native export,
    whose class never depended on arithmetic, and for a statement that failed
    and stays at p3.  Nothing is written when nothing changes: an event
    claiming a change that did not happen is worse than no event, because a
    reader counting reclassifications would count it.

    Both directions are permitted.  A rerun that finds a previously balanced
    document unbalanced demotes it, and that demotion is the one most worth
    having on the record.

    The change is logged *before* the column moves, which is the rule the
    decision log is built on: the event is written before the state changes, or
    the state does not change.  If the flush of the log fails, the document is
    left holding the class it can still account for.

    The class is derived from the document's recorded shape and the outcome
    passed in.  No caller supplies a class here either.

    A reservation withholds the auto-admitting class
    ------------------------------------------------

    ``reservations`` carries the reasons the reader of the file said it must
    not auto-admit, whatever its arithmetic says.  Where they are present, any
    class that would enter the ledger without a human act is withheld and the
    document lands at p3 instead.

    The test is :func:`~services.financial.proof_class.admits_automatically`
    rather than an equality against p0, because p0 is not the only class that
    admits itself -- ``AUTO_ADMITTED_CLASSES`` also holds p1 and p2.  Keying
    this on p0 would state the rule in terms of the one class today's reserving
    parsers happen to reach, and a totals-free format that later learns to
    raise a reservation would land at p1 and auto-admit anyway, having said in
    terms that it must not.  The property being asserted is "does not enter the
    ledger unexamined", so it is the property that is tested.

    This is not a second opinion about the arithmetic, and it does not claim
    the file failed.  The three cases that raise a reservation -- a camt.053
    marked ``DUPL``, a BAI2 group carrying test status, a NACHA batch of
    prenotifications -- all *pass*, and the first and last of them pass
    perfectly, because a re-sent message repeats totals that already agreed and
    a run of zero-dollar account tests satisfies every control total while
    moving no money at all.  Grading on the arithmetic alone is therefore
    exactly wrong here: the stronger the agreement, the more certainly the
    document auto-admits, and what it auto-admits is either money counted twice
    or test data entered as payments.

    The rule is applied here rather than left to callers because this function
    is the only place a *stored* document's class changes.  The four native
    parsers each withhold the same promotion when computing the class of a
    document they have just read, but a parser's verdict is not what this
    column holds -- a caller reporting a reconciliation outcome would otherwise
    undo it, and the document would auto-admit on the strength of a check that
    was never in dispute.

    A reservation only ever withholds auto-admission.  It does not demote a
    document the arithmetic already placed at p3, because p3 requires the human
    act the reservation is asking for and there is nothing below it to gain,
    and it does not touch p4: a narrative is never regraded at all.

    The document's ledger rows move with it
    ---------------------------------------

    Every row carries a copy of its document's class, because totals filter on
    it and a filter that joins to the document on every aggregate is a filter
    that gets forgotten.  The copy is what makes this function's job bigger
    than one column.

    ``DEFAULT_TOTAL_CLASSES`` is ``{p0, p1, p2}``.  A statement is admitted at
    p3; its rows cannot exist before it does and the arithmetic cannot run
    before its rows do, so the rows are necessarily written at p3 too.  If
    promoting the document to p2 left them there, every row of a statement that
    *balanced* would silently leave every total -- the arithmetic would have
    passed and the money would have vanished from the report.  So the rows are
    moved here, and the count moved is recorded in the decision.

    Only rows still holding the document's previous class are touched.  A row
    adjudicated to a class of its own no longer matches, and so is left alone:
    an automatic pass must not erase a human decision.  One consequence is
    worth naming rather than hiding -- if a document's class does *not* change,
    this function returns early and rows left stale by some earlier interrupted
    pass stay stale.  Repairing those needs a marker distinguishing an
    adjudicated row from a stale one, which the schema does not yet carry.

    :raises UnknownSourceShapeError: if the document did not record its shape.
    :raises RunScopeError: if ``run`` is ingesting a different case.
    """
    from sqlalchemy import func, select, update
    if not isinstance(reconciliation, ReconciliationStatus):
        raise SourceDocumentError(
            "reconciliation must be a ReconciliationStatus, got "
            f"{type(reconciliation).__name__}; a bare string is how "
            "'balanced' and 'balance' become two answers, one of which "
            "silently fails to promote"
        )
    if run is not None and run.case_id != document.case_id:
        raise RunScopeError(
            f"source document {document.id} belongs to case "
            f"{document.case_id}, but this run is ingesting case {run.case_id}"
        )

    # A bare string is a sequence of characters, so passing one reservation
    # unwrapped would silently become dozens of one-letter reasons -- and
    # would still be truthy, so the withholding would appear to work and the
    # logged reason would be nonsense.
    if isinstance(reservations, (str, bytes)):
        raise SourceDocumentError(
            "reservations must be a sequence of strings, not a single string; "
            f"{reservations!r} would be read one character at a time"
        )
    held = tuple(reservations)
    for reason in held:
        if not isinstance(reason, str):
            raise SourceDocumentError(
                "each reservation must be a string, got "
                f"{type(reason).__name__}; the reason is written into the "
                "decision log and read by a person"
            )

    shape = read_source_shape(document)
    current = document.proof_class
    earned = assign_proof_class(shape, reconciliation)
    graded = earned
    withheld = bool(held) and admits_automatically(earned)
    if withheld:
        graded = ProofClass.p3
    if graded.value == current:
        return None

    # Counted before anything moves, so the number in the reason is the number
    # the update is then held to.
    stale_rows = session.scalar(
        select(func.count())
        .select_from(FinancialTransaction)
        .where(
            FinancialTransaction.source_document_id == document.id,
            FinancialTransaction.proof_class == current,
        )
    )

    # Spelled out on the artefact rather than left to be inferred from a class
    # lower than the arithmetic earned.  A reviewer looking at a document that
    # balanced and did not auto-admit needs the reason on the record, not in a
    # parser.
    withholding = ""
    if withheld:
        withholding = (
            f"; {earned.value} withheld despite the check reporting "
            f"{reconciliation.value}, on {len(held)} admissibility "
            "reservation(s): " + " | ".join(held)
        )

    adjudication = decisions.record(
        session,
        case_id=document.case_id,
        subject=document,
        subject_type=AdjudicationSubject.source_document,
        decision=AdjudicationDecision.reclassify_document,
        reason=(
            f"reconciliation reported {reconciliation.value} for a "
            f"{shape.value} source; proof class {current} -> {graded.value}; "
            f"{stale_rows} ledger row(s) reclassified with it" + withholding
        ),
        actor=reconciliation_actor(),
        before={"proof_class": current},
        after={"proof_class": graded.value},
        ingestion_run_id=None if run is None else run.run_id,
    )

    if stale_rows:
        # "fetch" so that rows already loaded in this session are expired
        # rather than left holding the old class in memory, which would make
        # the caller's own objects disagree with the table it just wrote.
        result = session.execute(
            update(FinancialTransaction)
            .where(
                FinancialTransaction.source_document_id == document.id,
                FinancialTransaction.proof_class == current,
            )
            .values(proof_class=graded.value)
            .execution_options(synchronize_session="fetch")
        )
        if result.rowcount != stale_rows:
            # The count in the decision is now a claim the table does not
            # support.  Raising leaves the caller to roll back rather than
            # commit a log entry that misstates what happened.
            raise SourceDocumentError(
                f"source document {document.id}: {stale_rows} ledger rows were "
                f"at {current} when the decision was written but "
                f"{result.rowcount} moved; the recorded count would misstate "
                "the change, so nothing here is committed"
            )

    document.proof_class = graded.value
    session.flush()
    return adjudication
