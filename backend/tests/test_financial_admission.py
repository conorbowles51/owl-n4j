"""Tests for recording that someone overrode the router.

:mod:`services.financial.admission` writes one kind of row: a named person was
shown that a file looks like bank data, disagreed, and sent it to the general
document pipeline anyway.  It is the only decision in the vocabulary that
records a choice *not* to use this subsystem on evidence it would otherwise
claim, and it is the only one whose subject is not a financial table.

So the tests are about the two ways that row can be wrong in a way nothing
downstream would catch:

* it can be written when there was nothing to override, which would put a
  decision in the log that nobody had to take and would inflate every later
  count of how often the team overruled the router;
* it can carry one file's identity beside another file's finding, which would
  read as authoritative about both.  There is no foreign key from an
  adjudication to anything, so if that pairing is not checked in the service it
  is not checked at all.

And one thing the row has to get right rather than refuse: the finding it
copies in.  Detection is a function of the detector, the detector changes, and
a check re-run next year against a file admitted this year answers a different
question than the one the person was actually looking at.  The finding is
therefore asserted to be *stored*, not derivable.

The fixture follows ``test_financial_decisions``: SQLite on disk rather than
``:memory:`` so the caller does not share one connection with the code under
test, and ``PRAGMA foreign_keys=ON``.  It is deliberately lighter than that
module's -- an admission is taken on the evidence list, before any ingestion
run, account or document exists, and a fixture that built them would suggest
they were needed.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
import uuid
from pathlib import Path

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import (
    AdjudicationDecision,
    AdjudicationSubject,
    GlobalRole,
)
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.financial import AdjudicationEvent, FinancialIngestionRun
from postgres.models.user import User
from services.financial import decisions
from services.financial.admission import (
    ROUTED_DOCUMENT_PIPELINE,
    ROUTED_HELD,
    AdmissionError,
    NothingToOverrideError,
    WrongFileError,
    record_admission,
)
from services.financial.decisions import Actor, DecisionError
from services.financial.duplicates import CrossCaseError
from services.financial.route_check import FileRouteCheck

TABLES = [
    User.__table__,
    Case.__table__,
    EvidenceFolder.__table__,
    EvidenceFile.__table__,
    # No run is ever opened here -- an admission precedes ingestion, and
    # ``ingestion_run_id`` is asserted null.  The table is created anyway
    # because SQLite resolves a foreign key's parent at insert time under
    # ``PRAGMA foreign_keys=ON``, even for a null value.
    FinancialIngestionRun.__table__,
    AdjudicationEvent.__table__,
]


class AdmissionTestCase(unittest.TestCase):
    """One matter with one held file, and a second matter to cross."""

    def setUp(self):
        self._directory = tempfile.mkdtemp(prefix="loupe-admission-")
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
            title="Admission Fixture",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        # A real second matter rather than a random uuid, so the cross-case
        # refusal is tested against the thing it exists to prevent.
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
        # A second file in this matter, so "a check about a different file" is
        # a file that exists rather than one that does not.
        self.other_file = EvidenceFile(
            id=uuid.uuid4(),
            case_id=self.case.id,
            original_filename="february-statement.pdf",
            stored_path="/evidence/february-statement.pdf",
            sha256="b" * 64,
        )
        self.foreign_file = EvidenceFile(
            id=uuid.uuid4(),
            case_id=self.other_case.id,
            original_filename="not-our-matter.pdf",
            stored_path="/evidence/not-our-matter.pdf",
            sha256="c" * 64,
        )
        self.db.add_all(
            [
                self.user,
                self.case,
                self.other_case,
                self.evidence_file,
                self.other_file,
                self.foreign_file,
            ]
        )
        self.db.commit()

        self.actor = Actor(
            name=self.user.name, email=self.user.email, user_id=self.user.id
        )

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        shutil.rmtree(self._directory, ignore_errors=True)

    # -- helpers ---------------------------------------------------------

    def native_check(self, evidence_file=None, **over) -> FileRouteCheck:
        """The ordinary held file: one format claims it, so it is readable."""
        target = evidence_file if evidence_file is not None else self.evidence_file
        fields = dict(
            file_id=str(target.id),
            file_name=target.original_filename,
            claimants=("ofx",),
        )
        fields.update(over)
        return FileRouteCheck(**fields)

    def admit(self, **over):
        """``record_admission`` against the fixture file, all overridable."""
        kwargs = dict(
            case_id=self.case.id,
            evidence_file=self.evidence_file,
            check=self.native_check(),
            reason="the statement is an exhibit, we want it in the text index",
            actor=self.actor,
        )
        kwargs.update(over)
        return record_admission(self.db, **kwargs)

    def stored_rows(self):
        return list(
            self.db.execute(select(AdjudicationEvent)).scalars().all()
        )


class TheRecordedAdmission(AdmissionTestCase):
    def test_a_held_file_is_recorded_against_the_evidence_file(self):
        """The subject is the file, because nothing else exists yet."""
        event = self.admit()

        self.assertEqual(
            event.subject_type, AdjudicationSubject.evidence_file.value
        )
        self.assertEqual(event.subject_id, self.evidence_file.id)
        self.assertEqual(
            event.decision, AdjudicationDecision.admit_financial_document.value
        )

    def test_the_decision_is_flushed_before_it_is_returned(self):
        """The caller must hold a decision with an identity before enqueueing.

        If the job is enqueued first and the write then fails, the file has
        been sent with no record of anyone choosing to send it -- which is the
        exact situation this module exists to prevent.
        """
        event = self.admit()
        self.assertIsNotNone(event.id)

    def test_who_decided_and_why_are_both_stored(self):
        event = self.admit(reason="counsel asked for it in the exhibit bundle")

        self.assertEqual(event.actor_user_id, self.user.id)
        self.assertEqual(event.actor_name, "Investigator")
        self.assertEqual(event.actor_email, "investigator@example.test")
        self.assertEqual(
            event.reason, "counsel asked for it in the exhibit bundle"
        )

    def test_no_ingestion_run_is_named(self):
        """There is none to name.  The decision precedes ingestion entirely."""
        event = self.admit()
        self.assertIsNone(event.ingestion_run_id)

    def test_a_second_admission_takes_the_next_sequence(self):
        """``created_at`` cannot order these; ``subject_sequence`` can.

        Postgres ``now()`` is transaction-start time, so two decisions written
        in one transaction share it.
        """
        first = self.admit()
        second = self.admit(reason="re-sent after the folder was re-scanned")

        self.assertEqual(first.subject_sequence, 1)
        self.assertEqual(second.subject_sequence, 2)

    def test_sequences_are_counted_per_file_not_per_case(self):
        self.admit()
        second_file = self.admit(
            evidence_file=self.other_file,
            check=self.native_check(self.other_file),
        )
        self.assertEqual(second_file.subject_sequence, 1)


class TheCopiedFinding(AdmissionTestCase):
    """What the router said, frozen at the moment someone overrode it."""

    def test_the_finding_is_stored_rather_than_left_to_be_re_derived(self):
        """A check run next year answers a different question.

        Detection is a function of the detector and the detector changes.  The
        finding has to be what the person was actually shown.
        """
        event = self.admit()

        self.assertEqual(event.before["route_outcome"], "native")
        self.assertEqual(event.before["claimants"], ["ofx"])
        self.assertEqual(event.before["detected_format"], "ofx")

    def test_routed_to_is_the_only_key_that_differs(self):
        """``before`` and ``after`` do not diff a column, and should not.

        Nothing in ``evidence_files`` changes: "held" was never a stored
        status, it was the absence of a job.  What the two sides carry is the
        finding that was overridden, unchanged, beside the one thing the
        decision actually did.
        """
        event = self.admit()

        self.assertEqual(set(event.before), set(event.after))
        differing = {
            key
            for key in event.before
            if event.before[key] != event.after[key]
        }
        self.assertEqual(differing, {"routed_to"})

    def test_the_two_sides_name_the_destinations(self):
        event = self.admit()

        self.assertEqual(event.before["routed_to"], ROUTED_HELD)
        self.assertEqual(event.after["routed_to"], ROUTED_DOCUMENT_PIPELINE)

    def test_an_ambiguous_file_records_no_detected_format(self):
        """Two claimants is an answer about the file, not a format for it.

        Picking one would record a confident format for something whose format
        is in doubt -- and it would be recorded here permanently.
        """
        event = self.admit(
            check=self.native_check(claimants=("ofx", "qif")),
        )

        self.assertEqual(event.before["route_outcome"], "ambiguous")
        self.assertEqual(event.before["claimants"], ["ofx", "qif"])
        self.assertIsNone(event.before["detected_format"])

    def test_an_unreadable_file_can_be_admitted(self):
        """Unreadable blocks, so it is a finding someone may override."""
        event = self.admit(
            check=self.native_check(claimants=(), reason="permission denied"),
        )
        self.assertEqual(event.before["route_outcome"], "unreadable")

    def test_an_undetermined_file_can_be_admitted(self):
        """The bytes were read and the detector returned no answer."""
        event = self.admit(
            check=self.native_check(claimants=(), undetermined=True),
        )
        self.assertEqual(event.before["route_outcome"], "undetermined")

    def test_the_claimants_are_copied_not_referenced(self):
        """The stored list must not be the dataclass's own tuple."""
        check = self.native_check(claimants=("ofx", "qif"))
        event = self.admit(check=check)

        self.assertIsInstance(event.before["claimants"], list)
        self.assertEqual(event.before["claimants"], list(check.claimants))


class TheOverridesItRefuses(AdmissionTestCase):
    def test_a_file_the_router_did_not_hold_is_not_an_override(self):
        """No claimant, no objection, nothing to admit it past.

        Recording one would put a decision in the log that nobody had to take,
        and every later count of "how often did we overrule the router" would
        be wrong by however many of these got in.
        """
        with self.assertRaises(NothingToOverrideError) as caught:
            self.admit(check=self.native_check(claimants=()))

        self.assertIn("not_native", str(caught.exception))

    def test_a_file_that_is_not_in_the_case_is_not_an_override(self):
        """``not_found`` is deliberately absent from ``BLOCKING_OUTCOMES``.

        ``process/background`` already refuses the whole request over one, so
        there is no send here for anyone to authorise.
        """
        with self.assertRaises(NothingToOverrideError) as caught:
            self.admit(check=self.native_check(claimants=(), missing=True))

        self.assertIn("not_found", str(caught.exception))

    def test_nothing_is_written_when_there_was_nothing_to_override(self):
        with self.assertRaises(NothingToOverrideError):
            self.admit(check=self.native_check(claimants=()))

        self.assertEqual(self.stored_rows(), [])

    def test_a_check_about_a_different_file_is_refused(self):
        """The event would carry one file's id beside another's finding."""
        with self.assertRaises(WrongFileError) as caught:
            self.admit(check=self.native_check(self.other_file))

        message = str(caught.exception)
        self.assertIn(str(self.other_file.id), message)
        self.assertIn(str(self.evidence_file.id), message)

    def test_nothing_is_written_when_the_check_is_about_another_file(self):
        with self.assertRaises(WrongFileError):
            self.admit(check=self.native_check(self.other_file))

        self.assertEqual(self.stored_rows(), [])

    def test_a_dict_is_not_a_check(self):
        """The finding is copied into the event, so it is not taken on trust."""
        with self.assertRaises(AdmissionError) as caught:
            self.admit(check={"outcome": "native", "claimants": ["ofx"]})

        self.assertIn("FileRouteCheck", str(caught.exception))

    def test_the_wire_shape_of_a_check_is_not_a_check(self):
        """``as_dict`` is what the endpoint returns, so this is the likely slip.

        It carries every key the event needs and would sail through a duck-typed
        reader, recording a finding the router never made.
        """
        wire = self.native_check().as_dict()
        with self.assertRaises(AdmissionError) as caught:
            self.admit(check=wire)

        self.assertNotIsInstance(caught.exception, NothingToOverrideError)
        self.assertIn("FileRouteCheck", str(caught.exception))

    def test_the_type_is_checked_before_anything_is_read_from_it(self):
        """A dict with no ``blocks_document_processing`` must not AttributeError.

        The error a caller sees should name the thing they got wrong.
        """
        with self.assertRaises(AdmissionError):
            self.admit(check={})

    def test_a_non_blocking_check_about_the_wrong_file_reports_the_override(self):
        """Guard order is deliberate and is asserted so it stays deliberate.

        Both faults are present; the one reported is the one that would have
        made the row meaningless even if the file had matched.
        """
        with self.assertRaises(NothingToOverrideError):
            self.admit(check=self.native_check(self.other_file, claimants=()))


class TheReason(AdmissionTestCase):
    def test_a_blank_reason_is_refused(self):
        """Including one made only of whitespace the database also rejects."""
        for blank in ("", "   ", "\t", "\n", " \t\n "):
            with self.subTest(reason=repr(blank)):
                with self.assertRaises(DecisionError):
                    self.admit(reason=blank)

    def test_a_missing_reason_is_refused(self):
        with self.assertRaises(DecisionError):
            self.admit(reason=None)

    def test_nothing_is_written_when_the_reason_is_blank(self):
        """An admission without stated grounds is the unexplained edit."""
        with self.assertRaises(DecisionError):
            self.admit(reason="   ")

        self.assertEqual(self.stored_rows(), [])


class TheCaseBoundary(AdmissionTestCase):
    def test_a_file_from_another_matter_is_refused(self):
        """Filing this in the wrong matter is a confidentiality failure."""
        with self.assertRaises(CrossCaseError):
            self.admit(
                evidence_file=self.foreign_file,
                check=self.native_check(self.foreign_file),
            )

    def test_nothing_is_written_across_the_case_boundary(self):
        with self.assertRaises(CrossCaseError):
            self.admit(
                evidence_file=self.foreign_file,
                check=self.native_check(self.foreign_file),
            )

        self.assertEqual(self.stored_rows(), [])


class TheWidenedVocabulary(AdmissionTestCase):
    """The two members this item added, and the places that must agree."""

    def test_every_subject_in_the_enum_has_a_model(self):
        """Otherwise a decision the database would accept raises KeyError.

        Enforced at import as well; asserted here so the failure names the
        member rather than arriving as an import error in an unrelated suite.
        """
        missing = [
            subject.value
            for subject in AdjudicationSubject
            if subject not in decisions._SUBJECT_MODELS
        ]
        self.assertEqual(missing, [])
        self.assertEqual(decisions._MISSING_SUBJECT_MODELS, ())

    def test_the_evidence_file_subject_maps_to_the_evidence_file_model(self):
        self.assertIs(
            decisions._SUBJECT_MODELS[AdjudicationSubject.evidence_file],
            EvidenceFile,
        )

    def test_the_stored_words_are_the_ones_the_migration_admits(self):
        """A rename on either side without the other silently fails the CHECK."""
        self.assertEqual(
            AdjudicationSubject.evidence_file.value, "evidence_file"
        )
        self.assertEqual(
            AdjudicationDecision.admit_financial_document.value,
            "admit_financial_document",
        )

    def test_both_new_words_fit_their_columns(self):
        """Postgres truncates nothing; it raises.  SQLite here would not."""
        columns = AdjudicationEvent.__table__.c
        self.assertLessEqual(
            len(AdjudicationSubject.evidence_file.value),
            columns.subject_type.type.length,
        )
        self.assertLessEqual(
            len(AdjudicationDecision.admit_financial_document.value),
            columns.decision.type.length,
        )

    def test_the_admission_appears_in_the_file_s_history(self):
        """The ledger view reads this; an unreadable subject would hide it."""
        self.admit()
        self.db.commit()

        entries = decisions.history(
            self.db,
            self.evidence_file,
            AdjudicationSubject.evidence_file,
        )

        self.assertEqual(len(entries), 1)
        self.assertEqual(
            entries[0].decision,
            AdjudicationDecision.admit_financial_document.value,
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
