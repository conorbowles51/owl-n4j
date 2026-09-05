"""Tests for reading ingestion runs back out.

``services.financial.runs`` has written a row per pipeline execution since it
was built, and until ``list_runs``/``to_run_view`` nothing read one. The tests
here are organised around the two things this read has to get right, both of
which are places it deliberately differs from the ledger read beside it.

*The default population is every status.* ``list_transactions`` defaults to
admitted because that is the population totals are filtered to. Runs invert
that: a failed or aborted run is the reason to look at all, so
:class:`ListRunsTests` checks that the unfiltered call returns failures
alongside completions, that an explicit status narrows it, and that the case
scoping and ordering a read endpoint needs are honest.

*Nothing is derived.* :class:`ToRunViewTests` checks that every field comes off
the stored row -- counts recorded when the run ended rather than recounted from
a ledger that adjudication has since moved, ``status`` as the plain string the
writer put there rather than an enum instance, and no judgement anywhere about
whether a ``running`` run has been abandoned. That judgement belongs to
``reap_stale_runs``, which writes it down; a reader making it independently
would be a second opinion with no record behind it.

The database-backed tests use a file on disk rather than ``:memory:``, matching
``test_financial_transaction_query``: the run service opens sessions of its own,
and a test where the caller and the bookkeeping share one connection cannot see
what production sees.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import GlobalRole, IngestionRunStatus
from postgres.models.financial import FinancialIngestionRun
from postgres.models.user import User
from services.financial.run_query import (
    RunQueryError,
    list_runs,
    to_run_view,
)
from services.financial.runs import open_ingestion_run

TABLES = [
    User.__table__,
    Case.__table__,
    FinancialIngestionRun.__table__,
]

#: A fixed instant, so ordering assertions do not depend on how fast the test
#: machine gets through three inserts.
NOON = datetime(2026, 3, 4, 12, 0, 0, tzinfo=timezone.utc)


class RunQueryTestCase(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.mkdtemp(prefix="loupe-run-query-")
        self.engine = create_engine(
            f"sqlite+pysqlite:///{Path(self._directory) / 'runs.db'}",
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
            title="Run Query Fixture",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        self.other_case = Case(
            id=uuid.uuid4(),
            title="A Different Matter",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        self.db.add_all([self.user, self.case, self.other_case])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        shutil.rmtree(self._directory, ignore_errors=True)

    def run_row(
        self,
        *,
        case_id=None,
        status=IngestionRunStatus.completed,
        started_at=NOON,
        **overrides,
    ) -> FinancialIngestionRun:
        """A stored run, written directly so status and time are exact."""
        row = FinancialIngestionRun(
            id=uuid.uuid4(),
            case_id=case_id or self.case.id,
            status=status.value,
            started_at=started_at,
            **overrides,
        )
        self.db.add(row)
        self.db.commit()
        return row


class ListRunsTests(RunQueryTestCase):
    def test_defaults_to_every_status_not_just_the_ones_that_worked(self):
        """The inversion of the ledger read's default, and the point of it."""
        completed = self.run_row(status=IngestionRunStatus.completed)
        failed = self.run_row(status=IngestionRunStatus.failed)
        aborted = self.run_row(status=IngestionRunStatus.aborted)
        running = self.run_row(status=IngestionRunStatus.running)
        pending = self.run_row(status=IngestionRunStatus.pending)

        found = {row.id for row in list_runs(self.db, self.case.id)}

        self.assertEqual(
            found,
            {completed.id, failed.id, aborted.id, running.id, pending.id},
        )

    def test_an_explicit_status_narrows_the_population(self):
        failed = self.run_row(status=IngestionRunStatus.failed)
        self.run_row(status=IngestionRunStatus.completed)

        rows = list_runs(
            self.db, self.case.id, status=IngestionRunStatus.failed
        )

        self.assertEqual([row.id for row in rows], [failed.id])

    def test_newest_first(self):
        oldest = self.run_row(started_at=NOON - timedelta(hours=2))
        newest = self.run_row(started_at=NOON)
        middle = self.run_row(started_at=NOON - timedelta(hours=1))

        rows = list_runs(self.db, self.case.id)

        self.assertEqual(
            [row.id for row in rows], [newest.id, middle.id, oldest.id]
        )

    def test_another_case_is_not_visible(self):
        mine = self.run_row()
        self.run_row(case_id=self.other_case.id)

        rows = list_runs(self.db, self.case.id)

        self.assertEqual([row.id for row in rows], [mine.id])

    def test_limit_takes_the_newest_not_an_arbitrary_slice(self):
        newest = self.run_row(started_at=NOON)
        self.run_row(started_at=NOON - timedelta(hours=1))
        self.run_row(started_at=NOON - timedelta(hours=2))

        rows = list_runs(self.db, self.case.id, limit=1)

        self.assertEqual([row.id for row in rows], [newest.id])

    def test_a_limit_of_zero_is_refused_rather_than_returning_nothing(self):
        """Zero would look like a request and answer with silence."""
        self.run_row()

        with self.assertRaises(RunQueryError):
            list_runs(self.db, self.case.id, limit=0)

    def test_a_negative_limit_is_refused(self):
        with self.assertRaises(RunQueryError):
            list_runs(self.db, self.case.id, limit=-1)

    def test_a_case_with_no_runs_returns_empty_rather_than_raising(self):
        self.assertEqual(list_runs(self.db, self.other_case.id), [])

    def test_the_ordering_is_total_so_equal_timestamps_do_not_reorder(self):
        """Two runs started in the same instant still come back in one order.

        ``started_at`` alone is not a total order and a case can hold two runs
        opened within the same recorded moment. The secondary sort on ``id``
        is what stops the same query answering differently on two calls.
        """
        first = self.run_row(started_at=NOON)
        second = self.run_row(started_at=NOON)
        expected = sorted([first.id, second.id], key=str)

        once = [row.id for row in list_runs(self.db, self.case.id)]
        self.db.expire_all()
        twice = [row.id for row in list_runs(self.db, self.case.id)]

        self.assertEqual(once, twice)
        self.assertEqual(once, expected)


class ToRunViewTests(RunQueryTestCase):
    def test_counts_are_the_recorded_ones(self):
        """Read off the row, never recounted from the ledger.

        The model's own docstring is explicit that recomputing these against a
        ledger adjudication has since moved would answer a different question.
        """
        row = self.run_row(
            documents_seen=3,
            transactions_admitted=118,
            transactions_quarantined=2,
        )

        view = to_run_view(row)

        self.assertEqual(view.documents_seen, 3)
        self.assertEqual(view.transactions_admitted, 118)
        self.assertEqual(view.transactions_quarantined, 2)

    def test_status_comes_back_as_a_plain_string(self):
        row = self.run_row(status=IngestionRunStatus.failed)

        view = to_run_view(row)

        self.assertEqual(view.status, "failed")
        self.assertNotIsInstance(view.status, IngestionRunStatus)

    def test_a_failure_carries_its_reason(self):
        """The error and the moment it stopped, both off the row.

        ``completed_at`` is asserted against the stored value rather than
        against the literal that was written. The column is
        ``DateTime(timezone=True)``: Postgres returns it with its offset and
        SQLite, having nowhere to keep one, returns it naive. Converting
        whatever was stored is this function's whole job, so pinning one
        backend's spelling of the instant would be testing the driver.
        """
        row = self.run_row(
            status=IngestionRunStatus.failed,
            error="IngestionError: row 14 names an account the document never introduced",
            completed_at=NOON + timedelta(minutes=2),
        )

        view = to_run_view(row)

        self.assertIn("row 14", view.error)
        self.assertEqual(view.completed_at, row.completed_at.isoformat())
        self.assertTrue(view.completed_at.startswith("2026-03-04T12:02:00"))

    def test_a_running_run_has_no_completion_and_no_verdict(self):
        """It is reported as running. Nothing here calls it abandoned."""
        row = self.run_row(status=IngestionRunStatus.running)

        view = to_run_view(row)

        self.assertEqual(view.status, "running")
        self.assertIsNone(view.completed_at)
        self.assertIsNone(view.error)

    def test_the_starting_email_survives_the_user_id_being_gone(self):
        """The reason the writer records both is that one of them nulls.

        ``started_by_user_id`` is ``ON DELETE SET NULL``; ``started_by_email``
        is a plain column and is not touched. Who started a run has to outlive
        the account being removed.
        """
        row = self.run_row(
            started_by_user_id=None,
            started_by_email="departed@example.test",
        )

        view = to_run_view(row)

        self.assertIsNone(view.started_by_user_id)
        self.assertEqual(view.started_by_email, "departed@example.test")

    def test_config_comes_back_as_a_plain_dict(self):
        row = self.run_row(config={"default_currency": "GBP"})

        view = to_run_view(row)

        self.assertEqual(view.config, {"default_currency": "GBP"})
        self.assertIsInstance(view.config, dict)

    def test_an_absent_config_reads_as_empty_not_none(self):
        row = self.run_row(config=None)

        self.assertEqual(to_run_view(row).config, {})

    def test_to_json_is_json_safe_throughout(self):
        """Every uuid a string, every datetime an ISO string, no enums."""
        import json

        row = self.run_row(
            status=IngestionRunStatus.completed,
            started_by_user_id=self.user.id,
            started_by_email=self.user.email,
            completed_at=NOON + timedelta(minutes=5),
            documents_seen=1,
            transactions_admitted=40,
            notes="second pass over the March statement",
        )

        payload = to_run_view(row).to_json()

        # Would raise if anything in the shape were a uuid, datetime or enum.
        json.dumps(payload)
        self.assertEqual(payload["key"], str(row.id))
        self.assertEqual(payload["case_id"], str(self.case.id))
        self.assertEqual(payload["started_by_user_id"], str(self.user.id))


class RunQueryAgainstTheWriterTests(RunQueryTestCase):
    """The read against runs the run service itself opened and terminated.

    The tests above write rows directly so that status and timestamps are
    exact. These two check the read is not merely self-consistent: a run opened
    and closed through ``open_ingestion_run`` has to come back saying what
    actually happened to it.
    """

    def test_a_run_opened_by_the_service_is_visible_while_it_is_running(self):
        handle = open_ingestion_run(
            case_id=self.case.id,
            actor=self.user,
            session_factory=self.SessionLocal,
        )

        (row,) = list_runs(self.db, self.case.id)
        view = to_run_view(row)

        self.assertEqual(view.key, str(handle.run_id))
        self.assertEqual(view.status, "running")
        self.assertEqual(view.started_by_email, self.user.email)
        self.assertIsNone(view.completed_at)

    def test_terminating_a_run_is_what_the_read_then_reports(self):
        handle = open_ingestion_run(
            case_id=self.case.id,
            actor=self.user,
            session_factory=self.SessionLocal,
        )
        handle.document_seen()
        handle.transaction_admitted(count=40)
        handle.transaction_quarantined()
        handle.terminate(IngestionRunStatus.completed)

        self.db.expire_all()
        (row,) = list_runs(self.db, self.case.id)
        view = to_run_view(row)

        self.assertEqual(view.status, "completed")
        self.assertIsNotNone(view.completed_at)
        self.assertEqual(view.documents_seen, 1)
        self.assertEqual(view.transactions_admitted, 40)
        self.assertEqual(view.transactions_quarantined, 1)


if __name__ == "__main__":
    unittest.main()
