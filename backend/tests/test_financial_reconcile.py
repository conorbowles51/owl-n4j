"""Tests for the balance identity.

The identity is the one check in this subsystem that a language model cannot
argue with, so the tests are mostly about the ways a plausible implementation
would quietly stop being a check:

* substituting zero for a balance nobody could read, which turns a missing
  observation into a delta the size of the real opening balance;
* counting rows that were set aside, so a period balances because the
  inconvenient rows are not in the sum;
* reporting a balance struck against a carried-forward opening as though it
  proved these rows complete, when it restates the neighbouring period;
* summing across currencies, which produces a number with no referent.

Each of those is a test that fails loudly if the rule is relaxed.

The pure tests exercise ``evaluate_identity`` directly.  The database-backed
ones follow ``test_financial_periods``: a SQLite file on disk rather than
``:memory:`` so the caller does not share one connection with the services
under test, and ``PRAGMA foreign_keys=ON`` because several assertions here
depend on the ledger's own constraints holding.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import (
    ExtractionLayer,
    GlobalRole,
    LedgerStatus,
    ProofClass,
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
from services.financial.reconcile import (
    LedgerOverflowError,
    MixedCurrencyError,
    ReconciliationError,
    TransactionTotals,
    empty_totals,
    evaluate_identity,
    reconcile_period,
    total_transactions,
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

GBP = "GBP"
USD = "USD"
JAN = date(2026, 1, 1)
JAN_15 = date(2026, 1, 15)
JAN_31 = date(2026, 1, 31)


def gbp(minor: int) -> Money:
    return Money(minor_units=minor, currency=GBP)


def printed(minor: int) -> BalanceObservation:
    return BalanceObservation.printed(gbp(minor))


def carried(minor: int) -> BalanceObservation:
    return BalanceObservation.carried_forward(gbp(minor), from_period_id=uuid.uuid4())


def totals(
    credits: int = 0,
    debits: int = 0,
    *,
    counted: int = 0,
    excluded: dict | None = None,
    currency: str = GBP,
) -> TransactionTotals:
    """Totals built by hand, so the pure tests need no database."""
    return TransactionTotals(
        currency=currency,
        credits=Money(minor_units=credits, currency=currency),
        debits=Money(minor_units=debits, currency=currency),
        counted=counted,
        excluded=dict(excluded or {}),
    )


# ---------------------------------------------------------------------------
# Totals as a value.  What was counted, and what was left out.
# ---------------------------------------------------------------------------


class TransactionTotalsTests(unittest.TestCase):
    def test_net_is_credits_less_debits(self):
        self.assertEqual(totals(credits=500_00, debits=120_00).net, gbp(380_00))

    def test_net_may_be_negative(self):
        """A month that spent more than it received is ordinary, not an error."""
        self.assertEqual(totals(credits=10_00, debits=90_00).net, gbp(-80_00))

    def test_a_period_with_nothing_excluded_is_complete(self):
        counted = totals(credits=1_00, counted=1)
        self.assertTrue(counted.is_complete)
        self.assertEqual(counted.excluded_count, 0)

    def test_excluded_rows_are_counted_by_status(self):
        partial = totals(
            credits=1_00,
            counted=1,
            excluded={
                LedgerStatus.quarantined.value: 2,
                LedgerStatus.superseded.value: 1,
            },
        )
        self.assertFalse(partial.is_complete)
        self.assertEqual(partial.excluded_count, 3)

    def test_empty_totals_are_zero_and_complete(self):
        empty = empty_totals(GBP)
        self.assertEqual(empty.credits, gbp(0))
        self.assertEqual(empty.debits, gbp(0))
        self.assertEqual(empty.net, gbp(0))
        self.assertEqual(empty.counted, 0)
        self.assertTrue(empty.is_complete)

    def test_empty_totals_normalise_the_currency_code(self):
        self.assertEqual(empty_totals("gbp").currency, GBP)


# ---------------------------------------------------------------------------
# The identity itself.  Pure arithmetic over observations.
# ---------------------------------------------------------------------------


class IdentityArithmeticTests(unittest.TestCase):
    def test_closing_identity_balances(self):
        outcome = evaluate_identity(
            opening=printed(100_00),
            closing=printed(380_00),
            totals=totals(credits=400_00, debits=120_00, counted=6),
            currency=GBP,
        )
        self.assertIs(outcome.status, ReconciliationStatus.balanced)
        self.assertTrue(outcome.is_balanced)
        self.assertTrue(outcome.was_attempted)
        self.assertEqual(outcome.computed_closing, gbp(380_00))
        self.assertEqual(outcome.delta, gbp(0))
        self.assertIsNone(outcome.unavailable_reason)

    def test_missing_debits_produce_a_positive_delta(self):
        """The rows on hand make more money than the statement ended with."""
        outcome = evaluate_identity(
            opening=printed(100_00),
            closing=printed(380_00),
            totals=totals(credits=400_00, debits=70_00, counted=5),
            currency=GBP,
        )
        self.assertIs(outcome.status, ReconciliationStatus.unbalanced)
        self.assertFalse(outcome.is_balanced)
        self.assertEqual(outcome.computed_closing, gbp(430_00))
        self.assertEqual(outcome.delta, gbp(50_00))

    def test_missing_credits_produce_a_negative_delta(self):
        outcome = evaluate_identity(
            opening=printed(100_00),
            closing=printed(380_00),
            totals=totals(credits=350_00, debits=120_00, counted=5),
            currency=GBP,
        )
        self.assertIs(outcome.status, ReconciliationStatus.unbalanced)
        self.assertEqual(outcome.delta, gbp(-50_00))

    def test_a_single_penny_is_a_failure(self):
        """Exactness is the point; there is no tolerance band to hide in."""
        outcome = evaluate_identity(
            opening=printed(100_00),
            closing=printed(380_01),
            totals=totals(credits=400_00, debits=120_00, counted=6),
            currency=GBP,
        )
        self.assertIs(outcome.status, ReconciliationStatus.unbalanced)
        self.assertEqual(outcome.delta, gbp(-1))

    def test_negative_balances_are_arithmetic_not_errors(self):
        """An overdrawn account is a normal statement."""
        outcome = evaluate_identity(
            opening=printed(-250_00),
            closing=printed(-100_00),
            totals=totals(credits=200_00, debits=50_00, counted=3),
            currency=GBP,
        )
        self.assertIs(outcome.status, ReconciliationStatus.balanced)

    def test_an_empty_period_with_equal_balances_balances(self):
        """A dormant month really does reconcile."""
        outcome = evaluate_identity(
            opening=printed(100_00),
            closing=printed(100_00),
            totals=empty_totals(GBP),
            currency=GBP,
        )
        self.assertIs(outcome.status, ReconciliationStatus.balanced)
        self.assertEqual(outcome.totals.counted, 0)

    def test_an_empty_period_with_differing_balances_fails_by_the_whole_movement(self):
        """A total extraction failure, which a dormant month is not."""
        outcome = evaluate_identity(
            opening=printed(100_00),
            closing=printed(380_00),
            totals=empty_totals(GBP),
            currency=GBP,
        )
        self.assertIs(outcome.status, ReconciliationStatus.unbalanced)
        self.assertEqual(outcome.delta, gbp(-280_00))


class AbsentBalanceTests(unittest.TestCase):
    """The rule that stops a missing observation being read as a discrepancy."""

    def test_absent_opening_makes_the_identity_unavailable(self):
        outcome = evaluate_identity(
            opening=BalanceObservation.absent(),
            closing=printed(380_00),
            totals=totals(credits=400_00, debits=120_00, counted=6),
            currency=GBP,
        )
        self.assertIs(outcome.status, ReconciliationStatus.unavailable)
        self.assertIsNone(outcome.computed_closing)
        self.assertIsNone(outcome.delta)
        self.assertIn("opening", outcome.unavailable_reason)

    def test_absent_closing_makes_the_identity_unavailable(self):
        outcome = evaluate_identity(
            opening=printed(100_00),
            closing=BalanceObservation.absent(),
            totals=totals(credits=400_00, debits=120_00, counted=6),
            currency=GBP,
        )
        self.assertIs(outcome.status, ReconciliationStatus.unavailable)
        self.assertIn("closing", outcome.unavailable_reason)

    def test_both_absent_names_both(self):
        outcome = evaluate_identity(
            opening=BalanceObservation.absent(),
            closing=BalanceObservation.absent(),
            totals=empty_totals(GBP),
            currency=GBP,
        )
        self.assertIs(outcome.status, ReconciliationStatus.unavailable)
        self.assertIn("opening", outcome.unavailable_reason)
        self.assertIn("closing", outcome.unavailable_reason)

    def test_unavailable_still_reports_what_was_counted(self):
        """Useful to whoever has to go and find the missing balance."""
        outcome = evaluate_identity(
            opening=BalanceObservation.absent(),
            closing=printed(380_00),
            totals=totals(credits=400_00, debits=120_00, counted=6),
            currency=GBP,
        )
        self.assertEqual(outcome.totals.counted, 6)
        self.assertEqual(outcome.totals.net, gbp(280_00))
        self.assertEqual(outcome.printed_closing, gbp(380_00))
        self.assertIsNone(outcome.opening)

    def test_zero_is_a_balance_and_not_an_absence(self):
        """The distinction the whole design turns on, asserted at the identity."""
        outcome = evaluate_identity(
            opening=printed(0),
            closing=printed(280_00),
            totals=totals(credits=400_00, debits=120_00, counted=6),
            currency=GBP,
        )
        self.assertIs(outcome.status, ReconciliationStatus.balanced)
        self.assertEqual(outcome.opening, gbp(0))

    def test_absent_opening_is_not_silently_treated_as_zero(self):
        """The regression this module exists to prevent.

        Were the absent opening read as zero, these totals would close exactly
        against the printed closing balance and the period would be reported
        balanced on a number nobody observed.
        """
        outcome = evaluate_identity(
            opening=BalanceObservation.absent(),
            closing=printed(280_00),
            totals=totals(credits=400_00, debits=120_00, counted=6),
            currency=GBP,
        )
        self.assertIsNot(outcome.status, ReconciliationStatus.balanced)
        self.assertIs(outcome.status, ReconciliationStatus.unavailable)


class IndependenceTests(unittest.TestCase):
    """Whether the identity checked these rows, or the period next door."""

    def test_two_printed_balances_are_independent(self):
        outcome = evaluate_identity(
            opening=printed(100_00),
            closing=printed(380_00),
            totals=totals(credits=400_00, debits=120_00, counted=6),
            currency=GBP,
        )
        self.assertTrue(outcome.independent)
        self.assertTrue(outcome.proves_completeness)

    def test_a_carried_forward_opening_is_computed_but_not_independent(self):
        outcome = evaluate_identity(
            opening=carried(100_00),
            closing=printed(380_00),
            totals=totals(credits=400_00, debits=120_00, counted=6),
            currency=GBP,
        )
        self.assertIs(outcome.status, ReconciliationStatus.balanced)
        self.assertFalse(outcome.independent)
        self.assertFalse(outcome.proves_completeness)

    def test_a_carried_forward_closing_is_not_independent_either(self):
        outcome = evaluate_identity(
            opening=printed(100_00),
            closing=carried(380_00),
            totals=totals(credits=400_00, debits=120_00, counted=6),
            currency=GBP,
        )
        self.assertFalse(outcome.independent)

    def test_independence_is_reported_even_when_unavailable(self):
        """It is a property of the sources, not of whether the sum ran."""
        outcome = evaluate_identity(
            opening=printed(100_00),
            closing=BalanceObservation.absent(),
            totals=empty_totals(GBP),
            currency=GBP,
        )
        self.assertIs(outcome.status, ReconciliationStatus.unavailable)
        self.assertFalse(outcome.independent)

    def test_excluded_rows_stop_a_balance_proving_completeness(self):
        """Balanced over a subset is not balanced over the statement."""
        outcome = evaluate_identity(
            opening=printed(100_00),
            closing=printed(380_00),
            totals=totals(
                credits=400_00,
                debits=120_00,
                counted=6,
                excluded={LedgerStatus.quarantined.value: 2},
            ),
            currency=GBP,
        )
        self.assertTrue(outcome.is_balanced)
        self.assertFalse(outcome.totals.is_complete)
        self.assertFalse(outcome.proves_completeness)

    def test_unbalanced_never_proves_completeness(self):
        outcome = evaluate_identity(
            opening=printed(100_00),
            closing=printed(999_00),
            totals=totals(credits=400_00, debits=120_00, counted=6),
            currency=GBP,
        )
        self.assertTrue(outcome.independent)
        self.assertTrue(outcome.totals.is_complete)
        self.assertFalse(outcome.proves_completeness)

    def test_not_attempted_is_not_an_attempt(self):
        outcome = evaluate_identity(
            opening=BalanceObservation.absent(),
            closing=BalanceObservation.absent(),
            totals=empty_totals(GBP),
            currency=GBP,
        )
        # unavailable is a result, not an absence of one
        self.assertTrue(outcome.was_attempted)


class IdentityRefusalTests(unittest.TestCase):
    """Inputs that make the identity meaningless rather than false."""

    def test_opening_in_another_currency_is_refused(self):
        with self.assertRaises(MixedCurrencyError):
            evaluate_identity(
                opening=BalanceObservation.printed(
                    Money(minor_units=100_00, currency=USD)
                ),
                closing=printed(380_00),
                totals=empty_totals(GBP),
                currency=GBP,
            )

    def test_closing_in_another_currency_is_refused(self):
        with self.assertRaises(MixedCurrencyError):
            evaluate_identity(
                opening=printed(100_00),
                closing=BalanceObservation.printed(
                    Money(minor_units=380_00, currency=USD)
                ),
                totals=empty_totals(GBP),
                currency=GBP,
            )

    def test_totals_in_another_currency_are_refused(self):
        with self.assertRaises(MixedCurrencyError):
            evaluate_identity(
                opening=printed(100_00),
                closing=printed(380_00),
                totals=empty_totals(USD),
                currency=GBP,
            )

    def test_a_bare_number_is_not_an_observation(self):
        with self.assertRaises(ReconciliationError) as caught:
            evaluate_identity(
                opening=gbp(100_00),
                closing=printed(380_00),
                totals=empty_totals(GBP),
                currency=GBP,
            )
        self.assertIn("BalanceObservation", str(caught.exception))

    def test_an_unknown_currency_is_refused(self):
        with self.assertRaises(Exception):
            evaluate_identity(
                opening=printed(100_00),
                closing=printed(380_00),
                totals=empty_totals(GBP),
                currency="ZZZ",
            )


# ---------------------------------------------------------------------------
# Totalling and recording against a real ledger.
# ---------------------------------------------------------------------------


class ReconcilePersistenceTestCase(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.mkdtemp(prefix="loupe-reconcile-")
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
            title="Reconciliation Fixture",
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
            identity_key="gb-barclays-20445566",
            institution_name="Barclays",
            identifier_as_printed="20-44-55 66",
            identifier_normalised="20445566",
            currency=GBP,
        )
        self.db.add_all(
            [self.user, self.case, self.evidence_file, self.account]
        )
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

        self._row_index = 0

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        shutil.rmtree(self._directory, ignore_errors=True)

    # -- fixtures ----------------------------------------------------------

    def make_period(self, opening=None, closing=None, bounds=None):
        period = record_statement_period(
            self.db,
            self.run,
            StatementPeriodDraft(
                account_id=self.account.id,
                source_document_id=self.document.id,
                currency=GBP,
                bounds=bounds or PeriodBounds.printed(JAN, JAN_31),
                opening=opening or printed(100_00),
                closing=closing or printed(380_00),
            ),
        )
        self.db.commit()
        return period

    def add_row(
        self,
        period,
        *,
        amount: int,
        direction: TransactionDirection,
        status: LedgerStatus = LedgerStatus.admitted,
        currency: str = GBP,
    ):
        self._row_index += 1
        row = FinancialTransaction(
            id=uuid.uuid4(),
            account_id=self.account.id,
            source_document_id=self.document.id,
            statement_period_id=period.id,
            ref_id=f"row-{self._row_index:04d}",
            row_index=self._row_index,
            amount_minor=amount,
            currency=currency,
            direction=direction.value,
            transaction_date=JAN_15,
            ordering_date=JAN_15,
            ordering_date_source="transaction",
            description=f"row {self._row_index}",
            proof_class=ProofClass.p2.value,
            extraction_layer=ExtractionLayer.structural.value,
            ledger_status=status.value,
            content_hash=f"{self._row_index:064d}",
        )
        self.db.add(self.run.stamp(row))
        self.db.commit()
        return row


class TotalTransactionsTests(ReconcilePersistenceTestCase):
    def test_a_period_with_no_rows_totals_to_zero(self):
        period = self.make_period()
        result = total_transactions(
            self.db, period_id=period.id, currency=GBP
        )
        self.assertEqual(result.credits, gbp(0))
        self.assertEqual(result.debits, gbp(0))
        self.assertEqual(result.counted, 0)
        self.assertTrue(result.is_complete)

    def test_credits_and_debits_are_summed_separately(self):
        period = self.make_period()
        self.add_row(period, amount=400_00, direction=TransactionDirection.credit)
        self.add_row(period, amount=70_00, direction=TransactionDirection.debit)
        self.add_row(period, amount=50_00, direction=TransactionDirection.debit)

        result = total_transactions(self.db, period_id=period.id, currency=GBP)
        self.assertEqual(result.credits, gbp(400_00))
        self.assertEqual(result.debits, gbp(120_00))
        self.assertEqual(result.net, gbp(280_00))
        self.assertEqual(result.counted, 3)

    def test_non_admitted_rows_are_excluded_and_counted(self):
        """The rule that stops a period balancing by setting rows aside."""
        period = self.make_period()
        self.add_row(period, amount=400_00, direction=TransactionDirection.credit)
        self.add_row(
            period,
            amount=999_00,
            direction=TransactionDirection.debit,
            status=LedgerStatus.quarantined,
        )
        self.add_row(
            period,
            amount=888_00,
            direction=TransactionDirection.credit,
            status=LedgerStatus.superseded,
        )
        self.add_row(
            period,
            amount=777_00,
            direction=TransactionDirection.debit,
            status=LedgerStatus.rejected,
        )

        result = total_transactions(self.db, period_id=period.id, currency=GBP)
        self.assertEqual(result.credits, gbp(400_00))
        self.assertEqual(result.debits, gbp(0))
        self.assertEqual(result.counted, 1)
        self.assertFalse(result.is_complete)
        self.assertEqual(result.excluded_count, 3)
        self.assertEqual(result.excluded[LedgerStatus.quarantined.value], 1)
        self.assertEqual(result.excluded[LedgerStatus.superseded.value], 1)
        self.assertEqual(result.excluded[LedgerStatus.rejected.value], 1)

    def test_rows_in_another_period_are_not_counted(self):
        period = self.make_period()
        other = self.make_period(bounds=PeriodBounds.printed(JAN_31, JAN_31))
        self.add_row(period, amount=400_00, direction=TransactionDirection.credit)
        self.add_row(other, amount=900_00, direction=TransactionDirection.credit)

        result = total_transactions(self.db, period_id=period.id, currency=GBP)
        self.assertEqual(result.credits, gbp(400_00))
        self.assertEqual(result.counted, 1)

    def test_an_admitted_row_in_another_currency_is_refused(self):
        period = self.make_period()
        self.add_row(
            period,
            amount=400_00,
            direction=TransactionDirection.credit,
            currency=USD,
        )
        with self.assertRaises(MixedCurrencyError) as caught:
            total_transactions(self.db, period_id=period.id, currency=GBP)
        self.assertIn(USD, str(caught.exception))

    def test_a_quarantined_row_in_another_currency_is_not_refused(self):
        """It cannot corrupt a total it is not part of."""
        period = self.make_period()
        self.add_row(period, amount=400_00, direction=TransactionDirection.credit)
        self.add_row(
            period,
            amount=999_00,
            direction=TransactionDirection.debit,
            currency=USD,
            status=LedgerStatus.quarantined,
        )

        result = total_transactions(self.db, period_id=period.id, currency=GBP)
        self.assertEqual(result.credits, gbp(400_00))
        self.assertEqual(result.excluded_count, 1)


class ReconcilePeriodTests(ReconcilePersistenceTestCase):
    def test_a_balancing_period_records_every_field(self):
        period = self.make_period()
        self.add_row(period, amount=400_00, direction=TransactionDirection.credit)
        self.add_row(period, amount=120_00, direction=TransactionDirection.debit)

        outcome = reconcile_period(self.db, period)
        self.db.commit()

        self.assertIs(outcome.status, ReconciliationStatus.balanced)
        self.assertEqual(
            period.reconciliation_status, ReconciliationStatus.balanced.value
        )
        self.assertEqual(period.credit_total_minor, 400_00)
        self.assertEqual(period.debit_total_minor, 120_00)
        self.assertEqual(period.transaction_count, 2)
        self.assertEqual(period.computed_closing_minor, 380_00)
        self.assertEqual(period.delta_minor, 0)
        self.assertIsNotNone(period.reconciled_at)

    def test_an_unbalanced_period_records_the_delta_with_its_sign(self):
        period = self.make_period()
        self.add_row(period, amount=400_00, direction=TransactionDirection.credit)
        self.add_row(period, amount=70_00, direction=TransactionDirection.debit)

        outcome = reconcile_period(self.db, period)
        self.db.commit()

        self.assertIs(outcome.status, ReconciliationStatus.unbalanced)
        self.assertEqual(period.delta_minor, 50_00)
        self.assertEqual(period.computed_closing_minor, 430_00)

    def test_an_unavailable_period_records_the_totals_but_invents_nothing(self):
        period = self.make_period(opening=BalanceObservation.absent())
        self.add_row(period, amount=400_00, direction=TransactionDirection.credit)
        self.add_row(period, amount=120_00, direction=TransactionDirection.debit)

        outcome = reconcile_period(self.db, period)
        self.db.commit()

        self.assertIs(outcome.status, ReconciliationStatus.unavailable)
        self.assertEqual(period.credit_total_minor, 400_00)
        self.assertEqual(period.debit_total_minor, 120_00)
        self.assertEqual(period.transaction_count, 2)
        self.assertIsNone(period.computed_closing_minor)
        self.assertIsNone(period.delta_minor)
        # reconciled_at records the attempt, not the success
        self.assertIsNotNone(period.reconciled_at)

    def test_the_reconciliation_timestamp_may_be_supplied(self):
        period = self.make_period()
        moment = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
        reconcile_period(self.db, period, now=moment)
        self.db.commit()
        self.assertEqual(
            period.reconciled_at.replace(tzinfo=timezone.utc), moment
        )

    def test_quarantined_rows_do_not_rescue_a_failing_period(self):
        """The period balances only if the quarantined debit is counted."""
        period = self.make_period()
        self.add_row(period, amount=400_00, direction=TransactionDirection.credit)
        self.add_row(
            period,
            amount=120_00,
            direction=TransactionDirection.debit,
            status=LedgerStatus.quarantined,
        )

        outcome = reconcile_period(self.db, period)
        self.db.commit()

        self.assertIs(outcome.status, ReconciliationStatus.unbalanced)
        self.assertEqual(period.delta_minor, 120_00)
        self.assertEqual(period.transaction_count, 1)

    def test_a_balance_over_a_subset_does_not_prove_completeness(self):
        period = self.make_period()
        self.add_row(period, amount=400_00, direction=TransactionDirection.credit)
        self.add_row(period, amount=120_00, direction=TransactionDirection.debit)
        self.add_row(
            period,
            amount=1_00,
            direction=TransactionDirection.debit,
            status=LedgerStatus.quarantined,
        )

        outcome = reconcile_period(self.db, period)
        self.assertTrue(outcome.is_balanced)
        self.assertFalse(outcome.proves_completeness)

    def test_a_carried_forward_opening_balances_without_proving_anything(self):
        neighbour = self.make_period(bounds=PeriodBounds.printed(JAN, JAN))
        period = self.make_period(
            opening=BalanceObservation.carried_forward(
                gbp(100_00), from_period_id=neighbour.id
            ),
            bounds=PeriodBounds.printed(JAN_15, JAN_31),
        )
        self.add_row(period, amount=400_00, direction=TransactionDirection.credit)
        self.add_row(period, amount=120_00, direction=TransactionDirection.debit)

        outcome = reconcile_period(self.db, period)
        self.db.commit()

        self.assertIs(outcome.status, ReconciliationStatus.balanced)
        self.assertFalse(outcome.independent)
        self.assertFalse(outcome.proves_completeness)

    def test_reconciling_twice_gives_the_same_answer(self):
        period = self.make_period()
        self.add_row(period, amount=400_00, direction=TransactionDirection.credit)
        self.add_row(period, amount=120_00, direction=TransactionDirection.debit)

        first = reconcile_period(self.db, period)
        second = reconcile_period(self.db, period)
        self.db.commit()

        self.assertEqual(first.status, second.status)
        self.assertEqual(first.delta, second.delta)
        self.assertEqual(period.transaction_count, 2)

    def test_a_value_too_large_for_the_column_is_named_not_swallowed(self):
        """The overflow guard fires in Python, so it fires on either backend.

        The two backends disagree about the totals themselves.  SQLite sums
        ``BIGINT`` in 64 bits and raises ``integer overflow`` inside the query;
        Postgres widens ``sum(bigint)`` to ``numeric`` and hands back a value
        the column could not store.  So ``_fits`` is the only thing standing
        between a Postgres ledger and a driver error at some later commit, and
        the case exercised here — a computed closing balance that overflows —
        is the one where the arithmetic happens in Python and the guard
        behaves identically on both.
        """
        period = self.make_period(
            opening=printed(2**63 - 1), closing=printed(0)
        )
        self.add_row(period, amount=100_00, direction=TransactionDirection.credit)

        with self.assertRaises(LedgerOverflowError) as caught:
            reconcile_period(self.db, period)
        self.assertIn("computed_closing_minor", str(caught.exception))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
