"""Tests for delta localisation and for setting evidence aside.

The tests are arranged around the one thing that can go badly wrong here.
Quarantining a row removes it from the totals, so quarantining the row whose
amount equals the residual makes the period balance — always, by arithmetic
necessity rather than by luck.  A localiser allowed to act on its own guesses
would therefore launder every failing statement into a clean one.  Most of
what follows exists to prove that cannot happen: that a conjecture is refused
as grounds, that the refusal is by construction rather than by a caller
remembering to check, and that a quarantine which does rescue a period says so.

No case material appears here.  The rows are round numbers with reference ids
like ``R1``, and one test asserts structurally that nothing else can reach the
rendered output.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
import uuid
from dataclasses import FrozenInstanceError, fields
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import (
    ExtractionLayer,
    GlobalRole,
    LedgerStatus,
    ProofClass,
    QuarantineReason,
    ReconciliationStatus,
    TransactionDirection,
)
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.financial import (
    FinancialAccount,
    FinancialIngestionRun,
    FinancialSourceDocument,
    FinancialStatementPeriod,
    FinancialTransaction,
)
from postgres.models.user import User
from services.financial.money import Money
from services.financial.periods import (
    BalanceObservation,
    PeriodBounds,
    StatementPeriodDraft,
    record_statement_period,
)
from services.financial.quarantine import (
    BalanceBreak,
    Candidate,
    CandidateKind,
    Localisation,
    LocalisationError,
    LocalisationStrength,
    QuarantineBasis,
    RescueWarning,
    RowObservation,
    Signature,
    UngroundedQuarantineError,
    localise,
    quarantine_transaction,
    quarantined_row_ids,
    release_transaction,
    would_rescue,
)
from services.financial.reconcile import (
    IdentityOutcome,
    empty_totals,
    reconcile_period,
)
from services.financial.runs import open_ingestion_run

TABLES = [
    User.__table__,
    Case.__table__,
    EvidenceFolder.__table__,
    EvidenceFile.__table__,
    FinancialIngestionRun.__table__,
    FinancialSourceDocument.__table__,
    FinancialAccount.__table__,
    FinancialStatementPeriod.__table__,
    FinancialTransaction.__table__,
]

USD = "USD"
CREDIT = TransactionDirection.credit
DEBIT = TransactionDirection.debit


def usd(text: str) -> Money:
    return Money.from_decimal(Decimal(text), USD)


def row(index, amount, direction=CREDIT, balance=None, page=None):
    return RowObservation(
        ref_id=f"R{index}",
        row_index=index,
        amount=usd(amount),
        direction=direction,
        running_balance=None if balance is None else usd(balance),
        page=page,
    )


def outcome(delta, status=ReconciliationStatus.unbalanced):
    """An IdentityOutcome carrying just the fields quarantine reads."""
    return IdentityOutcome(
        status=status,
        totals=empty_totals(USD),
        opening=usd("1000.00"),
        printed_closing=usd("1000.00"),
        computed_closing=None if delta is None else usd("1000.00") + delta,
        delta=delta,
        independent=True,
        unavailable_reason=None,
    )


class FakeTransaction:
    """The two columns quarantine writes, without a database.

    The functions under test touch ``ledger_status`` and ``quarantine_reason``
    and nothing else, so a stub keeps these tests to the logic.  What a stub
    cannot show is that the pair the service writes is a pair the database
    will accept; ``QuarantineSurvivesTheDatabase`` at the end of this module
    commits the writes for real.
    """

    def __init__(self, status=LedgerStatus.admitted, reason=None, id_=None):
        self.id = id_ or uuid.uuid4()
        self.ledger_status = status.value if hasattr(status, "value") else status
        self.quarantine_reason = reason


# ---------------------------------------------------------------------------


class TheRowObservationRefusesIncoherentRows(unittest.TestCase):
    def test_an_amount_has_to_be_money(self):
        with self.assertRaises(LocalisationError):
            RowObservation(ref_id="R1", row_index=1, amount=25, direction=CREDIT)

    def test_a_negative_amount_is_refused(self):
        """Sign lives in the direction; an amount carrying one is a bug."""
        with self.assertRaises(LocalisationError) as caught:
            RowObservation(
                ref_id="R1", row_index=1, amount=usd("-25.00"), direction=CREDIT
            )
        self.assertIn("direction", str(caught.exception))

    def test_a_direction_has_to_be_the_enum(self):
        with self.assertRaises(LocalisationError):
            RowObservation(
                ref_id="R1", row_index=1, amount=usd("25.00"), direction="credit"
            )

    def test_a_running_balance_in_another_currency_is_refused(self):
        with self.assertRaises(LocalisationError):
            RowObservation(
                ref_id="R1",
                row_index=1,
                amount=usd("25.00"),
                direction=CREDIT,
                running_balance=Money.from_decimal(Decimal("25.00"), "EUR"),
            )

    def test_a_credit_adds_and_a_debit_subtracts(self):
        self.assertEqual(row(1, "25.00", CREDIT).signed, usd("25.00"))
        self.assertEqual(row(1, "25.00", DEBIT).signed, usd("-25.00"))

    def test_rows_are_frozen(self):
        observation = row(1, "25.00")
        with self.assertRaises(FrozenInstanceError):
            observation.row_index = 2


class TheChainWalkProvesWhereItCan(unittest.TestCase):
    """The printed running balance is the only proof-grade signal there is."""

    def test_a_chain_that_holds_produces_no_breaks(self):
        rows = [
            row(1, "100.00", CREDIT, "1100.00"),
            row(2, "25.00", DEBIT, "1075.00"),
        ]
        found = localise(residual=usd("0.00"), rows=rows, opening=usd("1000.00"))
        self.assertEqual(found.breaks, ())
        self.assertIs(found.strength, LocalisationStrength.none)

    def test_a_spurious_row_breaks_the_chain_at_that_row(self):
        """A row the statement's own balances decline to include.

        The chain says the balance did not move at row 2, so the row is not
        part of what the bank recorded, and the identity is over by exactly
        its amount.
        """
        rows = [
            row(1, "100.00", CREDIT, "1100.00"),
            row(2, "50.00", CREDIT, "1100.00"),
            row(3, "25.00", DEBIT, "1075.00"),
        ]
        found = localise(residual=usd("50.00"), rows=rows, opening=usd("1000.00"))
        self.assertEqual(len(found.breaks), 1)
        self.assertEqual(found.breaks[0].row_index, 2)
        self.assertEqual(found.breaks[0].before_ref, "R1")
        self.assertEqual(found.breaks[0].discrepancy, usd("-50.00"))
        self.assertIs(found.strength, LocalisationStrength.proved)

    def test_a_break_that_accounts_for_the_whole_residual_is_proved(self):
        rows = [row(1, "100.00", CREDIT, "1150.00")]
        found = localise(residual=usd("-50.00"), rows=rows, opening=usd("1000.00"))
        self.assertIs(found.strength, LocalisationStrength.proved)
        self.assertTrue(found.is_actionable)

    def test_a_break_that_does_not_account_for_it_is_only_partial(self):
        """Found something; did not find everything.  Not grounds."""
        rows = [row(1, "100.00", CREDIT, "1150.00")]
        found = localise(residual=usd("-90.00"), rows=rows, opening=usd("1000.00"))
        self.assertIs(found.strength, LocalisationStrength.partial)
        self.assertFalse(found.is_actionable)

    def test_rows_without_a_printed_balance_do_not_break_the_chain(self):
        """Statements print a balance on some lines and not others.

        The chain still holds across the gap, because the unbalanced rows are
        carried into the next expectation rather than being treated as breaks.
        """
        rows = [
            row(1, "100.00", CREDIT),
            row(2, "25.00", DEBIT),
            row(3, "10.00", CREDIT, "1085.00"),
        ]
        found = localise(residual=usd("0.00"), rows=rows, opening=usd("1000.00"))
        self.assertEqual(found.breaks, ())
        self.assertEqual(found.rows_with_balance, 1)

    def test_the_chain_can_break_against_the_opening_balance(self):
        rows = [row(1, "100.00", CREDIT, "1200.00")]
        found = localise(residual=usd("-100.00"), rows=rows, opening=usd("1000.00"))
        self.assertEqual(found.breaks[0].before_ref, None)
        self.assertTrue(found.breaks[0].at_opening)
        # The break still names the row it lands on, which is what a reader
        # needs; only the predecessor is absent.
        self.assertEqual(found.breaks[0].after_ref, "R1")

    def test_without_an_opening_the_chain_starts_at_the_first_printed_balance(self):
        rows = [row(1, "100.00", CREDIT, "1100.00"), row(2, "50.00", CREDIT, "1150.00")]
        found = localise(residual=usd("0.00"), rows=rows)
        self.assertEqual(found.breaks, ())


class ACandidateIsNeverACause(unittest.TestCase):
    """Measured against the corpus: a fit is usually a coincidence."""

    def test_a_row_equal_to_the_residual_is_a_candidate_not_a_finding(self):
        found = localise(residual=usd("24.00"), rows=[row(1, "24.00")])
        self.assertIs(found.strength, LocalisationStrength.conjectural)
        self.assertFalse(found.is_actionable)
        self.assertEqual(found.candidates[0].kind, CandidateKind.equals_residual)

    def test_a_row_at_half_the_residual_fits_a_sign_flip(self):
        """Reversing a credit of x moves the net by twice x."""
        found = localise(residual=usd("50.00"), rows=[row(1, "25.00")])
        self.assertEqual(found.candidates[0].kind, CandidateKind.sign_flip)

    def test_competing_candidates_are_all_reported(self):
        """The count is the finding.

        Three rows of $20.00 against a $20.00 residual is the shape of
        USA-ET-004539, where picking one would have been arbitrary.
        """
        rows = [row(1, "20.00"), row(2, "20.00"), row(3, "20.00")]
        found = localise(residual=usd("20.00"), rows=rows)
        self.assertEqual(found.candidate_count, 3)
        self.assertFalse(found.is_actionable)

    def test_a_zero_residual_has_no_candidates(self):
        found = localise(residual=usd("0.00"), rows=[row(1, "20.00")])
        self.assertEqual(found.candidates, ())

    def test_candidates_do_not_downgrade_a_proof(self):
        """A chain break outranks a coincidence that points elsewhere."""
        rows = [
            row(1, "100.00", CREDIT, "1150.00"),
            row(2, "50.00", DEBIT),
        ]
        found = localise(residual=usd("-50.00"), rows=rows, opening=usd("1000.00"))
        self.assertIs(found.strength, LocalisationStrength.proved)
        self.assertTrue(found.candidates)


class SignaturesHintAtAKindOfErrorNotAPlace(unittest.TestCase):
    def test_a_residual_divisible_by_nine_signals_a_transposition(self):
        """The two $9.36 failures in the corpus carry this signature."""
        found = localise(residual=usd("9.36"), rows=[])
        self.assertIn(Signature.transposition, found.signatures)

    def test_a_residual_equal_to_the_opening_says_it_was_never_applied(self):
        found = localise(
            residual=usd("1000.00"), rows=[], opening=usd("1000.00")
        )
        self.assertIn(Signature.opening_omitted, found.signatures)

    def test_a_residual_of_twice_the_opening_says_its_sign_was_flipped(self):
        found = localise(
            residual=usd("2000.00"), rows=[], opening=usd("1000.00")
        )
        self.assertIn(Signature.opening_sign_flipped, found.signatures)

    def test_a_signature_alone_does_not_make_a_localisation(self):
        found = localise(residual=usd("9.36"), rows=[])
        self.assertIs(found.strength, LocalisationStrength.none)
        self.assertFalse(found.is_actionable)


class LocalisationRefusesIncoherentInput(unittest.TestCase):
    def test_a_residual_has_to_be_money(self):
        with self.assertRaises(LocalisationError):
            localise(residual=24, rows=[])

    def test_a_row_in_another_currency_is_refused(self):
        eur = RowObservation(
            ref_id="R1",
            row_index=1,
            amount=Money.from_decimal(Decimal("24.00"), "EUR"),
            direction=CREDIT,
        )
        with self.assertRaises(LocalisationError) as caught:
            localise(residual=usd("24.00"), rows=[eur])
        self.assertIn("two currencies", str(caught.exception))

    def test_an_opening_in_another_currency_is_refused(self):
        with self.assertRaises(LocalisationError):
            localise(
                residual=usd("24.00"),
                rows=[],
                opening=Money.from_decimal(Decimal("1.00"), "EUR"),
            )


class UnlocalisedIsAResultNotAnError(unittest.TestCase):
    """Nine of the twelve real failures land here."""

    def test_nothing_found_returns_a_report_rather_than_raising(self):
        found = localise(residual=usd("2099.14"), rows=[row(1, "13.00")])
        self.assertIs(found.strength, LocalisationStrength.none)
        self.assertEqual(found.breaks, ())
        self.assertEqual(found.candidates, ())

    def test_an_absent_chain_is_reported_as_absent(self):
        """Not one of the corpus's 30,570 rows prints a balance."""
        found = localise(residual=usd("24.00"), rows=[row(1, "13.00")])
        self.assertFalse(found.chain_was_available)
        self.assertIn("no running balance was printed", found.render())

    def test_a_walked_chain_is_reported_as_available(self):
        found = localise(
            residual=usd("0.00"), rows=[row(1, "13.00", CREDIT, "1013.00")]
        )
        self.assertTrue(found.chain_was_available)


class GroundsCannotBeAConjecture(unittest.TestCase):
    """The guarantee the module exists for."""

    def _conjectural(self):
        return localise(residual=usd("24.00"), rows=[row(1, "24.00")])

    def test_a_conjecture_is_refused_as_grounds(self):
        with self.assertRaises(UngroundedQuarantineError) as caught:
            QuarantineBasis.from_proof(self._conjectural())
        self.assertIn("would make the period balance", str(caught.exception))

    def test_an_empty_localisation_is_refused_as_grounds(self):
        with self.assertRaises(UngroundedQuarantineError):
            QuarantineBasis.from_proof(localise(residual=usd("24.00"), rows=[]))

    def test_a_partial_localisation_is_refused_as_grounds(self):
        partial = localise(
            residual=usd("-90.00"),
            rows=[row(1, "100.00", CREDIT, "1150.00")],
            opening=usd("1000.00"),
        )
        self.assertIs(partial.strength, LocalisationStrength.partial)
        with self.assertRaises(UngroundedQuarantineError):
            QuarantineBasis.from_proof(partial)

    def test_a_proof_is_accepted_and_names_the_row(self):
        proved = localise(
            residual=usd("-50.00"),
            rows=[row(1, "100.00", CREDIT, "1150.00")],
            opening=usd("1000.00"),
        )
        basis = QuarantineBasis.from_proof(proved)
        self.assertIs(basis.reason, QuarantineReason.balance_break)
        self.assertIn("row 1", basis.detail)

    def test_grounds_have_to_be_a_localisation(self):
        with self.assertRaises(UngroundedQuarantineError):
            QuarantineBasis.from_proof("the row looked wrong")

    def test_there_is_no_constructor_taking_a_candidate(self):
        """Structural: the omission is the design, so assert it stays.

        A future constructor that accepted a candidate would reintroduce the
        laundering path without failing any behavioural test above.
        """
        constructors = {
            name
            for name in vars(QuarantineBasis)
            if not name.startswith("_")
            and isinstance(vars(QuarantineBasis)[name], classmethod)
        }
        self.assertEqual(
            constructors,
            {
                "from_proof",
                "from_adjudication",
                "unreadable_row",
                "currency_mismatch",
                "unexplained_delta",
            },
        )


class GroundsFromAPerson(unittest.TestCase):
    def test_an_adjudication_records_who_and_why(self):
        basis = QuarantineBasis.from_adjudication(
            actor="n.byrne", reason="duplicate page in the source scan"
        )
        self.assertIs(basis.reason, QuarantineReason.adjudicated)
        self.assertIn("n.byrne", basis.detail)
        self.assertIn("duplicate page", basis.detail)

    def test_an_adjudication_without_an_actor_is_refused(self):
        with self.assertRaises(UngroundedQuarantineError):
            QuarantineBasis.from_adjudication(actor="  ", reason="looked wrong")

    def test_an_adjudication_without_a_reason_is_refused(self):
        with self.assertRaises(UngroundedQuarantineError):
            QuarantineBasis.from_adjudication(actor="n.byrne", reason="")

    def test_a_basis_always_carries_a_detail(self):
        with self.assertRaises(UngroundedQuarantineError):
            QuarantineBasis(reason=QuarantineReason.balance_break, detail="   ")

    def test_a_reason_outside_the_vocabulary_is_refused(self):
        with self.assertRaises(UngroundedQuarantineError):
            QuarantineBasis(reason="seemed_off", detail="a detail")


class ADocumentLevelDeltaIsGroundsOnlyWhenItFails(unittest.TestCase):
    def test_an_unbalanced_identity_is_grounds(self):
        basis = QuarantineBasis.unexplained_delta(outcome(usd("24.00")))
        self.assertIs(basis.reason, QuarantineReason.unexplained_delta)
        self.assertIn("24.00", basis.detail)

    def test_an_unavailable_identity_is_not_grounds(self):
        """A statement that printed no control total is not defective.

        129 of the corpus's documents are untestable.  Quarantining them would
        discard most of a typical disclosure on the basis that the bank chose
        not to print a summary box.
        """
        with self.assertRaises(UngroundedQuarantineError) as caught:
            QuarantineBasis.unexplained_delta(
                outcome(None, ReconciliationStatus.unavailable)
            )
        self.assertIn("fact about the statement", str(caught.exception))

    def test_a_balanced_identity_is_not_grounds(self):
        with self.assertRaises(UngroundedQuarantineError):
            QuarantineBasis.unexplained_delta(
                outcome(usd("0.00"), ReconciliationStatus.balanced)
            )


class QuarantiningARow(unittest.TestCase):
    def setUp(self):
        self.basis = QuarantineBasis.unreadable_row("amount column was cut off")

    def test_a_row_is_set_aside_with_its_grounds_recorded(self):
        txn = FakeTransaction()
        quarantine_transaction(txn, self.basis)
        self.assertEqual(txn.ledger_status, LedgerStatus.quarantined.value)
        self.assertEqual(
            txn.quarantine_reason, QuarantineReason.unreadable_row.value
        )

    def test_a_bare_string_is_not_grounds(self):
        with self.assertRaises(UngroundedQuarantineError) as caught:
            quarantine_transaction(FakeTransaction(), "it looked wrong")
        self.assertIn("not grounds", str(caught.exception))

    def test_requarantining_on_the_same_grounds_is_idempotent(self):
        txn = FakeTransaction(
            LedgerStatus.quarantined, QuarantineReason.unreadable_row.value
        )
        quarantine_transaction(txn, self.basis)
        self.assertEqual(
            txn.quarantine_reason, QuarantineReason.unreadable_row.value
        )

    def test_requarantining_on_different_grounds_is_refused(self):
        """The ledger appends; overwriting a reason erases a decision."""
        txn = FakeTransaction(
            LedgerStatus.quarantined, QuarantineReason.adjudicated.value
        )
        with self.assertRaises(UngroundedQuarantineError) as caught:
            quarantine_transaction(txn, self.basis)
        self.assertIn("erase the earlier decision", str(caught.exception))

    def test_a_superseded_row_is_not_quarantined_over(self):
        txn = FakeTransaction(LedgerStatus.superseded)
        with self.assertRaises(UngroundedQuarantineError):
            quarantine_transaction(txn, self.basis)

    def test_a_currency_mismatch_states_both_currencies(self):
        basis = QuarantineBasis.currency_mismatch(
            row_currency="EUR", period_currency="USD"
        )
        self.assertIn("EUR", basis.detail)
        self.assertIn("USD", basis.detail)


class ReleasingARow(unittest.TestCase):
    def test_a_release_clears_the_status_and_the_reason(self):
        txn = FakeTransaction(
            LedgerStatus.quarantined, QuarantineReason.unreadable_row.value
        )
        release_transaction(txn, actor="n.byrne", reason="rescanned at 600dpi")
        self.assertEqual(txn.ledger_status, LedgerStatus.admitted.value)
        self.assertIsNone(txn.quarantine_reason)

    def test_releasing_an_admitted_row_is_refused(self):
        with self.assertRaises(UngroundedQuarantineError):
            release_transaction(FakeTransaction(), actor="n", reason="r")

    def test_a_release_has_to_name_who_and_why(self):
        txn = FakeTransaction(LedgerStatus.quarantined, "unreadable_row")
        with self.assertRaises(UngroundedQuarantineError):
            release_transaction(txn, actor="n.byrne", reason="  ")


class ARescueIsVisible(unittest.TestCase):
    """A balance reached by subtraction has to say so."""

    def test_removing_rows_that_close_the_gap_is_reported(self):
        warning = would_rescue(
            outcome=outcome(usd("50.00")), rows=[row(1, "50.00", CREDIT)]
        )
        self.assertIsInstance(warning, RescueWarning)
        self.assertTrue(warning.would_balance)

    def test_removing_rows_that_do_not_close_the_gap_is_not_a_rescue(self):
        self.assertIsNone(
            would_rescue(outcome=outcome(usd("50.00")), rows=[row(1, "10.00")])
        )

    def test_a_balanced_period_cannot_be_rescued(self):
        self.assertIsNone(
            would_rescue(
                outcome=outcome(usd("0.00"), ReconciliationStatus.balanced),
                rows=[row(1, "50.00")],
            )
        )

    def test_an_unavailable_identity_cannot_be_rescued(self):
        self.assertIsNone(
            would_rescue(
                outcome=outcome(None, ReconciliationStatus.unavailable),
                rows=[row(1, "50.00")],
            )
        )

    def test_a_debit_rescues_a_negative_residual(self):
        warning = would_rescue(
            outcome=outcome(usd("-50.00")), rows=[row(1, "50.00", DEBIT)]
        )
        self.assertIsNotNone(warning)

    def test_a_row_in_another_currency_is_refused(self):
        eur = RowObservation(
            ref_id="R1",
            row_index=1,
            amount=Money.from_decimal(Decimal("50.00"), "EUR"),
            direction=CREDIT,
        )
        with self.assertRaises(LocalisationError):
            would_rescue(outcome=outcome(usd("50.00")), rows=[eur])


class ReportsCarryNoCaseContent(unittest.TestCase):
    def test_a_reading_carries_only_references_and_amounts(self):
        """Structural, so that adding a description field fails here first."""
        self.assertEqual(
            {f.name for f in fields(RowObservation)},
            {
                "ref_id",
                "row_index",
                "amount",
                "direction",
                "running_balance",
                "page",
            },
        )

    def test_the_rendered_report_is_deterministic(self):
        rows = [row(1, "100.00", CREDIT, "1150.00")]
        first = localise(residual=usd("-50.00"), rows=rows, opening=usd("1000.00"))
        second = localise(residual=usd("-50.00"), rows=rows, opening=usd("1000.00"))
        self.assertEqual(first.render(), second.render())

    def test_the_render_names_rows_by_reference_only(self):
        found = localise(
            residual=usd("-50.00"),
            rows=[row(1, "100.00", CREDIT, "1150.00")],
            opening=usd("1000.00"),
        )
        rendered = found.render()
        self.assertIn("R1", rendered)
        self.assertIn("residual", rendered)
        self.assertIn("strength proved", rendered)


class ListingWhatIsSetAside(unittest.TestCase):
    def test_only_quarantined_rows_are_listed_and_the_order_is_stable(self):
        rows = [
            FakeTransaction(LedgerStatus.quarantined, "unreadable_row"),
            FakeTransaction(),
            FakeTransaction(LedgerStatus.quarantined, "adjudicated"),
            FakeTransaction(LedgerStatus.superseded),
        ]
        listed = quarantined_row_ids(rows)
        self.assertEqual(len(listed), 2)
        self.assertEqual(listed, quarantined_row_ids(list(reversed(rows))))


class TheFindingTypesAreValueObjects(unittest.TestCase):
    def test_a_break_reports_its_discrepancy(self):
        brk = BalanceBreak(
            after_ref="R2",
            row_index=2,
            expected=usd("1150.00"),
            printed=usd("1100.00"),
            before_ref="R1",
        )
        self.assertEqual(brk.discrepancy, usd("-50.00"))
        self.assertFalse(brk.at_opening)

    def test_findings_are_frozen(self):
        candidate = Candidate(
            ref_id="R1", row_index=1, kind=CandidateKind.equals_residual
        )
        with self.assertRaises(FrozenInstanceError):
            candidate.ref_id = "R2"

    def test_a_localisation_counts_the_rows_it_saw(self):
        found = localise(
            residual=usd("0.00"),
            rows=[row(1, "10.00"), row(2, "20.00", CREDIT, "1030.00")],
            opening=usd("1000.00"),
        )
        self.assertIsInstance(found, Localisation)
        self.assertEqual(found.rows_seen, 2)
        self.assertEqual(found.rows_with_balance, 1)


# ---------------------------------------------------------------------------
# The same two writes, against a real session.
# ---------------------------------------------------------------------------


class QuarantineSurvivesTheDatabase(unittest.TestCase):
    """The status and the reason are held to agree by a check constraint.

    Everything above this line runs against a stub, which will hold whatever
    it is given.  The ledger will not: ``ck_financial_transactions_quarantine
    _coherent`` refuses a row set aside with no recorded grounds and a reason
    left behind after a release.  That makes the stub tests necessary and not
    sufficient — a service that wrote one column without the other would pass
    every one of them and fail at the first commit.

    The fixture follows ``test_financial_reconcile``: SQLite on disk rather
    than ``:memory:``, so the caller is not sharing a single connection with
    the code under test, and foreign keys on.
    """

    def setUp(self):
        self._directory = tempfile.mkdtemp(prefix="loupe-quarantine-")
        self.engine = create_engine(
            f"sqlite+pysqlite:///{Path(self._directory) / 'ledger.db'}",
            future=True,
        )

        @event.listens_for(self.engine, "connect")
        def _configure(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA synchronous=OFF")
            cursor.close()

        Base.metadata.create_all(self.engine, tables=TABLES)
        self.SessionLocal = sessionmaker(
            bind=self.engine, autoflush=False, autocommit=False
        )
        self.db = self.SessionLocal()

        self.user = User(
            id=uuid.uuid4(),
            email="investigator@example.test",
            name="Investigator",
            password_hash="not-used",
            global_role=GlobalRole.user,
            is_active=True,
        )
        self.case = Case(
            id=uuid.uuid4(),
            title="Quarantine Fixture",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        self.evidence_file = EvidenceFile(
            id=uuid.uuid4(),
            case_id=self.case.id,
            original_filename="january-statement.pdf",
            stored_path="/evidence/january-statement.pdf",
            sha256="a" * 64,
        )
        self.account = FinancialAccount(
            id=uuid.uuid4(),
            case_id=self.case.id,
            identity_key="us-chase-000123456",
            institution_name="Chase",
            identifier_as_printed="000 123 456",
            identifier_normalised="000123456",
            currency=USD,
        )
        self.db.add_all([self.user, self.case, self.evidence_file, self.account])
        self.db.commit()

        self.run = open_ingestion_run(
            case_id=self.case.id,
            actor=self.user,
            session_factory=self.SessionLocal,
        )
        self.document = FinancialSourceDocument(
            id=uuid.uuid4(),
            evidence_file_id=self.evidence_file.id,
            sha256_at_ingestion="a" * 64,
            document_type="bank_statement",
            proof_class=ProofClass.p2.value,
            extraction_layer=ExtractionLayer.structural.value,
            parser_name="statement_pdf",
            parser_version="1.4.0",
        )
        self.db.add(self.run.stamp(self.document))
        self.db.commit()

        self.period = record_statement_period(
            self.db,
            self.run,
            StatementPeriodDraft(
                account_id=self.account.id,
                source_document_id=self.document.id,
                currency=USD,
                bounds=PeriodBounds.printed(date(2026, 1, 1), date(2026, 1, 31)),
                opening=BalanceObservation.printed(usd("1000.00")),
                closing=BalanceObservation.printed(usd("1200.00")),
            ),
        )
        self.db.commit()
        self._row_index = 0

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        shutil.rmtree(self._directory, ignore_errors=True)

    def add_row(self, amount: str, direction=CREDIT):
        self._row_index += 1
        stored = FinancialTransaction(
            id=uuid.uuid4(),
            account_id=self.account.id,
            source_document_id=self.document.id,
            statement_period_id=self.period.id,
            ref_id=f"row-{self._row_index:04d}",
            row_index=self._row_index,
            amount_minor=usd(amount).minor_units,
            currency=USD,
            direction=direction.value,
            transaction_date=date(2026, 1, 15),
            ordering_date=date(2026, 1, 15),
            ordering_date_source="transaction",
            description=f"row {self._row_index}",
            proof_class=ProofClass.p2.value,
            extraction_layer=ExtractionLayer.structural.value,
            ledger_status=LedgerStatus.admitted.value,
            content_hash=f"{self._row_index:064d}",
        )
        self.db.add(self.run.stamp(stored))
        self.db.commit()
        return stored

    def test_a_quarantine_written_by_the_service_commits(self):
        stored = self.add_row("50.00")
        quarantine_transaction(
            stored, QuarantineBasis.unreadable_row("amount column was truncated")
        )
        self.db.commit()

        self.db.expire_all()
        reloaded = self.db.get(FinancialTransaction, stored.id)
        self.assertEqual(reloaded.ledger_status, LedgerStatus.quarantined.value)
        self.assertEqual(
            reloaded.quarantine_reason, QuarantineReason.unreadable_row.value
        )

    def test_a_release_written_by_the_service_commits(self):
        """The reason has to be cleared in the same statement as the status."""
        stored = self.add_row("50.00")
        quarantine_transaction(
            stored, QuarantineBasis.unreadable_row("amount column was truncated")
        )
        self.db.commit()

        release_transaction(
            stored, actor="A. Reviewer", reason="second read produced the amount"
        )
        self.db.commit()

        self.db.expire_all()
        reloaded = self.db.get(FinancialTransaction, stored.id)
        self.assertEqual(reloaded.ledger_status, LedgerStatus.admitted.value)
        self.assertIsNone(reloaded.quarantine_reason)

    def test_every_reason_the_service_can_produce_is_one_the_ledger_accepts(self):
        """The enum and the check constraint are two lists that could drift.

        A reason the code can construct and the database will not store is a
        crash at the worst moment — after the decision has been made and
        while it is being recorded.
        """
        for reason in QuarantineReason:
            with self.subTest(reason=reason.value):
                stored = self.add_row("10.00")
                quarantine_transaction(
                    stored,
                    QuarantineBasis(reason=reason, detail="grounds under test"),
                )
                self.db.commit()
                self.db.expire_all()
                self.assertEqual(
                    self.db.get(FinancialTransaction, stored.id).quarantine_reason,
                    reason.value,
                )

    def test_a_quarantined_row_leaves_the_totals(self):
        """The consequence the grounds requirement exists to guard.

        Quarantine is not an annotation: the row stops counting.  Here the
        period balances only because a row was removed, which is exactly the
        move that would launder a failing statement if resemblance were
        grounds.
        """
        # Opening 1,000 and a printed closing of 1,200, so 200.00 of genuine
        # movement.  The spurious row is the entire discrepancy.
        self.add_row("200.00")
        spurious = self.add_row("100.00")

        before = reconcile_period(self.db, self.period)
        self.assertIs(before.status, ReconciliationStatus.unbalanced)
        self.assertEqual(before.delta, usd("100.00"))
        self.assertEqual(before.totals.counted, 2)

        quarantine_transaction(
            spurious,
            QuarantineBasis.from_adjudication(
                actor="A. Reviewer", reason="row belongs to the following period"
            ),
        )
        self.db.commit()

        after = reconcile_period(self.db, self.period)
        self.db.commit()
        self.assertIs(after.status, ReconciliationStatus.balanced)
        self.assertEqual(after.totals.counted, 1)
        # Balanced, but not clean: the excluded count travels with the result
        # so this period cannot present itself as a complete reading.
        self.assertFalse(after.totals.is_complete)
        self.assertEqual(
            after.totals.excluded, {LedgerStatus.quarantined.value: 1}
        )
        self.assertFalse(after.proves_completeness)

    def test_quarantined_row_ids_reads_the_stored_rows(self):
        kept = self.add_row("300.00")
        setaside = self.add_row("100.00")
        quarantine_transaction(
            setaside, QuarantineBasis.unreadable_row("date column overlapped")
        )
        self.db.commit()

        self.db.expire_all()
        rows = (
            self.db.execute(
                select(FinancialTransaction).order_by(
                    FinancialTransaction.row_index
                )
            )
            .scalars()
            .all()
        )
        self.assertEqual(quarantined_row_ids(rows), (setaside.id,))
        self.assertNotIn(kept.id, quarantined_row_ids(rows))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
