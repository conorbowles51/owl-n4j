"""Assignment of the P0–P4 proof class, and what each class licenses.

The vocabulary already existed: :class:`~postgres.models.enums.ProofClass` is
defined, and ``proof_class`` is a ``NOT NULL`` column on both
``financial_source_documents`` and ``financial_transactions``, with a check
constraint that refuses ``p4`` on a transaction.  What did not exist was
anything that *computes* a class.  Every caller and every test supplied one by
hand, which meant the taxonomy was enforced at the boundary and asserted
everywhere inside it — a class that a caller chooses is an opinion, and the
whole point of the taxonomy is that it is not one.  This module is the missing
function.

Which axis the classes key on
-----------------------------

P0–P4 can be keyed on two different axes, and the labels collide.  One keys on
*what proof the source carries*: p0 self-proving, p1 partially proving, **p2
cross-provable**, p3 structurally constrained, p4 assertional.  The other keys
on *source format, then arithmetic outcome*: p0 native with control totals, p1
native without, **p2 statement that balances**, p3 statement that does not, p4
assertional.  Three of the five labels mean different things depending on which
axis is in force, so the choice has to be stated rather than assumed.

This module implements the second: format, then outcome.  One consequence is
recorded here because it is invisible from inside the code.  Cross-document
corroboration — one document independently confirming a row in another,
measured across this corpus at 10,208 of 24,077 independent rows (42.4%) — has
no class of its own here, because the p2 label is spent on statement
arithmetic.  Corroboration is not lost; it is an attribute a row carries rather
than a class it belongs to.  Nothing in this module depends on resolving that,
but a reader who arrives expecting p2 to mean "cross-provable" will misread
every class it assigns.

Why this cannot live in the extractor
-------------------------------------

A class is a function of the source format **and the verification outcome**,
computed at ingestion.  The verification outcome is
:class:`~postgres.models.enums.ReconciliationStatus`, produced by
:func:`~services.financial.statement_totals.check_header_identity` over a
normalised control block.  That runs in the backend, over a period that has
already been read.  ``extract_entities.py`` runs before any of it exists.

So an extractor cannot assign a proof class, and a design that asks it to must
either guess p2 versus p3 or read the model's opinion — the two failures the
work already done in ``6ef152e`` exists to prevent.  What the
extractor can honestly report is the *shape* of the source, which is a
property of the format alone.  :class:`SourceShape` is that, and
:func:`assign_proof_class` is the join of shape with outcome.

The safe direction is not symmetric
-----------------------------------

p0, p1 and p2 enter the verified ledger automatically.  p3 enters
only on a recorded human act.  p4 never enters at all.  So the errors are not
equal: classifying a document one class too low costs an adjudication that a
person will resolve, while classifying it one class too high puts an unchecked
row inside a total — the exact failure this system exists
to prevent.  Every ambiguous case below therefore resolves downward, and
:func:`assign_proof_class` will not name an auto-admitting class on anything weaker than
a passing check.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from postgres.models.enums import ProofClass, ReconciliationStatus


class ProofClassError(Exception):
    """Base for refusals to assign a class."""


class UnclassifiableSourceError(ProofClassError):
    """Raised when no class can be assigned on the evidence supplied.

    Deliberately an error rather than a default.  There is no "unknown" member
    of :class:`ProofClass` and adding one would be worse than raising: the
    column is ``NOT NULL``, so an unknown class would have to be spelled as
    some real class, and whichever one was chosen would either auto-admit
    unverified material or quarantine verified material.
    """


class SourceShape(str, Enum):
    """What the source format affords, before any arithmetic has been run.

    This is the half of the class decision that is knowable at extraction
    time, and it is deliberately about the *format* rather than the content.
    A statement is a statement whether or not it turns out to balance; that it
    balances is the other half, and it arrives later.

    P2 and P3 share statement_document, distinguished by arithmetic outcome.
    Selected documentary rows have their own shape because checking a subset
    cannot establish that a whole financial record was captured.
    """

    # A structured file whose format mandates control totals: camt.053, BAI2,
    # NACHA.  The totals are guaranteed to be present, which is what makes the
    # arithmetic a guarantee rather than a hope.  Unreachable until the native
    # parsers land; no corpus document is currently read this way.
    native_with_control_totals = "native_with_control_totals"
    # A structured file with no control totals: OFX/QFX, a bank CSV export.
    # The structure constrains the fields but proves nothing about the set.
    native_without_control_totals = "native_without_control_totals"
    # A statement rendered as a document — PDF, scan, photograph.  Whether its
    # arithmetic closes is not a property of the format and is not known here.
    statement_document = "statement_document"
    # Deliberately selected rows from a financial record, with neither whole-
    # document coverage nor a complete statement/control block established.
    # This is not for figures asserted in letters, interviews or other prose.
    selected_document_rows = "selected_document_rows"
    # Financial claims embedded in unstructured material: chat, email, an
    # interview transcript.  Produces assertions with a speaker, never rows
    # with a document coordinate.
    unstructured_narrative = "unstructured_narrative"


#: Classes that enter the verified ledger with no human act.
AUTO_ADMITTED_CLASSES: frozenset[ProofClass] = frozenset(
    {ProofClass.p0, ProofClass.p1, ProofClass.p2}
)

#: Classes that may appear in the ledger at all.  ``p3`` is admissible only
#: through a recorded adjudication; ``p4`` is absent because the database
#: refuses it on a transaction, and that refusal is the processor boundary.
LEDGER_CLASSES: frozenset[ProofClass] = frozenset(
    {ProofClass.p0, ProofClass.p1, ProofClass.p2, ProofClass.p3}
)

#: The default membership of any total, chart or aggregate.  Stated
#: as a constant so that a caller widening it has to say so in code that can be
#: found, rather than by omitting a filter.
DEFAULT_TOTAL_CLASSES: frozenset[ProofClass] = AUTO_ADMITTED_CLASSES

#: Outcomes that establish the arithmetic actually closed.  Only
#: :attr:`ReconciliationStatus.balanced` does.  ``unavailable`` and
#: ``not_attempted`` are both absences of evidence and are treated alike.
_PASSING = frozenset({ReconciliationStatus.balanced})


def assign_proof_class(
    shape: SourceShape,
    reconciliation: Optional[ReconciliationStatus] = None,
) -> ProofClass:
    """Assign a proof class from the source shape and the arithmetic outcome.

    Pure.  No database, no model, no caller-supplied class.  ``reconciliation``
    is optional because it does not exist for every shape — a narrative has no
    arithmetic to run and a totals-free export has none to run against — but
    where a check was possible and did not pass, the result is never an
    auto-admitting class.

    Two rules here follow from no stated principle and are resolved
    conservatively:

    *Demotion on a failed check.*  Keying p0 and p1 on format alone would leave
    a camt.053 whose own mandatory totals contradict each other
    is still p0 and still auto-admits.  That cannot be right — a document that
    fails the check its format guarantees is the strongest possible signal that
    something is wrong with it — so a failing outcome demotes to p3 whatever
    the shape.  p3's prose says "statement document", which such a file is not,
    but p3's *operational* meaning is "arithmetic unsatisfied; human
    adjudication required", which is exactly the position it is in.

    *An unchecked mandatory-totals file is not yet p0.*  Where the format
    guarantees totals, ``not_attempted`` means the guarantee has not been
    collected, not that it held.  Calling that p0 would auto-admit on the
    strength of a check nobody ran.  It resolves to p3 and becomes p0 when the
    check passes.

    :raises UnclassifiableSourceError: if ``shape`` is not a known member.
    """
    if not isinstance(shape, SourceShape):
        raise UnclassifiableSourceError(
            f"source shape {shape!r} is not a SourceShape; a proof class cannot "
            "be assigned from an unrecognised format"
        )

    # A narrative yields assertions, not rows.  No arithmetic applies to it,
    # and none is consulted: an outcome passed alongside a narrative describes
    # some other artefact and must not be allowed to promote a claim.
    if shape is SourceShape.unstructured_narrative:
        return ProofClass.p4

    # Balancing a selected subset does not prove completeness. An outcome
    # alone must never turn nominated financial rows into a checked statement.
    # A separately established complete reading requires its own source record.
    if shape is SourceShape.selected_document_rows:
        return ProofClass.p3

    passed = reconciliation in _PASSING
    failed = reconciliation is ReconciliationStatus.unbalanced

    if failed:
        return ProofClass.p3

    if shape is SourceShape.statement_document:
        return ProofClass.p2 if passed else ProofClass.p3

    if shape is SourceShape.native_with_control_totals:
        return ProofClass.p0 if passed else ProofClass.p3

    # native_without_control_totals: no arithmetic is available by construction,
    # so there is nothing to demote on and format validation is the whole of the
    # check.  p1 is admitted automatically on that basis.
    return ProofClass.p1


def admits_automatically(proof_class: ProofClass) -> bool:
    """True where the class enters the verified ledger without a human act."""
    return proof_class in AUTO_ADMITTED_CLASSES


def requires_adjudication(proof_class: ProofClass) -> bool:
    """True where a recorded human verdict is the only route into the ledger."""
    return proof_class is ProofClass.p3


def may_produce_ledger_rows(proof_class: ProofClass) -> bool:
    """True where the class may yield transaction rows at all.

    False only for p4, and the database enforces the same rule independently
    through ``ck_financial_transactions_proof_class``.  Both exist on purpose:
    this one so a caller can ask before building a row, the constraint so that
    a caller who does not ask still cannot store one.
    """
    return proof_class in LEDGER_CLASSES


def counts_toward_totals(
    proof_class: ProofClass,
    *,
    included: frozenset[ProofClass] = DEFAULT_TOTAL_CLASSES,
) -> bool:
    """True where the class participates in an aggregate under ``included``.

    The parameter exists because a total has to *state* which classes it
    covers, which means the set has to be a value that can be reported, not a
    rule buried in a query.
    """
    return proof_class in included


#: Forward mapping from the retired four-value ``evidence_strength``
#: vocabulary.  Deliberately lossy, and lossy downward:
#:
#: ``narrative``   → p4.  Exact: both mean a claim in unstructured material.
#: ``derived``     → p1.  A table or spreadsheet is a structured source with no
#:                  control totals, which is what p1 is.
#: ``documentary`` → p3, *not* p2.  This is the consequential one.  A
#:                  documentary source type meant the source looked like a
#:                  statement; it never meant the arithmetic had been checked,
#:                  because under the old model no arithmetic ran.  Mapping it
#:                  to p2 would silently move every legacy documentary row into
#:                  the auto-admitted population on the strength of a check that
#:                  never happened.  p3 says what is true: it is a statement
#:                  document whose arithmetic is unavailable.
#: ``unknown``     → absent.  There is no honest class for it, so it maps to
#:                  nothing and :func:`from_legacy_strength` raises.
_LEGACY_STRENGTH_TO_CLASS: dict[str, ProofClass] = {
    "narrative": ProofClass.p4,
    "derived": ProofClass.p1,
    "documentary": ProofClass.p3,
}


def from_legacy_strength(evidence_strength: str) -> ProofClass:
    """Map a retired ``evidence_strength`` value forward to a proof class.

    This is a migration aid, not an ingestion path.  It exists so that a case
    ingested under the old model can be read in the new vocabulary, and it is
    not applied automatically: the ``uses_legacy_financial_model`` pattern
    is kept, so a legacy case keeps
    reporting the model it was built under until someone decides otherwise.
    Re-labelling old rows in place would claim a provenance they do not have.

    :raises UnclassifiableSourceError: on ``unknown`` or an unrecognised value.
    """
    try:
        return _LEGACY_STRENGTH_TO_CLASS[evidence_strength]
    except KeyError:
        raise UnclassifiableSourceError(
            f"evidence_strength {evidence_strength!r} has no proof class; "
            "'unknown' recorded that the old model could not grade the source, "
            "and inventing a class for it would either admit unverified "
            "material or quarantine verified material"
        ) from None
