"""Tests for the caller that turns an override into something a person can do.

:mod:`services.financial.admission` was already tested at length, and it is not
retested here.  What is new in :mod:`services.financial.admit_file` is the
joining up, and the joins are where the failures live:

*The finding in the log is read from the file, not supplied.*  ``record_admission``
copies whatever check it is handed straight into the event, so whoever chooses
the check chooses what the record says the router found.  This module reads the
file again immediately before writing, which is the only reason the log can be
read afterwards as evidence of what was actually there.  Asserted by admitting
a file whose bytes the test controls and then reading the stored event.

*A file in another matter is refused the same way a file that does not exist
is.*  Two distinguishable refusals would let anyone with a case id enumerate
another case's evidence list one guess at a time, and nothing downstream would
notice, because both look like ordinary rejections.

*Nothing is written on a refusal.*  Every refusal path rolls back, and a
half-written decision surviving one would put a person's name against an
override they did not complete.

*Two admissions are two events.*  ``AdjudicationDecision`` says an admission
"authorises one send" and takes no reversal member because "a send cannot be
un-sent".  So deduplicating would be wrong, and the count of how often the team
overruled the router would be wrong with it.

The fixture follows ``test_financial_admission``: SQLite on disk so the caller
does not share one connection with the code under test, ``PRAGMA
foreign_keys=ON``, no ingestion run.  It adds real files on disk, because unlike
that module this one classifies by reading bytes rather than by being handed a
check.  The bank file is built by the camt.053 suite's own fixture builder
rather than restated, for the reason the engine's route tests give: a second
copy of a format would drift from the first and the two would then disagree
silently.
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
from postgres.models.enums import AdjudicationDecision, AdjudicationSubject, GlobalRole
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.financial import AdjudicationEvent, FinancialIngestionRun
from postgres.models.user import User
from services.financial.admission import ROUTED_DOCUMENT_PIPELINE, ROUTED_HELD
from services.financial.admit_file import (
    FileAdmission,
    FileAdmissionOutcome,
    admit_case_file,
    find_case_file,
)

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


class AdmitCaseFileTestCase(unittest.TestCase):
    """One matter with files on disk, and a second matter to cross."""

    def setUp(self):
        self._directory = tempfile.mkdtemp(prefix="loupe-admit-file-")
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
            title="Admit Fixture",
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
        """The router's job: a stored path turned into one this process can open.

        ``stored`` is never None: ``evidence_files.stored_path`` is declared
        NOT NULL.  A resolver that cannot place a file returns None instead,
        which is the condition
        :func:`~services.financial.admit_file.admit_case_file` has to survive.
        """
        return self.evidence_root / stored

    def admit(self, record, *, reason="Ledger cannot parse it; index the text.", actor=None):
        return admit_case_file(
            self.db,
            case_id=self.case.id,
            file_id=record.id,
            actor=self.user if actor is None else actor,
            reason=reason,
            resolve_path=self.resolve_path,
        )

    def events(self, record=None) -> list[AdjudicationEvent]:
        query = select(AdjudicationEvent).order_by(AdjudicationEvent.subject_sequence)
        if record is not None:
            query = query.where(AdjudicationEvent.subject_id == record.id)
        return list(self.db.scalars(query).all())

    # -- the ordinary admission ------------------------------------------

    def test_a_held_bank_file_is_admitted_and_the_decision_is_appended(self):
        result = self.admit(self.bank_file)

        self.assertIsInstance(result, FileAdmission)
        self.assertIs(result.outcome, FileAdmissionOutcome.admitted)
        self.assertTrue(result.admitted)
        self.assertEqual(result.file_id, str(self.bank_file.id))
        self.assertEqual(result.file_name, "january-statement.xml")
        self.assertEqual(result.route_outcome, "native")
        self.assertEqual(result.detected_format, "camt053")
        self.assertEqual(result.claimants, ("camt053",))

        appended = self.events(self.bank_file)
        self.assertEqual(len(appended), 1)
        self.assertEqual(
            appended[0].decision, AdjudicationDecision.admit_financial_document.value
        )
        self.assertEqual(
            appended[0].subject_type, AdjudicationSubject.evidence_file.value
        )
        self.assertEqual(str(appended[0].id), result.adjudication_id)

    def test_the_decision_names_the_person_and_their_own_grounds(self):
        result = self.admit(self.bank_file, reason="Bank sent it in the wrong format.")

        appended = self.events(self.bank_file)[0]
        self.assertEqual(appended.reason, "Bank sent it in the wrong format.")
        self.assertEqual(appended.actor_name, "Investigator")
        self.assertEqual(appended.actor_email, "investigator@example.test")
        self.assertEqual(appended.actor_user_id, self.user.id)
        # Echoed back rather than restated, so a caller shows what went into the
        # log instead of what it sent.
        self.assertEqual(result.reason, "Bank sent it in the wrong format.")

    def test_the_event_records_the_move_out_of_the_hold(self):
        self.admit(self.bank_file)
        appended = self.events(self.bank_file)[0]

        self.assertEqual(appended.before["routed_to"], ROUTED_HELD)
        self.assertEqual(appended.after["routed_to"], ROUTED_DOCUMENT_PIPELINE)
        self.assertEqual(appended.before.keys(), appended.after.keys())

    def test_an_admission_precedes_any_ingestion_run(self):
        """Nothing has been ingested yet, so there is no run to attribute it to."""
        self.admit(self.bank_file)
        self.assertIsNone(self.events(self.bank_file)[0].ingestion_run_id)

    # -- the finding is read, not supplied --------------------------------

    def test_the_finding_stored_is_the_one_read_from_the_file(self):
        """The property the whole module exists for.

        There is no parameter by which a caller could state the finding, and
        the finding in the log is the file's own.  Asserted by admitting a file
        this test wrote the bytes of and reading back what the event says was
        found.
        """
        self.admit(self.bank_file)
        found = self.events(self.bank_file)[0].before

        self.assertEqual(found["route_outcome"], "native")
        self.assertEqual(found["detected_format"], "camt053")
        self.assertEqual(found["claimants"], ["camt053"])

    def test_a_file_two_formats_claim_is_admitted_with_both_named(self):
        contrived = self.written(
            "contrived.xml", CONTRIVED_AMBIGUOUS, name="contrived.xml"
        )
        result = self.admit(contrived)

        self.assertIs(result.outcome, FileAdmissionOutcome.admitted)
        self.assertEqual(result.route_outcome, "ambiguous")
        self.assertIsNone(result.detected_format)
        self.assertEqual(result.claimants, ("camt053", "mt940"))
        self.assertEqual(self.events(contrived)[0].before["claimants"], ["camt053", "mt940"])

    def test_a_file_that_cannot_be_read_is_held_and_so_is_admissible(self):
        """The router blocks what it could not look at, so that is overridable too."""
        absent = self.written("absent.dat", None, name="absent.dat")
        result = self.admit(absent)

        self.assertIs(result.outcome, FileAdmissionOutcome.admitted)
        self.assertEqual(result.route_outcome, "unreadable")
        self.assertEqual(self.events(absent)[0].before["route_outcome"], "unreadable")

    def test_a_file_the_resolver_cannot_place_is_held_and_so_is_admissible(self):
        """A stored path this process cannot turn into a real one.

        The file exists and its bytes are a bank statement, but the resolver
        cannot say where they are -- what happens in a container whose mount
        differs from the one that took the upload.  The router cannot look, so
        it holds, so a person can overrule it.  The admission is not allowed to
        depend on the router having succeeded in reading the file.
        """
        result = admit_case_file(
            self.db,
            case_id=self.case.id,
            file_id=self.bank_file.id,
            actor=self.user,
            reason="Storage is not mounted here; index the text instead.",
            resolve_path=lambda stored: None,
        )

        self.assertIs(result.outcome, FileAdmissionOutcome.admitted)
        self.assertEqual(result.route_outcome, "unreadable")
        self.assertEqual(
            self.events(self.bank_file)[0].before["route_outcome"], "unreadable"
        )

    # -- nothing to override ----------------------------------------------

    def test_an_ordinary_document_has_nothing_to_override(self):
        result = self.admit(self.letter)

        self.assertIs(result.outcome, FileAdmissionOutcome.nothing_to_override)
        self.assertFalse(result.admitted)
        self.assertEqual(result.route_outcome, "not_native")
        self.assertEqual(result.routed_to, ROUTED_HELD)
        self.assertIn("nothing to overrule", result.reason)

    def test_nothing_is_appended_when_there_was_nothing_to_override(self):
        """Otherwise every later count of how often the router was overruled is high."""
        self.admit(self.letter)
        self.assertEqual(self.events(), [])

    # -- files that are not this case's ------------------------------------

    def test_a_file_in_another_matter_is_not_found(self):
        foreign = self.written(
            "foreign.xml", camt.build(), name="not-our-matter.xml", case=self.other_case
        )
        result = self.admit(foreign)

        self.assertIs(result.outcome, FileAdmissionOutcome.not_found)
        self.assertEqual(self.events(), [])

    def test_a_file_that_does_not_exist_reads_identically(self):
        """Two distinguishable refusals would enumerate another case's evidence."""
        foreign = self.written(
            "foreign2.xml", camt.build(), name="not-our-matter.xml", case=self.other_case
        )
        elsewhere = self.admit(foreign).as_dict()
        nowhere = admit_case_file(
            self.db,
            case_id=self.case.id,
            file_id=uuid.uuid4(),
            actor=self.user,
            reason="anything",
            resolve_path=self.resolve_path,
        ).as_dict()

        elsewhere.pop("file_id")
        nowhere.pop("file_id")
        self.assertEqual(elsewhere, nowhere)

    def test_find_case_file_will_not_reach_into_another_matter(self):
        foreign = self.written(
            "foreign3.xml", camt.build(), name="not-our-matter.xml", case=self.other_case
        )
        self.assertIsNone(
            find_case_file(self.db, case_id=self.case.id, file_id=foreign.id)
        )
        self.assertIsNotNone(
            find_case_file(self.db, case_id=self.other_case.id, file_id=foreign.id)
        )

    # -- refusals ----------------------------------------------------------

    def test_a_blank_reason_is_refused_and_nothing_is_written(self):
        result = self.admit(self.bank_file, reason="   ")

        self.assertIs(result.outcome, FileAdmissionOutcome.refused)
        self.assertFalse(result.admitted)
        self.assertEqual(self.events(), [])

    def test_a_refusal_still_carries_what_the_router_found(self):
        """Otherwise the caller has to ask again, and the second answer may differ."""
        result = self.admit(self.bank_file, reason="")

        self.assertEqual(result.route_outcome, "native")
        self.assertEqual(result.detected_format, "camt053")
        self.assertEqual(result.file_name, "january-statement.xml")
        self.assertEqual(result.routed_to, ROUTED_HELD)

    def test_an_actor_with_no_name_is_refused(self):
        class Anonymous:
            id = None
            name = "  "
            email = "someone@example.test"

        result = self.admit(self.bank_file, actor=Anonymous())

        self.assertIs(result.outcome, FileAdmissionOutcome.refused)
        self.assertIn("name", result.reason)
        self.assertEqual(self.events(), [])

    def test_an_actor_with_no_address_is_refused(self):
        class Nameless:
            id = None
            name = "Investigator"
            email = None

        result = self.admit(self.bank_file, actor=Nameless())

        self.assertIs(result.outcome, FileAdmissionOutcome.refused)
        self.assertEqual(self.events(), [])

    # -- two admissions are two decisions ----------------------------------

    def test_a_second_admission_is_appended_rather_than_deduplicated(self):
        """An admission authorises one send, and two sends are two decisions."""
        first = self.admit(self.bank_file, reason="First send.")
        second = self.admit(self.bank_file, reason="Sent again after re-upload.")

        self.assertTrue(first.admitted)
        self.assertTrue(second.admitted)
        self.assertNotEqual(first.adjudication_id, second.adjudication_id)

        appended = self.events(self.bank_file)
        self.assertEqual([row.subject_sequence for row in appended], [1, 2])
        self.assertEqual(
            [row.reason for row in appended],
            ["First send.", "Sent again after re-upload."],
        )

    # -- the shape the interface reads --------------------------------------

    def test_as_dict_carries_every_field_on_every_outcome(self):
        """A key present only on the interesting branch answers nothing."""
        admitted = self.admit(self.bank_file).as_dict()
        untouched = self.admit(self.letter).as_dict()

        self.assertEqual(admitted.keys(), untouched.keys())
        self.assertTrue(admitted["admitted"])
        self.assertFalse(untouched["admitted"])
        self.assertEqual(admitted["routed_to"], ROUTED_DOCUMENT_PIPELINE)
        self.assertEqual(untouched["routed_to"], ROUTED_HELD)
        self.assertEqual(admitted["claimants"], ["camt053"])

    def test_as_dict_is_json_serialisable(self):
        """It is going out over the wire, so a tuple in it is a failed response."""
        import json

        for result in (self.admit(self.bank_file), self.admit(self.letter)):
            payload = result.as_dict()
            self.assertEqual(json.loads(json.dumps(payload)), payload)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
