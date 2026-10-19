"""Tests for reading a stored period into the form the localisation arithmetic needs.

``services.financial.quarantine`` is pure, and ``test_financial_quarantine``
tests it as such: it hands ``localise`` a residual and a list of observations
built by hand, and never touches a database.  That is the right way to test
arithmetic and it is also why the arithmetic had no callers.  These tests cover
the join: stored rows to observations, a stored period to a live identity, and
the two rescue questions asked of a real ledger rather than of a fixture.

Three things here are worth stating because they are decisions rather than
mechanics, and a later reader will otherwise assume they were accidents.

*The chain is walked over admitted rows only.*  ``localise`` calls a set of
breaks ``proved`` when their discrepancies account for the whole residual, and
the residual is produced by ``total_transactions``, which sums admitted rows.
Walking any other population against that residual compares two numbers that do
not measure the same thing, and ``proved`` is the one verdict in this subsystem
that is grounds for setting evidence aside.  So the filter is load bearing and
it is tested directly.

*The identity is recomputed rather than read off the period.*  A period carries
the delta its last reconciliation wrote.  Anything admitted, corrected or set
aside since then has moved the real figure and left that column behind, and the
rescue question is about the gap as it stands at the moment of the write.  The
test for this stores a deliberately stale delta on the period and checks the
answer disagrees with it.

*A missing answer is not a negative answer.*  ``rescue_if_removed`` returns no
warning in several unrelated situations, and none of them is a claim that the
period was checked and found safe.  Each is enumerated, because collapsing them
is exactly the mistake that would make a laundering check quietly stop working.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import (
    ExtractionLayer,
    GlobalRole,
    LedgerStatus,
    LocatorKind,
    ReconciliationStatus,
    TransactionDirection,
)
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.financial import (
    AdjudicationEvent,
    FinancialAccount,
    FinancialIngestionRun,
    FinancialSourceDocument,
    FinancialStatementPeriod,
    FinancialTransaction,
)
from postgres.models.user import User
from services.financial.documents import SourceDocumentDraft, record_source_document
from services.financial.localisation import (
    current_identity,
    localise_period,
    observe_period_rows,
    observe_transaction,
    rescue_if_removed,
)
from services.financial.locators import Locator
from services.financial.money import Money
from services.financial.periods import (
    BalanceObservation,
    PeriodBounds,
    StatementPeriodDraft,
    record_statement_period,
)
from services.financial.proof_class import SourceShape
from services.financial.quarantine import (
    LocalisationStrength,
    RescueWarning,
    RowObservation,
)
from services.financial.references import RowReading
from services.financial.runs import open_ingestion_run
from services.financial.transactions import TransactionDraft, record_transactions

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
    AdjudicationEvent.__table__,
]

GBP = "GBP"
HASH_A = "a" * 64
JANUARY = date(2024, 1, 15)

#: ``None`` is a meaningful value for a balance here -- it is a statement that
#: printed none -- so the fixture cannot use it to mean "unspecified".
_UNSET = object()


def gbp(minor: int) -> Money:
    return Money.from_minor_units(minor, GBP)


class FakeTransaction:
    """A stored row's columns without a database behind them.

    ``observe_transaction`` reads attributes and nothing else, so the cases
    about a single row -- a missing running balance, a direction that is
    neither word, an unusable page -- are cheaper and clearer tested here than
    through an insert.  The cases about *which* rows are read need the real
    query and use the fixture below.
    """

    def __init__(self, **fields):
        self.ref_id = fields.pop("ref_id", "row-1")
        self.row_index = fields.pop("row_index", 0)
        self.amount_minor = fields.pop("amount_minor", 10_00)
        self.currency = fields.pop("currency", GBP)
        self.direction = fields.pop("direction", TransactionDirection.credit.value)
        self.running_balance_minor = fields.pop("running_balance_minor", None)
        self.provenance = fields.pop("provenance", {})
        self.statement_period_id = fields.pop("statement_period_id", None)
        self.ledger_status = fields.pop(
            "ledger_status", LedgerStatus.admitted.value
        )
        for key, value in fields.items():
            setattr(self, key, value)


class ObserveTransactionTests(unittest.TestCase):
    """One stored row reduced to what the arithmetic reads."""

    def test_the_columns_become_money_and_an_enum(self):
        observation = observe_transaction(
            FakeTransaction(
                ref_id="row-7",
                row_index=3,
                amount_minor=25_00,
                direction=TransactionDirection.debit.value,
                running_balance_minor=100_00,
            )
        )

        self.assertIsInstance(observation, RowObservation)
        self.assertEqual(observation.ref_id, "row-7")
        self.assertEqual(observation.row_index, 3)
        self.assertEqual(observation.amount, gbp(25_00))
        self.assertEqual(observation.direction, TransactionDirection.debit)
        self.assertEqual(observation.running_balance, gbp(100_00))

    def test_a_row_with_no_printed_balance_says_so_rather_than_saying_zero(self):
        # A statement that prints no running balance and one that prints a
        # balance of zero are different documents.  Zero here would put a
        # fictional figure into the chain walk and manufacture a break.
        observation = observe_transaction(
            FakeTransaction(running_balance_minor=None)
        )

        self.assertIsNone(observation.running_balance)
        self.assertFalse(observation.carries_balance)

    def test_a_direction_that_is_neither_word_fails_loudly(self):
        # The alternative is summing it as though it were a debit, which
        # would move a total by twice the amount and explain nothing.
        with self.assertRaises(ValueError):
            observe_transaction(FakeTransaction(direction="sideways"))

    def test_the_page_is_carried_when_provenance_records_one(self):
        observation = observe_transaction(
            FakeTransaction(provenance={"page": 4})
        )

        self.assertEqual(observation.page, 4)

    def test_an_unusable_page_is_an_absence_rather_than_a_failure(self):
        # ``page`` is carried for citation and never read by the arithmetic,
        # so a period full of rows that can be localised perfectly well must
        # not be lost to a provenance key somebody typed as a string.
        for provenance in ({}, {"page": "4"}, {"page": None}, None, "not-a-dict"):
            with self.subTest(provenance=provenance):
                observation = observe_transaction(
                    FakeTransaction(provenance=provenance)
                )

                self.assertIsNone(observation.page)

    def test_a_boolean_page_is_not_read_as_page_one(self):
        # ``bool`` is an ``int`` in Python, so an isinstance check alone would
        # silently cite page 1 for every row whose provenance held a flag.
        observation = observe_transaction(FakeTransaction(provenance={"page": True}))

        self.assertIsNone(observation.page)


class LocalisationTestCase(unittest.TestCase):
    """A case with one account, one document and one statement period."""

    #: The printed closing balance.  Rows are added by the tests, so a period
    #: created with this closing is unbalanced until the tests make it agree.
    CLOSING = 100_00
    OPENING = 100_00

    def setUp(self):
        self._directory = tempfile.mkdtemp(prefix="loupe-localisation-")
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
            email="alex@owl.test",
            name="Alex",
            password_hash="not-used",
            global_role=GlobalRole.user,
            is_active=True,
        )
        self.case = Case(
            id=uuid.uuid4(),
            title="Localisation Fixture",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        self.evidence_file = EvidenceFile(
            id=uuid.uuid4(),
            case_id=self.case.id,
            original_filename="january-statement.pdf",
            stored_path="/evidence/january-statement.pdf",
            sha256=HASH_A,
        )
        self.db.add_all([self.user, self.case, self.evidence_file])
        self.db.commit()

        self.run = open_ingestion_run(
            case_id=self.case.id,
            actor=self.user,
            session_factory=self.SessionLocal,
        )
        self.document = record_source_document(
            self.db,
            self.run,
            SourceDocumentDraft(
                evidence_file_id=self.evidence_file.id,
                sha256_at_ingestion=HASH_A,
                document_type="bank_statement",
                shape=SourceShape.statement_document,
                extraction_layer=ExtractionLayer.structural,
                parser_name="statement_pdf",
                parser_version="1.4.0",
            ),
        )
        self.account = FinancialAccount(
            id=uuid.uuid4(),
            case_id=self.case.id,
            first_seen_run_id=self.run.run_id,
            identity_key="gb-barclays-20445561",
            institution_name="Barclays",
            identifier_as_printed="20-44-55 61",
            identifier_normalised="20445561",
            currency=GBP,
        )
        self.db.add(self.account)
        self.db.flush()
        self.period = self.make_period()
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        shutil.rmtree(self._directory, ignore_errors=True)

    def make_period(self, *, opening=_UNSET, closing=_UNSET):
        opening = self.OPENING if opening is _UNSET else opening
        closing = self.CLOSING if closing is _UNSET else closing
        # One document may cover several periods, but not two with the same
        # bounds, so each period made here occupies its own month.
        self._periods = getattr(self, "_periods", 0) + 1
        month = self._periods
        return record_statement_period(
            self.db,
            self.run,
            StatementPeriodDraft(
                account_id=self.account.id,
                source_document_id=self.document.id,
                currency=GBP,
                bounds=PeriodBounds.printed(
                    date(2024, month, 1), date(2024, month, 28)
                ),
                opening=(
                    BalanceObservation.absent()
                    if opening is None
                    else BalanceObservation.printed(gbp(opening))
                ),
                closing=(
                    BalanceObservation.absent()
                    if closing is None
                    else BalanceObservation.printed(gbp(closing))
                ),
            ),
        )

    def add_row(
        self,
        *,
        row_index: int,
        amount_minor: int,
        direction=TransactionDirection.credit,
        running_balance_minor=None,
        period=None,
    ) -> FinancialTransaction:
        (written,) = record_transactions(
            self.db,
            self.run,
            self.document,
            [
                TransactionDraft(
                    reading=RowReading(
                        currency=GBP,
                        amount_minor=amount_minor,
                        direction=direction,
                        posted_date=JANUARY,
                        running_balance_minor=running_balance_minor,
                        # Two rows of the same amount and date in one document
                        # hash identically and collide on the content-hash
                        # constraint.  Real statements distinguish them by
                        # narrative; these do the same.
                        description=f"row {row_index}",
                    ),
                    row_index=row_index,
                    account_id=self.account.id,
                    locator=Locator(kind=LocatorKind.unlocated),
                    statement_period_id=(
                        self.period.id if period is None else period.id
                    ),
                )
            ],
        )
        self.db.commit()
        return written


class ObservePeriodRowsTests(LocalisationTestCase):
    """Which rows the chain is walked over, and in what order."""

    def test_rows_come_back_in_the_statements_own_order(self):
        # Inserted out of order on purpose.  The running-balance chain is
        # meaningless in any order but the printed one, and ``row_index`` is
        # position in the source document.
        self.add_row(row_index=2, amount_minor=30_00)
        self.add_row(row_index=0, amount_minor=10_00)
        self.add_row(row_index=1, amount_minor=20_00)

        rows = observe_period_rows(self.db, period_id=self.period.id)

        self.assertEqual([row.row_index for row in rows], [0, 1, 2])
        self.assertEqual(
            [row.amount for row in rows], [gbp(10_00), gbp(20_00), gbp(30_00)]
        )

    def test_only_admitted_rows_are_read(self):
        # The filter is not tidiness.  ``localise`` compares break
        # discrepancies against a residual computed from admitted rows, so a
        # chain walked over a different population would make ``proved`` -- the
        # only verdict that is grounds -- rest on two incomparable numbers.
        self.add_row(row_index=0, amount_minor=10_00)
        set_aside = self.add_row(row_index=1, amount_minor=20_00)
        set_aside.ledger_status = LedgerStatus.quarantined.value
        set_aside.quarantine_reason = "adjudicated"
        self.db.commit()

        rows = observe_period_rows(self.db, period_id=self.period.id)

        self.assertEqual([row.row_index for row in rows], [0])

    def test_rows_of_another_period_are_not_read(self):
        other = self.make_period()
        self.db.commit()
        self.add_row(row_index=0, amount_minor=10_00)
        self.add_row(row_index=1, amount_minor=20_00, period=other)

        rows = observe_period_rows(self.db, period_id=self.period.id)

        self.assertEqual([row.amount for row in rows], [gbp(10_00)])

    def test_a_period_with_no_rows_is_an_empty_result_not_a_failure(self):
        self.assertEqual(observe_period_rows(self.db, period_id=self.period.id), ())


class CurrentIdentityTests(LocalisationTestCase):
    """The balance identity as it stands now, computed without writing."""

    def test_a_period_whose_rows_agree_with_its_closing_balance_balances(self):
        period = self.make_period(closing=self.OPENING + 25_00)
        self.db.commit()
        self.add_row(row_index=0, amount_minor=25_00, period=period)

        outcome = current_identity(self.db, period)

        self.assertEqual(outcome.status, ReconciliationStatus.balanced)
        self.assertEqual(outcome.delta, gbp(0))

    def test_a_period_whose_rows_do_not_reach_its_closing_balance_is_unbalanced(self):
        self.add_row(row_index=0, amount_minor=25_00)

        outcome = current_identity(self.db, self.period)

        self.assertEqual(outcome.status, ReconciliationStatus.unbalanced)
        # Opening 100.00 plus a 25.00 credit computes 125.00 against a printed
        # 100.00, so the identity is out by 25.00.
        self.assertEqual(outcome.delta, gbp(25_00))

    def test_a_period_with_no_printed_balances_cannot_be_checked(self):
        period = self.make_period(opening=None, closing=None)
        self.db.commit()

        outcome = current_identity(self.db, period)

        self.assertEqual(outcome.status, ReconciliationStatus.unavailable)
        self.assertIsNone(outcome.delta)

    def test_nothing_is_written_to_the_period(self):
        # ``reconcile_period`` assigns its result and flushes.  This function
        # deliberately does not, because the rescue check runs inside a
        # caller's transaction and must not leave a reconciliation behind if
        # that transaction is rolled back.
        self.add_row(row_index=0, amount_minor=25_00)
        before = self.period.reconciliation_status

        current_identity(self.db, self.period)

        self.assertEqual(self.period.reconciliation_status, before)
        self.assertNotIn(self.period, self.db.dirty)

    def test_the_stored_delta_is_not_trusted(self):
        # A period carries whatever its last reconciliation wrote.  The rescue
        # question is about the gap as it stands at the moment of the write, so
        # a stale column must not be able to answer it.
        self.add_row(row_index=0, amount_minor=25_00)
        self.period.balance_delta_minor = 999_99
        self.period.reconciliation_status = ReconciliationStatus.balanced.value
        self.db.commit()

        outcome = current_identity(self.db, self.period)

        self.assertEqual(outcome.delta, gbp(25_00))
        self.assertEqual(outcome.status, ReconciliationStatus.unbalanced)


class LocalisePeriodTests(LocalisationTestCase):
    """Accounting for a residual, and saying when there is none to account for."""

    def test_a_balancing_period_has_nothing_to_localise(self):
        # ``None`` here is not ``LocalisationStrength.none``.  This is a period
        # with no problem; that is a period with a problem nobody can place.
        self.assertIsNone(localise_period(self.db, self.period))

    def test_a_period_that_cannot_be_checked_has_nothing_to_localise(self):
        period = self.make_period(opening=None, closing=None)
        self.db.commit()

        self.assertIsNone(localise_period(self.db, period))

    def test_a_break_in_the_printed_chain_is_found_and_proves_the_residual(self):
        # Opening 100.00.  The statement prints a running balance after each
        # row.  Row 1 credits 25.00 but the printed balance jumps by 50.00, so
        # the chain breaks there by 25.00.  The rows sum to 50.00, computing a
        # closing of 150.00 against a printed 175.00: a residual of 25.00, the
        # same figure the break accounts for, which is what makes it proved.
        period = self.make_period(closing=175_00)
        self.db.commit()
        self.add_row(
            row_index=0,
            amount_minor=10_00,
            running_balance_minor=110_00,
            period=period,
        )
        self.add_row(
            row_index=1,
            amount_minor=25_00,
            running_balance_minor=160_00,
            period=period,
        )
        self.add_row(
            row_index=2,
            amount_minor=15_00,
            running_balance_minor=175_00,
            period=period,
        )

        result = localise_period(self.db, period)

        self.assertIsNotNone(result)
        self.assertEqual(result.strength, LocalisationStrength.proved)
        self.assertTrue(result.is_actionable)
        self.assertEqual([b.row_index for b in result.breaks], [1])
        self.assertEqual(result.rows_seen, 3)
        self.assertEqual(result.rows_with_balance, 3)

    def test_a_residual_no_break_accounts_for_is_not_grounds(self):
        # A period out by an amount the printed chain agrees with throughout:
        # every balance follows from the one before it, so the failure is not
        # in the rows that are present and nothing here may be quarantined.
        self.add_row(row_index=0, amount_minor=10_00, running_balance_minor=110_00)
        self.add_row(row_index=1, amount_minor=20_00, running_balance_minor=130_00)

        result = localise_period(self.db, self.period)

        self.assertIsNotNone(result)
        self.assertFalse(result.is_actionable)
        self.assertEqual(result.breaks, ())


class RescueIfRemovedTests(LocalisationTestCase):
    """Whether setting a row aside would close the gap, asked before the write."""

    def test_a_row_that_accounts_for_the_whole_residual_is_flagged(self):
        # The hazard this exists to surface: the period is out by 25.00 and
        # this row is a 25.00 credit, so removing it makes the statement
        # balance by arithmetic necessity rather than by being wrong.
        row = self.add_row(row_index=0, amount_minor=25_00)

        warning = rescue_if_removed(self.db, row)

        self.assertIsInstance(warning, RescueWarning)
        self.assertEqual(warning.residual_before, gbp(25_00))
        self.assertEqual(warning.removed, gbp(25_00))
        self.assertTrue(warning.would_balance)

    def test_a_row_that_does_not_close_the_gap_is_not_flagged(self):
        self.add_row(row_index=0, amount_minor=25_00)
        row = self.add_row(row_index=1, amount_minor=5_00)

        self.assertIsNone(rescue_if_removed(self.db, row))

    def test_a_debit_is_measured_in_the_direction_it_moves_the_total(self):
        # Removing a debit raises the computed closing.  A period out by
        # -25.00 is therefore rescued by removing a 25.00 debit, and a check
        # that ignored direction would look at the same row and see 25.00
        # against a gap of -25.00 and say no.
        row = self.add_row(
            row_index=0, amount_minor=25_00, direction=TransactionDirection.debit
        )

        warning = rescue_if_removed(self.db, row)

        self.assertIsNotNone(warning)
        self.assertEqual(warning.residual_before, gbp(-25_00))
        self.assertEqual(warning.removed, gbp(-25_00))

    def test_a_row_belonging_to_no_period_has_no_identity_to_rescue(self):
        row = self.add_row(row_index=0, amount_minor=25_00)
        row.statement_period_id = None
        self.db.commit()

        self.assertIsNone(rescue_if_removed(self.db, row))

    def test_a_row_that_is_already_set_aside_cannot_leave_the_totals_twice(self):
        self.add_row(row_index=0, amount_minor=25_00)
        row = self.add_row(row_index=1, amount_minor=25_00)
        row.ledger_status = LedgerStatus.quarantined.value
        row.quarantine_reason = "adjudicated"
        self.db.commit()

        self.assertIsNone(rescue_if_removed(self.db, row))

    def test_a_balancing_period_has_no_gap_to_close(self):
        self.add_row(row_index=0, amount_minor=25_00)
        period = self.make_period(closing=self.OPENING + 25_00)
        self.db.commit()
        row = (
            self.db.query(FinancialTransaction)
            .filter(FinancialTransaction.statement_period_id == self.period.id)
            .one()
        )
        row.statement_period_id = period.id
        self.db.commit()

        self.assertIsNone(rescue_if_removed(self.db, row))

    def test_a_period_that_cannot_be_checked_yields_no_warning(self):
        period = self.make_period(opening=None, closing=None)
        self.db.commit()
        row = self.add_row(row_index=0, amount_minor=25_00, period=period)

        self.assertIsNone(rescue_if_removed(self.db, row))

    def test_a_period_that_has_gone_from_under_the_row_yields_no_warning(self):
        # Not reachable through the foreign key today, and cheap to be exact
        # about: the alternative is an AttributeError inside a write path.
        row = self.add_row(row_index=0, amount_minor=25_00)
        row.statement_period_id = uuid.uuid4()

        self.assertIsNone(rescue_if_removed(self.db, row))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
