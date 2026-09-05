"""Tests for setting one stored ledger row aside, and letting it back in.

``services.financial.quarantine`` has had both writers for as long as the
ledger has had a status column, and until now nothing called either of them.
``test_financial_quarantine`` covers what the writers refuse; these tests cover
the half that was missing, which is finding the row in the first place and
turning each refusal into something an interface can show.

Three things a driver has to get right that the writers do not have to think
about.

*A row in another case is not a row.*  Both writers take a transaction already
loaded and a ``case_id`` given separately, and ``decisions.record`` compares
them as a last line.  That check can only fire once somebody has loaded a row
belonging to a matter they may not be able to see, so the lookup here filters
on the case and reports a foreign row identically to one that does not exist.

*A refusal is a fact, not a fault.*  Every ``UngroundedQuarantineError`` the
writers raise is a true statement about the ledger's current state -- already
set aside on other grounds, already outside every total, nothing to release.
A person clicking on a row fetched a minute ago has no way to know any of them
in advance, so they come back as ``refused`` carrying the writer's sentence.

*An idempotent write is not a write.*  ``quarantine_transaction`` deliberately
appends nothing for a row already quarantined on the same grounds.  Reporting
that as ``quarantined`` would name an adjudication belonging to somebody
else's earlier decision, so it is reported as ``unchanged`` with no id claimed.

The database-backed tests use a file on disk rather than ``:memory:``, matching
``test_financial_transaction_query``, for the reason that test gives.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
import uuid
from datetime import date
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import (
    AdjudicationDecision,
    AdjudicationSubject,
    ExtractionLayer,
    GlobalRole,
    LedgerStatus,
    LocatorKind,
    QuarantineReason,
    TransactionDirection,
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
from services.financial import quarantine_row
from services.financial.decisions import Actor, history
from services.financial.documents import SourceDocumentDraft, record_source_document
from services.financial.locators import Locator
from services.financial.money import Money, MoneyError
from services.financial.periods import (
    BalanceObservation,
    PeriodBounds,
    StatementPeriodDraft,
    record_statement_period,
)
from services.financial.proof_class import SourceShape
from services.financial.quarantine import QuarantineBasis, quarantine_transaction
from services.financial.quarantine_row import (
    ActorError,
    RowAdjudication,
    RowAdjudicationOutcome,
    actor_from_user,
    find_case_transaction,
    quarantine_case_row,
    release_case_row,
)
from services.financial.references import RowReading
from services.financial.runs import open_ingestion_run
from services.financial.transactions import TransactionDraft, record_transactions

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

GBP = "GBP"
HASH_A = "a" * 64
JANUARY = date(2024, 1, 15)

UNLOCATED = Locator(kind=LocatorKind.unlocated)


def reading(**overrides) -> RowReading:
    overrides.setdefault("currency", GBP)
    overrides.setdefault("amount_minor", 12_50)
    overrides.setdefault("direction", TransactionDirection.debit)
    overrides.setdefault("posted_date", JANUARY)
    return RowReading(**overrides)


class ActorFromUserTests(unittest.TestCase):
    """The person making the request, as somebody a decision can name."""

    class FakeUser:
        def __init__(self, **fields):
            for key, value in fields.items():
                setattr(self, key, value)

    def test_name_email_and_id_are_all_carried(self):
        user_id = uuid.uuid4()
        actor = actor_from_user(
            self.FakeUser(name="Alex", email="alex@owl.test", id=user_id)
        )

        self.assertIsInstance(actor, Actor)
        self.assertEqual(actor.name, "Alex")
        self.assertEqual(actor.email, "alex@owl.test")
        self.assertEqual(actor.user_id, user_id)

    def test_surrounding_whitespace_is_stripped(self):
        actor = actor_from_user(
            self.FakeUser(name="  Alex  ", email="  alex@owl.test ", id=uuid.uuid4())
        )

        self.assertEqual(actor.name, "Alex")
        self.assertEqual(actor.email, "alex@owl.test")

    def test_a_non_uuid_id_is_dropped_rather_than_stored(self):
        # ``Actor.user_id`` is a foreign key to users; a string that merely
        # looks like one would fail at the constraint, far from here.
        actor = actor_from_user(
            self.FakeUser(name="Alex", email="alex@owl.test", id="not-a-uuid")
        )

        self.assertIsNone(actor.user_id)

    def test_a_user_with_no_name_is_refused(self):
        with self.assertRaises(ActorError):
            actor_from_user(self.FakeUser(name="   ", email="alex@owl.test"))

    def test_a_user_with_no_email_is_refused(self):
        with self.assertRaises(ActorError):
            actor_from_user(self.FakeUser(name="Alex", email=None))


class RowAdjudicationTests(unittest.TestCase):
    """The response object, and which outcomes count as having changed a row."""

    def test_only_quarantined_and_released_are_applied(self):
        applied = {
            outcome
            for outcome in RowAdjudicationOutcome
            if RowAdjudication(transaction_id="x", outcome=outcome).applied
        }

        self.assertEqual(
            applied,
            {
                RowAdjudicationOutcome.quarantined,
                RowAdjudicationOutcome.released,
            },
        )

    def test_as_dict_carries_every_field_the_interface_needs(self):
        result = RowAdjudication(
            transaction_id="t-1",
            outcome=RowAdjudicationOutcome.quarantined,
            reason=None,
            ledger_status="quarantined",
            quarantine_reason="adjudicated",
            adjudication_id="a-1",
            rescues_period=False,
        )

        self.assertEqual(
            result.as_dict(),
            {
                "transaction_id": "t-1",
                "outcome": "quarantined",
                "applied": True,
                "reason": None,
                "ledger_status": "quarantined",
                "quarantine_reason": "adjudicated",
                "adjudication_id": "a-1",
                "rescues_period": False,
            },
        )

    def test_an_unanswered_rescue_check_is_absent_rather_than_false(self):
        # False is a finding: nothing was made to balance by the removal.
        # None is the absence of one.  A serialiser that flattened the two
        # would let a period whose identity could not be computed read as a
        # period that was checked and found safe.
        result = RowAdjudication(
            transaction_id="t-1", outcome=RowAdjudicationOutcome.quarantined
        )

        self.assertIsNone(result.as_dict()["rescues_period"])


class QuarantineRowTestCase(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.mkdtemp(prefix="loupe-quarantine-row-")
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
            email="alex@owl.test",
            name="Alex",
            password_hash="not-used",
            global_role=GlobalRole.user,
            is_active=True,
        )
        self.case = Case(
            id=uuid.uuid4(),
            title="Quarantine Fixture",
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
            original_filename="january-statement.pdf",
            stored_path="/evidence/january-statement.pdf",
            sha256=HASH_A,
        )
        self.db.add_all(
            [self.user, self.case, self.other_case, self.evidence_file]
        )
        self.db.commit()

        self.run = open_ingestion_run(
            case_id=self.case.id,
            actor=self.user,
            session_factory=self.SessionLocal,
        )
        self.document = record_source_document(
            self.db,
            self.run,
            SourceDocumentDraft(
                evidence_file_id=self.evidence_file.id,
                sha256_at_ingestion=HASH_A,
                document_type="bank_statement",
                shape=SourceShape.statement_document,
                extraction_layer=ExtractionLayer.structural,
                parser_name="statement_pdf",
                parser_version="1.4.0",
            ),
        )
        self.acct = self.account()
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        shutil.rmtree(self._directory, ignore_errors=True)

    def account(self, case_id=None):
        self._accounts = getattr(self, "_accounts", 0) + 1
        digits = f"2044556{self._accounts}"
        account = FinancialAccount(
            id=uuid.uuid4(),
            case_id=case_id or self.case.id,
            first_seen_run_id=self.run.run_id,
            identity_key=f"gb-barclays-{digits}",
            institution_name="Barclays",
            identifier_as_printed=f"20-44-55 6{self._accounts}",
            identifier_normalised=digits,
            currency=GBP,
        )
        self.db.add(account)
        self.db.flush()
        return account

    def row(self, row_index=0, amount_minor=12_50) -> FinancialTransaction:
        (written,) = record_transactions(
            self.db,
            self.run,
            self.document,
            [
                TransactionDraft(
                    reading=reading(amount_minor=amount_minor),
                    row_index=row_index,
                    account_id=self.acct.id,
                    locator=UNLOCATED,
                )
            ],
        )
        self.db.commit()
        return written

    def events(self, transaction):
        return history(self.db, transaction, AdjudicationSubject.transaction)


class FindCaseTransactionTests(QuarantineRowTestCase):
    def test_a_row_in_this_case_is_found(self):
        written = self.row()

        found = find_case_transaction(
            self.db, case_id=self.case.id, transaction_id=written.id
        )

        self.assertIsNotNone(found)
        self.assertEqual(found.id, written.id)

    def test_a_row_in_another_case_is_not_found(self):
        written = self.row()

        found = find_case_transaction(
            self.db, case_id=self.other_case.id, transaction_id=written.id
        )

        self.assertIsNone(found)


class QuarantineCaseRowTests(QuarantineRowTestCase):
    def test_the_row_is_set_aside_and_the_decision_appended(self):
        written = self.row()

        result = quarantine_case_row(
            self.db,
            case_id=self.case.id,
            transaction_id=written.id,
            actor=self.user,
            reason="the amount is illegible on the page",
        )

        self.assertEqual(result.outcome, RowAdjudicationOutcome.quarantined)
        self.assertTrue(result.applied)
        self.assertEqual(result.ledger_status, LedgerStatus.quarantined.value)
        self.assertEqual(
            result.quarantine_reason, QuarantineReason.adjudicated.value
        )
        self.assertIsNotNone(result.adjudication_id)

        self.db.refresh(written)
        self.assertEqual(written.ledger_status, LedgerStatus.quarantined.value)
        self.assertEqual(
            written.quarantine_reason, QuarantineReason.adjudicated.value
        )

    def test_the_decision_names_the_person_and_carries_the_reason(self):
        written = self.row()

        result = quarantine_case_row(
            self.db,
            case_id=self.case.id,
            transaction_id=written.id,
            actor=self.user,
            reason="the amount is illegible on the page",
        )

        (event,) = self.events(written)
        self.assertEqual(str(event.id), result.adjudication_id)
        self.assertEqual(event.decision, AdjudicationDecision.quarantine_row.value)
        self.assertEqual(event.actor_name, "Alex")
        self.assertEqual(event.actor_email, "alex@owl.test")
        self.assertEqual(event.actor_user_id, self.user.id)
        # The detail the writer built is what a reader sees, and it has to
        # carry both halves: who took it, and what they said.
        self.assertIn("Alex", event.reason)
        self.assertIn("the amount is illegible on the page", event.reason)

    def test_the_decision_records_the_status_it_changed(self):
        written = self.row()

        quarantine_case_row(
            self.db,
            case_id=self.case.id,
            transaction_id=written.id,
            actor=self.user,
            reason="illegible",
        )

        (event,) = self.events(written)
        self.assertEqual(event.before["ledger_status"], LedgerStatus.admitted.value)
        self.assertIsNone(event.before["quarantine_reason"])
        self.assertEqual(
            event.after["ledger_status"], LedgerStatus.quarantined.value
        )
        self.assertEqual(
            event.after["quarantine_reason"], QuarantineReason.adjudicated.value
        )

    def test_a_second_identical_quarantine_appends_nothing(self):
        written = self.row()
        quarantine_case_row(
            self.db,
            case_id=self.case.id,
            transaction_id=written.id,
            actor=self.user,
            reason="illegible",
        )

        again = quarantine_case_row(
            self.db,
            case_id=self.case.id,
            transaction_id=written.id,
            actor=self.user,
            reason="illegible again",
        )

        self.assertEqual(again.outcome, RowAdjudicationOutcome.unchanged)
        self.assertFalse(again.applied)
        # No id is claimed, because the only decision on this row belongs to
        # the first call.
        self.assertIsNone(again.adjudication_id)
        self.assertEqual(len(self.events(written)), 1)

    def test_a_row_quarantined_on_computed_grounds_is_refused_not_overwritten(self):
        written = self.row()
        quarantine_transaction(
            self.db,
            written,
            QuarantineBasis.unreadable_row("the decimal point did not read"),
            case_id=self.case.id,
            actor=Actor(name="Reconciliation", email="recon@loupe.invalid"),
        )
        self.db.commit()

        result = quarantine_case_row(
            self.db,
            case_id=self.case.id,
            transaction_id=written.id,
            actor=self.user,
            reason="setting it aside myself",
        )

        self.assertEqual(result.outcome, RowAdjudicationOutcome.refused)
        self.assertIn("already quarantined", result.reason)
        self.db.refresh(written)
        self.assertEqual(
            written.quarantine_reason, QuarantineReason.unreadable_row.value
        )
        self.assertEqual(len(self.events(written)), 1)

    def test_a_superseded_row_is_refused(self):
        written = self.row()
        written.ledger_status = LedgerStatus.superseded.value
        self.db.commit()

        result = quarantine_case_row(
            self.db,
            case_id=self.case.id,
            transaction_id=written.id,
            actor=self.user,
            reason="illegible",
        )

        self.assertEqual(result.outcome, RowAdjudicationOutcome.refused)
        self.assertEqual(result.ledger_status, LedgerStatus.superseded.value)
        self.assertEqual(self.events(written), ())

    def test_an_empty_reason_is_refused_and_the_row_is_untouched(self):
        written = self.row()

        result = quarantine_case_row(
            self.db,
            case_id=self.case.id,
            transaction_id=written.id,
            actor=self.user,
            reason="   ",
        )

        self.assertEqual(result.outcome, RowAdjudicationOutcome.refused)
        self.db.refresh(written)
        self.assertEqual(written.ledger_status, LedgerStatus.admitted.value)
        self.assertEqual(self.events(written), ())

    def test_a_user_who_cannot_be_named_is_refused(self):
        written = self.row()

        class Nameless:
            name = ""
            email = "nobody@owl.test"
            id = None

        result = quarantine_case_row(
            self.db,
            case_id=self.case.id,
            transaction_id=written.id,
            actor=Nameless(),
            reason="illegible",
        )

        self.assertEqual(result.outcome, RowAdjudicationOutcome.refused)
        self.db.refresh(written)
        self.assertEqual(written.ledger_status, LedgerStatus.admitted.value)

    def test_a_row_in_another_case_is_reported_as_missing(self):
        written = self.row()

        result = quarantine_case_row(
            self.db,
            case_id=self.other_case.id,
            transaction_id=written.id,
            actor=self.user,
            reason="illegible",
        )

        self.assertEqual(result.outcome, RowAdjudicationOutcome.not_found)
        self.db.refresh(written)
        self.assertEqual(written.ledger_status, LedgerStatus.admitted.value)

    def test_a_row_that_does_not_exist_is_reported_the_same_way(self):
        missing = uuid.uuid4()

        result = quarantine_case_row(
            self.db,
            case_id=self.case.id,
            transaction_id=missing,
            actor=self.user,
            reason="illegible",
        )

        self.assertEqual(result.outcome, RowAdjudicationOutcome.not_found)
        self.assertEqual(result.transaction_id, str(missing))

    def test_a_database_fault_is_write_failed_and_discarded(self):
        written = self.row()

        with patch.object(
            quarantine_row,
            "quarantine_transaction",
            side_effect=SQLAlchemyError("connection lost"),
        ):
            result = quarantine_case_row(
                self.db,
                case_id=self.case.id,
                transaction_id=written.id,
                actor=self.user,
                reason="illegible",
            )

        self.assertEqual(result.outcome, RowAdjudicationOutcome.write_failed)
        self.db.refresh(written)
        self.assertEqual(written.ledger_status, LedgerStatus.admitted.value)


class QuarantineRescueTests(QuarantineRowTestCase):
    """What the write path reports about the period the row is leaving.

    Removing a row from a failing statement moves that statement's arithmetic,
    and a row whose amount happens to equal the gap makes the statement balance
    the moment it comes out.  That is true whether the row was set aside for a
    good reason or a bad one, so the balance is not evidence of anything on its
    own and the system does not treat it as such.  It refuses nothing and it
    warns about nothing.  What it does is say, on the record, that this is what
    happened, so that whoever reads the decision later can weigh the grounds
    against the effect instead of finding a clean statement and no way to know
    it was cleaned.
    """

    OPENING = 100_00

    def period(self, *, closing_minor, month=1):
        return record_statement_period(
            self.db,
            self.run,
            StatementPeriodDraft(
                account_id=self.acct.id,
                source_document_id=self.document.id,
                currency=GBP,
                bounds=PeriodBounds.printed(
                    date(2024, month, 1), date(2024, month, 28)
                ),
                opening=BalanceObservation.printed(
                    Money.from_minor_units(self.OPENING, GBP)
                ),
                closing=BalanceObservation.printed(
                    Money.from_minor_units(closing_minor, GBP)
                ),
            ),
        )

    def period_row(
        self,
        *,
        period,
        row_index=0,
        amount_minor=25_00,
        direction=TransactionDirection.credit,
    ) -> FinancialTransaction:
        (written,) = record_transactions(
            self.db,
            self.run,
            self.document,
            [
                TransactionDraft(
                    reading=reading(
                        amount_minor=amount_minor,
                        direction=direction,
                        # Rows identical in amount, date and direction hash the
                        # same inside one document and collide on the content
                        # hash.  Real statements tell them apart by narrative.
                        description=f"row {row_index}",
                    ),
                    row_index=row_index,
                    account_id=self.acct.id,
                    locator=UNLOCATED,
                    statement_period_id=period.id,
                )
            ],
        )
        self.db.commit()
        return written

    def test_a_quarantine_that_makes_the_period_balance_says_so(self):
        # The statement prints an unchanged closing balance and carries one
        # 25.00 credit, so it is out by 25.00.  Setting that row aside closes
        # the gap exactly, which is the case the whole check exists for.
        period = self.period(closing_minor=self.OPENING)
        written = self.period_row(period=period)

        result = quarantine_case_row(
            self.db,
            case_id=self.case.id,
            transaction_id=written.id,
            actor=self.user,
            reason="the amount is illegible on the page",
        )

        self.assertEqual(result.outcome, RowAdjudicationOutcome.quarantined)
        self.assertIs(result.rescues_period, True)
        self.assertIn("makes the period balance", result.reason)
        self.assertIn("25.00", result.reason)

    def test_the_rescue_is_reported_without_refusing_the_quarantine(self):
        # Stated separately from the sentence because it is the more important
        # half.  A person's grounds are grounds; the arithmetic does not get a
        # veto over them, and a row proved wrong by its own statement is
        # supposed to come out and leave the statement balancing.
        period = self.period(closing_minor=self.OPENING)
        written = self.period_row(period=period)

        quarantine_case_row(
            self.db,
            case_id=self.case.id,
            transaction_id=written.id,
            actor=self.user,
            reason="the amount is illegible on the page",
        )

        self.db.refresh(written)
        self.assertEqual(written.ledger_status, LedgerStatus.quarantined.value)
        self.assertEqual(
            written.quarantine_reason, QuarantineReason.adjudicated.value
        )

    def test_the_sentence_is_not_written_into_the_reason_the_person_gave(self):
        # The adjudication log stores "<person>: <their reason>".  Appending a
        # machine observation to that string would leave a record in which the
        # person appears to have written words nobody wrote, which is the one
        # thing an evidence log cannot do.
        period = self.period(closing_minor=self.OPENING)
        written = self.period_row(period=period)

        quarantine_case_row(
            self.db,
            case_id=self.case.id,
            transaction_id=written.id,
            actor=self.user,
            reason="the amount is illegible on the page",
        )

        (event,) = self.events(written)
        self.assertEqual(event.reason, "Alex: the amount is illegible on the page")

    def test_a_quarantine_that_leaves_the_period_out_reports_no_rescue(self):
        # Two credits against an unchanged closing balance: the statement is
        # out by 30.00 and the row coming out is 5.00, so it explains part of
        # the gap and closes none of it.
        period = self.period(closing_minor=self.OPENING)
        self.period_row(period=period, row_index=0, amount_minor=25_00)
        written = self.period_row(period=period, row_index=1, amount_minor=5_00)

        result = quarantine_case_row(
            self.db,
            case_id=self.case.id,
            transaction_id=written.id,
            actor=self.user,
            reason="duplicated from the previous page",
        )

        self.assertEqual(result.outcome, RowAdjudicationOutcome.quarantined)
        self.assertIs(result.rescues_period, False)
        self.assertIsNone(result.reason)

    def test_a_period_that_already_balances_has_no_gap_to_close(self):
        # Nothing was made to balance by this removal, because it balanced
        # before it.  False rather than None: the question was answered.
        period = self.period(closing_minor=self.OPENING + 25_00)
        written = self.period_row(period=period)

        result = quarantine_case_row(
            self.db,
            case_id=self.case.id,
            transaction_id=written.id,
            actor=self.user,
            reason="the amount is illegible on the page",
        )

        self.assertIs(result.rescues_period, False)

    def test_a_row_belonging_to_no_period_is_answered_not_left_unknown(self):
        # Where there is no identity there is no gap, so no gap was closed.
        # Every row in this file's other tests is one of these, which is why
        # they all read False and none of them reads None.
        written = self.row()

        result = quarantine_case_row(
            self.db,
            case_id=self.case.id,
            transaction_id=written.id,
            actor=self.user,
            reason="the amount is illegible on the page",
        )

        self.assertIs(result.rescues_period, False)

    def test_a_check_that_cannot_be_answered_does_not_stop_the_quarantine(self):
        # The person's decision does not depend on the arithmetic being
        # available.  The row goes out and the unanswered question is recorded
        # as unanswered rather than as a clean bill of health.
        period = self.period(closing_minor=self.OPENING)
        written = self.period_row(period=period)

        with patch.object(
            quarantine_row,
            "rescue_if_removed",
            side_effect=MoneyError("currencies do not match"),
        ):
            result = quarantine_case_row(
                self.db,
                case_id=self.case.id,
                transaction_id=written.id,
                actor=self.user,
                reason="the amount is illegible on the page",
            )

        self.assertEqual(result.outcome, RowAdjudicationOutcome.quarantined)
        self.assertIsNone(result.rescues_period)
        self.db.refresh(written)
        self.assertEqual(written.ledger_status, LedgerStatus.quarantined.value)

    def test_a_refusal_reports_no_finding_because_nothing_was_removed(self):
        # An empty reason never reaches the write, so there is no removal to
        # describe and nothing to say about the period.
        period = self.period(closing_minor=self.OPENING)
        written = self.period_row(period=period)

        result = quarantine_case_row(
            self.db,
            case_id=self.case.id,
            transaction_id=written.id,
            actor=self.user,
            reason="   ",
        )

        self.assertEqual(result.outcome, RowAdjudicationOutcome.refused)
        self.assertIsNone(result.rescues_period)


class ReleaseCaseRowTests(QuarantineRowTestCase):
    def quarantined(self, **kwargs) -> FinancialTransaction:
        written = self.row(**kwargs)
        quarantine_case_row(
            self.db,
            case_id=self.case.id,
            transaction_id=written.id,
            actor=self.user,
            reason="illegible",
        )
        self.db.refresh(written)
        return written

    def test_the_row_is_readmitted_and_its_reason_nulled(self):
        written = self.quarantined()

        result = release_case_row(
            self.db,
            case_id=self.case.id,
            transaction_id=written.id,
            actor=self.user,
            reason="checked against the original, the figure is right",
        )

        self.assertEqual(result.outcome, RowAdjudicationOutcome.released)
        self.assertTrue(result.applied)
        self.assertEqual(result.ledger_status, LedgerStatus.admitted.value)
        self.assertIsNone(result.quarantine_reason)

        self.db.refresh(written)
        self.assertEqual(written.ledger_status, LedgerStatus.admitted.value)
        self.assertIsNone(written.quarantine_reason)

    def test_the_reversal_is_appended_after_the_quarantine_not_instead_of_it(self):
        written = self.quarantined()

        result = release_case_row(
            self.db,
            case_id=self.case.id,
            transaction_id=written.id,
            actor=self.user,
            reason="checked against the original",
        )

        held, released = self.events(written)
        self.assertEqual(held.decision, AdjudicationDecision.quarantine_row.value)
        self.assertEqual(released.decision, AdjudicationDecision.release_row.value)
        self.assertLess(held.subject_sequence, released.subject_sequence)
        self.assertEqual(str(released.id), result.adjudication_id)
        # The row can no longer say why it was held; the reversal is the only
        # place that record survives.
        self.assertEqual(
            released.before["quarantine_reason"],
            QuarantineReason.adjudicated.value,
        )
        self.assertIsNone(released.after["quarantine_reason"])
        self.assertEqual(released.reason, "checked against the original")

    def test_a_computed_quarantine_can_be_released_by_a_person(self):
        written = self.row()
        quarantine_transaction(
            self.db,
            written,
            QuarantineBasis.unreadable_row("the decimal point did not read"),
            case_id=self.case.id,
            actor=Actor(name="Reconciliation", email="recon@loupe.invalid"),
        )
        self.db.commit()

        result = release_case_row(
            self.db,
            case_id=self.case.id,
            transaction_id=written.id,
            actor=self.user,
            reason="read the figure off the original page",
        )

        self.assertEqual(result.outcome, RowAdjudicationOutcome.released)
        held, released = self.events(written)
        # The grounds the arithmetic raised are still on the record, with the
        # person's reversal after them rather than over them.
        self.assertEqual(held.actor_name, "Reconciliation")
        self.assertEqual(released.actor_name, "Alex")

    def test_an_admitted_row_is_refused(self):
        written = self.row()

        result = release_case_row(
            self.db,
            case_id=self.case.id,
            transaction_id=written.id,
            actor=self.user,
            reason="letting it back in",
        )

        self.assertEqual(result.outcome, RowAdjudicationOutcome.refused)
        self.assertIn("nothing to release", result.reason)
        self.assertEqual(self.events(written), ())

    def test_an_empty_reason_is_refused_and_the_row_stays_quarantined(self):
        written = self.quarantined()

        result = release_case_row(
            self.db,
            case_id=self.case.id,
            transaction_id=written.id,
            actor=self.user,
            reason="  ",
        )

        self.assertEqual(result.outcome, RowAdjudicationOutcome.refused)
        self.db.refresh(written)
        self.assertEqual(written.ledger_status, LedgerStatus.quarantined.value)
        self.assertEqual(len(self.events(written)), 1)

    def test_a_row_in_another_case_is_reported_as_missing(self):
        written = self.quarantined()

        result = release_case_row(
            self.db,
            case_id=self.other_case.id,
            transaction_id=written.id,
            actor=self.user,
            reason="letting it back in",
        )

        self.assertEqual(result.outcome, RowAdjudicationOutcome.not_found)
        self.db.refresh(written)
        self.assertEqual(written.ledger_status, LedgerStatus.quarantined.value)

    def test_a_database_fault_is_write_failed_and_discarded(self):
        written = self.quarantined()

        with patch.object(
            quarantine_row,
            "release_transaction",
            side_effect=SQLAlchemyError("connection lost"),
        ):
            result = release_case_row(
                self.db,
                case_id=self.case.id,
                transaction_id=written.id,
                actor=self.user,
                reason="letting it back in",
            )

        self.assertEqual(result.outcome, RowAdjudicationOutcome.write_failed)
        self.db.refresh(written)
        self.assertEqual(written.ledger_status, LedgerStatus.quarantined.value)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
