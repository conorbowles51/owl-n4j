"""Tests for run identity: what produced each fact in the financial ledger.

Two properties carry most of the weight here, and both are about what survives
a bad outcome rather than what happens on the happy path.

*A run always reaches a terminal state.*  Every exit from the context manager
is exercised: normal return, deliberate abort, ordinary exception, and
``KeyboardInterrupt``.  A run left saying ``running`` is worse than no run at
all, because it reads as work still in progress.

*A failed run still leaves a record.*  This is the reason the bookkeeping uses
a session of its own, and it is the reason these tests use a database on disk
rather than the in-memory one used elsewhere in this suite.  With
``sqlite:///:memory:`` every session would either get its own empty database or,
under a shared pool, share a single connection and therefore a single
transaction — and a test where the caller and the bookkeeping share a
transaction cannot detect the bug it exists to catch.  On disk they are
genuinely separate connections, which is what production looks like.

SQLite's coarse write locking does show through in one place, noted where it
bites.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import (
    DateSource,
    ExtractionLayer,
    GlobalRole,
    IngestionRunStatus,
    ProofClass,
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
from services.financial import version
from services.financial.runs import (
    MAX_ERROR_CHARS,
    RunAborted,
    RunScopeError,
    ingestion_run,
    open_ingestion_run,
    reap_stale_runs,
)
from services.financial.version import (
    PIPELINE_VERSION,
    UNVERIFIED,
    code_fingerprint_detail,
    code_version,
    reset_caches,
    ruleset_version,
)


# Creation order.  ``evidence_folders`` and ``financial_statement_periods`` are
# here only because ``evidence_files`` and ``financial_transactions`` reference
# them: SQLite, once foreign key enforcement is on, requires the parent table to
# exist even where every child value is null.
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


class RunTestCase(unittest.TestCase):
    """A case, a document and an account on a real database file.

    ``self.db`` is the caller's session — the one a pipeline would be writing
    ledger rows through.  ``self.SessionLocal`` is handed to the run service as
    its session factory, so the run's own bookkeeping opens connections of its
    own, exactly as it does in production.
    """

    def setUp(self):
        self._directory = tempfile.mkdtemp(prefix="loupe-runs-")
        self.engine = create_engine(
            f"sqlite+pysqlite:///{Path(self._directory) / 'ledger.db'}",
            future=True,
        )

        @event.listens_for(self.engine, "connect")
        def _configure(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            # These tests commit far more often than the rest of the suite,
            # because a run's bookkeeping commits separately from the caller's
            # work.  Without this, every one of those commits waits on an fsync
            # and the file adds twenty seconds for no gain: durability across a
            # power cut is not a property of a database that is deleted in
            # tearDown.
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
            title="Run Fixture",
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
            original_filename="march-statement.pdf",
            stored_path="/evidence/march-statement.pdf",
            sha256="a" * 64,
        )
        self.account = FinancialAccount(
            id=uuid.uuid4(),
            case_id=self.case.id,
            identity_key="gb-barclays-20445566",
            institution_name="Barclays",
            identifier_as_printed="20-44-55 66",
            identifier_normalised="20445566",
            currency="GBP",
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

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        shutil.rmtree(self._directory, ignore_errors=True)

    # -- helpers ------------------------------------------------------------

    def read_run(self, run_id):
        """Read a run through a session of its own.

        Every assertion about a run goes through here rather than through
        ``self.db``, so that what is being asserted is what the database
        holds and not what some other session happens to have cached.
        """
        session = self.SessionLocal()
        try:
            return session.get(FinancialIngestionRun, run_id)
        finally:
            session.close()

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

    def new_transaction(self, **overrides):
        return FinancialTransaction(
            id=overrides.pop("id", uuid.uuid4()),
            account_id=overrides.pop("account_id", self.account.id),
            ref_id=overrides.pop("ref_id", f"TXN-{uuid.uuid4().hex[:8]}"),
            row_index=overrides.pop("row_index", 0),
            amount_minor=overrides.pop("amount_minor", 125_00),
            currency=overrides.pop("currency", "GBP"),
            direction=overrides.pop("direction", TransactionDirection.debit.value),
            transaction_date=overrides.pop("transaction_date", date(2026, 3, 4)),
            ordering_date=overrides.pop("ordering_date", date(2026, 3, 4)),
            ordering_date_source=overrides.pop(
                "ordering_date_source", DateSource.transaction.value
            ),
            proof_class=overrides.pop("proof_class", ProofClass.p2.value),
            extraction_layer=overrides.pop(
                "extraction_layer", ExtractionLayer.structural.value
            ),
            content_hash=overrides.pop("content_hash", uuid.uuid4().hex),
            **overrides,
        )

    def insert_run(self, **overrides):
        """Insert a run row directly, bypassing the service.

        Used where a test needs a run in a state the service will not produce
        on its own — an old ``started_at``, most of all.
        """
        session = self.SessionLocal()
        try:
            run = FinancialIngestionRun(
                id=overrides.pop("id", uuid.uuid4()),
                case_id=overrides.pop("case_id", self.case.id),
                status=overrides.pop("status", IngestionRunStatus.running.value),
                code_version=overrides.pop("code_version", "1.0.0+deadbeefdeadbeef"),
                started_at=overrides.pop("started_at", datetime.now(timezone.utc)),
                **overrides,
            )
            session.add(run)
            session.commit()
            return run.id
        finally:
            session.close()


class IngestionRunLifecycleTests(RunTestCase):
    """Every exit path from the context manager reaches a terminal state."""

    def test_a_completed_run_is_recorded_as_completed(self):
        with ingestion_run(
            case_id=self.case.id,
            actor=self.user,
            session_factory=self.SessionLocal,
        ) as run:
            run_id = run.run_id

        stored = self.read_run(run_id)
        self.assertEqual(stored.status, IngestionRunStatus.completed.value)
        self.assertIsNotNone(stored.completed_at)
        self.assertIsNone(stored.error)

    def test_a_run_is_running_while_it_is_running(self):
        with ingestion_run(
            case_id=self.case.id,
            session_factory=self.SessionLocal,
        ) as run:
            # Read from a separate session: the point is that the run is
            # already committed and visible to other readers while the work is
            # still in flight, not merely held in memory until it finishes.
            in_flight = self.read_run(run.run_id)
            self.assertEqual(in_flight.status, IngestionRunStatus.running.value)
            self.assertIsNone(in_flight.completed_at)

    def test_counts_are_recorded_as_they_stood_when_the_run_ended(self):
        with ingestion_run(
            case_id=self.case.id,
            session_factory=self.SessionLocal,
        ) as run:
            run.document_seen()
            run.document_seen(2)
            run.transaction_admitted(41)
            run.transaction_quarantined()
            run_id = run.run_id

        stored = self.read_run(run_id)
        self.assertEqual(stored.documents_seen, 3)
        self.assertEqual(stored.transactions_admitted, 41)
        self.assertEqual(stored.transactions_quarantined, 1)

    def test_the_code_version_is_recorded_without_being_asked_for(self):
        with ingestion_run(
            case_id=self.case.id,
            session_factory=self.SessionLocal,
        ) as run:
            run_id = run.run_id

        stored = self.read_run(run_id)
        self.assertEqual(stored.code_version, code_version())
        self.assertTrue(stored.code_version.startswith(f"{PIPELINE_VERSION}+"))

    def test_the_ruleset_version_is_derived_from_the_ruleset(self):
        rules = {"tolerance_minor": 0, "layer": "structural"}
        with ingestion_run(
            case_id=self.case.id,
            ruleset=rules,
            session_factory=self.SessionLocal,
        ) as run:
            run_id = run.run_id

        stored = self.read_run(run_id)
        self.assertEqual(stored.ruleset_version, ruleset_version(rules))

    def test_no_ruleset_records_no_ruleset_version(self):
        with ingestion_run(
            case_id=self.case.id,
            session_factory=self.SessionLocal,
        ) as run:
            run_id = run.run_id

        self.assertIsNone(self.read_run(run_id).ruleset_version)

    def test_the_actor_is_recorded_by_id_and_by_email(self):
        with ingestion_run(
            case_id=self.case.id,
            actor=self.user,
            session_factory=self.SessionLocal,
        ) as run:
            run_id = run.run_id

        stored = self.read_run(run_id)
        self.assertEqual(stored.started_by_user_id, self.user.id)
        # The email is copied because the foreign key nulls when a user is
        # deleted, and "who started this" has to survive an account being
        # removed.
        self.assertEqual(stored.started_by_email, self.user.email)

    def test_a_system_run_records_no_actor(self):
        with ingestion_run(
            case_id=self.case.id,
            session_factory=self.SessionLocal,
        ) as run:
            run_id = run.run_id

        stored = self.read_run(run_id)
        self.assertIsNone(stored.started_by_user_id)
        self.assertIsNone(stored.started_by_email)

    def test_notes_and_config_are_recorded(self):
        with ingestion_run(
            case_id=self.case.id,
            config={"batch": "march"},
            notes="Re-ingest after the parser fix.",
            session_factory=self.SessionLocal,
        ) as run:
            run_id = run.run_id

        stored = self.read_run(run_id)
        self.assertEqual(stored.config, {"batch": "march"})
        self.assertEqual(stored.notes, "Re-ingest after the parser fix.")


class IngestionRunFailureTests(RunTestCase):
    """What the ledger says after a run goes wrong."""

    def test_an_exception_marks_the_run_failed_and_is_re_raised(self):
        captured = {}

        with self.assertRaises(ValueError) as raised:
            with ingestion_run(
                case_id=self.case.id,
                session_factory=self.SessionLocal,
            ) as run:
                captured["id"] = run.run_id
                raise ValueError("the page was unreadable")

        self.assertEqual(str(raised.exception), "the page was unreadable")
        stored = self.read_run(captured["id"])
        self.assertEqual(stored.status, IngestionRunStatus.failed.value)
        self.assertEqual(stored.error, "ValueError: the page was unreadable")
        self.assertIsNotNone(stored.completed_at)

    def test_a_failed_runs_record_survives_the_callers_rollback(self):
        # The caller's row is added but deliberately not flushed.  SQLite locks
        # the whole database file for the duration of a write transaction, so
        # flushing here would block the bookkeeping session and the test would
        # be measuring a limitation of the test database rather than this code.
        # Postgres, where this runs in production, takes a row lock instead,
        # and the FOR KEY SHARE lock that a foreign key reference places on the
        # run row is compatible with the non-key UPDATE that terminate() makes.
        captured = {}

        with self.assertRaises(RuntimeError):
            with ingestion_run(
                case_id=self.case.id,
                session_factory=self.SessionLocal,
            ) as run:
                captured["id"] = run.run_id
                self.db.add(run.stamp(self.new_document()))
                raise RuntimeError("parser crashed")

        self.db.rollback()

        stored = self.read_run(captured["id"])
        self.assertEqual(stored.status, IngestionRunStatus.failed.value)
        self.assertEqual(stored.error, "RuntimeError: parser crashed")

    def test_rows_committed_before_a_failure_survive_and_name_the_failed_run(self):
        captured = {}

        with self.assertRaises(RuntimeError):
            with ingestion_run(
                case_id=self.case.id,
                session_factory=self.SessionLocal,
            ) as run:
                captured["id"] = run.run_id
                document = run.stamp(self.new_document())
                captured["document"] = document.id
                self.db.add(document)
                self.db.add(
                    run.stamp(self.new_transaction(source_document_id=document.id))
                )
                # Committing releases SQLite's write lock, so the bookkeeping
                # session can proceed.  It is also the realistic case: work
                # already committed is exactly what a later quarantine pass has
                # to be able to find.
                self.db.commit()
                raise RuntimeError("the next page was unreadable")

        stored = self.read_run(captured["id"])
        self.assertEqual(stored.status, IngestionRunStatus.failed.value)

        session = self.SessionLocal()
        try:
            document = session.get(FinancialSourceDocument, captured["document"])
            self.assertIsNotNone(document)
            self.assertEqual(document.ingestion_run_id, captured["id"])
        finally:
            session.close()

    def test_a_keyboard_interrupt_marks_the_run_failed_and_is_re_raised(self):
        captured = {}

        with self.assertRaises(KeyboardInterrupt):
            with ingestion_run(
                case_id=self.case.id,
                session_factory=self.SessionLocal,
            ) as run:
                captured["id"] = run.run_id
                raise KeyboardInterrupt

        # An interrupted run did not finish, so it is not completed; and nobody
        # made a decision about the ledger, so it is not aborted either.
        self.assertEqual(
            self.read_run(captured["id"]).status, IngestionRunStatus.failed.value
        )

    def test_a_long_error_is_truncated_rather_than_stored_whole(self):
        captured = {}

        with self.assertRaises(ValueError):
            with ingestion_run(
                case_id=self.case.id,
                session_factory=self.SessionLocal,
            ) as run:
                captured["id"] = run.run_id
                raise ValueError("x" * (MAX_ERROR_CHARS * 3))

        error = self.read_run(captured["id"]).error
        self.assertEqual(len(error), MAX_ERROR_CHARS)
        self.assertTrue(error.endswith("…"))

    def test_counts_at_the_moment_of_failure_are_kept(self):
        captured = {}

        with self.assertRaises(ValueError):
            with ingestion_run(
                case_id=self.case.id,
                session_factory=self.SessionLocal,
            ) as run:
                captured["id"] = run.run_id
                run.document_seen(4)
                run.transaction_admitted(9)
                raise ValueError("stopped here")

        stored = self.read_run(captured["id"])
        self.assertEqual(stored.documents_seen, 4)
        self.assertEqual(stored.transactions_admitted, 9)


class IngestionRunAbortTests(RunTestCase):
    """A deliberate stop is recorded as a decision, not as a breakage."""

    def test_an_abort_is_suppressed_and_recorded_as_aborted(self):
        with ingestion_run(
            case_id=self.case.id,
            session_factory=self.SessionLocal,
        ) as run:
            run_id = run.run_id
            raise RunAborted("No statement periods were found in the document.")

        # Control reaches here: raising RunAborted is how a caller says "stop
        # and record why", so the block exits normally.
        stored = self.read_run(run_id)
        self.assertEqual(stored.status, IngestionRunStatus.aborted.value)
        self.assertEqual(
            stored.error, "No statement periods were found in the document."
        )

    def test_an_abort_is_not_a_failure(self):
        with ingestion_run(
            case_id=self.case.id,
            session_factory=self.SessionLocal,
        ) as run:
            run_id = run.run_id
            raise RunAborted("Operator cancelled.")

        self.assertNotEqual(
            self.read_run(run_id).status, IngestionRunStatus.failed.value
        )

    def test_an_abort_without_a_reason_records_no_reason(self):
        with ingestion_run(
            case_id=self.case.id,
            session_factory=self.SessionLocal,
        ) as run:
            run_id = run.run_id
            raise RunAborted()

        stored = self.read_run(run_id)
        self.assertEqual(stored.status, IngestionRunStatus.aborted.value)
        self.assertIsNone(stored.error)


class IngestionRunTerminationTests(RunTestCase):
    """Terminating is a once-only act."""

    def test_a_second_termination_is_refused(self):
        handle = open_ingestion_run(
            case_id=self.case.id, session_factory=self.SessionLocal
        )
        handle.terminate(IngestionRunStatus.completed)

        with self.assertRaises(RunScopeError):
            handle.terminate(IngestionRunStatus.failed)

        # The first terminal status is the true one and stands.
        self.assertEqual(
            self.read_run(handle.run_id).status, IngestionRunStatus.completed.value
        )

    def test_a_non_terminal_status_is_refused(self):
        handle = open_ingestion_run(
            case_id=self.case.id, session_factory=self.SessionLocal
        )
        for status in (IngestionRunStatus.pending, IngestionRunStatus.running):
            with self.subTest(status=status):
                with self.assertRaises(ValueError):
                    handle.terminate(status)
        handle.terminate(IngestionRunStatus.completed)

    def test_a_closed_run_refuses_further_rows(self):
        handle = open_ingestion_run(
            case_id=self.case.id, session_factory=self.SessionLocal
        )
        handle.terminate(IngestionRunStatus.completed)

        with self.assertRaises(RunScopeError):
            handle.stamp(self.new_document())

    def test_open_ingestion_run_leaves_the_run_running(self):
        handle = open_ingestion_run(
            case_id=self.case.id, session_factory=self.SessionLocal
        )
        try:
            stored = self.read_run(handle.run_id)
            self.assertEqual(stored.status, IngestionRunStatus.running.value)
            self.assertEqual(handle.status, IngestionRunStatus.running)
        finally:
            handle.terminate(IngestionRunStatus.completed)


class IngestionRunStampingTests(RunTestCase):
    """Attribution is checked, not assumed."""

    def setUp(self):
        super().setUp()
        self.handle = open_ingestion_run(
            case_id=self.case.id, session_factory=self.SessionLocal
        )

    def tearDown(self):
        if not self.handle.status.value == IngestionRunStatus.completed.value:
            self.handle.terminate(IngestionRunStatus.completed)
        super().tearDown()

    def test_stamping_attributes_a_row_to_the_run_and_the_case(self):
        document = self.handle.stamp(self.new_document())
        self.assertEqual(document.ingestion_run_id, self.handle.run_id)
        self.assertEqual(document.case_id, self.case.id)

    def test_stamping_returns_the_row_so_it_can_be_used_inline(self):
        document = self.new_document()
        self.assertIs(self.handle.stamp(document), document)

    def test_stamping_a_row_that_already_names_this_run_is_accepted(self):
        document = self.handle.stamp(self.new_document())
        self.assertIs(self.handle.stamp(document), document)

    def test_a_row_belonging_to_another_run_is_refused(self):
        foreign_run = uuid.uuid4()
        document = self.new_document(ingestion_run_id=foreign_run)

        with self.assertRaises(RunScopeError) as raised:
            self.handle.stamp(document)

        self.assertIn(str(foreign_run), str(raised.exception))
        # The row is left as it was rather than half-claimed.
        self.assertEqual(document.ingestion_run_id, foreign_run)

    def test_a_row_belonging_to_another_case_is_refused(self):
        document = self.new_document(case_id=self.other_case.id)

        with self.assertRaises(RunScopeError):
            self.handle.stamp(document)

    def test_a_row_with_nowhere_to_record_a_run_is_refused(self):
        # An account is an identity that persists across runs, so it carries no
        # ingestion_run_id.  Stamping one is a programming error and saying so
        # is more useful than silently doing nothing.
        account = FinancialAccount(
            id=uuid.uuid4(),
            case_id=self.case.id,
            identity_key="gb-hsbc-99887766",
            institution_name="HSBC",
            identifier_as_printed="99-88-77 66",
            identifier_normalised="99887766",
            currency="GBP",
        )
        with self.assertRaises(RunScopeError):
            self.handle.stamp(account)

    def test_stamp_all_attributes_every_row(self):
        rows = [self.new_document() for _ in range(3)]
        stamped = self.handle.stamp_all(rows)

        self.assertEqual(len(stamped), 3)
        for row in stamped:
            self.assertEqual(row.ingestion_run_id, self.handle.run_id)

    def test_a_stamped_row_satisfies_the_databases_own_requirement(self):
        document = self.handle.stamp(self.new_document())
        self.db.add(document)
        self.db.commit()

        session = self.SessionLocal()
        try:
            stored = session.get(FinancialSourceDocument, document.id)
            self.assertEqual(stored.ingestion_run_id, self.handle.run_id)
        finally:
            session.close()


class ReapStaleRunsTests(RunTestCase):
    """The safety net for a process that never got to close its own run."""

    def test_a_run_past_the_threshold_is_closed_as_failed(self):
        stale = self.insert_run(
            started_at=datetime.now(timezone.utc) - timedelta(hours=6)
        )

        reaped = reap_stale_runs(
            older_than=timedelta(hours=1), session_factory=self.SessionLocal
        )

        self.assertEqual(reaped, [stale])
        stored = self.read_run(stale)
        # Failed, not aborted: nobody decided to stop it, and recording a crash
        # as a decision would misstate the record.
        self.assertEqual(stored.status, IngestionRunStatus.failed.value)
        self.assertIsNotNone(stored.completed_at)
        self.assertIn("Abandoned", stored.error)

    def test_a_recent_run_is_left_alone(self):
        fresh = self.insert_run(
            started_at=datetime.now(timezone.utc) - timedelta(minutes=5)
        )

        reaped = reap_stale_runs(
            older_than=timedelta(hours=1), session_factory=self.SessionLocal
        )

        self.assertEqual(reaped, [])
        self.assertEqual(
            self.read_run(fresh).status, IngestionRunStatus.running.value
        )

    def test_a_run_that_already_ended_is_not_touched(self):
        old_completion = datetime.now(timezone.utc) - timedelta(days=2)
        finished = self.insert_run(
            status=IngestionRunStatus.completed.value,
            started_at=datetime.now(timezone.utc) - timedelta(days=2),
            completed_at=old_completion,
        )

        reaped = reap_stale_runs(
            older_than=timedelta(hours=1), session_factory=self.SessionLocal
        )

        self.assertEqual(reaped, [])
        self.assertEqual(
            self.read_run(finished).status, IngestionRunStatus.completed.value
        )

    def test_the_threshold_is_applied_against_a_supplied_moment(self):
        run_id = self.insert_run(
            started_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
        )

        # Not yet stale as at 12:30.
        self.assertEqual(
            reap_stale_runs(
                older_than=timedelta(hours=1),
                session_factory=self.SessionLocal,
                now=datetime(2026, 3, 1, 12, 30, tzinfo=timezone.utc),
            ),
            [],
        )
        # Stale as at 14:00.
        self.assertEqual(
            reap_stale_runs(
                older_than=timedelta(hours=1),
                session_factory=self.SessionLocal,
                now=datetime(2026, 3, 1, 14, 0, tzinfo=timezone.utc),
            ),
            [run_id],
        )

    def test_a_naive_stored_timestamp_is_read_as_utc(self):
        # SQLite has no time zones and returns naive datetimes.  If the reaper
        # compared those against an aware cutoff it would raise TypeError, and
        # the safety net would be the thing that broke.
        run_id = self.insert_run(
            started_at=datetime.now(timezone.utc) - timedelta(days=1)
        )
        session = self.SessionLocal()
        try:
            self.assertIsNone(
                session.get(FinancialIngestionRun, run_id).started_at.tzinfo
            )
        finally:
            session.close()

        self.assertEqual(
            reap_stale_runs(
                older_than=timedelta(hours=1), session_factory=self.SessionLocal
            ),
            [run_id],
        )

    def test_reaping_leaves_a_live_run_of_the_service_alone(self):
        handle = open_ingestion_run(
            case_id=self.case.id, session_factory=self.SessionLocal
        )
        try:
            reaped = reap_stale_runs(
                older_than=timedelta(hours=1), session_factory=self.SessionLocal
            )
            self.assertEqual(reaped, [])
        finally:
            handle.terminate(IngestionRunStatus.completed)


class CodeVersionTests(unittest.TestCase):
    """The code version is measured from the source, never declared."""

    def setUp(self):
        self._real_root = version._PACKAGE_ROOT
        self._directory = Path(tempfile.mkdtemp(prefix="loupe-version-"))
        reset_caches()

    def tearDown(self):
        version._PACKAGE_ROOT = self._real_root
        shutil.rmtree(self._directory, ignore_errors=True)
        reset_caches()

    def use_package(self, files: dict[str, str]) -> None:
        for name, body in files.items():
            path = self._directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        version._PACKAGE_ROOT = self._directory
        reset_caches()

    def test_the_real_package_fingerprints_itself(self):
        value = code_version()
        self.assertTrue(value.startswith(f"{PIPELINE_VERSION}+"))
        self.assertNotIn(UNVERIFIED, value)

    def test_the_version_is_stable_across_calls(self):
        self.assertEqual(code_version(), code_version())

    def test_the_detail_names_every_source_file(self):
        self.use_package({"__init__.py": "", "money.py": "x = 1\n"})
        detail = code_fingerprint_detail()
        self.assertEqual(sorted(detail), ["__init__.py", "money.py"])

    def test_editing_a_source_file_changes_the_version(self):
        self.use_package({"__init__.py": "", "runs.py": "x = 1\n"})
        before = code_version()

        self.use_package({"__init__.py": "", "runs.py": "x = 2\n"})
        self.assertNotEqual(before, code_version())

    def test_even_a_comment_changes_the_version(self):
        # Honest churn, and the correct trade: the fingerprint is over bytes,
        # and a version that only moves when someone decides it should is the
        # version that is stale when it matters.
        self.use_package({"__init__.py": "", "runs.py": "x = 1\n"})
        before = code_version()

        self.use_package({"__init__.py": "", "runs.py": "x = 1  # note\n"})
        self.assertNotEqual(before, code_version())

    def test_renaming_a_file_changes_the_version(self):
        self.use_package({"__init__.py": "", "parser.py": "x = 1\n"})
        before = code_version()

        shutil.rmtree(self._directory)
        self.use_package({"__init__.py": "", "parsers.py": "x = 1\n"})
        # Identical content under a different name: a different module runs, so
        # this must not be invisible.
        self.assertNotEqual(before, code_version())

    def test_adding_a_file_changes_the_version(self):
        self.use_package({"__init__.py": ""})
        before = code_version()

        self.use_package({"__init__.py": "", "extra.py": "\n"})
        self.assertNotEqual(before, code_version())

    def test_bytecode_is_ignored(self):
        self.use_package({"__init__.py": "", "runs.py": "x = 1\n"})
        before = code_version()

        (self._directory / "__pycache__").mkdir()
        (self._directory / "__pycache__" / "runs.py").write_text("noise\n")
        reset_caches()
        self.assertEqual(before, code_version())

    def test_an_unreadable_package_is_recorded_as_unverified(self):
        version._PACKAGE_ROOT = self._directory / "does-not-exist"
        reset_caches()
        # Loud rather than silent: recording a bare version here would assert a
        # precision that was never established.
        self.assertEqual(code_version(), f"{PIPELINE_VERSION}+{UNVERIFIED}")


class RulesetVersionTests(unittest.TestCase):
    """The ruleset version is derived from the rules that were in force."""

    def test_no_ruleset_gives_no_version(self):
        self.assertIsNone(ruleset_version(None))

    def test_key_order_does_not_change_the_version(self):
        self.assertEqual(
            ruleset_version({"a": 1, "b": 2}),
            ruleset_version({"b": 2, "a": 1}),
        )

    def test_a_changed_rule_changes_the_version(self):
        self.assertNotEqual(
            ruleset_version({"tolerance_minor": 0}),
            ruleset_version({"tolerance_minor": 1}),
        )

    def test_an_empty_ruleset_is_not_the_same_as_no_ruleset(self):
        self.assertIsNotNone(ruleset_version({}))

    def test_the_version_is_labelled(self):
        self.assertTrue(ruleset_version({"a": 1}).startswith("rules+"))

    def test_a_non_serialisable_ruleset_is_refused(self):
        # Coercing here would produce a version that no longer identifies the
        # rules it names, which is the precise failure this guards against.
        with self.assertRaises(TypeError):
            ruleset_version({"cutoff": date(2026, 3, 1)})

    def test_a_nan_tolerance_is_refused(self):
        with self.assertRaises(ValueError):
            ruleset_version({"tolerance": float("nan")})


if __name__ == "__main__":
    unittest.main()
