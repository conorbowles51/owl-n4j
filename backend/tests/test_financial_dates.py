"""Tests for row date plausibility and period coverage.

The danger here is the mirror image of the one in quarantine.py.  There, a
localiser trusting its own guess would launder failing statements into clean
ones.  Here, a date check trusting its own notion of "implausible" would do
the opposite: it would discard good evidence.  In the corpus this module was
measured against, treating "outside the stated period" as a fault in the row
would have set aside 343 rows, of which 332 sit in a single document whose
rows are almost certainly right and whose period is almost certainly a misread
aggregate over a multi-statement PDF.  Most of what follows exists to prove
that cannot happen: that only a proved impossibility yields grounds, that the
refusal is by construction rather than by a caller remembering to check, and
that a period which cannot be trusted is recorded as unchecked rather than as
passed.

The three corpus figures quoted below — one impossible row, 343 out-of-period
rows in four documents, and four documents whose rows span more time than
their period allows — are what the module was built from, and the arithmetic
that produced each is reproduced here on synthetic rows.

No case material appears here.  The dates are round, the amounts absent, and
the one 24th-century date is the shape of the corpus defect rather than its
content.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
import uuid
from dataclasses import FrozenInstanceError
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import (
    DateSource,
    ExtractionLayer,
    GlobalRole,
    LedgerStatus,
    PeriodBoundsSource,
    ProofClass,
    QuarantineReason,
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
from services.financial.dates import (
    CoverageFinding,
    DateCoherenceError,
    DatePlausibility,
    DateFinding,
    RowDate,
    UngroundedDateQuarantineError,
    check_row_date,
    read_row_date,
    survey_row_dates,
)
from services.financial.money import Money
from services.financial.periods import (
    BalanceObservation,
    PeriodBounds,
    StatementPeriodDraft,
    record_statement_period,
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

# The moment the document was read.  Always supplied, never inferred.
READ_ON = date(2026, 3, 1)

JANUARY = PeriodBounds.printed(date(2026, 1, 1), date(2026, 1, 31))


def row(index: int, value: date, source: DateSource = DateSource.transaction) -> RowDate:
    return RowDate(row_index=index, value=value, source=source)


class RowDateTests(unittest.TestCase):
    """What a row date refuses to be."""

    def test_a_datetime_is_refused_even_though_it_is_a_date(self):
        # datetime subclasses date, so an isinstance check would let it
        # through, and it would then carry a time component into a Date column
        # and into every comparison the module makes.
        with self.assertRaises(DateCoherenceError) as caught:
            RowDate(0, datetime(2026, 1, 15, 9, 30), DateSource.transaction)
        self.assertIn("must be a date", str(caught.exception))

    def test_a_negative_row_index_is_refused(self):
        with self.assertRaises(DateCoherenceError):
            RowDate(-1, date(2026, 1, 15), DateSource.transaction)

    def test_a_bare_string_source_is_refused(self):
        # The column stores a string, so a caller passing the stored value
        # straight back in would otherwise construct a row whose source could
        # never match a DateSource comparison.
        with self.assertRaises(DateCoherenceError):
            RowDate(0, date(2026, 1, 15), "transaction")

    def test_a_row_date_cannot_be_mutated_after_construction(self):
        r = row(0, date(2026, 1, 15))
        with self.assertRaises(FrozenInstanceError):
            r.value = date(2026, 2, 15)


class ImpossibilityTests(unittest.TestCase):
    """The one row-level conclusion that needs no invented constant.

    The corpus contains exactly one provably wrong date: a row dated
    ``2321-10-08`` between neighbours dated 2020-06-06 and 2021-10-12.  It is
    caught not by an opinion about which years are reasonable but by the
    observation that a statement cannot print a transaction which has not
    happened yet.
    """

    def test_a_row_dated_after_the_document_was_read_is_disproved(self):
        finding = check_row_date(
            row(3, date(2321, 10, 8)), bounds=JANUARY, observed_at=READ_ON
        )
        self.assertIs(finding.plausibility, DatePlausibility.impossible_future)
        self.assertTrue(finding.is_provably_wrong)

    def test_the_impossibility_is_found_before_the_period_is_consulted(self):
        # This is the corpus case exactly: the document whose row was misread
        # as 2321 also had its period end derived from that same row, so a
        # check that consulted the period first would have found nothing
        # wrong.  The impossibility test must not depend on any other
        # extracted field being right.
        contaminated = PeriodBounds.derived(date(2020, 5, 18), date(2321, 10, 8))
        finding = check_row_date(
            row(3, date(2321, 10, 8)), bounds=contaminated, observed_at=READ_ON
        )
        self.assertIs(finding.plausibility, DatePlausibility.impossible_future)

    def test_a_row_dated_on_the_day_of_reading_is_not_disproved(self):
        # The boundary belongs to the possible side: a statement read on the
        # day of its last transaction is ordinary.
        finding = check_row_date(
            row(0, READ_ON),
            bounds=PeriodBounds.printed(date(2026, 2, 1), date(2026, 3, 31)),
            observed_at=READ_ON,
        )
        self.assertIsNot(finding.plausibility, DatePlausibility.impossible_future)

    def test_an_implausibly_old_row_is_not_disproved(self):
        # The corpus contains no implausibly old row, so no rule is invented
        # to catch one.  A 1970 date on a 2026 statement is odd, but "odd" is
        # not a finding this module is entitled to make, and a minimum year
        # would be a guess that discards evidence.
        finding = check_row_date(
            row(0, date(1970, 1, 1)), bounds=JANUARY, observed_at=READ_ON
        )
        self.assertIs(finding.plausibility, DatePlausibility.outside_printed_period)
        self.assertFalse(finding.is_provably_wrong)

    def test_the_module_never_reads_a_clock(self):
        # A finding that changes with the day it was computed cannot be
        # reproduced from the record.  There is no default anchor.
        with self.assertRaises(TypeError):
            check_row_date(row(0, date(2026, 1, 15)), bounds=JANUARY)

    def test_a_datetime_anchor_is_refused(self):
        with self.assertRaises(DateCoherenceError) as caught:
            check_row_date(
                row(0, date(2026, 1, 15)),
                bounds=JANUARY,
                observed_at=datetime(2026, 3, 1, 12, 0),
            )
        self.assertIn("never reads a clock", str(caught.exception))


class GroundsTests(unittest.TestCase):
    """What may and may not be used to set a row aside.

    This is the class that matters most.  Quarantining on the out-of-period
    signal would have removed 343 corpus rows, the majority of them good.
    """

    def test_a_disproved_row_yields_grounds_naming_the_contradiction(self):
        finding = check_row_date(
            row(3, date(2321, 10, 8)), bounds=JANUARY, observed_at=READ_ON
        )
        basis = finding.grounds()
        self.assertEqual(basis.reason, QuarantineReason.unreadable_row)
        self.assertIn("2321-10-08", basis.detail)
        self.assertIn("has not happened", basis.detail)

    def test_an_out_of_period_row_refuses_to_yield_grounds(self):
        finding = check_row_date(
            row(0, date(2025, 12, 15)), bounds=JANUARY, observed_at=READ_ON
        )
        self.assertIs(finding.plausibility, DatePlausibility.outside_printed_period)
        with self.assertRaises(UngroundedDateQuarantineError) as caught:
            finding.grounds()
        self.assertIn("not grounds against the row", str(caught.exception))

    def test_an_ordinary_row_refuses_to_yield_grounds(self):
        finding = check_row_date(
            row(0, date(2026, 1, 15)), bounds=JANUARY, observed_at=READ_ON
        )
        with self.assertRaises(UngroundedDateQuarantineError):
            finding.grounds()

    def test_an_unchecked_row_refuses_to_yield_grounds(self):
        finding = check_row_date(
            row(0, date(2026, 1, 15)),
            bounds=PeriodBounds.absent(),
            observed_at=READ_ON,
        )
        with self.assertRaises(UngroundedDateQuarantineError):
            finding.grounds()

    def test_every_plausibility_except_the_proof_refuses_grounds(self):
        # Structural rather than enumerated by hand, so that a plausibility
        # added later must be considered here rather than defaulting into
        # being grounds for discarding evidence.
        for plausibility in DatePlausibility:
            outside = plausibility is DatePlausibility.outside_printed_period
            finding = DateFinding(
                row=row(0, date(2026, 1, 15)),
                plausibility=plausibility,
                observed_at=READ_ON,
                days_outside=17 if outside else 0,
            )
            if plausibility is DatePlausibility.impossible_future:
                self.assertEqual(
                    finding.grounds().reason, QuarantineReason.unreadable_row
                )
            else:
                with self.assertRaises(UngroundedDateQuarantineError):
                    finding.grounds()


class DerivedBoundsTests(unittest.TestCase):
    """A bound inferred from the rows cannot be used to check those rows."""

    def test_rows_are_not_compared_against_derived_bounds(self):
        finding = check_row_date(
            row(0, date(2019, 1, 1)),
            bounds=PeriodBounds.derived(date(2026, 1, 1), date(2026, 1, 31)),
            observed_at=READ_ON,
        )
        self.assertIs(finding.plausibility, DatePlausibility.unchecked_derived_bounds)

    def test_a_half_derived_period_is_still_not_usable(self):
        half = PeriodBounds(
            start=date(2026, 1, 1),
            end=date(2026, 1, 31),
            start_source=PeriodBoundsSource.printed,
            end_source=PeriodBoundsSource.derived,
        )
        finding = check_row_date(
            row(0, date(2026, 2, 20)), bounds=half, observed_at=READ_ON
        )
        self.assertIs(finding.plausibility, DatePlausibility.unchecked_derived_bounds)

    def test_absent_bounds_are_distinguished_from_derived_ones(self):
        finding = check_row_date(
            row(0, date(2026, 1, 15)),
            bounds=PeriodBounds.absent(),
            observed_at=READ_ON,
        )
        self.assertIs(finding.plausibility, DatePlausibility.unchecked_absent_bounds)

    def test_unchecked_is_not_reported_as_checked(self):
        # "Not checked" and "checked and fine" are different states and only
        # one of them is reassuring.  Collapsing them would let an unreadable
        # period silently certify every row beneath it.
        for bounds in (
            PeriodBounds.absent(),
            PeriodBounds.derived(date(2026, 1, 1), date(2026, 1, 31)),
        ):
            finding = check_row_date(
                row(0, date(2026, 1, 15)), bounds=bounds, observed_at=READ_ON
            )
            self.assertFalse(finding.was_checked)


class FindingCoherenceTests(unittest.TestCase):
    """A finding may not describe a comparison it did not make."""

    def test_an_outside_finding_must_say_by_how_far(self):
        with self.assertRaises(DateCoherenceError):
            DateFinding(
                row=row(0, date(2025, 12, 1)),
                plausibility=DatePlausibility.outside_printed_period,
                observed_at=READ_ON,
                days_outside=0,
            )

    def test_a_finding_that_made_no_comparison_may_not_carry_a_distance(self):
        with self.assertRaises(DateCoherenceError):
            DateFinding(
                row=row(0, date(2026, 1, 15)),
                plausibility=DatePlausibility.unchecked_absent_bounds,
                observed_at=READ_ON,
                days_outside=9,
            )

    def test_the_distance_is_measured_to_the_nearer_bound(self):
        before = check_row_date(
            row(0, date(2025, 12, 22)), bounds=JANUARY, observed_at=READ_ON
        )
        self.assertEqual(before.days_outside, 10)
        after = check_row_date(
            row(1, date(2026, 2, 10)), bounds=JANUARY, observed_at=READ_ON
        )
        self.assertEqual(after.days_outside, 10)

    def test_the_period_bounds_themselves_are_inside(self):
        for value in (date(2026, 1, 1), date(2026, 1, 31)):
            finding = check_row_date(row(0, value), bounds=JANUARY, observed_at=READ_ON)
            self.assertIs(finding.plausibility, DatePlausibility.within_printed_period)


class CoverageTests(unittest.TestCase):
    """Whether a period and its rows describe the same statement.

    The proof is that if the rows span more calendar time than the period
    provides, no assignment of blame to individual dates can reconcile them.
    It needs no threshold, which matters because the four corpus documents
    exceed their periods by ratios of 12.93, 2.63, 1.16 and 1.01 — no
    percentage separates the last of those from an ordinary document.
    """

    def test_rows_inside_the_period_are_covered(self):
        survey = survey_row_dates(
            [row(0, date(2026, 1, 5)), row(1, date(2026, 1, 20))],
            bounds=JANUARY,
            observed_at=READ_ON,
        )
        self.assertIs(survey.coverage, CoverageFinding.covered)
        self.assertFalse(survey.period_cannot_cover_the_rows)

    def test_rows_outside_a_period_they_would_still_fit_in_are_not_a_contradiction(self):
        # Consistent with an offset period, or with individual misread dates.
        # This module does not choose between them, and says so by declining
        # to call it a contradiction.
        survey = survey_row_dates(
            [row(0, date(2026, 2, 3)), row(1, date(2026, 2, 20))],
            bounds=JANUARY,
            observed_at=READ_ON,
        )
        self.assertIs(survey.coverage, CoverageFinding.rows_outside)
        self.assertFalse(survey.period_cannot_cover_the_rows)
        self.assertEqual(len(survey.outside), 2)

    def test_rows_spanning_more_time_than_the_period_are_a_contradiction(self):
        # The shape of USA-ET-004653: rows spanning 1435 days under a period
        # stating 545.
        survey = survey_row_dates(
            [row(0, date(2026, 1, 10)), row(1, date(2026, 2, 25))],
            bounds=JANUARY,
            observed_at=READ_ON,
        )
        self.assertEqual(survey.stated_span_days, 30)
        self.assertEqual(survey.observed_span_days, 46)
        self.assertIs(survey.coverage, CoverageFinding.span_contradiction)
        self.assertTrue(survey.period_cannot_cover_the_rows)

    def test_a_single_day_of_excess_is_still_a_contradiction(self):
        # The shape of USA-ET-006246: 183 observed days against 182 stated.
        # A threshold tuned to catch the other three would have missed this.
        bounds = PeriodBounds.printed(date(2026, 1, 1), date(2026, 1, 11))
        survey = survey_row_dates(
            [row(0, date(2026, 1, 1)), row(1, date(2026, 1, 12))],
            bounds=bounds,
            observed_at=READ_ON,
        )
        self.assertEqual(survey.stated_span_days, 10)
        self.assertEqual(survey.observed_span_days, 11)
        self.assertIs(survey.coverage, CoverageFinding.span_contradiction)

    def test_one_disproved_row_cannot_manufacture_a_contradiction(self):
        # This is the trap.  A single 24th-century misread would otherwise
        # make every document it appears in look like a multi-statement PDF,
        # and the conclusion "this period does not cover these rows" would be
        # drawn from the one row already known to be wrong.
        survey = survey_row_dates(
            [
                row(0, date(2026, 1, 5)),
                row(1, date(2321, 10, 8)),
                row(2, date(2026, 1, 20)),
            ],
            bounds=JANUARY,
            observed_at=READ_ON,
        )
        self.assertEqual(len(survey.impossible), 1)
        self.assertEqual(survey.observed_span_days, 15)
        self.assertIs(survey.coverage, CoverageFinding.covered)
        self.assertFalse(survey.period_cannot_cover_the_rows)

    def test_coverage_is_not_asserted_over_bounds_that_were_not_checked(self):
        for bounds in (
            PeriodBounds.absent(),
            PeriodBounds.derived(date(2026, 1, 1), date(2026, 1, 2)),
        ):
            survey = survey_row_dates(
                [row(0, date(2020, 1, 1)), row(1, date(2026, 6, 1))],
                bounds=bounds,
                observed_at=READ_ON,
            )
            self.assertIs(survey.coverage, CoverageFinding.not_checkable)
            self.assertFalse(survey.period_cannot_cover_the_rows)
            self.assertEqual(survey.checked_count, 0)

    def test_a_survey_counts_only_the_rows_it_actually_compared(self):
        survey = survey_row_dates(
            [row(0, date(2026, 1, 5)), row(1, date(2321, 10, 8))],
            bounds=JANUARY,
            observed_at=READ_ON,
        )
        self.assertEqual(survey.checked_count, 1)

    def test_an_empty_document_reports_no_span(self):
        survey = survey_row_dates([], bounds=JANUARY, observed_at=READ_ON)
        self.assertIsNone(survey.observed_span_days)
        self.assertIs(survey.coverage, CoverageFinding.covered)


class StoredRowTests(unittest.TestCase):
    """The columns the ledger stores are the columns this module reads.

    Everything above works on value objects, and would pass unchanged if
    ``read_row_date`` took ``posted_date`` where it meant ``ordering_date``.
    """

    def setUp(self):
        self._directory = tempfile.mkdtemp()
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
            title="Dates Fixture",
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
                bounds=JANUARY,
                opening=BalanceObservation.printed(
                    Money.from_decimal(Decimal("1000.00"), USD)
                ),
                closing=BalanceObservation.printed(
                    Money.from_decimal(Decimal("1200.00"), USD)
                ),
            ),
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        shutil.rmtree(self._directory, ignore_errors=True)

    def add_row(self, *, row_index, ordering, posted, source):
        stored = FinancialTransaction(
            id=uuid.uuid4(),
            account_id=self.account.id,
            source_document_id=self.document.id,
            statement_period_id=self.period.id,
            ref_id=f"row-{row_index:04d}",
            row_index=row_index,
            amount_minor=5000,
            currency=USD,
            direction=TransactionDirection.credit.value,
            transaction_date=ordering,
            posted_date=posted,
            ordering_date=ordering,
            ordering_date_source=source.value,
            description=f"row {row_index}",
            proof_class=ProofClass.p2.value,
            extraction_layer=ExtractionLayer.structural.value,
            ledger_status=LedgerStatus.admitted.value,
            content_hash=f"{row_index:064d}",
        )
        self.db.add(self.run.stamp(stored))
        self.db.commit()
        return stored

    def test_a_stored_row_reads_back_its_ordering_date_and_not_another(self):
        stored = self.add_row(
            row_index=7,
            ordering=date(2026, 1, 15),
            posted=date(2026, 1, 18),
            source=DateSource.transaction,
        )
        recovered = read_row_date(stored)
        self.assertEqual(recovered.row_index, 7)
        self.assertEqual(recovered.value, date(2026, 1, 15))
        self.assertIs(recovered.source, DateSource.transaction)

    def test_the_stored_source_string_becomes_the_enum_it_names(self):
        stored = self.add_row(
            row_index=8,
            ordering=date(2026, 1, 20),
            posted=date(2026, 1, 20),
            source=DateSource.posted,
        )
        self.assertIs(read_row_date(stored).source, DateSource.posted)

    def test_a_stored_row_survives_the_round_trip_into_a_finding(self):
        stored = self.add_row(
            row_index=9,
            ordering=date(2025, 12, 20),
            posted=date(2025, 12, 20),
            source=DateSource.transaction,
        )
        self.db.expire_all()
        reloaded = self.db.get(FinancialTransaction, stored.id)
        finding = check_row_date(
            read_row_date(reloaded), bounds=JANUARY, observed_at=READ_ON
        )
        self.assertIs(finding.plausibility, DatePlausibility.outside_printed_period)
        self.assertEqual(finding.days_outside, 12)

    def test_which_date_was_chosen_does_not_change_the_verdict(self):
        # A transaction date and a posted date are checked identically; the
        # arithmetic of "before the period started" does not care which column
        # the value came from.  The source is recorded so the choice can be
        # reviewed, not so it can change the answer.
        findings = []
        for index, source in enumerate(
            (DateSource.transaction, DateSource.posted, DateSource.value), start=20
        ):
            stored = self.add_row(
                row_index=index,
                ordering=date(2026, 2, 14),
                posted=date(2026, 2, 14),
                source=source,
            )
            findings.append(
                check_row_date(
                    read_row_date(stored), bounds=JANUARY, observed_at=READ_ON
                )
            )
        self.assertEqual(
            {f.plausibility for f in findings},
            {DatePlausibility.outside_printed_period},
        )
        self.assertEqual({f.days_outside for f in findings}, {14})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
