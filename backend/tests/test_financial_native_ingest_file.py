"""Tests for the entry point that takes one evidence file all the way in.

``native_ingest`` is given a reading and an open run and writes them.  This
module's subject is everything around that: finding the file, reading it,
deciding whether the case should have it twice, owning the run's lifetime,
committing, and turning each documented failure into a word the caller can act
on.  So the assertions here are about *outcomes and side effects* rather than
about what any writer put in a column, which is the writer suites' question.

Three things are checked over and over because each of them has failed
somewhere before, in this package or another:

*The run outlives the rollback.*  A write that fails discards the half-written
document on the caller's session, and the record that the attempt happened must
survive that.  It does only because ``runs`` terminates on a session of its
own, so every failure test asserts the run row is still there and says
``failed``.

*A file that will not parse opens no run.*  A run whose counts are all zero
because somebody uploaded a photograph is a record of nothing, and the reading
failures are the cases where nothing was attempted.

*The commit happened.*  ``ingest_case_file`` is the only layer that commits.
The stored tests read the rows back through a second session, because a test
that reads them through the session that wrote them would pass on a function
that never committed at all.

The failures that come from the writers are provoked two ways on purpose.
``contradictory_period`` has bytes that genuinely cause it, so it is driven end
to end and is the test that actually proves the run and rollback behaviour.
The others are provoked by making ``ingest_native_reading`` raise, because what
is under test there is the translation of an exception into an outcome, and
constructing a file that produces each one would test the writers a second
time in the suite that is least able to say anything useful about them.

The database is a file on disk rather than ``:memory:``, matching
``test_financial_native_ingest``: the run service opens sessions of its own,
and a test where the caller and the bookkeeping share one connection cannot see
what production sees.
"""

from __future__ import annotations

import datetime
import shutil
import tempfile
import unittest
import uuid
from datetime import date as D
from inspect import signature
from pathlib import Path
from unittest import mock

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import GlobalRole, IngestionRunStatus
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
from services.financial.accounts import AccountError
from services.financial.native import CenturyWindow
from services.financial.native_ingest import (
    ContradictoryPeriodError,
    IngestionError,
    UnattributableRowError,
)
from services.financial.native_ingest_file import (
    READING_OUTCOMES,
    FileIngestion,
    IngestOutcome,
    existing_document_for,
    ingest_case_file,
)
from services.financial.native_precheck import PrecheckOutcome
from services.financial.native_subjects import SubjectError

# The parser suites' own fixture builders, for the reason
# ``test_financial_native_ingest`` gives: a second copy of a file layout drifts
# from the first the moment either changes, and the two then disagree silently.
from tests.test_financial_camt053 import stmt
from tests.test_financial_native import (
    WINDOW,
    bai2_bytes,
    camt_bytes,
    mt940_bytes,
)
from tests.test_financial_native_ingest import disagreeing

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

#: The IBAN ``stmt()`` prints, and so the key its rows carry.
IBAN = "GB29NWBK60161331926819"

#: A window no statement in these fixtures falls inside.  Used to provoke the
#: two-digit-year failure, which is the one reading outcome that needs a file
#: the parsers *can* read.
FOREIGN_WINDOW = CenturyWindow(D(2000, 1, 1), D(2009, 12, 31))

CONTRADICTORY = camt_bytes(statements=stmt(identification="A") + disagreeing("B"))

#: Distinguishes "the helper picks a path" from a path a test chose, including
#: the empty one.  See ``IngestFileTestCase.evidence``.
_DEFAULT_PATH = object()


class IngestFileTestCase(unittest.TestCase):
    """One case, and evidence files whose bytes are really on disk.

    ``resolve_path`` exists because a stored path is not always a path in this
    process, so the tests use one: rows record a container-shaped path and the
    resolver maps it onto the temp directory the bytes were actually written
    to.  A test that passed ``Path`` straight through would not exercise the
    argument the router is obliged to supply.
    """

    def setUp(self):
        self._directory = tempfile.mkdtemp(prefix="loupe-ingest-file-")
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
            title="Ingest Entry Point Fixture",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        self.other_case = Case(
            id=uuid.uuid4(),
            title="Somebody Else's Matter",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        self.db.add_all([self.user, self.case, self.other_case])
        self.db.commit()

        self._files = 0

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        shutil.rmtree(self._directory, ignore_errors=True)

    # -- helpers ------------------------------------------------------------

    def resolve_path(self, stored_path):
        """The router's job, in one line: a recorded path onto a real one."""
        if not stored_path:
            return None
        return Path(self._directory) / Path(stored_path).name

    def evidence(
        self,
        data: bytes = None,
        *,
        case=None,
        sha256: str = None,
        stored_path=_DEFAULT_PATH,
        write: bool = True,
    ) -> EvidenceFile:
        """An evidence row, with its bytes on disk unless asked otherwise.

        ``stored_path`` takes a sentinel rather than defaulting to ``None`` or
        ``""``, because both of those are values a test needs to be able to ask
        for: the column is ``NOT NULL``, so the pathless file production can
        actually hold is the empty one.
        """
        self._files += 1
        name = f"statement-{self._files}.dat"
        record = EvidenceFile(
            id=uuid.uuid4(),
            case_id=(case or self.case).id,
            original_filename=name,
            stored_path=(
                f"/evidence/{name}" if stored_path is _DEFAULT_PATH else stored_path
            ),
            sha256=sha256 or (f"{self._files:02d}" * 32),
        )
        self.db.add(record)
        self.db.commit()
        if write and data is not None:
            (Path(self._directory) / name).write_bytes(data)
        return record

    def ingest(self, record: EvidenceFile, **kwargs) -> FileIngestion:
        kwargs.setdefault("window", WINDOW)
        return ingest_case_file(
            self.db,
            case_id=kwargs.pop("case_id", self.case.id),
            file_id=record.id,
            resolve_path=self.resolve_path,
            actor=kwargs.pop("actor", self.user),
            session_factory=self.SessionLocal,
            **kwargs,
        )

    # -- reading the record back --------------------------------------------

    def fresh(self):
        """A session that has never seen the write, for asserting the commit."""
        return self.SessionLocal()

    def runs(self) -> list[FinancialIngestionRun]:
        with self.fresh() as session:
            return list(
                session.execute(
                    select(FinancialIngestionRun).order_by(
                        FinancialIngestionRun.started_at
                    )
                ).scalars()
            )

    def documents(self) -> list[FinancialSourceDocument]:
        with self.fresh() as session:
            return list(
                session.execute(select(FinancialSourceDocument)).scalars()
            )

    def transactions(self) -> list[FinancialTransaction]:
        with self.fresh() as session:
            return list(session.execute(select(FinancialTransaction)).scalars())

    def assertOnlyRunIs(self, status: IngestionRunStatus):
        runs = self.runs()
        self.assertEqual(len(runs), 1, "expected exactly one run")
        self.assertEqual(runs[0].status, status.value)
        return runs[0]


# ---------------------------------------------------------------------------
# The ordinary case
# ---------------------------------------------------------------------------


class StoredTests(IngestFileTestCase):
    """A file the case should have, arriving whole and staying arrived."""

    def test_a_camt053_file_is_stored_and_the_run_completes(self):
        result = self.ingest(self.evidence(camt_bytes()))

        self.assertIs(result.outcome, IngestOutcome.stored)
        self.assertTrue(result.stored)
        self.assertIsNone(result.reason)
        self.assertEqual(result.detected_format, "camt053")
        self.assertOnlyRunIs(IngestionRunStatus.completed)

    def test_the_rows_survive_a_session_that_never_saw_the_write(self):
        """The commit is this module's, and nothing below it would do it.

        Read back through a second session on purpose.  Every writer flushes
        and none commits, so a version of ``ingest_case_file`` with the commit
        deleted would still return a result naming rows and identifiers -- and
        a test reading through ``self.db`` would confirm every one of them,
        moments before the transaction was discarded.
        """
        result = self.ingest(self.evidence(camt_bytes()))

        documents = self.documents()
        self.assertEqual(len(documents), 1)
        self.assertEqual(str(documents[0].id), result.document_id)
        self.assertEqual(
            len(self.transactions()), result.transactions_stored
        )
        self.assertGreater(result.transactions_stored, 0)

    def test_the_reported_identifiers_are_the_rows_that_were_written(self):
        result = self.ingest(self.evidence(camt_bytes()))

        with self.fresh() as session:
            accounts = set(
                str(row.id)
                for row in session.execute(select(FinancialAccount)).scalars()
            )
            periods = set(
                str(row.id)
                for row in session.execute(
                    select(FinancialStatementPeriod)
                ).scalars()
            )

        self.assertEqual(set(result.account_ids), accounts)
        self.assertEqual(set(result.period_ids), periods)
        self.assertTrue(result.account_ids)
        self.assertTrue(result.period_ids)

    def test_the_document_and_its_rows_name_the_run_that_was_reported(self):
        """The run in the response is the run on the record.

        Provenance is the whole point of the run, and a response naming a
        different one would send anyone tracing a figure to the wrong record.
        """
        result = self.ingest(self.evidence(camt_bytes()))

        with self.fresh() as session:
            document = session.get(
                FinancialSourceDocument, uuid.UUID(result.document_id)
            )
            self.assertEqual(str(document.ingestion_run_id), result.run_id)
            for row in session.execute(select(FinancialTransaction)).scalars():
                self.assertEqual(str(row.ingestion_run_id), result.run_id)

    def test_every_format_this_repository_parses_goes_in(self):
        """Not a parser test.  A test that the entry point is not camt-shaped.

        The reading and the writing are both exercised elsewhere per format;
        what could plausibly break only here is a step that assumed something
        camt053 happens to have, so each format needs to have gone through the
        whole path at least once.
        """
        for label, data in (
            ("camt053", camt_bytes()),
            ("bai2", bai2_bytes()),
            ("mt940", mt940_bytes()),
        ):
            with self.subTest(format=label):
                result = self.ingest(self.evidence(data))
                self.assertIs(result.outcome, IngestOutcome.stored)
                self.assertEqual(result.detected_format, label)
                self.assertGreater(result.transactions_stored, 0)

    def test_the_run_records_who_asked_for_it(self):
        self.ingest(self.evidence(camt_bytes()))

        run = self.assertOnlyRunIs(IngestionRunStatus.completed)
        self.assertEqual(run.started_by_user_id, self.user.id)
        self.assertEqual(run.started_by_email, self.user.email)

    def test_the_document_type_can_be_overridden(self):
        result = self.ingest(
            self.evidence(camt_bytes()), document_type="bank statement"
        )

        with self.fresh() as session:
            document = session.get(
                FinancialSourceDocument, uuid.UUID(result.document_id)
            )
            self.assertEqual(document.document_type, "bank statement")

        # The detected format is still reported as detected.  Overriding what
        # the document is called does not change what the file was read as,
        # and conflating the two would make the response unable to say a
        # parser had been chosen wrongly.
        self.assertEqual(result.detected_format, "camt053")

    def test_the_institution_is_recorded_as_given(self):
        result = self.ingest(
            self.evidence(camt_bytes()), institution_name="Barclays"
        )

        with self.fresh() as session:
            document = session.get(
                FinancialSourceDocument, uuid.UUID(result.document_id)
            )
            self.assertEqual(document.institution_name, "Barclays")


# ---------------------------------------------------------------------------
# Files that never reach a run
# ---------------------------------------------------------------------------


class UnreadTests(IngestFileTestCase):
    """Every way the bytes can fail before a run would be worth opening."""

    def assertNoRun(self, result: FileIngestion, outcome: IngestOutcome):
        self.assertIs(result.outcome, outcome)
        self.assertIsNone(result.run_id)
        self.assertEqual(self.runs(), [])
        self.assertEqual(self.documents(), [])
        self.assertIsNotNone(result.reason)

    def test_a_file_in_another_case_is_not_found(self):
        record = self.evidence(camt_bytes(), case=self.other_case)

        self.assertNoRun(self.ingest(record), IngestOutcome.not_found)

    def test_a_file_that_does_not_exist_is_not_found(self):
        result = ingest_case_file(
            self.db,
            case_id=self.case.id,
            file_id=uuid.uuid4(),
            resolve_path=self.resolve_path,
            window=WINDOW,
            session_factory=self.SessionLocal,
        )

        self.assertNoRun(result, IngestOutcome.not_found)

    def test_a_file_in_another_case_is_worded_as_a_missing_one(self):
        """Asking cannot be used to learn what another case contains.

        The two are separate tests because the wording is the security
        property, not an incidental: a distinguishable message would let a
        caller enumerate file identifiers across matters by watching which
        answer came back.
        """
        elsewhere = self.ingest(self.evidence(camt_bytes(), case=self.other_case))
        missing = ingest_case_file(
            self.db,
            case_id=self.case.id,
            file_id=uuid.uuid4(),
            resolve_path=self.resolve_path,
            window=WINDOW,
            session_factory=self.SessionLocal,
        )

        self.assertEqual(elsewhere.reason, missing.reason)
        self.assertIs(elsewhere.outcome, missing.outcome)

    def test_bytes_no_parser_claims_are_unrecognised(self):
        record = self.evidence(b"a photograph of a bank statement, probably\n")

        self.assertNoRun(self.ingest(record), IngestOutcome.unrecognised)

    def test_a_file_with_no_stored_path_is_unreadable(self):
        """Empty and not ``None``: ``evidence_files.stored_path`` is NOT NULL,
        so a row with nowhere to read from is one holding the empty string, and
        that is what the resolver has to be given."""
        record = self.evidence(camt_bytes(), stored_path="", write=False)

        self.assertNoRun(self.ingest(record), IngestOutcome.unreadable)

    def test_a_file_whose_bytes_are_gone_is_unreadable(self):
        record = self.evidence(camt_bytes(), write=False)

        self.assertNoRun(self.ingest(record), IngestOutcome.unreadable)

    def test_a_two_digit_year_outside_the_window_is_out_of_window(self):
        """The window is the caller's, and a file that cannot fit it is said so.

        ``mt940`` prints two-digit years, so the reading depends entirely on
        the window; asked to place this statement in the 2000s, the parser
        cannot, and that is a fact about the request rather than a fault.
        """
        record = self.evidence(mt940_bytes())

        self.assertNoRun(
            self.ingest(record, window=FOREIGN_WINDOW),
            IngestOutcome.out_of_window,
        )

    def test_a_file_with_no_recorded_hash_is_unreadable(self):
        """The hash is what tells one unidentified account from another.

        Set directly rather than through the helper, because the column is
        ``NOT NULL`` and a row like this is one that predates the constraint.
        """
        record = self.evidence(camt_bytes())
        self.db.execute(
            EvidenceFile.__table__.update()
            .where(EvidenceFile.id == record.id)
            .values(sha256="   ")
        )
        self.db.commit()

        self.assertNoRun(self.ingest(record), IngestOutcome.unreadable)


# ---------------------------------------------------------------------------
# The same file twice
# ---------------------------------------------------------------------------


class ReingestTests(IngestFileTestCase):
    """The refusal of a file the case already holds, and what it is for.

    Not for stopping the ledger doubling: the schema does that on its own, and
    ``test_the_schema_and_not_the_guard_is_what_stops_the_doubling`` holds it
    to it.  The refusal is for what happens instead, which is a constraint name
    arriving as a failed write after a run has been opened and a document
    written and discarded.
    """

    def setUp(self):
        super().setUp()
        self.record = self.evidence(camt_bytes())
        self.first = self.ingest(self.record)
        self.assertIs(self.first.outcome, IngestOutcome.stored)

    def test_a_second_ingest_is_refused_and_writes_nothing(self):
        second = self.ingest(self.record)

        self.assertIs(second.outcome, IngestOutcome.already_ingested)
        self.assertEqual(len(self.documents()), 1)
        self.assertEqual(
            len(self.transactions()), self.first.transactions_stored
        )

    def test_the_refusal_names_the_document_that_already_holds_it(self):
        """A refusal that did not say where the file went would be a dead end.

        The identifiers are the response's whole use to an interface: they are
        what lets it offer to show the reader the ledger the file is already
        in, instead of an error with nothing behind it.
        """
        second = self.ingest(self.record)

        self.assertEqual(second.document_id, self.first.document_id)
        self.assertEqual(second.run_id, self.first.run_id)
        self.assertEqual(second.detected_format, "camt053")
        self.assertIn("already holds", second.reason)

    def test_the_refusal_opens_no_run(self):
        """Only one run, and it is the completed one from setUp."""
        self.ingest(self.record)

        self.assertOnlyRunIs(IngestionRunStatus.completed)

    def test_there_is_no_way_to_ask_for_the_second_reading_anyway(self):
        """No override, because nothing reachable could resolve what it left.

        A re-read whose rows hash differently -- a corrected window, a
        different assumed currency -- is the only one the constraint below
        would let through, and it would leave one case holding two
        contradictory readings of one file.  ``duplicates`` is what resolves
        that and it is not wired to anything yet.
        """
        parameters = signature(ingest_case_file).parameters
        self.assertNotIn("reingest", parameters)
        self.assertNotIn("force", parameters)

    def test_the_schema_and_not_the_guard_is_what_stops_the_doubling(self):
        """Deleting the guard would not double the money.  It would obscure it.

        ``ref_id`` is derived from the file's digest and the row's content, so
        a second reading of unchanged bytes reproduces every reference exactly
        and ``uq_financial_transactions_case_ref`` refuses the set.  This is
        asserted rather than assumed because the module's refusal is justified
        on it: if a future change made ``ref_id`` vary between readings, the
        early refusal would become the only thing standing between one file and
        two sets of transactions, and this test is what would say so.
        """
        # The guard's own lookup is what is being bypassed, so bypass exactly
        # that and leave the rest of the path alone.
        with mock.patch(
            "services.financial.native_ingest_file.existing_document_for",
            return_value=None,
        ):
            second = self.ingest(self.record)

        self.assertIs(second.outcome, IngestOutcome.write_failed)
        # The table and not the constraint's name: SQLite names the columns and
        # Postgres names the constraint, and pinning either would make this a
        # test of which database the suite happens to run on.
        self.assertIn("financial_transactions", second.reason)
        self.assertEqual(
            len(self.transactions()),
            self.first.transactions_stored,
            "the refused set must not have left rows behind",
        )
        self.assertEqual(
            len(self.documents()),
            1,
            "the document written before the constraint fired is rolled back",
        )
        self.assertEqual(
            [run.status for run in self.runs()],
            [IngestionRunStatus.completed.value, IngestionRunStatus.failed.value],
            "the attempt is on the record even though nothing of it survived",
        )

    def test_the_same_file_in_another_case_is_not_a_repeat(self):
        """The guard is per case, because a ledger is per case.

        Two matters can hold the same statement and neither's totals are
        affected by the other's.  A guard keyed on the evidence file alone
        would refuse the second matter its own copy.
        """
        shared = self.evidence(camt_bytes(), case=self.other_case)
        result = self.ingest(shared, case_id=self.other_case.id)

        self.assertIs(result.outcome, IngestOutcome.stored)
        self.assertEqual(len(self.documents()), 2)


class ExistingDocumentTests(IngestFileTestCase):
    """The lookup the guard is built on, on its own."""

    def test_nothing_ingested_means_no_document(self):
        record = self.evidence(camt_bytes())

        self.assertIsNone(
            existing_document_for(
                self.db, case_id=self.case.id, file_id=record.id
            )
        )

    def test_it_is_scoped_to_the_case(self):
        record = self.evidence(camt_bytes())
        self.ingest(record)

        self.assertIsNone(
            existing_document_for(
                self.db, case_id=self.other_case.id, file_id=record.id
            )
        )

    def test_it_returns_the_earliest_of_several(self):
        """Earliest, so the answer is the document the ledger was built on.

        Nothing in this module writes the second one -- the refusal it feeds is
        what stops that -- so the second is written here directly.  The lookup
        still has to order, because ``documents.py`` writes one row per file
        per run by design and unit 9 of the wiring plan is where a case comes
        to hold more than one legitimately.  Someone asking "where did this
        file go" wants the row the existing figures came from.
        """
        record = self.evidence(camt_bytes())
        first = self.ingest(record)
        self.assertIs(first.outcome, IngestOutcome.stored)

        earlier = self.db.get(FinancialSourceDocument, uuid.UUID(first.document_id))
        # A run of its own, because ``financial_source_documents`` is unique on
        # ``(ingestion_run_id, evidence_file_id)``: one row per file per run is
        # the rule, and a second row is by definition a second run.
        later_run = FinancialIngestionRun(
            id=uuid.uuid4(),
            case_id=self.case.id,
            status=IngestionRunStatus.completed.value,
        )
        self.db.add(later_run)
        self.db.flush()
        self.db.add(
            FinancialSourceDocument(
                id=uuid.uuid4(),
                case_id=self.case.id,
                evidence_file_id=record.id,
                ingestion_run_id=later_run.id,
                sha256_at_ingestion=earlier.sha256_at_ingestion,
                document_type=earlier.document_type,
                proof_class=earlier.proof_class,
                extraction_layer=earlier.extraction_layer,
                parser_name=earlier.parser_name,
                parser_version=earlier.parser_version,
                # Explicit rather than defaulted: the two rows are written in
                # the same second, and the ordering under test is the point.
                created_at=earlier.created_at + datetime.timedelta(days=1),
            )
        )
        self.db.commit()

        self.assertEqual(len(self.documents()), 2)
        found = existing_document_for(
            self.db, case_id=self.case.id, file_id=record.id
        )
        self.assertEqual(str(found.id), first.document_id)


# ---------------------------------------------------------------------------
# Failures inside the write
# ---------------------------------------------------------------------------


class ContradictionTests(IngestFileTestCase):
    """One real file that fails inside the write, followed all the way down.

    This is the test that proves the run and rollback behaviour, because it is
    the one where every layer is the real one.  The patched tests below check
    only that each exception becomes the right word.
    """

    def test_a_self_contradicting_document_is_refused_by_name(self):
        result = self.ingest(self.evidence(CONTRADICTORY))

        self.assertIs(result.outcome, IngestOutcome.contradictory_period)
        self.assertIn(IBAN, result.reason)
        self.assertEqual(result.detected_format, "camt053")

    def test_the_refusal_writes_nothing(self):
        self.ingest(self.evidence(CONTRADICTORY))

        self.assertEqual(self.documents(), [])
        self.assertEqual(self.transactions(), [])

    def test_the_run_survives_the_rollback_and_says_it_failed(self):
        """The record that the attempt happened is the point of the run.

        The caller's session discards the half-written document.  The run is
        written on a session of its own, which is what lets it still be there
        afterwards -- and without it a refused ingest would leave no trace at
        all, so a case with a document missing would have nothing to explain
        why.
        """
        result = self.ingest(self.evidence(CONTRADICTORY))

        run = self.assertOnlyRunIs(IngestionRunStatus.failed)
        self.assertEqual(str(run.id), result.run_id)

    def test_the_session_is_usable_afterwards(self):
        """A refusal leaves the caller a session it can keep working in.

        The router returns 200 carrying the outcome, so the request continues
        past this point; a session left mid-transaction would fail the next
        thing to touch it, at a line with nothing wrong with it.
        """
        self.ingest(self.evidence(CONTRADICTORY))

        good = self.ingest(self.evidence(camt_bytes()))
        self.assertIs(good.outcome, IngestOutcome.stored)

    def test_a_good_file_still_goes_in_after_one_was_refused(self):
        """Two runs, one failed and one completed, both on the record."""
        self.ingest(self.evidence(CONTRADICTORY))
        self.ingest(self.evidence(camt_bytes()))

        self.assertEqual(
            [run.status for run in self.runs()],
            [IngestionRunStatus.failed.value, IngestionRunStatus.completed.value],
        )


class WriteFailureTranslationTests(IngestFileTestCase):
    """Each documented failure, arriving as its own word rather than an error.

    ``ingest_native_reading`` is made to raise rather than provoked into it.
    What is under test is the mapping, and the writers each have a suite that
    proves they raise these for the right reasons; building four files to
    re-prove it here would tie this suite to parser details it has no business
    knowing about.
    """

    def raising(self, exception: Exception) -> FileIngestion:
        with mock.patch(
            "services.financial.native_ingest_file.ingest_native_reading",
            side_effect=exception,
        ):
            return self.ingest(self.evidence(camt_bytes()))

    def assertRefused(self, exception, outcome: IngestOutcome):
        with self.assertLogs("services.financial", level="ERROR"):
            result = self.raising(exception)
        self.assertIs(result.outcome, outcome)
        self.assertEqual(result.reason, str(exception))
        self.assertEqual(result.detected_format, "camt053")
        run = self.assertOnlyRunIs(IngestionRunStatus.failed)
        self.assertEqual(str(run.id), result.run_id)
        self.assertEqual(self.documents(), [])
        return result

    def assertRefusedQuietly(self, exception, outcome: IngestOutcome):
        """As above, for the refusals that are not logged as errors.

        A judgement about the evidence is not a fault, and logging it at
        ``ERROR`` would put a correctly refused file in the same place as a
        broken deployment.
        """
        result = self.raising(exception)
        self.assertIs(result.outcome, outcome)
        self.assertEqual(result.reason, str(exception))
        run = self.assertOnlyRunIs(IngestionRunStatus.failed)
        self.assertEqual(str(run.id), result.run_id)
        self.assertEqual(self.documents(), [])
        return result

    def test_accounts_that_cannot_be_described_are_undescribable(self):
        self.assertRefusedQuietly(
            SubjectError("no account could be described"),
            IngestOutcome.undescribable,
        )

    def test_a_row_naming_an_unknown_account_is_unattributable(self):
        self.assertRefusedQuietly(
            UnattributableRowError("row 4 names ELSEWHERE"),
            IngestOutcome.unattributable,
        )

    def test_a_contradicting_period_is_named_as_one(self):
        self.assertRefusedQuietly(
            ContradictoryPeriodError("two claims, one span"),
            IngestOutcome.contradictory_period,
        )

    def test_any_other_writer_refusal_is_refused(self):
        """``IngestionError`` is the base, and it is caught last on purpose.

        A refusal added to ``native_ingest`` after this was written arrives
        here as an outcome the interface can show, rather than escaping as a
        failed request with a traceback in it.
        """
        self.assertRefusedQuietly(
            IngestionError("some new rule"), IngestOutcome.refused
        )

    def test_a_fault_in_a_writer_is_a_write_failure(self):
        self.assertRefused(
            AccountError("column too long"), IngestOutcome.write_failed
        )

    def test_something_unanticipated_is_not_given_an_outcome(self):
        """A bug is not a finding, so it propagates.

        Inventing an outcome for an exception nobody predicted would file a
        defect in this code as a fact about the evidence, and the file would
        be recorded as unreadable when there is nothing wrong with it.
        """
        with self.assertRaises(ZeroDivisionError):
            self.raising(ZeroDivisionError("not about the evidence"))

        # The run still terminated, because ``ingestion_run`` marks it failed
        # on the way past.
        self.assertOnlyRunIs(IngestionRunStatus.failed)


# ---------------------------------------------------------------------------
# The vocabulary itself
# ---------------------------------------------------------------------------


class OutcomeVocabularyTests(unittest.TestCase):
    """The two enums have to stay in step, and only a test can hold them there."""

    def test_every_precheck_failure_has_an_ingest_word(self):
        """Total over the failures, so a new precheck outcome cannot be lost.

        ``_unread`` falls back to ``unreadable`` for anything unmapped, which
        is the safe answer and also a silent one: without this test a new
        ``PrecheckOutcome`` would be reported to the interface under the wrong
        word and nothing would say so.
        """
        failures = set(PrecheckOutcome) - {PrecheckOutcome.readable}

        self.assertEqual(set(READING_OUTCOMES), failures)

    def test_readable_is_deliberately_absent(self):
        """It is precheck's word for "this would ingest"; once it has, it is
        ``stored``."""
        self.assertNotIn(PrecheckOutcome.readable, READING_OUTCOMES)

    def test_the_shared_words_are_spelled_the_same(self):
        """A file precheck called ``unrecognised`` must not come back from
        ingest under another name, or the dialog that showed it is lying."""
        for precheck, ingest in READING_OUTCOMES.items():
            with self.subTest(outcome=precheck.value):
                self.assertEqual(precheck.value, ingest.value)

    def test_the_words_ingestion_adds_are_the_ones_only_it_can_decide(self):
        """Named exhaustively, so adding an outcome is a deliberate act.

        Each of these is a fact about rows already stored or about the write
        itself, which is exactly why precheck cannot report them and why the
        dialog cannot promise a file will go in.
        """
        added = set(IngestOutcome) - set(READING_OUTCOMES.values())

        self.assertEqual(
            {outcome.value for outcome in added},
            {
                "stored",
                "already_ingested",
                "undescribable",
                "contradictory_period",
                "refused",
                "write_failed",
            },
        )


class FileIngestionShapeTests(unittest.TestCase):
    """What the router serialises."""

    def test_stored_is_true_only_for_stored(self):
        for outcome in IngestOutcome:
            with self.subTest(outcome=outcome.value):
                result = FileIngestion(file_id="f", outcome=outcome)
                self.assertEqual(
                    result.stored, outcome is IngestOutcome.stored
                )

    def test_the_dict_carries_the_outcome_as_a_string(self):
        result = FileIngestion(
            file_id="f", outcome=IngestOutcome.already_ingested
        )

        self.assertEqual(result.as_dict()["outcome"], "already_ingested")
        self.assertFalse(result.as_dict()["stored"])

    def test_the_identifier_tuples_serialise_as_lists(self):
        """JSON has no tuple, and a caller comparing lengths should not have
        to know which one it got."""
        result = FileIngestion(
            file_id="f",
            outcome=IngestOutcome.stored,
            account_ids=("a", "b"),
            period_ids=("p",),
        )

        payload = result.as_dict()
        self.assertEqual(payload["account_ids"], ["a", "b"])
        self.assertEqual(payload["period_ids"], ["p"])

    def test_every_field_is_reported(self):
        """The dict is the whole record, so a field added and not serialised
        would be invisible to every caller."""
        import dataclasses

        names = {field.name for field in dataclasses.fields(FileIngestion)}
        payload = FileIngestion(file_id="f", outcome=IngestOutcome.stored).as_dict()

        self.assertEqual(names - set(payload), set())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
