"""Tests for duplicate document detection.

The defect this module exists to prevent is unusually quiet.  Two copies of one
statement become two documents, two periods and two sets of rows, and each
period reconciles perfectly, because each is a faithful reading of the same
page.  Nothing goes red.  The damage is one level up, in everything that adds
periods together.  So these tests are mostly about the ways a plausible
implementation would still be wrong while appearing to work:

* fingerprinting anything case-bound, which would make the same statement in
  two matters look like two different statements and quietly disable the
  cross-matter question entirely;
* fingerprinting a surrogate id or depending on row order, either of which
  makes a re-scan of the same page look like new evidence -- the exact case
  plain file hashing already misses;
* excluding on ``same_account_period``, which would silently discard interim
  statements, corrected reissues and split months;
* superseding a document without taking its rows out of the totals, so the
  aggregate stays inflated and the badge in the UI says the problem is solved;
* letting any status change cross a case boundary.

The database-backed tests follow ``test_financial_reconcile``: a SQLite file on
disk rather than ``:memory:`` so the caller does not share one connection with
the services under test, and ``PRAGMA foreign_keys=ON`` because several
assertions depend on the ledger's own constraints holding.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
import uuid
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import (
    AdjudicationDecision,
    AdjudicationSubject,
    DocumentStatus,
    DuplicateMatchRung,
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
    FinancialAdjudication,
    FinancialIngestionRun,
    FinancialSourceDocument,
    FinancialStatementPeriod,
    FinancialTransaction,
)
from postgres.models.user import User
from services.financial.decisions import Actor, history
from services.financial.duplicates import (
    CrossCaseError,
    DuplicateError,
    cross_matter_sightings,
    find_groups,
    fingerprint_document,
    nominate_primary,
    purge_document,
    resolve_duplicates,
    restore_document,
    store_fingerprint,
)
from services.financial.money import Money
from services.financial.periods import (
    BalanceObservation,
    PeriodBounds,
    StatementPeriodDraft,
    record_statement_period,
)
from services.financial.reconcile import total_transactions
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
    FinancialAdjudication.__table__,
]

GBP = "GBP"
JAN = date(2026, 1, 1)
JAN_15 = date(2026, 1, 15)
JAN_31 = date(2026, 1, 31)
FEB = date(2026, 2, 1)
FEB_28 = date(2026, 2, 28)

# The account as printed on the statement.  Deliberately shared between the two
# cases below: it is the same real account, disclosed in two matters.
IDENTITY_KEY = "gb-barclays-20445566"

# When fixture documents are ingested.  Fixed, and the same for every document
# unless a test says otherwise, because age is the second-to-last component of
# the nomination ordering and letting the clock supply it makes the suite a
# lottery.  ``created_at`` defaults to ``func.now()``, which on SQLite has
# one-second resolution: two copies made in quick succession almost always tie
# on age and fall through to the id, but when a second boundary happens to fall
# between them age decides instead and the nominated primary changes.  That is
# rare enough to pass hundreds of runs and then fail one, which is the least
# useful way for a test to be wrong.  Pinning it means age never decides by
# accident, only on purpose.
INGESTED_AT = datetime(2026, 3, 1, 12, 0, 0)


def gbp(minor: int) -> Money:
    return Money(minor_units=minor, currency=GBP)


def printed(minor: int) -> BalanceObservation:
    return BalanceObservation.printed(gbp(minor))


class DuplicateTestCase(unittest.TestCase):
    """Two matters, each holding the same real account.

    Case B exists in every fixture rather than only in the cross-matter tests,
    so that a status change leaking out of case A has somewhere to leak to.  A
    scoping test against an empty database proves nothing.
    """

    def setUp(self):
        self._directory = tempfile.mkdtemp(prefix="loupe-duplicates-")
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
            title="Matter A",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        self.other_case = Case(
            id=uuid.uuid4(),
            title="Matter B",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        self.db.add_all([self.user, self.case, self.other_case])
        self.db.commit()

        self.account = self._account(self.case.id)
        self.other_account = self._account(self.other_case.id)
        self.db.add_all([self.account, self.other_account])
        self.db.commit()

        self.run = open_ingestion_run(
            case_id=self.case.id,
            actor=self.user,
            session_factory=self.SessionLocal,
        )
        self.other_run = open_ingestion_run(
            case_id=self.other_case.id,
            actor=self.user,
            session_factory=self.SessionLocal,
        )

        self._file_index = 0
        self._row_index = 0
        self.actor = Actor(
            name=self.user.name, email=self.user.email, user_id=self.user.id
        )

    def resolve(self, case_id=None, **kwargs):
        """``resolve_duplicates`` with the actor these fixtures decide as.

        The actor is required by the service even though every exclusion here
        is automatic, so this helper exists to keep that requirement from
        being restated twelve times rather than to make it optional.
        """
        return resolve_duplicates(
            self.db,
            self.case.id if case_id is None else case_id,
            actor=self.actor,
            **kwargs,
        )

    def restore(self, document, **kwargs):
        """``restore_document`` with the who and the why it now requires."""
        kwargs.setdefault(
            "reason", "Nomination reviewed; the exclusion was wrong."
        )
        return restore_document(
            self.db,
            document,
            case_id=kwargs.pop("case_id", self.case.id),
            actor=kwargs.pop("actor", self.actor),
            **kwargs,
        )

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        shutil.rmtree(self._directory, ignore_errors=True)

    # -- fixtures ----------------------------------------------------------

    def _account(
        self,
        case_id,
        *,
        identity_key: str = IDENTITY_KEY,
        account_id: uuid.UUID | None = None,
    ) -> FinancialAccount:
        """The same account, by its printed identifiers, in a given matter.

        The identity key is identical across the two cases on purpose.  It is
        derived from what the statement printed, so it has to be, and the
        cross-matter question depends on it being so.

        ``account_id`` is the surrogate, and pinning it is how a test controls
        the order rows come back from the database without changing a single
        thing the fingerprint is computed from.  That gap between the two --
        storage order and content -- is the whole subject of
        ``test_the_fingerprint_does_not_depend_on_period_order``.
        """
        suffix = identity_key.rsplit("-", 1)[-1]
        return FinancialAccount(
            id=account_id or uuid.uuid4(),
            case_id=case_id,
            identity_key=identity_key,
            institution_name="Barclays",
            identifier_as_printed=f"20-44-55 {suffix[-2:]}",
            identifier_normalised=suffix,
            currency=GBP,
        )

    def make_document(
        self,
        *,
        run=None,
        case=None,
        sha256: str | None = None,
        extraction_layer: int = ExtractionLayer.structural.value,
        document_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
    ) -> FinancialSourceDocument:
        """One document.

        ``document_id`` and ``created_at`` exist so that a test about one
        component of the nomination ordering can hold every later component
        equal.  Without them a tie is broken by a random uuid4, and a test
        that passes because of the draw is not a test.

        ``created_at`` defaults to ``INGESTED_AT`` rather than to the clock, so
        that documents tie on age unless a test deliberately separates them.
        See the constant for why the clock is not safe here.
        """
        run = run or self.run
        case = case or self.case
        self._file_index += 1
        evidence_file = EvidenceFile(
            id=uuid.uuid4(),
            case_id=case.id,
            original_filename=f"statement-{self._file_index}.pdf",
            stored_path=f"/evidence/statement-{self._file_index}.pdf",
            sha256=f"{self._file_index:064d}",
        )
        self.db.add(evidence_file)
        self.db.commit()

        document = FinancialSourceDocument(
            id=document_id or uuid.uuid4(),
            evidence_file_id=evidence_file.id,
            sha256_at_ingestion=sha256 or f"{self._file_index:064d}",
            document_type="bank_statement",
            proof_class=ProofClass.p2.value,
            extraction_layer=extraction_layer,
            parser_name="statement_pdf",
            parser_version="1.4.0",
        )
        document.created_at = created_at or INGESTED_AT
        self.db.add(run.stamp(document))
        self.db.commit()
        return document

    def make_period(
        self,
        document,
        *,
        account=None,
        bounds=None,
        opening=None,
        closing=None,
        run=None,
    ):
        return record_statement_period(
            self.db,
            run or self.run,
            StatementPeriodDraft(
                account_id=(account or self.account).id,
                source_document_id=document.id,
                currency=GBP,
                bounds=bounds or PeriodBounds.printed(JAN, JAN_31),
                opening=opening or printed(100_00),
                closing=closing or printed(380_00),
            ),
        )

    def add_row(
        self,
        period,
        document,
        *,
        amount: int,
        direction: TransactionDirection = TransactionDirection.credit,
        content_hash: str | None = None,
        account=None,
        status: LedgerStatus = LedgerStatus.admitted,
        quarantine_reason: QuarantineReason | None = None,
        run=None,
    ):
        # A quarantined row has to say on what grounds, and the database now
        # holds it to that.  Tests here care that a row is set aside, not why,
        # so supply a reason rather than making every call site repeat one.
        if status is LedgerStatus.quarantined and quarantine_reason is None:
            quarantine_reason = QuarantineReason.unreadable_row
        self._row_index += 1
        row = FinancialTransaction(
            id=uuid.uuid4(),
            account_id=(account or self.account).id,
            source_document_id=document.id,
            statement_period_id=period.id,
            ref_id=f"row-{self._row_index:04d}",
            row_index=self._row_index,
            amount_minor=amount,
            currency=GBP,
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
            content_hash=content_hash or f"{self._row_index:064d}",
        )
        self.db.add((run or self.run).stamp(row))
        self.db.commit()
        return row

    def make_copy(
        self,
        *,
        rows=((400_00, "aa"), (20_00, "bb")),
        run=None,
        case=None,
        account=None,
        sha256: str | None = None,
        bounds=None,
        opening=None,
        closing=None,
        extraction_layer: int = ExtractionLayer.structural.value,
        document_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
        fingerprint: bool = True,
    ) -> FinancialSourceDocument:
        """A whole document: one period over one account, with rows.

        ``rows`` carries an explicit content hash per row so that two copies
        can be made to agree or disagree on their reading independently of
        anything else about them.
        """
        document = self.make_document(
            run=run,
            case=case,
            sha256=sha256,
            extraction_layer=extraction_layer,
            document_id=document_id,
            created_at=created_at,
        )
        period = self.make_period(
            document,
            account=account,
            bounds=bounds,
            opening=opening,
            closing=closing,
            run=run,
        )
        for amount, tag in rows:
            self.add_row(
                period,
                document,
                amount=amount,
                content_hash=tag * 32,
                account=account,
                run=run,
            )
        if fingerprint:
            store_fingerprint(self.db, document)
            self.db.commit()
        return document

    def reload(self, document) -> FinancialSourceDocument:
        self.db.expire_all()
        return self.db.get(FinancialSourceDocument, document.id)


# ---------------------------------------------------------------------------
# Fingerprints.  What makes two readings the same reading.
# ---------------------------------------------------------------------------


class FingerprintTests(DuplicateTestCase):
    def test_two_copies_of_one_statement_agree_on_both_fingerprints(self):
        """The case the module exists for: same page, different file."""
        first = self.make_copy(sha256="1" * 64)
        second = self.make_copy(sha256="2" * 64)

        self.assertNotEqual(first.sha256_at_ingestion, second.sha256_at_ingestion)
        self.assertEqual(first.duplicate_group_key, second.duplicate_group_key)
        self.assertEqual(first.content_fingerprint, second.content_fingerprint)

    def test_the_fingerprint_does_not_depend_on_row_order(self):
        """Rows come back in whatever order the database chose.

        If that leaked into the hash, a re-scan of the same page would look
        like new evidence, which is precisely the failure being guarded
        against.
        """
        first = self.make_copy(rows=((400_00, "aa"), (20_00, "bb")))
        second = self.make_copy(rows=((20_00, "bb"), (400_00, "aa")))
        self.assertEqual(first.content_fingerprint, second.content_fingerprint)

    def test_the_fingerprint_does_not_depend_on_period_order(self):
        """The same argument as above, one level up.

        Every other fingerprint test here uses a single-period document, and
        with one period sorting is a no-op -- so an implementation that hashed
        periods in whatever order the database returned them would pass all of
        them.  A statement covering two accounts is entirely ordinary, and two
        disclosures of it need not have been stored in the same order.

        Producing that difference takes some care, because the obvious way does
        not work.  ``fingerprint_document`` selects periods without an ORDER BY,
        and on SQLite that query is served from the unique index over
        ``(source_document_id, account_id, period_start, period_end)`` -- so
        rows come back in account-then-date order no matter what order they were
        inserted in.  An earlier version of this test built the same two months
        forwards and backwards, got the identical sequence both times, and
        passed against an implementation that did no sorting at all.

        So the order is varied through the one column that decides it and that
        the fingerprint does not read: the surrogate ``account_id``.  Both
        documents cover the same two accounts, identified as the statement
        prints them, over the same month.  The two matters happen to have
        created their account rows in opposite orders, which is not a fact about
        the evidence and must not reach the digest.

        That this is a cross-matter pair is not incidental.  The fingerprint is
        deliberately case-independent, so the same statement filed in two
        matters is exactly where the surrogate ids diverge while the content
        does not -- which makes it both the sharpest available test of ordering
        and a direct assertion of the property ``cross_matter_sightings``
        depends on.
        """
        first_key = f"{IDENTITY_KEY}-aaa"
        second_key = f"{IDENTITY_KEY}-bbb"
        # Four ids, not two: the surrogate is unique across the whole table, so
        # each matter needs its own pair.  Only the order within a pair matters,
        # and it is opposite between the two.  Letters, not an all-digit hex:
        # SQLite applies numeric affinity to a text value that looks like a
        # number and hands back an integer.
        a_low = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
        a_high = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2")
        b_low = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1")
        b_high = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2")
        self.assertLess(str(a_low), str(a_high))
        self.assertLess(str(b_low), str(b_high))

        def build(case, run, keys) -> object:
            """One document over both accounts, in the given storage order."""
            accounts = [
                self._account(case.id, identity_key=key, account_id=account_id)
                for key, account_id in keys
            ]
            self.db.add_all(accounts)
            self.db.commit()

            document = self.make_document(case=case, run=run)
            for account, tag in zip(accounts, ("aa", "bb")):
                period = self.make_period(document, account=account, run=run)
                self.add_row(
                    period,
                    document,
                    amount=400_00,
                    account=account,
                    content_hash=tag * 32,
                    run=run,
                )
            return document, store_fingerprint(self.db, document)

        forwards_doc, forwards = build(
            self.case, self.run, [(first_key, a_low), (second_key, a_high)]
        )
        backwards_doc, backwards = build(
            self.other_case,
            self.other_run,
            [(first_key, b_high), (second_key, b_low)],
        )

        # The premise: the two documents really are stored the other way round.
        # Without this the assertions below could hold because nothing differed,
        # which is how the earlier version of this test came to prove nothing.
        self.assertEqual(
            self._stored_identity_keys(forwards_doc), [first_key, second_key]
        )
        self.assertEqual(
            self._stored_identity_keys(backwards_doc), [second_key, first_key]
        )

        self.assertEqual(forwards.group_key, backwards.group_key)
        self.assertEqual(
            forwards.content_fingerprint, backwards.content_fingerprint
        )

    def _stored_identity_keys(self, document) -> list:
        """The accounts of a document's periods, in the order the query gives.

        Deliberately the same select as ``fingerprint_document`` makes, with no
        ORDER BY, so that it observes the storage order rather than imposing
        one.
        """
        periods = self.db.scalars(
            select(FinancialStatementPeriod).where(
                FinancialStatementPeriod.source_document_id == document.id
            )
        ).all()
        return [
            self.db.get(FinancialAccount, period.account_id).identity_key
            for period in periods
        ]

    def test_differing_rows_break_the_content_fingerprint_only(self):
        """A dropped row is exactly what separates a good copy from a bad one.

        The group key must survive it -- otherwise the two copies never meet
        and the comparison never happens.
        """
        full = self.make_copy(rows=((400_00, "aa"), (20_00, "bb")))
        partial = self.make_copy(rows=((400_00, "aa"),))

        self.assertEqual(full.duplicate_group_key, partial.duplicate_group_key)
        self.assertNotEqual(full.content_fingerprint, partial.content_fingerprint)

    def test_a_different_period_is_a_different_group(self):
        january = self.make_copy(bounds=PeriodBounds.printed(JAN, JAN_31))
        february = self.make_copy(bounds=PeriodBounds.printed(FEB, FEB_28))
        self.assertNotEqual(
            january.duplicate_group_key, february.duplicate_group_key
        )

    def test_the_fingerprint_is_the_same_in_another_matter(self):
        """Case independence, asserted directly rather than inferred.

        This is the property that makes the cross-matter question answerable.
        If a surrogate id ever creeps into the hash, this is the test that
        notices.
        """
        mine = self.make_copy()
        theirs = self.make_copy(
            run=self.other_run, case=self.other_case, account=self.other_account
        )

        self.assertNotEqual(mine.case_id, theirs.case_id)
        self.assertEqual(mine.duplicate_group_key, theirs.duplicate_group_key)
        self.assertEqual(mine.content_fingerprint, theirs.content_fingerprint)

    def test_an_absent_start_and_an_absent_end_are_not_the_same(self):
        """Absent fields are written as empty, not skipped.

        Both periods carry exactly one date and it is the same date, so the
        only thing distinguishing them is which end of the period it sits at.
        An implementation that appends only the fields it has produces one
        identical string for both, and two genuinely different periods are
        then held to be the same reading.

        The shared date is the whole point.  An earlier version of this test
        used a different date on each side, which meant the strings differed
        whether or not position was preserved, and the test passed against an
        implementation that had thrown position away.
        """
        no_end = self.make_copy(
            bounds=PeriodBounds(
                start=JAN,
                end=None,
                start_source=PeriodBoundsSource.printed,
                end_source=PeriodBoundsSource.absent,
            )
        )
        no_start = self.make_copy(
            bounds=PeriodBounds(
                start=None,
                end=JAN,
                start_source=PeriodBoundsSource.absent,
                end_source=PeriodBoundsSource.printed,
            )
        )
        self.assertNotEqual(
            no_start.duplicate_group_key, no_end.duplicate_group_key
        )
        self.assertNotEqual(
            no_start.content_fingerprint, no_end.content_fingerprint
        )

    def test_fingerprinting_is_stable_across_repeated_calls(self):
        document = self.make_copy()
        again = fingerprint_document(self.db, document)
        self.assertEqual(again.group_key, document.duplicate_group_key)
        self.assertEqual(again.content_fingerprint, document.content_fingerprint)

    def test_store_fingerprint_persists_both_values(self):
        document = self.make_copy(fingerprint=False)
        self.assertIsNone(document.duplicate_group_key)

        store_fingerprint(self.db, document)
        self.db.commit()

        reloaded = self.reload(document)
        self.assertIsNotNone(reloaded.duplicate_group_key)
        self.assertIsNotNone(reloaded.content_fingerprint)


# ---------------------------------------------------------------------------
# The cascade.  How strongly two documents were shown to match.
# ---------------------------------------------------------------------------


class RungTests(DuplicateTestCase):
    def test_identical_bytes_is_the_strongest_rung(self):
        self.make_copy(sha256="f" * 64)
        self.make_copy(sha256="f" * 64)

        groups = find_groups(self.db, self.case.id)
        self.assertEqual(len(groups), 1)
        secondary = [m for m in groups[0].members if not m.is_primary]
        self.assertEqual(len(secondary), 1)
        self.assertEqual(secondary[0].rung, DuplicateMatchRung.identical_bytes)

    def test_different_bytes_with_the_same_reading_is_rung_one(self):
        """The rung that earns the module.  File hashing would miss this."""
        self.make_copy(sha256="1" * 64)
        self.make_copy(sha256="2" * 64)

        groups = find_groups(self.db, self.case.id)
        secondary = [m for m in groups[0].members if not m.is_primary]
        self.assertEqual(secondary[0].rung, DuplicateMatchRung.identical_reading)

    def test_the_same_account_and_period_with_different_rows_is_rung_two(self):
        self.make_copy(rows=((400_00, "aa"), (20_00, "bb")), sha256="1" * 64)
        self.make_copy(rows=((400_00, "aa"), (99_00, "cc")), sha256="2" * 64)

        groups = find_groups(self.db, self.case.id)
        secondary = [m for m in groups[0].members if not m.is_primary]
        self.assertEqual(
            secondary[0].rung, DuplicateMatchRung.same_account_period
        )

    def test_a_rung_two_match_is_flagged_and_never_excluded(self):
        """An interim statement and its replacement match at rung two.

        So do a statement and its corrected reissue, and the two halves of a
        month printed separately.  Excluding on this rung destroys evidence.
        """
        self.make_copy(rows=((400_00, "aa"),), sha256="1" * 64)
        self.make_copy(rows=((400_00, "aa"), (99_00, "cc")), sha256="2" * 64)

        groups = self.resolve()
        self.db.commit()

        self.assertEqual(groups[0].excluded_ids, ())
        self.assertTrue(groups[0].review_required)
        statuses = {
            d.status
            for d in self.db.scalars(
                select(FinancialSourceDocument).where(
                    FinancialSourceDocument.case_id == self.case.id
                )
            ).all()
        }
        self.assertEqual(statuses, {DocumentStatus.admitted.value})

    def test_a_strong_match_is_excluded_and_still_flagged(self):
        """An automatic exclusion nobody reviews is a quiet deletion."""
        self.make_copy(sha256="1" * 64)
        self.make_copy(sha256="2" * 64)

        groups = self.resolve()
        self.db.commit()

        self.assertEqual(len(groups[0].excluded_ids), 1)
        excluded = self.db.get(
            FinancialSourceDocument, groups[0].excluded_ids[0]
        )
        self.assertEqual(excluded.status, DocumentStatus.superseded.value)
        self.assertTrue(excluded.duplicate_review_required)

    def test_a_lone_document_forms_no_group(self):
        self.make_copy()
        self.assertEqual(find_groups(self.db, self.case.id), ())

    def test_an_unfingerprinted_document_is_skipped_not_guessed_at(self):
        """A null group key means 'not computed', never 'unique'."""
        self.make_copy(sha256="1" * 64)
        self.make_copy(sha256="1" * 64, fingerprint=False)

        self.assertEqual(find_groups(self.db, self.case.id), ())


# ---------------------------------------------------------------------------
# Nomination.  Which copy is kept.
# ---------------------------------------------------------------------------


class NominationTests(DuplicateTestCase):
    def test_the_copy_that_reconciles_is_preferred(self):
        """The balance identity picks, which is the whole point.

        Both copies read the same account over the same dates.  One closes
        against its printed balances and one does not, so they are not equally
        good readings and the arithmetic can say which.

        The identity is the first component of the ordering, and everything
        after it must be pinned or this test does not test it.  An earlier
        version left age and id free.  Both copies were then created in the same
        second -- SQLite's ``CURRENT_TIMESTAMP`` has one-second resolution, so
        the ages tied -- and the winner was decided by a random uuid4.  Against
        an implementation that ignored the arithmetic entirely the test passed
        about half the time, which is the worst possible result: it looked green
        on the run that mattered and only showed up under mutation, and then
        only on some runs.

        So the ages are equal by construction and the ids are pinned the wrong
        way round: the copy that drops a row sorts first on every component
        after the arithmetic, and wins unless the arithmetic is what separates
        them.
        """
        # Letters, not an all-digit hex.  See the extraction-layer test below.
        bad = self.make_copy(
            rows=((400_00, "aa"),),
            opening=printed(100_00),
            closing=printed(620_00),
            sha256="2" * 64,
            document_id=uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1"),
            created_at=INGESTED_AT,
        )
        good = self.make_copy(
            rows=((400_00, "aa"), (120_00, "bb")),
            opening=printed(100_00),
            closing=printed(620_00),
            sha256="1" * 64,
            document_id=uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2"),
            created_at=INGESTED_AT,
        )
        self.assertLess(str(bad.id), str(good.id))

        for order in ([bad, good], [good, bad]):
            self.assertEqual(nominate_primary(self.db, order).id, good.id)

    def test_nomination_does_not_depend_on_the_order_given(self):
        good = self.make_copy(
            rows=((400_00, "aa"), (120_00, "bb")),
            opening=printed(100_00),
            closing=printed(620_00),
            sha256="1" * 64,
        )
        bad = self.make_copy(
            rows=((400_00, "aa"),),
            opening=printed(100_00),
            closing=printed(620_00),
            sha256="2" * 64,
        )
        self.assertEqual(
            nominate_primary(self.db, [good, bad]).id,
            nominate_primary(self.db, [bad, good]).id,
        )

    def test_equally_good_copies_are_separated_by_extraction_layer(self):
        """The layer decides, and nothing after it is allowed to help.

        Extraction layer is followed in the ordering by age and then by id, so
        a test that leaves either of those free can pass without the layer
        being consulted at all -- the draw decides and the test says nothing.
        Both are pinned here, and the id is pinned the wrong way round on
        purpose: the guessed copy sorts first on every component after the
        layer, so it wins unless the layer is what separates them.
        """
        # Letters, not an all-digit hex.  SQLite applies numeric affinity to a
        # text value that looks like a number, so a uuid of 000...001 comes
        # back out of the database as the integer 1.
        guessed = self.make_copy(
            sha256="2" * 64,
            extraction_layer=ExtractionLayer.grounded_model.value,
            document_id=uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1"),
            created_at=INGESTED_AT,
        )
        native = self.make_copy(
            sha256="1" * 64,
            extraction_layer=ExtractionLayer.native.value,
            document_id=uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2"),
            created_at=INGESTED_AT,
        )
        self.assertLess(str(guessed.id), str(native.id))

        for order in ([guessed, native], [native, guessed]):
            self.assertEqual(nominate_primary(self.db, order).id, native.id)

    def test_indistinguishable_copies_still_nominate_deterministically(self):
        """Arbitrary must still mean the same every time.

        A duplicate resolution that reshuffled itself between runs would be
        evidence of nothing.  The two input orders are the point: repeating
        one order proves only that ``min`` is a function, and would hold just
        as well for an implementation that returned whichever copy it happened
        to see first.
        """
        first = self.make_copy(sha256="1" * 64)
        second = self.make_copy(sha256="2" * 64)
        expected = min(str(first.id), str(second.id))

        for order in ([first, second], [second, first], [second, first]):
            self.assertEqual(str(nominate_primary(self.db, order).id), expected)

    def test_an_empty_group_has_no_primary(self):
        with self.assertRaises(DuplicateError):
            nominate_primary(self.db, [])


# ---------------------------------------------------------------------------
# Resolution.  What supersession actually does to the totals.
# ---------------------------------------------------------------------------


class ResolutionTests(DuplicateTestCase):
    def test_superseding_takes_the_rows_out_of_the_totals(self):
        """The assertion that matters.

        Marking a document superseded while its rows keep counting would leave
        every aggregate inflated and put a badge in the interface saying the
        problem was handled.
        """
        self.make_copy(sha256="1" * 64)
        self.make_copy(sha256="2" * 64)

        groups = self.resolve()
        self.db.commit()

        excluded_id = groups[0].excluded_ids[0]
        period = self.db.scalars(
            select(FinancialStatementPeriod).where(
                FinancialStatementPeriod.source_document_id == excluded_id
            )
        ).first()
        totals = total_transactions(self.db, period_id=period.id, currency=GBP)
        self.assertEqual(totals.counted, 0)
        self.assertEqual(totals.credits, gbp(0))

    def test_the_primary_keeps_counting(self):
        self.make_copy(sha256="1" * 64)
        self.make_copy(sha256="2" * 64)

        groups = self.resolve()
        self.db.commit()

        period = self.db.scalars(
            select(FinancialStatementPeriod).where(
                FinancialStatementPeriod.source_document_id == groups[0].primary_id
            )
        ).first()
        totals = total_transactions(self.db, period_id=period.id, currency=GBP)
        self.assertEqual(totals.counted, 2)
        self.assertEqual(totals.credits, gbp(420_00))
        # The reported group has to agree with what was done to the database.
        # A caller that hides everything in ``excluded_ids`` would empty the
        # account while every row in it is still admitted, and the totals
        # above would go on saying so.
        self.assertNotIn(groups[0].primary_id, groups[0].excluded_ids)

    def test_the_primary_is_not_recorded_as_having_matched_anything(self):
        """A rung is a claim, so the kept copy must not carry one.

        ``duplicate_match_rung`` records how a document was shown to duplicate
        the copy that replaced it.  The primary was not replaced, so a rung on
        it asserts something that did not happen -- and it reads, to anything
        querying later, as a document that has been superseded.  The status
        stays admitted either way, which is why this needs asserting directly
        rather than being inferred from the totals.
        """
        self.make_copy(sha256="1" * 64)
        self.make_copy(sha256="2" * 64)

        groups = self.resolve()
        self.db.commit()

        primary = self.db.get(FinancialSourceDocument, groups[0].primary_id)
        self.assertIsNone(primary.duplicate_match_rung)
        self.assertIsNone(primary.superseded_by_id)
        self.assertEqual(primary.status, DocumentStatus.admitted.value)

    def test_the_superseded_document_points_at_its_primary(self):
        self.make_copy(sha256="1" * 64)
        self.make_copy(sha256="2" * 64)

        groups = self.resolve()
        self.db.commit()

        excluded = self.db.get(
            FinancialSourceDocument, groups[0].excluded_ids[0]
        )
        self.assertEqual(excluded.superseded_by_id, groups[0].primary_id)
        self.assertEqual(
            excluded.duplicate_match_rung, int(DuplicateMatchRung.identical_reading)
        )

    def test_resolution_is_idempotent(self):
        self.make_copy(sha256="1" * 64)
        self.make_copy(sha256="2" * 64)

        first = self.resolve()
        self.db.commit()
        second = self.resolve()
        self.db.commit()

        self.assertEqual(first[0].primary_id, second[0].primary_id)
        self.assertEqual(first[0].excluded_ids, second[0].excluded_ids)

    def test_resolution_never_touches_another_matter(self):
        """The rule Neil set: seeing a cross-matter copy is fine, acting is not."""
        self.make_copy(sha256="1" * 64)
        self.make_copy(sha256="2" * 64)
        theirs = self.make_copy(
            run=self.other_run,
            case=self.other_case,
            account=self.other_account,
            sha256="1" * 64,
        )

        self.resolve()
        self.db.commit()

        untouched = self.reload(theirs)
        self.assertEqual(untouched.status, DocumentStatus.admitted.value)
        self.assertIsNone(untouched.superseded_by_id)
        self.assertIsNone(untouched.duplicate_match_rung)
        self.assertFalse(untouched.duplicate_review_required)

    def test_a_cross_matter_copy_is_not_gathered_into_the_group(self):
        self.make_copy(sha256="1" * 64)
        self.make_copy(
            run=self.other_run,
            case=self.other_case,
            account=self.other_account,
            sha256="1" * 64,
        )
        self.assertEqual(find_groups(self.db, self.case.id), ())


# ---------------------------------------------------------------------------
# Restoring.  Supersession hides; it does not delete.
# ---------------------------------------------------------------------------


class RestoreTests(DuplicateTestCase):
    def test_a_restored_document_counts_again(self):
        self.make_copy(sha256="1" * 64)
        self.make_copy(sha256="2" * 64)
        groups = self.resolve()
        self.db.commit()

        excluded = self.db.get(
            FinancialSourceDocument, groups[0].excluded_ids[0]
        )
        self.restore(excluded)
        self.db.commit()

        reloaded = self.reload(excluded)
        self.assertEqual(reloaded.status, DocumentStatus.admitted.value)
        self.assertIsNone(reloaded.superseded_by_id)
        self.assertIsNone(reloaded.duplicate_match_rung)

        period = self.db.scalars(
            select(FinancialStatementPeriod).where(
                FinancialStatementPeriod.source_document_id == reloaded.id
            )
        ).first()
        totals = total_transactions(self.db, period_id=period.id, currency=GBP)
        self.assertEqual(totals.counted, 2)

    def test_restoring_does_not_readmit_rows_set_aside_for_other_reasons(self):
        """Restoring a document is a statement about the document.

        It is not a licence to overturn every other decision made about its
        contents, so a row quarantined on its own merits stays quarantined.

        The quarantined row has to sit on the copy that gets superseded, and
        that copy has to actually get superseded.  An earlier version of this
        test wrote the row hashes at two different lengths, so the two copies
        never matched beyond ``same_account_period``, nothing was excluded,
        the restore loop ran zero times, and the assertion below passed
        against a ``restore_document`` that readmitted everything it touched.
        Hence the explicit check that the group resolved the way it needed to
        before anything is concluded from what came after.
        """
        # Worse extraction layer, so this is the copy that loses nomination.
        # Everything ahead of the layer in the ordering is equal by
        # construction: both copies read the same two rows over the same
        # printed balances, and neither closes.
        document = self.make_document(
            sha256="1" * 64,
            extraction_layer=ExtractionLayer.grounded_model.value,
            created_at=INGESTED_AT,
        )
        period = self.make_period(document)
        self.add_row(period, document, amount=400_00, content_hash="a" * 32)
        self.add_row(
            period,
            document,
            amount=999_00,
            content_hash="q" * 32,
            status=LedgerStatus.quarantined,
        )
        store_fingerprint(self.db, document)
        twin = self.make_copy(
            rows=((400_00, "a"), (999_00, "q")),
            sha256="2" * 64,
            extraction_layer=ExtractionLayer.structural.value,
            created_at=INGESTED_AT,
        )
        self.db.commit()

        self.assertEqual(document.content_fingerprint, twin.content_fingerprint)

        groups = self.resolve()
        self.db.commit()
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].primary_id, twin.id)
        self.assertEqual(groups[0].excluded_ids, (document.id,))

        self.restore(self.db.get(FinancialSourceDocument, document.id))
        self.db.commit()

        rows = {
            row.content_hash: row.ledger_status
            for row in self.db.scalars(
                select(FinancialTransaction).where(
                    FinancialTransaction.source_document_id == document.id
                )
            )
        }
        self.assertEqual(rows["a" * 32], LedgerStatus.admitted.value)
        self.assertEqual(rows["q" * 32], LedgerStatus.quarantined.value)


# ---------------------------------------------------------------------------
# The cross-matter question.  Reads only.
# ---------------------------------------------------------------------------


class CrossMatterTests(DuplicateTestCase):
    def test_the_same_statement_in_another_matter_is_visible(self):
        mine = self.make_copy()
        theirs = self.make_copy(
            run=self.other_run, case=self.other_case, account=self.other_account
        )

        sightings = cross_matter_sightings(self.db, mine)
        self.assertEqual(len(sightings), 1)
        self.assertEqual(sightings[0].document_id, theirs.id)
        self.assertEqual(sightings[0].case_id, self.other_case.id)
        self.assertTrue(sightings[0].same_reading)

    def test_a_weaker_cross_matter_match_is_reported_as_such(self):
        mine = self.make_copy(rows=((400_00, "aa"),))
        self.make_copy(
            rows=((400_00, "aa"), (99_00, "cc")),
            run=self.other_run,
            case=self.other_case,
            account=self.other_account,
        )

        sightings = cross_matter_sightings(self.db, mine)
        self.assertEqual(len(sightings), 1)
        self.assertFalse(sightings[0].same_reading)

    def test_looking_across_matters_changes_nothing(self):
        mine = self.make_copy()
        theirs = self.make_copy(
            run=self.other_run, case=self.other_case, account=self.other_account
        )

        before = (theirs.status, theirs.superseded_by_id, theirs.duplicate_match_rung)
        cross_matter_sightings(self.db, mine)
        self.db.commit()

        reloaded = self.reload(theirs)
        self.assertEqual(
            (
                reloaded.status,
                reloaded.superseded_by_id,
                reloaded.duplicate_match_rung,
            ),
            before,
        )

    def test_copies_within_the_same_matter_are_not_reported_as_cross_matter(self):
        mine = self.make_copy(sha256="1" * 64)
        self.make_copy(sha256="2" * 64)
        self.assertEqual(cross_matter_sightings(self.db, mine), ())

    def test_an_unfingerprinted_document_has_no_sightings(self):
        document = self.make_copy(fingerprint=False)
        self.assertEqual(cross_matter_sightings(self.db, document), ())


# ---------------------------------------------------------------------------
# Purge.  Deliberate, explained, and refused across matters.
# ---------------------------------------------------------------------------


class PurgeTests(DuplicateTestCase):
    def _actor(self) -> dict:
        """The three loose actor arguments are now one ``Actor``.

        They were three because the row has three columns, which is the
        wrong reason: a name that can be passed without an address is a name
        that will be.  The dataclass validates both at construction, so a
        decision recorded here is one somebody can be asked about.
        """
        return {
            "reason": "Confirmed duplicate disclosure; retaining the primary.",
            "actor": self.actor,
        }

    def test_purging_writes_its_adjudication_and_deletes_the_document(self):
        self.make_copy(sha256="1" * 64)
        self.make_copy(sha256="2" * 64)
        groups = self.resolve()
        self.db.commit()

        excluded = self.db.get(
            FinancialSourceDocument, groups[0].excluded_ids[0]
        )
        excluded_id = excluded.id
        adjudication = purge_document(
            self.db, excluded, case_id=self.case.id, **self._actor()
        )
        self.db.commit()

        self.assertIsNone(
            self.db.get(FinancialSourceDocument, excluded_id)
        )
        stored = self.db.get(FinancialAdjudication, adjudication.id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.subject_id, excluded_id)
        self.assertEqual(stored.subject_type, "source_document")
        self.assertEqual(stored.decision, "purge_duplicate")
        self.assertEqual(
            stored.before["status"], DocumentStatus.superseded.value
        )

    def test_a_purge_across_matters_is_refused(self):
        theirs = self.make_copy(
            run=self.other_run, case=self.other_case, account=self.other_account
        )
        with self.assertRaises(CrossCaseError):
            purge_document(
                self.db, theirs, case_id=self.case.id, **self._actor()
            )
        self.db.rollback()
        self.assertIsNotNone(
            self.db.get(FinancialSourceDocument, theirs.id)
        )

    def test_a_purge_without_a_reason_is_refused(self):
        document = self.make_copy()
        actor = self._actor()
        actor["reason"] = "   "
        with self.assertRaises(DuplicateError):
            purge_document(self.db, document, case_id=self.case.id, **actor)
        self.db.rollback()
        self.assertIsNotNone(
            self.db.get(FinancialSourceDocument, document.id)
        )

    def test_purging_a_primary_with_dependents_is_refused(self):
        """The foreign key is ON DELETE SET NULL.

        So the delete would succeed and leave the superseded copies hidden
        with nothing recording what they were hidden for.  That is worse than
        either outcome the caller was choosing between, and it would be
        silent.
        """
        self.make_copy(sha256="1" * 64)
        self.make_copy(sha256="2" * 64)
        groups = self.resolve()
        self.db.commit()

        primary = self.db.get(FinancialSourceDocument, groups[0].primary_id)
        with self.assertRaises(DuplicateError):
            purge_document(
                self.db, primary, case_id=self.case.id, **self._actor()
            )
        self.db.rollback()
        self.assertIsNotNone(
            self.db.get(FinancialSourceDocument, groups[0].primary_id)
        )

    def test_the_adjudication_is_written_before_the_delete(self):
        """The decision record is established first, and not merely queued.

        Within one transaction the committed end state is the same whichever
        order the two writes are issued in, so this asserts the observable
        part of the guarantee: the adjudication has been flushed, and so has
        an id, by the time the caller gets it back.  An implementation that
        adds it to the session after the delete and leaves it for whoever
        commits next hands back a row with no identity and puts the
        destruction ahead of the record of why.
        """
        document = self.make_copy()
        adjudication = purge_document(
            self.db, document, case_id=self.case.id, **self._actor()
        )
        self.assertIsNotNone(adjudication.id)

    def test_the_adjudication_survives_the_document(self):
        """The record of a decision has to outlive the thing decided."""
        document = self.make_copy()
        document_id = document.id
        adjudication = purge_document(
            self.db, document, case_id=self.case.id, **self._actor()
        )
        self.db.commit()
        self.db.expire_all()

        stored = self.db.get(FinancialAdjudication, adjudication.id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.subject_id, document_id)
        self.assertIsNone(self.db.get(FinancialSourceDocument, document_id))


class TheDecisionLog(DuplicateTestCase):
    """What the document's own columns cannot say, and the log now does.

    Supersession is better off than quarantine here: ``superseded_by_id`` keeps
    pointing at the primary, so the disposition survives in the row.  The
    reversal is the problem.  ``restore_document`` nulls both columns that
    recorded the exclusion, so a restored document and one that was never a
    duplicate are byte-identical afterwards — which is the same defect the
    quarantine tests state, reached by a different route.  These tests assert
    the log carries the difference.
    """

    def make_pair(self):
        """Two readings of one statement, resolved.  Returns (primary, excluded)."""
        self.make_copy(sha256="1" * 64)
        self.make_copy(sha256="2" * 64)
        groups = self.resolve()
        self.db.commit()
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0].excluded_ids), 1)
        return (
            self.db.get(FinancialSourceDocument, groups[0].primary_id),
            self.db.get(FinancialSourceDocument, groups[0].excluded_ids[0]),
        )

    def told(self, document):
        return history(self.db, document, AdjudicationSubject.source_document)

    def test_an_exclusion_is_recorded_against_the_document_it_hid(self):
        primary, excluded = self.make_pair()

        self.assertEqual(self.told(primary), ())
        told = self.told(excluded)
        self.assertEqual(len(told), 1)
        self.assertEqual(
            told[0].decision, AdjudicationDecision.supersede_duplicate.value
        )
        self.assertEqual(told[0].subject_sequence, 1)
        self.assertIn(str(primary.id), told[0].reason)

    def test_a_restored_document_is_not_indistinguishable_from_an_untouched_one(
        self,
    ):
        """The defect, stated as a test.

        Both documents below end admitted with both duplicate columns null,
        and that is correct: a restored document is not a duplicate, so it must
        not carry a rung or a supersession pointer.  The columns are identical
        by design and the difference has to live somewhere else.
        """
        primary, excluded = self.make_pair()
        self.restore(excluded)
        self.db.commit()
        self.db.expire_all()

        columns = [
            (
                document.status,
                document.superseded_by_id,
                document.duplicate_match_rung,
                document.duplicate_review_required,
            )
            for document in (
                self.db.get(FinancialSourceDocument, primary.id),
                self.db.get(FinancialSourceDocument, excluded.id),
            )
        ]
        self.assertEqual(columns[0], columns[1])

        self.assertEqual(self.told(primary), ())
        self.assertEqual(
            [event.decision for event in self.told(excluded)],
            [
                AdjudicationDecision.supersede_duplicate.value,
                AdjudicationDecision.restore_document.value,
            ],
        )

    def test_the_pair_is_ordered_even_written_in_one_transaction(self):
        """``created_at`` cannot separate these two; ``subject_sequence`` can.

        Both writes happen without an intervening commit, so under Postgres
        they share a transaction timestamp and under SQLite they are very
        likely to share a second.  Ordering on ``created_at`` then ``id`` would
        put the restore first half the time, and would look authoritative
        while doing it.
        """
        _, excluded = self.make_pair()
        self.restore(excluded)
        self.db.commit()

        told = self.told(excluded)
        self.assertEqual([event.subject_sequence for event in told], [1, 2])

    def test_the_exclusion_survives_the_restore_that_nulls_it(self):
        """The rung and the pointer are gone from the row; they are in ``before``."""
        primary, excluded = self.make_pair()
        rung = excluded.duplicate_match_rung
        self.assertIsNotNone(rung)

        self.restore(excluded)
        self.db.commit()

        restore = self.told(excluded)[1]
        self.assertEqual(restore.before["superseded_by_id"], str(primary.id))
        self.assertEqual(restore.before["duplicate_match_rung"], rung)
        self.assertEqual(restore.before["status"], DocumentStatus.superseded.value)
        self.assertIsNone(restore.after["superseded_by_id"])
        self.assertIsNone(restore.after["duplicate_match_rung"])
        self.assertEqual(restore.after["status"], DocumentStatus.admitted.value)

    def test_the_stated_reason_reaches_the_log(self):
        _, excluded = self.make_pair()
        reason = "Nomination reversed: the excluded copy carries the bank's stamp."
        self.restore(excluded, reason=reason)
        self.db.commit()

        self.assertEqual(self.told(excluded)[1].reason, reason)

    def test_rerunning_the_resolver_appends_nothing(self):
        """Re-running is not re-deciding.

        ``resolve_duplicates`` is re-runnable and is reached routinely for
        documents already superseded by the same primary at the same rung.
        Appending an event for that would make the log answer "how many times
        was this excluded" with the number of times the resolver was run.
        """
        _, excluded = self.make_pair()
        self.resolve()
        self.resolve()
        self.db.commit()

        self.assertEqual(len(self.told(excluded)), 1)

    def test_the_decision_names_who_and_which_run(self):
        """Who and when, without either standing in for the other.

        The run id is passed explicitly here rather than through ``resolve``,
        because the argument is optional and a helper that always supplied it
        would leave the ``None`` case untested while looking like it covered
        both.
        """
        self.make_copy(sha256="1" * 64)
        self.make_copy(sha256="2" * 64)
        groups = self.resolve(ingestion_run_id=self.run.run_id)
        self.db.commit()
        excluded = self.db.get(FinancialSourceDocument, groups[0].excluded_ids[0])

        told = self.told(excluded)[0]
        self.assertEqual(told.ingestion_run_id, self.run.run_id)
        self.assertEqual(told.actor_name, self.user.name)
        self.assertEqual(told.actor_email, self.user.email)
        self.assertEqual(told.actor_user_id, self.user.id)
        self.assertEqual(told.case_id, self.case.id)

    def test_a_restore_cannot_be_filed_in_another_matter(self):
        _, excluded = self.make_pair()

        with self.assertRaises(CrossCaseError):
            self.restore(excluded, case_id=self.other_case.id)

    def test_an_automatic_exclusion_still_needs_an_actor(self):
        """"The system did it" is not an answer to who took this out of the totals."""
        self.make_copy(sha256="1" * 64)
        self.make_copy(sha256="2" * 64)
        self.db.commit()

        with self.assertRaises(DuplicateError) as caught:
            resolve_duplicates(self.db, self.case.id, actor="n.byrne")
        self.assertIn("Actor", str(caught.exception))

    def test_a_purge_records_that_nothing_is_left(self):
        """``after=None`` is the honest snapshot, and the log outlives the row."""
        _, excluded = self.make_pair()
        excluded_id = excluded.id

        adjudication = purge_document(
            self.db,
            excluded,
            case_id=self.case.id,
            reason="Retention schedule; the primary is kept.",
            actor=self.actor,
        )
        self.db.commit()
        self.db.expire_all()

        self.assertIsNone(self.db.get(FinancialSourceDocument, excluded_id))
        stored = self.db.get(FinancialAdjudication, adjudication.id)
        self.assertEqual(
            stored.decision, AdjudicationDecision.purge_duplicate.value
        )
        self.assertIsNone(stored.after)
        self.assertIsNotNone(stored.before)
        self.assertEqual(stored.subject_id, excluded_id)
        # Sequence 2: the supersession that hid it is still sequence 1, and
        # survives the row it was about.
        self.assertEqual(stored.subject_sequence, 2)


if __name__ == "__main__":
    unittest.main()
