"""Tests for cross-period continuity.

Two halves.  The first works on :class:`PeriodLink` values directly, because
the classification of a seam is arithmetic over dates and integers and does not
need a database to be wrong in.  The second commits real periods and reads them
back, because the half above cannot show that the columns the ledger actually
stores are the columns this module reads — a service that read
``period_start`` where it meant ``period_end`` would pass every test in the
first half.

The numbers quoted in the docstrings are from the corpus this module was
measured against: 21 accounts, of which 8 hold more than one statement.
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
    BalanceSource,
    DocumentStatus,
    ExtractionLayer,
    GlobalRole,
    PeriodBoundsSource,
    ProofClass,
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
from services.financial.continuity import (
    AccountContinuity,
    ContinuityError,
    ContinuityScopeError,
    ExclusionReason,
    PeriodLink,
    SeamAgreement,
    SeamKind,
    assess_seam,
    build_run,
    order_links,
    read_account_continuity,
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
GBP = "GBP"
ACCOUNT = uuid.UUID("00000000-0000-0000-0000-0000000000aa")


def usd(minor: int) -> Money:
    return Money(minor_units=minor, currency=USD)


def link(
    start: date,
    end: date,
    *,
    opening=None,
    closing=None,
    account_id: uuid.UUID = ACCOUNT,
    period_id=None,
    currency: str = USD,
    opening_carried_from=None,
    closing_carried_from=None,
) -> PeriodLink:
    """A period reduced to what a seam is computed from."""
    return PeriodLink(
        period_id=period_id or uuid.uuid4(),
        document_id=uuid.uuid4(),
        account_id=account_id,
        currency=currency,
        start=start,
        end=end,
        opening=opening,
        closing=closing,
        opening_carried_from_period_id=opening_carried_from,
        closing_carried_from_period_id=closing_carried_from,
    )


class SeamsInTime(unittest.TestCase):
    """Where two periods meet, measured only in days."""

    def test_periods_that_abut_are_contiguous(self):
        seam = assess_seam(
            link(date(2026, 1, 1), date(2026, 1, 31)),
            link(date(2026, 2, 1), date(2026, 2, 28)),
        )
        self.assertIs(seam.kind, SeamKind.contiguous)
        self.assertEqual(seam.uncovered_days, 0)

    def test_a_missing_statement_is_a_gap_counted_in_days(self):
        """The count is of days nothing covers, not of days between dates.

        A statement ending the 31st and the next starting the 2nd leaves one
        uncovered day, not two.  An off-by-one here would report a gap after
        every month in the corpus.
        """
        seam = assess_seam(
            link(date(2026, 1, 1), date(2026, 1, 31)),
            link(date(2026, 2, 2), date(2026, 2, 28)),
        )
        self.assertIs(seam.kind, SeamKind.gap)
        self.assertEqual(seam.uncovered_days, 1)

    def test_a_whole_missing_month_is_measured_from_printed_bounds(self):
        seam = assess_seam(
            link(date(2026, 1, 1), date(2026, 1, 31)),
            link(date(2026, 3, 1), date(2026, 3, 31)),
        )
        self.assertIs(seam.kind, SeamKind.gap)
        self.assertEqual(seam.uncovered_days, 28)

    def test_periods_claiming_the_same_days_overlap(self):
        seam = assess_seam(
            link(date(2026, 1, 1), date(2026, 1, 31)),
            link(date(2026, 1, 15), date(2026, 2, 14)),
        )
        self.assertIs(seam.kind, SeamKind.overlap)
        self.assertLess(seam.uncovered_days, 0)

    def test_two_copies_of_one_statement_overlap_rather_than_abut(self):
        """Unresolved duplicates must not read as a continuous run.

        Collapsing duplicates is duplicate resolution's job.  What this module
        must not do is quietly accept two copies of January as January and
        February, which would report a continuous history built from one
        statement.
        """
        seam = assess_seam(
            link(date(2026, 1, 1), date(2026, 1, 31), closing=usd(500)),
            link(date(2026, 1, 1), date(2026, 1, 31), opening=usd(100)),
        )
        self.assertIs(seam.kind, SeamKind.overlap)
        self.assertFalse(seam.proves_continuous)


class SeamsInMoney(unittest.TestCase):
    """Whether the earlier closing balance meets the later opening balance."""

    def test_matching_balances_agree(self):
        seam = assess_seam(
            link(date(2026, 1, 1), date(2026, 1, 31), closing=usd(12345)),
            link(date(2026, 2, 1), date(2026, 2, 28), opening=usd(12345)),
        )
        self.assertIs(seam.agreement, SeamAgreement.agrees)
        self.assertIsNone(seam.discrepancy)
        self.assertTrue(seam.proves_continuous)

    def test_an_inverted_sign_is_not_a_break(self):
        """Six of the corpus's six abutting disagreements were exactly this.

        A closing of -213.91 meeting an opening of +213.91 is one number under
        two conventions, not two numbers.  Reporting it as a break would send
        an investigator looking for a missing 427.82 that never existed.
        """
        seam = assess_seam(
            link(date(2026, 1, 1), date(2026, 1, 31), closing=usd(-21391)),
            link(date(2026, 2, 1), date(2026, 2, 28), opening=usd(21391)),
        )
        self.assertIs(seam.agreement, SeamAgreement.sign_inverted)
        self.assertTrue(seam.agrees_under_a_sign_convention)
        self.assertEqual(seam.discrepancy, usd(42782))

    def test_an_inverted_sign_does_not_prove_continuity(self):
        """Reported, but not counted as proof.

        The claim rests on a convention this module did not verify, and
        ``statement_totals`` is what verifies it.  Anything short of outright
        agreement has to stay short of proof.
        """
        seam = assess_seam(
            link(date(2026, 1, 1), date(2026, 1, 31), closing=usd(-500)),
            link(date(2026, 2, 1), date(2026, 2, 28), opening=usd(500)),
        )
        self.assertFalse(seam.proves_continuous)

    def test_zero_balances_agree_rather_than_reading_as_inverted(self):
        """Zero is its own negation, and equality must be tested first."""
        seam = assess_seam(
            link(date(2026, 1, 1), date(2026, 1, 31), closing=usd(0)),
            link(date(2026, 2, 1), date(2026, 2, 28), opening=usd(0)),
        )
        self.assertIs(seam.agreement, SeamAgreement.agrees)
        self.assertTrue(seam.proves_continuous)

    def test_genuinely_different_balances_disagree(self):
        seam = assess_seam(
            link(date(2026, 1, 1), date(2026, 1, 31), closing=usd(10000)),
            link(date(2026, 2, 1), date(2026, 2, 28), opening=usd(12500)),
        )
        self.assertIs(seam.agreement, SeamAgreement.disagrees)
        self.assertEqual(seam.discrepancy, usd(2500))
        self.assertFalse(seam.proves_continuous)

    def test_a_missing_balance_is_unavailable_and_not_zero(self):
        """39 of the corpus's adjacent pairs are missing one balance.

        Treating an absent balance as zero would turn every one of them into a
        break the size of the real balance.
        """
        seam = assess_seam(
            link(date(2026, 1, 1), date(2026, 1, 31), closing=None),
            link(date(2026, 2, 1), date(2026, 2, 28), opening=usd(12345)),
        )
        self.assertIs(seam.agreement, SeamAgreement.unavailable)
        self.assertIsNone(seam.discrepancy)
        self.assertFalse(seam.proves_continuous)

    def test_a_carried_forward_opening_cannot_corroborate_its_source(self):
        """The two numbers are one number, so there is no test to pass.

        This is the case most likely to be reported as a success by accident,
        and the one where a false success is worst: a balance is carried
        forward precisely when the later statement printed none, so the
        periods with the least evidence would end up with the most.
        """
        earlier = link(date(2026, 1, 1), date(2026, 1, 31), closing=usd(9999))
        later = link(
            date(2026, 2, 1),
            date(2026, 2, 28),
            opening=usd(9999),
            opening_carried_from=earlier.period_id,
        )
        seam = assess_seam(earlier, later)
        self.assertIs(seam.agreement, SeamAgreement.circular)
        self.assertFalse(seam.proves_continuous)

    def test_a_balance_carried_forward_from_elsewhere_still_counts(self):
        """Circularity is about this seam, not about carrying in general."""
        earlier = link(date(2026, 1, 1), date(2026, 1, 31), closing=usd(9999))
        later = link(
            date(2026, 2, 1),
            date(2026, 2, 28),
            opening=usd(9999),
            opening_carried_from=uuid.uuid4(),
        )
        seam = assess_seam(earlier, later)
        self.assertIs(seam.agreement, SeamAgreement.agrees)

    def test_a_closing_carried_backwards_is_circular_too(self):
        later = link(date(2026, 2, 1), date(2026, 2, 28), opening=usd(4242))
        earlier = link(
            date(2026, 1, 1),
            date(2026, 1, 31),
            closing=usd(4242),
            closing_carried_from=later.period_id,
        )
        self.assertIs(
            assess_seam(earlier, later).agreement, SeamAgreement.circular
        )

    def test_two_currencies_are_reported_rather_than_subtracted(self):
        seam = assess_seam(
            link(date(2026, 1, 1), date(2026, 1, 31), closing=usd(100)),
            link(
                date(2026, 2, 1),
                date(2026, 2, 28),
                opening=Money(minor_units=100, currency=GBP),
                currency=GBP,
            ),
        )
        self.assertIs(seam.agreement, SeamAgreement.currency_mismatch)
        self.assertIsNone(seam.discrepancy)

    def test_a_gap_whose_balances_agree_is_flagged_for_a_human(self):
        """None of the corpus's 48 gaps agreed, which is why this is notable.

        A missing statement almost always moved the balance.  Agreement across
        one means the absent statement was empty or the two periods are not
        the neighbours they look like — either way, a person should see it.
        """
        seam = assess_seam(
            link(date(2026, 1, 1), date(2026, 1, 31), closing=usd(7777)),
            link(date(2026, 3, 1), date(2026, 3, 31), opening=usd(7777)),
        )
        self.assertIs(seam.kind, SeamKind.gap)
        self.assertIs(seam.agreement, SeamAgreement.agrees)
        self.assertTrue(seam.balance_survived_the_gap)
        self.assertFalse(
            seam.proves_continuous,
            "agreement across a gap is not evidence that nothing is missing",
        )

    def test_a_gap_with_moving_balances_is_not_flagged(self):
        seam = assess_seam(
            link(date(2026, 1, 1), date(2026, 1, 31), closing=usd(100)),
            link(date(2026, 3, 1), date(2026, 3, 31), opening=usd(900)),
        )
        self.assertFalse(seam.balance_survived_the_gap)

    def test_a_seam_joins_one_account(self):
        with self.assertRaises(ContinuityScopeError):
            assess_seam(
                link(date(2026, 1, 1), date(2026, 1, 31)),
                link(
                    date(2026, 2, 1),
                    date(2026, 2, 28),
                    account_id=uuid.uuid4(),
                ),
            )


class PeriodLinkRefusals(unittest.TestCase):
    def test_a_period_cannot_end_before_it_starts(self):
        with self.assertRaises(ContinuityError):
            link(date(2026, 2, 1), date(2026, 1, 1))

    def test_a_bare_number_is_not_a_balance(self):
        """Without a currency the comparison is meaningless, so refuse it."""
        with self.assertRaises(ContinuityError):
            link(date(2026, 1, 1), date(2026, 1, 31), closing=12345)

    def test_span_counts_both_endpoints(self):
        self.assertEqual(link(date(2026, 1, 1), date(2026, 1, 1)).span_days, 1)
        self.assertEqual(link(date(2026, 1, 1), date(2026, 1, 31)).span_days, 31)


class Enclosure(unittest.TestCase):
    """Multi-year exports are a coarser grain, not a neighbouring period."""

    def test_a_longer_period_containing_another_encloses_it(self):
        export = link(date(2020, 1, 1), date(2021, 12, 31))
        month = link(date(2020, 6, 1), date(2020, 6, 30))
        self.assertTrue(export.encloses(month))
        self.assertFalse(month.encloses(export))

    def test_identical_spans_do_not_enclose_each_other(self):
        """Otherwise duplicate resolution would happen here, by accident.

        Two periods covering the same dates are duplicates or a contradiction.
        Discarding one of them under the name of enclosure would settle that
        question silently and in the wrong module.
        """
        a = link(date(2026, 1, 1), date(2026, 1, 31))
        b = link(date(2026, 1, 1), date(2026, 1, 31))
        self.assertFalse(a.encloses(b))
        self.assertFalse(b.encloses(a))

    def test_an_enclosing_period_is_set_aside_with_a_reason(self):
        export = link(date(2020, 1, 1), date(2020, 12, 31))
        jan = link(date(2020, 1, 1), date(2020, 1, 31))
        feb = link(date(2020, 2, 1), date(2020, 2, 29))
        kept, excluded = order_links([export, jan, feb])

        self.assertEqual([l.period_id for l in kept], [jan.period_id, feb.period_id])
        self.assertEqual(len(excluded), 1)
        self.assertEqual(excluded[0].period_id, export.period_id)
        self.assertIs(excluded[0].reason, ExclusionReason.enclosing)
        self.assertIn("2 shorter period(s)", excluded[0].detail)

    def test_removing_the_export_reveals_the_seam_it_hid(self):
        """The whole point of the exclusion, stated as a test.

        With the export in the run, January and February each overlap it and
        the contiguous seam between them is never assessed.  This is the
        corpus's ``USA-ET-005974.pdf``, which spans nine months and carries no
        balances at all.
        """
        export = link(date(2020, 1, 1), date(2020, 12, 31))
        jan = link(date(2020, 1, 1), date(2020, 1, 31), closing=usd(5000))
        feb = link(date(2020, 2, 1), date(2020, 2, 29), opening=usd(5000))

        kept, _ = order_links([export, jan, feb])
        seams = [assess_seam(a, b) for a, b in zip(kept, kept[1:])]

        self.assertEqual(len(seams), 1)
        self.assertTrue(seams[0].proves_continuous)

    def test_ordering_is_stable_for_identical_bounds(self):
        """A run that changes shape between reads cannot be evidence."""
        ids = [uuid.UUID(int=i) for i in (3, 1, 2)]
        links = [
            link(date(2026, 1, 1), date(2026, 1, 31), period_id=i) for i in ids
        ]
        first, _ = order_links(links)
        second, _ = order_links(list(reversed(links)))
        self.assertEqual(
            [l.period_id for l in first], [l.period_id for l in second]
        )


class RunSummary(unittest.TestCase):
    """What a run says once every seam in it has been read."""

    def make_run(self, *links) -> AccountContinuity:
        kept, excluded = order_links(links)
        return AccountContinuity(
            account_id=ACCOUNT,
            periods=tuple(kept),
            seams=tuple(
                assess_seam(a, b) for a, b in zip(kept, kept[1:])
            ),
            excluded=tuple(excluded),
        )

    def test_an_unbroken_run_reports_no_gaps_and_no_breaks(self):
        run = self.make_run(
            link(date(2026, 1, 1), date(2026, 1, 31), closing=usd(100)),
            link(
                date(2026, 2, 1), date(2026, 2, 28),
                opening=usd(100), closing=usd(250),
            ),
            link(date(2026, 3, 1), date(2026, 3, 31), opening=usd(250)),
        )
        self.assertEqual(run.gaps, ())
        self.assertEqual(run.breaks, ())
        self.assertEqual(run.uncovered_days, 0)
        self.assertTrue(run.is_unbroken)
        self.assertEqual(run.covered_from, date(2026, 1, 1))
        self.assertEqual(run.covered_to, date(2026, 3, 31))

    def test_one_period_is_not_a_continuous_history(self):
        """A single statement has no seam, so it is evidence of nothing here.

        Reporting ``is_unbroken`` for it would let an account represented by
        one month of a five-year matter look complete.
        """
        run = self.make_run(link(date(2026, 1, 1), date(2026, 1, 31)))
        self.assertEqual(run.seams, ())
        self.assertFalse(run.is_unbroken)

    def test_an_empty_run_is_not_unbroken(self):
        run = AccountContinuity(account_id=ACCOUNT)
        self.assertFalse(run.is_unbroken)
        self.assertIsNone(run.covered_from)
        self.assertIsNone(run.covered_to)

    def test_uncovered_days_totals_only_the_gaps(self):
        run = self.make_run(
            link(date(2026, 1, 1), date(2026, 1, 31)),
            link(date(2026, 3, 1), date(2026, 3, 31)),
            link(date(2026, 5, 1), date(2026, 5, 31)),
        )
        self.assertEqual(len(run.gaps), 2)
        self.assertEqual(run.uncovered_days, 28 + 30)
        self.assertFalse(run.is_unbroken)

    def test_a_sign_inversion_is_not_counted_as_a_break(self):
        """``breaks`` is what an investigator is asked to explain.

        Putting a convention in it would have produced six false leads in the
        measured corpus and no true ones.
        """
        run = self.make_run(
            link(date(2026, 1, 1), date(2026, 1, 31), closing=usd(-500)),
            link(date(2026, 2, 1), date(2026, 2, 28), opening=usd(500)),
        )
        self.assertEqual(run.breaks, ())
        self.assertFalse(run.is_unbroken)
        self.assertTrue(run.seams[0].agrees_under_a_sign_convention)

    def test_overlaps_are_reported_separately_from_gaps(self):
        run = self.make_run(
            link(date(2026, 1, 1), date(2026, 1, 31)),
            link(date(2026, 1, 15), date(2026, 2, 14)),
        )
        self.assertEqual(len(run.overlaps), 1)
        self.assertEqual(run.gaps, ())
        self.assertEqual(run.uncovered_days, 0)


class ContinuitySurvivesTheDatabase(unittest.TestCase):
    """The same readings, taken from committed periods.

    Everything above operates on values built in the test.  What that cannot
    show is that the columns this module reads are the columns the ledger
    writes: a reading that took ``period_start`` for ``period_end``, or read
    the opening balance into the closing slot, would satisfy every assertion
    above and be wrong on every real account.
    """

    def setUp(self):
        self._directory = tempfile.mkdtemp(prefix="loupe-continuity-")
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
            title="Continuity Fixture",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        self.account = FinancialAccount(
            id=uuid.uuid4(),
            case_id=self.case.id,
            identity_key="us-example-0440",
            institution_name="Example Bank",
            identifier_as_printed="****0440",
            identifier_normalised="0440",
            currency=USD,
        )
        self.db.add_all([self.user, self.case, self.account])
        self.db.commit()

        self.run = open_ingestion_run(
            case_id=self.case.id,
            actor=self.user,
            session_factory=self.SessionLocal,
        )
        self._seq = 0

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        shutil.rmtree(self._directory, ignore_errors=True)

    # -- fixtures ----------------------------------------------------------

    def make_document(self, status: str = DocumentStatus.admitted.value):
        self._seq += 1
        digest = f"{self._seq:064d}"
        evidence_file = EvidenceFile(
            id=uuid.uuid4(),
            case_id=self.case.id,
            original_filename=f"statement-{self._seq}.pdf",
            stored_path=f"/evidence/statement-{self._seq}.pdf",
            sha256=digest,
        )
        self.db.add(evidence_file)
        self.db.flush()
        document = FinancialSourceDocument(
            id=uuid.uuid4(),
            evidence_file_id=evidence_file.id,
            sha256_at_ingestion=digest,
            document_type="bank_statement",
            proof_class=ProofClass.p2.value,
            extraction_layer=ExtractionLayer.structural.value,
            parser_name="statement_pdf",
            parser_version="1.4.0",
            status=status,
        )
        self.db.add(self.run.stamp(document))
        self.db.commit()
        return document

    def make_period(
        self,
        start,
        end,
        *,
        opening=None,
        closing=None,
        start_source=PeriodBoundsSource.printed,
        end_source=PeriodBoundsSource.printed,
        status: str = DocumentStatus.admitted.value,
    ):
        document = self.make_document(status=status)

        def observed(amount):
            if amount is None:
                return BalanceObservation(source=BalanceSource.absent)
            return BalanceObservation(
                source=BalanceSource.printed, amount=amount
            )

        return record_statement_period(
            self.db,
            self.run,
            StatementPeriodDraft(
                account_id=self.account.id,
                source_document_id=document.id,
                currency=USD,
                bounds=PeriodBounds(
                    start=start,
                    end=end,
                    start_source=start_source,
                    end_source=end_source,
                ),
                opening=observed(opening),
                closing=observed(closing),
            ),
        )

    # -- tests -------------------------------------------------------------

    def test_a_committed_run_reads_back_as_continuous(self):
        self.make_period(
            date(2026, 1, 1), date(2026, 1, 31), opening=usd(1000), closing=usd(2500)
        )
        self.make_period(
            date(2026, 2, 1), date(2026, 2, 28), opening=usd(2500), closing=usd(3100)
        )
        self.db.commit()

        run = read_account_continuity(
            self.db, case_id=self.case.id, account_id=self.account.id
        )
        self.assertEqual(len(run.periods), 2)
        self.assertEqual(len(run.seams), 1)
        self.assertTrue(run.is_unbroken)
        self.assertEqual(run.covered_from, date(2026, 1, 1))
        self.assertEqual(run.covered_to, date(2026, 2, 28))

    def test_the_balances_are_read_into_the_slots_they_were_written_to(self):
        """Guards the mix-up a value-only test cannot see.

        The two periods are chosen so that reading opening for closing would
        still produce a seam, but the wrong one: it would report agreement
        where the truth is a break, which is the direction that matters.
        """
        self.make_period(
            date(2026, 1, 1), date(2026, 1, 31), opening=usd(4000), closing=usd(9000)
        )
        self.make_period(
            date(2026, 2, 1), date(2026, 2, 28), opening=usd(4000), closing=usd(1000)
        )
        self.db.commit()

        run = read_account_continuity(
            self.db, case_id=self.case.id, account_id=self.account.id
        )
        seam = run.seams[0]
        self.assertIs(seam.agreement, SeamAgreement.disagrees)
        self.assertEqual(seam.earlier.closing, usd(9000))
        self.assertEqual(seam.later.opening, usd(4000))
        self.assertEqual(seam.discrepancy, usd(-5000))

    def test_a_gap_between_committed_periods_is_found(self):
        self.make_period(
            date(2026, 1, 1), date(2026, 1, 31), opening=usd(100), closing=usd(500)
        )
        self.make_period(
            date(2026, 3, 1), date(2026, 3, 31), opening=usd(900), closing=usd(950)
        )
        self.db.commit()

        run = read_account_continuity(
            self.db, case_id=self.case.id, account_id=self.account.id
        )
        self.assertEqual(len(run.gaps), 1)
        self.assertEqual(run.uncovered_days, 28)
        self.assertFalse(run.is_unbroken)

    def test_a_superseded_duplicate_is_excluded_from_the_run(self):
        """83 of the first survey's 87 phantom overlaps came from this.

        A duplicate left in the run makes an account appear to double back on
        itself once per duplicate group, and buries the real seam underneath.
        """
        self.make_period(
            date(2026, 1, 1), date(2026, 1, 31), opening=usd(100), closing=usd(500)
        )
        self.make_period(
            date(2026, 1, 1),
            date(2026, 1, 31),
            opening=usd(100),
            closing=usd(500),
            status=DocumentStatus.superseded.value,
        )
        self.make_period(
            date(2026, 2, 1), date(2026, 2, 28), opening=usd(500), closing=usd(700)
        )
        self.db.commit()

        run = read_account_continuity(
            self.db, case_id=self.case.id, account_id=self.account.id
        )
        self.assertEqual(len(run.periods), 2)
        self.assertEqual(run.overlaps, ())
        self.assertTrue(run.is_unbroken)

        set_aside = [e for e in run.excluded if e.reason is ExclusionReason.not_admitted]
        self.assertEqual(len(set_aside), 1)
        self.assertEqual(set_aside[0].detail, DocumentStatus.superseded.value)

    def test_a_derived_bound_is_excluded_because_it_would_invent_a_gap(self):
        """A bound read off the rows shrinks to fit whatever was extracted.

        Comparing it with a neighbour asks whether the extraction agrees with
        itself.  ``PeriodBounds.supports_continuity`` says so, and this is the
        assertion that the reading actually consults it.
        """
        self.make_period(
            date(2026, 1, 1), date(2026, 1, 31), opening=usd(100), closing=usd(500)
        )
        self.make_period(
            date(2026, 2, 3),
            date(2026, 2, 26),
            opening=usd(500),
            closing=usd(700),
            start_source=PeriodBoundsSource.derived,
            end_source=PeriodBoundsSource.derived,
        )
        self.db.commit()

        run = read_account_continuity(
            self.db, case_id=self.case.id, account_id=self.account.id
        )
        self.assertEqual(len(run.periods), 1)
        self.assertEqual(run.seams, ())
        self.assertEqual(
            [e.reason for e in run.excluded], [ExclusionReason.derived_bounds]
        )

    def test_an_undated_period_is_set_aside_rather_than_placed(self):
        """A period with no bounds cannot be ordered, so it cannot be joined.

        The schema keeps a unique index reserved for exactly this row, so an
        undated period is an expected inhabitant of the table rather than a
        malformed one.  It is set aside with a reason, because dropping it
        silently would let a document vanish from the account's history
        without anything recording that it had been seen at all.

        Mutation testing found this branch untested: admitting undated
        periods to the run broke nothing.
        """
        self.make_period(
            date(2026, 1, 1), date(2026, 1, 31), opening=usd(100), closing=usd(500)
        )
        undated = self.make_period(
            None,
            None,
            opening=usd(500),
            closing=usd(700),
            start_source=PeriodBoundsSource.absent,
            end_source=PeriodBoundsSource.absent,
        )
        self.db.commit()

        run = read_account_continuity(
            self.db, case_id=self.case.id, account_id=self.account.id
        )
        self.assertEqual(len(run.periods), 1)
        self.assertEqual(run.seams, ())
        self.assertEqual(
            [e.reason for e in run.excluded], [ExclusionReason.undated]
        )
        self.assertEqual(run.excluded[0].period_id, undated.id)

    def test_an_account_with_no_periods_reads_as_empty(self):
        run = read_account_continuity(
            self.db, case_id=self.case.id, account_id=self.account.id
        )
        self.assertEqual(run.periods, ())
        self.assertEqual(run.seams, ())
        self.assertFalse(run.is_unbroken)

    def test_the_reading_is_scoped_to_the_case(self):
        """The account id alone is unique; depending on that is a leak waiting.

        Asking for this account under another case must return nothing rather
        than the periods themselves.
        """
        self.make_period(
            date(2026, 1, 1), date(2026, 1, 31), opening=usd(100), closing=usd(500)
        )
        self.db.commit()

        run = read_account_continuity(
            self.db, case_id=uuid.uuid4(), account_id=self.account.id
        )
        self.assertEqual(run.periods, ())

    def test_build_run_refuses_periods_from_two_accounts(self):
        other = FinancialAccount(
            id=uuid.uuid4(),
            case_id=self.case.id,
            identity_key="us-example-9299",
            institution_name="Example Bank",
            identifier_as_printed="****9299",
            identifier_normalised="9299",
            currency=USD,
        )
        self.db.add(other)
        self.db.commit()

        mine = self.make_period(
            date(2026, 1, 1), date(2026, 1, 31), opening=usd(100), closing=usd(500)
        )
        theirs = self.make_period(
            date(2026, 2, 1), date(2026, 2, 28), opening=usd(500), closing=usd(700)
        )
        theirs.account_id = other.id
        self.db.commit()

        with self.assertRaises(ContinuityScopeError):
            build_run([mine, theirs])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
