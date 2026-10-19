"""Tests for statement periods and the provenance of their four values.

Almost every test here is about a distinction that a naive schema collapses:
absent against zero, printed against derived, printed against carried forward.
Collapsing any of them produces a ledger that answers confidently and wrongly,
which is worse than one that declines to answer.

The database-backed tests use a file on disk rather than ``:memory:``, matching
``test_financial_runs``: the run service opens sessions of its own, and a test
where the caller and the bookkeeping share one connection cannot see what
production sees.  ``PRAGMA foreign_keys=ON`` is essential here rather than
incidental — several of these tests assert on constraint behaviour, and SQLite
does not enforce foreign keys unless asked.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import (
    BalanceSource,
    ExtractionLayer,
    GlobalRole,
    PeriodBoundsSource,
    ProofClass,
    ReconciliationStatus,
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
    BalanceCoherenceError,
    BalanceObservation,
    PeriodBounds,
    PeriodBoundsError,
    PeriodCurrencyError,
    StatementPeriodDraft,
    read_bounds,
    read_closing,
    read_opening,
    record_statement_period,
)
from services.financial.runs import RunScopeError, open_ingestion_run

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
JAN = date(2026, 1, 1)
JAN_31 = date(2026, 1, 31)


# ---------------------------------------------------------------------------
# Value objects.  No database needed: these are about what may be said at all.
# ---------------------------------------------------------------------------


class BalanceObservationTests(unittest.TestCase):
    def test_absent_is_not_zero(self):
        """The distinction the whole module exists to preserve."""
        absent = BalanceObservation.absent()
        zero = BalanceObservation.printed(Money(minor_units=0, currency=GBP))

        self.assertTrue(absent.is_absent)
        self.assertFalse(zero.is_absent)
        self.assertIsNone(absent.minor_units)
        self.assertEqual(zero.minor_units, 0)
        self.assertNotEqual(absent, zero)

    def test_zero_is_a_real_balance(self):
        """A closed account really can print 0.00, and that is an observation."""
        zero = BalanceObservation.printed(Money(minor_units=0, currency=GBP))
        self.assertTrue(zero.is_independent)
        self.assertEqual(zero.currency, GBP)

    def test_absent_may_not_carry_an_amount(self):
        with self.assertRaises(BalanceCoherenceError) as caught:
            BalanceObservation(
                source=BalanceSource.absent,
                amount=Money(minor_units=100, currency=GBP),
            )
        self.assertIn("absent", str(caught.exception))

    def test_printed_must_carry_an_amount(self):
        with self.assertRaises(BalanceCoherenceError):
            BalanceObservation(source=BalanceSource.printed)

    def test_carried_forward_must_name_its_source_period(self):
        """Otherwise 'carried_forward' is a claim nobody can check."""
        with self.assertRaises(BalanceCoherenceError) as caught:
            BalanceObservation(
                source=BalanceSource.carried_forward,
                amount=Money(minor_units=100, currency=GBP),
            )
        self.assertIn("carried from", str(caught.exception))

    def test_printed_may_not_name_a_source_period(self):
        with self.assertRaises(BalanceCoherenceError):
            BalanceObservation(
                source=BalanceSource.printed,
                amount=Money(minor_units=100, currency=GBP),
                carried_from_period_id=uuid.uuid4(),
            )

    def test_carried_forward_is_not_independent_evidence(self):
        """It closes against the neighbour, not against these rows."""
        carried = BalanceObservation.carried_forward(
            Money(minor_units=100, currency=GBP), from_period_id=uuid.uuid4()
        )
        self.assertFalse(carried.is_independent)
        self.assertFalse(carried.is_absent)

    def test_amount_must_be_money_not_a_bare_number(self):
        """A bare int has no currency, and a balance without one is not a balance."""
        with self.assertRaises(BalanceCoherenceError) as caught:
            BalanceObservation(source=BalanceSource.printed, amount=100)
        self.assertIn("Money", str(caught.exception))

    def test_source_must_be_the_enum(self):
        with self.assertRaises(BalanceCoherenceError):
            BalanceObservation(
                source="printed", amount=Money(minor_units=1, currency=GBP)
            )


class PeriodBoundsTests(unittest.TestCase):
    def test_derived_bounds_do_not_support_continuity(self):
        """The central claim: a derived bound cannot prove a statement missing."""
        self.assertTrue(PeriodBounds.printed(JAN, JAN_31).supports_continuity)
        self.assertFalse(PeriodBounds.derived(JAN, JAN_31).supports_continuity)
        self.assertFalse(PeriodBounds.absent().supports_continuity)

    def test_one_printed_bound_is_not_enough_for_continuity(self):
        """A gap argument needs both ends printed, not just the one being compared."""
        mixed = PeriodBounds(
            start=JAN,
            end=JAN_31,
            start_source=PeriodBoundsSource.derived,
            end_source=PeriodBoundsSource.printed,
        )
        self.assertFalse(mixed.supports_continuity)

    def test_mixed_sources_are_allowed(self):
        """Statements that print only a closing date are real and common."""
        mixed = PeriodBounds(
            start=JAN,
            end=JAN_31,
            start_source=PeriodBoundsSource.derived,
            end_source=PeriodBoundsSource.printed,
        )
        self.assertEqual(mixed.start_source, PeriodBoundsSource.derived)
        self.assertEqual(mixed.end_source, PeriodBoundsSource.printed)

    def test_absent_source_may_not_carry_a_date(self):
        with self.assertRaises(PeriodBoundsError):
            PeriodBounds(start=JAN, start_source=PeriodBoundsSource.absent)

    def test_present_source_must_carry_a_date(self):
        with self.assertRaises(PeriodBoundsError):
            PeriodBounds(start=None, start_source=PeriodBoundsSource.printed)

    def test_datetime_is_refused(self):
        """datetime subclasses date and would smuggle a time into a Date column."""
        with self.assertRaises(PeriodBoundsError) as caught:
            PeriodBounds(
                start=datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc),
                end=JAN_31,
                start_source=PeriodBoundsSource.printed,
                end_source=PeriodBoundsSource.printed,
            )
        self.assertIn("datetime", str(caught.exception))

    def test_backwards_period_is_refused(self):
        with self.assertRaises(PeriodBoundsError) as caught:
            PeriodBounds.printed(JAN_31, JAN)
        self.assertIn("backwards", str(caught.exception))

    def test_single_day_period_is_allowed(self):
        """The boundary of the backwards check: equal dates are not backwards."""
        bounds = PeriodBounds.printed(JAN, JAN)
        self.assertEqual(bounds.start, bounds.end)

    def test_source_must_be_the_enum(self):
        with self.assertRaises(PeriodBoundsError):
            PeriodBounds(start=JAN, start_source="printed")


class StatementPeriodDraftTests(unittest.TestCase):
    def setUp(self):
        self.account_id = uuid.uuid4()
        self.document_id = uuid.uuid4()

    def draft(self, **overrides):
        return StatementPeriodDraft(
            account_id=overrides.pop("account_id", self.account_id),
            source_document_id=overrides.pop("source_document_id", self.document_id),
            currency=overrides.pop("currency", GBP),
            **overrides,
        )

    def test_defaults_are_absent_not_zero(self):
        draft = self.draft()
        self.assertTrue(draft.opening.is_absent)
        self.assertTrue(draft.closing.is_absent)
        self.assertFalse(draft.bounds.supports_continuity)

    def test_currency_is_normalised(self):
        self.assertEqual(self.draft(currency="gbp").currency, GBP)

    def test_unknown_currency_is_refused(self):
        with self.assertRaises(Exception):
            self.draft(currency="ZZZ")

    def test_balance_in_another_currency_is_refused(self):
        """A period holding two currencies has no balance identity."""
        with self.assertRaises(PeriodCurrencyError) as caught:
            self.draft(
                opening=BalanceObservation.printed(
                    Money(minor_units=100, currency="USD")
                )
            )
        self.assertIn("USD", str(caught.exception))

    def test_independently_checkable_needs_both_balances_printed(self):
        printed = BalanceObservation.printed(Money(minor_units=100, currency=GBP))
        carried = BalanceObservation.carried_forward(
            Money(minor_units=100, currency=GBP), from_period_id=uuid.uuid4()
        )

        self.assertTrue(
            self.draft(opening=printed, closing=printed).is_independently_checkable
        )
        self.assertFalse(
            self.draft(opening=carried, closing=printed).is_independently_checkable
        )
        self.assertFalse(
            self.draft(opening=printed, closing=BalanceObservation.absent())
            .is_independently_checkable
        )


# ---------------------------------------------------------------------------
# Persistence.  These assert on constraints, so they need a real database.
# ---------------------------------------------------------------------------


class PeriodPersistenceTestCase(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.mkdtemp(prefix="loupe-periods-")
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
            title="Period Fixture",
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
            [
                self.user,
                self.case,
                self.other_case,
                self.evidence_file,
                self.account,
            ]
        )
        self.db.commit()

        self.run = open_ingestion_run(
            case_id=self.case.id,
            actor=self.user,
            session_factory=self.SessionLocal,
        )
        self.document = self.new_document()
        self.db.add(self.run.stamp(self.document))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        shutil.rmtree(self._directory, ignore_errors=True)

    def new_document(self, **overrides):
        return FinancialSourceDocument(
            id=overrides.pop("id", uuid.uuid4()),
            evidence_file_id=overrides.pop("evidence_file_id", self.evidence_file.id),
            sha256_at_ingestion=overrides.pop("sha256_at_ingestion", "a" * 64),
            document_type=overrides.pop("document_type", "bank_statement"),
            proof_class=overrides.pop("proof_class", ProofClass.p2.value),
            extraction_layer=overrides.pop(
                "extraction_layer", ExtractionLayer.structural.value
            ),
            parser_name=overrides.pop("parser_name", "statement_pdf"),
            parser_version=overrides.pop("parser_version", "1.4.0"),
            **overrides,
        )

    def draft(self, **overrides):
        return StatementPeriodDraft(
            account_id=overrides.pop("account_id", self.account.id),
            source_document_id=overrides.pop("source_document_id", self.document.id),
            currency=overrides.pop("currency", GBP),
            **overrides,
        )


class RecordStatementPeriodTests(PeriodPersistenceTestCase):
    def test_records_all_four_provenance_values(self):
        period = record_statement_period(
            self.db,
            self.run,
            self.draft(
                bounds=PeriodBounds.printed(JAN, JAN_31),
                opening=BalanceObservation.printed(
                    Money(minor_units=100_00, currency=GBP)
                ),
                closing=BalanceObservation.printed(
                    Money(minor_units=250_00, currency=GBP)
                ),
            ),
        )
        self.db.commit()

        self.assertEqual(period.period_start_source, "printed")
        self.assertEqual(period.period_end_source, "printed")
        self.assertEqual(period.opening_balance_source, "printed")
        self.assertEqual(period.closing_balance_source, "printed")
        self.assertEqual(period.opening_balance_minor, 100_00)
        self.assertEqual(
            period.reconciliation_status, ReconciliationStatus.not_attempted.value
        )

    def test_attributes_the_period_to_the_run_and_case(self):
        period = record_statement_period(self.db, self.run, self.draft())
        self.db.commit()

        self.assertEqual(period.ingestion_run_id, self.run.run_id)
        self.assertEqual(period.case_id, self.case.id)

    def test_absent_balances_persist_as_null_not_zero(self):
        period = record_statement_period(self.db, self.run, self.draft())
        self.db.commit()

        self.assertIsNone(period.opening_balance_minor)
        self.assertEqual(period.opening_balance_source, "absent")

    def test_zero_balance_persists_as_zero(self):
        """The regression this pair of tests exists to prevent."""
        period = record_statement_period(
            self.db,
            self.run,
            self.draft(
                opening=BalanceObservation.printed(Money(minor_units=0, currency=GBP))
            ),
        )
        self.db.commit()

        self.assertEqual(period.opening_balance_minor, 0)
        self.assertEqual(period.opening_balance_source, "printed")

    def test_account_from_another_case_is_refused(self):
        stranger = FinancialAccount(
            id=uuid.uuid4(),
            case_id=self.other_case.id,
            identity_key="gb-other-99887766",
            institution_name="Other Bank",
            identifier_as_printed="99-88-77 66",
            identifier_normalised="99887766",
            currency=GBP,
        )
        self.db.add(stranger)
        self.db.commit()

        with self.assertRaises(RunScopeError) as caught:
            record_statement_period(
                self.db, self.run, self.draft(account_id=stranger.id)
            )
        self.assertIn(str(self.other_case.id), str(caught.exception))

    def test_missing_account_is_refused(self):
        with self.assertRaises(RunScopeError):
            record_statement_period(
                self.db, self.run, self.draft(account_id=uuid.uuid4())
            )

    def test_missing_document_is_refused(self):
        with self.assertRaises(RunScopeError):
            record_statement_period(
                self.db, self.run, self.draft(source_document_id=uuid.uuid4())
            )

    def test_a_closed_run_may_not_record_periods(self):
        self.run.terminate(self.run.status.__class__.completed)
        with self.assertRaises(RunScopeError):
            record_statement_period(self.db, self.run, self.draft())


class PeriodConstraintTests(PeriodPersistenceTestCase):
    """What the database refuses regardless of what the service layer does.

    These write through raw SQL rather than the service, because the point is
    that the constraint holds even when the value object is bypassed.
    """

    def insert(self, **columns):
        # ``.hex`` rather than ``str``: the Postgres UUID type renders as
        # CHAR(32) on SQLite and stores the undashed form, so a dashed string
        # here would silently match no parent row and fail every foreign key.
        row = {
            "id": uuid.uuid4().hex,
            "case_id": self.case.id.hex,
            "source_document_id": self.document.id.hex,
            "account_id": self.account.id.hex,
            "ingestion_run_id": self.run.run_id.hex,
            "currency": GBP,
            "period_start": None,
            "period_end": None,
            "period_start_source": "absent",
            "period_end_source": "absent",
            "opening_balance_minor": None,
            "opening_balance_source": "absent",
            "closing_balance_minor": None,
            "closing_balance_source": "absent",
            "reconciliation_status": ReconciliationStatus.not_attempted.value,
        }
        row.update(columns)
        names = ", ".join(row)
        binds = ", ".join(f":{name}" for name in row)
        self.db.execute(
            text(
                f"INSERT INTO financial_statement_periods ({names}) VALUES ({binds})"
            ),
            row,
        )
        self.db.commit()

    def test_two_undated_periods_for_one_document_and_account_are_refused(self):
        """The hole the partial unique index closes.

        Nulls are distinct in a unique constraint in both SQLite and Postgres,
        so the four-column constraint on (document, account, start, end) does
        nothing at all when the dates could not be read — which is exactly the
        document a duplicate is hardest to spot on.
        """
        self.insert()
        with self.assertRaises(IntegrityError):
            self.insert()

    def test_two_dated_periods_for_one_document_and_account_are_refused(self):
        self.insert(
            period_start=JAN.isoformat(),
            period_end=JAN_31.isoformat(),
            period_start_source="printed",
            period_end_source="printed",
        )
        with self.assertRaises(IntegrityError):
            self.insert(
                period_start=JAN.isoformat(),
                period_end=JAN_31.isoformat(),
                period_start_source="printed",
                period_end_source="printed",
            )

    def test_an_undated_and_a_dated_period_may_coexist(self):
        """The partial index must not over-reach onto dated rows."""
        self.insert()
        self.insert(
            period_start=JAN.isoformat(),
            period_end=JAN_31.isoformat(),
            period_start_source="printed",
            period_end_source="printed",
        )
        count = self.db.execute(
            text("SELECT count(*) FROM financial_statement_periods")
        ).scalar_one()
        self.assertEqual(count, 2)

    def test_absent_balance_source_with_a_value_is_refused(self):
        with self.assertRaises(IntegrityError):
            self.insert(opening_balance_source="absent", opening_balance_minor=100)

    def test_printed_balance_source_without_a_value_is_refused(self):
        with self.assertRaises(IntegrityError):
            self.insert(opening_balance_source="printed", opening_balance_minor=None)

    def test_printed_balance_of_zero_is_accepted(self):
        """The coherence check compares booleans, so 0 is not mistaken for absent."""
        self.insert(opening_balance_source="printed", opening_balance_minor=0)

    def test_absent_date_source_with_a_date_is_refused(self):
        with self.assertRaises(IntegrityError):
            self.insert(period_start_source="absent", period_start=JAN.isoformat())

    def test_printed_date_source_without_a_date_is_refused(self):
        with self.assertRaises(IntegrityError):
            self.insert(period_start_source="printed", period_start=None)

    def test_unknown_bounds_source_is_refused(self):
        with self.assertRaises(IntegrityError):
            self.insert(
                period_start_source="guessed", period_start=JAN.isoformat()
            )


class ReadBackTests(PeriodPersistenceTestCase):
    def test_round_trips_printed_bounds_and_balances(self):
        record_statement_period(
            self.db,
            self.run,
            self.draft(
                bounds=PeriodBounds.printed(JAN, JAN_31),
                opening=BalanceObservation.printed(
                    Money(minor_units=100_00, currency=GBP)
                ),
                closing=BalanceObservation.printed(
                    Money(minor_units=250_00, currency=GBP)
                ),
            ),
        )
        self.db.commit()

        session = self.SessionLocal()
        try:
            stored = session.query(FinancialStatementPeriod).one()
            self.assertEqual(read_bounds(stored), PeriodBounds.printed(JAN, JAN_31))
            self.assertEqual(
                read_opening(stored),
                BalanceObservation.printed(Money(minor_units=100_00, currency=GBP)),
            )
            self.assertEqual(read_closing(stored).minor_units, 250_00)
        finally:
            session.close()

    def test_round_trips_absence_as_absence(self):
        record_statement_period(self.db, self.run, self.draft())
        self.db.commit()

        session = self.SessionLocal()
        try:
            stored = session.query(FinancialStatementPeriod).one()
            self.assertTrue(read_opening(stored).is_absent)
            self.assertIsNone(read_opening(stored).minor_units)
            self.assertFalse(read_bounds(stored).supports_continuity)
        finally:
            session.close()

    def test_round_trips_derived_bounds_as_derived(self):
        """A derived bound must not come back out of the database as printed."""
        record_statement_period(
            self.db, self.run, self.draft(bounds=PeriodBounds.derived(JAN, JAN_31))
        )
        self.db.commit()

        session = self.SessionLocal()
        try:
            stored = session.query(FinancialStatementPeriod).one()
            bounds = read_bounds(stored)
            self.assertEqual(bounds.start_source, PeriodBoundsSource.derived)
            self.assertFalse(bounds.supports_continuity)
        finally:
            session.close()

    def test_carried_forward_round_trips_with_its_source_period(self):
        first = record_statement_period(
            self.db,
            self.run,
            self.draft(
                bounds=PeriodBounds.printed(JAN, JAN_31),
                closing=BalanceObservation.printed(
                    Money(minor_units=250_00, currency=GBP)
                ),
            ),
        )
        self.db.commit()

        # A second evidence file, not just a second document row: source
        # documents are unique on (run, evidence file), so one run cannot
        # ingest the same file twice.
        february_file = EvidenceFile(
            id=uuid.uuid4(),
            case_id=self.case.id,
            original_filename="february-statement.pdf",
            stored_path="/evidence/february-statement.pdf",
            sha256="b" * 64,
        )
        self.db.add(february_file)
        self.db.commit()

        second_document = self.new_document(
            evidence_file_id=february_file.id, sha256_at_ingestion="b" * 64
        )
        self.db.add(self.run.stamp(second_document))
        self.db.commit()

        second = record_statement_period(
            self.db,
            self.run,
            self.draft(
                source_document_id=second_document.id,
                bounds=PeriodBounds.printed(date(2026, 2, 1), date(2026, 2, 28)),
                opening=BalanceObservation.carried_forward(
                    Money(minor_units=250_00, currency=GBP), from_period_id=first.id
                ),
            ),
        )
        self.db.commit()

        opening = read_opening(second)
        self.assertEqual(opening.source, BalanceSource.carried_forward)
        self.assertEqual(opening.carried_from_period_id, first.id)
        self.assertFalse(opening.is_independent)

    def test_carried_forward_whose_source_period_is_gone_raises(self):
        """SET NULL on that link permits this row; reading it must not paper over it.

        Reconstructing it as printed would upgrade weak evidence on the way out
        of the database, which is precisely the failure the source column
        exists to prevent.
        """
        record_statement_period(
            self.db,
            self.run,
            self.draft(
                opening=BalanceObservation.printed(
                    Money(minor_units=250_00, currency=GBP)
                )
            ),
        )
        self.db.commit()

        # Force the state a cascade would leave behind.
        self.db.execute(
            text(
                "UPDATE financial_statement_periods "
                "SET opening_balance_source = 'carried_forward', "
                "opening_carried_from_period_id = NULL"
            )
        )
        self.db.commit()

        session = self.SessionLocal()
        try:
            stored = session.query(FinancialStatementPeriod).one()
            with self.assertRaises(BalanceCoherenceError) as caught:
                read_opening(stored)
            self.assertIn("deleted", str(caught.exception))
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
