"""Tests for recorded verdicts on failing balance identities.

Two things are under test and they are different in kind.

The first is the module's rules: that a verdict must pay the arithmetic debt
its alleged mechanism implies, that it cannot cite a corroborating document
under a grade that does not rest on one, and that it cannot be recorded
without a reason.  Those tests are ordinary unit tests and most of them assert
that something is *refused*.

The second is the twelve verdicts themselves.  The ET-Fraud corpus contains
twelve documents whose printed control block does not close under either
dialect, and every one of them is explained below.  Those records are asserted
here as data because the corpus is not in the repository — it is case
material and stays out — so the tests cannot re-read the documents.  What they
can do, and what makes this more than a transcription, is check that each
verdict is *arithmetically obliged*: that the residual really is twice the
printed opening, or that the named rows really do sum to the shortfall.  A
figure mistyped when these records were written breaks a test.

The records carry document identifiers and amounts and nothing else.  No
account numbers, no account holders, no transaction descriptions.  The
narrative detail that justifies each verdict lives in
``docs/financial-forensics/unexplained-identities-2026-04.md``, which is where
a person reads it; here the reasons are stated in the terms a checker needs.

The split between the two failure classes is not a judgement call.  Ten of the
twelve print flow totals that disagree with the sum of their own extracted
rows, so those totals came off the page and a failing identity implicates a
balance.  The remaining two print flow totals equal to their row sums to the
cent, so the header was computed from the rows and carries no independent
information; there the rows are what can be wrong.  That test was run before
these verdicts were written.
"""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError, fields
from decimal import Decimal

from services.financial.adjudication import (
    Adjudication,
    AdjudicationError,
    BalanceFailure,
    Corroboration,
    MalformedVerdictError,
    UnpaidObligationError,
    restatement_delta,
)
from services.financial.money import Money

USD = "USD"


def usd(text: str) -> Money:
    return Money.from_decimal(Decimal(text), USD)


def _sign_dropped(
    document: str,
    printed_opening: str,
    residual: str,
    corroboration: Corroboration,
    reason: str,
    corroborating_document: str | None = None,
) -> Adjudication:
    return Adjudication(
        document=document,
        failure=BalanceFailure.opening_sign_dropped,
        residual=usd(residual),
        corroboration=corroboration,
        reason=reason,
        printed_opening=usd(printed_opening),
        corroborating_document=corroborating_document,
    )


# ---------------------------------------------------------------------------
# The twelve
# ---------------------------------------------------------------------------

# Seven statements, extracted into ten files: three of them were extracted
# twice and both copies carry the same defect, which is itself the point of
# the re-extraction finding recorded separately.  Each is a Bank of America
# statement on an overdrawn account, where the reader recorded the opening
# balance as a positive number.  In every case the preceding statement, where
# the corpus has one, prints the same figure as a negative closing balance —
# and negative *closing* balances are captured correctly throughout the
# corpus, which is what localises the defect to the opening-balance line.

OPENING_SIGN_DROPPED: tuple[Adjudication, ...] = (
    _sign_dropped(
        "USA-ET-002551",
        printed_opening="1049.57",
        residual="2099.14",
        corroboration=Corroboration.adjacent_statement,
        corroborating_document="USA-ET-002543",
        reason=(
            "The preceding statement on the same account closes the contiguous "
            "period at -1049.57 and its own identity closes exactly."
        ),
    ),
    _sign_dropped(
        "USA-ET-002557",
        printed_opening="1049.57",
        residual="2099.14",
        corroboration=Corroboration.adjacent_statement,
        corroborating_document="USA-ET-002543",
        reason=(
            "Second extraction of the statement adjudicated as USA-ET-002551, "
            "carrying the identical defect and the same corroboration."
        ),
    ),
    _sign_dropped(
        "USA-ET-002659",
        printed_opening="4.68",
        residual="9.36",
        corroboration=Corroboration.adjacent_statement,
        corroborating_document="USA-ET-002649",
        reason=(
            "The preceding statement closes the contiguous period at -4.68 and "
            "its own identity closes exactly."
        ),
    ),
    _sign_dropped(
        "USA-ET-002665",
        printed_opening="4.68",
        residual="9.36",
        corroboration=Corroboration.adjacent_statement,
        corroborating_document="USA-ET-002649",
        reason=(
            "Second extraction of the statement adjudicated as USA-ET-002659, "
            "carrying the identical defect and the same corroboration."
        ),
    ),
    _sign_dropped(
        "USA-ET-002689",
        printed_opening="3.68",
        residual="7.36",
        corroboration=Corroboration.adjacent_statement,
        corroborating_document="USA-ET-002671",
        reason=(
            "The preceding statement closes the contiguous period at -3.68 and "
            "its own identity closes exactly."
        ),
    ),
    _sign_dropped(
        "USA-ET-002713",
        printed_opening="2.14",
        residual="4.28",
        corroboration=Corroboration.adjacent_statement,
        corroborating_document="USA-ET-002701",
        reason=(
            "The preceding statement closes the contiguous period at -2.14 and "
            "its own identity closes exactly. This document's own closing balance "
            "of -10.91 is captured with its sign intact, which is why the defect "
            "is read as specific to the opening line rather than to the reader's "
            "handling of negatives generally."
        ),
    ),
    _sign_dropped(
        "USA-ET-002719",
        printed_opening="10.91",
        residual="21.82",
        corroboration=Corroboration.chained_statement,
        corroborating_document="USA-ET-002713",
        reason=(
            "The preceding statement closes the contiguous period at -10.91, but "
            "that statement is USA-ET-002713, adjudicated above rather than closing "
            "on its own arithmetic. The corroboration is real and it is dependent: "
            "overturning the earlier verdict removes the support for this one. Its "
            "own arithmetic obligation is met independently."
        ),
    ),
    _sign_dropped(
        "USA-ET-046337",
        printed_opening="213.91",
        residual="427.82",
        corroboration=Corroboration.adjacent_statement,
        corroborating_document="USA-ET-046327",
        reason=(
            "The preceding statement closes the contiguous period at -213.91 and "
            "its own identity closes exactly."
        ),
    ),
    _sign_dropped(
        "USA-ET-001291",
        printed_opening="12.00",
        residual="24.00",
        corroboration=Corroboration.arithmetic_only,
        reason=(
            "No preceding statement is in the corpus: the nearest earlier one on "
            "this account ends over four weeks before this period begins, so a "
            "statement is missing rather than merely unhelpful. The verdict rests "
            "on the residual being exactly twice the printed opening and on no "
            "other single sign flip closing the identity. The closing balance is "
            "corroborated forward by the following statement, which opens at the "
            "same figure; the opening balance is not corroborated at all."
        ),
    ),
    _sign_dropped(
        "USA-ET-001299",
        printed_opening="12.00",
        residual="24.00",
        corroboration=Corroboration.arithmetic_only,
        reason=(
            "Second extraction of the statement adjudicated as USA-ET-001291, "
            "carrying the identical defect and the same uncorroborated standing."
        ),
    ),
)


# Two Capital One statements whose header flow totals equal the sum of their
# own extracted rows to the cent.  The header was therefore computed from the
# rows and cannot corroborate them, so a failing identity implicates the rows.
# In both, the text of a transaction that was never recorded survives at the
# start of a neighbouring row -- the reader consumed a page boundary and
# swallowed what followed.  Every row in both documents is recorded at high
# confidence, including the ones that swallowed transactions.

ROWS_LOST: tuple[Adjudication, ...] = (
    Adjudication(
        document="USA-ET-004539",
        failure=BalanceFailure.rows_lost_in_extraction,
        residual=usd("20.00"),
        corroboration=Corroboration.same_document,
        reason=(
            "Row 62's description begins with the stranded tail of a debit -- an "
            "amount of $20.00 and a running balance of $45.26 -- followed by page "
            "furniture and then the transaction the row actually records. The "
            "debit itself was never emitted as a row. Note that the residual alone "
            "cannot distinguish a lost $20.00 debit from an invented $20.00 "
            "credit; the text is what settles it."
        ),
        missing_outflows=(usd("20.00"),),
    ),
    Adjudication(
        document="USA-ET-004573",
        failure=BalanceFailure.rows_lost_in_extraction,
        residual=usd("113.29"),
        corroboration=Corroboration.same_document,
        reason=(
            "Two losses. Row 18 strands the tail of a $13.29 debit with a running "
            "balance of $408.16. Row 52's description swallows three further "
            "transactions -- debits of $100.00 and $50.00 and a credit of $50.00, "
            "a net outflow of $100.00 -- none of which were emitted as rows. The "
            "running balances quoted inside that description are internally "
            "consistent with each other, which corroborates the reading without "
            "reference to any other document."
        ),
        missing_outflows=(usd("13.29"), usd("100.00")),
    ),
)


ALL_ADJUDICATIONS: tuple[Adjudication, ...] = OPENING_SIGN_DROPPED + ROWS_LOST


class TheTwelveDocuments(unittest.TestCase):
    """The corpus verdicts, checked as claims rather than read as labels."""

    def test_every_unexplained_document_is_adjudicated(self) -> None:
        """Twelve documents failed; twelve verdicts exist, one each.

        The count is asserted because the alternative -- adjudicating the easy
        ones and leaving the rest as a residue -- is exactly what a report
        should not be able to do quietly.
        """
        self.assertEqual(len(ALL_ADJUDICATIONS), 12)
        documents = [a.document for a in ALL_ADJUDICATIONS]
        self.assertEqual(len(set(documents)), 12, "a document is adjudicated twice")

    def test_construction_proves_each_obligation(self) -> None:
        """Every record above was validated when this module imported.

        The obligations are enforced in ``__post_init__``, so the records
        existing at all is the assertion.  This test restates it explicitly so
        that the guarantee is visible to someone reading the tests rather than
        implicit in the import succeeding.
        """
        for adjudication in ALL_ADJUDICATIONS:
            with self.subTest(document=adjudication.document):
                self.assertFalse(adjudication.residual.is_zero)
                self.assertTrue(adjudication.reason.strip())

    def test_dropped_signs_miss_by_exactly_twice_the_opening(self) -> None:
        """The arithmetic that makes the verdict falsifiable, stated directly."""
        for adjudication in OPENING_SIGN_DROPPED:
            with self.subTest(document=adjudication.document):
                opening = adjudication.printed_opening
                assert opening is not None
                self.assertEqual(adjudication.residual, opening * 2)
                self.assertTrue(opening.is_positive)

    def test_dropped_signs_restate_to_an_overdrawn_opening(self) -> None:
        """The correction is a negative opening balance, which is the claim.

        An account that was overdrawn at the start of the period is the whole
        substance of this verdict class.  If the restatement came out positive
        the mechanism would be incoherent.
        """
        for adjudication in OPENING_SIGN_DROPPED:
            with self.subTest(document=adjudication.document):
                restated = adjudication.restated_opening
                assert restated is not None
                self.assertTrue(restated.is_negative)
                self.assertEqual(abs(restated), adjudication.printed_opening)

    def test_lost_rows_account_for_the_whole_shortfall(self) -> None:
        """Named amounts sum to the residual exactly, not approximately."""
        for adjudication in ROWS_LOST:
            with self.subTest(document=adjudication.document):
                total = sum(
                    (a for a in adjudication.missing_outflows),
                    Money.zero(USD),
                )
                self.assertEqual(total, adjudication.residual)

    def test_the_one_chained_verdict_cites_an_adjudicated_document(self) -> None:
        """USA-ET-002719 depends on USA-ET-002713, and that is recorded as such.

        This is the test that stops a chain of dependent verdicts being
        presented as independent corroboration.  If someone regrades this to
        ``adjacent_statement`` -- which is the tempting simplification,
        because the corroborating statement does print the figure -- the test
        fails, because the cited document is one of the twelve.
        """
        adjudicated = {a.document for a in ALL_ADJUDICATIONS}
        chained = [
            a
            for a in ALL_ADJUDICATIONS
            if a.corroboration is Corroboration.chained_statement
        ]
        self.assertEqual([a.document for a in chained], ["USA-ET-002719"])
        self.assertEqual(chained[0].corroborating_document, "USA-ET-002713")
        self.assertIn(chained[0].corroborating_document, adjudicated)

        for adjudication in ALL_ADJUDICATIONS:
            if adjudication.corroboration is Corroboration.adjacent_statement:
                with self.subTest(document=adjudication.document):
                    self.assertNotIn(
                        adjudication.corroborating_document,
                        adjudicated,
                        "an adjacent-statement corroborator must not itself be "
                        "adjudicated; that is what chained_statement is for",
                    )

    def test_the_uncorroborated_verdicts_are_marked_as_such(self) -> None:
        """Two records rest on arithmetic alone and say so.

        Both are extractions of the same statement, whose predecessor is
        missing from the corpus.  A report that presented these alongside the
        adjacent-statement verdicts without distinction would overstate them.
        """
        uncorroborated = [
            a.document for a in ALL_ADJUDICATIONS if not a.is_independently_corroborated
        ]
        self.assertEqual(uncorroborated, ["USA-ET-001291", "USA-ET-001299"])

    def test_the_correction_equals_the_shortfall_in_every_case(self) -> None:
        """Whatever the mechanism, restating closes the identity exactly.

        This holds by construction rather than by luck, and asserting it
        across both failure classes is what makes the two obligations
        comparable: each verdict's correction is precisely the amount by which
        its document missed.
        """
        for adjudication in ALL_ADJUDICATIONS:
            with self.subTest(document=adjudication.document):
                self.assertEqual(
                    restatement_delta(adjudication), adjudication.residual
                )


class ObligationsAreEnforced(unittest.TestCase):
    """A verdict that does not pay its debt cannot be constructed."""

    def test_a_dropped_sign_that_does_not_double_is_refused(self) -> None:
        """The single check that makes the class falsifiable.

        Off by a cent is still refused: a mechanism that predicts an exact
        figure is not evidence for anything if near enough counts.
        """
        with self.assertRaises(UnpaidObligationError):
            _sign_dropped(
                "USA-ET-000000",
                printed_opening="10.00",
                residual="20.01",
                corroboration=Corroboration.arithmetic_only,
                reason="off by a cent",
            )

    def test_named_rows_must_sum_to_the_residual(self) -> None:
        with self.assertRaises(UnpaidObligationError):
            Adjudication(
                document="USA-ET-000000",
                failure=BalanceFailure.rows_lost_in_extraction,
                residual=usd("113.29"),
                corroboration=Corroboration.same_document,
                reason="approximately right is not right",
                missing_outflows=(usd("13.29"), usd("99.00")),
            )

    def test_lost_rows_must_be_named(self) -> None:
        """'Some rows are missing' explains every failing document equally."""
        with self.assertRaises(MalformedVerdictError):
            Adjudication(
                document="USA-ET-000000",
                failure=BalanceFailure.rows_lost_in_extraction,
                residual=usd("113.29"),
                corroboration=Corroboration.same_document,
                reason="extraction error",
            )

    def test_a_dropped_sign_needs_the_printed_opening(self) -> None:
        with self.assertRaises(MalformedVerdictError):
            Adjudication(
                document="USA-ET-000000",
                failure=BalanceFailure.opening_sign_dropped,
                residual=usd("24.00"),
                corroboration=Corroboration.arithmetic_only,
                reason="no figure to check against",
            )

    def test_an_already_negative_opening_has_no_dropped_sign(self) -> None:
        """The allegation is incoherent if the figure carries its sign."""
        with self.assertRaises(MalformedVerdictError):
            _sign_dropped(
                "USA-ET-000000",
                printed_opening="-12.00",
                residual="-24.00",
                corroboration=Corroboration.arithmetic_only,
                reason="the sign is right there",
            )

    def test_the_two_mechanisms_cannot_be_alleged_together(self) -> None:
        """One verdict, one mechanism, one debt.

        A record claiming both would satisfy neither obligation cleanly and
        would be unfalsifiable in the familiar way: whatever the residual, some
        combination of a sign and some rows explains it.
        """
        with self.assertRaises(MalformedVerdictError):
            Adjudication(
                document="USA-ET-000000",
                failure=BalanceFailure.opening_sign_dropped,
                residual=usd("24.00"),
                corroboration=Corroboration.arithmetic_only,
                reason="both at once",
                printed_opening=usd("12.00"),
                missing_outflows=(usd("5.00"),),
            )

    def test_lost_rows_make_no_claim_about_the_opening(self) -> None:
        with self.assertRaises(MalformedVerdictError):
            Adjudication(
                document="USA-ET-000000",
                failure=BalanceFailure.rows_lost_in_extraction,
                residual=usd("20.00"),
                corroboration=Corroboration.same_document,
                reason="irrelevant figure recorded",
                printed_opening=usd("42.46"),
                missing_outflows=(usd("20.00"),),
            )

    def test_missing_outflows_are_magnitudes(self) -> None:
        """Direction is carried by the field name, not by a sign.

        Allowing negatives here would let a set of amounts sum to the residual
        while containing entries that mean the opposite of what the field
        says, which defeats the check.
        """
        with self.assertRaises(MalformedVerdictError):
            Adjudication(
                document="USA-ET-000000",
                failure=BalanceFailure.rows_lost_in_extraction,
                residual=usd("20.00"),
                corroboration=Corroboration.same_document,
                reason="signed magnitudes",
                missing_outflows=(usd("40.00"), usd("-20.00")),
            )

    def test_a_closing_identity_is_not_adjudicable(self) -> None:
        """There is nothing to explain, and a verdict would imply there was."""
        with self.assertRaises(MalformedVerdictError):
            _sign_dropped(
                "USA-ET-000000",
                printed_opening="0.00",
                residual="0.00",
                corroboration=Corroboration.arithmetic_only,
                reason="nothing wrong here",
            )

    def test_a_verdict_requires_a_reason(self) -> None:
        for blank in ("", "   "):
            with self.subTest(reason=repr(blank)):
                with self.assertRaises(MalformedVerdictError):
                    _sign_dropped(
                        "USA-ET-000000",
                        printed_opening="12.00",
                        residual="24.00",
                        corroboration=Corroboration.arithmetic_only,
                        reason=blank,
                    )

    def test_every_refusal_is_an_adjudication_error(self) -> None:
        """Callers can catch one class and quarantine the record.

        Both refusal types are failures of the same kind from a caller's point
        of view -- this verdict is not admissible -- and the distinction
        between them is for the person reading the message.
        """
        for error in (UnpaidObligationError, MalformedVerdictError):
            with self.subTest(error=error.__name__):
                self.assertTrue(issubclass(error, AdjudicationError))


class CorroborationIsGraded(unittest.TestCase):
    """The grade and the citation cannot disagree."""

    def test_a_citing_grade_must_name_a_document(self) -> None:
        for grade in (Corroboration.adjacent_statement, Corroboration.chained_statement):
            with self.subTest(grade=grade.value):
                with self.assertRaises(MalformedVerdictError):
                    _sign_dropped(
                        "USA-ET-000000",
                        printed_opening="12.00",
                        residual="24.00",
                        corroboration=grade,
                        reason="cites nothing",
                    )

    def test_a_non_citing_grade_must_not_name_one(self) -> None:
        """Otherwise the record reads as corroborated when it is not."""
        for grade in (Corroboration.arithmetic_only, Corroboration.same_document):
            with self.subTest(grade=grade.value):
                with self.assertRaises(MalformedVerdictError):
                    _sign_dropped(
                        "USA-ET-000000",
                        printed_opening="12.00",
                        residual="24.00",
                        corroboration=grade,
                        reason="names a document it does not rely on",
                        corroborating_document="USA-ET-000001",
                    )

    def test_a_document_cannot_corroborate_itself(self) -> None:
        with self.assertRaises(MalformedVerdictError):
            _sign_dropped(
                "USA-ET-000000",
                printed_opening="12.00",
                residual="24.00",
                corroboration=Corroboration.adjacent_statement,
                reason="circular",
                corroborating_document="USA-ET-000000",
            )

    def test_arithmetic_only_is_the_sole_uncorroborated_grade(self) -> None:
        """The property exists so callers need not enumerate the enum.

        If a grade is added later, this test is where the meaning of
        "independently corroborated" has to be decided rather than inherited.
        """
        for grade in Corroboration:
            record = Adjudication(
                document="USA-ET-000000",
                failure=BalanceFailure.opening_sign_dropped,
                residual=usd("24.00"),
                corroboration=grade,
                reason="grade under test",
                printed_opening=usd("12.00"),
                corroborating_document=(
                    "USA-ET-000001"
                    if grade
                    in (
                        Corroboration.adjacent_statement,
                        Corroboration.chained_statement,
                    )
                    else None
                ),
            )
            with self.subTest(grade=grade.value):
                self.assertEqual(
                    record.is_independently_corroborated,
                    grade is not Corroboration.arithmetic_only,
                )


class RecordsAreImmutableAndCarryNoCaseContent(unittest.TestCase):
    """What the verdicts may hold, and what they may not."""

    def test_a_recorded_verdict_cannot_be_edited(self) -> None:
        """Changing a verdict means recording a new one, which leaves a trace."""
        record = OPENING_SIGN_DROPPED[0]
        with self.assertRaises(FrozenInstanceError):
            record.residual = usd("1.00")  # type: ignore[misc]

    def test_restated_opening_is_absent_for_other_mechanisms(self) -> None:
        """It is a claim about the opening balance, so classes that make no
        such claim return nothing rather than something plausible."""
        for adjudication in ROWS_LOST:
            with self.subTest(document=adjudication.document):
                self.assertIsNone(adjudication.restated_opening)

    def test_the_record_has_nowhere_to_put_case_content(self) -> None:
        """The corpus is case material and is not in this repository.

        These records exist so the reasoning survives without the documents,
        which means they must not become the place the documents' contents
        leak into version control.  Prose cannot be policed by a test, but the
        shape of the record can: there is no field for an account number, an
        account holder, a counterparty or a transaction description, and
        adding one fails here.  A reviewer then has to argue for it rather
        than slip it in.
        """
        self.assertEqual(
            {f.name for f in fields(Adjudication)},
            {
                "document",
                "failure",
                "residual",
                "corroboration",
                "reason",
                "printed_opening",
                "missing_outflows",
                "corroborating_document",
            },
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
