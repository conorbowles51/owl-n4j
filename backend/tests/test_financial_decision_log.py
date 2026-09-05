"""Tests for reading the adjudication log back out.

``adjudications`` has had writers since :mod:`services.financial.decisions`
was built.  It has never had a reader.  ``decisions.history`` is not one: it
takes a loaded subject object and filters on ``subject_type`` and
``subject_id`` and **not** on ``case_id``, which is correct for the one caller
it was written for and is a confidentiality hole in anything reached from a
request.  So the first thing checked here, and the thing checked hardest, is
that the case is part of the query rather than an assumption about it.

Three groups of claims, in rough order of what it would cost to get them
wrong.

*The case bounds the read.*  A decision about a subject in another matter must
not come back, and it must not come back even when the caller names that
subject's own id -- because a subject id is exactly what an attacker would
have if they had ever seen one row.

*The order says only what it can support.*  ``created_at`` is Postgres
``now()``, transaction-start time, so events written together share it; ``id``
is a random uuid4 and cannot break the tie.  ``decisions.history`` learned
this the expensive way, having once shipped a docstring claiming an ``id``
tiebreak settled the sequence of a quarantine and the release that undid it.
The reader here orders newest first, resolves ties within a subject by
``subject_sequence`` -- the only authoritative order in the table -- and is
total, so a page boundary does not show or skip a row at the database's
discretion.

*A machine's decision is not read as a person's.*  ``reclassify_document`` is
written by the reconciliation stage on every run.  ``by_machine`` is derived
from the actor's address, and getting it wrong presents software's
reclassification of a document's proof class as somebody's judgement, which is
the most misleading single thing this log could be made to say.

Two ways of putting rows in the table are used deliberately.  Most fixtures go
through :func:`services.financial.decisions.record`, so what is read back is
what the real writer writes, sequences and all.  The ordering fixtures insert
``AdjudicationEvent`` rows directly, because ``created_at`` is a server
default and the tests in that group are precisely about which timestamps
events carry; there is no way to state that through the writer.  A reader's
contract is about rows in a table, not about the route they took to get
there, so this is a legitimate fixture and not a shortcut past the writer.
"""

from __future__ import annotations

import datetime as _datetime
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import (
    AdjudicationDecision,
    AdjudicationSubject,
    GlobalRole,
)
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
from services.financial.decision_log import (
    DEFAULT_DECISION_LIMIT,
    MAX_DECISION_LIMIT,
    DecisionLogError,
    list_case_decisions,
    to_record,
)
from services.financial.decisions import Actor, record
from services.financial.documents import (
    RECONCILIATION_ACTOR_EMAIL,
    RECONCILIATION_ACTOR_NAME,
)

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

HASH_A = "a" * 64
HASH_B = "b" * 64

#: A fixed instant the ordering fixtures count from, so a failure reads as a
#: wrong order rather than as a clock.
NOON = _datetime.datetime(2024, 3, 1, 12, 0, 0, tzinfo=_datetime.timezone.utc)


class DecisionLogTestCase(unittest.TestCase):
    """A case with two subjects in it, and a second matter to be excluded from.

    On disk rather than ``:memory:``, matching the other database-backed
    financial tests: nothing here opens a second session, but a file keeps the
    fixture the same shape as its neighbours.
    """

    def setUp(self):
        self._directory = tempfile.mkdtemp(prefix="loupe-decision-log-")
        self.engine = create_engine(
            f"sqlite+pysqlite:///{Path(self._directory) / 'decisions.db'}",
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
            title="Decision Log Fixture",
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

        self.evidence_file = self.file(sha256=HASH_A)
        self.account = self.acct()
        self.db.commit()

        self.actor = Actor(
            name="Investigator",
            email="investigator@example.test",
            user_id=self.user.id,
        )
        self.machine = Actor(
            name=RECONCILIATION_ACTOR_NAME, email=RECONCILIATION_ACTOR_EMAIL
        )

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        shutil.rmtree(self._directory, ignore_errors=True)

    # -- fixtures ---------------------------------------------------------

    def file(self, *, case=None, sha256=HASH_A, name="statement.pdf"):
        evidence_file = EvidenceFile(
            id=uuid.uuid4(),
            case_id=(case or self.case).id,
            original_filename=name,
            stored_path=f"/evidence/{name}",
            sha256=sha256,
        )
        self.db.add(evidence_file)
        self.db.flush()
        return evidence_file

    def acct(self, *, case=None, digits="20445561"):
        account = FinancialAccount(
            id=uuid.uuid4(),
            case_id=(case or self.case).id,
            identity_key=f"gb-barclays-{digits}",
            institution_name="Barclays",
            identifier_normalised=digits,
            currency="GBP",
        )
        self.db.add(account)
        self.db.flush()
        return account

    def decide(
        self,
        subject,
        subject_type,
        *,
        case=None,
        decision=AdjudicationDecision.admit_financial_document,
        reason="Because it is a statement and the figures have to be traceable.",
        actor=None,
        before=None,
        after=None,
    ):
        """One decision, written the way production writes it."""
        event_row = record(
            self.db,
            case_id=(case or self.case).id,
            subject=subject,
            subject_type=subject_type,
            decision=decision,
            reason=reason,
            actor=actor or self.actor,
            before=before,
            after=after,
        )
        self.db.commit()
        return event_row

    def insert(
        self,
        *,
        case=None,
        subject_id=None,
        subject_type=AdjudicationSubject.evidence_file,
        sequence=1,
        decision=AdjudicationDecision.admit_financial_document,
        reason="Stated.",
        created_at=NOON,
        actor_email="investigator@example.test",
        actor_name="Investigator",
    ):
        """A row placed directly, so its timestamp can be stated.

        ``created_at`` is a server default, so the writer cannot be asked for
        a particular instant.  Used only by the tests that are about which
        instant an event carries.
        """
        row = AdjudicationEvent(
            id=uuid.uuid4(),
            case_id=(case or self.case).id,
            subject_type=subject_type.value,
            subject_id=subject_id or self.evidence_file.id,
            subject_sequence=sequence,
            decision=decision.value,
            reason=reason,
            actor_name=actor_name,
            actor_email=actor_email,
            created_at=created_at,
        )
        self.db.add(row)
        self.db.commit()
        return row

    def ids(self, page):
        return [record_.id for record_ in page.decisions]


class CaseScopeTests(DecisionLogTestCase):
    """The case is in the WHERE clause, not checked after the fact."""

    def test_returns_decisions_recorded_in_this_case(self):
        written = self.decide(
            self.evidence_file, AdjudicationSubject.evidence_file
        )

        page = list_case_decisions(self.db, self.case.id)

        self.assertEqual(self.ids(page), [str(written.id)])
        self.assertEqual(page.total, 1)
        self.assertEqual(page.case_id, str(self.case.id))

    def test_excludes_decisions_recorded_in_another_case(self):
        other_file = self.file(
            case=self.other_case, sha256=HASH_B, name="other.pdf"
        )
        self.decide(self.evidence_file, AdjudicationSubject.evidence_file)
        self.decide(
            other_file,
            AdjudicationSubject.evidence_file,
            case=self.other_case,
        )

        page = list_case_decisions(self.db, self.case.id)

        self.assertEqual(page.total, 1)
        self.assertEqual(
            {record_.case_id for record_ in page.decisions},
            {str(self.case.id)},
        )

    def test_naming_another_cases_subject_returns_nothing(self):
        # The failure this guards is the one `decisions.history` would have
        # if it were reached from a request: subject ids are unguessable, but
        # a caller who has seen one is not guessing.
        other_file = self.file(
            case=self.other_case, sha256=HASH_B, name="other.pdf"
        )
        self.decide(
            other_file,
            AdjudicationSubject.evidence_file,
            case=self.other_case,
        )

        page = list_case_decisions(
            self.db, self.case.id, subject_id=other_file.id
        )

        self.assertEqual(page.decisions, ())
        self.assertEqual(page.total, 0)

    def test_a_case_with_no_decisions_is_an_empty_page_not_an_error(self):
        page = list_case_decisions(self.db, self.case.id)

        self.assertEqual(page.decisions, ())
        self.assertEqual(page.total, 0)
        self.assertFalse(page.truncated)

    def test_refuses_a_read_with_no_case(self):
        with self.assertRaises(DecisionLogError) as raised:
            list_case_decisions(self.db, None)

        self.assertIn("needs a case", str(raised.exception))


class FilterTests(DecisionLogTestCase):
    def setUp(self):
        super().setUp()
        self.on_file = self.decide(
            self.evidence_file, AdjudicationSubject.evidence_file
        )
        self.on_account = self.decide(
            self.account,
            AdjudicationSubject.account,
            decision=AdjudicationDecision.supersede_duplicate,
            reason="The same account arrived twice under two spellings.",
        )

    def test_filters_by_subject_type(self):
        page = list_case_decisions(
            self.db,
            self.case.id,
            subject_type=AdjudicationSubject.account,
        )

        self.assertEqual(self.ids(page), [str(self.on_account.id)])
        self.assertEqual(page.total, 1)

    def test_filters_by_subject_id(self):
        page = list_case_decisions(
            self.db, self.case.id, subject_id=self.evidence_file.id
        )

        self.assertEqual(self.ids(page), [str(self.on_file.id)])

    def test_filters_by_decision(self):
        page = list_case_decisions(
            self.db,
            self.case.id,
            decision=AdjudicationDecision.supersede_duplicate,
        )

        self.assertEqual(self.ids(page), [str(self.on_account.id)])

    def test_total_counts_the_filtered_population_not_the_case(self):
        # A reader filtered to one subject needs that subject's count. The
        # case's own count answers a question nobody asked here.
        page = list_case_decisions(
            self.db,
            self.case.id,
            subject_type=AdjudicationSubject.account,
        )

        self.assertEqual(page.total, 1)
        self.assertEqual(list_case_decisions(self.db, self.case.id).total, 2)

    def test_refuses_a_subject_type_given_as_a_string(self):
        # For the reason `record` refuses one: a vocabulary member misspelt
        # as text returns an empty page rather than saying the word is not in
        # the vocabulary.
        with self.assertRaises(DecisionLogError) as raised:
            list_case_decisions(
                self.db, self.case.id, subject_type="evidence_file"
            )

        self.assertIn("AdjudicationSubject", str(raised.exception))

    def test_refuses_a_decision_given_as_a_string(self):
        with self.assertRaises(DecisionLogError) as raised:
            list_case_decisions(
                self.db, self.case.id, decision="release_row"
            )

        self.assertIn("AdjudicationDecision", str(raised.exception))


class OrderTests(DecisionLogTestCase):
    """What the order claims, and what it refuses to claim."""

    def test_newest_first(self):
        older = self.insert(sequence=1, created_at=NOON)
        newer = self.insert(
            sequence=2,
            created_at=NOON + _datetime.timedelta(minutes=5),
        )

        page = list_case_decisions(self.db, self.case.id)

        self.assertEqual(self.ids(page), [str(newer.id), str(older.id)])

    def test_events_sharing_a_timestamp_on_one_subject_order_by_sequence(self):
        # The case `decisions.history` exists for: a quarantine and the
        # release that undid it, written in one transaction, sharing
        # `now()` exactly. Newest first means the reversal leads.
        first = self.insert(
            sequence=1,
            decision=AdjudicationDecision.quarantine_row,
            subject_type=AdjudicationSubject.account,
            subject_id=self.account.id,
        )
        second = self.insert(
            sequence=2,
            decision=AdjudicationDecision.release_row,
            subject_type=AdjudicationSubject.account,
            subject_id=self.account.id,
        )

        page = list_case_decisions(self.db, self.case.id)

        self.assertEqual(self.ids(page), [str(second.id), str(first.id)])

    def test_every_record_carries_the_sequence_that_is_authoritative(self):
        self.insert(sequence=1)
        self.insert(sequence=2)

        page = list_case_decisions(self.db, self.case.id)

        self.assertEqual(
            [record_.subject_sequence for record_ in page.decisions], [2, 1]
        )

    def test_the_order_is_total_so_paging_does_not_lose_a_row(self):
        # Six events across two subjects, all on one timestamp: the worst
        # case the table can produce. Paged two at a time, every row must
        # appear exactly once.
        for sequence in (1, 2, 3):
            self.insert(sequence=sequence)
            self.insert(
                sequence=sequence,
                subject_type=AdjudicationSubject.account,
                subject_id=self.account.id,
            )

        seen = []
        for offset in (0, 2, 4):
            page = list_case_decisions(
                self.db, self.case.id, limit=2, offset=offset
            )
            seen.extend(self.ids(page))

        self.assertEqual(len(seen), 6)
        self.assertEqual(len(set(seen)), 6)

    def test_the_same_read_twice_returns_the_same_order(self):
        for sequence in (1, 2, 3):
            self.insert(sequence=sequence)
            self.insert(
                sequence=sequence,
                subject_type=AdjudicationSubject.account,
                subject_id=self.account.id,
            )

        first = self.ids(list_case_decisions(self.db, self.case.id))
        second = self.ids(list_case_decisions(self.db, self.case.id))

        self.assertEqual(first, second)


class PagingTests(DecisionLogTestCase):
    def setUp(self):
        super().setUp()
        self.written = [
            self.insert(
                sequence=sequence,
                created_at=NOON + _datetime.timedelta(minutes=sequence),
            )
            for sequence in range(1, 6)
        ]

    def test_total_is_the_whole_population_not_the_page(self):
        page = list_case_decisions(self.db, self.case.id, limit=2)

        self.assertEqual(len(page.decisions), 2)
        self.assertEqual(page.total, 5)

    def test_truncated_says_rows_were_left_off(self):
        page = list_case_decisions(self.db, self.case.id, limit=2)

        self.assertTrue(page.truncated)

    def test_the_last_page_is_not_truncated(self):
        page = list_case_decisions(self.db, self.case.id, limit=2, offset=4)

        self.assertEqual(len(page.decisions), 1)
        self.assertFalse(page.truncated)

    def test_a_page_holding_everything_is_not_truncated(self):
        page = list_case_decisions(self.db, self.case.id)

        self.assertEqual(len(page.decisions), 5)
        self.assertFalse(page.truncated)

    def test_offset_walks_the_same_order(self):
        whole = self.ids(list_case_decisions(self.db, self.case.id))
        walked = []
        for offset in range(0, 5, 2):
            walked.extend(
                self.ids(
                    list_case_decisions(
                        self.db, self.case.id, limit=2, offset=offset
                    )
                )
            )

        self.assertEqual(walked, whole)

    def test_an_offset_past_the_end_is_an_empty_page_with_a_true_total(self):
        page = list_case_decisions(self.db, self.case.id, offset=500)

        self.assertEqual(page.decisions, ())
        self.assertEqual(page.total, 5)
        self.assertFalse(page.truncated)

    def test_a_limit_over_the_cap_is_capped_rather_than_refused(self):
        page = list_case_decisions(
            self.db, self.case.id, limit=MAX_DECISION_LIMIT + 1000
        )

        self.assertEqual(page.limit, MAX_DECISION_LIMIT)

    def test_the_default_limit_is_reported(self):
        page = list_case_decisions(self.db, self.case.id)

        self.assertEqual(page.limit, DEFAULT_DECISION_LIMIT)
        self.assertEqual(page.offset, 0)

    def test_refuses_a_limit_below_one(self):
        with self.assertRaises(DecisionLogError):
            list_case_decisions(self.db, self.case.id, limit=0)

    def test_refuses_a_negative_offset(self):
        with self.assertRaises(DecisionLogError):
            list_case_decisions(self.db, self.case.id, offset=-1)

    def test_refuses_a_boolean_limit(self):
        # `isinstance(True, int)` is true, and a limit of True is a limit of
        # one row that nobody asked for.
        with self.assertRaises(DecisionLogError):
            list_case_decisions(self.db, self.case.id, limit=True)


class RecordShapeTests(DecisionLogTestCase):
    def test_reads_back_what_the_writer_wrote(self):
        written = self.decide(
            self.evidence_file,
            AdjudicationSubject.evidence_file,
            reason="Held by the router and sent on anyway.",
            before={"routed_to": "held"},
            after={"routed_to": "document_pipeline"},
        )

        page = list_case_decisions(self.db, self.case.id)
        record_ = page.decisions[0]

        self.assertEqual(record_.id, str(written.id))
        self.assertEqual(record_.case_id, str(self.case.id))
        self.assertEqual(record_.subject_type, "evidence_file")
        self.assertEqual(record_.subject_id, str(self.evidence_file.id))
        self.assertEqual(record_.subject_sequence, 1)
        self.assertEqual(record_.decision, "admit_financial_document")
        self.assertEqual(record_.reason, "Held by the router and sent on anyway.")
        self.assertEqual(record_.before, {"routed_to": "held"})
        self.assertEqual(record_.after, {"routed_to": "document_pipeline"})
        self.assertEqual(record_.actor_name, "Investigator")
        self.assertEqual(record_.actor_email, "investigator@example.test")
        self.assertEqual(record_.actor_user_id, str(self.user.id))
        self.assertIsNone(record_.ingestion_run_id)
        self.assertIsNotNone(record_.recorded_at)

    def test_an_event_with_no_snapshot_carries_none_not_an_empty_dict(self):
        # A review that changed nothing is written with both sides absent.
        # An empty dict would read as a diff over no fields.
        self.decide(self.evidence_file, AdjudicationSubject.evidence_file)

        record_ = list_case_decisions(self.db, self.case.id).decisions[0]

        self.assertIsNone(record_.before)
        self.assertIsNone(record_.after)

    def test_a_persons_decision_is_not_marked_as_a_machines(self):
        self.decide(self.evidence_file, AdjudicationSubject.evidence_file)

        record_ = list_case_decisions(self.db, self.case.id).decisions[0]

        self.assertFalse(record_.by_machine)

    def test_the_reconciliation_stages_decision_is_marked_as_a_machines(self):
        self.decide(
            self.evidence_file,
            AdjudicationSubject.evidence_file,
            decision=AdjudicationDecision.reclassify_document,
            reason="The arithmetic reported and the class moved.",
            actor=self.machine,
        )

        record_ = list_case_decisions(self.db, self.case.id).decisions[0]

        self.assertTrue(record_.by_machine)
        self.assertEqual(record_.actor_email, RECONCILIATION_ACTOR_EMAIL)

    def test_the_machine_address_is_matched_regardless_of_case(self):
        self.insert(actor_email=RECONCILIATION_ACTOR_EMAIL.upper())

        record_ = list_case_decisions(self.db, self.case.id).decisions[0]

        self.assertTrue(record_.by_machine)

    def test_an_address_merely_containing_the_machines_is_not_the_machines(self):
        self.insert(actor_email="not-" + RECONCILIATION_ACTOR_EMAIL)

        record_ = list_case_decisions(self.db, self.case.id).decisions[0]

        self.assertFalse(record_.by_machine)

    def test_as_dict_names_every_field_the_record_carries(self):
        self.decide(self.evidence_file, AdjudicationSubject.evidence_file)

        record_ = list_case_decisions(self.db, self.case.id).decisions[0]

        self.assertEqual(
            set(record_.as_dict()),
            {
                "id",
                "case_id",
                "subject_type",
                "subject_id",
                "subject_sequence",
                "decision",
                "reason",
                "before",
                "after",
                "actor_name",
                "actor_email",
                "actor_user_id",
                "ingestion_run_id",
                "recorded_at",
                "by_machine",
            },
        )

    def test_page_as_dict_carries_the_counts_a_reader_needs(self):
        self.decide(self.evidence_file, AdjudicationSubject.evidence_file)

        payload = list_case_decisions(self.db, self.case.id, limit=1).as_dict()

        self.assertEqual(
            set(payload),
            {
                "case_id",
                "decisions",
                "total",
                "limit",
                "offset",
                "truncated",
            },
        )
        self.assertEqual(len(payload["decisions"]), 1)
        self.assertIsInstance(payload["decisions"][0], dict)

    def test_a_record_is_json_ready(self):
        # Everything crossing the wire is a string, an int, a bool, None, or
        # a dict that `decisions._jsonable` already vetted. A uuid or a
        # datetime reaching here would fail at serialisation, a long way from
        # this module.
        import json

        self.decide(
            self.evidence_file,
            AdjudicationSubject.evidence_file,
            before={"routed_to": "held"},
            after={"routed_to": "document_pipeline"},
        )

        payload = list_case_decisions(self.db, self.case.id).as_dict()

        self.assertIsInstance(json.dumps(payload), str)

    def test_to_record_states_which_address_it_calls_the_machines(self):
        # Passed in rather than looked up per row, so a page of five hundred
        # does not repeat the deferred import five hundred times.
        row = self.insert(actor_email="someone@example.test")

        as_person = to_record(row, machine_email=RECONCILIATION_ACTOR_EMAIL)
        as_machine = to_record(row, machine_email="someone@example.test")

        self.assertFalse(as_person.by_machine)
        self.assertTrue(as_machine.by_machine)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
