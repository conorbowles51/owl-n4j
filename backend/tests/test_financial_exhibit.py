"""Tests for :mod:`services.financial.exhibit`.

Four things these tests exist to hold, beyond the obvious one that the counts
and subtotals are right.

**That both grounds are recorded when both hold.**  Two independent things send
an artefact to Rule 107: it asserts more than the records contain, or some
underlying row is not material the system will stand behind.  A tag that
stopped at whichever it found first would tell a proponent that fixing one
thing moves the artefact, when fixing it would leave the artefact exactly where
it was.  :class:`BothGroundsAreRecorded` holds the case where both apply, in
both orders of construction, and asserts the count as well as the membership so
that a mutant which appends the same reason twice dies too.

**That adjudication does not create substrate.**  This is the tempting mistake
and the one with a settled answer already in the codebase:
:mod:`services.financial.adjudication` says in as many words that a document
whose arithmetic does not close is p3, and that a well-corroborated
adjudication explains why it is p3 rather than making it p2.  Admission to the
ledger and admissibility as a summary's substrate are different questions.
:class:`AdjudicationDoesNotCreateSubstrate` holds the distinction on the
smallest fact pattern that shows it -- twenty-nine p1 rows and one adjudicated
p3 -- and holds that the adjudication is nonetheless *reported*, because the
honest sentence is "we know why this one fails and here is the corroboration",
not silence.

**That an unmet obligation is not the wrong category.**  Making records
available to the other parties is an act of the proponent's, curable by an
email, and is not a property of the data.  An exhibit with an outstanding
disclosure is a Rule 1006 summary that may not be offered yet, not a Rule 107
aid.  :class:`DisclosureIsAConditionNotADowngrade` holds that the rule does not
move, that the obligation lands in ``conditions`` rather than ``caveats``, and
that the same shortfall under Rule 107 lands in ``caveats`` instead, because
Rule 107 imposes no such requirement and recording one would invent an
obligation.

**That a total cannot disagree with its own rows.**  The exhibit is the artefact
a witness is asked to stand behind, and a discrepancy between the printed total
and the printed rows would be found by opposing counsel with a calculator
rather than by us.  :class:`InvariantsAreEnforced` breaks each of the four
identities deliberately -- total against rows, total against class subtotals,
class counts against row count, and a category with no stated ground -- and
requires each to raise.
"""

from __future__ import annotations

import itertools
import unittest

from postgres.models.enums import ProofClass
from services.financial import exhibit
from services.financial.exhibit import (
    CAVEAT_ADJUDICATION_RELIED_ON,
    CAVEAT_ASSERTIONS_PRESENT,
    CAVEAT_MIXED_COMPOSITION,
    CAVEAT_NOT_OBVIOUSLY_VOLUMINOUS,
    CAVEAT_SINGLE_DOCUMENT,
    CAVEAT_UNADJUDICATED_P3,
    CAVEAT_UNDISCLOSED_SOURCES,
    CONDITION_MAKE_AVAILABLE,
    CONVENIENTLY_EXAMINABLE_ROWS,
    REASON_CONTENT_IS_AN_AID,
    REASON_SUBSTRATE_BELOW_SUMMARY,
    REASON_SUMMARISES_ADMISSIBLE_RECORDS,
    SUMMARISING_CONTENT,
    SUMMARY_SUBSTRATE_CLASSES,
    ContentKind,
    Disclosure,
    DisclosureError,
    DuplicateReferenceError,
    ExhibitContentError,
    ExhibitCurrencyError,
    ExhibitInvariantError,
    ExhibitRow,
    ExhibitTag,
    SourceDocument,
    SummaryRule,
    may_bear_summary,
    tag_exhibit,
    weakest_content,
)
from services.financial.flow import ClassComposition
from services.financial.money import Money

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64

NOTE = "produced 2026-01-05 at Owl CG, Bates OWL000001-000412"


def usd(units: int) -> Money:
    return Money.from_minor_units(units, "USD")


def doc(
    identifier: str,
    digest: str = DIGEST_A,
    *,
    available: bool = True,
) -> SourceDocument:
    """A source document, disclosed by default so tests opt in to the shortfall."""
    return SourceDocument(
        identifier=identifier,
        sha256=digest,
        made_available=available,
        availability_note=NOTE if available else None,
    )


def row(
    reference: str,
    *,
    proof_class: ProofClass = ProofClass.p1,
    units: int = 100,
    document: str = "stmt-1",
    adjudicated: bool = False,
) -> ExhibitRow:
    return ExhibitRow(
        reference=reference,
        proof_class=proof_class,
        amount=usd(units),
        document=document,
        adjudicated=adjudicated,
    )


def many(count: int, *, document: str = "stmt-1") -> tuple[ExhibitRow, ...]:
    """``count`` clean p1 rows, enough of them to clear the volume caveat."""
    return tuple(
        row(f"r{index}", units=100 + index, document=document)
        for index in range(count)
    )


def tag(rows, documents=None, **kwargs) -> ExhibitTag:
    """``tag_exhibit`` with the boring arguments defaulted."""
    if documents is None:
        cited = sorted({r.document for r in rows})
        documents = [doc(identifier) for identifier in cited]
    kwargs.setdefault("content", ContentKind.enumeration)
    kwargs.setdefault("currency", "USD")
    return tag_exhibit(rows, documents, **kwargs)


# ---------------------------------------------------------------------------
# What the system will stand behind
# ---------------------------------------------------------------------------


class SummarySubstrateTests(unittest.TestCase):
    """P0-P2 is substrate; P3 and P4 are not, per `13` §2.2."""

    def test_p0_p1_p2_may_bear_a_summary(self):
        for proof_class in (ProofClass.p0, ProofClass.p1, ProofClass.p2):
            with self.subTest(proof_class=proof_class):
                self.assertTrue(may_bear_summary(proof_class))

    def test_p3_may_not(self):
        self.assertFalse(may_bear_summary(ProofClass.p3))

    def test_p4_may_not(self):
        self.assertFalse(may_bear_summary(ProofClass.p4))

    def test_every_class_is_decided(self):
        """No class falls through undecided as the enum grows."""
        for proof_class in ProofClass:
            with self.subTest(proof_class=proof_class):
                self.assertIsInstance(may_bear_summary(proof_class), bool)

    def test_the_membership_is_exactly_three(self):
        self.assertEqual(
            SUMMARY_SUBSTRATE_CLASSES,
            frozenset({ProofClass.p0, ProofClass.p1, ProofClass.p2}),
        )

    def test_the_set_is_immutable(self):
        """A caller cannot widen the evidentiary claim by mutating a module
        constant, which is the whole reason it is a frozenset."""
        self.assertIsInstance(SUMMARY_SUBSTRATE_CLASSES, frozenset)

    def test_it_is_not_an_alias_of_the_ledger_rule(self):
        """Same membership today, and deliberately a separate object.

        The ledger's auto-admission rule answers to delivery pressure; the
        evidentiary claim answers to a court.  If a later hand loosened the
        first, an alias would loosen the second silently.  This test fails the
        moment someone replaces the definition with an import.
        """
        from services.financial import proof_class as proof_class_module

        self.assertEqual(
            SUMMARY_SUBSTRATE_CLASSES,
            proof_class_module.AUTO_ADMITTED_CLASSES,
            "membership is expected to coincide today",
        )
        self.assertIsNot(
            SUMMARY_SUBSTRATE_CLASSES,
            proof_class_module.AUTO_ADMITTED_CLASSES,
            "the two must not be the same object; see the constant's comment",
        )


# ---------------------------------------------------------------------------
# What the artefact asserts
# ---------------------------------------------------------------------------


class ContentKindTests(unittest.TestCase):
    def test_the_two_summarising_kinds(self):
        self.assertEqual(
            SUMMARISING_CONTENT,
            frozenset({ContentKind.enumeration, ContentKind.calculation}),
        )

    def test_a_chart_is_a_calculation_not_an_aid(self):
        """Rule 1006's own text names "summary, chart, or calculation".

        The line is not tables-versus-pictures.  A bar chart whose every bar is
        an arithmetic consequence of the rows proves the content of the
        records; what would make it an aid is selection for emphasis, which is
        arrangement.
        """
        self.assertIn(ContentKind.calculation, SUMMARISING_CONTENT)

    def test_arrangement_and_interpretation_are_aids(self):
        for kind in (ContentKind.arrangement, ContentKind.interpretation):
            with self.subTest(kind=kind):
                self.assertNotIn(kind, SUMMARISING_CONTENT)

    def test_every_kind_is_decided(self):
        for kind in ContentKind:
            with self.subTest(kind=kind):
                self.assertIsInstance(kind in SUMMARISING_CONTENT, bool)

    def test_the_order_covers_every_member_exactly_once(self):
        self.assertEqual(sorted(exhibit._CONTENT_ORDER, key=str), sorted(ContentKind, key=str))
        self.assertEqual(len(exhibit._CONTENT_ORDER), len(set(exhibit._CONTENT_ORDER)))

    def test_the_order_runs_from_nearest_to_furthest(self):
        self.assertEqual(
            exhibit._CONTENT_ORDER,
            (
                ContentKind.enumeration,
                ContentKind.calculation,
                ContentKind.arrangement,
                ContentKind.interpretation,
            ),
        )

    def test_summarising_kinds_precede_the_aids_in_the_order(self):
        """The rank is not merely an order, it agrees with the category."""
        worst_summary = max(
            exhibit._CONTENT_RANK[k] for k in SUMMARISING_CONTENT
        )
        best_aid = min(
            exhibit._CONTENT_RANK[k]
            for k in ContentKind
            if k not in SUMMARISING_CONTENT
        )
        self.assertLess(worst_summary, best_aid)


class WeakestContentTests(unittest.TestCase):
    """A compound page is characterised by its weakest part."""

    def test_a_single_kind_is_its_own_weakest(self):
        for kind in ContentKind:
            with self.subTest(kind=kind):
                self.assertIs(weakest_content([kind]), kind)

    def test_a_table_beside_a_diagram_is_a_diagram(self):
        self.assertIs(
            weakest_content([ContentKind.enumeration, ContentKind.arrangement]),
            ContentKind.arrangement,
        )

    def test_order_of_arrival_does_not_matter(self):
        for pair in itertools.permutations(
            [ContentKind.calculation, ContentKind.interpretation]
        ):
            with self.subTest(pair=pair):
                self.assertIs(weakest_content(pair), ContentKind.interpretation)

    def test_every_pair_agrees_with_the_rank(self):
        for left, right in itertools.product(ContentKind, repeat=2):
            with self.subTest(left=left, right=right):
                expected = max(
                    (left, right), key=lambda k: exhibit._CONTENT_RANK[k]
                )
                self.assertIs(weakest_content([left, right]), expected)

    def test_repeats_do_not_change_the_answer(self):
        self.assertIs(
            weakest_content(
                [ContentKind.enumeration] * 5 + [ContentKind.calculation]
            ),
            ContentKind.calculation,
        )

    def test_an_empty_page_is_refused(self):
        with self.assertRaises(ExhibitContentError):
            weakest_content([])

    def test_a_non_member_is_refused(self):
        with self.assertRaises(ExhibitContentError):
            weakest_content([ContentKind.enumeration, "calculation"])

    def test_the_string_value_of_a_member_is_not_a_member(self):
        """``ContentKind`` is a ``str`` enum, so this is the live confusion."""
        with self.assertRaises(ExhibitContentError):
            weakest_content(["enumeration"])

    def test_it_consumes_an_iterator(self):
        self.assertIs(
            weakest_content(iter([ContentKind.arrangement])),
            ContentKind.arrangement,
        )


# ---------------------------------------------------------------------------
# The documents behind the exhibit
# ---------------------------------------------------------------------------


class SourceDocumentTests(unittest.TestCase):
    def test_a_disclosed_document_round_trips(self):
        d = doc("stmt-1")
        self.assertEqual(d.identifier, "stmt-1")
        self.assertEqual(d.sha256, DIGEST_A)
        self.assertTrue(d.made_available)
        self.assertEqual(d.availability_note, NOTE)

    def test_availability_defaults_to_false(self):
        """The safe default is the one that understates the proponent's case."""
        d = SourceDocument("stmt-1", DIGEST_A)
        self.assertFalse(d.made_available)
        self.assertIsNone(d.availability_note)

    def test_an_empty_identifier_is_refused(self):
        with self.assertRaises(DisclosureError):
            SourceDocument("", DIGEST_A)

    def test_a_whitespace_identifier_is_refused(self):
        with self.assertRaises(DisclosureError):
            SourceDocument("   ", DIGEST_A)

    def test_a_digest_of_the_wrong_length_is_refused(self):
        for digest in ("a" * 63, "a" * 65, ""):
            with self.subTest(length=len(digest)):
                with self.assertRaises(DisclosureError):
                    SourceDocument("stmt-1", digest)

    def test_an_upper_case_digest_is_refused(self):
        """One form, so that two records of the same document compare equal."""
        with self.assertRaises(DisclosureError):
            SourceDocument("stmt-1", "A" * 64)

    def test_a_non_hex_digest_is_refused(self):
        with self.assertRaises(DisclosureError):
            SourceDocument("stmt-1", "g" * 64)

    def test_a_trailing_newline_is_refused(self):
        """The reason the pattern is anchored with ``\\Z`` and not ``$``.

        A digest read from a file with the newline still attached would pass a
        ``$``-anchored check and then fail to equal the same document's digest
        computed anywhere else.
        """
        with self.assertRaises(DisclosureError):
            SourceDocument("stmt-1", "a" * 64 + "\n")

    def test_a_leading_newline_is_refused(self):
        with self.assertRaises(DisclosureError):
            SourceDocument("stmt-1", "\n" + "a" * 64)

    def test_a_non_string_digest_is_refused(self):
        with self.assertRaises(DisclosureError):
            SourceDocument("stmt-1", 12345)

    def test_disclosed_without_particulars_is_refused(self):
        """"Produced" with no where and no when is not a record of anything."""
        with self.assertRaises(DisclosureError):
            SourceDocument("stmt-1", DIGEST_A, True, None)

    def test_disclosed_with_blank_particulars_is_refused(self):
        with self.assertRaises(DisclosureError):
            SourceDocument("stmt-1", DIGEST_A, True, "   ")

    def test_particulars_without_disclosure_are_refused(self):
        """The note would read as though the obligation had been met."""
        with self.assertRaises(DisclosureError):
            SourceDocument("stmt-1", DIGEST_A, False, NOTE)

    def test_it_is_hashable_and_frozen(self):
        d = doc("stmt-1")
        self.assertIn(d, {d})
        with self.assertRaises(Exception):
            d.made_available = False


class ExhibitRowTests(unittest.TestCase):
    def test_a_clean_row_round_trips(self):
        r = row("r1", units=250, document="stmt-2")
        self.assertEqual(r.reference, "r1")
        self.assertEqual(r.amount, usd(250))
        self.assertEqual(r.document, "stmt-2")
        self.assertFalse(r.adjudicated)

    def test_an_empty_reference_is_refused(self):
        """Without a reference, an annotation on the exported page returns to
        nothing -- the loss `11` §6 records."""
        with self.assertRaises(ExhibitContentError):
            row("")

    def test_a_whitespace_reference_is_refused(self):
        with self.assertRaises(ExhibitContentError):
            row("  ")

    def test_an_empty_document_is_refused(self):
        with self.assertRaises(ExhibitContentError):
            row("r1", document="")

    def test_a_whitespace_document_is_refused(self):
        with self.assertRaises(ExhibitContentError):
            row("r1", document=" ")

    def test_a_non_proof_class_is_refused(self):
        with self.assertRaises(ExhibitContentError):
            ExhibitRow("r1", "p1", usd(100), "stmt-1")

    def test_a_float_amount_is_refused(self):
        with self.assertRaises(ExhibitContentError):
            ExhibitRow("r1", ProofClass.p1, 1.0, "stmt-1")

    def test_an_int_amount_is_refused(self):
        with self.assertRaises(ExhibitContentError):
            ExhibitRow("r1", ProofClass.p1, 100, "stmt-1")

    def test_adjudication_is_allowed_on_p3(self):
        r = row("r1", proof_class=ProofClass.p3, adjudicated=True)
        self.assertTrue(r.adjudicated)

    def test_adjudication_is_refused_on_every_other_class(self):
        """On p0-p2 it implies a doubt the arithmetic does not support; on p4
        it implies an admission that never happened."""
        for proof_class in ProofClass:
            if proof_class is ProofClass.p3:
                continue
            with self.subTest(proof_class=proof_class):
                with self.assertRaises(ExhibitContentError):
                    row("r1", proof_class=proof_class, adjudicated=True)

    def test_an_unadjudicated_p3_is_constructible(self):
        """Below the ledger's own admission rule, and still a row an exhibit
        may have to describe."""
        r = row("r1", proof_class=ProofClass.p3)
        self.assertFalse(r.adjudicated)


class DisclosureTests(unittest.TestCase):
    def test_an_empty_manifest_describes_itself(self):
        self.assertEqual(Disclosure(()).describe(), "no documents")

    def test_an_empty_manifest_is_complete(self):
        self.assertTrue(Disclosure(()).is_complete)

    def test_all_available(self):
        d = Disclosure((doc("stmt-1"), doc("stmt-2", DIGEST_B)))
        self.assertTrue(d.is_complete)
        self.assertEqual(d.outstanding, ())
        self.assertEqual(len(d.available), 2)
        self.assertEqual(d.describe(), "2 documents, all made available")

    def test_the_singular_is_used_for_one(self):
        d = Disclosure((doc("stmt-1"),))
        self.assertEqual(d.describe(), "1 document, all made available")

    def test_outstanding_is_named(self):
        d = Disclosure(
            (doc("stmt-1"), doc("stmt-2", DIGEST_B, available=False))
        )
        self.assertFalse(d.is_complete)
        self.assertEqual([x.identifier for x in d.outstanding], ["stmt-2"])
        self.assertEqual([x.identifier for x in d.available], ["stmt-1"])
        self.assertEqual(
            d.describe(),
            "2 documents, 1 not yet made available: stmt-2",
        )

    def test_every_document_outstanding(self):
        d = Disclosure(
            (
                doc("stmt-1", available=False),
                doc("stmt-2", DIGEST_B, available=False),
            )
        )
        self.assertEqual(
            d.describe(),
            "2 documents, 2 not yet made available: stmt-1, stmt-2",
        )

    def test_available_and_outstanding_partition_the_manifest(self):
        d = Disclosure(
            (
                doc("stmt-1"),
                doc("stmt-2", DIGEST_B, available=False),
                doc("stmt-3", DIGEST_C),
            )
        )
        self.assertEqual(
            len(d.available) + len(d.outstanding), len(d.documents)
        )


class BuildDisclosureTests(unittest.TestCase):
    """The manifest is checked against the rows, three ways."""

    def test_it_is_derived_in_identifier_order(self):
        rows = (row("r1", document="stmt-2"), row("r2", document="stmt-1"))
        built = exhibit._build_disclosure(
            rows, [doc("stmt-2", DIGEST_B), doc("stmt-1")]
        )
        self.assertEqual(
            [d.identifier for d in built.documents], ["stmt-1", "stmt-2"]
        )

    def test_a_document_listed_twice_is_refused(self):
        with self.assertRaises(DisclosureError) as caught:
            exhibit._build_disclosure(
                (row("r1"),), [doc("stmt-1"), doc("stmt-1", DIGEST_B)]
            )
        self.assertIn("twice", str(caught.exception))

    def test_a_row_citing_an_unlisted_document_is_refused(self):
        """The fatal one: the exhibit would rest on material the other side
        was never told about, silently."""
        with self.assertRaises(DisclosureError) as caught:
            exhibit._build_disclosure(
                (row("r1", document="stmt-9"),), [doc("stmt-1")]
            )
        self.assertIn("stmt-9", str(caught.exception))

    def test_a_listed_document_no_row_cites_is_refused(self):
        """Overstating what the exhibit rests on sends someone to produce
        papers it does not need."""
        with self.assertRaises(DisclosureError) as caught:
            exhibit._build_disclosure(
                (row("r1"),), [doc("stmt-1"), doc("stmt-7", DIGEST_B)]
            )
        self.assertIn("stmt-7", str(caught.exception))

    def test_a_non_document_in_the_manifest_is_refused(self):
        with self.assertRaises(DisclosureError):
            exhibit._build_disclosure((row("r1"),), ["stmt-1"])

    def test_several_rows_may_share_one_document(self):
        built = exhibit._build_disclosure(
            (row("r1"), row("r2"), row("r3")), [doc("stmt-1")]
        )
        self.assertEqual(len(built.documents), 1)

    def test_every_cited_document_appears_once(self):
        rows = (
            row("r1", document="stmt-1"),
            row("r2", document="stmt-2"),
            row("r3", document="stmt-1"),
        )
        built = exhibit._build_disclosure(
            rows, [doc("stmt-1"), doc("stmt-2", DIGEST_B)]
        )
        self.assertEqual(
            [d.identifier for d in built.documents], ["stmt-1", "stmt-2"]
        )


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------


class CompositionTests(unittest.TestCase):
    def test_a_uniform_exhibit(self):
        composition = exhibit._composition(many(4))
        self.assertEqual(composition.counts, {ProofClass.p1: 4})
        self.assertTrue(composition.is_uniform)
        self.assertIs(composition.weakest, ProofClass.p1)

    def test_counts_and_subtotals_agree_per_class(self):
        rows = (
            row("r1", proof_class=ProofClass.p0, units=100),
            row("r2", proof_class=ProofClass.p1, units=200),
            row("r3", proof_class=ProofClass.p1, units=300),
            row("r4", proof_class=ProofClass.p4, units=400),
        )
        composition = exhibit._composition(rows)
        self.assertEqual(
            composition.counts,
            {ProofClass.p0: 1, ProofClass.p1: 2, ProofClass.p4: 1},
        )
        self.assertEqual(composition.amounts[ProofClass.p1], usd(500))
        self.assertEqual(composition.amounts[ProofClass.p0], usd(100))
        self.assertEqual(composition.amounts[ProofClass.p4], usd(400))

    def test_the_weakest_class_is_the_weakest_present(self):
        rows = (
            row("r1", proof_class=ProofClass.p0),
            row("r2", proof_class=ProofClass.p3),
        )
        self.assertIs(exhibit._composition(rows).weakest, ProofClass.p3)

    def test_ordering_comes_from_flow_and_is_strongest_first(self):
        rows = (
            row("r1", proof_class=ProofClass.p4),
            row("r2", proof_class=ProofClass.p0),
            row("r3", proof_class=ProofClass.p2),
        )
        self.assertEqual(
            exhibit._composition(rows).classes,
            (ProofClass.p0, ProofClass.p2, ProofClass.p4),
        )

    def test_it_returns_the_shared_type(self):
        """One question about composition, one answer to it."""
        self.assertIsInstance(exhibit._composition(many(2)), ClassComposition)

    def test_row_order_does_not_change_the_result(self):
        rows = (
            row("r1", proof_class=ProofClass.p0, units=100),
            row("r2", proof_class=ProofClass.p1, units=200),
            row("r3", proof_class=ProofClass.p4, units=300),
        )
        for permutation in itertools.permutations(rows):
            with self.subTest(order=[r.reference for r in permutation]):
                self.assertEqual(
                    exhibit._composition(permutation).counts,
                    exhibit._composition(rows).counts,
                )
                self.assertEqual(
                    exhibit._composition(permutation).classes,
                    exhibit._composition(rows).classes,
                )


def spread(count: int, *, first: str = "stmt-1", second: str = "stmt-2"):
    """``count`` clean p1 rows drawn from two documents.

    Two rather than one because an exhibit whose every row comes from a single
    document draws a caveat of its own, and a test of the clean path should not
    have to explain that away.
    """
    return tuple(
        row(
            f"r{index}",
            units=100 + index,
            document=first if index % 2 == 0 else second,
        )
        for index in range(count)
    )


# ---------------------------------------------------------------------------
# The category
# ---------------------------------------------------------------------------


class TheCleanSummaryPath(unittest.TestCase):
    """Thirty P1 rows over two documents, enumerated: Rule 1006, nothing owed.

    Worth stating positively and in one place.  Most of what follows is a
    departure from this case, and a suite that only ever tested departures
    would not notice a mutant that made every artefact an aid.
    """

    def setUp(self):
        self.tagged = tag(spread(30))

    def test_it_is_a_rule_1006_summary(self):
        self.assertIs(self.tagged.rule, SummaryRule.rule_1006)

    def test_it_is_evidence(self):
        """Goes to the jury room; the court may not instruct otherwise."""
        self.assertTrue(self.tagged.is_evidence)

    def test_the_ground_is_stated_and_is_the_only_one(self):
        self.assertEqual(
            self.tagged.reasons, (REASON_SUMMARISES_ADMISSIBLE_RECORDS,)
        )

    def test_nothing_is_outstanding(self):
        self.assertEqual(self.tagged.conditions, ())
        self.assertTrue(self.tagged.is_offerable)

    def test_nothing_is_contestable_on_these_facts(self):
        self.assertEqual(self.tagged.caveats, ())

    def test_the_total_is_the_sum_of_the_rows(self):
        self.assertEqual(self.tagged.total, usd(sum(100 + i for i in range(30))))

    def test_it_describes_itself_in_one_sentence(self):
        self.assertEqual(
            self.tagged.describe(),
            f"rule_1006: 30 rows totalling {self.tagged.total.format()} "
            f"(p1 30 rows {self.tagged.total.format()})",
        )


class ContentKindDecidesTheCategory(unittest.TestCase):
    """The first of the two grounds: what the artefact asserts."""

    def test_summarising_content_may_be_evidence(self):
        for kind in sorted(SUMMARISING_CONTENT, key=lambda k: k.value):
            with self.subTest(content=kind):
                self.assertIs(
                    tag(spread(30), content=kind).rule, SummaryRule.rule_1006
                )

    def test_content_that_adds_to_the_records_is_an_aid(self):
        for kind in ContentKind:
            if kind in SUMMARISING_CONTENT:
                continue
            with self.subTest(content=kind):
                self.assertIs(
                    tag(spread(30), content=kind).rule, SummaryRule.rule_107
                )

    def test_the_aid_reason_names_the_kind(self):
        """So a reader can tell which part of the page cost the category."""
        for kind in ContentKind:
            if kind in SUMMARISING_CONTENT:
                continue
            with self.subTest(content=kind):
                tagged = tag(spread(30), content=kind)
                self.assertEqual(len(tagged.reasons), 1)
                self.assertTrue(
                    tagged.reasons[0].startswith(REASON_CONTENT_IS_AN_AID)
                )
                self.assertIn(f"({kind.value})", tagged.reasons[0])

    def test_every_kind_is_decided(self):
        for kind in ContentKind:
            with self.subTest(content=kind):
                self.assertIn(
                    tag(spread(30), content=kind).rule,
                    (SummaryRule.rule_1006, SummaryRule.rule_107),
                )

    def test_the_content_is_carried_on_the_tag(self):
        """The declaration survives the decision it was used to make."""
        for kind in ContentKind:
            with self.subTest(content=kind):
                self.assertIs(tag(spread(30), content=kind).content, kind)


class SubstrateDecidesTheCategory(unittest.TestCase):
    """The second ground: what the underlying rows are."""

    def _sole(self, proof_class, *, adjudicated=False):
        rows = tuple(
            row(
                f"r{index}",
                proof_class=proof_class,
                units=100 + index,
                document="stmt-1" if index % 2 == 0 else "stmt-2",
                adjudicated=adjudicated,
            )
            for index in range(30)
        )
        return tag(rows)

    def test_p0_p1_p2_alone_bear_a_summary(self):
        for proof_class in (ProofClass.p0, ProofClass.p1, ProofClass.p2):
            with self.subTest(proof_class=proof_class):
                self.assertIs(
                    self._sole(proof_class).rule, SummaryRule.rule_1006
                )

    def test_p3_alone_does_not(self):
        self.assertIs(self._sole(ProofClass.p3).rule, SummaryRule.rule_107)

    def test_p4_alone_does_not(self):
        self.assertIs(self._sole(ProofClass.p4).rule, SummaryRule.rule_107)

    def test_one_weak_row_in_thirty_is_enough(self):
        """`13` §2.2 is a floor, not an average.  A person eyeballing the table
        would not see this row; a machine counting classes does."""
        rows = spread(29) + (row("weak", proof_class=ProofClass.p4),)
        self.assertIs(tag(rows).rule, SummaryRule.rule_107)

    def test_the_reason_counts_one_row_in_the_singular(self):
        rows = spread(29) + (row("weak", proof_class=ProofClass.p4),)
        tagged = tag(rows)
        self.assertEqual(len(tagged.reasons), 1)
        self.assertTrue(
            tagged.reasons[0].startswith(REASON_SUBSTRATE_BELOW_SUMMARY)
        )
        self.assertIn("(1 row at p4)", tagged.reasons[0])

    def test_the_reason_names_every_class_that_fell_short(self):
        rows = spread(28) + (
            row("weak-a", proof_class=ProofClass.p4),
            row("weak-b", proof_class=ProofClass.p3),
        )
        self.assertIn("(2 rows at p3, p4)", tag(rows).reasons[0])

    def test_the_reason_does_not_name_classes_that_did_not(self):
        rows = spread(29) + (row("weak", proof_class=ProofClass.p3),)
        self.assertNotIn("p1", tag(rows).reasons[0])

    def test_a_summary_reason_is_not_also_recorded(self):
        """One category, one explanation of it."""
        rows = spread(29) + (row("weak", proof_class=ProofClass.p3),)
        self.assertNotIn(REASON_SUMMARISES_ADMISSIBLE_RECORDS, tag(rows).reasons)


class BothGroundsAreRecorded(unittest.TestCase):
    """When both apply, both are said.

    A tag that stopped at whichever ground it found first would tell a
    proponent that redrawing the page as a table would move the artefact into
    Rule 1006, when the P4 row would leave it exactly where it was.
    """

    def _both(self, *, weak_first: bool):
        weak = (row("weak", proof_class=ProofClass.p4),)
        clean = spread(29)
        rows = weak + clean if weak_first else clean + weak
        return tag(rows, content=ContentKind.interpretation)

    def test_exactly_two_grounds_are_recorded(self):
        """The count as well as the membership, so that a mutant which appends
        one of them twice dies here too."""
        for weak_first in (True, False):
            with self.subTest(weak_first=weak_first):
                self.assertEqual(len(self._both(weak_first=weak_first).reasons), 2)

    def test_the_content_ground_is_recorded(self):
        for weak_first in (True, False):
            with self.subTest(weak_first=weak_first):
                reasons = self._both(weak_first=weak_first).reasons
                self.assertTrue(
                    any(r.startswith(REASON_CONTENT_IS_AN_AID) for r in reasons)
                )

    def test_the_substrate_ground_is_recorded(self):
        for weak_first in (True, False):
            with self.subTest(weak_first=weak_first):
                reasons = self._both(weak_first=weak_first).reasons
                self.assertTrue(
                    any(
                        r.startswith(REASON_SUBSTRATE_BELOW_SUMMARY)
                        for r in reasons
                    )
                )

    def test_row_order_does_not_change_the_grounds(self):
        self.assertEqual(
            self._both(weak_first=True).reasons,
            self._both(weak_first=False).reasons,
        )

    def test_the_grounds_are_recorded_in_a_fixed_order(self):
        """Content first, substrate second, so two tags over the same material
        diff cleanly."""
        reasons = self._both(weak_first=False).reasons
        self.assertTrue(reasons[0].startswith(REASON_CONTENT_IS_AN_AID))
        self.assertTrue(reasons[1].startswith(REASON_SUBSTRATE_BELOW_SUMMARY))

    def test_it_is_still_only_one_category(self):
        self.assertIs(self._both(weak_first=False).rule, SummaryRule.rule_107)

    def test_removing_one_ground_leaves_the_other(self):
        """The point of recording both: fixing the content does not move it."""
        rows = spread(29) + (row("weak", proof_class=ProofClass.p4),)
        redrawn = tag(rows, content=ContentKind.enumeration)
        self.assertIs(redrawn.rule, SummaryRule.rule_107)
        self.assertEqual(len(redrawn.reasons), 1)
        self.assertTrue(
            redrawn.reasons[0].startswith(REASON_SUBSTRATE_BELOW_SUMMARY)
        )


class AdjudicationDoesNotCreateSubstrate(unittest.TestCase):
    """Admission to the ledger and admissibility as substrate are different.

    :mod:`services.financial.adjudication` says it in as many words: a document
    whose arithmetic does not close is P3, and a well-corroborated adjudication
    explains why it is P3 rather than making it P2.  The honest sentence is "we
    know why this one fails and here is the corroboration".
    """

    def setUp(self):
        self.rows = spread(29) + (
            row("adj", proof_class=ProofClass.p3, adjudicated=True),
        )
        self.tagged = tag(self.rows)

    def test_one_adjudicated_p3_still_costs_the_category(self):
        self.assertIs(self.tagged.rule, SummaryRule.rule_107)

    def test_it_is_not_evidence(self):
        self.assertFalse(self.tagged.is_evidence)

    def test_the_substrate_ground_names_p3(self):
        self.assertIn("(1 row at p3)", self.tagged.reasons[0])

    def test_the_adjudication_is_nonetheless_reported(self):
        """Not silence.  The corroboration is the answer to the obvious
        question about the row, and burying it would invite the question."""
        self.assertIn(f"{CAVEAT_ADJUDICATION_RELIED_ON} (1)", self.tagged.caveats)

    def test_an_adjudicated_row_is_not_also_called_unadjudicated(self):
        self.assertFalse(
            any(c.startswith(CAVEAT_UNADJUDICATED_P3) for c in self.tagged.caveats)
        )

    def test_an_unadjudicated_p3_is_called_that_instead(self):
        rows = spread(29) + (row("raw", proof_class=ProofClass.p3),)
        caveats = tag(rows).caveats
        self.assertIn(f"{CAVEAT_UNADJUDICATED_P3} (1)", caveats)
        self.assertFalse(
            any(c.startswith(CAVEAT_ADJUDICATION_RELIED_ON) for c in caveats)
        )

    def test_both_kinds_of_p3_are_counted_separately(self):
        rows = spread(28) + (
            row("adj", proof_class=ProofClass.p3, adjudicated=True),
            row("raw", proof_class=ProofClass.p3),
        )
        caveats = tag(rows).caveats
        self.assertIn(f"{CAVEAT_ADJUDICATION_RELIED_ON} (1)", caveats)
        self.assertIn(f"{CAVEAT_UNADJUDICATED_P3} (1)", caveats)

    def test_adjudicating_every_row_does_not_promote_the_exhibit(self):
        """The tempting mistake, on the fact pattern that tempts it most."""
        rows = tuple(
            row(
                f"r{index}",
                proof_class=ProofClass.p3,
                units=100 + index,
                document="stmt-1" if index % 2 == 0 else "stmt-2",
                adjudicated=True,
            )
            for index in range(30)
        )
        tagged = tag(rows)
        self.assertIs(tagged.rule, SummaryRule.rule_107)
        self.assertIn(f"{CAVEAT_ADJUDICATION_RELIED_ON} (30)", tagged.caveats)

    def test_the_flag_is_refused_on_a_class_it_cannot_describe(self):
        """Held here as well as on the row, because this is the class whose
        premise it is."""
        for proof_class in ProofClass:
            if proof_class is ProofClass.p3:
                continue
            with self.subTest(proof_class=proof_class):
                with self.assertRaises(ExhibitContentError):
                    row("x", proof_class=proof_class, adjudicated=True)


class DisclosureIsAConditionNotADowngrade(unittest.TestCase):
    """An unmet obligation is work outstanding, not the wrong category.

    Making the records available is an act of the proponent's, curable by an
    email, and is not a property of the data.
    """

    def setUp(self):
        self.rows = spread(30)
        self.short = [doc("stmt-1"), doc("stmt-2", DIGEST_B, available=False)]
        self.tagged = tag(self.rows, self.short)

    def test_the_category_does_not_move(self):
        self.assertIs(self.tagged.rule, SummaryRule.rule_1006)

    def test_it_is_still_evidence(self):
        self.assertTrue(self.tagged.is_evidence)

    def test_the_obligation_is_recorded_as_a_condition(self):
        self.assertEqual(len(self.tagged.conditions), 1)
        self.assertTrue(
            self.tagged.conditions[0].startswith(CONDITION_MAKE_AVAILABLE)
        )

    def test_the_condition_names_the_document_still_owed(self):
        """So the email writes itself."""
        self.assertIn("stmt-2", self.tagged.conditions[0])
        self.assertNotIn("stmt-1", self.tagged.conditions[0])

    def test_it_is_not_also_filed_as_an_argument(self):
        self.assertFalse(
            any(
                c.startswith(CAVEAT_UNDISCLOSED_SOURCES)
                for c in self.tagged.caveats
            )
        )

    def test_it_is_not_offerable_yet(self):
        self.assertFalse(self.tagged.is_offerable)

    def test_meeting_it_makes_the_exhibit_offerable(self):
        cured = tag(self.rows, [doc("stmt-1"), doc("stmt-2", DIGEST_B)])
        self.assertEqual(cured.conditions, ())
        self.assertTrue(cured.is_offerable)
        self.assertIs(cured.rule, SummaryRule.rule_1006)

    def test_the_description_says_what_is_outstanding(self):
        self.assertIn("outstanding:", self.tagged.describe())

    def test_under_rule_107_the_same_shortfall_is_a_caveat(self):
        """Rule 107 imposes no availability requirement, so recording one would
        invent an obligation the proponent does not have."""
        aid = tag(self.rows, self.short, content=ContentKind.interpretation)
        self.assertIs(aid.rule, SummaryRule.rule_107)
        self.assertEqual(aid.conditions, ())
        self.assertTrue(
            any(c.startswith(CAVEAT_UNDISCLOSED_SOURCES) for c in aid.caveats)
        )

    def test_an_aid_with_undisclosed_sources_is_still_offerable(self):
        aid = tag(self.rows, self.short, content=ContentKind.interpretation)
        self.assertTrue(aid.is_offerable)

    def test_a_caveat_never_makes_an_exhibit_unofferable(self):
        """Caveats are arguments; an exhibit does not become unofferable
        because someone may argue about it."""
        rows = spread(29) + (row("weak", proof_class=ProofClass.p4),)
        tagged = tag(rows)
        self.assertTrue(tagged.caveats)
        self.assertTrue(tagged.is_offerable)


# ---------------------------------------------------------------------------
# Arguments, which are not work
# ---------------------------------------------------------------------------


class CaveatsAreArguments(unittest.TestCase):
    """Each of the six, and the order they are recorded in."""

    def test_a_small_set_draws_the_volume_caveat(self):
        self.assertIn(
            f"{CAVEAT_NOT_OBVIOUSLY_VOLUMINOUS} (24 rows, below 25)",
            tag(spread(24)).caveats,
        )

    def test_the_threshold_boundary_is_exclusive(self):
        """At exactly the threshold the caveat does not fire: the number is the
        first count that is comfortably voluminous, not the last that is not."""
        self.assertFalse(
            any(
                c.startswith(CAVEAT_NOT_OBVIOUSLY_VOLUMINOUS)
                for c in tag(spread(CONVENIENTLY_EXAMINABLE_ROWS)).caveats
            )
        )
        self.assertTrue(
            any(
                c.startswith(CAVEAT_NOT_OBVIOUSLY_VOLUMINOUS)
                for c in tag(spread(CONVENIENTLY_EXAMINABLE_ROWS - 1)).caveats
            )
        )

    def test_the_threshold_is_settable(self):
        self.assertFalse(
            any(
                c.startswith(CAVEAT_NOT_OBVIOUSLY_VOLUMINOUS)
                for c in tag(spread(10), voluminous_threshold=10).caveats
            )
        )
        self.assertTrue(
            any(
                c.startswith(CAVEAT_NOT_OBVIOUSLY_VOLUMINOUS)
                for c in tag(spread(10), voluminous_threshold=11).caveats
            )
        )

    def test_zero_suppresses_it_entirely(self):
        """For a caller who has satisfied themselves on the point."""
        self.assertEqual(tag(spread(2), voluminous_threshold=0).caveats, ())

    def test_the_threshold_is_carried_on_the_tag(self):
        """A reader can see which number the caveat was measured against."""
        self.assertEqual(tag(spread(30), voluminous_threshold=7).voluminous_threshold, 7)

    def test_one_document_draws_its_own_caveat(self):
        self.assertIn(f"{CAVEAT_SINGLE_DOCUMENT} (stmt-1)", tag(many(30)).caveats)

    def test_two_documents_do_not(self):
        self.assertFalse(
            any(c.startswith(CAVEAT_SINGLE_DOCUMENT) for c in tag(spread(30)).caveats)
        )

    def test_neither_volume_nor_single_document_applies_to_an_aid(self):
        """Both are arguments about Rule 1006's own preconditions, and Rule 107
        has no such preconditions to argue about."""
        aid = tag(many(3), content=ContentKind.interpretation)
        self.assertIs(aid.rule, SummaryRule.rule_107)
        self.assertFalse(
            any(c.startswith(CAVEAT_NOT_OBVIOUSLY_VOLUMINOUS) for c in aid.caveats)
        )
        self.assertFalse(
            any(c.startswith(CAVEAT_SINGLE_DOCUMENT) for c in aid.caveats)
        )

    def test_p4_rows_are_counted_as_assertions(self):
        rows = spread(28) + (
            row("a", proof_class=ProofClass.p4),
            row("b", proof_class=ProofClass.p4),
        )
        self.assertIn(f"{CAVEAT_ASSERTIONS_PRESENT} (2)", tag(rows).caveats)

    def test_a_uniform_exhibit_draws_no_composition_caveat(self):
        self.assertFalse(
            any(c.startswith(CAVEAT_MIXED_COMPOSITION) for c in tag(spread(30)).caveats)
        )

    def test_a_mixed_exhibit_does(self):
        rows = spread(29) + (row("other", proof_class=ProofClass.p0),)
        caveat = [
            c for c in tag(rows).caveats if c.startswith(CAVEAT_MIXED_COMPOSITION)
        ]
        self.assertEqual(len(caveat), 1)
        self.assertIn("p0 1 row", caveat[0])
        self.assertIn("p1 29 rows", caveat[0])

    def test_the_summary_order_is_fixed(self):
        """Volume, then single document, then composition."""
        rows = tuple(
            row(
                f"r{index}",
                proof_class=ProofClass.p0 if index else ProofClass.p1,
                units=100 + index,
            )
            for index in range(10)
        )
        caveats = tag(rows).caveats
        self.assertEqual(len(caveats), 3)
        self.assertTrue(caveats[0].startswith(CAVEAT_NOT_OBVIOUSLY_VOLUMINOUS))
        self.assertTrue(caveats[1].startswith(CAVEAT_SINGLE_DOCUMENT))
        self.assertTrue(caveats[2].startswith(CAVEAT_MIXED_COMPOSITION))

    def test_the_aid_order_is_fixed(self):
        """Assertions, adjudication, unadjudicated P3, then composition."""
        rows = spread(27) + (
            row("p4", proof_class=ProofClass.p4),
            row("adj", proof_class=ProofClass.p3, adjudicated=True),
            row("raw", proof_class=ProofClass.p3),
        )
        caveats = tag(rows).caveats
        self.assertEqual(len(caveats), 4)
        self.assertTrue(caveats[0].startswith(CAVEAT_ASSERTIONS_PRESENT))
        self.assertTrue(caveats[1].startswith(CAVEAT_ADJUDICATION_RELIED_ON))
        self.assertTrue(caveats[2].startswith(CAVEAT_UNADJUDICATED_P3))
        self.assertTrue(caveats[3].startswith(CAVEAT_MIXED_COMPOSITION))

    def test_the_disclosure_caveat_precedes_the_rest(self):
        """It is the one an opponent reaches for first."""
        rows = spread(29) + (row("p4", proof_class=ProofClass.p4),)
        caveats = tag(
            rows,
            [doc("stmt-1"), doc("stmt-2", DIGEST_B, available=False)],
            content=ContentKind.interpretation,
        ).caveats
        self.assertTrue(caveats[0].startswith(CAVEAT_UNDISCLOSED_SOURCES))


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


class RefusalsAreExplicit(unittest.TestCase):
    """Everything this refuses rather than repairs."""

    def test_an_exhibit_of_no_rows(self):
        """A total of zero meaning 'no rows' reads on the page exactly like a
        total of zero meaning 'the money nets out'."""
        with self.assertRaises(ExhibitContentError):
            tag_exhibit((), [], content=ContentKind.enumeration, currency="USD")

    def test_something_that_is_not_a_row(self):
        with self.assertRaises(ExhibitContentError) as caught:
            tag_exhibit(
                (row("r0"), "r1"),
                [doc("stmt-1")],
                content=ContentKind.enumeration,
                currency="USD",
            )
        self.assertIn("row 1", str(caught.exception))

    def test_content_outside_the_vocabulary(self):
        for bad in ("enumeration", None, 0):
            with self.subTest(content=bad):
                with self.assertRaises(ExhibitContentError):
                    tag(spread(3), content=bad)

    def test_a_threshold_that_is_not_a_count(self):
        for bad in (25.0, "25", None, True, False):
            with self.subTest(threshold=bad):
                with self.assertRaises(ExhibitContentError):
                    tag(spread(3), voluminous_threshold=bad)

    def test_a_negative_threshold(self):
        """Zero already means 'suppressed'; a negative number would read as
        though it had been considered."""
        with self.assertRaises(ExhibitContentError):
            tag(spread(3), voluminous_threshold=-1)

    def test_a_currency_this_system_does_not_know(self):
        with self.assertRaises(ExhibitCurrencyError):
            tag(spread(3), currency="QQQ")

    def test_rows_in_a_currency_other_than_the_stated_one(self):
        """Dropping them would produce a total that looks complete and is not."""
        rows = spread(2) + (
            ExhibitRow(
                reference="eur",
                proof_class=ProofClass.p1,
                amount=Money.from_minor_units(500, "EUR"),
                document="stmt-1",
            ),
        )
        with self.assertRaises(ExhibitCurrencyError) as caught:
            tag(rows)
        self.assertIn("EUR", str(caught.exception))

    def test_a_repeated_reference(self):
        """A reviewer's note comes back to the reference; a repeated one lands
        the round trip on the wrong row without anything looking wrong."""
        with self.assertRaises(DuplicateReferenceError):
            tag((row("same", units=100), row("same", units=200)))

    def test_a_row_citing_a_document_the_manifest_omits(self):
        with self.assertRaises(DisclosureError):
            tag_exhibit(
                spread(4),
                [doc("stmt-1")],
                content=ContentKind.enumeration,
                currency="USD",
            )

    def test_a_manifest_entry_no_row_cites(self):
        with self.assertRaises(DisclosureError):
            tag_exhibit(
                many(4),
                [doc("stmt-1"), doc("stmt-9", DIGEST_C)],
                content=ContentKind.enumeration,
                currency="USD",
            )

    def test_a_document_listed_twice(self):
        with self.assertRaises(DisclosureError):
            tag_exhibit(
                many(4),
                [doc("stmt-1"), doc("stmt-1", DIGEST_B, available=False)],
                content=ContentKind.enumeration,
                currency="USD",
            )

    def test_a_manifest_of_names_rather_than_documents(self):
        with self.assertRaises(DisclosureError):
            tag_exhibit(
                many(4),
                ["stmt-1"],
                content=ContentKind.enumeration,
                currency="USD",
            )


# ---------------------------------------------------------------------------
# What the tag reads back
# ---------------------------------------------------------------------------


class TheTagReadsBack(unittest.TestCase):
    def setUp(self):
        self.rows = spread(30)
        self.tagged = tag(self.rows)

    def test_the_row_count(self):
        self.assertEqual(self.tagged.row_count, 30)

    def test_the_rows_are_carried_in_the_order_given(self):
        self.assertEqual(self.tagged.rows, self.rows)

    def test_the_references_are_in_row_order_not_sorted(self):
        """A note on the fourth line means the fourth line."""
        rows = (row("zebra"), row("alpha", units=200), row("mike", units=300))
        self.assertEqual(tag(rows).references, ("zebra", "alpha", "mike"))

    def test_a_sequence_is_accepted_and_frozen(self):
        tagged = tag(list(self.rows))
        self.assertIsInstance(tagged.rows, tuple)

    def test_the_currency_is_the_resolved_code(self):
        """Not the string the caller happened to type."""
        self.assertEqual(tag(spread(3), currency="usd").currency, "USD")

    def test_is_evidence_follows_the_rule(self):
        self.assertTrue(self.tagged.is_evidence)
        self.assertFalse(
            tag(self.rows, content=ContentKind.interpretation).is_evidence
        )

    def test_the_manifest_is_in_identifier_order(self):
        self.assertEqual(
            [d.identifier for d in self.tagged.disclosure.documents],
            ["stmt-1", "stmt-2"],
        )

    def test_the_composition_accounts_for_every_row(self):
        self.assertEqual(sum(self.tagged.composition.counts.values()), 30)

    def test_the_description_of_an_aid_names_the_rule(self):
        aid = tag(self.rows, content=ContentKind.interpretation)
        self.assertTrue(aid.describe().startswith("rule_107: 30 rows totalling "))

    def test_the_description_puts_arguments_last(self):
        tagged = tag(
            spread(24),
            [doc("stmt-1"), doc("stmt-2", DIGEST_B, available=False)],
        )
        described = tagged.describe()
        self.assertLess(
            described.index("outstanding:"), described.index("contestable:")
        )

    def test_a_single_row_is_described_in_the_singular(self):
        self.assertIn("1 row totalling", tag((row("only"),)).describe())


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


def _intact(**overrides) -> ExhibitTag:
    """A valid tag built by hand, with fields replaced one at a time.

    Built directly rather than through :func:`tag_exhibit` because the point is
    to break identities that the entry point cannot produce, and a test that
    could only reach them through the entry point would be testing the entry
    point twice.
    """
    rows = spread(4)
    fields = dict(
        rule=SummaryRule.rule_1006,
        content=ContentKind.enumeration,
        currency="USD",
        rows=rows,
        total=usd(sum(100 + index for index in range(4))),
        disclosure=Disclosure(
            documents=(doc("stmt-1"), doc("stmt-2", DIGEST_B))
        ),
        composition=exhibit._composition(rows),
        reasons=(REASON_SUMMARISES_ADMISSIBLE_RECORDS,),
        conditions=(),
        caveats=(),
        voluminous_threshold=CONVENIENTLY_EXAMINABLE_ROWS,
    )
    fields.update(overrides)
    return ExhibitTag(**fields)


class InvariantsAreEnforced(unittest.TestCase):
    """A discrepancy here would be found by opposing counsel with a calculator."""

    def test_the_baseline_is_valid(self):
        """Otherwise the tests below would pass for the wrong reason."""
        self.assertIs(_intact().rule, SummaryRule.rule_1006)

    def test_a_total_that_is_not_the_sum_of_the_rows(self):
        with self.assertRaises(ExhibitInvariantError) as caught:
            _intact(total=usd(1))
        self.assertIn("not the sum of its own rows", str(caught.exception))

    def test_class_subtotals_that_do_not_reach_the_total(self):
        with self.assertRaises(ExhibitInvariantError) as caught:
            _intact(
                composition=ClassComposition(
                    counts={ProofClass.p1: 4}, amounts={ProofClass.p1: usd(1)}
                )
            )
        self.assertIn("proof-class subtotals", str(caught.exception))

    def test_class_counts_that_do_not_reach_the_row_count(self):
        with self.assertRaises(ExhibitInvariantError) as caught:
            _intact(
                composition=ClassComposition(
                    counts={ProofClass.p1: 3},
                    amounts={
                        ProofClass.p1: usd(sum(100 + i for i in range(4)))
                    },
                )
            )
        self.assertIn("accounts for 3 rows", str(caught.exception))

    def test_a_category_with_no_stated_ground(self):
        """An unexplained category is one a witness cannot defend."""
        with self.assertRaises(ExhibitInvariantError):
            _intact(reasons=())

    def test_a_tag_over_no_rows(self):
        with self.assertRaises(ExhibitContentError):
            _intact(rows=(), total=usd(0))

    def test_the_tag_is_frozen(self):
        """The rule cannot be edited away from the reasons that produced it."""
        with self.assertRaises(Exception):
            _intact().rule = SummaryRule.rule_107

    def test_is_evidence_cannot_disagree_with_the_rule(self):
        """A property, not a stored field, so there is nothing to set."""
        self.assertFalse(_intact(rule=SummaryRule.rule_107).is_evidence)


# ---------------------------------------------------------------------------
# Determinism and surface
# ---------------------------------------------------------------------------


class TheSameMaterialTagsTheSameWay(unittest.TestCase):
    """Two tags over the same material must diff cleanly or the diff is noise."""

    def test_repeating_the_call_repeats_the_tag(self):
        rows = spread(27) + (
            row("p4", proof_class=ProofClass.p4),
            row("adj", proof_class=ProofClass.p3, adjudicated=True),
            row("raw", proof_class=ProofClass.p3),
        )
        first, second = tag(rows), tag(rows)
        self.assertEqual(first.reasons, second.reasons)
        self.assertEqual(first.caveats, second.caveats)
        self.assertEqual(first.describe(), second.describe())

    def test_manifest_order_does_not_matter(self):
        rows = spread(6)
        forward = [doc("stmt-1"), doc("stmt-2", DIGEST_B)]
        self.assertEqual(
            tag(rows, forward).disclosure.documents,
            tag(rows, list(reversed(forward))).disclosure.documents,
        )

    def test_the_composition_is_ordered_strongest_first(self):
        rows = (
            row("a", proof_class=ProofClass.p4),
            row("b", proof_class=ProofClass.p0, units=200),
            row("c", proof_class=ProofClass.p2, units=300),
        )
        self.assertEqual(
            tag(rows).composition.classes,
            (ProofClass.p0, ProofClass.p2, ProofClass.p4),
        )


class ThePackageSurfaceIsWired(unittest.TestCase):
    """Everything this module adds is reachable from ``services.financial``.

    The package re-exports flat, and a name added to a module but not to the
    package is a name callers will not find.
    """

    NAMES = (
        "CAVEAT_ADJUDICATION_RELIED_ON",
        "CAVEAT_ASSERTIONS_PRESENT",
        "CAVEAT_MIXED_COMPOSITION",
        "CAVEAT_NOT_OBVIOUSLY_VOLUMINOUS",
        "CAVEAT_SINGLE_DOCUMENT",
        "CAVEAT_UNADJUDICATED_P3",
        "CAVEAT_UNDISCLOSED_SOURCES",
        "CONDITION_MAKE_AVAILABLE",
        "CONVENIENTLY_EXAMINABLE_ROWS",
        "ContentKind",
        "Disclosure",
        "DisclosureError",
        "DuplicateReferenceError",
        "ExhibitContentError",
        "ExhibitCurrencyError",
        "ExhibitError",
        "ExhibitInvariantError",
        "ExhibitRow",
        "ExhibitTag",
        "REASON_CONTENT_IS_AN_AID",
        "REASON_SUBSTRATE_BELOW_SUMMARY",
        "REASON_SUMMARISES_ADMISSIBLE_RECORDS",
        "SUMMARISING_CONTENT",
        "SUMMARY_SUBSTRATE_CLASSES",
        "SourceDocument",
        "SummaryRule",
        "may_bear_summary",
        "tag_exhibit",
        "weakest_content",
    )

    def test_every_name_is_exported(self):
        import services.financial as package

        for name in self.NAMES:
            with self.subTest(name=name):
                self.assertIn(name, package.__all__)

    def test_every_name_is_the_same_object(self):
        import services.financial as package

        for name in self.NAMES:
            with self.subTest(name=name):
                self.assertIs(getattr(package, name), getattr(exhibit, name))

    def test_the_errors_share_one_root(self):
        """A caller who wants to catch everything this raises can catch one
        class, and one that wants to distinguish them still can."""
        for error in (
            ExhibitContentError,
            DuplicateReferenceError,
            DisclosureError,
            ExhibitCurrencyError,
            ExhibitInvariantError,
        ):
            with self.subTest(error=error.__name__):
                self.assertTrue(issubclass(error, exhibit.ExhibitError))


if __name__ == "__main__":
    unittest.main()
