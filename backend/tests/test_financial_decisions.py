"""Tests for the adjudication log itself.

The two callers — quarantine and duplicates — are tested where they live, and
those tests assert that a decision reaches the log.  This module tests the
things :func:`record` refuses, because every one of them is a way to write a
row that looks like evidence and is not:

* a decision filed against the wrong kind of subject, which there is no foreign
  key to catch and which reads as authoritative while being about something
  else;
* a decision filed in another matter, which is a confidentiality breach rather
  than a bug;
* a ``before``/``after`` pair whose two sides list different keys, which cannot
  be read as a diff at all;
* a pair whose two sides are equal, which claims a change that did not happen;
* a float in a snapshot, which is how a rounded amount re-enters a ledger that
  is otherwise integer minor units and gets quoted later as the figure of
  record;
* a bare string where an actor belongs.

And one thing it assigns rather than refuses: ``subject_sequence``, which is
the only column in the table that can carry an order.  ``created_at`` cannot —
Postgres ``now()`` is transaction-start time, so a quarantine and the release
that undid it share it, and those two are exactly the pair most likely to be
written together.

The fixture follows ``test_financial_quarantine``: SQLite on disk rather than
``:memory:`` so the caller does not share one connection with the code under
test, and ``PRAGMA foreign_keys=ON``.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import (
    AdjudicationDecision,
    AdjudicationSubject,
    ExtractionLayer,
    GlobalRole,
    LedgerStatus,
    ProofClass,
    TransactionDirection,
)
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.financial import (
    FinancialAccount,
    AdjudicationEvent,
    FinancialIngestionRun,
    FinancialSourceDocument,
    FinancialStatementPeriod,
    FinancialTransaction,
)
from postgres.models.user import User
from services.financial.decisions import (
    Actor,
    DecisionError,
    MalformedSnapshotError,
    SubjectMismatchError,
    history,
    record,
)
from services.financial.duplicates import CrossCaseError
from services.financial.money import Money, parse_money
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
    AdjudicationEvent.__table__,
]

USD = "USD"


def usd(text: str) -> Money:
    return parse_money(text, USD)


class DecisionTestCase(unittest.TestCase):
    """One case, one account, one document, one period, one row."""

    def setUp(self):
        self._directory = tempfile.mkdtemp(prefix="loupe-decisions-")
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
            title="Decisions Fixture",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        # A second matter, so "another case" is a real case rather than a
        # random uuid.  A decision filed across this boundary is the
        # confidentiality failure, and it should be refused whether or not the
        # other side exists.
        self.other_case = Case(
            id=uuid.uuid4(),
            title="Another Matter Entirely",
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

        self.row = FinancialTransaction(
            id=uuid.uuid4(),
            account_id=self.account.id,
            source_document_id=self.document.id,
            statement_period_id=self.period.id,
            ref_id="row-0001",
            row_index=1,
            amount_minor=usd("200.00").minor_units,
            currency=USD,
            direction=TransactionDirection.credit.value,
            transaction_date=date(2026, 1, 15),
            ordering_date=date(2026, 1, 15),
            ordering_date_source="transaction",
            description="row 1",
            proof_class=ProofClass.p2.value,
            extraction_layer=ExtractionLayer.structural.value,
            ledger_status=LedgerStatus.admitted.value,
            content_hash=f"{1:064d}",
        )
        self.db.add(self.run.stamp(self.row))
        self.db.commit()

        self.actor = Actor(
            name=self.user.name, email=self.user.email, user_id=self.user.id
        )

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        shutil.rmtree(self._directory, ignore_errors=True)

    def record(self, **kwargs):
        """``record`` against the fixture row, with everything overridable."""
        kwargs.setdefault("case_id", self.case.id)
        kwargs.setdefault("subject", self.row)
        kwargs.setdefault("subject_type", AdjudicationSubject.transaction)
        kwargs.setdefault("decision", AdjudicationDecision.quarantine_row)
        kwargs.setdefault("reason", "the amount column was cut off")
        kwargs.setdefault("actor", self.actor)
        return record(self.db, **kwargs)

    def insert_by_hand(self, **over):
        """Write a row past the service, to reach the table's own constraints.

        Every field is valid unless a caller overrides it, and
        ``test_the_hand_written_control_row_is_accepted`` commits it untouched.
        Without that control, a test asserting ``IntegrityError`` would pass
        just as well if some unrelated NOT NULL were failing, and would go on
        passing after the constraint it names had been dropped.
        """
        defaults = dict(
            case_id=self.case.id,
            subject_type=AdjudicationSubject.transaction.value,
            subject_id=self.row.id,
            subject_sequence=1,
            decision=AdjudicationDecision.release_row.value,
            reason="written past the service to reach the constraint",
            actor_user_id=self.user.id,
            actor_name=self.user.name,
            actor_email=self.user.email,
        )
        defaults.update(over)
        self.db.add(AdjudicationEvent(**defaults))

    def assert_refused_by(self, constraint: str):
        """Commit, and require the named constraint to be what refused it."""
        with self.assertRaises(IntegrityError) as caught:
            self.db.commit()
        self.assertIn(constraint, str(caught.exception.orig))
        self.db.rollback()


class TheActor(DecisionTestCase):
    def test_a_name_and_an_address_are_both_required(self):
        """Three loose columns became one object so they could not drift apart."""
        for bad in ({"name": "", "email": "a@b.test"}, {"name": "A", "email": "  "}):
            with self.subTest(**bad):
                with self.assertRaises(DecisionError):
                    Actor(**bad)

    def test_a_user_id_is_optional(self):
        """The account may be deleted; who decided must survive that."""
        actor = Actor(name="Outside Counsel", email="counsel@example.test")
        self.assertIsNone(actor.user_id)

        stored = self.record(actor=actor)
        self.assertIsNone(stored.actor_user_id)
        self.assertEqual(stored.actor_name, "Outside Counsel")
        self.assertEqual(stored.actor_email, "counsel@example.test")

    def test_a_bare_string_is_not_an_actor(self):
        with self.assertRaises(DecisionError) as caught:
            self.record(actor="n.byrne")
        self.assertIn("Actor", str(caught.exception))

    def test_the_name_is_copied_in_not_joined_at_read_time(self):
        """A renamed or deleted account must not rewrite who decided what."""
        stored = self.record()
        self.db.commit()

        self.user.name = "Someone Else"
        self.db.commit()
        self.db.expire_all()

        reloaded = self.db.get(AdjudicationEvent, stored.id)
        self.assertEqual(reloaded.actor_name, "Investigator")


class TheSubject(DecisionTestCase):
    def test_a_subject_of_the_wrong_kind_is_refused(self):
        """There is no foreign key to catch this later.

        ``subject_id`` deliberately carries none, because a decision has to
        outlive the row it was about and a cascade would delete the audit
        trail at the moment it mattered.  So the type has to be checked here or
        nowhere.
        """
        with self.assertRaises(SubjectMismatchError) as caught:
            self.record(
                subject=self.document,
                subject_type=AdjudicationSubject.transaction,
            )
        message = str(caught.exception)
        self.assertIn("FinancialTransaction", message)
        self.assertIn("FinancialSourceDocument", message)

    def test_every_subject_type_in_the_vocabulary_maps_to_a_model(self):
        """A member with no model would raise ``KeyError`` at the first use."""
        subjects = {
            AdjudicationSubject.transaction: self.row,
            AdjudicationSubject.statement_period: self.period,
            AdjudicationSubject.source_document: self.document,
            AdjudicationSubject.account: self.account,
            AdjudicationSubject.evidence_file: self.evidence_file,
        }
        self.assertEqual(set(subjects), set(AdjudicationSubject))

        for subject_type, subject in subjects.items():
            with self.subTest(subject_type=subject_type.value):
                stored = self.record(
                    subject=subject,
                    subject_type=subject_type,
                    decision=AdjudicationDecision.explain_balance_failure,
                    reason="recorded to prove the subject type is writable",
                )
                self.assertEqual(stored.subject_id, subject.id)
                self.assertEqual(stored.subject_type, subject_type.value)

    def test_a_subject_type_that_is_not_the_enum_is_refused(self):
        with self.assertRaises(DecisionError) as caught:
            self.record(subject_type="transaction")
        self.assertIn("AdjudicationSubject", str(caught.exception))

    def test_a_decision_that_is_not_the_enum_is_refused(self):
        """Free text is how one decision becomes three answers to one question."""
        with self.assertRaises(DecisionError) as caught:
            self.record(decision="quarantine_row")
        self.assertIn("AdjudicationDecision", str(caught.exception))

    def test_an_unflushed_subject_is_refused(self):
        """A decision pointing at nothing is worse than no decision."""
        unsaved = FinancialTransaction(
            id=None,
            account_id=self.account.id,
            source_document_id=self.document.id,
            statement_period_id=self.period.id,
        )
        with self.assertRaises(DecisionError) as caught:
            self.record(subject=unsaved)
        self.assertIn("no id", str(caught.exception))

    def test_a_decision_cannot_be_filed_in_another_matter(self):
        """Not a bug; a confidentiality breach, which is why it has its own type."""
        with self.assertRaises(CrossCaseError):
            self.record(case_id=self.other_case.id)

    def test_a_reason_is_required(self):
        for bad in (None, "", "   ", 7):
            with self.subTest(reason=bad):
                with self.assertRaises(DecisionError) as caught:
                    self.record(reason=bad)
                self.assertIn("unexplained edit", str(caught.exception))


class TheSnapshot(DecisionTestCase):
    def test_a_float_is_refused_and_the_message_says_where(self):
        """The one place a rounded amount could re-enter an exact ledger."""
        with self.assertRaises(MalformedSnapshotError) as caught:
            self.record(before={"amount": 200.0}, after={"amount": 300})
        message = str(caught.exception)
        self.assertIn("before.amount", message)
        self.assertIn("integer minor units", message)

    def test_a_float_nested_in_a_list_is_still_refused(self):
        with self.assertRaises(MalformedSnapshotError) as caught:
            self.record(
                before={"amounts": [1, 2.5]}, after={"amounts": [1, 3]}
            )
        self.assertIn("before.amounts[1]", str(caught.exception))

    def test_money_is_kept_as_units_and_currency(self):
        """Not as a formatted string: a snapshot has to survive being read back."""
        stored = self.record(
            before={"amount": usd("200.00")},
            after={"amount": usd("300.00")},
        )
        self.assertEqual(
            stored.before["amount"], {"minor_units": 20000, "currency": USD}
        )
        self.assertEqual(
            stored.after["amount"], {"minor_units": 30000, "currency": USD}
        )

    def test_enums_uuids_and_dates_are_converted(self):
        subject_id = uuid.uuid4()
        moment = datetime(2026, 1, 15, 9, 30, tzinfo=timezone.utc)
        stored = self.record(
            before={
                "status": LedgerStatus.admitted,
                "id": subject_id,
                "seen": moment,
                "on": date(2026, 1, 15),
            },
            after={
                "status": LedgerStatus.quarantined,
                "id": subject_id,
                "seen": moment,
                "on": date(2026, 1, 16),
            },
        )
        self.assertEqual(stored.before["status"], LedgerStatus.admitted.value)
        self.assertEqual(stored.before["id"], str(subject_id))
        self.assertEqual(stored.before["seen"], moment.isoformat())
        self.assertEqual(stored.before["on"], "2026-01-15")

    def test_a_non_string_key_is_refused(self):
        """Coercing it would make two different keys collide silently."""
        with self.assertRaises(MalformedSnapshotError) as caught:
            self.record(before={1: "a"}, after={1: "b"})
        self.assertIn("non-string key", str(caught.exception))

    def test_a_value_with_no_agreed_json_form_is_refused(self):
        with self.assertRaises(MalformedSnapshotError) as caught:
            self.record(before={"who": object()}, after={"who": None})
        self.assertIn("no agreed JSON form", str(caught.exception))

    def test_a_snapshot_that_is_not_a_mapping_is_refused(self):
        with self.assertRaises(MalformedSnapshotError) as caught:
            self.record(before=["status"], after={"status": "x"})
        self.assertIn("must be a mapping", str(caught.exception))

    def test_the_two_sides_must_describe_the_same_fields(self):
        """A key missing on the right is indistinguishable from a cleared field."""
        with self.assertRaises(MalformedSnapshotError) as caught:
            self.record(
                before={"status": "admitted", "reason": None},
                after={"status": "quarantined"},
            )
        message = str(caught.exception)
        self.assertIn("only in before: ['reason']", message)
        self.assertIn("only in after: []", message)

    def test_identical_sides_are_refused(self):
        """An event claiming a change that did not happen dilutes the log."""
        with self.assertRaises(MalformedSnapshotError) as caught:
            self.record(
                before={"status": "admitted"}, after={"status": "admitted"}
            )
        self.assertIn("did not happen", str(caught.exception))

    def test_both_sides_may_be_absent(self):
        """A verdict that changes no status still belongs in the log."""
        stored = self.record(
            decision=AdjudicationDecision.explain_balance_failure,
            reason="the statement omits a page; the identity cannot close",
        )
        self.assertIsNone(stored.before)
        self.assertIsNone(stored.after)

    def test_one_side_may_be_absent(self):
        """A purge has no ``after``; the subject no longer exists."""
        stored = self.record(
            decision=AdjudicationDecision.purge_duplicate,
            reason="retention schedule; the primary is kept",
            before={"status": "superseded"},
            after=None,
        )
        self.assertEqual(stored.before, {"status": "superseded"})
        self.assertIsNone(stored.after)


class TheSequence(DecisionTestCase):
    def test_decisions_about_one_subject_are_numbered_from_one(self):
        first = self.record(reason="set aside: the amount column was cut off")
        second = self.record(
            decision=AdjudicationDecision.release_row,
            reason="rescanned at 600dpi; the row reads cleanly",
        )
        self.assertEqual((first.subject_sequence, second.subject_sequence), (1, 2))

    def test_the_counter_is_per_subject_not_per_table(self):
        """Two subjects both start at 1, which is what makes a gap meaningful."""
        about_row = self.record()
        about_document = self.record(
            subject=self.document,
            subject_type=AdjudicationSubject.source_document,
            decision=AdjudicationDecision.supersede_duplicate,
            reason="duplicate of the structural reading",
        )
        self.assertEqual(about_row.subject_sequence, 1)
        self.assertEqual(about_document.subject_sequence, 1)

    def test_the_counter_does_not_collide_across_subject_types(self):
        """The high-water mark is read per ``(subject_type, subject_id)``.

        Reading it by ``subject_id`` alone would be almost right, since ids are
        uuid4 and do not repeat across tables in practice.  Almost right is the
        problem: the constraint is on the triple, so the query that feeds it
        has to be too.
        """
        self.record()
        self.record()
        about_period = self.record(
            subject=self.period,
            subject_type=AdjudicationSubject.statement_period,
            decision=AdjudicationDecision.explain_balance_failure,
            reason="the printed closing balance is illegible",
        )
        self.assertEqual(about_period.subject_sequence, 1)

    def test_two_decisions_cannot_claim_one_position(self):
        """The unique constraint is what makes a gap or a repeat a fact.

        Without it, two writers racing on one subject both read the same
        high-water mark and both write it, and the history has two rows in one
        place with no way to tell which came first.
        """
        first = self.record()
        self.db.flush()

        self.insert_by_hand(subject_sequence=first.subject_sequence)

        # SQLite reports a uniqueness violation by listing the columns, where
        # Postgres names the constraint.  Asserting the columns is the part
        # that is true on both, and it is also the part worth asserting: the
        # constraint is only useful if it covers this triple, and a future
        # edit narrowing it to two of the three would still fail under a test
        # that only looked for the word "UNIQUE".
        with self.assertRaises(IntegrityError) as caught:
            self.db.commit()
        message = str(caught.exception.orig)
        for column in ("subject_type", "subject_id", "subject_sequence"):
            self.assertIn(f"adjudications.{column}", message)
        self.db.rollback()

    def test_the_hand_written_control_row_is_accepted(self):
        """The control for every refusal below it.

        If this row did not commit, each of those tests would be asserting that
        a valid row fails, and would pass whether or not the constraint it
        names still existed.
        """
        self.insert_by_hand()
        self.db.commit()

        told = history(self.db, self.row, AdjudicationSubject.transaction)
        self.assertEqual(len(told), 1)

    def test_a_sequence_below_one_is_refused(self):
        self.insert_by_hand(subject_sequence=0)
        self.assert_refused_by("ck_adjudications_sequence_positive")

    def test_a_decision_outside_the_vocabulary_is_refused_by_the_database(self):
        """The service checks the enum; the check constraint catches the rest.

        Both are needed.  The service refuses a bad call, but the table is also
        written by migrations and by hand, and ``decision`` is the column a
        ``GROUP BY`` counts in a deposition.  ``released`` below is not a typo:
        it is the spelling a second writer would reach for, and the one that
        would silently split the count in two.
        """
        self.insert_by_hand(decision="released")
        self.assert_refused_by("ck_adjudications_decision")

    def test_a_subject_type_outside_the_vocabulary_is_refused_by_the_database(
        self,
    ):
        self.insert_by_hand(subject_type="txn")
        self.assert_refused_by("ck_adjudications_subject_type")

    def test_a_blank_reason_is_refused_by_the_database(self):
        """The service refuses whitespace; so, independently, does the table."""
        self.insert_by_hand(reason="   ")
        self.assert_refused_by("ck_adjudications_reason_not_blank")


class TheHistory(DecisionTestCase):
    def test_history_is_ordered_by_sequence_not_by_time(self):
        """The pair that most needs ordering is the pair written together.

        The two timestamps are forced to disagree with the sequence, and that
        is the whole test.  Written normally these rows tie on ``created_at``
        — Postgres ``now()`` is transaction-start time, SQLite is second
        granular — and on a tie the engine hands them back in insertion order,
        which is sequence order.  So a version of ``history`` that ordered on
        ``created_at`` would return exactly the right answer here and the
        assertion would pass while checking nothing.  It was verified by
        mutation that this is not hypothetical: swapping the ``order_by`` to
        ``created_at`` left the earlier form of this test green.

        Backdating the release is not a contrived case either.  It is what a
        clock correction, a replica with skew, or a backfill written after the
        fact all look like once the rows are on disk.  The sequence is the only
        column that cannot be revised by any of them.
        """
        self.record(reason="set aside: the amount column was cut off")
        self.record(
            decision=AdjudicationDecision.release_row,
            reason="rescanned at 600dpi; the row reads cleanly",
        )
        self.db.commit()

        first, second = (
            self.db.execute(
                select(AdjudicationEvent).order_by(
                    AdjudicationEvent.subject_sequence
                )
            )
            .scalars()
            .all()
        )
        second.created_at = first.created_at - timedelta(minutes=5)
        self.db.commit()

        told = history(self.db, self.row, AdjudicationSubject.transaction)
        self.assertEqual(
            [event.decision for event in told],
            [
                AdjudicationDecision.quarantine_row.value,
                AdjudicationDecision.release_row.value,
            ],
        )
        self.assertEqual([event.subject_sequence for event in told], [1, 2])

    def test_history_of_an_untouched_subject_is_empty(self):
        self.assertEqual(
            history(self.db, self.row, AdjudicationSubject.transaction), ()
        )

    def test_history_does_not_mix_subjects(self):
        self.record()
        self.record(
            subject=self.document,
            subject_type=AdjudicationSubject.source_document,
            decision=AdjudicationDecision.supersede_duplicate,
            reason="duplicate of the structural reading",
        )
        self.db.commit()

        self.assertEqual(
            len(history(self.db, self.row, AdjudicationSubject.transaction)), 1
        )
        self.assertEqual(
            len(
                history(
                    self.db, self.document, AdjudicationSubject.source_document
                )
            ),
            1,
        )

    def test_history_does_not_mix_subject_types_sharing_an_id(self):
        """Filtering on ``subject_id`` alone would pass every other test here.

        Ids are uuid4, so two tables sharing one is vanishingly unlikely in
        practice and trivial to arrange deliberately — which is what an
        adversarial read of the log would do.  The filter is on the pair.
        """
        self.record()
        self.db.commit()

        # A stand-in whose id is the row's, asked about as a document.
        class _Impostor:
            id = self.row.id

        self.assertEqual(
            history(self.db, _Impostor(), AdjudicationSubject.source_document),
            (),
        )

    def test_the_decision_survives_a_flush_and_reads_back_whole(self):
        stored = self.record(
            before={"ledger_status": "admitted", "quarantine_reason": None},
            after={
                "ledger_status": "quarantined",
                "quarantine_reason": "unreadable_row",
            },
            ingestion_run_id=self.run.run_id,
        )
        self.db.commit()
        self.db.expire_all()

        reloaded = self.db.get(AdjudicationEvent, stored.id)
        self.assertEqual(reloaded.case_id, self.case.id)
        self.assertEqual(reloaded.subject_id, self.row.id)
        self.assertEqual(reloaded.ingestion_run_id, self.run.run_id)
        self.assertEqual(reloaded.before["quarantine_reason"], None)
        self.assertEqual(reloaded.after["quarantine_reason"], "unreadable_row")
        self.assertIsNotNone(reloaded.created_at)


if __name__ == "__main__":
    unittest.main()
