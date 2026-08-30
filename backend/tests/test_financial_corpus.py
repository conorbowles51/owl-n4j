"""Tests for the corpus harness.

The harness is the thing that checks the reader against 326 real documents,
which raises an obvious problem: those documents are case material and are not
in this repository, so the tests that need them cannot run everywhere and the
tests that run everywhere cannot use them.

The split below is the answer, and it is deliberate rather than a compromise.
:class:`TheClassifier`, :class:`DiscoverySkipsTheCorpusOwnBookkeeping`,
:class:`ReportsAnswerQuestionsAboutTheWholeCorpus` and
:class:`ReadingsCarryNoCaseContent` run anywhere, on synthetic control blocks
built out of round numbers and placeholder identifiers.  They test the logic.
:class:`TheEtFraudCorpus` needs the evidence and skips without it.  It tests
the *measurements* — the ones written into
:class:`~postgres.models.enums.TotalsConvention`, into the statement-totals
module docstring, and into the two findings under ``docs/financial-forensics``.

What the second half is really for is the join between two things that must
not drift apart: the set of documents this harness finds failing, and the set
:mod:`services.financial.adjudication` has verdicts for.  Both are written
down independently.  A reader fix that makes a document close leaves a stale
verdict; a regression that breaks a new one leaves an unexplained failure.
Asserting the two sets are equal catches both, and asserting each verdict's
recorded residual equals the residual the corpus actually produces catches the
subtler case where the set is right and a number in it has gone stale.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError, dataclass, fields
from decimal import Decimal
from pathlib import Path

from postgres.models.enums import TotalsConvention
from services.financial.adjudication import Adjudication
from services.financial.corpus import (
    CorpusOutcome,
    CorpusReport,
    CorpusUnavailableError,
    DocumentReading,
    MalformedExtractionError,
    iter_extraction_files,
    load_corpus,
    read_extraction,
    survey,
)
from services.financial.money import Money
from tests.test_financial_adjudication import ALL_ADJUDICATIONS

USD = "USD"


def usd(text: str) -> Money:
    return Money.from_decimal(Decimal(text), USD)


def block(**figures: object) -> dict[str, object]:
    """A synthetic extraction carrying nothing but a control block."""
    return {"bank": "Placeholder Bank", "header_totals": dict(figures)}


def classify(document: str = "DOC-1", batch: str = "2026-01-01", **figures):
    return read_extraction(
        block(**figures), document=document, batch=batch, currency=USD
    )


# ---------------------------------------------------------------------------


class TheClassifier(unittest.TestCase):
    """One extraction in, one outcome out, with nothing inferred quietly."""

    def test_a_block_that_only_subtracts_is_magnitude(self):
        reading = classify(
            beginning_balance=100.0,
            ending_balance=120.0,
            deposits=50.0,
            withdrawals=30.0,
        )
        self.assertIs(reading.outcome, CorpusOutcome.magnitude)
        self.assertEqual(reading.balancing, frozenset({TotalsConvention.magnitude}))
        self.assertEqual(reading.delta_magnitude, usd("0.00"))
        self.assertEqual(reading.delta_signed, usd("60.00"))

    def test_a_block_printing_outflows_negative_is_signed(self):
        reading = classify(
            beginning_balance=100.0,
            ending_balance=120.0,
            deposits=50.0,
            withdrawals=-30.0,
        )
        self.assertIs(reading.outcome, CorpusOutcome.signed)
        self.assertEqual(reading.balancing, frozenset({TotalsConvention.signed}))
        self.assertEqual(reading.delta_signed, usd("0.00"))
        self.assertEqual(reading.delta_magnitude, usd("60.00"))

    def test_a_block_whose_outflows_are_all_zero_evidences_no_dialect(self):
        reading = classify(
            beginning_balance=100.0,
            ending_balance=150.0,
            deposits=50.0,
            checks=0.0,
        )
        self.assertIs(reading.outcome, CorpusOutcome.ambiguous)
        self.assertEqual(len(reading.balancing), 2)

    def test_a_block_that_closes_under_neither_dialect_is_unexplained(self):
        reading = classify(
            beginning_balance=100.0,
            ending_balance=999.0,
            deposits=50.0,
            withdrawals=30.0,
        )
        self.assertIs(reading.outcome, CorpusOutcome.unexplained)
        self.assertEqual(reading.balancing, frozenset())
        self.assertTrue(reading.is_testable)

    def test_a_lost_sign_on_the_opening_leaves_a_residual_of_twice_it(self):
        """The mechanism ten files in the corpus exhibit, in miniature.

        Included here because it is the one arithmetic relationship the
        adjudication records are held to, and it should be demonstrable
        without any case material at all.
        """
        reading = classify(
            beginning_balance=12.00,  # printed positive; the statement said -12.00
            ending_balance=-12.00,
            deposits=100.0,
            withdrawals=100.0,
        )
        self.assertIs(reading.outcome, CorpusOutcome.unexplained)
        self.assertEqual(reading.residual, usd("24.00"))
        self.assertEqual(reading.residual, usd("12.00") * 2)

    def test_a_block_with_no_balances_is_not_testable(self):
        reading = classify(deposits=50.0, withdrawals=30.0)
        self.assertIs(reading.outcome, CorpusOutcome.not_testable)
        self.assertFalse(reading.is_testable)

    def test_balances_with_no_flows_are_also_not_testable(self):
        reading = classify(beginning_balance=100.0, ending_balance=100.0)
        self.assertIs(reading.outcome, CorpusOutcome.not_testable)

    def test_an_unreadable_figure_is_an_outcome_and_not_an_exception(self):
        """A survey that dies on one document reports nothing about the rest."""
        reading = classify(
            beginning_balance="not a number",
            ending_balance=100.0,
            deposits=50.0,
        )
        self.assertIs(reading.outcome, CorpusOutcome.unreadable)
        self.assertIsNotNone(reading.unreadable_reason)
        self.assertIn("beginning_balance", reading.unreadable_reason)
        self.assertFalse(reading.is_testable)

    def test_field_names_no_role_claims_are_reported_rather_than_dropped(self):
        reading = classify(
            beginning_balance=100.0,
            ending_balance=120.0,
            deposits=50.0,
            withdrawals=30.0,
            average_ledger_balance=88.0,
            notes="anything",
        )
        self.assertEqual(
            reading.unmapped, ("average_ledger_balance", "notes")
        )

    def test_aliases_are_followed_rather_than_fixed_field_names(self):
        """The same block under two naming conventions classifies identically."""
        first = classify(
            beginning_balance=100.0,
            ending_balance=120.0,
            deposits_credits=50.0,
            withdrawals_debits=30.0,
        )
        second = classify(
            opening=100.0,
            closing=120.0,
            credits=50.0,
            debits=30.0,
        )
        self.assertIs(first.outcome, CorpusOutcome.magnitude)
        self.assertIs(second.outcome, CorpusOutcome.magnitude)
        self.assertEqual(first.delta_magnitude, second.delta_magnitude)
        self.assertEqual(first.unmapped, ())
        self.assertEqual(second.unmapped, ())

    def test_several_withdrawal_buckets_are_summed_not_first_matched(self):
        reading = classify(
            beginning_balance=100.0,
            ending_balance=40.0,
            deposits_additions=50.0,
            checks=40.0,
            electronic_withdrawals=60.0,
            other_withdrawals=10.0,
        )
        self.assertIs(reading.outcome, CorpusOutcome.magnitude)

    def test_the_institution_is_carried_verbatim(self):
        payload = {"bank": "Capital One 360 (subpoena response)",
                   "header_totals": {}}
        reading = read_extraction(
            payload, document="DOC-1", batch="B", currency=USD
        )
        self.assertEqual(reading.institution, "Capital One 360 (subpoena response)")

    def test_a_non_string_institution_is_dropped_rather_than_coerced(self):
        payload = {"bank": 7, "header_totals": {}}
        reading = read_extraction(
            payload, document="DOC-1", batch="B", currency=USD
        )
        self.assertIsNone(reading.institution)


class TheClassifierRefusesMalformedFiles(unittest.TestCase):
    """A fault in the file is not a finding about the document."""

    def test_a_missing_control_block_raises_rather_than_reading_as_untestable(self):
        with self.assertRaises(MalformedExtractionError) as caught:
            read_extraction(
                {"bank": "Placeholder Bank"},
                document="DOC-1",
                batch="B",
                currency=USD,
            )
        self.assertIn("never printed one", str(caught.exception))

    def test_an_empty_control_block_is_untestable_and_not_an_error(self):
        """A document that printed no control totals is ordinary, not broken."""
        reading = read_extraction(
            {"header_totals": {}}, document="DOC-1", batch="B", currency=USD
        )
        self.assertIs(reading.outcome, CorpusOutcome.not_testable)

    def test_a_control_block_that_is_not_a_mapping_raises(self):
        with self.assertRaises(MalformedExtractionError):
            read_extraction(
                {"header_totals": [1, 2, 3]},
                document="DOC-1",
                batch="B",
                currency=USD,
            )

    def test_an_extraction_that_is_not_a_mapping_raises(self):
        with self.assertRaises(MalformedExtractionError):
            read_extraction(
                ["not", "an", "extraction"],
                document="DOC-1",
                batch="B",
                currency=USD,
            )

    def test_a_reading_must_name_its_document(self):
        with self.assertRaises(MalformedExtractionError):
            read_extraction(block(), document="   ", batch="B", currency=USD)

    def test_a_reading_must_name_its_batch(self):
        """Because the same document is extracted twice and the answers differ."""
        with self.assertRaises(MalformedExtractionError):
            read_extraction(block(), document="DOC-1", batch="", currency=USD)


class DiscoverySkipsTheCorpusOwnBookkeeping(unittest.TestCase):
    """Inventories, queues and archives are not extractions."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def write(self, relative: str, payload: object = None) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload if payload is not None else {}))

    def test_batches_and_extractions_are_found_in_a_stable_order(self):
        self.write("2026-01-02/DOC-2.json")
        self.write("2026-01-01/DOC-3.json")
        self.write("2026-01-01/DOC-1.json")
        found = list(iter_extraction_files(self.root))
        self.assertEqual(
            [(f.batch, f.document) for f in found],
            [
                ("2026-01-01", "DOC-1"),
                ("2026-01-01", "DOC-3"),
                ("2026-01-02", "DOC-2"),
            ],
        )

    def test_underscored_files_and_directories_are_skipped(self):
        self.write("2026-01-01/DOC-1.json")
        self.write("2026-01-01/_queue.json")
        self.write("2026-01-01/_audit_summary.json")
        self.write("_archive_bad_run/DOC-9.json")
        self.write("_ocr_cache/DOC-8.json")
        self.write("_inventory.json")
        found = list(iter_extraction_files(self.root))
        self.assertEqual([f.document for f in found], ["DOC-1"])

    def test_non_json_files_are_skipped(self):
        self.write("2026-01-01/DOC-1.json")
        (self.root / "2026-01-01" / "_progress.md").write_text("notes")
        (self.root / "2026-01-01" / "README.txt").write_text("notes")
        found = list(iter_extraction_files(self.root))
        self.assertEqual([f.document for f in found], ["DOC-1"])

    def test_an_absent_corpus_is_distinguishable_from_an_empty_one(self):
        with self.assertRaises(CorpusUnavailableError):
            list(iter_extraction_files(self.root / "nowhere"))

    def test_a_root_holding_no_batches_raises_rather_than_reporting_zero(self):
        with self.assertRaises(CorpusUnavailableError):
            load_corpus(self.root, currency=USD)

    def test_load_reads_and_classifies(self):
        self.write(
            "2026-01-01/DOC-1.json",
            {
                "bank": "Placeholder Bank",
                "header_totals": {
                    "beginning_balance": 100.0,
                    "ending_balance": 120.0,
                    "deposits": 50.0,
                    "withdrawals": 30.0,
                },
            },
        )
        report = load_corpus(self.root, currency=USD)
        self.assertEqual(report.file_count, 1)
        self.assertEqual(report.counts()[CorpusOutcome.magnitude], 1)

    def test_a_file_that_is_not_json_stops_the_survey(self):
        self.write("2026-01-01/DOC-1.json")
        (self.root / "2026-01-01" / "DOC-2.json").write_text("{ not json")
        with self.assertRaises(MalformedExtractionError):
            load_corpus(self.root, currency=USD)


class ReportsAnswerQuestionsAboutTheWholeCorpus(unittest.TestCase):
    """The questions that only make sense across all the documents at once."""

    def reading(self, document, batch, outcome, **kwargs) -> DocumentReading:
        base = dict(
            document=document,
            batch=batch,
            outcome=outcome,
            currency=USD,
            institution=None,
            balancing=frozenset(),
            delta_magnitude=None,
            delta_signed=None,
            unmapped=(),
            signs_coherent=True,
        )
        base.update(kwargs)
        return DocumentReading(**base)

    def test_files_and_documents_are_counted_separately(self):
        report = survey(
            [
                self.reading("DOC-1", "b1", CorpusOutcome.magnitude),
                self.reading("DOC-1", "b2", CorpusOutcome.magnitude),
                self.reading("DOC-2", "b1", CorpusOutcome.magnitude),
            ]
        )
        self.assertEqual(report.file_count, 3)
        self.assertEqual(report.document_count, 2)
        self.assertEqual(report.re_extracted, ("DOC-1",))

    def test_every_outcome_appears_in_the_census_including_the_absent_ones(self):
        report = survey([self.reading("DOC-1", "b1", CorpusOutcome.magnitude)])
        counts = report.counts()
        self.assertEqual(set(counts), set(CorpusOutcome))
        self.assertEqual(counts[CorpusOutcome.unreadable], 0)

    def test_the_counts_partition_the_survey(self):
        report = survey(
            [
                self.reading("DOC-1", "b1", CorpusOutcome.magnitude),
                self.reading("DOC-2", "b1", CorpusOutcome.not_testable),
                self.reading("DOC-3", "b1", CorpusOutcome.unexplained),
            ]
        )
        self.assertEqual(sum(report.counts().values()), report.file_count)

    def test_agreeing_re_extractions_are_not_a_disagreement(self):
        report = survey(
            [
                self.reading("DOC-1", "b1", CorpusOutcome.magnitude),
                self.reading("DOC-1", "b2", CorpusOutcome.magnitude),
            ]
        )
        self.assertEqual(report.re_extracted, ("DOC-1",))
        self.assertEqual(report.disagreements(), ())

    def test_a_re_extraction_that_lost_a_testable_identity_is_flagged(self):
        report = survey(
            [
                self.reading("DOC-1", "2026-01-01", CorpusOutcome.magnitude),
                self.reading("DOC-1", "2026-01-02", CorpusOutcome.not_testable),
            ]
        )
        disagreements = report.disagreements()
        self.assertEqual(len(disagreements), 1)
        self.assertTrue(disagreements[0].lost_a_testable_identity)

    def test_gaining_a_testable_identity_is_a_disagreement_but_not_a_loss(self):
        report = survey(
            [
                self.reading("DOC-1", "2026-01-01", CorpusOutcome.not_testable),
                self.reading("DOC-1", "2026-01-02", CorpusOutcome.magnitude),
            ]
        )
        disagreements = report.disagreements()
        self.assertEqual(len(disagreements), 1)
        self.assertFalse(disagreements[0].lost_a_testable_identity)

    def test_disagreements_are_ordered_by_batch_so_direction_is_visible(self):
        report = survey(
            [
                self.reading("DOC-1", "2026-01-02", CorpusOutcome.not_testable),
                self.reading("DOC-1", "2026-01-01", CorpusOutcome.magnitude),
            ]
        )
        self.assertEqual(
            report.disagreements()[0].outcomes,
            (
                ("2026-01-01", CorpusOutcome.magnitude),
                ("2026-01-02", CorpusOutcome.not_testable),
            ),
        )

    def test_the_unmapped_census_counts_across_documents(self):
        report = survey(
            [
                self.reading(
                    "DOC-1", "b1", CorpusOutcome.magnitude, unmapped=("notes",)
                ),
                self.reading(
                    "DOC-2",
                    "b1",
                    CorpusOutcome.magnitude,
                    unmapped=("notes", "cycles"),
                ),
            ]
        )
        self.assertEqual(report.unmapped_census(), {"notes": 2, "cycles": 1})

    def test_a_report_renders_the_same_way_twice(self):
        report = survey(
            [
                self.reading(
                    "DOC-1",
                    "b1",
                    CorpusOutcome.unexplained,
                    delta_magnitude=usd("24.00"),
                ),
                self.reading("DOC-2", "b1", CorpusOutcome.magnitude),
            ]
        )
        self.assertEqual(report.render(), report.render())
        self.assertIn("Unexplained", report.render())
        self.assertIn("DOC-1", report.render())


class ReadingsCarryNoCaseContent(unittest.TestCase):
    """Structural, not heuristic.  A record cannot leak what it cannot hold."""

    def test_the_reading_has_nowhere_to_put_case_content(self):
        self.assertEqual(
            {f.name for f in fields(DocumentReading)},
            {
                "document",
                "batch",
                "outcome",
                "currency",
                "institution",
                "balancing",
                "delta_magnitude",
                "delta_signed",
                "unmapped",
                "signs_coherent",
                "unreadable_reason",
            },
        )

    def test_a_reading_cannot_be_edited_after_the_fact(self):
        reading = classify(
            beginning_balance=100.0,
            ending_balance=120.0,
            deposits=50.0,
            withdrawals=30.0,
        )
        with self.assertRaises(FrozenInstanceError):
            reading.outcome = CorpusOutcome.magnitude  # type: ignore[misc]

    def test_a_report_cannot_be_edited_after_the_fact(self):
        report = survey([])
        with self.assertRaises(FrozenInstanceError):
            report.readings = ()  # type: ignore[misc]

    def test_transaction_rows_never_reach_a_reading(self):
        """The extractor emits them; nothing here reads or retains them."""
        payload = {
            "bank": "Placeholder Bank",
            "account_holder": "A PERSON",
            "account_number": "0000 0000 0000",
            "transactions": [{"description_raw": "a description"}],
            "header_totals": {
                "beginning_balance": 100.0,
                "ending_balance": 120.0,
                "deposits": 50.0,
                "withdrawals": 30.0,
            },
        }
        reading = read_extraction(
            payload, document="DOC-1", batch="b1", currency=USD
        )
        rendered = survey([reading]).render()
        for leaked in ("A PERSON", "0000", "a description"):
            self.assertNotIn(leaked, rendered)


# ---------------------------------------------------------------------------
# The measurements, which need the evidence
# ---------------------------------------------------------------------------

CORPUS_ROOT = Path(__file__).resolve().parents[2] / "bundle" / "extraction-json"


@dataclass(frozen=True)
class CorpusExpectation:
    """The ET-Fraud corpus as measured, batches 2026-04-11 to 2026-04-18.

    Every number here is quoted somewhere a reader will believe it: in
    :class:`~postgres.models.enums.TotalsConvention`, in the statement-totals
    module docstring, and in the two notes under ``docs/financial-forensics``.
    They are gathered in one object so that a change to any of them is a
    reviewable diff against a named expectation rather than an edited constant
    in an assertion, and so that a change made here without a corresponding
    change to the prose is visible.

    A number that moves is not necessarily wrong.  It does need a reason.
    """

    files: int = 326
    documents: int = 307
    re_extracted: int = 19
    testable: int = 197
    magnitude: int = 182
    signed: int = 2
    ambiguous: int = 1
    unexplained: int = 12
    not_testable: int = 129
    unreadable: int = 0
    disagreements: int = 6


EXPECTED = CorpusExpectation()

#: Named individually because there are few enough to name, and because a
#: count alone would not catch one document swapping places with another.
EXPECTED_SIGNED = ("USA-ET-006751", "USA-ET-035622")
EXPECTED_AMBIGUOUS = ("USA-ET-004306",)


@unittest.skipUnless(
    CORPUS_ROOT.is_dir(),
    f"the ET-Fraud corpus is not present at {CORPUS_ROOT}; it is case "
    "material and is not committed",
)
class TheEtFraudCorpus(unittest.TestCase):
    """What the reader actually sees, on the documents the claims came from."""

    report: CorpusReport

    @classmethod
    def setUpClass(cls):
        cls.report = load_corpus(CORPUS_ROOT, currency=USD)

    def test_the_corpus_is_the_size_the_documentation_says(self):
        self.assertEqual(self.report.file_count, EXPECTED.files)
        self.assertEqual(self.report.document_count, EXPECTED.documents)
        self.assertEqual(len(self.report.re_extracted), EXPECTED.re_extracted)

    def test_the_outcome_census_matches(self):
        counts = self.report.counts()
        self.assertEqual(counts[CorpusOutcome.magnitude], EXPECTED.magnitude)
        self.assertEqual(counts[CorpusOutcome.signed], EXPECTED.signed)
        self.assertEqual(counts[CorpusOutcome.ambiguous], EXPECTED.ambiguous)
        self.assertEqual(counts[CorpusOutcome.unexplained], EXPECTED.unexplained)
        self.assertEqual(counts[CorpusOutcome.not_testable], EXPECTED.not_testable)
        self.assertEqual(counts[CorpusOutcome.unreadable], EXPECTED.unreadable)

    def test_the_census_partitions_the_corpus(self):
        self.assertEqual(sum(self.report.counts().values()), EXPECTED.files)
        self.assertEqual(
            EXPECTED.magnitude
            + EXPECTED.signed
            + EXPECTED.ambiguous
            + EXPECTED.unexplained,
            EXPECTED.testable,
        )
        self.assertEqual(self.report.testable_count, EXPECTED.testable)

    def test_no_control_block_in_the_corpus_is_unreadable(self):
        """Stated as an assertion because the first one should be news."""
        unreadable = self.report.documents_with(CorpusOutcome.unreadable)
        self.assertEqual(unreadable, ())

    def test_the_two_signed_documents_are_the_two_that_were_measured(self):
        self.assertEqual(
            self.report.documents_with(CorpusOutcome.signed), EXPECTED_SIGNED
        )

    def test_the_signed_pair_miss_hugely_under_the_other_dialect(self):
        """The reason a hard-coded dialect would rank them worst, not best."""
        for document in EXPECTED_SIGNED:
            for reading in self.report.readings_for(document):
                self.assertEqual(reading.delta_signed, usd("0.00"))
                assert reading.delta_magnitude is not None
                self.assertGreater(
                    abs(reading.delta_magnitude), usd("270000.00")
                )

    def test_the_one_ambiguous_document_is_the_one_that_was_measured(self):
        self.assertEqual(
            self.report.documents_with(CorpusOutcome.ambiguous), EXPECTED_AMBIGUOUS
        )

    def test_every_failing_document_has_a_verdict(self):
        failing = set(self.report.documents_with(CorpusOutcome.unexplained))
        adjudicated = {a.document for a in ALL_ADJUDICATIONS}
        self.assertEqual(
            failing,
            adjudicated,
            "the set of documents whose identity does not close has moved "
            "away from the set that has verdicts; either a reader fix has "
            "left a verdict stale, or a regression has left a failure "
            "unexplained",
        )

    def test_every_verdict_records_the_residual_the_corpus_produces(self):
        """Catches the set staying right while a number inside it goes stale."""
        by_document: dict[str, Adjudication] = {
            a.document: a for a in ALL_ADJUDICATIONS
        }
        for document, verdict in sorted(by_document.items()):
            readings = self.report.readings_for(document)
            self.assertTrue(readings, f"{document} is not in the corpus")
            for reading in readings:
                self.assertIs(
                    reading.outcome,
                    CorpusOutcome.unexplained,
                    f"{document} has a verdict but its identity now closes",
                )
                self.assertEqual(
                    reading.residual,
                    verdict.residual,
                    f"{document}: the verdict records a residual of "
                    f"{verdict.residual.format()} and the corpus produces "
                    f"{reading.residual.format() if reading.residual else '—'}",
                )

    def test_re_extraction_lost_identities_and_gained_none(self):
        """The finding in ``re-extraction-regression-2026-04.md``, standing."""
        disagreements = self.report.disagreements()
        self.assertEqual(len(disagreements), EXPECTED.disagreements)
        for item in disagreements:
            self.assertTrue(
                item.lost_a_testable_identity,
                f"{item.document} disagrees across batches without losing a "
                "testable identity, which is a different defect from the one "
                "that was measured",
            )

    def test_no_control_block_field_is_unmapped_on_a_failing_document(self):
        """An unrecognised outflow name would present as a missing outflow.

        The failing documents are where that would matter most and be hardest
        to see, since the identity is already not closing for a reason that has
        been written down.
        """
        for document in self.report.documents_with(CorpusOutcome.unexplained):
            for reading in self.report.readings_for(document):
                suspicious = [
                    field
                    for field in reading.unmapped
                    if any(
                        token in field.lower()
                        for token in ("deposit", "withdraw", "debit", "credit",
                                      "balance", "check", "fee")
                    )
                ]
                self.assertEqual(
                    suspicious,
                    [],
                    f"{document} carries control-block field(s) {suspicious} "
                    "that look like flows or balances and that no role claims",
                )

    def test_the_report_renders(self):
        rendered = self.report.render()
        self.assertIn(f"extractions:  {EXPECTED.files}", rendered)
        self.assertIn("Unexplained", rendered)
        self.assertIn("Re-extraction disagreements", rendered)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
