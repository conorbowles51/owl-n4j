"""Tests for the assignment of the P0-P4 proof class.

The function under test is twelve lines of branching over two enums, so the
interesting tests are not the ones that check it computes what it says.  They
are the ones that fail if someone later relaxes a rule that looks arbitrary
and is not.

Four such rules exist, and each has a test whose name says what breaks:

* A class is never assigned from format alone where the format promises
  arithmetic.  A ``camt.053`` nobody checked is p3, not p0 — ``not_attempted``
  means the guarantee was not collected, not that it held.
* A failed check demotes whatever the shape.  On a literal reading of `13`
  §2.1, p0 keys on format, so a native file whose own mandatory totals
  contradict each other would still auto-admit.  That is the strongest
  available signal that something is wrong with the file, so it goes to p3.
* An arithmetic outcome supplied alongside a narrative is ignored.  A
  narrative has no arithmetic of its own, so any outcome handed in with one
  describes some other artefact, and must not be allowed to promote a claim
  out of p4.
* p0 and p2 are unreachable without :attr:`ReconciliationStatus.balanced`.
  This is the whole safety property, asserted over the entire input space
  rather than at the four points a reader might think to check.

The full 4x5 matrix is asserted as a literal table.  It is small enough to
write out, and a table makes a behaviour change show up as a diff on the
expectation rather than as a passing test that now means something else.

One asymmetry in `13` is recorded here rather than corrected, in
:meth:`AutoAdmissionTest.test_p1_auto_admits_without_any_arithmetic`: p1 — a
bank CSV with no control totals — enters the ledger automatically having had
no check run, while p3 — a statement that was checked and did not close —
requires a human.  That is `13` §2.2 as written.  It is defensible (p1's
structure constrains the fields, and there is no arithmetic available to run)
but it means "auto-admitted" does not mean "verified", and a reader who
assumes it does will be wrong about roughly the population that matters.
"""

from __future__ import annotations

import unittest

from postgres.models.enums import ProofClass, ReconciliationStatus
from services.financial.proof_class import (
    AUTO_ADMITTED_CLASSES,
    DEFAULT_TOTAL_CLASSES,
    LEDGER_CLASSES,
    SourceShape,
    UnclassifiableSourceError,
    admits_automatically,
    assign_proof_class,
    counts_toward_totals,
    from_legacy_strength,
    may_produce_ledger_rows,
    requires_adjudication,
)

# Local aliases.  The real names say what they mean and are right in
# production code; here they would wrap each row of the 4x5 table onto three
# lines and destroy the one property that makes a table worth writing out.
NATIVE_TOTALS = SourceShape.native_with_control_totals
NATIVE_PLAIN = SourceShape.native_without_control_totals
STATEMENT = SourceShape.statement_document
NARRATIVE = SourceShape.unstructured_narrative

BALANCED = ReconciliationStatus.balanced
UNBALANCED = ReconciliationStatus.unbalanced
NOT_ATTEMPTED = ReconciliationStatus.not_attempted
UNAVAILABLE = ReconciliationStatus.unavailable

#: Every outcome a check can have, plus the absence of one.  ``None`` is not a
#: fifth status: it is what a caller passes when no check was even applicable,
#: and it must behave like ``not_attempted`` rather than like a pass.
ALL_OUTCOMES = (None,) + tuple(ReconciliationStatus)


def label(outcome):
    """A subTest label for an outcome that may be ``None``."""
    return getattr(outcome, "value", None)


class ClassifyMatrixTest(unittest.TestCase):
    """The whole input space, written out."""

    #: (shape, outcome) -> class.  Read down a column to see what an outcome
    #: does to each format; read across a row to see what a format affords.
    EXPECTED = {
        (NATIVE_TOTALS, None): ProofClass.p3,
        (NATIVE_TOTALS, NOT_ATTEMPTED): ProofClass.p3,
        (NATIVE_TOTALS, BALANCED): ProofClass.p0,
        (NATIVE_TOTALS, UNBALANCED): ProofClass.p3,
        (NATIVE_TOTALS, UNAVAILABLE): ProofClass.p3,
        (NATIVE_PLAIN, None): ProofClass.p1,
        (NATIVE_PLAIN, NOT_ATTEMPTED): ProofClass.p1,
        (NATIVE_PLAIN, BALANCED): ProofClass.p1,
        (NATIVE_PLAIN, UNBALANCED): ProofClass.p3,
        (NATIVE_PLAIN, UNAVAILABLE): ProofClass.p1,
        (STATEMENT, None): ProofClass.p3,
        (STATEMENT, NOT_ATTEMPTED): ProofClass.p3,
        (STATEMENT, BALANCED): ProofClass.p2,
        (STATEMENT, UNBALANCED): ProofClass.p3,
        (STATEMENT, UNAVAILABLE): ProofClass.p3,
        (NARRATIVE, None): ProofClass.p4,
        (NARRATIVE, NOT_ATTEMPTED): ProofClass.p4,
        (NARRATIVE, BALANCED): ProofClass.p4,
        (NARRATIVE, UNBALANCED): ProofClass.p4,
        (NARRATIVE, UNAVAILABLE): ProofClass.p4,
    }

    def test_matrix_is_complete(self) -> None:
        """The table covers every input, so the assertions below are total."""
        self.assertEqual(
            set(self.EXPECTED),
            {(shape, out) for shape in SourceShape for out in ALL_OUTCOMES},
        )

    def test_matrix(self) -> None:
        for (shape, outcome), expected in self.EXPECTED.items():
            with self.subTest(shape=shape.value, outcome=label(outcome)):
                self.assertIs(assign_proof_class(shape, outcome), expected)

    def test_omitting_the_outcome_matches_not_attempted(self) -> None:
        """``None`` is an absence of evidence, not a distinct kind of it."""
        for shape in SourceShape:
            with self.subTest(shape=shape.value):
                self.assertIs(
                    assign_proof_class(shape),
                    assign_proof_class(shape, NOT_ATTEMPTED),
                )


class SafetyPropertyTest(unittest.TestCase):
    """Properties asserted over the whole input space, not at sample points."""

    def test_promoted_classes_require_a_passing_check(self) -> None:
        """p0 and p2 are unreachable on anything but ``balanced``.

        These are the two classes that auto-admit *because* arithmetic closed.
        p1 also auto-admits, but on the different basis that no arithmetic was
        ever available (see :class:`AutoAdmissionTest`), so it is excluded here
        deliberately rather than by oversight.
        """
        for shape in SourceShape:
            for outcome in ALL_OUTCOMES:
                if outcome is BALANCED:
                    continue
                with self.subTest(shape=shape.value, outcome=label(outcome)):
                    self.assertNotIn(
                        assign_proof_class(shape, outcome),
                        {ProofClass.p0, ProofClass.p2},
                        "a class meaning 'the arithmetic closed' was assigned "
                        "without the arithmetic having closed",
                    )

    def test_a_failed_check_never_auto_admits(self) -> None:
        """``unbalanced`` puts a human in the loop whatever the format."""
        for shape in SourceShape:
            if shape is NARRATIVE:
                continue  # p4 does not enter the ledger at all; covered below.
            with self.subTest(shape=shape.value):
                assigned = assign_proof_class(shape, UNBALANCED)
                self.assertIs(assigned, ProofClass.p3)
                self.assertFalse(admits_automatically(assigned))
                self.assertTrue(requires_adjudication(assigned))

    def test_mandatory_totals_file_is_not_p0_until_checked(self) -> None:
        """The guarantee has to be collected, not assumed from the format.

        This is the rule `13` §2.1 does not state.  Reading it literally, p0
        keys on format alone and this file is p0 the moment it is recognised.
        That would auto-admit it on the strength of a check nobody ran.
        """
        for outcome in (None, NOT_ATTEMPTED, UNAVAILABLE):
            with self.subTest(outcome=label(outcome)):
                self.assertIs(
                    assign_proof_class(NATIVE_TOTALS, outcome), ProofClass.p3
                )
        self.assertIs(
            assign_proof_class(NATIVE_TOTALS, BALANCED), ProofClass.p0
        )

    def test_a_native_file_that_fails_its_own_totals_is_demoted(self) -> None:
        """Format is not a defence against the format's own arithmetic."""
        self.assertIs(
            assign_proof_class(NATIVE_TOTALS, UNBALANCED), ProofClass.p3
        )

    def test_narrative_ignores_any_outcome_handed_to_it(self) -> None:
        """A narrative has no arithmetic, so an outcome cannot promote it.

        Passing ``balanced`` alongside a narrative is not evidence about the
        narrative; it is evidence about whatever else the caller had open.
        """
        for outcome in ALL_OUTCOMES:
            with self.subTest(outcome=label(outcome)):
                assigned = assign_proof_class(NARRATIVE, outcome)
                self.assertIs(assigned, ProofClass.p4)
                self.assertFalse(may_produce_ledger_rows(assigned))

    def test_every_result_is_a_real_class(self) -> None:
        for shape in SourceShape:
            for outcome in ALL_OUTCOMES:
                with self.subTest(shape=shape.value, outcome=label(outcome)):
                    self.assertIsInstance(
                        assign_proof_class(shape, outcome), ProofClass
                    )

    def test_every_class_is_reachable(self) -> None:
        """No member of the taxonomy is dead code.

        If a class can never be assigned, either the taxonomy has a label it
        does not need or the function has a branch it never takes.  Both are
        worth knowing about.
        """
        reached = {
            assign_proof_class(shape, outcome)
            for shape in SourceShape
            for outcome in ALL_OUTCOMES
        }
        self.assertEqual(reached, set(ProofClass))


class RefusalTest(unittest.TestCase):
    """What happens when the shape is not a shape."""

    def test_unknown_shape_raises_rather_than_defaulting(self) -> None:
        for bad in (None, "statement_document", "", 0, ProofClass.p2, object()):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(UnclassifiableSourceError):
                    assign_proof_class(bad)  # type: ignore[arg-type]

    def test_the_string_value_of_a_shape_is_not_a_shape(self) -> None:
        """``SourceShape`` is a ``str`` enum, so this is the likely near miss.

        A caller that reads a shape out of JSON gets the string, not the
        member.  It must not silently assign a class: the string carries no
        guarantee that it came from this vocabulary at all.
        """
        with self.assertRaises(UnclassifiableSourceError):
            assign_proof_class(STATEMENT.value)  # type: ignore[arg-type]

    def test_the_refusal_names_the_offending_value(self) -> None:
        with self.assertRaises(UnclassifiableSourceError) as caught:
            assign_proof_class("bank_statement")  # type: ignore[arg-type]
        self.assertIn("bank_statement", str(caught.exception))


class AutoAdmissionTest(unittest.TestCase):
    """Which classes enter the ledger, and on whose authority."""

    def test_auto_admitted_classes(self) -> None:
        self.assertEqual(
            AUTO_ADMITTED_CLASSES,
            {ProofClass.p0, ProofClass.p1, ProofClass.p2},
        )
        for proof_class in ProofClass:
            with self.subTest(proof_class=proof_class.value):
                self.assertEqual(
                    admits_automatically(proof_class),
                    proof_class in AUTO_ADMITTED_CLASSES,
                )

    def test_only_p3_requires_adjudication(self) -> None:
        for proof_class in ProofClass:
            with self.subTest(proof_class=proof_class.value):
                self.assertEqual(
                    requires_adjudication(proof_class),
                    proof_class is ProofClass.p3,
                )

    def test_adjudication_and_auto_admission_are_disjoint(self) -> None:
        """A class is admitted one way or the other, never both."""
        for proof_class in ProofClass:
            with self.subTest(proof_class=proof_class.value):
                self.assertFalse(
                    admits_automatically(proof_class)
                    and requires_adjudication(proof_class)
                )

    def test_only_p4_is_barred_from_the_ledger(self) -> None:
        self.assertEqual(LEDGER_CLASSES, set(ProofClass) - {ProofClass.p4})
        for proof_class in ProofClass:
            with self.subTest(proof_class=proof_class.value):
                self.assertEqual(
                    may_produce_ledger_rows(proof_class),
                    proof_class is not ProofClass.p4,
                )

    def test_auto_admitted_is_a_subset_of_ledger_classes(self) -> None:
        """Nothing may auto-admit into a table it may not appear in."""
        self.assertTrue(AUTO_ADMITTED_CLASSES < LEDGER_CLASSES)

    def test_every_ledger_class_has_exactly_one_route_in(self) -> None:
        for proof_class in LEDGER_CLASSES:
            with self.subTest(proof_class=proof_class.value):
                self.assertTrue(
                    admits_automatically(proof_class)
                    ^ requires_adjudication(proof_class)
                )

    def test_p1_auto_admits_without_any_arithmetic(self) -> None:
        """Recorded, not endorsed: `13` §2.2 as written.

        A bank CSV enters the verified ledger with no check run, while a
        statement that *was* checked and did not close needs a human.  The
        justification is that p1's structure constrains the fields and there is
        no arithmetic available to run against it, so there is nothing to fail.
        The consequence is that membership of ``AUTO_ADMITTED_CLASSES`` does
        not mean an arithmetic check passed.  This test exists so that reading
        it into the code is impossible.
        """
        assigned = assign_proof_class(NATIVE_PLAIN)
        self.assertIs(assigned, ProofClass.p1)
        self.assertTrue(admits_automatically(assigned))
        self.assertFalse(requires_adjudication(assigned))


class TotalsMembershipTest(unittest.TestCase):
    """Which classes are inside a number."""

    def test_default_total_classes_are_the_auto_admitted_ones(self) -> None:
        self.assertEqual(DEFAULT_TOTAL_CLASSES, AUTO_ADMITTED_CLASSES)

    def test_default_excludes_p3_and_p4(self) -> None:
        self.assertFalse(counts_toward_totals(ProofClass.p3))
        self.assertFalse(counts_toward_totals(ProofClass.p4))

    def test_default_includes_the_auto_admitted(self) -> None:
        for proof_class in AUTO_ADMITTED_CLASSES:
            with self.subTest(proof_class=proof_class.value):
                self.assertTrue(counts_toward_totals(proof_class))

    def test_widening_is_explicit_and_local(self) -> None:
        """A total including adjudicated rows has to say so in its call.

        `13` §2.2 requires a total to state its own composition.  Passing the
        set is what makes that statement a value the caller holds, rather than
        a filter buried in a query where nobody can quote it.
        """
        with_p3 = frozenset(AUTO_ADMITTED_CLASSES | {ProofClass.p3})
        self.assertTrue(counts_toward_totals(ProofClass.p3, included=with_p3))
        self.assertFalse(counts_toward_totals(ProofClass.p3))

    def test_included_is_keyword_only(self) -> None:
        """So a second positional argument cannot silently widen a total."""
        with self.assertRaises(TypeError):
            counts_toward_totals(
                ProofClass.p3, frozenset(ProofClass)  # type: ignore[misc]
            )


class LegacyStrengthTest(unittest.TestCase):
    """Reading a case ingested under the retired four-value vocabulary."""

    def test_narrative_maps_to_p4(self) -> None:
        self.assertIs(from_legacy_strength("narrative"), ProofClass.p4)

    def test_derived_maps_to_p1(self) -> None:
        self.assertIs(from_legacy_strength("derived"), ProofClass.p1)

    def test_documentary_maps_to_p3_not_p2(self) -> None:
        """The consequential one.

        ``documentary`` recorded that the source *looked like* a statement.  It
        never recorded that the arithmetic had been checked, because under the
        old model no arithmetic ran.  Mapping it to p2 would move every legacy
        documentary row into the auto-admitted population on the strength of a
        check that never happened.
        """
        assigned = from_legacy_strength("documentary")
        self.assertIs(assigned, ProofClass.p3)
        self.assertFalse(admits_automatically(assigned))
        self.assertTrue(requires_adjudication(assigned))

    def test_unknown_raises(self) -> None:
        """No honest class exists for 'the old model could not grade this'."""
        with self.assertRaises(UnclassifiableSourceError):
            from_legacy_strength("unknown")

    def test_unrecognised_value_raises(self) -> None:
        for bad in ("", "documentry", "DOCUMENTARY", "p2", "None"):
            with self.subTest(bad=bad):
                with self.assertRaises(UnclassifiableSourceError):
                    from_legacy_strength(bad)

    def test_mapping_is_case_sensitive(self) -> None:
        """Not a convenience.  A caller holding ``'Documentary'`` holds a value
        from somewhere other than the retired enum, and guessing what it meant
        is how the wrong class gets assigned quietly."""
        with self.assertRaises(UnclassifiableSourceError):
            from_legacy_strength("Documentary")

    def test_covers_the_retired_vocabulary(self) -> None:
        """Every old value is either mapped or explicitly refused.

        The retired set is spelled out here rather than imported: the point is
        that this module has an answer for each of the four, and importing the
        list from the module under test would make the assertion vacuous.
        """
        for legacy in ("documentary", "derived", "narrative"):
            with self.subTest(legacy=legacy):
                self.assertIsInstance(from_legacy_strength(legacy), ProofClass)
        with self.assertRaises(UnclassifiableSourceError):
            from_legacy_strength("unknown")

    def test_legacy_never_auto_admits_a_documentary_source(self) -> None:
        """The property the previous tests are individually about."""
        admitted = {
            legacy
            for legacy in ("documentary", "derived", "narrative")
            if admits_automatically(from_legacy_strength(legacy))
        }
        self.assertEqual(admitted, {"derived"})


class SchemaAgreementTest(unittest.TestCase):
    """The module and the database have to mean the same thing.

    Both enforce the taxonomy independently and on purpose — the module so a
    caller can ask before building a row, the constraint so a caller who does
    not ask still cannot store one.  Independent enforcement is only a
    safeguard while the two agree, and nothing but a test makes them agree.
    """

    def test_check_constraint_lists_exactly_the_enum(self) -> None:
        from postgres.models.financial import _PROOF_CLASSES

        listed = {
            value.strip().strip("'")
            for value in _PROOF_CLASSES.strip("()").split(",")
        }
        self.assertEqual(listed, {member.value for member in ProofClass})

    def test_transactions_refuse_p4(self) -> None:
        """``may_produce_ledger_rows`` and the constraint state one rule."""
        from postgres.models.financial import FinancialTransaction

        constraints = {
            getattr(arg, "name", None)
            for arg in FinancialTransaction.__table__.constraints
        }
        self.assertIn("ck_financial_transactions_no_p4", constraints)
        self.assertFalse(may_produce_ledger_rows(ProofClass.p4))

    def test_source_documents_permit_p4(self) -> None:
        """p4 is a real source class; it just never yields transaction rows.

        The processor boundary falls between the two tables, so a constraint
        barring p4 from source documents would be a different, wrong system.
        """
        from postgres.models.financial import FinancialSourceDocument

        constraints = {
            getattr(arg, "name", None)
            for arg in FinancialSourceDocument.__table__.constraints
        }
        self.assertIn("ck_financial_source_documents_proof_class", constraints)
        self.assertNotIn("ck_financial_source_documents_no_p4", constraints)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
