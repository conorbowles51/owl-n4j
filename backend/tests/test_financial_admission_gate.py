"""Tests for the half of the rule that refuses, rather than the half that records.

:mod:`services.financial.admission` states the rule as *"the event is written
before the file is sent, or it is not sent"*.  ``record_admission`` and
``admit_case_file`` are the writing half and are tested elsewhere.  This module
tests the refusing half: that a file the router holds back cannot reach the
document pipeline unless a decision to send it is already on the record.

What is asserted here, and why each of these and not others:

*A held file with no decision behind it stops the request.*  This is the whole
point of the module and everything else is a qualification of it.

*A held file with a decision behind it proceeds.*  A gate that refused
regardless would satisfy the first assertion and be useless, and the two
together are what make the admission mean something.

*The decision has to be the right one, about the right file, in the right
matter.*  Three separate assertions, because each is a different way for a gate
to be walked past: any adjudication at all clearing a file, one file's decision
clearing another, or a decision filed in a different matter clearing this one.
The last would be a confidentiality failure and not merely a bug.

*The finding is read from the file's bytes at the moment of the check.*  The
file on disk is rewritten under a row that still describes a letter, and the
gate refuses.  If the gate trusted anything stored about the file, swapping the
bytes after upload would be enough to get a statement into the text index.

*One held file refuses the whole batch, and every held file is named.*  Both
sides of the decision recorded in the module docstring: nothing partial goes
through, and one refusal tells the caller everything they must decide about.

*Nothing blocking means the database is not read.*  Asserted with a session
that raises on any use.  This is not a performance test.  ``process_db_files``
is called in at least one place with an object that has ``commit`` and nothing
else, so a gate that queried unconditionally would break a caller that never
had a held file to begin with.

*An admission is not consumed.*  Asserted as it actually behaves, which is that
one decision clears the same file for every later send.  The module docstring
says at length why nothing here can do better and what closing it would take.
The test exists so that the limit is recorded in the suite rather than only in
prose, and so that closing it later fails a test that says what changed.

*A refusal leaves the files exactly as it found them.*  Driven through
``process_db_files`` itself rather than the gate alone, because the property is
about ordering in the caller: not marked processing, no snapshot, nothing sent.

The fixture follows ``test_financial_admit_file``: SQLite on disk so the test's
session is not the one under test, ``PRAGMA foreign_keys=ON``, real bytes on
disk because this module classifies by reading them.  The bank file is built by
the camt.053 suite's own builder rather than restated here, for the reason that
suite gives: a second copy of a format drifts from the first and the two then
disagree silently.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import AdjudicationDecision, AdjudicationSubject, GlobalRole
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.financial import AdjudicationEvent, FinancialIngestionRun
from postgres.models.user import User
from services.financial import decisions
from services.financial.admission_gate import (
    HeldFile,
    UnadmittedFileError,
    admitted_file_ids,
    gate_document_processing,
    held_without_admission,
)
from services.financial.admit_file import admit_case_file

from tests import test_financial_camt053 as camt

TABLES = [
    User.__table__,
    Case.__table__,
    EvidenceFolder.__table__,
    EvidenceFile.__table__,
    # Created for the reason ``test_financial_admission`` gives: SQLite resolves
    # a foreign key's parent at insert time even when the value is null.
    FinancialIngestionRun.__table__,
    AdjudicationEvent.__table__,
]

#: A letter.  What the document pipeline is for, and what the router lets past.
A_DOCUMENT = b"Dear Sir,\n\nPlease find enclosed the statements you asked for.\n"

#: Claimed by camt.053 and by MT940 at once.  Taken verbatim from the backend's
#: own ambiguity fixture so the two cannot drift into disagreeing about what
#: ambiguity looks like.
CONTRIVED_AMBIGUOUS = (
    b'<?xml version="1.0"?>'
    b'<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">'
    b"<BkToCstmrStmt><Nrtv>{4:</Nrtv></BkToCstmrStmt></Document>"
)


class HostileSession:
    """A session that fails the test if it is used at all.

    Raises on every attribute rather than on a named few, so that a future
    query written through some other method is caught by the same object.
    """

    def __getattr__(self, name):
        raise AssertionError(
            f"the gate touched the database (session.{name}) when nothing "
            "in the request blocked"
        )


class AdmissionGateTestCase(unittest.TestCase):
    """One matter with files on disk, and a second matter to cross."""

    def setUp(self):
        self._directory = tempfile.mkdtemp(prefix="loupe-admission-gate-")
        self.root = Path(self._directory)
        self.evidence_root = self.root / "evidence"
        self.evidence_root.mkdir()

        self.engine = create_engine(
            f"sqlite+pysqlite:///{self.root / 'ledger.db'}", future=True
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
            title="Gate Fixture",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        self.other_case = Case(
            id=uuid.uuid4(),
            title="Another Matter Entirely",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        self.db.add_all([self.user, self.case, self.other_case])
        self.db.commit()

        self.bank_file = self.written(
            "january.xml", camt.build(), name="january-statement.xml"
        )
        self.letter = self.written("letter.txt", A_DOCUMENT, name="letter.txt")

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        shutil.rmtree(self._directory, ignore_errors=True)

    # -- helpers ---------------------------------------------------------

    def written(
        self,
        stored: str,
        data: bytes | None,
        *,
        name: str,
        case=None,
    ) -> EvidenceFile:
        """One evidence row, with bytes behind it unless ``data`` is None.

        ``data=None`` builds the row without writing the file, which is how an
        unreadable file is produced without contriving a permission.
        """
        if data is not None:
            (self.evidence_root / stored).write_bytes(data)
        record = EvidenceFile(
            id=uuid.uuid4(),
            case_id=(case or self.case).id,
            original_filename=name,
            stored_path=stored,
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        )
        self.db.add(record)
        self.db.commit()
        return record

    def resolve_path(self, stored):
        """The caller's job: a stored path turned into one this process opens.

        The gate is handed the caller's resolver rather than resolving for
        itself, so that it classifies the same bytes the send will carry.
        """
        return self.evidence_root / stored

    def gate(self, *files, case=None):
        gate_document_processing(
            self.db,
            case_id=(case or self.case).id,
            files=list(files),
            resolve_path=self.resolve_path,
        )

    def admit(self, record, *, reason="Ledger cannot parse it; index the text."):
        return admit_case_file(
            self.db,
            case_id=self.case.id,
            file_id=record.id,
            actor=self.user,
            reason=reason,
            resolve_path=self.resolve_path,
        )

    def events(self) -> list[AdjudicationEvent]:
        return list(
            self.db.scalars(
                select(AdjudicationEvent).order_by(AdjudicationEvent.subject_sequence)
            ).all()
        )

    # -- what passes -----------------------------------------------------

    def test_a_letter_passes(self):
        """The ordinary case.  Nothing is held, so nothing is asked."""
        self.assertIsNone(self.gate(self.letter))

    def test_no_files_at_all_passes(self):
        self.assertIsNone(self.gate())

    def test_nothing_blocking_does_not_read_the_database(self):
        """A caller with a session that cannot answer a query is not broken.

        ``process_db_files`` is called in the recovery test with an object that
        has ``commit`` and nothing else.  The gate has to be invisible to a
        request the router does not object to, or it would break callers that
        never had a held file.
        """
        gate_document_processing(
            HostileSession(),
            case_id=self.case.id,
            files=[self.letter],
            resolve_path=self.resolve_path,
        )

    def test_empty_file_list_does_not_read_the_database(self):
        gate_document_processing(
            HostileSession(),
            case_id=self.case.id,
            files=[],
            resolve_path=self.resolve_path,
        )

    def test_admitted_file_ids_does_not_query_for_an_empty_input(self):
        self.assertEqual(
            admitted_file_ids(HostileSession(), case_id=self.case.id, file_ids=[]),
            set(),
        )

    # -- what is refused -------------------------------------------------

    def test_a_native_file_with_no_decision_is_refused(self):
        with self.assertRaises(UnadmittedFileError) as caught:
            self.gate(self.bank_file)

        held = caught.exception.held
        self.assertEqual(len(held), 1)
        self.assertEqual(held[0].file_id, str(self.bank_file.id))
        self.assertEqual(held[0].file_name, "january-statement.xml")
        self.assertEqual(held[0].route_outcome, "native")
        self.assertEqual(held[0].detected_format, "camt053")
        self.assertEqual(held[0].claimants, ("camt053",))

    def test_an_ambiguous_file_is_refused_with_every_claimant(self):
        ambiguous = self.written(
            "both.xml", CONTRIVED_AMBIGUOUS, name="could-be-either.xml"
        )
        with self.assertRaises(UnadmittedFileError) as caught:
            self.gate(ambiguous)

        held = caught.exception.held[0]
        self.assertEqual(held.route_outcome, "ambiguous")
        # No format is named, because naming one would record a confident
        # answer about a file whose format is in doubt.
        self.assertIsNone(held.detected_format)
        self.assertGreater(len(held.claimants), 1)

    def test_an_unreadable_file_is_refused(self):
        """A row whose bytes are not there is held, not waved through.

        The router cannot say a file is safe to send when it could not read
        it, and the direction the mistake falls has to be that nothing
        happens.
        """
        missing = self.written("gone.xml", None, name="gone.xml")
        with self.assertRaises(UnadmittedFileError) as caught:
            self.gate(missing)
        self.assertEqual(caught.exception.held[0].route_outcome, "unreadable")

    def test_a_file_the_resolver_cannot_place_is_refused(self):
        """A resolver returning None means "I could not find this".

        Treated as unreadable rather than as absent, for the same reason: an
        unanswered question about a file is not permission to send it.
        """
        with self.assertRaises(UnadmittedFileError) as caught:
            gate_document_processing(
                self.db,
                case_id=self.case.id,
                files=[self.bank_file],
                resolve_path=lambda _stored: None,
            )
        self.assertEqual(caught.exception.held[0].route_outcome, "unreadable")

    # -- the decision has to be the right one ----------------------------

    def test_an_admitted_file_passes(self):
        self.admit(self.bank_file)
        self.assertIsNone(self.gate(self.bank_file))

    def test_a_decision_about_another_file_does_not_clear_this_one(self):
        second_bank_file = self.written(
            "february.xml", camt.build(), name="february-statement.xml"
        )
        self.admit(second_bank_file)

        with self.assertRaises(UnadmittedFileError) as caught:
            self.gate(self.bank_file)
        self.assertEqual(
            [h.file_id for h in caught.exception.held], [str(self.bank_file.id)]
        )

    def test_a_decision_in_another_matter_does_not_clear_this_file(self):
        """A decision filed elsewhere is not an answer about this case.

        The file ids alone would find the row, since they are uuid4 and a file
        belongs to one matter.  The case is in the filter so that whatever
        went wrong upstream to let a decision be filed against another matter,
        it could not also clear a file here.
        """
        self.admit(self.bank_file)

        self.assertEqual(
            admitted_file_ids(
                self.db, case_id=self.other_case.id, file_ids=[self.bank_file.id]
            ),
            set(),
        )
        with self.assertRaises(UnadmittedFileError):
            self.gate(self.bank_file, case=self.other_case)

    def test_a_different_kind_of_decision_does_not_clear_the_file(self):
        """Any adjudication at all must not count as an admission.

        The log carries eight kinds of decision about several kinds of
        subject.  A gate that asked only "is there a row about this file"
        would let a reclassification, or a restore, stand in for a decision
        nobody took.
        """
        decisions.record(
            self.db,
            case_id=self.case.id,
            subject=self.bank_file,
            subject_type=AdjudicationSubject.evidence_file,
            decision=AdjudicationDecision.reclassify_document,
            reason="Filed under the wrong account; moved.",
            actor=decisions.Actor(
                name=self.user.name, email=self.user.email, user_id=self.user.id
            ),
            before={"account": "current"},
            after={"account": "savings"},
        )
        self.db.commit()
        self.assertEqual(len(self.events()), 1)

        with self.assertRaises(UnadmittedFileError):
            self.gate(self.bank_file)

    # -- the finding is the file's own -----------------------------------

    def test_the_check_is_re_run_from_the_bytes_on_disk(self):
        """Swapping the bytes after upload does not get a statement past.

        The row still describes the letter it was created as.  The gate reads
        the file, so it refuses.  A gate that trusted anything recorded about
        the file at upload time would be walked past by exactly this.
        """
        (self.evidence_root / "letter.txt").write_bytes(camt.build())

        with self.assertRaises(UnadmittedFileError) as caught:
            self.gate(self.letter)
        held = caught.exception.held[0]
        self.assertEqual(held.file_id, str(self.letter.id))
        self.assertEqual(held.route_outcome, "native")

    # -- the shape of the refusal ----------------------------------------

    def test_one_held_file_refuses_the_whole_batch(self):
        """Four files go, one is held, none are processed.

        The alternative is a caller who asked for four and got three, with
        nothing in the response naming the fourth.  That reads as success.
        """
        also_fine = self.written("memo.txt", A_DOCUMENT, name="memo.txt")
        with self.assertRaises(UnadmittedFileError) as caught:
            self.gate(self.letter, self.bank_file, also_fine)

        self.assertEqual(
            [h.file_id for h in caught.exception.held], [str(self.bank_file.id)]
        )

    def test_every_held_file_is_named_not_just_the_first(self):
        """One refusal tells the caller everything they must decide about.

        Refusing one at a time would make a batch take as many round trips as
        it has held files to learn its own shape.
        """
        second = self.written(
            "february.xml", camt.build(), name="february-statement.xml"
        )
        third = self.written("both.xml", CONTRIVED_AMBIGUOUS, name="either.xml")

        with self.assertRaises(UnadmittedFileError) as caught:
            self.gate(self.letter, self.bank_file, second, third)

        self.assertEqual(
            {h.file_id for h in caught.exception.held},
            {str(self.bank_file.id), str(second.id), str(third.id)},
        )

    def test_an_admitted_file_is_dropped_from_the_refusal_the_others_remain(self):
        second = self.written(
            "february.xml", camt.build(), name="february-statement.xml"
        )
        self.admit(self.bank_file)

        with self.assertRaises(UnadmittedFileError) as caught:
            self.gate(self.bank_file, second)
        self.assertEqual(
            [h.file_id for h in caught.exception.held], [str(second.id)]
        )

    def test_the_message_names_the_files(self):
        message = ""
        try:
            self.gate(self.bank_file)
        except UnadmittedFileError as exc:
            message = str(exc)
        self.assertIn("january-statement.xml", message)

    def test_as_dict_carries_the_finding_not_only_the_refusal(self):
        """The interface can offer the admission without a second request.

        ``/route-check`` is a separate call whose answer, taken later, may not
        be the one this refusal was based on.
        """
        with self.assertRaises(UnadmittedFileError) as caught:
            self.gate(self.bank_file)

        body = caught.exception.as_dict()
        self.assertEqual(body["error"], "unadmitted_files")
        self.assertIn("january-statement.xml", body["message"])
        self.assertEqual(len(body["held"]), 1)
        self.assertEqual(
            body["held"][0],
            {
                "file_id": str(self.bank_file.id),
                "file_name": "january-statement.xml",
                "route_outcome": "native",
                "detected_format": "camt053",
                "claimants": ["camt053"],
            },
        )

    def test_held_without_admission_returns_empty_rather_than_raising(self):
        """The reporting form, for a caller that wants the list not the refusal."""
        self.assertEqual(
            held_without_admission(
                self.db,
                case_id=self.case.id,
                files=[self.letter],
                resolve_path=self.resolve_path,
            ),
            (),
        )
        held = held_without_admission(
            self.db,
            case_id=self.case.id,
            files=[self.bank_file],
            resolve_path=self.resolve_path,
        )
        self.assertEqual(len(held), 1)
        self.assertIsInstance(held[0], HeldFile)

    # -- the limit, asserted so that closing it fails a test -------------

    def test_an_admission_is_not_consumed_by_a_send(self):
        """One recorded decision clears the same file for every later send.

        ``AdjudicationDecision`` says an admission "authorises one send", and
        ``admit_case_file`` appends a second event for a second send rather
        than deduplicating.  This gate does not honour that, and nothing in
        the schema can: there is no link from a decision to a processing job
        and no per-file record of a send that a decision could be spent
        against.  Asserted as it behaves rather than as it ought to, so that
        the limit is in the suite and not only in prose.  A change that closes
        it should fail here and say so.
        """
        self.admit(self.bank_file)
        for _ in range(3):
            self.assertIsNone(self.gate(self.bank_file))
        self.assertEqual(len(self.events()), 1)

    def test_the_gate_writes_nothing(self):
        before = len(self.events())
        self.admit(self.bank_file)
        after_admission = len(self.events())
        self.gate(self.bank_file)
        self.assertEqual(before, 0)
        self.assertEqual(after_admission, 1)
        self.assertEqual(len(self.events()), 1)


class ProcessingRouteRefusalTestCase(unittest.TestCase):
    """The refusal as the processing service applies it.

    The gate alone cannot show the property that matters most, which is about
    ordering in the caller: a refusal must leave the files exactly as it found
    them.  That is a fact about where the call sits, so it is tested through
    ``process_db_files``.

    The engine client and the storage layer are replaced rather than run.  What
    is being asserted is that they are *not reached*, and a fake that records
    being called is the only way to assert that about a call that should not
    happen.
    """

    def setUp(self):
        self._directory = tempfile.mkdtemp(prefix="loupe-gate-route-")
        self.root = Path(self._directory)
        self.case_id = uuid.uuid4()

        self.statement = self.root / "january.xml"
        self.statement.write_bytes(camt.build())
        self.letter = self.root / "letter.txt"
        self.letter.write_bytes(A_DOCUMENT)

        self.marked_processing: list[list] = []
        self.snapshots: list = []
        self.uploads: list = []

    def tearDown(self):
        shutil.rmtree(self._directory, ignore_errors=True)

    def evidence_row(self, path: Path):
        return SimpleNamespace(
            id=uuid.uuid4(),
            case_id=self.case_id,
            status="unprocessed",
            processing_stale=False,
            stored_path=str(path),
            folder_id=None,
            original_filename=path.name,
            engine_job_id=None,
            last_error=None,
        )

    def run_process(self, rows, *, held):
        """Call ``process_db_files`` with everything below the gate faked out.

        ``held`` is what ``gate_document_processing`` should be told about, and
        is asserted rather than passed: the point of the test is that the
        service hands the gate the files it is about to send.
        """
        from services import evidence_processing_service as processing

        async def no_reconciliation(db, case_id):
            return 0

        async def record_upload(**kwargs):
            self.uploads.append(kwargs)
            return [{"id": str(uuid.uuid4())} for _ in rows]

        class FakeSession:
            """Enough of a session for the gate's one query."""

            def __init__(self):
                self.commits = 0

            def commit(self):
                self.commits += 1

            def scalars(self, _statement):
                return SimpleNamespace(all=lambda: [])

        session = FakeSession()

        with mock.patch.multiple(
            processing,
            reconcile_case_jobs=no_reconciliation,
            build_processing_snapshot=lambda *a, **k: {},
            get_subscriber=lambda: SimpleNamespace(
                track_jobs=self._track_jobs,
            ),
        ), mock.patch.object(
            processing.EvidenceDBStorage,
            "get_files_by_ids",
            staticmethod(lambda db, file_ids: list(rows)),
        ), mock.patch.object(
            processing.EvidenceDBStorage,
            "mark_processing",
            staticmethod(
                lambda db, file_ids, force=False: self.marked_processing.append(
                    list(file_ids)
                )
            ),
        ), mock.patch.object(
            processing.EvidenceDBStorage,
            "set_processing_snapshot",
            staticmethod(lambda *a, **k: self.snapshots.append(k)),
        ), mock.patch.object(
            processing.evidence_engine_client,
            "upload_file_paths_batch",
            record_upload,
        ):
            return asyncio.run(
                processing.process_db_files(
                    session,
                    case_id=self.case_id,
                    file_ids=[row.id for row in rows],
                )
            )

    async def _track_jobs(self, job_ids, case_id):
        return None

    def test_a_held_file_stops_the_request_before_anything_is_written(self):
        rows = [self.evidence_row(self.letter), self.evidence_row(self.statement)]

        with self.assertRaises(UnadmittedFileError) as caught:
            self.run_process(rows, held=True)

        self.assertEqual(
            [h.file_name for h in caught.exception.held], ["january.xml"]
        )
        # The three things the service does after the gate, none of them done.
        self.assertEqual(self.marked_processing, [])
        self.assertEqual(self.snapshots, [])
        self.assertEqual(self.uploads, [])
        # And the rows themselves are untouched, which is what the next
        # attempt depends on.
        self.assertTrue(all(row.status == "unprocessed" for row in rows))

    def test_an_ordinary_batch_is_unaffected(self):
        rows = [self.evidence_row(self.letter)]
        result = self.run_process(rows, held=False)

        self.assertEqual(result["file_count"], 1)
        self.assertEqual(len(self.marked_processing), 1)
        self.assertEqual(len(self.uploads), 1)

    def test_a_file_missing_from_disk_is_skipped_not_gated(self):
        """A file nobody is about to send needs no decision behind it.

        The gate is applied to what is actually going, so a statement that is
        not on disk is still the ordinary "missing, skipped" it has always
        been rather than a refusal of the whole batch.
        """
        absent = self.evidence_row(self.root / "not-here.xml")
        rows = [self.evidence_row(self.letter), absent]

        result = self.run_process(rows, held=False)

        self.assertEqual(result["file_count"], 1)
        self.assertEqual(result["missing_on_disk"], 1)
        self.assertEqual(len(self.uploads), 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
