"""Tests for the adapter that names the accounts a native file is about.

The corpus caveat from ``test_financial_native`` applies again and compounds
once more: these fixtures are the four parser suites' builders, read through
the row adapter, read again here.  Nothing below is independent evidence that
any parser is right.  What it is evidence for is the seam this module owns --
that the accounts it names are the accounts the rows point at, that a period is
claimed only where the file claims one, and that the two cases which would put
one account's money on another are refused rather than guessed.

:class:`SubjectJoinTests` carries most of the weight and is the reason the
module exists.  ``account_key`` is the only join between a row and an account,
so a subject whose key is derived even slightly differently from the row
adapter's produces rows that match no account at all.  The test asserts the
containment directly, for all four formats, against the real row adapter --
which is the only form of the check that would survive someone "tidying" one
of the two derivations and not the other.

:class:`UnidentifiedAccountTests` pins the refusal.  One statement that prints
no identifier is an ordinary unidentified account.  Two in one file is not:
every row of both carries ``account_key=None``, nothing is left to attribute
them by, and storing them would merge two accounts inside one matter.  The
refusal is asserted, and so is the case just below it -- that one such
statement still works -- because a guard that refused both would be indistinguishable
from a correct one on the failing test alone.

:class:`PeriodClaimTests` pins what a period *is*.  BAI2 states an as-of date
and not a span, so only its end bound is printed; NACHA states no coverage for
anybody and gets no period at all.  Both are asserted as the file's own claim
rather than as an implementation detail, because the tempting change in both
cases is to fill the missing half in and make the shapes uniform.
"""

from __future__ import annotations

import datetime
import unittest

from postgres.models.enums import PeriodBoundsSource
from services.financial.native import CenturyWindow, NativeFormat, read_native
from services.financial.native_subjects import (
    AccountSubject,
    PeriodFacts,
    SubjectError,
    describe_subjects,
)

# The same builders the row-adapter suite imports, for the same reason: a copy
# of any of these fixtures here would drift from its origin silently.
from tests.test_financial_bai2 import file_of
from tests.test_financial_camt053 import build as camt_build, stmt
from tests.test_financial_mt940 import message
from tests.test_financial_nacha import (
    batch_control,
    batch_header,
    entry,
    file_control,
    file_header,
    joined,
)
from tests.test_financial_native import (
    WINDOW,
    bai2_bytes,
    camt_bytes,
    mt940_bytes,
    nacha_bytes,
    NACHA_SIMPLE,
)

D = datetime.date

#: An account element printing no identifier at all -- no IBAN, no ``Othr``.
#: ``Camt053Account.identifier`` is ``Optional`` and returns ``None`` here,
#: which is the case the indistinguishability guard exists for.
NO_IDENTIFIER = '<Acct><Ccy>USD</Ccy><Ownr><Nm>Unnamed Co</Nm></Ownr></Acct>'

#: A second identified account, for files that name two.
OTHER_ACCOUNT = '<Acct><Id><Othr><Id>ACCT-999</Id></Othr></Id><Ccy>USD</Ccy></Acct>'

#: An identifier the placeholder guard rejects.  The account is named on the
#: page and the name is a non-value, which is not the same as unnamed.
PLACEHOLDER = '<Acct><Id><Othr><Id>N/A</Id></Othr></Id><Ccy>USD</Ccy></Acct>'


class SubjectTestCase(unittest.TestCase):
    """Shared readings.  Every fixture goes through the real row adapter."""

    def subjects(self, data: bytes, *, distinguisher: str = "sha256:test", **kw):
        reading = read_native(data, window=WINDOW, **kw)
        return reading, describe_subjects(
            reading, window=WINDOW, distinguisher=distinguisher
        )

    def camt(self, account: str | None = None, **kw):
        return self.subjects(camt_build(statements=stmt(account=account)), **kw)


# ---------------------------------------------------------------------------
# The invariant the module exists to hold
# ---------------------------------------------------------------------------


class SubjectJoinTests(SubjectTestCase):
    """Every row's account key is a key some subject claims.

    This is the whole contract.  ``account_key`` is the only thing connecting a
    stored row to a stored account, and the two strings are computed in two
    different modules -- the row adapter in ``native`` and the subject adapter
    here.  If they ever disagree, rows land against an account that was never
    written, and nothing later in the pipeline can notice.
    """

    def assertJoins(self, reading, subjects) -> None:
        row_keys = {row.account_key for row in reading.rows}
        subject_keys = {subject.account_key for subject in subjects}
        missing = row_keys - subject_keys
        self.assertEqual(
            missing,
            set(),
            f"{len(missing)} row account key(s) name no subject: {sorted(map(str, missing))}",
        )

    def test_camt053_rows_all_reach_a_subject(self) -> None:
        self.assertJoins(*self.subjects(camt_bytes()))

    def test_bai2_rows_all_reach_a_subject(self) -> None:
        self.assertJoins(*self.subjects(bai2_bytes(), default_currency="USD"))

    def test_mt940_rows_all_reach_a_subject(self) -> None:
        self.assertJoins(*self.subjects(mt940_bytes()))

    def test_nacha_rows_all_reach_a_subject(self) -> None:
        self.assertJoins(*self.subjects(nacha_bytes(NACHA_SIMPLE)))

    def test_a_file_naming_two_accounts_joins_both(self) -> None:
        reading, subjects = self.subjects(
            camt_build(
                statements=stmt(identification="S1")
                + stmt(identification="S2", account=OTHER_ACCOUNT)
            )
        )
        self.assertEqual(len(subjects), 2)
        self.assertJoins(reading, subjects)
        self.assertEqual(
            [subject.account_key for subject in subjects],
            ["GB29NWBK60161331926819", "ACCT-999"],
        )

    def test_subjects_are_returned_in_file_order(self) -> None:
        _, subjects = self.subjects(
            camt_build(
                statements=stmt(identification="S1", account=OTHER_ACCOUNT)
                + stmt(identification="S2")
            )
        )
        self.assertEqual(
            [subject.account_key for subject in subjects],
            ["ACCT-999", "GB29NWBK60161331926819"],
        )


# ---------------------------------------------------------------------------
# What each format claims about coverage
# ---------------------------------------------------------------------------


class PeriodClaimTests(SubjectTestCase):
    """A period is recorded only where the file claims one, and only as claimed."""

    def test_camt053_prints_both_bounds(self) -> None:
        _, subjects = self.camt()
        bounds = subjects[0].period.bounds
        self.assertEqual(bounds.start, D(2026, 2, 1))
        self.assertEqual(bounds.end, D(2026, 2, 28))
        self.assertIs(bounds.start_source, PeriodBoundsSource.printed)
        self.assertIs(bounds.end_source, PeriodBoundsSource.printed)

    def test_camt053_carries_its_printed_balances(self) -> None:
        _, subjects = self.camt()
        period = subjects[0].period
        self.assertEqual(period.currency, "USD")
        self.assertEqual(str(period.opening.amount), "10,000.00 USD")
        self.assertEqual(str(period.closing.amount), "12,500.00 USD")

    def test_bai2_states_an_end_and_no_start(self) -> None:
        """BAI2 dates the group as of a moment; it does not state a span.

        The start is absent rather than invented.  A fabricated start would
        assert coverage the file never claimed, and would do it in the one
        field a later stage uses to argue that a statement is missing.
        """
        _, subjects = self.subjects(bai2_bytes(), default_currency="USD")
        bounds = subjects[0].period.bounds
        self.assertIsNone(bounds.start)
        self.assertIs(bounds.start_source, PeriodBoundsSource.absent)
        self.assertEqual(bounds.end, D(2024, 1, 15))
        self.assertIs(bounds.end_source, PeriodBoundsSource.printed)

    def test_a_half_open_period_cannot_argue_continuity(self) -> None:
        _, subjects = self.subjects(bai2_bytes(), default_currency="USD")
        self.assertFalse(subjects[0].period.bounds.supports_continuity)

    def test_mt940_takes_both_bounds_from_its_balances(self) -> None:
        _, subjects = self.subjects(mt940_bytes())
        bounds = subjects[0].period.bounds
        self.assertEqual(bounds.start, D(2024, 1, 15))
        self.assertEqual(bounds.end, D(2024, 1, 16))
        self.assertIs(bounds.start_source, PeriodBoundsSource.printed)
        self.assertIs(bounds.end_source, PeriodBoundsSource.printed)

    def test_nacha_claims_no_period_for_anybody(self) -> None:
        """The absence is the finding, not a gap to be filled.

        A period asserts that a document covers an account between two dates
        and closes over it.  NACHA is a batch of instructions: it prints no
        balance for any account in it and closes over none of them.
        """
        _, subjects = self.subjects(nacha_bytes(NACHA_SIMPLE))
        self.assertTrue(subjects)
        for subject in subjects:
            self.assertIsNone(subject.period)


class NachaSubjectTests(SubjectTestCase):
    """A NACHA file describes many accounts and is about none of them."""

    def file_with(self, *entries: str) -> bytes:
        count = len(entries)
        return joined(
            [
                file_header(),
                batch_header(),
                *entries,
                batch_control(
                    count=count, entry_hash=2100002 * count, credits=150000 * count
                ),
                file_control(
                    count=count, entry_hash=2100002 * count, credits=150000 * count
                ),
            ]
        ).encode("utf-8")

    def test_the_account_is_the_receivers(self) -> None:
        _, subjects = self.subjects(nacha_bytes(NACHA_SIMPLE))
        self.assertEqual(subjects[0].account_key, "021000021/111111")
        self.assertEqual(subjects[0].draft.holder_name, "ALICE SMITH")

    def test_one_subject_per_distinct_receiver_not_per_row(self) -> None:
        """Three entries, two receivers, and the repeat does not make a third."""
        reading, subjects = self.subjects(
            self.file_with(
                entry(account="111111", name="ALICE SMITH", trace="091000010000001"),
                entry(account="222222", name="BOB JONES", trace="091000010000002"),
                entry(account="111111", name="ALICE SMITH", trace="091000010000003"),
            )
        )
        self.assertEqual(len(reading.rows), 3)
        self.assertEqual(len(subjects), 2)
        self.assertEqual(
            [subject.account_key for subject in subjects],
            ["021000021/111111", "021000021/222222"],
        )

    def test_the_originator_is_the_institution_not_an_account(self) -> None:
        """The ``5`` record names a company but prints it no account.

        Recording the originator as an account of its own would invent an
        identifier the file does not contain.  Its name is kept where it is
        true instead: this is who paid the receiver.
        """
        _, subjects = self.subjects(nacha_bytes(NACHA_SIMPLE))
        self.assertEqual(subjects[0].draft.institution_name, "OWL CONSULTANCY")
        keys = {subject.account_key for subject in subjects}
        self.assertNotIn("OWL CONSULTANCY", keys)

    def test_the_routing_number_is_carried_onto_the_draft(self) -> None:
        _, subjects = self.subjects(nacha_bytes(NACHA_SIMPLE))
        self.assertEqual(subjects[0].draft.routing_number, "021000021")


# ---------------------------------------------------------------------------
# Accounts the document could not name
# ---------------------------------------------------------------------------


class UnidentifiedAccountTests(SubjectTestCase):
    """The two cases that would otherwise merge one account into another."""

    def test_a_statement_printing_no_identifier_becomes_unidentified(self) -> None:
        _, subjects = self.camt(NO_IDENTIFIER, distinguisher="sha256:abc")
        self.assertEqual(len(subjects), 1)
        subject = subjects[0]
        self.assertIsNone(subject.account_key)
        self.assertEqual(subject.draft.distinguisher, "sha256:abc:0")
        self.assertEqual(subject.draft.identity().tier, "unidentified")

    def test_what_the_page_did_say_is_still_kept(self) -> None:
        _, subjects = self.camt(NO_IDENTIFIER)
        self.assertEqual(subjects[0].draft.holder_name, "Unnamed Co")

    def test_two_unidentified_accounts_in_one_file_are_refused(self) -> None:
        """Their rows are indistinguishable, so attributing them is guessing."""
        with self.assertRaises(SubjectError) as caught:
            self.subjects(
                camt_build(
                    statements=stmt(identification="S1", account=NO_IDENTIFIER)
                    + stmt(identification="S2", account=NO_IDENTIFIER)
                )
            )
        message_text = str(caught.exception)
        self.assertIn("print no identifier", message_text)
        self.assertIn("account key", message_text)

    def test_one_unidentified_beside_an_identified_one_is_fine(self) -> None:
        """The guard counts unnamed accounts, not accounts.

        Asserted because a guard that refused this too would pass the refusal
        test above and still be wrong: only one of the two files has rows that
        cannot be told apart.
        """
        reading, subjects = self.subjects(
            camt_build(
                statements=stmt(identification="S1", account=NO_IDENTIFIER)
                + stmt(identification="S2", account=OTHER_ACCOUNT)
            )
        )
        self.assertEqual(len(subjects), 2)
        self.assertEqual(
            [subject.account_key for subject in subjects], [None, "ACCT-999"]
        )
        self.assertEqual(
            {row.account_key for row in reading.rows} - {None}, {"ACCT-999"}
        )

    def test_two_identified_statements_for_one_account_are_not_the_refusal(self) -> None:
        """A combined file holding two statements for one account is ordinary."""
        _, subjects = self.subjects(
            camt_build(
                statements=stmt(identification="S1") + stmt(identification="S2")
            )
        )
        self.assertEqual(len(subjects), 2)
        self.assertEqual(
            {subject.account_key for subject in subjects},
            {"GB29NWBK60161331926819"},
        )

    def test_a_placeholder_identifier_falls_back_to_unidentified(self) -> None:
        """``N/A`` is a non-value, and the guard in ``accounts`` rejects it.

        The fallback is to record an account this document could not name --
        not to force the placeholder through as though it identified anybody.
        """
        _, subjects = self.camt(PLACEHOLDER, distinguisher="sha256:def")
        subject = subjects[0]
        self.assertEqual(subject.draft.distinguisher, "sha256:def:0")
        self.assertEqual(subject.draft.identity().tier, "unidentified")

    def test_the_placeholder_is_still_recorded_as_printed(self) -> None:
        """The page said ``N/A`` and the page is the evidence."""
        _, subjects = self.camt(PLACEHOLDER)
        self.assertEqual(subjects[0].draft.identifier_as_printed, "N/A")

    def test_the_placeholder_still_joins_its_rows(self) -> None:
        """The key stays the printed string even though the draft is unnamed.

        The key answers "which rows are these"; the draft answers "whose
        account is this".  Conflating them would strand the rows.
        """
        reading, subjects = self.camt(PLACEHOLDER)
        self.assertEqual(subjects[0].account_key, "N/A")
        self.assertEqual({row.account_key for row in reading.rows}, {"N/A"})


class DistinguisherTests(SubjectTestCase):
    """The distinguisher is what stops two files' unnamed accounts merging."""

    def test_it_is_required(self) -> None:
        reading = read_native(camt_bytes(), window=WINDOW)
        with self.assertRaises(SubjectError) as caught:
            describe_subjects(reading, window=WINDOW, distinguisher="")
        self.assertIn("distinguisher", str(caught.exception))

    def test_whitespace_is_not_a_distinguisher(self) -> None:
        reading = read_native(camt_bytes(), window=WINDOW)
        with self.assertRaises(SubjectError):
            describe_subjects(reading, window=WINDOW, distinguisher="   ")

    def test_two_documents_unnamed_accounts_do_not_collide(self) -> None:
        """The property the whole guard rests on.

        A bare positional counter would give every file's first unnamed
        account the same key, which is the merge this is here to prevent.
        """
        _, first = self.camt(NO_IDENTIFIER, distinguisher="sha256:aaa")
        _, second = self.camt(NO_IDENTIFIER, distinguisher="sha256:bbb")
        self.assertNotEqual(
            first[0].draft.identity().key, second[0].draft.identity().key
        )

    def test_re_reading_one_document_reaches_the_same_account(self) -> None:
        _, first = self.camt(NO_IDENTIFIER, distinguisher="sha256:aaa")
        _, again = self.camt(NO_IDENTIFIER, distinguisher="sha256:aaa")
        self.assertEqual(
            first[0].draft.identity().key, again[0].draft.identity().key
        )


# ---------------------------------------------------------------------------
# Dates the window cannot read
# ---------------------------------------------------------------------------


class WindowTests(SubjectTestCase):
    """A bound the window cannot resolve is recorded absent, not raised.

    ``read_native`` resolves MT940's ``:61:`` line dates and never its
    ``:60a:``/``:62a:`` balance dates, so a statement stamped outside the
    engagement's window whose lines fall inside it parses, reads, and arrives
    here with two dates that have no reading.  Discarding the statement over
    its bounds alone would throw away rows, amounts and balances that are all
    perfectly good.
    """

    OUT_OF_WINDOW = message(
        ":20:MIN",
        ":25:ACCOUNT",
        ":28C:1",
        ":60F:C190115USD100,00",
        ":61:2401150115C50,00NTRFREF//BANKREF",
        ":62F:C190116USD150,00",
    )

    def test_the_statement_still_reads(self) -> None:
        reading, subjects = self.subjects(self.OUT_OF_WINDOW.encode("utf-8"))
        self.assertEqual(len(reading.rows), 1)
        self.assertEqual(len(subjects), 1)

    def test_the_bounds_are_absent_rather_than_wrong(self) -> None:
        _, subjects = self.subjects(self.OUT_OF_WINDOW.encode("utf-8"))
        bounds = subjects[0].period.bounds
        self.assertIsNone(bounds.start)
        self.assertIsNone(bounds.end)
        self.assertIs(bounds.start_source, PeriodBoundsSource.absent)
        self.assertIs(bounds.end_source, PeriodBoundsSource.absent)

    def test_the_balances_are_kept_even_though_their_dates_were_not(self) -> None:
        """The amounts were readable; only the dates were not."""
        _, subjects = self.subjects(self.OUT_OF_WINDOW.encode("utf-8"))
        period = subjects[0].period
        self.assertEqual(str(period.opening.amount), "100.00 USD")
        self.assertEqual(str(period.closing.amount), "150.00 USD")

    def test_a_bai2_group_stating_no_date_leaves_both_bounds_absent(self) -> None:
        text = file_of(
            "01,SENDER,RECEIVER,240115,0800,1,,,2/",
            "02,RECEIVER,BANK,1,,0800,USD,2/",
            "03,1234567890,USD,010,10000,,,015,15000,,,100,8000,2,,400,3000,1,/",
            "16,165,5000,0,REF1,CUST1,Deposit one/",
            "16,165,3000,0,REF2,CUST2,Deposit two/",
            "49,47000,5/",
            "98,47000,1,7/",
            "99,47000,1,9/",
        )
        _, subjects = self.subjects(text.encode("utf-8"), default_currency="USD")
        bounds = subjects[0].period.bounds
        self.assertIsNone(bounds.start)
        self.assertIsNone(bounds.end)


# ---------------------------------------------------------------------------
# Shape of what is returned
# ---------------------------------------------------------------------------


class ReturnShapeTests(SubjectTestCase):
    """The adapter writes nothing and returns facts, not rows."""

    def test_subjects_are_returned_as_a_tuple(self) -> None:
        _, subjects = self.camt()
        self.assertIsInstance(subjects, tuple)
        self.assertIsInstance(subjects[0], AccountSubject)

    def test_a_period_is_a_period_facts(self) -> None:
        _, subjects = self.camt()
        self.assertIsInstance(subjects[0].period, PeriodFacts)

    def test_subjects_are_frozen(self) -> None:
        _, subjects = self.camt()
        with self.assertRaises(Exception):
            subjects[0].account_key = "changed"

    def test_every_native_format_has_an_adapter(self) -> None:
        """A format that parses but cannot be attributed would strand its rows.

        Asserted over the enum rather than over a list written here, so that
        adding a fifth parser fails this test instead of silently reaching the
        refusal at run time.
        """
        covered = {
            NativeFormat.camt053,
            NativeFormat.bai2,
            NativeFormat.mt940,
            NativeFormat.nacha,
        }
        self.assertEqual(set(NativeFormat), covered)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
