"""Tests for running the balance identity across a case, and reading it back.

``test_financial_reconcile`` covers the arithmetic and what it refuses to
assume.  These cover the half that had no caller: finding the periods, running
the check over all of them, and turning each failure into something an
interface can render without the sweep stopping.

Four things this layer has to get right that ``reconcile_period`` does not have
to think about.

*A period in another case is not a period.*  ``reconcile_period`` takes a
period already loaded and never sees a case id, so nothing in it can notice
that the object came from a matter the caller cannot see.  The sweep filters on
the case, and a case whose periods all belong to somebody else reconciles
nothing.

*One bad period cannot abandon the rest.*  The periods most likely to refuse
are the ones holding damaged data, so a sweep that stopped at the first would
leave the rest unchecked exactly when checking matters.  Every refusal is
recorded against its own period and the sweep continues.

*A refusal must not leave a number behind.*  ``reconcile_period`` assigns
``reconciliation_status`` before the range guard on the totals can raise, so a
refusal from ``_fits`` leaves the object carrying a verdict the arithmetic
never stood behind.  If that reached the commit, the period would report a
status produced by a computation that failed.  Two tests hold this: one for a
refusal raised before the mutation, one for a refusal raised after it.

*A read does not recompute.*  ``list_period_reconciliations`` reports the
column.  A ``GET`` that recomputed would make the figure an analyst quoted a
figure that no longer exists anywhere, and would let two people opening the
same case minutes apart see different arithmetic.

The database-backed tests use a file on disk rather than ``:memory:``, matching
``test_financial_reconcile``, for the reason that test gives.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError
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
import services.financial.reconcile_case  # noqa: F401  (registers the submodule)
from services.financial.money import Money
from services.financial.periods import (
    BalanceObservation,
    PeriodBounds,
    StatementPeriodDraft,
    record_statement_period,
)
from services.financial.reconcile import (
    IdentityOutcome,
    LedgerOverflowError,
    TransactionTotals,
)
from services.financial.reconcile_case import (
    CaseOutcome,
    CaseReconciliation,
    PeriodOutcome,
    PeriodReconciliation,
    PeriodReconciliationView,
    ReconciliationQueryError,
    list_period_reconciliations,
    reconcile_case,
    to_reconciliation_view,
)
from services.financial.runs import open_ingestion_run

# ``services.financial`` re-exports a *function* named ``reconcile_case``, which
# shadows the submodule of the same name.  So ``from services.financial import
# reconcile_case`` binds the function, and ``patch("services.financial.
# reconcile_case.reconcile_period")`` fails the same way, because mock resolves
# a dotted target with ``getattr`` before it falls back to importing.  The
# module object has to be taken from ``sys.modules``, where the import above
# put it.
module = sys.modules["services.financial.reconcile_case"]

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
FEB = date(2026, 2, 1)
FEB_28 = date(2026, 2, 28)
MAR = date(2026, 3, 1)
MAR_31 = date(2026, 3, 31)

STAMP = datetime(2026, 4, 1, 9, 30, tzinfo=timezone.utc)


def gbp(minor: int) -> Money:
    return Money(minor_units=minor, currency=GBP)


def printed(minor: int) -> BalanceObservation:
    return BalanceObservation.printed(gbp(minor))


def absent() -> BalanceObservation:
    return BalanceObservation.absent()


# ---------------------------------------------------------------------------
# The response objects, which need no database
# ---------------------------------------------------------------------------


def period_result(
    outcome: PeriodOutcome = PeriodOutcome.balanced,
    *,
    stored_status: str | None = None,
    identity: IdentityOutcome | None = None,
    reason: str | None = None,
) -> PeriodReconciliation:
    return PeriodReconciliation(
        period_id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        currency=GBP,
        period_start=JAN,
        period_end=JAN_31,
        outcome=outcome,
        stored_status=stored_status or outcome.value,
        identity=identity,
        reason=reason,
    )


class PeriodOutcomeTests(unittest.TestCase):
    def test_every_outcome_but_refused_was_written(self):
        recorded = {
            member for member in PeriodOutcome if member.recorded
        }

        self.assertEqual(
            recorded,
            {
                PeriodOutcome.balanced,
                PeriodOutcome.unbalanced,
                PeriodOutcome.unavailable,
            },
        )

    def test_the_recorded_members_spell_the_stored_column_exactly(self):
        """A reader comparing a response to the column must not have to translate."""
        for member in PeriodOutcome:
            if not member.recorded:
                continue
            self.assertEqual(member.value, ReconciliationStatus(member.value).value)

    def test_not_attempted_is_deliberately_not_an_outcome(self):
        # This enum only ever describes a period that was just run, and a run
        # period is never "not attempted".
        self.assertNotIn(
            ReconciliationStatus.not_attempted.value,
            {member.value for member in PeriodOutcome},
        )


class CaseReconciliationTests(unittest.TestCase):
    def test_applied_is_true_when_at_least_one_period_was_recorded(self):
        result = CaseReconciliation(
            case_id=uuid.uuid4(),
            outcome=CaseOutcome.completed,
            periods=(
                period_result(PeriodOutcome.refused, stored_status="not_attempted"),
                period_result(PeriodOutcome.unbalanced),
            ),
            reason=None,
        )

        self.assertTrue(result.applied)

    def test_a_sweep_where_every_period_refused_applied_nothing(self):
        result = CaseReconciliation(
            case_id=uuid.uuid4(),
            outcome=CaseOutcome.completed,
            periods=(
                period_result(PeriodOutcome.refused, stored_status="not_attempted"),
                period_result(PeriodOutcome.refused, stored_status="balanced"),
            ),
            reason=None,
        )

        self.assertFalse(result.applied)

    def test_a_case_with_no_periods_applied_nothing(self):
        result = CaseReconciliation(
            case_id=uuid.uuid4(),
            outcome=CaseOutcome.no_periods,
            periods=(),
            reason=None,
        )

        self.assertFalse(result.applied)

    def test_a_failed_write_applied_nothing_even_holding_results(self):
        # Nothing reaches the caller on a rollback, but the property must not
        # depend on that: it says whether the database kept anything.
        result = CaseReconciliation(
            case_id=uuid.uuid4(),
            outcome=CaseOutcome.write_failed,
            periods=(period_result(PeriodOutcome.balanced),),
            reason="database is locked",
        )

        self.assertFalse(result.applied)

    def test_counts_key_every_outcome_even_at_zero(self):
        result = CaseReconciliation(
            case_id=uuid.uuid4(),
            outcome=CaseOutcome.completed,
            periods=(
                period_result(PeriodOutcome.balanced),
                period_result(PeriodOutcome.balanced),
                period_result(PeriodOutcome.unbalanced),
            ),
            reason=None,
        )

        self.assertEqual(
            result.counts(),
            {
                "balanced": 2,
                "unbalanced": 1,
                "unavailable": 0,
                "refused": 0,
            },
        )

    def test_as_dict_carries_the_summary_and_every_period(self):
        case_id = uuid.uuid4()
        result = CaseReconciliation(
            case_id=case_id,
            outcome=CaseOutcome.completed,
            periods=(period_result(PeriodOutcome.unbalanced),),
            reason=None,
        )

        payload = result.as_dict()

        self.assertEqual(payload["case_id"], str(case_id))
        self.assertEqual(payload["outcome"], "completed")
        self.assertTrue(payload["applied"])
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["counts"]["unbalanced"], 1)
        self.assertEqual(len(payload["periods"]), 1)


class PeriodReconciliationPayloadTests(unittest.TestCase):
    def test_a_refused_period_nulls_every_identity_field_rather_than_dropping_it(self):
        payload = period_result(
            PeriodOutcome.refused,
            stored_status="balanced",
            reason="totals are USD but the period is GBP",
        ).as_dict()

        for key in (
            "opening_minor",
            "printed_closing_minor",
            "computed_closing_minor",
            "delta_minor",
            "credit_total_minor",
            "debit_total_minor",
            "transaction_count",
            "independent",
            "proves_completeness",
            "unavailable_reason",
        ):
            self.assertIn(key, payload)
            self.assertIsNone(payload[key])

        self.assertEqual(payload["excluded_counts"], {})
        self.assertFalse(payload["recorded"])
        self.assertEqual(payload["stored_status"], "balanced")
        self.assertEqual(payload["reason"], "totals are USD but the period is GBP")

    def test_a_computed_identity_is_flattened_onto_the_payload(self):
        identity = IdentityOutcome(
            status=ReconciliationStatus.unbalanced,
            totals=TransactionTotals(
                currency=GBP,
                credits=gbp(400_00),
                debits=gbp(120_00),
                counted=3,
                excluded={"quarantined": 1},
            ),
            opening=gbp(100_00),
            printed_closing=gbp(380_00),
            computed_closing=gbp(380_00),
            delta=gbp(0),
            independent=True,
            unavailable_reason=None,
        )

        payload = period_result(
            PeriodOutcome.unbalanced, identity=identity
        ).as_dict()

        self.assertEqual(payload["opening_minor"], 100_00)
        self.assertEqual(payload["printed_closing_minor"], 380_00)
        self.assertEqual(payload["credit_total_minor"], 400_00)
        self.assertEqual(payload["debit_total_minor"], 120_00)
        self.assertEqual(payload["transaction_count"], 3)
        self.assertEqual(payload["excluded_counts"], {"quarantined": 1})
        self.assertEqual(payload["excluded_count"], 1)
        self.assertTrue(payload["independent"])
        self.assertTrue(payload["recorded"])

    def test_an_unset_date_serialises_as_null_not_the_string_none(self):
        result = PeriodReconciliation(
            period_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            currency=GBP,
            period_start=None,
            period_end=None,
            outcome=PeriodOutcome.balanced,
            stored_status="balanced",
            identity=None,
            reason=None,
        )

        payload = result.as_dict()
        self.assertIsNone(payload["period_start"])
        self.assertIsNone(payload["period_end"])


class PeriodReconciliationViewTests(unittest.TestCase):
    """Independence is read from the two stored sources, not from a flag."""

    def view(self, opening_source: str, closing_source: str):
        return PeriodReconciliationView(
            period_id=uuid.uuid4(),
            case_id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            source_document_id=uuid.uuid4(),
            ingestion_run_id=uuid.uuid4(),
            currency=GBP,
            period_start=JAN,
            period_end=JAN_31,
            reconciliation_status="balanced",
            opening_balance_minor=100_00,
            opening_balance_source=opening_source,
            closing_balance_minor=380_00,
            closing_balance_source=closing_source,
            computed_closing_minor=380_00,
            delta_minor=0,
            credit_total_minor=400_00,
            debit_total_minor=120_00,
            transaction_count=3,
            reconciled_at=STAMP,
        )

    def test_two_printed_balances_are_independent(self):
        self.assertTrue(self.view("printed", "printed").is_independent)

    def test_a_carried_forward_opening_is_not_independent(self):
        self.assertFalse(self.view("carried_forward", "printed").is_independent)

    def test_a_carried_forward_closing_is_not_independent(self):
        self.assertFalse(self.view("printed", "carried_forward").is_independent)

    def test_an_absent_balance_is_not_independent(self):
        self.assertFalse(self.view("absent", "printed").is_independent)

    def test_to_json_reports_independence_and_the_timestamp(self):
        payload = self.view("printed", "printed").to_json()

        self.assertTrue(payload["independent"])
        self.assertEqual(payload["reconciled_at"], STAMP.isoformat())
        self.assertEqual(payload["reconciliation_status"], "balanced")


# ---------------------------------------------------------------------------
# The sweep, against a real ledger
# ---------------------------------------------------------------------------


class ReconcileCaseTestCase(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.mkdtemp(prefix="loupe-reconcile-case-")
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
            title="Reconcile Case Fixture",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        self.other_case = Case(
            id=uuid.uuid4(),
            title="A Different Matter",
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
        self.db.add_all(
            [self.user, self.case, self.other_case, self.evidence_file]
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

        self.account = self.make_account()
        self._row_index = 0

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        shutil.rmtree(self._directory, ignore_errors=True)

    # -- fixtures ----------------------------------------------------------

    def make_account(self, case_id=None):
        self._accounts = getattr(self, "_accounts", 0) + 1
        digits = f"2044556{self._accounts}"
        account = FinancialAccount(
            id=uuid.uuid4(),
            case_id=case_id or self.case.id,
            first_seen_run_id=self.run.run_id,
            identity_key=f"gb-barclays-{digits}",
            institution_name="Barclays",
            identifier_as_printed=f"20-44-55 6{self._accounts}",
            identifier_normalised=digits,
            currency=GBP,
        )
        self.db.add(account)
        self.db.commit()
        return account

    def make_period(
        self,
        *,
        opening=None,
        closing=None,
        bounds=None,
        account=None,
        currency=GBP,
    ):
        period = record_statement_period(
            self.db,
            self.run,
            StatementPeriodDraft(
                account_id=(account or self.account).id,
                source_document_id=self.document.id,
                currency=currency,
                bounds=bounds or PeriodBounds.printed(JAN, JAN_31),
                opening=opening if opening is not None else printed(100_00),
                closing=closing if closing is not None else printed(380_00),
            ),
        )
        self.db.commit()
        return period

    def add_row(
        self,
        period,
        *,
        amount: int,
        direction: TransactionDirection = TransactionDirection.credit,
        status: LedgerStatus = LedgerStatus.admitted,
        currency: str = GBP,
    ):
        quarantine_reason = (
            QuarantineReason.unreadable_row
            if status is LedgerStatus.quarantined
            else None
        )
        self._row_index += 1
        row = FinancialTransaction(
            id=uuid.uuid4(),
            account_id=period.account_id,
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
            quarantine_reason=(
                quarantine_reason.value if quarantine_reason is not None else None
            ),
            content_hash=f"{self._row_index:064d}",
        )
        self.db.add(self.run.stamp(row))
        self.db.commit()
        return row

    def stored(self, period_id):
        self.db.expire_all()
        return self.db.get(FinancialStatementPeriod, period_id)


class SweepScopeTests(ReconcileCaseTestCase):
    def test_a_case_with_no_periods_reports_no_periods_and_writes_nothing(self):
        result = reconcile_case(self.db, self.case.id)

        self.assertIs(result.outcome, CaseOutcome.no_periods)
        self.assertEqual(result.periods, ())
        self.assertFalse(result.applied)
        self.assertIsNone(result.reason)

    def test_periods_of_another_case_are_not_touched(self):
        period = self.make_period()

        result = reconcile_case(self.db, self.other_case.id)

        self.assertIs(result.outcome, CaseOutcome.no_periods)
        self.assertEqual(
            self.stored(period.id).reconciliation_status,
            ReconciliationStatus.not_attempted.value,
        )

    def test_an_account_filter_narrows_the_sweep(self):
        mine = self.make_period()
        other_account = self.make_account()
        theirs = self.make_period(
            account=other_account, bounds=PeriodBounds.printed(FEB, FEB_28)
        )

        result = reconcile_case(
            self.db, self.case.id, account_id=self.account.id
        )

        self.assertEqual(len(result.periods), 1)
        self.assertEqual(result.periods[0].period_id, mine.id)
        self.assertEqual(
            self.stored(theirs.id).reconciliation_status,
            ReconciliationStatus.not_attempted.value,
        )

    def test_periods_are_visited_oldest_first(self):
        march = self.make_period(bounds=PeriodBounds.printed(MAR, MAR_31))
        january = self.make_period(bounds=PeriodBounds.printed(JAN, JAN_31))
        february = self.make_period(bounds=PeriodBounds.printed(FEB, FEB_28))

        result = reconcile_case(self.db, self.case.id)

        self.assertEqual(
            [period.period_id for period in result.periods],
            [january.id, february.id, march.id],
        )

    def test_a_period_with_no_printed_start_sorts_last(self):
        undated = self.make_period(bounds=PeriodBounds.absent())
        january = self.make_period(bounds=PeriodBounds.printed(JAN, JAN_31))

        result = reconcile_case(self.db, self.case.id)

        self.assertEqual(
            [period.period_id for period in result.periods],
            [january.id, undated.id],
        )


class SweepResultTests(ReconcileCaseTestCase):
    def test_a_period_whose_rows_add_up_is_recorded_balanced(self):
        period = self.make_period(opening=printed(100_00), closing=printed(380_00))
        self.add_row(period, amount=400_00, direction=TransactionDirection.credit)
        self.add_row(period, amount=120_00, direction=TransactionDirection.debit)

        result = reconcile_case(self.db, self.case.id, now=STAMP)

        (one,) = result.periods
        self.assertIs(one.outcome, PeriodOutcome.balanced)
        self.assertTrue(one.recorded)
        self.assertIsNone(one.reason)

        row = self.stored(period.id)
        self.assertEqual(
            row.reconciliation_status, ReconciliationStatus.balanced.value
        )
        self.assertEqual(row.credit_total_minor, 400_00)
        self.assertEqual(row.debit_total_minor, 120_00)
        self.assertEqual(row.transaction_count, 2)
        self.assertEqual(row.computed_closing_minor, 380_00)
        self.assertEqual(row.delta_minor, 0)
        self.assertIsNotNone(row.reconciled_at)

    def test_a_missing_transaction_shows_as_a_delta_not_a_balance(self):
        """The whole point of the check: a dropped row has no other witness."""
        period = self.make_period(opening=printed(100_00), closing=printed(380_00))
        self.add_row(period, amount=400_00, direction=TransactionDirection.credit)
        # The 120.00 debit that the statement printed never made it in.

        result = reconcile_case(self.db, self.case.id)

        (one,) = result.periods
        self.assertIs(one.outcome, PeriodOutcome.unbalanced)
        self.assertEqual(self.stored(period.id).delta_minor, 120_00)

    def test_a_period_with_no_printed_opening_is_unavailable_not_zero(self):
        period = self.make_period(opening=absent(), closing=printed(380_00))
        self.add_row(period, amount=400_00, direction=TransactionDirection.credit)

        result = reconcile_case(self.db, self.case.id)

        (one,) = result.periods
        self.assertIs(one.outcome, PeriodOutcome.unavailable)
        row = self.stored(period.id)
        self.assertEqual(
            row.reconciliation_status, ReconciliationStatus.unavailable.value
        )
        # Totals were genuinely computed and are worth keeping; the two values
        # that would have been inventions stay null.
        self.assertEqual(row.credit_total_minor, 400_00)
        self.assertIsNone(row.computed_closing_minor)
        self.assertIsNone(row.delta_minor)

    def test_the_whole_sweep_shares_one_timestamp(self):
        self.make_period(bounds=PeriodBounds.printed(JAN, JAN_31))
        self.make_period(bounds=PeriodBounds.printed(FEB, FEB_28))

        reconcile_case(self.db, self.case.id, now=STAMP)

        stamps = {
            period.reconciled_at
            for period in list_period_reconciliations(self.db, self.case.id)
        }
        self.assertEqual(len(stamps), 1)

    def test_re_running_after_a_row_is_set_aside_changes_the_verdict(self):
        """The claim this path makes that the parse-time verdict cannot."""
        period = self.make_period(opening=printed(100_00), closing=printed(380_00))
        self.add_row(period, amount=400_00, direction=TransactionDirection.credit)
        debit = self.add_row(
            period, amount=120_00, direction=TransactionDirection.debit
        )

        first = reconcile_case(self.db, self.case.id)
        self.assertIs(first.periods[0].outcome, PeriodOutcome.balanced)

        debit.ledger_status = LedgerStatus.quarantined.value
        debit.quarantine_reason = QuarantineReason.unreadable_row.value
        self.db.commit()

        second = reconcile_case(self.db, self.case.id)
        self.assertIs(second.periods[0].outcome, PeriodOutcome.unbalanced)

    def test_counts_summarise_a_mixed_sweep(self):
        balanced = self.make_period(bounds=PeriodBounds.printed(JAN, JAN_31))
        self.add_row(balanced, amount=280_00)
        self.make_period(bounds=PeriodBounds.printed(FEB, FEB_28))
        self.make_period(
            bounds=PeriodBounds.printed(MAR, MAR_31), opening=absent()
        )

        result = reconcile_case(self.db, self.case.id)

        self.assertIs(result.outcome, CaseOutcome.completed)
        self.assertTrue(result.applied)
        self.assertEqual(
            result.counts(),
            {"balanced": 1, "unbalanced": 1, "unavailable": 1, "refused": 0},
        )


class SweepRefusalTests(ReconcileCaseTestCase):
    def test_a_mixed_currency_period_refuses_without_stopping_the_sweep(self):
        bad = self.make_period(bounds=PeriodBounds.printed(JAN, JAN_31))
        self.add_row(bad, amount=400_00, currency=USD)
        good = self.make_period(bounds=PeriodBounds.printed(FEB, FEB_28))
        self.add_row(good, amount=280_00)

        result = reconcile_case(self.db, self.case.id)

        self.assertIs(result.outcome, CaseOutcome.completed)
        first, second = result.periods
        self.assertEqual(first.period_id, bad.id)
        self.assertIs(first.outcome, PeriodOutcome.refused)
        self.assertFalse(first.recorded)
        self.assertIn("USD", first.reason)

        self.assertEqual(second.period_id, good.id)
        self.assertIs(second.outcome, PeriodOutcome.balanced)
        self.assertEqual(
            self.stored(good.id).reconciliation_status,
            ReconciliationStatus.balanced.value,
        )

    def test_a_refusal_before_the_mutation_leaves_the_column_untouched(self):
        bad = self.make_period()
        self.add_row(bad, amount=400_00, currency=USD)

        result = reconcile_case(self.db, self.case.id)

        self.assertIs(result.periods[0].outcome, PeriodOutcome.refused)
        self.assertEqual(
            result.periods[0].stored_status,
            ReconciliationStatus.not_attempted.value,
        )
        self.assertEqual(
            self.stored(bad.id).reconciliation_status,
            ReconciliationStatus.not_attempted.value,
        )

    def test_a_refusal_after_the_mutation_discards_the_half_written_verdict(self):
        """``_fits`` raises after ``reconciliation_status`` has been assigned.

        Reproduced rather than provoked with a real overflow, because what is
        under test is the sweep discarding the mutation, not SQLite's integer
        handling.  The mutation and the exception are exactly the order
        ``reconcile_period`` performs them in.
        """
        period = self.make_period()

        def mutate_then_raise(session, target, **_kwargs):
            target.reconciliation_status = ReconciliationStatus.balanced.value
            target.credit_total_minor = 400_00
            raise LedgerOverflowError("debit_total_minor would be 2**63")

        with patch.object(
            module, "reconcile_period", side_effect=mutate_then_raise
        ):
            result = reconcile_case(self.db, self.case.id)

        (one,) = result.periods
        self.assertIs(one.outcome, PeriodOutcome.refused)
        self.assertEqual(
            one.stored_status, ReconciliationStatus.not_attempted.value
        )

        row = self.stored(period.id)
        self.assertEqual(
            row.reconciliation_status, ReconciliationStatus.not_attempted.value
        )
        self.assertIsNone(row.credit_total_minor)

    def test_a_refusal_does_not_erase_a_verdict_an_earlier_run_recorded(self):
        """A read failure today is not evidence that yesterday's finding was wrong."""
        period = self.make_period(opening=printed(100_00), closing=printed(380_00))
        self.add_row(period, amount=280_00)

        reconcile_case(self.db, self.case.id)
        self.assertEqual(
            self.stored(period.id).reconciliation_status,
            ReconciliationStatus.balanced.value,
        )

        # The period now holds a row in another currency, so the identity can
        # no longer be computed at all.
        self.add_row(period, amount=50_00, currency=USD)

        result = reconcile_case(self.db, self.case.id)

        self.assertIs(result.periods[0].outcome, PeriodOutcome.refused)
        self.assertEqual(
            result.periods[0].stored_status, ReconciliationStatus.balanced.value
        )
        self.assertEqual(
            self.stored(period.id).reconciliation_status,
            ReconciliationStatus.balanced.value,
        )

    def test_a_sweep_of_nothing_but_refusals_completed_but_applied_nothing(self):
        bad = self.make_period()
        self.add_row(bad, amount=400_00, currency=USD)

        result = reconcile_case(self.db, self.case.id)

        self.assertIs(result.outcome, CaseOutcome.completed)
        self.assertFalse(result.applied)
        self.assertEqual(result.counts()["refused"], 1)


class SweepDatabaseFailureTests(ReconcileCaseTestCase):
    def test_a_database_error_rolls_back_and_reports_write_failed(self):
        self.make_period()

        with patch.object(
            module,
            "reconcile_period",
            side_effect=OperationalError("SELECT 1", {}, Exception("locked")),
        ):
            result = reconcile_case(self.db, self.case.id)

        self.assertIs(result.outcome, CaseOutcome.write_failed)
        self.assertEqual(result.periods, ())
        self.assertFalse(result.applied)
        self.assertIn("locked", result.reason)

    def test_a_failed_commit_reports_write_failed_and_records_nothing(self):
        period = self.make_period()
        self.add_row(period, amount=280_00)

        with patch.object(
            self.db,
            "commit",
            side_effect=OperationalError("COMMIT", {}, Exception("disk full")),
        ):
            result = reconcile_case(self.db, self.case.id)

        self.assertIs(result.outcome, CaseOutcome.write_failed)
        self.assertIn("disk full", result.reason)
        self.assertEqual(
            self.stored(period.id).reconciliation_status,
            ReconciliationStatus.not_attempted.value,
        )


# ---------------------------------------------------------------------------
# Reading the recorded result
# ---------------------------------------------------------------------------


class ListPeriodReconciliationsTests(ReconcileCaseTestCase):
    def test_an_unreconciled_period_is_listed_by_default(self):
        """The single most important thing this read can report."""
        period = self.make_period()

        (row,) = list_period_reconciliations(self.db, self.case.id)

        self.assertEqual(row.id, period.id)
        self.assertEqual(
            row.reconciliation_status, ReconciliationStatus.not_attempted.value
        )

    def test_the_read_does_not_recompute(self):
        period = self.make_period(opening=printed(100_00), closing=printed(380_00))
        self.add_row(period, amount=400_00, direction=TransactionDirection.credit)

        (row,) = list_period_reconciliations(self.db, self.case.id)

        self.assertEqual(
            row.reconciliation_status, ReconciliationStatus.not_attempted.value
        )
        self.assertIsNone(row.delta_minor)
        self.assertIsNone(row.reconciled_at)

    def test_periods_of_another_case_are_not_returned(self):
        self.make_period()

        self.assertEqual(
            list(list_period_reconciliations(self.db, self.other_case.id)), []
        )

    def test_a_status_filter_narrows_the_result(self):
        balanced = self.make_period(bounds=PeriodBounds.printed(JAN, JAN_31))
        self.add_row(balanced, amount=280_00)
        self.make_period(bounds=PeriodBounds.printed(FEB, FEB_28))
        reconcile_case(self.db, self.case.id)

        rows = list_period_reconciliations(
            self.db,
            self.case.id,
            reconciliation_status=ReconciliationStatus.unbalanced,
        )

        self.assertEqual([row.reconciliation_status for row in rows], ["unbalanced"])

    def test_an_account_filter_narrows_the_result(self):
        mine = self.make_period()
        other_account = self.make_account()
        self.make_period(
            account=other_account, bounds=PeriodBounds.printed(FEB, FEB_28)
        )

        rows = list_period_reconciliations(
            self.db, self.case.id, account_id=self.account.id
        )

        self.assertEqual([row.id for row in rows], [mine.id])

    def test_results_are_oldest_first(self):
        march = self.make_period(bounds=PeriodBounds.printed(MAR, MAR_31))
        january = self.make_period(bounds=PeriodBounds.printed(JAN, JAN_31))

        rows = list_period_reconciliations(self.db, self.case.id)

        self.assertEqual([row.id for row in rows], [january.id, march.id])

    def test_a_limit_takes_the_oldest(self):
        self.make_period(bounds=PeriodBounds.printed(MAR, MAR_31))
        january = self.make_period(bounds=PeriodBounds.printed(JAN, JAN_31))

        rows = list_period_reconciliations(self.db, self.case.id, limit=1)

        self.assertEqual([row.id for row in rows], [january.id])

    def test_a_non_positive_limit_is_refused_rather_than_ignored(self):
        for limit in (0, -1):
            with self.subTest(limit=limit):
                with self.assertRaises(ReconciliationQueryError):
                    list_period_reconciliations(
                        self.db, self.case.id, limit=limit
                    )


class ToReconciliationViewTests(ReconcileCaseTestCase):
    def test_the_view_projects_the_stored_columns(self):
        period = self.make_period(opening=printed(100_00), closing=printed(380_00))
        self.add_row(period, amount=400_00, direction=TransactionDirection.credit)
        self.add_row(period, amount=120_00, direction=TransactionDirection.debit)
        reconcile_case(self.db, self.case.id, now=STAMP)

        (row,) = list_period_reconciliations(self.db, self.case.id)
        payload = to_reconciliation_view(row).to_json()

        self.assertEqual(payload["period_id"], str(period.id))
        self.assertEqual(payload["case_id"], str(self.case.id))
        self.assertEqual(payload["account_id"], str(self.account.id))
        self.assertEqual(payload["reconciliation_status"], "balanced")
        self.assertEqual(payload["opening_balance_minor"], 100_00)
        self.assertEqual(payload["closing_balance_minor"], 380_00)
        self.assertEqual(payload["computed_closing_minor"], 380_00)
        self.assertEqual(payload["delta_minor"], 0)
        self.assertEqual(payload["credit_total_minor"], 400_00)
        self.assertEqual(payload["debit_total_minor"], 120_00)
        self.assertEqual(payload["transaction_count"], 2)
        self.assertTrue(payload["independent"])

    def test_a_never_reconciled_period_reports_nulls_and_not_attempted(self):
        self.make_period()

        (row,) = list_period_reconciliations(self.db, self.case.id)
        payload = to_reconciliation_view(row).to_json()

        self.assertEqual(payload["reconciliation_status"], "not_attempted")
        self.assertIsNone(payload["computed_closing_minor"])
        self.assertIsNone(payload["delta_minor"])
        self.assertIsNone(payload["transaction_count"])
        self.assertIsNone(payload["reconciled_at"])


if __name__ == "__main__":
    unittest.main()
