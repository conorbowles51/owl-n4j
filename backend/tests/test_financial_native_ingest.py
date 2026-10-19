"""Tests for the driver that walks a native reading through the four writers.

This module owns no rules of its own.  Every rule it tests lives in a writer,
and what the driver contributes is the order the writers are called in and the
two joins nothing below it can check: a row to its account, and a row to its
period.  The tests are organised around those two joins and around the three
things the driver decides for itself -- what the document's metadata says, what
the run counted, and what class the document ends at.

Why the period tests are the longest section
--------------------------------------------

A document can state one account's periods in three arrangements that look
alike and mean different things, and the writers cannot tell them apart because
each sees one period at a time.

*One span, stated once.*  The ordinary file.

*One span, stated twice, agreeing.*  A file that carries the same statement in
two messages.  It covers one span, so its rows sit inside one period and are
linked; the period is written once because
``uq_financial_statement_periods_document_account_period`` permits one.  This
case is in the suite because the first draft of the driver wrote one period per
statement and would have raised ``IntegrityError`` on it -- on a file with
nothing wrong with it.

*Two spans.*  January and February for one account in one file.  Both periods
are real and both carry their own printed balances, so both are written; but
every row of both carries the same ``account_key`` and nothing else, so no row
can be attributed to either period without inventing a rule the file never
stated.  The rows are stored unlinked and the document says why.

*One span, stated twice, disagreeing.*  Only one of the two claims can be
stored, and storing either would put it on the record as the document's only
claim.  Refused whole.

The distinction the tests are really pinning is that ambiguity is a property of
*spans*, not of statements.  Counting statements would make the second and
third cases identical, and the rows of a merely duplicated statement would lose
a period link they are entitled to.

The database-backed tests use a file on disk rather than ``:memory:``, matching
``test_financial_documents`` and ``test_financial_transactions_writer``: the run
service opens sessions of its own, and a test where the caller and the
bookkeeping share one connection cannot see what production sees.

The fixtures are imported from the parser suites rather than restated, for the
reason ``test_financial_native`` gives: a second copy of a file layout drifts
from the first the moment either changes, and the two then disagree silently.
"""

from __future__ import annotations

import dataclasses
import shutil
import tempfile
import unittest
import uuid
from pathlib import Path

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import GlobalRole, ProofClass
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
from services.financial.camt053 import (
    CAMT053_BALANCE_CLOSING_BOOKED,
    CAMT053_BALANCE_OPENING_BOOKED,
)
from services.financial.native import read_native
from services.financial.native_ingest import (
    AMBIGUOUS_PERIOD_METADATA_KEY,
    RESERVATIONS_METADATA_KEY,
    REVERSAL_METADATA_KEY,
    ContradictoryPeriodError,
    IngestionError,
    UnattributableRowError,
    ingest_native_reading,
)
from services.financial.runs import open_ingestion_run

# The parser suites' own fixture builders.  See the module docstring.
from tests.test_financial_camt053 import (
    DEFAULT_ENTRIES,
    bal,
    ntry,
    stmt,
)
from tests.test_financial_native import (
    NACHA_SIMPLE,
    WINDOW,
    bai2_bytes,
    camt_bytes,
    mt940_bytes,
    nacha_bytes,
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

#: The IBAN ``stmt()`` prints, and so the key its rows carry.
IBAN = "GB29NWBK60161331926819"

#: A second account, for the file that covers two.
OTHER_IBAN = "DE89370400440532013000"

SECOND_ACCOUNT = (
    f"<Acct><Id><IBAN>{OTHER_IBAN}</IBAN></Id><Ccy>USD</Ccy>"
    "<Ownr><Nm>Marlow Holdings LLC</Nm></Ownr>"
    "<Svcr><FinInstnId><BIC>NWBKGB2L</BIC></FinInstnId></Svcr></Acct>"
)

EUR_ACCOUNT = (
    f"<Acct><Id><IBAN>{OTHER_IBAN}</IBAN></Id><Ccy>EUR</Ccy>"
    "<Ownr><Nm>Marlow Holdings LLC</Nm></Ownr>"
    "<Svcr><FinInstnId><BIC>DEUTDEFF</BIC></FinInstnId></Svcr></Acct>"
)


def march(identification: str = "STMT-2") -> str:
    """``stmt()`` moved to a second span, by the suite's own ``replace`` idiom.

    Only the ``FrToDt`` timestamps are rewritten.  The balance dates carry no
    ``T``, so they are untouched and the statement keeps stating its balances
    as of the days it always did -- which is the point: two spans, one set of
    figures each, nothing else changed.
    """
    return (
        stmt(identification=identification)
        .replace("2026-02-01T00:00:00", "2026-03-01T00:00:00")
        .replace("2026-02-28T23:59:59", "2026-03-31T23:59:59")
    )


def disagreeing(identification: str = "STMT-2") -> str:
    """``stmt()`` over the same span, with a different opening balance."""
    return stmt(
        identification=identification,
        balances=(
            bal(CAMT053_BALANCE_OPENING_BOOKED, "9999.00")
            + bal(CAMT053_BALANCE_CLOSING_BOOKED, "12500.00", date="2026-02-28")
        ),
    )


class NativeIngestTestCase(unittest.TestCase):
    """One case, one run, and a fresh evidence file per document.

    ``uq_financial_source_documents_run_file`` holds one run to one reading of
    one file, so every document this suite admits needs an evidence file of its
    own rather than a second row against the first.
    """

    def setUp(self):
        self._directory = tempfile.mkdtemp(prefix="loupe-native-ingest-")
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
            title="Native Ingestion Fixture",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        self.db.add_all([self.user, self.case])
        self.db.commit()

        self._files = 0
        self.run = open_ingestion_run(
            case_id=self.case.id,
            actor=self.user,
            session_factory=self.SessionLocal,
        )

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        shutil.rmtree(self._directory, ignore_errors=True)

    # -- helpers ------------------------------------------------------------

    def evidence(self, sha256: str) -> EvidenceFile:
        self._files += 1
        record = EvidenceFile(
            id=uuid.uuid4(),
            case_id=self.case.id,
            original_filename=f"statement-{self._files}.dat",
            stored_path=f"/evidence/statement-{self._files}.dat",
            sha256=sha256,
        )
        self.db.add(record)
        self.db.commit()
        return record

    def ingest(self, data: bytes, *, sha256: str = HASH_A, **kwargs):
        """Read one file and store it, the way a caller of the driver would."""
        reading = read_native(data, window=WINDOW)
        return self.ingest_reading(reading, sha256=sha256, **kwargs)

    def ingest_reading(self, reading, *, sha256: str = HASH_A, **kwargs):
        evidence_file = self.evidence(sha256)
        result = ingest_native_reading(
            self.db,
            self.run,
            reading,
            evidence_file_id=evidence_file.id,
            sha256=sha256,
            window=WINDOW,
            **kwargs,
        )
        self.db.commit()
        return result

    def stored_rows(self) -> list[FinancialTransaction]:
        return list(
            self.db.execute(
                select(FinancialTransaction).order_by(FinancialTransaction.row_index)
            ).scalars()
        )

    def stored_periods(self) -> list[FinancialStatementPeriod]:
        return list(
            self.db.execute(select(FinancialStatementPeriod)).scalars()
        )


# ---------------------------------------------------------------------------
# The four formats, end to end
# ---------------------------------------------------------------------------


class FourFormatTests(NativeIngestTestCase):
    """Every format this repository parses reaches the database intact.

    The assertions are deliberately about the join and not about the parse.
    Whether the parser read the right amounts is ``test_financial_camt053``'s
    question and the other three suites'; whether every row it read arrived,
    against an account that exists, is this one's.
    """

    def assertArrived(self, result, reading):
        self.assertEqual(result.row_count, len(reading.rows))
        self.assertEqual(len(self.stored_rows()), len(reading.rows))
        self.assertEqual(
            {row.account_id for row in self.stored_rows()},
            {account.id for account in result.accounts},
        )
        self.assertEqual(
            result.document.document_type, reading.format.value
        )

    def test_camt053_is_stored_whole(self):
        data = camt_bytes()
        reading = read_native(data, window=WINDOW)
        self.assertArrived(self.ingest(data), reading)

    def test_bai2_is_stored_whole(self):
        data = bai2_bytes()
        reading = read_native(data, window=WINDOW)
        self.assertArrived(self.ingest(data), reading)

    def test_mt940_is_stored_whole(self):
        data = mt940_bytes()
        reading = read_native(data, window=WINDOW)
        self.assertArrived(self.ingest(data), reading)

    def test_nacha_is_stored_whole(self):
        data = nacha_bytes(NACHA_SIMPLE)
        reading = read_native(data, window=WINDOW)
        self.assertArrived(self.ingest(data), reading)

    def test_the_parser_is_recorded_on_the_document(self):
        """Which parser, at which version, read this file.

        A ledger built by a parser that was later found wrong has to be
        findable, and the only thing that makes it findable is the version
        having been written down at the time.
        """
        reading = read_native(camt_bytes(), window=WINDOW)
        result = self.ingest_reading(reading)
        self.assertEqual(result.document.parser_name, reading.parser_name)
        self.assertEqual(result.document.parser_version, reading.parser_version)
        self.assertEqual(
            result.document.extraction_layer, reading.extraction_layer
        )

    def test_a_caller_may_name_the_document_type_itself(self):
        """A bank shipping camt.053 inside its own export format.

        The format is what the bytes are; the document type is what the client
        called the thing they sent, and the second is not the driver's to
        overrule.
        """
        result = self.ingest(camt_bytes(), document_type="Quarterly Export")
        self.assertEqual(result.document.document_type, "Quarterly Export")


# ---------------------------------------------------------------------------
# The first join: a row to its account
# ---------------------------------------------------------------------------


class AttributionTests(NativeIngestTestCase):
    """Which account a row is stored against, and what happens when nobody knows.

    This is the join that nothing downstream can audit.  A row written against
    the wrong account is a well-formed row: it hashes, it balances against
    nothing in particular, and every report that reads it reads it as fact.
    The only place the mistake is visible is here.
    """

    def test_two_accounts_in_one_file_each_get_their_own_rows(self):
        result = self.ingest(
            camt_bytes(
                statements=stmt(identification="A")
                + stmt(identification="B", account=SECOND_ACCOUNT)
            )
        )
        self.assertEqual(len(result.accounts), 2)

        by_number = {account.id: account.iban for account in result.accounts}
        grouped: dict[str, int] = {}
        for row in self.stored_rows():
            grouped[by_number[row.account_id]] = (
                grouped.get(by_number[row.account_id], 0) + 1
            )
        self.assertEqual(grouped, {IBAN: 3, OTHER_IBAN: 3})

    def test_one_account_stated_twice_reaches_one_account_row(self):
        """Two statements, one account.  The second must find the first.

        ``record_account`` gets or creates, and the driver keys its mapping by
        the row key rather than by the subject, so a duplicated statement does
        not produce a second account for the same number.
        """
        result = self.ingest(
            camt_bytes(
                statements=stmt(identification="A") + stmt(identification="B")
            )
        )
        self.assertEqual(len(result.accounts), 1)
        self.assertEqual(
            len(list(self.db.execute(select(FinancialAccount)).scalars())), 1
        )

    def test_a_row_naming_an_account_no_subject_covers_is_refused(self):
        """Not written against a guess, and not quietly dropped.

        Both alternatives are worse than the refusal.  Inventing an account
        puts movements on a number the document never printed; dropping the row
        removes money from a total that a reconciliation has already declared
        balanced, so the file would go on to fail arithmetic it actually
        passed.
        """
        reading = read_native(camt_bytes(), window=WINDOW)
        doctored = dataclasses.replace(
            reading,
            rows=(
                dataclasses.replace(reading.rows[0], account_key="NOT-A-SUBJECT"),
            )
            + reading.rows[1:],
        )

        with self.assertRaises(UnattributableRowError) as caught:
            self.ingest_reading(doctored)
        self.assertIn("NOT-A-SUBJECT", str(caught.exception))
        self.assertIn("no subject of this document covers", str(caught.exception))

    def test_a_refused_row_leaves_no_rows_behind(self):
        """The refusal comes before any row is written, not part-way through.

        Rows are drafted for the whole document and only then handed to the
        writer, so a document with one unattributable row stores none of them.
        A partial ledger for a document that was refused would be worse than
        no ledger, because it would look complete.
        """
        reading = read_native(camt_bytes(), window=WINDOW)
        doctored = dataclasses.replace(
            reading,
            rows=reading.rows[:-1]
            + (dataclasses.replace(reading.rows[-1], account_key="ELSEWHERE"),),
        )

        with self.assertRaises(UnattributableRowError):
            self.ingest_reading(doctored)
        self.db.rollback()
        self.assertEqual(self.stored_rows(), [])


# ---------------------------------------------------------------------------
# What travels with a row
# ---------------------------------------------------------------------------


class RowContentTests(NativeIngestTestCase):
    """The three things about a row that only this module can carry across."""

    def test_the_reversal_flag_reaches_the_rows_metadata(self):
        """``is_reversal`` has no column, and losing it is not recoverable.

        ``services.financial.linkage.classify`` uses it to tell a reversal from
        an identifier conflict: a reversal legitimately carries the same
        reference as the entry it reverses, in the same account, in the
        opposite direction -- the one arrangement that would otherwise be
        reported as a contradiction.  Nothing yet builds linkage candidates
        from stored rows, so a driver that dropped the flag would pass every
        test in this repository and be discovered years later.
        """
        balances = bal(CAMT053_BALANCE_OPENING_BOOKED, "10000.00") + bal(
            CAMT053_BALANCE_CLOSING_BOOKED, "15000.00", date="2026-02-28"
        )
        entries = DEFAULT_ENTRIES + ntry(
            "2500.00", "CRDT", reference="R1", reversal=True
        )
        reading = read_native(
            camt_bytes(statements=stmt(entries=entries, balances=balances)),
            window=WINDOW,
        )
        self.assertEqual(
            [row.is_reversal for row in reading.rows],
            [False, False, False, True],
        )

        self.ingest_reading(reading)
        self.assertEqual(
            [row.metadata_[REVERSAL_METADATA_KEY] for row in self.stored_rows()],
            [False, False, False, True],
        )

    def test_the_locator_reaches_provenance_under_the_shared_key(self):
        """One reader opens a row's place in its source, whatever produced it.

        ``services.financial.table_geometry`` already writes locators under
        this key for rows that came off a page.  A native row that stored its
        locator somewhere else would need a second reader that knew which.
        """
        reading = read_native(camt_bytes(), window=WINDOW)
        self.ingest_reading(reading)
        for stored, parsed in zip(self.stored_rows(), reading.rows):
            self.assertEqual(stored.provenance["locator"], parsed.locator.to_json())

    def test_the_row_index_is_the_parsers_own(self):
        """Renumbering would change every row's identity.

        The occurrence index that separates two honestly identical readings is
        counted across the document, and a re-ingestion of an unchanged file
        that numbered its rows differently would produce different content
        hashes for the same money.
        """
        reading = read_native(
            camt_bytes(
                statements=stmt(identification="A")
                + stmt(identification="B", account=SECOND_ACCOUNT)
            ),
            window=WINDOW,
        )
        self.ingest_reading(reading)
        self.assertEqual(
            [row.row_index for row in self.stored_rows()],
            [row.row_index for row in reading.rows],
        )

    def test_a_gap_in_the_parsers_numbering_is_preserved(self):
        """The test above cannot fail today, and this one is why it is kept.

        Every parser in this repository currently numbers its rows ``0..n-1``,
        which is also what enumerating the drafts would produce -- so a driver
        that renumbered them would pass the preceding test, and did, when the
        renumbering was introduced deliberately to check.  The invariant is
        that the index is *carried*, not that it happens to match a counter.

        A gap is what a parser produces when it numbers rows against their
        position in the source and skips one it could not read.  Numbering
        against the source is what makes the index a locator into the document
        rather than a position in a list, and closing the gap here would move
        every later row onto a different content hash while the file itself was
        unchanged -- the one thing a re-ingestion must not do.
        """
        reading = read_native(camt_bytes(), window=WINDOW)
        skipped = dataclasses.replace(
            reading,
            rows=tuple(
                dataclasses.replace(row, row_index=index)
                for row, index in zip(reading.rows, (0, 2, 5))
            ),
        )
        self.ingest_reading(skipped)
        self.assertEqual([row.row_index for row in self.stored_rows()], [0, 2, 5])


# ---------------------------------------------------------------------------
# The second join: a row to its period
# ---------------------------------------------------------------------------


class PeriodTests(NativeIngestTestCase):
    """The four arrangements a document can state one account's periods in.

    See the module docstring.  These tests exist because the writers cannot
    tell the arrangements apart -- ``record_statement_period`` writes one
    period and is explicitly not get-or-create -- so the whole distinction is
    the driver's, and a driver that got it wrong would either crash on an
    ordinary file or silently link rows to a period they do not belong to.
    """

    def test_one_span_links_every_row_to_it(self):
        result = self.ingest(camt_bytes())
        self.assertEqual(len(result.periods), 1)
        self.assertEqual(result.unlinked_rows, 0)
        self.assertEqual(
            {row.statement_period_id for row in self.stored_rows()},
            {result.periods[0].id},
        )

    def test_one_span_stated_twice_is_written_once_and_still_links(self):
        """A file carrying the same statement in two messages.

        One span, so one period -- the unique constraint permits exactly one
        for a document, an account and a span, and the first draft of this
        driver wrote one per statement and raised ``IntegrityError`` here.  And
        because it is one span, there is only one period a row could belong to,
        so the rows are linked rather than orphaned: treating a redundant file
        as an ambiguous one would cost every row a link it is entitled to.
        """
        result = self.ingest(
            camt_bytes(
                statements=stmt(identification="A") + stmt(identification="B")
            )
        )
        self.assertEqual(len(result.periods), 1)
        self.assertEqual(len(self.stored_periods()), 1)
        self.assertEqual(result.unlinked_rows, 0)

        rows = self.stored_rows()
        self.assertEqual(len(rows), 6)
        self.assertEqual(
            {row.statement_period_id for row in rows}, {result.periods[0].id}
        )
        self.assertNotIn(
            AMBIGUOUS_PERIOD_METADATA_KEY, result.document.metadata_
        )

    def test_two_spans_record_both_periods_and_link_neither(self):
        """January and February for one account, in one file.

        Both periods are real and both carry their own printed balances, so
        both are recorded.  But every row of both statements carries the same
        ``account_key`` and nothing else, so which period a row belongs to is
        not in the reading.  Splitting by date would apply a rule the file
        never stated, hardest at the period boundary -- which is exactly where
        a reconciliation is most likely to be contested.
        """
        result = self.ingest(
            camt_bytes(statements=stmt(identification="A") + march())
        )
        self.assertEqual(len(result.periods), 2)
        self.assertEqual(len(self.stored_periods()), 2)

        rows = self.stored_rows()
        self.assertEqual(len(rows), 6)
        self.assertEqual(result.unlinked_rows, 6)
        self.assertEqual({row.statement_period_id for row in rows}, {None})

    def test_two_spans_are_named_on_the_document_as_the_reason(self):
        """A reviewer asking why these rows have no period gets an answer.

        Without this the rows are simply period-less, which is also what a
        NACHA file's rows are, and the two are not the same situation at all.
        """
        result = self.ingest(
            camt_bytes(statements=stmt(identification="A") + march())
        )
        self.assertEqual(
            result.document.metadata_[AMBIGUOUS_PERIOD_METADATA_KEY], [IBAN]
        )

    def test_one_account_ambiguous_does_not_unlink_another(self):
        """The second account's single span is still a link its rows may have.

        Ambiguity is per account.  A file where one account is stated twice
        over different spans says nothing at all about a second account it also
        covers, and withholding that account's period link would be this
        module penalising rows for what happened elsewhere in the file.
        """
        result = self.ingest(
            camt_bytes(
                statements=stmt(identification="A")
                + march("B")
                + stmt(identification="C", account=SECOND_ACCOUNT)
            )
        )
        self.assertEqual(len(result.periods), 3)

        other = next(a for a in result.accounts if a.iban == OTHER_IBAN)
        linked = [
            row for row in self.stored_rows() if row.account_id == other.id
        ]
        self.assertEqual(len(linked), 3)
        self.assertEqual(len({row.statement_period_id for row in linked}), 1)
        self.assertNotIn(None, {row.statement_period_id for row in linked})

        self.assertEqual(result.unlinked_rows, 6)
        self.assertEqual(
            result.document.metadata_[AMBIGUOUS_PERIOD_METADATA_KEY], [IBAN]
        )

    def test_one_span_stated_twice_with_different_figures_is_refused(self):
        """Only one of the two claims could be stored, so neither is.

        Storing either would put one of a document's two contradictory claims
        on the record as though the document had made it alone -- and the
        arithmetic that a later reconciliation runs would then be arithmetic
        over a figure the document also denied.
        """
        with self.assertRaises(ContradictoryPeriodError) as caught:
            self.ingest(
                camt_bytes(
                    statements=stmt(identification="A") + disagreeing("B")
                )
            )
        message = str(caught.exception)
        self.assertIn(IBAN, message)
        self.assertIn("2026-02-01..2026-02-28", message)
        self.assertIn("different figures", message)

    def test_a_refused_contradiction_writes_no_rows(self):
        """The refusal lands before the rows, because periods come first."""
        with self.assertRaises(ContradictoryPeriodError):
            self.ingest(
                camt_bytes(
                    statements=stmt(identification="A") + disagreeing("B")
                )
            )
        self.db.rollback()
        self.assertEqual(self.stored_rows(), [])

    def test_a_format_that_states_no_period_leaves_rows_unlinked_and_uncounted(
        self,
    ):
        """NACHA's rows are period-less and none of them is a loss.

        A NACHA file is a batch of payment instructions, not a statement; it
        states no span at all, so there is nothing its rows failed to be linked
        to.  Counting them as unlinked would report a file that is exactly what
        it should be as a file with something missing, and the count is what a
        reviewer would be shown.
        """
        result = self.ingest(nacha_bytes(NACHA_SIMPLE))
        self.assertEqual(result.periods, ())
        self.assertEqual(result.unlinked_rows, 0)
        self.assertEqual(
            {row.statement_period_id for row in self.stored_rows()}, {None}
        )
        self.assertNotIn(
            AMBIGUOUS_PERIOD_METADATA_KEY, result.document.metadata_
        )


# ---------------------------------------------------------------------------
# What the document says about itself
# ---------------------------------------------------------------------------


class DocumentMetadataTests(NativeIngestTestCase):
    """The three facts the driver derives rather than copies."""

    def test_the_reservations_are_written_even_when_there_are_none(self):
        """An absent key means nobody asked; an empty list means nobody found any.

        ``reclassify_after_reconciliation`` is given the reservations directly
        and acts on them, but it decides a class and keeps no list.  Without
        this key the *reasons* would not survive the ingestion that acted on
        them, and a reviewer asking why a perfectly balanced document sits at
        p3 would have no answer on the record.
        """
        result = self.ingest(camt_bytes())
        self.assertEqual(result.document.metadata_[RESERVATIONS_METADATA_KEY], [])

    def test_a_reservation_reaches_the_document(self):
        reading = read_native(
            camt_bytes(
                statements=stmt().replace(
                    "<Acct>", "<CpyDplctInd>DUPL</CpyDplctInd><Acct>"
                )
            ),
            window=WINDOW,
        )
        self.assertEqual(len(reading.admissibility_reservations), 1)

        result = self.ingest_reading(reading)
        self.assertEqual(
            result.document.metadata_[RESERVATIONS_METADATA_KEY],
            list(reading.admissibility_reservations),
        )

    def test_the_callers_metadata_is_kept_alongside(self):
        result = self.ingest(camt_bytes(), metadata={"received_from": "counsel"})
        self.assertEqual(result.document.metadata_["received_from"], "counsel")
        self.assertIn(RESERVATIONS_METADATA_KEY, result.document.metadata_)

    def test_one_currency_is_recorded_on_the_document(self):
        result = self.ingest(camt_bytes())
        self.assertEqual(result.document.currency, "USD")

    def test_two_currencies_leave_the_document_without_one(self):
        """A document holding two currencies has no currency.

        Recording either would make a reader believe the other's totals were
        denominated in it, and totals are what this record exists to support.
        """
        eur_balances = bal(
            CAMT053_BALANCE_OPENING_BOOKED, "10000.00", currency="EUR"
        ) + bal(
            CAMT053_BALANCE_CLOSING_BOOKED,
            "12500.00",
            currency="EUR",
            date="2026-02-28",
        )
        eur_entries = (
            ntry("3000.00", "CRDT", currency="EUR", reference="F1")
            + ntry("2000.00", "CRDT", currency="EUR", reference="F2")
            + ntry("2500.00", "DBIT", currency="EUR", reference="F3")
        )
        result = self.ingest(
            camt_bytes(
                statements=stmt(identification="A")
                + stmt(
                    identification="B",
                    account=EUR_ACCOUNT,
                    balances=eur_balances,
                    entries=eur_entries,
                )
            )
        )
        self.assertEqual(
            {account.currency for account in result.accounts}, {"USD", "EUR"}
        )
        self.assertIsNone(result.document.currency)

    def test_the_institution_the_accounts_agree_on_is_recorded(self):
        result = self.ingest(nacha_bytes(NACHA_SIMPLE))
        self.assertEqual(
            result.document.institution_name,
            result.accounts[0].institution_name,
        )
        self.assertIsNotNone(result.document.institution_name)

    def test_a_caller_naming_the_institution_is_not_second_guessed(self):
        result = self.ingest(camt_bytes(), institution_name="National Westminster")
        self.assertEqual(result.document.institution_name, "National Westminster")


# ---------------------------------------------------------------------------
# What the run counted
# ---------------------------------------------------------------------------


class RunCountTests(NativeIngestTestCase):
    """Counting is the driver's, and it happens exactly once.

    ``record_transactions`` deliberately does not touch the run counters --
    "a writer that counts plus a driver that counts is a run reporting twice
    what it ingested" -- so these tests are the only place the arrangement is
    checked from the outside.
    """

    def test_one_document_and_its_rows_are_counted_once_each(self):
        reading = read_native(camt_bytes(), window=WINDOW)
        self.ingest_reading(reading)
        counts = self.run.counts
        self.assertEqual(counts.documents_seen, 1)
        self.assertEqual(counts.transactions_admitted, len(reading.rows))
        self.assertEqual(counts.transactions_quarantined, 0)

    def test_two_documents_accumulate(self):
        first = read_native(camt_bytes(), window=WINDOW)
        second = read_native(nacha_bytes(NACHA_SIMPLE), window=WINDOW)
        self.ingest_reading(first, sha256=HASH_A)
        self.ingest_reading(second, sha256=HASH_B)

        counts = self.run.counts
        self.assertEqual(counts.documents_seen, 2)
        self.assertEqual(
            counts.transactions_admitted, len(first.rows) + len(second.rows)
        )

    def test_nothing_is_quarantined_by_this_path(self):
        """Native rows are admitted; a whole file is refused or none of it is.

        Quarantine is a per-row outcome and this driver has no per-row failure
        mode: a row it cannot attribute stops the document, and a row it can is
        written.  A count above zero here would mean a row was written into a
        state nothing in this module can produce.
        """
        self.ingest(camt_bytes())
        self.assertEqual(self.run.counts.transactions_quarantined, 0)


# ---------------------------------------------------------------------------
# Where the document ends up
# ---------------------------------------------------------------------------


class ReclassificationTests(NativeIngestTestCase):
    """The last stage, and the reason it is last.

    A document is admitted before anything can grade it -- the arithmetic runs
    over statement periods and transactions, and those reference the document,
    so the document has to exist first.  Reclassification therefore happens
    after the rows are written, and these tests are what would fail if it were
    moved earlier for tidiness: the rows would keep the admission class and
    every total that filters on class would quietly omit them.
    """

    def test_a_balanced_document_is_promoted_and_takes_its_rows_with_it(self):
        result = self.ingest(camt_bytes())
        self.assertEqual(result.document.proof_class, ProofClass.p0.value)
        self.assertIsNotNone(result.adjudication)
        self.assertEqual(
            {row.proof_class for row in self.stored_rows()},
            {ProofClass.p0.value},
        )

    def test_a_reserved_document_stays_at_the_admission_class(self):
        """Balanced arithmetic is not enough when the file said not to trust it.

        A ``DUPL`` statement's totals are not merely sound, they are identical
        to the original's, so nothing in the arithmetic can catch it.  The
        reservation is the only thing standing between a duplicate and being
        counted twice at p0.
        """
        result = self.ingest(
            camt_bytes(
                statements=stmt().replace(
                    "<Acct>", "<CpyDplctInd>DUPL</CpyDplctInd><Acct>"
                )
            )
        )
        self.assertEqual(result.document.proof_class, ProofClass.p3.value)
        self.assertIsNone(result.adjudication)
        self.assertEqual(
            {row.proof_class for row in self.stored_rows()},
            {ProofClass.p3.value},
        )

    def test_the_rows_are_written_before_the_class_moves(self):
        """Stated as its own test because the ordering is invisible in the result.

        Both orderings produce a promoted document.  Only one produces promoted
        rows, and a suite that checked the document alone would pass against a
        driver that reclassified first and left every row behind at p3.
        """
        result = self.ingest(camt_bytes())
        self.assertEqual(len(self.stored_rows()), 3)
        self.assertEqual(
            {row.proof_class for row in self.stored_rows()},
            {result.document.proof_class},
        )


# ---------------------------------------------------------------------------
# What the driver will not be called with
# ---------------------------------------------------------------------------


class ArgumentTests(NativeIngestTestCase):
    """The guards under test here are the driver's, not the schema's.

    These call :func:`ingest_native_reading` directly rather than through the
    ``ingest_reading`` helper, because that helper passes the hash on to the
    ``EvidenceFile`` row it creates.  Routed through it, a blank or absent hash
    raises ``IntegrityError`` from a NOT NULL constraint before the driver is
    ever entered -- so the test would pass while saying nothing about the
    driver, and would go on passing if the driver's own guard were deleted.
    The evidence file below therefore carries a *valid* hash, and only the
    argument being tested is malformed.
    """

    def refuse(self, reading, **kwargs):
        """Call the driver with one deliberately malformed argument."""
        evidence_file = self.evidence(HASH_A)
        with self.assertRaises(IngestionError) as caught:
            ingest_native_reading(
                self.db,
                self.run,
                reading,
                evidence_file_id=evidence_file.id,
                window=WINDOW,
                **kwargs,
            )
        return str(caught.exception)

    def test_a_loose_mapping_is_not_a_reading(self):
        """This writes what a parser read, and cannot take a dictionary.

        A mapping that happened to carry the right keys would be a reading
        nobody parsed, stored with a parser name and version that named a
        parser which never saw the file.
        """
        message = self.refuse({"rows": [], "format": "camt053"}, sha256=HASH_A)
        self.assertIn("NativeReading", message)

    def test_a_missing_hash_is_refused(self):
        """The hash is doing two jobs, and both of them fail silently.

        It is what the document records as its own digest, and it is what
        distinguishes this document's unnamed accounts from every other
        document's.  A blank one would merge two unrelated cases' unnamed
        accounts into a single identity.
        """
        reading = read_native(camt_bytes(), window=WINDOW)
        for value in ("", "   ", "\t\n"):
            with self.subTest(value=repr(value)):
                self.assertIn("sha256 is required", self.refuse(reading, sha256=value))

    def test_a_hash_that_is_not_a_string_is_refused(self):
        """``None`` and a bytes digest are the two ways this arrives wrong.

        ``None`` is an unset variable reaching the driver; bytes is a caller
        handing over ``hashlib.sha256(...).digest()`` instead of its
        ``.hexdigest()``.  Neither is caught by a truthiness check, which is
        why the guard tests the type before it strips.
        """
        reading = read_native(camt_bytes(), window=WINDOW)
        for value in (None, b"\x00" * 32, 0):
            with self.subTest(value=repr(value)):
                self.assertIn("sha256 is required", self.refuse(reading, sha256=value))

    def test_no_document_survives_a_refused_argument(self):
        """A guard that raised after writing would leave an orphan document.

        The checks run before ``record_source_document``, so a refusal must
        leave the case exactly as it was.  Asserting on the exception alone
        would not notice a driver that wrote first and validated second.
        """
        reading = read_native(camt_bytes(), window=WINDOW)
        self.refuse(reading, sha256="")
        self.assertEqual(self.stored_rows(), [])
        self.assertEqual(self.stored_periods(), [])
        self.assertEqual(
            list(self.db.execute(select(FinancialSourceDocument)).scalars()), []
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
