"""Tests for reading the ledger back out: the other half of "both stores".

``services.financial.transactions.record_transactions`` has had a writer for
as long as the relational ledger has existed; nothing before
``list_transactions``/``to_view`` could read a row back out of Postgres
through anything other than a database client opened by hand. The tests here
are organised around the two things a reader needs to get right that a writer
does not have to think about.

*The default population is not "every row".* ``ledger_status`` left unset
means admitted, because admitted is the population every other total in this
ledger already assumes. A caller that wants quarantined or superseded rows
has to say so, and :class:`ListTransactionsTests` checks both the default and
the override, plus the ordering, account, date-range, and case-scoping
filters a read endpoint needs to be trustworthy.

*The locator does not live where the reader wants it.* The writer nests it
under ``provenance[LOCATOR_PROVENANCE_KEY]`` because provenance is an open
bag; :class:`ToViewTests` checks that ``to_view`` lifts it back out to a
top-level field, and that every closed-vocabulary column comes back as the
plain string or int the writer put there, not an enum instance.

The database-backed tests use a file on disk rather than ``:memory:``,
matching ``test_financial_transactions_writer``: the run service opens
sessions of its own, and a test where the caller and the bookkeeping share
one connection cannot see what production sees.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import (
    ExtractionLayer,
    GlobalRole,
    LedgerStatus,
    LocatorKind,
    ReconciliationStatus,
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
from services.financial.documents import SourceDocumentDraft, record_source_document
from services.financial.locators import Locator
from services.financial.proof_class import SourceShape
from services.financial.references import RowReading
from services.financial.runs import open_ingestion_run
from services.financial.transaction_query import (
    LedgerQueryError,
    list_transactions,
    to_view,
)
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
HASH_B = "b" * 64

JANUARY = date(2024, 1, 15)
FEBRUARY = date(2024, 2, 15)
MARCH = date(2024, 3, 15)

#: The honest locator for rows these tests are not about: nothing is claimed.
UNLOCATED = Locator(kind=LocatorKind.unlocated)


def reading(**overrides) -> RowReading:
    """An ordinary debit, dated the one way most sources date a row."""
    overrides.setdefault("currency", GBP)
    overrides.setdefault("amount_minor", 12_50)
    overrides.setdefault("direction", TransactionDirection.debit)
    overrides.setdefault("posted_date", JANUARY)
    return RowReading(**overrides)


class LedgerQueryTestCase(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.mkdtemp(prefix="loupe-ledger-query-")
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
            title="Ledger Query Fixture",
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
        self.document = self.admit()
        self.acct = self.account()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        shutil.rmtree(self._directory, ignore_errors=True)

    def admit(self, run=None, evidence_file_id=None, sha256=HASH_A, **overrides):
        overrides.setdefault("evidence_file_id", evidence_file_id or self.evidence_file.id)
        overrides.setdefault("sha256_at_ingestion", sha256)
        overrides.setdefault("document_type", "bank_statement")
        overrides.setdefault("shape", SourceShape.statement_document)
        overrides.setdefault("extraction_layer", ExtractionLayer.structural)
        overrides.setdefault("parser_name", "statement_pdf")
        overrides.setdefault("parser_version", "1.4.0")
        return record_source_document(
            self.db, run or self.run, SourceDocumentDraft(**overrides)
        )

    def account(self, case_id=None, run=None):
        """A distinct account per call, so identity keys do not collide."""
        self._accounts = getattr(self, "_accounts", 0) + 1
        digits = f"2044556{self._accounts}"
        account = FinancialAccount(
            id=uuid.uuid4(),
            case_id=case_id or self.case.id,
            first_seen_run_id=(run or self.run).run_id,
            identity_key=f"gb-barclays-{digits}",
            institution_name="Barclays",
            identifier_as_printed=f"20-44-55 6{self._accounts}",
            identifier_normalised=digits,
            currency=GBP,
        )
        self.db.add(account)
        self.db.flush()
        return account

    def draft(self, **overrides) -> TransactionDraft:
        overrides.setdefault("reading", reading())
        overrides.setdefault("row_index", 0)
        overrides.setdefault("account_id", self.acct.id)
        overrides.setdefault("locator", UNLOCATED)
        return TransactionDraft(**overrides)

    def write(self, drafts, document=None, run=None):
        return record_transactions(
            self.db, run or self.run, document or self.document, drafts
        )


class ListTransactionsTests(LedgerQueryTestCase):
    def test_defaults_to_admitted_rows_only(self):
        (admitted,) = self.write([self.draft()])
        (to_quarantine,) = self.write(
            [self.draft(row_index=1, reading=reading(amount_minor=13_50))]
        )
        to_quarantine.ledger_status = LedgerStatus.quarantined.value
        to_quarantine.quarantine_reason = "unreadable_row"
        self.db.commit()

        rows = list_transactions(self.db, self.case.id)

        self.assertEqual([row.id for row in rows], [admitted.id])

    def test_an_explicit_status_overrides_the_default(self):
        (admitted,) = self.write([self.draft()])
        (quarantined,) = self.write(
            [self.draft(row_index=1, reading=reading(amount_minor=13_50))]
        )
        quarantined.ledger_status = LedgerStatus.quarantined.value
        quarantined.quarantine_reason = "unreadable_row"
        self.db.commit()

        rows = list_transactions(
            self.db, self.case.id, ledger_status=LedgerStatus.quarantined
        )

        self.assertEqual([row.id for row in rows], [quarantined.id])

    def test_orders_by_ordering_date_then_row_index(self):
        later, earlier_second, earlier_first = self.write(
            [
                self.draft(reading=reading(posted_date=FEBRUARY), row_index=2),
                self.draft(reading=reading(posted_date=JANUARY), row_index=1),
                self.draft(reading=reading(posted_date=JANUARY), row_index=0),
            ]
        )

        rows = list_transactions(self.db, self.case.id)

        self.assertEqual(
            [row.id for row in rows],
            [earlier_first.id, earlier_second.id, later.id],
        )

    def test_filters_by_account(self):
        other_account = self.account()
        (row_on_first,) = self.write([self.draft()])
        (row_on_second,) = self.write(
            [
                self.draft(
                    row_index=1,
                    account_id=other_account.id,
                    reading=reading(amount_minor=13_50),
                )
            ]
        )

        rows = list_transactions(self.db, self.case.id, account_id=self.acct.id)

        self.assertEqual([row.id for row in rows], [row_on_first.id])
        self.assertNotIn(row_on_second.id, [row.id for row in rows])

    def test_filters_by_ordering_date_range(self):
        january_row, february_row, march_row = self.write(
            [
                self.draft(reading=reading(posted_date=JANUARY), row_index=0),
                self.draft(reading=reading(posted_date=FEBRUARY), row_index=1),
                self.draft(reading=reading(posted_date=MARCH), row_index=2),
            ]
        )

        rows = list_transactions(
            self.db, self.case.id, start_date=FEBRUARY, end_date=FEBRUARY
        )

        self.assertEqual([row.id for row in rows], [february_row.id])

    def test_a_start_date_after_the_end_date_is_refused(self):
        with self.assertRaises(LedgerQueryError):
            list_transactions(
                self.db, self.case.id, start_date=FEBRUARY, end_date=JANUARY
            )

    def test_a_row_in_another_case_is_not_returned(self):
        other_evidence = EvidenceFile(
            id=uuid.uuid4(),
            case_id=self.other_case.id,
            original_filename="other-statement.pdf",
            stored_path="/evidence/other-statement.pdf",
            sha256=HASH_B,
        )
        self.db.add(other_evidence)
        self.db.commit()

        other_run = open_ingestion_run(
            case_id=self.other_case.id,
            actor=self.user,
            session_factory=self.SessionLocal,
        )
        other_document = self.admit(
            run=other_run, evidence_file_id=other_evidence.id, sha256=HASH_B
        )
        other_account = self.account(case_id=self.other_case.id, run=other_run)
        (this_case_row,) = self.write([self.draft()])
        (other_case_row,) = self.write(
            [
                self.draft(row_index=0, account_id=other_account.id),
            ],
            document=other_document,
            run=other_run,
        )

        rows = list_transactions(self.db, self.case.id)

        self.assertEqual([row.id for row in rows], [this_case_row.id])
        self.assertNotIn(other_case_row.id, [row.id for row in rows])


class ToViewTests(LedgerQueryTestCase):
    def test_lifts_the_locator_out_of_provenance(self):
        (row,) = self.write([self.draft(locator=UNLOCATED)])

        view = to_view(row)

        self.assertEqual(view.locator, UNLOCATED.to_json())

    def test_dates_are_isoformat_strings(self):
        (row,) = self.write([self.draft(reading=reading(posted_date=JANUARY))])

        view = to_view(row)

        self.assertEqual(view.ordering_date, "2024-01-15")

    def test_closed_vocabulary_columns_come_back_as_plain_primitives(self):
        (row,) = self.write(
            [self.draft(reading=reading(direction=TransactionDirection.credit))]
        )

        view = to_view(row)

        self.assertEqual(view.direction, "credit")
        self.assertIsInstance(view.direction, str)
        self.assertEqual(view.ledger_status, "admitted")
        self.assertIsInstance(view.proof_class, str)
        self.assertIsInstance(view.extraction_layer, int)

    def test_to_json_is_a_plain_serialisable_dict(self):
        (row,) = self.write([self.draft()])

        payload = to_view(row).to_json()

        self.assertEqual(payload["key"], str(row.id))
        self.assertEqual(payload["case_id"], str(self.case.id))
        self.assertEqual(payload["account_id"], str(self.acct.id))
        self.assertIsNone(payload["statement_period_id"])
        self.assertIsNone(payload["superseded_by_id"])

    def test_json_money_preserves_full_bigint_precision_and_negative_balance(self):
        import json
        (row,) = self.write([self.draft()])
        row.amount_minor = 9007199254740993
        row.running_balance_minor = -9223372036854775808
        payload = json.loads(json.dumps(to_view(row).to_json()))
        self.assertEqual(payload["amount_minor"], "9007199254740993")
        self.assertEqual(payload["running_balance_minor"], "-9223372036854775808")



if __name__ == "__main__":
    unittest.main()
